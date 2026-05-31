# Car Hunter 🚗

Automated hybrid SUV hunter for the Polish used-car market. Monitors Otomoto, OLX Auto, AAA Auto, Spoticar, Toyota Pewne Auto, and Das WeltAuto — filters by your requirements, scores reliability, estimates leasing costs, and sends alerts via Telegram, Gmail, or Discord.

## Features

- **Multi-source scraping** — 6 Polish car marketplaces monitored simultaneously
- **Requirements engine** — filter by price, year, mileage, fuel type, transmission, body type
- **Reliability scoring** — weighted 6-factor model (reliability 35%, maintenance 20%, mileage 15%, service history 10%, price value 10%, resale 10%)
- **Market intelligence** — detects suspiciously cheap cars, tracks price vs market average
- **Leasing calculator** — PMT-based monthly payment, total cost, cost per year
- **Multi-channel alerts** — Telegram bot, Gmail HTML email, Discord webhook
- **Deduplication** — tracks listings across runs, alerts once per 24h per channel
- **Stale cleanup** — marks unseen listings inactive after 7 days

## Requirements

- Python 3.11+
- PostgreSQL 16
- Docker & Docker Compose (for containerised deployment)

## Quick Start

### Local (without Docker)

```bash
cd apps/car-hunter
pip install -e .
playwright install chromium

# Copy and edit environment variables
cp .env.example .env
$EDITOR .env

# Run one scrape cycle
python -m src.main scrape

# List top results
python -m src.main list

# Start scheduler (runs every 30 min by default)
python -m src.main run
```

### Docker Compose

```bash
cd apps/car-hunter
cp .env.example .env
$EDITOR .env

docker compose up -d
docker compose logs -f car-hunter
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_URL` | Yes | — | PostgreSQL async URL (`postgresql+asyncpg://user:pass@host/db`) |
| `TELEGRAM_BOT_TOKEN` | No | — | BotFather token for Telegram alerts |
| `TELEGRAM_CHAT_ID` | No | — | Telegram chat/channel ID |
| `GMAIL_USER` | No | — | Gmail address (sender) |
| `GMAIL_APP_PASSWORD` | No | — | Gmail App Password (not your login password) |
| `GMAIL_TO` | No | — | Recipient email address |
| `DISCORD_WEBHOOK_URL` | No | — | Discord channel webhook URL |
| `MAX_PRICE_PLN` | No | `60000` | Maximum price in PLN |
| `MIN_YEAR` | No | `2020` | Minimum manufacture year |
| `MAX_MILEAGE_KM` | No | `150000` | Maximum mileage in km |
| `SCRAPE_INTERVAL_MINUTES` | No | `30` | How often to scrape |
| `ALERT_SCORE_THRESHOLD` | No | `6.0` | Minimum reliability score to trigger an alert |

## Reliability Score Model

Scores are out of 10, combining 6 weighted factors:

| Factor | Weight | Notes |
|--------|--------|-------|
| Reliability reputation | 35% | Based on make/model data |
| Maintenance cost | 20% | Estimated annual service cost |
| Mileage | 15% | 0 km = 10, 150k km = 5, 250k+ = 0 |
| Service history | 10% | Inferred from listing metadata |
| Price vs market | 10% | Compared to DB average for same make/model/year |
| Resale value | 10% | 3-year depreciation estimate |

### Example Rankings (Toyota C-HR Hybrid 2022, 80k km, dealer, 52k PLN)

```
Reliability score: 8.6/10
  ✓ Better than 87% of current listings
```

## Alert Example

**Telegram:**
```
🚗 New car found!

Toyota C-HR 2.0 Hybrid 2021
💰 58,900 PLN

📅 Year: 2021
🛣 Mileage: 112,000 km
⛽ Fuel: Hybrid
🔄 Gearbox: Automatic
🏪 Seller: Dealer
📍 Location: Warszawa

🟢 Reliability score: 8.4/10
📊 vs market avg: -6.2%

📋 Leasing estimate
  ↳ Down payment: 11,780 PLN
  ↳ Monthly: 987 PLN
  ↳ Total 48mo cost: 67,156 PLN

🔗 View listing
```

## Architecture

```
src/
├── config.py          # Pydantic Settings from env vars
├── main.py            # CLI entry point (run/scrape/list)
├── models/
│   ├── database.py    # SQLAlchemy async ORM models
│   └── schemas.py     # Pydantic v2 validation schemas
├── scrapers/          # One scraper per source
│   ├── base.py        # Shared HTTP + parsing helpers
│   ├── otomoto.py
│   ├── olx.py
│   ├── aaa_auto.py
│   ├── spoticar.py
│   ├── toyota_pewne.py
│   └── das_weltauto.py
├── filters/
│   └── requirements.py  # Requirements engine
├── scoring/
│   ├── reliability.py   # Weighted scorer
│   └── market_analysis.py  # Price intelligence
├── leasing/
│   └── calculator.py    # PMT leasing formula
├── notifications/
│   ├── base.py
│   ├── telegram.py
│   ├── gmail.py
│   ├── discord.py
│   └── manager.py       # Deduplication + routing
└── scheduler/
    └── jobs.py          # APScheduler job definitions
```

## Testing

The test suite (`tests/`) covers the pure business logic — scoring, leasing
math, the requirements filter, market analysis, and scraper HTML/JSON parsing
against static fixtures (no network calls required).

```bash
cd apps/car-hunter
pip install -e ".[dev]"
pytest -q
```

## GitHub Actions

The workflow at `.github/workflows/car-hunter.yml` runs lint (ruff) and the
test suite (pytest) on every push, then the scrape job every 6 hours.

Add secrets in your repository settings:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GMAIL_USER`
- `GMAIL_APP_PASSWORD`
- `GMAIL_TO`
- `DISCORD_WEBHOOK_URL`

## Known Problematic Models (Flagged Automatically)

- Ford Kuga PHEV (2020 battery recall)
- Early VW DSG7 wet clutch (pre-2018)
- Mitsubishi Outlander PHEV Gen1 battery degradation
