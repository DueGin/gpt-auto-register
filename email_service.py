"""
邮箱服务模块
支持三种邮箱方案:
  1. 2925.com 子邮箱方案（推荐）: 主邮箱生成子邮箱，通过 IMAP 读取验证邮件
  2. Cloudflare 临时邮箱方案: 基于 cloudflare_temp_email 项目
  3. Gmail 子邮箱方案: 使用 username+随机后缀@domain 别名，通过 IMAP 读取验证邮件
"""

import random
import string
import time
import email
import threading
from email import policy
from email.header import decode_header
import imaplib
import poplib

from config import (
    EMAIL_PROVIDER,
    EMAIL_2925_ACCOUNTS,
    EMAIL_MASTER_EMAIL,
    EMAIL_MASTER_PASSWORD,
    EMAIL_2925_IMAP_HOST,
    EMAIL_2925_IMAP_PORT,
    GMAIL_ACCOUNTS,
    GMAIL_IMAP_HOST,
    GMAIL_IMAP_PORT,
    EMAIL_WORKER_URL,
    EMAIL_DOMAIN,
    EMAIL_PREFIX_LENGTH,
    EMAIL_WAIT_TIMEOUT,
    EMAIL_POLL_INTERVAL,
    HTTP_TIMEOUT,
    QQ_EMAIL_ENABLED,
    QQ_EMAIL_ADDRESS,
    QQ_EMAIL_AUTH_CODE,
    QQ_EMAIL_PROTOCOL,
    QQ_IMAP_HOST,
    QQ_IMAP_PORT,
    QQ_POP_HOST,
    QQ_POP_PORT,
    QQ_MAILBOX
)
from utils import http_session, get_user_agent, extract_verification_code

# 生成 2925 子邮箱时，随机后缀的最小长度为6位。
SUB_EMAIL_SUFFIX_MIN_LENGTH = 6
SUB_EMAIL_SUFFIX_MAX_LENGTH = 8
# 2925邮箱方案下，等待验证码邮件的最长时间为180秒（3分钟）
MAX_2925_VERIFICATION_WAIT_SECONDS = 80

# Gmail 子邮箱后缀长度
GMAIL_SUB_SUFFIX_MIN_LENGTH = 6
GMAIL_SUB_SUFFIX_MAX_LENGTH = 8
# Gmail 方案下，等待验证码邮件的最长时间
MAX_GMAIL_VERIFICATION_WAIT_SECONDS = 120


# ==============================================================
# 2925 多邮箱轮询管理器
# ==============================================================

class Email2925RoundRobin:
    """
    2925 多邮箱轮询管理器（线程安全）
    按顺序轮流使用配置的多个邮箱账号，避免单个邮箱被频繁使用
    支持多线程并发调用
    """

    def __init__(self):
        self._index = 0
        self._lock = threading.Lock()
        self._accounts = []
        self._init_accounts()

    def _init_accounts(self):
        """初始化邮箱账号列表（优先用 accounts 列表，回退到单邮箱配置）"""
        if EMAIL_2925_ACCOUNTS:
            self._accounts = [
                {"email": acc.email, "password": acc.password}
                for acc in EMAIL_2925_ACCOUNTS
                if acc.email
            ]
        # 回退：使用单邮箱配置
        if not self._accounts and EMAIL_MASTER_EMAIL:
            self._accounts = [
                {"email": EMAIL_MASTER_EMAIL, "password": EMAIL_MASTER_PASSWORD}
            ]

        if self._accounts:
            print(f"📧 2925 邮箱轮询: 已加载 {len(self._accounts)} 个邮箱账号")
        else:
            print("⚠️ 未配置任何 2925 邮箱账号")

    def next_account(self):
        """
        获取下一个邮箱账号（线程安全轮询）

        返回:
            dict: {"email": ..., "password": ...}，无可用账号返回 None
        """
        if not self._accounts:
            return None

        with self._lock:
            account = self._accounts[self._index % len(self._accounts)]
            self._index += 1
            idx = self._index
        return account

    @property
    def total(self):
        return len(self._accounts)


# 全局轮询实例
_round_robin = Email2925RoundRobin()


# ==============================================================
# 2925.com 子邮箱方案
# ==============================================================

