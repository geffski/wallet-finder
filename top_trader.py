"""
Wallet Finder - Enhanced Version with Proxy Support
Fetches token info (ATH, symbol), then finds profitable traders/holders via GMGN.
Captures token-specific PnL for every wallet hit.
Uses residential proxies for improved reliability and reduced rate limiting.

Now includes:
- API response validation with change detection
- Structured logging
"""

import asyncio
import json
import time
import random
import uuid
import os
import re
from datetime import datetime
from typing import Optional, List, Dict, Set, Tuple
from db_manager import DatabaseManager
from proxy_manager import get_proxy_manager, ProxyManager
from api_validators import GMGNValidator, run_preflight_checks
from logger import get_logger
from base_api_client import BaseAPIClient

from curl_cffi.requests import AsyncSession
import config

# Delay between API batches (in seconds) to avoid rate limiting
API_DELAY = config.API_DELAY
MAX_CONCURRENT_TOKENS = config.MAX_CONCURRENT_TOKENS
MAX_GLOBAL_REQUESTS = config.MAX_GLOBAL_REQUESTS

# Browser Identity for GMGN
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://gmgn.ai",
    "Referer": "https://gmgn.ai/",
    "Connection": "keep-alive",
}

class WalletFinder(BaseAPIClient):
    """Fetch and analyze wallet data from GMGN API using async workers with proxy rotation."""
    
    BASE_URL = "https://gmgn.ai/vas/api/v1/token_traders/sol"
    HOLDERS_URL = "https://gmgn.ai/vas/api/v1/token_holders/sol"
    INFO_URL = "https://gmgn.ai/mrwapi/v1/multi_token_info"
    
    def __init__(self, session: AsyncSession, db: DatabaseManager, proxy_manager: ProxyManager):
        super().__init__(
            session=session,
            proxy_manager=proxy_manager,
            max_concurrent_requests=MAX_GLOBAL_REQUESTS,
            max_retries=3
        )
        self.db = db

    async def fetch_token_info(self, contract_address: str) -> dict:
        """Fetch token details like symbol and ATH price with validation."""
        
        # Generate unique fingerprint for anti-detection (intentionally unique per request)
        request_params = {
            "device_id": str(uuid.uuid4()),
            "fp_did": uuid.uuid4().hex[:32],
            "client_id": f"gmgn_web_{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}-{uuid.uuid4().hex[:7]}",
            "from_app": "gmgn",
            "app_ver": f"{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}-{uuid.uuid4().hex[:7]}",
            "tz_name": "Europe/Rome",
            "tz_offset": "3600",
            "app_lang": "en-US",
            "os": "web"
        }
        
        request_payload = {
            "chain": "sol",
            "addresses": [contract_address]
        }
        
        # Use base class method with token info validator
        def validate_response(response_data):
            return GMGNValidator.validate_token_info(response_data)
        
        response = await self.post(
            url=self.INFO_URL,
            endpoint_name="token_info",
            params=request_params,
            json_data=request_payload,
            validator=validate_response
        )
        
        # Extract data from response
        if response.get("code") == 0:
            return response.get("data") or {}
        else:
            return {}
    
    async def fetch_trending_tokens(self, timeframe: str) -> List[str]:
        """Scrape trending tokens for a specific timeframe from GMGN rank API."""
        logger = get_logger()
        url = f"{config.GMGN_RANK_URL}/{timeframe}"
        
        # Fresh identifiers for each request
        params = {
            "device_id": str(uuid.uuid4()),
            "fp_did": uuid.uuid4().hex[:32],
            "client_id": f"gmgn_web_{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}-{uuid.uuid4().hex[:7]}",
            "from_app": "gmgn",
            "app_ver": f"{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}-{uuid.uuid4().hex[:7]}",
            "tz_name": "Europe/Rome",
            "tz_offset": "3600",
            "app_lang": "en-US",
            "os": "web",
            "worker": "0",
            "orderby": "swaps",
            "direction": "desc",
            "filters[]": ["renounced", "frozen"],
            "min_created": "1440m",
            "max_created": "129600m",
            "min_marketcap": "100000",
            "min_gas_fee": "10"
        }
        
        current_proxy = self.proxy_manager.get_proxy()
        
        async with self.request_semaphore:
            try:
                response = await self.session.get(
                    url, 
                    params=params, 
                    timeout=30,
                    proxy=current_proxy
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    validation = GMGNValidator.validate_rank_response(response_data)
                    
                    if validation.valid:
                        self.proxy_manager.report_success(current_proxy)
                        addresses = [item.get("address") for item in validation.data if item.get("address")]
                        logger.info(f"Found {len(addresses)} tokens for {timeframe} timeframe")
                        return addresses
                    else:
                        logger.warning(f"Rank validation failed for {timeframe}: {validation.error}")
                        
                elif response.status_code == 429:
                    self.proxy_manager.report_failure(current_proxy, is_rate_limit=True)
                else:
                    self.proxy_manager.report_failure(current_proxy)
                    
            except Exception as error:
                self.proxy_manager.report_failure(current_proxy)
                logger.error(f"Error fetching rank for {timeframe}: {type(error).__name__}: {error}")
                
        return []

    async def fetch_endpoint(self, url: str, params: dict, endpoint_type: str) -> dict:
        """Fetch data from endpoint with proxy rotation, retry logic, and validation."""
        
        # Use base class method with GMGN-specific validator
        def validate_response(response_data):
            return GMGNValidator.validate_traders_response(response_data, endpoint_type)
        
        response = await self.get(
            url=url,
            endpoint_name=endpoint_type,
            params=params,
            validator=validate_response
        )
        
        # Format response for compatibility with existing code
        if response.get("code") == 0:
            data = response.get("data")
            return {"code": 0, "data": {"list": data} if data else {}}
        else:
            return {"code": -1, "data": {}}

    async def find_profitable_wallets(
        self,
        contract_address: str,
    ) -> List[dict]:
        """Query ALL 6 endpoint combinations concurrently and return hits with token-specific PnL."""
            
        fetch_limit = 100
        
        categories = [
            ("trader_profit", self.BASE_URL, "profit"),
            ("trader_realized", self.BASE_URL, "realized_profit"),
            ("trader_unrealized", self.BASE_URL, "unrealized_profit"),
            ("holder_amount", self.HOLDERS_URL, "amount_percentage"),
            ("holder_profit", self.HOLDERS_URL, "profit"),
            ("holder_unrealized", self.HOLDERS_URL, "unrealized_profit")
        ]
        
        tasks = []
        for cat_name, base_url, order_by in categories:
            url = f"{base_url}/{contract_address}"
            params = {"limit": fetch_limit, "orderby": order_by, "direction": "desc"}
            tasks.append(self.fetch_endpoint(url, params, f"{cat_name}"))

        results = await asyncio.gather(*tasks)
        
        all_hits = []

        for i, response in enumerate(results):
            category_name = categories[i][0]
            if response.get("code") == 0:
                data = response.get("data", {})
                batch = data.get("list", []) or data.get("holders", [])
                
                for rank, w in enumerate(batch, 1):
                    # Capture every address from the response without filtering
                    # GMGN uses 'profit' for both total and unrealized/realized variants in some fields
                    # We take the main 'profit' field which matches the orderby criteria usually.
                    token_pnl = float(w.get("profit", 0) or 0)
                    
                    all_hits.append({
                        "address": w.get("address"),
                        "category": category_name,
                        "rank": rank,
                        "pnl_on_token": token_pnl
                    })
        
        return all_hits

# ============================================================================
# MAIN PIPELINE
# ============================================================================

async def analyze_token(token: str, finder: WalletFinder, settings: dict, semaphore: asyncio.Semaphore):
    async with semaphore:
        short_token = f"{token[:10]}...{token[-6:]}"
        print(f"🔍 Analyzing Token: {short_token}")
        
        # 1. Check if token info already exists in database
        symbol = None
        ath_price = None
        
        # Try to get from database first
        try:
            conn = finder.db._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT symbol, ath_price FROM tokens WHERE address = ?", (token,))
            result = cursor.fetchone()
            if result:
                symbol, ath_price = result
                if symbol:
                    print(f"   💾 Token info from cache: {symbol} | ATH: {ath_price}")
        except Exception:
            pass  # If DB lookup fails, fall back to API
        
        # 2. Fetch from API only if not in database
        if symbol is None:
            info = await finder.fetch_token_info(token)
            symbol = info.get("symbol", "UNKNOWN")
            ath_price = info.get("ath_price", 0)
            
            if symbol != "UNKNOWN":
                print(f"   📊 Token: {symbol} | ATH: {ath_price}")

        # 3. Get Every Wallet from the response
        hits = await finder.find_profitable_wallets(contract_address=token)
        
        # 4. Save the token itself to the database (even if no hits found)
        # This prevents us from re-analyzing empty tokens forever
        await finder.db.async_get_or_create_token(token, symbol, ath_price)
        
        # 5. Save to DB using batch insert
        unique_wallets = set()
        batch_hits = []
        
        for hit in hits:
            addr = hit["address"]
            if addr in config.BANNED_WALLETS:
                continue
                
            batch_hits.append({
                'token_address': token,
                'wallet_address': addr,
                'category': hit["category"],
                'rank': hit["rank"],
                'pnl_on_token': hit["pnl_on_token"],
                'symbol': symbol,
                'ath_price': ath_price
            })
            unique_wallets.add(hit["address"])
        
        # Single transaction for all hits from this token (async - non-blocking)
        await finder.db.async_add_discovery_hits_batch(batch_hits)
        
        print(f"   ➜ Saved {len(hits)} hits ({len(unique_wallets)} unique wallets) for {symbol}")
        await asyncio.sleep(API_DELAY)

async def main():
    import sys
    # Load tokens from config.py
    tokens = config.MANUAL_TOKENS
    
    # Detect if we want a full re-audit
    force_all = '--all' in sys.argv
    exclude_bundlers = True
    
    db = DatabaseManager()
    proxy_manager = get_proxy_manager()
    
    print(f"🚀 Starting Wallet Discovery")
    print(f"   Settings: capture_all=True, skip_duplicate_tokens=True")
    if proxy_manager.enabled:
        print(f"🌐 Using {len(proxy_manager.proxies)} residential proxies for requests")
    
    async with AsyncSession(impersonate="chrome120") as session:
        session.headers.update(HEADERS)
        
        # Run pre-flight API check before processing
        preflight_passed = await run_preflight_checks(
            session, proxy_manager, 
            check_gmgn=True, 
            check_cielo=False  # Only check GMGN for this script
        )
        if not preflight_passed:
            return
        
        
        finder = WalletFinder(session, db, proxy_manager)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TOKENS)
        
        # Step 4: Scrape trending tokens from all timeframes
        timeframes = ["1m", "5m", "1h", "6h", "24h"]
        print(f"📡 Scraping trending tokens from GMGN ({', '.join(timeframes)})")
        
        ticker_tasks = [finder.fetch_trending_tokens(tf) for tf in timeframes]
        ticker_results = await asyncio.gather(*ticker_tasks)
        
        scraped_tokens = set()
        for res in ticker_results:
            scraped_tokens.update(res)
        
        # Step 5: Merge with manual tokens and ensure uniqueness
        initial_tokens = list(set(tokens) | scraped_tokens)
        
        # Step 6: Filter out already processed tokens
        existing_tokens = set(await db.async_get_all_token_addresses())
        all_tokens = [t for t in initial_tokens if t not in existing_tokens]
        
        new_tokens_count = len(scraped_tokens - set(tokens))
        skipped_count = len(initial_tokens) - len(all_tokens)
        
        print(f"📊 Tokens: {len(initial_tokens)} found ({len(tokens)} manual + {new_tokens_count} new scraped)")
        if skipped_count > 0:
            print(f"   ⏭️  Skipping {skipped_count} tokens already in database")
        print(f"   🚀 Analyzing {len(all_tokens)} new tokens")
        
        if not all_tokens:
            print("✅ No new tokens to analyze.")
            return

        # Step 7: Process all tokens in batches with smart jitter
        settings = {"exclude_bundlers": exclude_bundlers}
        batch_size = config.BREAK_AFTER_BATCH
        
        for i in range(0, len(all_tokens), batch_size):
            batch = all_tokens[i:i + batch_size]
            tasks = [analyze_token(t, finder, settings, semaphore) for t in batch]
            await asyncio.gather(*tasks)
            
            # Smart break after each batch to mimic human behavior
            if i + batch_size < len(all_tokens):
                break_duration = random.uniform(config.BREAK_DURATION_MIN, config.BREAK_DURATION_MAX)
                print(f"   ☕ Taking a {break_duration:.1f}s break to stay under the radar...")
                await asyncio.sleep(break_duration)
    
    # Print proxy statistics at the end
    if proxy_manager.enabled:
        proxy_manager.print_stats()
    
    print(f"\n✅ Token discovery complete!")
    print(f"   💡 Tip: Run 'python wallet_stats.py' to audit discovered wallets")
    print(f"   💡 Or use 'python main.py' to run the full pipeline")


def run_with_graceful_shutdown():
    """Run main() with graceful shutdown on Ctrl+C."""
    import signal
    from logger import get_logger
    
    logger = get_logger()
    
    def signal_handler(sig, frame):
        logger.warning("Shutdown signal received. Completing current operations...")
    
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

