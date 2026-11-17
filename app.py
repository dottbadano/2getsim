import importlib
import os
import random
import time
import streamlit as st
from case_builder import render_case_builder
from font import apply_fonts
from security import render_regia_master, risolvi_identita_gioco, verifica_accesso
from valutazione import render_osservatorio_master

st.set_page_config(page_title="2getSIM", page_icon="⚡", layout="wide")
apply_fonts()

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


def _calcola_costo_opzione(opt):
    if "costo" in opt:
        return int(opt["costo"])
    return {"verde": 1200, "blu": 3500, "giallo": 8500, "rosso": 14000}[_deduci_colore_opzione(opt)]


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


def _applica_scelta_in_coda(stato_run):
    pending = stato_run.pop("scelta_pendente", None)
    if not pending:
        return
    opt = pending["opt"]
    col_scelta = _deduci_colore_opzione(opt)
    stato_run["vitalita"] = max(0, min(100, stato_run["vitalita"] + opt.get("d_vit", 0)))
    stato_run["oncologico"] = max(0, min(100, stato_run["oncologico"] + opt.get("d_onc", 0)))
    stato_run["qol"] = max(0, min(100, stato_run["qol"] + opt.get("d_qol", 0)))
    stato_run["spesa_ssn"] = stato_run.get("spesa_ssn", 0) + _calcola_costo_opzione(opt)
    stato_run["percorso"].append(
        {
            "nodo_id": pending["nodo_id"],
            "nodo": pending["nodo_titolo"],
            "scelta": opt["testo"],
            "colore": col_scelta,
            "anamnesi_aperta": pending["anamnesi_aperta"],
        }
    )
    stato_run["current_node"] = opt["next"]


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
            attivi.append(v)

    if not attivi:
        return 0, 0, False

    min_step = min(len(v.get("percorso", [])) for v in attivi)
    in_gioco_questo_passo = [v for v in attivi if len(v.get("percorso", [])) == min_step]
    pronti = [v for v in in_gioco_questo_passo if "scelta_pendente" in v]

    tot_attesi = len(in_gioco_questo_passo)
    tot_pronti = len(pronti)

    if tot_attesi > 0 and (tot_pronti >= tot_attesi or (forzata and tot_pronti > 0)):
        for v in pronti:
            _applica_scelta_in_coda(v)
        return tot_pronti, tot_attesi, True

    return tot_pronti, tot_attesi, False


def _colore_barra(valore):
    if valore >= 65:
        return "#16a34a"  # Verde clinico
    if valore >= 35:
        return "#d97706"  # Ambra
    return "#dc2626"      # Rosso critico


