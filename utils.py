"""
工具函数模块
包含通用的辅助函数
"""

import random
import string
import csv
import os
import threading
from pathlib import Path
import re
import time
import json
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    PASSWORD_LENGTH,
    PASSWORD_CHARS,
    PASSWORD_CHARS,
    TXT_FILE,
    HTTP_MAX_RETRIES,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT,
    USER_AGENT,
    MIN_AGE,
    MAX_AGE,
    BILLING_INFO
)

# 尝试导入 BeautifulSoup 用于网页解析
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("⚠️ BeautifulSoup 未安装，meiguodizhi.com 地址抓取功能将不可用")
    print("   安装命令: pip install beautifulsoup4")

# 尝试导入 Faker 库
try:
    from faker import Faker
    # 创建多语言环境的 Faker 实例（英语为主，增加真实感）
    fake = Faker(['en_US', 'en_GB'])
    # 设置随机种子以确保可重复性（可选）
    # Faker.seed(0)
    FAKER_AVAILABLE = True
    print("✅ Faker 库已加载，将使用更真实的假数据")
except ImportError:
    FAKER_AVAILABLE = False
    print("⚠️ Faker 库未安装，将使用内置姓名列表")
    print("   安装命令: pip install Faker")

# ============================================================
# 常用英文名字库（用于随机生成用户姓名）
# ============================================================

FIRST_NAMES = [
    # 男性名字
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Christopher", "Daniel", "Matthew", "Anthony", "Mark",
    "Donald", "Steven", "Paul", "Andrew", "Joshua", "Kenneth", "Kevin", "Brian",
    "George", "Timothy", "Ronald", "Edward", "Jason", "Jeffrey", "Ryan",
    # 女性名字
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan",
    "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
    "Ashley", "Kimberly", "Emily", "Donna", "Michelle", "Dorothy", "Carol",
    "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon", "Laura", "Cynthia"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen",
    "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell"
]


