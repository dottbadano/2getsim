import streamlit as st
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

@st.cache_resource
def get_google_credentials():
    cfg = st.secrets["google_oauth"]
    creds = Credentials(
        token=None,
        refresh_token=cfg["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds

def get_worksheet():
    creds = get_google_credentials()
    gc = gspread.authorize(creds)
    sheet_name = st.secrets["google_oauth"]["spreadsheet_name"]
    sh = gc.open(sheet_name)
    return sh.sheet1

def get_drive_service():
    creds = get_google_credentials()
    return build("drive", "v3", credentials=creds)

def registra_scelta(
    edizione: str,
    scenario: str,
    postazione: str,
    modalita: str,
    membri: str,
    passo: int,
    snodo_id: str,
    scelta: str,
    colore: str,
    anamnesi: str,
    vitalita: float,
    controllo_onc: float,
    qol: float,
    spesa_ssn: float,
):
    ws = get_worksheet()
    riga = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        edizione,
        scenario,
        postazione,
        modalita,
        membri,
        passo,
        snodo_id,
        scelta,
        colore,
        anamnesi,
        vitalita,
        controllo_onc,
        qol,
        spesa_ssn,
    ]
    ws.append_row(riga, value_input_option="USER_ENTERED")
