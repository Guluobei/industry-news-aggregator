"""行业新闻聚合推送器 - 微信公众号收集器"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from src.collectors.base import BaseCollector
from src.collectors.rss_collector import RSSCollector
from src.issues import ErrorIssue, FatalIssue, IssueTracker, WarnIssue
from src.models import NewsItem
from src.utils import fetch_url

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class WeChatCollector(BaseCollector):
    """微信公众号收集器：通过RSSHub获取公众号文章"""

    # 已知公众号名称 → 微信ID映射（可手动维护扩展）
    KNOWN_ACCOUNTS: dict[str, str] = {
        "中国保险报": "zgbxb_2012",
        "保观": "Insurance-Review",
        "银保监微课堂": "cbirc_wechat",
        "慧保天下": "hbtxgb",
        "券商中国": "quanshangcn",
        "21世纪经济报道": "jjbd21",
        "财新网": "caixinwang",
        "澎湃新闻": "thepapernews",
    }

    def collect(self, source: str, issue_tracker: IssueTracker, **kwargs) -> list[NewsItem]:
        """
        从微信公众号收集新闻

        Args:
            source: "公众号:名称" 格式或公众号名称
            issue_tracker: 问题追踪器
        """
        rsshub_url = kwargs.get("rsshub_url", "http://localhost:1200")

        # 解析公众号名称
        account_name = self._parse_account_name(source)
        source_name = f"公众号:{account_name}"

        # Step 1: 检查RSSHub是否可用
        self._check_rsshub_health(rsshub_url, issue_tracker)

        # Step 2: 获取微信ID
        wechat_id = self.KNOWN_ACCOUNTS.get(account_name)

        if not wechat_id:
            wechat_id = self._search_account_id(account_name, rsshub_url)

        if not wechat_id:
            raise ErrorIssue(
                code="WECHAT_NOT_FOUND",
                source=source_name,
                reason=f"未找到公众号「{account_name}」，可能名称有误或该公众号未被收录",
                suggestion="请确认公众号名称是否正确（区分大小写），或在配置中手动添加微信ID",
            )

        # Step 3: 通过RSSHub获取文章
        rss_url = f"{rsshub_url.rstrip('/')}/wechat/mp/{wechat_id}"

        try:
            items = RSSCollector().collect(rss_url, issue_tracker, source_name=source_name)
        except ErrorIssue as e:
            # RSSHub返回404 → 公众号可能已注销
            if "404" in e.issue.reason or "NOT_FOUND" in e.issue.code:
                raise ErrorIssue(
                    code="WECHAT_INVALID",
                    source=source_name,
                    reason=f"公众号「{account_name}」的RSS获取失败，可能已注销或停止更新",
                    suggestion="请在微信中搜索确认该公众号是否仍正常运营",
                    detail=e.issue.detail,
                )
            raise

        # Step 4: 检查是否长期无更新
        if items:
            from datetime import datetime, timezone

            latest = items[0]
            if latest.publish_time:
                now = datetime.now(timezone.utc)
                if latest.publish_time.tzinfo is None:
                    latest.publish_time = latest.publish_time.replace(tzinfo=timezone.utc)
                days_since = (now - latest.publish_time).days
                if days_since > 30:
                    issue_tracker.record(WarnIssue(
                        code="WECHAT_STALE",
                        source=source_name,
                        reason=f"公众号「{account_name}」已超过{days_since}天未更新，最近一篇文章发布于{latest.publish_time.strftime('%Y-%m-%d')}",
                        suggestion="如确认该公众号已停更，建议从配置中移除",
                    ).issue)

        if not items:
            raise WarnIssue(
                code="WECHAT_EMPTY",
                source=source_name,
                reason=f"公众号「{account_name}」在指定时间范围内没有发布新文章",
                suggestion="正常现象，下次执行时将自动检查",
            )

        logger.info(f"公众号「{account_name}」收集到 {len(items)} 篇文章")
        return items

    def _parse_account_name(self, source: str) -> str:
        """从源标识中解析公众号名称"""
        if source.startswith("公众号:") or source.startswith("公众号："):
            return source.split(":", 1)[-1].split("：", 1)[-1].strip()
        return source.strip()

    def _check_rsshub_health(self, rsshub_url: str, issue_tracker: IssueTracker) -> None:
        """检查RSSHub服务是否可用"""
        try:
            resp = httpx.get(f"{rsshub_url.rstrip('/')}/", timeout=10)
            if resp.status_code != 200:
                raise FatalIssue(
                    code="RSSHUB_DOWN",
                    source="RSSHub服务",
                    reason=f"RSSHub服务异常（HTTP {resp.status_code}），微信公众号将无法采集",
                    suggestion="请检查RSSHub服务是否正常运行：docker ps | grep rsshub",
                )
        except httpx.ConnectError:
            raise FatalIssue(
                code="RSSHUB_UNREACHABLE",
                source="RSSHub服务",
                reason="无法连接RSSHub服务，微信公众号将无法采集",
                suggestion="请检查RSSHub是否已启动：docker-compose ps",
            )
        except httpx.TimeoutException:
            raise FatalIssue(
                code="RSSHUB_TIMEOUT",
                source="RSSHub服务",
                reason="RSSHub服务响应超时，微信公众号将无法采集",
                suggestion="请检查RSSHub服务负载是否过高，或重启服务",
            )
        except FatalIssue:
            raise
        except Exception as e:
            logger.debug(f"RSSHub健康检查异常: {e}")

    def _search_account_id(self, name: str, rsshub_url: str) -> str | None:
        """通过RSSHub搜索接口查找公众号ID"""
        search_url = f"{rsshub_url.rstrip('/')}/wechat/mp/search/{name}"
        try:
            resp = fetch_url(search_url, timeout=15)
            # 解析RSS结果，提取第一个匹配的公众号文章链接中的ID
            import feedparser

            feed = feedparser.parse(resp.text)
            if feed.entries:
                # 从第一篇文章链接中提取公众号ID
                link = feed.entries[0].get("link", "")
                # 微信文章链接格式: https://mp.weixin.qq.com/s/xxx 或包含__biz参数
                if "__biz" in link:
                    import re

                    match = re.search(r"__biz=([^&]+)", link)
                    if match:
                        return match.group(1)
            return None
        except Exception as e:
            logger.debug(f"搜索公众号ID失败: {e}")
            return None
