#!/usr/bin/env python3
"""
先爬取地址，再启动注册服务
用法:
    python3 start_with_scraper.py --scrape 20   # 爬取20个地址后启动服务
    python3 start_with_scraper.py               # 直接启动服务
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path
import shutil


def _configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if not hasattr(stream, "reconfigure"):
            continue
        try:
            encoding = stream.encoding or "utf-8"
            stream.reconfigure(encoding=encoding, errors="replace")
        except Exception:
            pass


_configure_stdio()

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_ROOT = Path(__file__).resolve().parent


def _copy_new_outputs(scraper_dir: Path, output_dir: Path, before: set[Path]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    after = set(scraper_dir.glob("basic_addresses_*.json")) | set(scraper_dir.glob("basic_addresses_*.csv"))
    new_files = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)

    if not new_files:
        print("⚠️ 未检测到新的输出文件（basic_addresses_*.json/csv）")
        return

    if output_dir.resolve() == scraper_dir.resolve():
        print(f"✅ 输出已保存在: {scraper_dir}")
        return

    for fp in new_files:
        dest = output_dir / fp.name
        shutil.copy2(fp, dest)
        print(f"✅ 已复制到: {dest}")

def run_scraper(count: int, output_dir: Path):
    """运行爬虫采集地址"""
    scraper_dir = Path("美国地址爬虫_副本")
    scraper_dir = PROJECT_ROOT / scraper_dir
    
    if not scraper_dir.exists():
        print("❌ 爬虫目录不存在: 美国地址爬虫_副本")
        return False
    
    scraper_script = scraper_dir / "basic_fields_scraper.py"
    if not scraper_script.exists():
        print(f"❌ 爬虫脚本不存在: {scraper_script}")
        return False
    
    print(f"🕷️  启动爬虫，采集 {count} 个地址...")
    
    try:
        before = set(scraper_dir.glob("basic_addresses_*.json")) | set(scraper_dir.glob("basic_addresses_*.csv"))
        # 创建临时 Python 脚本来运行爬虫
        temp_scraper = scraper_dir / "temp_scraper_runner.py"
        with open(temp_scraper, 'w', encoding='utf-8') as f:
            f.write(f'''#!/usr/bin/env python3
import sys
sys.path.insert(0, ".")
from basic_fields_scraper import scrape_basic
scrape_basic(count={count}, delay=2)
''')
        
        # 运行爬虫
        result = subprocess.run(
            [sys.executable, "temp_scraper_runner.py"],
            cwd=str(scraper_dir),
            capture_output=False
        )
        
        # 清理临时文件
        try:
            temp_scraper.unlink()
        except:
            pass
        
        ok = result.returncode == 0
        if ok:
            _copy_new_outputs(scraper_dir=scraper_dir, output_dir=output_dir, before=before)
        return ok
    except Exception as e:
        print(f"❌ 爬虫执行失败: {e}")
        return False

def start_service():
    """启动 Web 服务"""
    print("\n🚀 启动注册服务...")
    print("📺 访问: http://localhost:7070")
    print("🛑 按 Ctrl+C 停止\n")
    
    try:
        from waitress import serve
        import server
        
        serve(server.app, host='0.0.0.0', port=7070, threads=6)
    except KeyboardInterrupt:
        print("\n✅ 服务已停止")
    except Exception as e:
        print(f"❌ 服务启动失败: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='爬取地址并启动服务')
    parser.add_argument('--scrape', type=int, help='采集指定数量的地址')
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT),
        help="将爬取到的 basic_addresses_*.json/csv 额外复制到该目录（默认：项目根目录）",
    )
    args = parser.parse_args()
    
    # 加载配置并检查地址库
    from config import cfg
    import json
    output_dir = Path(args.output_dir)
    
    # 如果指定了采集数量
    if args.scrape:
        if run_scraper(args.scrape, output_dir=output_dir):
            print("✅ 地址采集完成")
        else:
            print("⚠️ 地址采集出现问题，继续启动服务...")
    else:
        # 检查地址库
        scraper_dir = Path("美国地址爬虫_副本")
        scraper_dir = PROJECT_ROOT / scraper_dir
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
        
        print(f"📋 当前地址库: {total} 个地址")
        print(f"📝 地址来源: {cfg.payment.billing.address_source}")
    
    # 启动服务
    start_service()

if __name__ == '__main__':
    main()
