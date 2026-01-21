#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查所有字段的调试脚本"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
import time

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=chrome_options)

try:
    print("正在访问网站...")
    driver.get('https://www.meiguodizhi.com/')
    
    # 等待页面加载
    wait = WebDriverWait(driver, 10)
    wait.until(lambda d: d.find_element(By.CLASS_NAME, 'data_Full_Name').get_attribute('value'))
    time.sleep(2)
    
    print("\n=== 所有data_开头的input字段 ===\n")
    inputs = driver.find_elements(By.CSS_SELECTOR, 'input[class*="data_"]')
    
    for inp in inputs:
        classes = inp.get_attribute('class')
        value = inp.get_attribute('value')
        # 提取data_开头的class名
        class_list = classes.split()
        data_class = [c for c in class_list if c.startswith('data_')]
        if data_class and value:
            print(f"{data_class[0]:30s} = {value}")
    
finally:
    driver.quit()