def create_2925_sub_email():
    """
    基于 2925.com 邮箱生成子邮箱（支持多邮箱轮询，线程安全）

    原理: 从轮询管理器获取下一个主邮箱，在其用户名后添加随机后缀生成子邮箱
    例如主邮箱 a17351500865@2925.com → 子邮箱 a17351500865abc123@2925.com
    子邮箱收到的邮件会自动进入主邮箱收件箱

    返回:
        tuple: (子邮箱地址, account_dict)，失败返回 (None, None)
        account_dict 包含 {"email": 主邮箱, "password": 密码}，供后续 IMAP 读取使用
    """
    print("📧 正在生成 2925 子邮箱...")

    account = _round_robin.next_account()
    if not account:
        print("❌ 无可用的 2925 邮箱账号")
        return None, None

    master_email = account["email"]
    print(f"  🔄 轮询使用邮箱: {master_email} (第 {_round_robin._index}/{_round_robin.total} 个)")

    if '@' not in master_email:
        print(f"❌ 邮箱格式错误: {master_email}")
        return None, None

    master_username, domain = master_email.split('@', 1)

    # 生成子邮箱：主邮箱名 + 随机字符 + @域名
    # 要求：随机串总长度 6-8 位，且首字符不能是数字
    suffix_length = random.randint(SUB_EMAIL_SUFFIX_MIN_LENGTH, SUB_EMAIL_SUFFIX_MAX_LENGTH)
    first_char = random.choice(string.ascii_lowercase)
    remaining = ''.join(random.choices(
        string.ascii_lowercase + string.digits,
        k=suffix_length - 1
    ))
    suffix = f"{first_char}{remaining}"

    sub_email = f"{master_username}{suffix}@{domain}"
    print(f"✅ 子邮箱生成成功: {sub_email}")

    # 返回 account 信息，供后续 IMAP 读取使用（线程安全，不再用函数属性）
    return sub_email, account


def _fetch_code_via_2925_imap(target_email: str, master_email: str = None, master_password: str = None, max_messages: int = 20):
    """
    通过 IMAP 从 2925 主邮箱读取发给指定子邮箱的 OpenAI 验证码

    注意: 2925 IMAP 服务器不支持 SEARCH 命令，
    需要通过 select 获取邮件总数后直接 FETCH。

    参数:
        target_email: 要匹配的子邮箱地址（收件人）
        master_email: 登录的主邮箱地址（轮询模式下由调用方传入）
        master_password: 登录的主邮箱密码
        max_messages: 最多检查的邮件数

    返回:
        str: 验证码，未找到返回 None
    """
    # 优先使用传入的邮箱，回退到全局配置
    login_email = master_email or EMAIL_MASTER_EMAIL
    login_password = master_password or EMAIL_MASTER_PASSWORD

    if not login_email:
        print("  ❌ 无可用的 IMAP 登录邮箱")
        return None

    client = None
    try:
        client = imaplib.IMAP4_SSL(EMAIL_2925_IMAP_HOST, EMAIL_2925_IMAP_PORT)
        client.login(login_email, login_password)

        # select 返回邮件总数
        status, data = client.select("INBOX")
        if status != 'OK' or not data or not data[0]:
            return None

        total = int(data[0])
        if total == 0:
            return None

        target_lower = target_email.lower()

        # 从最新邮件开始往前检查（直接用序号 FETCH，不用 SEARCH）
        start = max(1, total - max_messages + 1)
        for i in range(total, start - 1, -1):
            try:
                status, msg_data = client.fetch(str(i), "(RFC822)")
                if status != 'OK':
                    continue
            except Exception:
                continue

            for part in msg_data:
                if isinstance(part, tuple):
                    raw_bytes = part[1]
                    parsed = _parse_email_bytes(raw_bytes)
                    subject = parsed['subject']
                    sender = parsed['sender']
                    body = parsed['body']

                    # 获取收件人地址
                    try:
                        msg_obj = email.message_from_bytes(raw_bytes, policy=policy.default)
                        to_header = msg_obj.get('To', '') or ''
                        cc_header = msg_obj.get('Cc', '') or ''
                        delivered_to = msg_obj.get('Delivered-To', '') or ''
                        all_recipients = f"{to_header} {cc_header} {delivered_to}".lower()
                    except Exception:
                        all_recipients = ''

                    # 检查是否是发给目标子邮箱的 OpenAI 邮件
                    sender_lower = sender.lower()
                    subject_lower = subject.lower()
                    is_openai_mail = ('openai' in sender_lower) or ('chatgpt' in subject_lower)
                    is_target = target_lower in all_recipients

                    if is_openai_mail and is_target:
                        # 尝试从主题提取验证码
                        code = extract_verification_code(subject)
                        if code:
                            return code
                        # 尝试从正文提取
                        if body:
                            code = extract_verification_code(body)
                            if code:
                                return code
    except Exception as e:
        print(f"  2925 IMAP 读取错误: {e}")
    finally:
        if client:
            try:
                client.logout()
            except Exception:
                pass
    return None


