from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd
import pymysql

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DBConfig:
    """Database connection configuration resolved from environment prefix."""

    host: str
    port: int
    user: str
    password: str
    database: str

    @classmethod
    def from_env(cls, environment: str) -> DBConfig:
        prefix = f"{environment.upper()}_"
        fields = ("HOST", "PORT", "USER", "PASSWORD", "DATABASE")
        try:
            values = {f.lower(): getattr(settings, f"{prefix}{f}") for f in fields}
        except AttributeError as e:
            raise ValueError(
                f"DB config missing for '{environment}'. "
                f"Required: {', '.join(f'{prefix}{f}' for f in fields)}"
            ) from e
        values["port"] = int(values["port"])
        return cls(**values)


class MysqlConnector:
    """MySQL connector with context manager, upsert, and delete+insert support.

    Usage:
        with MysqlConnector("CFO") as conn:
            df = conn.read_query_table("SELECT * FROM my_table")
            conn.upsert_data(df, "my_table")
            conn.delete_and_insert(df, "my_table", where="date = %s", where_params=("2024-01-01",))
    """

    def __init__(self, environment: str) -> None:
        self._config = DBConfig.from_env(environment)
        self._environment = environment
        self.connection = pymysql.connect(
            host=self._config.host,
            user=self._config.user,
            password=self._config.password,
            database=self._config.database,
            port=self._config.port,
            charset="utf8mb4",
            autocommit=False,
        )
        self.cursor = self.connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.connection.rollback()
            logger.warning(
                "Transaction rolled back on %s: %s: %s",
                self._environment, exc_type.__name__, exc_val,
            )
        self.close()

    def read_query_table(self, query: str, params: tuple | None = None) -> pd.DataFrame:
        """Execute a SELECT query and return results as DataFrame.

        Args:
            query: SQL query string. Use %s placeholders for parameters.
            params: Optional tuple of parameter values for safe interpolation.
        """
        self.cursor.execute(query, params)
        columns = [desc[0] for desc in self.cursor.description]
        rows = self.cursor.fetchall()
        return pd.DataFrame(rows, columns=columns)

    def upsert_data(
        self,
        df: pd.DataFrame,
        table_name: str,
        exclude_columns: tuple[str, ...] = ("id", "created_at", "updated_at"),
    ) -> str:
        """INSERT ... ON DUPLICATE KEY UPDATE (MySQL 8.0+ compatible).

        Uses VALUES() syntax which is universally supported across MySQL 8.0.x.
        The AS alias syntax (MySQL 8.0.20+) is avoided for cross-server compatibility.
        """
        if df.empty:
            return f"No data to upsert into {table_name}"

        df = df.fillna("")
        columns = [c for c in df.columns if c not in exclude_columns]
        placeholders = ", ".join(["%s"] * len(columns))
        col_list = ", ".join(f"`{c}`" for c in columns)
        update_set = ", ".join(f"`{c}` = VALUES(`{c}`)" for c in columns)

        query = (
            f"INSERT INTO `{table_name}` ({col_list}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_set}"
        )
        values = [tuple(row[c] for c in columns) for _, row in df.iterrows()]
        self.cursor.executemany(query, values)
        self.connection.commit()
        return f"{len(df)} records upserted into {table_name}"

    def delete_and_insert(
        self,
        df: pd.DataFrame,
        table_name: str,
        where: str,
        where_params: tuple | None = None,
        exclude_columns: tuple[str, ...] = ("id", "created_at", "updated_at"),
    ) -> str:
        """Delete matching rows then insert in a single transaction.

        Use when upsert is insufficient (e.g., composite key changes, full partition refresh).

        Args:
            df: Data to insert after deletion.
            table_name: Target table.
            where: WHERE clause with %s placeholders (e.g. "date = %s AND brand = %s").
            where_params: Parameter values for the WHERE clause.
            exclude_columns: Columns to skip during insert.
        """
        if df.empty:
            return f"No data to insert into {table_name}"

        df = df.fillna("")
        columns = [c for c in df.columns if c not in exclude_columns]
        placeholders = ", ".join(["%s"] * len(columns))
        col_list = ", ".join(f"`{c}`" for c in columns)

        delete_query = f"DELETE FROM `{table_name}` WHERE {where}"
        insert_query = f"INSERT INTO `{table_name}` ({col_list}) VALUES ({placeholders})"

        values = [tuple(row[c] for c in columns) for _, row in df.iterrows()]

        self.cursor.execute(delete_query, where_params)
        deleted = self.cursor.rowcount
        self.cursor.executemany(insert_query, values)
        self.connection.commit()

        logger.info("delete_and_insert on %s: deleted %d, inserted %d", table_name, deleted, len(values))
        return f"Deleted {deleted}, inserted {len(values)} rows in {table_name}"

    def get_column_max_length(self, table_name: str, column_name: str) -> int | None:
        """Get CHARACTER_MAXIMUM_LENGTH using parameterized query."""
        query = (
            "SELECT CHARACTER_MAXIMUM_LENGTH "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = %s "
            "AND COLUMN_NAME = %s"
        )
        result = self.read_query_table(query, (table_name, column_name))
        if not result.empty and result.iloc[0]["CHARACTER_MAXIMUM_LENGTH"] is not None:
            return int(result.iloc[0]["CHARACTER_MAXIMUM_LENGTH"])
        return None

    def close(self) -> None:
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

    # Legacy alias
    connectClose = close
