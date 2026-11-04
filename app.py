"""Local no-key dashboard for comparing Steam chart signals and player activity.

The program replaces data/latest_steam_retention.csv on every run. It does not
use, request, or store a Steam API key.
"""

from __future__ import annotations

import csv
import re
import time
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, send_from_directory

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
CSV_PATH = DATA_DIR / "latest_steam_retention.csv"
USER_AGENT = "SteamRetentionResearch/1.0 (educational project; respectful-rate-limit)"
REQUEST_DELAY_SECONDS = 1.5
MAX_GAMES = 30

FIELDNAMES = [
    "scrape_timestamp_utc", "chart_date", "region", "app_id", "game",
    "analysis_bucket", "has_singleplayer", "has_multiplayer", "store_features_raw",
    "sales_rank_proxy", "price_display", "listed_price_usd", "weeks_on_chart",
    "avg_players_last_30_days", "player_gain_last_30_days", "player_change_percent",
    "peak_players_last_30_days", "activity_ratio_30d", "audience_per_dollar",
    "steam_url", "steamcharts_url", "top_sellers_chart_url",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
ROBOTS: dict[str, RobotFileParser] = {}

app = Flask(__name__, static_folder=str(PROJECT_ROOT), static_url_path="")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def first_tuesday(year: int, month: int) -> date:
    """Steam's dated Top Seller chart is weekly, so use the first Tuesday."""
    for day in range(1, monthrange(year, month)[1] + 1):
        candidate = date(year, month, day)
        if candidate.weekday() == 1:
            return candidate
    raise ValueError("Could not determine a Tuesday for the requested month.")


def robots_allowed(url: str) -> bool:
    """Check robots.txt rather than attempting to evade a source's rules."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in ROBOTS:
        parser = RobotFileParser()
        parser.set_url(f"{base}/robots.txt")
        try:
            parser.read()
        except OSError as error:
            raise RuntimeError(f"Could not verify robots.txt for {parsed.netloc}: {error}") from error
        ROBOTS[base] = parser
    return ROBOTS[base].can_fetch(USER_AGENT, url)


def get_html(url: str) -> str:
    if not robots_allowed(url):
        raise RuntimeError(f"robots.txt does not allow this request: {url}")
    response = SESSION.get(url, timeout=25)
    response.raise_for_status()
    return response.text


def parse_number(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", "").replace("+", ""))
    return float(match.group()) if match else None


def parse_price(value: str) -> float | None:
    if "free" in value.lower():
        return 0.0
    match = re.search(r"\$(\d+(?:\.\d{1,2})?)", value)
    return float(match.group(1)) if match else None


def extract_sellers(chart_url: str, limit: int) -> list[dict[str, Any]]:
    """Extract a small, distinct game sample from a weekly revenue chart."""
    soup = BeautifulSoup(get_html(chart_url), "html.parser")
    sellers: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in soup.select("tr"):
        links = row.select('a[href*="/app/"]')
        game_link = next((link for link in links if clean_text(link.get_text(" ", strip=True))), None)
        if not game_link:
            continue
        app_match = re.search(r"/app/(\d+)", game_link.get("href", ""))
        if not app_match or app_match.group(1) in seen:
            continue

        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.select("td")]
        row_text = clean_text(row.get_text(" ", strip=True))
        rank_match = re.match(r"(\d+)", row_text)
        if not rank_match:
            continue

        last_cell_numbers = re.findall(r"\d+", cells[-1]) if cells else []
        seen.add(app_match.group(1))
        sellers.append({
            "app_id": app_match.group(1),
            "game": clean_text(game_link.get_text(" ", strip=True)),
            "sales_rank_proxy": int(rank_match.group(1)),
            "price_display": next((cell for cell in cells if "$" in cell or "Free To Play" in cell), "Unknown"),
            "weeks_on_chart": int(last_cell_numbers[-1]) if last_cell_numbers else None,
            "steam_url": f"https://store.steampowered.com/app/{app_match.group(1)}/",
        })
        if len(sellers) >= limit:
            break

    if not sellers:
        raise RuntimeError("No game rows were found in the requested Steam chart. Its page structure may have changed.")
    return sellers


def store_features(app_id: str) -> tuple[str, bool, bool, str]:
    """Classify using Steam Store feature labels instead of guessing from titles."""
    url = f"https://store.steampowered.com/app/{app_id}/?cc=us&l=english"
    soup = BeautifulSoup(get_html(url), "html.parser")
    blocks = [clean_text(block.get_text(" ", strip=True)) for block in soup.select(".game_area_details_specs")]
    evidence = " | ".join(blocks)
    normalized = evidence.lower()
    has_singleplayer = "single-player" in normalized
    multiplayer_terms = (
        "multi-player", "online pvp", "online co-op", "lan pvp", "lan co-op",
        "shared/split screen pvp", "shared/split screen co-op", "mmo",
        "cross-platform multiplayer", "remote play together",
    )
    has_multiplayer = any(term in normalized for term in multiplayer_terms)

    # The assignment calls for two buckets. A game with any multiplayer feature
    # is considered Multiplayer; the two source flags remain in the CSV.
    if has_multiplayer:
        bucket = "Multiplayer"
    elif has_singleplayer:
        bucket = "Singleplayer"
    else:
        bucket = "Unclassified"
    return evidence, has_singleplayer, has_multiplayer, bucket


def steamcharts_last_30_days(app_id: str) -> dict[str, float | str | None]:
    """Read SteamCharts' visible rolling 30-day table row for one game."""
    url = f"https://steamcharts.com/app/{app_id}"
    soup = BeautifulSoup(get_html(url), "html.parser")
    for row in soup.select("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.select("td")]
        if len(cells) >= 5 and cells[0].lower() == "last 30 days":
            average = parse_number(cells[1])
            gain = parse_number(cells[2])
            previous_average = average - gain if average is not None and gain is not None else None
            activity_ratio = average / previous_average if previous_average and previous_average > 0 else None
            return {
                "avg_players_last_30_days": average,
                "player_gain_last_30_days": gain,
                "player_change_percent": parse_number(cells[3]),
                "peak_players_last_30_days": parse_number(cells[4]),
                "activity_ratio_30d": activity_ratio,
                "steamcharts_url": url,
            }
    raise RuntimeError("SteamCharts did not provide a Last 30 Days row for this App ID.")


def write_csv(records: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def collect(year: int, month: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    """Create one complete replacement CSV; records are never appended."""
    limit = min(max(limit, 1), MAX_GAMES)
    chart_date = first_tuesday(year, month)
    if chart_date > date.today():
        raise ValueError("The first weekly chart in that month has not been published yet.")
    chart_url = f"https://store.steampowered.com/charts/topsellers/US/{chart_date.year}-{chart_date.month}-{chart_date.day}"
    write_csv([])  # Clear previous output before this fresh scrape starts.
    sellers = extract_sellers(chart_url, limit)
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records: list[dict[str, Any]] = []
    skipped = 0

    for seller in sellers:
        try:
            features, has_single, has_multi, bucket = store_features(seller["app_id"])
            time.sleep(REQUEST_DELAY_SECONDS)
            if bucket == "Unclassified":
                skipped += 1
                continue
            activity = steamcharts_last_30_days(seller["app_id"])
            price = parse_price(seller["price_display"])
            average = activity["avg_players_last_30_days"]
            audience_per_dollar = average / price if isinstance(average, float) and price and price > 0 else None
            records.append({
                **seller,
                **activity,
                "scrape_timestamp_utc": timestamp,
                "chart_date": chart_date.isoformat(),
                "region": "US",
                "analysis_bucket": bucket,
                "has_singleplayer": has_single,
                "has_multiplayer": has_multi,
                "store_features_raw": features,
                "listed_price_usd": price,
                "audience_per_dollar": audience_per_dollar,
                "top_sellers_chart_url": chart_url,
            })
        except (requests.RequestException, RuntimeError, ValueError) as error:
            print(f"Skipping {seller['app_id']}: {error}")
            skipped += 1
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

    write_csv(records)
    return records, skipped


@app.get("/")
def homepage() -> Any:
    return send_from_directory(PROJECT_ROOT, "index.html")


@app.post("/api/scrape")
def scrape() -> Any:
    payload = request.get_json(silent=True) or {}
    try:
        year = int(payload.get("year"))
        month = int(payload.get("month"))
        limit = int(payload.get("limit", 20))
        if not (2005 <= year <= date.today().year and 1 <= month <= 12):
            raise ValueError("Choose a valid month from 2005 through the present.")
        records, skipped = collect(year, month, limit)
        return jsonify({"records": records, "skipped": skipped})
    except (TypeError, ValueError, RuntimeError) as error:
        return jsonify({"error": str(error)}), 400


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    app.run(debug=True)
