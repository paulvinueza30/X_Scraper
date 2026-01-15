"""
Configuration handling for X/Twitter Scraper
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta


@dataclass
class ScraperConfig:
    """Configuration for the X/Twitter scraper."""

    # Account list - can be usernames or full URLs
    accounts: List[str] = field(default_factory=list)

    # Number of posts to scrape per account
    posts_per_account: int = 20

    # Output directory
    output_dir: str = "./data"

    # Optional date cutoff (days) - stop scraping when posts are older than this
    date_cutoff_days: Optional[int] = None

    # Browser settings
    headless: bool = False
    slow_mo: int = 50  # Milliseconds between actions

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 2.0  # Base delay in seconds (exponential backoff)

    # Scroll settings
    scroll_delay_min: float = 1.5  # Minimum delay between scrolls
    scroll_delay_max: float = 3.0  # Maximum delay between scrolls
    scroll_amount_min: int = 400   # Minimum pixels to scroll
    scroll_amount_max: int = 800   # Maximum pixels to scroll

    # Timeout settings (milliseconds)
    page_timeout: int = 30000
    element_timeout: int = 10000

    # Session/auth settings
    session_file: Optional[str] = None  # Path to Playwright storage state file

    # Logging settings
    log_file: Optional[str] = None  # Optional log file path
    log_level: str = "INFO"

    # User agent (None = use browser default)
    user_agent: Optional[str] = None

    def __post_init__(self):
        """Validate and normalize configuration."""
        # Normalize accounts - extract handles from URLs
        self.accounts = [self._normalize_account(acc) for acc in self.accounts]

        # Ensure output directory exists
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def _normalize_account(self, account: str) -> str:
        """
        Normalize account input to just the handle.

        Accepts:
        - username
        - @username
        - https://x.com/username
        - https://twitter.com/username
        """
        account = account.strip()

        # Remove URL prefix
        for prefix in ["https://x.com/", "https://twitter.com/",
                       "http://x.com/", "http://twitter.com/",
                       "x.com/", "twitter.com/"]:
            if account.lower().startswith(prefix.lower()):
                account = account[len(prefix):]
                break

        # Remove @ prefix
        if account.startswith("@"):
            account = account[1:]

        # Remove any trailing path (e.g., /status/123)
        if "/" in account:
            account = account.split("/")[0]

        return account

    def get_cutoff_date(self) -> Optional[datetime]:
        """Get the cutoff datetime based on date_cutoff_days."""
        if self.date_cutoff_days is None:
            return None
        return datetime.now() - timedelta(days=self.date_cutoff_days)

    @classmethod
    def from_file(cls, config_path: str) -> "ScraperConfig":
        """Load configuration from a JSON file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(**data)

    @classmethod
    def from_dict(cls, data: dict) -> "ScraperConfig":
        """Create configuration from a dictionary."""
        return cls(**data)

    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {
            "accounts": self.accounts,
            "posts_per_account": self.posts_per_account,
            "output_dir": self.output_dir,
            "date_cutoff_days": self.date_cutoff_days,
            "headless": self.headless,
            "slow_mo": self.slow_mo,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "scroll_delay_min": self.scroll_delay_min,
            "scroll_delay_max": self.scroll_delay_max,
            "scroll_amount_min": self.scroll_amount_min,
            "scroll_amount_max": self.scroll_amount_max,
            "page_timeout": self.page_timeout,
            "element_timeout": self.element_timeout,
            "session_file": self.session_file,
            "log_file": self.log_file,
            "log_level": self.log_level,
            "user_agent": self.user_agent
        }

    def save(self, path: str):
        """Save configuration to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


def create_sample_config(path: str = "config.json"):
    """Create a sample configuration file."""
    sample = ScraperConfig(
        accounts=["elonmusk", "OpenAI", "@anthropikiw"],
        posts_per_account=25,
        output_dir="./data",
        date_cutoff_days=30,
        headless=False,
        log_file="./logs/scraper.log"
    )
    sample.save(path)
    return path
