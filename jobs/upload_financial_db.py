import logging
import sys

import pandas as pd

from lib.google_sheet import GoogleSheetApi
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger("financial_upload")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


def upload_financial_db(payload):
    logger.info("Started uploading financial data to DB")

    gs_api = GoogleSheetApi()

    spreadsheet_url = "https://docs.google.com/spreadsheets/d/1_ePkpj4FjjoMO44NG-K-gFPz3VHEnW-IZJ5xg5dxO2U/"
    doc = gs_api.get_doc(spreadsheet_url)
    ws_list = doc.worksheets()

    df_list = {}
    for ws in ws_list:
        df_list[ws.title] = gs_api.get_dataframe(spreadsheet_url, ws.title)
        logger.debug(f"Loaded sheet: {ws.title}")

    # PL: calculate sales rate and prior month
    df_pl = df_list["DB_PL"]
    df_pl_grouped = (
        pd.DataFrame(
            df_pl[df_pl["acc_name"] == "매출"]
            .groupby(["mtd_yyyymm", "sales_channel", "brand"])["amount"]
            .sum()
        )
        .reset_index()
        .rename(columns={"amount": "sales_amount"})
    )
    merged_df = pd.merge(
        df_pl, df_pl_grouped, on=["mtd_yyyymm", "sales_channel", "brand"], how="left"
    )

    # Prior month for PL
    df_pl_prior = df_pl.copy()
    df_pl_prior["mtd_yyyymm"] = pd.to_datetime(df_pl_prior["mtd_yyyymm"])
    df_pl_prior["mtd_yyyymm"] = (
        df_pl_prior["mtd_yyyymm"] + pd.DateOffset(months=1)
    ).dt.strftime("%Y-%m-%d")
    df_pl_prior = df_pl_prior.rename(columns={"amount": "prior_month"})
    df_pl_prior = df_pl_prior[
        ["mtd_yyyymm", "acc_name", "sales_channel", "brand", "prior_month"]
    ]

    merged_df_pl = pd.merge(
        merged_df,
        df_pl_prior,
        on=["mtd_yyyymm", "acc_name", "sales_channel", "brand"],
        how="left",
    )
    for col in ["amount", "sales_amount", "prior_month"]:
        merged_df_pl[col] = merged_df_pl[col].fillna(0).replace("", 0)

    df_list["DB_PL"] = merged_df_pl

    # Prior month for BS
    df_bs = df_list["DB_BS"].copy()
    df_bs["mtd_yyyymm"] = pd.to_datetime(df_bs["mtd_yyyymm"])
    df_bs["mtd_yyyymm"] = (
        df_bs["mtd_yyyymm"] + pd.DateOffset(months=1)
    ).dt.strftime("%Y-%m-%d")
    df_bs = df_bs.rename(columns={"amount": "prior_month"})
    df_bs = df_bs[["mtd_yyyymm", "acc_code", "acc_name", "prior_month"]]

    merged_df_bs = pd.merge(
        df_list["DB_BS"], df_bs, on=["mtd_yyyymm", "acc_code", "acc_name"], how="left"
    )
    merged_df_bs["prior_month"] = merged_df_bs["prior_month"].fillna(0)
    df_list["DB_BS"] = merged_df_bs

    # DB Upload
    table_map = {
        "DB_BS": "fn_fs_bs",
        "DB_PL": "fn_fs_pl",
        "DB_normalize": "fn_fs_pl_normalize",
        "DB_inventory": "fn_fs_bs_inventory_cost",
        "DB_advpayment": "fn_fs_bs_advpayment",
        "DB_accpayable": "fn_fs_bs_accpayable",
        "DB_unitcost": "fn_fs_bs_inventory_unitcost",
        "brand_aquisition": "fn_fs_bs_aquisitions",
        "benchmark": "fn_fs_benchmark",
        "Comments": "fn_fs_comments",
    }

    with MysqlConnector("CFO") as conn:
        for sheet_key, table in table_map.items():
            if sheet_key in df_list:
                conn.upsert_data(df_list[sheet_key], table)
                logger.debug(f"Upserted {sheet_key} -> {table}")

    logger.info("Finished uploading financial data to DB")
    return "Financial DB upload completed"