def create_http_session():
    """
    创建带有重试机制的 HTTP Session
    
    返回:
        requests.Session: 配置好重试策略的 Session 对象
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=HTTP_MAX_RETRIES,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# 创建全局 HTTP Session
http_session = create_http_session()


def get_user_agent():
    """
    获取 User-Agent 字符串
    
    返回:
        str: User-Agent
    """
    return USER_AGENT


def generate_random_password(length=None):
    """
    生成随机密码
    确保密码包含大写字母、小写字母、数字和特殊字符
    
    参数:
        length: 密码长度，默认使用配置文件中的值
    
    返回:
        str: 生成的密码
    """
    if length is None:
        length = PASSWORD_LENGTH
    
    # 先随机生成指定长度的密码
    password = ''.join(random.choice(PASSWORD_CHARS) for _ in range(length))
    
    # 确保包含各类字符（替换前4位）
    password = (
        random.choice(string.ascii_uppercase) +   # 大写字母
        random.choice(string.ascii_lowercase) +   # 小写字母
        random.choice(string.digits) +            # 数字
        random.choice("!@#$%") +                  # 特殊字符
        password[4:]                              # 剩余部分
    )
    
    print(f"✅ 已生成密码: {password}")
    return password


# 文件写入锁，保证多线程并发写入安全
_file_lock = threading.Lock()


def save_to_txt(email: str, password: str = None, status="已注册"):
    """
    保存账号信息到 TXT 文件，格式: 邮箱----密码----时间----状态
    如果账号已存在，则更新其信息
    线程安全：使用文件锁保证并发写入不冲突
    """
    with _file_lock:
        try:
            file_path = os.path.join(os.path.dirname(__file__), TXT_FILE)
            current_date = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 读取现有内容
            lines = []
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

            # 检查是否已存在，存在则更新
            found = False
            new_line_content = f"{email}----{password if password else 'N/A'}----{current_date}----{status}\n"

            for i, line in enumerate(lines):
                # 检查邮箱是否在行首，避免匹配到邮箱作为密码或状态的一部分
                if line.startswith(f"{email}----"):
                    parts = line.strip().split("----")
                    current_password_in_file = parts[1] if len(parts) > 1 else 'N/A'

                    # 如果传入了新密码则用新密码，否则沿用旧密码
                    final_password = password if password else current_password_in_file
                    lines[i] = f"{email}----{final_password}----{current_date}----{status}\n"
                    found = True
                    break

            if not found:
                lines.append(new_line_content)

            # 写回文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            print(f"💾 账号状态已更新: {status}")

        except Exception as e:
            print(f"❌ 保存/更新账号信息失败: {e}")

def update_account_status(
    email: str,
    new_status: str,
    password: str = None,
    record_id = None,
):
    """
    专门用于更新账号状态的快捷函数
    
    参数:
        email: 邮箱地址
        new_status: 新的状态字符串
        password: 如果需要更新密码，则传入新密码，否则为 None
    """
    save_to_txt(email, password, new_status)
    if new_status == "已开通Plus":
        try:
            from feishu_bitable import update_plus_redeemed_time_in_bitable
            update_plus_redeemed_time_in_bitable(email=email, record_id=record_id)
        except Exception:
            pass


def extract_verification_code(content: str):
    """
    从邮件内容中提取 6 位数字验证码
    
    参数:
        content: 邮件内容（HTML 或纯文本）
    
    返回:
        str: 提取到的验证码，未找到返回 None
    """
    if not content:
        return None
    
    # 验证码匹配模式（按优先级排列）
    patterns = [
        r'代码为\s*(\d{6})',           # 中文格式
        r'code is\s*(\d{6})',          # 英文格式
        r'verification code[:\s]*(\d{6})',  # 完整英文格式
        r'(\d{6})',                     # 通用 6 位数字
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            code = matches[0]
            print(f"  ✅ 提取到验证码: {code}")
            return code
    
    return None


def generate_random_name():
    """
    生成随机英文姓名
    
    使用 Faker 库生成更真实的姓名，如果 Faker 不可用则回退到内置列表
    
    返回:
        str: 格式为 "FirstName LastName" 的随机姓名
    """
    if FAKER_AVAILABLE:
        # 使用 Faker 直接生成名和姓，避免前缀后缀问题
        # 随机选择生成男性或女性名字
        if random.choice([True, False]):
            first_name = fake.first_name_male()
        else:
            first_name = fake.first_name_female()
        
        last_name = fake.last_name()
        full_name = f"{first_name} {last_name}"
    else:
        # 回退到内置列表
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        full_name = f"{first_name} {last_name}"
    
    print(f"✅ 已生成随机姓名: {full_name}")
    return full_name


def generate_random_birthday():
    """
    生成随机生日
    确保年龄在配置的范围内（MIN_AGE 到 MAX_AGE）
    
    使用 Faker 库生成更真实的生日日期
    
    返回:
        tuple: (年份字符串, 月份字符串, 日期字符串)
               例如: ("1995", "03", "15")
    """
    if FAKER_AVAILABLE:
        # 使用 Faker 生成符合年龄范围的生日
        birthday = fake.date_of_birth(minimum_age=MIN_AGE, maximum_age=MAX_AGE)
        year_str = str(birthday.year)
        month_str = str(birthday.month).zfill(2)
        day_str = str(birthday.day).zfill(2)
    else:
        # 回退到原始逻辑
        from datetime import datetime as dt
        today = dt.now()
        
        min_birth_year = today.year - MAX_AGE
        max_birth_year = today.year - MIN_AGE
        birth_year = random.randint(min_birth_year, max_birth_year)
        birth_month = random.randint(1, 12)
        
        if birth_month in [1, 3, 5, 7, 8, 10, 12]:
            max_day = 31
        elif birth_month in [4, 6, 9, 11]:
            max_day = 30
        else:
            if (birth_year % 4 == 0 and birth_year % 100 != 0) or (birth_year % 400 == 0):
                max_day = 29
            else:
                max_day = 28
        
        birth_day = random.randint(1, max_day)
        
        year_str = str(birth_year)
        month_str = str(birth_month).zfill(2)
        day_str = str(birth_day).zfill(2)
    
    print(f"✅ 已生成随机生日: {year_str}/{month_str}/{day_str}")
    return year_str, month_str, day_str


def generate_user_info():
    """
    生成完整的随机用户信息
    
    返回:
        dict: 包含姓名和生日的字典
              {
                  'name': 'John Smith',
                  'year': '1995',
                  'month': '03',
                  'day': '15'
              }
    """
    name = generate_random_name()
    year, month, day = generate_random_birthday()
    
    return {
        'name': name,
        'year': year,
        'month': month,
        'day': day
    }


def generate_us_address():
    """
    生成随机美国地址
    使用 Faker 生成真实风格的美国地址
    """
    if FAKER_AVAILABLE:
        # 使用美国 Faker
        fake_us = Faker('en_US')
        
        # 常见的免税或低税州（对支付友好）
        states = [
            {"name": "Delaware", "code": "DE", "cities": ["Wilmington", "Dover", "Newark"]},
            {"name": "Oregon", "code": "OR", "cities": ["Portland", "Salem", "Eugene"]},
            {"name": "Montana", "code": "MT", "cities": ["Billings", "Missoula", "Helena"]},
            {"name": "New Hampshire", "code": "NH", "cities": ["Manchester", "Nashua", "Concord"]},
        ]
        
        state_info = random.choice(states)
        city = random.choice(state_info["cities"])
        
        # 生成街道地址
        street_number = random.randint(100, 9999)
        street_names = ["Main St", "Oak Ave", "Maple Dr", "Cedar Ln", "Park Blvd", 
                       "Washington St", "Lincoln Ave", "Jefferson Dr", "Madison Ln"]
        street = random.choice(street_names)
        
        addr = {
            "zip": fake_us.zipcode_in_state(state_info["code"]) if hasattr(fake_us, 'zipcode_in_state') else f"{random.randint(10000, 99999)}",
            "state": state_info["name"],
            "city": city,
            "address1": f"{street_number} {street}"
        }
    else:
        # 回退到固定地址
        addr = {
            "zip": "10001",
            "state": "New York",
            "city": "New York",
            "address1": f"{random.randint(100, 999)} Main St"
        }
    
    print(f"✅ 已生成美国地址: {addr['city']}, {addr['state']} {addr['zip']}")
    return addr


def load_scraped_address_from_file(dir_path: str = "美国地址爬虫_副本", pattern: str = "basic_addresses_*.json"):
    """
    从爬虫生成的 JSON 文件中取出一个地址并移除已使用项。

    默认目录: 美国地址爬虫_副本/basic_addresses_*.json
    取出顺序: 逐个文件按名称排序，从文件头部弹出第一条，写回剩余；如果文件为空则删除。

    返回:
        dict | None: {name, address1, city, state, zip}
    """
    dir_p = Path(dir_path)
    if not dir_p.exists():
        return None

    files = sorted(dir_p.glob(pattern))
    for fp in files:
        try:
            with fp.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        if not isinstance(data, list) or not data:
            try:
                fp.unlink()
            except Exception:
                pass
            continue

        # 弹出第一条记录
        record = data.pop(0)

        # 写回剩余数据，空则删除文件
        try:
            if data:
                with fp.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                fp.unlink()
        except Exception:
            pass

        # 兼容字段名映射
        def _get(*keys):
            for k in keys:
                if k in record and record[k]:
                    return str(record[k]).strip()
            return ""

        mapped = {
            "name": _get("name", "全名"),
            "address1": _get("address1", "街道", "地址"),
            "city": _get("city", "城市"),
            "state": _get("state", "州", "州全称"),
            "zip": _get("zip", "邮编"),
        }

        required = ["address1", "city", "state", "zip"]
        if all(mapped.get(k) for k in required):
            print(f"✅ 从文件 {fp.name} 取出地址: {mapped['address1']}, {mapped['city']} {mapped['state']} {mapped['zip']}")
            return mapped

    return None


def fetch_meiguodizhi_address(driver=None):
    """
    从 meiguodizhi.com 获取随机美国地址和姓名
    先尝试 API，失败则使用网页解析
    
    参数:
        driver: 可选的 Selenium WebDriver 实例（用于网页解析）
    
    返回:
        dict: 包含姓名和地址的字典，失败时返回 None
              {
                  'name': '姓名',
                  'address1': '街道地址',
                  'city': '城市',
                  'state': '州缩写',
                  'zip': '邮编'
              }
    """
    # 先尝试 API 方式
    try:
        import requests
        import json
        
        print("🌐 正在从 meiguodizhi.com API 获取随机美国地址...")
        
        timestamp = int(time.time() * 1000)
        api_url = f'https://www.meiguodizhi.com/api/v1/dz?t={timestamp}'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.meiguodizhi.com/'
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('status') == 'ok' and data.get('address'):
            address_info = data['address']
            
            address_data = {
                'name': address_info.get('Full_Name', '').strip(),
                'address1': address_info.get('Address', '').strip(),
                'city': address_info.get('City', '').strip(),
                'state': address_info.get('State', '').strip(),
                'zip': address_info.get('Zip_Code', '').strip()
            }
            
            required_fields = ['name', 'address1', 'city', 'state', 'zip']
            if all(field in address_data and address_data[field] for field in required_fields):
                print(f"✅ 成功从 meiguodizhi.com API 获取地址:")
                print(f"   姓名: {address_data['name']}")
                print(f"   地址: {address_data['address1']}, {address_data['city']}, {address_data['state']} {address_data['zip']}")
                return address_data
        else:
            print(f"⚠️ API 返回异常: {data.get('status')}，尝试网页解析...")
    except Exception as e:
        print(f"⚠️ API 方式失败: {e}，尝试网页解析...")
    
    # API 失败，尝试网页解析
    try:
        import requests
        from bs4 import BeautifulSoup
        
        print("🌐 正在从 meiguodizhi.com 网页解析地址...")
        
        url = 'https://www.meiguodizhi.com/'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 查找地址信息（根据网页结构解析）
        address_data = {}
        
        # 尝试查找包含地址的表格或列表
        # 方法1: 查找所有文本，匹配地址格式
        text_content = soup.get_text()
        
        # 尝试查找特定的元素
        # 根据实际网页结构调整选择器
        name_elem = soup.find(text=lambda t: t and '姓名' in t or 'Full Name' in t)
        address_elem = soup.find(text=lambda t: t and '地址' in t or 'Address' in t)
        
        # 如果能找到结构化数据
        if BS4_AVAILABLE:
            # 查找所有的行或项目
            rows = soup.find_all(['tr', 'div', 'li'])
            
            for row in rows:
                text = row.get_text(strip=True)
                
                # 匹配姓名
                if ('姓名' in text or 'Full Name' in text or 'Name' in text) and not address_data.get('name'):
                    # 提取姓名值
                    parts = text.split(':', 1) if ':' in text else text.split('：', 1)
                    if len(parts) == 2:
                        address_data['name'] = parts[1].strip()
                
                # 匹配地址
                if ('地址' in text or 'Address' in text or 'Street' in text) and not address_data.get('address1'):
                    parts = text.split(':', 1) if ':' in text else text.split('：', 1)
                    if len(parts) == 2:
                        address_data['address1'] = parts[1].strip()
                
                # 匹配城市
                if ('城市' in text or 'City' in text) and not address_data.get('city'):
                    parts = text.split(':', 1) if ':' in text else text.split('：', 1)
                    if len(parts) == 2:
                        address_data['city'] = parts[1].strip()
                
                # 匹配州
                if ('州' in text or 'State' in text) and not address_data.get('state'):
                    parts = text.split(':', 1) if ':' in text else text.split('：', 1)
                    if len(parts) == 2:
                        address_data['state'] = parts[1].strip()
                
                # 匹配邮编
                if ('邮编' in text or 'Zip' in text or 'Postal' in text) and not address_data.get('zip'):
                    parts = text.split(':', 1) if ':' in text else text.split('：', 1)
                    if len(parts) == 2:
                        address_data['zip'] = parts[1].strip()
            
            # 验证是否获取到完整数据
            required_fields = ['name', 'address1', 'city', 'state', 'zip']
            if all(field in address_data and address_data[field] for field in required_fields):
                print(f"✅ 成功从 meiguodizhi.com 网页解析地址:")
                print(f"   姓名: {address_data['name']}")
                print(f"   地址: {address_data['address1']}, {address_data['city']}, {address_data['state']} {address_data['zip']}")
                return address_data
            else:
                print(f"⚠️ 网页解析获取数据不完整: {address_data}")
                return None
        else:
            print("❌ BeautifulSoup 未安装，无法解析网页")
            return None
            
    except requests.exceptions.Timeout:
        print("❌ 从 meiguodizhi.com 获取地址超时（网络延迟）")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到 meiguodizhi.com（网络错误或网站不可用）")
        return None
    except Exception as e:
        print(f"❌ 从 meiguodizhi.com 获取地址失败: {e}")
        return None


def generate_billing_info(country="US", driver=None):
    """
    生成完整的支付账单信息（姓名 + 地址）
    
    参数:
        country: 国家代码，默认 "US"（美国）
        driver: 可选的 Selenium WebDriver 实例，用于从 meiguodizhi.com 获取地址时复用
    
    返回:
        dict: 包含姓名和地址的完整账单信息
    """
    billing_cfg = BILLING_INFO
    
    # 1. 检查是否要使用 meiguodizhi.com 获取地址
    address_source = billing_cfg.get("address_source", "local")

    if address_source == "scraped":
        dir_path = billing_cfg.get("scraped_dir", "美国地址爬虫_副本")
        addr = load_scraped_address_from_file(dir_path=dir_path)
        if addr:
            name = billing_cfg.get("name") or addr.get("name") or generate_random_name()
            billing_info = {
                "name": name,
                "zip": addr["zip"],
                "state": addr["state"],
                "city": addr["city"],
                "address1": addr["address1"],
                "address2": "",
                "country": billing_cfg.get("country", country).upper()
            }
            print("📄 使用本地爬取文件中的地址")
            print(f"   姓名: {billing_info['name']}")
            print(f"   地址: {billing_info['address1']}, {billing_info['city']}, {billing_info['state']} {billing_info['zip']}")
            return billing_info
        else:
            print("⚠️ 本地爬取文件中没有可用地址，回退到其他来源")
    
    if address_source == "meiguodizhi":
        print("🌐 配置要求从 meiguodizhi.com 获取地址...")
        # 尝试从 meiguodizhi.com 获取地址
        meiguodizhi_data = fetch_meiguodizhi_address(driver=driver)
        if meiguodizhi_data:
            name = billing_cfg.get("name") or meiguodizhi_data.get("name", "") or generate_random_name()
            billing_info = {
                "name": name,
                "zip": meiguodizhi_data.get("zip", ""),
                "state": meiguodizhi_data.get("state", ""),
                "city": meiguodizhi_data.get("city", ""),
                "address1": meiguodizhi_data.get("address1", ""),
                "address2": "",
                "country": "US"
            }
            print("✅ 已从 meiguodizhi.com API 获取新地址:")
            print(f"   姓名: {billing_info['name']}")
            print(f"   完整地址: {billing_info['address1']}, {billing_info['city']}, {billing_info['state']} {billing_info['zip']}")
            return billing_info
        else:
            print("⚠️ meiguodizhi.com API 调用失败，回退到本地生成")
    
    # 2. 检查是否使用配置中的静态账单信息
    if billing_cfg.get("use_static"):
        name = billing_cfg.get("name") or generate_random_name()
        billing_info = {
            "name": name,
            "zip": billing_cfg.get("zip", ""),
            "state": billing_cfg.get("state", ""),
            "city": billing_cfg.get("city", ""),
            "address1": billing_cfg.get("address1", ""),
            "address2": billing_cfg.get("address2", ""),
            "country": billing_cfg.get("country", country).upper()
        }
        print("📋 使用配置中的账单信息:")
        print(f"   姓名: {billing_info['name']}")
        print(f"   地址: {billing_info['address1']}, {billing_info['city']}, {billing_info['state']} {billing_info['zip']}")
        return billing_info
    
    # 3. 本地生成随机地址（默认）
    print("🎲 使用本地生成的随机地址")
    name = billing_cfg.get("name") or generate_random_name()
    address = generate_us_address()
    
    billing_info = {
        "name": name,
        "zip": address["zip"],
        "state": address["state"],
        "city": address["city"],
        "address1": address["address1"],
        "country": "US"
    }
    
    print(f"📋 完整账单信息已生成:")
    print(f"   姓名: {billing_info['name']}")
    print(f"   地址: {billing_info['address1']}, {billing_info['city']}")
    print(f"   州/省: {billing_info['state']}, 邮编: {billing_info['zip']}")
    
    return billing_info
