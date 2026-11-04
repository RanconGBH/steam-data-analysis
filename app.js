let retentionChart;
let playersChart;

document.getElementById("month").value = new Date().toISOString().slice(0, 7);
document.getElementById("scrape-button").addEventListener("click", scrapeCharts);

async function scrapeCharts() {
  const [year, month] = document.getElementById("month").value.split("-");
  const limit = Number(document.getElementById("limit").value);
  const status = document.getElementById("status");
  const button = document.getElementById("scrape-button");

  if (!year || !month) return (status.textContent = "Please choose a chart month first.");
  button.disabled = true;
  status.textContent = "Scraping public chart and player data. Please keep this page open…";

  try {
    const response = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year: Number(year), month: Number(month), limit })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Server returned ${response.status}`);

    renderTable(payload.records);
    renderCharts(payload.records);
    status.textContent = `${payload.records.length} fresh records saved. ${payload.skipped} entries were skipped or could not be classified.`;
    document.getElementById("download-link").href = `data/latest_steam_retention.csv?updated=${Date.now()}`;
  } catch (error) {
    status.textContent = `Could not complete the scrape: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;"
  }[character]));
}

function formatNumber(value, digits = 0) {
  return value === null || value === undefined || value === ""
    ? "—"
    : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function renderTable(records) {
  document.getElementById("results").innerHTML = records.map(record => `
    <tr>
      <td><a href="${escapeHtml(record.steam_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(record.game)}</a></td>
      <td>${escapeHtml(record.analysis_bucket)}</td>
      <td>${formatNumber(record.sales_rank_proxy)}</td>
      <td>${escapeHtml(record.price_display)}</td>
      <td>${formatNumber(record.avg_players_last_30_days, 1)}</td>
      <td>${formatNumber(record.player_change_percent, 2)}%</td>
      <td>${formatNumber(record.activity_ratio_30d, 3)}</td>
    </tr>`).join("");
}

function average(values) {
  const usable = values.filter(value => Number.isFinite(value));
  return usable.length ? usable.reduce((sum, value) => sum + value, 0) / usable.length : null;
}

function summarize(records, field) {
  const buckets = ["Singleplayer", "Multiplayer"];
  return buckets.map(bucket => average(records
    .filter(record => record.analysis_bucket === bucket)
    .map(record => record[field] === null || record[field] === "" ? Number.NaN : Number(record[field]))));
}

function renderCharts(records) {
  const labels = ["Singleplayer", "Multiplayer"];
  retentionChart?.destroy();
  playersChart?.destroy();

  retentionChart = new Chart(document.getElementById("retention-chart"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Current 30-day activity ÷ prior 30-day activity", data: summarize(records, "activity_ratio_30d"), backgroundColor: "#2679ad" }] },
    options: { responsive: true, scales: { y: { beginAtZero: true } } }
  });
  playersChart = new Chart(document.getElementById("players-chart"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Average concurrent players", data: summarize(records, "avg_players_last_30_days"), backgroundColor: "#67a985" }] },
    options: { responsive: true, scales: { y: { beginAtZero: true } } }
  });
}
