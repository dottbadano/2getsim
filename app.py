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
        return tot_pronti, tot_attesi, True

    return tot_pronti, tot_attesi, False


def _colore_barra(valore):
    if valore >= 65:
        return "#16a34a"
    if valore >= 35:
        return "#d97706"
    return "#dc2626"


def _render_quadro_conclusivo_sobrio(state, stato_clinico_label, nota_clinica, chiave, anamnesi_open_key, room):
    vit = max(0, min(100, state.get("vitalita", 0)))
    onc = max(0, min(100, state.get("oncologico", 0)))
    qol = max(0, min(100, state.get("qol", 0)))

    st.markdown(
        f"""
        <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.2rem;">
            <div style="font-size: 0.8rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #475569;">
                Quadro Clinico Conclusivo
            </div>
            <h3 style="margin: 0.25rem 0 0.5rem 0; color: #0f172a; font-size: 1.35rem;">{stato_clinico_label}</h3>
            <p style="margin: 0 0 1.25rem 0; color: #334155; font-size: 0.96rem; line-height: 1.5;">{nota_clinica}</p>
            <div style="margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
                    <span>❤️ Vitalità</span>
                    <span>{vit}%</span>
                </div>
                <div style="background: #e2e8f0; border-radius: 8px; height: 18px; width: 100%; overflow: hidden;">
                    <div style="background: {_colore_barra(vit)}; height: 100%; width: {vit}%; transition: width 0.4s;"></div>
                </div>
            </div>
            <div style="margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
                    <span>🎯 Controllo Oncologico</span>
                    <span>{onc}%</span>
                </div>
                <div style="background: #e2e8f0; border-radius: 8px; height: 18px; width: 100%; overflow: hidden;">
                    <div style="background: {_colore_barra(onc)}; height: 100%; width: {onc}%; transition: width 0.4s;"></div>
                </div>
            </div>
            <div style="margin-bottom: 1.1rem;">
                <div style="display: flex; justify-content: space-between; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
                    <span>🌿 Qualità di Vita (QoL)</span>
                    <span>{qol}%</span>
                </div>
                <div style="background: #e2e8f0; border-radius: 8px; height: 18px; width: 100%; overflow: hidden;">
                    <div style="background: {_colore_barra(qol)}; height: 100%; width: {qol}%; transition: width 0.4s;"></div>
                </div>
            </div>
            <div style="border-top: 1px solid #cbd5e1; padding-top: 0.85rem; color: #1e293b; font-size: 0.95rem;">
                <span>📋 <strong>Consultazioni anamnesi:</strong> {state.get('consultazioni_anamnesi', 0)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    badge_col = {"verde": "🟢", "giallo": "🟡", "blu": "🔵", "rosso": "🔴"}
    with st.expander("🗂️ Riepilogo decisioni e razionale clinico EAU/ESMO", expanded=True):
        percorso_svolto = state.get("percorso", [])
        for i in range(len(percorso_svolto)):
            step = percorso_svolto[i]
            icona = badge_col.get(step.get("colore", ""), "⚪")
            st.markdown(f"**{i + 1}. {step['nodo']}** — {icona} `{step['scelta']}`")
            if step.get("razionale"):
                st.caption(f"💡 *Razionale:* {step['razionale']}")

    if st.button("🔄 Ripeti Simulazione", use_container_width=True):
        room.get("stati_casi", {}).pop(chiave, None)
        st.session_state[anamnesi_open_key] = False
        st.rerun()


with st.sidebar:
    st.markdown(f"### 👤 **{etichetta}**")
    c1, c2 = st.columns(2)
    if c1.button("🔄 Aggiorna", use_container_width=True):
        st.rerun()
    if c2.button("Esci", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

    st.divider()
    vista_master = "🎮 Simulazione Aula"
    if role == "master":
        vista_master = st.radio(
            "Vista Docente:",
            ["🎮 Simulazione Aula", "🧠 Osservatorio Errori & Gruppi", "✍️ Crea Caso Clinico"],
        )
        st.divider()

    caso_attivo = room.get("caso_attivo_globale")
    if cases:
        idx = cases.index(caso_attivo) if caso_attivo in cases else 0
        selected_id = st.selectbox("Seleziona Scenario", cases, index=idx, format_func=get_case_label)
    else:
        selected_id = None

    if role == "master" and selected_id:
        render_regia_master(room, selected_id)

if role == "master" and vista_master == "✍️ Crea Caso Clinico":
    render_case_builder(CASE_DIR)
    st.stop()

if role == "master" and vista_master == "🧠 Osservatorio Errori & Gruppi":
    render_osservatorio_master(room, role)
    st.stop()

if not selected_id:
    st.error("Inserisci almeno un file nella cartella 'storycase/' (es. 001.py) oppure crealo da 'Crea Caso Clinico'.")
    st.stop()

mod = importlib.import_module(f"{CASE_DIR}.{selected_id}")
importlib.reload(mod)
caso = mod.CASO

stati_casi = room.setdefault("stati_casi", {})
chiave = f"{selected_id}__{bucket}"
if chiave not in stati_casi:
    stati_casi[chiave] = {
        "etichetta": etichetta,
        "current_node": caso["nodo_iniziale"],
        "vitalita": caso.get("vitalita_iniziale", 100),
        "oncologico": caso.get("oncologico_iniziale", 100),
        "qol": caso.get("qol_iniziale", 75),
        "percorso": [],
        "ordine_opzioni": {},
        "consultazioni_anamnesi": 0,
    }

state = stati_casi[chiave]
n_pronti, n_attesi, sbloccato = _sincronizza_barriera_aula(room, selected_id, caso, forzata=False)
if sbloccato:
    st.rerun()

anamnesi_open_key = f"show_anamnesi_{chiave}"
if anamnesi_open_key not in st.session_state:
    st.session_state[anamnesi_open_key] = False

st.markdown(
    f"""
    <div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 1.4rem; border-radius: 12px; color: white; margin-bottom: 1.5rem;">
        <span style="background: #334155; padding: 4px 10px; border-radius: 6px; font-size: 0.8rem;">Postazione: {etichetta}</span>
        <h2 style="margin: 0.5rem 0 0.2rem 0; font-size: 1.45rem;">{caso['titolo']}</h2>
        <p style="margin: 0; color: #94a3b8; font-size: 0.95rem;">{caso.get('sottotitolo', '')}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_l, col_r = st.columns([1.15, 1.75], gap="large")

with col_l:
    st.markdown("### 📊 Parametri Paziente")
    vit_c = max(0, min(100, state["vitalita"]))
    onc_c = max(0, min(100, state["oncologico"]))
    qol_c = max(0, min(100, state["qol"]))

    m1, m2, m3 = st.columns(3)
    m1.metric("❤️ Vitalità", f"{vit_c}%")
    m2.metric("🎯 Controllo Onc.", f"{onc_c}%")
    m3.metric("🌿 Qualità di Vita", f"{qol_c}%")

    if 30 <= qol_c < 40 and not _is_terminato(state, caso):
        st.warning("⚠️ Qualità di Vita critica: il paziente fatica a tollerare il carico terapeutico.")

    st.divider()

    if len(state["percorso"]) == 0:
        st.markdown("### 📋 Cartella Paziente & Anamnesi")
        st.info(caso["scheda_paziente"])
    else:
        if not st.session_state[anam
