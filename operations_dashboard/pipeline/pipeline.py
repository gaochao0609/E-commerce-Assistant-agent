"""定义运营仪表盘的数据抓取与指标计算流程。"""

from __future__ import annotations

from datetime import date
from typing import Optional

from ..config import AppConfig
from ..data_sources.base import SalesDataSource
from ..metrics.calculations import DashboardSummary, build_dashboard_summary
from ..utils.dates import recent_period


class DashboardPipeline:
    """
    协调数据抓取与指标汇总的高层管道。

    构造函数需要注入应用配置与数据源，便于在不同上下文中复用。
    """

    def __init__(self, *, config: AppConfig, data_source: SalesDataSource) -> None:
        self._config = config
        self._data_source = data_source

    def run(
        self,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        top_n: Optional[int] = None,
    ) -> DashboardSummary:
        """
        功能说明:
            执行数据抓取与指标汇总，返回仪表盘摘要。
        参数:
            start (Optional[date]): 可选的开始日期。
            end (Optional[date]): 可选的结束日期。
            top_n (Optional[int]): 覆盖默认配置的 Top N 数量。
        返回:
            DashboardSummary: 汇总后的仪表盘结果。
        """
        if start is None or end is None:
            # 未显式指定时间窗口时，根据配置自动回退到最近窗口。
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
