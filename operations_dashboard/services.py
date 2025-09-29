from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from amazon_paapi import AmazonApi
from amazon_paapi.models import SortBy
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from .config import AppConfig
from .data_sources.amazon_business_reports import create_default_mock_source
from .data_sources.base import SalesDataSource, SalesRecord, TrafficRecord
from .metrics.calculations import build_dashboard_summary
from .reporting.formatter import summary_to_dict
from .storage.repository import SQLiteRepository, StoredSummary
from .utils.dates import recent_period

logger = logging.getLogger(__name__)

PAAPI_RESOURCES: List[str] = [
    "ItemInfo.Title",
    "BrowseNodeInfo.BrowseNodes",
    "BrowseNodeInfo.BrowseNodes.Ancestor",
    "BrowseNodeInfo.BrowseNodes.SalesRank",
]
MAX_ITEMS_PER_REQUEST = 10


@dataclass
class ServiceContext:
    config: AppConfig
    data_source: SalesDataSource
    repository: Optional[SQLiteRepository] = None
    llm: Optional[ChatOpenAI] = None


def create_service_context(
    config: AppConfig,
    *,
    data_source: Optional[SalesDataSource] = None,
    repository: Optional[SQLiteRepository] = None,
    llm: Optional[ChatOpenAI] = None,
) -> ServiceContext:
    data_source = data_source or create_default_mock_source(config)
    if repository is None and config.storage.enabled:
        repository = SQLiteRepository(config.storage.db_path)
    if llm is None and os.getenv("OPENAI_API_KEY"):
        llm = ChatOpenAI(api_key=os.environ.get("OPENAI_API_KEY"), model="gpt-3.5-turbo", temperature=0)
    return ServiceContext(config=config, data_source=data_source, repository=repository, llm=llm)


def _extract_items(search_result: object) -> Sequence:
    items_container = getattr(search_result, "items", None)
    if not items_container:
        return []
    if isinstance(items_container, (list, tuple)):
        return items_container
    for attr in ("items", "item"):
        extracted = getattr(items_container, attr, None)
        if extracted:
            return extracted
    return []


def _extract_primary_node(item: object) -> Tuple[Optional[str], Optional[int]]:
    browse_info = getattr(item, "browse_node_info", None)
    nodes = getattr(browse_info, "browse_nodes", None)
    if not nodes:
        nodes = getattr(browse_info, "browse_node", None)
    if isinstance(nodes, (list, tuple)):
        node = nodes[0] if nodes else None
    else:
        node = nodes
    if not node:
        return None, None
    display_name = getattr(node, "display_name", None)
    sales_rank = getattr(node, "sales_rank", None)
    return display_name, sales_rank


def _extract_title(item: object) -> str:
    item_info = getattr(item, "item_info", None)
    title_info = getattr(item_info, "title", None) if item_info else None
    title = getattr(title_info, "display_value", None) if title_info else None
    return title or getattr(item, "asin", None) or "未知商品"


def records_to_payload(records: List[SalesRecord]) -> List[Dict[str, Any]]:
    return [
        {
            "day": record.day.isoformat(),
            "asin": record.asin,
            "title": record.title,
            "units_ordered": record.units_ordered,
            "ordered_revenue": record.ordered_revenue,
            "sessions": record.sessions,
            "conversions": record.conversions,
            "refunds": record.refunds,
        }
        for record in records
    ]


def traffic_to_payload(records: List[TrafficRecord]) -> List[Dict[str, Any]]:
    return [
        {
            "day": record.day.isoformat(),
            "asin": record.asin,
            "sessions": record.sessions,
            "page_views": record.page_views,
            "buy_box_percentage": record.buy_box_percentage,
        }
        for record in records
    ]


