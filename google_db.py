import io
from datetime import datetime
import gspread
import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

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


def _trova_o_crea_cartella(service, nome_cartella: str, parent_id: str = None) -> str:
    q = f"name = '{nome_cartella}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    res = service.files().list(q=q, fields="files(id, name)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": nome_cartella, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def carica_immagine_drive(uploaded_file, nome_caso: str, nodo_id: str) -> str:
    """Carica un'immagine su Drive dentro 2getSIM_Congresso/01_Media_Casi_Clinici e restituisce drive:ID."""
    service = get_drive_service()
    root_id = _trova_o_crea_cartella(service, "2getSIM_Congresso")
    media_id = _trova_o_crea_cartella(service, "01_Media_Casi_Clinici", parent_id=root_id)

    nome_pulito = f"{nome_caso}_{nodo_id}_{uploaded_file.name}"
    meta = {"name": nome_pulito, "parents": [media_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(uploaded_file.getvalue()),
        mimetype=uploaded_file.type or "image/png",
        resumable=False,
    )
    file_creato = service.files().create(body=meta, media_body=media, fields="id").execute()
    return f"drive:{file_creato['id']}"


@st.cache_data(ttl=3600, show_spinner=False)
def scarica_immagine_drive(drive_ref: str) -> bytes:
    """Scarica l'immagine da Drive e la mantiene in cache per i tablet collegati."""
    file_id = drive_ref.replace("drive:", "", 1)
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()
