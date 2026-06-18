"""行业新闻聚合推送器 - 排序器"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.models import NewsItem

logger = logging.getLogger(__name__)


class Ranker:
    """综合打分排序器"""

    # 来源权重：官方/权威源 > 行业媒体 > 自媒体
    SOURCE_WEIGHTS = {
        # 监管/官方
        "nhsa.gov.cn": 1.5,
        "nfra.gov.cn": 1.5,
        "cbirc.gov.cn": 1.5,
        "gov.cn": 1.3,
        # 主流财经媒体
        "caixin.com": 1.3,
        "21jingji.com": 1.2,
        "yicai.com": 1.2,
        "jiemian.com": 1.1,
        "finance.sina.com.cn": 1.1,
        "finance.qq.com": 1.1,
        # 科技媒体
        "36kr.com": 1.0,
        "ifanr.com": 1.0,
        "infoq.cn": 1.0,
    }

    def rank(
        self,
        scored_items: list[tuple[NewsItem, float]],
        top_n: int = 10,
    ) -> list[NewsItem]:
        """
        综合打分排序

        评分维度：
        - 关键词得分（40%）：命中关键词数量
        - 时效性（30%）：越新分越高，指数衰减
        - 来源权重（20%）：权威源加分
        - 内容丰富度（10%）：正文长度

        Args:
            scored_items: (NewsItem, keyword_score) 列表
            top_n: 取前N条

        Returns:
            排序后的NewsItem列表
        """
        now = datetime.now(timezone.utc)
        ranked: list[tuple[NewsItem, float]] = []

        for item, kw_score in scored_items:
            # 1. 关键词得分（归一化到0-40）
            kw_component = min(kw_score * 5, 40.0)

            # 2. 时效性（0-30）：24小时内满分，7天衰减到接近0
            time_component = 0.0
            if item.publish_time:
                if item.publish_time.tzinfo is None:
                    item.publish_time = item.publish_time.replace(tzinfo=timezone.utc)
                hours_ago = (now - item.publish_time).total_seconds() / 3600
                # 指数衰减：24h=30分，48h≈18分，168h≈3分
                time_component = 30.0 * (0.5 ** (hours_ago / 24))
            else:
                time_component = 5.0  # 无日期的给基础分

            # 3. 来源权重（0-20）
            source_weight = self._get_source_weight(item.url, item.source)
            source_component = source_weight * 20.0

            # 4. 内容丰富度（0-10）
            content_len = len(item.content) if item.content else 0
            content_component = min(content_len / 200, 10.0)

            total = kw_component + time_component + source_component + content_component

            ranked.append((item, total))
            logger.debug(
                f"排序: {item.title[:30]}... "
                f"kw={kw_component:.1f} time={time_component:.1f} "
                f"src={source_component:.1f} content={content_component:.1f} "
                f"total={total:.1f}"
            )

        # 按总分降序排列
        ranked.sort(key=lambda x: x[1], reverse=True)

        result = [item for item, _ in ranked[:top_n]]
        logger.info(f"排序完成，取Top {len(result)} 条")
        return result

    def _get_source_weight(self, url: str, source_name: str) -> float:
        """获取来源权重（0-1）"""
        from src.utils import get_domain

        domain = get_domain(url).lower()

        # 精确匹配域名
        for known_domain, weight in self.SOURCE_WEIGHTS.items():
            if known_domain in domain:
                return weight

        # 公众号默认权重
        if source_name.startswith("公众号:"):
            return 0.9

        # 未知来源
        return 0.8
