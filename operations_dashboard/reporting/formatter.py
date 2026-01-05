"""提供仪表盘摘要的结构化格式化工具。"""

from __future__ import annotations

from typing import Dict

from ..metrics.calculations import DashboardSummary


def summary_to_dict(summary: DashboardSummary) -> Dict[str, object]:
    """
    功能说明:
        将 DashboardSummary 转换为可 JSON 序列化的字典。
    参数:
        summary (DashboardSummary): 仪表盘汇总对象。
    返回:
        Dict[str, object]: 序列化后的摘要结构。
    """
    return {
        "source": summary.source_name,
        "window": {
            "start": summary.start.isoformat(),
            "end": summary.end.isoformat(),
        },
        "totals": {
            "revenue": summary.totals.total_revenue,
            "units": summary.totals.total_units,
            "sessions": summary.totals.total_sessions,
            "conversion_rate": summary.totals.conversion_rate,
            "refund_rate": summary.totals.refund_rate,
        },
        "top_products": [
            {
                "asin": product.asin,
                "title": product.title,
                "revenue": product.revenue,
                "units": product.units,
                "sessions": product.sessions,
                "conversion_rate": product.conversion_rate,
                "refunds": product.refunds,
                "buy_box_percentage": product.buy_box_percentage,
            }
            for product in summary.top_products
        ],
    }
