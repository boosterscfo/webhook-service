import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from app.config import settings


class GoogleSheetApi:
    def __init__(self) -> None:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(
            settings.GOOGLE_KEY_PATH, scopes=scope
        )
        self.gc = gspread.Client(auth=creds)

    def get_doc(self, spreadsheet_url: str):
        return self.gc.open_by_url(spreadsheet_url)

    def get_dataframe(
        self, spreadsheet_url, sheetname=None, header_row=1, range=None
    ) -> pd.DataFrame:
        doc = self.get_doc(spreadsheet_url)
        worksheet = doc.worksheet(sheetname) if sheetname else doc.sheet1

        if range:
            cells = worksheet.get(range)
            if cells:
                header = self._make_unique_headers(cells[0])
                df = pd.DataFrame(cells[1:], columns=header)
            else:
                header = self._make_unique_headers(worksheet.row_values(header_row))
                df = pd.DataFrame(columns=header)
        else:
            try:
                records = worksheet.get_all_records(head=header_row)
                if records:
                    df = pd.DataFrame(records)
                else:
                    header = self._make_unique_headers(worksheet.row_values(header_row))
                    df = pd.DataFrame(columns=header)
            except Exception:
                all_values = worksheet.get_all_values()
                if all_values:
                    header_idx = header_row - 1 if len(all_values) >= header_row else 0
                    header = self._make_unique_headers(all_values[header_idx])
                    data_rows = all_values[header_row:] if len(all_values) > header_row else []
                    df = pd.DataFrame(data_rows, columns=header)
                else:
                    header = self._make_unique_headers(worksheet.row_values(header_row))
                    df = pd.DataFrame(columns=header)

        df.dropna(how="all", axis=0, inplace=True)
        return df

    def paste_values_to_googlesheet(
        self, df, spreadsheet_url, input_sheet_name, start_cell, append=False
    ) -> str:
        if df.empty:
            return "No data to paste"

        doc = self.get_doc(spreadsheet_url)
        worksheet = doc.worksheet(input_sheet_name)

        if append:
            col_letter = start_cell[0]
            values_list = worksheet.col_values(self.column_to_number(col_letter))
            last_row = len(values_list) + 1
            start_cell = f"{col_letter}{last_row}"

        values = df.values.tolist()
        return self.update_sheet_range(
            spreadsheet_url, start_cell, values, input_sheet_name
        )

    def update_sheet_range(
        self, spreadsheet_url, start_cell, data_array, sheetname=None
    ) -> str:
        doc = self.get_doc(spreadsheet_url)
        worksheet = doc.worksheet(sheetname) if sheetname else doc.sheet1

        if data_array and len(data_array) > 0:
            num_rows = len(data_array)
            num_cols = len(data_array[0])

            start_col_str = ""
            start_row_str = ""
            for ch in start_cell:
                if ch.isalpha():
                    start_col_str += ch
                else:
                    start_row_str += ch

            end_col_num = self.column_to_number(start_col_str) + num_cols - 1
            end_col = self.number_to_column(end_col_num)
            end_row = int(start_row_str) + num_rows - 1
            end_cell = f"{end_col}{end_row}"
            cell_range = f"{start_cell}:{end_cell}"

            worksheet.update(cell_range, data_array, value_input_option="USER_ENTERED")

            return f"{start_cell}:{end_cell} of {sheetname} is updated.\n"
        return "No data to update.\n"

    def clear_contents(self, spreadsheet_url, range=None, sheetname=None) -> str:
        doc = self.get_doc(spreadsheet_url)
        worksheet = doc.worksheet(sheetname) if sheetname else doc.sheet1

        data = worksheet.get_all_values()
        if not data or not any(row for row in data if any(cell for cell in row)):
            return "No data found to clear."
        max_row = len(data)

        start_row_index = 1
        if range:
            parts = range.split(":")[0]
            row_part = "".join(c for c in parts if c.isdigit())
            if row_part:
                start_row_index = int(row_part)

        if start_row_index > max_row:
            return f"Start row {start_row_index} is beyond the last row. No data to clear."

        if range and ":" in range:
            end_part = range.split(":")[1]
            if not any(c.isdigit() for c in end_part):
                start_range = range.split(":")[0]
                range = f"{start_range}:{end_part}{max_row}"

        worksheet.batch_clear([range])
        return f"Range {range} has been cleared."

    @staticmethod
    def column_to_number(col_str: str) -> int:
        number = 0
        for char in col_str.upper():
            number = number * 26 + (ord(char) - ord("A") + 1)
        return number

    @staticmethod
    def number_to_column(col_num: int) -> str:
        col_str = ""
        while col_num > 0:
            col_num, remainder = divmod(col_num - 1, 26)
            col_str = chr(65 + remainder) + col_str
        return col_str

    def _make_unique_headers(self, headers: list) -> list:
        seen = {}
        unique_headers = []
        for header in headers:
            if header in seen:
                seen[header] += 1
                unique_headers.append(f"{header}_{seen[header]}")
            else:
                seen[header] = 0
                unique_headers.append(header)
        return unique_headers
