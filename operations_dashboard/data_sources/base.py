"""定义运营仪表盘所需的销量与流量数据抽象模型。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List, Protocol


@dataclass
class SalesRecord:
    """
    表示某个 ASIN 在单日的销售表现。

    属性:
        day (date): 数据所属的自然日。
        asin (str): Amazon 标准识别号。
        title (str): 商品标题或识别名称。
        units_ordered (int): 当日订单量。
        ordered_revenue (float): 当日销售额。
        sessions (int): 当日访问会话数。
        conversions (float): 转化率（下单数/会话数）。
        refunds (int): 退款单数。
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
    """
    表示某个 ASIN 在单日的流量指标。

    属性:
        day (date): 数据所属的自然日。
        asin (str): Amazon 标准识别号。
        sessions (int): 会话数。
        page_views (int): 页面浏览量。
        buy_box_percentage (float): 购物车占有率。
    """

    day: date
    asin: str
    sessions: int
    page_views: int
    buy_box_percentage: float


class SalesDataSource(ABC):
    """
    抽象基类，描述如何获取销量与流量数据。

    子类需实现销售和流量的抓取逻辑，以便管道统一调用。
    """

    name: str

    @abstractmethod
    def fetch_sales(self, start: date, end: date) -> List[SalesRecord]:
        """
        功能说明:
            获取指定时间范围内（闭区间）的销售记录。
        参数:
            start (date): 起始日期。
            end (date): 结束日期。
        返回:
            List[SalesRecord]: 按日期展开的销售记录列表。
        """

    @abstractmethod
    def fetch_traffic(self, start: date, end: date) -> List[TrafficRecord]:
        """
        功能说明:
            获取指定时间范围内（闭区间）的流量记录。
        参数:
            start (date): 起始日期。
            end (date): 结束日期。
        返回:
            List[TrafficRecord]: 按日期展开的流量记录列表。
        """


class CredentialProvider(Protocol):
    """
    定义数据源期望的凭证字段集合。

    属性:
        access_key (str): 访问密钥。
        secret_key (str): 密钥，用于签名。
        associate_tag (Optional[str]): 关联标签，可为空。
        marketplace (str): 市场代码，如 US/JP。
    """

    access_key: str
    secret_key: str
    associate_tag: str | None
    marketplace: str
