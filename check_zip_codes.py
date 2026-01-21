#!/usr/bin/env python3
import json
from pathlib import Path
import re

def is_valid_zip(zip_code):
    """检查邮编是否有效（5 位数或 5+4 位）"""
    if not zip_code:
        return False
    # 移除所有非数字字符
    cleaned = re.sub(r'\D', '', str(zip_code))
    return len(cleaned) == 5 or len(cleaned) == 9

def fix_zip_codes():
    """修复所有 JSON 文件中的邮编"""
    dir_path = Path("美国地址爬虫_副本")
    
    for json_file in sorted(dir_path.glob('basic_addresses_*.json')):
        print(f"\n检查文件: {json_file.name}")
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        invalid_count = 0
        for record in data:
            zip_code = record.get('邮编', '')
            if not is_valid_zip(zip_code):
                invalid_count += 1
                print(f"  ❌ 无效邮编: {zip_code} - {record.get('全名')}")
        
        if invalid_count == 0:
            print(f"  ✅ 所有邮编有效")
        else:
            print(f"  ⚠️ 发现 {invalid_count} 个无效邮编")

if __name__ == '__main__':
    fix_zip_codes()
