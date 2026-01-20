#!/usr/bin/env python3
"""
测试从 meiguodizhi.com 抓取地址功能
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import fetch_meiguodizhi_address, generate_billing_info

def test_fetch_address():
    """测试从 meiguodizhi.com 抓取地址"""
    print("\n" + "=" * 50)
    print("🧪 测试: 从 meiguodizhi.com 获取随机美国地址")
    print("=" * 50)
    
    result = fetch_meiguodizhi_address()
    
    if result:
        print("\n✅ 测试通过! 成功获取地址:")
        print(f"   姓名: {result.get('name')}")
        print(f"   街道: {result.get('address1')}")
        print(f"   城市: {result.get('city')}")
        print(f"   州: {result.get('state')}")
        print(f"   邮编: {result.get('zip')}")
        print(f"   电话: {result.get('phone', 'N/A')}")
    else:
        print("\n❌ 测试失败: 无法获取地址")
    
    return result

def test_generate_billing_info():
    """测试生成完整账单信息"""
    print("\n" + "=" * 50)
    print("🧪 测试: 生成完整账单信息 (使用 meiguodizhi.com)")
    print("=" * 50)
    
    # 这将根据 config.yaml 中的 address_source 设置自动选择
    result = generate_billing_info(country="US")
    
    if result:
        print("\n✅ 账单信息生成成功:")
        for key, value in result.items():
            print(f"   {key}: {value}")
    else:
        print("\n❌ 账单信息生成失败")
    
    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="测试地址抓取功能")
    parser.add_argument("--fetch", action="store_true", help="测试 meiguodizhi.com 抓取")
    parser.add_argument("--billing", action="store_true", help="测试生成账单信息")
    parser.add_argument("--all", action="store_true", help="运行所有测试")
    
    args = parser.parse_args()
    
    if args.all or args.fetch:
        test_fetch_address()
    
    if args.all or args.billing:
        test_generate_billing_info()
    
    if not any([args.all, args.fetch, args.billing]):
        print("用法:")
        print("  python test_meiguodizhi.py --fetch   # 测试地址抓取")
        print("  python test_meiguodizhi.py --billing # 测试账单信息生成")
        print("  python test_meiguodizhi.py --all     # 运行所有测试")
