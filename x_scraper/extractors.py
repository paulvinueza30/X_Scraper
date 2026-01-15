"""
Data extraction utilities for X/Twitter Scraper.

This module contains robust extractors with multiple selector fallbacks
to handle X's frequently changing DOM structure.
"""

import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from playwright.async_api import Locator, Page

from .logger import get_logger

logger = get_logger()


@dataclass
class PostData:
    """Structured data for a single post/tweet."""
    account_handle: str = ""
    account_display_name: str = ""
    post_url: str = ""
    post_id: str = ""
    timestamp: str = ""  # ISO format
    text_content: str = ""
    reply_count: int = 0
    repost_count: int = 0
    like_count: int = 0
    view_count: int = 0
    is_repost: bool = False
    is_quote: bool = False
    media_urls: List[str] = field(default_factory=list)
    scraped_at: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


# Selector strategies - multiple fallbacks for each element type
# X frequently changes data-testid values and DOM structure

SELECTORS = {
    # Tweet/post article containers
    "tweet_article": [
        'article[data-testid="tweet"]',
        'article[role="article"]',
        'div[data-testid="cellInnerDiv"] article',
        '[data-testid="tweetText"]/.ancestor::article',
    ],

    # Tweet text content
    "tweet_text": [
        '[data-testid="tweetText"]',
        'div[lang]',  # Tweet text usually has lang attribute
        'article div[dir="auto"]',
    ],

    # User info within tweet
    "user_link": [
        'a[role="link"][href*="/"]',
        'div[data-testid="User-Name"] a',
        'a[href^="/"][tabindex="-1"]',
    ],

    # Display name
    "display_name": [
        'div[data-testid="User-Name"] span',
        'a[role="link"] span span',
    ],

    # Handle/username
    "handle": [
        'div[data-testid="User-Name"] a[href^="/"]',
        'a[tabindex="-1"][href^="/"]',
    ],

    # Timestamp/time element
    "timestamp": [
        'time[datetime]',
        'a[href*="/status/"] time',
    ],

    # Post permalink
    "permalink": [
        'a[href*="/status/"]',
        'time[datetime]/.ancestor::a',
    ],

    # Engagement metrics
    "reply_count": [
        '[data-testid="reply"] span',
        'button[data-testid="reply"] span span',
        '[aria-label*="Repl"] span',
    ],

    "repost_count": [
        '[data-testid="retweet"] span',
        'button[data-testid="retweet"] span span',
        '[aria-label*="Repost"] span',
        '[aria-label*="retweet"] span',
    ],

    "like_count": [
        '[data-testid="like"] span',
        'button[data-testid="like"] span span',
        '[aria-label*="Like"] span',
    ],

    "view_count": [
        'a[href*="/analytics"] span',
        '[aria-label*="View"] span',
        '[aria-label*="view"] span',
    ],

    # Media
    "media_images": [
        'img[src*="pbs.twimg.com/media"]',
        'div[data-testid="tweetPhoto"] img',
        'img[alt="Image"]',
    ],

    "media_videos": [
        'video source',
        'video[src]',
        '[data-testid="videoComponent"] video',
    ],

    # Repost/quote indicators
    "repost_indicator": [
        '[data-testid="socialContext"]',
        'span:has-text("reposted")',
        'span:has-text("Reposted")',
    ],

    "quote_indicator": [
        '[data-testid="quoteTweet"]',
        'div[role="link"][tabindex="0"]',  # Quoted tweet container
    ],
}


def parse_count(text: str) -> int:
    """
    Parse engagement count strings like '1.5K', '2M', '500' to integers.

    Args:
        text: Count string (e.g., "1.5K", "2M", "500")

    Returns:
        Integer count value
    """
    if not text:
        return 0

    text = text.strip().upper()

    # Remove commas
    text = text.replace(",", "")

    # Handle suffixes
    multipliers = {
        "K": 1000,
        "M": 1000000,
        "B": 1000000000,
    }

    for suffix, multiplier in multipliers.items():
        if suffix in text:
            try:
                num = float(text.replace(suffix, ""))
                return int(num * multiplier)
            except ValueError:
                return 0

    # Plain number
    try:
        return int(float(text))
    except ValueError:
        return 0


async def try_selectors(element: Locator, selectors: List[str]) -> Optional[Locator]:
    """
    Try multiple selectors and return the first matching locator.

    Args:
        element: Parent element to search within
        selectors: List of CSS selectors to try

    Returns:
        First matching locator or None
    """
    for selector in selectors:
        try:
            loc = element.locator(selector).first
            if await loc.count() > 0:
                return loc
        except Exception:
            continue
    return None


async def get_text_safe(locator: Optional[Locator], default: str = "") -> str:
    """Safely get text content from a locator."""
    if locator is None:
        return default
    try:
        text = await locator.text_content(timeout=2000)
        return text.strip() if text else default
    except Exception:
        return default


async def get_attribute_safe(
    locator: Optional[Locator],
    attr: str,
    default: str = ""
) -> str:
    """Safely get attribute value from a locator."""
    if locator is None:
        return default
    try:
        value = await locator.get_attribute(attr, timeout=2000)
        return value if value else default
    except Exception:
        return default


