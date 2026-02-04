"""
Wallet Stats Checker - Stealth & Reliability Version with Proxy Support
Implements identity rotation, adaptive backoff, proxy rotation, and robust tRPC parsing.

Now includes:
- Centralized configuration
- Structured logging with file output
- API response validation with change detection
"""

import asyncio
import json
import random
import time
from typing import List, Dict, Optional, Tuple

from curl_cffi.requests import AsyncSession, RequestsError
from db_manager import DatabaseManager
from proxy_manager import get_proxy_manager, ProxyManager
from logger import get_logger
from api_validators import CieloValidator, run_preflight_checks
import config

# ============================================================================
# CONFIGURATION (from centralized config)
# ============================================================================

MIN_PNL = config.MIN_PNL_THRESHOLD
MIN_TRADES = config.MIN_TRADES_THRESHOLD

MAX_CONCURRENT_REQUESTS = config.MAX_CONCURRENT_WALLET_CHECKS
DELAY_MIN = config.REQUEST_DELAY_MIN
DELAY_MAX = config.REQUEST_DELAY_MAX

MAX_RETRIES = config.MAX_RETRIES
RETRY_DELAY = config.RETRY_DELAY

# ============================================================================
# IDENTITIES: Browser Rotation Pool
# ============================================================================

IDENTITIES = [
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "fp": "chrome120"
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "fp": "chrome119"
    },
    {
        "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
        "fp": "chrome116"
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "fp": "chrome120"
    }
]

# ============================================================================
# CORE CLIENT
# ============================================================================

