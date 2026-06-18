"""行业新闻聚合推送器 - 关键词筛选器"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.models import NewsItem
from src.utils import is_within_hours

if TYPE_CHECKING:
    from src.config import FilterConfig
    from src.issues import IssueTracker

logger = logging.getLogger(__name__)


class KeywordFilter:
    """关键词筛选器：支持包含/排除/加分逻辑"""

    def filter(
        self,
        items: list[NewsItem],
        config: "FilterConfig",
        issue_tracker: "IssueTracker",
    ) -> list[tuple[NewsItem, float]]:
        """
        筛选并打分

        Returns:
            (NewsItem, score) 列表，已按分数降序排列
        """
        keywords = config.keywords
        exclude = config.exclude
        hours = config.hours

        if not keywords:
            # 无关键词 → 仅做时间过滤
            return [
                (item, 0.0)
                for item in items
                if is_within_hours(item.publish_time, hours)
            ]

        scored: list[tuple[NewsItem, float]] = []

        for item in items:
            # 时间范围过滤
            if not is_within_hours(item.publish_time, hours):
                continue

            text = f"{item.title} {item.content} {item.summary}".lower()

            # 排除关键词：命中任一则丢弃
            excluded = False
            for kw in exclude:
                if kw.lower() in text:
                    excluded = True
                    break
            if excluded:
                continue

            # 关键词匹配：任一命中即保留，并计算加分
            matched_keywords = []
            score = 0.0
            for kw in keywords:
                if kw.lower() in text:
                    matched_keywords.append(kw)
                    score += 1.0

            if score > 0:
                # 标题中命中额外加分
                title_lower = item.title.lower()
                for kw in keywords:
                    if kw.lower() in title_lower:
                        score += 0.5

                item.extra["matched_keywords"] = matched_keywords
                scored.append((item, score))

        logger.info(
            f"关键词筛选：{len(items)} → {len(scored)} 条 "
            f"(关键词: {keywords}, 排除: {exclude})"
        )
        return scored
