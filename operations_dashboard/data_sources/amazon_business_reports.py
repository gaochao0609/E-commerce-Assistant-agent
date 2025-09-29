"""提供基于 Amazon Business Report 的模拟数据源，方便本地开发与测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, List

from ..config import AppConfig
from .base import CredentialProvider, SalesDataSource, SalesRecord, TrafficRecord


@dataclass
class MockDataSourceSettings:
    """
    控制模拟数据源行为的配置项。

    属性:
        seed (int): 伪随机种子，确保数据可复现。
        asin_list (List[str] | None): 需要生成的 ASIN 列表，None 表示使用默认样例。
    """

    seed: int = 2024
    asin_list: List[str] | None = None


class MockAmazonBusinessReportSource(SalesDataSource):
    """
    基于线性同余发生器的可复现模拟数据源。

    通过伪随机算法模拟销量与流量走势，形似 Amazon Business Report 导出内容。
    """

    def __init__(self, credentials: CredentialProvider, settings: MockDataSourceSettings | None = None) -> None:
        """
        功能说明:
            创建模拟数据源实例。
        参数:
            credentials (CredentialProvider): Amazon 凭证，用于兼容真实实现接口。
            settings (Optional[MockDataSourceSettings]): 控制伪随机行为的配置。
        """
        self.name = "mock_amazon_business_report"
        self._credentials = credentials
        self._settings = settings or MockDataSourceSettings()
        self._asin_list = list(settings.asin_list) if settings and settings.asin_list else [
            "B0TESTSKU01",
            "B0TESTSKU02",
            "B0TESTSKU03",
        ]

    def fetch_sales(self, start: date, end: date) -> List[SalesRecord]:
        """
        功能说明:
            生成指定时间范围内的伪随机销售数据。
        参数:
            start (date): 起始日期。
            end (date): 结束日期。
        返回:
            List[SalesRecord]: 销售记录列表。
        """
        rng = _PseudoRandom(self._settings.seed + 1)
        timeline = list(_iter_days(start, end))
        records: List[SalesRecord] = []
        for asin in self._asin_list:
            base_units = max(10, rng.randint(20, 80))
            base_revenue = max(400, rng.randint(800, 2000))
            for day in timeline:
                # 使用基础值叠加随机波动来模拟真实销量。
                units = max(0, int(base_units * rng.uniform(0.6, 1.3)))
                revenue = round(base_revenue * rng.uniform(0.6, 1.2), 2)
                sessions = max(units * rng.randint(4, 9), 1)
                conversion = round(units / sessions if sessions else 0, 4)
                refunds = rng.randint(0, 2)
                records.append(
                    SalesRecord(
                        day=day,
                        asin=asin,
                        title=f"Mock Product {asin[-2:]}",
                        units_ordered=units,
                        ordered_revenue=revenue,
                        sessions=sessions,
                        conversions=conversion,
                        refunds=refunds,
                    )
                )
        return records

    def fetch_traffic(self, start: date, end: date) -> List[TrafficRecord]:
        """
        功能说明:
            生成指定时间范围内的伪随机流量数据。
        参数:
            start (date): 起始日期。
            end (date): 结束日期。
        返回:
            List[TrafficRecord]: 流量记录列表。
        """
        rng = _PseudoRandom(self._settings.seed + 2)
        timeline = list(_iter_days(start, end))
        records: List[TrafficRecord] = []
        for asin in self._asin_list:
            base_sessions = max(50, rng.randint(150, 400))
            for day in timeline:
                sessions = max(1, int(base_sessions * rng.uniform(0.5, 1.3)))
                page_views = sessions + rng.randint(20, 200)
                buy_box = round(rng.uniform(75, 98), 2)
                records.append(
                    TrafficRecord(
                        day=day,
                        asin=asin,
                        sessions=sessions,
                        page_views=page_views,
                        buy_box_percentage=buy_box,
                    )
                )
        return records


def create_default_mock_source(config: AppConfig) -> MockAmazonBusinessReportSource:
    """
    功能说明:
        使用应用配置中的凭证构建默认的模拟数据源。
    参数:
        config (AppConfig): 应用配置，提供 Amazon 凭证。
    返回:
        MockAmazonBusinessReportSource: 预配置的模拟数据源实例。
    """
    return MockAmazonBusinessReportSource(credentials=config.amazon)


def _iter_days(start: date, end: date) -> Iterable[date]:
    """
    功能说明:
        生成起止日期（闭区间）内的所有日期。
    参数:
        start (date): 开始日期。
        end (date): 结束日期。
    返回:
        Iterable[date]: 逐日迭代器。
    """
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


class _PseudoRandom:
    """简单的线性同余伪随机数发生器，用于生成可复现的数据。"""

    def __init__(self, seed: int) -> None:
        self._state = seed % 2147483647 or 42

    def _next(self) -> float:
        # 使用 MINSTD 参数生成均匀分布的随机数。
        self._state = (self._state * 48271) % 2147483647
        return self._state / 2147483647

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self._next()

    def randint(self, low: int, high: int) -> int:
        return int(low + (high - low) * self._next())
