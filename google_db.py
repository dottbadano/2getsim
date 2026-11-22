import io
import json
import mimetypes
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import gspread
import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from supabase import Client, create_client

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

SOTTOCARTELLE_BIBLIO = ["EAU", "ESMO", "Farmaci e Studi Clinici"]


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
    return build("drive", "v3", credentials=creds, cache_discovery=False)


@st.cache_resource
def get_supabase_client() -> Client:
    """Inizializza il client Supabase Enterprise con chiave sb_secret."""
    url = st.secrets["SUPABASE_URL"].strip()
    key = st.secrets["SUPABASE_SERVICE_KEY"].strip()
    return create_client(url, key)


# ==============================================================================
# COMPATIBILITÀ SIMULATORE ESISTENTE (app.py)
# ==============================================================================

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


def _trova_o_crea_cartella(service, nome_cartella: str, parent_id: Optional[str] = None) -> str:
    q = f"name = '{nome_cartella}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    res = service.files().list(q=q, fields="files(id, name)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta: Dict[str, Any] = {"name": nome_cartella, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def _get_root_folders() -> Tuple[str, str]:
    """Restituisce (biblio_folder_id, cases_folder_id) usando i Secrets o creando la struttura su Drive."""
    service = get_drive_service()
    biblio_id = st.secrets.get("DRIVE_LIBRARY_FOLDER_ID", "").strip()
    cases_id = st.secrets.get("DRIVE_CASES_FOLDER_ID", "").strip()

    if not biblio_id or biblio_id.startswith("INCOLLA"):
        root_id = _trova_o_crea_cartella(service, "2getSIM_Congresso")
        biblio_id = _trova_o_crea_cartella(service, "Bibliografia", parent_id=root_id)

    if not cases_id or cases_id.startswith("INCOLLA"):
        root_id = _trova_o_crea_cartella(service, "2getSIM_Congresso")
        cases_id = _trova_o_crea_cartella(service, "Casi_Clinici_v2", parent_id=root_id)

    return biblio_id, cases_id


def _upsert_drive_file(folder_id: str, filename: str, data_bytes: bytes, mime_type: str) -> str:
    service = get_drive_service()
    q = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    existing = service.files().list(q=q, fields="files(id)").execute().get("files", [])
    media = MediaIoBaseUpload(io.BytesIO(data_bytes), mimetype=mime_type, resumable=False)
    if existing:
        fid = existing[0]["id"]
        service.files().update(fileId=fid, media_body=media).execute()
        return fid
    created = service.files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=media,
        fields="id",
    ).execute()
    return created["id"]


def carica_immagine_drive(uploaded_file, nome_caso: str, nodo_id: str) -> str:
    """Salva l'immagine nella cartella Drive dedicata al caso e restituisce drive:ID."""
    service = get_drive_service()
    _, cases_id = _get_root_folders()
    case_folder_id = _trova_o_crea_cartella(service, nome_caso, parent_id=cases_id)
    nome_pulito = f"{nome_caso}_{nodo_id}_{uploaded_file.name}"
    mime_type = uploaded_file.type or "image/png"
    fid = _upsert_drive_file(case_folder_id, nome_pulito, uploaded_file.getvalue(), mime_type)
    return f"drive:{fid}"


@st.cache_data(ttl=3600, show_spinner=False)
def scarica_immagine_drive(drive_ref: str) -> bytes:
    """Scarica i byte di un'immagine da Drive (accetta sia 'drive:ID' che 'ID')."""
    file_id = drive_ref.replace("drive:", "", 1)
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


