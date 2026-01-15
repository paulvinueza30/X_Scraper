#!/usr/bin/env python3
"""
X/Twitter Scraper - Main Entry Point

A production-ready Playwright-based scraper for X.com (Twitter).

Usage:
    python scrape.py --config config.json
    python scrape.py --accounts user1,user2 --limit 25 --out ./data
    python scrape.py --login  # Interactive login to save session
    python scrape.py --help   # Show all options

For more information, see README.md
"""

import sys
import os

# Add the project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from x_scraper.cli import main

if __name__ == "__main__":
    main()
