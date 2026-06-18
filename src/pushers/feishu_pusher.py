"""行业新闻聚合推送器 - 飞书推送器（文档+消息卡片）"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from src.issues import ErrorIssue, FatalIssue, IssueTracker
from src.models import ExecutionResult, NewsItem
from src.pushers.base import BasePusher
from src.pushers.templates import FeishuTemplateBuilder

if TYPE_CHECKING:
    from src.config import FeishuPushConfig

logger = logging.getLogger(__name__)


class FeishuPusher(BasePusher):
    """飞书推送器：创建文档 + 发送消息卡片"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def push(
        self,
        items: list[NewsItem],
        issue_tracker: IssueTracker,
        result: ExecutionResult,
        **kwargs,
    ) -> bool:
        """执行飞书推送"""
        config: "FeishuPushConfig" = kwargs["config"]
        industry = kwargs.get("industry", "")

        # Step 1: 获取tenant_access_token
        token = self._get_tenant_token(config, issue_tracker)
        if not token:
            return False

        doc_url = ""

        # Step 2: 创建飞书文档
        if config.doc_folder:
            doc_url = self._create_and_fill_doc(
                token, config, items, industry, issue_tracker, result
            )

        # Step 3: 发送消息卡片通知
        if config.notify_chat:
            self._send_card_message(
                token, config, items, industry, issue_tracker, result, doc_url
            )

        result.doc_url = doc_url
        result.pushed_channels.append("feishu")
        return True

    def _get_tenant_token(self, config: "FeishuPushConfig", issue_tracker: IssueTracker) -> str:
        """获取飞书tenant_access_token"""
        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": config.app_id,
            "app_secret": config.app_secret,
        }

        try:
            resp = httpx.post(url, json=payload, timeout=15)
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            issue_tracker.record(FatalIssue(
                code="FEISHU_AUTH_FAILED",
                source="飞书推送",
                reason="飞书应用认证失败，无法获取访问令牌",
                suggestion="请检查网络连接，以及 FEISHU_APP_ID 和 FEISHU_APP_SECRET 是否正确设置",
                detail=str(e),
            ).issue)
            return ""

        if data.get("code") != 0:
            issue_tracker.record(FatalIssue(
                code="FEISHU_AUTH_FAILED",
                source="飞书推送",
                reason=f"飞书应用认证失败：{data.get('msg', '未知错误')}",
                suggestion="请确认 FEISHU_APP_ID 和 FEISHU_APP_SECRET 是否正确，应用是否已启用",
                detail=json.dumps(data, ensure_ascii=False),
            ).issue)
            return ""

        return data.get("tenant_access_token", "")

    def _create_and_fill_doc(
        self,
        token: str,
        config: "FeishuPushConfig",
        items: list[NewsItem],
        industry: str,
        issue_tracker: IssueTracker,
        result: ExecutionResult,
    ) -> str:
        """创建飞书文档并填充内容"""
        now = datetime.now()
        title = f"《{industry}行业资讯Top{len(items)}》{now.year}年{now.month}月"

        # 创建文档
        create_url = f"{self.BASE_URL}/docx/v1/documents"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"folder_token": config.doc_folder, "title": title}

        try:
            resp = httpx.post(create_url, json=payload, headers=headers, timeout=15)
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            issue_tracker.record(ErrorIssue(
                code="FEISHU_DOC_FAILED",
                source="飞书推送",
                reason=f"飞书文档创建失败：{type(e).__name__}",
                suggestion="请检查网络连接和飞书应用权限",
                detail=str(e),
            ).issue)
            return ""

        if data.get("code") != 0:
            # 文件夹token无效
            if data.get("code") == 99991668:
                issue_tracker.record(FatalIssue(
                    code="FEISHU_FOLDER_INVALID",
                    source="飞书推送",
                    reason=f"飞书文件夹token无效（{config.doc_folder}），无法创建文档",
                    suggestion="请在飞书中打开目标文件夹，从URL中获取正确的folder_token",
                    detail=json.dumps(data, ensure_ascii=False),
                ).issue)
            else:
                issue_tracker.record(ErrorIssue(
                    code="FEISHU_DOC_FAILED",
                    source="飞书推送",
                    reason=f"飞书文档创建失败：{data.get('msg', '未知错误')}",
                    suggestion="请检查飞书应用是否拥有该文件夹的写入权限",
                    detail=json.dumps(data, ensure_ascii=False),
                ).issue)
            return ""

        doc_id = data["data"]["document"]["document_id"]
        doc_url = f"https://feishu.cn/docx/{doc_id}"

        # 填充文档内容
        self._fill_doc_content(token, doc_id, items, industry, issue_tracker)

        logger.info(f"飞书文档创建成功: {doc_url}")
        return doc_url

    def _fill_doc_content(
        self,
        token: str,
        doc_id: str,
        items: list[NewsItem],
        industry: str,
        issue_tracker: IssueTracker,
    ) -> None:
        """向飞书文档填充内容块"""
        url = f"{self.BASE_URL}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        blocks = FeishuTemplateBuilder.build_doc_blocks(items, industry)

        try:
            resp = httpx.post(url, json={"children": blocks}, headers=headers, timeout=30)
            data = resp.json()
            if data.get("code") != 0:
                logger.warning(f"飞书文档内容填充部分失败: {data.get('msg')}")
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            logger.warning(f"飞书文档内容填充异常: {e}")

    def _send_card_message(
        self,
        token: str,
        config: "FeishuPushConfig",
        items: list[NewsItem],
        industry: str,
        issue_tracker: IssueTracker,
        result: ExecutionResult,
        doc_url: str,
    ) -> None:
        """发送飞书消息卡片"""
        url = f"{self.BASE_URL}/im/v1/messages?receive_id_type=chat_id"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        card = FeishuTemplateBuilder.build_card(items, industry, result, issue_tracker, doc_url)

        payload = {
            "receive_id": config.notify_chat,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }

        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=15)
            data = resp.json()
            if data.get("code") != 0:
                issue_tracker.record(ErrorIssue(
                    code="FEISHU_MSG_FAILED",
                    source="飞书推送",
                    reason=f"飞书消息卡片发送失败：{data.get('msg', '未知错误')}",
                    suggestion="请检查群聊ID是否正确，以及机器人是否已加入该群",
                    detail=json.dumps(data, ensure_ascii=False),
                ).issue)
            else:
                logger.info("飞书消息卡片发送成功")
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            issue_tracker.record(ErrorIssue(
                code="FEISHU_MSG_FAILED",
                source="飞书推送",
                reason=f"飞书消息卡片发送失败：{type(e).__name__}",
                suggestion="请检查网络连接",
                detail=str(e),
            ).issue)
