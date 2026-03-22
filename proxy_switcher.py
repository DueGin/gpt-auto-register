"""
Clash 代理节点切换模块

通过 Clash (mihomo) RESTful API 自动切换代理节点。
支持三种策略: random(随机) / round_robin(轮询) / low_latency(延迟最低)
支持地理位置白名单过滤。

独立运行:
    python proxy_switcher.py --list          # 列出可用节点
    python proxy_switcher.py --current       # 查看当前节点
    python proxy_switcher.py --rotate        # 切换到下一个节点
    python proxy_switcher.py --switch "节点名" # 切换到指定节点
    python proxy_switcher.py --test-all      # 测试所有节点延迟
"""

import random
import threading
import urllib.parse
from typing import Optional, List, Dict, Callable

import requests


# Clash 内置节点/策略名，不应被当作可用代理
_BUILTIN_NAMES = {
    "DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE",
    "GLOBAL", "direct", "reject",
}


class ProxySwitcher:
    """Clash 代理节点切换器"""

    def __init__(self, config, print_func: Callable = None):
        """
        初始化切换器

        参数:
            config: ProxyConfig dataclass 或任何拥有以下属性的对象:
                clash_api_url, clash_secret, proxy_group,
                strategy, region_whitelist,
                latency_test_url, latency_test_timeout
            print_func: 自定义打印函数（用于 server.py 日志劫持），默认为内置 print
        """
        self._print = print_func or print

        self._api_url = (config.clash_api_url or "http://127.0.0.1:9097").rstrip("/")
        self._secret = config.clash_secret or ""
        self._group = config.proxy_group or "GLOBAL"
        self._strategy = (config.strategy or "random").lower()
        self._whitelist: List[str] = list(config.region_whitelist or [])
        self._latency_url = config.latency_test_url or "https://www.gstatic.com/generate_204"
        self._latency_timeout = config.latency_test_timeout or 5000

        self._index = 0
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers.update(self._headers())

    def _headers(self) -> dict:
        """构造 Clash API 认证头"""
        h = {"Content-Type": "application/json"}
        if self._secret:
            h["Authorization"] = f"Bearer {self._secret}"
        return h

    def _get(self, path: str, params: dict = None, timeout: int = 10) -> Optional[dict]:
        """GET 请求 Clash API"""
        url = f"{self._api_url}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self._print(f"⚠️ Clash API GET {path} 失败: {e}")
            return None

    def _put(self, path: str, json_data: dict, timeout: int = 10) -> bool:
        """PUT 请求 Clash API"""
        url = f"{self._api_url}{path}"
        try:
            resp = self._session.put(url, json=json_data, timeout=timeout)
            resp.raise_for_status()
            return True
        except Exception as e:
            self._print(f"⚠️ Clash API PUT {path} 失败: {e}")
            return False

    # ========== 查询接口 ==========

    def get_proxy_group(self) -> Optional[dict]:
        """
        获取指定代理组的信息

        返回:
            dict: {"all": ["节点1", ...], "now": "当前节点", "type": "Selector", ...}
            None: 请求失败
        """
        encoded_group = urllib.parse.quote(self._group, safe="")
        return self._get(f"/proxies/{encoded_group}")

    def get_all_groups(self) -> List[str]:
        """获取所有 Selector 类型的代理组名"""
        data = self._get("/proxies")
        if not data:
            return []
        proxies = data.get("proxies", {})
        groups = []
        for name, info in proxies.items():
            if isinstance(info, dict) and info.get("type") == "Selector":
                groups.append(name)
        return sorted(groups)

    def get_current(self) -> Optional[str]:
        """获取当前选中的节点名"""
        group = self.get_proxy_group()
        if group:
            return group.get("now")
        return None

    def _matches_whitelist(self, proxy_name: str) -> bool:
        """检查节点名是否匹配地理位置白名单"""
        if not self._whitelist:
            return True  # 无白名单则全部可用
        name_lower = proxy_name.lower()
        return any(kw.lower() in name_lower for kw in self._whitelist)

    def _is_usable_proxy(self, name: str) -> bool:
        """判断是否为可用的实际代理节点（排除内置和策略组）"""
        if name in _BUILTIN_NAMES:
            return False
        return True

    def get_available_proxies(self) -> List[str]:
        """
        获取当前代理组中符合白名单条件的可用节点列表

        返回:
            list[str]: 可用节点名列表
        """
        group = self.get_proxy_group()
        if not group:
            return []

        all_proxies = group.get("all", [])
        # 获取组内子代理组名（需排除）
        all_data = self._get("/proxies")
        sub_groups = set()
        if all_data:
            proxies_map = all_data.get("proxies", {})
            for name, info in proxies_map.items():
                if isinstance(info, dict) and info.get("type") in (
                    "Selector", "URLTest", "Fallback", "LoadBalance", "Relay"
                ):
                    sub_groups.add(name)

        available = []
        for name in all_proxies:
            if name in _BUILTIN_NAMES:
                continue
            if name in sub_groups:
                continue
            if not self._matches_whitelist(name):
                continue
            available.append(name)

        return available

    # ========== 延迟测试 ==========

    def test_delay(self, proxy_name: str) -> Optional[int]:
        """
        测试指定节点的延迟

        参数:
            proxy_name: 节点名

        返回:
            int: 延迟毫秒数
            None: 超时或失败
        """
        encoded_name = urllib.parse.quote(proxy_name, safe="")
        data = self._get(
            f"/proxies/{encoded_name}/delay",
            params={"timeout": self._latency_timeout, "url": self._latency_url},
            timeout=max(10, self._latency_timeout // 1000 + 5),
        )
        if data and "delay" in data:
            return data["delay"]
        return None

    def test_all_delays(self) -> Dict[str, Optional[int]]:
        """
        测试所有可用节点的延迟

        返回:
            dict: {节点名: 延迟ms 或 None}
        """
        available = self.get_available_proxies()
        results = {}
        for name in available:
            delay = self.test_delay(name)
            results[name] = delay
        return results

    # ========== 切换接口 ==========

    def switch_to(self, proxy_name: str) -> bool:
        """
        切换到指定节点

        参数:
            proxy_name: 目标节点名

        返回:
            bool: 是否成功
        """
        encoded_group = urllib.parse.quote(self._group, safe="")
        return self._put(f"/proxies/{encoded_group}", {"name": proxy_name})

    def select_next(self) -> Optional[str]:
        """
        根据策略选择下一个节点（不执行切换）

        返回:
            str: 选中的节点名
            None: 无可用节点
        """
        available = self.get_available_proxies()
        if not available:
            self._print("⚠️ 无可用代理节点（检查白名单配置和 Clash 节点列表）")
            return None

        current = self.get_current()

        with self._lock:
            if self._strategy == "round_robin":
                selected = available[self._index % len(available)]
                self._index += 1
                # 如果选到当前节点且有其他可选，再跳一个
                if selected == current and len(available) > 1:
                    selected = available[self._index % len(available)]
                    self._index += 1

            elif self._strategy == "low_latency":
                self._print("⏱️ 正在测试节点延迟...")
                delays = {}
                for name in available:
                    d = self.test_delay(name)
                    if d is not None:
                        delays[name] = d
                        self._print(f"   {name}: {d}ms")
                    else:
                        self._print(f"   {name}: 超时")
                if not delays:
                    self._print("⚠️ 所有节点延迟测试均超时，随机选择")
                    selected = random.choice(available)
                else:
                    selected = min(delays, key=delays.get)
                    self._print(f"   最低延迟: {selected} ({delays[selected]}ms)")

            else:  # random (默认)
                # 尽量避免选到当前节点
                candidates = [n for n in available if n != current]
                if not candidates:
                    candidates = available
                selected = random.choice(candidates)

        return selected

    def check_ip_location(self) -> Optional[str]:
        """
        通过公网 API 检测当前代理出口的 IP 和地区

        返回:
            str: 格式如 "1.2.3.4 (Japan, Tokyo)"，失败返回 None
        """
        # 按优先级尝试多个 IP 查询服务
        apis = [
            {
                "url": "http://ip-api.com/json/?lang=zh-CN",
                "parse": lambda r: f"{r.get('query', '?')} ({r.get('country', '?')}, {r.get('city', '?')})",
            },
            {
                "url": "https://ipinfo.io/json",
                "parse": lambda r: f"{r.get('ip', '?')} ({r.get('country', '?')}, {r.get('city', '?')})",
            },
            {
                "url": "https://ipapi.co/json/",
                "parse": lambda r: f"{r.get('ip', '?')} ({r.get('country_name', '?')}, {r.get('city', '?')})",
            },
        ]
        for api in apis:
            try:
                resp = requests.get(api["url"], timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    return api["parse"](data)
            except Exception:
                continue
        return None

    def rotate(self) -> Optional[str]:
        """
        选择下一个节点并执行切换（对外主入口）

        返回:
            str: 新节点名
            None: 切换失败
        """
        old_node = self.get_current()
        selected = self.select_next()
        if not selected:
            return None

        self._print(f"🔄 切换代理: [{old_node}] → [{selected}]")
        if self.switch_to(selected):
            # 切换后再确认一次实际生效的节点
            actual = self.get_current()
            if actual == selected:
                self._print(f"✅ 代理切换成功: [{selected}]")
            elif actual:
                self._print(f"⚠️ 切换后实际节点: [{actual}]（与预期 [{selected}] 不一致！）")
            # 检测实际出口 IP 和地区
            location = self.check_ip_location()
            if location:
                self._print(f"🌍 当前出口 IP: {location}")
            else:
                self._print(f"⚠️ 无法检测出口 IP（IP 查询服务不可用）")
            return selected
        else:
            self._print(f"❌ 代理切换失败: [{old_node}] → [{selected}]")
        return None

    def print_available_proxies(self):
        """打印可用代理节点列表（启动时调用）"""
        available = self.get_available_proxies()
        current = self.get_current()
        self._print(f"📋 代理组: {self._group} | 策略: {self._strategy} | "
                    f"白名单: {self._whitelist or '(无)'}")
        self._print(f"   可用节点 ({len(available)}):")
        for i, name in enumerate(available, 1):
            marker = " ← 当前" if name == current else ""
            self._print(f"     {i}. {name}{marker}")
        if not available:
            self._print("   ⚠️ 无可用节点！请检查白名单配置和 Clash 节点列表")

    def close(self):
        """关闭 HTTP 会话"""
        try:
            self._session.close()
        except Exception:
            pass


# ==============================================================
# 独立运行支持
# ==============================================================

def _create_switcher_from_config():
    """从 config.yaml 创建 ProxySwitcher 实例"""
    from config import cfg
    if not cfg.proxy.enabled:
        print("⚠️ 代理轮换未启用 (proxy.enabled = false)")
        print("   提示: 在 config.yaml 中设置 proxy.enabled: true")
    return ProxySwitcher(cfg.proxy)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clash 代理节点切换工具")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="列出可用节点（已按白名单过滤）")
    group.add_argument("--groups", action="store_true", help="列出所有 Selector 代理组")
    group.add_argument("--current", action="store_true", help="查看当前节点")
    group.add_argument("--rotate", action="store_true", help="切换到下一个节点")
    group.add_argument("--switch", type=str, metavar="NODE", help="切换到指定节点")
    group.add_argument("--test-all", action="store_true", help="测试所有节点延迟")
    args = parser.parse_args()

    switcher = _create_switcher_from_config()

    if args.list:
        switcher.print_available_proxies()

    elif args.groups:
        groups = switcher.get_all_groups()
        print(f"\n📋 Selector 代理组 ({len(groups)}):\n")
        for g in groups:
            print(f"   • {g}")

    elif args.current:
        current = switcher.get_current()
        if current:
            print(f"🔵 当前节点: {current}")
        else:
            print("❌ 无法获取当前节点")

    elif args.rotate:
        print(f"🔄 策略: {switcher._strategy}")
        result = switcher.rotate()
        if not result:
            print("❌ 切换失败")

    elif args.switch:
        switcher.switch_to(args.switch)

    elif args.test_all:
        print(f"\n⏱️ 测试延迟 (超时: {switcher._latency_timeout}ms)...\n")
        delays = switcher.test_all_delays()
        if delays:
            sorted_delays = sorted(delays.items(), key=lambda x: x[1] if x[1] is not None else 99999)
            for name, d in sorted_delays:
                if d is not None:
                    print(f"   {d:>5}ms  {name}")
                else:
                    print(f"   超时     {name}")
        else:
            print("❌ 无可用节点")

    switcher.close()


if __name__ == "__main__":
    main()
