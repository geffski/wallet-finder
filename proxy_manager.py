"""
Proxy Manager - Smart Rotation & Health Tracking
Manages residential proxies with automatic failover and health monitoring.
"""

import os
import random
import time
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class ProxyHealth:
    """Tracks health metrics for a single proxy."""
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    last_used: float = 0.0
    last_success: float = 0.0
    is_cooling_down: bool = False
    cooldown_until: float = 0.0
    
    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0
    
    @property
    def is_healthy(self) -> bool:
        """A proxy is unhealthy if it has 3+ consecutive failures."""
        if self.is_cooling_down and time.time() < self.cooldown_until:
            return False
        return self.consecutive_failures < 3


class ProxyManager:
    """
    Intelligent proxy rotation with health tracking.
    
    Features:
    - Round-robin rotation with health awareness
    - Automatic cooldown for failing proxies
    - Failover to healthy proxies
    - Statistics tracking
    """
    
    # Cooldown duration after 3 consecutive failures (seconds)
    COOLDOWN_DURATION = 60
    
    def __init__(self):
        self.proxies: List[str] = []
        self.health: Dict[str, ProxyHealth] = {}
        self.current_index: int = 0
        self.enabled: bool = False
        self._load_proxies()
    
    def _load_proxies(self):
        """Load proxies from environment variables."""
        use_proxies = os.getenv("USE_PROXIES", "true").lower()
        if use_proxies != "true":
            print("⚠️  Proxies disabled via USE_PROXIES=false")
            return
        
        proxy_str = os.getenv("RESIDENTIAL_PROXIES", "")
        if not proxy_str:
            print("⚠️  No proxies found in RESIDENTIAL_PROXIES env var")
            return
        
        raw_proxies = [p.strip() for p in proxy_str.split(",") if p.strip()]
        
        for raw in raw_proxies:
            formatted = self._format_proxy(raw)
            if formatted:
                self.proxies.append(formatted)
                self.health[formatted] = ProxyHealth()
        
        if self.proxies:
            self.enabled = True
            print(f"🌐 Loaded {len(self.proxies)} residential proxies")
            # Shuffle for randomized starting point
            random.shuffle(self.proxies)
    
    def _format_proxy(self, raw: str) -> Optional[str]:
        """
        Convert host:port:user:pass to http://user:pass@host:port
        """
        parts = raw.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            return f"http://{user}:{password}@{host}:{port}"
        elif len(parts) == 2:
            # No auth: host:port
            host, port = parts
            return f"http://{host}:{port}"
        else:
            # Don't log raw proxy string - may contain credentials
            print(f"⚠️  Invalid proxy format: [REDACTED] (expected host:port:user:pass or host:port)")
            return None
    
    def get_proxy(self) -> Optional[str]:
        """
        Get the next healthy proxy using smart rotation.
        Returns None if proxies are disabled or all are unhealthy.
        """
        if not self.enabled or not self.proxies:
            return None
        
        # Try to find a healthy proxy, starting from current index
        attempts = 0
        while attempts < len(self.proxies):
            proxy = self.proxies[self.current_index]
            health = self.health[proxy]
            
            # Check if cooldown has expired
            if health.is_cooling_down and time.time() >= health.cooldown_until:
                health.is_cooling_down = False
                health.consecutive_failures = 0
                print(f"🔄 Proxy {self._mask_proxy(proxy)} recovered from cooldown")
            
            # Rotate index for next call
            self.current_index = (self.current_index + 1) % len(self.proxies)
            
            if health.is_healthy:
                health.last_used = time.time()
                return proxy
            
            attempts += 1
        
        # All proxies are unhealthy - force use the oldest cooldown one
        print("⚠️  All proxies in cooldown, using least-recently-used")
        oldest = min(self.proxies, key=lambda p: self.health[p].cooldown_until)
        self.health[oldest].is_cooling_down = False
        return oldest
    
    def report_success(self, proxy: str):
        """Report a successful request through this proxy."""
        if proxy and proxy in self.health:
            proxy_health = self.health[proxy]
            proxy_health.success_count += 1
            proxy_health.consecutive_failures = 0
            proxy_health.last_success = time.time()
            proxy_health.is_cooling_down = False
    
    def report_failure(self, proxy: str, is_rate_limit: bool = False):
        """
        Report a failed request through this proxy.
        Rate limits are less severe than connection failures.
        """
        if proxy and proxy in self.health:
            proxy_health = self.health[proxy]
            proxy_health.failure_count += 1
            
            # Rate limits add 1, hard failures add 2 to consecutive count
            proxy_health.consecutive_failures += 1 if is_rate_limit else 2
            
            if proxy_health.consecutive_failures >= 3:
                proxy_health.is_cooling_down = True
                proxy_health.cooldown_until = time.time() + self.COOLDOWN_DURATION
                print(f"🧊 Proxy {self._mask_proxy(proxy)} entering {self.COOLDOWN_DURATION}s cooldown")
    
    def _mask_proxy(self, proxy: str) -> str:
        """Mask proxy credentials for logging."""
        if "@" in proxy:
            # http://user:pass@host:port -> http://***@host:port
            prefix, suffix = proxy.split("@")
            return f"***@{suffix}"
        return proxy
    
    def get_stats(self) -> Dict:
        """Get statistics for all proxies."""
        stats = {
            "total": len(self.proxies),
            "healthy": sum(1 for p in self.proxies if self.health[p].is_healthy),
            "in_cooldown": sum(1 for p in self.proxies if self.health[p].is_cooling_down),
            "proxies": []
        }
        
        for proxy in self.proxies:
            h = self.health[proxy]
            stats["proxies"].append({
                "proxy": self._mask_proxy(proxy),
                "success": h.success_count,
                "failures": h.failure_count,
                "success_rate": f"{h.success_rate:.1%}",
                "healthy": h.is_healthy
            })
        
        return stats
    
    def print_stats(self):
        """Print a summary of proxy health."""
        stats = self.get_stats()
        print(f"\n📊 PROXY STATS: {stats['healthy']}/{stats['total']} healthy")
        for p in stats["proxies"]:
            status = "✅" if p["healthy"] else "🧊"
            print(f"   {status} {p['proxy']}: {p['success']}/{p['success']+p['failures']} ({p['success_rate']})")


# Global singleton instance
_proxy_manager: Optional[ProxyManager] = None

def get_proxy_manager() -> ProxyManager:
    """Get the global ProxyManager instance."""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager
