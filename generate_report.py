"""
Elite Wallet Report Generator
Generates an HTML report of top-performing wallets with their origin tokens.
Properly deduplicates wallets while showing all their token discoveries.
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict
from pathlib import Path

import config
from logger import get_logger

# --- CONFIGURATION (from centralized config) ---
DB_PATH = str(config.DB_PATH)
OUTPUT_FILE = str(config.REPORT_OUTPUT_PATH)
MIN_GLOBAL_PNL = config.MIN_PNL_THRESHOLD
MIN_TRADES = config.MIN_TRADES_THRESHOLD
MIN_HIGH_PROFIT_TOKENS = config.MIN_HIGH_PROFIT_TOKENS
MIN_TOKEN_PNL_FOR_COUNT = config.MIN_TOKEN_PNL_FOR_COUNT


def fetch_all_audited_wallets(min_capture_date: str = None) -> List[Dict]:
    """
    Fetch all wallets that have been audited, without hardcoded thresholds.
    Returns a list of wallets with their token discoveries.
    Uses a single JOIN query for optimal performance.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database '{DB_PATH}' not found.")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Single query with LEFT JOIN to get wallets and their portfolio in one go
        date_filter = ""
        params = []
        
        if min_capture_date:
            date_filter = "AND cs.captured_at >= ?"
            params.append(min_capture_date)
            
        print("📊 Fetching all audited wallets and portfolio data from database...")
        
        # Single optimized query with LEFT JOIN
        cursor.execute(f'''
            SELECT 
                w.id,
                w.address,
                cs.pnl_usd as global_pnl,
                cs.trades_30d as global_trades,
                cs.captured_at,
                wp.symbol,
                wp.token_address,
                wp.pnl_usd as token_pnl,
                wp.num_swaps
            FROM wallets w
            JOIN cielo_stats cs ON w.id = cs.wallet_id
            LEFT JOIN wallet_portfolio wp ON w.id = wp.wallet_id
            WHERE cs.id IN (SELECT MAX(id) FROM cielo_stats GROUP BY wallet_id)
            {date_filter}
            ORDER BY w.id, wp.pnl_usd DESC
        ''', params)
        
        # Build wallet objects from the joined results
        wallets_dict = {}
        
        for row in cursor.fetchall():
            wid, address, pnl, trades, cap_at, symbol, token_addr, token_pnl, swaps = row
            
            # Create wallet entry if not exists
            if wid not in wallets_dict:
                wallets_dict[wid] = {
                    'address': address,
                    'global_pnl': pnl or 0,
                    'global_trades': trades or 0,
                    'captured_at': cap_at,
                    'discoveries': []
                }
            
            # Add portfolio item if exists (LEFT JOIN may have NULL portfolio)
            if symbol is not None:
                wallets_dict[wid]['discoveries'].append({
                    'symbol': symbol,
                    'pnl_on_token': token_pnl,
                    'address': token_addr,
                    'swaps': swaps
                })
        
        # Convert to list and sort by PnL descending
        all_results = list(wallets_dict.values())
        all_results.sort(key=lambda x: x['global_pnl'], reverse=True)
        
        print(f"   ✅ Loaded {len(all_results)} wallets with portfolio data")
        return all_results
        
    finally:
        conn.close()


