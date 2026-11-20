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
        .block-container {padding-top: 1.2rem !important; padding-bottom: 1.5rem !important;}
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
    return nid in caso_dict.get("esiti", {}) or stato_run.get("vitalita", 100) <= 0 or stato_run.get("oncologico", 100) <= 0 or stato_run.get("qol", 75) < 30


def _applica_scelta_in_coda(stato_run, scenario_id="", postazione_id="", room_ref=None):
    pending = stato_run.pop("scelta_pendente", None)
    if not pending:
        return
    opt = pending["opt"]
    col_scelta = _deduci_colore_opzione(opt)
    stato_run["vitalita"] = max(0, min(100, stato_run["vitalita"] + opt.get("d_vit", 0)))
    stato_run["oncologico"] = max(0, min(100, stato_run["oncologico"] + opt.get("d_onc", 0)))
    stato_run["qol"] = max(0, min(100, stato_run["qol"] + opt.get("d_qol", 0)))
    stato_run["percorso"].append({
        "nodo_id": pending["nodo_id"],
        "nodo": pending["nodo_titolo"],
        "scelta": opt["testo"],
        "colore": col_scelta,
        "razionale": opt.get("razionale", ""),
        "anamnesi_aperta": pending["anamnesi_aperta"],
    })
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
                modalita=str(r_ref.get("modalita_attiva", "Aula")),
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
    in_gioco = [(ent, v) for ent, v in attivi if len(v.get("percorso", [])) == min_step]
    pronti = [(ent, v) for ent, v in in_gioco if "scelta_pendente" in v]
    if len(in_gioco) > 0 and (len(pronti) >= len(in_gioco) or (forzata and len(pronti) > 0)):
        for ent, v in pronti:
            _applica_scelta_in_coda(v, scenario_id=selected_id, postazione_id=ent, room_ref=room)
        return len(pronti), len(in_gioco), True
    return len(pronti), len(in_gioco), False


def _colore_barra(valore):
    return "#16a34a" if valore >= 65 else ("#d97706" if valore >= 35 else "#dc2626")


def _barra_html(etichetta_bar, valore):
    col = _colore_barra(valore)
    return (
        f'<div style="margin-bottom:0.9rem;">'
        f'<div style="display:flex;justify-content:space-between;font-weight:700;color:#0f172a;margin-bottom:4px;"><span>{etichetta_bar}</span><span>{valore}%</span></div>'
        f'<div style="background:#e2e8f0;border-radius:8px;height:16px;width:100%;overflow:hidden;"><div style="background:{col};height:100%;width:{valore}%;"></div></div>'
        f'</div>'
    )


