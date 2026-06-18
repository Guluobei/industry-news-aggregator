"""行业新闻聚合推送器 - 飞书模板构建器（固定美观模板）"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from src.models import ExecutionResult, NewsItem
from src.utils import truncate_text

if TYPE_CHECKING:
    from src.issues import IssueTracker


class FeishuTemplateBuilder:
    """飞书固定模板构建器"""

    @staticmethod
    def build_card(
        items: list[NewsItem],
        industry: str,
        result: ExecutionResult,
        issue_tracker: "IssueTracker",
        doc_url: str = "",
    ) -> dict:
        """构建飞书消息卡片（固定模板）"""
        now = datetime.now()
        date_str = f"{now.year}年{now.month}月{now.day}日"

        elements: list[dict] = []

        # 1. 统计摘要
        elements.append({
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {"tag": "lark_md", "content": f"**信息源**\n{result.total_sources}个"},
                },
                {
                    "is_short": True,
                    "text": {"tag": "lark_md", "content": f"**收集文章**\n{result.total_collected}篇"},
                },
                {
                    "is_short": True,
                    "text": {"tag": "lark_md", "content": f"**筛选后**\n{result.filtered_count}条"},
                },
                {
                    "is_short": True,
                    "text": {"tag": "lark_md", "content": f"**行业**\n{industry or '综合'}"},
                },
            ],
        })

        elements.append({"tag": "hr"})

        # 2. 问题区域（如果有）
        issue_summary = issue_tracker.get_summary()
        has_issues = issue_summary["total"] > 0

        if has_issues:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**执行状态：{issue_tracker.get_status_label()}**"},
            })

            for issue_dict in issue_summary["issues"][:5]:  # 最多显示5条
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"{issue_dict['icon']} **{issue_dict['source']}**\n"
                            f"问题：{issue_dict['reason']}\n"
                            f"建议：{issue_dict['suggestion']}"
                        ),
                    },
                })

            if issue_summary["total"] > 5:
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"...还有 {issue_summary['total'] - 5} 条问题，详见日志"},
                })

            elements.append({"tag": "hr"})

        # 3. 新闻列表（卡片中只显示标题和来源，最多10条）
        if items:
            for i, item in enumerate(items, 1):
                summary_text = truncate_text(item.summary or item.content, 80)
                content = f"**{i}. {item.title}**\n来源：{item.source} · {item.publish_time_str}"
                if summary_text:
                    content += f"\n> {summary_text}"

                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content},
                })

                if i < len(items):
                    elements.append({"tag": "hr"})
        else:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "本次未筛选到符合条件的新闻"},
            })

        # 4. 查看完整文档按钮
        if doc_url:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看完整文档"},
                        "url": doc_url,
                        "type": "primary",
                    }
                ],
            })

        # 5. 页脚
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "由行业新闻聚合器自动生成 · 仅供内部学习使用",
                }
            ],
        })

        # 卡片整体
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📰 {industry or '行业'}资讯 Top{len(items)} · {date_str}",
                },
                "template": "red" if issue_tracker.has_fatal() else "blue",
            },
            "elements": elements,
        }

    @staticmethod
    def build_doc_blocks(items: list[NewsItem], industry: str) -> list[dict]:
        """构建飞书文档内容块（固定模板）"""
        now = datetime.now()
        blocks: list[dict] = []

        # 副标题
        blocks.append({
            "block_type": 3,  # Heading2
            "heading2": {
                "elements": [{"text_run": {"content": f"{now.year}年{now.month}月 · 第{((now.day - 1) // 7) + 1}周"}}]
            },
        })

        # 统计信息
        stats_text = f"覆盖信息源 | 筛选出{len(items)}条 | 关键词命中率自动计算"
        blocks.append({
            "block_type": 2,  # Text
            "text": {
                "elements": [{"text_run": {"content": stats_text}}],
                "style": {},
            },
        })

        # 分隔线
        blocks.append({"block_type": 22})  # Divider

        # 每条新闻
        cn_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        for i, item in enumerate(items):
            num = cn_nums[i] if i < len(cn_nums) else str(i + 1)

            # 标题
            blocks.append({
                "block_type": 4,  # Heading3
                "heading3": {
                    "elements": [{"text_run": {"content": f"{num}、{item.title}"}}]
                },
            })

            # 来源和时间
            meta_text = f"来源：{item.source} | 时间：{item.publish_time_str}"
            blocks.append({
                "block_type": 2,
                "text": {
                    "elements": [{"text_run": {"content": meta_text}}],
                    "style": {},
                },
            })

            # 摘要
            summary = item.summary or truncate_text(item.content, 300)
            if summary:
                blocks.append({
                    "block_type": 2,
                    "text": {
                        "elements": [{"text_run": {"content": summary}}],
                        "style": {},
                    },
                })

            # 原文链接
            if item.url:
                blocks.append({
                    "block_type": 2,
                    "text": {
                        "elements": [
                            {"text_run": {"content": "原文链接："}},
                            {"text_run": {"content": item.url, "text_element_style": {"link": {"url": item.url}}}},
                        ],
                        "style": {},
                    },
                })

            # 分隔线
            blocks.append({"block_type": 22})

        # 页脚
        blocks.append({
            "block_type": 2,
            "text": {
                "elements": [{"text_run": {"content": f"本资源仅供内部学习使用，严禁对外宣传。\n生成时间：{now.strftime('%Y-%m-%d %H:%M')}"}},
                ],
            },
        })

        return blocks
