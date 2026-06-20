# 行业新闻聚合推送器

自动收集行业新闻，智能筛选排序，推送到飞书/邮箱/本地文件。

## 特性

- **零门槛配置**：用户只需提供网址或公众号名称，系统自动识别类型
- **多源支持**：新闻网站、微信公众号、RSS源、JSON API
- **智能筛选**：关键词匹配、去重、综合排序（时效性+来源权重+内容丰富度）
- **问题追踪**：全流程卡点识别，自动通知用户并提供解决建议
- **多渠道推送**：飞书文档、飞书消息卡片、邮件HTML、本地文件
- **固定美观模板**：无需自定义，开箱即用

---

## 完整使用路径

### 前置条件

| 工具 | 用途 | 获取方式 |
|------|------|---------|
| Python 3.10+ | 运行环境 | https://python.org |
| Git | 下载代码 | https://git-scm.com |
| Docker（可选） | 一键部署 | https://docker.com |
| 飞书账号 | 飞书推送 | 飞书App |
| 邮箱账号 | 邮件推送 | 任意邮箱 |

---

### Step 1：获取项目

**方式A：Git克隆（推荐）**
```bash
git clone https://github.com/Guluobei/industry-news-aggregator.git
cd industry-news-aggregator
```

**方式B：下载ZIP**
1. 浏览器打开 https://github.com/Guluobei/industry-news-aggregator
2. 点击绿色 Code 按钮 → Download ZIP
3. 解压到任意目录

---

### Step 2：安装依赖

```bash
# 在项目目录下执行
pip install -e .

# 验证安装
python -m src.main --help
```

应显示帮助信息，无报错。

---

### Step 3：配置文件

```bash
cp config.example.yaml config.yaml
```

用文本编辑器打开 `config.yaml`，填写三部分：

#### Part 1：信息源（你想从哪里收集新闻）

```yaml
sources:
  # 新闻网站：直接粘贴网址
  - "https://finance.sina.com.cn"        # 新浪财经
  - "https://www.21jingji.com"           # 21世纪经济报道
  - "https://36kr.com"                   # 36氪

  # 微信公众号：填"公众号:"+名称
  - "公众号:中国保险报"
  - "公众号:保观"
```

#### Part 2：筛选条件（你想看什么新闻）

```yaml
filter:
  industry: "保险"            # 你的行业
  keywords:                   # 关注的关键词，命中任一即收录
    - "保险"
    - "医保"
    - "监管"
    - "新规"
  exclude:                    # 不想看的，命中任一即排除
    - "娱乐"
    - "八卦"
  top_n: 10                   # 每次推送几条
  hours: 168                  # 收集几小时内的新闻（168=7天）
```

#### Part 3：推送渠道（新闻发到哪里）

```yaml
push:
  # 飞书推送
  feishu:
    enabled: true
    doc_folder: "你的文件夹token"    # 见Step 5获取方法
    notify_chat: "你的群聊ID"        # 见Step 5获取方法

  # 邮件推送（可选）
  email:
    enabled: false              # 不需要则改false

  # 本地文件（建议始终开启，作为备份）
  local:
    enabled: true
    path: "./output"
    format: "markdown"
```

---

### Step 4：测试运行（无需凭证）

```bash
# 试运行模式：只输出到本地文件，不推送
python -m src.main --config config.yaml --dry-run
```

执行后查看 `output/` 目录，应看到生成的 Markdown 文件。如果为空：
- 检查信息源URL是否可访问（浏览器打开试试）
- 放宽关键词或增加 `hours` 值

---

### Step 5：获取飞书凭证（如需飞书推送）

**5.1 创建飞书应用**
1. 打开 https://open.feishu.cn/app
2. 点击"创建企业自建应用"
3. 填写应用名称（如"新闻聚合器"）和描述
4. 创建后，在"凭证与基础信息"页面记录 `App ID` 和 `App Secret`

**5.2 配置应用权限**
进入应用 → 权限管理，开启以下权限：
- `docx:document`（创建和编辑文档）
- `im:message`（发送消息）
- `drive:drive`（文件夹操作）

**5.3 获取文件夹Token**
1. 在飞书云空间新建一个文件夹（如"新闻资讯"）
2. 打开该文件夹，从浏览器地址栏复制URL
3. URL格式：`https://feishu.cn/drive/folder/XXXXXXXXX`
4. 其中 `XXXXXXXXX` 就是 `folder_token`

**5.4 获取群聊ID**
1. 在飞书中创建一个群（或用现有群）
2. 将你创建的应用机器人添加到群中
3. 群聊ID可通过飞书OpenAPI获取（参考飞书文档）

**5.5 发布应用**
应用 → 版本发布与管理 → 创建版本 → 申请线上版本 → 等待管理员审批

---

### Step 6：设置环境变量

凭证不写在配置文件里，通过环境变量注入。

**Mac/Linux：**
```bash
export FEISHU_APP_ID="cli_xxxxxxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxxxxxxxxxxxxxxxxxx"
export EMAIL_USER="your@email.com"        # 如启用邮件推送
export EMAIL_PASSWORD="your_auth_code"    # 邮箱授权码（非登录密码）
```

