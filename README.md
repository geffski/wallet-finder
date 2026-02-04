# Wallet Finder Bot

**Elite Solana Wallet Discovery & Analysis Tool**

Automatically discovers and analyzes high-performing Solana wallets by tracking trending tokens and their top traders.

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure (copy .env.example to .env and edit)
cp .env.example .env

# 3. Run full pipeline
python main.py --all
```

---

## 📖 Documentation

**See [DOCUMENTATION.md](DOCUMENTATION.md) for complete guide.**

---

## ✨ Features

- ✅ **Discovery Engine** - Tracks trending tokens and identifies top traders
- ✅ **Audit System** - Validates wallet performance (PnL, trades, portfolio)
- ✅ **HTML Reports** - Beautiful reports with filtering and pagination
- ✅ **Proxy Support** - Residential proxy rotation for reliability
- ✅ **Circuit Breaker** - Automatic failure handling
- ✅ **Database Migrations** - Safe schema evolution

---

## 📊 Usage

### Full Pipeline
```bash
python main.py --all
```

### Individual Scripts
```bash
# Discovery only
python top-trader.py

# Audit only
python wallet-stats.py --all

# Report only
python generate_report.py --type ALL
```

---

## 🗂️ Project Structure

```
wallet-finder/
├── main.py                 # Pipeline orchestrator
├── top-trader.py           # Discovery engine (GMGN API)
├── wallet-stats.py         # Audit engine (Cielo API)
├── generate_report.py      # HTML report generator
├── db_manager.py           # Database layer
├── base_api_client.py      # Shared HTTP client
├── proxy_manager.py        # Proxy rotation
├── config.py               # Configuration
└── DOCUMENTATION.md        # Complete documentation
```

---

## ⚙️ Configuration

Edit `.env`:

```bash
# Proxy Settings
USE_PROXIES=true
RESIDENTIAL_PROXIES="host:port:user:pass,..."

# Rate Limiting
MAX_CONCURRENT_WALLET_CHECKS=15
MAX_CONCURRENT_TOKENS=10

# Thresholds
MIN_PNL_THRESHOLD=15000.0
MIN_TRADES_THRESHOLD=20
```

---

## 📈 Performance

- **Concurrent Requests:** 15-20 simultaneous API calls
- **Database:** SQLite with WAL mode (concurrent reads)
- **API Caching:** 30% fewer redundant calls
- **Report Generation:** Optimized single-query approach

---

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| Database locked | Already fixed with write locking |
| Rate limit (429) | Enable proxies, reduce concurrency |
| Circuit breaker open | Wait 60s, check proxy config |
| Report too large | Already fixed with pagination (50 at a time) |

**See [DOCUMENTATION.md](DOCUMENTATION.md#troubleshooting) for details.**

---

## 📝 License

MIT License - See LICENSE file

---

**For complete documentation, see [DOCUMENTATION.md](DOCUMENTATION.md)**
