"""
飞书多维表格（Bitable）写入模块

在注册成功后，将账号信息写入指定多维表格数据表。
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import requests

from config import cfg

_TOKEN_CACHE: Dict[str, Any] = {
    "tenant_access_token": None,
    "expires_at": 0.0,
}

_DEBUG = (os.getenv("FEISHU_BITABLE_DEBUG") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _now_datetime_value(fmt: str) -> Any:
    if (fmt or "").lower() == "timestamp_ms":
        return int(time.time() * 1000)
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _mask_email(email: str) -> str:
    e = (email or "").strip()
    if "@" not in e:
        return "***"
    name, domain = e.split("@", 1)
    if len(name) <= 2:
        return f"{name[:1]}***@{domain}"
    return f"{name[:2]}***@{domain}"


def _mask_password(password: str) -> str:
    p = (password or "").strip()
    if not p:
        return ""
    if len(p) <= 2:
        return "*" * len(p)
    return p[:1] + ("*" * (len(p) - 2)) + p[-1:]


def _mask_token(token: str) -> str:
    t = (token or "").strip()
    if not t:
        return ""
    if len(t) <= 10:
        return t[:2] + ("*" * (len(t) - 2))
    return t[:6] + "..." + t[-4:]


def _safe_fields_for_log(fields: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    email_field_name = (cfg.feishu_bitable.fields.email or "").strip()
    password_field_name = (cfg.feishu_bitable.fields.password or "").strip()
    for k, v in (fields or {}).items():
        if (email_field_name and k == email_field_name) or (
            isinstance(v, str) and "@" in v
        ):
            safe[k] = _mask_email(v)
        elif (password_field_name and k == password_field_name) or k in {
            "密码",
            "password",
            "Password",
        }:
            safe[k] = _mask_password(str(v))
        else:
            safe[k] = v
    return safe


def _response_text_preview(resp: Any, limit: int = 1200) -> str:
    text = getattr(resp, "text", None)
    if not text:
        content = getattr(resp, "content", b"") or b""
        if isinstance(content, (bytes, bytearray)):
            try:
                text = content.decode("utf-8", errors="ignore")
            except Exception:
                text = ""
        else:
            text = str(content)
    text = str(text)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _get_tenant_access_token(
    session: requests.Session,
    api_base_url: str,
    app_id: str,
    app_secret: str,
    timeout: int = 15,
) -> str:
    cached_token = _TOKEN_CACHE.get("tenant_access_token")
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0.0)
    now = time.time()
    if cached_token and now < (expires_at - 60):
        return str(cached_token)

    url = f"{api_base_url.rstrip('/')}/auth/v3/tenant_access_token/internal/"
    resp = session.post(
        url,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json() or {}
    if data.get("code") != 0 or not data.get("tenant_access_token"):
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")

    token = str(data["tenant_access_token"])
    expire_seconds = int(data.get("expire") or 7200)
    _TOKEN_CACHE["tenant_access_token"] = token
    _TOKEN_CACHE["expires_at"] = now + expire_seconds
    if _DEBUG:
        print(
            "🔑 已获取 tenant_access_token:"
            f" token={_mask_token(token)} expire={expire_seconds}s"
        )
    return token


def _build_record_fields(
    email: str,
    password: str,
    status: str,
    account_type: str,
) -> Dict[str, Any]:
    fields_cfg = cfg.feishu_bitable.fields
    record_fields: Dict[str, Any] = {}

    if fields_cfg.email:
        record_fields[fields_cfg.email] = email
    if fields_cfg.password:
        record_fields[fields_cfg.password] = password
    if fields_cfg.registered_at:
        record_fields[fields_cfg.registered_at] = _now_datetime_value(
            cfg.feishu_bitable.created_at_format
        )
    elif fields_cfg.created_at:
        record_fields[fields_cfg.created_at] = _now_datetime_value(
            cfg.feishu_bitable.created_at_format
        )
    if fields_cfg.account_type:
        record_fields[fields_cfg.account_type] = account_type
    if fields_cfg.status:
        record_fields[fields_cfg.status] = status

    return record_fields


def write_account_to_bitable(
    email: str,
    password: str,
    status: str = "已注册",
    account_type: str = "GPT",
) -> Tuple[bool, Optional[str]]:
    """
    写入一条记录到飞书多维表格。

    返回:
        (ok, record_id)
    """
    conf = cfg.feishu_bitable
    if not conf.enabled:
        return False, None

    missing = [
        name
        for name, val in [
            ("app_id", conf.app_id),
            ("app_secret", conf.app_secret),
            ("app_token", conf.app_token),
            ("table_id", conf.table_id),
        ]
        if not val
    ]
    if missing:
        print(f"⚠️ 飞书多维表格未配置完整，缺少: {', '.join(missing)}，已跳过写入")
        return False, None

    normalized_account_type = (account_type or "").strip()
    if normalized_account_type.lower() == "gpt":
        normalized_account_type = "GPT"
    elif normalized_account_type.lower() == "claude":
        normalized_account_type = "Claude"

    record_fields = _build_record_fields(email, password, status, normalized_account_type)
    if not record_fields:
        print("⚠️ 飞书多维表格字段映射为空，已跳过写入")
        return False, None

    session = requests.Session()
    try:
        token = _get_tenant_access_token(
            session=session,
            api_base_url=conf.api_base_url,
            app_id=conf.app_id,
            app_secret=conf.app_secret,
        )
        url = (
            f"{conf.api_base_url.rstrip('/')}/bitable/v1/apps/{conf.app_token}/tables/"
            f"{conf.table_id}/records"
        )
        print(
            "📌 准备写入飞书多维表格:"
            f" app_token=...{str(conf.app_token)[-6:]}"
            f" table_id={conf.table_id}"
            f" fields={_safe_fields_for_log(record_fields)}"
        )
        resp = session.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": record_fields},
            timeout=20,
        )
        http_status = int(getattr(resp, "status_code", 0) or 0)
        try:
            data = resp.json() or {}
        except Exception:
            data = {}

        if http_status >= 400:
            print(
                "⚠️ 写入飞书多维表格 HTTP 错误:"
                f" status={http_status} url={url}"
                f" body={_response_text_preview(resp)}"
            )
            if data:
                print(
                    "⚠️ 写入飞书多维表格返回:"
                    f" code={data.get('code')} msg={data.get('msg') or data.get('message')}"
                )
            return False, None

        if data.get("code") != 0:
            print(
                "⚠️ 写入飞书多维表格失败:"
                f" code={data.get('code')} msg={data.get('msg') or data.get('message')}"
            )
            return False, None

        data_data = data.get("data") or {}
        record_obj = data_data.get("record") or {}
        record_id = record_obj.get("record_id") or data_data.get("record_id")
        print(f"✅ 已写入飞书多维表格 record_id={record_id}")
        return True, record_id
    except Exception as e:
        print(f"⚠️ 写入飞书多维表格异常（不影响注册结果）: {e}")
        return False, None
    finally:
        session.close()


def _stringify_field_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool)):
        return str(val)
    if isinstance(val, list):
        return ",".join(_stringify_field_value(x) for x in val)
    if isinstance(val, dict):
        return str(val)
    return str(val)


def _find_record_id_by_email(
    session: requests.Session,
    api_base_url: str,
    tenant_access_token: str,
    app_token: str,
    table_id: str,
    email: str,
    email_field_name: str,
    page_size: int = 200,
    max_pages: int = 50,
) -> Optional[str]:
    url = f"{api_base_url.rstrip('/')}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    page_token: Optional[str] = None
    for _ in range(max_pages):
        params: Dict[str, Any] = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        resp = session.get(
            url,
            headers={"Authorization": f"Bearer {tenant_access_token}"},
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json() or {}
        if data.get("code") != 0:
            raise RuntimeError(f"查询飞书多维表格记录失败: {data}")

        data_data = data.get("data") or {}
        items = data_data.get("items") or data_data.get("records") or []
        for item in items:
            fields = (item or {}).get("fields") or {}
            field_val = fields.get(email_field_name)
            if _stringify_field_value(field_val).strip().lower() == email.strip().lower():
                return (item or {}).get("record_id")

        if not data_data.get("has_more"):
            break
        page_token = data_data.get("page_token")
        if not page_token:
            break

    return None


def update_plus_redeemed_time_in_bitable(
    email: str,
    record_id: Optional[str] = None,
) -> bool:
    """
    更新“兑换Plus时间”字段。
    优先使用 record_id；否则会按“邮箱”字段遍历查找。
    """
    conf = cfg.feishu_bitable
    if not conf.enabled:
        return False

    fields_cfg = conf.fields
    if not fields_cfg.plus_redeemed_at:
        print("⚠️ 未配置飞书多维表格字段 plus_redeemed_at，已跳过更新")
        return False

    if not record_id:
        if not (fields_cfg.email and email):
            print("⚠️ 未配置飞书多维表格字段 email，无法按邮箱匹配记录")
            return False

    session = requests.Session()
    try:
        token = _get_tenant_access_token(
            session=session,
            api_base_url=conf.api_base_url,
            app_id=conf.app_id,
            app_secret=conf.app_secret,
        )

        if not record_id:
            record_id = _find_record_id_by_email(
                session=session,
                api_base_url=conf.api_base_url,
                tenant_access_token=token,
                app_token=conf.app_token,
                table_id=conf.table_id,
                email=email,
                email_field_name=fields_cfg.email,
            )

        if not record_id:
            print("⚠️ 未找到需要更新的飞书多维表格记录（按邮箱匹配失败）")
            return False

        url = (
            f"{conf.api_base_url.rstrip('/')}/bitable/v1/apps/{conf.app_token}/tables/"
            f"{conf.table_id}/records/{record_id}"
        )
        print(
            "📌 准备更新飞书多维表格兑换Plus时间:"
            f" record_id={record_id} email={_mask_email(email)}"
        )
        resp = session.put(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "fields": {
                    fields_cfg.plus_redeemed_at: _now_datetime_value(conf.created_at_format)
                }
            },
            timeout=20,
        )
        http_status = int(getattr(resp, "status_code", 0) or 0)
        try:
            data = resp.json() or {}
        except Exception:
            data = {}

        if http_status >= 400:
            print(
                "⚠️ 更新飞书多维表格兑换Plus时间 HTTP 错误:"
                f" status={http_status} url={url}"
                f" body={_response_text_preview(resp)}"
            )
            if data:
                print(
                    "⚠️ 更新飞书多维表格返回:"
                    f" code={data.get('code')} msg={data.get('msg') or data.get('message')}"
                )
            return False

        if data.get("code") != 0:
            print(
                "⚠️ 更新飞书多维表格兑换Plus时间失败:"
                f" code={data.get('code')} msg={data.get('msg') or data.get('message')}"
            )
            return False

        print("✅ 已更新飞书多维表格兑换Plus时间")
        return True
    except Exception as e:
        print(f"⚠️ 更新飞书多维表格兑换Plus时间异常（不影响主流程）: {e}")
        return False
    finally:
        session.close()
