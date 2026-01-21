#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义爬虫示例
你可以修改这个文件来满足自己的需求
"""

from address_scraper import AddressScraper

def example_1_random_addresses():
    """示例1：爬取随机地址"""
    print("=" * 60)
    print("示例1：爬取随机地址")
    print("=" * 60)
    
    scraper = AddressScraper(headless=True)  # headless=True 不显示浏览器窗口
    
    # 爬取10个地址，每次间隔2秒
    addresses = scraper.scrape_multiple_addresses(count=10, delay=2)
    
    if addresses:
        # 保存为JSON和CSV
        scraper.save_to_json(addresses, 'my_addresses.json')
        scraper.save_to_csv(addresses, 'my_addresses.csv')
        
        # 打印统计信息
        print(f"\n成功爬取 {len(addresses)} 个地址")
        print(f"文件已保存：my_addresses.json 和 my_addresses.csv")


def example_2_specific_city():
    """示例2：爬取特定城市的地址"""
    print("\n" + "=" * 60)
    print("示例2：爬取纽约市的地址")
    print("=" * 60)
    
    scraper = AddressScraper(headless=True)
    
    # 爬取纽约的地址
    ny_addresses = scraper.scrape_city_addresses('New-York', count=5, delay=2)
    
    if ny_addresses:
        scraper.save_to_json(ny_addresses, 'newyork_addresses.json')
        print(f"\n成功爬取 {len(ny_addresses)} 个纽约地址")
        
        # 显示第一个地址
        if ny_addresses:
            print("\n第一个地址示例：")
            for key, value in ny_addresses[0].items():
                print(f"  {key}: {value}")


def example_3_specific_state():
    """示例3：爬取特定州的地址"""
    print("\n" + "=" * 60)
    print("示例3：爬取加州的地址")
    print("=" * 60)
    
    scraper = AddressScraper(headless=True)
    
    # 爬取加州的地址
    ca_addresses = scraper.scrape_state_addresses('california', count=5, delay=2)
    
    if ca_addresses:
        scraper.save_to_json(ca_addresses, 'california_addresses.json')
        print(f"\n成功爬取 {len(ca_addresses)} 个加州地址")


def example_4_multiple_cities():
    """示例4：批量爬取多个城市"""
    print("\n" + "=" * 60)
    print("示例4：批量爬取多个城市的地址")
    print("=" * 60)
    
    cities = ['New-York', 'Los-Angeles', 'Chicago', 'Houston']
    scraper = AddressScraper(headless=True)
    
    all_addresses = {}
    
    for city in cities:
        print(f"\n正在爬取 {city}...")
        addresses = scraper.scrape_city_addresses(city, count=3, delay=2)
        all_addresses[city] = addresses
        print(f"{city} 完成，获取 {len(addresses)} 个地址")
    
    # 保存所有城市的数据
    scraper.save_to_json(all_addresses, 'multiple_cities.json')
    print(f"\n所有数据已保存到 multiple_cities.json")


def example_5_custom_processing():
    """示例5：自定义数据处理"""
    print("\n" + "=" * 60)
    print("示例5：爬取并筛选数据")
    print("=" * 60)
    
    scraper = AddressScraper(headless=True)
    addresses = scraper.scrape_multiple_addresses(count=10, delay=2)
    
    if addresses:
        # 只保留某些字段
        simplified = []
        for addr in addresses:
            simplified.append({
                '姓名': addr.get('全名', ''),
                '城市': addr.get('城市', ''),
                '州': addr.get('州', ''),
                '邮编': addr.get('邮编', ''),
                '电话': addr.get('电话号码', ''),
            })
        
        scraper.save_to_json(simplified, 'simplified_addresses.json')
        scraper.save_to_csv(simplified, 'simplified_addresses.csv')
        print(f"\n已保存简化版数据（仅包含关键字段）")


if __name__ == "__main__":
    # 取消注释你想运行的示例
    
    example_1_random_addresses()
    
    # example_2_specific_city()
    
    # example_3_specific_state()
    
    # example_4_multiple_cities()
    
    # example_5_custom_processing()
    
    print("\n" + "=" * 60)
    print("所有任务完成！")
    print("=" * 60)
