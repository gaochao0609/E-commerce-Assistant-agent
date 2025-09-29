from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, List

from ..config import AppConfig
from .base import CredentialProvider, SalesDataSource, SalesRecord, TrafficRecord


@dataclass
class MockDataSourceSettings:
    """伪造数据源的控制参数。"""

    seed: int = 2024
    asin_list: List[str] | None = None


class MockAmazonBusinessReportSource(SalesDataSource):
    """使用确定性的随机数，模拟 Amazon Business Reports 输出。"""

    def __init__(self, credentials: CredentialProvider, settings: MockDataSourceSettings | None = None) -> None:
        """构造模拟数据源。

        参数:
            credentials: Amazon 凭证（占位使用，不参与生成）。
            settings: 可选的伪造参数设置。
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
        """生成指定时间区间的模拟销量数据。"""
        rng = _PseudoRandom(self._settings.seed + 1)
        timeline = list(_iter_days(start, end))
        records: List[SalesRecord] = []
        for asin in self._asin_list:
            base_units = max(10, rng.randint(20, 80))
            base_revenue = max(400, rng.randint(800, 2000))
            for day in timeline:
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
        """生成指定时间区间的模拟流量数据。"""
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
    """基于全局配置构建默认的模拟数据源。"""

    return MockAmazonBusinessReportSource(credentials=config.amazon)


def _iter_days(start: date, end: date) -> Iterable[date]:
    """生成包含起止日期的连续日期序列。"""

    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


class _PseudoRandom:
    """轻量随机数生成器，避免外部依赖。"""

    def __init__(self, seed: int) -> None:
        self._state = seed % 2147483647 or 42

    def _next(self) -> float:
        self._state = (self._state * 48271) % 2147483647
        return self._state / 2147483647

    def uniform(self, low: float, high: float) -> float:
        """返回 [low, high] 的均匀分布值。"""

        return low + (high - low) * self._next()

    def randint(self, low: int, high: int) -> int:
        """返回 [low, high) 的整数随机值。"""

        return int(low + (high - low) * self._next())
