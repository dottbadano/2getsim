import importlib
import os
import streamlit as st
from case_builder import render_case_builder
from font import apply_fonts
from security import render_regia_master, risolvi_identita_gioco, verifica_accesso
from text import render_box_esito, render_header_caso

st.set_page_config(page_title="2getSIM", page_icon="⚡", layout="wide")
apply_fonts()

room, role, uid = verifica_accesso()
bucket, etichetta = risolvi_identita_gioco(room, role, uid)

CASE_DIR = "casi_clinici"
os.makedirs(CASE_DIR, exist_ok=True)
cases = sorted([f[:-3] for f in os.listdir(CASE_DIR) if f.endswith(".py") and f != "__init__"])

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
        vista_master = st.radio("Vista Docente:", ["🎮 Simulazione Aula", "✍️ Crea Caso Clinico"])
        st.divider()

    if cases:
        idx = cases.index(room["caso_attivo_globale"]) if room["caso_attivo_globale"] in cases else 0
        selected_id = st.selectbox("Caso Clinico", cases, index=idx, format_func=lambda x: f"Caso {x}")
    else:
        selected_id = None

    if role == "master" and selected_id:
        render_regia_master(room, selected_id)

# Se il Master ha scelto l'Editor Visuale, mostra case_builder.py
if role == "master" and vista_master == "✍️ Crea Caso Clinico":
    render_case_builder(CASE_DIR)
    st.stop()

if not selected_id:
    st.error("Inserisci almeno un file nella cartella 'casi_clinici/' (es. 001.py) oppure crealo da 'Crea Caso Clinico'.")
    st.stop()

mod = importlib.import_module(f"{CASE_DIR}.{selected_id}")
importlib.reload(mod)
caso = mod.CASO

chiave = f"{selected_id}__{bucket}"
if chiave not in room["stati_casi"]:
    room["stati_casi"][chiave] = {
        "current_node": caso["nodo_iniziale"],
        "vitalita": caso.get("vitalita_iniziale", 100),
        "oncologico": caso.get("oncologico_iniziale", 100),
        "qol": caso.get("qol_iniziale", 75),
        "percorso": [],
    }
state = room["stati_casi"][chiave]

st.markdown(render_header_caso(caso, selected_id, etichetta), unsafe_allow_html=True)
col_l, col_r = st.columns([1, 1.8], gap="large")

with col_l:
    st.markdown("### 📋 Cartella Paziente")
    st.info(caso["scheda_paziente"])
    m1, m2, m3 = st.columns(3)
    m1.metric("Vitalità", f"{max(0, min(100, state['vitalita']))}%")
    m2.metric("Controllo Onc.", f"{max(0, min(100, state['oncologico']))}%")
    m3.metric("Qualità di Vita", f"{max(0, min(100, state['qol']))}%")

    if role == "master":
        with st.expander("📡 Monitor Live & Debug", expanded=True):
            nodi = list(caso["nodi"].keys()) + list(caso["esiti"].keys())
            salto = st.selectbox("Salta nodo:", nodi, index=nodi.index(state["current_node"]))
            if st.button("Vai al nodo", use_container_width=True):
                state["current_node"] = salto
                st.rerun()
            pref = f"{selected_id}__"
            for k, v in room["stati_casi"].items():
                if k.startswith(pref):
                    st.caption(f"• **{k[len(pref):]}** → `{v['current_node']}` (V:{v['vitalita']} O:{v['oncologico']} Q:{v['qol']})")

with col_r:
    nid = state["current_node"]
    if nid in caso["nodi"]:
        nodo = caso["nodi"][nid]
        st.markdown(f"### {nodo['titolo']}")
        st.write(nodo["testo"])
        if nodo.get("immagine") and os.path.exists(nodo["immagine"]):
            st.image(nodo["immagine"], use_container_width=True)

        with st.form(f"f_{chiave}_{nid}"):
            scelta = st.radio("Condotta clinica:", [o["testo"] for o in nodo["opzioni"]])
            if st.form_submit_button("Conferma Scelta ➡️", use_container_width=True):
                opt = next(o for o in nodo["opzioni"] if o["testo"] == scelta)
                state["vitalita"] += opt.get("d_vit", 0)
                state["oncologico"] += opt.get("d_onc", 0)
                state["qol"] += opt.get("d_qol", 0)
                state["percorso"].append({"nodo": nodo["titolo"], "scelta": opt["testo"]})
                state["current_node"] = opt["next"]
                st.rerun()

    elif nid in caso["esiti"]:
        st.markdown(render_box_esito(caso["esiti"][nid]), unsafe_allow_html=True)
        for idx, step in enumerate(state["percorso"], 1):
            st.markdown(f"**{idx}. {step['nodo']}** → `{step['scelta']}`")
        if st.button("🔄 Ripeti Caso", use_container_width=True):
            del room["stati_casi"][chiave]
            st.rerun()
