"""
Command-line interface for X/Twitter Scraper.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import ScraperConfig, create_sample_config
from .scraper import run_scraper
from .session import interactive_login, verify_session
from .logger import setup_logger


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="scrape",
        description="X/Twitter Scraper - Scrape posts from X.com profiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  scrape --config config.json
  scrape --config config.json --headless --limit 50
  scrape --accounts elonmusk,OpenAI --limit 25 --out ./data
  scrape --login                     # Interactive login to save session
  scrape --verify-session            # Check if saved session is valid

For more information, see the README.md file.
        """
    )

    # Main operation modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--login",
        action="store_true",
        help="Launch browser for interactive login and save session"
    )
    mode_group.add_argument(
        "--verify-session",
        action="store_true",
        help="Verify that saved session is still valid"
    )
    mode_group.add_argument(
        "--init-config",
        action="store_true",
        help="Create a sample config.json file"
    )

    # Configuration
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to configuration JSON file"
    )

    # Account specification (alternative to config file)
    parser.add_argument(
        "--accounts", "-a",
        type=str,
        default=None,
        help="Comma-separated list of accounts to scrape (e.g., 'user1,user2,user3')"
    )

    # Output settings
    parser.add_argument(
        "--out", "-o",
        type=str,
        default=None,
        help="Output directory for scraped data (default: ./data)"
    )

    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Maximum posts to scrape per account (overrides config)"
    )

    # Browser settings
    parser.add_argument(
        "--headless",
        action="store_true",
        default=None,
        help="Run browser in headless mode"
    )

    parser.add_argument(
        "--headful",
        action="store_true",
        default=None,
        help="Run browser in headful mode (visible window)"
    )

    # Date cutoff
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only scrape posts from the last N days"
    )

    # Session
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Path to session storage state file"
    )

    # Logging
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file (in addition to console output)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (debug) logging"
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-essential output"
    )

    return parser.parse_args()


def build_config(args: argparse.Namespace) -> ScraperConfig:
    """
    Build ScraperConfig from command-line arguments.

    Args:
        args: Parsed command-line arguments

    Returns:
        ScraperConfig instance
    """
    # Start with config file if provided
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: Config file not found: {args.config}", file=sys.stderr)
            sys.exit(1)
        config = ScraperConfig.from_file(args.config)
    else:
        config = ScraperConfig()

    # Override with command-line arguments
    if args.accounts:
        config.accounts = [a.strip() for a in args.accounts.split(",")]

    if args.out:
        config.output_dir = args.out

    if args.limit is not None:
        config.posts_per_account = args.limit

    if args.headless:
        config.headless = True
    elif args.headful:
        config.headless = False

    if args.days is not None:
        config.date_cutoff_days = args.days

    if args.session:
        config.session_file = args.session

    if args.log_file:
        config.log_file = args.log_file

    if args.verbose:
        config.log_level = "DEBUG"
    elif args.quiet:
        config.log_level = "WARNING"

    return config


def main():
    """Main entry point for CLI."""
    args = parse_args()

    # Determine log level
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.WARNING
    else:
        log_level = logging.INFO

    # Set up logging
    logger = setup_logger(
        name="x_scraper",
        log_file=args.log_file,
        level=log_level
    )

    # Handle special modes
    if args.init_config:
        config_path = create_sample_config("config.json")
        logger.info(f"Created sample config file: {config_path}")
        logger.info("Edit config.json to add your accounts and settings")
        return

    if args.login:
        logger.info("Starting interactive login mode...")
        success = asyncio.run(interactive_login(args.session))
        if success:
            logger.info("Login successful! You can now run the scraper.")
            sys.exit(0)
        else:
            logger.error("Login failed or was not completed.")
            sys.exit(1)

    if args.verify_session:
        logger.info("Verifying saved session...")
        valid = asyncio.run(verify_session(args.session))
        if valid:
            logger.info("Session is valid.")
            sys.exit(0)
        else:
            logger.warning("Session is invalid or expired.")
            sys.exit(1)

    # Build configuration
    config = build_config(args)

    # Validate we have accounts to scrape
    if not config.accounts:
        logger.error(
            "No accounts specified. Use --config with a config file, "
            "or --accounts to specify accounts directly."
        )
        logger.info("Run 'scrape --init-config' to create a sample config file.")
        sys.exit(1)

    # Update logger with config settings
    if config.log_file and not args.log_file:
        setup_logger(
            name="x_scraper",
            log_file=config.log_file,
            level=getattr(logging, config.log_level.upper(), logging.INFO)
        )

    # Run the scraper
    try:
        result = asyncio.run(run_scraper(config))

        # Report results
        stats = result.get("stats", {})
        if stats.get("accounts_failed", 0) > 0:
            sys.exit(2)  # Partial failure

    except KeyboardInterrupt:
        logger.info("\nScraping interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