def _render_quadro_conclusivo_sobrio(state, label, nota, chiave, anamnesi_open_key, room):
    vit, onc, qol = [max(0, min(100, state.get(k, 0))) for k in ("vitalita", "oncologico", "qol")]
    barre = _barra_html("❤️ Vitalità", vit) + _barra_html("🎯 Controllo Oncologico", onc) + _barra_html("🌿 Qualità di Vita (QoL)", qol)
    st.markdown(
        f"""
        <div style="background:#f8fafc; border:1px solid #cbd5e1; border-radius:12px; padding:1.5rem; margin-bottom:1.2rem;">
            <div style="font-size:0.8rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:#475569;">Quadro Clinico Conclusivo</div>
            <h3 style="margin:0.25rem 0 0.5rem 0; color:#0f172a; font-size:1.35rem;">{label}</h3>
            <p style="margin:0 0 1.2rem 0; color:#334155; font-size:0.96rem; line-height:1.5;">{nota}</p>
            {barre}
            <div style="border-top:1px solid #cbd5e1; padding-top:0.8rem; color:#1e293b; font-size:0.95rem;">📋 <strong>Consultazioni anamnesi:</strong> {state.get('consultazioni_anamnesi', 0)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    badge = {"verde": "🟢", "giallo": "🟡", "blu": "🔵", "rosso": "🔴"}
    with st.expander("🗂️ Riepilogo decisioni prese lungo il percorso", expanded=True):
        for idx, step in enumerate(state["percorso"], 1):
            dot = badge.get(step.get("colore", ""), "⚪")
            st.markdown(f"**{idx}. {step['nodo']}** — {dot} `{step['scelta']}`")
            if step.get("razionale"):
                st.caption(f"💡 {step['razionale']}")
    if st.button("🔄 Ripeti Simulazione", use_container_width=True):
        room["stati_casi"].pop(chiave, None)
        st.session_state[anamnesi_open_key] = False
        st.rerun()


# --- BARRA SUPERIORE DI CONTROLLO (SEMPRE VISIBILE ANCHE SU GOOGLE SITES) ---
if role == "master":
    if "master_mode" not in st.session_state:
        st.session_state["master_mode"] = "simulazione"

    b1, b2, b3, b4 = st.columns([1.4, 1.4, 1.4, 0.8])
    if b1.button("🎮 Vai a Simulazione", type="primary" if st.session_state["master_mode"] == "simulazione" else "secondary", use_container_width=True):
        st.session_state["master_mode"] = "simulazione"
        st.rerun()
    if b2.button("✍️ Crea Caso Clinico", type="primary" if st.session_state["master_mode"] == "crea_caso" else "secondary", use_container_width=True):
        st.session_state["master_mode"] = "crea_caso"
        st.rerun()
    if b3.button("🧠 Osservatorio & Debriefing", type="primary" if st.session_state["master_mode"] == "osservatorio" else "secondary", use_container_width=True):
        st.session_state["master_mode"] = "osservatorio"
        st.rerun()
    if b4.button("🚪 Esci", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

    st.divider()

    if st.session_state["master_mode"] == "crea_caso":
        render_case_builder(CASE_DIR)
        st.stop()
    if st.session_state["master_mode"] == "osservatorio":
        render_osservatorio_master(room, role)
        st.stop()
else:
    top_u1, top_u2, top_u3 = st.columns([3, 1, 1])
    top_u1.markdown(f"👤 **{etichetta}**")
    if top_u2.button("🔄 Aggiorna", use_container_width=True):
        st.rerun()
    if top_u3.button("🚪 Esci", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

if not cases:
    st.error("Nessuno scenario trovato in 'storycase/'. Clicca su '✍️ Crea Caso Clinico' in alto.")
    st.stop()

if role == "master":
    idx = cases.index(room["caso_attivo_globale"]) if room["caso_attivo_globale"] in cases else 0
    selected_id = st.selectbox("📂 Scenario selezionato:", cases, index=idx, format_func=get_case_label)
    with st.expander("🎛️ Regia Aula: Squadre, Gioco Singolo & Accessi", expanded=True):
        render_regia_master(room, selected_id)
else:
    selected_id = room["caso_attivo_globale"] if room["caso_attivo_globale"] in cases else cases[0]

mod = importlib.import_module(f"{CASE_DIR}.{selected_id}")
importlib.reload(mod)
caso = mod.CASO
chiave = f"{selected_id}__{bucket}"
if chiave not in room["stati_casi"]:
    room["stati_casi"][chiave] = {
        "etichetta": etichetta,
        "current_node": caso["nodo_iniziale"],
        "vitalita": caso.get("vitalita_iniziale", 100),
        "oncologico": caso.get("oncologico_iniziale", 100),
        "qol": caso.get("qol_iniziale", 75),
        "percorso": [],
        "ordine_opzioni": {},
        "consultazioni_anamnesi": 0,
    }
state = room["stati_casi"][chiave]
n_pronti, n_attesi, sbloccato = _sincronizza_barriera_aula(room, selected_id, caso, forzata=False)
if sbloccato:
    st.rerun()

anamnesi_open_key = f"show_anamnesi_{chiave}"
if anamnesi_open_key not in st.session_state:
    st.session_state[anamnesi_open_key] = False

st.markdown(
    f"""
    <div style="background:linear-gradient(135deg,#1e293b,#0f172a); padding:1.3rem; border-radius:12px; color:white; margin-bottom:1.2rem;">
        <span style="background:#334155; padding:4px 10px; border-radius:6px; font-size:0.8rem;">Postazione: {etichetta}</span>
        <h2 style="margin:0.4rem 0 0.2rem 0; font-size:1.4rem;">{caso['titolo']}</h2>
        <p style="margin:0; color:#94a3b8; font-size:0.95rem;">{caso.get('sottotitolo', '')}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_l, col_r = st.columns([1.15, 1.75], gap="large")
with col_l:
    st.markdown("### 📊 Parametri Paziente")
    vit_c, onc_c, qol_c = [max(0, min(100, state[k])) for k in ("vitalita", "oncologico", "qol")]
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
        if not st.session_state[anamnesi_open_key]:
            if st.button("📋 Consulta Anamnesi", use_container_width=True):
                st.session_state[anamnesi_open_key] = True
                state["consultazioni_anamnesi"] = state.get("consultazioni_anamnesi", 0) + 1
                st.rerun()
        else:
            if st.button("🙈 Chiudi Anamnesi", use_container_width=True):
                st.session_state[anamnesi_open_key] = False
                st.rerun()
            st.info(caso["scheda_paziente"])
    if role == "master":
        with st.expander("📡 Monitor Live, Salto Nodo & Google Sheet", expanded=False):
            st.markdown(f"**Stato votazione snodo:** `{n_pronti} / {n_attesi}` pronti")
            if n_attesi > 0:
                st.progress(min(1.0, n_pronti / n_attesi))
            if st.button("⏭️ Forza Avanzamento Ora (ignora assenti)", use_container_width=True):
                _sincronizza_barriera_aula(room, selected_id, caso, forzata=True)
                st.rerun()
            st.divider()
            if GSHEETS_ATTIVO:
                if st.button("🧪 Testa scrittura su Google Sheet", use_container_width=True):
                    try:
                        registra_scelta(
                            edizione="TEST_CONNESSIONE", scenario=selected_id, postazione="REGIA_MASTER",
                            modalita="Test", membri=etichetta, passo=0, snodo_id="TEST",
                            scelta="Verifica connessione Google Sheet OK", colore="verde", anamnesi="No",
                            vitalita=100, controllo_onc=100, qol=75, spesa_ssn=0,
                        )
                        st.success("✅ Riga di prova scritta su Google Sheet!")
                    except Exception as err:
                        st.error(f"Errore scrittura Sheet: {err}")
            else:
                st.warning("⚠️ Modulo google_db.py non caricato nel repository.")
            if "ultimo_errore_gsheets" in st.session_state:
                st.caption(f"⚠️ Ultimo avviso Sheets: {st.session_state['ultimo_errore_gsheets']}")
            st.divider()
            nodi = list(caso["nodi"].keys()) + list(caso["esiti"].keys())
            salto = st.selectbox("Salta nodo (solo tua vista):", nodi, index=nodi.index(state["current_node"]) if state["current_node"] in nodi else 0)
            if st.button("Vai al nodo", use_container_width=True):
                state.pop("scelta_pendente", None)
                state["current_node"] = salto
                st.session_state[anamnesi_open_key] = False
                st.rerun()
            pref = f"{selected_id}__"
            for k, v in room["stati_casi"].items():
                if k.startswith(pref):
                    cons = v.get("consultazioni_anamnesi", 0)
                    stato_voto = "⏳ Pronta" if "scelta_pendente" in v else "✍️ Vota"
                    st.caption(f"• **{k[len(pref):]}** [{stato_voto}] → `{v['current_node']}` | V:{v['vitalita']}% O:{v['oncologico']}% Q:{v['qol']}% | Anamn: {cons}x")

with col_r:
    nid = state["current_node"]
    if state["vitalita"] <= 0 and nid not in caso["esiti"]:
        _render_quadro_conclusivo_sobrio(state, "Exitus clinico (Vitalità 0%)", "La somma delle tossicità o delle complicanze cliniche ha compromesso irreversibilmente la sopravvivenza del paziente.", chiave, anamnesi_open_key, room)
    elif state["oncologico"] <= 0 and nid not in caso["esiti"]:
        _render_quadro_conclusivo_sobrio(state, "Progressione oncologica incontrollata (0%)", "I ritardi diagnostici o le scelte non adeguate alla biologia della malattia hanno chiuso la finestra di curabilità.", chiave, anamnesi_open_key, room)
    elif state["qol"] < 30 and nid not in caso["esiti"]:
        _render_quadro_conclusivo_sobrio(state, "Interruzione volontaria delle cure (QoL < 30%)", "Il paziente riferisce di non riuscire più a tollerare il carico terapeutico e sospende ogni trattamento attivo.", chiave, anamnesi_open_key, room)
    elif nid in caso["nodi"]:
        nodo = caso["nodi"][nid]
        st.markdown(f"### {nodo['titolo']}")
        st.write(nodo["testo"])
        img_ref = nodo.get("immagine", "")
        if img_ref.startswith("drive:") and GSHEETS_ATTIVO:
            try:
                st.image(scarica_immagine_drive(img_ref), use_container_width=True)
            except Exception:
                st.warning("⚠️ Immagine radiologica non raggiungibile su Drive.")
        elif img_ref and os.path.exists(img_ref):
            st.image(img_ref, use_container_width=True)
        if "scelta_pendente" in state and role != "master":
            st.success(f"✅ **Scelta registrata:** _{state['scelta_pendente']['opt']['testo']}_")
            st.info(f"⏳ **In attesa degli altri collegati ({n_pronti} su {n_attesi} hanno confermato).** Lo snodo successivo partirà automaticamente per tutti.")
            if n_attesi > 0:
                st.progress(min(1.0, n_pronti / n_attesi))
            if st.button("✏️ Cambia risposta finché gli altri votano", use_container_width=True):
                state.pop("scelta_pendente", None)
                st.rerun()
            time.sleep(2.5)
            st.rerun()
        else:
            if nid not in state["ordine_opzioni"]:
                indici = list(range(len(nodo["opzioni"])))
                random.shuffle(indici)
                state["ordine_opzioni"][nid] = indici
            opzioni_ordinate = [nodo["opzioni"][i] for i in state["ordine_opzioni"][nid]]
            with st.form(f"f_{chiave}_{nid}"):
                scelta = st.radio("Condotta clinica:", [o["testo"] for o in opzioni_ordinate])
                if st.form_submit_button("Conferma Scelta ➡️", use_container_width=True):
                    opt = next(o for o in opzioni_ordinate if o["testo"] == scelta)
                    state["scelta_pendente"] = {
                        "nodo_id": nid,
                        "nodo_titolo": nodo["titolo"],
                        "opt": opt,
                        "anamnesi_aperta": st.session_state[anamnesi_open_key],
                    }
                    if role == "master":
                        _applica_scelta_in_coda(state, scenario_id=selected_id, postazione_id=bucket, room_ref=room)
                    else:
                        _sincronizza_barriera_aula(room, selected_id, caso, forzata=False)
                    st.session_state[anamnesi_open_key] = False
                    st.rerun()
    elif nid in caso["esiti"]:
        esito = dict(caso["esiti"][nid])
        _render_quadro_conclusivo_sobrio(state, esito.get("titolo", "Percorso clinico completato"), esito.get("descrizione", "Valuta i parametri clinici finali raggiunti dal paziente."), chiave, anamnesi_open_key, room)
