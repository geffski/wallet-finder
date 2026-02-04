#!/usr/bin/env python3
"""
Wallet Discovery Pipeline Orchestrator

Runs the complete wallet discovery and auditing workflow:
1. Discover wallets from trending tokens (top_trader.py)
2. Audit discovered wallets for performance (wallet_stats.py)
3. Generate HTML report (generate_report.py)

Usage:
    python main.py              # Run with default settings
    python main.py --all        # Force re-audit all wallets
    python main.py --skip-audit # Only discover, skip audit
"""

import asyncio
import sys
import argparse
from pathlib import Path


async def run_discovery_pipeline(force_all: bool = False, skip_audit: bool = False):
    """
    Run the complete wallet discovery pipeline.
    
    Args:
        force_all: If True, re-audit all wallets (not just pending)
        skip_audit: If True, skip the audit step
    """
    
    print("=" * 70)
    print("🚀 WALLET DISCOVERY PIPELINE")
    print("=" * 70)
    
    # Step 1: Discover wallets from trending tokens
    print("\n📡 STEP 1: Discovering wallets from trending tokens...")
    print("-" * 70)
    
    try:
        # Import dynamically to avoid circular dependencies
        import top_trader
        await top_trader.main()
    except Exception as e:
        print(f"❌ Discovery failed: {e}")
        return False
    
    # Step 2: Audit discovered wallets (optional)
    if not skip_audit:
        print("\n" + "=" * 70)
        print("📊 STEP 2: Auditing discovered wallets...")
        print("-" * 70)
        
        try:
            import wallet_stats
            await wallet_stats.main(force_all=force_all)
        except Exception as e:
            print(f"❌ Audit failed: {e}")
            return False
    else:
        print("\n⏭️  Skipping audit step (--skip-audit)")
    
    # Step 3: Generate report
    print("\n" + "=" * 70)
    print("📄 STEP 3: Generating HTML report...")
    print("-" * 70)
    
    try:
        from generate_report import generate_html
        generate_html(report_type='SESSION')
    except Exception as e:
        print(f"❌ Report generation failed: {e}")
        return False
    
    print("\n" + "=" * 70)
    print("✅ PIPELINE COMPLETE")
    print("=" * 70)
    return True


def main():
    """Parse arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        description='Run the complete wallet discovery and auditing pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py              # Run with default settings
  python main.py --all        # Force re-audit all wallets
  python main.py --skip-audit # Only discover, skip audit
        """
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Force re-audit all wallets (not just pending ones)'
    )
    
    parser.add_argument(
        '--skip-audit',
        action='store_true',
        help='Skip the wallet audit step (only discover)'
    )
    
    args = parser.parse_args()
    
    # Run the pipeline
    try:
        success = asyncio.run(run_discovery_pipeline(
            force_all=args.all,
            skip_audit=args.skip_audit
        ))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
