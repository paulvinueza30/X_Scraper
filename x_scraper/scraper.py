"""
Core scraper implementation for X/Twitter.

Handles browser automation, scrolling, retry logic, and orchestration.
"""

import asyncio
import random
from datetime import datetime
from typing import List, Dict, Optional, Set
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout
)

from .config import ScraperConfig
from .session import SessionManager
from .extractors import (
    PostData,
    extract_post_data,
    is_post_within_cutoff,
    SELECTORS
)
from .output import OutputHandler
from .logger import get_logger, ScrapeStats

logger = get_logger()


class XScraper:
    """Main scraper class for X/Twitter."""

    def __init__(self, config: ScraperConfig):
        """
        Initialize the scraper.

        Args:
            config: ScraperConfig instance
        """
        self.config = config
        self.session_manager = SessionManager(config.session_file)
        self.output_handler = OutputHandler(config.output_dir)
        self.stats = ScrapeStats()

        # Track seen post IDs to avoid duplicates
        self.seen_post_ids: Set[str] = set()

    async def _create_browser_context(
        self,
        browser: Browser
    ) -> BrowserContext:
        """Create a browser context with appropriate settings."""
        context_options = {
            "viewport": {"width": 1280, "height": 900},
            "user_agent": self.config.user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        # Add session state if available
        session_path = self.session_manager.get_storage_state_for_context()
        if session_path:
            context_options["storage_state"] = session_path
            logger.info("Using saved session state for authentication")

        return await browser.new_context(**context_options)

    async def _random_delay(self, min_delay: float = None, max_delay: float = None):
        """Add a random delay to appear more human-like."""
        min_d = min_delay or self.config.scroll_delay_min
        max_d = max_delay or self.config.scroll_delay_max
        delay = random.uniform(min_d, max_d)
        await asyncio.sleep(delay)

    async def _scroll_page(self, page: Page) -> int:
        """
        Scroll the page down by a random amount.

        Returns:
            Number of pixels scrolled
        """
        scroll_amount = random.randint(
            self.config.scroll_amount_min,
            self.config.scroll_amount_max
        )
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        return scroll_amount

    async def _wait_for_tweets(self, page: Page) -> bool:
        """
        Wait for tweet articles to load on the page.

        Returns:
            True if tweets were found
        """
        for selector in SELECTORS["tweet_article"]:
            try:
                await page.wait_for_selector(
                    selector,
                    timeout=self.config.element_timeout
                )
                return True
            except PlaywrightTimeout:
                continue

        return False

    async def _get_tweet_articles(self, page: Page):
        """Get all tweet article elements on the page."""
        for selector in SELECTORS["tweet_article"]:
            articles = page.locator(selector)
            count = await articles.count()
            if count > 0:
                return articles
        return None

    async def _handle_rate_limit(
        self,
        page: Page,
        attempt: int
    ) -> bool:
        """
        Check for and handle rate limiting.

        Returns:
            True if rate limited and should retry
        """
        # Check for common rate limit indicators
        rate_limit_indicators = [
            "Rate limit exceeded",
            "Something went wrong",
            "Try again",
            "too many requests",
        ]

        page_content = await page.content()

        for indicator in rate_limit_indicators:
            if indicator.lower() in page_content.lower():
                delay = self.config.retry_delay * (2 ** attempt)
                logger.warning(
                    f"Rate limit detected. Waiting {delay:.1f}s before retry..."
                )
                await asyncio.sleep(delay)
                return True

        return False

    async def _scrape_account(
        self,
        page: Page,
        handle: str
    ) -> List[PostData]:
        """
        Scrape posts from a single account.

        Args:
            page: Playwright page object
            handle: Account handle to scrape

        Returns:
            List of PostData objects
        """
        posts: List[PostData] = []
        account_seen_ids: Set[str] = set()
        no_new_posts_count = 0
        max_no_new_posts = 5  # Stop if we see no new posts after 5 scrolls
        cutoff_date = self.config.get_cutoff_date()

        profile_url = f"https://x.com/{handle}"
        logger.info(f"Scraping @{handle}: {profile_url}")

        # Navigate to profile with retry
        for attempt in range(self.config.max_retries):
            try:
                await page.goto(
                    profile_url,
                    wait_until="domcontentloaded",
                    timeout=self.config.page_timeout
                )

                # Check for rate limiting
                if await self._handle_rate_limit(page, attempt):
                    continue

                # Wait for tweets to load
                if await self._wait_for_tweets(page):
                    break

                # Check if account exists
                if "This account doesn't exist" in await page.content():
                    logger.warning(f"Account @{handle} does not exist")
                    return posts

                if "Account suspended" in await page.content():
                    logger.warning(f"Account @{handle} is suspended")
                    return posts

            except PlaywrightTimeout:
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Timeout loading @{handle}. Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Failed to load @{handle} after {attempt + 1} attempts")
                    return posts
            except Exception as e:
                logger.error(f"Error loading @{handle}: {e}")
                return posts

        # Initial delay to let page settle
        await self._random_delay(1.5, 2.5)

        # Scroll and collect posts
        while len(posts) < self.config.posts_per_account:
            articles = await self._get_tweet_articles(page)

            if not articles:
                logger.debug("No tweet articles found on page")
                break

            article_count = await articles.count()
            new_posts_this_scroll = 0

            for i in range(article_count):
                if len(posts) >= self.config.posts_per_account:
                    break

                try:
                    article = articles.nth(i)
                    post = await extract_post_data(article, handle, page)

                    if post and post.post_id:
                        # Skip duplicates
                        if post.post_id in account_seen_ids:
                            continue

                        if post.post_id in self.seen_post_ids:
                            continue

                        # Check date cutoff
                        if not is_post_within_cutoff(post, cutoff_date):
                            logger.info(
                                f"Reached date cutoff for @{handle}. "
                                f"Collected {len(posts)} posts."
                            )
                            return posts

                        account_seen_ids.add(post.post_id)
                        self.seen_post_ids.add(post.post_id)
                        posts.append(post)
                        new_posts_this_scroll += 1

                        logger.debug(
                            f"Post {len(posts)}/{self.config.posts_per_account}: "
                            f"{post.post_id}"
                        )

                except Exception as e:
                    logger.debug(f"Error extracting post {i}: {e}")
                    continue

            # Check if we're getting new posts
            if new_posts_this_scroll == 0:
                no_new_posts_count += 1
                if no_new_posts_count >= max_no_new_posts:
                    logger.info(
                        f"No new posts after {max_no_new_posts} scrolls. "
                        f"Collected {len(posts)} posts."
                    )
                    break
            else:
                no_new_posts_count = 0

            # Scroll down
            await self._scroll_page(page)
            await self._random_delay()

            # Check for rate limiting periodically
            if random.random() < 0.1:  # 10% chance per scroll
                if await self._handle_rate_limit(page, 0):
                    await page.reload()
                    await self._wait_for_tweets(page)

        logger.info(f"Collected {len(posts)} posts from @{handle}")
        return posts

    async def scrape(self) -> Dict[str, List[PostData]]:
        """
        Main scraping method. Scrapes all configured accounts.

        Returns:
            Dictionary mapping handles to lists of posts
        """
        self.stats.start()
        results: Dict[str, List[PostData]] = {}

        if not self.config.accounts:
            logger.error("No accounts configured to scrape")
            return results

        logger.info(f"Starting scrape of {len(self.config.accounts)} accounts")
        logger.info(f"Posts per account: {self.config.posts_per_account}")
        logger.info(f"Headless mode: {self.config.headless}")

        if self.config.date_cutoff_days:
            logger.info(f"Date cutoff: {self.config.date_cutoff_days} days")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config.headless,
                slow_mo=self.config.slow_mo
            )

            context = await self._create_browser_context(browser)
            page = await context.new_page()

            # Set default timeout
            page.set_default_timeout(self.config.page_timeout)

            for handle in self.config.accounts:
                try:
                    posts = await self._scrape_account(page, handle)
                    results[handle] = posts

                    if posts:
                        self.stats.add_account_success(handle, len(posts))
                    else:
                        self.stats.add_account_failure(handle, "No posts collected")

                    # Delay between accounts
                    if handle != self.config.accounts[-1]:
                        delay = random.uniform(2.0, 4.0)
                        logger.info(f"Waiting {delay:.1f}s before next account...")
                        await asyncio.sleep(delay)

                except Exception as e:
                    logger.error(f"Failed to scrape @{handle}: {e}")
                    self.stats.add_account_failure(handle, str(e))
                    results[handle] = []

            # Save session state if logged in
            if self.session_manager.has_session():
                try:
                    await self.session_manager.save_session(context)
                except Exception as e:
                    logger.debug(f"Could not update session: {e}")

            await browser.close()

        self.stats.end()
        return results

    async def run(self) -> Dict[str, any]:
        """
        Run the full scraping pipeline including output.

        Returns:
            Dictionary with results and file paths
        """
        # Scrape all accounts
        results = await self.scrape()

        # Save outputs
        saved_files = self.output_handler.save_all_results(results)

        # Print summary
        self.stats.print_summary(logger)

        return {
            "posts": results,
            "files": saved_files,
            "stats": self.stats.get_summary()
        }


async def run_scraper(config: ScraperConfig) -> Dict[str, any]:
    """
    Convenience function to run the scraper with a config.

    Args:
        config: ScraperConfig instance

    Returns:
        Dictionary with results
    """
    scraper = XScraper(config)
    return await scraper.run()
