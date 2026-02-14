from lib.google_sheet import GoogleSheetApi
from lib.mysql_connector import MysqlConnector
from lib.slack import SlackNotifier


def update_to_sheet(host: str, query: str, sheet_info: dict, user_email=None, info_label=None) -> str:
    with MysqlConnector(host) as conn:
        query = query.replace("\n", " ").replace("\t", " ").strip()
        df = conn.read_query_table(query)

    gs_api = GoogleSheetApi()
    result = gs_api.paste_values_to_googlesheet(
        df, sheet_info["url"], sheet_info["sheet"], sheet_info["cell"]
    )

    if user_email:
        user_id = SlackNotifier.find_slackid(user_email)
        text = f"{info_label} Information Update Completed"
        header = f"{info_label} Information Update Completed! :partying_face:"
        url_button = {
            "text": ":point_right: Global Boosta Manual Entry",
            "emoji": True,
            "url": sheet_info["url"],
        }
        response = SlackNotifier.notify(
            text, header, user_id=user_id, url_button=url_button
        )
        result += f"\n{response.get('text', '')}\n"

    return result


def update_route(payload: dict) -> str:
    spreadsheet_url = "https://docs.google.com/spreadsheets/d/1JZi452tQn1ORaPi21gvI7t1hQkpQ7l8KF_dEg-n9rZY/"

    if payload["service"] == "product_info":
        query = """
            SELECT
                shops.shop_name,
                nansoft_products.product_code,
                nansoft_products.product_name,
                nansoft_products.barcode
            FROM nansoft_products
            INNER JOIN shops ON nansoft_products.shop_id = shops.id
            ORDER BY nansoft_products.shop_id, nansoft_products.barcode;
        """
        sheet_info = {"url": spreadsheet_url, "sheet": "Code", "cell": "L2"}
        info_label = "Product"
        host = "BOOSTA"
    elif payload["service"] == "customer_info":
        query = """
            SELECT
                erp_channel_lists.CustName,
                erp_channel_lists.CustClass,
                erp_channel_lists.CustBasicSeq
            FROM erp_channel_lists
            WHERE erp_channel_lists.CustClass IN ('수출B2B', '오프라인B2B')
            ORDER BY CustClass, CustBasicSeq;
        """
        sheet_info = {"url": spreadsheet_url, "sheet": "Code", "cell": "Q2"}
        info_label = "Customer"
        host = "BOOSTAAPI"
    else:
        return "Unknown service"

    return update_to_sheet(
        host=host,
        query=query,
        sheet_info=sheet_info,
        user_email=payload.get("user_email"),
        info_label=info_label,
    )
