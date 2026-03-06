import logging

import pandas as pd

from app.config import settings
from lib.google_sheet import GoogleSheetApi
from lib.mysql_connector import MysqlConnector
from lib.slack import SlackNotifier

logger = logging.getLogger(__name__)

MIGRATION_SHEET_ID = "1qmbkOETkJJEUgb8N9njAOoCl17jnHg1Ya5PCJjIknBc"
SPREADSHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{MIGRATION_SHEET_ID}/"
)
TARGET_SHEET_NAME = "변경대상광고"
CHANNEL_ID = "C06NZHCD17F"

STEP1_QUERY = """
SELECT
    fia.id          AS internal_ad_id,
    fia.ad_id       AS meta_ad_id,
    fia.name        AS ad_name,
    fia.product_name,
    fia.ad_type,
    fia.author,
    fia.start_time  AS ad_start_time,
    fis.id          AS internal_adset_id,
    fis.adset_id    AS meta_adset_id,
    fis.name        AS adset_name,
    fis.start_time  AS adset_start_time,
    fic.id          AS internal_campaign_id,
    fic.campaign_id AS meta_campaign_id,
    fic.name        AS campaign_name
FROM facebook_id_ads fia
INNER JOIN facebook_id_adsets fis ON fia.adset_id = fis.id
INNER JOIN facebook_id_campaigns fic ON fis.campaign_id = fic.id
WHERE fic.name LIKE %s
  AND fia.status = 'ACTIVE'
  AND fis.status = 'ACTIVE'
  AND fic.status = 'ACTIVE'
ORDER BY fia.name
"""

STEP2_QUERY = """
SELECT
    facebook_id_ad_id   AS internal_ad_id,
    SUM(spend)                      AS spend_30d,
    SUM(impressions)                AS impr_30d,
    SUM(clicks)                     AS clicks_30d,
    SUM(fb_pixel_purchase)          AS purchases_30d,
    SUM(fb_pixel_purchase_values)   AS purchase_value_30d
FROM facebook_data_ads
WHERE date_start >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
  AND facebook_id_ad_id IN ({placeholders})
GROUP BY facebook_id_ad_id
ORDER BY spend_30d DESC
"""

STEP3_QUERY = """
SELECT
    facebook_id_ad_id   AS internal_ad_id,
    SUM(spend)                      AS spend_total,
    SUM(impressions)                AS impr_total,
    SUM(fb_pixel_purchase)          AS purchases_total,
    SUM(fb_pixel_purchase_values)   AS purchase_value_total,
    MIN(date_start)                 AS first_data_date,
    MAX(date_start)                 AS last_data_date
FROM facebook_data_ads
WHERE facebook_id_ad_id IN ({placeholders})
GROUP BY facebook_id_ad_id
ORDER BY spend_total DESC
"""

SHEET_COLUMNS = [
    "internal_ad_id",
    "meta_ad_id",
    "campaign_name",
    "adset_name",
    "ad_name",
    "parsed_date",
    "parsed_product",
    "parsed_ao_pm",
    "parsed_creative",
    "parsed_material",
    "parsed_remainder",
    "adset_start_time",
    "spend_30d",
    "impr_30d",
    "purchases_30d",
    "spend_total",
    "impr_total",
    "purchases_total",
    "purchase_value_total",
    "first_data_date",
    "last_data_date",
    "parse_error",
]

SHEET_HEADERS = [
    "내부 광고ID",
    "Meta 광고ID",
    "캠페인명",
    "세트명",
    "광고명(원본)",
    "파싱:세팅일자",
    "파싱:제품코드",
    "파싱:상시/프모",
    "파싱:제작유형",
    "파싱:소재유형",
    "파싱:USP+제작자+기타",
    "세트 시작일",
    "30일 지출",
    "30일 노출",
    "30일 구매",
    "전체 지출",
    "전체 노출",
    "전체 구매",
    "전체 구매금액",
    "최초 데이터일",
    "최종 데이터일",
    "파싱오류",
]


def _get_channel_id(payload: dict) -> str:
    if payload.get("test") and settings.SLACK_CHANNEL_ID_TEST:
        return settings.SLACK_CHANNEL_ID_TEST
    return CHANNEL_ID


def _extract_active_ads(conn: MysqlConnector) -> pd.DataFrame:
    return conn.read_query_table(STEP1_QUERY, params=("%이퀄베리%",))


