import sqlite3
import threading
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from functools import partial
import config

class DatabaseManager:
    """
    Optimized SQLite database manager with:
    - Persistent connection (no per-operation connection overhead)
    - Thread-safe singleton connection
    - Proper IntegrityError handling for race conditions
    - Transaction support for batch operations
    - Eliminated N+1 query patterns
    - Async wrappers for non-blocking operation in async code
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: str = "wallet_finder.db"):
        """Ensure single instance (singleton pattern) - thread-safe."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
                cls._instance._db_path = db_path
            return cls._instance
    
    def __init__(self, db_path: str = "wallet_finder.db"):
        with self._lock:
            if self._initialized:
                # Warn if trying to use different db_path than existing instance
                if db_path != self._db_path:
                    import warnings
                    warnings.warn(
                        f"DatabaseManager singleton already exists with db_path='{self._db_path}'. "
                        f"Ignoring new db_path='{db_path}'.",
                        RuntimeWarning
                    )
                return
            
            self.db_path = db_path
            self._db_path = db_path
            self._conn = None
            self._conn_lock = threading.Lock()
            self._write_lock = threading.Lock()  # Lock for sync write operations
            # Separate async locks: WAL mode allows concurrent reads with one writer
            self._db_async_write_lock = asyncio.Lock()  # Serialize async writes
            # No read lock needed - WAL mode handles concurrent reads natively
            self._init_db()
            self._initialized = True

    def _get_connection(self) -> sqlite3.Connection:
        """
        Returns a persistent connection. Thread-safe.
        Uses check_same_thread=False for asyncio compatibility.
        """
        if self._conn is None:
            with self._conn_lock:
                if self._conn is None:
                    self._conn = sqlite3.connect(
                        self.db_path, 
                        check_same_thread=False,
                        timeout=30.0  # Wait up to 30s for locks
                    )
                    # Enable WAL mode for better concurrent read/write
                    self._conn.execute("PRAGMA journal_mode=WAL")
                    self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self):
        """Initialize the database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Table for Tokens with ATH Price
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE NOT NULL,
                symbol TEXT,
                ath_price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table for Wallets with Generated Links
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cielo_link TEXT GENERATED ALWAYS AS (
                    'https://app.cielo.finance/profile/' || address || '?timeframe=30d&sortBy=pnl_desc'
                ) VIRTUAL,
                gmgn_link TEXT GENERATED ALWAYS AS (
                    'https://gmgn.ai/sol/address/' || address
                ) VIRTUAL
            )
        ''')
        
        # Table for Discovery Hits (Wallet found in a specific Token)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS discovery_hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_id INTEGER,
                wallet_id INTEGER,
                category TEXT,
                rank INTEGER,
                pnl_on_token REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (token_id) REFERENCES tokens (id),
                FOREIGN KEY (wallet_id) REFERENCES wallets (id)
            )
        ''')
        
        # Table for Cielo Performance Stats with Generated Links
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cielo_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id INTEGER NOT NULL,
                pnl_usd REAL,
                trades_30d INTEGER,
                captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (wallet_id) REFERENCES wallets (id)
            )
        ''')
        # Table for Wallet Portfolio (Detailed token performance from Cielo)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wallet_portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            )
        ''')

        # Table for Blocked Bots (Over 5k trades)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id INTEGER UNIQUE NOT NULL,
                reason TEXT,
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (wallet_id) REFERENCES wallets (id)
            )
        ''')
        
        # Indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_wallet_address ON wallets(address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_token_address ON tokens(address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_discovery_wallet ON discovery_hits(wallet_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stats_wallet ON cielo_stats(wallet_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_portfolio_wallet ON wallet_portfolio(wallet_id)')
        
        conn.commit()
        
        # Run migrations after initial schema
        self._run_migrations()

    def _get_schema_version(self) -> int:
        """Get current database schema version."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create version table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        ''')
        conn.commit()
        
        cursor.execute('SELECT MAX(version) FROM schema_version')
        result = cursor.fetchone()
        return result[0] if result[0] else 0

    def _set_schema_version(self, version: int, description: str):
        """Record that a migration was applied."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO schema_version (version, description) VALUES (?, ?)',
            (version, description)
        )
        conn.commit()

    def _run_migrations(self):
        """
        Apply database migrations based on version.
        
        Add new migrations here as the schema evolves.
        Each migration should:
        1. Check current version
        2. Apply changes if needed
        3. Update version
        """
        current_version = self._get_schema_version()
        logger = get_logger()
        
        # Example Migration 1: Add last_updated column to wallets
        # (Not needed now, but shows the pattern)
        # if current_version < 1:
        #     logger.info("📦 Applying migration 1: Adding last_updated column to wallets...")
        #     conn = self._get_connection()
        #     cursor = conn.cursor()
        #     cursor.execute('ALTER TABLE wallets ADD COLUMN last_updated TIMESTAMP')
        #     conn.commit()
        #     self._set_schema_version(1, "Added last_updated column to wallets")
        #     logger.info("   ✅ Migration 1 complete")
        
        # Future migrations go here
        # if current_version < 2:
        #     logger.info("📦 Applying migration 2: ...")
        #     ...
        #     self._set_schema_version(2, "Description of migration 2")
        #     logger.info("   ✅ Migration 2 complete")
        
        if current_version == 0:
            logger.debug("Database schema is up to date (no migrations needed)")

    def get_or_create_wallet(self, wallet_address: str, cursor: sqlite3.Cursor = None) -> int:
        """
        Returns the internal ID of a wallet, creating it if it doesn't exist.
        Uses INSERT ... ON CONFLICT ... RETURNING for single-query efficiency.
        Thread-safe with write lock.
        """
        if wallet_address in config.BANNED_WALLETS:
            raise ValueError(f"CRITICAL: Attempted to process BANNED wallet {wallet_address}. Blocking database write.")

        with self._write_lock:
            conn = self._get_connection()
            active_cursor = cursor or conn.cursor()
            
            # Single query: Insert if not exists, always return ID
            # SQLite 3.35+ supports RETURNING clause
            active_cursor.execute('''
                INSERT INTO wallets (address) VALUES (?)
                ON CONFLICT(address) DO UPDATE SET address = address
                RETURNING id
            ''', (wallet_address,))
            
            result = active_cursor.fetchone()
            
            if cursor is None:
                conn.commit()
            
            return result[0]

    def get_or_create_token(self, token_address: str, symbol: str = None, ath_price: float = None, cursor: sqlite3.Cursor = None) -> int:
        """
        Returns the internal ID of a token, creating it if it doesn't exist.
        Uses INSERT ... ON CONFLICT ... RETURNING for efficiency.
        Updates symbol/ath_price if they were NULL.
        Thread-safe with write lock.
        """
        with self._write_lock:
            conn = self._get_connection()
            active_cursor = cursor or conn.cursor()
            
            # Single query using UPSERT pattern with RETURNING
            # This handles: insert new, return existing, and update NULL fields
            active_cursor.execute('''
                INSERT INTO tokens (address, symbol, ath_price) VALUES (?, ?, ?)
                ON CONFLICT(address) DO UPDATE SET 
                    symbol = COALESCE(tokens.symbol, excluded.symbol),
                    ath_price = COALESCE(tokens.ath_price, excluded.ath_price)
                RETURNING id
            ''', (token_address, symbol, ath_price))
            
            result = active_cursor.fetchone()
            
            if cursor is None:
                conn.commit()
            
            return result[0]

    def add_discovery_hit(self, token_address: str, wallet_address: str, category: str, rank: int, pnl_on_token: float, symbol: str = None, ath_price: float = None):
        """
        Records a wallet being found in a specific token list.
        Uses a single transaction for all operations (fixes N+1 pattern).
        Thread-safe with write lock.
        """
        with self._write_lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # All operations share the same cursor/transaction
                token_id = self.get_or_create_token(token_address, symbol, ath_price, cursor=cursor)
                wallet_id = self.get_or_create_wallet(wallet_address, cursor=cursor)
                
                cursor.execute('''
                    INSERT INTO discovery_hits (token_id, wallet_id, category, rank, pnl_on_token)
                    VALUES (?, ?, ?, ?, ?)
                ''', (token_id, wallet_id, category, rank, pnl_on_token))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e

    def add_discovery_hits_batch(self, hits: List[Dict]):
        """
        Batch insert multiple discovery hits in a single transaction.
        Much more efficient than individual inserts.
        Thread-safe with write lock.
        
        hits: List of dicts with keys: token_address, wallet_address, category, rank, pnl_on_token, symbol, ath_price
        """
        if not hits:
            return
        
        with self._write_lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # Cache for token/wallet IDs to avoid repeated lookups within the batch
                token_cache = {}
                wallet_cache = {}
                
                for hit in hits:
                    token_addr = hit['token_address']
                    wallet_addr = hit['wallet_address']
                    
                    # Double-check safety: Skip banned wallets
                    if wallet_addr in config.BANNED_WALLETS:
                        continue
                    
                    # Get or create token (use cache if available)
                    if token_addr not in token_cache:
                        token_cache[token_addr] = self.get_or_create_token(
                            token_addr, 
                            hit.get('symbol'), 
                            hit.get('ath_price'),
                            cursor=cursor
                        )
                    token_id = token_cache[token_addr]
                    
                    # Get or create wallet (use cache if available)
                    if wallet_addr not in wallet_cache:
                        wallet_cache[wallet_addr] = self.get_or_create_wallet(wallet_addr, cursor=cursor)
                    wallet_id = wallet_cache[wallet_addr]
                    
                    cursor.execute('''
                        INSERT INTO discovery_hits (token_id, wallet_id, category, rank, pnl_on_token)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (token_id, wallet_id, hit['category'], hit['rank'], hit['pnl_on_token']))
                
                conn.commit()
                
            except Exception as e:
                conn.rollback()
                raise e

    def add_cielo_stats(self, wallet_address: str, pnl_usd: float, trades: int):
        """Adds a new performance snapshot for a wallet. Thread-safe with write lock."""
        with self._write_lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                wallet_id = self.get_or_create_wallet(wallet_address, cursor=cursor)
                rounded_pnl = round(pnl_usd, 2)
                
                cursor.execute('''
                    INSERT INTO cielo_stats (wallet_id, wallet_address, pnl_usd, trades_30d)
                    VALUES (?, ?, ?, ?)
                ''', (wallet_id, wallet_address, rounded_pnl, trades))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e

    def add_cielo_stats_batch(self, stats: List[Dict]):
        """
        Batch insert multiple cielo stats in a single transaction.
        Thread-safe with write lock.
        
        stats: List of dicts with keys: wallet_address, pnl_usd, trades
        """
        if not stats:
            return
        
        with self._write_lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                wallet_cache = {}
                
                for stat in stats:
                    wallet_addr = stat['wallet_address']
                    
                    if wallet_addr not in wallet_cache:
                        wallet_cache[wallet_addr] = self.get_or_create_wallet(wallet_addr, cursor=cursor)
                    wallet_id = wallet_cache[wallet_addr]
                    
                    cursor.execute('''
                        INSERT INTO cielo_stats (wallet_id, wallet_address, pnl_usd, trades_30d)
                        VALUES (?, ?, ?, ?)
                    ''', (wallet_id, wallet_addr, round(stat['pnl_usd'], 2), stat['trades']))
                
                conn.commit()
                
            except Exception as e:
                conn.rollback()
                raise e

    def get_pending_wallets(self, min_hours_since_check: int = 168) -> List[str]:
        """Gets wallets that need auditing (un-checked, or checked long ago), excluding bots."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT w.address
            FROM wallets w
            JOIN discovery_hits dh ON w.id = dh.wallet_id
            LEFT JOIN bots b ON w.id = b.wallet_id
            LEFT JOIN (
                SELECT wallet_id, MAX(captured_at) as last_check
                FROM cielo_stats
                GROUP BY wallet_id
            ) stats ON w.id = stats.wallet_id
            WHERE b.id IS NULL 
            AND (stats.last_check IS NULL 
                 OR (julianday('now') - julianday(stats.last_check)) * 24 > ?)
        ''', (min_hours_since_check,))
        
        return [row[0] for row in cursor.fetchall()]

    def get_top_alpha_wallets(self, min_token_overlap: int = 2) -> List[Dict]:
        """
        Returns wallets found in multiple tokens, ranked by consistency.
        Returns structured data instead of concatenated strings.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Step 1: Get wallets that appear in multiple tokens
        cursor.execute('''
            SELECT 
                w.id,
                w.address,
                COUNT(DISTINCT dh.token_id) as token_count,
                MAX(cs.pnl_usd) as global_pnl,
                MAX(cs.trades_30d) as total_trades
            FROM wallets w
            JOIN discovery_hits dh ON w.id = dh.wallet_id
            LEFT JOIN cielo_stats cs ON w.id = cs.wallet_id
            GROUP BY w.id
            HAVING token_count >= ?
            ORDER BY token_count DESC, global_pnl DESC
        ''', (min_token_overlap,))
        
        wallets = cursor.fetchall()
        
        if not wallets:
            return []
        
        wallet_ids = [row[0] for row in wallets]
        
        # Step 2: Get token details for these wallets in a single query
        # Build parameterized query safely without f-strings
        placeholders = ','.join('?' * len(wallet_ids))
        query = '''
            SELECT 
                dh.wallet_id,
                t.symbol,
                ROUND(dh.pnl_on_token, 0) as pnl,
                dh.category,
                dh.rank
            FROM discovery_hits dh
            JOIN tokens t ON dh.token_id = t.id
            WHERE dh.wallet_id IN ({})
            ORDER BY dh.wallet_id, dh.pnl_on_token DESC
        '''.format(placeholders)
        cursor.execute(query, wallet_ids)
        
        # Group token details by wallet_id
        token_details_by_wallet = {}
        for row in cursor.fetchall():
            wallet_id = row[0]
            if wallet_id not in token_details_by_wallet:
                token_details_by_wallet[wallet_id] = []
            token_details_by_wallet[wallet_id].append({
                'symbol': row[1],
                'pnl': row[2],
                'category': row[3],
                'rank': row[4]
            })
        
        # Build final result with structured data
        results = []
        for wallet_row in wallets:
            wallet_id, address, token_count, global_pnl, total_trades = wallet_row
            results.append({
                'address': address,
                'token_count': token_count,
                'global_pnl': global_pnl or 0,
                'total_trades': total_trades or 0,
                'token_hits': token_details_by_wallet.get(wallet_id, [])
            })
        
        return results

    def save_wallet_portfolio(self, wallet_address: str, trades: List[Dict]):
        """Save high-performing trades for a specific wallet. Thread-safe with write lock."""
        with self._write_lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # 1. Get wallet ID
                cursor.execute("SELECT id FROM wallets WHERE address = ?", (wallet_address,))
                row = cursor.fetchone()
                if not row:
                    return
                wallet_id = row[0]
                
                # 2. UPSERT trades
                # Batch insert for efficiency
                for trade in trades:
                    cursor.execute('''
                        INSERT INTO wallet_portfolio (
                            wallet_id, token_address, symbol, name, pnl_usd, num_swaps, last_trade_ts, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(wallet_id, token_address) DO UPDATE SET
                            symbol = excluded.symbol,
                            name = excluded.name,
                            pnl_usd = excluded.pnl_usd,
                            num_swaps = excluded.num_swaps,
                            last_trade_ts = excluded.last_trade_ts,
                            updated_at = CURRENT_TIMESTAMP
                    ''', (
                        wallet_id,
                        trade.get('token_address'),
                        trade.get('symbol') or trade.get('token_symbol'), # Handle both keys
                        trade.get('name') or trade.get('token_name'),
                        trade.get('pnl_usd') or trade.get('total_pnl_usd'),
                        trade.get('num_swaps'),
                        trade.get('last_trade_ts') or trade.get('last_trade')
                    ))
                
                conn.commit()
            except sqlite3.Error as e:
                conn.rollback()
                raise e

    def get_wallet_portfolio(self, wallet_address: str, min_pnl: float = 1000) -> List[Dict]:
        """Fetch saved portfolio for a wallet, filtered by PnL."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wp.token_address, wp.symbol, wp.name, wp.pnl_usd, wp.num_swaps
            FROM wallet_portfolio wp
            JOIN wallets w ON wp.wallet_id = w.id
            WHERE w.address = ? AND wp.pnl_usd >= ?
            ORDER BY wp.pnl_usd DESC
        ''', (wallet_address, min_pnl))
        
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def mark_as_bot(self, wallet_address: str, reason: str = "over 5k trades"):
        """Mark a wallet as a bot to permanently exclude it from auditing. Thread-safe with write lock."""
        with self._write_lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                wallet_id = self.get_or_create_wallet(wallet_address, cursor=cursor)
                cursor.execute('''
                    INSERT INTO bots (wallet_id, reason) VALUES (?, ?)
                    ON CONFLICT(wallet_id) DO NOTHING
                ''', (wallet_id, reason))
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e

    def close(self):
        """Explicitly close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # =========================================================================
    # ASYNC WRAPPERS - Non-blocking versions for use in async code
    # These run the sync operations in a thread pool to avoid blocking
    # the asyncio event loop.
    # WAL mode allows concurrent reads, so only writes need locking.
    # =========================================================================

    async def async_get_or_create_token(self, token_address: str, symbol: str = None, ath_price: float = None) -> int:
        """Async version of get_or_create_token - runs in thread pool."""
        async with self._db_async_write_lock:
            return await asyncio.to_thread(self.get_or_create_token, token_address, symbol, ath_price)

    async def async_add_discovery_hit(self, token_address: str, wallet_address: str, 
                                       category: str, rank: int, pnl_on_token: float, 
                                       symbol: str = None, ath_price: float = None):
        """Async version of add_discovery_hit - runs in thread pool."""
        async with self._db_async_write_lock:
            return await asyncio.to_thread(
                self.add_discovery_hit, 
                token_address, wallet_address, category, rank, pnl_on_token, symbol, ath_price
            )

    async def async_add_discovery_hits_batch(self, hits: List[Dict]):
        """Async version of add_discovery_hits_batch - runs in thread pool."""
        async with self._db_async_write_lock:
            return await asyncio.to_thread(self.add_discovery_hits_batch, hits)

    async def async_add_cielo_stats(self, wallet_address: str, pnl_usd: float, trades: int):
        """Async version of add_cielo_stats - runs in thread pool."""
        async with self._db_async_write_lock:
            return await asyncio.to_thread(self.add_cielo_stats, wallet_address, pnl_usd, trades)

    async def async_add_cielo_stats_batch(self, stats: List[Dict]):
        """Async version of add_cielo_stats_batch - runs in thread pool."""
        async with self._db_async_write_lock:
            return await asyncio.to_thread(self.add_cielo_stats_batch, stats)

    async def async_get_pending_wallets(self, min_hours_since_check: int = 12) -> List[str]:
        """Async version of get_pending_wallets - runs in thread pool. No lock needed (WAL mode allows concurrent reads)."""
        return await asyncio.to_thread(self.get_pending_wallets, min_hours_since_check)

    async def async_get_top_alpha_wallets(self, min_token_overlap: int = 2) -> List[Dict]:
        """Async version of get_top_alpha_wallets - runs in thread pool. No lock needed (WAL mode allows concurrent reads)."""
        return await asyncio.to_thread(self.get_top_alpha_wallets, min_token_overlap)

    async def async_save_wallet_portfolio(self, wallet_address: str, trades: List[Dict]):
        """Async version of save_wallet_portfolio - runs in thread pool."""
        async with self._db_async_write_lock:
            return await asyncio.to_thread(self.save_wallet_portfolio, wallet_address, trades)

    async def async_get_wallet_portfolio(self, wallet_address: str, min_pnl: float = 1000):
        """Async version of get_wallet_portfolio - runs in thread pool. No lock needed (WAL mode allows concurrent reads)."""
        return await asyncio.to_thread(self.get_wallet_portfolio, wallet_address, min_pnl)

    async def async_get_all_wallets(self) -> List[str]:
        """Get ALL wallet addresses from the database, excluding bots. No lock needed (WAL mode allows concurrent reads)."""
        def _get_all():
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT w.address FROM wallets w
                LEFT JOIN bots b ON w.id = b.wallet_id
                WHERE b.id IS NULL
                ORDER BY w.id
            ''')
            return [row[0] for row in cursor.fetchall()]
        
        return await asyncio.to_thread(_get_all)
    
    async def async_mark_as_bot(self, wallet_address: str, reason: str = "over 5k trades"):
        """Async version of mark_as_bot."""
        async with self._db_async_write_lock:
            return await asyncio.to_thread(self.mark_as_bot, wallet_address, reason)

    async def async_get_all_token_addresses(self) -> List[str]:
        """Get ALL processed token addresses from the database. No lock needed (WAL mode allows concurrent reads)."""
        def _get_all():
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT address FROM tokens')
            return [row[0] for row in cursor.fetchall()]
        
        return await asyncio.to_thread(_get_all)
