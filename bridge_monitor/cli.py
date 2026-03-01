import argparse
import json
import logging
import sys
from .database import Database
from .checker import TransactionChecker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Check for new config format
        if 'common' not in config or 'tokens' not in config:
            logger.error("=" * 70)
            logger.error("ERROR: Config file uses old format!")
            logger.error("=" * 70)
            logger.error("")
            logger.error("Your config.json needs to be updated to support multiple tokens.")
            logger.error("Please see config.example.json for the new format.")
            logger.error("")
            logger.error("Key changes:")
            logger.error("  - Common settings moved to 'common' section")
            logger.error("  - Token-specific settings in 'tokens' section")
            logger.error("  - Support for multiple tokens (BEAM, USDT, USDC, etc.)")
            logger.error("")
            sys.exit(1)
        
        return config
        
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        logger.error("Create a config.json file based on config.example.json")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        sys.exit(1)


def format_report(report: dict):
    """Format report for console output"""
    print("\n" + "="*60)
    print(" BRIDGE TRANSACTION CHECKER REPORT")
    print("="*60)
    
    print("\nBlockchain Status:")
    print(f"  Ethereum Block: {report['eth_block']}")
    print(f"  Beam Height:    {report['beam_height']}")
    
    # Display stats for each token
    for token_name, token_stats in report['tokens'].items():
        print(f"\n\n{'='*60}")
        print(f" Token: {token_name}")
        print(f"{'='*60}")
        
        print("\nETH → Beam Transactions:")
        eth2beam = token_stats.get('eth2beam', {})
        print(f"  Total:     {eth2beam.get('total', 0)}")
        print(f"  Completed: {eth2beam.get('completed', 0)}")
        print(f"  Pending:   {eth2beam.get('pending', 0)}")
        print(f"  Failed:    {eth2beam.get('failed', 0)}")
        
        print("\nBeam → ETH Transactions:")
        beam2eth = token_stats.get('beam2eth', {})
        print(f"  Total:     {beam2eth.get('total', 0)}")
        print(f"  Completed: {beam2eth.get('completed', 0)}")
        print(f"  Pending:   {beam2eth.get('pending', 0)}")
        print(f"  Failed:    {beam2eth.get('failed', 0)}")
    
    if report['stuck_transactions']:
        print("\n\n⚠️  FAILED TRANSACTIONS:")
        for tx in report['stuck_transactions']:
            print(f"\n  [{tx['token']}] [{tx['direction']}] Message ID: {tx['message_id']}")
            print(f"    Status: {tx['status']}")
            if tx['eth_tx_hash']:
                print(f"    ETH TX: {tx['eth_tx_hash']}")
    else:
        print("\n\n✅ No failed transactions")
    
    print("\n" + "="*60 + "\n")


def cmd_check(args):
    """Run transaction checker"""
    config = load_config(args.config)
    db = Database(args.database)
    
    try:
        checker = TransactionChecker(config, db, token=args.token)
        
        logger.info("Starting transaction check...")
        checker.check_all()
        
        # Generate and display report
        report = checker.get_report()
        
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            format_report(report)
        
    finally:
        db.close()


def cmd_report(args):
    """Display current status report"""
    config = load_config(args.config)
    db = Database(args.database)
    
    try:
        checker = TransactionChecker(config, db, token=args.token)
        report = checker.get_report()
        
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            format_report(report)
    
    finally:
        db.close()


def cmd_list(args):
    """List transactions"""
    db = Database(args.database)
    
    try:
        txs = db.get_all_transactions(token=args.token, direction=args.direction)
        
        if args.json:
            # Convert Row objects to dicts
            txs_list = [dict(tx) for tx in txs]
            print(json.dumps(txs_list, indent=2))
        else:
            print(f"\nTransactions ({len(txs)} total):\n")
            print(f"{'Token':<8} {'Dir':<10} {'MsgID':<8} {'Status':<15} {'ETH Block':<12} {'Beam Height':<12}")
            print("-" * 80)
            
            for tx in txs:
                print(f"{tx['token']:<8} {tx['direction']:<10} {tx['message_id']:<8} {tx['status']:<15} "
                      f"{tx.get('eth_block_number') or 'N/A':<12} {tx.get('beam_height') or 'N/A':<12}")
    
    finally:
        db.close()


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Bridge Transaction Checker - Monitor Beam-Ethereum bridge transactions'
    )
    
    parser.add_argument(
        '-c', '--config',
        default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    
    parser.add_argument(
        '-d', '--database',
        default='bridge_monitor.db',
        help='Path to database file (default: bridge_monitor.db)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Check command
    check_parser = subparsers.add_parser('check', help='Check all transactions')
    check_parser.add_argument('--token', help='Filter by specific token (e.g., BEAM, USDT, USDC)')
    check_parser.add_argument('--json', action='store_true', help='Output as JSON')
    check_parser.set_defaults(func=cmd_check)
    
    # Report command
    report_parser = subparsers.add_parser('report', help='Display current status report')
    report_parser.add_argument('--token', help='Filter by specific token (e.g., BEAM, USDT, USDC)')
    report_parser.add_argument('--json', action='store_true', help='Output as JSON')
    report_parser.set_defaults(func=cmd_report)
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all transactions')
    list_parser.add_argument('--token', help='Filter by specific token (e.g., BEAM, USDT, USDC)')
    list_parser.add_argument('--direction', choices=['eth2beam', 'beam2eth'], help='Filter by direction')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.set_defaults(func=cmd_list)
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
