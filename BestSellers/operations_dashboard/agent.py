"""基于 LangGraph 的运营日报工作流，集成畅销榜工具。"""

from __future__ import annotations

import csv
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from amazon_paapi import AmazonApi
from amazon_paapi.models import SortBy
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from .config import AppConfig
from .data_sources.amazon_business_reports import create_default_mock_source
from .data_sources.base import SalesRecord, TrafficRecord
from .metrics.calculations import DashboardSummary, build_dashboard_summary
from .pipeline.pipeline import DashboardPipeline
from .reporting.formatter import summary_to_dict
from .storage.repository import SQLiteRepository, StoredSummary
from .utils.dates import recent_period

# PAAPI 资源声明与默认配置
PAAPI_RESOURCES: List[str] = [
    "ItemInfo.Title",
    "BrowseNodeInfo.BrowseNodes",
    "BrowseNodeInfo.BrowseNodes.Ancestor",
    "BrowseNodeInfo.BrowseNodes.SalesRank",
]
MAX_ITEMS_PER_REQUEST = 10


def _parse_optional_date(value: Optional[str]) -> Optional[date]:
    """将 ISO 字符串解析为日期；若为空则返回 None。"""

    if not value:
        return None
    return date.fromisoformat(value)


def _extract_items(search_result: object) -> Sequence:
    """从 PAAPI SearchItems 返回值中读取商品集合。"""

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
    """提取首个浏览节点名称及销量排名。"""

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
    """获取商品标题，如缺失则回退到 ASIN。"""

    item_info = getattr(item, "item_info", None)
    title_info = getattr(item_info, "title", None) if item_info else None
    title = getattr(title_info, "display_value", None) if title_info else None
    if title:
        return title
    asin = getattr(item, "asin", None)
    return asin or "未知商品"


class FetchInput(BaseModel):
    """数据获取工具的入参。"""

    start: Optional[str] = Field(None, description="统计窗口起始日期，ISO 格式")
    end: Optional[str] = Field(None, description="统计窗口结束日期，ISO 格式")
    window_days: Optional[int] = Field(
        None,
        ge=1,
        le=90,
        description="若未指定起止日期，使用最近 N 天窗口",
    )
    top_n: Optional[int] = Field(None, ge=1, le=50, description="重点商品数量")


class FetchOutput(BaseModel):
    """数据获取工具的出参。"""

    start: str
    end: str
    source: str
    sales: List[Dict[str, object]]
    traffic: List[Dict[str, object]]
    top_n: Optional[int]


class MetricsInput(BaseModel):
    """指标计算工具的入参。"""

    start: str
    end: str
    source: str
    sales: List[Dict[str, object]]
    traffic: List[Dict[str, object]]
    top_n: Optional[int] = None


class MetricsOutput(BaseModel):
    """指标计算工具的出参。"""

    summary: Dict[str, object]


class InsightInput(BaseModel):
    """洞察总结工具入参。"""

    summary: Dict[str, object]
    focus: Optional[str] = Field(
        None,
        description="指定关注点，如“转化率”“退款率”",
    )


class InsightOutput(BaseModel):
    """洞察总结工具出参。"""

    report: Dict[str, object]


class HistoryInput(BaseModel):
    """历史分析工具的入参。"""

    limit: int = Field(6, ge=2, le=60, description="分析近 N 期记录")
    metrics: List[str] = Field(
        default_factory=lambda: ["revenue", "units", "sessions"],
        description="需要关注的指标列表",
    )


class HistoryOutput(BaseModel):
    """历史分析工具的出参。"""

    analysis: Dict[str, object]
    time_series: Dict[str, List[Dict[str, object]]]


class ExportHistoryInput(BaseModel):
    """历史导出工具的入参。"""

    limit: int = Field(30, ge=1, le=180, description="导出的历史条目数")
    path: str = Field(..., description="CSV 输出路径")


class ExportHistoryOutput(BaseModel):
    """历史导出工具的出参。"""

    message: str


class BestsellerInput(BaseModel):
    """畅销榜工具的入参。"""

    category: str = Field(..., description="商品关键词或类目描述")
    search_index: str = Field(..., description="PAAPI SearchIndex，如 'Shoes'、'Apparel'")
    browse_node_id: Optional[str] = Field(None, description="可选 BrowseNodeId")
    max_items: Optional[int] = Field(None, ge=1, le=MAX_ITEMS_PER_REQUEST, description="返回条数")


class BestsellerOutput(BaseModel):
    """畅销榜工具的出参。"""

    items: List[Dict[str, object]]


