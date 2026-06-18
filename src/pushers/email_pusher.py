"""行业新闻聚合推送器 - 邮件推送器"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from src.issues import ErrorIssue, FatalIssue, IssueTracker
from src.models import ExecutionResult, NewsItem
from src.pushers.base import BasePusher

if TYPE_CHECKING:
    from src.config import EmailPushConfig

logger = logging.getLogger(__name__)


class EmailPusher(BasePusher):
    """邮件推送器：发送HTML格式资讯简报"""

    def push(
        self,
        items: list[NewsItem],
        issue_tracker: IssueTracker,
        result: ExecutionResult,
        **kwargs,
    ) -> bool:
        """执行邮件推送"""
        config: "EmailPushConfig" = kwargs["config"]
        industry = kwargs.get("industry", "")

        now = datetime.now()
        date_str = f"{now.year}年{now.month}月{now.day}日"

        # 构建邮件
        subject = f"【{industry or '行业'}资讯】{date_str} Top{len(items)}"
        html_content = self._build_html(items, industry, date_str, result, issue_tracker)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.smtp_user
        msg["To"] = ", ".join(config.to)

        # 纯文本备选
        text_content = self._build_text(items, industry, date_str)
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # 发送
        try:
            if config.smtp_port == 465:
                server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30)
                server.starttls()

            server.login(config.smtp_user, config.smtp_password)
            server.sendmail(config.smtp_user, config.to, msg.as_string())
            server.quit()

            logger.info(f"邮件发送成功：{subject} → {config.to}")
            result.pushed_channels.append("email")
            return True

        except smtplib.SMTPAuthenticationError:
            issue_tracker.record(FatalIssue(
                code="EMAIL_AUTH_FAILED",
                source="邮箱推送",
                reason="邮箱SMTP认证失败，用户名或密码/授权码不正确",
                suggestion="请确认 EMAIL_USER 和 EMAIL_PASSWORD 是否正确。注意：部分邮箱需使用授权码而非登录密码",
            ).issue)
            return False

        except smtplib.SMTPConnectError:
            issue_tracker.record(ErrorIssue(
                code="EMAIL_CONNECT_FAILED",
                source="邮箱推送",
                reason=f"无法连接邮箱服务器 {config.smtp_host}:{config.smtp_port}",
                suggestion="请检查SMTP地址和端口是否正确，网络是否通畅",
            ).issue)
            return False

        except smtplib.SMTPException as e:
            issue_tracker.record(ErrorIssue(
                code="EMAIL_SEND_FAILED",
                source="邮箱推送",
                reason=f"邮件发送失败：{type(e).__name__}",
                suggestion="请检查收件人地址是否正确",
                detail=str(e),
            ).issue)
            return False

        except Exception as e:
            issue_tracker.record(ErrorIssue(
                code="EMAIL_UNKNOWN_ERROR",
                source="邮箱推送",
                reason=f"邮件发送出现未知错误：{type(e).__name__}",
                suggestion="请查看日志获取详细信息",
                detail=str(e),
            ).issue)
            return False

    def _build_html(
        self,
        items: list[NewsItem],
        industry: str,
        date_str: str,
        result: ExecutionResult,
        issue_tracker: IssueTracker,
    ) -> str:
        """构建HTML邮件内容（固定美观模板）"""
        from src.pushers.templates import FeishuTemplateBuilder

        # 统计卡片
        stats_html = f"""
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
            <tr>
                <td style="background:#f0f4ff;padding:15px;text-align:center;border-radius:8px 0 0 8px;">
                    <div style="font-size:24px;font-weight:bold;color:#2b6cb0;">{result.total_sources}</div>
                    <div style="font-size:12px;color:#666;">信息源</div>
                </td>
                <td style="background:#f0fff4;padding:15px;text-align:center;">
                    <div style="font-size:24px;font-weight:bold;color:#2f855a;">{result.total_collected}</div>
                    <div style="font-size:12px;color:#666;">收集文章</div>
                </td>
                <td style="background:#fffaf0;padding:15px;text-align:center;">
                    <div style="font-size:24px;font-weight:bold;color:#dd6b20;">{result.filtered_count}</div>
                    <div style="font-size:12px;color:#666;">筛选后</div>
                </td>
                <td style="background:#fff5f5;padding:15px;text-align:center;border-radius:0 8px 8px 0;">
                    <div style="font-size:24px;font-weight:bold;color:#c53030;">{industry or '综合'}</div>
                    <div style="font-size:12px;color:#666;">行业</div>
                </td>
            </tr>
        </table>
        """

        # 问题区域
        issues_html = ""
        issue_summary = issue_tracker.get_summary()
        if issue_summary["total"] > 0:
            issues_html = f"""
            <div style="background:#fff5f5;border-left:4px solid #c53030;padding:15px;margin:20px 0;border-radius:4px;">
                <div style="font-weight:bold;color:#c53030;margin-bottom:10px;">执行状态：{issue_tracker.get_status_label()}</div>
            """
            for issue_dict in issue_summary["issues"][:5]:
                issues_html += f"""
                <div style="margin:8px 0;padding:8px;background:#fff;border-radius:4px;">
                    <div>{issue_dict['icon']} <strong>{issue_dict['source']}</strong></div>
                    <div style="color:#666;font-size:13px;">问题：{issue_dict['reason']}</div>
                    <div style="color:#888;font-size:12px;">建议：{issue_dict['suggestion']}</div>
                </div>
                """
            issues_html += "</div>"

        # 新闻列表
        news_html = ""
        for i, item in enumerate(items, 1):
            summary = item.summary or item.content[:200] if item.content else ""
            link_html = f'<a href="{item.url}" style="color:#2b6cb0;text-decoration:none;">阅读原文 →</a>' if item.url else ""
            news_html += f"""
            <div style="margin:20px 0;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;">
                <div style="display:flex;align-items:flex-start;">
                    <span style="background:#2b6cb0;color:#fff;padding:2px 10px;border-radius:4px;font-size:14px;margin-right:10px;min-width:30px;text-align:center;">{i:02d}</span>
                    <div style="flex:1;">
                        <div style="font-size:16px;font-weight:bold;color:#1a365d;margin-bottom:5px;">{item.title}</div>
                        <div style="font-size:12px;color:#888;margin-bottom:10px;">来源：{item.source} · {item.publish_time_str}</div>
                        <div style="font-size:14px;color:#4a5568;line-height:1.6;">{summary}</div>
                        <div style="margin-top:10px;">{link_html}</div>
                    </div>
                </div>
            </div>
            """

        if not items:
            news_html = '<div style="text-align:center;padding:40px;color:#999;">本次未筛选到符合条件的新闻</div>'

        # 完整HTML
        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin:0;padding:0;background:#f7faf9;font-family:'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif;">
            <div style="max-width:680px;margin:0 auto;padding:20px;">
                <!-- 标题 -->
                <div style="background:linear-gradient(135deg,#2b6cb0,#4299e1);padding:30px;border-radius:12px 12px 0 0;text-align:center;">
                    <h1 style="color:#fff;margin:0;font-size:24px;">📰 {industry or '行业'}资讯 Top{len(items)}</h1>
                    <p style="color:#bee3f8;margin:5px 0 0 0;font-size:14px;">{date_str}</p>
                </div>

                <!-- 内容区 -->
                <div style="background:#fff;padding:20px;border:1px solid #e2e8f0;">
                    {stats_html}
                    {issues_html}
                    {news_html}
                </div>

                <!-- 页脚 -->
                <div style="background:#f7fafc;padding:15px;border-radius:0 0 12px 12px;text-align:center;border:1px solid #e2e8f0;border-top:none;">
                    <p style="color:#a0aec0;font-size:12px;margin:0;">
                        本邮件由行业新闻聚合器自动生成<br>
                        仅供内部学习使用，严禁对外宣传
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

    def _build_text(self, items: list[NewsItem], industry: str, date_str: str) -> str:
        """构建纯文本邮件内容"""
        lines = [f"{'=' * 50}", f"  {industry or '行业'}资讯 Top{len(items)}", f"  {date_str}", f"{'=' * 50}", ""]

        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item.title}")
            lines.append(f"   来源：{item.source} · {item.publish_time_str}")
            if item.summary:
                lines.append(f"   {item.summary[:100]}")
            if item.url:
                lines.append(f"   原文：{item.url}")
            lines.append("")

        lines.append(f"{'=' * 50}")
        lines.append("本邮件由行业新闻聚合器自动生成")
        lines.append("仅供内部学习使用，严禁对外宣传")
        return "\n".join(lines)
