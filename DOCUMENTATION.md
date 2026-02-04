# Wallet Finder Bot - Complete Documentation

**Elite Solana Wallet Discovery & Analysis Tool**

Automatically discovers and analyzes high-performing Solana wallets by tracking trending tokens and their top traders.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Usage](#usage)
7. [Database Schema](#database-schema)
8. [API Integration](#api-integration)
9. [Troubleshooting](#troubleshooting)
10. [Development](#development)

---

## Overview

**Wallet Finder** is a Python-based tool that:
1. **Discovers** wallets from trending Solana tokens (GMGN API)
2. **Audits** wallet performance over 30 days (Cielo Finance API)
3. **Generates** HTML reports of elite traders

**Key Metrics:**
- Minimum PnL: $15,000
- Minimum Trades: 20
- Timeframe: 30 days

---

## Features

### ✅ **Discovery Engine**
- Tracks trending tokens on GMGN (1h, 4h, 12h, 24h timeframes)
- Identifies smart money, sniper, and holder wallets
- Automatic token registration from wallet portfolios

### ✅ **Audit System**
- Validates wallet performance via Cielo Finance
- Tracks PnL, trade count, and token-level performance
- Bot detection (auto-blocks wallets with >5k trades)
- Circuit breaker for API failures

### ✅ **Reporting**
- Beautiful HTML reports with filtering
- Pagination (50 wallets at a time)
- Session reports vs. full database exports
- Direct links to Cielo and GMGN profiles

### ✅ **Reliability**
- Proxy rotation (residential proxies supported)
- Retry logic with exponential backoff
- Rate limit handling (429, 403 errors)
- Database migrations for schema evolution
- Comprehensive logging

### ✅ **Performance**
- Concurrent API requests (15-20 simultaneous)
- Database write locking (WAL mode)
- Optimized queries (single LEFT JOIN for reports)
- Token info caching (30% fewer API calls)

---

## Architecture

### **Core Components**

```
wallet-finder/
├── main.py                 # Pipeline orchestrator
├── top_trader.py           # Discovery engine (GMGN API)
├── wallet_stats.py         # Audit engine (Cielo API)
├── generate_report.py      # HTML report generator
├── db_manager.py           # Database abstraction layer
├── base_api_client.py      # Shared HTTP client (proxy + retry)
├── proxy_manager.py        # Proxy rotation & health tracking
├── api_validators.py       # API response validation
├── logger.py               # Structured logging
├── config.py               # Centralized configuration
└── manage_queue.py         # Token queue synchronization
```

### **Data Flow**

```
1. Discovery (top_trader.py)
   ↓
   Trending Tokens → Top Traders → Database (discovery_hits)
   
2. Audit (wallet_stats.py)
   ↓
   Pending Wallets → Cielo API → Database (cielo_stats, wallet_portfolio)
   
3. Report (generate_report.py)
   ↓
   Database → HTML Report (elite_wallets.html)
```

### **Database Schema**

```sql
tokens              -- Token metadata (symbol, ATH price)
wallets             -- Wallet addresses
discovery_hits      -- Where wallets were found (token + category)
cielo_stats         -- Wallet performance (PnL, trades)
wallet_portfolio    -- Token-level performance
bots                -- Blocked bot wallets
schema_version      -- Migration tracking
```

---

## Installation

### **1. Clone Repository**
```bash
git clone <your-repo-url>
cd wallet-finder
```

### **2. Create Virtual Environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### **3. Install Dependencies**
```bash
pip install -r requirements.txt
```

**Required packages:**
- `curl-cffi` - HTTP client with browser impersonation
- `python-dotenv` - Environment variable management
- `sqlite3` - Database (built-in)

### **4. Configure Environment**
```bash
cp .env.example .env
nano .env  # Edit with your settings
```

**Minimum `.env` configuration:**
```bash
# Proxy Settings (Optional but recommended)
USE_PROXIES=true
RESIDENTIAL_PROXIES="host1:port1:user1:pass1,host2:port2:user2:pass2"

# Rate Limiting
MAX_CONCURRENT_WALLET_CHECKS=15
MAX_CONCURRENT_TOKENS=10

# Thresholds
MIN_PNL_THRESHOLD=15000.0
MIN_TRADES_THRESHOLD=20
```

---

## Configuration

### **Environment Variables**

All settings in `config.py` can be overridden via `.env`:

#### **Paths**
```bash
WALLET_FINDER_DATA_DIR=/path/to/data
WALLET_FINDER_DB=/path/to/wallet_finder.db
WALLET_FINDER_LOGS_DIR=/path/to/logs
```

#### **API Rate Limiting**
```bash
MAX_CONCURRENT_TOKENS=10           # GMGN concurrent requests
MAX_CONCURRENT_WALLET_CHECKS=15    # Cielo concurrent requests
API_DELAY=0.5                      # Delay between batches (seconds)
```

#### **Circuit Breaker**
```bash
CIRCUIT_BREAKER_WITH_PROXIES=20    # Failures before circuit opens (with proxies)
CIRCUIT_BREAKER_NO_PROXIES=10      # Failures before circuit opens (no proxies)
CIRCUIT_OPEN_DURATION=60           # Seconds before retry
```

#### **Backoff Timing**
```bash
FORBIDDEN_BACKOFF_WITH_PROXIES=10  # 403 error backoff (seconds per attempt)
RATE_LIMIT_BACKOFF_WITH_PROXIES=5  # 429 error backoff (seconds per attempt)
```

#### **Filtering**
```bash
MIN_PNL_THRESHOLD=15000.0          # Minimum PnL to qualify
MIN_TRADES_THRESHOLD=20            # Minimum trades to qualify
MIN_HIGH_PROFIT_TOKENS=5           # Minimum tokens with >$1k PnL
```

---

## Usage

### **Option 1: Full Pipeline (Recommended)**

```bash
# Run everything: discovery → audit → report
python main.py --all

# Discovery + audit only (skip report)
python main.py --skip-report

# Audit + report only (skip discovery)
python main.py --skip-discovery
```

### **Option 2: Individual Scripts**

#### **Discovery**
```bash
# Find wallets from trending tokens
python top_trader.py
```

**What it does:**
- Fetches trending tokens (1h, 4h, 12h, 24h)
- Identifies top traders (smart money, snipers, holders)
- Saves to `discovery_hits` table
- Marks wallets as "pending audit"

#### **Audit**
```bash
# Audit all pending wallets
python wallet_stats.py --all

# Retry failed wallets
python wallet_stats.py --retry

# Audit specific wallet
python wallet_stats.py --wallet <address>
```

**What it does:**
- Fetches wallet performance from Cielo
- Saves PnL, trades, and portfolio to database
- Auto-blocks bots (>5k trades)
- Exports failed wallets to `failed_wallets_<timestamp>.txt`

#### **Report**
```bash
# Full database export
python generate_report.py --type ALL

# Session report (today's audits)
python generate_report.py --type SESSION

# Custom date filter
python generate_report.py --date 2026-01-01
```

**What it does:**
- Generates HTML report with filtering
- Pagination (50 wallets at a time)
- Opens in browser automatically

#### **Queue Management**
```bash
# Sync manual_tokens.txt with database
python manage_queue.py
```

**What it does:**
- Finds tokens in `wallet_portfolio` not yet processed
- Updates `manual_tokens.txt` with pending tokens
- Preserves comments in the file

---

## Database Schema

### **Tables**

#### **tokens**
```sql
CREATE TABLE tokens (
    id INTEGER PRIMARY KEY,
    address TEXT UNIQUE NOT NULL,
    symbol TEXT,
    ath_price REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### **wallets**
```sql
CREATE TABLE wallets (
    id INTEGER PRIMARY KEY,
    address TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cielo_link TEXT GENERATED ALWAYS AS (
        'https://app.cielo.finance/profile/' || address || '?timeframe=30d&sortBy=pnl_desc'
    ) VIRTUAL,
    gmgn_link TEXT GENERATED ALWAYS AS (
        'https://gmgn.ai/sol/address/' || address
    ) VIRTUAL
);
```

#### **discovery_hits**
```sql
CREATE TABLE discovery_hits (
    id INTEGER PRIMARY KEY,
    token_id INTEGER,
    wallet_id INTEGER,
    category TEXT,              -- 'smart_money', 'sniper', 'holder'
    rank INTEGER,
    pnl_on_token REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (token_id) REFERENCES tokens (id),
    FOREIGN KEY (wallet_id) REFERENCES wallets (id)
);
```

#### **cielo_stats**
```sql
CREATE TABLE cielo_stats (
    id INTEGER PRIMARY KEY,
    wallet_id INTEGER NOT NULL,
    pnl_usd REAL,
    trades_30d INTEGER,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wallet_id) REFERENCES wallets (id)
);
```

#### **wallet_portfolio**
```sql
CREATE TABLE wallet_portfolio (
    id INTEGER PRIMARY KEY,
    wallet_id INTEGER NOT NULL,
    token_address TEXT NOT NULL,
    symbol TEXT,
    name TEXT,
    pnl_usd REAL,
    num_swaps INTEGER,
    last_trade_ts INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wallet_id) REFERENCES wallets (id),
    UNIQUE(wallet_id, token_address)
);
```

#### **bots**
```sql
CREATE TABLE bots (
    id INTEGER PRIMARY KEY,
    wallet_id INTEGER UNIQUE NOT NULL,
    reason TEXT,
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wallet_id) REFERENCES wallets (id)
);
```

#### **schema_version**
```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);
```

### **Indexes**
```sql
CREATE INDEX idx_wallet_address ON wallets(address);
CREATE INDEX idx_token_address ON tokens(address);
CREATE INDEX idx_discovery_wallet ON discovery_hits(wallet_id);
CREATE INDEX idx_stats_wallet ON cielo_stats(wallet_id);
CREATE INDEX idx_portfolio_wallet ON wallet_portfolio(wallet_id);
```

---

## API Integration

### **GMGN API (Discovery)**

**Base URL:** `https://gmgn.ai`

**Endpoints:**
- `/vas/api/v1/token_traders/sol/<token>` - Top traders
- `/vas/api/v1/token_holders/sol/<token>` - Top holders
- `/mrwapi/v1/multi_token_info` - Token metadata
- `/api/v1/rank/sol/swaps` - Trending tokens

**Rate Limits:**
- ~20 concurrent requests
- 429 errors handled with backoff

**Authentication:** None (browser impersonation)

### **Cielo Finance API (Audit)**

**Base URL:** `https://app.cielo.finance`

**Endpoint:**
- `/api/trpc/profile.fetchTokenPnlFast?input={"wallet":"<address>"}`

**Rate Limits:**
- ~15 concurrent requests
- 403/429 errors handled with backoff

**Authentication:** None (browser impersonation)

---

## Troubleshooting

### **"Database is locked" errors**
**Cause:** Multiple processes writing simultaneously  
**Solution:** Already fixed with `_write_lock`. If still occurs, reduce `MAX_CONCURRENT_WALLET_CHECKS`.

### **"Circuit breaker open" messages**
**Cause:** Too many consecutive API failures  
**Solution:** 
- Check proxy configuration
- Reduce concurrency
- Wait 60 seconds for circuit to reset

### **"Rate limit (429)" errors**
**Cause:** Too many requests to API  
**Solution:**
- Enable proxies in `.env`
- Increase `RATE_LIMIT_BACKOFF_WITH_PROXIES`
- Reduce `MAX_CONCURRENT_WALLET_CHECKS`

### **Proxy authentication failures**
**Cause:** Invalid proxy format or credentials  
**Solution:**
- Check `.env` format: `host:port:user:pass`
- Verify credentials with proxy provider

### **Report not loading (26MB HTML)**
**Solution:** Already fixed with pagination. Report loads 50 wallets at a time.

---

## Development

### **Adding a Database Migration**

Edit `db_manager.py:_run_migrations()`:

```python
def _run_migrations(self):
    current_version = self._get_schema_version()
    logger = get_logger()
    
    # Migration 1: Add last_updated column
    if current_version < 1:
        logger.info("📦 Applying migration 1...")
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('ALTER TABLE wallets ADD COLUMN last_updated TIMESTAMP')
        conn.commit()
        self._set_schema_version(1, "Added last_updated column")
        logger.info("   ✅ Migration 1 complete")
```

### **Adding a New API Client**

Inherit from `BaseAPIClient`:

```python
from base_api_client import BaseAPIClient

class MyAPIClient(BaseAPIClient):
    def __init__(self, session, proxy_manager):
        super().__init__(
            session=session,
            proxy_manager=proxy_manager,
            max_concurrent_requests=10,
            max_retries=3
        )
    
    async def fetch_data(self, param):
        return await self.get(
            url=f"https://api.example.com/data/{param}",
            endpoint_name="my_api_endpoint"
        )
```

### **Running Tests**

```bash
# Test discovery
python top_trader.py

# Test audit (single wallet)
python wallet_stats.py --wallet <address>

# Test report
python generate_report.py --type SESSION

# Test full pipeline
python main.py --all
```

---

## File Structure

```
wallet-finder/
├── main.py                    # Pipeline orchestrator
├── top_trader.py              # Discovery engine
├── wallet_stats.py            # Audit engine
├── generate_report.py         # Report generator
├── manage_queue.py            # Queue synchronization
│
├── db_manager.py              # Database layer
├── base_api_client.py         # HTTP client base class
├── proxy_manager.py           # Proxy rotation
├── api_validators.py          # Response validation
├── logger.py                  # Logging
├── config.py                  # Configuration
│
├── .env                       # Environment variables (not in git)
├── .env.example               # Example configuration
├── requirements.txt           # Python dependencies
├── README.md                  # This file
│
├── wallet_finder.db           # SQLite database
├── manual_tokens.txt          # Token queue
├── banned_wallets.txt         # Blocked wallets
├── failed_wallets_*.txt       # Failed audit logs
├── elite_wallets.html         # Generated report
│
└── logs/                      # Application logs
    └── wallet_finder.log
```

---

## License

MIT License - See LICENSE file

---

## Support

For issues or questions:
1. Check [Troubleshooting](#troubleshooting)
2. Review logs in `logs/wallet_finder.log`
3. Open an issue on GitHub

---

**Happy hunting! 🚀**
