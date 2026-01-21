#!/usr/bin/env python3
"""
快速启动注册程序
直接运行此脚本即可启动 Web 注册服务

用法:
    python3 quick_start.py          # 直接启动
    python3 quick_start.py --scrape 20  # 先爬取20个地址再启动
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置检查
from config import cfg
from pathlib import Path
import json

def check_addresses():
    """检查地址库"""
    scraper_dir = Path("美国地址爬虫_副本")
    total = 0
    
    if scraper_dir.exists():
        for json_file in scraper_dir.glob("basic_addresses_*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        total += len(data)
            except:
                pass
    
    return total

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='快速启动注册服务')
    parser.add_argument('--scrape', type=int, help='先采集指定数量的地址')
    args = parser.parse_args()
    
    # 如果指定了爬虫
    if args.scrape:
        print(f"📥 先采集 {args.scrape} 个地址...")
        os.system(f"python3 start_with_scraper.py --scrape {args.scrape}")
        return
    
    # 检查地址库
    addr_count = check_addresses()
    print(f"\n📋 当前地址库: {addr_count} 个地址")
    print(f"📝 地址来源: {cfg.payment.billing.address_source}")
    
    if addr_count == 0 and cfg.payment.billing.address_source == "scraped":
        print("\n⚠️ 爬虫地址库为空!")
        print("💡 建议运行: python3 quick_start.py --scrape 20")
        response = input("\n是否继续? (y/n): ").strip().lower()
        if response != 'y':
            return
    
    print("\n🚀 启动注册服务...")
    print("📺 访问: http://localhost:7070")
    print("🛑 按 Ctrl+C 停止\n")
    
    # 启动服务
    from waitress import serve
    import server
    
    serve(server.app, host='0.0.0.0', port=7070, threads=6)

if __name__ == '__main__':
    main()