def _records_to_payload(records: List[SalesRecord]) -> List[Dict[str, object]]:
    """将 SalesRecord 列表转为可序列化的字典列表。"""

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


def _traffic_to_payload(records: List[TrafficRecord]) -> List[Dict[str, object]]:
    """将 TrafficRecord 列表转为可序列化的字典列表。"""

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


def _payload_to_sales(payload: List[Dict[str, object]]) -> List[SalesRecord]:
    """把字典列表恢复为 SalesRecord 对象。"""

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


def _payload_to_traffic(payload: List[Dict[str, object]]) -> List[TrafficRecord]:
    """把字典列表恢复为 TrafficRecord 对象。"""

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


def _stored_to_point(summary: StoredSummary) -> Dict[str, object]:
    """将数据库中的摘要转换为时间序列数据点。"""

    return {
        "start": summary.start,
        "end": summary.end,
        "revenue": summary.total_revenue,
        "units": summary.total_units,
        "sessions": summary.total_sessions,
        "conversion_rate": summary.conversion_rate,
        "refund_rate": summary.refund_rate,
    }


def _calc_growth(current: float, base: Optional[float]) -> Optional[float]:
    """计算相对增长率；若基数为 0 或缺失则返回 None。"""

    if base is None or base == 0:
        return None
    return (current - base) / base


def _find_yoy(repository: SQLiteRepository, current_start: date) -> Optional[StoredSummary]:
    """尝试在仓储中找到去年同期开端的摘要记录。"""

    try:
        target = current_start.replace(year=current_start.year - 1)
    except ValueError:
        target = current_start - timedelta(days=365)
    return repository.fetch_by_start_date(target.isoformat())


