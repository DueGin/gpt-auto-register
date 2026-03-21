"""
浏览器自动化模块
使用 undetected-chromedriver 实现 ChatGPT 注册流程
"""

import time
import os
import re
import subprocess
import threading
from typing import Optional
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from config import (
    MAX_WAIT_TIME,
    SHORT_WAIT_TIME,
    ERROR_PAGE_MAX_RETRIES,
    BUTTON_CLICK_MAX_RETRIES,
    CREDIT_CARD_INFO,
    BROWSER_INCOGNITO
)
from utils import generate_user_info, generate_billing_info


class SafeChrome(uc.Chrome):
    """
    自定义 Chrome 类，修复 Windows 下退出时的 WinError 6
    """
    def __del__(self):
        try:
            self.quit()
        except OSError:
            pass
        except Exception:
            pass

    def quit(self):
        try:
            super().quit()
        except OSError:
            pass
        except Exception:
            pass


_CHROME_MAJOR_RE = re.compile(r"(\d+)\.")


def _parse_chrome_major(version_str: Optional[str]) -> Optional[int]:
    if not version_str:
        return None
    match = _CHROME_MAJOR_RE.search(str(version_str))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_chrome_major_from_error(message: str) -> Optional[int]:
    if not message:
        return None
    match = re.search(r"Current browser version is (\d+)\.", message)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _run_version_command(command: list[str]) -> Optional[str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except Exception:
        return None

    output = (completed.stdout or "").strip()
    return output or None


def _get_windows_chrome_version_from_registry() -> Optional[str]:
    try:
        import winreg  # type: ignore
    except Exception:
        return None

    candidates = [
        (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon", "version"),
        (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon", "pv"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon", "version"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon", "pv"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Google\Chrome\BLBeacon", "version"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Google\Chrome\BLBeacon", "pv"),
    ]

    for root, path, name in candidates:
        try:
            with winreg.OpenKey(root, path) as key:
                value, _ = winreg.QueryValueEx(key, name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        except OSError:
            continue
        except Exception:
            continue

    return None


def _detect_local_chrome_major_version() -> Optional[int]:
    env_value = os.environ.get("CHROME_VERSION_MAIN") or os.environ.get("UC_VERSION_MAIN")
    if env_value:
        try:
            return int(str(env_value).strip())
        except ValueError:
            pass

    if os.name == "nt":
        major = _parse_chrome_major(_get_windows_chrome_version_from_registry())
        if major:
            return major

    for cmd in (
        ["google-chrome", "--version"],
        ["google-chrome-stable", "--version"],
        ["chromium", "--version"],
        ["chromium-browser", "--version"],
        ["chrome", "--version"],
        ["chrome.exe", "--version"],
    ):
        major = _parse_chrome_major(_run_version_command(cmd))
        if major:
            return major

    return None


def _create_uc_driver(
    options: uc.ChromeOptions,
    real_headless: bool,
    version_main: Optional[int],
) -> uc.Chrome:
    kwargs = {
        "options": options,
        "use_subprocess": True,
        "headless": real_headless,
        "patcher_force_close": False,
    }
    if version_main is not None:
        kwargs["version_main"] = int(version_main)
    return SafeChrome(**kwargs)


# ChromeDriver 初始化锁 — undetected_chromedriver 下载/拷贝驱动文件不是线程安全的
# 多线程并发 create_driver 时需要排队，避免文件操作冲突
_driver_init_lock = threading.Lock()


def create_driver(headless=False):
    """
    创建 undetected Chrome 浏览器驱动
    
    参数:
        headless (bool): 是否使用无头模式
        
    返回:
        uc.Chrome: 浏览器驱动实例
    """
    print(f"🌐 正在初始化浏览器 (Headless: {headless})...")

    # === 伪无头模式 (Fake Headless) ===
    # 真正的 Headless 很难过 Cloudflare，我们使用"移出屏幕"的策略
    # 这样既拥有完整的浏览器指纹，用户又看不到窗口
    real_headless = False

    if headless:
        print("  👻 使用'伪无头'模式 (Off-screen) 以绕过检测...")

    # 使用自定义的 SafeChrome (注意: 传入 real_headless=False)
    version_main = _detect_local_chrome_major_version()
    if version_main:
        print(f"[INFO] 检测到本机 Chrome 主版本: {version_main}")
    else:
        print("[WARN] 未检测到本机 Chrome 版本，将尝试自动选择驱动（可用 CHROME_VERSION_MAIN 覆盖）")

    def _make_options():
        """创建新的 ChromeOptions（undetected_chromedriver 不允许复用 options 对象）"""
        opts = uc.ChromeOptions()
        if BROWSER_INCOGNITO:
            opts.add_argument("--incognito")
        if headless:
            opts.add_argument("--window-position=-10000,-10000")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--start-maximized")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--lang=zh-CN,zh;q=0.9,en;q=0.8")
        return opts

    # 加锁：undetected_chromedriver 下载/拷贝驱动文件不是线程安全的
    # 多线程并发时需要排队创建 driver，避免文件冲突
    with _driver_init_lock:
        try:
            driver = _create_uc_driver(options=_make_options(), real_headless=real_headless, version_main=version_main)
        except Exception as e:
            fallback_major = _extract_chrome_major_from_error(str(e))
            if fallback_major and fallback_major != version_main:
                print(f"[WARN] ChromeDriver 版本与本机 Chrome 不匹配，重试 version_main={fallback_major} ...")
                driver = _create_uc_driver(options=_make_options(), real_headless=real_headless, version_main=fallback_major)
            else:
                raise
    
    # === 深度伪装 (针对 Headless 模式) ===
    if headless:
        print("🎭 应用深度指纹伪装...")
        
        # 1. 伪造 WebGL 供应商 (让它看起来像有真实显卡)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    // 37445: UNMASKED_VENDOR_WEBGL
                    // 37446: UNMASKED_RENDERER_WEBGL
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel(R) Iris(R) Xe Graphics';
                    }
                    return getParameter(parameter);
                };
            """
        })
        
        # 2. 伪造插件列表 (Headless 默认是空的)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en'],
                });
            """
        })
        
        # 3. 绕过常见的检测属性
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                // 覆盖 window.chrome
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // 伪造 permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                    Promise.resolve({ state: 'denied' }) :
                    originalQuery(parameters)
                );
            """
        })

    return driver


def check_and_handle_error(driver, max_retries=None):
    """
    检测页面错误并自动重试
    
    参数:
        driver: 浏览器驱动
        max_retries: 最大重试次数
    
    返回:
        bool: 是否检测到错误并处理
    """
    if max_retries is None:
        max_retries = ERROR_PAGE_MAX_RETRIES
    
    for attempt in range(max_retries):
        try:
            page_source = driver.page_source.lower()
            error_keywords = ['出错', 'error', 'timed out', 'operation timeout', 'route error', 'invalid content']
            has_error = any(keyword in page_source for keyword in error_keywords)
            
            if has_error:
                try:
                    retry_btn = driver.find_element(By.CSS_SELECTOR, 'button[data-dd-action-name="Try again"]')
                    print(f"⚠️ 检测到错误页面，正在重试（第 {attempt + 1}/{max_retries} 次）...")
                    driver.execute_script("arguments[0].click();", retry_btn)
                    wait_time = 5 + (attempt * 2)
                    print(f"  等待 {wait_time} 秒后继续...")
                    time.sleep(wait_time)
                    return True
                except Exception:
                    time.sleep(2)
                    continue
            return False
            
        except Exception as e:
            print(f"  错误检测异常: {e}")
            return False
    
    return False


def click_button_with_retry(driver, selector, max_retries=None):
    """
    带重试机制的按钮点击
    
    参数:
        driver: 浏览器驱动
        selector: CSS 选择器
        max_retries: 最大重试次数
    
    返回:
        bool: 是否成功点击
    """
    if max_retries is None:
        max_retries = BUTTON_CLICK_MAX_RETRIES
    
    for attempt in range(max_retries):
        try:
            button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            driver.execute_script("arguments[0].click();", button)
            return True
        except Exception as e:
            print(f"  第 {attempt + 1} 次点击失败，正在重试...")
            time.sleep(2)
    
    return False


def type_slowly(element, text, delay=0.05):
    """
    模拟人工缓慢输入
    
    参数:
        element: 输入框元素
        text: 要输入的文本
        delay: 每个字符之间的延迟（秒）
    """
    for char in text:
        element.send_keys(char)
        time.sleep(delay)


def fill_signup_form(driver, email: str, password: str):
    """
    填写注册表单
    适配 ChatGPT 新版统一登录/注册页面
    
    参数:
        driver: 浏览器驱动
        email: 邮箱地址
        password: 密码
    
    返回:
        bool: 是否成功填写
    """
    wait = WebDriverWait(driver, MAX_WAIT_TIME)
    
    try:
        # 1. 等待邮箱输入框出现
        print(f"DEBUG: 当前页面标题: {driver.title}")
        print(f"DEBUG: 当前页面URL: {driver.current_url}")
        print("📧 等待邮箱输入框...")
        
        # 检查是否是 Cloudflare 验证页
        if "Just a moment" in driver.title or "Ray ID" in driver.page_source or "请稍候" in driver.title:
             print("⚠️ 检测到 Cloudflare 验证页面...")
             # 尝试等待
             time.sleep(10)
             if "Just a moment" in driver.title or "请稍候" in driver.title:
                 print("  🔄 尝试刷新页面以突破验证...")
                 driver.refresh()
                 time.sleep(10)
                 
             # 再次检查，尝试点击验证框
             try:
                 # 寻找 CF 验证 iframe
                 frames = driver.find_elements(By.TAG_NAME, "iframe")
                 for frame in frames:
                     try:
                         driver.switch_to.frame(frame)
                         # 常见的验证框 ID 或 Class
                         checkbox = driver.find_elements(By.CSS_SELECTOR, "#checkbox, .checkbox, input[type='checkbox'], #challenge-stage")
                         if checkbox:
                             print("  🖱️ 尝试点击验证框...")
                             driver.execute_script("arguments[0].click();", checkbox[0])
                             time.sleep(5)
                         driver.switch_to.default_content()
                     except:
                         driver.switch_to.default_content()
             except: pass

        # 0. 检查是否在着陆页，需要点击注册/登录
        print("🔍 检查是否需要点击 注册/登录 按钮...")
        try:
            # 寻找 Sign up / Log in 按钮
            signup_btns = driver.find_elements(By.XPATH, '//button[contains(., "Sign up")] | //button[contains(., "注册")] | //div[contains(text(), "Sign up")] | //div[contains(text(), "注册")]')
            login_btns = driver.find_elements(By.XPATH, '//button[contains(., "Log in")] | //button[contains(., "登录")] | //div[contains(text(), "Log in")] | //div[contains(text(), "登录")]')
            
            target_btn = None
            if signup_btns:
                target_btn = signup_btns[0]
                print("  -> 找到 注册(Sign up) 按钮")
            elif login_btns:
                target_btn = login_btns[0]
                print("  -> 找到 登录(Log in) 按钮")
                
            if target_btn and target_btn.is_displayed():
                driver.execute_script("arguments[0].click();", target_btn)
                print("  ✅ 已点击入口按钮")
                time.sleep(3)
        except Exception as e:
            print(f"  ⚠️ 检查入口按钮时出错 (非致命): {e}")

        email_input = WebDriverWait(driver, SHORT_WAIT_TIME).until(
            EC.visibility_of_element_located((
                By.CSS_SELECTOR, 
                'input[type="email"], input[name="email"], input[autocomplete="email"]'
            ))
        )
        
        # 使用 ActionChains 模拟真实用户操作
        print("📝 正在输入邮箱...")
        actions = ActionChains(driver)
        actions.move_to_element(email_input)
        actions.click()
        actions.pause(0.3)
        actions.send_keys(email)
        actions.perform()
        
        time.sleep(1)
        
        # 验证输入是否成功
        actual_value = email_input.get_attribute('value')
        if actual_value == email:
            print(f"✅ 已输入邮箱: {email}")
        else:
            print(f"⚠️ 输入可能不完整，实际值: {actual_value}")
        
        time.sleep(1)
        
        # 2. 点击继续按钮
        print("🔘 点击继续按钮...")
        continue_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
        )
        actions = ActionChains(driver)
        actions.move_to_element(continue_btn)
        actions.click()
        actions.perform()
        print("✅ 已点击继续")
        time.sleep(3)
        
        # 4. 输入密码
        print("🔑 等待密码输入框...")
        password_input = WebDriverWait(driver, SHORT_WAIT_TIME).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="new-password"]'))
        )
        password_input.clear()
        time.sleep(0.5)
        type_slowly(password_input, password)
        print("✅ 已输入密码")
        time.sleep(2)
        
        # 5. 点击继续
        print("🔘 点击继续按钮...")
        if not click_button_with_retry(driver, 'button[type="submit"]'):
            print("❌ 点击继续按钮失败")
            return False
        print("✅ 已点击继续")
        
        time.sleep(3)
        while check_and_handle_error(driver):
            time.sleep(2)
        
        return True
        
    except Exception as e:
        print(f"❌ 填写表单失败: {e}")
        return False



def login(driver, email, password):
    """
    登录 ChatGPT
    """
    print(f"🔐 正在登录 {email}...")
    wait = WebDriverWait(driver, 30)
    
    try:
        driver.get("https://chat.openai.com/auth/login")
        time.sleep(5)
        
        # 0. 点击初始页面的 Log in / 登录 按钮
        print("🔘 寻找 Log in / 登录 按钮...")
        try:
            # 尝试多种选择器，支持中文
            xpaths = [
                '//button[@data-testid="login-button"]',
                '//button[contains(., "Log in")]',
                '//button[contains(., "登录")]',
                '//div[contains(text(), "Log in")]',
                '//div[contains(text(), "登录")]'
            ]
            
            login_btn = None
            for xpath in xpaths:
                try:
                    btns = driver.find_elements(By.XPATH, xpath)
                    for btn in btns:
                        if btn.is_displayed():
                            login_btn = btn
                            break
                    if login_btn:
                        break
                except:
                    continue
            
            if login_btn:
                # 确保点击
                try:
                    login_btn.click()
                except:
                    driver.execute_script("arguments[0].click();", login_btn)
                print("✅ 点击了登录按钮")
            else:
                print("⚠️ 未找到显式的登录按钮，尝试直接寻找输入框")
        except Exception as e:
            print(f"⚠️ 点击登录按钮出错: {e}")
            
        time.sleep(3)
        
        # 1. 输入邮箱
        print("📧 输入邮箱...")
        # 增加等待时间
        email_input = wait.until(EC.visibility_of_element_located((
            By.CSS_SELECTOR, 
            'input[name="username"], input[name="email"], input[id="email-input"]'
        )))
        email_input.clear()
        type_slowly(email_input, email)
        
        # 点击继续
        print("🔘 点击继续...")
        continue_btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"], button[class*="continue-btn"]')
        continue_btn.click()
        time.sleep(3)
        
        # ⚠️ 关键修正：检查是否进入了验证码模式，如果是，切换回密码模式
        print("🔍 检查登录方式...")
        try:
            # 寻找所有包含 "密码" 或 "Password" 的文本元素，只要它们看起来像链接或按钮
            # 排除掉密码输入框本身的 label
            switch_candidates = driver.find_elements(By.XPATH, 
                '//*[contains(text(), "密码") or contains(text(), "Password")]'
            )
            
            clicked_switch = False
            for el in switch_candidates:
                if not el.is_displayed():
                    continue
                    
                tag_name = el.tag_name.lower()
                text = el.text
                
                # 排除 label 和 title
                if tag_name in ['h1', 'h2', 'label', 'span'] and '输入' not in text and 'Enter' not in text and '使用' not in text:
                    continue
                    
                # 尝试点击看起来像切换链接的元素
                if '输入密码' in text or 'Enter password' in text or '使用密码' in text or 'password instead' in text:
                    print(f"⚠️ 尝试点击切换链接: '{text}' ({tag_name})...")
                    try:
                        el.click()
                        clicked_switch = True
                        time.sleep(2)
                        break
                    except:
                        # 可能是被遮挡，尝试 JS 点击
                        driver.execute_script("arguments[0].click();", el)
                        clicked_switch = True
                        time.sleep(2)
                        break
            
            if not clicked_switch:
                print("  ℹ️ 未找到明显的'切换密码'链接，假设在密码输入页或强制验证码页")
                
        except Exception as e:
            print(f"  检查登录方式出错: {e}")
        
        # 2. 输入密码
        print("🔑 等待密码输入框...")
        try:
            password_input = wait.until(EC.visibility_of_element_located((
                By.CSS_SELECTOR, 
                'input[name="password"], input[type="password"]'
            )))
            password_input.clear()
            type_slowly(password_input, password)
            
            # 点击继续/登录
            print("🔘 点击登录...")
            continue_btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"], button[name="action"]')
            continue_btn.click()
            
            print("⏳ 等待登录完成...")
            time.sleep(10)
        
        except Exception as e:
            print("❌ 未找到密码输入框。")
            print("  可能原因: 1. 强制验证码登录; 2. 页面加载过慢; 3. 选择器失效")
            print("  尝试手动干预或检查页面...")
            raise e # 抛出异常以终止测试
        
        # 检查是否登录成功
        if "auth" not in driver.current_url:
            print("✅ 登录成功")
            return True
        else:
            print("⚠️ 可能还在登录页面 (URL包含 auth)")
            # 再次检查是否有错误提示
            try:
                err = driver.find_element(By.CSS_SELECTOR, '.error-message, [role="alert"]')
                print(f"❌登录错误提示: {err.text}")
            except:
                pass
            return True
            
    except Exception as e:
        print(f"❌ 登录失败: {e}")
        return False


def enter_verification_code(driver, code: str):
    """
    输入验证码
    
    参数:
        driver: 浏览器驱动
        code: 验证码
    
    返回:
        bool: 是否成功
    """
    try:
        print("🔢 正在输入验证码...")
        
        # 先检查错误
        while check_and_handle_error(driver):
            time.sleep(2)
        
        code_input = WebDriverWait(driver, 60).until(
            EC.visibility_of_element_located((
                By.CSS_SELECTOR, 
                'input[name="code"], input[placeholder*="代码"], input[aria-label*="代码"]'
            ))
        )
        code_input.clear()
        time.sleep(0.5)
        type_slowly(code_input, code, delay=0.1)
        print(f"✅ 已输入验证码: {code}")
        time.sleep(2)
        
        # 点击继续
        print("🔘 点击继续按钮...")
        if not click_button_with_retry(driver, 'button[type="submit"]'):
            print("❌ 点击继续按钮失败")
            return False
        print("✅ 已点击继续")
        
        time.sleep(3)
        while check_and_handle_error(driver):
            time.sleep(2)
        
        return True
        
    except Exception as e:
        print(f"❌ 输入验证码失败: {e}")
        return False


def fill_profile_info(driver):
    """
    填写用户资料（随机生成的姓名和生日）
    
    参数:
        driver: 浏览器驱动
    
    返回:
        bool: 是否成功
    """
    wait = WebDriverWait(driver, MAX_WAIT_TIME)
    
    # 生成随机用户信息
    user_info = generate_user_info()
    user_name = user_info['name']
    birthday_year = user_info['year']
    birthday_month = user_info['month']
    birthday_day = user_info['day']
    
    try:
        # 1. 输入姓名
        print("👤 等待姓名输入框...")
        name_input = WebDriverWait(driver, 60).until(
            EC.visibility_of_element_located((
                By.CSS_SELECTOR, 
                'input[name="name"], input[autocomplete="name"]'
            ))
        )
        name_input.clear()
        time.sleep(0.5)
        type_slowly(name_input, user_name)
        print(f"✅ 已输入姓名: {user_name}")
        time.sleep(1)
        
        # 2. 输入生日
        print("🎂 正在输入生日...")
        time.sleep(1)
        
        # 年份
        year_input = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-type="year"]'))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", year_input)
        time.sleep(0.5)
        
        actions = ActionChains(driver)
        actions.click(year_input).perform()
        time.sleep(0.3)
        year_input.send_keys(Keys.CONTROL + "a")
        time.sleep(0.1)
        type_slowly(year_input, birthday_year, delay=0.1)
        time.sleep(0.5)
        
        # 月份
        month_input = driver.find_element(By.CSS_SELECTOR, '[data-type="month"]')
        actions = ActionChains(driver)
        actions.click(month_input).perform()
        time.sleep(0.3)
        month_input.send_keys(Keys.CONTROL + "a")
        time.sleep(0.1)
        type_slowly(month_input, birthday_month, delay=0.1)
        time.sleep(0.5)
        
        # 日期
        day_input = driver.find_element(By.CSS_SELECTOR, '[data-type="day"]')
        actions = ActionChains(driver)
        actions.click(day_input).perform()
        time.sleep(0.3)
        day_input.send_keys(Keys.CONTROL + "a")
        time.sleep(0.1)
        type_slowly(day_input, birthday_day, delay=0.1)
        
        print(f"✅ 已输入生日: {birthday_year}/{birthday_month}/{birthday_day}")
        time.sleep(1)
        
        # 3. 点击最后的继续按钮
        print("🔘 点击最终提交按钮...")
        continue_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
        )
        continue_btn.click()
        print("✅ 已提交注册信息")
        
        return True
        
    except Exception as e:
        print(f"❌ 填写资料失败: {e}")
        return False


def handle_stripe_input(driver, field_name, input_selectors, value, timeout=20):
    """
    智能填写 Stripe 字段
    逻辑：先在主文档找 -> 找不到则递归遍历所有 iframe 找
    """
    selectors = [s.strip() for s in input_selectors.split(',')]
    
    # 辅助函数：在当前上下文尝试查找并输入
    def try_fill():
        wait = WebDriverWait(driver, timeout)
        for selector in selectors:
            try:
                el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                if not el.is_displayed():
                    continue
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                except Exception:
                    pass
                try:
                    el.click()
                except Exception:
                    pass
                try:
                    el.clear()
                except Exception:
                    pass
                type_slowly(el, value)
                return True
            except:
                continue
        return False

    # 1. 尝试主文档
    if try_fill():
        print(f"  ✅ 在主文档找到 {field_name}")
        return True
        
    # 2. 递归遍历 iframe (支持多层嵌套，Stripe 支付元素通常 2-3 层)
    def traverse_frames(driver, depth=0, max_depth=6):
        if depth >= max_depth:
            return False
            
        # 获取当前上下文的所有 iframe
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        
        for i, frame in enumerate(frames):
            try:
                # 只有可见的 iframe 才可能是包含输入框的
                if not frame.is_displayed():
                    continue
                    
                driver.switch_to.frame(frame)
                
                # 尝试在当前 frame 填写
                if try_fill():
                    print(f"  ✅ 在 iframe (d={depth}, i={i}) 中找到 {field_name}")
                    driver.switch_to.default_content() # 找到后彻底重置回主文档
                    return True
                
                # 递归查找子 frame
                if traverse_frames(driver, depth + 1, max_depth):
                    return True
                    
                # 回退到父 frame
                driver.switch_to.parent_frame()
                
            except Exception as e:
                # 发生异常，尝试回退并继续
                try: driver.switch_to.parent_frame()
                except: pass
                continue
        
        return False

    driver.switch_to.default_content()
    if traverse_frames(driver):
        return True
                
    print(f"  ❌ 未找到 {field_name}")
    return False


def subscribe_plus_trial(driver):
    """
    订阅 ChatGPT Plus 免费试用 (日本地址版)
    """
    print("\n" + "=" * 50)
    print("💳 开始 Plus 试用订阅流程")
    print("   将自动检测页面国家并生成对应地址")
    print("=" * 50)
    
    wait = WebDriverWait(driver, 30)
    
    try:
        # 1. 访问 Pricing 页面
        url = "https://chatgpt.com/#pricing"
        print(f"🌐 正在打开 {url}...")
        driver.get(url)
        time.sleep(5)
        
        # 2. 点击 Plus 订阅按钮 (确保选择 Plus 而不是 Team)
        print("🔘 寻找 Plus 订阅按钮...")
        subscribe_btn = None
        
        def find_and_click_subscribe(retry_count=0):
            if retry_count > 3: return False

            # 尝试清理路上的弹窗：Next, Back, Done, Okay, Tips, Get started
            # 新用户的导览通常是一系列的，需要循环清理
            try:
                print("  🧹 扫描并清理可能的导览弹窗...")
                for _ in range(3): # 最多尝试清理3次（针对多步导览）
                    # 查找虽然不是 Plus 按钮，但是像导览控制的按钮
                    # 增加中文关键词：下一步，知道了，开始，跳过，好的，明白
                    guides = driver.find_elements(By.XPATH, '//button[contains(., "Next") or contains(., "Okay") or contains(., "Done") or contains(., "Start") or contains(., "Get started") or contains(., "Next tip") or contains(., "Later") or contains(., "下一步") or contains(., "知道了") or contains(., "开始") or contains(., "跳过") or contains(., "好的") or contains(., "Got it") or contains(., "Close") or contains(., "Dismiss")]')
                    
                    clicked_any = False
                    for btn in guides:
                        if btn.is_displayed():
                            txt = btn.text.lower()
                            # 排除掉升级按钮本身
                            if "upgrade" not in txt and "plus" not in txt and "trial" not in txt:
                                try:
                                    driver.execute_script("arguments[0].click();", btn)
                                    print(f"    -> 点击了导览按钮: {btn.text}")
                                    time.sleep(0.5)
                                    clicked_any = True
                                except: pass
                    
                    if not clicked_any:
                        break
                    time.sleep(1)
            except:
                pass

            # 确保在 Personal/个人 标签页（不是 Business/Team）
            try:
                print("  🔘 确保选择 个人 标签...")
                # 查找并点击 个人 标签（排除 Business）
                tabs = driver.find_elements(By.XPATH, '//button')
                for tab in tabs:
                    txt = tab.text.strip()
                    # 精确匹配 "个人" 或 "Personal"，排除 Business
                    if txt in ['个人', 'Personal'] and 'Business' not in txt:
                        if tab.is_displayed():
                            driver.execute_script("arguments[0].click();", tab)
                            print(f"  -> 已点击 '{txt}' 标签")
                            time.sleep(1)
                            break
            except Exception as e:
                print(f"  ⚠️ 切换个人标签时: {e}")

            # 寻找 Plus 套餐的 "领取免费试用" 按钮
            # 页面结构：三列（免费版、Plus、Pro），我们要点中间那个
            print("  🔘 寻找 Plus 套餐的订阅按钮...")
            buttons_xpaths = [
                # 优先：中间的 Plus 卡片内的按钮
                '//div[contains(., "Plus") and contains(., "$20")]//button[contains(., "领取免费试用") or contains(., "Start trial") or contains(., "Get Plus")]',
                '//button[contains(., "领取免费试用")]',  # 中文版
                '//button[contains(., "Get Plus")]',
                '//button[contains(., "Start trial")]',
                '//button[contains(., "Upgrade to Plus")]'
            ]
            
            for xpath in buttons_xpaths:
                try:
                    btns = driver.find_elements(By.XPATH, xpath)
                    for btn in btns:
                        if btn.is_displayed():
                            print(f"  找到按钮: {btn.text}")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(1)
                            try:
                                btn.click()
                                return True
                            except Exception as e:
                                print(f"  ⚠️ 点击被拦截，尝试再次清理弹窗... {e}")
                                # 递归重试
                                time.sleep(2)
                                return find_and_click_subscribe(retry_count + 1)
                except:
                    continue
            
            # 如果还没找到，可能是弹窗层级太深，或者需要刷新
            if retry_count == 0:
                 print("  ⚠️ 未直接找到按钮，尝试刷新页面...")
                 driver.refresh()
                 time.sleep(5)
                 return find_and_click_subscribe(retry_count + 1)
                 
            return False

        if not find_and_click_subscribe():
             print("❌ 经多次重试仍未找到 Plus 订阅按钮")
             try: driver.save_screenshot("debug_no_plus_btn.png")
             except: pass
             return False
        
        print("✅ 已点击 Plus 订阅按钮")     
            
        print("⏳ 等待支付页面加载 (智能检测)...")
        # 替换固定的 sleep(10)，改为动态监测表单元素
        page_loaded = False
        start_wait = time.time()
        while time.time() - start_wait < 30:
            # 检查是否有输入框或 iframe
            inputs = driver.find_elements(By.CSS_SELECTOR, "input, iframe")
            if len(inputs) > 3:
                # 进一步检查是否有支付相关的特征
                page_source = driver.page_source.lower()
                if "stripe" in page_source or "card" in page_source or "payment" in page_source or "支付" in page_source:
                    print("  ✅ 检测到支付表单元素，页面已就绪")
                    page_loaded = True
                    break
            time.sleep(1)
        
        if not page_loaded:
            print("⚠️ 页面加载似乎超时，尝试继续填写...")
        
        time.sleep(2) # 额外缓冲
        
        # -------------------------------------------------------------------------
        # 3. 填写支付表单
        # -------------------------------------------------------------------------
        print("💳 开始填写支付信息...")
        wait_input = WebDriverWait(driver, 15)
        
        # 辅助函数：在当前上下文查找元素（支持多个选择器）
        def find_visible(selector):
            """查找可见元素，支持逗号分隔的多选择器"""
            selectors = [s.strip() for s in selector.split(',')] if ',' in selector else [selector]
            for sel in selectors:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed(): return el
                except: 
                    pass
                try:
                    el = driver.find_element(By.XPATH, sel) # 兼容 XPATH
                    if el.is_displayed(): return el
                except:
                    pass
            return None
        
        def find_all_inputs():
            """查找所有可见的输入框"""
            inputs = []
            try:
                # 策略 1: 查找所有非隐藏、非提交的 input
                all_inputs = driver.find_elements(By.CSS_SELECTOR, 'input:not([type="hidden"]):not([type="submit"])')
                for inp in all_inputs:
                    try:
                        if inp.is_displayed():
                            inputs.append(inp)
                    except:
                        pass
            except:
                pass
            
            # 策略 2: 如果上面没有找到，尝试更通用的选择器
            if not inputs:
                try:
                    all_inputs = driver.find_elements(By.TAG_NAME, 'input')
                    for inp in all_inputs:
                        try:
                            # 排除隐藏的和提交按钮
                            inp_type = inp.get_attribute('type') or 'text'
                            if inp_type not in ['hidden', 'submit', 'button']:
                                if inp.is_displayed():
                                    inputs.append(inp)
                        except:
                            pass
                except:
                    pass
            
            return inputs
        
        def get_input_context(inp):
            """获取输入框的上下文信息（label、placeholder、aria-label等）"""
            context = ""
            try:
                context += inp.get_attribute('placeholder') or ""
                context += " " + (inp.get_attribute('aria-label') or "")
                context += " " + (inp.get_attribute('name') or "")
                context += " " + (inp.get_attribute('id') or "")
                context += " " + (inp.get_attribute('autocomplete') or "")
                # Stripe/Elements 特定属性
                context += " " + (inp.get_attribute('data-elements-stable-field-name') or "")
                context += " " + (inp.get_attribute('aria-describedby') or "")
                context += " " + (inp.get_attribute('data-test') or "")
                context += " " + (inp.get_attribute('title') or "")
                # 查找关联的 label
                inp_id = inp.get_attribute('id')
                if inp_id:
                    try:
                        label = driver.find_element(By.CSS_SELECTOR, f'label[for="{inp_id}"]')
                        context += " " + (label.text or "")
                    except:
                        pass
                # 查找父级的文本
                try:
                    parent = inp.find_element(By.XPATH, '..')
                    parent_text = parent.text[:100] if parent.text else ""
                    context += " " + parent_text
                except:
                    pass
            except:
                pass
            return context.lower()

        # 辅助函数：遍历查找并执行操作
        def run_in_all_frames(action_name, action_func, max_depth=6):
            """在所有 iframe（含嵌套）中尝试执行 action_func"""
            visited = 0
            found = False

            def _traverse(depth=0):
                nonlocal visited, found
                if depth > max_depth or found:
                    return
                try:
                    if action_func():
                        found = True
                        print(f"  ✅ {action_name} (depth={depth})")
                        return
                except Exception:
                    pass
                frames = driver.find_elements(By.TAG_NAME, "iframe")
                for idx, f in enumerate(frames):
                    try:
                        visited += 1
                        driver.switch_to.frame(f)
                        _traverse(depth + 1)
                        driver.switch_to.parent_frame()
                        if found:
                            return
                    except Exception:
                        try: driver.switch_to.parent_frame()
                        except: pass

            driver.switch_to.default_content()
            _traverse(0)
            if not found:
                print(f"  ⚠️ 未能完成: {action_name} (visited iframes={visited})")
            return found

        # ============== 1. 自动检测当前国家 ==============
        current_country_code = "US" # 默认美国（根据截图页面默认是美国）
        detected_country_name = "United States"

        def detect_country():
            nonlocal current_country_code, detected_country_name
            
            # 方法0: 直接在页面上查找"美国"文本
            try:
                page_text = driver.page_source
                if "美国" in page_text or "United States" in page_text:
                    current_country_code = "US"
                    detected_country_name = "United States (页面文本)"
                    return True
            except:
                pass
            
            # 尝试查找国家下拉框
            # 1. 查找 Select
            try:
                sel = find_visible('select[name="billingAddressCountry"], select[id^="Field-countryInput"]')
                if sel:
                    val = sel.get_attribute('value')
                    if val in ["US", "United States", "美国"]:
                        current_country_code = "US"
                        detected_country_name = "United States"
                    elif val in ["JP", "Japan", "日本"]:
                        current_country_code = "JP"
                        detected_country_name = "Japan"
                    else:
                        current_country_code = "JP" # 其他国家暂且当做 JP 处理（或根据需求扩展）
                        detected_country_name = val
                    return True
            except: pass

            # 2. 查找 Div 模拟的下拉框
            try:
                 # 查找包含 "国家" 或 "Country" 标签附近的 Div
                 dropdown_div = find_visible('//label[contains(text(), "国家") or contains(text(), "Country")]/following::div[contains(@class, "Select")][1]')
                 if not dropdown_div:
                     # 尝试找包含已知国家名的 Div
                     dropdown_div = find_visible('//*[contains(text(), "United States") or contains(text(), "美国") or contains(text(), "Japan") or contains(text(), "日本")]/ancestor::div[contains(@class, "Select") or contains(@class, "Input")][1]')
                 
                 if dropdown_div:
                     text = dropdown_div.text
                     if any(k in text for k in ["United States", "美国", "US"]):
                         current_country_code = "US"
                         detected_country_name = "United States"
                     elif any(k in text for k in ["Japan", "日本"]):
                         current_country_code = "JP"
                         detected_country_name = "Japan"
                     else:
                        current_country_code = "JP"
                        detected_country_name = text
                     return True
            except: pass
            
            # 3. 兜底：直接找页面上有没有显示 "美国" 或 "United States" 的独立文本，且位置靠前
            try:
                # 寻找表单区域内的 "美国" 文本
                us_text = find_visible('//form//div[contains(text(), "美国") or contains(text(), "United States")]')
                if us_text:
                     current_country_code = "US"
                     detected_country_name = "United States (Text Match)"
                     return True
            except: pass
            
            return False

        print("🌏 自动检测当前国家...")
        run_in_all_frames("检测国家", detect_country)
        print(f"   -> 检测结果: {detected_country_name} (Code: {current_country_code})")
        print("   -> 将生成该国家的真实地址进行填写")

        # 生成对应国家的随机账单信息（传入 driver 以便复用浏览器获取地址）
        billing_info = generate_billing_info(current_country_code, driver=driver)
        
        # ============== 智能表单填写 ==============
        def smart_fill_field(keywords, value, field_description):
            """
            智能填写字段：通过关键词匹配输入框
            keywords: 用于匹配的关键词列表
            value: 要填入的值
            field_description: 字段描述（用于日志）
            """
            inputs = find_all_inputs()
            for inp in inputs:
                context = get_input_context(inp)
                # 检查是否匹配任何关键词
                if any(kw in context for kw in keywords):
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                        time.sleep(0.3)
                        inp.click()
                        time.sleep(0.2)
                        
                        # 多步骤清空字段，确保彻底移除已有内容
                        inp.send_keys(Keys.CONTROL + "a")  # 全选
                        time.sleep(0.1)
                        inp.send_keys(Keys.DELETE)  # 删除
                        time.sleep(0.1)
                        inp.clear()  # 再清一遍
                        time.sleep(0.2)
                        
                        type_slowly(inp, value)
                        time.sleep(0.2)
                        print(f"  ✅ {field_description}: {value}")
                        return True
                    except Exception as e:
                        print(f"  ⚠️ 填写 {field_description} 失败: {e}")
            return False
        
        # ============== 2. 填写姓名 ==============
        def fill_name():
            """填写姓名字段 - 多策略查找"""
            # 先等待，确保 DOM 已加载
            time.sleep(0.5)
            
            # 策略 1: 直接通过 CSS 查询 placeholder 含"全名"的字段
            print(f"  🔍 策略1: 查找 placeholder 含'全名'的字段...")
            try:
                inputs = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder*="全名"], input[placeholder*="姓名"]')
                print(f"     找到 {len(inputs)} 个匹配字段")
                for inp in inputs:
                    try:
                        if inp.is_displayed():
                            print(f"     ✓ 找到可见字段: {inp.get_attribute('placeholder')}")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                            time.sleep(0.3)
                            inp.click()
                            time.sleep(0.3)
                            inp.send_keys(Keys.CONTROL + "a")
                            time.sleep(0.1)
                            inp.send_keys(Keys.DELETE)
                            time.sleep(0.2)
                            type_slowly(inp, billing_info["name"])
                            time.sleep(0.3)
                            print(f"  ✅ 姓名已填写: {billing_info['name']}")
                            return True
                    except Exception as e:
                        print(f"     ⚠️ 该字段不可用: {e}")
            except Exception as e:
                print(f"     ⚠️ 策略1失败: {e}")
            
            # 策略 2: 通过 label 标签找
            print(f"  🔍 策略2: 通过 label 标签查找...")
            try:
                labels = driver.find_elements(By.XPATH, "//label[contains(text(), '全名') or contains(text(), '姓名')]")
                for label in labels:
                    inp_id = label.get_attribute('for')
                    if inp_id:
                        inp = driver.find_element(By.ID, inp_id)
                        if inp.is_displayed():
                            print(f"     ✓ 找到关联输入框: {inp_id}")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                            time.sleep(0.3)
                            inp.click()
                            time.sleep(0.3)
                            inp.send_keys(Keys.CONTROL + "a")
                            time.sleep(0.1)
                            inp.send_keys(Keys.DELETE)
                            time.sleep(0.2)
                            type_slowly(inp, billing_info["name"])
                            time.sleep(0.3)
                            print(f"  ✅ 姓名已填写: {billing_info['name']}")
                            return True
            except Exception as e:
                print(f"     ⚠️ 策略2失败: {e}")
            
            # 策略 3: 通过绝对定位的 text 内容查找 label
            print(f"  🔍 策略3: 通过 aria-label 查找...")
            try:
                inputs = driver.find_elements(By.XPATH, 
                    "//input[@aria-label and (contains(@aria-label, '全名') or contains(@aria-label, '姓名'))]")
                for inp in inputs:
                    if inp.is_displayed():
                        print(f"     ✓ 找到: {inp.get_attribute('aria-label')}")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                        time.sleep(0.3)
                        inp.click()
                        time.sleep(0.3)
                        inp.send_keys(Keys.CONTROL + "a")
                        time.sleep(0.1)
                        inp.send_keys(Keys.DELETE)
                        time.sleep(0.2)
                        type_slowly(inp, billing_info["name"])
                        time.sleep(0.3)
                        print(f"  ✅ 姓名已填写: {billing_info['name']}")
                        return True
            except Exception as e:
                print(f"     ⚠️ 策略3失败: {e}")
            
            # 策略 4: 遍历所有输入框，按顺序填写（可能是表单中第一个 name 输入框）
            print(f"  🔍 策略4: 遍历所有输入框...")
            inputs = find_all_inputs()
            print(f"     找到 {len(inputs)} 个输入框")
            
            for idx, inp in enumerate(inputs):
                context = get_input_context(inp)
                print(f"     [{idx}] {context[:70]}")
                
                # 精确匹配"全名"或"姓名"
                if '全名' in context or '姓名' in context:
                    print(f"     ✓ 匹配到姓名字段 [{idx}]")
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                        time.sleep(0.3)
                        inp.click()
                        time.sleep(0.3)
                        inp.send_keys(Keys.CONTROL + "a")
                        time.sleep(0.1)
                        inp.send_keys(Keys.DELETE)
                        time.sleep(0.2)
                        type_slowly(inp, billing_info["name"])
                        time.sleep(0.3)
                        print(f"  ✅ 姓名已填写: {billing_info['name']}")
                        return True
                    except Exception as e:
                        print(f"  ⚠️ 填写失败: {e}")
            
            print(f"  ❌ 所有策略都失败了")
            return False
            
        print(f"👤 寻找并填写姓名: {billing_info['name']}...")
        
        # 带重试的填写姓名函数
        def fill_name_with_retry(max_attempts=5, wait_between=2):
            """带重试机制的填写姓名，等待字段加载"""
            for attempt in range(max_attempts):
                if attempt > 0:
                    print(f"  ⏳ 第 {attempt+1}/{max_attempts} 次尝试 (等待 {wait_between}s)...")
                    time.sleep(wait_between)
                
                # 先在主框架尝试
                try:
                    driver.switch_to.default_content()
                    if fill_name():
                        print("  ✅ 在主框架成功填写姓名")
                        return True
                except:
                    pass
                
                # 再尝试所有 iframe
                try:
                    driver.switch_to.default_content()
                    frames = driver.find_elements(By.TAG_NAME, "iframe")
                    for frame_idx, frame in enumerate(frames):
                        try:
                            driver.switch_to.frame(frame)
                            if fill_name():
                                print(f"  ✅ 在 iframe[{frame_idx}] 成功填写姓名")
                                driver.switch_to.default_content()
                                return True
                            driver.switch_to.default_content()
                        except:
                            driver.switch_to.default_content()
                except:
                    pass
            
            print("  ❌ 多次重试后仍无法找到姓名字段")
            return False
        
        # 执行带重试的填写
        fill_name_with_retry(max_attempts=8, wait_between=2)

        # ============== 3. 填写地址 ==============
        def fill_address():
            filled_any = False
            google_autofilled = False  # 标记 Google 是否自动填充了地址
            
            # 地址字段关键词（新版页面可能只有一个"地址"字段）
            address_keywords = ['地址', 'address', 'addressline', 'street', '街道']
            if smart_fill_field(address_keywords, billing_info["address1"], "地址"):
                filled_any = True
                time.sleep(0.8)
                
                # 输入地址后，尝试选择第一个推荐地址
                try:
                    # 等待自动完成下拉出现
                    time.sleep(0.5)
                    
                    # 查找推荐地址列表（常见的选择器）
                    suggestions = None
                    suggestion_selectors = [
                        '//*[contains(@class, "autocomplete") or contains(@class, "suggestion") or contains(@class, "dropdown")]//div[not(./*)][text()]',
                        '//*[@role="listbox"]//div[@role="option"]',
                        '//ul[contains(@class, "autocomplete")]//li',
                        '//*[contains(@class, "place-list")]//li',
                        '//*[contains(text(), "Maplewood") or contains(text(), "Maple")]',
                    ]
                    
                    first_suggestion = None
                    for selector in suggestion_selectors:
                        try:
                            if selector.startswith('//'):
                                elements = driver.find_elements(By.XPATH, selector)
                            else:
                                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            
                            if elements:
                                first_suggestion = elements[0]
                                print(f"  ✅ 找到推荐地址: {first_suggestion.text[:50]}")
                                break
                        except:
                            continue
                    
                    if first_suggestion:
                        # 点击第一个推荐地址
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_suggestion)
                        time.sleep(0.3)
                        first_suggestion.click()
                        print(f"  ✅ 已选择推荐地址 (Google 将自动填充城市/州/邮编)")
                        google_autofilled = True
                        time.sleep(2.5)  # 增加等待时间，让 Google 完成自动填充
                    else:
                        # 如果没找到下拉，按下 ArrowDown + Enter 选择第一个
                        try:
                            ActionChains(driver).send_keys(Keys.ARROW_DOWN, Keys.ENTER).perform()
                            print(f"  ✅ 通过键盘选择第一个推荐地址 (Google 将自动填充城市/州/邮编)")
                            google_autofilled = True
                            time.sleep(2.5)  # 增加等待时间，让 Google 完成自动填充
                        except:
                            # 最后的兜底：关闭可能出现的自动完成下拉
                            try:
                                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                            except:
                                pass
                except Exception as e:
                    print(f"  ⚠️ 地址自动选择失败: {e}")
                    try:
                        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    except:
                        pass
            
            # 如果 Google 已经自动填充，跳过手动填写邮编/城市/州
            if google_autofilled:
                print("  ℹ️ 跳过邮编/城市/州手动填写（Google 已自动填充）")
                return filled_any
            
            # 邮编字段 - 暂时禁用
            # zip_keywords = ['邮编', 'zip', 'postal', 'postcode', '邮政编码']
            # if smart_fill_field(zip_keywords, billing_info["zip"], "邮编"):
            #     filled_any = True
            #     time.sleep(3)  # 增加等待时间，让页面响应和加载
            print("  ⏭️  邮编字段已跳过（测试模式）")
            
            # 城市字段
            city_keywords = ['城市', 'city', 'locality', '市']
            if smart_fill_field(city_keywords, billing_info["city"], "城市"):
                filled_any = True
                time.sleep(1)  # 等待页面响应
            
            # 州/省字段
            state_keywords = ['州', 'state', 'province', 'region', '省']
            state_el = None
            inputs = find_all_inputs()
            for inp in inputs:
                context = get_input_context(inp)
                if any(kw in context for kw in state_keywords) and 'united states' not in context:
                    state_el = inp
                    break
            
            # 也检查 select 下拉框
            if not state_el:
                try:
                    selects = driver.find_elements(By.TAG_NAME, 'select')
                    for sel in selects:
                        context = get_input_context(sel)
                        if any(kw in context for kw in state_keywords):
                            state_el = sel
                            break
                except:
                    pass
            
            if state_el:
                try:
                    if state_el.tag_name == 'select':
                        state_el.send_keys(billing_info["state"])
                        state_el.send_keys(Keys.ENTER)
                    else:
                        # 多步骤清空州字段
                        state_el.send_keys(Keys.CONTROL + "a")
                        time.sleep(0.1)
                        state_el.send_keys(Keys.DELETE)
                        time.sleep(0.1)
                        state_el.clear()
                        time.sleep(0.2)
                        type_slowly(state_el, billing_info["state"])
                        time.sleep(0.3)
                        state_el.send_keys(Keys.ARROW_DOWN)
                        state_el.send_keys(Keys.ENTER)
                    print(f"  ✅ 州/省: {billing_info['state']}")
                    filled_any = True
                except Exception as e:
                    print(f"  ⚠️ 填写州失败: {e}")
                
            return filled_any or True  # 即使没填也返回 True 继续执行

        print("🏠 寻找并填写地址...")
        # 增加等待时间，让页面完全加载
        time.sleep(2)
        run_in_all_frames("填写地址", fill_address)
        time.sleep(2)  # 增加等待，让地址自动完成有时间加载

        # ============== 4. 填写信用卡 ==============
        print("💳 正在填写信用卡信息...")
        card = CREDIT_CARD_INFO
        # 确保回到主文档，再去遍历 Stripe 的多层 iframe
        try: driver.switch_to.default_content()
        except: pass
        
        # 直接填写信用卡字段（不通过 run_in_all_frames，避免 nonlocal 问题）
        def fill_card_direct():
            """直接在当前上下文填写信用卡字段"""
            filled_count = 0
            
            inputs = find_all_inputs()
            print(f"  📂 当前上下文找到 {len(inputs)} 个输入框")
            
            # 第一遍：只找卡号
            for inp in inputs:
                context = get_input_context(inp)
                is_card = ('卡号' in context or 'cardnumber' in context or 'cc-number' in context or 
                          ('1234' in context and '/' not in context and 'expir' not in context))
                is_not_other = ('安全' not in context and 'cvc' not in context and 'cvv' not in context and 
                               '有效' not in context and 'expir' not in context)
                
                if is_card and is_not_other:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                        inp.click()
                        time.sleep(0.2)
                        inp.clear()
                        type_slowly(inp, card["number"], delay=0.02)
                        print(f"  ✅ 卡号: {card['number'][:4]}****{card['number'][-4:]}")
                        filled_count += 1
                        time.sleep(0.5)
                        break
                    except Exception as e:
                        print(f"  ⚠️ 卡号填写失败: {e}")
            
            # 重新获取输入框
            inputs = find_all_inputs()
            
            # 第二遍：只找有效期
            for inp in inputs:
                context = get_input_context(inp)
                is_expiry = ('有效期' in context or '月/年' in context or 'expir' in context or 
                            'mm / yy' in context or 'mm/yy' in context or 'cc-exp' in context or
                            ('exp' in context and 'security' not in context and 'cvc' not in context))
                
                if is_expiry:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                        inp.click()
                        time.sleep(0.2)
                        inp.clear()
                        type_slowly(inp, card["expiry"], delay=0.05)
                        print(f"  ✅ 有效期: {card['expiry']}")
                        filled_count += 1
                        time.sleep(0.5)
                        break
                    except Exception as e:
                        print(f"  ⚠️ 有效期填写失败: {e}")
            
            # 重新获取输入框
            inputs = find_all_inputs()
            
            # 第三遍：只找安全码
            for inp in inputs:
                context = get_input_context(inp)
                is_cvc = ('安全码' in context or 'cvc' in context or 'cvv' in context or 
                         'security code' in context or 'securitycode' in context or
                         (context.strip() == '' and len(context) < 20))  # 空的或很短的字段可能是 CVC
                is_not_card = ('卡号' not in context and 'cardnumber' not in context and 
                              '1234 1234' not in context and 'number' not in context)
                is_not_expiry = ('有效期' not in context and 'expir' not in context and 'mm/' not in context)
                
                if is_cvc and is_not_card and is_not_expiry:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                        inp.click()
                        time.sleep(0.2)
                        inp.clear()
                        type_slowly(inp, card["cvc"], delay=0.05)
                        print(f"  ✅ 安全码: {card['cvc']}")
                        filled_count += 1
                        break
                    except Exception as e:
                        print(f"  ⚠️ 安全码填写失败: {e}")
            
            return filled_count
        
        # 在主文档和所有 iframe 中尝试
        def try_fill_card_in_frames():
            total_filled = 0
            
            def _traverse_frames(depth=0, max_depth=5):
                nonlocal total_filled
                if depth > max_depth:
                    return
                
                filled = fill_card_direct()
                total_filled += filled
                
                if filled >= 3:  # 三个字段都填了
                    return
                
                frames = driver.find_elements(By.TAG_NAME, "iframe")
                for frame in frames:
                    try:
                        if frame.is_displayed():
                            driver.switch_to.frame(frame)
                            _traverse_frames(depth + 1, max_depth)
                            if total_filled >= 3:
                                driver.switch_to.default_content()
                                return
                            driver.switch_to.parent_frame()
                    except:
                        try:
                            driver.switch_to.parent_frame()
                        except:
                            pass
            
            driver.switch_to.default_content()
            _traverse_frames()
            return total_filled
        
        filled_card_fields = try_fill_card_in_frames()
        print(f"  📊 共填写了 {filled_card_fields} 个信用卡字段")
        
        # 智能填写未完全成功就继续尝试，不切换传统选择器
        if filled_card_fields < 3:
            print("  ⚠️ 智能填写未完全成功，继续尝试智能填写方式...")
            # 移除了切换到传统选择器的逻辑
            # 系统将在后续提交时继续使用智能填写方式

        time.sleep(2)
        
        # ============== 5. 循环提交与补全 ==============
        def loop_submit_and_fix():
            max_attempts = 5
            for attempt in range(max_attempts):
                print(f"🔄 尝试提交 ({attempt + 1}/{max_attempts})...")
                
                # 1. 点击提交
                driver.switch_to.default_content() # 按钮通常在主文档
                submit_clicked = False
                
                # 尝试多种提交按钮选择器
                submit_selectors = [
                    "button[type='submit']",
                    "button[class*='Subscribe']",
                    "button[class*='submit']",
                    "//button[contains(text(), '订阅')]",
                    "//button[contains(text(), 'Subscribe')]",
                    "//button[contains(text(), '提交')]",
                    "//button[contains(text(), '支付')]",
                    "//button[contains(text(), 'Pay')]",
                ]
                
                for selector in submit_selectors:
                    try:
                        if selector.startswith('//'):
                            btn = driver.find_element(By.XPATH, selector)
                        else:
                            btn = driver.find_element(By.CSS_SELECTOR, selector)
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", btn)
                            print(f"  🔘 已点击提交按钮: {btn.text or selector}")
                            submit_clicked = True
                            break
                    except:
                        continue
                
                if not submit_clicked:
                    print("  ⚠️ 未找到提交按钮")
                
                time.sleep(3) # 等待校验结果
                
                # -------------------------------
                # 新增: 检查是否有验证码 (hCaptcha/Cloudflare)
                # -------------------------------
                try:
                    # 查找可能的验证码 iframe
                    captcha_frames = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='hcaptcha'], iframe[src*='challenges'], iframe[title*='widget'], iframe[title*='验证']")
                    for frame in captcha_frames:
                        if frame.is_displayed():
                            print("  ⚠️ 发现验证码，尝试点击...")
                            driver.switch_to.frame(frame)
                            try:
                                # hCaptcha / Cloudflare 常见的 Checkbox
                                checkbox = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#checkbox, .checkbox, #challenge-stage")))
                                checkbox.click()
                                print("    ✅ 已点击验证码复选框")
                                time.sleep(5) # 等待验证通过
                            except Exception as e:
                                print(f"    ⚠️ 点击验证码失败: {e}")
                            
                            driver.switch_to.default_content()
                except:
                    driver.switch_to.default_content()

                # 2. 检查是否有 '该字段不完整' / 'Incomplete field'
                # 需要遍历 iframe 检查
                time.sleep(1.5)  # 增加等待时间，让页面完全加载后再检查错误
                has_error = False
                driver.switch_to.default_content()
                frames = driver.find_elements(By.TAG_NAME, "iframe")
                all_frames = [None] + frames # None 表示主文档
                
                for frame in all_frames:
                    if frame:
                        try: driver.switch_to.frame(frame)
                        except: continue
                    else:
                        driver.switch_to.default_content()
                        
                    # 查找红字错误
                    errors = driver.find_elements(By.XPATH, '//*[contains(text(), "该字段不完整") or contains(text(), "Incomplete field") or contains(text(), "Required")]')
                    
                    if errors:
                        print(f"  ⚠️ 发现 {len(errors)} 个未完成字段，正在补全...")
                        time.sleep(1)  # 增加等待，让页面稳定后再补填
                        has_error = True
                        
                        # --- US 补全策略 ---

                        # 1. 检查地址行1 (最常见的遗漏)
                        try:
                             line1_inputs = driver.find_elements(By.CSS_SELECTOR, '#Field-addressLine1Input, input[name="addressLine1"], input[placeholder="地址第 1 行"], input[placeholder="Address line 1"]')
                             for el in line1_inputs:
                                 if el.is_displayed():
                                      current_value = el.get_attribute('value') or ""
                                      if not current_value or current_value != billing_info['address1']:
                                           print(f"    -> 补填 Address Line 1 ({billing_info['address1']})")
                                           el.send_keys(Keys.CONTROL + "a")
                                           time.sleep(0.1)
                                           el.send_keys(Keys.DELETE)
                                           time.sleep(0.1)
                                           el.clear()
                                           time.sleep(0.2)
                                           type_slowly(el, billing_info['address1'])
                                           try: el.send_keys(Keys.ENTER)
                                           except: pass
                                           time.sleep(1)  # 等待地址填充效果
                        except Exception as e:
                            print(f"    debug: 补填 address1 异常 {e}")

                        # 2. 检查州/State
                        time.sleep(0.8)  # 等待页面响应
                        state_inputs = driver.find_elements(By.CSS_SELECTOR, '#Field-administrativeAreaInput, select[name="state"], input[name="state"]')
                        for el in state_inputs:
                            try:
                                if el.is_displayed():
                                    state_value = billing_info.get('state', 'New York')
                                    print(f"    -> 补填 State ({state_value})")
                                    if el.tag_name == 'select':
                                        el.send_keys(state_value)
                                        el.send_keys(Keys.ENTER)
                                    else:
                                        el.send_keys(Keys.CONTROL + "a")
                                        time.sleep(0.1)
                                        el.send_keys(Keys.DELETE)
                                        time.sleep(0.1)
                                        el.clear()
                                        time.sleep(0.2)
                                        type_slowly(el, state_value)
                                        time.sleep(0.3)
                                        el.send_keys(Keys.ARROW_DOWN)
                                        el.send_keys(Keys.ENTER)
                            except: pass

                        # Check ZIP/postal code: keep existing value, fill when empty.
                        time.sleep(0.8)  # wait for page response
                        zip_inputs = driver.find_elements(
                            By.CSS_SELECTOR,
                            '#Field-postalCodeInput, input[name="postalCode"], input[autocomplete="postal-code"]'
                        )
                        for el in zip_inputs:
                            try:
                                if el.is_displayed():
                                    current_value = (el.get_attribute('value') or '').strip()
                                    if current_value:
                                        print(f"    -> Zip already set ({current_value})")
                                        continue
                                    expected_zip = billing_info.get('zip', '10001')
                                    print(f"    -> Fill Zip ({expected_zip})")
                                    # Multi-step clear to remove autofill
                                    el.send_keys(Keys.CONTROL + "a")
                                    time.sleep(0.1)
                                    el.send_keys(Keys.DELETE)
                                    time.sleep(0.1)
                                    el.clear()
                                    time.sleep(0.2)
                                    type_slowly(el, expected_zip)
                                    time.sleep(0.8)  # wait for zip fill effect
                            except:
                                pass
                        
                        # 检查城市
                        time.sleep(0.8)  # 等待页面响应
                        city_inputs = driver.find_elements(By.CSS_SELECTOR, '#Field-localityInput, input[name="city"]')
                        for el in city_inputs:
                            try:
                                if el.is_displayed() and not el.get_attribute('value'):
                                    city_value = billing_info.get('city', 'New York')
                                    print(f"    -> 补填 City ({city_value})")
                                    el.clear()
                                    type_slowly(el, city_value)
                            except: pass
                            
                    driver.switch_to.default_content()
                    if has_error: break # 只要发现错误就跳出 iframe 循环去点击提交
                
                if not has_error:
                    print("✅ 似乎没有表单错误了，等待结果...")
                    return True
                
                time.sleep(1)
            
            return False

        print("🚀 进入提交循环...")
        check_result = loop_submit_and_fix()

        print("✅ 表单提交流程结束，正在等待支付结果/页面跳转...")
        
        # 支付可能需要较长时间验证
        # 我们轮询检查 URL 变化
        start_time = time.time()
        while time.time() - start_time < 30:
            current_url = driver.current_url
            print(f"  当前 URL: {current_url}")
            
            # 成功信号 1: 回到主页
            if ("chatgpt.com" in current_url or "chat.openai.com" in current_url) and "pricing" not in current_url and "payment" not in current_url:
                 print("✅ 检测到跳转回主页，订阅成功！")
                 
                 # 顺便处理一下那个 "好的，开始吧" 弹窗，方便后续取消操作
                 try:
                    okay_btn = driver.find_element(By.XPATH, '//button[contains(., "Okay") or contains(., "开始") or contains(., "Let")]')
                    okay_btn.click()
                    print("  -> 已关闭欢迎弹窗")
                 except: pass
                 
                 return True

            # 成功信号 2: 出现 "Welcome" 弹窗
            try:
                if driver.find_element(By.XPATH, '//div[contains(text(), "ChatGPT")]//div[contains(text(), "Tips")]').is_displayed():
                    print("✅ 检测到欢迎弹窗，订阅成功！")
                    return True
            except: pass
            
            # 失败信号
            try:
                 error_msg = driver.find_element(By.CSS_SELECTOR, '.StripeElement--invalid, .error-message, [role="alert"]')
                 if error_msg and error_msg.is_displayed():
                     print(f"❌ 支付遇到错误: {error_msg.text}")
                     # 不要立即放弃，有时候是临时的
            except:
                 pass
                 
            time.sleep(2)

        print("❌ 等待跳转超时，且仍在支付页面，订阅可能失败。")
        return False
            
    except Exception as e:
        print(f"❌ 订阅流程出错: {e}")
        return False


def cancel_subscription(driver):
    """
    取消订阅
    """
    print("\n" + "=" * 50)
    print("🛑 开始取消订阅流程")
    print("=" * 50)
    
    wait = WebDriverWait(driver, 20)
    
    try:
        # 确保回到主页
        if "chatgpt.com" not in driver.current_url:
            driver.get("https://chatgpt.com")
        
        # ===== 等待页面完全加载 =====
        print("⏳ 等待页面完全加载...")
        for _ in range(10):  # 最多等 20 秒
            try:
                # 标志性元素：输入框或头像按钮
                driver.find_element(By.ID, "prompt-textarea")
                print("  ✅ 页面加载完成")
                break
            except:
                time.sleep(2)
        
        time.sleep(2)  # 额外缓冲
            
        # 🧹 清理可能存在的欢迎弹窗 (Critical!)
        print("🧹 检查并清理欢迎弹窗...")
        for _ in range(3):
            try:
                welcomes = driver.find_elements(By.XPATH, '//button[contains(., "Okay") or contains(., "开始") or contains(., "Let")]')
                clicked = False
                for btn in welcomes:
                    if btn.is_displayed():
                        print(f"  -> 点击关闭欢迎弹窗: {btn.text}")
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1)
                        clicked = True
                if not clicked:
                     break
            except:
                pass
            time.sleep(1)
        
        # ===== 打开个人菜单 (带重试) =====
        print("🔘 打开个人菜单...")
        menu_opened = False
        for attempt in range(3):
            try:
                # 尝试多种选择器找头像/菜单
                selectors = [
                    'div[data-testid="user-menu"]',
                    '.text-token-text-secondary',
                    '//div[contains(@class, "group relative")]'
                ]
                
                for sel in selectors:
                    try:
                        if sel.startswith('//'):
                            btn = driver.find_element(By.XPATH, sel)
                        else:
                            btn = driver.find_element(By.CSS_SELECTOR, sel)
                        btn.click()
                        menu_opened = True
                        break
                    except:
                        continue
                
                if menu_opened:
                    print(f"  ✅ 菜单打开成功 (第 {attempt+1} 次尝试)")
                    break
                    
            except Exception as e:
                print(f"  ⚠️ 第 {attempt+1} 次尝试失败: {e}")
            
            if not menu_opened:
                print(f"  🔄 等待 2s 后重试...")
                time.sleep(2)
        
        if not menu_opened:
            print("❌ 经多次重试仍无法打开个人菜单")
            return False
            
        
        time.sleep(2)
        
        # 调试：打印菜单内容
        try:
            menu = driver.find_element(By.CSS_SELECTOR, '[role="menu"], div[data-testid*="menu"]')
            print(f" 菜单内容:\n{menu.text}")
        except:
            pass
        
        print("🔘 点击 My Plan / 我的套餐...")
        found_my_plan = False
        try:
            # 优先找 "我的套餐" / "My plan"
            my_plan_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//div[contains(text(), "My plan") or contains(text(), "我的套餐")]')))
            my_plan_btn.click()
            found_my_plan = True
        except:
            print("⚠️ 未找到 '我的套餐'，尝试通过 '设置' 进入...")
            
            try:
                # 1. 点击 "设置" / "Settings"
                settings_btn = driver.find_element(By.XPATH, '//div[contains(text(), "Settings") or contains(text(), "设置")]')
                settings_btn.click()
                print("  -> 已点击 '设置'")
                time.sleep(2)
                
                # 2. 点击左侧 "帐户" / "Account" (如果是 Tab)
                # 3. 在设置弹窗中，点击 "Account" / "帐户" 标签
                print("  -> 切换到 '帐户' 标签...")
                
                from selenium.webdriver.common.action_chains import ActionChains
                
                try:
                    # 用 Selenium 精确查找帐户按钮
                    account_btns = driver.find_elements(By.XPATH, '//div[@role="dialog"]//button')
                    
                    for btn in account_btns:
                        try:
                            txt = btn.text.strip()
                            if txt == '帐户' or txt == '账户' or txt.lower() == 'account':
                                print(f"  -> 找到并点击帐户按钮: '{txt}'")
                                actions = ActionChains(driver)
                                actions.move_to_element(btn).click().perform()
                                time.sleep(1)
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"  ⚠️ 点击帐户标签时出错: {e}")
                
                time.sleep(1)  # 等待页面切换

                # 3. 检查状态或点击 "管理"
                # 截图显示如果已取消，会提示 "将于...取消"。
                try:
                    status_text = driver.find_element(By.XPATH, '//*[contains(text(), "你的套餐将于") or contains(text(), "Your plan will be canceled")]')
                    print(f"  ℹ️ 检测到订阅状态: {status_text.text}")
                    print("  ✅ 订阅似乎已经取消，不再继续。")
                    return True
                except:
                    pass

                # 4. 点击 "管理" / "Manage" 按钮 (ChatGPT Plus 区域的那个)
                print("  -> 寻找 ChatGPT Plus 区域的 '管理' 按钮...")
                try:
                    # 方法1：找包含 "ChatGPT Plus" 的区域，然后在其中找管理按钮
                    manage_btn = driver.find_element(By.XPATH, 
                        '//*[contains(text(), "ChatGPT Plus")]/ancestor::div[1]//button[contains(., "管理") or contains(., "Manage")]')
                    manage_btn.click()
                    print("  -> 已点击 ChatGPT Plus 区域的 '管理'")
                except:
                    try:
                        # 方法2：找标题"帐户"下方第一个管理按钮
                        manage_btn = driver.find_element(By.XPATH, 
                            '//h2[contains(., "帐户") or contains(., "Account")]/following::button[contains(., "管理") or contains(., "Manage")][1]')
                        manage_btn.click()
                        print("  -> 已点击标题下方的 '管理'")
                    except:
                        try:
                            # 方法3：找页面顶部区域的管理按钮（排除付款区域）
                            manage_btns = driver.find_elements(By.XPATH, '//button[contains(., "管理") or contains(., "Manage")]')
                            for btn in manage_btns:
                                # 检查这个按钮是否在页面上半部分（ChatGPT Plus 区域通常在上面）
                                location = btn.location
                                if location['y'] < 400 and btn.is_displayed():  # 假设上半部分 y < 400
                                    btn.click()
                                    print(f"  -> 已点击位置靠上的 '管理' (y={location['y']})")
                                    break
                        except Exception as e:
                            print(f"  ❌ 未找到管理按钮: {e}")
                            return False
                
                time.sleep(2)
                
                # ---------------------------------------------------------
                # 新分支：检测是否是应用内下拉菜单 (In-App Cancellation)
                # ---------------------------------------------------------
                print("  -> 等待下拉菜单出现...")
                time.sleep(2)  # 等待菜单动画
                
                try:
                    # 尝试多种选择器找 "取消订阅" / "Cancel subscription"
                    cancel_xpaths = [
                        '//*[contains(text(), "取消订阅")]',
                        '//*[contains(text(), "Cancel subscription")]',
                        '//div[contains(text(), "取消订阅")]',
                        '//span[contains(text(), "取消订阅")]',
                        '//button[contains(., "取消订阅")]'
                    ]
                    
                    cancel_item = None
                    for xp in cancel_xpaths:
                        try:
                            items = driver.find_elements(By.XPATH, xp)
                            for item in items:
                                if item.is_displayed():
                                    cancel_item = item
                                    print(f"  -> 找到取消按钮: {item.text}")
                                    break
                        except: pass
                        if cancel_item: break
                    
                    if cancel_item:
                        print("  -> 点击 '取消订阅'...")
                        driver.execute_script("arguments[0].click();", cancel_item)
                        time.sleep(2)
                        
                        # 处理确认弹窗
                        print("  -> 等待确认弹窗...")
                        confirm_xpaths = [
                            '//button[contains(., "取消订阅")]',
                            '//button[contains(., "Cancel subscription")]',
                            '//div[@role="dialog"]//button[contains(@class, "danger")]'
                        ]
                        
                        for xp in confirm_xpaths:
                            try:
                                confirm_btns = driver.find_elements(By.XPATH, xp)
                                for btn in confirm_btns:
                                    if btn.is_displayed() and ("取消" in btn.text or "Cancel" in btn.text):
                                        driver.execute_script("arguments[0].click();", btn)
                                        print("✅ 已点击最终确认取消！")
                                        return True
                            except: pass
                        
                        print("  ⚠️ 未能点击确认按钮")
                    else:
                        print("  ℹ️ 未检测到应用内取消菜单")
                        
                except Exception as e:
                    print(f"  ℹ️ 应用内取消流程异常: {e}")
                
                # ---------------------------------------------------------
                # 旧分支：Stripe Billing Portal 跳转
                # ---------------------------------------------------------
                # 如果上面没找到菜单，可能是旧版，跳转到了新标签页
                pass
                
            except Exception as e:
                print(f"❌ 通过设置页面取消失败: {e}")
                return False
        else:
             print("🔘 点击管理订阅 (My Plan 路径)...")
             try:
                manage_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[contains(text(), "Manage my subscription") or contains(text(), "管理我的订阅")]')))
                manage_btn.click()
             except:
                print("❌ 未找到管理订阅按钮")
                return False

        time.sleep(5)
        print("🌐 跳转到 Billing Portal...")
        
        print("🔘 寻找取消按钮...")
        try:
             # Stripe Portal 页面
             # 有时需要先切 iframe? 通常是新窗口或当前页跳转
            cancel_btn = wait.until(EC.presence_of_element_located((By.XPATH, '//button[contains(., "Cancel plan") or contains(., "取消方案")]')))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cancel_btn)
            time.sleep(1)
            cancel_btn.click()
        except:
             # 有时候是 "Cancel trial"
            try:
                cancel_btn = driver.find_element(By.XPATH, '//button[contains(., "Cancel trial") or contains(., "取消试用")]')
                cancel_btn.click()
            except:
                print("⚠️ 未找到取消按钮，可能已经取消或需要人工干预")
                return False
            
        time.sleep(2)
        print("🔘 确认取消...")
        try:
            confirm_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(., "Cancel plan") or contains(., "Confirm cancellation")]')))
            confirm_btn.click()
            print("✅ 订阅已取消！")
        except:
            print("⚠️ 未找到确认取消按钮")
            
        time.sleep(3)
        return True
        
    except Exception as e:
        print(f"❌ 取消订阅失败: {e}")
        return False
