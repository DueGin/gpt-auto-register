#!/bin/bash
# 快速启动脚本

# 检查地址库
echo "📋 检查地址库..."
python3 start_with_scraper.py --check

echo ""
echo "选择模式:"
echo "1) 直接启动注册服务（使用已有地址）"
echo "2) 先爬虫采集10个地址，再启动注册服务"
echo "3) 先爬虫采集50个地址，再启动注册服务"
echo ""
read -p "请输入选择 (1-3): " choice

case $choice in
    1)
        echo "启动注册服务..."
        python3 start_with_scraper.py --server
        ;;
    2)
        echo "先采集10个地址，再启动..."
        python3 start_with_scraper.py --scrape 10
        ;;
    3)
        echo "先采集50个地址，再启动..."
        python3 start_with_scraper.py --scrape 50
        ;;
    *)
        echo "无效选择"
        ;;
esac
