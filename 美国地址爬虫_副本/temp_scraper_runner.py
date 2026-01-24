#!/usr/bin/env python3
import sys
import argparse

sys.path.insert(0, ".")
from basic_fields_scraper import scrape_basic


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the basic fields scraper with configurable count and delay.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of items to scrape (default: 20).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2,
        help="Delay between requests in seconds (default: 2).",
    )

    args = parser.parse_args()
    scrape_basic(count=args.count, delay=args.delay)


if __name__ == "__main__":
    main()
from basic_fields_scraper import scrape_basic
scrape_basic(count=20, delay=2)
