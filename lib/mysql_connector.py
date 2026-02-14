import logging

import pandas as pd
import pymysql

from app.config import settings

logger = logging.getLogger(__name__)


class MysqlConnector:
    def __init__(self, environment: str) -> None:
        prefix = f"{environment.upper()}_"
        self.connection = pymysql.connect(
            host=getattr(settings, f"{prefix}HOST"),
            user=getattr(settings, f"{prefix}USER"),
            password=getattr(settings, f"{prefix}PASSWORD"),
            database=getattr(settings, f"{prefix}DATABASE"),
            port=getattr(settings, f"{prefix}PORT"),
            charset="utf8mb4",
        )
        self.cursor = self.connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def read_query_table(self, query: str) -> pd.DataFrame:
        self.cursor.execute(query)
        columns = [desc[0] for desc in self.cursor.description]
        rows = self.cursor.fetchall()
        return pd.DataFrame(rows, columns=columns)

    def upsert_data(self, df: pd.DataFrame, table_name: str) -> str:
        if df.empty:
            return f"No data to upsert into {table_name}"

        df = df.fillna("")
        columns = [c for c in df.columns if c not in ("id", "created_at", "updated_at")]
        placeholders = ", ".join(["%s"] * len(columns))
        col_list = ", ".join(columns)
        update_set = ", ".join(f"{c} = new.{c}" for c in columns)

        query = (
            f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders}) "
            f"AS new ON DUPLICATE KEY UPDATE {update_set}"
        )
        values = [tuple(row[c] for c in columns) for _, row in df.iterrows()]
        self.cursor.executemany(query, values)
        self.connection.commit()
        return f"{len(df)} records upserted into {table_name}"

    def get_column_max_length(self, table_name: str, column_name: str) -> int | None:
        query = (
            "SELECT CHARACTER_MAXIMUM_LENGTH "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            f"AND TABLE_NAME = '{table_name}' "
            f"AND COLUMN_NAME = '{column_name}'"
        )
        result = self.read_query_table(query)
        if not result.empty and result.iloc[0]["CHARACTER_MAXIMUM_LENGTH"] is not None:
            return int(result.iloc[0]["CHARACTER_MAXIMUM_LENGTH"])
        return None

    def close(self) -> None:
        self.cursor.close()
        self.connection.close()

    # Legacy alias
    def connectClose(self) -> None:
        self.close()
