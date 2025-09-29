from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List, Protocol


@dataclass
class SalesRecord:
    """订单层面的销量记录。

    属性:
        day: 数据对应的日期。
        asin: 商品的 ASIN 标识。
        title: 商品标题。
        units_ordered: 当天下单件数。
        ordered_revenue: 当天下单金额（货币单位取决于市场）。
        sessions: 会话数量或从销售数据估算的流量。
        conversions: 转化率 (0-1)。
        refunds: 退款件数。
    """

    day: date
    asin: str
    title: str
    units_ordered: int
    ordered_revenue: float
    sessions: int
    conversions: float
    refunds: int = 0


@dataclass
class TrafficRecord:
    """站内流量/会话相关记录。"""

    day: date
    asin: str
    sessions: int
    page_views: int
    buy_box_percentage: float


class SalesDataSource(ABC):
    """Amazon 销售与流量数据源抽象基类。"""

    name: str

    @abstractmethod
    def fetch_sales(self, start: date, end: date) -> List[SalesRecord]:
        """拉取指定时间段的销量记录列表。"""

    @abstractmethod
    def fetch_traffic(self, start: date, end: date) -> List[TrafficRecord]:
        """拉取指定时间段的流量/会话记录列表。"""


class CredentialProvider(Protocol):
    """凭证提供协议，用于给真实 Amazon 客户端注入认证信息。"""

    access_key: str
    secret_key: str
    associate_tag: str | None
    marketplace: str
