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
          <td>${escapeHtml(row.target_matchup)}</td>
          <td>${escapeHtml((row.market_keys || []).join(", ") || "n/a")}</td>
          <td class="numeric">${escapeHtml(formatPoints(row.line_points || []))}</td>
          <td class="numeric">${formatNumber(row.aggregated_mean_value)}</td>
          <td class="numeric">${formatNumber(row.highest_variance_vector)}</td>
          <td class="numeric">${formatSigned(row.adjustment_score)}</td>
          <td class="numeric">${formatNumber(row.normalized_probability)}</td>
          <td class="numeric">${row.source_count}</td>
          <td>${escapeHtml(formatVectors(row.telemetry_vectors || []))}</td>
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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

els.tabs.addEventListener("click", (event) => {
  const tab = event.target.closest("[data-category-key]");
  if (!tab) return;
  state.activeCategoryKey = tab.dataset.categoryKey;
  loadPayload(state.activeCategoryKey);
});

els.refreshButton.addEventListener("click", () => loadPayload());

loadPayload();
