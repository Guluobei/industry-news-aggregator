"""行业新闻聚合推送器 - 微信公众号收集器"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import feedparser
import httpx
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.collectors.rss_collector import RSSCollector
from src.issues import ErrorIssue, IssueTracker, WarnIssue
from src.models import NewsItem
from src.utils import fetch_url, parse_date

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class WeChatCollector(BaseCollector):
    """微信公众号收集器

    采集策略（按优先级自动降级）：
    1. 用户已知公众号ID（KNOWN_ACCOUNTS或自定义）→ 走RSSHub
    2. 未知公众号ID → 通过RSSHub搜索接口查找
    3. RSSHub不可用时 → 通过搜狗微信搜索降级
    """

    # 已知公众号名称 → 微信ID映射（可手动维护扩展）
    # 微信ID即公众号URL中的微信号，如 https://mp.weixin.qq.com/s/xxx 中的 __biz 参数
    KNOWN_ACCOUNTS: dict[str, str] = {
        "中国保险报": "zgbxb_2012",
        "保观": "Insurance-Review",
        "银保监微课堂": "cbirc_wechat",
        "慧保天下": "hbtxgb",
        "券商中国": "quanshangcn",
        "21世纪经济报道": "jjbd21",
        "财新网": "caixinwang",
        "澎湃新闻": "thepapernews",
    }

    # 搜狗微信搜索（RSSHub不可用时的降级方案）
    SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"
    SOGOU_ARTICLE_URL = "https://weixin.sogou.com"

    def collect(self, source: str, issue_tracker: IssueTracker, **kwargs) -> list[NewsItem]:
        """
        从微信公众号收集新闻

        Args:
            source: "公众号:名称" 格式或公众号名称
            issue_tracker: 问题追踪器
        """
        rsshub_url = kwargs.get("rsshub_url", "http://localhost:1200")

        # 解析公众号名称
        account_name = self._parse_account_name(source)
        source_name = f"公众号:{account_name}"

        # Step 1: 检查RSSHub是否可用（不再作为致命错误，降级为提示）
        rsshub_available = self._check_rsshub(rsshub_url, issue_tracker)

        # Step 2: 获取微信ID
        wechat_id = self.KNOWN_ACCOUNTS.get(account_name)

        if not wechat_id and rsshub_available:
            wechat_id = self._search_account_id_via_rsshub(account_name, rsshub_url)

        if not wechat_id:
            # 降级：通过搜狗搜索查找公众号
            wechat_id = self._search_account_id_via_sogou(account_name, issue_tracker)

        if not wechat_id:
            raise ErrorIssue(
                code="WECHAT_NOT_FOUND",
                source=source_name,
                reason=f"未找到公众号「{account_name}」，可能名称有误或该公众号未被收录",
                suggestion="请确认公众号名称是否正确，或在配置中手动添加微信ID（KNOWN_ACCOUNTS字典）",
            )

        # Step 3: 通过RSSHub或搜狗获取文章
        if rsshub_available:
            try:
                items = self._collect_via_rsshub(rsshub_url, wechat_id, source_name, account_name, issue_tracker)
            except ErrorIssue as e:
                if "404" in e.issue.reason or "NOT_FOUND" in e.issue.code:
                    # RSSHub获取失败，降级到搜狗
                    logger.warning(f"RSSHub获取失败，降级到搜狗搜索: {account_name}")
                    items = self._collect_via_sogou(account_name, source_name, issue_tracker)
                else:
                    raise
        else:
            # RSSHub不可用，直接走搜狗
            items = self._collect_via_sogou(account_name, source_name, issue_tracker)

        # Step 4: 检查是否长期无更新
        if items:
            from datetime import datetime, timezone

            latest = items[0]
            if latest.publish_time:
                now = datetime.now(timezone.utc)
                if latest.publish_time.tzinfo is None:
                    latest.publish_time = latest.publish_time.replace(tzinfo=timezone.utc)
                days_since = (now - latest.publish_time).days
                if days_since > 30:
                    issue_tracker.record(WarnIssue(
                        code="WECHAT_STALE",
                        source=source_name,
                        reason=f"公众号「{account_name}」已超过{days_since}天未更新，最近一篇文章发布于{latest.publish_time.strftime('%Y-%m-%d')}",
                        suggestion="如确认该公众号已停更，建议从配置中移除",
                    ).issue)

        if not items:
            # 区分不同原因
            if not rsshub_available:
                # RSSHub不可用 + 搜狗也搜不到
                raise WarnIssue(
                    code="WECHAT_NEED_RSSHUB",
                    source=source_name,
                    reason=f"公众号「{account_name}」采集需要RSSHub支持",
                    suggestion="请部署自建RSSHub（推荐）或使用支持公众号的第三方RSS服务。当前无RSSHub时无法采集公众号内容",
                )
            raise WarnIssue(
                code="WECHAT_EMPTY",
                source=source_name,
                reason=f"公众号「{account_name}」在指定时间范围内没有发布新文章",
                suggestion="正常现象，下次执行时将自动检查",
            )

        logger.info(f"公众号「{account_name}」收集到 {len(items)} 篇文章")
        return items

    def _parse_account_name(self, source: str) -> str:
        """从源标识中解析公众号名称"""
        if source.startswith("公众号:") or source.startswith("公众号："):
            return source.split(":", 1)[-1].split("：", 1)[-1].strip()
        return source.strip()

    def _check_rsshub(self, rsshub_url: str, issue_tracker: IssueTracker) -> bool:
        """检查RSSHub服务是否可用（不抛致命错误，返回bool）"""
        try:
            resp = httpx.get(f"{rsshub_url.rstrip('/')}/", timeout=10)
            if resp.status_code == 200:
                return True
            issue_tracker.record(WarnIssue(
                code="RSSHUB_DOWN",
                source="RSSHub服务",
                reason=f"RSSHub服务异常（HTTP {resp.status_code}）",
                suggestion="公众号采集将自动降级到搜狗微信搜索。如需启用RSSHub，请检查服务状态",
            ).issue)
            return False
        except httpx.ConnectError:
            issue_tracker.record(WarnIssue(
                code="RSSHUB_UNREACHABLE",
                source="RSSHub服务",
                reason="无法连接RSSHub服务",
                suggestion="公众号采集将自动降级到搜狗微信搜索。如需启用RSSHub，请先启动服务",
            ).issue)
            return False
        except httpx.TimeoutException:
            issue_tracker.record(WarnIssue(
                code="RSSHUB_TIMEOUT",
                source="RSSHub服务",
                reason="RSSHub服务响应超时",
                suggestion="公众号采集将自动降级到搜狗微信搜索",
            ).issue)
            return False
        except Exception as e:
            logger.debug(f"RSSHub健康检查异常: {e}")
            return False

    def _search_account_id_via_rsshub(self, name: str, rsshub_url: str) -> str | None:
        """通过RSSHub搜索接口查找公众号ID"""
        search_url = f"{rsshub_url.rstrip('/')}/wechat/mp/search/{name}"
        try:
            resp = fetch_url(search_url, timeout=15)
            feed = feedparser.parse(resp.text)
            if feed.entries:
                link = feed.entries[0].get("link", "")
                if "__biz" in link:
                    match = re.search(r"__biz=([^&]+)", link)
                    if match:
                        return match.group(1)
            return None
        except Exception as e:
            logger.debug(f"RSSHub搜索公众号ID失败: {e}")
            return None

    def _collect_via_rsshub(
        self,
        rsshub_url: str,
        wechat_id: str,
        source_name: str,
        account_name: str,
        issue_tracker: IssueTracker,
    ) -> list[NewsItem]:
        """通过RSSHub获取公众号文章"""
        rss_url = f"{rsshub_url.rstrip('/')}/wechat/mp/{wechat_id}"
        return RSSCollector().collect(rss_url, issue_tracker, source_name=source_name)

    def _search_account_id_via_sogou(
        self,
        name: str,
        issue_tracker: IssueTracker,
    ) -> str | None:
        """通过搜狗微信搜索查找公众号ID

        Returns:
            公众号的__biz参数（用作唯一标识）
        """
        try:
            params = {"type": "1", "query": name}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://weixin.sogou.com/",
            }
            resp = httpx.get(self.SOGOU_SEARCH_URL, params=params, headers=headers, timeout=15, follow_redirects=True)
            resp.raise_for_status()

            # 解析搜狗搜索结果，提取公众号__biz
            # 搜狗返回的HTML中包含目标公众号的链接
            html = resp.text
            # 查找 __biz 参数
            matches = re.findall(r'__biz=([A-Za-z0-9%+/=]+)', html)
            if matches:
                return matches[0]
            return None
        except Exception as e:
            logger.debug(f"搜狗搜索公众号ID失败: {e}")
            return None

    def _collect_via_sogou(
        self,
        account_name: str,
        source_name: str,
        issue_tracker: IssueTracker,
    ) -> list[NewsItem]:
        """通过搜狗微信搜索获取公众号文章列表"""
        items: list[NewsItem] = []

        try:
            # Step 1: 搜索公众号主页
            params = {"type": "1", "query": account_name}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://weixin.sogou.com/",
            }
            resp = httpx.get(self.SOGOU_SEARCH_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()

            # Step 2: 从搜索结果中提取公众号最新文章列表
            soup = BeautifulSoup(resp.text, "lxml")

            # 搜狗搜索结果中，文章列表位于 .news-list 或 .s-p-top 类的容器
            article_blocks = soup.select("li[class*='news']") or soup.select(".s-p") or soup.select("li")

            for block in article_blocks[:15]:  # 最多15条
                try:
                    # 提取标题
                    title_elem = block.select_one("a") or block.select_one("h3") or block.select_one(".tit")
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue

                    # 提取链接
                    href = ""
                    for a in block.select("a[href]"):
                        href = a.get("href", "")
                        if href and "javascript:" not in href:
                            break
                    if not href:
                        continue

                    # 搜狗返回的是中间页URL，需要拼接
                    if href.startswith("/"):
                        full_url = self.SOGOU_ARTICLE_URL + href
                    elif href.startswith("http"):
                        full_url = href
                    else:
                        continue

                    # 提取摘要
                    summary_elem = block.select_one(".txt-info, .txt, p")
                    summary = summary_elem.get_text(strip=True) if summary_elem else ""

                    # 提取时间（搜狗通常显示 "1天前"、"刚刚" 等）
                    time_elem = block.select_one(".s-p, .time, .date, em")
                    time_text = time_elem.get_text(strip=True) if time_elem else ""
                    publish_time = self._parse_sogou_time(time_text)

                    items.append(NewsItem(
                        title=title,
                        url=full_url,
                        source=f"公众号:{account_name}",
                        content=summary,
                        summary=summary[:300] if summary else "",
                        publish_time=publish_time,
                    ))
                except Exception as e:
                    logger.debug(f"解析搜狗文章块失败: {e}")
                    continue

            if not items:
                logger.warning(f"搜狗搜索未找到「{account_name}」的文章，搜狗可能加强了反爬")

        except httpx.HTTPStatusError as e:
            raise ErrorIssue(
                code="WECHAT_SOGOU_BLOCKED",
                source=source_name,
                reason=f"搜狗微信搜索返回HTTP {e.response.status_code}，可能触发了反爬",
                suggestion="建议部署自建RSSHub以获得稳定的公众号采集能力",
            )
        except Exception as e:
            raise ErrorIssue(
                code="WECHAT_SOGOU_FAILED",
                source=source_name,
                reason=f"通过搜狗采集公众号失败：{type(e).__name__}",
                suggestion="建议部署自建RSSHub以获得稳定的公众号采集能力",
                detail=str(e),
            )

        return items

    def _parse_sogou_time(self, time_text: str) -> object:
        """解析搜狗时间格式（如"2小时前"、"昨天"、"3天前"）"""
        from datetime import datetime, timedelta, timezone

        if not time_text:
            return None

        now = datetime.now(timezone.utc)

        # 处理相对时间
        if "刚刚" in time_text:
            return now
        if "分钟前" in time_text:
            match = re.search(r"(\d+)\s*分钟前", time_text)
            if match:
                return now - timedelta(minutes=int(match.group(1)))
        if "小时前" in time_text:
            match = re.search(r"(\d+)\s*小时前", time_text)
            if match:
                return now - timedelta(hours=int(match.group(1)))
        if "昨天" in time_text:
            return now - timedelta(days=1)
        if "天前" in time_text:
            match = re.search(r"(\d+)\s*天前", time_text)
            if match:
                return now - timedelta(days=int(match.group(1)))
        if "周前" in time_text:
            match = re.search(r"(\d+)\s*周前", time_text)
            if match:
                return now - timedelta(weeks=int(match.group(1)))

        # 尝试标准日期解析
        return parse_date(time_text)
