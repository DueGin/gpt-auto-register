#!/usr/bin/env python3
"""
清理和整理地址数据
从 random_addresses.json 提取完整的 basic 字段地址
"""

import json
from pathlib import Path
from datetime import datetime

# 读取 random_addresses.json
scraper_dir = Path("美国地址爬虫_副本")
random_file = scraper_dir / "random_addresses.json"

print("📄 读取源文件...")
with open(random_file, 'r', encoding='utf-8') as f:
    all_addresses = json.load(f)

print(f"✅ 共读取 {len(all_addresses)} 条地址")

# 提取需要的字段
target_fields = ["全名", "街道", "城市", "州全称", "邮编"]
cleaned_addresses = []

for addr in all_addresses:
    cleaned = {}
    cleaned["全名"] = addr.get("全名", "").strip()
    cleaned["街道"] = addr.get("街道", "").strip()
    cleaned["城市"] = addr.get("城市", "").strip()
    cleaned["州全称"] = addr.get("州全称", "").strip()
    cleaned["邮编"] = addr.get("邮编", "").strip()
    
    # 只保留完整的记录
    if all(cleaned.get(k) for k in target_fields):
        cleaned_addresses.append(cleaned)

print(f"✅ 提取了 {len(cleaned_addresses)} 条完整地址")

# 保存为新的 basic_addresses 文件
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
output_file = scraper_dir / f"basic_addresses_{ts}.json"

with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(cleaned_addresses, f, ensure_ascii=False, indent=2)

print(f"✅ 已保存到: {output_file.name}\n")

# 显示前 5 条数据验证
print("📋 前 5 条地址预览:")
print("-" * 60)
for i, addr in enumerate(cleaned_addresses[:5], 1):
    print(f"[{i}] {addr['全名']:15} | {addr['城市']:15} {addr['州全称']:12} {addr['邮编']}")

print("-" * 60)
print(f"✅ 总计 {len(cleaned_addresses)} 条有效地址\n")

# 删除有问题的文件
print("🧹 清理...")
bad_files = [
    "basic_addresses_20260121-124423.json",
    "basic_addresses_20260121-110405.json",
]

for bad_name in bad_files:
    bad_file = scraper_dir / bad_name
    if bad_file.exists():
        bad_file.unlink()
        print(f"✅ 已删除: {bad_name}")

print("\n✨ 地址整理完成！")
