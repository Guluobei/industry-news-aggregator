"""行业新闻聚合推送器 - 飞书模板构建器（固定美观模板）

设计原则：
- 视觉层次清晰（标题/统计/列表/页脚）
- 行业标签强化品牌识别
- 问题区域醒目
- 新闻条目分块明确
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from src.models import ExecutionResult, NewsItem
from src.utils import truncate_text

if TYPE_CHECKING:
    from src.issues import IssueTracker


# 行业颜色映射（飞书卡片 template 字段）
INDUSTRY_THEMES = {
    "保险": "blue",
    "金融": "blue",
    "证券": "indigo",
    "银行": "blue",
    "医疗": "green",
    "医药": "green",
    "科技": "purple",
    "AI": "purple",
    "互联网": "orange",
    "教育": "yellow",
    "汽车": "wathet",
    "": "blue",
}


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
        """构建飞书消息卡片（固定模板）

        卡片结构：
        - 头部：标题 + 日期
        - 统计：四列指标
        - 状态：执行结果
        - 问题（如有）
        - 新闻列表
        - 操作按钮
        - 页脚
        """
        now = datetime.now()
        date_str = f"{now.year}年{now.month}月{now.day}日"
        weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]

        # 状态徽标
        status_label = issue_tracker.get_status_label()
        status_icon = status_label.split()[0] if status_label else "🟢"
        status_text = status_label.split(" ", 1)[-1] if status_label else "成功"

        # 颜色：有致命错误用红色，否则用行业主题色
        if issue_tracker.has_fatal():
            header_template = "red"
        else:
            header_template = INDUSTRY_THEMES.get(industry, "blue")

        elements: list[dict] = []

        # ============ 1. 顶部统计区 ============
        elements.append({
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"📅 **日期**\n{date_str} {weekday_cn}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"🏷️ **行业**\n{industry or '综合资讯'}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"📊 **源/文章**\n"
                            f"{result.success_sources}/{result.total_sources} 源 · {result.total_collected} 篇"
                        ),
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"🎯 **精选**\n{result.filtered_count} 条",
                    },
                },
            ],
        })

        elements.append({"tag": "hr"})

        # ============ 2. 状态行 ============
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"{status_icon} **执行状态：{status_text}**",
            },
        })

        # ============ 3. 问题区域（如果有）============
        issue_summary = issue_tracker.get_summary()
        if issue_summary["total"] > 0:
            # 区分严重程度
            fatal_count = sum(1 for i in issue_summary["issues"] if i["level"] == "FATAL")
            error_count = sum(1 for i in issue_summary["issues"] if i["level"] == "ERROR")
            warn_count = sum(1 for i in issue_summary["issues"] if i["level"] == "WARN")

            breakdown_parts = []
            if fatal_count:
                breakdown_parts.append(f"🔴致命 {fatal_count}")
            if error_count:
                breakdown_parts.append(f"🟠错误 {error_count}")
            if warn_count:
                breakdown_parts.append(f"🟡警告 {warn_count}")

            if breakdown_parts:
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**问题统计**：{' · '.join(breakdown_parts)}",
                    },
                })

            # 展示前5条关键问题
            display_issues = issue_summary["issues"][:5]
            for issue_dict in display_issues:
                # 简化展示，只保留最关键信息
                content = (
                    f"{issue_dict['icon']} **{issue_dict['source']}**\n"
                    f"问题：{issue_dict['reason']}\n"
                    f"建议：{issue_dict['suggestion']}"
                )
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content},
                })

            if issue_summary["total"] > 5:
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"💡 还有 **{issue_summary['total'] - 5}** 条问题未显示，请查看完整报告",
                    },
                })

            elements.append({"tag": "hr"})

        # ============ 4. 新闻列表 ============
        if items:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"📰 **今日 Top {len(items)} 要闻**",
                },
            })

            for i, item in enumerate(items, 1):
                summary_text = truncate_text(item.summary or item.content, 100)

                # 来源标签 emoji
                source_icon = FeishuTemplateBuilder._get_source_icon(item.source)

                # 标题 + 来源 + 时间
                content_lines = [f"**{i}. [{item.title}]({item.url})**"]
                content_lines.append(f"{source_icon} {item.source} · ⏰ {item.publish_time_str}")

                if summary_text:
                    content_lines.append(f"> {summary_text}")

                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "\n".join(content_lines),
                    },
                })

                if i < len(items):
                    elements.append({"tag": "hr"})
        else:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "⚠️ 本次未筛选到符合条件的新闻，请检查关键词配置",
                },
            })

        # ============ 5. 操作按钮 ============
        actions = []
        if doc_url:
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📄 查看完整文档"},
                "url": doc_url,
                "type": "primary",
            })
        if items:
            # 第一个文章链接作为快捷入口
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔗 阅读头条"},
                "url": items[0].url,
                "type": "default",
            })

        if actions:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "action",
                "actions": actions,
            })

        # ============ 6. 页脚 ============
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"由「行业新闻聚合器」自动生成 · {now.strftime('%Y-%m-%d %H:%M')} · 仅供内部学习使用",
                }
            ],
        })

        # ============ 组装卡片 ============
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📰 {industry or '行业'}资讯 Top{len(items)} · {date_str}",
                },
                "template": header_template,
            },
            "elements": elements,
        }

    @staticmethod
    def _get_source_icon(source: str) -> str:
        """根据来源类型返回对应 emoji"""
        if source.startswith("公众号"):
            return "📱"
        if "rss" in source.lower() or any(
            site in source for site in ["36氪", "第一财经", "21世纪", "界面", "新浪"]
        ):
            return "🌐"
        if "api" in source.lower():
            return "🔌"
        return "📄"

    @staticmethod
    def build_doc_blocks(items: list[NewsItem], industry: str) -> list[dict]:
        """构建飞书文档内容块（固定模板）

        文档结构：
        - 文档头：日期 + 行业
        - 统计：来源/筛选/时间
        - 目录（如有需要）
        - 要闻详情
        - 页脚
        """
        now = datetime.now()
        blocks: list[dict] = []

        # ============ 1. 文档标题（Heading1）============
        blocks.append({
            "block_type": 3,  # Heading1
            "heading1": {
                "elements": [
                    {"text_run": {"content": f"{industry or '行业'}资讯日报"}},
                ],
            },
        })

        # ============ 2. 副标题（Heading2）============
        cn_week = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
        week_of_month = ((now.day - 1) // 7) + 1
        subtitle = f"{now.year}年{now.month}月{now.day}日 · 星期{cn_week} · 第{week_of_month}周"
        blocks.append({
            "block_type": 4,  # Heading2
            "heading2": {
                "elements": [{"text_run": {"content": subtitle}}],
            },
        })

        # ============ 3. 概览区（带背景色的引用块）============
        overview_text = (
            f"📊 覆盖 {len(set(item.source for item in items))} 个信息源"
            f"  ·  🎯 精选 {len(items)} 条要闻"
            f"  ·  ⏰ 时间窗口：近 7 天"
        )
        blocks.append({
            "block_type": 15,  # Quote
            "quote": {
                "elements": [{"text_run": {"content": overview_text}}],
            },
        })

        blocks.append({"block_type": 22})  # Divider

        # ============ 4. 要闻列表 ============
        cn_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        for i, item in enumerate(items):
            num = cn_nums[i] if i < len(cn_nums) else str(i + 1)

            # 标题（Heading3）
            title_block = {
                "block_type": 5,  # Heading3
                "heading3": {
                    "elements": [
                        {"text_run": {"content": f"{num}、{item.title}"}},
                    ],
                },
            }
            blocks.append(title_block)

            # 元信息（来源、时间）
            source_icon = FeishuTemplateBuilder._get_source_icon(item.source)
            meta_block = {
                "block_type": 2,
                "text": {
                    "elements": [
                        {"text_run": {"content": f"{source_icon} ", "text_element_style": {"bold": True}}},
                        {"text_run": {"content": item.source}},
                        {"text_run": {"content": "    "}},
                        {"text_run": {"content": "⏰ ", "text_element_style": {"bold": True}}},
                        {"text_run": {"content": item.publish_time_str}},
                    ],
                    "style": {},
                },
            }
            blocks.append(meta_block)

            # 摘要（正文）
            summary = item.summary or truncate_text(item.content, 300)
            if summary:
                blocks.append({
                    "block_type": 2,
                    "text": {
                        "elements": [{"text_run": {"content": summary}}],
                        "style": {},
                    },
                })

            # 原文链接（独立一行，醒目）
            if item.url:
                blocks.append({
                    "block_type": 2,
                    "text": {
                        "elements": [
                            {"text_run": {"content": "👉 原文链接：", "text_element_style": {"bold": True}}},
                            {
                                "text_run": {
                                    "content": item.url,
                                    "text_element_style": {"link": {"url": item.url}},
                                }
                            },
                        ],
                        "style": {},
                    },
                })

            # 每条要闻后加分隔
            blocks.append({"block_type": 22})

        # ============ 5. 页脚 ============
        blocks.append({
            "block_type": 2,
            "text": {
                "elements": [
                    {
                        "text_run": {
                            "content": f"—— 本日报由「行业新闻聚合器」自动生成 ——\n",
                            "text_element_style": {"italic": True},
                        }
                    },
                    {
                        "text_run": {
                            "content": f"生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n",
                            "text_element_style": {"italic": True, "color": 4},
                        }
                    },
                    {
                        "text_run": {
                            "content": "本资源仅供内部学习使用，严禁对外宣传或商业用途",
                            "text_element_style": {"italic": True, "color": 4},
                        }
                    },
                ],
                "style": {},
            },
        })

        return blocks
