"""
Centralized Configuration
All paths and settings in one place, with environment variable overrides.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# BASE PATHS
# ============================================================================

# Project root (where this file lives)
PROJECT_ROOT = Path(__file__).parent.absolute()

# Data directory (can be overridden via env)
DATA_DIR = Path(os.getenv("WALLET_FINDER_DATA_DIR", PROJECT_ROOT))

# Logs directory
LOGS_DIR = Path(os.getenv("WALLET_FINDER_LOGS_DIR", PROJECT_ROOT / "logs"))
LOGS_DIR.mkdir(exist_ok=True)

# ============================================================================
# FILE PATHS
# ============================================================================

# Database
DB_PATH = Path(os.getenv("WALLET_FINDER_DB", DATA_DIR / "wallet_finder.db"))

# Configuration files
TOKENS_CONFIG_PATH = Path(os.getenv("WALLET_FINDER_TOKENS", DATA_DIR / "tokens.json"))

# Output files
REPORT_OUTPUT_PATH = Path(os.getenv("WALLET_FINDER_REPORT", DATA_DIR / "elite_wallets.html"))
MANUAL_TOKENS_PATH = DATA_DIR / "manual_tokens.txt"

# ============================================================================
# API SETTINGS
# ============================================================================

# GMGN API
GMGN_BASE_URL = os.getenv("GMGN_BASE_URL", "https://gmgn.ai")
GMGN_TRADERS_URL = f"{GMGN_BASE_URL}/vas/api/v1/token_traders/sol"
GMGN_HOLDERS_URL = f"{GMGN_BASE_URL}/vas/api/v1/token_holders/sol"
GMGN_TOKEN_INFO_URL = f"{GMGN_BASE_URL}/mrwapi/v1/multi_token_info"
GMGN_RANK_URL = f"{GMGN_BASE_URL}/api/v1/rank/sol/swaps"

# Cielo API
CIELO_BASE_URL = os.getenv("CIELO_BASE_URL", "https://app.cielo.finance")
CIELO_API_URL = f"{CIELO_BASE_URL}/api/trpc/profile.fetchTokenPnlFast"

# ============================================================================
# RATE LIMITING & CONCURRENCY
# ============================================================================

# Top-trader settings (GMGN - Strict)
API_DELAY = float(os.getenv("API_DELAY", "0.5"))
MAX_CONCURRENT_TOKENS = int(os.getenv("MAX_CONCURRENT_TOKENS", "10"))
MAX_GLOBAL_REQUESTS = int(os.getenv("MAX_GLOBAL_REQUESTS", "20"))

# Wallet-stats settings (Cielo - Lenient)
MAX_CONCURRENT_WALLET_CHECKS = int(os.getenv("MAX_CONCURRENT_WALLET_CHECKS", "15"))
REQUEST_DELAY_MIN = float(os.getenv("REQUEST_DELAY_MIN", "0.3"))
REQUEST_DELAY_MAX = float(os.getenv("REQUEST_DELAY_MAX", "0.8"))

# Smart Jitter (Human-like breaks to avoid detection)
BREAK_AFTER_BATCH = int(os.getenv("BREAK_AFTER_BATCH", "25"))        # Take a break every N requests
BREAK_DURATION_MIN = float(os.getenv("BREAK_DURATION_MIN", "3.0"))   # Minimum break (seconds)
BREAK_DURATION_MAX = float(os.getenv("BREAK_DURATION_MAX", "8.0"))   # Maximum break (seconds)

# Retry settings
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "10.0"))

# ============================================================================
# CIRCUIT BREAKER & BACKOFF CONFIGURATION
# ============================================================================

# Circuit Breaker Thresholds
# - Higher threshold with proxies because we rotate IPs on failures
# - Lower threshold without proxies to avoid API bans from same IP
CIRCUIT_BREAKER_THRESHOLD_WITH_PROXIES = int(os.getenv("CIRCUIT_BREAKER_WITH_PROXIES", "20"))
CIRCUIT_BREAKER_THRESHOLD_NO_PROXIES = int(os.getenv("CIRCUIT_BREAKER_NO_PROXIES", "10"))
CIRCUIT_OPEN_DURATION = int(os.getenv("CIRCUIT_OPEN_DURATION", "60"))  # Seconds before retry

# Backoff Multipliers (seconds per attempt)
# 403 Forbidden errors (proxy/IP blocked)
FORBIDDEN_BACKOFF_WITH_PROXIES = int(os.getenv("FORBIDDEN_BACKOFF_WITH_PROXIES", "10"))
FORBIDDEN_BACKOFF_NO_PROXIES = int(os.getenv("FORBIDDEN_BACKOFF_NO_PROXIES", "30"))

# 429 Rate Limit errors
RATE_LIMIT_BACKOFF_WITH_PROXIES = int(os.getenv("RATE_LIMIT_BACKOFF_WITH_PROXIES", "5"))
RATE_LIMIT_BACKOFF_NO_PROXIES = int(os.getenv("RATE_LIMIT_BACKOFF_NO_PROXIES", "15"))

# Identity Rotation (wallet-stats.py)
ROTATE_IDENTITY_EVERY = int(os.getenv("ROTATE_IDENTITY_EVERY", "15"))  # Wallets between rotations

# ============================================================================
# FILTERING THRESHOLDS
# ============================================================================

# Elite Criteria (Used for Wallet-stats and Report)
MIN_PNL_THRESHOLD = float(os.getenv("MIN_PNL_THRESHOLD", "15000.0"))
MIN_TRADES_THRESHOLD = int(os.getenv("MIN_TRADES_THRESHOLD", "20"))
MIN_HIGH_PROFIT_TOKENS = int(os.getenv("MIN_HIGH_PROFIT_TOKENS", "5")) # Min tokens with >$1k PnL
MIN_TOKEN_PNL_FOR_COUNT = float(os.getenv("MIN_TOKEN_PNL_FOR_COUNT", "1000.0")) # What counts as "high profit"
AUDIT_INTERVAL_HOURS = int(os.getenv("AUDIT_INTERVAL_HOURS", "2160")) # 90 days

# ============================================================================
# MANUAL TOKEN LIST
# ============================================================================

# Add token addresses here that you want to crawl manually
# Now read from manual_tokens.txt for scalability
def _load_manual_tokens():
    tokens = []
    if MANUAL_TOKENS_PATH.exists():
        with open(MANUAL_TOKENS_PATH, "r") as f:
            tokens = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    return list(set(tokens))

MANUAL_TOKENS = _load_manual_tokens()

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"
LOG_MAX_SIZE_MB = int(os.getenv("LOG_MAX_SIZE_MB", "10"))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_config_summary() -> dict:
    """Return a summary of current configuration for logging."""
    return {
        "data_dir": str(DATA_DIR),
        "db_path": str(DB_PATH),
        "tokens_config": str(TOKENS_CONFIG_PATH),
        "log_level": LOG_LEVEL,
        "log_to_file": LOG_TO_FILE,
        "max_concurrent_tokens": MAX_CONCURRENT_TOKENS,
        "max_concurrent_wallet_checks": MAX_CONCURRENT_WALLET_CHECKS,
        # Elite thresholds are now only for legacy compatibility or defaults
        "min_pnl_threshold": MIN_PNL_THRESHOLD, 
        "min_trades_threshold": MIN_TRADES_THRESHOLD,
    }



def register_manual_token(token_address: str):
    """Safely append a new token to the manual list if not present."""
    if not token_address or len(token_address) < 32:
        return
        
    current_tokens = set()
    if MANUAL_TOKENS_PATH.exists():
        with open(MANUAL_TOKENS_PATH, "r") as f:
            current_tokens = {line.strip() for line in f if line.strip() and not line.strip().startswith("#")}
    
    if token_address not in current_tokens:
        with open(MANUAL_TOKENS_PATH, "a") as f:
            f.write(f"{token_address}\n")
        return True
    return False



def print_config():
    """Print current configuration."""
    print("\n📋 Current Configuration:")
    for key, value in get_config_summary().items():
        print(f"   {key}: {value}")
    print(f"   manual_tokens_count: {len(MANUAL_TOKENS)}")
    print(f"   banned_wallets_count: {len(BANNED_WALLETS)}")
    print()


# ============================================================================
# BANNED WALLETS
# ============================================================================

# These wallets will be completely ignored (no DB entry, no API calls)
BANNED_WALLETS_PATH = DATA_DIR / "banned_wallets.txt"

def _load_banned_wallets():
    wallets = set()
    if BANNED_WALLETS_PATH.exists():
        with open(BANNED_WALLETS_PATH, "r") as f:
            wallets = {line.strip() for line in f if line.strip() and not line.strip().startswith("#")}
    return wallets

BANNED_WALLETS = _load_banned_wallets()
