"""收集器注册表 - 自动注册所有收集器"""

from src.collectors.base import BaseCollector, CollectorRegistry
from src.collectors.rss_collector import RSSCollector
from src.collectors.web_collector import WebCollector
from src.collectors.wechat_collector import WeChatCollector
from src.collectors.api_collector import APICollector
from src.collectors.detector import SourceDetector

# 注册收集器
CollectorRegistry.register("rss", RSSCollector)
CollectorRegistry.register("web", WebCollector)
CollectorRegistry.register("wechat", WeChatCollector)
CollectorRegistry.register("api", APICollector)

__all__ = [
    "BaseCollector",
    "CollectorRegistry",
    "SourceDetector",
    "RSSCollector",
    "WebCollector",
    "WeChatCollector",
    "APICollector",
]
