"""
配置加载模块
从 config.yaml 文件加载配置，支持动态更新

使用方法:
    from config import cfg
    
    # 访问配置项
    total = cfg.registration.total_accounts
    email_domain = cfg.email.domain
    
    # 或者直接导入常量（兼容旧代码）
    from config import TOTAL_ACCOUNTS, EMAIL_DOMAIN
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

# 尝试导入 yaml，如果未安装则提示
try:
    import yaml
except ImportError:
    print("❌ 缺少 PyYAML 依赖，请先安装:")
    print("   pip install pyyaml")
    sys.exit(1)


# ==============================================================
# 配置数据类定义
# ==============================================================

@dataclass
class RegistrationConfig:
    """注册配置"""
    total_accounts: int = 1
    min_age: int = 20
    max_age: int = 40


@dataclass
class EmailConfig:
    """邮箱服务配置"""
    worker_url: str = ""
    domain: str = ""
    prefix_length: int = 10
    wait_timeout: int = 120
    poll_interval: int = 3
    admin_password: str = ""


@dataclass
class QQEmailConfig:
    """QQ 邮箱读取配置"""
    enabled: bool = False
    address: str = ""
    auth_code: str = ""
    protocol: str = "imap"   # imap 或 pop
    imap_host: str = "imap.qq.com"
    imap_port: int = 993
    pop_host: str = "pop.qq.com"
    pop_port: int = 995
    mailbox: str = "INBOX"


@dataclass
class BrowserConfig:
    """浏览器配置"""
    max_wait_time: int = 600
    short_wait_time: int = 120
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


@dataclass
class PasswordConfig:
    """密码配置"""
    length: int = 16
    charset: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%"


@dataclass
class RetryConfig:
    """重试配置"""
    http_max_retries: int = 5
    http_timeout: int = 30
    error_page_max_retries: int = 5
    button_click_max_retries: int = 3


@dataclass
class BatchConfig:
    """批量注册配置"""
    interval_min: int = 5
    interval_max: int = 15


@dataclass
class FilesConfig:
    """文件路径配置"""
    accounts_file: str = "registered_accounts.txt"


@dataclass
class CreditCardConfig:
    """信用卡配置"""
    number: str = ""
    expiry: str = ""
    expiry_month: str = ""
    expiry_year: str = ""
    cvc: str = ""


@dataclass
class BillingInfoConfig:
    """账单地址配置"""
    use_static: bool = False
    name: str = ""
    country: str = ""
    state: str = ""
    city: str = ""
    address1: str = ""
    address2: str = ""
    zip: str = ""
    address_source: str = "local"  # "local" 或 "meiguodizhi"


@dataclass
class PaymentConfig:
    """支付配置"""
    credit_card: CreditCardConfig = field(default_factory=CreditCardConfig)
    billing: BillingInfoConfig = field(default_factory=BillingInfoConfig)


@dataclass
class FeishuBitableFieldsConfig:
    """飞书多维表格字段映射（字段名需与表格中一致）"""
    email: str = "邮箱"
    password: str = "密码"
    registered_at: str = "注册时间"
    plus_redeemed_at: str = "兑换Plus时间"
    account_type: str = "类型"
    # 兼容旧字段（可留空）
    status: str = ""
    created_at: str = ""


@dataclass
class FeishuBitableConfig:
    """飞书多维表格配置"""
    enabled: bool = False
    api_base_url: str = "https://open.feishu.cn/open-apis"
    app_id: str = ""
    app_secret: str = ""
    app_token: str = ""
    table_id: str = ""
    created_at_format: str = "datetime_str"  # datetime_str 或 timestamp_ms
    fields: FeishuBitableFieldsConfig = field(default_factory=FeishuBitableFieldsConfig)


@dataclass
class AppConfig:
    """应用程序完整配置"""
    registration: RegistrationConfig = field(default_factory=RegistrationConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    qq_email: QQEmailConfig = field(default_factory=QQEmailConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    password: PasswordConfig = field(default_factory=PasswordConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)
    files: FilesConfig = field(default_factory=FilesConfig)
    payment: PaymentConfig = field(default_factory=PaymentConfig)
    feishu_bitable: FeishuBitableConfig = field(default_factory=FeishuBitableConfig)


# ==============================================================
# 配置加载器
# ==============================================================

class ConfigLoader:
    """
    配置加载器
    支持从 YAML 文件加载配置，并合并默认值
    """
    
    # 配置文件搜索路径（按优先级排序）
    CONFIG_FILES = [
        "config.yaml",
        "config.yml",
        "config.local.yaml",
        "config.local.yml",
    ]
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器
        
        参数:
            config_path: 指定配置文件路径，如果为 None 则自动搜索
        """
        self.config_path = config_path
        self.raw_config: Dict[str, Any] = {}
        self.config = AppConfig()
        
        self._load_config()
    
    def _find_config_file(self) -> Optional[Path]:
        """查找配置文件"""
        # 获取脚本所在目录
        base_dir = Path(__file__).parent
        
        for filename in self.CONFIG_FILES:
            config_file = base_dir / filename
            if config_file.exists():
                return config_file
        
        return None
    
    def _load_config(self) -> None:
        """加载配置文件"""
        if self.config_path:
            config_file = Path(self.config_path)
        else:
            config_file = self._find_config_file()
        
        if config_file is None or not config_file.exists():
            print("⚠️ 未找到配置文件 config.yaml")
            print("   请复制 config.example.yaml 为 config.yaml 并修改配置")
            print("   使用默认配置继续运行...")
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.raw_config = yaml.safe_load(f) or {}
            
            self.config_path = str(config_file)
            print(f"📄 已加载配置文件: {config_file.name}")
            
            # 解析配置到数据类
            self._parse_config()
            
        except yaml.YAMLError as e:
            print(f"❌ 配置文件格式错误: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 加载配置文件失败: {e}")
            sys.exit(1)
    
    def _parse_config(self) -> None:
        """解析原始配置到数据类"""
        # 注册配置
        if 'registration' in self.raw_config:
            reg = self.raw_config['registration']
            self.config.registration = RegistrationConfig(
                total_accounts=reg.get('total_accounts', 1),
                min_age=reg.get('min_age', 20),
                max_age=reg.get('max_age', 40)
            )
        
        # 邮箱配置
        if 'email' in self.raw_config:
            email = self.raw_config['email']
            self.config.email = EmailConfig(
                worker_url=email.get('worker_url', ''),
                domain=email.get('domain', ''),
                prefix_length=email.get('prefix_length', 10),
                wait_timeout=email.get('wait_timeout', 120),
                poll_interval=email.get('poll_interval', 3),
                admin_password=email.get('admin_password', '')
            )

        # QQ 邮箱配置
        if 'qq_email' in self.raw_config:
            qq_email = self.raw_config['qq_email']
            self.config.qq_email = QQEmailConfig(
                enabled=qq_email.get('enabled', False),
                address=qq_email.get('address', ''),
                auth_code=qq_email.get('auth_code', ''),
                protocol=qq_email.get('protocol', 'imap'),
                imap_host=qq_email.get('imap_host', 'imap.qq.com'),
                imap_port=qq_email.get('imap_port', 993),
                pop_host=qq_email.get('pop_host', 'pop.qq.com'),
                pop_port=qq_email.get('pop_port', 995),
                mailbox=qq_email.get('mailbox', 'INBOX')
            )
        
        # 浏览器配置
        if 'browser' in self.raw_config:
            browser = self.raw_config['browser']
            self.config.browser = BrowserConfig(
                max_wait_time=browser.get('max_wait_time', 600),
                short_wait_time=browser.get('short_wait_time', 120),
                user_agent=browser.get('user_agent', '')
            )
        
        # 密码配置
        if 'password' in self.raw_config:
            pwd = self.raw_config['password']
            self.config.password = PasswordConfig(
                length=pwd.get('length', 16),
                charset=pwd.get('charset', '')
            )
        
        # 重试配置
        if 'retry' in self.raw_config:
            retry = self.raw_config['retry']
            self.config.retry = RetryConfig(
                http_max_retries=retry.get('http_max_retries', 5),
                http_timeout=retry.get('http_timeout', 30),
                error_page_max_retries=retry.get('error_page_max_retries', 5),
                button_click_max_retries=retry.get('button_click_max_retries', 3)
            )
        
        # 批量配置
        if 'batch' in self.raw_config:
            batch = self.raw_config['batch']
            self.config.batch = BatchConfig(
                interval_min=batch.get('interval_min', 5),
                interval_max=batch.get('interval_max', 15)
            )
        
        # 文件配置
        if 'files' in self.raw_config:
            files = self.raw_config['files']
            self.config.files = FilesConfig(
                accounts_file=files.get('accounts_file', 'registered_accounts.txt')
            )
        
        # 支付配置
        if 'payment' in self.raw_config:
            payment = self.raw_config['payment']
            self.config.payment = PaymentConfig(
                credit_card=CreditCardConfig(
                    number=payment.get('credit_card', {}).get('number', ''),
                    expiry=payment.get('credit_card', {}).get('expiry', ''),
                    expiry_month=payment.get('credit_card', {}).get('expiry_month', ''),
                    expiry_year=payment.get('credit_card', {}).get('expiry_year', ''),
                    cvc=payment.get('credit_card', {}).get('cvc', '')
                ),
                billing=BillingInfoConfig(
                    use_static=payment.get('billing', {}).get('use_static', False),
                    name=payment.get('billing', {}).get('name', ''),
                    country=payment.get('billing', {}).get('country', ''),
                    state=payment.get('billing', {}).get('state', ''),
                    city=payment.get('billing', {}).get('city', ''),
                    address1=payment.get('billing', {}).get('address1', ''),
                    address2=payment.get('billing', {}).get('address2', ''),
                    zip=payment.get('billing', {}).get('zip', ''),
                    address_source=payment.get('address_source', 'local')
                )
            )

        # 飞书多维表格配置
        if 'feishu_bitable' in self.raw_config:
            fb = self.raw_config.get('feishu_bitable') or {}
            fb_fields = fb.get('fields', {}) or {}
            self.config.feishu_bitable = FeishuBitableConfig(
                enabled=fb.get('enabled', False),
                api_base_url=fb.get('api_base_url', 'https://open.feishu.cn/open-apis'),
                app_id=fb.get('app_id', ''),
                app_secret=fb.get('app_secret', ''),
                app_token=fb.get('app_token', ''),
                table_id=fb.get('table_id', ''),
                created_at_format=fb.get('created_at_format', 'datetime_str'),
                fields=FeishuBitableFieldsConfig(
                    email=fb_fields.get('email', '邮箱'),
                    password=fb_fields.get('password', '密码'),
                    registered_at=fb_fields.get('registered_at', fb_fields.get('created_at', '注册时间')),
                    plus_redeemed_at=fb_fields.get('plus_redeemed_at', '兑换Plus时间'),
                    account_type=fb_fields.get('account_type', '类型'),
                    status=fb_fields.get('status', ''),
                    created_at=fb_fields.get('created_at', ''),
                ),
            )
    
    def reload(self) -> None:
        """重新加载配置文件"""
        self._load_config()
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取原始配置值（支持点号路径）
        
        参数:
            key: 配置键，支持点号分隔的路径，如 'email.domain'
            default: 默认值
        
        返回:
            配置值或默认值
        """
        keys = key.split('.')
        value = self.raw_config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value


# ==============================================================
# 全局配置实例
# ==============================================================

# 创建全局配置加载器
_loader = ConfigLoader()

# 配置对象（推荐使用）
cfg = _loader.config


# ==============================================================
# 兼容性导出（保持旧代码兼容）
# ==============================================================

# 注册配置
TOTAL_ACCOUNTS = cfg.registration.total_accounts
MIN_AGE = cfg.registration.min_age
MAX_AGE = cfg.registration.max_age

# 邮箱配置
EMAIL_WORKER_URL = cfg.email.worker_url
EMAIL_DOMAIN = cfg.email.domain
EMAIL_PREFIX_LENGTH = cfg.email.prefix_length
EMAIL_WAIT_TIMEOUT = cfg.email.wait_timeout
EMAIL_POLL_INTERVAL = cfg.email.poll_interval
EMAIL_ADMIN_PASSWORD = cfg.email.admin_password

# QQ 邮箱配置
QQ_EMAIL_ENABLED = cfg.qq_email.enabled
QQ_EMAIL_ADDRESS = cfg.qq_email.address
QQ_EMAIL_AUTH_CODE = cfg.qq_email.auth_code
QQ_EMAIL_PROTOCOL = (cfg.qq_email.protocol or "imap").lower()
QQ_IMAP_HOST = cfg.qq_email.imap_host
QQ_IMAP_PORT = cfg.qq_email.imap_port
QQ_POP_HOST = cfg.qq_email.pop_host
QQ_POP_PORT = cfg.qq_email.pop_port
QQ_MAILBOX = cfg.qq_email.mailbox

# 浏览器配置
MAX_WAIT_TIME = cfg.browser.max_wait_time
SHORT_WAIT_TIME = cfg.browser.short_wait_time
USER_AGENT = cfg.browser.user_agent

# 密码配置
PASSWORD_LENGTH = cfg.password.length
PASSWORD_CHARS = cfg.password.charset

# 重试配置
HTTP_MAX_RETRIES = cfg.retry.http_max_retries
HTTP_TIMEOUT = cfg.retry.http_timeout
ERROR_PAGE_MAX_RETRIES = cfg.retry.error_page_max_retries
BUTTON_CLICK_MAX_RETRIES = cfg.retry.button_click_max_retries

# 批量配置
BATCH_INTERVAL_MIN = cfg.batch.interval_min
BATCH_INTERVAL_MAX = cfg.batch.interval_max

# 文件配置
TXT_FILE = cfg.files.accounts_file

# 支付配置（字典格式，兼容旧代码）
def _normalize_expiry(expiry, month, year):
    expiry_raw = "" if expiry is None else str(expiry)
    expiry_digits = "".join(ch for ch in expiry_raw if ch.isdigit())
    if expiry_digits:
        return expiry_digits

    month_raw = "" if month is None else str(month)
    year_raw = "" if year is None else str(year)
    month_digits = "".join(ch for ch in month_raw if ch.isdigit())
    year_digits = "".join(ch for ch in year_raw if ch.isdigit())

    if month_digits:
        month_digits = month_digits.zfill(2)
    if year_digits:
        year_digits = year_digits[-2:]

    if month_digits and year_digits:
        return f"{month_digits}{year_digits}"
    return ""

_expiry_value = _normalize_expiry(
    cfg.payment.credit_card.expiry,
    cfg.payment.credit_card.expiry_month,
    cfg.payment.credit_card.expiry_year,
)
CREDIT_CARD_INFO = {
    "number": cfg.payment.credit_card.number,
    "expiry": _expiry_value,
    "expiry_month": cfg.payment.credit_card.expiry_month,
    "expiry_year": cfg.payment.credit_card.expiry_year,
    "cvc": cfg.payment.credit_card.cvc
}

# 账单配置（字典形式，方便使用）
BILLING_INFO = {
    "use_static": cfg.payment.billing.use_static,
    "name": cfg.payment.billing.name,
    "country": cfg.payment.billing.country,
    "state": cfg.payment.billing.state,
    "city": cfg.payment.billing.city,
    "address1": cfg.payment.billing.address1,
    "address2": cfg.payment.billing.address2,
    "zip": cfg.payment.billing.zip,
    "address_source": cfg.payment.billing.address_source,
}

# 飞书多维表格配置（兼容导出）
FEISHU_BITABLE_ENABLED = cfg.feishu_bitable.enabled
FEISHU_API_BASE_URL = cfg.feishu_bitable.api_base_url
FEISHU_APP_ID = cfg.feishu_bitable.app_id
FEISHU_APP_SECRET = cfg.feishu_bitable.app_secret
FEISHU_BITABLE_APP_TOKEN = cfg.feishu_bitable.app_token
FEISHU_BITABLE_TABLE_ID = cfg.feishu_bitable.table_id
FEISHU_BITABLE_CREATED_AT_FORMAT = cfg.feishu_bitable.created_at_format
FEISHU_BITABLE_FIELDS = {
    "email": cfg.feishu_bitable.fields.email,
    "password": cfg.feishu_bitable.fields.password,
    "registered_at": cfg.feishu_bitable.fields.registered_at,
    "plus_redeemed_at": cfg.feishu_bitable.fields.plus_redeemed_at,
    "account_type": cfg.feishu_bitable.fields.account_type,
    "status": cfg.feishu_bitable.fields.status,
    "created_at": cfg.feishu_bitable.fields.created_at,
}


# ==============================================================
# 工具函数
# ==============================================================

def reload_config() -> None:
    """
    重新加载配置文件
    注意：这不会更新已导入的常量，只会更新 cfg 对象
    """
    global cfg
    _loader.reload()
    cfg = _loader.config


def get_config() -> AppConfig:
    """获取当前配置对象"""
    return cfg


def print_config_summary() -> None:
    """打印配置摘要"""
    print("\n" + "=" * 50)
    print("📋 当前配置摘要")
    print("=" * 50)
    print(f"  注册账号数量: {cfg.registration.total_accounts}")
    print(f"  邮箱域名: {cfg.email.domain}")
    print(f"  Worker URL: {cfg.email.worker_url[:30]}...")
    print(f"  QQ 邮箱轮询: {'启用' if cfg.qq_email.enabled else '未启用'}")
    print(f"  账号保存文件: {cfg.files.accounts_file}")
    print(f"  批量间隔: {cfg.batch.interval_min}-{cfg.batch.interval_max}秒")
    print(f"  飞书多维表格: {'启用' if cfg.feishu_bitable.enabled else '未启用'}")
    print("=" * 50 + "\n")


# 模块加载时打印一次配置信息（可选）
if __name__ == "__main__":
    print_config_summary()
