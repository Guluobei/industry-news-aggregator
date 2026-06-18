"""行业新闻聚合推送器 - 筛选引擎（整合关键词/去重/排序）"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.filters.dedup import Deduplicator
from src.filters.keyword_filter import KeywordFilter
from src.filters.ranker import Ranker
from src.issues import IssueTracker, WarnIssue
from src.models import NewsItem

if TYPE_CHECKING:
    from src.config import FilterConfig

logger = logging.getLogger(__name__)


class FilterEngine:
    """筛选引擎：整合关键词筛选、去重、排序"""

    def __init__(self) -> None:
        self.keyword_filter = KeywordFilter()
        self.deduplicator = Deduplicator(title_threshold=80.0)
        self.ranker = Ranker()

    def process(
        self,
        items: list[NewsItem],
        config: "FilterConfig",
        issue_tracker: IssueTracker,
    ) -> list[NewsItem]:
        """
        完整筛选流程：去重 → 关键词筛选 → 排序

        Args:
            items: 收集到的所有新闻
            config: 筛选配置
            issue_tracker: 问题追踪器

        Returns:
            筛选排序后的Top N新闻列表
        """
        if not items:
            issue_tracker.record(WarnIssue(
                code="NO_INPUT",
                source="筛选引擎",
                reason="收集到的新闻为空，无法进行筛选",
                suggestion="请检查信息源是否正常工作",
            ).issue)
            return []

        logger.info(f"筛选引擎开始处理：{len(items)} 条新闻")

        # Step 1: 去重
        deduped = self.deduplicator.deduplicate(items)

        # Step 2: 关键词筛选与打分
        scored = self.keyword_filter.filter(deduped, config, issue_tracker)

        # Step 3: 检查筛选结果
        top_n = config.top_n

        if len(scored) == 0:
            issue_tracker.record(WarnIssue(
                code="NO_RESULTS",
                source="筛选引擎",
                reason="所有信息源在指定时间范围内均未命中关键词，筛选结果为0",
                suggestion=f"请检查：1) 关键词是否过于狭窄 2) 时间范围（{config.hours}小时）是否太短 3) 信息源是否正常",
            ).issue)
            return []

        if len(scored) < top_n:
            issue_tracker.record(WarnIssue(
                code="INSUFFICIENT_RESULTS",
                source="筛选引擎",
                reason=f"筛选后仅{len(scored)}条新闻，不足目标{top_n}条",
                suggestion="已按实际数量推送，可考虑放宽关键词或扩大时间范围",
            ).issue)

        # Step 4: 综合排序
        ranked = self.ranker.rank(scored, top_n=top_n)

        logger.info(f"筛选引擎完成：{len(items)} → {len(ranked)} 条")
        return ranked
