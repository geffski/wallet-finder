#!/bin/bash
# Fresh Git Repository Setup
# Run this script to reset and republish your wallet-finder repo

echo "🧹 Cleaning up old git history..."
rm -rf .git

echo "📦 Initializing fresh repository..."
git init

echo "📝 Adding files..."
git add .

echo "💾 Creating initial commit..."
git commit -m "Initial commit - Wallet Finder Bot

Features:
- Elite Solana wallet discovery from trending tokens
- Automated wallet performance auditing
- HTML report generation with filtering
- Proxy rotation and rate limit handling
- Circuit breaker for API failures
- Database migrations for schema evolution

Tech Stack:
- Python 3.x
- SQLite (WAL mode)
- GMGN API (discovery)
- Cielo Finance API (auditing)
- curl-cffi (HTTP client)
"

echo "🔗 Adding remote..."
git remote add origin https://github.com/geffski/wallet-finder.git

echo "🌿 Setting main branch..."
git branch -M main

echo "🚀 Force pushing to GitHub..."
echo "⚠️  This will overwrite the existing repository!"
read -p "Press Enter to continue or Ctrl+C to cancel..."

git push -u origin main --force

echo "✅ Done! Repository published to:"
echo "   https://github.com/geffski/wallet-finder"
echo ""
echo "📖 Documentation will be available at:"
echo "   https://github.com/geffski/wallet-finder/blob/main/DOCUMENTATION.md"
