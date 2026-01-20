import importlib
import sys
import types
import unittest
from unittest.mock import patch


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, routes: dict):
        self.routes = routes
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers, timeout))
        payload = self.routes.get(("POST", url))
        if payload is None:
            return FakeResponse(404, {"code": 404, "msg": "not found"})
        return FakeResponse(200, payload)

    def put(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("PUT", url, json, headers, timeout))
        payload = self.routes.get(("PUT", url))
        if payload is None:
            return FakeResponse(404, {"code": 404, "msg": "not found"})
        return FakeResponse(200, payload)

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params, headers, timeout))
        payload = self.routes.get(("GET", url))
        if payload is None:
            return FakeResponse(404, {"code": 404, "msg": "not found"})
        return FakeResponse(200, payload)

    def close(self):
        return None


def _load_feishu_bitable_with_stub_cfg(cfg_stub):
    config_mod = types.ModuleType("config")
    config_mod.cfg = cfg_stub
    sys.modules["config"] = config_mod

    if "requests" not in sys.modules:
        requests_mod = types.ModuleType("requests")

        class _PlaceholderSession:
            pass

        requests_mod.Session = _PlaceholderSession
        sys.modules["requests"] = requests_mod

    if "feishu_bitable" in sys.modules:
        del sys.modules["feishu_bitable"]
    import feishu_bitable  # noqa: F401

    return importlib.import_module("feishu_bitable")


class TestFeishuBitable(unittest.TestCase):
    def setUp(self):
        self.api_base_url = "https://open.feishu.cn/open-apis"
        self.app_id = "cli_test"
        self.app_secret = "secret_test"
        self.app_token = "basc_test"
        self.table_id = "tbl_test"

        self.cfg_stub = types.SimpleNamespace(
            feishu_bitable=types.SimpleNamespace(
                enabled=True,
                api_base_url=self.api_base_url,
                app_id=self.app_id,
                app_secret=self.app_secret,
                app_token=self.app_token,
                table_id=self.table_id,
                created_at_format="timestamp_ms",
                fields=types.SimpleNamespace(
                    email="邮箱",
                    password="密码",
                    registered_at="注册时间",
                    plus_redeemed_at="兑换Plus时间",
                    account_type="类型",
                    status="",
                    created_at="",
                ),
            )
        )

    def test_insert_record_fields_and_type_enum(self):
        feishu_bitable = _load_feishu_bitable_with_stub_cfg(self.cfg_stub)
        feishu_bitable._TOKEN_CACHE["tenant_access_token"] = None
        feishu_bitable._TOKEN_CACHE["expires_at"] = 0.0

        token_url = f"{self.api_base_url}/auth/v3/tenant_access_token/internal/"
        insert_url = (
            f"{self.api_base_url}/bitable/v1/apps/{self.app_token}/tables/"
            f"{self.table_id}/records"
        )
        routes = {
            ("POST", token_url): {
                "code": 0,
                "tenant_access_token": "tenant_token_x",
                "expire": 7200,
            },
            ("POST", insert_url): {
                "code": 0,
                "data": {"record": {"record_id": "rec_123"}},
            },
        }
        session = FakeSession(routes=routes)

        with (
            patch.object(feishu_bitable.requests, "Session", return_value=session),
            patch.object(feishu_bitable.time, "time", return_value=1700000000.0),
        ):
            ok, record_id = feishu_bitable.write_account_to_bitable(
                email="a@b.com",
                password="p@ss",
                account_type="claude",
            )

        self.assertTrue(ok)
        self.assertEqual(record_id, "rec_123")

        self.assertEqual(len(session.calls), 2)
        method1, url1, json1, headers1, _ = session.calls[0]
        self.assertEqual(method1, "POST")
        self.assertEqual(url1, token_url)
        self.assertEqual(json1, {"app_id": self.app_id, "app_secret": self.app_secret})
        self.assertIsNone(headers1)

        method2, url2, json2, headers2, _ = session.calls[1]
        self.assertEqual(method2, "POST")
        self.assertEqual(url2, insert_url)
        self.assertEqual(headers2, {"Authorization": "Bearer tenant_token_x"})

        fields = (json2 or {}).get("fields") or {}
        self.assertEqual(fields.get("邮箱"), "a@b.com")
        self.assertEqual(fields.get("密码"), "p@ss")
        self.assertEqual(fields.get("类型"), "Claude")
        self.assertEqual(fields.get("注册时间"), 1700000000000)
        self.assertNotIn("兑换Plus时间", fields)

    def test_update_plus_time_by_record_id(self):
        feishu_bitable = _load_feishu_bitable_with_stub_cfg(self.cfg_stub)
        feishu_bitable._TOKEN_CACHE["tenant_access_token"] = None
        feishu_bitable._TOKEN_CACHE["expires_at"] = 0.0

        token_url = f"{self.api_base_url}/auth/v3/tenant_access_token/internal/"
        update_url = (
            f"{self.api_base_url}/bitable/v1/apps/{self.app_token}/tables/"
            f"{self.table_id}/records/rec_123"
        )
        routes = {
            ("POST", token_url): {
                "code": 0,
                "tenant_access_token": "tenant_token_x",
                "expire": 7200,
            },
            ("PUT", update_url): {"code": 0, "data": {}},
        }
        session = FakeSession(routes=routes)

        with (
            patch.object(feishu_bitable.requests, "Session", return_value=session),
            patch.object(feishu_bitable.time, "time", return_value=1700000000.0),
        ):
            ok = feishu_bitable.update_plus_redeemed_time_in_bitable(
                email="a@b.com",
                record_id="rec_123",
            )

        self.assertTrue(ok)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1][0], "PUT")
        self.assertEqual(session.calls[1][1], update_url)
        self.assertEqual(
            session.calls[1][3],
            {"Authorization": "Bearer tenant_token_x"},
        )
        self.assertEqual(
            session.calls[1][2],
            {"fields": {"兑换Plus时间": 1700000000000}},
        )


if __name__ == "__main__":
    unittest.main()
