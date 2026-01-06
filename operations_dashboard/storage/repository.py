"""使用 SQLite 持久化仪表盘摘要及商品表现数据。"""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..metrics.calculations import DashboardSummary, ProductPerformance


@dataclass
class StoredProduct:
    """
    表示存储在 products 表中的一行数据。

    属性:
        asin (str): 商品 ASIN。
        title (str): 商品标题。
        revenue (float): 销售额。
        units (int): 销量。
        sessions (int): 会话数。
        conversion_rate (float): 转化率。
        refunds (int): 退款数量。
        buy_box_percentage (Optional[float]): 购物车占有率。
    """

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
    """
    表示存储在 summaries 表中的聚合摘要。

    属性:
        id (int): 主键 ID。
        start (str): 窗口开始日期（ISO 字符串）。
        end (str): 窗口结束日期。
        source (str): 数据来源名称。
        total_revenue (float): 总销售额。
        total_units (int): 总销量。
        total_sessions (int): 总会话数。
        conversion_rate (float): 综合转化率。
        refund_rate (float): 退款率。
        created_at (str): 创建时间。
        products (List[StoredProduct]): 关联的 Top 商品列表。
    """

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


@dataclass
class StoredUpload:
    """
    表示持久化保存的上传表格数据。

    属性:
        id (str): 上传记录 ID。
        filename (str): 原始文件名。
        headers (List[str]): 表头字段列表。
        rows (List[List[str]]): 表格数据行。
        row_count (int): 行数统计。
        column_count (int): 列数统计。
        created_at (str): 创建时间。
    """

    id: str
    filename: str
    headers: List[str]
    rows: List[List[str]]
    row_count: int
    column_count: int
    created_at: str


class SQLiteRepository:
    """
    为仪表盘摘要提供基于 SQLite 的持久化能力。

    负责初始化表结构、写入摘要与商品记录，以及读取历史数据。
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    def initialize(self) -> None:
        """
        功能说明:
            确保数据库文件及表结构存在。
        """
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

                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    headers_json TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    column_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_summary(self, summary: DashboardSummary) -> int:
        """
        功能说明:
            将 DashboardSummary 持久化至数据库。
        参数:
            summary (DashboardSummary): 仪表盘摘要。
        返回:
            int: 新插入摘要的主键 ID。
        """
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
        """
        功能说明:
            按时间倒序获取最近的摘要记录。
        参数:
            limit (int): 需要返回的记录数量。
        返回:
            List[StoredSummary]: 最近的摘要列表。
        """
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
        """
        功能说明:
            按窗口开始日期查询对应的摘要，常用于同比对比。
        参数:
            start (str): 起始日期，ISO 字符串。
        返回:
            Optional[StoredSummary]: 匹配到的摘要或 None。
        """
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
        """
        功能说明:
            查询某摘要 ID 对应的商品行。
        参数:
            conn (sqlite3.Connection): 已开启的数据库连接。
            summary_id (int): 摘要主键 ID。
        返回:
            List[StoredProduct]: 商品记录列表。
        """
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
        return [StoredProduct(*row) for row in product_rows]

    def save_upload(
        self,
        *,
        filename: str,
        headers: List[str],
        rows: List[List[str]],
        row_count: int,
        column_count: int,
    ) -> StoredUpload:
        """
        功能说明:
            持久化保存上传表格数据。
        参数:
            filename (str): 原始文件名。
            headers (List[str]): 表头字段列表。
            rows (List[List[str]]): 表格数据行。
            row_count (int): 行数统计。
            column_count (int): 列数统计。
        返回:
            StoredUpload: 保存后的上传记录。
        """
        created_at = datetime.utcnow().isoformat(timespec="seconds")
        upload_id = uuid4().hex
        headers_json = json.dumps(headers, ensure_ascii=False)
        rows_json = json.dumps(rows, ensure_ascii=False)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO uploads (
                    id, filename, headers_json, rows_json,
                    row_count, column_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    filename,
                    headers_json,
                    rows_json,
                    row_count,
                    column_count,
                    created_at,
                ),
            )
        return StoredUpload(
            id=upload_id,
            filename=filename,
            headers=headers,
            rows=rows,
            row_count=row_count,
            column_count=column_count,
            created_at=created_at,
        )

    def fetch_upload(self, upload_id: str) -> Optional[StoredUpload]:
        """
        功能说明:
            获取指定 ID 的上传表格记录。
        参数:
            upload_id (str): 上传记录 ID。
        返回:
            Optional[StoredUpload]: 找到则返回记录，否则为 None。
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM uploads
                WHERE id = ?
                """,
                (upload_id,),
            ).fetchone()
            if not row:
                return None
            headers = json.loads(row["headers_json"]) if row["headers_json"] else []
            rows = json.loads(row["rows_json"]) if row["rows_json"] else []
            return StoredUpload(
                id=row["id"],
                filename=row["filename"],
                headers=headers,
                rows=rows,
                row_count=row["row_count"],
                column_count=row["column_count"],
                created_at=row["created_at"],
            )

    def fetch_recent_uploads(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        功能说明:
            获取最近上传记录列表（不包含表格明细）。
        参数:
            limit (int): 返回的最大记录数。
        返回:
            List[Dict[str, Any]]: 上传记录摘要列表。
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = list(
                conn.execute(
                    """
                    SELECT id, filename, row_count, column_count, created_at
                    FROM uploads
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            )
            return [
                {
                    "id": row["id"],
                    "filename": row["filename"],
                    "row_count": row["row_count"],
                    "column_count": row["column_count"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def delete_upload(self, upload_id: str) -> bool:
        """
        功能说明:
            删除指定上传记录。
        参数:
            upload_id (str): 上传记录 ID。
        返回:
            bool: 是否成功删除。
        """
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM uploads
                WHERE id = ?
                """,
                (upload_id,),
            )
            return cursor.rowcount > 0
