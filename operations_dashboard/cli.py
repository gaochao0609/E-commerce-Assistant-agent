"""运营仪表盘演示的命令行入口，串联数据拉取与报告生成。"""

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .config import AmazonCredentialConfig, AppConfig, DashboardConfig, StorageConfig
from .data_sources.amazon_business_reports import create_default_mock_source
from .pipeline.pipeline import DashboardPipeline
from .reporting.formatter import format_text_report, summary_to_dict
from .storage.repository import SQLiteRepository

DATE_FMT = "%Y-%m-%d"
# CLI 中所有日期相关参数均采用统一的格式化规则，便于提示与校验。


def parse_args() -> argparse.Namespace:
    """
    功能说明:
        构建并解析命令行参数，返回解析后的命名空间。
    返回:
        argparse.Namespace: 包含用户指定的运行选项。
    """
    parser = argparse.ArgumentParser(description="Operations dashboard demo runner")
    parser.add_argument(
        "--mode",
        choices=["mock", "live"],
        default="mock",
        help="Use mock data or switch to live PAAPI (not implemented).",
    )
    parser.add_argument("--marketplace", default="US", help="Marketplace code, e.g. US/JP/DE.")
    parser.add_argument("--window-days", type=int, default=7, help="Rolling window length in days.")
    parser.add_argument("--top-n", type=int, default=10, help="How many top products to surface.")
    parser.add_argument("--start", type=str, help="Optional start date, format YYYY-MM-DD.")
    parser.add_argument("--end", type=str, help="Optional end date, format YYYY-MM-DD.")
    parser.add_argument("--output-json", type=Path, help="Path to save the JSON payload.")
    parser.add_argument("--persist", action="store_true", help="Persist summary into SQLite database.")
    parser.add_argument("--db-path", type=Path, help="Override database path when persisting.")
    parser.add_argument("--history", type=int, default=0, help="Show latest N historical summaries after saving.")
    return parser.parse_args()


def build_mock_config(args: argparse.Namespace) -> AppConfig:
    """
    功能说明:
        基于 CLI 解析结果生成一个用于本地演示的 Mock 配置。
    参数:
        args (argparse.Namespace): 命令行解析得到的参数集合。
    返回:
        AppConfig: 用于后续管道运行的配置对象。
    """
    amazon = AmazonCredentialConfig(
        access_key="mock",
        secret_key="mock",
        associate_tag=None,
        marketplace=args.marketplace,
    )
    dashboard = DashboardConfig(
        marketplace=args.marketplace,
        refresh_window_days=args.window_days,
        top_n_products=args.top_n,
    )
    storage_enabled = args.persist or args.db_path is not None
    storage = StorageConfig(
        enabled=storage_enabled,
        db_path=str(args.db_path) if args.db_path else "operations_dashboard.sqlite3",
    )
    return AppConfig(amazon=amazon, dashboard=dashboard, storage=storage)


def parse_date(value: Optional[str]) -> Optional[date]:
    """
    功能说明:
        将 `YYYY-MM-DD` 字符串解析为 `date` 对象。
    参数:
        value (Optional[str]): 用户输入的日期字符串，可为空。
    返回:
        Optional[date]: 成功解析后的日期；若为空则返回 `None`。
    """
    if not value:
        return None
    return datetime.strptime(value, DATE_FMT).date()


def persist_summary(config: AppConfig, summary) -> SQLiteRepository:
    """
    功能说明:
        将生成的仪表盘摘要持久化到 SQLite 数据库。
    参数:
        config (AppConfig): 提供数据库路径及启用信息。
        summary: 打包后的仪表盘汇总对象。
    返回:
        SQLiteRepository: 已初始化且写入完成的仓库实例。
    """
    repo = SQLiteRepository(config.storage.db_path)
    repo.initialize()
    summary_id = repo.save_summary(summary)
    print(f"Summary saved to {config.storage.db_path} (id={summary_id}).")
    return repo


def run_cli() -> None:
    """
    功能说明:
        命令行主入口：读取参数、执行管道、输出报告并根据需要持久化。
    """
    args = parse_args()
    if args.mode == "live":
        raise NotImplementedError(
            "Live Amazon integration is not wired yet. Use --mode mock or plug in a real data source."
        )

    config = build_mock_config(args)
    data_source = create_default_mock_source(config)
    pipeline = DashboardPipeline(config=config, data_source=data_source)

    start = parse_date(args.start)
    end = parse_date(args.end)
    summary = pipeline.run(start=start, end=end, top_n=args.top_n)

    report_text = format_text_report(summary)
    print(report_text)

    if args.output_json:
        # 将汇总转为 JSON 并写入文件，encode 为 UTF-8 以保留中文字符。
        payload = summary_to_dict(summary)
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"JSON report written to: {args.output_json}")

    repo: Optional[SQLiteRepository] = None
    if config.storage.enabled:
        repo = persist_summary(config, summary)

    if repo and args.history > 0:
        print(f"\n最近 {args.history} 期历史概览：")
        for stored in repo.fetch_recent_summaries(limit=args.history):
            revenue_str = f"{stored.total_revenue:,.2f}"
            print(
                f"[{stored.id}] {stored.start}~{stored.end} | Revenue {revenue_str} | "
                f"Units {stored.total_units} | Sessions {stored.total_sessions}"
            )


if __name__ == "__main__":  # pragma: no cover
    run_cli()
