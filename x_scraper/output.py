"""
Output handlers for X/Twitter Scraper.

Handles saving scraped data to JSON and CSV formats.
"""

import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from .extractors import PostData
from .logger import get_logger

logger = get_logger()


class OutputHandler:
    """Handle saving scraped data to various formats."""

    def __init__(self, output_dir: str = "./data"):
        """
        Initialize output handler.

        Args:
            output_dir: Directory to save output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_json(self, data: List[Dict[str, Any]], filename: str) -> str:
        """
        Save data to JSON file.

        Args:
            data: List of dictionaries to save
            filename: Output filename (without path)

        Returns:
            Full path to saved file
        """
        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Saved JSON: {filepath}")
        return str(filepath)

    def save_csv(self, data: List[Dict[str, Any]], filename: str) -> str:
        """
        Save data to CSV file.

        Args:
            data: List of dictionaries to save
            filename: Output filename (without path)

        Returns:
            Full path to saved file
        """
        if not data:
            logger.warning(f"No data to save to CSV: {filename}")
            filepath = self.output_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("")
            return str(filepath)

        filepath = self.output_dir / filename

        # Get all unique fields from all records
        fieldnames = []
        for record in data:
            for key in record.keys():
                if key not in fieldnames:
                    fieldnames.append(key)

        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()

            for record in data:
                # Convert list fields to string for CSV
                row = {}
                for key, value in record.items():
                    if isinstance(value, list):
                        row[key] = "; ".join(str(v) for v in value)
                    else:
                        row[key] = value
                writer.writerow(row)

        logger.info(f"Saved CSV: {filepath}")
        return str(filepath)

    def save_posts(
        self,
        posts: List[PostData],
        handle: Optional[str] = None,
        combined: bool = False
    ) -> Dict[str, str]:
        """
        Save posts to both JSON and CSV.

        Args:
            posts: List of PostData objects
            handle: Account handle (for per-account files)
            combined: If True, save as combined results files

        Returns:
            Dictionary with paths to saved files
        """
        data = [post.to_dict() for post in posts]

        if combined:
            json_file = "results.json"
            csv_file = "results.csv"
        elif handle:
            # Sanitize handle for filename
            safe_handle = "".join(c for c in handle if c.isalnum() or c in "_-")
            json_file = f"{safe_handle}.json"
            csv_file = f"{safe_handle}.csv"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_file = f"posts_{timestamp}.json"
            csv_file = f"posts_{timestamp}.csv"

        return {
            "json": self.save_json(data, json_file),
            "csv": self.save_csv(data, csv_file)
        }

    def save_all_results(
        self,
        posts_by_account: Dict[str, List[PostData]]
    ) -> Dict[str, Any]:
        """
        Save all results - per-account files and combined files.

        Args:
            posts_by_account: Dictionary mapping handles to list of posts

        Returns:
            Dictionary with all saved file paths
        """
        saved_files = {
            "per_account": {},
            "combined": {}
        }

        # Save per-account files
        for handle, posts in posts_by_account.items():
            if posts:
                saved_files["per_account"][handle] = self.save_posts(
                    posts, handle=handle
                )

        # Combine all posts
        all_posts = []
        for posts in posts_by_account.values():
            all_posts.extend(posts)

        # Save combined files
        if all_posts:
            saved_files["combined"] = self.save_posts(all_posts, combined=True)

        return saved_files
