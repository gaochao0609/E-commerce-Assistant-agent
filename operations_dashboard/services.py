"""运营仪表盘服务层，封装数据读取、指标计算以及 MCP 集成的业务逻辑。"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
TRUSTED_DIRECTORIES_ROOT = (PROJECT_ROOT / "trusted_directories").resolve()
TRUSTED_EXPORT_ROOT = (TRUSTED_DIRECTORIES_ROOT / "exports").resolve()

PAAPI_RESOURCES: List[str] = [
    "ItemInfo.Title",
    "BrowseNodeInfo.BrowseNodes",
    "BrowseNodeInfo.BrowseNodes.Ancestor",
    "BrowseNodeInfo.BrowseNodes.SalesRank",
]
# Amazon PAAPI 搜索请求所需的资源字段，确保返回标题、节点链路与销量排名。
MAX_ITEMS_PER_REQUEST = 10
# 控制单次畅销榜请求的最大商品数量，避免违反 PAAPI 速率限制。


def _is_within(path: Path, root: Path) -> bool:
    """Return True if path is within the given root (inclusive)."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sanitize_export_subpath(raw_path: Path) -> Path:
    """Convert a user supplied export path into a safe relative path."""
    if raw_path.is_absolute():
        try:
            relative = raw_path.relative_to(raw_path.anchor)
        except ValueError:
            relative = Path(raw_path.name)
    else:
        relative = raw_path
    safe_parts = [
        part for part in relative.parts if part not in {"", ".", ".."}
    ]
    if not safe_parts:
        return Path("history.csv")
    return Path(*safe_parts)


@dataclass
class ServiceContext:
    """
    汇总运营仪表盘服务所需的共享依赖。

    属性:
        config (AppConfig): 全局配置，包含市场、存储等信息。
        data_source (SalesDataSource): 用于拉取销量与流量的具体实现。
        repository (Optional[SQLiteRepository]): 可选的 SQLite 仓库，用于持久化。
        llm (Optional[ChatOpenAI]): 可选的语言模型实例，用于生成洞察。
    """

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
    """构建 MCP 工具与 LangGraph Agent 所共享的业务上下文。

    参数:
        config: 应用配置，包含市场、存储及凭证信息。
        data_source: 可选的销量数据提供方，未传入时使用内置的 Mock 数据源。
        repository: 可选的 SQLite 仓储实例；当开启持久化且未传入时会自动创建。
        llm: 可选的 ChatOpenAI 实例，用于生成自然语言洞察。

    返回:
        ServiceContext: 汇聚配置、数据源、仓储与 LLM 的上下文对象。
    """
    data_source = data_source or create_default_mock_source(config)
    if repository is None and config.storage.enabled:
        repository = SQLiteRepository(config.storage.db_path)
    api_key = config.openai_api_key
    logger.debug(
        "create_service_context key_present=%s ChatOpenAI=%s initial_llm=%s",
        bool(api_key),
        ChatOpenAI,
        llm,
    )
    if ChatOpenAI is None:
        raise RuntimeError("ChatOpenAI import returned None. Check langchain-openai installation.")
    if llm is None and api_key:
        llm = ChatOpenAI(
            api_key=api_key,
            model=config.openai_model,
            temperature=config.openai_temperature,
        )
    context = ServiceContext(config=config, data_source=data_source, repository=repository, llm=llm)
    logger.debug("create_service_context returning llm=%s", context.llm)
    return context


def _extract_items(search_result: object) -> Sequence:
    """
    功能说明:
        从 PAAPI 返回结果中提取 items 列表，兼容不同版本的字段命名。
    参数:
        search_result (object): Amazon PAAPI 的原始响应对象。
    返回:
        Sequence: 抽取出的商品对象序列，若无数据则返回空列表。
    """
    # 1. 直接尝试访问 items 属性，不存在时提前返回空列表。
    items_container = getattr(search_result, "items", None)
    if not items_container:
        return []
    # 2. 若已经是序列类型则直接返回，保持原有顺序。
    if isinstance(items_container, (list, tuple)):
        return items_container
    # 3. 兼容部分 SDK 使用的 items/item 嵌套字段。
    for attr in ("items", "item"):
        extracted = getattr(items_container, attr, None)
        if extracted:
            return extracted
    return []


