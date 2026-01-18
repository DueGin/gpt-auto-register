from __future__ import annotations

import argparse
import random
import string
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from config import cfg
from feishu_bitable import _get_tenant_access_token
from feishu_bitable import write_account_to_bitable, update_plus_redeemed_time_in_bitable


def _mask(s: str, keep_start: int = 3, keep_end: int = 2) -> str:
    v = (s or "").strip()
    if not v:
        return ""
    if len(v) <= keep_start + keep_end:
        return v[:1] + ("*" * (len(v) - 1))
    return v[:keep_start] + ("*" * (len(v) - keep_start - keep_end)) + v[-keep_end:]


def _rand_email(domain: str) -> str:
    prefix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"debug_{prefix}@{domain}"


def _print_http_result(title: str, resp):
    status = getattr(resp, "status_code", None)
    print(f"{title}: status={status}")
    try:
        data = resp.json()
        print(f"{title}: json={data}")
    except Exception:
        text = getattr(resp, "text", "") or ""
        if len(text) > 1200:
            text = text[:1200] + "..."
        print(f"{title}: text={text}")


def check_bitable_access() -> None:
    if requests is None:
        print("⚠️ 当前环境缺少 requests，无法执行 --check")
        return

    fb = cfg.feishu_bitable
    session = requests.Session()
    try:
        token = _get_tenant_access_token(
            session=session,
            api_base_url=fb.api_base_url,
            app_id=fb.app_id,
            app_secret=fb.app_secret,
        )

        app_info_url = f"{fb.api_base_url.rstrip('/')}/bitable/v1/apps/{fb.app_token}"
        tables_url = f"{fb.api_base_url.rstrip('/')}/bitable/v1/apps/{fb.app_token}/tables"

        print("🔍 检查 Bitable app_token 可访问性...")
        resp = session.get(app_info_url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        _print_http_result("GET app_info", resp)

        print("🔍 检查 tables 列表可访问性...")
        resp = session.get(tables_url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        _print_http_result("GET tables", resp)

        try:
            data = resp.json() or {}
            items = (data.get("data") or {}).get("items") or []
            if items:
                print("📋 该 app_token 下的 table_id 列表（节选）:")
                for it in items[:10]:
                    print(f"- {it.get('table_id')} name={it.get('name')}")
        except Exception:
            pass
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="飞书多维表格调试脚本：插入/更新记录")
    parser.add_argument("--email", default="", help="写入的邮箱（默认自动生成）")
    parser.add_argument("--password", default="", help="写入的密码（默认自动生成）")
    parser.add_argument("--type", default="GPT", choices=["GPT", "Claude"], help="类型枚举")
    parser.add_argument("--check", action="store_true", help="先检查 app_token/table 权限")
    parser.add_argument("--insert", action="store_true", help="执行插入记录")
    parser.add_argument("--update-plus", action="store_true", help="执行更新兑换Plus时间")
    parser.add_argument("--record-id", default="", help="用于更新的 record_id（可选）")
    args = parser.parse_args()

    fb = cfg.feishu_bitable
    print("\n" + "=" * 60)
    print("🔎 飞书多维表格调试信息（已脱敏）")
    print("=" * 60)
    print(f"enabled: {fb.enabled}")
    print(f"api_base_url: {fb.api_base_url}")
    print(f"app_id: {_mask(fb.app_id)}")
    print(f"app_secret: {_mask(fb.app_secret)}")
    print(f"app_token: {_mask(fb.app_token)}")
    print(f"table_id: {fb.table_id}")
    print(
        "fields:"
        f" email={fb.fields.email}"
        f" password={fb.fields.password}"
        f" registered_at={fb.fields.registered_at}"
        f" plus_redeemed_at={fb.fields.plus_redeemed_at}"
        f" account_type={fb.fields.account_type}"
    )
    print("=" * 60 + "\n")

    if not fb.enabled:
        print("❌ feishu_bitable.enabled=false：请先在 config.yaml 里启用再测试")
        return 2

    if not (args.insert or args.update_plus):
        print("❌ 请至少指定一个动作：--insert 或 --update-plus")
        return 2

    if args.check:
        check_bitable_access()
        print("")

    email = args.email.strip() or _rand_email(cfg.email.domain or "example.com")
    password = args.password.strip() or ("Dbg_" + "".join(random.choices(string.ascii_letters + string.digits, k=12)))
    record_id = args.record_id.strip() or None

    if args.insert:
        print("🧪 开始插入记录...")
        ok, rid = write_account_to_bitable(
            email=email,
            password=password,
            status="已注册",
            account_type=args.type,
        )
        print(f"结果: ok={ok} record_id={rid}")
        if ok and rid:
            record_id = rid
        print("")

    if args.update_plus:
        print("🧪 开始更新兑换Plus时间...")
        print(f"使用 record_id: {record_id or '(空，将按邮箱遍历查找)'}")
        ok = update_plus_redeemed_time_in_bitable(email=email, record_id=record_id)
        print(f"结果: ok={ok}")
        print("")

    print("✅ 调试脚本执行完成")
    time.sleep(0.2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
