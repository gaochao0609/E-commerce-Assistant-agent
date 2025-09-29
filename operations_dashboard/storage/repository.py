from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from ..metrics.calculations import DashboardSummary, ProductPerformance


@dataclass
class StoredProduct:
    """数据库中记录的重点商品信息。"""

    asin: str
    title: str
    revenue: float
    units: int
    sessions: int
    conversion_rate: float
    refunds: int
    buy_box_percentage: Optional[float]


@dataclass
class StoredSummary:
    """数据库中保存的汇总摘要。"""

    id: int
    start: str
    end: str
    source: str
    total_revenue: float
    total_units: int
    total_sessions: int
    conversion_rate: float
    refund_rate: float
    created_at: str
    products: List[StoredProduct]


class SQLiteRepository:
    """基于 SQLite 的持久化仓储。"""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    def initialize(self) -> None:
        """初始化数据库文件及表结构。"""

        if not self._db_path.parent.exists():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    source TEXT NOT NULL,
                    total_revenue REAL NOT NULL,
                    total_units INTEGER NOT NULL,
                    total_sessions INTEGER NOT NULL,
                    conversion_rate REAL NOT NULL,
                    refund_rate REAL NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary_id INTEGER NOT NULL,
                    asin TEXT NOT NULL,
                    title TEXT NOT NULL,
                    revenue REAL NOT NULL,
                    units INTEGER NOT NULL,
                    sessions INTEGER NOT NULL,
                    conversion_rate REAL NOT NULL,
                    refunds INTEGER NOT NULL,
                    buy_box_percentage REAL,
                    UNIQUE(summary_id, asin),
                    FOREIGN KEY(summary_id) REFERENCES summaries(id) ON DELETE CASCADE
                );
                """
            )

    def save_summary(self, summary: DashboardSummary) -> int:
        """将 DashboardSummary 写入数据库并返回生成的主键。"""

        created_at = datetime.utcnow().isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.execute(
                """
                INSERT INTO summaries (
                    start_date, end_date, source,
                    total_revenue, total_units, total_sessions,
                    conversion_rate, refund_rate, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.start.isoformat(),
                    summary.end.isoformat(),
                    summary.source_name,
                    summary.totals.total_revenue,
                    summary.totals.total_units,
                    summary.totals.total_sessions,
                    summary.totals.conversion_rate,
                    summary.totals.refund_rate,
                    created_at,
                ),
            )
            summary_id = cursor.lastrowid

            product_rows = [
                (
                    summary_id,
                    product.asin,
                    product.title,
                    product.revenue,
                    product.units,
                    product.sessions,
                    product.conversion_rate,
                    product.refunds,
                    product.buy_box_percentage,
                )
                for product in summary.top_products
            ]
            conn.executemany(
                """
                INSERT OR REPLACE INTO products (
                    summary_id, asin, title, revenue, units, sessions,
                    conversion_rate, refunds, buy_box_percentage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product_rows,
            )
        return summary_id

    def fetch_recent_summaries(self, limit: int = 10) -> List[StoredSummary]:
        """按时间逆序返回最近的汇总记录。"""

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = list(
                conn.execute(
                    """
                    SELECT * FROM summaries
                    ORDER BY start_date DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            )
            summaries: List[StoredSummary] = []
            for row in rows:
                products = self._fetch_products(conn, row["id"])
                summaries.append(
                    StoredSummary(
                        id=row["id"],
                        start=row["start_date"],
                        end=row["end_date"],
                        source=row["source"],
                        total_revenue=row["total_revenue"],
                        total_units=row["total_units"],
                        total_sessions=row["total_sessions"],
                        conversion_rate=row["conversion_rate"],
                        refund_rate=row["refund_rate"],
                        created_at=row["created_at"],
                        products=products,
                    )
                )
            return summaries

    def fetch_by_start_date(self, start: str) -> Optional[StoredSummary]:
        """根据起始日期查找单条摘要，用于同比等场景。"""

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM summaries
                WHERE start_date = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (start,),
            ).fetchone()
            if not row:
                return None
            products = self._fetch_products(conn, row["id"])
            return StoredSummary(
                id=row["id"],
                start=row["start_date"],
                end=row["end_date"],
                source=row["source"],
                total_revenue=row["total_revenue"],
                total_units=row["total_units"],
                total_sessions=row["total_sessions"],
                conversion_rate=row["conversion_rate"],
                refund_rate=row["refund_rate"],
                created_at=row["created_at"],
                products=products,
            )

    def _fetch_products(self, conn: sqlite3.Connection, summary_id: int) -> List[StoredProduct]:
        """获取指定汇总的重点商品列表。"""

        product_rows = conn.execute(
            """
            SELECT asin, title, revenue, units, sessions,
                   conversion_rate, refunds, buy_box_percentage
            FROM products
            WHERE summary_id = ?
            ORDER BY revenue DESC
            """,
            (summary_id,),
        )
        return [
            StoredProduct(*row)
            for row in product_rows
        ]
