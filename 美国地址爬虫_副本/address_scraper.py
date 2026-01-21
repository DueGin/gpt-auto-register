#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美国地址爬虫
用途：从 meiguodizhi.com 爬取随机生成的虚拟地址信息
注意：该网站使用JavaScript动态加载数据，需要使用Selenium
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import json
import time
import csv
from datetime import datetime
import re


class AddressScraper:
    """地址爬虫类"""
    
    def __init__(self, headless=True):
        """
        初始化爬虫
        :param headless: 是否使用无头模式（不显示浏览器窗口）
        """
        self.base_url = "https://www.meiguodizhi.com/"
        self.driver = None
        self.headless = headless
        
    def init_driver(self):
        """初始化Selenium驱动"""
        if self.driver:
            return
            
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            print("Chrome驱动初始化成功")
        except Exception as e:
            print(f"Chrome驱动初始化失败: {e}")
            print("请确保已安装Chrome浏览器和chromedriver")
            raise
    
    def close_driver(self):
        """关闭驱动"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def fetch_page(self, url):
        """获取网页并等待JavaScript加载"""
        try:
            self.driver.get(url)
            # 等待数据加载完成 - 等待全名字段有值
            wait = WebDriverWait(self.driver, 10)
            # 等待元素存在
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'data_Full_Name')))
            # 等待元素的value属性不为空
            wait.until(lambda driver: driver.find_element(By.CLASS_NAME, 'data_Full_Name').get_attribute('value'))
            # 再等待一下确保所有数据都加载完成
            time.sleep(2)
            return self.driver.page_source
        except Exception as e:
            print(f"加载页面失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def parse_address(self):
        """从当前页面解析地址信息 - 直接从driver获取"""
        data = {}
        
        try:
            # 通过class名称直接查找input标签并获取value
            field_mapping = {
                'data_Full_Name': '全名',
                'data_Gender': '性别',
                'data_Birthday': '生日',
                'data_Title': 'Title',
                'data_Hair_Color': '头发颜色',
                'data_Address': '街道',
                'data_City': '城市',
                'data_State': '州',
                'data_State_Full': '州全称',
                'data_Zip_Code': '邮编',
                'data_Telephone': '电话号码',
                'data_Temporary_mail': '临时邮箱',
                'data_Credit_Card_Type': '信用卡类型',
                'data_Credit_Card_Number': '信用卡号',
                'data_CVV2': 'CVV2',
                'data_Expires': '过期时间',
                'data_Occupation': '职业',
                'data_Company_Name': '公司名称',
                'data_Company_Size': '公司规模',
                'data_Employment_Status': '就业状态',
                'data_Monthly_Salary': '月薪',
                'data_Social_Security_Number': '社会保障号',
                'data_Username': '用户名',
                'data_Password': '密码',
                'data_Height': '身高',
                'data_Weight': '体重',
                'data_Blood_Type': '血型',
                'data_System': '操作系统',
                'data_GUID': 'GUID',
                'data_Browser_User_Agent': '浏览器UserAgent',
                'data_Educational_Background': '教育背景',
                'data_Website': '个人主页',
                'data_Security_Question': '安全问题',
                'data_Security_Answer': '问题答案',
            }
            
            for class_name, field_name in field_mapping.items():
                try:
                    element = self.driver.find_element(By.CLASS_NAME, class_name)
                    value = element.get_attribute('value')
                    if value:
                        value = value.strip()
                        if value:
                            data[field_name] = value
                except:
                    pass  # 如果找不到元素就跳过
            
            # 添加爬取时间
            data['爬取时间'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            return data
        except Exception as e:
            print(f"解析数据出错: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def scrape_single_address(self):
        """爬取单个地址"""
        html = self.fetch_page(self.base_url)
        if html:
            return self.parse_address()
        return None
    
    def scrape_multiple_addresses(self, count=10, delay=2):
        """
        爬取多个地址
        :param count: 要爬取的地址数量
        :param delay: 每次请求之间的延迟（秒）
        """
        self.init_driver()
        addresses = []
        print(f"开始爬取 {count} 个地址...")
        
        try:
            for i in range(count):
                print(f"正在爬取第 {i+1}/{count} 个地址...")
                data = self.scrape_single_address()
                if data:
                    addresses.append(data)
                    name = data.get('全名', 'N/A')
                    city = data.get('城市', '')
                    print(f"成功爬取: {name} ({city})")
                else:
                    print(f"第 {i+1} 个地址爬取失败")
                
                # 延迟，避免请求过快
                if i < count - 1:
                    time.sleep(delay)
        finally:
            self.close_driver()
        
        print(f"爬取完成！共获取 {len(addresses)} 个地址")
        return addresses
    
    def save_to_json(self, data, filename='addresses.json'):
        """保存为JSON文件"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"数据已保存到 {filename}")
        except Exception as e:
            print(f"保存JSON文件失败: {e}")
    
    def save_to_csv(self, data, filename='addresses.csv'):
        """保存为CSV文件"""
        try:
            if not data:
                print("没有数据可保存")
                return
            
            # 获取所有可能的字段
            all_keys = set()
            for item in data:
                all_keys.update(item.keys())
            
            fieldnames = sorted(list(all_keys))
            
            with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
            
            print(f"数据已保存到 {filename}")
        except Exception as e:
            print(f"保存CSV文件失败: {e}")
    
    def scrape_city_addresses(self, city_name, count=5, delay=2):
        """
        爬取指定城市的地址
        :param city_name: 城市名称（英文），如 'New-York', 'Los-Angeles'
        :param count: 爬取数量
        :param delay: 延迟时间
        """
        url = f"{self.base_url}usa-address/hot-city-{city_name}"
        self.init_driver()
        addresses = []
        
        print(f"开始爬取 {city_name} 的地址...")
        
        try:
            for i in range(count):
                print(f"正在爬取第 {i+1}/{count} 个地址...")
                html = self.fetch_page(url)
                if html:
                    data = self.parse_address()
                    if data:
                        addresses.append(data)
                        name = data.get('全名', 'N/A')
                        print(f"成功爬取: {name}")
                
                if i < count - 1:
                    time.sleep(delay)
        finally:
            self.close_driver()
        
        return addresses
    
    def scrape_state_addresses(self, state_name, count=5, delay=2):
        """
        爬取指定州的地址
        :param state_name: 州名称（英文小写），如 'california', 'texas'
        :param count: 爬取数量
        :param delay: 延迟时间
        """
        url = f"{self.base_url}usa-address/{state_name}"
        self.init_driver()
        addresses = []
        
        print(f"开始爬取 {state_name} 州的地址...")
        
        try:
            for i in range(count):
                print(f"正在爬取第 {i+1}/{count} 个地址...")
                html = self.fetch_page(url)
                if html:
                    data = self.parse_address()
                    if data:
                        addresses.append(data)
                        name = data.get('全名', 'N/A')
                        print(f"成功爬取: {name}")
                
                if i < count - 1:
                    time.sleep(delay)
        finally:
            self.close_driver()
        
        return addresses


