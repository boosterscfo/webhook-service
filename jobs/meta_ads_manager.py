import re

import numpy as np
import pandas as pd

from lib.google_sheet import GoogleSheetApi
from lib.mysql_connector import MysqlConnector
from lib.slack import SlackNotifier

keyword_sheetname = "0_키워드생성"
sheet_name = "1_광고이름생성"
regis_sheetname = "2_변경대상광고"
unregis_sheetname = "2_등록대상광고"
delete_sheet_name = "2_삭제광고"
spreadsheet_url = "https://docs.google.com/spreadsheets/d/1zxUeBvU5k8Szvmmp_gBAqV9vCDGf2SGb_xPgxtlYOpg/"
regis_url = "https://docs.google.com/spreadsheets/d/1zxUeBvU5k8Szvmmp_gBAqV9vCDGf2SGb_xPgxtlYOpg/edit#gid=1225401231"
unregis_url = "https://docs.google.com/spreadsheets/d/1zxUeBvU5k8Szvmmp_gBAqV9vCDGf2SGb_xPgxtlYOpg/edit#gid=600293708"
default_email = "default@email.com"
channel_id = "C06NZHCD17F"


def slack_send(df, colname, channel_id, target, header, footer, url, user_id=None):
    header_text = f"""
*[{target} 알리미]*
안녕하세요. {header} :blush:
""".strip()

    body = ""
    for brand in df["brand"].unique():
        filtered = df.query(f"brand == '{brand}'")[colname]
        count = len(filtered)
        arr_name = [f"`{name}`" for name in filtered[:3].values]
        more = f"\nㆍ이외 {count - 3}건" if count > 3 else ""
        body += f"*{brand} (총 {count}건)*\n" + "\n".join(arr_name) + more + "\n\n"

    footer_text = f"`2_{target}` {footer}"
    url_button = {"text": "Meta Ads Manager", "url": url}

    return SlackNotifier.notify(
        f"{target} 알리미",
        header_text,
        body=body,
        footer=footer_text,
        channel_id=channel_id,
        url_button=url_button,
        user_id=user_id,
        bot_name="META",
    )


