#!/usr/bin/env python3
"""
批量从 meiguodizhi.com 爬取美国地址并保存到文件

使用方法:
    python scripts/batch_fetch_addresses.py --count 100 --output addresses.json
    python scripts/batch_fetch_addresses.py -c 50 -o addresses.csv --format csv
"""

import sys
import os
import time
import json
import argparse
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import fetch_meiguodizhi_address


def batch_fetch_addresses(count=100, delay_min=1, delay_max=3, output_file=None, file_format='json'):
    """
    批量爬取地址
    
    参数:
        count: 要爬取的地址数量
        delay_min: 每次请求之间的最小延迟(秒)
        delay_max: 每次请求之间的最大延迟(秒)
        output_file: 输出文件路径
        file_format: 输出格式 ('json' 或 'csv')
    """
    import random
    
    addresses = []
    success_count = 0
    fail_count = 0
    
    print("=" * 60)
    print(f"📥 开始批量爬取美国地址 (目标: {count} 个)")
    print("=" * 60)
    
    for i in range(count):
        print(f"\n[{i+1}/{count}] 正在获取地址...")
        
        try:
            address_data = fetch_meiguodizhi_address()
            
            if address_data:
                # 检查是否重复（基于地址1）
                is_duplicate = any(
                    addr.get('address1') == address_data.get('address1') 
                    for addr in addresses
                )
                
                if is_duplicate:
                    print(f"⚠️ 地址重复，跳过")
                    fail_count += 1
                else:
                    addresses.append(address_data)
                    success_count += 1
                    print(f"✅ 成功 ({success_count}/{count})")
            else:
                fail_count += 1
                print(f"❌ 失败 ({fail_count} 次失败)")
        
        except KeyboardInterrupt:
            print("\n\n⚠️ 用户中断，正在保存已获取的地址...")
            break
        except Exception as e:
            fail_count += 1
            print(f"❌ 异常: {e}")
        
        # 如果还没完成，等待一段时间再继续
        if i < count - 1:
            delay = random.uniform(delay_min, delay_max)
            print(f"⏳ 等待 {delay:.1f} 秒...")
            time.sleep(delay)
    
    # 保存结果
    print("\n" + "=" * 60)
    print(f"📊 爬取完成:")
    print(f"   ✅ 成功: {success_count}")
    print(f"   ❌ 失败: {fail_count}")
    print(f"   📦 总计: {len(addresses)} 个有效地址")
    print("=" * 60)
    
    if addresses and output_file:
        save_addresses(addresses, output_file, file_format)
    
    return addresses


def save_addresses(addresses, output_file, file_format='json'):
    """
    保存地址到文件
    
    参数:
        addresses: 地址列表
        output_file: 输出文件路径
        file_format: 文件格式 ('json' 或 'csv')
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if file_format == 'json':
            # 保存为 JSON
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(addresses, f, indent=2, ensure_ascii=False)
            print(f"\n💾 已保存到: {output_path} (JSON 格式)")
        
        elif file_format == 'csv':
            # 保存为 CSV
            import csv
            
            if not addresses:
                print("⚠️ 没有地址可保存")
                return
            
            # 获取所有字段名
            fieldnames = list(addresses[0].keys())
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(addresses)
            
            print(f"\n💾 已保存到: {output_path} (CSV 格式)")
        
        else:
            print(f"❌ 不支持的格式: {file_format}")
            return
        
        # 显示文件大小
        file_size = output_path.stat().st_size
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        
        print(f"📏 文件大小: {size_str}")
        
    except Exception as e:
        print(f"❌ 保存文件失败: {e}")


def load_addresses(input_file):
    """
    从文件加载地址
    
    参数:
        input_file: 输入文件路径
    """
    input_path = Path(input_file)
    
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_path}")
        return []
    
    try:
        file_format = input_path.suffix.lower()
        
        if file_format == '.json':
            with open(input_path, 'r', encoding='utf-8') as f:
                addresses = json.load(f)
            print(f"✅ 从 {input_path} 加载了 {len(addresses)} 个地址")
            return addresses
        
        elif file_format == '.csv':
            import csv
            addresses = []
            with open(input_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                addresses = list(reader)
            print(f"✅ 从 {input_path} 加载了 {len(addresses)} 个地址")
            return addresses
        
        else:
            print(f"❌ 不支持的文件格式: {file_format}")
            return []
    
    except Exception as e:
        print(f"❌ 加载文件失败: {e}")
        return []


def display_addresses(addresses, limit=10):
    """
    显示地址列表
    
    参数:
        addresses: 地址列表
        limit: 显示数量限制
    """
    if not addresses:
        print("⚠️ 没有地址可显示")
        return
    
    print("\n" + "=" * 60)
    print(f"📋 地址列表 (显示前 {min(limit, len(addresses))} 个):")
    print("=" * 60)
    
    for i, addr in enumerate(addresses[:limit], 1):
        print(f"\n[{i}]")
        print(f"  姓名: {addr.get('name', 'N/A')}")
        print(f"  地址: {addr.get('address1', 'N/A')}")
        print(f"  城市: {addr.get('city', 'N/A')}")
        print(f"  州: {addr.get('state', 'N/A')}")
        print(f"  邮编: {addr.get('zip', 'N/A')}")
    
    if len(addresses) > limit:
        print(f"\n... 还有 {len(addresses) - limit} 个地址未显示")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='批量从 meiguodizhi.com 爬取美国地址',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 爬取 100 个地址并保存为 JSON
  python scripts/batch_fetch_addresses.py -c 100 -o addresses.json
  
  # 爬取 50 个地址并保存为 CSV
  python scripts/batch_fetch_addresses.py -c 50 -o addresses.csv -f csv
  
  # 查看已保存的地址
  python scripts/batch_fetch_addresses.py --view addresses.json
        """
    )
    
    parser.add_argument(
        '-c', '--count',
        type=int,
        default=10,
        help='要爬取的地址数量 (默认: 10)'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        help='输出文件路径 (如: addresses.json 或 addresses.csv)'
    )
    
    parser.add_argument(
        '-f', '--format',
        type=str,
        choices=['json', 'csv'],
        default='json',
        help='输出文件格式 (默认: json)'
    )
    
    parser.add_argument(
        '--delay-min',
        type=float,
        default=1.0,
        help='请求之间的最小延迟(秒) (默认: 1.0)'
    )
    
    parser.add_argument(
        '--delay-max',
        type=float,
        default=3.0,
        help='请求之间的最大延迟(秒) (默认: 3.0)'
    )
    
    parser.add_argument(
        '--view',
        type=str,
        help='查看已保存的地址文件'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='查看地址时的显示数量限制 (默认: 10)'
    )
    
    args = parser.parse_args()
    
    # 如果是查看模式
    if args.view:
        addresses = load_addresses(args.view)
        display_addresses(addresses, args.limit)
        return
    
    # 确定输出文件
    if not args.output:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        args.output = f"addresses_{timestamp}.{args.format}"
        print(f"ℹ️ 未指定输出文件，将保存到: {args.output}")
    
    # 开始爬取
    addresses = batch_fetch_addresses(
        count=args.count,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        output_file=args.output,
        file_format=args.format
    )
    
    # 显示部分结果
    if addresses:
        display_addresses(addresses, limit=5)


if __name__ == '__main__':
    main()
