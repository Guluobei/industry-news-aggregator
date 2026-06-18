"""行业新闻聚合推送器 - RSS收集器"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import feedparser
import httpx

from src.collectors.base import BaseCollector
from src.issues import ErrorIssue, IssueTracker, WarnIssue
from src.models import NewsItem
from src.utils import clean_text, default_headers, fetch_url, parse_date, truncate_text

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    """RSS/Atom源收集器"""

    def collect(self, source: str, issue_tracker: IssueTracker, **kwargs) -> list[NewsItem]:
        """
        从RSS源收集新闻

        Args:
            source: RSS源URL
            issue_tracker: 问题追踪器
        """
        # 检查是否有detector发现的RSS URL覆盖
        rss_url = source
        if hasattr(issue_tracker, "_rss_overrides") and source in issue_tracker._rss_overrides:
            rss_url = issue_tracker._rss_overrides[source]

        source_name = kwargs.get("source_name", rss_url)

        try:
            resp = fetch_url(rss_url, timeout=20)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ErrorIssue(
                    code="RSS_NOT_FOUND",
                    source=source_name,
                    reason=f"RSS源「{source_name}」返回404，地址可能已失效",
                    suggestion="请检查RSS地址是否正确，或该源是否已停止服务",
                )
            raise ErrorIssue(
                code="RSS_HTTP_ERROR",
                source=source_name,
                reason=f"RSS源「{source_name}」请求失败（HTTP {e.response.status_code}）",
                suggestion="该源本次跳过，下次执行时将重试",
                detail=str(e),
            )
        except httpx.HTTPError as e:
            raise ErrorIssue(
                code="RSS_FETCH_FAILED",
                source=source_name,
                reason=f"RSS源「{source_name}」获取失败：{type(e).__name__}",
                suggestion="该源本次跳过，下次执行时将重试",
                detail=str(e),
            )

        # 解析RSS
        feed = feedparser.parse(resp.text)

        if feed.bozo and not feed.entries:
            raise ErrorIssue(
                code="RSS_PARSE_ERROR",
                source=source_name,
                reason=f"RSS源「{source_name}」解析失败，内容格式可能不正确",
                suggestion="请确认该地址是有效的RSS/Atom源",
                detail=str(getattr(feed, "bozo_exception", "")),
            )

        if not feed.entries:
            raise WarnIssue(
                code="RSS_EMPTY",
                source=source_name,
                reason=f"RSS源「{source_name}」在指定时间范围内没有新文章",
                suggestion="正常现象，下次执行时将自动检查",
            )

        # 获取feed标题作为来源名
        feed_title = feed.feed.get("title", source_name) if hasattr(feed, "feed") else source_name

        items: list[NewsItem] = []
        for entry in feed.entries:
            title = clean_text(entry.get("title", ""))
            if not title:
                continue

            link = entry.get("link", "")
            content = clean_text(
                entry.get("content", [{}])[0].get("value", "")
                if entry.get("content")
                else entry.get("summary", entry.get("description", ""))
            )
            summary = truncate_text(content, 300) if content else ""
            publish_time = parse_date(entry.get("published") or entry.get("updated"))
            author = entry.get("author", "")

            items.append(
                NewsItem(
                    title=title,
                    url=link,
                    source=feed_title,
                    content=content,
                    summary=summary,
                    publish_time=publish_time,
                    author=author,
                )
            )

        logger.info(f"RSS源「{feed_title}」收集到 {len(items)} 篇文章")
        return items