# ==============================================================================
# BIBLIOTECA PDF & GEMINI FILES CACHE (24H)
# ==============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def elenca_documenti_bibliografia() -> List[Dict[str, str]]:
    """Elenca tutti i PDF/TXT nelle sottocartelle della Biblioteca su Drive."""
    service = get_drive_service()
    biblio_id, _ = _get_root_folders()

    documenti: List[Dict[str, str]] = []
    # Assicura le 3 sottocartelle canoniche
    for sub in SOTTOCARTELLE_BIBLIO:
        _trova_o_crea_cartella(service, sub, parent_id=biblio_id)

    def _scan(folder_id: str, cat_name: str):
        q = f"'{folder_id}' in parents and trashed = false"
        res = service.files().list(q=q, pageSize=100, fields="files(id, name, mimeType)").execute()
        for f in res.get("files", []):
            mime = f.get("mimeType", "")
            if mime == "application/vnd.google-apps.folder":
                _scan(f["id"], f["name"])
            elif mime in ("application/pdf", "text/plain") or f["name"].lower().endswith(".pdf"):
                documenti.append({
                    "id": f["id"],
                    "name": f["name"],
                    "mimeType": "application/pdf" if f["name"].lower().endswith(".pdf") else mime,
                    "categoria": cat_name,
                })

    _scan(biblio_id, "Generale")
    return sorted(documenti, key=lambda x: (x["categoria"], x["name"]))


@st.cache_data(ttl=86400, show_spinner=False)
def carica_file_drive_su_gemini(drive_file_id: str, file_name: str, mime_type: str, api_key: str) -> str:
    """Scarica il PDF da Drive e lo carica sulla Gemini Files API (cache 24h) restituendo il file_uri."""
    file_bytes = scarica_immagine_drive(drive_file_id)

    boundary = "----2getSIMBoundary7MA4YWxkTrZu0gW"
    meta_json = json.dumps({"file": {"display_name": file_name}}).encode("utf-8")
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
    ).encode("utf-8") + meta_json + (
        f"\r\n--{boundary}\r\n"
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    upload_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?uploadType=multipart&key={api_key}"
    req = urllib.request.Request(
        upload_url,
        data=body,
        headers={
            "Content-Type": f"multipart/related; boundary={boundary}",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))
        return res_data["file"]["uri"]


# ==============================================================================
# ARCHIVIO CASI v2.0 SU DRIVE + PUBBLICAZIONE SU SUPABASE ENTERPRISE
# ==============================================================================

def elenca_casi_drive() -> List[Dict[str, Any]]:
    """Elenca tutti i casi salvati in JSON v2.0 su Drive (bozza e pubblicato)."""
    service = get_drive_service()
    _, cases_id = _get_root_folders()
    q = f"'{cases_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    folders = service.files().list(q=q, fields="files(id, name)").execute().get("files", [])

    risultati: List[Dict[str, Any]] = []
    for folder in folders:
        qj = f"name = 'caso.json' and '{folder['id']}' in parents and trashed = false"
        jf = service.files().list(q=qj, fields="files(id)").execute().get("files", [])
        if not jf:
            continue
        try:
            raw = scarica_immagine_drive(jf[0]["id"])
            data = json.loads(raw.decode("utf-8"))
            meta = data.get("meta", {})
            risultati.append({
                "case_id": meta.get("case_id", folder["name"]),
                "titolo": meta.get("titolo", "Senza titolo"),
                "area_clinica": meta.get("area_clinica", "N/D"),
                "stato": meta.get("stato", "bozza"),
                "versione": meta.get("versione", 1),
                "updated_at": meta.get("updated_at", ""),
            })
        except Exception:
            continue

    return sorted(risultati, key=lambda x: x.get("updated_at", ""), reverse=True)


def carica_caso_drive(case_id: str) -> Optional[Dict[str, Any]]:
    """Carica il JSON v2.0 di un caso dalla sua cartella Drive."""
    service = get_drive_service()
    _, cases_id = _get_root_folders()
    folder_id = _trova_o_crea_cartella(service, case_id, parent_id=cases_id)
    qj = f"name = 'caso.json' and '{folder_id}' in parents and trashed = false"
    jf = service.files().list(q=qj, fields="files(id)").execute().get("files", [])
    if not jf:
        return None
    raw = scarica_immagine_drive(jf[0]["id"])
    return json.loads(raw.decode("utf-8"))


def salva_caso_drive(case_data: Dict[str, Any], increment_version: bool = False) -> Dict[str, Any]:
    """Salva caso.json v2.0 nella cartella Drive dedicata al caso."""
    service = get_drive_service()
    _, cases_id = _get_root_folders()
    now_iso = datetime.now(timezone.utc).isoformat()

    meta = case_data.setdefault("meta", {})
    case_id = meta["case_id"]
    if increment_version:
        meta["versione"] = int(meta.get("versione", 1)) + 1
    meta.setdefault("created_at", now_iso)
    meta["updated_at"] = now_iso
    case_data["schema_version"] = "2.0"

    folder_id = _trova_o_crea_cartella(service, case_id, parent_id=cases_id)
    json_bytes = json.dumps(case_data, ensure_ascii=False, indent=2).encode("utf-8")
    _upsert_drive_file(folder_id, "caso.json", json_bytes, "application/json")
    return case_data


def _sincronizza_immagini_su_supabase(case_data: Dict[str, Any]) -> Dict[str, Any]:
    """Copia le immagini referenziate negli snodi da Drive al bucket Supabase 'case-media'."""
    supa = get_supabase_client()
    case_id = case_data["meta"]["case_id"]

    for nid, nodo in case_data.get("nodi", {}).items():
        img_ref = nodo.get("immagine", "")
        if img_ref and img_ref.startswith("drive:"):
            file_bytes = scarica_immagine_drive(img_ref)
            storage_path = f"{case_id}/{nid}.png"
            supa.storage.from_("case-media").upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": "image/png", "upsert": "true"},
            )
            nodo["immagine_public_url"] = supa.storage.from_("case-media").get_public_url(storage_path)

    return case_data