class CieloClient:
    # Circuit breaker states
    CIRCUIT_CLOSED = "CLOSED"      # Normal operation
    CIRCUIT_OPEN = "OPEN"          # Blocking all requests
    CIRCUIT_HALF_OPEN = "HALF_OPEN"  # Testing if service recovered
    
    def __init__(self, db: DatabaseManager, proxy_manager: ProxyManager):
        self.session: Optional[AsyncSession] = None
        self.db = db
        self.proxy_manager = proxy_manager
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self.rotation_lock = asyncio.Lock()  # Ensure only one task rotates at a time
        self.wallets_checked = 0
        self.current_identity = random.choice(IDENTITIES)
        
        # Track failed wallets for export
        self.failed_wallets: List[Tuple[str, str]] = []  # (wallet, error_reason)
        
        # Circuit breaker state
        self.consecutive_failures = 0
        self.max_consecutive_failures = (
            config.CIRCUIT_BREAKER_THRESHOLD_WITH_PROXIES if proxy_manager.enabled 
            else config.CIRCUIT_BREAKER_THRESHOLD_NO_PROXIES
        )
        self.circuit_state = self.CIRCUIT_CLOSED
        self.circuit_opened_at: float = 0.0
        self.half_open_lock = asyncio.Lock()  # Only one request tests half-open

    async def _create_session(self):
        """Create a fresh session with a specific identity."""
        if self.session:
            await self.session.close()
            
        identity = self.current_identity
        self.session = AsyncSession(impersonate=identity["fp"])
        self.session.headers.update({
            "User-Agent": identity["ua"],
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://app.cielo.finance/",
            "Origin": "https://app.cielo.finance",
            "Connection": "keep-alive",
            "Sec-Ch-Ua-Platform": '"macOS"' if "Mac" in identity["ua"] else '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
        
        # Warmup
        try:
            await self.session.get("https://app.cielo.finance/", timeout=15)
            await asyncio.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f"⚠️ Session warmup failed (non-critical): {type(e).__name__}")

    async def start(self):
        await self._create_session()
        logger = get_logger()
        logger.info(f"Identity Initialized: {self.current_identity['fp']}")

    async def rotate_identity(self):
        """Pick a new identity and recreate session with a lock."""
        async with self.rotation_lock:
            self.current_identity = random.choice([i for i in IDENTITIES if i != self.current_identity])
            await self._create_session()
            get_logger().debug(f"Rotating Identity to: {self.current_identity['fp']}")

    def _extract_stats(self, response_data: dict) -> Tuple[float, int, str, List[Dict]]:
        """
        Extract stats from Cielo response using API validator.
        This will alert if the API structure changes.
        """
        return CieloValidator.extract_stats(response_data)

    async def check_wallet(self, wallet: str) -> Dict:
        """Process a single wallet with proxy rotation and circuit breaker."""
        short_addr = f"{wallet[:8]}...{wallet[-6:]}"
        
        # Wrap everything in the semaphore to maintain concurrency limits
        async with self.semaphore:
            # ===== CIRCUIT BREAKER CHECK (inside semaphore to prevent race conditions) =====
            if self.circuit_state == self.CIRCUIT_OPEN:
                # Check if we should transition to half-open
                if time.time() - self.circuit_opened_at >= config.CIRCUIT_OPEN_DURATION:
                    async with self.half_open_lock:
                        # Double-check inside lock
                        if self.circuit_state == self.CIRCUIT_OPEN:
                            self.circuit_state = self.CIRCUIT_HALF_OPEN
                            print(f"\n🟡 CIRCUIT HALF-OPEN: Testing recovery with next request...")
                else:
                    # Still in open state, reject immediately
                    return {'wallet': wallet, 'pnl': 0, 'trades': 0, 'qualified': False, 
                            'status': 'CIRCUIT_OPEN', 'success': False}
            
            # 1. Handle identity rotation
            # Check if we should rotate identity
            if self.wallets_checked % config.ROTATE_IDENTITY_EVERY == 0:
                await self.rotate_identity()

            input_params = {
                "json": {
                    "wallet": wallet, "chains": "", "timeframe": "30d", 
                    "sortBy": "pnl_desc", "page": "1", "tokenFilter": ""
                }
            }
            url = f"https://app.cielo.finance/api/trpc/profile.fetchTokenPnlFast?input={json.dumps(input_params)}"

            # 2. Execute request with retries and proxy rotation
            for attempt in range(MAX_RETRIES):
                # Get a fresh proxy for each attempt
                proxy = self.proxy_manager.get_proxy()
                
                try:
                    await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
                    resp = await self.session.get(url, timeout=30, proxy=proxy)
                    
                    # Handle Hard Blocks (403)
                    if resp.status_code == 403:
                        self.consecutive_failures += 1
                        self.proxy_manager.report_failure(proxy)
                        
                        if self.consecutive_failures >= self.max_consecutive_failures:
                            self._open_circuit()
                            return {'wallet': wallet, 'pnl': 0, 'trades': 0, 'qualified': False, 
                                    'status': 'CIRCUIT_OPENED', 'success': False}
                        
                        # Backoff timing based on proxy availability
                        wait = (
                            config.FORBIDDEN_BACKOFF_WITH_PROXIES * (attempt + 1) if self.proxy_manager.enabled
                            else config.FORBIDDEN_BACKOFF_NO_PROXIES * (attempt + 1)
                        )
                        print(f"   🚫 [403 Forbidden] Rotating proxy... ({wait}s)")
                        await asyncio.sleep(wait)
                        await self.rotate_identity()
                        continue
                    
                    # Handle Rate Limits (429)
                    if resp.status_code == 429:
                        self.proxy_manager.report_failure(proxy, is_rate_limit=True)
                        wait = (
                            config.RATE_LIMIT_BACKOFF_WITH_PROXIES * (attempt + 1) if self.proxy_manager.enabled
                            else config.RATE_LIMIT_BACKOFF_NO_PROXIES * (attempt + 1)
                        )
                        print(f"   ⏳ [429 Rate Limit] Rotating proxy... ({wait}s)")
                        await asyncio.sleep(wait)
                        continue
                    
                    # Handle Bad Request (400) - don't retry, it's bad data
                    if resp.status_code == 400:
                        print(f"   ⚠️  [HTTP 400] Bad request for {short_addr} - skipping")
                        self.failed_wallets.append((wallet, "HTTP_400"))
                        return {'wallet': wallet, 'pnl': 0, 'trades': 0, 'qualified': False, 
                                'status': 'INVALID_WALLET', 'success': False}

                    if resp.status_code != 200:
                        self.proxy_manager.report_failure(proxy)
                        print(f"   ⚠️  [HTTP {resp.status_code}] for {short_addr}. Retrying...")
                        await asyncio.sleep(3)
                        continue

                    # 3. Handle Success & Parsing
                    self.proxy_manager.report_success(proxy)
                    
                    # Parse JSON response with error handling
                    try:
                        data = resp.json()
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON response from Cielo for {short_addr}: {e}")
                        self.failed_wallets.append((wallet, "INVALID_JSON"))
                        return {
                            'wallet': wallet, 'pnl': 0, 'trades': 0, 'qualified': False,
                            'status': 'INVALID_JSON', 'success': False
                        }
                    
                    pnl, trades, status, tokens = self._extract_stats(data)
                    
                    # Reset failure counter and close circuit on success
                    self.consecutive_failures = 0
                    if self.circuit_state == self.CIRCUIT_HALF_OPEN:
                        self._close_circuit()
                    
                    # Calculate if wallet meets qualification criteria
                    qualified = (pnl >= MIN_PNL and trades >= MIN_TRADES)

                    if status == "PARSE_ERROR":
                        print(f"   🚨 [Schema Error] Cielo structure changed for {short_addr}!")
                    
                    # SIMPLIFIED OUTPUT: No "elite" filtering visual clutter
                    icon = "✅" if status == "SUCCESS" else "❓"
                    print(f"[{icon}] {short_addr}: ${pnl:,.0f} | {trades} trades")
                    
                    # Save results to Database (async - non-blocking)
                    if status == "SUCCESS" or "SUCCESS_WITH_WARNINGS" in status:
                        # Check for Bot behavior (Over 5k trades)
                        if trades > 5000:
                            print(f"   🤖 Bot detected ({trades} trades)! Blocking {short_addr} permanently.")
                            await self.db.async_mark_as_bot(wallet, reason=f"High activity: {trades} trades")
                        else:
                            # Normal wallet: Save global stats
                            await self.db.async_add_cielo_stats(wallet, pnl, trades)
                            
                            # Save per-token portfolio breakdown
                            if tokens:
                                formatted_trades = []
                                for t in tokens:
                                    t_addr = t.get("token_address") or ""
                                    t_pnl = float(t.get("total_pnl_usd", 0) or 0)
                                    
                                    # AUTO-REGISTRATION: Capture every token address found in audits
                                    # that we haven't tracked yet.
                                    if config.register_manual_token(t_addr):
                                        logger.info(f"Auto-registered new token CA: {t_addr} (Source wallet: {wallet})")

                                    formatted_trades.append({
                                        "token_address": t_addr,
                                        "symbol": t.get("token_symbol") or "UNKNOWN",
                                        "name": t.get("token_name") or "",
                                        "pnl_usd": t_pnl,
                                        "num_swaps": int(t.get("num_swaps", 0) or 0),
                                        "last_trade_ts": int(t.get("last_trade", 0) or 0)
                                    })
                                await self.db.async_save_wallet_portfolio(wallet, formatted_trades)
                    
                    return {
                        'wallet': wallet, 'pnl': pnl, 'trades': trades,
                        'qualified': qualified, 'status': status, 'success': True
                    }

                except Exception as e:
                    self.proxy_manager.report_failure(proxy)
                    print(f"   ❌ [Connection Error] {short_addr}: {e}")
                    await asyncio.sleep(3)

        # If we exhaust retries, increment failure counter
        self.consecutive_failures += 1
        self.failed_wallets.append((wallet, "CONNECTION_FAILED"))
        
        # If we were in half-open and failed, go back to open
        if self.circuit_state == self.CIRCUIT_HALF_OPEN:
            self._open_circuit()
            
        return {'wallet': wallet, 'pnl': 0, 'trades': 0, 'qualified': False, 'status': 'FAILED', 'success': False}

    def _open_circuit(self):
        """Transition circuit to OPEN state."""
        self.circuit_state = self.CIRCUIT_OPEN
        self.circuit_opened_at = time.time()
        print(f"\n🔴 CIRCUIT BREAKER OPEN: {self.consecutive_failures} failures. "
              f"Will test recovery in {config.CIRCUIT_OPEN_DURATION}s.")

    def _close_circuit(self):
        """Transition circuit to CLOSED state (recovered)."""
        self.circuit_state = self.CIRCUIT_CLOSED
        self.consecutive_failures = 0
        print(f"\n🟢 CIRCUIT BREAKER CLOSED: Service recovered, resuming normal operation.")

    async def close(self):
        if self.session:
            await self.session.close()

# ============================================================================
# HELPERS & MAIN
# ============================================================================


async def main(force_all: bool = None):
    import sys
    logger = get_logger()
    
    # Parse command line arguments if not explicitly passed
    if force_all is None:
        force_all = '--all' in sys.argv
    
    retry_failed = '--retry-failed' in sys.argv
    
    logger.info("=" * 60)
    logger.info("STEALTH WALLET CHECKER (CIELO) - WITH PROXY SUPPORT")
    logger.info("=" * 60)
    
    db = DatabaseManager(str(config.DB_PATH))
    proxy_manager = get_proxy_manager()
    
    if proxy_manager.enabled:
        logger.info(f"Using {len(proxy_manager.proxies)} residential proxies")
    

    # 1. Get wallets from DB that need checking
    if retry_failed:
        # Load wallets from failed_wallets.txt
        failed_path = config.PROJECT_ROOT / "failed_wallets.txt"
        if not failed_path.exists():
            logger.error(f"❌ No failed_wallets.txt found at: {failed_path}")
            print(f"❌ No failed wallets file found. Run the script normally first.")
            return
        
        target_wallets = []
        with open(failed_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and ',' in line:
                    wallet, reason = line.split(',', 1)
                    target_wallets.append(wallet)
        
        logger.info(f"[--retry-failed] Retrying {len(target_wallets)} failed wallets from {failed_path}")
        print(f"🔄 Retrying {len(target_wallets)} failed wallets...")
        
    elif force_all:

    # ... (skipping to the loop) ...

                    if status == "PARSE_ERROR":
                        print(f"   🚨 [Schema Error] Cielo structure changed for {short_addr}!")
                    
                    # SIMPLIFIED OUTPUT: No "elite" filtering visual clutter
                    icon = "✅" if status == "SUCCESS" else "❓"
                    print(f"[{icon}] {short_addr}: ${pnl:,.0f} | {trades} trades")
                    
                    # Save results to Database (async - non-blocking)
                    if status == "SUCCESS" or "SUCCESS_WITH_WARNINGS" in status:

    # ... (skipping to the end writing logic) ...

    # Export failed wallets to file (Merge with existing)
    if client.failed_wallets:
        failed_path = config.PROJECT_ROOT / "failed_wallets.txt"
        existing_failures = {}
        
        # Load existing failures if they exist
        if failed_path.exists():
            try:
                with open(failed_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and ',' in line:
                            w, r = line.split(',', 1)
                            existing_failures[w] = r
            except Exception:
                pass
        
        # Merge current session failures (newest reason wins)
        for wallet, reason in client.failed_wallets:
            existing_failures[wallet] = reason
            
        # Write back all failures with Header
        with open(failed_path, "w") as f:
            f.write("# FAILED WALLETS LOG\n")
            f.write("# Format: wallet_address,error_reason\n")
            f.write("# These wallets failed API audits and will be retried with --retry-failed\n")
            for wallet, reason in sorted(existing_failures.items()):
                f.write(f"{wallet},{reason}\n")
        
        logger.warning(f"Failed wallets updated. Total unique failures tracked: {len(existing_failures)}")
        logger.warning(f"Saved to: {failed_path}")
        # Get ALL wallets from the database
        target_wallets = await db.async_get_all_wallets()
        logger.info(f"[--all] Forcing recheck of ALL {len(target_wallets)} wallets")
    else:
        # Normal mode: only pending wallets (never checked or > AUDIT_INTERVAL_HOURS ago)
        target_wallets = await db.async_get_pending_wallets(min_hours_since_check=config.AUDIT_INTERVAL_HOURS)
    
    if not target_wallets:
        logger.info("All wallets in database are up to date.")
        return

    logger.info(f"Found {len(target_wallets)} wallets needing audit.")
    
    client = CieloClient(db, proxy_manager)
    await client.start()
    
    # Run pre-flight API check before processing
    preflight_passed = await run_preflight_checks(
        client.session, proxy_manager, 
        check_gmgn=False,  # Only check Cielo for this script
        check_cielo=True
    )
    if not preflight_passed:
        await client.close()
        return
    
    start_time = time.time()
    
    # Process in batches for performance with smart jitter
    batch_size = config.BREAK_AFTER_BATCH
    for i in range(0, len(target_wallets), batch_size):
        batch = target_wallets[i:i + batch_size]
        tasks = [client.check_wallet(wallet) for wallet in batch]
        await asyncio.gather(*tasks)
        logger.info(f"Batch processed: {min(i + batch_size, len(target_wallets))}/{len(target_wallets)}")
        
        # Smart break after each batch to mimic human behavior
        if i + batch_size < len(target_wallets):
            break_duration = random.uniform(config.BREAK_DURATION_MIN, config.BREAK_DURATION_MAX)
            logger.debug(f"☕ Taking a {break_duration:.1f}s break to stay under the radar...")
            await asyncio.sleep(break_duration)
    
    await client.close()
    
    # 2. Final Report logic
    if proxy_manager.enabled:
        proxy_manager.print_stats()
    
    # Export failed wallets to file (Merge with existing)
    if client.failed_wallets:
        failed_path = config.PROJECT_ROOT / "failed_wallets.txt"
        existing_failures = {}
        preserved_comments = []
        
        # Load existing failures and comments if they exist
        if failed_path.exists():
            try:
                with open(failed_path, "r") as f:
                    for line in f:
                        original_line = line
                        line = line.strip()
                        
                        # Preserve comments exactly as they are in the file
                        if line.startswith("#"):
                            preserved_comments.append(original_line)
                            continue
                            
                        if line and ',' in line:
                            w, r = line.split(',', 1)
                            existing_failures[w] = r
            except Exception:
                pass
        

        # Merge current session failures (newest reason wins)
        for wallet, reason in client.failed_wallets:
            existing_failures[wallet] = reason
            
        # Write back preserved comments + all failures
        with open(failed_path, "w") as f:
            for comment in preserved_comments:
                f.write(comment)
                # Ensure newline if missing from preserved comment
                if not comment.endswith('\n'):
                    f.write('\n')
                    
            for wallet, reason in sorted(existing_failures.items()):
                f.write(f"{wallet},{reason}\n")
        
        logger.warning(f"Failed wallets updated. Total unique failures tracked: {len(existing_failures)}")
        logger.warning(f"Saved to: {failed_path}")
    
    elapsed = time.time() - start_time
    logger.info(f"Audited this session: {len(target_wallets)}")
    logger.info(f"Duration: {elapsed/60:.1f} minutes")
    
    # 3. Automatically generate the report
    logger.info("🎬 Campaign finished. Generating final report...")
    from generate_report import generate_html
    
    # Use 'ALL' report type if --all flag was used, else 'SESSION'
    report_type = 'ALL' if force_all else 'SESSION'
    generate_html(report_type=report_type)

    # Print session summary with any API alerts
    logger.session_summary()


def run_with_graceful_shutdown():
    """Run main() with graceful shutdown on Ctrl+C. Press twice to force quit."""
    import signal
    import sys
    import os
    
    logger = get_logger()
    interrupt_count = 0
    
    def signal_handler(sig, frame):
        nonlocal interrupt_count
        interrupt_count += 1
        
        if interrupt_count == 1:
            logger.warning("Shutdown signal received. Press Ctrl+C again to FORCE QUIT.")
            print("\n⚠️  Press Ctrl+C again to FORCE QUIT immediately.")
        else:
            logger.warning("Force quit requested. Exiting immediately.")
            print("\n🛑 FORCE QUIT!")
            os._exit(1)  # Force exit without cleanup
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    async def main_with_shutdown():
        try:
            await main()
        except asyncio.CancelledError:
            logger.warning("Operations cancelled.")
        except Exception as error:
            logger.error(f"Unexpected error: {type(error).__name__}: {error}", exc_info=True)
        finally:
            # Always print session summary on exit
            logger.session_summary()
    
    try:
        asyncio.run(main_with_shutdown())
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        logger.session_summary()


if __name__ == "__main__":
    run_with_graceful_shutdown()