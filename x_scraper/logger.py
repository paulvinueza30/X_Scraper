"""
Logging configuration for X/Twitter Scraper
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "x_scraper",
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    log_dir: Optional[str] = None
) -> logging.Logger:
    """
    Set up and return a configured logger.

    Args:
        name: Logger name
        log_file: Optional log file name (will be created in log_dir)
        level: Logging level
        log_dir: Directory for log files

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            log_file_path = log_path / log_file
        else:
            log_file_path = Path(log_file)
            log_file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
        logger.info(f"Logging to file: {log_file_path}")

    return logger


def get_logger(name: str = "x_scraper") -> logging.Logger:
    """Get an existing logger or create a basic one."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


class ScrapeStats:
    """Track and report scraping statistics."""

    def __init__(self):
        self.accounts_processed = 0
        self.accounts_failed = 0
        self.total_posts = 0
        self.posts_per_account = {}
        self.errors = []
        self.start_time = None
        self.end_time = None

    def start(self):
        """Mark the start of scraping."""
        self.start_time = datetime.now()

    def end(self):
        """Mark the end of scraping."""
        self.end_time = datetime.now()

    def add_account_success(self, handle: str, post_count: int):
        """Record successful account scrape."""
        self.accounts_processed += 1
        self.total_posts += post_count
        self.posts_per_account[handle] = post_count

    def add_account_failure(self, handle: str, error: str):
        """Record failed account scrape."""
        self.accounts_failed += 1
        self.errors.append({"account": handle, "error": error})

    def get_summary(self) -> dict:
        """Get summary statistics."""
        duration = None
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()

        return {
            "accounts_processed": self.accounts_processed,
            "accounts_failed": self.accounts_failed,
            "total_posts_scraped": self.total_posts,
            "posts_per_account": self.posts_per_account,
            "errors": self.errors,
            "duration_seconds": duration
        }

    def print_summary(self, logger: logging.Logger):
        """Print a formatted summary to the logger."""
        summary = self.get_summary()

        logger.info("=" * 60)
        logger.info("SCRAPE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Accounts processed: {summary['accounts_processed']}")
        logger.info(f"Accounts failed:    {summary['accounts_failed']}")
        logger.info(f"Total posts:        {summary['total_posts_scraped']}")

        if summary['duration_seconds']:
            logger.info(f"Duration:           {summary['duration_seconds']:.1f} seconds")

        if summary['posts_per_account']:
            logger.info("-" * 40)
            logger.info("Posts per account:")
            for handle, count in summary['posts_per_account'].items():
                logger.info(f"  @{handle}: {count} posts")

        if summary['errors']:
            logger.info("-" * 40)
            logger.warning("Errors encountered:")
            for err in summary['errors']:
                logger.warning(f"  @{err['account']}: {err['error']}")

        logger.info("=" * 60)
