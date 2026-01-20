#!/usr/bin/env python3
"""
测试 Stripe 支付表单自动填写功能
使用方法：
1. 手动打开浏览器并登录 ChatGPT
2. 进入支付页面 (https://chatgpt.com/checkout/...)
3. 运行此脚本进行自动填写测试
"""
import sys
import os
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CREDIT_CARD_INFO, BILLING_INFO
from utils import generate_billing_info

def test_form_fill():
    """测试表单填写（需要手动打开支付页面）"""
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    
    print("\n" + "=" * 60)
    print("🧪 Stripe 表单自动填写测试")
    print("=" * 60)
    
    # 显示配置信息
    print("\n📋 当前配置:")
    print(f"   卡号: {CREDIT_CARD_INFO['number'][:4]}****{CREDIT_CARD_INFO['number'][-4:]}")
    print(f"   有效期: {CREDIT_CARD_INFO['expiry']}")
    print(f"   CVC: ***")
    print(f"   地址来源: {BILLING_INFO.get('address_source', 'local')}")
    
    print("\n🌐 正在启动浏览器...")
    
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1400,900")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = uc.Chrome(options=options, use_subprocess=True)
    
    print("\n📝 请手动操作:")
    print("   1. 登录你的 ChatGPT 账号")
    print("   2. 进入 Plus 订阅支付页面")
    print("   3. 按 Enter 键开始自动填写测试")
    
    driver.get("https://chatgpt.com")
    
    input("\n⏸️  准备好后按 Enter 键继续...")
    
    # 生成账单信息
    print("\n📍 生成账单信息...")
    billing_info = generate_billing_info("US", driver=driver)
    print(f"   姓名: {billing_info['name']}")
    print(f"   地址: {billing_info['address1']}")
    print(f"   城市: {billing_info['city']}, {billing_info['state']} {billing_info['zip']}")
    
    # 辅助函数
    def type_slowly(element, text, delay=0.05):
        for char in text:
            element.send_keys(char)
            time.sleep(delay)
    
    def find_all_inputs():
        inputs = []
        try:
            all_inputs = driver.find_elements(By.CSS_SELECTOR, 'input:not([type="hidden"]):not([type="submit"])')
            for inp in all_inputs:
                if inp.is_displayed():
                    inputs.append(inp)
        except:
            pass
        return inputs
    
    def get_input_context(inp):
        context = ""
        try:
            context += inp.get_attribute('placeholder') or ""
            context += " " + (inp.get_attribute('aria-label') or "")
            context += " " + (inp.get_attribute('name') or "")
            context += " " + (inp.get_attribute('id') or "")
            context += " " + (inp.get_attribute('autocomplete') or "")
        except:
            pass
        return context.lower()
    
    # 遍历所有 iframe
    def traverse_and_fill(max_depth=5):
        def _fill_in_context(depth=0):
            if depth > max_depth:
                return
            
            print(f"\n  📂 检查层级 {depth}...")
            inputs = find_all_inputs()
            print(f"     找到 {len(inputs)} 个输入框")
            
            for i, inp in enumerate(inputs):
                context = get_input_context(inp)
                print(f"     [{i}] 上下文: {context[:60]}...")
                
                # 卡号
                if any(kw in context for kw in ['卡号', 'card number', 'cardnumber', '1234', '0000']):
                    try:
                        inp.click()
                        inp.clear()
                        type_slowly(inp, CREDIT_CARD_INFO['number'])
                        print(f"     ✅ 填写卡号")
                    except Exception as e:
                        print(f"     ❌ 卡号填写失败: {e}")
                
                # 有效期
                elif any(kw in context for kw in ['有效期', 'expir', 'mm / yy', 'mm/yy']):
                    try:
                        inp.click()
                        inp.clear()
                        type_slowly(inp, CREDIT_CARD_INFO['expiry'])
                        print(f"     ✅ 填写有效期")
                    except Exception as e:
                        print(f"     ❌ 有效期填写失败: {e}")
                
                # 安全码
                elif any(kw in context for kw in ['安全码', 'cvc', 'cvv', 'security']):
                    try:
                        inp.click()
                        inp.clear()
                        type_slowly(inp, CREDIT_CARD_INFO['cvc'])
                        print(f"     ✅ 填写安全码")
                    except Exception as e:
                        print(f"     ❌ 安全码填写失败: {e}")
                
                # 全名
                elif any(kw in context for kw in ['全名', 'name', '姓名']) and 'card' not in context:
                    try:
                        inp.click()
                        inp.clear()
                        type_slowly(inp, billing_info['name'])
                        print(f"     ✅ 填写姓名")
                    except Exception as e:
                        print(f"     ❌ 姓名填写失败: {e}")
                
                # 地址
                elif any(kw in context for kw in ['地址', 'address', '街道']):
                    try:
                        inp.click()
                        inp.clear()
                        type_slowly(inp, billing_info['address1'])
                        print(f"     ✅ 填写地址")
                        time.sleep(0.5)
                        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    except Exception as e:
                        print(f"     ❌ 地址填写失败: {e}")
            
            # 遍历 iframe
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            for idx, frame in enumerate(frames):
                try:
                    if frame.is_displayed():
                        driver.switch_to.frame(frame)
                        _fill_in_context(depth + 1)
                        driver.switch_to.parent_frame()
                except:
                    try:
                        driver.switch_to.parent_frame()
                    except:
                        pass
        
        driver.switch_to.default_content()
        _fill_in_context(0)
    
    print("\n🔍 开始扫描和填写表单...")
    traverse_and_fill()
    
    print("\n✅ 测试完成！")
    print("   请检查页面上的表单是否已正确填写")
    print("   按 Enter 键关闭浏览器...")
    
    input()
    driver.quit()

if __name__ == "__main__":
    test_form_fill()
