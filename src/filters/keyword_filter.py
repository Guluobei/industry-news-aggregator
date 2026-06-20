"""行业新闻聚合推送器 - 关键词筛选器

增强能力：
- 同义词支持（如"健康险"和"健康保险"）
- 标题权重 vs 内容权重区分
- 中文友好的部分匹配
- 行业关键词包（如保险行业预设）
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from src.models import NewsItem
from src.utils import is_within_hours

if TYPE_CHECKING:
    from src.config import FilterConfig
    from src.issues import IssueTracker

logger = logging.getLogger(__name__)


# 行业同义词词典（按行业分类）
# 用户配置关键词时，系统会自动展开同义词
INDUSTRY_SYNONYMS: dict[str, list[str]] = {
    # 保险行业
    "健康险": ["健康险", "健康保险", "医疗险", "医疗保险", "重疾险", "重疾保险"],
    "车险": ["车险", "车保险", "车辆保险", "机动车辆保险"],
    "寿险": ["寿险", "人寿保险", "人身保险", "人寿险"],
    "财产险": ["财产险", "财产保险", "财险"],
    "意外险": ["意外险", "意外伤害保险", "意外伤害险"],
    "养老险": ["养老险", "养老保险", "年金险", "年金保险"],
    "保险": ["保险", "险企", "险种", "保单", "投保", "承保", "理赔"],
    "监管": ["监管", "金融监管", "银保监", "金融监管总局", "保监会", "银保监会"],
    # 金融行业
    "银行": ["银行", "银行业", "商业银行", "央行", "中央银行"],
    "证券": ["证券", "券商", "证券公司", "证券交易所"],
    "基金": ["基金", "公募基金", "私募基金", "基金管理"],
    # 通用
    "AI": ["AI", "人工智能", "AIGC", "大模型", "LLM", "GPT"],
    "数字化": ["数字化", "数智化", "信息化", "数字转型"],
}

# 反向索引：每个同义词 → 主关键词
_SYNONYM_INDEX: dict[str, str] = {}
for _main, _aliases in INDUSTRY_SYNONYMS.items():
    for _alias in _aliases:
        _SYNONYM_INDEX[_alias.lower()] = _main


class KeywordFilter:
    """关键词筛选器：支持包含/排除/加分/同义词"""

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
        # 展开同义词：用户配置"健康险" → 自动包含"医疗保险"等
        expanded_keywords = self._expand_synonyms(config.keywords)
        expanded_exclude = self._expand_synonyms(config.exclude)
        hours = config.hours

        if not expanded_keywords:
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

            # 准备匹配文本（标题权重更高）
            title = item.title or ""
            content = (item.content or "") + (item.summary or "")
            title_lower = title.lower()
            content_lower = content.lower()

            # ========== 排除关键词（先做排除）==========
            excluded = False
            for kw in expanded_exclude:
                if kw.lower() in title_lower or kw.lower() in content_lower:
                    excluded = True
                    break
            if excluded:
                continue

            # ========== 包含关键词打分 ==========
            matched_main_kws: set[str] = set()  # 主关键词（去重）
            score = 0.0

            for kw in expanded_keywords:
                kw_lower = kw.lower()
                in_title = kw_lower in title_lower
                in_content = kw_lower in content_lower

                if in_title or in_content:
                    # 找到这个词对应的主关键词
                    main_kw = _SYNONYM_INDEX.get(kw_lower, kw)
                    matched_main_kws.add(main_kw)

                    # 基础分
                    score += 1.0

                    # 标题命中权重高
                    if in_title:
                        score += 0.8
                        # 完全匹配标题（关键词是标题的核心词）额外加分
                        if self._is_keyword_central(kw, title):
                            score += 0.3

            if score > 0:
                # 多个不同主关键词命中奖励（覆盖面广）
                if len(matched_main_kws) >= 3:
                    score += 0.5
                elif len(matched_main_kws) >= 2:
                    score += 0.2

                item.extra["matched_keywords"] = list(matched_main_kws)
                scored.append((item, score))

        logger.info(
            f"关键词筛选：{len(items)} → {len(scored)} 条 "
            f"(关键词: {config.keywords} [已展开同义词], 排除: {config.exclude})"
        )
        return scored

    def _expand_synonyms(self, keywords: list[str]) -> list[str]:
        """展开同义词

        用户配置 ["健康险", "AI"] →
        展开为 ["健康险", "健康保险", "医疗险", "医疗保险", "重疾险", "重疾保险", "AI", "人工智能", ...]

        这样只要文章中出现任一同义词，都能匹配上
        """
        if not keywords:
            return []

        expanded: list[str] = []
        seen: set[str] = set()  # 避免重复

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in seen:
                continue
            seen.add(kw_lower)
            expanded.append(kw)

            # 如果这个词在同义词词典中，添加所有别名
            if kw in INDUSTRY_SYNONYMS:
                for alias in INDUSTRY_SYNONYMS[kw]:
                    alias_lower = alias.lower()
                    if alias_lower not in seen:
                        seen.add(alias_lower)
                        expanded.append(alias)
            elif kw_lower in _SYNONYM_INDEX:
                # 用户配置的就是别名，找到主关键词，添加其他别名
                main_kw = _SYNONYM_INDEX[kw_lower]
                if main_kw in INDUSTRY_SYNONYMS:
                    for alias in INDUSTRY_SYNONYMS[main_kw]:
                        alias_lower = alias.lower()
                        if alias_lower not in seen:
                            seen.add(alias_lower)
                            expanded.append(alias)

        return expanded

    def _is_keyword_central(self, keyword: str, title: str) -> bool:
        """判断关键词是否在标题中处于核心位置

        判断依据：
        - 关键词出现在标题前30%位置
        - 或标题较短（< 20字）时出现在中段
        """
        if len(title) == 0:
            return False

        pos = title.find(keyword)
        if pos < 0:
            return False

        # 在标题前30%位置
        return pos / len(title) < 0.3
