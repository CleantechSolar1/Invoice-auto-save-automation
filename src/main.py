"""Main application entry point."""

import argparse
import sys
from pathlib import Path

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.services.invoice_service import InvoiceAutomationService
from src.utils.logging_config import setup_logging


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Automated Sales Invoice Email to SharePoint Filing Service"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single email check cycle and exit immediately (useful for cron jobs or testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without modifying SharePoint folders or uploading files",
    )
    parser.add_argument(
        "--today-only",
        action="store_true",
        help="Process only emails received today (default behavior)",
    )
    parser.add_argument(
        "--all-dates",
        action="store_true",
        help="Process emails from past days (full lookback window)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Filter emails received on or after this date (YYYY-MM-DD or ISO timestamp)",
    )
    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    # CLI flags override environment configuration if set
    if args.dry_run:
        settings.dry_run = True
    if args.start_date:
        settings.filter_start_date = args.start_date
    if args.today_only:
        settings.process_today_only = True
    elif args.all_dates:
        settings.process_today_only = False

    # Setup application logging
    logger = setup_logging(
        log_level=settings.log_level,
        log_file=settings.log_file_path,
    )

    logger.info("Initializing Cleantech Invoice Automation...")

    # Validate required mailbox and group configurations
    try:
        settings.validate_for_run()
    except ValueError as exc:
        logger.error("Configuration validation error: %s", exc)
        sys.exit(1)

    service = InvoiceAutomationService(config=settings)

    if args.once:
        service.run_startup_diagnostics()
        service.print_startup_banner()
        logger.info("Executing single processing cycle (--once flag)...")
        service.process_cycle()
        logger.info("Cycle completed. Exiting.")
    else:
        service.start_polling()


if __name__ == "__main__":
    main()
