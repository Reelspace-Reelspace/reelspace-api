import os, gspread, json
from google.oauth2.service_account import Credentials

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_sheet():
    sa_info = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    creds = Credentials.from_service_account_info(json.loads(sa_info), scopes=SCOPE)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    return sh

def append_row(sheet_name, row_values):
    sh = get_sheet()
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1, cols=len(row_values))
    ws.append_row(row_values, value_input_option="USER_ENTERED")
