"""
Queue Manager
Synchronizes the manual_tokens.txt queue with the database.

Logic:
1. Reads all discovered tokens from 'wallet_portfolio' table.
2. Reads all already processed tokens from 'tokens' table.
3. Calculates pending tokens (Discovered - Processed).
4. Updates 'manual_tokens.txt' with the pending list, preserving user comments.
"""

import sqlite3
import os
import config
from logger import get_logger

logger = get_logger()

def sync_queue():
    db_path = str(config.DB_PATH)
    manual_tokens_path = config.MANUAL_TOKENS_PATH
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return

    print("🔄 Synchronizing Token Queue...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. Get all tokens that HAVE been processed (Table: tokens)
        cursor.execute("SELECT address FROM tokens")
        processed_tokens = {row[0] for row in cursor.fetchall()}
        print(f"   📚 Processed Tokens (History): {len(processed_tokens)}")
        
        # 2. Get all tokens discovered in portfolios (Table: wallet_portfolio)
        cursor.execute("SELECT DISTINCT token_address FROM wallet_portfolio WHERE token_address IS NOT NULL AND length(token_address) > 30")
        discovered_tokens = {row[0] for row in cursor.fetchall()}
        print(f"   🌍 Discovered Tokens (Total): {len(discovered_tokens)}")
        
        # 3. Calculate Pending (Discovered - Processed)
        pending_tokens = discovered_tokens - processed_tokens
        
        # 4. Read manual_tokens.txt to preserve comments
        comments = []
        existing_manual = set()
        
        if manual_tokens_path.exists():
            with open(manual_tokens_path, 'r') as f:
                for line in f:
                    original = line
                    line = line.strip()
                    if line.startswith("#"):
                        comments.append(original)
                    elif line:
                        existing_manual.add(line)
        
        # Add any tokens manually added to the file that aren't in DB yet
        # (This protects manually added tokens that haven't been run yet)
        manually_added_pending = existing_manual - processed_tokens
        final_queue = pending_tokens.union(manually_added_pending)
        
        print(f"   ⏳ Pending Queue Size: {len(final_queue)}")
        
        # 5. Write back to file
        with open(manual_tokens_path, 'w') as f:
            # Write comments first
            for comment in comments:
                f.write(comment)
                if not comment.endswith('\n'):
                    f.write('\n')
            
            # Write pending tokens sorted
            for token in sorted(final_queue):
                f.write(f"{token}\n")
                
        print(f"✅ Queue updated! {len(final_queue)} tokens ready for top-trader.py")
        print(f"   📁 File: {manual_tokens_path}")

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    sync_queue()