def pubblica_caso_enterprise(case_data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    1. Imposta stato = 'pubblicato'
    2. Sincronizza le immagini su Supabase Storage ('case-media')
    3. Aggiorna la copia master caso.json su Google Drive
    4. Esegue upsert su Supabase tabella 'casi_clinici'
    """
    try:
        case_data["meta"]["stato"] = "pubblicato"
        case_data = _sincronizza_immagini_su_supabase(case_data)
        case_data = salva_caso_drive(case_data, increment_version=False)

        supa = get_supabase_client()
        meta = case_data["meta"]
        record = {
            "case_id": meta["case_id"],
            "stato": "pubblicato",
            "versione": int(meta.get("versione", 1)),
            "area_clinica": meta.get("area_clinica", ""),
            "titolo": meta.get("titolo", ""),
            "sottotitolo": meta.get("sottotitolo", ""),
            "payload": case_data,
            "updated_at": meta["updated_at"],
        }
        supa.table("casi_clinici").upsert(record, on_conflict="case_id").execute()
        return True, f"Caso {meta['case_id']} (v{meta['versione']}) pubblicato su Drive e Supabase.", case_data
    except Exception as e:
        return False, f"Errore durante la pubblicazione su Supabase: {str(e)}", case_data


def ritira_caso_in_bozza(case_data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """Riporta il caso in 'bozza' su Drive e lo rende invisibile nell'App Enterprise."""
    try:
        case_data["meta"]["stato"] = "bozza"
        case_data = salva_caso_drive(case_data, increment_version=False)

        supa = get_supabase_client()
        case_id = case_data["meta"]["case_id"]
        supa.table("casi_clinici").update({
            "stato": "bozza",
            "updated_at": case_data["meta"]["updated_at"],
        }).eq("case_id", case_id).execute()

        return True, f"Caso {case_id} riportato in BOZZA (nascosto dall'App Enterprise).", case_data
    except Exception as e:
        return False, f"Errore nel passaggio a bozza: {str(e)}", case_data
