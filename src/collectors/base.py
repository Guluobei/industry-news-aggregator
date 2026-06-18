"""行业新闻聚合推送器 - 收集器基类与注册表"""

from __future__ import annotations

import abc
import logging
from typing import TYPE_CHECKING

from src.models import NewsItem

if TYPE_CHECKING:
    from src.issues import IssueTracker

logger = logging.getLogger(__name__)


class BaseCollector(abc.ABC):
    """所有收集器的统一接口"""

    @abc.abstractmethod
    def collect(self, source: str, issue_tracker: "IssueTracker", **kwargs) -> list[NewsItem]:
        """
        从指定源收集新闻

        Args:
            source: 信息源标识（URL或名称）
            issue_tracker: 问题追踪器
            **kwargs: 额外参数

        Returns:
            NewsItem列表
        """
        ...


class CollectorRegistry:
    """收集器注册表：根据源类型自动选择收集器"""

    _registry: dict[str, type[BaseCollector]] = {}

    @classmethod
    def register(cls, source_type: str, collector_class: type[BaseCollector]) -> None:
        """注册收集器"""
        cls._registry[source_type] = collector_class
        logger.debug(f"注册收集器: {source_type} -> {collector_class.__name__}")

    @classmethod
    def get(cls, source_type: str) -> BaseCollector | None:
        """获取收集器实例"""
        collector_class = cls._registry.get(source_type)
        if collector_class is None:
            return None
        return collector_class()

    @classmethod
    def get_registered_types(cls) -> list[str]:
        """获取已注册的收集器类型"""
        return list(cls._registry.keys())
