# Financial Reconciliation System

Automated reconciliation of transactions from **Bank of America**, **Interactive Brokers**, **Charles Schwab**, and **QuickBooks Online** — with push-to-QBO so you can hand it straight to your CPA.

## Architecture Overview

```
┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐
│  Bank of America │  │ Interactive      │  │ Charles       │
│  (CSV export)    │  │ Brokers          │  │ Schwab        │
│                  │  │ (Flex API + CSV) │  │ (CSV export)  │
└────────┬────────┘  └────────┬─────────┘  └──────┬────────┘
         │                    │                    │
         ▼                    ▼                    ▼
    ┌─────────────────────────────────────────────────────┐
    │              CSV / XML Parsers                       │
    │   (Normalize all formats → UnifiedTransaction)      │
    └─────────────────────┬───────────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────────┐
    │            Reconciliation Engine                     │
    │   • Fuzzy match on date + amount + description      │
    │   • Detect duplicates across sources                 │
    │   • Flag conflicts for human review                  │
    │   • Separate matched vs unmatched                    │
    └──────────┬──────────────────────┬───────────────────┘
               │                      │
               ▼                      ▼
    ┌────────────────────┐  ┌──────────────────────────┐
    │  QBO API Push      │  │  File Export              │
    │  (python-quickbooks │  │  • CSV (bank feed import) │
    │   via OAuth2)      │  │  • IIF (QB Desktop)       │
    │                    │  │  • QBO/OFX (Web Connect)  │
    └────────────────────┘  └──────────────────────────┘
               │                      │
               ▼                      ▼
    ┌─────────────────────────────────────────────────────┐
    │              QuickBooks Online                       │
    │   (Your CPA sees clean, reconciled books)           │
    └─────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install

```bash
cd reconciler
pip install -r requirements.txt
```

### 2. Get Your Data

**Bank of America** (manual CSV — free):
- Log into bankofamerica.com
- Account → Download Transactions → CSV format
- Save to `./data/imports/bofa_checking.csv`

**Interactive Brokers** (automated via Flex API — free):
- Client Portal → Performance & Reports → Flex Queries
- Create Activity Flex Query (check all sections)
- Note the Query ID
- Settings → Flex Web Service → Generate token
- Set `IBKR_FLEX_TOKEN` and `IBKR_QUERY_ID` in `config.py`

**Charles Schwab** (manual CSV — free):
- Log into schwab.com
- Accounts → History → Set date range
- Export (top right) → CSV
- Save to `./data/imports/schwab_history.csv`

### 3. Run Reconciliation

```bash
# Import from all sources and reconcile
python main.py import \
  --bofa ./data/imports/bofa_checking.csv \
  --ibkr ./data/imports/ibkr_flex.csv \
  --schwab ./data/imports/schwab_history.csv

# Or auto-detect files in a directory
python main.py auto ./data/imports/
```

### 4. Export to QuickBooks

**Option A: File Import** (simplest, no API keys needed)
```bash
# CSV for QBO bank feed
python main.py export --format csv --output ./output/for_qbo.csv

# IIF for QuickBooks Desktop
python main.py export --format iif --output ./output/for_qbo.iif

# OFX/QBO for Web Connect
python main.py export --format qbo --output ./output/for_qbo.qbo
```

Then in QuickBooks: Banking → Upload Transactions → choose your file.

**Option B: Direct API Push** (fully automated)
```bash
# First time: opens browser for OAuth
python main.py push