def _extract_primary_node(item: object) -> Tuple[Optional[str], Optional[int]]:
    """
    功能说明:
        从商品对象中提取首个浏览节点名称及对应的销售排名。
    参数:
        item (object): Amazon PAAPI 商品对象。
    返回:
        Tuple[Optional[str], Optional[int]]: 节点显示名与 sales rank，若缺失则返回 None。
    """
    # 1. 获取浏览节点列表，兼容不同字段命名。
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
    """
    功能说明:
        获取商品的展示标题，若缺失则回退到 ASIN 或占位文本。
    参数:
        item (object): Amazon PAAPI 商品对象。
    返回:
        str: 商品标题或退化后的 ASIN/占位名称。
    """
    item_info = getattr(item, "item_info", None)
    title_info = getattr(item_info, "title", None) if item_info else None
    title = getattr(title_info, "display_value", None) if title_info else None
    return title or getattr(item, "asin", None) or "未知商品"


def records_to_payload(records: List[SalesRecord]) -> List[Dict[str, Any]]:
    """
    功能说明:
        将 SalesRecord 列表转换为 JSON 友好的字典结构。
    参数:
        records (List[SalesRecord]): 销售记录列表。
    返回:
        List[Dict[str, Any]]: 适合跨进程传输或序列化的字典数组。
    """
    # 将数据逐条展开为基础类型字段，避免 datetime 等复杂对象。
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
    """
    功能说明:
        将 TrafficRecord 列表转换为便于下游消费的字典结构。
    参数:
        records (List[TrafficRecord]): 流量记录列表。
    返回:
        List[Dict[str, Any]]: 包含流量指标的字典数组。
    """
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
    """
    功能说明:
        将字典形式的销售数据还原为 SalesRecord 对象，便于内部计算。
    参数:
        payload (List[Dict[str, Any]]): 序列化后的销售数据集合。
    返回:
        List[SalesRecord]: 结构化的销售记录列表。
    """
    return [
        SalesRecord(
            day=date.fromisoformat(item["day"]),
            asin=str(item["asin"]),
            title=str(item.get("title", "")),
            units_ordered=int(item["units_ordered"]),
            ordered_revenue=float(item["ordered_revenue"]),
            sessions=int(item["sessions"]),
            conversions=float(item["conversions"]),
            refunds=int(item["refunds"]),
        )
        for item in payload
    ]


def payload_to_traffic(payload: List[Dict[str, Any]]) -> List[TrafficRecord]:
    """
    功能说明:
        将字典形式的流量数据还原为 TrafficRecord 对象。
    参数:
        payload (List[Dict[str, Any]]): 序列化后的流量数据集合。
    返回:
        List[TrafficRecord]: 结构化的流量记录列表。
    """
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
    """
    功能说明:
        计算同比或环比的增长率，基准为 0 或缺失时返回 None。
    参数:
        current (float): 当前值。
        base (Optional[float]): 对比基准值，可为空。
    返回:
        Optional[float]: 增长率，使用小数表示。
    """
    if base is None or base == 0:
        return None
    return (current - base) / base


