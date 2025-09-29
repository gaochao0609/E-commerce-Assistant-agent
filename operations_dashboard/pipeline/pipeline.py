from __future__ import annotations

from datetime import date
from typing import Optional

from ..config import AppConfig
from ..data_sources.base import SalesDataSource
from ..metrics.calculations import DashboardSummary, build_dashboard_summary
from ..utils.dates import recent_period


class DashboardPipeline:
    """调度数据采集与 KPI 汇总的主流程。"""

    def __init__(self, *, config: AppConfig, data_source: SalesDataSource) -> None:
        """初始化管道。

        参数:
            config: 全局配置对象，提供默认窗口、Top N 等参数。
            data_source: 实际的数据源实现（可为真实或模拟）。
        """
        self._config = config
        self._data_source = data_source

    def run(
        self,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        top_n: Optional[int] = None,
    ) -> DashboardSummary:
        """执行一次汇总。

        参数:
            start: 自定义统计开始日期，未提供则使用配置窗口。
            end: 自定义统计结束日期。
            top_n: 覆盖默认的重点商品数量。

        返回:
            DashboardSummary，包含整体指标与重点商品列表。
        """
        if start is None or end is None:
            window_days = self._config.dashboard.refresh_window_days
            start, end = recent_period(window_days)

        sales_records = self._data_source.fetch_sales(start, end)
        traffic_records = self._data_source.fetch_traffic(start, end)

        summary = build_dashboard_summary(
            source_name=self._data_source.name,
            start=start,
            end=end,
            sales_records=sales_records,
            traffic_records=traffic_records,
            top_n=top_n or self._config.dashboard.top_n_products,
        )
        return summary
