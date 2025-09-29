from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class AmazonCredentialConfig:
    """Amazon API 凭证配置。"""

    access_key: str
    secret_key: str
    associate_tag: Optional[str] = None
    marketplace: str = "US"

    @classmethod
    def from_env(cls, prefix: str = "AMAZON_") -> "AmazonCredentialConfig":
        """从环境变量构造 Amazon 凭证配置。"""

        access_key = os.getenv(f"{prefix}ACCESS_KEY", "")
        secret_key = os.getenv(f"{prefix}SECRET_KEY", "")
        associate_tag = os.getenv(f"{prefix}ASSOCIATE_TAG")
        marketplace = os.getenv(f"{prefix}MARKETPLACE", "US")
        if not access_key or not secret_key:
            raise RuntimeError(
                "Amazon API credentials are missing."
                f" Set {prefix}ACCESS_KEY and {prefix}SECRET_KEY."
            )
        return cls(
            access_key=access_key,
            secret_key=secret_key,
            associate_tag=associate_tag,
            marketplace=marketplace,
        )


@dataclass
class DashboardConfig:
    """运行数据总览相关的可调参数配置。"""

    marketplace: str = "US"
    refresh_window_days: int = 7
    top_n_products: int = 20

    @classmethod
    def from_env(cls, prefix: str = "DASHBOARD_") -> "DashboardConfig":
        """从环境变量构造仪表盘配置。"""

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
    """持久化层配置。"""

    enabled: bool = False
    db_path: str = "operations_dashboard.sqlite3"

    @classmethod
    def from_env(cls, prefix: str = "STORAGE_") -> "StorageConfig":
        """从环境变量载入持久化设置。"""

        enabled_raw = os.getenv(f"{prefix}ENABLED", "0").lower()
        enabled = enabled_raw in {"1", "true", "yes"}
        db_path = os.getenv(f"{prefix}DB_PATH", "operations_dashboard.sqlite3")
        return cls(enabled=enabled, db_path=db_path)


@dataclass
class AppConfig:
    """聚合 Amazon 凭证、仪表盘与持久化设置的总配置对象。"""

    amazon: AmazonCredentialConfig
    dashboard: DashboardConfig
    storage: StorageConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        """从环境变量完成整体配置载入。"""

        return cls(
            amazon=AmazonCredentialConfig.from_env(),
            dashboard=DashboardConfig.from_env(),
            storage=StorageConfig.from_env(),
        )
