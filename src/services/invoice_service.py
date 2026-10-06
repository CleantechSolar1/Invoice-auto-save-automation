"""Service orchestrator for continuous email polling and automation cycle."""

import logging
import signal
import sys
import time
from typing import Dict

from src.auth.graph_auth import GraphAuthProvider
from src.config import Settings
from src.database.db import DatabaseManager
from src.graph.graph_client import GraphClient
from src.graph.outlook_client import OutlookClient
from src.graph.sharepoint_client import SharePointClient
from src.services.email_processor import EmailProcessor
from src.services.sharepoint_service import SharePointService

logger = logging.getLogger("invoice_automation.service")


class InvoiceAutomationService:
    """Manages the full lifecycle of the invoice automation worker."""

    def __init__(self, config: Settings):
        self.config = config
        self._running = False

        # Initialize database
        self.db = DatabaseManager(db_path=config.database_path)

        # Initialize Graph Auth and Clients
        self.auth_provider = GraphAuthProvider(
            tenant_id=config.tenant_id,
            client_id=config.client_id,
            client_secret=config.client_secret,
            scope=config.graph_scope,
        )

        self.graph_client = GraphClient(
            auth_provider=self.auth_provider,
            base_url=config.graph_base_url,
            timeout=config.request_timeout_seconds,
            max_retries=config.max_retries,
        )

        self.outlook_client = OutlookClient(
            graph_client=self.graph_client,
            processing_mailbox=config.processing_mailbox,
            invoice_group_address=config.invoice_group_address,
            timezone_name=config.app_timezone,
        )

        self.sharepoint_client = SharePointClient(
            graph_client=self.graph_client,
            hostname=config.sharepoint_hostname,
            site_path=config.sharepoint_site_path,
            library_name=config.sharepoint_library_name,
            root_folder=config.sharepoint_root_folder,
        )

        self.sharepoint_service = SharePointService(
            sharepoint_client=self.sharepoint_client,
            dry_run=config.dry_run,
        )

        self.email_processor = EmailProcessor(
            outlook_client=self.outlook_client,
            sharepoint_service=self.sharepoint_service,
            db_manager=self.db,
        )

    def print_startup_banner(self) -> None:
        """Print the standardized startup banner to console."""
        mode_str = "DRY RUN" if self.config.dry_run else "PRODUCTION"
        sharepoint_location = f"{self.config.sharepoint_library_name}/{self.config.sharepoint_root_folder}"

        if self.config.filter_start_date:
            filter_str = f"From {self.config.filter_start_date} onwards ({self.config.app_timezone})"
        elif self.config.process_today_only:
            filter_str = f"TODAY ONLY (from midnight, {self.config.app_timezone})"
        else:
            filter_str = f"Past {self.config.email_lookback_days} days"

        banner = f"""
==================================================
Cleantech Invoice Automation
==================================================
Processing Mailbox:
{self.config.processing_mailbox}

Invoice Group Address (To/CC Filter):
{self.config.invoice_group_address}

SharePoint:
{sharepoint_location}

Date Filter:
{filter_str}

Mode:
{mode_str}

Polling interval:
{self.config.poll_interval_seconds} seconds

Status:
Running...
==================================================
"""
        print(banner, flush=True)

    def run_startup_diagnostics(self) -> bool:
        """Run connectivity and configuration diagnostics before starting the loop."""
        print("========================================", flush=True)
        print("Microsoft Graph Connection Test", flush=True)
        print("========================================", flush=True)

        # 1. Test Auth
        try:
            token = self.auth_provider.get_access_token()
            print("\nTenant: OK\nAuthentication: OK\n", flush=True)
        except Exception as exc:
            print(f"\nAuthentication Failed: {exc}\n", flush=True)
            return False

        # 2. Test Processing Mailbox
        print(f"Processing mailbox:\n{self.config.processing_mailbox}\n", flush=True)
        mailbox_ok, messages_ok, error_detail = self.outlook_client.check_mailbox_access()
        if not mailbox_ok:
            error_banner = f"""========================================
CONFIGURATION / ACCESS ERROR
========================================

Processing mailbox:
{self.config.processing_mailbox}

The application could not access this mailbox.
Error details: {error_detail}

Verify:
1. The mailbox address/UPN is correct.
2. Microsoft Graph application permissions are granted.
3. Admin consent has been provided.
4. The application is allowed to access this mailbox.

Do NOT configure the mail-enabled security group as the Graph mailbox endpoint.
========================================
"""
            print(error_banner, flush=True)
            return False

        print("Mailbox lookup: OK")
        print("Messages endpoint: OK\n")

        # 3. Print Invoice Group Address
        print(f"Invoice group address:\n{self.config.invoice_group_address}\n", flush=True)

        # 4. Test SharePoint Connection
        try:
            self.sharepoint_client.get_site()
            print("SharePoint connection: OK\n", flush=True)
        except Exception as exc:
            print(f"SharePoint connection check: WARNING/FAILED ({exc})\n", flush=True)
            if not self.config.dry_run:
                logger.warning("SharePoint connection failed: %s", exc)

        print("========================================")
        print("System Ready")
        print("========================================\n", flush=True)
        return True

    def process_cycle(self) -> Dict[str, int]:
        """Execute a single polling and processing cycle across the processing mailbox."""
        logger.info("Starting mailbox check for %s...", self.config.processing_mailbox)
        stats: Dict[str, int] = {}

        try:
            messages = self.outlook_client.get_messages(
                lookback_days=self.config.email_lookback_days,
                today_only=self.config.process_today_only,
                start_date=self.config.filter_start_date,
            )

            count = 0
            for message in messages:
                count += 1
                try:
                    status = self.email_processor.process_message(message)
                    stats[status] = stats.get(status, 0) + 1
                except Exception as exc:
                    logger.error("Unexpected error processing message: %s", exc, exc_info=True)
                    stats["PROCESSING_ERROR"] = stats.get("PROCESSING_ERROR", 0) + 1

            logger.info("Cycle finished. Evaluated %d messages. Results: %s", count, stats)

        except Exception as exc:
            logger.error("Error during email polling cycle: %s", exc, exc_info=True)

        return stats

    def start_polling(self) -> None:
        """Run continuous polling loop with graceful termination handling."""
        self._running = True

        def _handle_shutdown(signum, frame):
            logger.info("Shutdown signal received (%s). Stopping gracefully...", signum)
            self._running = False

        signal.signal(signal.SIGINT, _handle_shutdown)
        signal.signal(signal.SIGTERM, _handle_shutdown)

        # Run diagnostics test
        self.run_startup_diagnostics()
        self.print_startup_banner()
        logger.info("Invoice Automation Service started successfully.")

        while self._running:
            start_time = time.time()
            self.process_cycle()

            elapsed = time.time() - start_time
            sleep_time = max(0.0, self.config.poll_interval_seconds - elapsed)

            # Sleep in short increments to respond promptly to shutdown signals
            while self._running and sleep_time > 0:
                step = min(sleep_time, 1.0)
                time.sleep(step)
                sleep_time -= step

        logger.info("Invoice Automation Service has stopped.")