def wait_for_verification_email_via_2925(target_email: str, timeout: int = None, master_account: dict = None):
    """
    使用 2925 IMAP 轮询等待发给指定子邮箱的验证码

    参数:
        target_email: 子邮箱地址
        timeout: 超时时间（秒）
        master_account: 主邮箱账号信息 {"email": ..., "password": ...}

    返回:
        str: 验证码，未找到返回 None
    """
    if timeout is None:
        timeout = EMAIL_WAIT_TIMEOUT
    timeout = min(timeout, MAX_2925_VERIFICATION_WAIT_SECONDS)

    # 使用传入的主邮箱账号，回退到全局配置
    if master_account:
        master_email = master_account["email"]
        master_password = master_account["password"]
        print(f"⏳ 正在从 2925 邮箱 [{master_email}] 等待验证邮件（目标: {target_email}，最长 {timeout} 秒）...")
    else:
        master_email = None
        master_password = None
        print(f"⏳ 正在从 2925 邮箱等待验证邮件（目标: {target_email}，最长 {timeout} 秒）...")

    start_time = time.time()

    while time.time() - start_time < timeout:
        code = _fetch_code_via_2925_imap(
            target_email,
            master_email=master_email,
            master_password=master_password
        )
        if code:
            print(f"\n📧 从 2925 邮箱获取到验证码: {code}")
            return code

        elapsed = int(time.time() - start_time)
        print(f"  2925 邮箱轮询中... ({elapsed}秒)", end='\r')
        time.sleep(EMAIL_POLL_INTERVAL)

    print("\n⏰ 2925 邮箱未收到验证码")
    return None


# ==============================================================
# Gmail 子邮箱方案
# ==============================================================

class EmailGmailRoundRobin:
    """
    Gmail 多邮箱轮询管理器（线程安全）
    按顺序轮流使用配置的多个 Gmail 账号，避免单个邮箱被频繁使用
    支持多线程并发调用
    """

    def __init__(self):
        self._index = 0
        self._lock = threading.Lock()
        self._accounts = []
        self._init_accounts()

    def _init_accounts(self):
        """初始化 Gmail 邮箱账号列表"""
        if GMAIL_ACCOUNTS:
            self._accounts = [
                {"email": acc.email, "app_password": acc.app_password}
                for acc in GMAIL_ACCOUNTS
                if acc.email
            ]

        if self._accounts:
            print(f"📧 Gmail 邮箱轮询: 已加载 {len(self._accounts)} 个邮箱账号")
        else:
            print("⚠️ 未配置任何 Gmail 邮箱账号")

    def next_account(self):
        """
        获取下一个 Gmail 邮箱账号（线程安全轮询）

        返回:
            dict: {"email": ..., "app_password": ...}，无可用账号返回 None
        """
        if not self._accounts:
            return None

        with self._lock:
            account = self._accounts[self._index % len(self._accounts)]
            self._index += 1
        return account

    @property
    def total(self):
        return len(self._accounts)


# 全局轮询实例
_gmail_round_robin = EmailGmailRoundRobin()


