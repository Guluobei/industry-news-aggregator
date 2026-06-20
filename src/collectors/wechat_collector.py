"""行业新闻聚合推送器 - 微信公众号收集器（多后端适配器）

核心原则：
- 微信公众号是"灰色"采集路径，所有方案都有失效风险
- 默认推荐微信读书方案（wewe-rss），相对最稳定
- 支持多后端配置，用户可按需选择
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import feedparser
import httpx
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.collectors.rss_collector import RSSCollector
from src.issues import ErrorIssue, IssueTracker, WarnIssue
from src.models import NewsItem
from src.utils import fetch_url, parse_date

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class WechatBackend:
    """微信采集后端抽象基类"""

    def __init__(self, name: str, base_url: str, **options):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.options = options

    def health_check(self) -> bool:
        """检查后端服务是否可用"""
        raise NotImplementedError

    def list_articles(self, feed_id: str, limit: int = 30) -> list[dict]:
        """列出指定 feed 的最近文章

        Returns:
            list of dict: 每个 dict 至少包含 title, url, publish_time
        """
        raise NotImplementedError

    def find_feed_id(self, account_name: str) -> str | None:
        """通过公众号名称查找 feed_id"""
        raise NotImplementedError


class WeWeRSSBackend(WechatBackend):
    """微信读书后端（推荐方案）

    优点：
    - 不需要扫码授权你的微信
    - API 相对稳定（更新频率比 RSSHub 慢但更可靠）
    - 维护活跃（cooderl/wewe-rss，2024-12 最新 v2.6.1）

    缺点：
    - 部分小众公众号不在微信读书内
    - 走 weread.111965.xyz 中转（有隐私风险，但作者声明不保存数据）
    - 长期看仍依赖腾讯 API 策略

    部署：参考 https://github.com/cooderl/wewe-rss
    """

    def health_check(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/", timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def find_feed_id(self, account_name: str) -> str | None:
        """wewe-rss 没有自动发现接口，需要用户先在 Web UI 添加订阅并获取 feed_id"""
        return None

    def list_articles(self, feed_id: str, limit: int = 30) -> list[dict]:
        """通过 RSS 接口拉取文章列表

        feed_id 格式: MP_WXS_xxxxx
        API 路径: /feeds/{feed_id}.rss
        """
        url = f"{self.base_url}/feeds/{feed_id}.rss"
        resp = fetch_url(url, timeout=20)
        feed = feedparser.parse(resp.text)

        items = []
        for entry in feed.entries[:limit]:
            publish_time = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                from datetime import datetime, timezone

                publish_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "published"):
                publish_time = parse_date(entry.published)

            items.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "publish_time": publish_time,
                "summary": entry.get("summary", ""),
                "author": entry.get("author", ""),
            })
        return items


class RSSHubBackend(WechatBackend):
    """RSSHub 后端

    优点：
    - 覆盖率高（可搜索/发现公众号）
    - 维护活跃（RSSHub 组织）

    缺点：
    - 公开实例屏蔽微信路由
    - 需自部署，配置相对复杂
    - 微信路径需启用对应路由（部分需登录态）
    """

    def health_check(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/", timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def find_feed_id(self, account_name: str) -> str | None:
        """通过 /wechat/mp/search/{name} 搜索公众号ID"""
        search_url = f"{self.base_url}/wechat/mp/search/{account_name}"
        try:
            resp = fetch_url(search_url, timeout=15)
            feed = feedparser.parse(resp.text)
            if feed.entries:
                link = feed.entries[0].get("link", "")
                if "__biz" in link:
                    match = re.search(r"__biz=([^&]+)", link)
                    if match:
                        return match.group(1)
            return None
        except Exception as e:
            logger.debug(f"RSSHub搜索公众号ID失败: {e}")
            return None

    def list_articles(self, feed_id: str, limit: int = 30) -> list[dict]:
        """通过 /wechat/mp/{id} 拉取文章"""
        rss_url = f"{self.base_url}/wechat/mp/{feed_id}"
        resp = fetch_url(rss_url, timeout=20)
        feed = feedparser.parse(resp.text)

        items = []
        for entry in feed.entries[:limit]:
            publish_time = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                from datetime import datetime, timezone

                publish_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "published"):
                publish_time = parse_date(entry.published)

            items.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "publish_time": publish_time,
                "summary": entry.get("summary", ""),
                "author": entry.get("author", ""),
            })
        return items


class SogouBackend(WechatBackend):
    """搜狗微信搜索后端（最后降级方案）

    优点：无需部署任何服务
    缺点：JS 渲染导致解析困难，仅作为占位降级，不保证能拿到内容
    """

    SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"

    def health_check(self) -> bool:
        """搜狗永远"可用"（不抛异常即视为可用）"""
        return True

    def find_feed_id(self, account_name: str) -> str | None:
        try:
            params = {"type": "1", "query": account_name}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Referer": "https://weixin.sogou.com/",
            }
            resp = httpx.get(self.SOGOU_SEARCH_URL, params=params, headers=headers, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            matches = re.findall(r"__biz=([A-Za-z0-9%+/=]+)", resp.text)
            return matches[0] if matches else None
        except Exception as e:
            logger.debug(f"搜狗搜索公众号ID失败: {e}")
            return None

    def list_articles(self, feed_id: str, limit: int = 30) -> list[dict]:
        """搜狗的反爬导致难以解析，仅作为占位"""
        raise NotImplementedError("搜狗路径反爬严重，不提供文章列表接口")


# 后端注册表
BACKEND_REGISTRY: dict[str, type[WechatBackend]] = {
    "wewe-rss": WeWeRSSBackend,
    "rsshub": RSSHubBackend,
    "sogou": SogouBackend,
}


class WeChatCollector(BaseCollector):
    """微信公众号收集器（多后端适配器）

    支持后端（按推荐顺序）：
    1. wewe-rss（微信读书） - 默认推荐，平衡稳定性和安全性
    2. rsshub（自部署）    - 覆盖率最高，需自部署
    3. sogou（搜狗）       - 兜底方案，效果有限

    公众号 feed_id 格式：
    - wewe-rss: "MP_WXS_xxxxx"（用户在 Web UI 添加订阅后获得）
    - rsshub: "__biz=xxxxx"（系统自动搜索）
    - sogou: "__biz=xxxxx"（系统自动搜索）

    配置示例：
    ```yaml
    wechat_accounts:
      - name: "中国保险报"
        backend: "wewe-rss"
        feed_id: "MP_WXS_3083075681"  # 在 wewe-rss Web UI 添加后获得
      - name: "保观"
        backend: "rsshub"
        # 无需 feed_id，系统自动搜索
    ```
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.backends: dict[str, WechatBackend] = {}
        self._init_backends()

    def _init_backends(self):
        """根据配置初始化后端实例"""
        wechat_config = (self.config or {}).get("wechat", {})

        # 默认后端配置
        defaults = {
            "wewe-rss": {"url": "http://localhost:4000", "enabled": True},
            "rsshub": {"url": "http://localhost:1200", "enabled": True},
        }

        for backend_name, backend_cls in BACKEND_REGISTRY.items():
            backend_conf = wechat_config.get(backend_name, {})
            cfg = {**defaults.get(backend_name, {}), **backend_conf}
            if cfg.get("enabled", True):
                self.backends[backend_name] = backend_cls(
                    name=backend_name,
                    base_url=cfg.get("url", defaults.get(backend_name, {}).get("url", "")),
                )

    def collect(self, source: str, issue_tracker: IssueTracker, **kwargs) -> list[NewsItem]:
        """
        从微信公众号收集新闻

        Args:
            source: "公众号:名称[:backend=xxx:feed_id=xxx]" 格式
            issue_tracker: 问题追踪器
        """
        # 解析 source 中的元数据
        meta = self._parse_source(source)
        account_name = meta["name"]
        specified_backend = meta.get("backend")
        specified_feed_id = meta.get("feed_id")
        source_name = f"公众号:{account_name}"

        # 决定后端优先级
        backend_order = self._resolve_backend_order(specified_backend)
        if specified_feed_id:
            # 用户已指定 feed_id，直接走对应后端
            backend = self.backends.get(specified_backend or "wewe-rss")
            if not backend:
                raise ErrorIssue(
                    code="WECHAT_BACKEND_UNAVAILABLE",
                    source=source_name,
                    reason=f"指定的后端「{specified_backend}」未启用或未配置",
                    suggestion="检查 config 中 wechat.{specified_backend} 配置",
                )
            return self._collect_from_backend(backend, specified_feed_id, account_name, source_name, issue_tracker)

        # 多后端降级流程
        last_error = None
        for backend_name in backend_order:
            if backend_name not in self.backends:
                continue
            backend = self.backends[backend_name]

            if not backend.health_check():
                issue_tracker.record(WarnIssue(
                    code=f"WECHAT_BACKEND_DOWN_{backend_name.upper().replace('-', '_')}",
                    source=f"微信后端:{backend_name}",
                    reason=f"后端「{backend_name}」不可用，跳过",
                    suggestion="如需启用此后端，请先部署对应服务",
                ).issue)
                continue

            # 尝试查找 feed_id
            feed_id = backend.find_feed_id(account_name)
            if not feed_id:
                continue

            try:
                return self._collect_from_backend(backend, feed_id, account_name, source_name, issue_tracker)
            except ErrorIssue as e:
                last_error = e
                issue_tracker.record(WarnIssue(
                    code=f"WECHAT_BACKEND_FAILED_{backend_name.upper().replace('-', '_')}",
                    source=source_name,
                    reason=f"后端「{backend_name}」采集失败：{e.issue.reason}",
                    suggestion="尝试下一个后端",
                ).issue)
                continue

        # 全部后端失败
        if last_error:
            raise ErrorIssue(
                code="WECHAT_ALL_BACKENDS_FAILED",
                source=source_name,
                reason=f"所有微信采集后端均失败，最后错误：{last_error.issue.reason}",
                suggestion="请在 wewe-rss Web UI 手动添加公众号订阅，并填入 feed_id",
            )
        raise ErrorIssue(
            code="WECHAT_NOT_FOUND",
            source=source_name,
            reason=f"未找到公众号「{account_name}」的 feed_id",
            suggestion=(
                "请在 wewe-rss Web UI 手动添加公众号订阅（推荐），"
                "或在 source 中指定 backend 和 feed_id"
            ),
        )

    def _collect_from_backend(
        self,
        backend: WechatBackend,
        feed_id: str,
        account_name: str,
        source_name: str,
        issue_tracker: IssueTracker,
    ) -> list[NewsItem]:
        """从指定后端采集文章"""
        try:
            raw_items = backend.list_articles(feed_id, limit=30)
        except Exception as e:
            raise ErrorIssue(
                code="WECHAT_FETCH_FAILED",
                source=source_name,
                reason=f"通过「{backend.name}」拉取文章失败：{type(e).__name__}",
                detail=str(e),
                suggestion="检查后端服务状态或网络连接",
            )

        items = []
        for raw in raw_items:
            if not raw.get("title") or not raw.get("url"):
                continue
            items.append(NewsItem(
                title=raw["title"],
                url=raw["url"],
                source=source_name,
                summary=raw.get("summary", "")[:300] if raw.get("summary") else "",
                content=raw.get("summary", ""),
                publish_time=raw.get("publish_time"),
                author=raw.get("author", ""),
            ))

        if not items:
            raise WarnIssue(
                code="WECHAT_EMPTY",
                source=source_name,
                reason=f"公众号「{account_name}」在指定时间范围内没有新文章",
                suggestion="正常现象，下次执行时将自动检查",
            )

        logger.info(f"公众号「{account_name}」通过「{backend.name}」收集到 {len(items)} 篇文章")
        return items

    def _resolve_backend_order(self, specified: str | None) -> list[str]:
        """解析后端优先级

        Args:
            specified: 用户在 source 中指定的后端名称

        Returns:
            后端名称列表（按尝试顺序）
        """
        # 默认顺序：wewe-rss > rsshub > sogou
        default_order = ["wewe-rss", "rsshub", "sogou"]
        if specified:
            # 把指定后端提到最前
            return [specified] + [b for b in default_order if b != specified]
        return [b for b in default_order if b in self.backends]

    def _parse_source(self, source: str) -> dict:
        """解析 source 字符串

        支持格式：
        - "公众号:中国保险报"
        - "公众号:中国保险报:backend=wewe-rss"
        - "公众号:中国保险报:backend=wewe-rss:feed_id=MP_WXS_123"
        - "公众号:中国保险报:feed_id=MP_WXS_123"
        """
        if source.startswith("公众号:") or source.startswith("公众号："):
            content = source.split(":", 1)[-1].split("：", 1)[-1].strip()
        else:
            content = source.strip()

        parts = content.split(":")
        result = {"name": parts[0].strip()}

        for part in parts[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip()
        return result
