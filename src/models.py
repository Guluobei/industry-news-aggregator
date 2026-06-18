"""行业新闻聚合推送器 - 数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NewsItem:
    """单条新闻数据模型"""
    title: str                           # 标题
    url: str                             # 原文链接
    source: str                          # 来源名称
    content: str = ""                    # 正文内容
    summary: str = ""                    # 摘要
    publish_time: datetime | None = None # 发布时间
    author: str = ""                     # 作者
    extra: dict[str, Any] = field(default_factory=dict)  # 扩展字段

    @property
    def publish_time_str(self) -> str:
        """格式化发布时间"""
        if self.publish_time:
            return self.publish_time.strftime("%Y-%m-%d %H:%M")
        return "未知时间"

    @property
    def publish_time_short(self) -> str:
        """短格式发布时间"""
        if self.publish_time:
            return self.publish_time.strftime("%Y-%m-%d")
        return "未知"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "content": self.content,
            "summary": self.summary,
            "publish_time": self.publish_time_str if self.publish_time else None,
            "author": self.author,
            "extra": self.extra,
        }


@dataclass
class ExecutionResult:
    """执行结果汇总"""
    date: str                                    # 执行日期
    total_sources: int = 0                       # 总信息源数
    success_sources: int = 0                     # 成功采集的源数
    failed_sources: int = 0                      # 失败的源数
    total_collected: int = 0                     # 收集到的文章总数
    filtered_count: int = 0                      # 筛选后的文章数
    pushed_channels: list[str] = field(default_factory=list)  # 成功推送的渠道
    failed_channels: list[str] = field(default_factory=list)  # 失败的渠道
    doc_url: str = ""                            # 生成的文档链接

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "total_sources": self.total_sources,
            "success_sources": self.success_sources,
            "failed_sources": self.failed_sources,
            "total_collected": self.total_collected,
            "filtered_count": self.filtered_count,
            "pushed_channels": self.pushed_channels,
            "failed_channels": self.failed_channels,
            "doc_url": self.doc_url,
        }