def create_gmail_sub_email():
    """
    基于 Gmail 邮箱生成子邮箱（支持多邮箱轮询，线程安全）

    原理: 使用 username+随机后缀@domain 别名格式
    发往子邮箱的邮件会自动进入主邮箱收件箱

    返回:
        tuple: (子邮箱地址, account_dict)，失败返回 (None, None)
        account_dict 包含 {"email": 主邮箱, "app_password": 密码}，供后续 IMAP 读取使用
    """
    print("📧 正在生成 Gmail 子邮箱...")

    account = _gmail_round_robin.next_account()
    if not account:
        print("❌ 无可用的 Gmail 邮箱账号")
        return None, None

    master_email = account["email"]
    print(f"  🔄 轮询使用 Gmail: {master_email} (第 {_gmail_round_robin._index}/{_gmail_round_robin.total} 个)")

    if '@' not in master_email:
        print(f"❌ 邮箱格式错误: {master_email}")
        return None, None

    username, domain = master_email.split('@', 1)

    # 生成子邮箱：username+随机字符@domain
    suffix_length = random.randint(GMAIL_SUB_SUFFIX_MIN_LENGTH, GMAIL_SUB_SUFFIX_MAX_LENGTH)
    first_char = random.choice(string.ascii_lowercase)
    remaining = ''.join(random.choices(
        string.ascii_lowercase + string.digits,
        k=suffix_length - 1
    ))
    suffix = f"{first_char}{remaining}"

    sub_email = f"{username}+{suffix}@{domain}"
    print(f"✅ Gmail 子邮箱生成成功: {sub_email}")

    # 返回 account 信息，供后续 IMAP 读取使用（线程安全，不再用函数属性）
    return sub_email, account


def _fetch_code_via_gmail_imap(target_email: str, master_email: str = None, app_password: str = None, max_messages: int = 20):
    """
    通过 IMAP 从 Gmail 邮箱读取发给指定子邮箱的 OpenAI 验证码

    Gmail IMAP 支持 SEARCH 命令，比 2925 更高效

    参数:
        target_email: 要匹配的子邮箱地址（收件人）
        master_email: 登录的主邮箱地址（轮询模式下由调用方传入）
        app_password: Google 应用专用密码
        max_messages: 最多检查的邮件数

    返回:
        str: 验证码，未找到返回 None
    """
    if not master_email or not app_password:
        print("  ❌ 无可用的 Gmail IMAP 登录凭据")
        return None

    client = None
    try:
        client = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
        client.login(master_email, app_password)
        client.select("INBOX")

        # Gmail 支持 SEARCH：搜索 FROM 包含 openai 的邮件
        status, data = client.search(None, '(FROM "openai")')
        if status != 'OK' or not data or not data[0]:
            # 回退：搜索所有邮件
            status, data = client.search(None, "ALL")
            if status != 'OK' or not data or not data[0]:
                return None

        ids = data[0].split()
        target_lower = target_email.lower()

        # 从最新邮件开始往前检查
        for msg_id in reversed(ids[-max_messages:]):
            try:
                status, msg_data = client.fetch(msg_id, "(RFC822)")
                if status != 'OK':
                    continue
            except Exception:
                continue

            for part in msg_data:
                if isinstance(part, tuple):
                    raw_bytes = part[1]
                    parsed = _parse_email_bytes(raw_bytes)
                    subject = parsed['subject']
                    sender = parsed['sender']
                    body = parsed['body']

                    # 获取收件人地址
                    try:
                        msg_obj = email.message_from_bytes(raw_bytes, policy=policy.default)
                        to_header = msg_obj.get('To', '') or ''
                        cc_header = msg_obj.get('Cc', '') or ''
                        delivered_to = msg_obj.get('Delivered-To', '') or ''
                        all_recipients = f"{to_header} {cc_header} {delivered_to}".lower()
                    except Exception:
                        all_recipients = ''

                    # 检查是否是发给目标子邮箱的 OpenAI 邮件
                    sender_lower = sender.lower()
                    subject_lower = subject.lower()
                    is_openai_mail = ('openai' in sender_lower) or ('chatgpt' in subject_lower)
                    is_target = target_lower in all_recipients

                    if is_openai_mail and is_target:
                        # 尝试从主题提取验证码
                        code = extract_verification_code(subject)
                        if code:
                            return code
                        # 尝试从正文提取
                        if body:
                            code = extract_verification_code(body)
                            if code:
                                return code
    except Exception as e:
        print(f"  Gmail IMAP 读取错误: {e}")
    finally:
        if client:
            try:
                client.logout()
            except Exception:
                pass
    return None