def find_yoy(repository: SQLiteRepository, current_start: date) -> Optional[StoredSummary]:
    """
    功能说明:
        查找与当前窗口开始日期对应的去年同期汇总数据。
    参数:
        repository (SQLiteRepository): 数据仓库实例。
        current_start (date): 当前窗口的起始日期。
    返回:
        Optional[StoredSummary]: 匹配到的历史汇总，否则为 None。
    """
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
    """
    功能说明:
        在指定时间窗口内拉取原始销量与流量数据。
    参数:
        context (ServiceContext): 包含数据源与配置的上下文。
        start (Optional[str]): 起始日期，ISO 格式。
        end (Optional[str]): 结束日期，ISO 格式。
        window_days (Optional[int]): 未指定时间范围时的滚动窗口天数。
        top_n (Optional[int]): 需要关注的 Top N 商品数量。
    返回:
        Dict[str, Any]: 包含窗口信息、数据源名称以及原始数据的字典。
    """
    # 1. 解析用户输入的日期字符串；若缺失则稍后根据配置计算窗口。
    parsed_start = date.fromisoformat(start) if start else None
    parsed_end = date.fromisoformat(end) if end else None
    window = window_days or context.config.dashboard.refresh_window_days
    if parsed_start and not parsed_end:
        # 2. 仅提供起始日期时，根据窗口长度推算结束日期。
        parsed_end = parsed_start + timedelta(days=max(window, 1) - 1)
    elif parsed_end and not parsed_start:
        # 3. 仅提供结束日期时，根据窗口长度回推起始日期。
        parsed_start = parsed_end - timedelta(days=max(window, 1) - 1)
    elif parsed_start is None and parsed_end is None:
        # 4. 两端均缺失时，使用默认窗口。
        parsed_start, parsed_end = recent_period(window)

    # 3. 调用数据源获取销量与流量原始记录。
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
    """
    功能说明:
        汇总销量与流量数据，生成 KPI 摘要并按需持久化。
    参数:
        context (ServiceContext): 服务上下文，提供配置与仓库。
        start (str): 窗口开始日期。
        end (str): 窗口结束日期。
        source (str): 数据来源标识。
        sales (List[Dict[str, Any]]): 序列化的销售记录。
        traffic (List[Dict[str, Any]]): 序列化的流量记录。
        top_n (Optional[int]): 覆盖默认配置的 Top N 数量。
    返回:
        Dict[str, Any]: 包含结构化摘要的字典。
    """
    # 1. 将序列化数据还原为记录对象并构建汇总摘要。
    summary = build_dashboard_summary(
        source_name=source,
        start=date.fromisoformat(start),
        end=date.fromisoformat(end),
        sales_records=payload_to_sales(sales),
        traffic_records=payload_to_traffic(traffic),
        top_n=top_n or context.config.dashboard.top_n_products,
    )
    # 2. 若仓库可用则落盘保存，便于后续历史分析。
    if context.repository and context.config.storage.enabled:
        context.repository.initialize()
        context.repository.save_summary(summary)
    return {"summary": summary_to_dict(summary)}




def generate_dashboard_insights(
    context: ServiceContext,
    *,
    summary: Optional[Dict[str, Any]] = None,
    focus: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    window_days: Optional[int] = None,
    top_n: Optional[int] = None,
) -> Dict[str, Any]:
    logger.debug("generate_dashboard_insights context.llm=%s", context.llm)
    """
    功能说明:
        调用配置好的 LLM 依据 KPI 摘要生成结构化洞察。
        当未提供摘要时，会根据指定的时间窗口自动计算。
    参数:
        context (ServiceContext): 服务上下文，需包含 LLM。
        summary (Optional[Dict[str, Any]]): 聚合后的 KPI 摘要，缺失时会触发自动计算。
        focus (Optional[str]): 需要额外关注的主题维度。
        start (Optional[str]): 自动计算时使用的开始日期（ISO 字符串）。
        end (Optional[str]): 自动计算时使用的结束日期（ISO 字符串）。
        window_days (Optional[int]): 未指定日期时的回溯天数。
        top_n (Optional[int]): 自动计算摘要时需要返回的重点商品数量。
    返回:
        Dict[str, Any]: 包含原始摘要与洞察文本的字典。
    """
    working_summary = summary
    if working_summary is None:
        data = fetch_dashboard_data(
            context,
            start=start,
            end=end,
            window_days=window_days,
            top_n=top_n,
        )
        metrics = compute_dashboard_metrics(
            context,
            start=data.get("start", start or ""),
            end=data.get("end", end or ""),
            source=data.get("source", context.config.dashboard.marketplace),
            sales=data.get("sales", []),
            traffic=data.get("traffic", []),
            top_n=top_n,
        )
        working_summary = metrics.get("summary")

    if working_summary is None:
        return {
            "report": {
                "summary": {},
                "insights": "暂时无法计算摘要，请检查输入数据。",
                "placeholder": True,
            }
        }

    if context.llm is None:
        raise RuntimeError("LLM missing from service context")
    instructions = (
        "请以资深运营顾问身份，依据提供的数据生成结构化洞察。"
        "优先关注“销量趋势、流量变化、转化率、退款”这些主题。"
    )
    if focus:
        instructions += f" 特别关注 {focus}。"
    response = context.llm.invoke(
        [
            SystemMessage(content=instructions),
            HumanMessage(content=f"请分析下面的 JSON 数据：{working_summary}"),
        ]
    )
    return {"report": {"summary": working_summary, "insights": response.content}}