def update_ads(payload: dict) -> str:
    gsapi = GoogleSheetApi()
    result = ""
    email = payload.get("user_email")
    trigger = payload.get("trigger")
    user_id = SlackNotifier.find_slackid(email) if email else None

    with MysqlConnector("BOOSTA") as conn:
        # Latest date
        date_df = conn.read_query_table(
            "SELECT MAX(date_start) AS lastest_date FROM facebook_data_ads;"
        )
        date_np = np.datetime64(date_df.values[0, 0])
        str_date = np.datetime_as_string(date_np, unit="D")

        # Ads data
        meta_df = conn.read_query_table(
            f"SELECT campaign_name, ad_id, ad_name "
            f"FROM facebook_data_ads "
            f"WHERE date_start = '{str_date}' "
            f"ORDER BY ad_id ASC, ad_name ASC;"
        )

        # Registered ads with 7 # marks
        meta_ad_name_df = conn.read_query_table(
            "SELECT * FROM facebook_id_ads WHERE name REGEXP '^([^#]*#[^#]*){7}$';"
        )

    meta_df["brand"] = meta_df["campaign_name"].str.extract(r"\[(.*?)\]")

    # Sheet data
    sheet_df = gsapi.get_dataframe(spreadsheet_url, sheet_name, header_row=1)

    # --- 변경대상 광고 ---
    meta_ad_name_df["identity_id"] = meta_ad_name_df["identity_id"].str.replace(
        " - 사본", ""
    )
    meta_id_df = meta_ad_name_df[["identity_id"]].astype(str)

    sheet_df = gsapi.get_dataframe(spreadsheet_url, sheet_name, header_row=1)
    sheet_df = sheet_df.query("brand != ''").astype(str)
    sheet_df.rename(columns={"id": "identity_id"}, inplace=True)

    delete_ads_df = gsapi.get_dataframe(spreadsheet_url, delete_sheet_name, header_row=1)

    sheet_df = pd.merge(
        sheet_df, delete_ads_df, how="left", on=["brand", "ad_name"], indicator=True
    )
    sheet_df = sheet_df.query("_merge != 'both'").drop(columns="_merge")

    sheet_only_df = (
        pd.merge(sheet_df, meta_id_df, how="left", on="identity_id", indicator=True)
        .query("_merge != 'both'")[["brand", "ad_name", "ad_id", "old_name"]]
    )

    result += gsapi.clear_contents(spreadsheet_url, range="A2:D", sheetname=regis_sheetname)
    if not sheet_only_df.empty:
        sheet_only_df = sheet_only_df.astype(str)
        sheet_only_df["ad_id"] = "'" + sheet_only_df["ad_id"]
        result += gsapi.paste_values_to_googlesheet(
            sheet_only_df, spreadsheet_url, regis_sheetname, "A2"
        )

    # --- 등록대상 광고 ---
    wanna_regis = gsapi.get_dataframe(spreadsheet_url, unregis_sheetname, header_row=1)
    wanna_regis = wanna_regis.astype(str).query("old_name != ''")

    if not wanna_regis.empty:
        check_col = [
            "brand_name", "contents_detail", "product_name", "event", "date",
            "ad_creator", "k1_main_usp", "K2_hooking", "K3_sub_keyword",
        ]
        wanna_regis = wanna_regis[
            wanna_regis[check_col].apply(lambda x: any(x != ""), axis=1)
        ]
    num_wanna_regis = len(wanna_regis)

    unregis_df = meta_df[meta_df["ad_name"].str.count(" #") < 7]
    unregis_df = unregis_df[["brand", "ad_id", "ad_name"]].rename(
        columns={"ad_name": "old_name"}
    ).astype(str)

    wanna_regis = pd.concat([wanna_regis, unregis_df])
    wanna_regis = wanna_regis.drop_duplicates(subset=["old_name"], keep="first")

    exist_ad_id = sheet_df[["ad_id"]].query("ad_id != ''")
    wanna_regis = pd.merge(wanna_regis, exist_ad_id, how="left", indicator=True)
    wanna_regis = wanna_regis.query("_merge != 'both'")

    using_col = [
        "brand", "ad_id", "old_name", "brand_name", "contents_detail",
        "product_name", "event", "date", "ad_creator", "k1_main_usp",
        "K2_hooking", "K3_sub_keyword", "description",
    ]
    wanna_regis = wanna_regis[[c for c in using_col if c in wanna_regis.columns]]

    result += gsapi.clear_contents(spreadsheet_url, range="A2:M", sheetname=unregis_sheetname)
    if not wanna_regis.empty:
        wanna_regis.fillna("", inplace=True)
        wanna_regis["ad_id"] = "'" + wanna_regis["ad_id"]
        result += gsapi.paste_values_to_googlesheet(
            wanna_regis, spreadsheet_url, unregis_sheetname, "A2"
        )

    # --- Slack ---
    change_header = "`2_변경대상광고` 시트에 아래 변경 대상 광고가 업데이트 되었습니다."
    change_footer = "광고관리자 페이지에서 시트에 등록된 광고명으로 변경해주세요. 변경후에도 `2_변경대상광고` 시트에서 내역이 사라지기까지 최대 1일 정도 걸릴 수 있습니다."
    regis_header = "`2_등록대상광고` 시트에 아래 등록 대상 광고가 업데이트 되었습니다."
    regis_footer = "시트에 정보를 기입하고 Key 컬럼에 값이 생성되면, 구글 시트의 입력 메뉴에 `2.광고등록` 버튼을 누르면 자동으로 등록됩니다!"

    if not trigger:
        if user_id:
            slack_send(sheet_only_df, "ad_name", channel_id, "업데이트", change_header, change_footer, regis_url, user_id)
            slack_send(wanna_regis, "old_name", channel_id, "업데이트", regis_header, regis_footer, unregis_url, user_id)
        else:
            slack_send(sheet_only_df, "ad_name", channel_id, "업데이트", change_header, change_footer, regis_url)
            slack_send(wanna_regis, "old_name", channel_id, "업데이트", regis_header, regis_footer, unregis_url)
    else:
        slack_send(sheet_only_df, "ad_name", channel_id, "업데이트", change_header, change_footer, regis_url)
        slack_send(wanna_regis, "old_name", channel_id, "업데이트", regis_header, regis_footer, unregis_url)

    return result