def wait_for_verification_email_via_gmail(target_email: str, timeout: int = None, master_account: dict = None):
    """
    使用 Gmail IMAP 轮询等待发给指定子邮箱的验证码

    参数:
        target_email: 子邮箱地址
        timeout: 超时时间（秒）
        master_account: 主邮箱账号信息 {"email": ..., "app_password": ...}

    返回:
        str: 验证码，未找到返回 None
    """
    if timeout is None:
        timeout = EMAIL_WAIT_TIMEOUT
    timeout = min(timeout, MAX_GMAIL_VERIFICATION_WAIT_SECONDS)

    # 使用传入的主邮箱账号
    if master_account:
        master_email = master_account["email"]
        app_password = master_account["app_password"]
        print(f"⏳ 正在从 Gmail [{master_email}] 等待验证邮件（目标: {target_email}，最长 {timeout} 秒）...")
    else:
        print("❌ Gmail 方案需要提供 master_account")
        return None

    start_time = time.time()

    while time.time() - start_time < timeout:
        code = _fetch_code_via_gmail_imap(
            target_email,
            master_email=master_email,
            app_password=app_password
        )
        if code:
            print(f"\n📧 从 Gmail 获取到验证码: {code}")
            return code

        elapsed = int(time.time() - start_time)
        print(f"  Gmail 邮箱轮询中... ({elapsed}秒)", end='\r')
        time.sleep(EMAIL_POLL_INTERVAL)

    print("\n⏰ Gmail 邮箱未收到验证码")
    return None


# ==============================================================
# Cloudflare 临时邮箱方案（旧方案）
# ==============================================================

def create_temp_email():
    """
    创建临时邮箱（根据 provider 配置选择方案）

    返回:
        tuple: (邮箱地址, JWT令牌或None)，失败返回 (None, None)
    """
    # 如果是 2925 方案，使用子邮箱生成
    if EMAIL_PROVIDER == "2925":
        return create_2925_sub_email()

    # Gmail 方案
    if EMAIL_PROVIDER == "gmail":
        return create_gmail_sub_email()

    # 以下为 Cloudflare 方案
    print("📧 正在创建临时邮箱...")

    # 生成随机邮箱前缀（服务器会自动添加 tmp 前缀）
    prefix = ''.join(random.choices(
        string.ascii_lowercase + string.digits,
        k=EMAIL_PREFIX_LENGTH
    ))

    # 当未配置 Worker 时，直接使用自有域名生成邮箱地址（依赖域名的 catch-all/转发）
    worker_url = (EMAIL_WORKER_URL or "").strip()
    if (not worker_url) or ("your-worker-name" in worker_url) or ("your-subdomain" in worker_url):
        fallback_email = f"{prefix}@{EMAIL_DOMAIN}"
        print(f"✅ 未配置 Worker，使用本地域名生成邮箱: {fallback_email}")
        return fallback_email, None

    headers = {
        "Content-Type": "application/json",
        "User-Agent": get_user_agent()
    }

    try:
        # 调用创建邮箱接口
        response = http_session.post(
            f"{EMAIL_WORKER_URL}/api/new_address",
            headers=headers,
            json={"name": prefix},
            timeout=HTTP_TIMEOUT
        )

        if response.status_code == 200:
            result = response.json()
            jwt_token = result.get('jwt')
            # 使用服务器返回的实际邮箱地址（包含 tmp 前缀）
            actual_email = result.get('address')

            if jwt_token and actual_email:
                print(f"✅ 邮箱创建成功: {actual_email}")
                return actual_email, jwt_token
            elif jwt_token:
                # 兼容：如果服务器没有返回 address，则自己拼接
                fallback_email = f"tmp{prefix}@{EMAIL_DOMAIN}"
                print(f"✅ 邮箱创建成功: {fallback_email}")
                return fallback_email, jwt_token
            else:
                print(f"⚠️ 响应中未包含 JWT: {result}")
        else:
            print(f"❌ API 错误: HTTP {response.status_code}")
            print(f"   响应内容: {response.text[:200]}")

    except Exception as e:
        print(f"❌ 创建邮箱失败: {e}")

    return None, None


def fetch_emails(jwt_token: str):
    """
    获取邮件列表（Cloudflare 方案）

    参数:
        jwt_token: 创建邮箱时获得的 JWT 令牌

    返回:
        list: 邮件列表，失败返回 None
    """
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "User-Agent": get_user_agent()
    }

    try:
        # API 需要 limit 和 offset 参数
        response = http_session.get(
            f"{EMAIL_WORKER_URL}/api/mails?limit=20&offset=0",
            headers=headers,
            timeout=HTTP_TIMEOUT
        )

        if response.status_code == 200:
            result = response.json()

            # 处理不同的返回格式
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return result.get('results', result.get('mails', []))
        else:
            print(f"  获取邮件错误: HTTP {response.status_code}")

    except Exception as e:
        print(f"  获取邮件错误: {e}")

    return None