def payload_to_sales(payload: List[Dict[str, Any]]) -> List[SalesRecord]:
    return [
        SalesRecord(
            day=date.fromisoformat(item["day"]),
            asin=str(item["asin"]),
            title=str(item.get("title", "")),
            units_ordered=int(item["units_ordered"]),
            ordered_revenue=float(item["ordered_revenue"]),
            sessions=int(item.get("sessions", 0)),
            conversions=float(item.get("conversions", 0.0)),
            refunds=int(item.get("refunds", 0)),
        )
        for item in payload
    ]


def payload_to_traffic(payload: List[Dict[str, Any]]) -> List[TrafficRecord]:
    return [
        TrafficRecord(
            day=date.fromisoformat(item["day"]),
            asin=str(item["asin"]),
            sessions=int(item["sessions"]),
            page_views=int(item["page_views"]),
            buy_box_percentage=float(item["buy_box_percentage"]),
        )
        for item in payload
    ]


def calc_growth(current: float, base: Optional[float]) -> Optional[float]:
    if base is None or base == 0:
        return None
    return (current - base) / base


def find_yoy(repository: SQLiteRepository, current_start: date) -> Optional[StoredSummary]:
    try:
        target = current_start.replace(year=current_start.year - 1)
    except ValueError:
        target = current_start - timedelta(days=365)
    return repository.fetch_by_start_date(target.isoformat())


def fetch_dashboard_data(
    context: ServiceContext,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    window_days: Optional[int] = None,
    top_n: Optional[int] = None,
) -> Dict[str, Any]:
    parsed_start = date.fromisoformat(start) if start else None
    parsed_end = date.fromisoformat(end) if end else None
    if parsed_start is None or parsed_end is None:
        window = window_days or context.config.dashboard.refresh_window_days
        parsed_start, parsed_end = recent_period(window)

    sales_records = context.data_source.fetch_sales(parsed_start, parsed_end)
    traffic_records = context.data_source.fetch_traffic(parsed_start, parsed_end)
    return {
        "start": parsed_start.isoformat(),
        "end": parsed_end.isoformat(),
        "source": context.data_source.name,
        "sales": records_to_payload(sales_records),
        "traffic": traffic_to_payload(traffic_records),
        "top_n": top_n,
    }


def compute_dashboard_metrics(
    context: ServiceContext,
    *,
    start: str,
    end: str,
    source: str,
    sales: List[Dict[str, Any]],
    traffic: List[Dict[str, Any]],
    top_n: Optional[int] = None,
) -> Dict[str, Any]:
    summary = build_dashboard_summary(
        source_name=source,
        start=date.fromisoformat(start),
        end=date.fromisoformat(end),
        sales_records=payload_to_sales(sales),
        traffic_records=payload_to_traffic(traffic),
        top_n=top_n or context.config.dashboard.top_n_products,
    )
    if context.repository and context.config.storage.enabled:
        context.repository.initialize()
        context.repository.save_summary(summary)
    return {"summary": summary_to_dict(summary)}


def generate_dashboard_insights(
    context: ServiceContext,
    *,
    summary: Dict[str, Any],
    focus: Optional[str] = None,
) -> Dict[str, Any]:
    if context.llm is None:
        raise RuntimeError("OPENAI_API_KEY 未配置，无法生成洞察。")
    instructions = (
        "你是一名亚马逊运营分析师，请基于给定的指标生成结构化洞察。"
        "按照“总体表现”“亮点商品”“风险/建议”三个部分输出。"
    )
    if focus:
        instructions += f" 优先关注：{focus}。"
    response = context.llm.invoke(
        [
            SystemMessage(content=instructions),
            HumanMessage(content=f"请分析以下 JSON 数据：{summary}"),
        ]
    )
    return {"report": {"summary": summary, "insights": response.content}}


