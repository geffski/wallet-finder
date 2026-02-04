"""
Base API Client - Shared HTTP logic with proxy rotation and retry handling

Provides a reusable foundation for API clients that need:
- Proxy rotation with health tracking
- Retry logic with exponential backoff
- Rate limit handling
- Request semaphore for concurrency control
- Consistent error handling
"""

import asyncio
import random
from typing import Optional, Dict, Any, Callable
from curl_cffi.requests import AsyncSession
from proxy_manager import ProxyManager
from logger import get_logger


class BaseAPIClient:
    """
    Base class for API clients with built-in proxy rotation and retry logic.
    
    Features:
    - Automatic proxy rotation on failures
    - Exponential backoff for retries
    - Rate limit handling (429)
    - Request concurrency control via semaphore
    - Consistent success/failure reporting
    
    Subclasses should implement:
    - Custom validation logic
    - Endpoint-specific methods
    """
    
    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_TIMEOUT = 30
    DEFAULT_RATE_LIMIT_BACKOFF = 3  # seconds per attempt
    DEFAULT_ERROR_BACKOFF = 1  # seconds
    
    def __init__(
        self, 
        session: AsyncSession, 
        proxy_manager: ProxyManager,
        max_concurrent_requests: int = 10,
        max_retries: int = DEFAULT_MAX_RETRIES
    ):
        """
        Initialize the base API client.
        
        Args:
            session: curl_cffi AsyncSession for making requests
            proxy_manager: ProxyManager for proxy rotation
            max_concurrent_requests: Maximum concurrent requests (semaphore limit)
            max_retries: Maximum retry attempts per request
        """
        self.session = session
        self.proxy_manager = proxy_manager
        self.request_semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.max_retries = max_retries
        self.logger = get_logger()
    
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        endpoint_name: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        timeout: int = DEFAULT_TIMEOUT,
        validator: Optional[Callable] = None,
        delay_range: tuple = (0.3, 0.8)
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with automatic retry and proxy rotation.
        
        Args:
            method: HTTP method ('GET', 'POST', etc.)
            url: Request URL
            endpoint_name: Human-readable endpoint name for logging
            params: Query parameters
            json_data: JSON body for POST requests
            timeout: Request timeout in seconds
            validator: Optional validation function (response_data) -> ValidationResult
            delay_range: Random delay range (min, max) in seconds before each request
        
        Returns:
            Response data dict, or error dict with {"code": -1, "data": {}}
        """
        
        for attempt in range(self.max_retries):
            # Get a fresh proxy for each attempt (allows failover)
            current_proxy = self.proxy_manager.get_proxy()
            
            async with self.request_semaphore:
                try:
                    # Random jitter to avoid thundering herd
                    await asyncio.sleep(random.uniform(*delay_range))
                    
                    # Make the request
                    if method.upper() == 'GET':
                        response = await self.session.get(
                            url,
                            params=params,
                            timeout=timeout,
                            proxy=current_proxy
                        )
                    elif method.upper() == 'POST':
                        response = await self.session.post(
                            url,
                            params=params,
                            json=json_data,
                            timeout=timeout,
                            proxy=current_proxy
                        )
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")
                    
                    # Handle rate limiting (429)
                    if response.status_code == 429:
                        self.proxy_manager.report_failure(current_proxy, is_rate_limit=True)
                        wait = (attempt + 1) * self.DEFAULT_RATE_LIMIT_BACKOFF
                        self.logger.debug(f"Rate limit on {endpoint_name}, rotating proxy ({wait}s)")
                        await asyncio.sleep(wait)
                        continue
                    
                    # Handle forbidden (403) - often means proxy is blocked
                    if response.status_code == 403:
                        self.proxy_manager.report_failure(current_proxy)
                        wait = (attempt + 1) * 5
                        self.logger.debug(f"Forbidden (403) on {endpoint_name}, rotating proxy ({wait}s)")
                        await asyncio.sleep(wait)
                        continue
                    
                    # Handle success (200)
                    if response.status_code == 200:
                        response_data = response.json()
                        
                        # Validate response if validator provided
                        if validator:
                            validation = validator(response_data)
                            
                            if validation.valid:
                                self.proxy_manager.report_success(current_proxy)
                                return self._format_success_response(validation.data)
                            else:
                                self.logger.warning(f"{endpoint_name} validation failed: {validation.error}")
                                return self._format_error_response()
                        else:
                            # No validation - return raw data
                            self.proxy_manager.report_success(current_proxy)
                            return response_data
                    
                    # Other non-200 status codes
                    self.proxy_manager.report_failure(current_proxy)
                    self.logger.debug(f"HTTP {response.status_code} on {endpoint_name}, retrying...")
                    await asyncio.sleep(self.DEFAULT_ERROR_BACKOFF)
                    
                except Exception as error:
                    self.proxy_manager.report_failure(current_proxy)
                    self.logger.error(f"Connection error for {endpoint_name}: {type(error).__name__}: {error}")
                    await asyncio.sleep(self.DEFAULT_ERROR_BACKOFF)
        
        # All retries exhausted
        self.logger.error(f"All {self.max_retries} retries exhausted for {endpoint_name}")
        return self._format_error_response()
    
    def _format_success_response(self, data: Any) -> Dict[str, Any]:
        """
        Format a successful response.
        Subclasses can override for custom formatting.
        """
        return {"code": 0, "data": data}
    
    def _format_error_response(self) -> Dict[str, Any]:
        """
        Format an error response.
        Subclasses can override for custom formatting.
        """
        return {"code": -1, "data": {}}
    
    async def get(
        self,
        url: str,
        endpoint_name: str,
        params: Optional[Dict] = None,
        validator: Optional[Callable] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Convenience method for GET requests."""
        return await self._request_with_retry(
            method='GET',
            url=url,
            endpoint_name=endpoint_name,
            params=params,
            validator=validator,
            **kwargs
        )
    
    async def post(
        self,
        url: str,
        endpoint_name: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        validator: Optional[Callable] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Convenience method for POST requests."""
        return await self._request_with_retry(
            method='POST',
            url=url,
            endpoint_name=endpoint_name,
            params=params,
            json_data=json_data,
            validator=validator,
            **kwargs
        )