# After first auth, it runs silently
python main.py push --yes
```

## How Data Flows From Each Source

### Bank of America → QuickBooks
| Method | Automation Level | Cost | Setup Time |
|--------|-----------------|------|------------|
| Manual CSV export | Semi-auto (you download monthly) | Free | 5 min |
| Plaid API | Fully automated | ~$50-100/mo | 2-3 hours |
| QBO native bank feed | Automated (but flaky) | Free w/ QBO | 10 min |

**Recommendation**: Start with manual CSV. If you're doing this monthly, that's 5 minutes of work. Plaid is worth it only if you need daily automation.

### Interactive Brokers → QuickBooks
| Method | Automation Level | Cost | Setup Time |
|--------|-----------------|------|------------|
| Flex Web Service API | Fully automated | Free | 30 min |
| Manual CSV Flex Query | Semi-auto | Free | 15 min |

**Recommendation**: Use the Flex Web Service API — it's free and fully automated. This system supports it natively via `fetchers.py`.

### Charles Schwab → QuickBooks
| Method | Automation Level | Cost | Setup Time |
|--------|-----------------|------|------------|
| Manual CSV export | Semi-auto | Free | 5 min |
| developer.schwab.com API | Automated (beta) | Free? | Hours |
| Plaid API | Automated | ~$50-100/mo | 2-3 hours |

**Recommendation**: Manual CSV for now. Schwab's developer API is still maturing post-TD Ameritrade merger.

## QuickBooks Online API Setup

1. Go to https://developer.intuit.com → Create account
2. Create a new app → QuickBooks Online
3. Copy **Client ID** and **Client Secret**
4. Set redirect URI: `http://localhost:5000/callback`
5. Update `config.py` with your credentials
6. Run `python main.py push` — it will open your browser for OAuth

**Important**: For personal/single-company use, you can keep your app in "Development" mode indefinitely. No need to go through Intuit's app review process.

## Reconciliation Logic

The engine uses multi-factor fuzzy matching:

| Factor | Weight | How It Works |
|--------|--------|-------------|
| Amount | 40% | Exact match = 1.0, within $1 = 0.8, within $5 = 0.4 |
| Date | 30% | Same day = 1.0, ±1 day = 0.9, ±3 days = gradual decay |
| Description | 20% | Sequence matcher similarity ratio |
| Payee | 10% | Sequence matcher on payee field |

Transactions scoring ≥ 0.85 are auto-matched. Between 0.5-0.85 are flagged for review. Below 0.5 are marked unmatched (new to QBO).

## Transaction Type Mapping

The system maps institution-specific categories to QBO accounts:

```
IBKR "Dividends"       → QBO "Dividend Income"
IBKR "Commission"      → QBO "Trading Commissions"
Schwab "Qualified Div"  → QBO "Qualified Dividend Income"
BofA "INTEREST"         → QBO "Interest Income"
BofA "FEE"              → QBO "Bank Charges & Fees"
```

Customize these in `config.py` → `AccountMapping` to match your chart of accounts.

## Automation Schedule

For a monthly workflow (recommended for most people):

```bash
# Add to crontab (runs 2nd of every month at 8am)
0 8 2 * * cd /path/to/reconciler && python main.py auto ./data/imports/ && python main.py export --format csv --output ./output/monthly_$(date +\%Y\%m).csv
```

For IBKR auto-fetch + reconcile:
```bash
# Daily at 7am (IBKR data updates overnight)
0 7 * * * cd /path/to/reconciler && python -c "from fetchers import IBKRFlexFetcher; IBKRFlexFetcher().fetch()" && python main.py auto ./data/imports/
```

## File Structure

```
reconciler/
├── main.py              # CLI entry point
├── config.py            # Credentials & account mappings
├── models.py            # UnifiedTransaction data model
├── parsers.py           # CSV/XML parsers for each institution
├── reconciler.py        # Matching & reconciliation engine
├── qbo_integration.py   # QuickBooks API + file exporters
├── fetchers.py          # Automated data fetchers (IBKR, Plaid)
├── requirements.txt
├── data/
│   ├── imports/         # Drop CSV files here
│   ├── processed/       # Reconciliation results & upload batches
│   ├── archive/         # Historical runs
│   └── logs/
└── output/              # Generated QBO import files
```

## Next Steps / Roadmap

- [ ] Set up IBKR Flex Query (30 min, one-time)
- [ ] Export CSVs from BofA and Schwab
- [ ] Run first reconciliation
- [ ] Set up QBO API credentials (if you want auto-push)
- [ ] Customize account mappings for your chart of accounts
- [ ] Set up cron job for monthly automation
- [ ] Consider Plaid for BofA automation (if volume warrants cost)
