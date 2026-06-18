# 行业新闻聚合推送器

自动收集行业新闻，智能筛选排序，推送到飞书/邮箱/本地文件。

## 特性

- **零门槛配置**：用户只需提供网址或公众号名称，系统自动识别类型
- **多源支持**：新闻网站、微信公众号、RSS源、JSON API
- **智能筛选**：关键词匹配、去重、综合排序（时效性+来源权重+内容丰富度）
- **问题追踪**：全流程卡点识别，自动通知用户并提供解决建议
- **多渠道推送**：飞书文档、飞书消息卡片、邮件HTML、本地文件
- **固定美观模板**：无需自定义，开箱即用

## 快速开始

### 1. 安装

```bash
# 克隆项目
git clone https://github.com/yourname/industry-news-aggregator.git
cd industry-news-aggregator

# 安装依赖
pip install -e .
```

### 2. 配置

```bash
# 复制配置模板
cp config.example.yaml config.yaml

# 编辑配置
vim config.yaml
```

配置文件只需填写三部分：

```yaml
# 1. 信息源（直接粘贴网址或公众号名）
sources:
  - "https://finance.sina.com.cn"
  - "公众号:中国保险报"

# 2. 筛选条件
filter:
  industry: "保险"
  keywords: ["保险", "医保", "监管"]
  top_n: 10

# 3. 推送渠道
push:
  feishu:
    enabled: true
    doc_folder: "your_folder_token"
    notify_chat: "your_chat_id"
```

### 3. 设置环境变量

```bash
# 飞书凭证
export FEISHU_APP_ID="your_app_id"
export FEISHU_APP_SECRET="your_app_secret"

# 邮箱凭证（如启用邮箱推送）
export EMAIL_USER="your_email@example.com"
export EMAIL_PASSWORD="your_auth_code"
```

### 4. 运行

```bash
# 正式运行
python -m src.main --config config.yaml

# 试运行（仅输出到本地，不推送）
python -m src.main --config config.yaml --dry-run

# 详细日志
python -m src.main --config config.yaml --verbose
```

## Docker部署（推荐）

一键部署包含RSSHub（用于公众号采集）：

```bash
# 设置环境变量
export FEISHU_APP_ID="your_app_id"
export FEISHU_APP_SECRET="your_app_secret"

# 启动
docker-compose up -d

# 手动触发一次
docker exec news-aggregator python -m src.main --config /app/config.yaml
```

## 信息源格式说明

| 格式 | 说明 | 示例 |
|------|------|------|
| 普通网址 | 系统自动识别为网页/RSS | `https://finance.sina.com.cn` |
| 公众号 | 前缀"公众号:"+名称 | `公众号:中国保险报` |
| RSS地址 | 含/feed或/rss的URL | `https://36kr.com/feed` |

系统会自动探测网址类型，用户无需关心技术细节。

## 问题通知机制

系统在执行过程中会自动识别以下卡点并通知用户：

| 问题类型 | 通知示例 |
|---------|---------|
| 网址无法访问 | "网址无法访问，请检查地址是否正确" |
| 公众号已注销 | "公众号RSS获取失败，可能已注销或停止更新" |
| RSSHub不可用 | "无法连接RSSHub服务，请检查是否已启动" |
| 反爬拦截 | "网站拒绝了访问请求（403），可能存在反爬机制" |
| 筛选结果为空 | "所有信息源均未命中关键词，请检查关键词配置" |
| 推送凭证错误 | "飞书应用认证失败，请检查App ID和Secret" |

通知通过飞书消息卡片或邮件发送，包含问题描述和可操作的解决建议。

## 项目结构

```
industry-news-aggregator/
├── src/
│   ├── main.py              # 主入口
│   ├── config.py            # 配置解析
│   ├── issues.py            # 问题追踪系统
│   ├── models.py            # 数据模型
│   ├── notifier.py          # 通知路由
│   ├── utils.py             # 工具函数
│   ├── collectors/          # 收集器
│   │   ├── base.py          # 基类
│   │   ├── detector.py      # URL自动识别
│   │   ├── rss_collector.py # RSS收集
│   │   ├── web_collector.py # 网页爬虫
│   │   ├── wechat_collector.py  # 公众号
│   │   ├── api_collector.py # API收集
│   │   └── registry.py      # 注册表
│   ├── filters/             # 筛选引擎
│   │   ├── keyword_filter.py
│   │   ├── dedup.py
│   │   ├── ranker.py
│   │   └── engine.py
│   └── pushers/             # 推送器
│       ├── base.py
│       ├── feishu_pusher.py
│       ├── email_pusher.py
│       ├── local_pusher.py
│       └── templates.py     # 固定模板
├── config.example.yaml      # 配置模板
├── docker-compose.yaml      # Docker部署
├── Dockerfile
└── pyproject.toml
```

## 扩展开发

### 新增收集器

```python
from src.collectors.base import BaseCollector
from src.collectors.registry import CollectorRegistry

class MyCollector(BaseCollector):
    def collect(self, source, issue_tracker, **kwargs):
        # 实现收集逻辑
        return items

CollectorRegistry.register("my_type", MyCollector)
```

### 新增推送渠道

```python
from src.pushers.base import BasePusher

class MyPusher(BasePusher):
    def push(self, items, issue_tracker, result, **kwargs):
        # 实现推送逻辑
        return True
```

## License

MIT
