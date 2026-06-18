"""行业新闻聚合推送器 - 通知路由器"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx

from src.issues import ErrorIssue, IssueTracker
from src.models import ExecutionResult, NewsItem
from src.pushers.templates import FeishuTemplateBuilder

if TYPE_CHECKING:
    from src.config import AppConfig

logger = logging.getLogger(__name__)


class NotificationRouter:
    """通知路由器：确保用户一定能收到执行报告"""

    def __init__(self, config: "AppConfig") -> None:
        self.config = config

    def send_report(
        self,
        items: list[NewsItem],
        result: ExecutionResult,
        issue_tracker: IssueTracker,
    ) -> None:
        """发送执行报告通知（兜底机制）"""
        industry = self.config.filter.industry
        sent = False

        # 优先飞书
        if self.config.push.feishu.enabled and self.config.push.feishu.notify_chat:
            sent = self._send_via_feishu(items, result, issue_tracker, industry)

        # 飞书失败则发邮件
        if not sent and self.config.push.email.enabled:
            sent = self._send_via_email(items, result, issue_tracker, industry)

        # 全部失败 → 写入本地日志文件
        if not sent:
            self._write_local_report(items, result, issue_tracker, industry)

    def _send_via_feishu(
        self,
        items: list[NewsItem],
        result: ExecutionResult,
        issue_tracker: IssueTracker,
        industry: str,
    ) -> bool:
        """通过飞书发送执行报告卡片"""
        feishu_config = self.config.push.feishu
        if not feishu_config.app_id or not feishu_config.app_secret:
            return False

        # 获取token
        try:
            token_resp = httpx.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": feishu_config.app_id, "app_secret": feishu_config.app_secret},
                timeout=15,
            )
            token_data = token_resp.json()
            if token_data.get("code") != 0:
                return False
            token = token_data["tenant_access_token"]
        except Exception:
            return False

        # 构建报告卡片
        card = FeishuTemplateBuilder.build_card(items, industry, result, issue_tracker, result.doc_url)

        # 发送
        try:
            resp = httpx.post(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "receive_id": feishu_config.notify_chat,
                    "msg_type": "interactive",
                    "content": json.dumps(card, ensure_ascii=False),
                },
                timeout=15,
            )
            data = resp.json()
            return data.get("code") == 0
        except Exception:
            return False

    def _send_via_email(
        self,
        items: list[NewsItem],
        result: ExecutionResult,
        issue_tracker: IssueTracker,
        industry: str,
    ) -> bool:
        """通过邮件发送执行报告"""
        from src.pushers.email_pusher import EmailPusher

        email_pusher = EmailPusher()
        return email_pusher.push(
            items,
            issue_tracker,
            result,
            config=self.config.push.email,
            industry=industry,
        )

    def _write_local_report(
        self,
        items: list[NewsItem],
        result: ExecutionResult,
        issue_tracker: IssueTracker,
        industry: str,
    ) -> None:
        """写入本地报告文件（最终兜底）"""
        from pathlib import Path
        from datetime import datetime

        report_dir = Path("./output/reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = report_dir / filename

        lines = [
            f"{'=' * 60}",
            f"  行业新闻聚合推送器 - 执行报告",
            f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{'=' * 60}",
            f"",
            f"执行状态：{issue_tracker.get_status_label()}",
            f"信息源：{result.total_sources}个（成功{result.success_sources}，失败{result.failed_sources}）",
            f"收集文章：{result.total_collected}篇",
            f"筛选后：{result.filtered_count}条",
            f"推送渠道：{result.pushed_channels or '无'}",
            f"",
        ]

        if issue_tracker.visible_issues:
            lines.append(f"{'─' * 60}")
            lines.append(f"问题列表：")
            lines.append(f"{'─' * 60}")
            for issue in issue_tracker.visible_issues:
                lines.append(f"{issue.icon} [{issue.code}] {issue.source}")
                lines.append(f"  问题：{issue.reason}")
                lines.append(f"  建议：{issue.suggestion}")
                lines.append(f"")

        if items:
            lines.append(f"{'─' * 60}")
            lines.append(f"新闻列表：")
            lines.append(f"{'─' * 60}")
            for i, item in enumerate(items, 1):
                lines.append(f"{i}. {item.title}")
                lines.append(f"   来源：{item.source} · {item.publish_time_str}")
                lines.append(f"")

        lines.append(f"{'=' * 60}")
        lines.append(f"（所有推送渠道均失败，报告已写入本地文件）")

        filepath.write_text("\n".join(lines), encoding="utf-8")
        logger.warning(f"所有推送渠道失败，执行报告已写入: {filepath}")
