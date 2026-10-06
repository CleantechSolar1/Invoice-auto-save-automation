"""Unit tests for configuration validation."""

import pytest
from src.config import Settings


def test_missing_processing_mailbox_raises():
    """Verify missing PROCESSING_MAILBOX raises a clear ValueError."""
    with pytest.raises(ValueError, match="PROCESSING_MAILBOX is missing"):
        cfg = Settings(
            processing_mailbox="",
            invoice_group_address="india.invoicing@cleantechsolar.com",
            dry_run=True,
        )
        cfg.validate_for_run()


def test_missing_invoice_group_address_raises():
    """Verify missing INVOICE_GROUP_ADDRESS raises a clear ValueError."""
    with pytest.raises(ValueError, match="INVOICE_GROUP_ADDRESS is missing"):
        cfg = Settings(
            processing_mailbox="surojit@cleantechsolar.com",
            invoice_group_address="",
            dry_run=True,
        )
        cfg.validate_for_run()


def test_valid_configuration():
    """Verify valid configuration passes validation."""
    cfg = Settings(
        processing_mailbox="surojit@cleantechsolar.com",
        invoice_group_address="india.invoicing@cleantechsolar.com",
        dry_run=True,
    )
    cfg.validate_for_run()
    assert cfg.processing_mailbox == "surojit@cleantechsolar.com"
    assert cfg.invoice_group_address == "india.invoicing@cleantechsolar.com"
