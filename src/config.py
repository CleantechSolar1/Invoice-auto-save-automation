"""Configuration management using Pydantic Settings."""

import os
import sys
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Azure Entra ID / Microsoft 365 Authentication
    tenant_id: str = Field(default="", description="Azure Tenant ID")
    client_id: str = Field(default="", description="Azure App Client ID")
    client_secret: str = Field(default="", description="Azure App Client Secret")

    # Mailbox Settings (No hardcoded email addresses)
    processing_mailbox: str = Field(
        default="",
        description="Target Microsoft 365 user mailbox that Microsoft Graph reads",
    )
    invoice_group_address: str = Field(
        default="",
        description="Business mail-enabled security group address for To/CC recipient filtering",
    )

    # SharePoint Settings
    sharepoint_hostname: str = Field(
        default="cleantechenergycorp.sharepoint.com",
        description="SharePoint domain/hostname",
    )
    sharepoint_site_path: str = Field(
        default="/OM",
        description="SharePoint site relative path",
    )
    sharepoint_library_name: str = Field(
        default="Customer Invoicing",
        description="Target Document Library name",
    )
    sharepoint_root_folder: str = Field(
        default="Invoices",
        description="Root folder under Document Library for invoices",
    )

    # Application Behavior
    poll_interval_seconds: int = Field(
        default=60,
        ge=5,
        description="Polling frequency in seconds",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    dry_run: bool = Field(
        default=False,
        description="If True, performs all validations without modifying SharePoint",
    )
    database_path: str = Field(
        default="invoice_automation.db",
        description="SQLite database path for tracking processed emails",
    )
    log_file_path: str = Field(
        default="logs/invoice_automation.log",
        description="Log file path",
    )

    # Microsoft Graph API settings
    graph_base_url: str = Field(
        default="https://graph.microsoft.com/v1.0",
        description="Microsoft Graph API base endpoint",
    )
    graph_scope: str = Field(
        default="https://graph.microsoft.com/.default",
        description="Default Graph API application scope",
    )
    request_timeout_seconds: int = Field(
        default=30,
        ge=5,
        description="HTTP request timeout in seconds",
    )
    max_retries: int = Field(
        default=4,
        ge=1,
        description="Maximum retry attempts on transient Graph API errors",
    )
    email_lookback_days: int = Field(
        default=30,
        ge=1,
        description="Number of past days to query for new emails",
    )
    process_today_only: bool = Field(
        default=True,
        description="If True, only processes emails received today",
    )
    filter_start_date: Optional[str] = Field(
        default=None,
        description="Optional custom ISO start date/datetime to filter emails from (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)",
    )
    app_timezone: str = Field(
        default="Asia/Kolkata",
        description="Application timezone for business day and date filters (e.g., Asia/Kolkata)",
    )

    @field_validator("sharepoint_site_path")
    @classmethod
    def clean_site_path(cls, v: str) -> str:
        """Ensure site path starts with a slash and does not end with one."""
        v = v.strip()
        if not v.startswith("/"):
            v = "/" + v
        return v.rstrip("/")

    @field_validator("processing_mailbox", "invoice_group_address")
    @classmethod
    def clean_email(cls, v: str) -> str:
        """Normalize email address to lower-case stripped."""
        return v.strip().lower() if v else ""

    @property
    def is_auth_configured(self) -> bool:
        """Check if essential Azure credentials are provided."""
        return bool(self.tenant_id and self.client_id and self.client_secret)

    def validate_for_run(self) -> None:
        """Validate critical configuration before running."""
        # 1. Validate PROCESSING_MAILBOX
        if not self.processing_mailbox:
            msg = """
========================================
CONFIGURATION ERROR

PROCESSING_MAILBOX is missing.

Example:
PROCESSING_MAILBOX=surojit@cleantechsolar.com
========================================
"""
            print(msg, file=sys.stderr)
            raise ValueError("PROCESSING_MAILBOX is missing in configuration")

        # 2. Validate INVOICE_GROUP_ADDRESS
        if not self.invoice_group_address:
            msg = """
========================================
CONFIGURATION ERROR

INVOICE_GROUP_ADDRESS is missing.

Example:
INVOICE_GROUP_ADDRESS=india.invoicing@cleantechsolar.com
========================================
"""
            print(msg, file=sys.stderr)
            raise ValueError("INVOICE_GROUP_ADDRESS is missing in configuration")

        # 3. Validate Azure AD Credentials (when not dry-run without credentials)
        if not self.is_auth_configured and not self.dry_run:
            raise ValueError(
                "Missing required Azure AD credentials: TENANT_ID, CLIENT_ID, and CLIENT_SECRET "
                "must be configured in your .env file or environment variables."
            )


# Global settings instance
settings = Settings()