def add_ad(payload: dict) -> str:
    gsapi = GoogleSheetApi()
    result = ""

    wanna_regis = gsapi.get_dataframe(spreadsheet_url, unregis_sheetname, header_row=1).astype(str)
    keyword_df = gsapi.get_dataframe(spreadsheet_url, keyword_sheetname, header_row=1)

    target_regis = wanna_regis.query(
        "Key != '' & brand_name !='' & contents_detail !='' & product_name !='' & event !='' & date !='' & ad_creator !=''"
    )
    reserve_regis = wanna_regis.query("Key == ''")

    if target_regis.empty:
        return result

    using_col = [
        "brand", "ad_id", "old_name", "brand_name", "contents_detail",
        "product_name", "event", "date", "ad_creator", "k1_main_usp",
        "K2_hooking", "K3_sub_keyword", "description",
    ]
    reserve_regis = reserve_regis[[c for c in using_col if c in reserve_regis.columns]]

    index_list = [
        idx for idx, val in target_regis["Key"].items()
        if val not in keyword_df["Key"].values
    ]

    add_keyword_df = target_regis.loc[index_list][
        ["brand", "k1_main_usp", "K2_hooking", "K3_sub_keyword", "description"]
    ].drop_duplicates()
    result += gsapi.paste_values_to_googlesheet(
        add_keyword_df, spreadsheet_url, keyword_sheetname, "A2", append=True
    )

    add_ad_df = target_regis[["Key", "contents_detail", "product_name", "event", "date", "ad_creator"]]
    add_id_df = target_regis[["ad_id", "old_name"]]
    raw_result = gsapi.paste_values_to_googlesheet(
        add_ad_df, spreadsheet_url, sheet_name, "B2", append=True
    )
    result += raw_result
    matches = re.findall(r"(\d+):", raw_result)
    startcell = "I" + matches[0]
    result += gsapi.paste_values_to_googlesheet(
        add_id_df, spreadsheet_url, sheet_name, startcell
    )

    result += gsapi.clear_contents(spreadsheet_url, range="A2:L", sheetname=unregis_sheetname)
    result += gsapi.paste_values_to_googlesheet(
        reserve_regis, spreadsheet_url, unregis_sheetname, "A2"
    )

    # Slack
    header = "광고 및 키워드 등록이 완료되었습니다. 등록된 광고는 다음과 같습니다."
    footer = "등록된 광고를 광고관리자에 등록해주세요. `2_변경대상광고` 시트에서 광고관리자에서 이름을 변경할 광고들을 확인해주세요."
    email = payload.get("user_email", default_email)
    user_id = SlackNotifier.find_slackid(email)

    if email != default_email and not target_regis.empty:
        if user_id:
            slack_send(target_regis, "old_name", channel_id, "광고 업데이트", header, footer, regis_url, user_id)
        else:
            slack_send(target_regis, "old_name", channel_id, "광고 업데이트", header, footer, regis_url)

    update_ads({"user_email": default_email})
    return result