**Windows（PowerShell）：**
```powershell
$env:FEISHU_APP_ID="cli_xxxxxxxxxxxx"
$env:FEISHU_APP_SECRET="xxxxxxxxxxxxxxxxxxxxxxxx"
```

**永久生效：**
- Mac/Linux：将 export 命令写入 `~/.bashrc` 或 `~/.zshrc`
- Windows：系统属性 → 高级 → 环境变量

---

### Step 7：部署RSSHub（如需公众号采集）

如果配置了微信公众号源，需要部署RSSHub：

```bash
# 一键启动（需安装Docker）
docker run -d --name rsshub -p 1200:1200 diygod/rsshub

# 验证
curl http://localhost:1200/
```

配置文件中确认RSSHub地址：
```yaml
rsshub_url: "http://localhost:1200"
```

---

### Step 8：正式运行

#### 方式A：手动运行

```bash
# 正式运行（收集+筛选+推送）
python -m src.main --config config.yaml

# 详细日志（排查问题时用）
python -m src.main --config config.yaml --verbose
```

#### 方式B：定时自动运行（推荐）

**Mac/Linux（crontab）：**
```bash
# 编辑定时任务
crontab -e

# 添加一行：每天早上9点执行
0 9 * * * cd /path/to/industry-news-aggregator && /usr/bin/python3 -m src.main --config config.yaml >> output/run.log 2>&1
```

**Windows（任务计划程序）：**
1. 开始菜单搜索"任务计划程序"
2. 创建基本任务 → 名称填"新闻收集" → 每天触发 → 9:00
3. 操作选"启动程序" → 程序填python路径 → 参数填 `-m src.main --config config.yaml`
4. 起始位置填项目目录路径

#### 方式C：Docker一键部署（最省心）

```bash
# 设置环境变量
export FEISHU_APP_ID="cli_xxxxxxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxxxxxxxxxxxxxxxxxx"

# 启动（含RSSHub）
docker-compose up -d

# 查看日志
docker logs news-aggregator

# 手动触发一次
docker exec news-aggregator python -m src.main --config /app/config.yaml
```

#### 方式D：GitHub Actions（无需服务器）

1. 将 `config.yaml` 提交到仓库（注意去掉真实凭证）
2. 在仓库 Settings → Secrets and variables → Actions 添加Secrets：
   - `FEISHU_APP_ID`
   - `FEISHU_APP_SECRET`
   - `EMAIL_USER`（可选）
   - `EMAIL_PASSWORD`（可选）
3. 每天北京时间9:00自动执行

---

### Step 9：查看推送结果

| 渠道 | 查看位置 |
|------|---------|
| 飞书群 | 群聊消息卡片 + 文件夹中的文档 |
| 飞书云空间 | 之前创建的文件夹 |
| 邮箱 | 收件箱 |
| 本地 | `output/` 目录下的 Markdown 文件 |

---

### Step 10：日常维护

#### 排查问题

如果推送失败或没收到新闻：

```bash
# 查看详细执行日志
python -m src.main --config config.yaml --verbose

# 查看本地报告（所有推送渠道都失败时）
ls output/reports/
```

常见问题自动提示示例：
- "公众号「保观」的RSS获取失败，可能已注销" → 在微信中确认该公众号是否正常
- "无法连接RSSHub服务" → 执行 `docker ps | grep rsshub` 检查
- "筛选结果为0" → 检查关键词是否太窄或时间范围是否太短
- "飞书应用认证失败" → 检查 FEISHU_APP_ID 和 FEISHU_APP_SECRET 是否正确

#### 添加/修改信息源

直接编辑 `config.yaml` 的 `sources` 部分，下次运行自动生效：

```yaml
sources:
  - "https://finance.sina.com.cn"
  - "公众号:中国保险报"
  - "https://www.yicai.com"          # 新增源，直接加一行
```

#### 更新代码

```bash
git pull origin main
pip install -e . --upgrade
```

---

### 快速验证清单

首次使用时按此顺序验证：

| 步骤 | 命令/操作 | 预期结果 |
|------|----------|---------|
| 1. 安装 | `pip install -e .` | 无报错 |
| 2. 试运行 | `python -m src.main --config config.yaml --dry-run` | output/目录生成Markdown文件 |
| 3. 查看输出 | 打开output/目录下的.md文件 | 看到新闻标题、来源、摘要 |
| 4. 飞书推送 | 设置凭证后去掉 `--dry-run` 运行 | 飞书群收到消息卡片 |
| 5. 定时任务 | 配置 crontab 或 Docker | 每天自动执行 |

---

## 信息源格式说明

| 格式 | 说明 | 示例 |
|------|------|------|
| 普通网址 | 系统自动识别为网页/RSS | `https://finance.sina.com.cn` |
| 公众号 | 前缀"公众号:"+名称 | `公众号:中国保险报` |
| RSS地址 | 含 `/feed` 或 `/rss` 的URL | `https://36kr.com/feed` |

系统会自动探测网址类型，用户无需关心技术细节。

---

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

---

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

---

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

---

## License

MIT