def generate_html(min_capture_date: str = None, report_type: str = 'SESSION'):
    """Generate the elite wallets HTML report.
    
    Args:
        min_capture_date: Optional date string to filter wallets from that date onwards.
        report_type: 'ALL' for full dump, 'SESSION' for dated report.
    """
    try:
        wallets = fetch_all_audited_wallets(min_capture_date=min_capture_date)
    except FileNotFoundError as error:
        print(f"❌ Error: {error}")
        return
    except sqlite3.Error as error:
        print(f"❌ Database error: {error}")
        return
    
    if not wallets:
        print("ℹ️ No audited wallets found in database.")
        return

    # Determine filename and banner based on report type
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if report_type == 'ALL':
        filename = "wallet-stats-all.html"
        banner_html = f"""
            <div style="background: linear-gradient(90deg, #d29922 0%, #9e6a03 100%); color: #0d1117; padding: 10px; text-align: center; font-weight: bold; border-radius: 8px; margin-bottom: 20px;">
                ⚠️ FULL DATABASE EXPORT • All {len(wallets)} tracked wallets • {today_str}
            </div>
        """
    else:
        filename = f"wallet-stats-{today_str}.html"
        banner_html = f"""
            <div style="background: linear-gradient(90deg, #3fb950 0%, #2ea043 100%); color: #0d1117; padding: 10px; text-align: center; font-weight: bold; border-radius: 8px; margin-bottom: 20px;">
                📅 SESSION REPORT • {today_str} • {len(wallets)} wallets
            </div>
        """

    output_path = config.DATA_DIR / filename
    
    # Convert wallets to JSON for client-side filtering
    wallets_json = json.dumps(wallets)

    # Build the HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Wallet Intelligence Dashboard</title>
        <style>
            :root {{
                --bg: #0b0f19;
                --card-bg: #161b22;
                --text: #c9d1d9;
                --accent: #58a6ff;
                --border: #30363d;
                --success: #3fb950;
                --warning: #d29922;
                --danger: #f85149;
                --muted: #8b949e;
                --input-bg: rgba(255, 255, 255, 0.05);
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                background-color: var(--bg);
                color: var(--text);
                margin: 0;
                padding: 40px;
                line-height: 1.5;
            }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            h1 {{ font-size: 2rem; color: #f0f6fc; margin-bottom: 5px; }}
            .subtitle {{ color: #8b949e; margin-bottom: 30px; }}
            
            /* SUMMARY BOX */
            .summary {{
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 30px;
                margin-bottom: 20px;
                display: flex;
                gap: 60px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }}
            .summary-stat {{ text-align: left; flex: 1; }}
            .summary-value {{ font-size: 28px; font-weight: bold; color: #f0f6fc; font-family: 'JetBrains Mono', monospace; }}
            .summary-label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}

            /* FILTER BAR */
            .filters-container {{
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 25px;
                margin-bottom: 30px;
                display: flex;
                align-items: flex-end;
                gap: 20px;
                flex-wrap: wrap;
                position: sticky;
                top: 20px;
                z-index: 100;
                box-shadow: 0 8px 24px rgba(0,0,0,0.5);
                backdrop-filter: blur(10px);
            }}
            .filter-group {{
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}
            .filter-group label {{
                font-size: 11px;
                font-weight: bold;
                color: var(--muted);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .filter-input {{
                background: var(--input-bg);
                border: 1px solid var(--border);
                border-radius: 8px;
                color: var(--text);
                padding: 12px 14px;
                font-size: 14px;
                width: 160px;
                transition: all 0.2s;
            }}
            .filter-input:focus {{
                outline: none;
                border-color: var(--accent);
                background: rgba(255, 255, 255, 0.1);
                box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1);
            }}
            .search-input {{ width: 300px; }}
            
            .visible-counter {{
                margin-left: auto;
                text-align: right;
                background: rgba(88, 166, 255, 0.1);
                padding: 10px 20px;
                border-radius: 8px;
                border: 1px solid rgba(88, 166, 255, 0.2);
            }}
            .visible-count {{ font-size: 22px; font-weight: bold; color: var(--accent); }}
            .visible-label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; }}

            /* WALLET CARDS */
            #wallets-list {{
                display: flex;
                flex-direction: column;
                gap: 20px;
            }}
            .wallet-card {{
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 12px;
                overflow: hidden;
                transition: all 0.2s;
                animation: fadeIn 0.4s ease-out;
            }}
            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(10px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            .wallet-card:hover {{ 
                border-color: #58a6ff66; 
                transform: translateY(-2px);
                box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            }}
            
            .wallet-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 20px 25px;
                background: #0d1117;
                border-bottom: 1px solid var(--border);
            }}
            .wallet-address-container {{
                display: flex;
                flex-direction: column;
                gap: 4px;
            }}
            .wallet-address {{
                font-family: 'JetBrains Mono', monospace;
                color: var(--accent);
                font-size: 15px;
                text-decoration: none;
                font-weight: 600;
            }}
            .wallet-address:hover {{ text-decoration: underline; }}
            .capture-date {{ font-size: 11px; color: var(--muted); }}
            
            .wallet-stats {{ display: flex; gap: 40px; }}
            .stat {{ text-align: right; }}
            .stat-value {{
                color: var(--success);
                font-weight: bold;
                font-size: 18px;
                font-family: 'JetBrains Mono', monospace;
            }}
            .stat-label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
            
            .wallet-links {{ display: flex; gap: 12px; }}
            .wallet-links a {{
                color: var(--text);
                text-decoration: none;
                font-size: 12px;
                padding: 8px 16px;
                border: 1px solid var(--border);
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.03);
                transition: all 0.2s;
                font-weight: 500;
            }}
            .wallet-links a:hover {{ 
                background: var(--accent); 
                color: white; 
                border-color: var(--accent);
            }}

            /* TABLE STYLES */
            .tokens-table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
            }}
            .tokens-table th {{
                text-align: left;
                padding: 15px 25px;
                color: var(--muted);
                font-weight: 500;
                border-bottom: 1px solid var(--border);
                background: rgba(255,255,255,0.02);
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .tokens-table td {{
                padding: 14px 25px;
                border-bottom: 1px solid #21262d;
            }}
            .tokens-table tr:last-child td {{ border-bottom: none; }}
            
            .col-token {{ font-weight: 600; color: #f0f6fc; }}
            .col-pnl {{ font-family: 'JetBrains Mono', monospace; text-align: right; }}
            .col-swaps {{ text-align: center; color: var(--muted); width: 120px; }}
            .col-link {{ text-align: right; width: 150px; }}

            .pnl-pos {{ color: var(--success); }}
            .pnl-neg {{ color: var(--danger); }}
            
            .token-link {{
                color: var(--accent);
                text-decoration: none;
                font-size: 11px;
                text-transform: uppercase;
                font-weight: bold;
                padding: 4px 8px;
                border: 1px solid rgba(88, 166, 255, 0.2);
                border-radius: 4px;
                transition: all 0.2s;
            }}
            .token-link:hover {{ 
                background: rgba(88, 166, 255, 0.1);
                border-color: var(--accent);
            }}
            
            .more-tokens-btn {{
                width: 100%;
                padding: 15px;
                background: rgba(255,255,255,0.02);
                border: none;
                border-top: 1px solid var(--border);
                color: var(--muted);
                font-size: 12px;
                cursor: pointer;
                transition: all 0.2s;
            }}
            .more-tokens-btn:hover {{ background: rgba(255,255,255,0.05); color: var(--text); }}

            /* PAGINATION */
            .load-more-container {{
                text-align: center;
                padding: 40px;
                margin-top: 20px;
            }}
            .load-more-btn {{
                background: var(--accent);
                color: white;
                border: none;
                padding: 15px 40px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s, background 0.2s;
                box-shadow: 0 4px 12px rgba(88, 166, 255, 0.3);
            }}
            .load-more-btn:hover {{ 
                transform: translateY(-2px);
                background: #79c0ff;
            }}
            .load-more-btn:disabled {{
                background: var(--border);
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }}

            @media (max-width: 1200px) {{
                .summary {{ gap: 20px; flex-wrap: wrap; }}
                .filters-container {{ top: 10px; padding: 15px; }}
                .search-input {{ width: 100%; order: -1; }}
                .filter-input {{ width: 100px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            {banner_html}
            <h1>🕵️ Terminal Wallet Intelligence</h1>
            <p class="subtitle">Complete audited wallet database. Total records: {len(wallets)}</p>
            
            <div id="summary-container" class="summary">
                <!-- Dynamic Summary -->
            </div>

            <div class="filters-container">
                <div class="filter-group">
                    <label>Search Address</label>
                    <input type="text" id="search-addr" class="filter-input search-input" placeholder="Paste wallet address...">
                </div>
                <div class="filter-group">
                    <label>Min PnL ($)</label>
                    <input type="number" id="min-pnl" class="filter-input" placeholder="0">
                </div>
                <div class="filter-group">
                    <label>Min Trades</label>
                    <input type="number" id="min-trades" class="filter-input" placeholder="0">
                </div>
                <div class="visible-counter">
                    <div id="visible-count" class="visible-count">0</div>
                    <div class="visible-label">Matching Wallets</div>
                </div>
            </div>

            <div id="wallets-list">
                <!-- Dynamic Wallet Cards -->
            </div>

            <div class="load-more-container">
                <button id="load-more" class="load-more-btn">Load More Wallets</button>
            </div>
        </div>

        <script>
            const allWallets = {wallets_json};
            let filteredWallets = [];
            let currentDisplayLimit = 50;
            const CHUNK_SIZE = 50;
            
            const searchInput = document.getElementById('search-addr');
            const minPnlInput = document.getElementById('min-pnl');
            const minTradesInput = document.getElementById('min-trades');
            const walletsList = document.getElementById('wallets-list');
            const visibleCountEl = document.getElementById('visible-count');
            const summaryContainer = document.getElementById('summary-container');
            const loadMoreBtn = document.getElementById('load-more');

            function formatCurrency(val) {{
                return new Intl.NumberFormat('en-US', {{
                    style: 'currency',
                    currency: 'USD',
                    maximumFractionDigits: 0
                }}).format(val);
            }}

            function filterWallets() {{
                const search = searchInput.value.toLowerCase().trim();
                const minPnl = parseFloat(minPnlInput.value) || -Infinity;
                const minTrades = parseInt(minTradesInput.value) || 0;

                filteredWallets = allWallets.filter(w => {{
                    const matchesSearch = !search || w.address.toLowerCase().includes(search);
                    return matchesSearch && w.global_pnl >= minPnl && w.global_trades >= minTrades;
                }});

                currentDisplayLimit = CHUNK_SIZE;
                updateView();
            }}

            function updateView() {{
                renderSummary(filteredWallets);
                renderWallets(filteredWallets.slice(0, currentDisplayLimit));
                visibleCountEl.textContent = filteredWallets.length;
                
                if (currentDisplayLimit >= filteredWallets.length) {{
                    loadMoreBtn.style.display = 'none';
                }} else {{
                    loadMoreBtn.style.display = 'inline-block';
                }}
            }}

            function loadMore() {{
                currentDisplayLimit += CHUNK_SIZE;
                updateView();
            }}

            function renderSummary(data) {{
                const totalPnl = data.reduce((sum, w) => sum + (w.global_pnl || 0), 0);
                const profWallets = data.filter(w => w.global_pnl > 0).length;

                summaryContainer.innerHTML = `
                    <div class="summary-stat">
                        <div class="summary-value">${{data.length.toLocaleString()}}</div>
                        <div class="summary-label">Wallets Found</div>
                    </div>
                    <div class="summary-stat">
                        <div class="summary-value">${{formatCurrency(totalPnl)}}</div>
                        <div class="summary-label">Combined Profit</div>
                    </div>
                    <div class="summary-stat">
                        <div class="summary-value">${{profWallets}}</div>
                        <div class="summary-label">Profitable Wallets</div>
                    </div>
                `;
            }}

            function renderWallets(data) {{
                if (data.length === 0) {{
                    walletsList.innerHTML = '<div style="text-align: center; padding: 100px; color: var(--muted);">No wallets matching your filters</div>';
                    return;
                }}

                walletsList.innerHTML = data.map(wallet => {{
                    const addr = wallet.address;
                    const cieloUrl = `https://app.cielo.finance/profile/${{addr}}?timeframe=30d&sortBy=pnl_desc`;
                    const gmgnUrl = `https://gmgn.ai/sol/address/${{addr}}`;
                    
                    // Show top 5 profitable tokens initially
                    const topTokens = wallet.discoveries
                        .filter(d => d.pnl_on_token >= 0)
                        .slice(0, 5);
                    
                    let tableRows = topTokens.map(t => {{
                        const pnlClass = t.pnl_on_token >= 0 ? "pnl-pos" : "pnl-neg";
                        return `
                            <tr>
                                <td class="col-token">${{t.symbol}}</td>
                                <td class="col-pnl ${{pnlClass}}">${{formatCurrency(t.pnl_on_token)}}</td>
                                <td class="col-swaps">${{t.swaps || '-'}} swaps</td>
                                <td class="col-link">
                                    <a href="https://gmgn.ai/sol/token/${{t.address}}" target="_blank" class="token-link">View Token</a>
                                </td>
                            </tr>
                        `;
                    }}).join('');

                    if (!tableRows) {{
                        tableRows = '<tr><td colspan="4" style="text-align: center; color: var(--muted); padding: 20px;">No profitable trades found in 30d history</td></tr>';
                    }}

                    const remaining = wallet.discoveries.filter(d => d.pnl_on_token >= 0).length - 5;

                    return `
                        <div class="wallet-card">
                            <div class="wallet-header">
                                <div class="wallet-address-container">
                                    <a href="${{cieloUrl}}" target="_blank" class="wallet-address">${{addr}}</a>
                                    <div class="capture-date">Last Audit: ${{wallet.captured_at}}</div>
                                </div>
                                <div class="wallet-stats">
                                    <div class="stat">
                                        <div class="stat-value ${{wallet.global_pnl >= 0 ? 'pnl-pos' : 'pnl-neg'}}">
                                            ${{formatCurrency(wallet.global_pnl)}}
                                        </div>
                                        <div class="stat-label">30d PnL</div>
                                    </div>
                                    <div class="stat">
                                        <div class="stat-value">${{wallet.global_trades}}</div>
                                        <div class="stat-label">Total Trades</div>
                                    </div>
                                </div>
                                <div class="wallet-links">
                                    <a href="${{gmgnUrl}}" target="_blank">GMGN</a>
                                    <a href="${{cieloUrl}}" target="_blank">Cielo</a>
                                </div>
                            </div>
                            <table class="tokens-table">
                                <thead>
                                    <tr>
                                        <th>Token</th>
                                        <th style="text-align: right">Realized PnL</th>
                                        <th style="text-align: center">Activity</th>
                                        <th></th>
                                    </tr>
                                </thead>
                                <tbody>${{tableRows}}</tbody>
                            </table>
                            ${{remaining > 0 ? `<button class="more-tokens-btn" onclick="window.open('${{cieloUrl}}', '_blank')">View ${{remaining}} more profitable trades on Cielo ↗</button>` : ''}}
                        </div>
                    `;
                }}).join('');
            }}

            [searchInput, minPnlInput, minTradesInput].forEach(el => {{
                el.addEventListener('input', filterWallets);
            }});

            loadMoreBtn.addEventListener('click', loadMore);

            // Initial Filter & Render
            filterWallets();
        </script>
    </body>
    </html>
    """

    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write(html)
    
    print(f"✅ Full Report generated: {output_path}")
    print(f"   📊 {len(wallets)} wallets processed.")
    
    import webbrowser
    report_url = Path(output_path).as_uri()
    print(f"   🔗 Opening report: {report_url}\n")
    webbrowser.open(report_url)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Generate Full Wallet Report')
    parser.add_argument('--date', type=str, default=None, 
                        help='Minimum capture date (e.g., 2026-01-01)')
    parser.add_argument('--type', type=str, choices=['ALL', 'SESSION'], default='SESSION',
                        help="Report type: 'ALL' for full database, 'SESSION' for dated report")
    args = parser.parse_args()
    generate_html(min_capture_date=args.date, report_type=args.type)

