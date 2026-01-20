#!/usr/bin/env python3
"""
调试脚本：用于分析 Stripe 支付表单中的所有输入框及其属性
运行方式：python3 debug_form.py
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc

# 启动浏览器
print("🚀 启动浏览器...")
driver = uc.Chrome(version_main=None, headless=False)

# 打开 ChatGPT Plus 支付页面（您需要替换为实际的 URL）
# 这里假设您已经有一个本地的 HTML 文件或可以访问的 URL
url = "https://chatgpt.com/auth/login"  # 或您已保存的本地文件路径
print(f"📄 打开页面: {url}")
driver.get(url)

time.sleep(5)

def get_input_context(inp, driver):
    """获取输入框的完整上下文"""
    context = ""
    try:
        context += inp.get_attribute('placeholder') or ""
        context += " | " + (inp.get_attribute('aria-label') or "")
        context += " | " + (inp.get_attribute('name') or "")
        context += " | " + (inp.get_attribute('id') or "")
        context += " | " + (inp.get_attribute('autocomplete') or "")
        context += " | " + (inp.get_attribute('data-elements-stable-field-name') or "")
        context += " | " + (inp.get_attribute('data-test') or "")
        context += " | " + (inp.get_attribute('title') or "")
        
        # 获取关联的 label
        inp_id = inp.get_attribute('id')
        if inp_id:
            try:
                label = driver.find_element(By.CSS_SELECTOR, f'label[for="{inp_id}"]')
                context += " | label: " + (label.text or "")
            except:
                pass
    except:
        pass
    return context.lower()

def debug_form():
    """调试表单 - 分析所有 iframe 中的输入框"""
    
    def _traverse_frames(depth=0, prefix=""):
        """递归遍历所有 iframe"""
        try:
            # 获取当前上下文中的所有输入框
            inputs = driver.find_elements(By.CSS_SELECTOR, 'input:not([type="hidden"]):not([type="submit"])')
            visible_inputs = [inp for inp in inputs if inp.is_displayed()]
            
            if visible_inputs:
                print(f"\n{prefix}[深度 {depth}] 找到 {len(visible_inputs)} 个可见输入框:")
                for idx, inp in enumerate(visible_inputs):
                    context = get_input_context(inp, driver)
                    print(f"{prefix}  [{idx}] {context[:120]}")
            
            # 查找 iframe
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            if frames:
                print(f"{prefix}[深度 {depth}] 找到 {len(frames)} 个 iframe")
            
            for idx, f in enumerate(frames):
                try:
                    print(f"{prefix}  → 进入 iframe [{idx}]")
                    driver.switch_to.frame(f)
                    _traverse_frames(depth + 1, prefix + "  ")
                    driver.switch_to.parent_frame()
                except Exception as e:
                    print(f"{prefix}  ⚠️ 无法访问 iframe: {e}")
                    try:
                        driver.switch_to.parent_frame()
                    except:
                        pass
        
        except Exception as e:
            print(f"{prefix}❌ 错误: {e}")
    
    # 从主页面开始
    driver.switch_to.default_content()
    print("🔍 开始分析表单结构...\n")
    _traverse_frames(0, "")

# 运行调试
time.sleep(2)
debug_form()

print("\n✅ 调试完成")
print("💡 建议：将上面的输出信息复制，用于优化 fill_name() 函数中的选择器")

# 保持浏览器打开以便观察
input("\n按 Enter 关闭浏览器...")
driver.quit()
