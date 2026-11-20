import importlib
import os
import random
import time
from datetime import datetime
import streamlit as st
from case_builder import render_case_builder
from font import apply_fonts
from security import render_regia_master, risolvi_identita_gioco, verifica_accesso
from valutazione import render_osservatorio_master

try:
    from google_db import registra_scelta, scarica_immagine_drive
    GSHEETS_ATTIVO = True
except Exception:
    GSHEETS_ATTIVO = False

st.set_page_config(page_title="2getSIM", page_icon="⚡", layout="wide")
apply_fonts()

st.markdown(
    """
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="2getSIM">
    <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display: none;}
        [data-testid="stToolbar"] {display: none !important;}
        [data-testid="stDecoration"] {display: none !important;}
        [data-testid="stStatusWidget"] {display: none !important;}
        .block-container {
            padding-top: 1.2rem !important;
            padding-bottom: 1.5rem !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

room, role, uid = verifica_accesso()
bucket, etichetta = risolvi_identita_gioco(room, role, uid)

CASE_DIR = "storycase"
os.makedirs(CASE_DIR, exist_ok=True)
cases = sorted([f[:-3] for f in os.listdir(CASE_DIR) if f.endswith(".py") and f != "__init__"])


def get_case_label(case_id):
    if role != "master":
        return case_id
    try:
        mod = importlib.import_module(f"{CASE_DIR}.{case_id}")
        desc = mod.CASO.get("descrizione_master") or mod.CASO.get("titolo", "")
        return f"{case_id} — {desc}" if desc else case_id
    except Exception:
        return case_id


def _deduci_colore_opzione(opt):
    if opt.get("colore") in ("verde", "blu", "giallo", "rosso"):
        return opt["colore"]
    do, dv, dq = opt.get("d_onc", 0), opt.get("d_vit", 0), opt.get("d_qol", 0)
    if do > 0 and dv >= 0:
        return "verde"
    if dq <= -20 and do >= -15:
        return "giallo"
    if dv <= -15 or do <= -25:
        return "rosso"
    return "blu"


def _is_terminato(stato_run, caso_dict):
    nid = stato_run.get("current_node", "")
    if nid in caso_dict.get("esiti", {}):
        return True
    if stato_run.get("vitalita", 100) <= 0:
        return True
    if stato_run.get("oncologico", 100) <= 0:
        return True
    if stato_run.get("qol", 75) < 30:
        return True
    return False


def _applica_scelta_in_coda(stato_run, scenario_id="", postazione_id="", room_ref=None):
    pending = stato_run.pop("scelta_pendente", None)
    if not pending:
        return
    opt = pending["opt"]
    col_scelta = _deduci_colore_opzione(opt)

    stato_run["vitalita"] = max(0, min(100, stato_run["vitalita"] + opt.get("d_vit", 0)))
    stato_run["oncologico"] = max(0, min(100, stato_run["oncologico"] + opt.get("d_onc", 0)))
    stato_run["qol"] = max(0, min(100, stato_run["qol"] + opt.get("d_qol", 0)))

    stato_run["percorso"].append(
        {
            "nodo_id": pending["nodo_id"],
            "nodo": pending["nodo_titolo"],
            "scelta": opt["testo"],
            "colore": col_scelta,
            "razionale": opt.get("razionale", ""),
            "anamnesi_aperta": pending["anamnesi_aperta"],
        }
    )
    stato_run["current_node"] = opt["next"]

    entita_low = postazione_id.lower()
    is_docente = entita_low in ("gbadano", "acavo", "smigone") or entita_low.startswith("master")
    if GSHEETS_ATTIVO and not is_docente:
        try:
            r_ref = room_ref or {}
            registra_scelta(
                edizione=str(r_ref.get("edizione", f"Corso_{datetime.now().strftime('%Y_%m')}")),
                scenario=scenario_id,
                postazione=postazione_id,
                modalita=str(r_ref.get("modalita_attiva", r_ref.get("modalita", "Aula"))),
                membri=str(stato_run.get("etichetta", postazione_id)),
                passo=len(stato_run["percorso"]),
                snodo_id=str(pending["nodo_id"]),
                scelta=str(opt["testo"]),
                colore=col_scelta,
                anamnesi="Sì" if pending["anamnesi_aperta"] else "No",
                vitalita=stato_run["vitalita"],
                controllo_onc=stato_run["oncologico"],
                qol=stato_run["qol"],
                spesa_ssn=0,
            )
        except Exception as e:
            st.session_state["ultimo_errore_gsheets"] = str(e)


def _sincronizza_barriera_aula(room, selected_id, caso_dict, forzata=False):
    pref = f"{selected_id}__"
    attivi = []
    for k, v in room.get("stati_casi", {}).items():
        if not k.startswith(pref):
            continue
        entita = k[len(pref):]
        if entita.lower() in ("gbadano", "acavo", "smigone") or entita.lower().startswith("master"):
            continue
        if not _is_terminato(v, caso_dict):
            attivi.append((entita, v))

    if not attivi:
        return 0, 0, False

    min_step = min(len(v.get("percorso", [])) for _, v in attivi)
    in_gioco_questo_passo = [(ent, v) for ent, v in attivi if len(v.get("percorso", [])) == min_step]
    pronti = [(ent, v) for ent, v in in_gioco_questo_passo if "scelta_pendente" in v]

    tot_attesi = len(in_gioco_questo_passo)
    tot_pronti = len(pronti)

    if tot_attesi > 0 and (tot_pronti >= tot_attesi or (forzata and tot_pronti > 0)):
        for ent, v in pronti:
            _applica_scelta_in_coda(v, scenario_id=selected_id, postazione_id=ent, room_ref=room)
        return tot_pronti, tot_att