def analyze_dashboard_history(
    context: ServiceContext,
    *,
    limit: int = 6,
    metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    功能说明:
        计算指定指标的环比、同比增长率，并生成时间序列数据。
    参数:
        context (ServiceContext): 服务上下文，需提供仓库访问能力。
        limit (int): 需要纳入分析的历史期数，默认最近 6 期。
        metrics (Optional[List[str]]): 需要分析的指标列表，None 表示默认指标。
    返回:
        Dict[str, Any]: 包含增长分析与时间序列的结构化结果。
    """
    if not context.repository:
        return {
            "analysis": {"error": "未启用数据库持久化，无法获取历史数据。"},
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
    # 1. 针对每个指标计算当前值、环比与同比增长。
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
    # 2. 构建时间序列，便于在前端绘制趋势曲线。
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
    """
    功能说明:
        导出指定数量的历史汇总记录到 CSV 文件。
    参数:
        context (ServiceContext): 服务上下文，需包含仓库实例。
        limit (int): 导出的记录数量。
        path (str): CSV 输出路径，可为相对路径。
    返回:
        Dict[str, Any]: 包含导出结果描述的字典。
    """

    if not context.repository:
        return {"message": "未启用数据库持久化，无法导出历史数据。"}

    context.repository.initialize()
    summaries = context.repository.fetch_recent_summaries(limit=limit)
    if not summaries:
        return {"message": "数据库中暂无可导出的历史记录。"}

    TRUSTED_EXPORT_ROOT.mkdir(parents=True, exist_ok=True)

    sanitized_subpath = _sanitize_export_subpath(Path(path))
    candidate_path = (TRUSTED_EXPORT_ROOT / sanitized_subpath).resolve()

    if not _is_within(candidate_path, TRUSTED_EXPORT_ROOT):
        return {
            "message": (
                f"Export path {candidate_path} must stay within trusted directories: "
                f"{TRUSTED_EXPORT_ROOT}"
            )
        }

    candidate_path.parent.mkdir(parents=True, exist_ok=True)

    with candidate_path.open("w", newline="", encoding="utf-8") as csvfile:
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

    relative_display = candidate_path.relative_to(TRUSTED_DIRECTORIES_ROOT)
    return {
        "message": (
            f"Exported history CSV to {candidate_path} "
            f"(trusted location: {relative_display})"
        )
    }


def amazon_bestseller_search(
    context: ServiceContext,
    *,
    category: str,
    search_index: str,
    browse_node_id: Optional[str] = None,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    """
    功能说明:
        调用 Amazon PAAPI 获取指定类目的畅销商品列表。
    参数:
        context (ServiceContext): 服务上下文，需提供 Amazon 凭证。
        category (str): 业务侧的类目描述。
        search_index (str): PAAPI 搜索索引，例如 "Books"。
        browse_node_id (Optional[str]): 指定的浏览节点 ID。
        max_items (Optional[int]): 返回的最大商品数量。
    返回:
        Dict[str, Any]: 包含畅销商品列表的字典。
    """
    try:
        from amazon_paapi import AmazonApi
        from amazon_paapi.models import SortBy
    except ImportError as exc:
        raise RuntimeError("python-amazon-paapi 未安装，无法调用 amazon_bestseller_search。") from exc

    amazon_conf = context.config.amazon
    # 1. 基础凭证缺失时拒绝请求，避免调用失败消耗额度。
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
    # 2. 有明确节点时使用 browse_node_id，否则退回到关键字搜索。
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
