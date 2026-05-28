const state = {
  payload: null,
  activeCategoryKey: null,
};

const els = {
  statusDot: document.querySelector("#statusDot"),
  statusText: document.querySelector("#statusText"),
  warningPanel: document.querySelector("#warningPanel"),
  trackedRows: document.querySelector("#trackedRows"),
  meanIndex: document.querySelector("#meanIndex"),
  maxVariance: document.querySelector("#maxVariance"),
  statsBuckets: document.querySelector("#statsBuckets"),
  activeCategory: document.querySelector("#activeCategory"),
  matrixRows: document.querySelector("#matrixRows"),
  refreshButton: document.querySelector("#refreshButton"),
  tabs: document.querySelector("#tabs"),
  // New Modal Elements
  depthModal: document.querySelector("#depthModal"),
  modalTitle: document.querySelector("#modalTitle"),
  modalBody: document.querySelector("#modalBody"),
  closeModalBtn: document.querySelector("#closeModalBtn"),
};

async function loadPayload(categoryKey = state.activeCategoryKey) {
  setStatus("loading", "Refreshing");
  try {
    const params = new URLSearchParams();
    if (categoryKey) params.set("category_key", categoryKey);
    const response = await fetch(`/api/index?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.payload = await response.json();
    state.activeCategoryKey = state.payload.selected_category_key;
    render();
  } catch (error) {
    setStatus("error", "Disconnected");
    els.warningPanel.hidden = false;
    els.warningPanel.textContent = `Dashboard API is unavailable: ${error.message}`;
  }
}

function setStatus(status, label) {
  els.statusText.textContent = label;
  els.statusDot.classList.toggle("live", status === "live");
}

function render() {
  const payload = state.payload;
  if (!payload) return;

  setStatus(payload.status === "live" ? "live" : "placeholder", payload.status);
  renderWarnings(payload.warnings || []);
  renderTabs(payload.categories || []);
  renderSummary(payload);
  renderRows(payload.rows || []);
}

function renderTabs(categories) {
  els.tabs.innerHTML = categories
    .map(
      (category) => `
        <button
          class="tab ${category.key === state.activeCategoryKey ? "is-active" : ""}"
          type="button"
          data-category-key="${escapeHtml(category.key)}"
        >${escapeHtml(category.title)}</button>
      `,
    )
    .join("");
}

function renderWarnings(warnings) {
  els.warningPanel.hidden = warnings.length === 0;
  els.warningPanel.innerHTML = warnings.map((warning) => `<div>${escapeHtml(warning)}</div>`).join("");
}

function renderSummary(payload) {
  const rows = payload.rows || [];
  const meanIndex = rows.length
    ? rows.reduce((sum, row) => sum + row.normalized_probability, 0) / rows.length
    : 0;
  const maxVariance = rows.length
    ? Math.max(...rows.map((row) => row.highest_variance_vector))
    : 0;
  const stats = payload.stats || {};
  const statsBuckets =
    (stats.team_standings || []).length +
    (stats.historical_scores || []).length +
    (stats.player_availability || []).length;

  els.trackedRows.textContent = String(rows.length);
  els.meanIndex.textContent = meanIndex.toFixed(4);
  els.maxVariance.textContent = maxVariance.toFixed(4);
  els.statsBuckets.textContent = String(statsBuckets);
}

function renderRows(rows) {
  const category = (state.payload.categories || []).find((item) => item.key === state.activeCategoryKey);
  els.activeCategory.textContent = category ? category.title : "Source Category";
  if (rows.length === 0) {
    els.matrixRows.innerHTML = `<tr><td class="empty-state" colspan="9">No entries available for this category.</td></tr>`;
    return;
  }

  els.matrixRows.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td data-label="Target">${escapeHtml(row.target_matchup)}</td>
          <td data-label="Favorite">${escapeHtml(row.market_favorite || "n/a")}</td>
          <td data-label="Prediction">
            <strong>${escapeHtml(row.predicted_winner || "n/a")}</strong>
            <div class="subtle">${formatPercent(row.normalized_probability)}</div>
          </td>
          <td data-label="Confidence" class="numeric">${formatPercent(row.prediction_confidence)}</td>
          <td data-label="Markets">${escapeHtml((row.market_keys || []).join(", ") || "n/a")}</td>
          <td data-label="Lines" class="numeric">${escapeHtml(formatPoints(row.line_points || []))}</td>
          <td data-label="Adjustment" class="numeric">${formatSigned(row.adjustment_score)}</td>
          <td data-label="Sources" class="numeric">${row.source_count}</td>
          <td data-label="Action">
            <button class="action-btn" data-action="view-depth" data-event-id="${escapeHtml(row.id)}" data-matchup="${escapeHtml(row.target_matchup)}">
              Deep Dive
            </button>
          </td>
        </tr>
      `,
    )
    .join("");
}

function formatPoints(points) {
  return points.length ? points.map((point) => Number(point).toFixed(1)).join(" / ") : "n/a";
}

function formatVectors(vectors) {
  if (!vectors.length) return "n/a";
  return vectors
    .slice(0, 3)
    .map((vector) => {
      const point = vector.point === null || vector.point === undefined ? "" : ` @ ${Number(vector.point).toFixed(1)}`;
      return `${vector.source_title}: ${vector.market_key} ${vector.name} ${vector.price}${point}`;
    })
    .join(" | ");
}

function formatNumber(value) {
  return Number(value || 0).toFixed(4);
}

function formatSigned(value) {
  const number = Number(value || 0);
  return `${number > 0 ? "+" : ""}${number.toFixed(4)}`;
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function encodePathSegment(value) {
  return encodeURIComponent(String(value));
}

// --- Deep Dive Modal Logic ---

async function openDepthModal(eventId, matchup) {
  els.modalTitle.textContent = `Deep Dive: ${matchup}`;
  els.modalBody.innerHTML = `<p style="color: var(--muted);">Fetching live multi-source vectors...</p>`;
  els.depthModal.showModal();

  try {
    const categoryKey = state.activeCategoryKey;
    const response = await fetch(`/api/sports/${categoryKey}/events/${eventId}/odds`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    
    const data = await response.json();
    renderDepthView(data);
  } catch (error) {
    els.modalBody.innerHTML = `<p style="color: var(--warn);">Failed to load depth data: ${error.message}</p>`;
  }
}

function renderDepthView(data) {
  if (!data || !data.bookmakers || data.bookmakers.length === 0) {
    els.modalBody.innerHTML = `<p>No extended market data available for this event.</p>`;
    return;
  }

  const teamNames = [data.away_team, data.home_team].filter(Boolean);
  const teamButtons = teamNames
    .map(
      (team) => `
        <button class="team-pill" type="button" data-action="view-roster" data-team="${escapeHtml(team)}">
          ${escapeHtml(team)}
        </button>
      `,
    )
    .join("");

  let rowsHtml = "";
  data.bookmakers.forEach((source) => {
    source.markets.forEach((market) => {
      market.outcomes.forEach((outcome) => {
        const pointDisplay = outcome.point !== undefined && outcome.point !== null ? Number(outcome.point).toFixed(1) : "-";
        const updateTime = new Date(source.last_update).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        
        rowsHtml += `
          <tr>
            <td><strong>${escapeHtml(source.title)}</strong></td>
            <td>${escapeHtml(market.key)}</td>
            <td>${teamNames.includes(outcome.name) ? teamTargetButton(outcome.name) : escapeHtml(outcome.name)}</td>
            <td class="numeric">${formatNumber(outcome.price)}</td>
            <td class="numeric">${pointDisplay}</td>
            <td>${updateTime}</td>
          </tr>
        `;
      });
    });
  });

  els.modalBody.innerHTML = `
    <section class="team-drilldown">
      <p class="eyebrow">Team rosters</p>
      <div class="team-pill-row">${teamButtons}</div>
      <div id="rosterPanel" class="roster-panel" hidden></div>
    </section>
    <div class="modal-table-wrap">
      <table class="depth-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Market</th>
            <th>Target Vector</th>
            <th>Line Value</th>
            <th>Point Limit</th>
            <th>Last Update</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

function teamTargetButton(team) {
  return `
    <button class="link-button" type="button" data-action="view-roster" data-team="${escapeHtml(team)}">
      ${escapeHtml(team)}
    </button>
  `;
}

async function loadTeamRoster(teamName) {
  const panel = document.querySelector("#rosterPanel");
  if (!panel) return;
  panel.hidden = false;
  panel.innerHTML = `<p class="subtle">Loading roster and player performance for ${escapeHtml(teamName)}...</p>`;

  try {
    const response = await fetch(`/api/sports/${state.activeCategoryKey}/teams/${encodePathSegment(teamName)}/roster`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderRosterPanel(panel, data);
  } catch (error) {
    panel.innerHTML = `<p style="color: var(--warn);">Failed to load roster: ${escapeHtml(error.message)}</p>`;
  }
}

function renderRosterPanel(panel, data) {
  if (!data || data.status !== "live") {
    panel.innerHTML = `<p>${escapeHtml(data?.message || "Roster data is not available for this team.")}</p>`;
    return;
  }

  const players = data.players || [];
  const rows = players
    .map((player) => {
      const stat = player.season_stat || {};
      const performance = player.performance || {};
      return `
        <tr>
          <td><strong>${escapeHtml(player.name)}</strong><div class="subtle">#${escapeHtml(player.jersey_number || "-")} ${escapeHtml(player.status || "")}</div></td>
          <td>${escapeHtml(player.position || "-")}</td>
          <td>${escapeHtml(stat.ops || stat.era || stat.avg || stat.whip || "n/a")}</td>
          <td><span class="trend ${escapeHtml(performance.direction || "neutral")}">${escapeHtml(performance.label || "Stable")}</span></td>
          <td class="numeric">${formatSigned(performance.score || 0)}</td>
        </tr>
      `;
    })
    .join("");

  panel.innerHTML = `
    <div class="roster-heading">
      <strong>${escapeHtml(data.team.name)}</strong>
      <span>${escapeHtml(data.team.abbreviation || "")} · ${players.length} active players</span>
    </div>
    <div class="modal-table-wrap compact">
      <table class="depth-table">
        <thead>
          <tr>
            <th>Player</th>
            <th>Pos</th>
            <th>Key Stat</th>
            <th>Performance</th>
            <th>Delta</th>
          </tr>
        </thead>
        <tbody>${rows || `<tr><td colspan="5">No active roster rows available.</td></tr>`}</tbody>
      </table>
    </div>
  `;
}

// --- Event Listeners ---

els.tabs.addEventListener("click", (event) => {
  const tab = event.target.closest("[data-category-key]");
  if (!tab) return;
  state.activeCategoryKey = tab.dataset.categoryKey;
  loadPayload(state.activeCategoryKey);
});

els.refreshButton.addEventListener("click", () => loadPayload());

// Listen for clicks on the Deep Dive buttons
els.matrixRows.addEventListener("click", async (event) => {
  const btn = event.target.closest('[data-action="view-depth"]');
  if (!btn) return;
  const eventId = btn.dataset.eventId;
  const matchup = btn.dataset.matchup;
  await openDepthModal(eventId, matchup);
});

els.modalBody.addEventListener("click", async (event) => {
  const btn = event.target.closest('[data-action="view-roster"]');
  if (!btn) return;
  await loadTeamRoster(btn.dataset.team);
});

// Close Modal
els.closeModalBtn.addEventListener("click", () => {
  els.depthModal.close();
});

// Init
loadPayload();
