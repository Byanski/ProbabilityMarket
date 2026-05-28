import logging
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TeamStatsConnector:
    """Fetches roster and player performance context from public sport stats APIs."""

    mlb_host = "https://statsapi.mlb.com/api/v1"

    def __init__(self, timeout_seconds: float = 8.0) -> None:
        self.timeout = httpx.Timeout(timeout_seconds)

    async def fetch_team_roster(self, category_key: str, team_name: str) -> dict[str, Any]:
        if category_key != "baseball_mlb":
            return {
                "status": "unsupported",
                "team_name": team_name,
                "message": "Roster drilldown is currently implemented for MLB teams. Add a stats connector for this sport to enable player-level views.",
                "players": [],
            }

        team = await self._find_mlb_team(team_name)
        if not team:
            return {
                "status": "not_found",
                "team_name": team_name,
                "message": "No matching MLB team was found.",
                "players": [],
            }

        roster_payload = await self._get_json(f"{self.mlb_host}/teams/{team['id']}/roster", params={"rosterType": "active"})
        roster = roster_payload.get("roster", []) if isinstance(roster_payload, dict) else []
        person_ids = [
            str(item.get("person", {}).get("id"))
            for item in roster
            if isinstance(item, dict) and item.get("person", {}).get("id")
        ]
        people = await self._fetch_mlb_people(person_ids)

        players = []
        for item in roster:
            if not isinstance(item, dict):
                continue
            person_id = item.get("person", {}).get("id")
            person = people.get(person_id, {})
            position = item.get("position", {}) or {}
            season_stat = self._best_stat(person, position.get("type"))
            performance = self._performance_summary(season_stat, position.get("type"))
            players.append(
                {
                    "id": person_id,
                    "name": item.get("person", {}).get("fullName", "Unknown Player"),
                    "jersey_number": item.get("jerseyNumber", ""),
                    "position": position.get("abbreviation", ""),
                    "position_type": position.get("type", ""),
                    "status": (item.get("status", {}) or {}).get("description", ""),
                    "handedness": {
                        "bat": (person.get("batSide", {}) or {}).get("description", ""),
                        "pitch": (person.get("pitchHand", {}) or {}).get("description", ""),
                    },
                    "season_stat": season_stat,
                    "performance": performance,
                }
            )

        return {
            "status": "live",
            "category_key": category_key,
            "team": {
                "id": team["id"],
                "name": team["name"],
                "abbreviation": team.get("abbreviation", ""),
                "venue": (team.get("venue", {}) or {}).get("name", ""),
                "season": team.get("season", datetime.utcnow().year),
            },
            "players": players,
        }

    async def _find_mlb_team(self, team_name: str) -> dict[str, Any] | None:
        payload = await self._get_json(f"{self.mlb_host}/teams", params={"sportId": "1", "activeStatus": "Y"})
        teams = payload.get("teams", []) if isinstance(payload, dict) else []
        normalized = self._normalize_name(team_name)
        for team in teams:
            candidates = {
                team.get("name", ""),
                f"{team.get('locationName', '')} {team.get('teamName', '')}",
                team.get("shortName", ""),
                team.get("clubName", ""),
            }
            if normalized in {self._normalize_name(candidate) for candidate in candidates if candidate}:
                return team
        return None

    async def _fetch_mlb_people(self, person_ids: list[str]) -> dict[int, dict[str, Any]]:
        if not person_ids:
            return {}

        season = str(datetime.utcnow().year)
        hydrate = f"stats(group=[hitting,pitching],type=[season,seasonAdvanced],season={season})"
        payload = await self._get_json(
            f"{self.mlb_host}/people",
            params={"personIds": ",".join(person_ids), "hydrate": hydrate},
        )
        people = payload.get("people", []) if isinstance(payload, dict) else []
        return {person.get("id"): person for person in people if isinstance(person, dict)}

    async def _get_json(self, url: str, params: dict[str, str]) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Team stats fetch failed for %s: %s", url, exc)
            return None

    def _best_stat(self, person: dict[str, Any], position_type: str | None) -> dict[str, Any]:
        groups = ["pitching", "hitting"] if position_type == "Pitcher" else ["hitting", "pitching"]
        for preferred_group in groups:
            for stat_block in person.get("stats", []) or []:
                group = (stat_block.get("group", {}) or {}).get("displayName")
                stat_type = (stat_block.get("type", {}) or {}).get("displayName")
                splits = stat_block.get("splits") or []
                if group == preferred_group and stat_type == "season" and splits:
                    stat = splits[0].get("stat", {}) if isinstance(splits[0], dict) else {}
                    return self._select_stat_fields(stat, preferred_group)
        return {}

    def _select_stat_fields(self, stat: dict[str, Any], group: str) -> dict[str, Any]:
        if group == "pitching":
            fields = ("gamesPlayed", "wins", "losses", "era", "inningsPitched", "strikeOuts", "whip", "avg")
        else:
            fields = ("gamesPlayed", "avg", "obp", "slg", "ops", "homeRuns", "rbi", "runs", "stolenBases")
        return {field: stat.get(field) for field in fields if field in stat}

    def _performance_summary(self, stat: dict[str, Any], position_type: str | None) -> dict[str, Any]:
        if not stat:
            return {"direction": "neutral", "score": 0.0, "label": "No season sample yet"}

        if position_type == "Pitcher":
            era = self._float(stat.get("era"))
            whip = self._float(stat.get("whip"))
            if era is None:
                return {"direction": "neutral", "score": 0.0, "label": "Pitching sample building"}
            score = 0.5 - min(era, 9.0) / 18.0
            if whip is not None:
                score += 0.15 - min(whip, 2.0) / 10.0
        else:
            ops = self._float(stat.get("ops"))
            avg = self._float(stat.get("avg"))
            if ops is None and avg is None:
                return {"direction": "neutral", "score": 0.0, "label": "Hitting sample building"}
            score = ((ops or 0.68) - 0.7) * 0.9 + ((avg or 0.24) - 0.24) * 0.4

        score = max(min(score, 0.25), -0.25)
        if score > 0.04:
            return {"direction": "gain", "score": round(score, 4), "label": "Performance gain"}
        if score < -0.04:
            return {"direction": "decrease", "score": round(score, 4), "label": "Performance decrease"}
        return {"direction": "neutral", "score": round(score, 4), "label": "Stable performance"}

    def _float(self, value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_name(self, value: str) -> str:
        return " ".join(value.lower().replace(".", "").split())
