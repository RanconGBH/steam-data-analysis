// In production, replace this with your deployed back-end URL.
// Example: "https://your-service.example.com/api/steam-charts"
const API_URL = "";

let appearanceChart;
let rankChart;

const mockRecords = [
  { chartDate: "2026-09-01", rank: 1, game: "Example Quest", price: "$39.99", weeks: 4 },
  { chartDate: "2026-09-08", rank: 3, game: "Example Quest", price: "$39.99", weeks: 5 },
  { chartDate: "2026-09-01", rank: 6, game: "Sample Arena", price: "Free To Play", weeks: 17 },
  { chartDate: "2026-09-08", rank: 2, game: "Sample Arena", price: "Free To Play", weeks: 18 },
  { chartDate: "2026-09-08", rank: 9, game: "Demo Valley", price: "$24.99", weeks: 2 }
];

document.getElementById("month").value = new Date().toISOString().slice(0, 7);
document.getElementById("load-button").addEventListener("click", loadCharts);

async function loadCharts() {
  const [year, month] = document.getElementById("month").value.split("-");
  const region = document.getElementById("region").value;
  const status = document.getElementById("status");

  if (!year || !month) return (status.textContent = "Please choose a month first.");
  status.textContent = "Loading chart data…";

  try {
    // The fallback makes this site usable on GitHub Pages before a back end exists.
    const records = API_URL
      ? await fetch(`${API_URL}?year=${year}&month=${month}&region=${region}`).then(checkResponse).then(r => r.json())
      : mockRecords;

    renderTable(records);
    renderCharts(records);
    status.textContent = `${records.length} records loaded for ${month}/${year} (${region}).`;
  } catch (error) {
    status.textContent = `Could not load data: ${error.message}`;
  }
}

function checkResponse(response) {
  if (!response.ok) throw new Error(`Server returned ${response.status}`);
  return response;
}

function renderTable(records) {
  document.getElementById("results").innerHTML = records.map(r => `
    <tr><td>${r.chartDate}</td><td>${r.rank}</td><td>${r.game}</td><td>${r.price}</td><td>${r.weeks}</td></tr>`).join("");
}

function renderCharts(records) {
  const games = [...new Set(records.map(r => r.game))];
  const appearances = games.map(game => records.filter(r => r.game === game).length);
  const averageRanks = games.map(game => {
    const ranks = records.filter(r => r.game === game).map(r => r.rank);
    return ranks.reduce((sum, rank) => sum + rank, 0) / ranks.length;
  });

  appearanceChart?.destroy();
  rankChart?.destroy();
  appearanceChart = new Chart(document.getElementById("appearances-chart"), {
    type: "bar", data: { labels: games, datasets: [{ label: "Appearances", data: appearances, backgroundColor: "#2679ad" }] },
    options: { responsive: true }
  });
  rankChart = new Chart(document.getElementById("rank-chart"), {
    type: "bar", data: { labels: games, datasets: [{ label: "Average rank (lower is better)", data: averageRanks, backgroundColor: "#67a985" }] },
    options: { responsive: true, scales: { y: { reverse: true, beginAtZero: true } } }
  });
}
