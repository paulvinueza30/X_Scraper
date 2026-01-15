"""
Session and authentication management for X/Twitter Scraper.

This module handles Playwright storage state for maintaining login sessions.
Never stores credentials directly - only browser state.
"""

import json
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext

from .logger import get_logger

logger = get_logger()


class SessionManager:
    """Manage browser session state for authenticated scraping."""

    DEFAULT_SESSION_PATH = "./.x_session/storage_state.json"

    def __init__(self, session_file: Optional[str] = None):
        """
        Initialize session manager.

        Args:
            session_file: Path to storage state file. If None, uses default.
        """
        self.session_file = Path(session_file or self.DEFAULT_SESSION_PATH)

    def has_session(self) -> bool:
        """Check if a saved session exists."""
        return self.session_file.exists()

    def get_session_path(self) -> str:
        """Get the absolute path to the session file."""
        return str(self.session_file.absolute())

    def delete_session(self):
        """Delete the saved session file."""
        if self.session_file.exists():
            self.session_file.unlink()
            logger.info(f"Deleted session file: {self.session_file}")

    async def save_session(self, context: BrowserContext):
        """
        Save the current browser context's storage state.

        Args:
            context: Playwright browser context to save
        """
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(self.session_file))
        logger.info(f"Session saved to: {self.session_file}")

    def get_storage_state_for_context(self) -> Optional[str]:
        """
        Get the storage state path if it exists, for use in browser context creation.

        Returns:
            Path to storage state file if it exists, None otherwise
        """
        if self.has_session():
            return str(self.session_file)
        return None


async def interactive_login(
    session_file: Optional[str] = None,
    headless: bool = False
) -> bool:
    """
    Launch browser for interactive login, then save session.

    This function:
    1. Opens a headful browser to x.com
    2. Waits for user to log in manually
    3. Saves the storage state for future use

    Args:
        session_file: Path to save the session file
        headless: Should always be False for interactive login

    Returns:
        True if session was saved successfully
    """
    if headless:
        logger.warning("Interactive login requires headful mode. Ignoring headless=True")

    manager = SessionManager(session_file)

    logger.info("=" * 60)
    logger.info("INTERACTIVE LOGIN MODE")
    logger.info("=" * 60)
    logger.info("A browser window will open to x.com")
    logger.info("Please log in manually, then press Enter in this terminal")
    logger.info("Your session will be saved for future scraping runs")
    logger.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=100
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        page = await context.new_page()

        # Navigate to X login page
        await page.goto("https://x.com/login", wait_until="domcontentloaded")

        # Wait for user to complete login
        input("\n>>> Press ENTER after you have logged in successfully... ")

        # Verify login by checking for home timeline or profile elements
        try:
            # Try to navigate to home to verify login
            await page.goto("https://x.com/home", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Check if we're actually logged in
            # Look for elements that only appear when logged in
            is_logged_in = await page.locator('[data-testid="primaryColumn"]').count() > 0

            if is_logged_in:
                await manager.save_session(context)
                logger.info("Login successful! Session saved.")
                await browser.close()
                return True
            else:
                logger.error("Could not verify login. Please try again.")
                await browser.close()
                return False

        except Exception as e:
            logger.error(f"Error during login verification: {e}")
            # Still try to save the session
            try:
                await manager.save_session(context)
                logger.info("Session saved (login status uncertain)")
                await browser.close()
                return True
            except Exception as save_error:
                logger.error(f"Failed to save session: {save_error}")
                await browser.close()
                return False


async def verify_session(session_file: Optional[str] = None) -> bool:
    """
    Verify that a saved session is still valid.

    Args:
        session_file: Path to the session file

    Returns:
        True if session is valid and logged in
    """
    manager = SessionManager(session_file)

    if not manager.has_session():
        logger.info("No saved session found")
        return False

    logger.info("Verifying saved session...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            context = await browser.new_context(
                storage_state=manager.get_storage_state_for_context()
            )

            page = await context.new_page()
            await page.goto("https://x.com/home", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Check for logged-in indicators
            is_logged_in = await page.locator('[data-testid="primaryColumn"]').count() > 0

            if is_logged_in:
                logger.info("Session is valid and logged in")
                await browser.close()
                return True
            else:
                logger.warning("Session appears to be expired or invalid")
                await browser.close()
                return False

        except Exception as e:
            logger.error(f"Error verifying session: {e}")
            await browser.close()
            return False