def _render_quadro_conclusivo_sobrio(state, stato_clinico_label, nota_clinica, chiave, anamnesi_open_key, room):
    """Mostra il quadro finale sobrio con le 3 barre cliniche in grande evidenza, spesa SSN e cronologia."""
    vit = max(0, min(100, state.get("vitalita", 0)))
    onc = max(0, min(100, state.get("oncologico", 0)))
    qol = max(0, min(100, state.get("qol", 0)))
    spesa_fmt = f"{state.get('spesa_ssn', 0):,}".replace(",", ".") + " €"

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

            <div style="border-top: 1px solid #cbd5e1; padding-top: 0.85rem; display: flex; justify-content: space-between; align-items: center; color: #1e293b; font-size: 0.95rem;">
                <span>💶 <strong>Impatto economico percorso (SSN):</strong> {spesa_fmt}</span>
                <span>📋 <strong>Consultazioni anamnesi:</strong> {state.get('consultazioni_anamnesi', 0)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("🗂️ Riepilogo decisioni prese lungo il percorso", expanded=True):
        for idx, step in enumerate(state["percorso"], 1):
            st.markdown(f"**{idx}. {step['nodo']}** → `{step['scelta']}`")

    if st.button("🔄 Ripeti Simulazione", use_container_width=True):
        del room["stati_casi"][chiave]
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

if role == "master" and vista_master == "🧠 Osservatorio Errori & Gruppi":
    render_osservatorio_master(room, role)
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

    m1, m2 = st.columns(2)
    m1.metric("❤️ Vitalità", f"{vit_c}%")
    m2.metric("🎯 Controllo Onc.", f"{onc_c}%")

    m3, m4 = st.columns(2)
    m3.metric("🌿 Qualità di Vita", f"{qol_c}%")
    spesa_fmt = f"{state.get('spesa_ssn', 0):,}".replace(",", ".") + " €"
    m4.metric("💶 Spesa SSN", spesa_fmt)

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
        with st.expander("📡 Monitor Live & Sincronizzazione Aula", expanded=True):
            st.markdown(f"**Stato votazione snodo corrente:** `{n_pronti} / {n_attesi}` pronti")
            if n_attesi > 0:
                st.progress(min(1.0, n_pronti / n_attesi))
            if st.button("⏭️ Forza Avanzamento Ora (ignora assenti)", use_container_width=True):
                _sincronizza_barriera_aula(room, selected_id, caso, forzata=True)
                st.rerun()

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
                    spesa_k = f"{v.get('spesa_ssn', 0):,}".replace(",", ".") + " €"
                    stato_voto = "⏳ Pronta" if "scelta_pendente" in v else "✍️ Vota"
                    st.caption(
                        f"• **{k[len(pref):]}** [{stato_voto}] → `{v['current_node']}` | V:{v['vitalita']}% O:{v['oncologico']}% Q:{v['qol']}% | 💶 {spesa_k} | Anamn: {cons}x"
                    )

with col_r:
    nid = state["current_node"]

    # 1. Exitus Vitalità <= 0
    if state["vitalita"] <= 0 and nid not in caso["esiti"]:
        _render_quadro_conclusivo_sobrio(
            state,
            "Exitus clinico (Vitalità 0%)",
            "La somma delle tossicità o delle complicanze cliniche ha compromesso irreversibilmente la sopravvivenza del paziente prima del completamento del percorso.",
            chiave,
            anamnesi_open_key,
            room,
        )

    # 2. Progressione Incontrollata Controllo Oncologico <= 0
    elif state["oncologico"] <= 0 and nid not in caso["esiti"]:
        _render_quadro_conclusivo_sobrio(
            state,
            "Progressione oncologica incontrollata (Controllo Oncologico 0%)",
            "I ritardi diagnostici o le scelte terapeutiche non adeguate alla biologia della malattia hanno chiuso la finestra di curabilità, portando a progressione sistemica estesa.",
            chiave,
            anamnesi_open_key,
            room,
        )

    # 3. Drop-out / Rifiuto cure QoL < 30%
    elif state["qol"] < 30 and nid not in caso["esiti"]:
        _render_quadro_conclusivo_sobrio(
            state,
            "Interruzione volontaria delle cure (QoL < 30%)",
            "Il paziente si presenta in ambulatorio riferendo di non riuscire più a tollerare il carico terapeutico e sceglie di sospendere ogni trattamento attivo.",
            chiave,
            anamnesi_open_key,
            room,
        )

    # 4. Snodo decisionale attivo
    elif nid in caso["nodi"]:
        nodo = caso["nodi"][nid]
        st.markdown(f"### {nodo['titolo']}")
        st.write(nodo["testo"])
        if nodo.get("immagine") and os.path.exists(nodo["immagine"]):
            st.image(nodo["immagine"], use_container_width=True)

        if "scelta_pendente" in state and role != "master":
            scelta_reg = state["scelta_pendente"]["opt"]["testo"]
            st.success(f"✅ **Scelta registrata:** _{scelta_reg}_")
            st.info(
                f"⏳ **In attesa degli altri collegati ({n_pronti} su {n_attesi} hanno confermato).** "
                "Lo snodo successivo partirà automaticamente per tutti non appena l'ultimo partecipante avrà premuto Conferma."
            )
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
                    if role == "master":
                        state["scelta_pendente"] = {
                            "nodo_id": nid,
                            "nodo_titolo": nodo["titolo"],
                            "opt": opt,
                            "anamnesi_aperta": st.session_state[anamnesi_open_key],
                        }
                        _applica_scelta_in_coda(state)
                    else:
                        state["scelta_pendente"] = {
                            "nodo_id": nid,
                            "nodo_titolo": nodo["titolo"],
                            "opt": opt,
                            "anamnesi_aperta": st.session_state[anamnesi_open_key],
                        }
                        _sincronizza_barriera_aula(room, selected_id, caso, forzata=False)
                    st.session_state[anamnesi_open_key] = False
                    st.rerun()

    # 5. Esito finale raggiunto al termine del percorso
    elif nid in caso["esiti"]:
        esito = dict(caso["esiti"][nid])
        _render_quadro_conclusivo_sobrio(
            state,
            "Percorso clinico completato",
            esito.get("descrizione", "Valuta i parametri clinici finali raggiunti dal paziente."),
            chiave,
            anamnesi_open_key,
            room,
        )
