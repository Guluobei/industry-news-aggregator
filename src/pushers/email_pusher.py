"""行业新闻聚合推送器 - 邮件推送器

设计原则：
- 卡片式布局，每条新闻一个独立卡片
- 行业主题色统一
- 响应式（兼容手机/桌面客户端）
- 邮件客户端兼容性（用 table 而非 div 布局）
"""

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


# 行业主题色（用于邮件头部和强调元素）
INDUSTRY_COLORS = {
    "保险": ("#1e40af", "#3b82f6"),   # 深蓝/亮蓝
    "金融": ("#1e3a8a", "#3b82f6"),
    "证券": ("#312e81", "#6366f1"),
    "医疗": ("#065f46", "#10b981"),
    "医药": ("#065f46", "#10b981"),
    "科技": ("#6b21a8", "#a855f7"),
    "AI": ("#6b21a8", "#a855f7"),
    "互联网": ("#9a3412", "#f97316"),
    "": ("#1e40af", "#3b82f6"),
}


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
        weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]

        # 构建邮件
        subject = f"【{industry or '行业'}资讯】{date_str} Top{len(items)}"
        html_content = self._build_html(items, industry, date_str, weekday_cn, result, issue_tracker)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.smtp_user
        msg["To"] = ", ".join(config.to)

        # 纯文本备选
        text_content = self._build_text(items, industry, date_str, weekday_cn)
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
        weekday_cn: str,
        result: ExecutionResult,
        issue_tracker: IssueTracker,
    ) -> str:
        """构建HTML邮件内容（卡片化模板）"""
        primary_color, accent_color = INDUSTRY_COLORS.get(industry, INDUSTRY_COLORS[""])

        # ============ 1. 顶部统计卡片 ============
        source_count = len(set(item.source for item in items))
        stats_html = f"""
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin:24px 0;border-collapse:separate;border-spacing:8px;">
            <tr>
                <td align="center" style="background:#eff6ff;padding:18px 12px;border-radius:8px;width:25%;">
                    <div style="font-size:28px;font-weight:700;color:{primary_color};line-height:1;">📅</div>
                    <div style="font-size:11px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;">日期</div>
                    <div style="font-size:13px;color:#1e293b;margin-top:4px;font-weight:600;">{date_str}</div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:2px;">{weekday_cn}</div>
                </td>
                <td align="center" style="background:#f0fdf4;padding:18px 12px;border-radius:8px;width:25%;">
                    <div style="font-size:28px;font-weight:700;color:#059669;line-height:1;">📊</div>
                    <div style="font-size:11px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;">覆盖源</div>
                    <div style="font-size:13px;color:#1e293b;margin-top:4px;font-weight:600;">{result.success_sources}/{result.total_sources} 个</div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:2px;">{result.total_collected} 篇文章</div>
                </td>
                <td align="center" style="background:#fff7ed;padding:18px 12px;border-radius:8px;width:25%;">
                    <div style="font-size:28px;font-weight:700;color:#ea580c;line-height:1;">🎯</div>
                    <div style="font-size:11px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;">精选</div>
                    <div style="font-size:13px;color:#1e293b;margin-top:4px;font-weight:600;">{result.filtered_count} 条</div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:2px;">来自 {source_count} 个源</div>
                </td>
                <td align="center" style="background:#fdf4ff;padding:18px 12px;border-radius:8px;width:25%;">
                    <div style="font-size:28px;font-weight:700;color:#a21caf;line-height:1;">🏷️</div>
                    <div style="font-size:11px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;">行业</div>
                    <div style="font-size:13px;color:#1e293b;margin-top:4px;font-weight:600;">{industry or '综合'}</div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:2px;">近 7 天</div>
                </td>
            </tr>
        </table>
        """

        # ============ 2. 问题区域 ============
        issues_html = ""
        issue_summary = issue_tracker.get_summary()
        if issue_summary["total"] > 0:
            # 按严重程度分组
            fatal_count = sum(1 for i in issue_summary["issues"] if i["level"] == "FATAL")
            error_count = sum(1 for i in issue_summary["issues"] if i["level"] == "ERROR")
            warn_count = sum(1 for i in issue_summary["issues"] if i["level"] == "WARN")

            breakdown = []
            if fatal_count:
                breakdown.append(f'<span style="color:#dc2626;font-weight:600;">●致命 {fatal_count}</span>')
            if error_count:
                breakdown.append(f'<span style="color:#ea580c;font-weight:600;">●错误 {error_count}</span>')
            if warn_count:
                breakdown.append(f'<span style="color:#ca8a04;font-weight:600;">●警告 {warn_count}</span>')

            issues_html = f"""
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin:24px 0;background:#fef2f2;border-left:4px solid #dc2626;border-radius:6px;overflow:hidden;">
                <tr>
                    <td style="padding:16px 20px;">
                        <div style="font-weight:700;color:#991b1b;margin-bottom:8px;font-size:15px;">
                            {issue_tracker.get_status_label()}
                        </div>
                        <div style="font-size:13px;color:#7f1d1d;margin-bottom:12px;">
                            {' · '.join(breakdown)}
                        </div>
            """
            for issue_dict in issue_summary["issues"][:5]:
                issues_html += f"""
                        <div style="margin:8px 0;padding:10px 12px;background:#fff;border-radius:4px;border-left:3px solid #e5e7eb;">
                            <div style="font-weight:600;color:#374151;font-size:13px;">{issue_dict['icon']} {issue_dict['source']}</div>
                            <div style="color:#6b7280;font-size:12px;margin-top:4px;line-height:1.5;">问题：{issue_dict['reason']}</div>
                            <div style="color:#9ca3af;font-size:12px;margin-top:2px;line-height:1.5;">建议：{issue_dict['suggestion']}</div>
                        </div>
                """
            if issue_summary["total"] > 5:
                issues_html += f"""
                        <div style="text-align:center;color:#9ca3af;font-size:12px;margin-top:8px;">
                            还有 {issue_summary['total'] - 5} 条问题未显示
                        </div>
                """
            issues_html += """
                    </td>
                </tr>
            </table>
            """

        # ============ 3. 新闻列表（每条一个卡片）============
        news_html = ""
        if items:
            news_html += f"""
            <div style="margin:30px 0 16px 0;padding-bottom:8px;border-bottom:2px solid {primary_color};">
                <h2 style="margin:0;color:{primary_color};font-size:18px;font-weight:700;">📰 今日 Top {len(items)} 要闻</h2>
            </div>
            """

            for i, item in enumerate(items, 1):
                summary = item.summary or (item.content[:200] if item.content else "")
                source_icon = self._get_source_icon(item.source)

                link_html = (
                    f'<a href="{item.url}" style="display:inline-block;background:{primary_color};color:#fff;padding:6px 16px;border-radius:4px;text-decoration:none;font-size:12px;font-weight:600;">阅读原文 →</a>'
                    if item.url else ""
                )

                news_html += f"""
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin:16px 0;background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
                    <tr>
                        <td style="padding:20px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td width="48" valign="top" style="padding-right:14px;">
                                        <div style="width:40px;height:40px;background:linear-gradient(135deg,{primary_color},{accent_color});color:#fff;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:18px;text-align:center;line-height:40px;">{i:02d}</div>
                                    </td>
                                    <td valign="top">
                                        <h3 style="margin:0 0 8px 0;color:#0f172a;font-size:16px;font-weight:700;line-height:1.4;">
                                            <a href="{item.url}" style="color:#0f172a;text-decoration:none;">{item.title}</a>
                                        </h3>
                                        <div style="font-size:12px;color:#94a3b8;margin-bottom:10px;">
                                            {source_icon} <span style="color:#64748b;">{item.source}</span>
                                            <span style="margin:0 6px;color:#cbd5e1;">·</span>
                                            ⏰ {item.publish_time_str}
                                        </div>
                """
                if summary:
                    news_html += f"""
                                        <div style="font-size:14px;color:#475569;line-height:1.7;margin-bottom:12px;">
                                            {summary}
                                        </div>
                    """
                news_html += f"""
                                        <div>{link_html}</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
                """
        else:
            news_html = """
            <div style="text-align:center;padding:60px 20px;color:#94a3b8;background:#f8fafc;border-radius:8px;margin:30px 0;">
                <div style="font-size:48px;margin-bottom:12px;">📭</div>
                <div style="font-size:14px;">本次未筛选到符合条件的新闻</div>
                <div style="font-size:12px;margin-top:6px;color:#cbd5e1;">请检查关键词配置或放宽时间范围</div>
            </div>
            """

        # ============ 4. 完整HTML ============
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light">
    <title>{industry or '行业'}资讯日报</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;color:#1e293b;-webkit-font-smoothing:antialiased;">
    <!-- 外层容器 -->
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#f1f5f9;padding:20px 0;">
        <tr>
            <td align="center">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="680" style="max-width:680px;width:100%;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1);">
                    <!-- 头部渐变背景 -->
                    <tr>
                        <td style="background:linear-gradient(135deg,{primary_color} 0%,{accent_color} 100%);padding:36px 32px;text-align:center;">
                            <div style="font-size:32px;margin-bottom:8px;">📰</div>
                            <h1 style="margin:0;color:#fff;font-size:26px;font-weight:700;letter-spacing:-0.5px;">{industry or '行业'}资讯日报</h1>
                            <p style="color:rgba(255,255,255,0.85);margin:8px 0 0 0;font-size:14px;font-weight:500;">{date_str} · {weekday_cn} · Top {len(items)}</p>
                        </td>
                    </tr>
                    <!-- 内容区 -->
                    <tr>
                        <td style="padding:24px 32px 32px 32px;">
                            {stats_html}
                            {issues_html}
                            {news_html}
                        </td>
                    </tr>
                    <!-- 页脚 -->
                    <tr>
                        <td style="background:#f8fafc;padding:20px 32px;text-align:center;border-top:1px solid #e2e8f0;">
                            <p style="color:#64748b;font-size:12px;margin:0 0 4px 0;font-weight:600;">本邮件由「行业新闻聚合器」自动生成</p>
                            <p style="color:#94a3b8;font-size:11px;margin:0;">仅供内部学习使用 · 严禁对外宣传或商业用途 · {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    def _build_text(
        self,
        items: list[NewsItem],
        industry: str,
        date_str: str,
        weekday_cn: str,
    ) -> str:
        """构建纯文本邮件内容"""
        lines = [
            "=" * 60,
            f"  📰 {industry or '行业'}资讯日报",
            f"  {date_str} · {weekday_cn}",
            "=" * 60,
            "",
        ]

        for i, item in enumerate(items, 1):
            lines.append(f"【{i:02d}】{item.title}")
            lines.append(f"    📌 来源：{item.source}")
            lines.append(f"    ⏰ 时间：{item.publish_time_str}")
            if item.summary:
                lines.append(f"    📝 {item.summary[:150]}")
            if item.url:
                lines.append(f"    🔗 {item.url}")
            lines.append("")

        lines.append("=" * 60)
        lines.append("本邮件由「行业新闻聚合器」自动生成")
        lines.append("仅供内部学习使用，严禁对外宣传")
        return "\n".join(lines)

    @staticmethod
    def _get_source_icon(source: str) -> str:
        """根据来源类型返回对应 emoji"""
        if source.startswith("公众号"):
            return "📱"
        if any(site in source for site in ["36氪", "第一财经", "21世纪", "界面", "新浪", "RSS"]):
            return "🌐"
        if "api" in source.lower():
            return "🔌"
        return "📄"
