"""行业新闻聚合推送器 - 去重器"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from rapidfuzz import fuzz

from src.models import NewsItem

logger = logging.getLogger(__name__)


class Deduplicator:
    """新闻去重器：基于标题相似度和URL"""

    def __init__(self, title_threshold: float = 80.0) -> None:
        """
        Args:
            title_threshold: 标题相似度阈值（0-100），超过则视为重复
        """
        self.title_threshold = title_threshold

    def deduplicate(self, items: list[NewsItem]) -> list[NewsItem]:
        """去重，保留较新或内容更丰富的条目"""
        if not items:
            return []

        result: list[NewsItem] = []
        seen_titles: list[str] = []
        seen_urls: set[str] = set()

        for item in items:
            # URL完全相同 → 去重
            if item.url and item.url in seen_urls:
                continue
            if item.url:
                seen_urls.add(item.url)

            # 标题相似度检查
            is_dup = False
            for seen_title in seen_titles:
                similarity = fuzz.ratio(item.title.lower(), seen_title.lower())
                if similarity >= self.title_threshold:
                    is_dup = True
                    logger.debug(
                        f"去重：「{item.title}」与「{seen_title}」相似度 {similarity:.1f}%"
                    )
                    break

            if not is_dup:
                result.append(item)
                seen_titles.append(item.title)

        removed = len(items) - len(result)
        if removed > 0:
            logger.info(f"去重：{len(items)} → {len(result)} 条（移除 {removed} 条重复）")

        return result
