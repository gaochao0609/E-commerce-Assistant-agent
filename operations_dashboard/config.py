"""运营仪表盘项目的配置模型，支持环境变量加载。"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AmazonCredentialConfig:
    """
    存放 Amazon PAAPI/Selling Partner 所需的访问凭证。

    属性:
        access_key (str): Amazon 提供的访问密钥。
        secret_key (str): 与访问密钥配套的密钥，用于签名。
        associate_tag (Optional[str]): 推广关联 ID，可为空。
        marketplace (str): 市场代码，默认使用 `US`。
    """

    access_key: str
    secret_key: str
    associate_tag: Optional[str] = None
    marketplace: str = "US"

    @classmethod
    def from_env(cls, prefix: str = "AMAZON_") -> "AmazonCredentialConfig":
        """
        功能说明:
            从环境变量读取 Amazon 凭证配置，若缺失则抛出异常。
        参数:
            prefix (str): 变量名前缀，允许在多环境中灵活切换。
        返回:
            AmazonCredentialConfig: 填充完成的配置实例。
        """
        access_key = os.getenv(f"{prefix}ACCESS_KEY", "")
        secret_key = os.getenv(f"{prefix}SECRET_KEY", "")
        associate_tag = os.getenv(f"{prefix}ASSOCIATE_TAG")
        marketplace = os.getenv(f"{prefix}MARKETPLACE", "US")
        # 凭证缺失时自动回退到 mock，避免阻断仅使用本地/模拟数据的场景。
        if not access_key or not secret_key:
            return cls(
                access_key="mock",
                secret_key="mock",
                associate_tag=associate_tag,
                marketplace=marketplace,
            )
        return cls(
            access_key=access_key,
            secret_key=secret_key,
            associate_tag=associate_tag,
            marketplace=marketplace,
        )


@dataclass
class DashboardConfig:
    """
    定义仪表盘层面的关键调优参数。

    属性:
        marketplace (str): 目标市场代码。
        refresh_window_days (int): 默认滚动窗口天数。
        top_n_products (int): 报告中关注的 Top 商品数量。
    """

    marketplace: str = "US"
    refresh_window_days: int = 7
    top_n_products: int = 20

    @classmethod
    def from_env(cls, prefix: str = "DASHBOARD_") -> "DashboardConfig":
        """
        功能说明:
            从环境变量加载仪表盘行为配置。
        参数:
            prefix (str): 环境变量前缀。
        返回:
            DashboardConfig: 包含窗口大小及 TopN 等参数的实例。
        """
        marketplace = os.getenv(f"{prefix}MARKETPLACE", "US")
        refresh_window_days = int(os.getenv(f"{prefix}WINDOW_DAYS", 7))
        top_n_products = int(os.getenv(f"{prefix}TOP_N", 20))
        return cls(
            marketplace=marketplace,
            refresh_window_days=refresh_window_days,
            top_n_products=top_n_products,
        )


@dataclass
class StorageConfig:
    """
    描述仪表盘汇总数据的持久化设置。

    属性:
        enabled (bool): 是否启用 SQLite 持久化能力。
        db_path (str): SQLite 文件路径，默认位于项目根目录。
    """

    enabled: bool = False
    db_path: str = "operations_dashboard.sqlite3"

    @classmethod
    def from_env(cls, prefix: str = "STORAGE_") -> "StorageConfig":
        """
        功能说明:
            从环境变量读取持久化相关配置。
        参数:
            prefix (str): 变量名前缀。
        返回:
            StorageConfig: 启用标识以及数据库路径配置。
        """
        enabled_raw = os.getenv(f"{prefix}ENABLED", "0").lower()
        enabled = enabled_raw in {"1", "true", "yes"}
        db_path = os.getenv(f"{prefix}DB_PATH", "operations_dashboard.sqlite3")
        return cls(enabled=enabled, db_path=db_path)


@dataclass
class AppConfig:
    """
    顶层组合配置，聚合凭证、仪表盘、存储与 LLM 设置。

    属性:
        amazon (AmazonCredentialConfig): Amazon 接入凭证。
        dashboard (DashboardConfig): 仪表盘运行参数。
        storage (StorageConfig): 持久化相关设置。
        openai_api_key (Optional[str]): OpenAI API Key。
        openai_model (str): 默认模型名称。
        openai_temperature (float): 生成温度。
    """

    amazon: AmazonCredentialConfig
    dashboard: DashboardConfig
    storage: StorageConfig
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-5-mini"
    openai_temperature: float = 0.0

    @classmethod
    def from_env(cls) -> "AppConfig":
        """
        功能说明:
            统一从环境变量载入所有子配置。
        返回:
            AppConfig: 完整的应用配置实例。
        """
        return cls(
            amazon=AmazonCredentialConfig.from_env(),
            dashboard=DashboardConfig.from_env(),
            storage=StorageConfig.from_env(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            openai_temperature=float(os.getenv("OPENAI_TEMPERATURE", "0")),
        )