def main():
    """主函数 - 示例用法"""
    scraper = AddressScraper()
    
    # 示例1: 爬取3个随机地址进行测试
    print("=" * 50)
    print("示例1: 爬取随机地址")
    print("=" * 50)
    addresses = scraper.scrape_multiple_addresses(count=3, delay=2)
    
    # 保存数据
    if addresses:
        scraper.save_to_json(addresses, 'random_addresses.json')
        scraper.save_to_csv(addresses, 'random_addresses.csv')
        
        # 显示第一个地址的详情
        if len(addresses) > 0:
            print("\n" + "=" * 50)
            print("第一个地址示例:")
            print("=" * 50)
            for key, value in addresses[0].items():
                if value:  # 只显示有值的字段
                    print(f"{key}: {value}")
    
    # 示例2: 爬取特定城市的地址
    # print("\n" + "=" * 50)
    # print("示例2: 爬取纽约地址")
    # print("=" * 50)
    # ny_addresses = scraper.scrape_city_addresses('New-York', count=5, delay=2)
    # if ny_addresses:
    #     scraper.save_to_json(ny_addresses, 'newyork_addresses.json')
    
    # 示例3: 爬取特定州的地址
    # print("\n" + "=" * 50)
    # print("示例3: 爬取加州地址")
    # print("=" * 50)
    # ca_addresses = scraper.scrape_state_addresses('california', count=5, delay=2)
    # if ca_addresses:
    #     scraper.save_to_json(ca_addresses, 'california_addresses.json')


if __name__ == "__main__":
    main()
