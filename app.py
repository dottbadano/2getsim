import importlib
import os
import random
import streamlit as st
from case_builder import render_case_builder
from font import apply_fonts
from security import render_regia_master, risolvi_identita_gioco, verifica_accesso
from text import render_box_esito

st.set_page_config(page_title="2getSIM", page_icon="⚡", layout="wide")
apply_fonts()

room, role, uid = verifica_accesso()
bucket, etichetta = risolvi_identita_gioco(room, role, uid)

CASE_DIR = "storycase"
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
        selected_id = st.selectbox("Seleziona Scenario", cases, index=idx, format_func=lambda x: f"Scenario {x}")
    else:
        selected_id = None

    if role == "master" and selected_id:
        render_regia_master(room, selected_id)

if role == "master" and vista_master == "✍️ Crea Caso Clinico":
    render_case_builder(CASE_DIR)
    st.stop()

if not selected_id:
    st.error("Inserisci almeno un file nella cartella 'storycase/' (es. 001.py) oppure crealo da 'Crea Caso Clinico'.")
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
        "ordine_opzioni": {},
        "consultazioni_anamnesi": 0,
    }
state = room["stati_casi"][chiave]

# Chiave locale per aprire/chiudere l'anamnesi sul singolo dispositivo
anamnesi_open_key = f"show_anamnesi_{chiave}"
if anamnesi_open_key not in st.session_state:
    st.session_state[anamnesi_open_key] = False

# Header pulito senza badge "Caso Clinico"
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

col_l, col_r = st.columns([1, 1.8], gap="large")

with col_l:
    st.markdown("### 📊 Stato Paziente")
    m1, m2, m3 = st.columns(3)
    m1.metric("Vitalità", f"{max(0, min(100, state['vitalita']))}%")
    m2.metric("Controllo Onc.", f"{max(0, min(100, state['oncologico']))}%")
    m3.metric("Qualità di Vita", f"{max(0, min(100, state['qol']))}%")

    st.divider()

    # Alla prima schermata (0 scelte fatte) l'anamnesi è aperta; dopo la prima scelta sparisce
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
        with st.expander("📡 Monitor Live & Debug", expanded=True):
            nodi = list(caso["nodi"].keys()) + list(caso["esiti"].keys())
            salto = st.selectbox("Salta nodo:", nodi, index=nodi.index(state["current_node"]) if state["current_node"] in nodi else 0)
            if st.button("Vai al nodo", use_container_width=True):
                state["current_node"] = salto
                st.session_state[anamnesi_open_key] = False
                st.rerun()
            pref = f"{selected_id}__"
            for k, v in room["stati_casi"].items():
                if k.startswith(pref):
                    cons = v.get("consultazioni_anamnesi", 0)
                    st.caption(
                        f"• **{k[len(pref):]}** → `{v['current_node']}` | V:{v['vitalita']}% O:{v['oncologico']}% Q:{v['qol']}% | Anamnesi aperta: {cons}x"
                    )

with col_r:
    nid = state["current_node"]

    # Controllo automatico exitus clinico se Vitalità <= 0 in qualsiasi punto
    if state["vitalita"] <= 0 and nid not in caso["esiti"]:
        esito_morte = caso["esiti"].get(
            "esito_exitus",
            {
                "tipo": "rosso",
                "titolo": "💀 EXITUS CLINICO — VITALITÀ A 0%",
                "sottotitolo": '"La somma delle complicanze non ha lasciato margine."',
                "descrizione": "Le scelte cliniche accumulate hanno portato a tossicità fatale o progressione sistemica irreversibile prima di completare il percorso terapeutico.",
            },
        )
        st.markdown(render_box_esito(esito_morte), unsafe_allow_html=True)
        for idx, step in enumerate(state["percorso"], 1):
            st.markdown(f"**{idx}. {step['nodo']}** → `{step['scelta']}`")
        if st.button("🔄 Ripeti Simulazione", use_container_width=True):
            del room["stati_casi"][chiave]
            st.session_state[anamnesi_open_key] = False
            st.rerun()

    elif nid in caso["nodi"]:
        nodo = caso["nodi"][nid]
        st.markdown(f"### {nodo['titolo']}")
        st.write(nodo["testo"])
        if nodo.get("immagine") and os.path.exists(nodo["immagine"]):
            st.image(nodo["immagine"], use_container_width=True)

        if nid not in state["ordine_opzioni"]:
            indici = list(range(len(nodo["opzioni"])))
            random.shuffle(indici)
            state["ordine_opzioni"][nid] = indici

        opzioni_ordinate = [nodo["opzioni"][i] for i in state["ordine_opzioni"][nid]]

        with st.form(f"f_{chiave}_{nid}"):
            scelta = st.radio("Condotta clinica:", [o["testo"] for o in opzioni_ordinate])
            if st.form_submit_button("Conferma Scelta ➡️", use_container_width=True):
                opt = next(o for o in opzioni_ordinate if o["testo"] == scelta)
                state["vitalita"] = max(0, min(100, state["vitalita"] + opt.get("d_vit", 0)))
                state["oncologico"] = max(0, min(100, state["oncologico"] + opt.get("d_onc", 0)))
                state["qol"] = max(0, min(100, state["qol"] + opt.get("d_qol", 0)))
                state["percorso"].append({"nodo": nodo["titolo"], "scelta": opt["testo"]})
                state["current_node"] = opt["next"]
                # Richiude automaticamente l'anamnesi al passaggio allo snodo successivo
                st.session_state[anamnesi_open_key] = False
                st.rerun()

    elif nid in caso["esiti"]:
        esito = dict(caso["esiti"][nid])
        if esito.get("tipo") == "bianco" and (state["qol"] < 55 or state["oncologico"] < 65 or state["vitalita"] < 60):
            esito = {
                "tipo": "giallo",
                "titolo": "⚠️ CONTROLLO ONCOLOGICO CON SEQUELE GRAVI",
                "sottotitolo": '"Hai indovinato la mossa finale, ma il paziente paga gli errori precedenti."',
                "descrizione": esito["descrizione"] + " Tuttavia, le scelte subottimali nelle fasi iniziali hanno lasciato sequele permanenti sulla qualità di vita o sul controllo di malattia.",
            }

        st.markdown(render_box_esito(esito), unsafe_allow_html=True)
        for idx, step in enumerate(state["percorso"], 1):
            st.markdown(f"**{idx}. {step['nodo']}** → `{step['scelta']}`")
        if st.button("🔄 Ripeti Simulazione", use_container_width=True):
            del room["stati_casi"][chiave]
            st.session_state[anamnesi_open_key] = False
            st.rerun()