def _get_amazon_bestsellers(
    config: AppConfig,
    category: str,
    search_index: str,
    browse_node_id: Optional[str] = None,
    max_items: Optional[int] = None,
) -> List[Dict[str, object]]:
    """调用 PAAPI 获取畅销商品列表。"""

    amazon_conf = config.amazon
    if amazon_conf.access_key in {"", "mock"} or amazon_conf.secret_key in {"", "mock"}:
        raise RuntimeError("Amazon PAAPI 凭证未正确配置，无法获取真实畅销榜数据。")

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
    payload: List[Dict[str, object]] = []
    for item in items:
        title = _extract_title(item)
        node_name, sales_rank = _extract_primary_node(item)
        payload.append(
            {
                "asin": getattr(item, "asin", None),
                "title": title,
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
    return payload


def build_operations_agent(
    config: AppConfig,
    *,
    data_source=None,
    repository: Optional[SQLiteRepository] = None,
) -> tuple:
    """构建运营日报 LangGraph agent 及工具列表。"""

    data_source = data_source or create_default_mock_source(config)
    pipeline = DashboardPipeline(config=config, data_source=data_source)
    llm = ChatOpenAI(api_key=os.environ.get("OPENAI_API_KEY"), model="gpt-3.5-turbo", temperature=0)

    @tool("fetch_dashboard_data", args_schema=FetchInput)
    def fetch_dashboard_data_tool(
        start: Optional[str] = None,
        end: Optional[str] = None,
        window_days: Optional[int] = None,
        top_n: Optional[int] = None,
    ) -> Dict[str, object]:
        """从数据源拉取指定区间的销量与流量原始记录。"""

        parsed_start = _parse_optional_date(start)
        parsed_end = _parse_optional_date(end)
        if parsed_start is None or parsed_end is None:
            window = window_days or config.dashboard.refresh_window_days
            parsed_start, parsed_end = recent_period(window)

        sales_records = data_source.fetch_sales(parsed_start, parsed_end)
        traffic_records = data_source.fetch_traffic(parsed_start, parsed_end)
        return FetchOutput(
            start=parsed_start.isoformat(),
            end=parsed_end.isoformat(),
            source=data_source.name,
            sales=_records_to_payload(sales_records),
            traffic=_traffic_to_payload(traffic_records),
            top_n=top_n,
        ).dict()

    @tool("compute_dashboard_metrics", args_schema=MetricsInput)
    def compute_dashboard_metrics_tool(
        start: str,
        end: str,
        source: str,
        sales: List[Dict[str, object]],
        traffic: List[Dict[str, object]],
        top_n: Optional[int] = None,
    ) -> Dict[str, object]:
        """基于原始数据计算运营指标。"""

        sales_records = _payload_to_sales(sales)
        traffic_records = _payload_to_traffic(traffic)
        summary = build_dashboard_summary(
            source_name=source,
            start=date.fromisoformat(start),
            end=date.fromisoformat(end),
            sales_records=sales_records,
            traffic_records=traffic_records,
            top_n=top_n or config.dashboard.top_n_products,
        )

        if repository and config.storage.enabled:
            repository.initialize()
            repository.save_summary(summary)

        return MetricsOutput(summary=summary_to_dict(summary)).dict()

    @tool("generate_dashboard_insights", args_schema=InsightInput)
    def generate_dashboard_insights_tool(
        summary: Dict[str, object],
        focus: Optional[str] = None,
    ) -> Dict[str, object]:
        """调用 LLM 对指标进行洞察总结。"""

        instructions = (
            "你是一名亚马逊运营分析师，请基于给定的指标生成结构化洞察。"
            "按照“总体表现”“亮点商品”“风险/建议”三个部分输出。"
        )
        if focus:
            instructions += f" 优先关注：{focus}。"

        message = [
            SystemMessage(content=instructions),
            HumanMessage(content=f"请分析以下 JSON 数据：{summary}"),
        ]
        response = llm.invoke(message)
        return InsightOutput(
            report={
                "summary": summary,
                "insights": response.content,
            }
        ).dict()

    @tool("analyze_dashboard_history", args_schema=HistoryInput)
    def analyze_dashboard_history_tool(
        limit: int = 6,
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        """结合历史记录计算环比/同比及趋势数据。"""

        if not repository:
            return HistoryOutput(
                analysis={"error": "未启用数据库持久化，无法读取历史数据。"},
                time_series={},
            ).dict()

        repository.initialize()
        summaries = repository.fetch_recent_summaries(limit=limit)
        if not summaries:
            return HistoryOutput(
                analysis={"error": "数据库暂无历史记录。"},
                time_series={},
            ).dict()

        current = summaries[0]
        previous = summaries[1] if len(summaries) > 1 else None
        yoy_summary = _find_yoy(repository, date.fromisoformat(current.start))

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
                "mom": _calc_growth(current_value, prev_value),
                "yoy": _calc_growth(current_value, yoy_value),
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

        return HistoryOutput(
            analysis=analysis,
            time_series=series,
        ).dict()

    @tool("export_dashboard_history", args_schema=ExportHistoryInput)
    def export_dashboard_history_tool(
        limit: int,
        path: str,
    ) -> Dict[str, object]:
        """导出历史数据到 CSV，便于接入 BI 工具。"""

        if not repository:
            return ExportHistoryOutput(message="未启用数据库持久化，无法导出历史数据。").dict()

        repository.initialize()
        summaries = repository.fetch_recent_summaries(limit=limit)
        if not summaries:
            return ExportHistoryOutput(message="数据库暂无可导出的历史记录。").dict()

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "id",
                "start",
                "end",
                "total_revenue",
                "total_units",
                "total_sessions",
                "conversion_rate",
                "refund_rate",
                "created_at",
            ])
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
        return ExportHistoryOutput(message=f"历史数据已导出到 {output_path}").dict()

    @tool("amazon_bestseller_search", args_schema=BestsellerInput)
    def amazon_bestseller_search_tool(
        category: str,
        search_index: str,
        browse_node_id: Optional[str] = None,
        max_items: Optional[int] = None,
    ) -> Dict[str, object]:
        """使用 PAAPI 查询指定类目的畅销商品。"""

        items = _get_amazon_bestsellers(
            config,
            category=category,
            search_index=search_index,
            browse_node_id=browse_node_id,
            max_items=max_items,
        )
        return BestsellerOutput(items=items).dict()

    tools = [
        fetch_dashboard_data_tool,
        compute_dashboard_metrics_tool,
        generate_dashboard_insights_tool,
        analyze_dashboard_history_tool,
        export_dashboard_history_tool,
        amazon_bestseller_search_tool,
    ]

    graph = create_react_agent(
        llm,
        tools=tools,
    )
    return graph, tools


def run_agent_demo(config: AppConfig, query: str) -> Dict[str, object]:
    """运行完整的 LangGraph 工作流并返回最终输出。"""

    repository = None
    if config.storage.enabled:
        repository = SQLiteRepository(config.storage.db_path)
    graph, _ = build_operations_agent(config, repository=repository)
    result = graph.invoke(
        {
            "messages": [
                SystemMessage(
                    content=(
                        "你需要按照“数据获取→指标计算→洞察总结→历史分析（可选）→导出（可选）→畅销榜查询（可选）"  # noqa: E501
                        "的顺序调用工具，最终给出结构化运营日报。"
                    )
                ),
                HumanMessage(content=query),
            ]
        }
    )
    return result
