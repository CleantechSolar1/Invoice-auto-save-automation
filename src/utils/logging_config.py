"""Logging configuration with secret redaction and dual console/file output."""

import logging
import os
import re
from pathlib import Path

# Regular expressions to detect and redact sensitive tokens or credentials
BEARER_REGEX = re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
SECRET_REGEX = re.compile(r"(client_secret|clientsecret|password|access_token)=['\"][^'\"]+['\"]", re.IGNORECASE)


class RedactingFilter(logging.Filter):
    """Filter that strips or masks sensitive tokens and secrets from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = BEARER_REGEX.sub(r"\1[REDACTED]", record.msg)
            record.msg = SECRET_REGEX.sub(r"\1=[REDACTED]", record.msg)
        if record.args:
            redacted_args = []
            for arg in record.args if isinstance(record.args, tuple) else [record.args]:
                if isinstance(arg, str):
                    arg = BEARER_REGEX.sub(r"\1[REDACTED]", arg)
                    arg = SECRET_REGEX.sub(r"\1=[REDACTED]", arg)
                redacted_args.append(arg)
            record.args = tuple(redacted_args) if isinstance(record.args, tuple) else redacted_args[0]
        return True


def setup_logging(log_level: str = "INFO", log_file: str = "logs/invoice_automation.log") -> logging.Logger:
    """Configure application-wide logging to console and rotating/file."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logger = logging.getLogger("invoice_automation")
    logger.setLevel(numeric_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    redacting_filter = RedactingFilter()

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redacting_filter)
    logger.addHandler(console_handler)

    # File Handler
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redacting_filter)
    logger.addHandler(file_handler)

    return logger
