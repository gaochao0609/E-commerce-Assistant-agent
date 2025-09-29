"""提供仪表盘摘要的结构化与文本格式化工具。"""

from __future__ import annotations

from typing import Dict, List

from ..metrics.calculations import DashboardSummary, ProductPerformance


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


def _format_product_line(idx: int, product: ProductPerformance) -> str:
    """
    功能说明:
        将单个商品表现格式化为人类可读的文本。
    参数:
        idx (int): 商品排名序号。
        product (ProductPerformance): 商品表现数据。
    返回:
        str: 格式化后的文本行。
    """
    buy_box = (
        f"Buy Box {product.buy_box_percentage:.2f}%"
        if product.buy_box_percentage is not None
        else "Buy Box n/a"
    )
    revenue = "$" + format(product.revenue, ",.2f")
    return (
        f"{idx}. {product.title} ({product.asin}) - Revenue {revenue}, "
        f"Units {product.units}, Sessions {product.sessions}, "
        f"CVR {product.conversion_rate:.2%}, Refunds {product.refunds}, {buy_box}"
    )


def format_text_report(summary: DashboardSummary) -> str:
    """
    功能说明:
        生成适合在控制台展示的运营日报文本。
    参数:
        summary (DashboardSummary): 仪表盘汇总对象。
    返回:
        str: 多行字符串，包含窗口信息与 Top 商品列表。
    """
    totals = summary.totals
    lines: List[str] = []
    lines.append(
        f"Window: {summary.start.isoformat()} to {summary.end.isoformat()}"
    )
    lines.append(f"Source: {summary.source_name}")
    revenue = "$" + format(totals.total_revenue, ",.2f")
    lines.append(
        f"Totals: Revenue {revenue}, Units {totals.total_units}, "
        f"Sessions {totals.total_sessions}, CVR {totals.conversion_rate:.2%}, "
        f"Refund Rate {totals.refund_rate:.2%}"
    )
    if not summary.top_products:
        lines.append("No product records available.")
        return "\n".join(lines)

    lines.append("Top products (by revenue):")
    for idx, product in enumerate(summary.top_products, start=1):
        lines.append(_format_product_line(idx, product))

    return "\n".join(lines)