def _extract_performance(
    conn: MysqlConnector, internal_ids: list[int]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    placeholders = ",".join(str(int(x)) for x in internal_ids)
    df_30d = conn.read_query_table(
        STEP2_QUERY.format(placeholders=placeholders)
    )
    df_total = conn.read_query_table(
        STEP3_QUERY.format(placeholders=placeholders)
    )
    return df_30d, df_total


def _to_native_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert Decimal and other DB-specific types to native Python types."""
    for col in df.columns:
        try:
            converted = pd.to_numeric(df[col], errors="coerce")
            if not converted.isna().all():
                has_original_strings = df[col].apply(
                    lambda x: isinstance(x, str)
                ).any()
                if not has_original_strings:
                    df[col] = converted.astype(float)
        except (ValueError, TypeError):
            pass
    return df


def _merge_data(
    df_ads: pd.DataFrame,
    df_30d: pd.DataFrame,
    df_total: pd.DataFrame,
) -> pd.DataFrame:
    result = (
        df_ads.merge(df_30d, on="internal_ad_id", how="left")
        .merge(df_total, on="internal_ad_id", how="left")
        .fillna(0)
        .sort_values("spend_30d", ascending=False)
    )
    return _to_native_types(result)


def _parse_legacy_names(df: pd.DataFrame) -> pd.DataFrame:
    parts = df["ad_name"].astype(str).str.split("_")

    df["parsed_date"] = ""
    df["parsed_product"] = ""
    df["parsed_ao_pm"] = ""
    df["parsed_creative"] = ""
    df["parsed_material"] = ""
    df["parsed_remainder"] = ""
    df["parse_error"] = False

    valid_mask = parts.str.len() >= 6

    df.loc[valid_mask, "parsed_date"] = parts[valid_mask].str[0]
    df.loc[valid_mask, "parsed_product"] = parts[valid_mask].str[1]
    df.loc[valid_mask, "parsed_ao_pm"] = parts[valid_mask].str[2]
    df.loc[valid_mask, "parsed_creative"] = parts[valid_mask].str[3]
    df.loc[valid_mask, "parsed_material"] = parts[valid_mask].str[4]
    df.loc[valid_mask, "parsed_remainder"] = parts[valid_mask].apply(
        lambda x: "_".join(x[5:])
    )

    date_invalid = ~df["parsed_date"].str.match(r"^\d{6}$") & valid_mask
    ao_pm_invalid = ~df["parsed_ao_pm"].isin({"ao", "pm"}) & valid_mask
    df.loc[~valid_mask | date_invalid | ao_pm_invalid, "parse_error"] = True

    return df


def _format_timestamp(series: pd.Series) -> pd.Series:
    """Convert microsecond/millisecond timestamps or datetime to YYYY-MM-DD strings."""
    def _convert(val):
        if pd.isna(val) or val == 0 or val == "0" or val == "":
            return ""
        if isinstance(val, str):
            if val.count("-") >= 2:
                return val[:10]
            try:
                val = float(val)
            except (ValueError, TypeError):
                return val
        if isinstance(val, (int, float)):
            ts = float(val)
            if ts > 1e15:
                ts = ts / 1_000_000
            elif ts > 1e12:
                ts = ts / 1_000
            try:
                return pd.Timestamp(ts, unit="s").strftime("%Y-%m-%d")
            except (ValueError, OSError):
                return str(val)
        return str(val)
    return series.apply(_convert)


def _build_sheet_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df[[c for c in SHEET_COLUMNS if c in df.columns]].copy()
    out["meta_ad_id"] = "'" + out["meta_ad_id"].astype(str)
    for col in ["adset_start_time", "first_data_date", "last_data_date"]:
        if col in out.columns:
            out[col] = _format_timestamp(out[col])
    return out


def _paste_to_sheet(gsapi: GoogleSheetApi, df: pd.DataFrame) -> str:
    result = gsapi.clear_contents(
        SPREADSHEET_URL, cell_range="A1:V", sheetname=TARGET_SHEET_NAME
    )
    result += gsapi.update_sheet_range(
        SPREADSHEET_URL, "A1", [SHEET_HEADERS], sheetname=TARGET_SHEET_NAME
    )
    if not df.empty:
        result += gsapi.paste_values_to_googlesheet(
            df, SPREADSHEET_URL, TARGET_SHEET_NAME, "A2"
        )
    return result


def _notify_slack(
    payload: dict, total: int, parsed_ok: int, parse_fail: int
) -> str:
    ch_id = _get_channel_id(payload)
    email = payload.get("user_email")
    user_id = SlackNotifier.find_slackid(email) if email else None

    header = "*[광고명 마이그레이션] 변경대상 광고 추출 완료*"
    body = (
        f"*추출 광고 수*: {total}건\n"
        f"*파싱 성공*: {parsed_ok}건\n"
        f"*파싱 실패*: {parse_fail}건"
    )
    footer = "Google Sheets에서 확인해주세요."
    url_button = {"text": "시트 열기", "url": SPREADSHEET_URL}

    try:
        return SlackNotifier.notify(
            text="광고명 마이그레이션 추출 완료",
            header=header,
            body=body,
            footer=footer,
            channel_id=ch_id,
            user_id=user_id,
            url_button=url_button,
            bot_name="META",
        )
    except Exception:
        logger.exception("Slack notification failed")
        return "Slack notification failed"


def run_extract(payload: dict) -> str:
    gsapi = GoogleSheetApi()
    result = ""

    with MysqlConnector("BOOSTA") as conn:
        df_ads = _extract_active_ads(conn)

        if df_ads.empty:
            msg = "Active 광고가 없습니다."
            logger.info(msg)
            _notify_slack(payload, total=0, parsed_ok=0, parse_fail=0)
            return msg

        internal_ids = df_ads["internal_ad_id"].tolist()
        df_30d, df_total = _extract_performance(conn, internal_ids)

    df = _merge_data(df_ads, df_30d, df_total)
    df = _parse_legacy_names(df)

    sheet_df = _build_sheet_dataframe(df)
    result += _paste_to_sheet(gsapi, sheet_df)

    total = len(df)
    parse_fail = int(df["parse_error"].sum())
    parsed_ok = total - parse_fail

    _notify_slack(payload, total, parsed_ok, parse_fail)

    summary = (
        f"추출 완료: 총 {total}건 "
        f"(파싱 성공 {parsed_ok}건, 실패 {parse_fail}건). "
        f"시트 업데이트 완료."
    )
    logger.info(summary)
    return summary
