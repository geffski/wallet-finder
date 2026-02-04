"""
Logging Framework
Provides structured logging with file rotation for overnight runs.
"""

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Import config (handle circular import)
try:
    from config import LOGS_DIR, LOG_LEVEL, LOG_TO_FILE, LOG_MAX_SIZE_MB, LOG_BACKUP_COUNT
except ImportError:
    # Fallback defaults if config not available
    LOGS_DIR = Path("logs")
    LOG_LEVEL = "INFO"
    LOG_TO_FILE = True
    LOG_MAX_SIZE_MB = 10
    LOG_BACKUP_COUNT = 5


# Custom log levels
API_ALERT = 35  # Between WARNING (30) and ERROR (40)
logging.addLevelName(API_ALERT, "API_ALERT")


class WalletFinderLogger:
    """
    Custom logger with:
    - Console output with colors
    - File output with rotation
    - API change alerts
    - Session statistics
    """
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'API_ALERT': '\033[35m', # Magenta
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[41m',  # Red background
        'RESET': '\033[0m',
    }
    
    # Emoji prefixes for console
    EMOJI = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️',
        'API_ALERT': '🚨',
        'ERROR': '❌',
        'CRITICAL': '💀',
    }
    
    def __init__(self, name: str = "wallet_finder"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)  # Capture all, filter at handler level
        self.logger.handlers = []  # Clear any existing handlers
        
        # Session stats
        self.session_start = datetime.now()
        self.api_alerts = []
        self.error_count = 0
        self.warning_count = 0
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Configure console and file handlers."""
        log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
        
        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(ColoredFormatter())
        self.logger.addHandler(console_handler)
        
        # File handler with rotation
        if LOG_TO_FILE:
            LOGS_DIR.mkdir(exist_ok=True)
            
            # Main log file
            log_file = LOGS_DIR / f"wallet_finder_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=LOG_MAX_SIZE_MB * 1024 * 1024,
                backupCount=LOG_BACKUP_COUNT,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)  # Log everything to file
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            self.logger.addHandler(file_handler)
            
            # Separate error log
            error_file = LOGS_DIR / "errors.log"
            error_handler = RotatingFileHandler(
                error_file,
                maxBytes=LOG_MAX_SIZE_MB * 1024 * 1024,
                backupCount=LOG_BACKUP_COUNT,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.WARNING)
            error_handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s\n',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            self.logger.addHandler(error_handler)
    
    def debug(self, message: str):
        self.logger.debug(message)
    
    def info(self, message: str):
        self.logger.info(message)
    
    def warning(self, message: str):
        self.warning_count += 1
        self.logger.warning(message)
    
    def error(self, message: str, exc_info: bool = False):
        self.error_count += 1
        self.logger.error(message, exc_info=exc_info)
    
    def critical(self, message: str, exc_info: bool = True):
        self.error_count += 1
        self.logger.critical(message, exc_info=exc_info)
    
    def api_alert(self, api_name: str, message: str, expected: str = None, got: str = None):
        """
        Log an API schema/structure change alert.
        These are important to review as they indicate the API may have changed.
        """
        alert = {
            'timestamp': datetime.now().isoformat(),
            'api': api_name,
            'message': message,
            'expected': expected,
            'got': got
        }
        self.api_alerts.append(alert)
        
        full_message = f"[{api_name}] {message}"
        if expected and got:
            full_message += f" (expected: {expected}, got: {got})"
        
        self.logger.log(API_ALERT, full_message)
    
    def session_summary(self):
        """Print a summary of the session for review."""
        duration = datetime.now() - self.session_start
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        self.logger.info("=" * 60)
        self.logger.info("SESSION SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Duration: {hours}h {minutes}m {seconds}s")
        self.logger.info(f"Errors: {self.error_count}")
        self.logger.info(f"Warnings: {self.warning_count}")
        self.logger.info(f"API Alerts: {len(self.api_alerts)}")
        
        if self.api_alerts:
            self.logger.warning("⚠️  API ALERTS DETECTED - Review these carefully:")
            for alert in self.api_alerts:
                self.logger.warning(f"  [{alert['api']}] {alert['message']}")
        
        if LOG_TO_FILE:
            self.logger.info(f"Logs saved to: {LOGS_DIR}")
        
        self.logger.info("=" * 60)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""
    
    def format(self, record):
        # Get color and emoji for this level
        level_name = record.levelname
        color = WalletFinderLogger.COLORS.get(level_name, '')
        reset = WalletFinderLogger.COLORS['RESET']
        emoji = WalletFinderLogger.EMOJI.get(level_name, '')
        
        # Format timestamp
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Build message
        if level_name in ('DEBUG',):
            formatted = f"{color}[{timestamp}] {record.getMessage()}{reset}"
        else:
            formatted = f"{emoji} {color}[{timestamp}] {record.getMessage()}{reset}"
        
        return formatted


# Global logger instance
_logger: Optional[WalletFinderLogger] = None


def get_logger() -> WalletFinderLogger:
    """Get the global logger instance."""
    global _logger
    if _logger is None:
        _logger = WalletFinderLogger()
    return _logger


def reset_logger():
    """Reset the global logger (useful for testing)."""
    global _logger
    _logger = None
