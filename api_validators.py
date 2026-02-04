"""
API Response Validators
Validates API responses and alerts when structure changes.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from logger import get_logger


@dataclass
class ValidationResult:
    """Result of validating an API response."""
    valid: bool
    data: Any = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class GMGNValidator:
    """Validates GMGN API responses."""
    
    # Expected response structure for reference
    EXPECTED_TOKEN_INFO = {
        "code": 0,
        "data": [{
            "symbol": "str",
            "ath_price": "float",
            "address": "str"
        }]
    }
    
    EXPECTED_TRADERS = {
        "code": 0,
        "data": {
            "list": [{
                "address": "str",
                "profit": "float",
                "is_suspicious": "bool",
                "maker_token_tags": "list"
            }]
        }
    }
    
    @staticmethod
    def validate_token_info(response: Dict) -> ValidationResult:
        """Validate token info response from GMGN."""
        logger = get_logger()
        
        # Check response code
        if not isinstance(response, dict):
            logger.api_alert("GMGN", "Token info response is not a dict", "dict", type(response).__name__)
            return ValidationResult(valid=False, error="Response is not a dictionary")
        
        code = response.get("code")
        if code is None:
            logger.api_alert("GMGN", "Missing 'code' field in token info response")
            return ValidationResult(valid=False, error="Missing 'code' field")
        
        if code != 0:
            # This is a normal API error, not a schema change
            return ValidationResult(valid=False, error=f"API returned error code: {code}")
        
        # Check data structure
        data = response.get("data")
        if data is None:
            logger.api_alert("GMGN", "Missing 'data' field in successful response")
            return ValidationResult(valid=False, error="Missing 'data' field")
        
        if not isinstance(data, list):
            logger.api_alert("GMGN", "Token info 'data' is not a list", "list", type(data).__name__)
            return ValidationResult(valid=False, error="'data' is not a list")
        
        if not data:
            return ValidationResult(valid=True, data=None, warnings=["Empty token info returned"])
        
        # Validate first token structure
        token = data[0]
        warnings = []
        
        if "symbol" not in token:
            logger.api_alert("GMGN", "Token info missing 'symbol' field")
            warnings.append("Missing 'symbol' field")
        
        if "ath_price" not in token and "highest_price" not in token:
            warnings.append("Missing 'ath_price' field (may use different name)")
        
        return ValidationResult(valid=True, data=token, warnings=warnings)
    
    @staticmethod
    def validate_traders_response(response: Dict, endpoint_type: str) -> ValidationResult:
        """Validate traders/holders response from GMGN."""
        logger = get_logger()
        
        if not isinstance(response, dict):
            logger.api_alert("GMGN", f"{endpoint_type} response is not a dict", "dict", type(response).__name__)
            return ValidationResult(valid=False, error="Response is not a dictionary")
        
        code = response.get("code")
        if code is None:
            logger.api_alert("GMGN", f"Missing 'code' field in {endpoint_type} response")
            return ValidationResult(valid=False, error="Missing 'code' field")
        
        if code != 0:
            return ValidationResult(valid=False, error=f"API returned error code: {code}")
        
        data = response.get("data")
        if data is None:
            logger.api_alert("GMGN", f"Missing 'data' field in {endpoint_type} response")
            return ValidationResult(valid=False, error="Missing 'data' field")
        
        if not isinstance(data, dict):
            logger.api_alert("GMGN", f"{endpoint_type} 'data' is not a dict", "dict", type(data).__name__)
            return ValidationResult(valid=False, error="'data' is not a dictionary")
        
        
        # Check for list or holders key (handle empty arrays properly)
        if "list" in data:
            items = data["list"]
        elif "holders" in data:
            items = data["holders"]
        else:
            logger.api_alert("GMGN", f"{endpoint_type} missing 'list' or 'holders' in data")
            return ValidationResult(valid=False, error="Missing 'list' or 'holders' field")
        
        if not isinstance(items, list):
            logger.api_alert("GMGN", f"{endpoint_type} items is not a list", "list", type(items).__name__)
            return ValidationResult(valid=False, error="Items is not a list")
        
        # Validate first item structure (if any)
        warnings = []
        if items:
            first = items[0]
            required_fields = ["address"]
            for field in required_fields:
                if field not in first:
                    logger.api_alert("GMGN", f"{endpoint_type} item missing required field '{field}'")
                    warnings.append(f"Missing '{field}' field in items")
            
            # Check for expected fields (not required but warn if missing)
            expected_fields = ["profit", "is_suspicious", "maker_token_tags"]
            for field in expected_fields:
                if field not in first:
                    warnings.append(f"Expected field '{field}' not found in items")
        
        return ValidationResult(valid=True, data=items, warnings=warnings)
    
    @staticmethod
    def validate_rank_response(response: Dict) -> ValidationResult:
        """Validate tokens rank response from GMGN."""
        logger = get_logger()
        
        if not isinstance(response, dict):
            logger.api_alert("GMGN", "Rank response is not a dict", "dict", type(response).__name__)
            return ValidationResult(valid=False, error="Response is not a dictionary")
        
        code = response.get("code")
        if code is None:
            logger.api_alert("GMGN", "Missing 'code' field in rank response")
            return ValidationResult(valid=False, error="Missing 'code' field")
        
        if code != 0:
            return ValidationResult(valid=False, error=f"API returned error code: {code}")
        
        data = response.get("data")
        if data is None:
            logger.api_alert("GMGN", "Missing 'data' field in rank response")
            return ValidationResult(valid=False, error="Missing 'data' field")
        
        if not isinstance(data, dict):
            logger.api_alert("GMGN", "Rank 'data' is not a dict", "dict", type(data).__name__)
            return ValidationResult(valid=False, error="'data' is not a dictionary")
        
        rank_list = data.get("rank")
        if rank_list is None:
            logger.api_alert("GMGN", "Missing 'rank' field in rank data")
            return ValidationResult(valid=False, error="Missing 'rank' list")
        
        if not isinstance(rank_list, list):
            logger.api_alert("GMGN", "Rank list is not a list", "list", type(rank_list).__name__)
            return ValidationResult(valid=False, error="Rank list is not a list")
            
        # Validate first item structure
        warnings = []
        if rank_list:
            first = rank_list[0]
            if "address" not in first:
                logger.api_alert("GMGN", "Rank item missing 'address' field")
                warnings.append("Missing 'address' field in rank items")
        
        return ValidationResult(valid=True, data=rank_list, warnings=warnings)


class CieloValidator:
    """Validates Cielo Finance API responses."""
    
    # Expected tRPC response structure
    EXPECTED_STRUCTURE = {
        "result": {
            "data": {
                "json": {
                    "data": {
                        "total_pnl_usd": "float",
                        "total_tokens_traded": "int"
                    }
                }
            }
        }
    }
    
    @staticmethod
    def validate_wallet_stats(response: Dict) -> ValidationResult:
        """Validate wallet stats response from Cielo."""
        logger = get_logger()
        
        if not isinstance(response, dict):
            logger.api_alert("CIELO", "Response is not a dict", "dict", type(response).__name__)
            return ValidationResult(valid=False, error="Response is not a dictionary")
        
        warnings = []
        
        # Navigate the nested structure
        try:
            result = response.get("result")
            if result is None:
                logger.api_alert("CIELO", "Missing 'result' field - tRPC structure may have changed")
                return ValidationResult(valid=False, error="Missing 'result' field")
            
            data_wrapper = result.get("data")
            if data_wrapper is None:
                logger.api_alert("CIELO", "Missing 'result.data' field")
                return ValidationResult(valid=False, error="Missing nested 'data' field")
            
            json_wrapper = data_wrapper.get("json")
            if json_wrapper is None:
                logger.api_alert("CIELO", "Missing 'result.data.json' field - tRPC structure changed")
                return ValidationResult(valid=False, error="Missing 'json' wrapper")
            
            if json_wrapper is None:
                return ValidationResult(valid=True, data=None, warnings=["Null json data"])
            
            inner_data = json_wrapper.get("data")
            if inner_data is None:
                return ValidationResult(valid=True, data=None, warnings=["No inner data (wallet may have no activity)"])
            
            # Validate expected fields
            if "total_pnl_usd" not in inner_data:
                logger.api_alert("CIELO", "Missing 'total_pnl_usd' field in wallet stats")
                warnings.append("Missing 'total_pnl_usd'")
            
            if "total_tokens_traded" not in inner_data:
                logger.api_alert("CIELO", "Missing 'total_tokens_traded' field in wallet stats")
                warnings.append("Missing 'total_tokens_traded'")
            
            return ValidationResult(valid=True, data=inner_data, warnings=warnings)
            
        except Exception as error:
            logger.api_alert("CIELO", f"Unexpected error parsing response: {type(error).__name__}: {error}")
            return ValidationResult(valid=False, error=f"Parse error: {error}")
    
    @staticmethod
    def extract_stats(response: Dict) -> Tuple[float, int, str, List[Dict]]:
        """
        Extract PnL, trades, and token list from Cielo response.
        Returns (pnl, trades, status, tokens) with proper error handling.
        """
        validation = CieloValidator.validate_wallet_stats(response)
        
        if not validation.valid:
            return 0.0, 0, f"VALIDATION_ERROR: {validation.error}", []
        
        if validation.data is None:
            return 0.0, 0, "NO_DATA", []
        
        try:
            # validation.data contains the inner_data from validate_wallet_stats
            inner_data = validation.data
            
            pnl = float(inner_data.get("total_pnl_usd", 0) or 0)
            trades = int(inner_data.get("total_tokens_traded", 0) or 0)
            tokens = inner_data.get("tokens", [])
            
            # Fallback: check for 'items' key if 'tokens' is empty
            if not tokens and "items" in inner_data:
                tokens = inner_data["items"]
            
            status = "SUCCESS"
            if validation.warnings:
                status = f"SUCCESS_WITH_WARNINGS: {', '.join(validation.warnings)}"
            
            return pnl, trades, status, tokens
            
        except (ValueError, TypeError) as error:
            get_logger().api_alert("CIELO", f"Type conversion error: {error}")
            return 0.0, 0, f"PARSE_ERROR: {error}", []


# ============================================================================
# PRE-FLIGHT API CHECKS
# ============================================================================

async def preflight_check_gmgn(session, proxy_manager) -> Tuple[bool, str]:
    """
    Test GMGN API before starting main processing.
    Tests multiple endpoints: token_traders, token_holders, and rank.
    Returns (success, message).
    """
    from logger import get_logger
    import uuid
    import random
    from datetime import datetime
    logger = get_logger()
    
    proxy = proxy_manager.get_proxy() if proxy_manager.enabled else None
    
    # Test 1: Token Traders endpoint
    test_token = "So11111111111111111111111111111111111111112"
    url_traders = f"https://gmgn.ai/vas/api/v1/token_traders/sol/{test_token}"
    params_traders = {"limit": 1, "orderby": "profit", "direction": "desc"}
    
    try:
        response = await session.get(url_traders, params=params_traders, timeout=15, proxy=proxy)
        
        if response.status_code == 429:
            return False, "Rate limited (429) - try again in a moment"
        if response.status_code == 403:
            return False, "Blocked (403) - check proxy configuration"
        if response.status_code != 200:
            return False, f"HTTP {response.status_code} - API may be down"
        
        data = response.json()
        validation = GMGNValidator.validate_traders_response(data, "preflight")
        
        if not validation.valid:
            return False, f"Traders API structure changed: {validation.error}"
            
    except Exception as e:
        if proxy_manager.enabled and proxy:
            proxy_manager.report_failure(proxy)
        return False, f"Traders endpoint error: {type(e).__name__}: {e}"
    
    # Test 2: Rank endpoint (trending tokens)
    url_rank = "https://gmgn.ai/api/v1/rank/sol/swaps/1h"
    params_rank = {
        "device_id": str(uuid.uuid4()),
        "fp_did": uuid.uuid4().hex[:32],
        "client_id": f"gmgn_web_{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}-{uuid.uuid4().hex[:7]}",
        "from_app": "gmgn",
        "app_ver": f"{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}-{uuid.uuid4().hex[:7]}",
        "tz_name": "Europe/Rome",
        "tz_offset": "3600",
        "app_lang": "en-US",
        "limit": "5",
        "orderby": "swaps",
        "direction": "desc"
    }
    
    try:
        response = await session.get(url_rank, params=params_rank, timeout=15, proxy=proxy)
        
        if response.status_code == 429:
            return False, "Rank endpoint rate limited (429)"
        if response.status_code == 403:
            return False, "Rank endpoint blocked (403) - check proxy configuration"
        if response.status_code != 200:
            return False, f"Rank endpoint HTTP {response.status_code}"
        
        data = response.json()
        validation = GMGNValidator.validate_rank_response(data)
        
        if not validation.valid:
            return False, f"Rank API structure changed: {validation.error}"
            
    except Exception as e:
        if proxy_manager.enabled and proxy:
            proxy_manager.report_failure(proxy)
        return False, f"Rank endpoint error: {type(e).__name__}: {e}"
    
    # All tests passed
    if proxy_manager.enabled:
        proxy_manager.report_success(proxy)
    return True, "All GMGN endpoints responding correctly ✓"


async def preflight_check_cielo(session, proxy_manager) -> Tuple[bool, str]:
    """
    Test Cielo API before starting main processing.
    Makes a single request to verify API structure.
    Returns (success, message).
    """
    import json as json_lib
    from logger import get_logger
    logger = get_logger()
    
    # Use a known active wallet for testing (from our own database)
    test_wallet = "13H846xTBgtimSPNu7sPVgySFJuPadbWti7ZedoBN7mE"
    
    input_params = {
        "json": {
            "wallet": test_wallet, 
            "chains": "", 
            "timeframe": "30d", 
            "sortBy": "pnl_desc", 
            "page": "1", 
            "tokenFilter": ""
        }
    }
    url = f"https://app.cielo.finance/api/trpc/profile.fetchTokenPnlFast?input={json_lib.dumps(input_params)}"
    
    proxy = proxy_manager.get_proxy() if proxy_manager.enabled else None
    
    try:
        response = await session.get(url, timeout=15, proxy=proxy)
        
        if response.status_code == 429:
            return False, "Rate limited (429) - try again in a moment"
        
        if response.status_code == 403:
            return False, "Blocked (403) - check proxy configuration"
        
        if response.status_code != 200:
            return False, f"HTTP {response.status_code} - API may be down"
        
        data = response.json()
        validation = CieloValidator.validate_wallet_stats(data)
        
        if validation.valid:
            if proxy_manager.enabled:
                proxy_manager.report_success(proxy)
            return True, "Cielo API responding correctly ✓"
        else:
            return False, f"API structure changed: {validation.error}"
            
    except Exception as e:
        if proxy_manager.enabled and proxy:
            proxy_manager.report_failure(proxy)
        return False, f"Connection error: {type(e).__name__}: {e}"


async def warmup_proxies(session, proxy_manager, api_type: str = "cielo") -> dict:
    """
    Test all proxies in parallel to identify healthy ones.
    Returns dict with healthy/unhealthy proxy lists.
    """
    import asyncio
    from logger import get_logger
    logger = get_logger()
    
    if not proxy_manager.enabled or not proxy_manager.proxies:
        return {"healthy": [], "unhealthy": [], "total": 0}
    
    print(f"\n🔥 Warming up {len(proxy_manager.proxies)} proxies...")
    
    async def test_single_proxy(proxy_url: str, index: int) -> tuple:
        """Test a single proxy and return (proxy, success, latency_ms, error)"""
        import time
        start = time.time()
        
        # Use appropriate test based on API type
        if api_type == "cielo":
            test_url = "https://app.cielo.finance/"
        else:  # gmgn
            test_url = "https://gmgn.ai/"
        
        try:
            response = await session.get(test_url, timeout=10, proxy=proxy_url)
            latency = (time.time() - start) * 1000  # Convert to ms
            
            if response.status_code in [200, 307, 301, 302]:  # Accept redirects
                return (proxy_url, True, latency, None)
            else:
                return (proxy_url, False, latency, f"HTTP {response.status_code}")
        except Exception as e:
            latency = (time.time() - start) * 1000
            error_msg = f"{type(e).__name__}"
            if "timeout" in str(e).lower():
                error_msg = "Timeout"
            elif "connection" in str(e).lower():
                error_msg = "Connection failed"
            return (proxy_url, False, latency, error_msg)
    
    # Test all proxies in parallel
    tasks = [test_single_proxy(proxy, i) for i, proxy in enumerate(proxy_manager.proxies)]
    results = await asyncio.gather(*tasks)
    
    # Categorize results
    healthy = []
    unhealthy = []
    
    for proxy_url, success, latency, error in results:
        # Mask proxy for display
        masked = proxy_manager._mask_proxy(proxy_url)
        
        if success:
            healthy.append((proxy_url, latency))
            status = f"✅ {masked}: {latency:.0f}ms"
            print(f"   {status}")
        else:
            unhealthy.append((proxy_url, error))
            status = f"❌ {masked}: {error}"
            print(f"   {status}")
    
    print(f"\n📊 Proxy Health: {len(healthy)}/{len(proxy_manager.proxies)} healthy")
    
    return {
        "healthy": healthy,
        "unhealthy": unhealthy,
        "total": len(proxy_manager.proxies)
    }


async def run_preflight_checks(session, proxy_manager, check_gmgn: bool = True, check_cielo: bool = True) -> bool:
    """
    Run pre-flight checks for specified APIs with proxy warmup.
    Returns True if all checks pass, False otherwise.
    """
    from logger import get_logger
    logger = get_logger()
    
    print("\n" + "=" * 60)
    print("🔍 PRE-FLIGHT CHECK")
    print("=" * 60)
    
    # Step 1: Warmup proxies if enabled
    if proxy_manager.enabled:
        api_type = "cielo" if check_cielo else "gmgn"
        warmup_results = await warmup_proxies(session, proxy_manager, api_type)
        
        if warmup_results["total"] > 0:
            healthy_count = len(warmup_results["healthy"])
            
            if healthy_count == 0:
                print("\n❌ No healthy proxies found!")
                print("   Cannot proceed without working proxies.")
                return False
            
            if healthy_count < warmup_results["total"] * 0.5:  # Less than 50% healthy
                print(f"\n⚠️  Only {healthy_count}/{warmup_results['total']} proxies are healthy")
                try:
                    response = input("   Continue with reduced proxy pool? [y/N]: ").strip().lower()
                    if response not in ('y', 'yes'):
                        print("   Aborting.\n")
                        return False
                except (EOFError, KeyboardInterrupt):
                    print("\n   Aborting.\n")
                    return False
    
    # Step 2: Test API endpoints
    print("\n🧪 Testing API endpoints...")
    all_passed = True
    
    if check_gmgn:
        print("   GMGN API...", end=" ", flush=True)
        success, message = await preflight_check_gmgn(session, proxy_manager)
        print(f"{'✅' if success else '❌'} {message}")
        if not success:
            all_passed = False
    
    if check_cielo:
        print("   Cielo API...", end=" ", flush=True)
        success, message = await preflight_check_cielo(session, proxy_manager)
        print(f"{'✅' if success else '❌'} {message}")
        if not success:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("✅ All checks passed! Starting processing...\n")
        return True
    else:
        print("\n⚠️  Some API checks failed!")
        print("   This may cause errors during processing.")
        
        try:
            response = input("   Continue anyway? [y/N]: ").strip().lower()
            if response in ('y', 'yes'):
                print("   Proceeding despite failed checks...\n")
                logger.warning("User chose to proceed despite failed preflight checks")
                return True
            else:
                print("   Aborting. Fix the issues and try again.\n")
                return False
        except (EOFError, KeyboardInterrupt):
            print("\n   Aborting.\n")
            return False
