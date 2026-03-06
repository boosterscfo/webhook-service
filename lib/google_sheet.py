import logging
import re
from functools import lru_cache

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from app.config import settings

logger = logging.getLogger(__name__)


class GoogleSheetApi:
    def __init__(self) -> None:
        creds = Credentials.from_service_account_file(
            settings.GOOGLE_KEY_PATH,
            scopes=[
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        self.gc = gspread.authorize(creds)

    @lru_cache(maxsize=16)
    def get_doc(self, spreadsheet_url: str) -> gspread.Spreadsheet:
        logger.debug("Opening spreadsheet: %s", spreadsheet_url)
        return self.gc.open_by_url(spreadsheet_url)

    def _get_worksheet(
        self, spreadsheet_url: str, sheetname: str | None = None
    ) -> gspread.Worksheet:
        doc = self.get_doc(spreadsheet_url)
        return doc.worksheet(sheetname) if sheetname else doc.sheet1

    def get_dataframe(
        self,
        spreadsheet_url: str,
        sheetname: str | None = None,
        header_row: int = 1,
        cell_range: str | None = None,
    ) -> pd.DataFrame:
        logger.debug(
            "Reading dataframe: sheet=%s, header_row=%d, cell_range=%s",
            sheetname,
            header_row,
            cell_range,
        )
        worksheet = self._get_worksheet(spreadsheet_url, sheetname)

        if cell_range:
            df = self._read_range(worksheet, cell_range, header_row)
        else:
            df = self._read_full_sheet(worksheet, header_row)

        df.dropna(how="all", axis=0, inplace=True)
        return df

    def _read_range(
        self, worksheet: gspread.Worksheet, cell_range: str, header_row: int
    ) -> pd.DataFrame:
        cells = worksheet.get(cell_range)
        if cells:
            header = self._make_unique_headers(cells[0])
            return pd.DataFrame(cells[1:], columns=header)
        header = self._make_unique_headers(worksheet.row_values(header_row))
        return pd.DataFrame(columns=header)

    def _read_full_sheet(
        self, worksheet: gspread.Worksheet, header_row: int
    ) -> pd.DataFrame:
        try:
            records = worksheet.get_all_records(head=header_row)
            if records:
                return pd.DataFrame(records)
            header = self._make_unique_headers(worksheet.row_values(header_row))
            return pd.DataFrame(columns=header)
        except Exception:
            logger.warning(
                "get_all_records failed for sheet '%s', falling back to get_all_values",
                worksheet.title,
                exc_info=True,
            )
            return self._read_full_sheet_fallback(worksheet, header_row)

    def _read_full_sheet_fallback(
        self, worksheet: gspread.Worksheet, header_row: int
    ) -> pd.DataFrame:
        all_values = worksheet.get_all_values()
        if all_values:
            header_idx = header_row - 1 if len(all_values) >= header_row else 0
            header = self._make_unique_headers(all_values[header_idx])
            data_rows = all_values[header_row:] if len(all_values) > header_row else []
            return pd.DataFrame(data_rows, columns=header)
        header = self._make_unique_headers(worksheet.row_values(header_row))
        return pd.DataFrame(columns=header)

    def paste_values_to_googlesheet(
        self,
        df: pd.DataFrame,
        spreadsheet_url: str,
        input_sheet_name: str,
        start_cell: str,
        append: bool = False,
    ) -> str:
        if df.empty:
            return "No data to paste"

        worksheet = self._get_worksheet(spreadsheet_url, input_sheet_name)

        if append:
            col_str, _ = self._parse_cell(start_cell)
            col_num = self.column_to_number(col_str)
            values_list = worksheet.col_values(col_num)
            last_row = len(values_list) + 1
            start_cell = f"{col_str}{last_row}"

        values = df.values.tolist()
        return self._update_worksheet_range(
            worksheet, start_cell, values, input_sheet_name
        )

    def update_sheet_range(
        self,
        spreadsheet_url: str,
        start_cell: str,
        data_array: list[list],
        sheetname: str | None = None,
    ) -> str:
        worksheet = self._get_worksheet(spreadsheet_url, sheetname)
        return self._update_worksheet_range(worksheet, start_cell, data_array, sheetname)

    def _update_worksheet_range(
        self,
        worksheet: gspread.Worksheet,
        start_cell: str,
        data_array: list[list],
        sheetname: str | None = None,
    ) -> str:
        if not data_array:
            return "No data to update.\n"

        num_rows = len(data_array)
        num_cols = len(data_array[0])

        start_col_str, start_row_str = self._parse_cell(start_cell)

        end_col_num = self.column_to_number(start_col_str) + num_cols - 1
        end_col = self.number_to_column(end_col_num)
        end_row = int(start_row_str) + num_rows - 1
        end_cell = f"{end_col}{end_row}"
        range_notation = f"{start_cell}:{end_cell}"

        worksheet.update(range_notation, data_array, value_input_option="USER_ENTERED")
        logger.debug("Updated %s on sheet '%s'", range_notation, sheetname)
        return f"{start_cell}:{end_cell} of {sheetname} is updated.\n"

    def clear_contents(
        self,
        spreadsheet_url: str,
        cell_range: str | None = None,
        sheetname: str | None = None,
    ) -> str:
        worksheet = self._get_worksheet(spreadsheet_url, sheetname)

        data = worksheet.get_all_values()
        if not data or not any(cell for row in data for cell in row):
            return "No data found to clear."
        max_row = len(data)

        start_row_index = 1
        if cell_range:
            parts = cell_range.split(":")[0]
            row_part = "".join(c for c in parts if c.isdigit())
            if row_part:
                start_row_index = int(row_part)

        if start_row_index > max_row:
            return f"Start row {start_row_index} is beyond the last row. No data to clear."

        if cell_range and ":" in cell_range:
            end_part = cell_range.split(":")[1]
            if not any(c.isdigit() for c in end_part):
                start_range = cell_range.split(":")[0]
                cell_range = f"{start_range}:{end_part}{max_row}"

        worksheet.batch_clear([cell_range])
        logger.debug("Cleared range %s on sheet '%s'", cell_range, sheetname)
        return f"Range {cell_range} has been cleared."

    @staticmethod
    def _parse_cell(cell: str) -> tuple[str, str]:
        match = re.match(r"^([A-Za-z]+)(\d+)$", cell)
        if not match:
            raise ValueError(f"Invalid cell reference: {cell}")
        return match.group(1).upper(), match.group(2)

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

    @staticmethod
    def _make_unique_headers(headers: list[str]) -> list[str]:
        seen: dict[str, int] = {}
        unique_headers: list[str] = []
        for header in headers:
            if header in seen:
                seen[header] += 1
                unique_headers.append(f"{header}_{seen[header]}")
            else:
                seen[header] = 0
                unique_headers.append(header)
        return unique_headers
