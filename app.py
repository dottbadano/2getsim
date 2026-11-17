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


def get_case_label(case_id):
    """Restituisce solo il codice '001' ai discenti; aggiunge la descrizione clinica ai Master."""
    if role != "master":
        return case_id
    try:
        mod = importlib.import_module(f"{CASE_DIR}.{case_id}")
        desc = mod.CASO.get("descrizione_master") or mod.CASO.get("titolo", "")
        return f"{case_id} — {desc}" if desc else case_id
    except Exception:
        return case_id


def _calcola_costo_opzione(opt):
    """Restituisce il costo esplicito dell'opzione oppure lo stima dai delta clinici/colore."""
    if "costo" in opt:
        return int(opt["costo"])
    colore = opt.get("colore")
    if colore == "verde":
        return 1200
    if colore == "blu":
        return 3500
    if colore == "giallo":
        return 8500
    if colore == "rosso":
        return 14000
    # Fallback automatico per file scritti senza campo 'colore'
    do, dv, dq = opt.get("d_onc", 0), opt.get("d_vit", 0), opt.get("d_qol", 0)
    if do > 0 and dv >= 0:
        return 1200
    if dq <= -20 and do >= -15:
        return 8500
    if dv <= -15 or do <= -25:
        return 14000
    return 3500


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
        selected_id = st.selectbox("Seleziona Scenario", cases, index=idx, format_func=get_case_label)
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
        "spesa_ssn": caso.get("spesa_iniziale", 0),
        "percorso": [],
        "ordine_opzioni": {},
        "consultazioni_anamnesi": 0,
    }
state = room["stati_casi"][chiave]

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
    st.markdown("### 📊 Stato Paziente & Risorse")
    m1, m2 = st.columns(2)
    m1.metric("❤️ Vitalità", f"{max(0, min(100, state['vitalita']))}%")
    m2.metric("🎯 Controllo Onc.", f"{max(0, min(100, state['oncologico']))}%")

    m3, m4 = st.columns(2)
    m3.metric("🌿 Qualità di Vita", f"{max(0, min(100, state['qol']))}%")
    spesa_fmt = f"{state.get('spesa_ssn', 0):,}".replace(",", ".") + " €"
    m4.metric("💶 Spesa SSN", spesa_fmt)

    if 30 <= state["qol"] < 40:
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
                    spesa_k = f"{v.get('spesa_ssn', 0):,}".replace(",", ".") + " €"
                    st.caption(
                        f"• **{k[len(pref):]}** → `{v['current_node']}` | V:{v['vitalita']}% O:{v['oncologico']}% Q:{v['qol']}% | 💶 {spesa_k} | Anamn: {cons}x"
                    )

with col_r:
    nid = state["current_node"]

    # 1. Controllo automatico Exitus se Vitalità <= 0
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

    # 2. Controllo automatico Progressione Incontrollata se Controllo Oncologico <= 0
    elif state["oncologico"] <= 0 and nid not in caso["esiti"]:
        esito_prog = caso["esiti"].get(
            "esito_progressione",
            {
                "tipo": "rosso",
                "titolo": "📉 PROGRESSIONE INCONTROLLATA — CONTROLLO ONCOLOGICO A 0%",
                "sottotitolo": '"La finestra di curabilità si è chiusa."',
                "descrizione": "I ritardi diagnostici o le terapie sottodosate rispetto alla biologia del tumore hanno portato a diffusione viscerale estesa non più suscettibile di terapie attive.",
            },
        )
        st.markdown(render_box_esito(esito_prog), unsafe_allow_html=True)
        for idx, step in enumerate(state["percorso"], 1):
            st.markdown(f"**{idx}. {step['nodo']}** → `{step['scelta']}`")
        if st.button("🔄 Ripeti Simulazione", use_container_width=True):
            del room["stati_casi"][chiave]
            st.session_state[anamnesi_open_key] = False
            st.rerun()

    # 3. Controllo automatico Drop-out / Rifiuto delle cure se QoL < 30%
    elif state["qol"] < 30 and nid not in caso["esiti"]:
        esito_dropout = caso["esiti"].get(
            "esito_dropout",
            {
                "tipo": "rosso",
                "titolo": "🛑 RIFIUTO DELLE CURE — QoL SOTTO IL 30%",
                "sottotitolo": '"Dottore, non riesco più a tollerare questa terapia... piuttosto che andare avanti così, meglio smettere."',
                "descrizione": "Il paziente torna in ambulatorio esausto per il carico di tossicità, sintomi urinari invalidanti o manovre invasive accumulate e decide di interrompere ogni trattamento attivo. Una terapia oncologicamente efficace ma non sostenibile dal paziente è un fallimento clinico.",
            },
        )
        st.markdown(render_box_esito(esito_dropout), unsafe_allow_html=True)
        for idx, step in enumerate(state["percorso"], 1):
            st.markdown(f"**{idx}. {step['nodo']}** → `{step['scelta']}`")
        if st.button("🔄 Ripeti Simulazione", use_container_width=True):
            del room["stati_casi"][chiave]
            st.session_state[anamnesi_open_key] = False
            st.rerun()

    # 4. Snodo decisionale attivo
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
                state["spesa_ssn"] = state.get("spesa_ssn", 0) + _calcola_costo_opzione(opt)
                state["percorso"].append({"nodo": nodo["titolo"], "scelta": opt["testo"]})
                state["current_node"] = opt["next"]
                st.session_state[anamnesi_open_key] = False
                st.rerun()

    # 5. Esito finale raggiunto al termine del percorso
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
        st.info(f"💶 **Costo complessivo del percorso assistenziale per il SSN:** {spesa_fmt}")
        for idx, step in enumerate(state["percorso"], 1):
            st.markdown(f"**{idx}. {step['nodo']}** → `{step['scelta']}`")
        if st.button("🔄 Ripeti Simulazione", use_container_width=True):
            del room["stati_casi"][chiave]
            st.session_state[anamnesi_open_key] = False
            st.rerun()