def get_email_detail(jwt_token: str, email_id: str):
    """
    获取邮件详情（Cloudflare 方案）

    参数:
        jwt_token: JWT 令牌
        email_id: 邮件 ID

    返回:
        dict: 邮件详情，失败返回 None
    """
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "User-Agent": get_user_agent()
    }

    try:
        response = http_session.get(
            f"{EMAIL_WORKER_URL}/api/mails/{email_id}",
            headers=headers,
            timeout=HTTP_TIMEOUT
        )

        if response.status_code == 200:
            return response.json()

    except Exception as e:
        print(f"  获取邮件详情错误: {e}")

    return None


# ==============================================================
# 邮件解析工具函数
# ==============================================================

def parse_raw_email(raw_content: str):
    """
    解析原始邮件内容

    参数:
        raw_content: 原始邮件字符串

    返回:
        dict: 包含 subject, body, sender 的字典
    """
    result = {'subject': '', 'body': '', 'sender': ''}

    if not raw_content:
        return result

    try:
        msg = email.message_from_string(raw_content, policy=policy.default)

        result['subject'] = msg.get('Subject', '')
        result['sender'] = msg.get('From', '')

        # 获取正文
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ['text/plain', 'text/html']:
                    payload = part.get_payload(decode=True)
                    if payload:
                        result['body'] = payload.decode('utf-8', errors='ignore')
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                result['body'] = payload.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  解析邮件错误: {e}")

    return result


