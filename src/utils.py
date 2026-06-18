"""行业新闻聚合推送器 - 工具函数"""

from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urljoin

import httpx
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)

# 常用User-Agent列表（随机轮换，降低反爬风险）
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def random_ua() -> str:
    """返回随机User-Agent"""
    return random.choice(USER_AGENTS)


def default_headers() -> dict[str, str]:
    """返回默认请求头"""
    return {
        "User-Agent": random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def fetch_url(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    timeout: int = 20,
    follow_redirects: bool = True,
) -> httpx.Response:
    """发送HTTP请求，带默认头和重试"""
    final_headers = default_headers()
    if headers:
        final_headers.update(headers)

    with httpx.Client(follow_redirects=follow_redirects, timeout=timeout) as client:
        resp = client.request(method, url, headers=final_headers)
        resp.raise_for_status()
        return resp


def parse_date(date_str: str | None) -> datetime | None:
    """解析各种格式的日期字符串"""
    if not date_str:
        return None
    try:
        dt = date_parser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError, OverflowError):
        return None


def is_within_hours(dt: datetime | None, hours: int) -> bool:
    """判断日期是否在指定小时范围内"""
    if dt is None:
        return True  # 无法判断日期时默认保留
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    return diff.total_seconds() <= hours * 3600


def clean_text(text: str | None) -> str:
    """清理文本：去除多余空白、HTML实体等"""
    if not text:
        return ""
    # 去除HTML标签
    text = re.sub(r"<[^>]+>", "", text)
    # 合并连续空白
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate_text(text: str, max_length: int) -> str:
    """截断文本到指定长度"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def normalize_url(url: str, base_url: str = "") -> str:
    """规范化URL（补全相对路径）"""
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if base_url:
        return urljoin(base_url, url)
    return url


def get_domain(url: str) -> str:
    """获取URL的域名"""
    parsed = urlparse(url)
    return parsed.netloc or ""
