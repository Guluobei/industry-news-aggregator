"""行业新闻聚合推送器 - 本地文件推送器"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.issues import ErrorIssue, IssueTracker
from src.models import ExecutionResult, NewsItem
from src.pushers.base import BasePusher

if TYPE_CHECKING:
    from src.config import LocalPushConfig

logger = logging.getLogger(__name__)


class LocalPusher(BasePusher):
    """本地文件推送器：输出Markdown/HTML/JSON"""

    def push(
        self,
        items: list[NewsItem],
        issue_tracker: IssueTracker,
        result: ExecutionResult,
        **kwargs,
    ) -> bool:
        """执行本地文件输出"""
        config: "LocalPushConfig" = kwargs["config"]
        industry = kwargs.get("industry", "")

        now = datetime.now()
        date_str = now.strftime("%Y%m%d_%H%M%S")
        output_dir = Path(config.path)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            if config.format == "markdown":
                filepath = output_dir / f"news_{date_str}.md"
                content = self._build_markdown(items, industry, now)
            elif config.format == "html":
                filepath = output_dir / f"news_{date_str}.html"
                content = self._build_html(items, industry, now, result, issue_tracker)
            elif config.format == "json":
                filepath = output_dir / f"news_{date_str}.json"
                content = json.dumps(
                    [item.to_dict() for item in items],
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                filepath = output_dir / f"news_{date_str}.md"
                content = self._build_markdown(items, industry, now)

            filepath.write_text(content, encoding="utf-8")
            logger.info(f"本地文件输出成功: {filepath}")
            result.pushed_channels.append("local")
            result.doc_url = str(filepath)
            return True

        except OSError as e:
            issue_tracker.record(ErrorIssue(
                code="LOCAL_WRITE_FAILED",
                source="本地文件推送",
                reason=f"本地文件写入失败：{type(e).__name__}",
                suggestion=f"请检查输出目录是否有写入权限：{config.path}",
                detail=str(e),
            ).issue)
            return False

    def _build_markdown(self, items: list[NewsItem], industry: str, now: datetime) -> str:
        """构建Markdown格式输出"""
        lines = [
            f"# {industry or '行业'}资讯 Top{len(items)}",
            f"",
            f"> {now.year}年{now.month}月{now.day}日 · 自动生成",
            f"",
            f"---",
            f"",
        ]

        cn_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        for i, item in enumerate(items):
            num = cn_nums[i] if i < len(cn_nums) else str(i + 1)
            lines.append(f"## {num}、{item.title}")
            lines.append(f"")
            lines.append(f"**来源**：{item.source} | **时间**：{item.publish_time_str}")
            lines.append(f"")
            if item.summary:
                lines.append(item.summary)
                lines.append(f"")
            if item.content and len(item.content) > len(item.summary or ""):
                lines.append("<details>")
                lines.append("<summary>查看完整内容</summary>")
                lines.append(f"")
                lines.append(item.content)
                lines.append(f"")
                lines.append("</details>")
                lines.append(f"")
            if item.url:
                lines.append(f"🔗 [阅读原文]({item.url})")
            lines.append(f"")
            lines.append(f"---")
            lines.append(f"")

        lines.append(f"")
        lines.append(f"*本资源仅供内部学习使用，严禁对外宣传。*")
        lines.append(f"*生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)

    def _build_html(self, items, industry, now, result, issue_tracker) -> str:
        """构建HTML格式输出（复用邮件模板）"""
        from src.pushers.email_pusher import EmailPusher

        email_pusher = EmailPusher()
        date_str = f"{now.year}年{now.month}月{now.day}日"
        return email_pusher._build_html(items, industry, date_str, result, issue_tracker)