def _decode_mime_header(value: str) -> str:
    """解码 MIME 编码的邮件头"""
    if not value:
        return ""

    decoded_parts = []
    for part, encoding in decode_header(value):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(encoding or "utf-8", errors="ignore"))
            except Exception:
                decoded_parts.append(part.decode("utf-8", errors="ignore"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


def _parse_email_bytes(raw_bytes: bytes):
    """
    从原始字节解析邮件（IMAP/POP 使用）

    返回:
        dict: 包含 subject, body, sender 的字典
    """
    if not raw_bytes:
        return {'subject': '', 'body': '', 'sender': ''}

    try:
        msg = email.message_from_bytes(raw_bytes, policy=policy.default)

        subject = _decode_mime_header(msg.get('Subject', ''))
        sender = _decode_mime_header(msg.get('From', ''))
        body = ''

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ['text/plain', 'text/html']:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        try:
                            body = payload.decode(charset, errors='ignore')
                        except Exception:
                            body = payload.decode('utf-8', errors='ignore')
                        if body:
                            break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                try:
                    body = payload.decode(charset, errors='ignore')
                except Exception:
                    body = payload.decode('utf-8', errors='ignore')

        return {'subject': subject, 'body': body, 'sender': sender}
    except Exception as e:
        print(f"  解析邮件错误: {e}")
        return {'subject': '', 'body': '', 'sender': ''}


def _extract_code_from_raw_email(raw_bytes: bytes, target_email: str = None):
    """从原始邮件字节中提取验证码（针对 QQ 邮箱读取）

    参数:
        raw_bytes: 原始邮件字节
        target_email: 可选，目标收件人邮箱地址。如果提供，只匹配发给该地址的邮件
    """
    parsed = _parse_email_bytes(raw_bytes)
    subject = parsed['subject']
    sender = parsed['sender']
    body = parsed['body']

    subject_lower = subject.lower()
    sender_lower = sender.lower()
    is_openai_mail = ('openai' in sender_lower) or ('chatgpt' in subject_lower)
    if not is_openai_mail:
        return None

    # 如果提供了 target_email，检查收件人是否匹配
    if target_email:
        try:
            msg_obj = email.message_from_bytes(raw_bytes, policy=policy.default)
            to_header = msg_obj.get('To', '') or ''
            cc_header = msg_obj.get('Cc', '') or ''
            delivered_to = msg_obj.get('Delivered-To', '') or ''
            # Cloudflare 转发时可能在 X-Forwarded-To 或 X-Original-To 中保留原始收件人
            x_forwarded_to = msg_obj.get('X-Forwarded-To', '') or ''
            x_original_to = msg_obj.get('X-Original-To', '') or ''
            all_recipients = f"{to_header} {cc_header} {delivered_to} {x_forwarded_to} {x_original_to}".lower()

            target_lower = target_email.lower()
            if target_lower not in all_recipients:
                return None
        except Exception:
            # 解析失败时不过滤，尝试提取验证码
            pass

    code = extract_verification_code(subject)
    if code:
        return code

    if body:
        return extract_verification_code(body)

    return None


# ==============================================================
# QQ 邮箱方案（旧方案，仅 Cloudflare 模式下使用）
# ==============================================================

def _fetch_code_via_imap(target_email: str = None, max_messages: int = 15):
    """通过 IMAP 轮询 QQ 邮箱

    参数:
        target_email: 目标收件人邮箱地址，用于匹配转发邮件的原始收件人
        max_messages: 最多检查的邮件数
    """
    client = None
    try:
        client = imaplib.IMAP4_SSL(QQ_IMAP_HOST, QQ_IMAP_PORT)
        client.login(QQ_EMAIL_ADDRESS, QQ_EMAIL_AUTH_CODE)
        client.select(QQ_MAILBOX)

        status, data = client.search(None, "ALL")
        if status != 'OK' or not data or not data[0]:
            return None

        ids = data[0].split()
        for msg_id in reversed(ids[-max_messages:]):
            status, msg_data = client.fetch(msg_id, "(RFC822)")
            if status != 'OK':
                continue
            for part in msg_data:
                if isinstance(part, tuple):
                    code = _extract_code_from_raw_email(part[1], target_email=target_email)
                    if code:
                        return code
    except Exception as e:
        print(f"  QQ IMAP 读取错误: {e}")
    finally:
        if client:
            try:
                client.logout()
            except Exception:
                pass
    return None


def _fetch_code_via_pop(target_email: str = None, max_messages: int = 10):
    """通过 POP 轮询 QQ 邮箱

    参数:
        target_email: 目标收件人邮箱地址，用于匹配转发邮件的原始收件人
        max_messages: 最多检查的邮件数
    """
    client = None
    try:
        client = poplib.POP3_SSL(QQ_POP_HOST, QQ_POP_PORT, timeout=HTTP_TIMEOUT)
        client.user(QQ_EMAIL_ADDRESS)
        client.pass_(QQ_EMAIL_AUTH_CODE)

        total_messages = len(client.list()[1])
        if total_messages == 0:
            return None

        start = max(1, total_messages - max_messages + 1)
        for i in range(total_messages, start - 1, -1):
            _, lines, _ = client.retr(i)
            raw_email = b"\r\n".join(lines)
            code = _extract_code_from_raw_email(raw_email, target_email=target_email)
            if code:
                return code
    except Exception as e:
        print(f"  QQ POP 读取错误: {e}")
    finally:
        if client:
            try:
                client.quit()
            except Exception:
                pass
    return None


def wait_for_verification_email_via_qq(timeout: int = None, target_email: str = None):
    """
    使用 QQ 邮箱轮询验证码（适用于 Cloudflare 路由到 QQ 的场景）

    参数:
        timeout: 超时时间（秒）
        target_email: 目标收件人邮箱地址，用于匹配转发邮件的原始收件人

    返回:
        str: 验证码，未找到返回 None
    """
    if timeout is None:
        timeout = EMAIL_WAIT_TIMEOUT

    if target_email:
        print(f"⏳ 正在从 QQ 邮箱等待验证邮件（目标: {target_email}，最长 {timeout} 秒）...")
    else:
        print(f"⏳ 正在从 QQ 邮箱等待验证邮件（最长 {timeout} 秒）...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        if QQ_EMAIL_PROTOCOL.startswith('pop'):
            code = _fetch_code_via_pop(target_email=target_email)
        else:
            code = _fetch_code_via_imap(target_email=target_email)

        if code:
            return code

        elapsed = int(time.time() - start_time)
        print(f"  QQ 邮箱轮询中... ({elapsed}秒)", end='\r')
        time.sleep(EMAIL_POLL_INTERVAL)

    print("\n⏰ QQ 邮箱未收到验证码")
    return None


# ==============================================================
# 统一入口
# ==============================================================

def wait_for_verification_email(jwt_token=None, timeout: int = None, target_email: str = None, master_account: dict = None):
    """
    等待并提取 OpenAI 验证码（统一入口）
    根据 provider 配置自动选择方案

    参数:
        jwt_token: JWT 令牌（Cloudflare 方案使用）/ 2925 方案下为 account dict
        timeout: 超时时间（秒），默认使用配置文件中的值
        target_email: 目标子邮箱地址（2925 方案使用，用于匹配收件人）
        master_account: 2925 主邮箱账号信息（并发安全，优先级最高）

    返回:
        str: 验证码，未找到返回 None
    """
    if timeout is None:
        timeout = EMAIL_WAIT_TIMEOUT

    # 2925 方案：直接通过 IMAP 从主邮箱读取
    if EMAIL_PROVIDER == "2925":
        if not target_email:
            print("⚠️ 2925 方案需要提供 target_email 参数")
            return None
        # master_account 可以从参数传入，也可以从 jwt_token 传入（兼容旧调用方式）
        account = master_account
        if not account and isinstance(jwt_token, dict):
            account = jwt_token
        return wait_for_verification_email_via_2925(target_email, timeout, master_account=account)

    # Gmail 方案：通过 IMAP 从 Gmail 读取
    if EMAIL_PROVIDER == "gmail":
        if not target_email:
            print("⚠️ Gmail 方案需要提供 target_email 参数")
            return None
        account = master_account
        if not account and isinstance(jwt_token, dict):
            account = jwt_token
        return wait_for_verification_email_via_gmail(target_email, timeout, master_account=account)

    # Cloudflare 方案：优先使用 QQ 邮箱轮询
    if QQ_EMAIL_ENABLED and QQ_EMAIL_ADDRESS and QQ_EMAIL_AUTH_CODE:
        code = wait_for_verification_email_via_qq(timeout, target_email=target_email)
        if code or not jwt_token:
            return code
        print("⚠️ QQ 邮箱未获取到验证码，尝试使用 Cloudflare 临时邮箱...")

    if not jwt_token:
        print("⚠️ 未提供 JWT 令牌，无法调用 Cloudflare 临时邮箱接口")
        return None

    print(f"⏳ 正在等待验证邮件（最长 {timeout} 秒）...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        emails = fetch_emails(jwt_token)

        if emails and len(emails) > 0:
            for email_item in emails:
                # 尝试解析 raw 字段（如果存在）
                raw_content = email_item.get('raw', '')
                if raw_content:
                    parsed = parse_raw_email(raw_content)
                    subject = parsed['subject']
                    sender = parsed['sender'].lower()
                    body = parsed['body']
                else:
                    # 回退到旧的字段
                    sender = str(email_item.get('from') or email_item.get('source', '')).lower()
                    subject = email_item.get('subject', '') or ''
                    body = ''

                # 判断是否为 OpenAI 验证邮件
                if 'openai' in sender or 'chatgpt' in subject.lower():
                    print(f"\n📧 收到 OpenAI 验证邮件!")
                    print(f"   主题: {subject}")

                    # 先尝试从主题提取验证码
                    code = extract_verification_code(subject)
                    if code:
                        return code

                    # 如果主题中没有，从正文提取
                    if body:
                        code = extract_verification_code(body)
                        if code:
                            return code

                    # 如果还没有，尝试获取邮件详情
                    email_id = email_item.get('id')
                    if email_id:
                        detail = get_email_detail(jwt_token, email_id)
                        if detail:
                            # 解析详情中的 raw
                            detail_raw = detail.get('raw', '')
                            if detail_raw:
                                parsed_detail = parse_raw_email(detail_raw)
                                code = extract_verification_code(parsed_detail['subject'])
                                if code:
                                    return code
                                code = extract_verification_code(parsed_detail['body'])
                                if code:
                                    return code

                            # 尝试其他字段
                            content = (
                                detail.get('html') or
                                detail.get('html_content') or
                                detail.get('text') or
                                detail.get('content', '')
                            )
                            if content:
                                code = extract_verification_code(content)
                                if code:
                                    return code

        # 显示等待进度
        elapsed = int(time.time() - start_time)
        print(f"  等待中... ({elapsed}秒)", end='\r')
        time.sleep(EMAIL_POLL_INTERVAL)

    print("\n⏰ 等待验证邮件超时")
    return None
