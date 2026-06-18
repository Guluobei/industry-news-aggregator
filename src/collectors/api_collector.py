"""行业新闻聚合推送器 - API收集器"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import httpx

from src.collectors.base import BaseCollector
from src.issues import ErrorIssue, IssueTracker, WarnIssue
from src.models import NewsItem
from src.utils import clean_text, fetch_url, parse_date, truncate_text

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class APICollector(BaseCollector):
    """通用API/JSON收集器"""

    def collect(self, source: str, issue_tracker: IssueTracker, **kwargs) -> list[NewsItem]:
        """
        从JSON API收集新闻

        Args:
            source: API URL
            issue_tracker: 问题追踪器
        """
        source_name = kwargs.get("source_name", source)
        headers = kwargs.get("headers", {})
        response_path = kwargs.get("response_path", "$.data")

        try:
            resp = fetch_url(source, headers=headers, timeout=20)
        except httpx.HTTPStatusError as e:
            raise ErrorIssue(
                code="API_HTTP_ERROR",
                source=source_name,
                reason=f"API「{source_name}」请求失败（HTTP {e.response.status_code}）",
                suggestion="请检查API地址和认证信息是否正确",
                detail=str(e),
            )
        except httpx.HTTPError as e:
            raise ErrorIssue(
                code="API_FETCH_FAILED",
                source=source_name,
                reason=f"API「{source_name}」获取失败：{type(e).__name__}",
                suggestion="该源本次跳过，下次执行时将重试",
                detail=str(e),
            )

        try:
            data = resp.json()
        except json.JSONDecodeError:
            raise ErrorIssue(
                code="API_NOT_JSON",
                source=source_name,
                reason=f"API「{source_name}」返回内容不是有效的JSON格式",
                suggestion="请确认该地址是JSON API",
            )

        # 按JSONPath提取数据列表
        items_data = self._extract_by_path(data, response_path)

        if not items_data or not isinstance(items_data, list):
            raise WarnIssue(
                code="API_EMPTY",
                source=source_name,
                reason=f"API「{source_name}」返回数据为空或格式不符",
                suggestion="请检查response_path配置是否正确",
            )

        items: list[NewsItem] = []
        for item in items_data:
            if not isinstance(item, dict):
                continue

            title = clean_text(
                item.get("title")
                or item.get("name")
                or item.get("subject")
                or ""
            )
            if not title:
                continue

            url = item.get("url") or item.get("link") or item.get("href") or ""
            content = clean_text(
                item.get("content")
                or item.get("body")
                or item.get("description")
                or item.get("summary")
                or ""
            )
            publish_time = parse_date(
                item.get("publish_time")
                or item.get("published_at")
                or item.get("date")
                or item.get("created_at")
            )
            author = item.get("author") or item.get("source") or ""

            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=source_name,
                    content=content,
                    summary=truncate_text(content, 300) if content else "",
                    publish_time=publish_time,
                    author=author,
                )
            )

        logger.info(f"API「{source_name}」收集到 {len(items)} 篇文章")
        return items

    def _extract_by_path(self, data: Any, path: str) -> Any:
        """简单的JSONPath提取（支持 $.key1.key2.key3 格式）"""
        if not path or path == "$":
            return data

        # 去掉 $ 前缀
        path = path.lstrip("$").lstrip(".")

        current = data
        for key in path.split("."):
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                idx = int(key)
                current = current[idx] if idx < len(current) else None
            else:
                return None
            if current is None:
                return None

        return current
