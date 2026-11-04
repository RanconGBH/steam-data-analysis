# Steam Chart Explorer

This is a no-key, local Flask dashboard that creates one fresh CSV per run. It combines:

- Steam Store's dated **Weekly Top Sellers** chart for rank and listed price;
- Steam Store feature labels for the game-type bucket; and
- SteamCharts' **Last 30 Days** row for concurrent-player activity.

## What the data means

`sales_rank_proxy` is a weekly revenue rank, **not** a count of purchases or units sold. The public pages do not reveal verified purchases for other developers' games.

`activity_ratio_30d` is calculated as:

```text
current 30-day average concurrent players / prior 30-day average concurrent players
```

It is a rolling audience-stability measure, not cohort retention from launch. `audience_per_dollar` is average concurrent players divided by current listed price; it excludes free-to-play games and does not measure revenue.

Games with any Steam Store multiplayer, co-op, or PvP feature are placed in **Multiplayer**. Titles with only a Single-player feature are placed in **Singleplayer**. The CSV retains both source flags so mixed-mode games can be identified later.

## Run locally

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`, choose a month and sample size, then select **Scrape and replace CSV**. The app clears `data/latest_steam_retention.csv` before the run and writes only fresh records.

## GitHub use

Commit this folder to a GitHub repository so the project and latest CSV can be version-controlled. GitHub Pages alone cannot run a Python scraper or write a CSV when a visitor clicks a button. To offer the live button publicly, deploy this Flask app on a Python-capable host; GitHub can remain the source repository.

## Responsible collection

The collector uses a clear User-Agent, checks robots.txt, limits requests to 30 games, pauses between requests, and does not bypass access controls. Review each source's current terms before broad or repeated collection.
