"""行业新闻聚合推送器 - 网页收集器"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.issues import ErrorIssue, IssueTracker, WarnIssue
from src.models import NewsItem
from src.utils import clean_text, default_headers, fetch_url, parse_date, truncate_text

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class WebCollector(BaseCollector):
    """网页爬虫收集器：自动提取新闻列表和正文"""

    # 新闻列表页常见CSS选择器模式（按优先级尝试）
    LIST_SELECTORS = [
        "ul.news-list li a",
        "ul.list li a",
        ".news-list a",
        ".list-content a",
        ".article-list a",
        ".content-list a",
        "ul.list-content li a",
        ".box-list li a",
        ".news_list li a",
        "div.list a",
        "table.news a",
        ".main-content a",
        "article a",
        ".post-list a",
    ]

    # 正文区域常见CSS选择器
    CONTENT_SELECTORS = [
        "article",
        ".article-content",
        ".article",
        ".content",
        ".news-content",
        ".main-content",
        "#content",
        ".post-content",
        ".entry-content",
        ".detail-content",
    ]

    # 日期正则模式
    DATE_PATTERNS = [
        r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{4}年\d{1,2}月\d{1,2}日)",
    ]

    def collect(self, source: str, issue_tracker: IssueTracker, **kwargs) -> list[NewsItem]:
        """
        从网页收集新闻

        Args:
            source: 网页URL
            issue_tracker: 问题追踪器
        """
        source_name = kwargs.get("source_name", source)
        domain = urlparse(source).netloc

        try:
            resp = fetch_url(source, timeout=20)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise ErrorIssue(
                    code="WEB_BLOCKED",
                    source=source_name,
                    reason=f"网站「{source_name}」拒绝了访问请求（403），可能存在反爬机制",
                    suggestion="可尝试：1) 稍后重试 2) 配置代理 3) 移除该源改用其他渠道",
                )
            if e.response.status_code == 429:
                raise ErrorIssue(
                    code="WEB_RATE_LIMITED",
                    source=source_name,
                    reason=f"网站「{source_name}」请求频率过高被限制（429）",
                    suggestion="系统将自动降低该源的采集频率，下次执行时重试",
                )
            raise ErrorIssue(
                code="WEB_HTTP_ERROR",
                source=source_name,
                reason=f"网站「{source_name}」请求失败（HTTP {e.response.status_code}）",
                suggestion="该源本次跳过，下次执行时将重试",
                detail=str(e),
            )
        except httpx.HTTPError as e:
            raise ErrorIssue(
                code="WEB_FETCH_FAILED",
                source=source_name,
                reason=f"网站「{source_name}」获取失败：{type(e).__name__}",
                suggestion="该源本次跳过，下次执行时将重试",
                detail=str(e),
            )

        soup = BeautifulSoup(resp.text, "lxml")

        # 提取文章链接列表
        article_links = self._extract_article_links(soup, source, domain)

        if not article_links:
            # 可能是文章详情页，直接提取
            item = self._extract_single_article(soup, source, source_name, resp.text)
            if item:
                return [item]
            raise WarnIssue(
                code="WEB_NO_LINKS",
                source=source_name,
                reason=f"网站「{source_name}」未找到新闻列表，可能是首页或特殊页面",
                suggestion="请提供该网站的具体新闻列表页地址（如 /news, /article 等）",
            )

        # 限制每源最多抓取30篇，避免过度请求
        article_links = article_links[:30]

        items: list[NewsItem] = []
        for link_info in article_links:
            url = link_info["url"]
            title = link_info["title"]

            # 获取正文
            try:
                article_resp = fetch_url(url, timeout=15)
                content = self._extract_content(article_resp.text)
                publish_time = self._extract_date(article_resp.text, soup)
            except (httpx.HTTPError, Exception) as e:
                logger.debug(f"获取文章正文失败 {url}: {e}")
                content = ""
                publish_time = None

            if not content or len(content) < 30:
                content = link_info.get("summary", "")

            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=source_name,
                    content=content,
                    summary=truncate_text(content, 300) if content else "",
                    publish_time=publish_time,
                )
            )

        logger.info(f"网站「{source_name}」收集到 {len(items)} 篇文章")
        return items

    def _extract_article_links(self, soup: BeautifulSoup, base_url: str, domain: str) -> list[dict]:
        """从页面中提取文章链接列表"""
        links: list[dict] = []
        seen_urls: set[str] = set()

        # 尝试预定义的列表选择器
        for selector in self.LIST_SELECTORS:
            elements = soup.select(selector)
            if elements:
                for el in elements:
                    href = el.get("href", "")
                    if not href:
                        continue
                    full_url = urljoin(base_url, href)
                    # 只保留同域名的链接
                    if domain not in urlparse(full_url).netloc:
                        continue
                    if full_url in seen_urls:
                        continue
                    title = clean_text(el.get_text())
                    if not title or len(title) < 5:
                        continue
                    seen_urls.add(full_url)
                    links.append({"url": full_url, "title": title})
                if links:
                    break

        # 如果预定义选择器没找到，用通用方法：查找所有带标题特征的链接
        if not links:
            for a_tag in soup.find_all("a", href=True):
                href = a_tag.get("href", "")
                full_url = urljoin(base_url, href)
                if domain not in urlparse(full_url).netloc:
                    continue
                if full_url in seen_urls:
                    continue
                title = clean_text(a_tag.get_text())
                # 过滤：标题长度5-100，排除导航类链接
                if not title or len(title) < 5 or len(title) > 100:
                    continue
                # 排除常见非文章链接
                skip_patterns = ["javascript:", "mailto:", "#", "login", "register", "about", "contact"]
                if any(p in full_url.lower() for p in skip_patterns):
                    continue
                seen_urls.add(full_url)
                links.append({"url": full_url, "title": title})

        return links

    def _extract_content(self, html: str) -> str:
        """使用trafilatura提取正文"""
        try:
            text = trafilatura.extract(
                html,
                include_links=False,
                include_tables=True,
                favor_precision=True,
            )
            return clean_text(text or "")
        except Exception:
            return ""

    def _extract_date(self, html: str, soup: BeautifulSoup) -> object:
        """从页面中提取发布日期"""
        # 尝试从meta标签提取
        for meta_name in ["article:published_time", "datePublished", "publishdate", "pubdate"]:
            meta = soup.find("meta", attrs={"property": meta_name}) or soup.find("meta", attrs={"name": meta_name})
            if meta and meta.get("content"):
                dt = parse_date(meta["content"])
                if dt:
                    return dt

        # 尝试从time标签提取
        time_tag = soup.find("time")
        if time_tag:
            dt = parse_date(time_tag.get("datetime") or time_tag.get_text())
            if dt:
                return dt

        # 尝试正则匹配
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, html)
            if match:
                dt = parse_date(match.group(1))
                if dt:
                    return dt

        return None

    def _extract_single_article(self, soup: BeautifulSoup, url: str, source_name: str, html: str) -> NewsItem | None:
        """提取单篇文章内容"""
        # 标题
        title = soup.find("title")
        title_text = clean_text(title.get_text()) if title else ""
        if not title_text:
            h1 = soup.find("h1")
            title_text = clean_text(h1.get_text()) if h1 else ""
        if not title_text:
            return None

        # 正文
        content = self._extract_content(html)
        if not content or len(content) < 50:
            return None

        publish_time = self._extract_date(html, soup)

        return NewsItem(
            title=title_text,
            url=url,
            source=source_name,
            content=content,
            summary=truncate_text(content, 300),
            publish_time=publish_time,
        )
