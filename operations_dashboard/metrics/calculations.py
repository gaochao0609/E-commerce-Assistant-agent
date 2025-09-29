"""提供仪表盘 KPI 汇总及 Top 商品排名的计算逻辑。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List

from ..data_sources.base import SalesRecord, TrafficRecord


@dataclass
class KPIOverview:
    """
    描述一个时间窗口内的顶层 KPI 指标。

    属性:
        total_revenue (float): 总销售额。
        total_units (int): 总销量。
        total_sessions (int): 总会话数。
        conversion_rate (float): 综合转化率。
        refund_rate (float): 退款率。
    """

    total_revenue: float
    total_units: int
    total_sessions: int
    conversion_rate: float
    refund_rate: float


@dataclass
class ProductPerformance:
    """
    记录单个 ASIN 的核心表现指标。

    属性:
        asin (str): 商品 ASIN。
        title (str): 商品标题。
        revenue (float): 销售额。
        units (int): 销量。
        sessions (int): 会话数。
        conversion_rate (float): 转化率。
        refunds (int): 退款数量。
        buy_box_percentage (float | None): 购物车占有率。
    """

    asin: str
    title: str
    revenue: float
    units: int
    sessions: int
    conversion_rate: float
    refunds: int
    buy_box_percentage: float | None


@dataclass
class DashboardSummary:
    """
    封装仪表盘汇总结果，供前端或导出使用。

    属性:
        start (date): 窗口开始日期。
        end (date): 窗口结束日期。
        source_name (str): 数据来源名称。
        totals (KPIOverview): 顶层 KPI 概览。
        top_products (List[ProductPerformance]): Top 商品表现列表。
    """

    start: date
    end: date
    source_name: str
    totals: KPIOverview
    top_products: List[ProductPerformance]


def build_dashboard_summary(
    *,
    source_name: str,
    start: date,
    end: date,
    sales_records: List[SalesRecord],
    traffic_records: List[TrafficRecord],
    top_n: int = 10,
) -> DashboardSummary:
    """
    功能说明:
        汇总销量与流量记录，生成仪表盘需要的 KPI 与 Top 商品列表。
    参数:
        source_name (str): 数据来源名称。
        start (date): 窗口开始日期。
        end (date): 窗口结束日期。
        sales_records (List[SalesRecord]): 销售记录。
        traffic_records (List[TrafficRecord]): 流量记录。
        top_n (int): 需要保留的 Top 商品数量。
    返回:
        DashboardSummary: 汇总后的仪表盘摘要。
    """
    aggregated = _aggregate_by_asin(sales_records, traffic_records)

    total_revenue = sum(item["revenue"] for item in aggregated.values())
    total_units = sum(item["units"] for item in aggregated.values())
    total_sessions = sum(item["sessions"] for item in aggregated.values())
    total_refunds = sum(item["refunds"] for item in aggregated.values())
    conversion_rate = (total_units / total_sessions) if total_sessions else 0
    refund_rate = (total_refunds / total_units) if total_units else 0

    top_products = [
        ProductPerformance(
            asin=asin,
            title=values["title"],
            revenue=round(values["revenue"], 2),
            units=values["units"],
            sessions=values["sessions"],
            conversion_rate=round(values["conversion"], 4),
            refunds=values["refunds"],
            buy_box_percentage=round(values["buy_box"], 2) if values["buy_box"] is not None else None,
        )
        for asin, values in sorted(
            aggregated.items(),
            key=lambda item: item[1]["revenue"],
            reverse=True,
        )[:top_n]
    ]

    totals = KPIOverview(
        total_revenue=round(total_revenue, 2),
        total_units=total_units,
        total_sessions=total_sessions,
        conversion_rate=round(conversion_rate, 4),
        refund_rate=round(refund_rate, 4),
    )

    return DashboardSummary(
        start=start,
        end=end,
        source_name=source_name,
        totals=totals,
        top_products=top_products,
    )


def _aggregate_by_asin(
    sales_records: List[SalesRecord],
    traffic_records: List[TrafficRecord],
) -> Dict[str, Dict[str, float | int | None]]:
    """
    功能说明:
        将销量与流量数据按 ASIN 聚合。
    参数:
        sales_records (List[SalesRecord]): 销售记录列表。
        traffic_records (List[TrafficRecord]): 流量记录列表。
    返回:
        Dict[str, Dict[str, float | int | None]]: 每个 ASIN 对应的聚合指标字典。
    """
    aggregated: Dict[str, Dict[str, float | int | None]] = {}

    for record in sales_records:
        asin_entry = aggregated.setdefault(
            record.asin,
            {
                "title": record.title,
                "revenue": 0.0,
                "units": 0,
                "sessions_estimate": 0,
                "sessions": 0,
                "conversion": 0.0,
                "refunds": 0,
                "buy_box_sum": 0.0,
                "buy_box_count": 0,
                "buy_box": None,
            },
        )
        asin_entry["title"] = record.title or asin_entry["title"]
        asin_entry["revenue"] += record.ordered_revenue
        asin_entry["units"] += record.units_ordered
        asin_entry["sessions_estimate"] += record.sessions
        asin_entry["refunds"] += record.refunds

    for record in traffic_records:
        asin_entry = aggregated.setdefault(
            record.asin,
            {
                "title": "Unknown ASIN",
                "revenue": 0.0,
                "units": 0,
                "sessions_estimate": 0,
                "sessions": 0,
                "conversion": 0.0,
                "refunds": 0,
                "buy_box_sum": 0.0,
                "buy_box_count": 0,
                "buy_box": None,
            },
        )
        asin_entry["sessions"] += record.sessions
        asin_entry["buy_box_sum"] += record.buy_box_percentage
        asin_entry["buy_box_count"] += 1

    for asin, values in aggregated.items():
        sessions = values["sessions"] or values["sessions_estimate"]
        units = values["units"]
        values["sessions"] = sessions
        values["conversion"] = (units / sessions) if sessions else 0.0
        if values["buy_box_count"]:
            values["buy_box"] = values["buy_box_sum"] / values["buy_box_count"]
        else:
            values["buy_box"] = None

    return aggregated