def analyze_dashboard_history(
    context: ServiceContext,
    *,
    limit: int = 6,
    metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not context.repository:
        return {
            "analysis": {"error": "未启用数据库持久化，无法读取历史数据。"},
            "time_series": {},
        }
    context.repository.initialize()
    summaries = context.repository.fetch_recent_summaries(limit=limit)
    if not summaries:
        return {
            "analysis": {"error": "数据库暂无历史记录。"},
            "time_series": {},
        }
    current = summaries[0]
    previous = summaries[1] if len(summaries) > 1 else None
    yoy_summary = find_yoy(context.repository, date.fromisoformat(current.start))
    metrics = metrics or ["revenue", "units", "sessions"]
    analysis: Dict[str, Dict[str, Optional[float]]] = {}
    for metric in metrics:
        attr = f"total_{metric}"
        if not hasattr(current, attr):
            continue
        current_value = float(getattr(current, attr))
        prev_value = float(getattr(previous, attr)) if previous and hasattr(previous, attr) else None
        yoy_value = float(getattr(yoy_summary, attr)) if yoy_summary and hasattr(yoy_summary, attr) else None
        analysis[metric] = {
            "current": current_value,
            "mom": calc_growth(current_value, prev_value),
            "yoy": calc_growth(current_value, yoy_value),
        }
    series = {
        metric: [
            {
                "start": item.start,
                "value": float(getattr(item, f"total_{metric}")),
            }
            for item in reversed(summaries)
            if hasattr(item, f"total_{metric}")
        ]
        for metric in metrics
    }
    return {"analysis": analysis, "time_series": series}


def export_dashboard_history(
    context: ServiceContext,
    *,
    limit: int,
    path: str,
) -> Dict[str, Any]:
    if not context.repository:
        return {"message": "未启用数据库持久化，无法导出历史数据。"}
    context.repository.initialize()
    summaries = context.repository.fetch_recent_summaries(limit=limit)
    if not summaries:
        return {"message": "数据库暂无可导出的历史记录。"}
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                "id",
                "start",
                "end",
                "total_revenue",
                "total_units",
                "total_sessions",
                "conversion_rate",
                "refund_rate",
                "created_at",
            ]
        )
        for item in summaries:
            writer.writerow(
                [
                    item.id,
                    item.start,
                    item.end,
                    item.total_revenue,
                    item.total_units,
                    item.total_sessions,
                    item.conversion_rate,
                    item.refund_rate,
                    item.created_at,
                ]
            )
    return {"message": f"历史数据已导出到 {output_path}"}


def amazon_bestseller_search(
    context: ServiceContext,
    *,
    category: str,
    search_index: str,
    browse_node_id: Optional[str] = None,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    amazon_conf = context.config.amazon
    if amazon_conf.access_key in {"", "mock"} or amazon_conf.secret_key in {"", "mock"}:
        raise RuntimeError("Amazon PAAPI 凭证未配置，无法获取畅销榜数据。")
    client = AmazonApi(
        amazon_conf.access_key,
        amazon_conf.secret_key,
        amazon_conf.associate_tag or "",
        amazon_conf.marketplace,
    )
    request_count = min(max_items or MAX_ITEMS_PER_REQUEST, MAX_ITEMS_PER_REQUEST)
    search_kwargs = {
        "search_index": search_index,
        "sort_by": SortBy.AVGCUSTOMERREVIEWS,
        "item_count": request_count,
        "resources": PAAPI_RESOURCES,
    }
    if browse_node_id:
        search_kwargs["browse_node_id"] = browse_node_id
    else:
        search_kwargs["keywords"] = category
    result = client.search_items(**search_kwargs)
    items = _extract_items(result)
    payload: List[Dict[str, Any]] = []
    for item in items:
        node_name, sales_rank = _extract_primary_node(item)
        payload.append(
            {
                "asin": getattr(item, "asin", None),
                "title": _extract_title(item),
                "category": node_name,
                "sales_rank": sales_rank,
            }
        )
        if len(payload) >= request_count:
            break
    if not payload:
        errors = getattr(result, "errors", None)
        messages = [getattr(err, "message", str(err)) for err in errors or []]
        raise RuntimeError(
            "未能获取到畅销商品数据。" + (" 错误：" + "; ".join(messages) if messages else "")
        )
    return {"items": payload}