def regis_slack_send(payload: dict = None) -> str:
    gsapi = GoogleSheetApi()
    regis_df = gsapi.get_dataframe(spreadsheet_url, regis_sheetname, header_row=1)
    return slack_send(
        regis_df, "new_name", "C04FQ47F231", "변경대상광고",
        "Meta 광고 중 시트에 등록되었으나 어드민에서 변경되지 않아 어드민 변경대상인 광고 알려드립니다.",
        "해당 시트의 ID 를 검색하여 등록된 광고명으로 변경해주세요.",
        regis_url,
    )


def unregis_slack_send(payload: dict = None) -> str:
    gsapi = GoogleSheetApi()
    unregis_df = gsapi.get_dataframe(spreadsheet_url, unregis_sheetname, header_row=1)
    return slack_send(
        unregis_df, "old_name", "C04FQ47F231", "등록대상광고",
        "Meta 광고 중 표준 광고명칭으로 바뀌지 않아 우선 시트에 등록하여 광고명이 생성되어야 하는 광고 알려드립니다.",
        "시트에 정보를 기입하고 Key 컬럼에 값이 생성되면, 구글 시트의 입력 메뉴에 `2.광고등록` 버튼을 누르면 자동으로 등록됩니다!",
        unregis_url,
    )


def unregis_user_slack_send(payload: dict) -> str:
    gsapi = GoogleSheetApi()
    result = ""

    unregis_df = gsapi.get_dataframe(spreadsheet_url, unregis_sheetname, header_row=1)
    unregis_df = unregis_df.query("email != ''")

    if unregis_df.empty:
        return "등록할 데이터가 없거나 보낼 사람을 찾지 못하였습니다"

    for email in unregis_df["email"].unique():
        temp_df = unregis_df.query(f"email == '{email}'")
        user_id = SlackNotifier.find_slackid(email)
        if user_id:
            name = temp_df["ad_creator"].iloc[0]
            header = f"{name} 크루님, Meta 광고 중 표준 광고명칭으로 바뀌지 않아 우선 시트에 등록하여 광고명이 생성되어야 하는 광고 알려드립니다!"
            footer = f"시트에서 {name} 크루님 이름으로 되어 있는 항목에 정보 입력한 후, Key 컬럼에 값이 생성되면, 구글 시트의 입력 메뉴에 `2.광고등록` 버튼을 누르면 자동으로 등록됩니다!"
            result = slack_send(temp_df, "old_name", channel_id, "등록대상광고", header, footer, unregis_url, user_id)
    return result


def regis_user_slack_send(payload: dict) -> str:
    gsapi = GoogleSheetApi()
    result = ""

    regis_df = gsapi.get_dataframe(spreadsheet_url, regis_sheetname, header_row=1)
    regis_df["creator"] = regis_df["ad_name"].str.extract(r"(?:.*?\s#){4}([^#]+)")

    email_df = gsapi.get_dataframe(
        spreadsheet_url, "기타코드", header_row=1, range="S1:T100"
    ).query("email != ''")

    regis_df["creator"] = regis_df["creator"].str.strip()
    regis_df = pd.merge(regis_df, email_df, how="left", on="creator")
    regis_df = regis_df.query("email != ''")

    if regis_df.empty:
        return "변경할 데이터가 없거나 보낼 사람을 찾지 못하였습니다"

    for email in regis_df["email"].unique():
        temp_df = regis_df.query(f"email == '{email}'")
        user_id = SlackNotifier.find_slackid(email)
        if user_id:
            name = temp_df["creator"].iloc[0]
            header = f"{name} 크루님, 시트에 등록된 광고 중 변경이 되지 않은 광고가 있어서 알림드립니다"
            footer = f"`2_변경대상광고` 시트에서 {name} 크루님 이름으로 되어 있는 광고를 등록해주세요. 이미 등록하신 경우 최대 1일 이내에 시트에서 해당 광고가 사라집니다."
            result = slack_send(temp_df, "ad_name", channel_id, "변경대상광고", header, footer, regis_url, user_id)
    return result