async def extract_post_data(
    article: Locator,
    target_handle: str,
    page: Page
) -> Optional[PostData]:
    """
    Extract all data from a single post/tweet article element.

    Args:
        article: The article locator for the tweet
        target_handle: The handle of the account being scraped
        page: The page object for additional queries

    Returns:
        PostData object or None if extraction fails
    """
    try:
        post = PostData(scraped_at=datetime.now().isoformat())

        # Extract timestamp and post URL
        time_elem = await try_selectors(article, SELECTORS["timestamp"])
        if time_elem:
            timestamp = await get_attribute_safe(time_elem, "datetime")
            if timestamp:
                post.timestamp = timestamp

        # Extract permalink and post ID
        permalink_elem = await try_selectors(article, SELECTORS["permalink"])
        if permalink_elem:
            href = await get_attribute_safe(permalink_elem, "href")
            if href:
                if href.startswith("/"):
                    post.post_url = f"https://x.com{href}"
                else:
                    post.post_url = href

                # Extract post ID from URL
                match = re.search(r"/status/(\d+)", href)
                if match:
                    post.post_id = match.group(1)

        # Extract handle from the post URL or user link
        if post.post_url:
            match = re.search(r"x\.com/([^/]+)/status", post.post_url)
            if match:
                post.account_handle = match.group(1)

        if not post.account_handle:
            post.account_handle = target_handle

        # Extract display name
        display_name_elem = await try_selectors(article, SELECTORS["display_name"])
        post.account_display_name = await get_text_safe(display_name_elem)

        # Extract tweet text
        text_elem = await try_selectors(article, SELECTORS["tweet_text"])
        post.text_content = await get_text_safe(text_elem)

        # Extract engagement counts
        # Reply count
        reply_elem = await try_selectors(article, SELECTORS["reply_count"])
        reply_text = await get_text_safe(reply_elem)
        post.reply_count = parse_count(reply_text)

        # Repost count
        repost_elem = await try_selectors(article, SELECTORS["repost_count"])
        repost_text = await get_text_safe(repost_elem)
        post.repost_count = parse_count(repost_text)

        # Like count
        like_elem = await try_selectors(article, SELECTORS["like_count"])
        like_text = await get_text_safe(like_elem)
        post.like_count = parse_count(like_text)

        # View count
        view_elem = await try_selectors(article, SELECTORS["view_count"])
        view_text = await get_text_safe(view_elem)
        post.view_count = parse_count(view_text)

        # Check if repost
        repost_indicator = await try_selectors(article, SELECTORS["repost_indicator"])
        if repost_indicator:
            indicator_text = await get_text_safe(repost_indicator)
            post.is_repost = "repost" in indicator_text.lower()

        # Check if quote tweet
        quote_indicator = await try_selectors(article, SELECTORS["quote_indicator"])
        post.is_quote = quote_indicator is not None and await quote_indicator.count() > 0

        # Extract media URLs
        media_urls = []

        # Images
        for selector in SELECTORS["media_images"]:
            try:
                images = article.locator(selector)
                count = await images.count()
                for i in range(count):
                    src = await images.nth(i).get_attribute("src", timeout=1000)
                    if src and "pbs.twimg.com" in src:
                        # Get highest quality version
                        if "?" in src:
                            src = src.split("?")[0]
                        src = f"{src}?format=jpg&name=large"
                        if src not in media_urls:
                            media_urls.append(src)
            except Exception:
                continue

        # Videos (get poster/thumbnail at minimum)
        for selector in SELECTORS["media_videos"]:
            try:
                videos = article.locator(selector)
                count = await videos.count()
                for i in range(count):
                    src = await videos.nth(i).get_attribute("src", timeout=1000)
                    if src and src not in media_urls:
                        media_urls.append(src)
            except Exception:
                continue

        post.media_urls = media_urls

        # Validate we have minimum required data
        if not post.post_id and not post.text_content:
            logger.debug("Skipping post with no ID and no text content")
            return None

        return post

    except Exception as e:
        logger.debug(f"Error extracting post data: {e}")
        return None


def parse_twitter_timestamp(timestamp_str: str) -> Optional[datetime]:
    """
    Parse various Twitter timestamp formats to datetime.

    Args:
        timestamp_str: Timestamp string (ISO format or relative)

    Returns:
        datetime object or None
    """
    if not timestamp_str:
        return None

    try:
        # ISO format (most common from time[datetime] attribute)
        if "T" in timestamp_str:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except Exception:
        pass

    return None


def is_post_within_cutoff(post: PostData, cutoff_date: Optional[datetime]) -> bool:
    """
    Check if a post is within the date cutoff.

    Args:
        post: PostData object
        cutoff_date: Cutoff datetime (posts older than this are excluded)

    Returns:
        True if post is within cutoff or no cutoff is set
    """
    if cutoff_date is None:
        return True

    if not post.timestamp:
        # If no timestamp, include the post (can't verify)
        return True

    post_date = parse_twitter_timestamp(post.timestamp)
    if post_date is None:
        return True

    # Remove timezone info for comparison if needed
    if post_date.tzinfo is not None:
        post_date = post_date.replace(tzinfo=None)

    return post_date >= cutoff_date
