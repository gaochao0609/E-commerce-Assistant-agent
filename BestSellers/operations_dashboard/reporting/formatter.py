from __future__ import annotations

from typing import Dict, List

from ..metrics.calculations import DashboardSummary, ProductPerformance


def summary_to_dict(summary: DashboardSummary) -> Dict[str, object]:
    """将仪表盘摘要结构化为 JSON 友好的字典。"""

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


def _format_currency(value: float) -> str:
    """把数值格式化为带千分位的美元字符串。"""

    return "$" + format(value, ",.2f")


def _format_product_line(idx: int, product: ProductPerformance) -> str:
    """渲染单个商品的文本行。"""

    buy_box = (
        f"Buy Box {product.buy_box_percentage:.2f}%"
        if product.buy_box_percentage is not None
        else "Buy Box n/a"
    )
    return (
        f"{idx}. {product.title} ({product.asin}) - Revenue {_format_currency(product.revenue)}, "
        f"Units {product.units}, Sessions {product.sessions}, "
        f"CVR {product.conversion_rate:.2%}, Refunds {product.refunds}, {buy_box}"
    )


def format_text_report(summary: DashboardSummary) -> str:
    """生成可读性良好的文本报告。"""

    totals = summary.totals
    lines: List[str] = []
    lines.append(
        f"Window: {summary.start.isoformat()} to {summary.end.isoformat()}"
    )
    lines.append(f"Source: {summary.source_name}")
    revenue = _format_currency(totals.total_revenue)
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
