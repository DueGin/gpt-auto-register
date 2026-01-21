#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只提取核心字段的爬虫示例。
字段：全名、街道、城市、州全称、邮编。
"""

from address_scraper import AddressScraper
import json
import csv
from datetime import datetime


TARGET_FIELDS = [
    "全名",
    "街道",
    "城市",
    "州全称",
    "邮编",
]


def scrape_basic(count: int = 5, delay: int = 2):
    scraper = AddressScraper(headless=True)
    records = scraper.scrape_multiple_addresses(count=count, delay=delay)

    simplified = []
    for rec in records:
        simplified.append({k: rec.get(k, "") for k in TARGET_FIELDS})
    
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_name = f"basic_addresses_{ts}.json"
    csv_name = f"basic_addresses_{ts}.csv"

    with open(json_name, "w", encoding="utf-8") as f:
        json.dump(simplified, f, ensure_ascii=False, indent=2)

    with open(csv_name, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TARGET_FIELDS)
        writer.writeheader()
        writer.writerows(simplified)

    print(f"已保存 JSON: {json_name}")
    print(f"已保存 CSV:  {csv_name}")
    return simplified


def main():
    scrape_basic(count=5, delay=2)


if __name__ == "__main__":
    main()
