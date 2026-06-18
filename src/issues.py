"""行业新闻聚合推送器 - 问题追踪与通知系统"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class IssueLevel(Enum):
    """问题级别"""
    FATAL = "fatal"    # 致命：整个流程无法执行
    ERROR = "error"    # 错误：某个源/渠道失败，其余可继续
    WARN = "warn"      # 警告：数据质量问题，流程可完成
    INFO = "info"      # 信息：正常状态提示


LEVEL_ICONS = {
    IssueLevel.FATAL: "🔴",
    IssueLevel.ERROR: "🟠",
    IssueLevel.WARN: "🟡",
    IssueLevel.INFO: "🔵",
}


@dataclass
class Issue:
    """单个问题记录"""
    code: str                   # 唯一错误码
    level: IssueLevel           # 级别
    source: str                 # 出问题的信息源/模块
    reason: str                 # 用户可读的问题描述
    suggestion: str             # 用户可操作的解决建议
    detail: str = ""            # 技术细节（可选，用于调试）

    @property
    def icon(self) -> str:
        return LEVEL_ICONS[self.level]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "icon": self.icon,
            "code": self.code,
            "source": self.source,
            "reason": self.reason,
            "suggestion": self.suggestion,
            "detail": self.detail,
        }


class IssueTracker:
    """全局问题收集器，贯穿整个流程"""

    def __init__(self) -> None:
        self._issues: list[Issue] = []

    def record(self, issue: Issue) -> None:
        """记录一个问题"""
        self._issues.append(issue)
        log_msg = f"[{issue.level.value.upper()}] {issue.code} | {issue.source}: {issue.reason}"
        if issue.level == IssueLevel.FATAL:
            logger.critical(log_msg)
        elif issue.level == IssueLevel.ERROR:
            logger.error(log_msg)
        elif issue.level == IssueLevel.WARN:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

    def has_fatal(self) -> bool:
        """是否存在致命问题"""
        return any(i.level == IssueLevel.FATAL for i in self._issues)

    def has_errors(self) -> bool:
        """是否存在错误（含致命）"""
        return any(i.level in (IssueLevel.FATAL, IssueLevel.ERROR) for i in self._issues)

    @property
    def issues(self) -> list[Issue]:
        return list(self._issues)

    @property
    def visible_issues(self) -> list[Issue]:
        """返回需要通知的问题（排除INFO级别）"""
        return [i for i in self._issues if i.level != IssueLevel.INFO]

    def get_summary(self) -> dict[str, Any]:
        """生成问题摘要，用于通知"""
        return {
            "fatal_count": sum(1 for i in self._issues if i.level == IssueLevel.FATAL),
            "error_count": sum(1 for i in self._issues if i.level == IssueLevel.ERROR),
            "warn_count": sum(1 for i in self._issues if i.level == IssueLevel.WARN),
            "total": len(self.visible_issues),
            "issues": [i.to_dict() for i in self.visible_issues],
        }

    def get_status_label(self) -> str:
        """获取执行状态标签"""
        summary = self.get_summary()
        if summary["fatal_count"] > 0:
            return "🔴 执行失败"
        elif summary["error_count"] > 0:
            return "🟠 部分失败"
        elif summary["warn_count"] > 0:
            return "🟡 有警告"
        return "🟢 全部正常"


# ========== 预定义异常 ==========

class FatalIssue(Exception):
    """致命问题异常，抛出后终止流程"""
    def __init__(self, code: str, source: str, reason: str, suggestion: str, detail: str = ""):
        self.issue = Issue(
            code=code,
            level=IssueLevel.FATAL,
            source=source,
            reason=reason,
            suggestion=suggestion,
            detail=detail,
        )
        super().__init__(reason)


class ErrorIssue(Exception):
    """错误问题异常，抛出后由调用方捕获并记录，继续执行"""
    def __init__(self, code: str, source: str, reason: str, suggestion: str, detail: str = ""):
        self.issue = Issue(
            code=code,
            level=IssueLevel.ERROR,
            source=source,
            reason=reason,
            suggestion=suggestion,
            detail=detail,
        )
        super().__init__(reason)


class WarnIssue(Exception):
    """警告问题异常，抛出后由调用方捕获并记录，继续执行"""
    def __init__(self, code: str, source: str, reason: str, suggestion: str, detail: str = ""):
        self.issue = Issue(
            code=code,
            level=IssueLevel.WARN,
            source=source,
            reason=reason,
            suggestion=suggestion,
            detail=detail,
        )
        super().__init__(reason)
