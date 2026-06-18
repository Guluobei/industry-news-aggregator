"""行业新闻聚合推送器 - URL自动识别器"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import httpx

from src.issues import ErrorIssue, FatalIssue, IssueTracker
from src.utils import default_headers

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 收集器类型枚举
COLLECTOR_RSS = "rss"
COLLECTOR_WEB = "web"
COLLECTOR_WECHAT = "wechat"
COLLECTOR_API = "api"


class SourceDetector:
    """URL自动识别器：用户只需提供网址，系统自动判断类型"""

    # RSS路径特征正则
    RSS_PATH_PATTERN = re.compile(r"/(feed|rss|atom|xml)(\?|$|/)", re.I)

    # HTML中RSS链接的发现正则
    RSS_LINK_PATTERN = re.compile(
        r'<link[^>]+(?:rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\']'
        r'|type=["\']application/(?:rss|atom)\+xml["\'][^>]+rel=["\']alternate["\'])'
        r'[^>]*href=["\']([^"\']+)["\']',
        re.I,
    )

    def detect(self, source: str, issue_tracker: IssueTracker) -> str:
        """
        自动识别信息源类型

        Args:
            source: 用户提供的信息源（URL或"公众号:名称"格式）
            issue_tracker: 问题追踪器

        Returns:
            收集器类型字符串
        """
        source = source.strip()

        # 1. 公众号快捷格式
        if source.startswith("公众号:") or source.startswith("公众号："):
            return COLLECTOR_WECHAT

        # 2. 微信域名
        if "mp.weixin.qq.com" in source or "weixin.sogou.com" in source:
            return COLLECTOR_WECHAT

        # 3. 非URL（纯文本）→ 当作公众号名
        if not source.startswith("http"):
            # 可能是公众号名称
            if len(source) <= 30:
                return COLLECTOR_WECHAT
            raise FatalIssue(
                code="SOURCE_INVALID_FORMAT",
                source=source,
                reason=f"无法识别「{source}」的格式",
                suggestion="请提供有效的网址（以http开头）或使用「公众号:名称」格式",
            )

        # 4. RSS路径特征
        if self.RSS_PATH_PATTERN.search(source):
            return COLLECTOR_RSS

        # 5. HTTP探测
        return self._detect_by_http(source, issue_tracker)

    def _detect_by_http(self, url: str, issue_tracker: IssueTracker) -> str:
        """通过HTTP请求自动判断类型"""
        headers = default_headers()

        # Step 1: HEAD请求探测
        try:
            with httpx.Client(follow_redirects=True, timeout=15) as client:
                resp = client.head(url, headers=headers)
                content_type = resp.headers.get("content-type", "").lower()
        except httpx.ConnectError:
            raise FatalIssue(
                code="SOURCE_UNREACHABLE",
                source=url,
                reason=f"网址「{url}」无法访问，连接被拒绝",
                suggestion="请检查地址是否正确，或该网站是否已关闭。可在浏览器中打开确认",
            )
        except httpx.TimeoutException:
            raise FatalIssue(
                code="SOURCE_TIMEOUT",
                source=url,
                reason=f"网址「{url}」响应超时（15秒内无响应）",
                suggestion="该网站可能访问缓慢或存在网络限制，可稍后重试",
            )
        except httpx.HTTPError as e:
            raise FatalIssue(
                code="SOURCE_HTTP_ERROR",
                source=url,
                reason=f"网址「{url}」请求失败：{type(e).__name__}",
                suggestion="请检查网址是否正确，或稍后重试",
                detail=str(e),
            )

        # 检查状态码
        if resp.status_code == 404:
            raise FatalIssue(
                code="SOURCE_NOT_FOUND",
                source=url,
                reason=f"网址「{url}」页面不存在（HTTP 404）",
                suggestion="请检查网址是否正确，或该页面是否已被删除",
            )
        if resp.status_code == 403:
            raise ErrorIssue(
                code="SOURCE_FORBIDDEN",
                source=url,
                reason=f"网址「{url}」访问被拒绝（HTTP 403），可能禁止爬虫访问",
                suggestion="可尝试手动复制内容，或联系网站管理员添加白名单",
            )

        # 根据Content-Type判断
        if "rss" in content_type or "atom" in content_type or "xml" in content_type:
            return COLLECTOR_RSS

        if "json" in content_type:
            return COLLECTOR_API

        # HTML页面 → 尝试发现RSS，否则走网页爬虫
        if "html" in content_type or "text" in content_type:
            return self._detect_html(url, issue_tracker)

        # 未知类型
        raise ErrorIssue(
            code="SOURCE_TYPE_UNKNOWN",
            source=url,
            reason=f"无法识别网址「{url}」的内容类型（{content_type}）",
            suggestion="目前支持新闻网站、微信公众号和RSS源，该网址可能不在支持范围内",
        )

    def _detect_html(self, url: str, issue_tracker: IssueTracker) -> str:
        """对HTML页面进一步判断：是否含RSS链接"""
        try:
            resp = httpx.get(url, headers=default_headers(), follow_redirects=True, timeout=15)
        except httpx.HTTPError as e:
            raise ErrorIssue(
                code="SOURCE_FETCH_FAILED",
                source=url,
                reason=f"获取网页内容失败：{type(e).__name__}",
                suggestion="该源本次跳过，下次执行时将重试",
                detail=str(e),
            )

        # 尝试发现RSS链接
        rss_url = self._find_rss_link(resp.text)
        if rss_url:
            logger.info(f"在 {url} 中发现RSS链接: {rss_url}")
            # 将发现的RSS URL存入issue_tracker的临时存储
            issue_tracker._issues  # 确保tracker存在
            # 通过setattr临时存储，供RSS收集器使用
            if not hasattr(issue_tracker, "_rss_overrides"):
                issue_tracker._rss_overrides = {}
            issue_tracker._rss_overrides[url] = rss_url
            return COLLECTOR_RSS

        return COLLECTOR_WEB

    def _find_rss_link(self, html: str) -> str | None:
        """从HTML中自动发现RSS/Atom链接"""
        match = self.RSS_LINK_PATTERN.search(html)
        if match:
            return match.group(1)
        return None
