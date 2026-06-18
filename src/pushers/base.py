"""行业新闻聚合推送器 - 推送器基类"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from src.models import NewsItem

if TYPE_CHECKING:
    from src.issues import IssueTracker
    from src.models import ExecutionResult


class BasePusher(abc.ABC):
    """所有推送器的统一接口"""

    @abc.abstractmethod
    def push(
        self,
        items: list[NewsItem],
        issue_tracker: "IssueTracker",
        result: "ExecutionResult",
        **kwargs,
    ) -> bool:
        """
        推送新闻到目标渠道

        Args:
            items: 新闻列表
            issue_tracker: 问题追踪器
            result: 执行结果（用于更新推送状态）
            **kwargs: 渠道特定参数

        Returns:
            是否推送成功
        """
        ...
