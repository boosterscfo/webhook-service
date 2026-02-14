import logging
import sys

import pandas as pd

from lib.google_sheet import GoogleSheetApi
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger("cash_mgmt")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


def _remove_comma_number(value):
    if isinstance(value, str):
        value = value.replace(",", "")
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _truncate_string(value, max_length, log=None):
    if not isinstance(value, str):
        return value
    value = value.strip()
    if max_length is None:
        return value
    if len(value) > max_length:
        original = value
        value = value[:max_length]
        if log:
            log.warning(
                f"String truncated ({max_length}): '{original}' -> '{value}'"
            )
    return value


def banktransactionUpload(payload):
    logger.info("banktransactionUpload started")

    gs_api = GoogleSheetApi()

    spreadsheet_url = "https://docs.google.com/spreadsheets/d/131-OBShJl6Pu8MtmPsLRdesIrmnLYz26GdoW9QJZKoc/"

    # --- banktransaction ---
    sheet_name = "DB_banktransaction"
    table_name = "fn_cash_banktransaction"

    df = gs_api.get_dataframe(spreadsheet_url, sheet_name, header_row=1)
    logger.info(f"Loaded {sheet_name}: {len(df)} rows")

    if "sheet_id" not in df.columns:
        if len(df) > 0:
            df.columns = df.iloc[0]
            df = df.drop(df.index[0]).reset_index(drop=True)
            if "sheet_id" not in df.columns:
                raise KeyError("sheet_id column not found")
        else:
            raise KeyError("No data")

    df["sheet_id"] = df["sheet_id"].apply(_remove_comma_number)

    process_cols = [
        "deposit", "withdrawal", "end_balance", "start_balance",
        "start_balance_KRW", "deposit_KRW", "withdrawal_KRW", "end_balance_KRW",
    ]

    for col in process_cols:
        df[col] = df[col].apply(lambda x: 0 if x == "-" or x == "" else x)

    for col in process_cols:
        df[col] = (
            pd.to_numeric(
                df[col].astype(str).str.replace(",", "")
                .str.replace("(", "-").str.replace(")", ""),
                errors="coerce",
            ).fillna(0)
        )

    non_process_cols = df.columns.difference(process_cols)
    df[non_process_cols] = df[non_process_cols].fillna("")

    if "fx_rate" in df.columns:
        df["fx_rate"] = pd.to_numeric(df["fx_rate"], errors="coerce").fillna(0)

    df["sheet_id"] = df["sheet_id"].astype(int)

    chunk_size = 20000
    with MysqlConnector("CFO") as conn:
        for start in range(0, len(df), chunk_size):
            chunk = df.iloc[start : start + chunk_size]
            msg = conn.upsert_data(chunk, table_name)
            logger.info(f"Chunk {start}-{start + chunk_size}: {msg}")

        # --- account_info ---
        sheet_name_acc = "account_info"
        table_name_acc = "fn_cash_bankaccount"

        df_acc = gs_api.get_dataframe(spreadsheet_url, sheet_name_acc, header_row=1)
        logger.info(f"Loaded {sheet_name_acc}: {len(df_acc)} rows")

        df_acc = df_acc.fillna("")

        acc_max_len = conn.get_column_max_length(table_name_acc, "acc_name")
        if acc_max_len and "acc_name" in df_acc.columns:
            df_acc["acc_name"] = df_acc["acc_name"].apply(
                lambda x: _truncate_string(x, acc_max_len, logger)
            )

        df_acc["sheet_id"] = df_acc["sheet_id"].astype(int)
        acc_msg = conn.upsert_data(df_acc, table_name_acc)
        logger.info(f"account_info: {acc_msg}")

    logger.info("banktransactionUpload completed")
    return f"{msg}\n{acc_msg}"
