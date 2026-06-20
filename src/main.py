"""行业新闻聚合推送器 - 主入口"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from src.collectors.detector import SourceDetector
from src.collectors.registry import CollectorRegistry
from src.config import AppConfig
from src.filters.engine import FilterEngine
from src.issues import ErrorIssue, FatalIssue, Issue, IssueTracker, IssueLevel, WarnIssue
from src.models import ExecutionResult, NewsItem
from src.notifier import NotificationRouter
from src.pushers.email_pusher import EmailPusher
from src.pushers.feishu_pusher import FeishuPusher
from src.pushers.local_pusher import LocalPusher

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run(config_path: str, dry_run: bool = False, verbose: bool = False) -> ExecutionResult:
    """
    执行新闻收集推送流程

    Args:
        config_path: 配置文件路径
        dry_run: 试运行模式（仅输出不推送）
        verbose: 详细日志

    Returns:
        执行结果
    """
    setup_logging(verbose)

    now = datetime.now()
    result = ExecutionResult(date=now.strftime("%Y-%m-%d"))
    issue_tracker = IssueTracker()

    logger.info("=" * 60)
    logger.info(f"行业新闻聚合推送器启动 - {now.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # ========== Step 1: 加载配置 ==========
    try:
        config = AppConfig.from_yaml(config_path)
        logger.info(f"配置加载成功：{len(config.sources)} 个信息源")
    except Exception as e:
        issue_tracker.record(Issue(
            code="CONFIG_LOAD_FAILED",
            level=IssueLevel.FATAL,
            source="配置加载",
            reason=f"配置文件加载失败：{type(e).__name__}",
            suggestion="请检查配置文件格式是否正确",
            detail=str(e),
        ))
        result.total_sources = 0
        return result

    result.total_sources = len(config.sources)

    # 校验推送渠道
    try:
        available_channels = config.validate_push_channels()
        logger.info(f"可用推送渠道：{available_channels}")
    except ValueError as e:
        issue_tracker.record(Issue(
            code="NO_PUSH_CHANNEL",
            level=IssueLevel.FATAL,
            source="推送配置",
            reason=str(e),
            suggestion="请在配置文件中至少启用一个推送渠道",
        ))
        return result

    # ========== Step 2: 收集新闻 ==========
    logger.info("-" * 40)
    logger.info("开始收集新闻...")
    logger.info("-" * 40)

    detector = SourceDetector()
    all_items: list[NewsItem] = []
    success_count = 0
    failed_count = 0

    # 扩展 sources：将 wechat_accounts 转成 "公众号:..." 形式
    extended_sources = list(config.sources)
    if config.wechat_accounts.enabled:
        for acc in config.wechat_accounts.accounts:
            source = f"公众号:{acc.name}"
            if acc.backend:
                source += f":backend={acc.backend}"
            if acc.feed_id:
                source += f":feed_id={acc.feed_id}"
            extended_sources.append(source)
        logger.info(f"从 wechat_accounts 追加 {len(config.wechat_accounts.accounts)} 个公众号源")

    for source in extended_sources:
        source_name = source[:50] + "..." if len(source) > 50 else source
        logger.info(f"正在处理信息源：{source_name}")

        try:
            # 自动识别类型
            collector_type = detector.detect(source, issue_tracker)
            logger.info(f"  → 识别为 {collector_type} 类型")

            # 获取收集器
            if collector_type == "wechat":
                wechat_config_dict = config.wechat_accounts.to_legacy_dict()
            else:
                wechat_config_dict = None

            collector = CollectorRegistry.get(collector_type, config=wechat_config_dict)
            if collector is None:
                raise ErrorIssue(
                    code="COLLECTOR_NOT_FOUND",
                    source=source_name,
                    reason=f"未找到 {collector_type} 类型的收集器",
                    suggestion="请检查系统是否正确安装所有收集器",
                )

            # 执行收集
            kwargs = {"source_name": source_name}

            items = collector.collect(source, issue_tracker, **kwargs)
            all_items.extend(items)
            success_count += 1
            logger.info(f"  → 收集到 {len(items)} 篇文章")

        except FatalIssue as e:
            # 致命错误：终止整个流程
            issue_tracker.record(e.issue)
            failed_count += 1
            break

        except (ErrorIssue, WarnIssue) as e:
            # 非致命错误：记录并继续
            issue_tracker.record(e.issue)
            failed_count += 1

        except Exception as e:
            # 未知异常：记录为ERROR并继续
            issue_tracker.record(Issue(
                code="COLLECT_UNKNOWN_ERROR",
                level=IssueLevel.ERROR,
                source=source_name,
                reason=f"收集过程中出现未知错误：{type(e).__name__}",
                suggestion="该源本次跳过，下次执行时将重试",
                detail=str(e),
            ))
            failed_count += 1

    result.success_sources = success_count
    result.failed_sources = failed_count
    result.total_collected = len(all_items)

    logger.info(f"收集完成：成功{success_count}个源，失败{failed_count}个源，共{len(all_items)}篇文章")

    # 如果有致命错误，直接发送通知
    if issue_tracker.has_fatal():
        logger.error("存在致命错误，跳过筛选和推送")
        _send_notification(config, [], result, issue_tracker, dry_run)
        return result

    # ========== Step 3: 筛选排序 ==========
    logger.info("-" * 40)
    logger.info("开始筛选排序...")
    logger.info("-" * 40)

    filter_engine = FilterEngine()
    filtered_items = filter_engine.process(all_items, config.filter, issue_tracker)
    result.filtered_count = len(filtered_items)

    logger.info(f"筛选完成：{len(all_items)} → {len(filtered_items)} 条")

    # ========== Step 4: 推送 ==========
    logger.info("-" * 40)
    logger.info("开始推送...")
    logger.info("-" * 40)

    if not dry_run:
        _push_to_channels(config, filtered_items, result, issue_tracker)
    else:
        logger.info("试运行模式：跳过推送，仅输出到本地")
        if config.push.local.enabled:
            LocalPusher().push(
                filtered_items, issue_tracker, result,
                config=config.push.local,
                industry=config.filter.industry,
            )

    # ========== Step 5: 发送执行报告通知 ==========
    _send_notification(config, filtered_items, result, issue_tracker, dry_run)

    logger.info("=" * 60)
    logger.info(f"执行完成 - 状态：{issue_tracker.get_status_label()}")
    logger.info(f"  信息源：{result.total_sources}个（成功{result.success_sources}，失败{result.failed_sources}）")
    logger.info(f"  收集文章：{result.total_collected}篇")
    logger.info(f"  筛选后：{result.filtered_count}条")
    logger.info(f"  推送渠道：{result.pushed_channels or '无'}")
    logger.info("=" * 60)

    return result


def _push_to_channels(
    config: AppConfig,
    items: list[NewsItem],
    result: ExecutionResult,
    issue_tracker: IssueTracker,
) -> None:
    """推送到所有已启用的渠道"""
    industry = config.filter.industry

    # 飞书推送
    if config.push.feishu.enabled:
        try:
            FeishuPusher().push(
                items, issue_tracker, result,
                config=config.push.feishu,
                industry=industry,
            )
        except FatalIssue as e:
            issue_tracker.record(e.issue)
        except Exception as e:
            issue_tracker.record(Issue(
                code="FEISHU_PUSH_ERROR",
                level=IssueLevel.ERROR,
                source="飞书推送",
                reason=f"飞书推送出现未知错误：{type(e).__name__}",
                suggestion="请查看日志获取详细信息",
                detail=str(e),
            ))

    # 邮件推送
    if config.push.email.enabled:
        try:
            EmailPusher().push(
                items, issue_tracker, result,
                config=config.push.email,
                industry=industry,
            )
        except FatalIssue as e:
            issue_tracker.record(e.issue)
        except Exception as e:
            issue_tracker.record(Issue(
                code="EMAIL_PUSH_ERROR",
                level=IssueLevel.ERROR,
                source="邮箱推送",
                reason=f"邮箱推送出现未知错误：{type(e).__name__}",
                suggestion="请查看日志获取详细信息",
                detail=str(e),
            ))

    # 本地文件推送
    if config.push.local.enabled:
        try:
            LocalPusher().push(
                items, issue_tracker, result,
                config=config.push.local,
                industry=industry,
            )
        except Exception as e:
            issue_tracker.record(Issue(
                code="LOCAL_PUSH_ERROR",
                level=IssueLevel.ERROR,
                source="本地文件推送",
                reason=f"本地文件推送出现未知错误：{type(e).__name__}",
                suggestion="请查看日志获取详细信息",
                detail=str(e),
            ))


def _send_notification(
    config: AppConfig,
    items: list[NewsItem],
    result: ExecutionResult,
    issue_tracker: IssueTracker,
    dry_run: bool,
) -> None:
    """发送执行报告通知"""
    if dry_run:
        logger.info("试运行模式：跳过通知发送")
        return

    try:
        router = NotificationRouter(config)
        router.send_report(items, result, issue_tracker)
    except Exception as e:
        logger.error(f"通知发送失败：{e}")


def main() -> None:
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="行业新闻聚合推送器 - 自动收集、筛选、推送行业资讯",
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="配置文件路径（默认：config.yaml）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式：仅输出到本地，不推送",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细日志输出",
    )

    args = parser.parse_args()

    result = run(args.config, dry_run=args.dry_run, verbose=args.verbose)

    # 退出码：有致命错误返回1，否则返回0
    sys.exit(1 if result.failed_sources > 0 and result.success_sources == 0 else 0)


if __name__ == "__main__":
    main()
