# 美国地址爬虫

从 meiguodizhi.com 爬取随机生成的虚拟美国地址信息。

⚠️ **注意**: 该网站使用JavaScript动态加载数据，因此本爬虫使用 Selenium + Chrome 来渲染网页。

## 功能特点

- ✅ 爬取随机美国地址
- ✅ 爬取指定城市的地址
- ✅ 爬取指定州的地址
- ✅ 支持导出为 JSON 和 CSV 格式
- ✅ 自动解析所有字段（姓名、地址、电话、邮箱、信用卡等）
- ✅ 请求延迟控制，避免过快请求

## 环境要求

1. Python 3.7+
2. Google Chrome 浏览器
3. ChromeDriver（会自动下载，无需手动安装）

## 安装依赖

```bash
pip install -r requirements.txt
```

依赖包包括:
- `selenium` - 用于自动化浏览器操作
- `beautifulsoup4` - 用于HTML解析
- `lxml` - BeautifulSoup的解析器

## 使用方法

### 1. 快速开始

直接运行示例程序：

```bash
python address_scraper.py
```

这将爬取3个随机地址并保存为 JSON 和 CSV 文件。

### 2. 自定义示例

运行 `custom_example.py` 查看更多示例：

```bash
python custom_example.py
```

该文件包含5个不同的使用场景，你可以根据需要修改和使用。

### 3. 编程使用

```python
from address_scraper import AddressScraper

# 创建爬虫实例
scraper = AddressScraper(headless=True)  # headless=True 表示不显示浏览器窗口

# 爬取10个随机地址
addresses = scraper.scrape_multiple_addresses(count=10, delay=2)

# 保存为JSON
scraper.save_to_json(addresses, 'addresses.json')

# 保存为CSV
scraper.save_to_csv(addresses, 'addresses.csv')
```

### 4. 爬取特定城市

```python
# 爬取纽约的地址
ny_addresses = scraper.scrape_city_addresses('New-York', count=5, delay=2)
scraper.save_to_json(ny_addresses, 'newyork.json')
```

支持的热门城市：
- `New-York` - 纽约
- `Los-Angeles` - 洛杉矶
- `Chicago` - 芝加哥
- `Houston` - 休斯敦
- `Phoenix` - 菲尼克斯
- `Philadelphia` - 费城
- `San-Antonio` - 圣安东尼奥
- `San-Diego` - 圣地亚哥
- `Dallas` - 达拉斯

### 5. 爬取特定州

```python
# 爬取加州的地址
ca_addresses = scraper.scrape_state_addresses('california', count=5, delay=2)
scraper.save_to_json(ca_addresses, 'california.json')
```

支持的州名（使用小写英文）：
- `california` - 加利福尼亚州
- `texas` - 德克萨斯州
- `florida` - 佛罗里达州
- `new-york` - 纽约州
- `pennsylvania` - 宾夕法尼亚州
- 等等...（所有美国州）

## 数据字段

爬取的数据包含以下信息：

### 基本资料
- 全名
- 性别
- 生日
- Title
- 头发颜色

### 地址信息
- 街道
- 区县
- 城市
- 州
- 州全称
- 邮编
- 电话号码
- 临时邮箱

### 就业 & 信用卡
- 信用卡类型
- 信用卡号
- CVV2
- 过期时间
- 职业
- 公司名称
- 公司规模
- 就业状态
- 月薪
- 社会保障号

### 更多资料
- 用户名
- 密码
- 身高
- 体重
- 血型
- 操作系统
- GUID
- 浏览器useragent
- 教育背景
- 个人主页
- 安全问题
- 问题答案

## 注意事项

1. **合法使用**: 该爬虫仅用于学习目的，请遵守网站的使用条款
2. **请求频率**: 默认设置了2秒延迟，请勿过快请求
3. **数据用途**: 爬取的数据为虚拟数据，仅供学习参考，请勿用于非法用途

## 示例输出

JSON格式：
```json
[
  {
    "全名": "Wall Berry",
    "性别": "Male",
    "生日": "4/12/1982",
    "街道": "3904 October Woods Dr",
    "城市": "Nashville",
    "州": "TN",
    "邮编": "37013",
    "电话号码": "+14354433018",
    ...
  }
]
```

## 许可

仅供学习使用。
