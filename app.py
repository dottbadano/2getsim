import json
import streamlit as st
from motore import (
    normalizza_json,
    valida_regole_peppiniello,
    salva_su_drive,
    caso_esempio_v2,
)

st.set_page_config(
    page_title="2getSIM Studio · Generatore & Sandbox",
    page_icon="❤️",
    layout="wide",
)


def clamp(val: int) -> int:
    return max(0, min(100, int(round(val))))


def stile_semaforo(val: int):
    if val >= 80:
        return "Ottimale", "#10b981", "rgba(16, 185, 129, 0.16)"
    if val >= 60:
        return "Discreto", "#0ea5e9", "rgba(14, 165, 233, 0.16)"
    if val >= 40:
        return "In Calo", "#f59e0b", "rgba(245, 158, 11, 0.16)"
    return "Critico", "#ef4444", "rgba(239, 68, 68, 0.24)"


def init_stato(caso: dict):
    p0 = caso.get("paziente_t0", {})
    st.session_state["caso_attivo"] = caso
    st.session_state["nodo_corrente"] = caso.get("nodo_iniziale", "snodo1")
    st.session_state["vitalita"] = int(p0.get("vitalita_iniziale", 80))
    st.session_state["oncologico"] = int(p0.get("oncologico_iniziale", 60))
    st.session_state["qol"] = int(p0.get("qol_iniziale", 75))
    st.session_state["coda_ritardati"] = []
    st.session_state["storico"] = []
    st.session_state["esito_key"] = None
    st.session_state["scelta_temp"] = None


if "caso_attivo" not in st.session_state:
    init_stato(caso_esempio_v2())

caso = st.session_state["caso_attivo"]

# --- SIDEBAR: IMPORTAZIONE, EXPORT & DRIVE ---
with st.sidebar:
    st.markdown("## 🔴 **2**getSIM Studio")
    st.caption("Validatore, Sandbox & Export per 2getSIM Enterprise")

    file_caricato = st.file_uploader("Carica file .json", type=["json"])
    if file_caricato is not None:
        raw_file = file_caricato.read().decode("utf-8", errors="ignore")
        parsed, err = normalizza_json(raw_file)
        if err:
            st.error(err)
        else:
            init_stato(parsed)
            st.success("JSON caricato e normalizzato.")

    with st.expander("Incolla JSON da Peppiniello / Gemini", expanded=False):
        raw_input = st.text_area("Incolla qui il JSON completo:", height=180)
        if st.button("Carica JSON incollato", use_container_width=True):
            parsed, err = normalizza_json(raw_input)
            if err:
                st.error(err)
            else:
                init_stato(parsed)
                st.success("Caso caricato con successo!")
                st.rerun()

    st.divider()
    json_pronto = json.dumps(caso, ensure_ascii=False, indent=2)
    nome_file = f"{caso.get('meta', {}).get('case_id', 'caso_2getsim')}.json"

    st.download_button(
        label="⬇️ Scarica JSON v2.0 (per 2getSIM)",
        data=json_pronto.encode("utf-8"),
        file_name=nome_file,
        mime="application/json",
        use_container_width=True,
        type="primary",
    )

    if st.button("☁️ Salva su Google Drive", use_container_width=True):
        ok, msg = salva_su_drive(caso, nome_file)
        if ok:
            st.success(msg)
        else:
            st.warning(msg)

    if st.button("🔄 Riavvia Simulazione da T0", use_container_width=True):
        init_stato(caso)
        st.rerun()

# --- MONITOR PARAMETRI (CUORE TACHICARDICO + SCUDO/QOL COLORATI SENZA BARRE) ---
vit = st.session_state["vitalita"]
onc = st.session_state["oncologico"]
qol = st.session_state["qol"]

vit_clamp = max(20, min(100, vit))
beat_sec = round(0.33 + ((vit_clamp - 20) / 80) * 1.67, 2)
stato_cuore = "TACHICARDIA" if vit <= 45 else "RITMO"

onc_nome, onc_hex, onc_bg = stile_semaforo(onc)
qol_nome, qol_hex, qol_bg = stile_semaforo(qol)

st.markdown(
    f"""
    <style>
    @keyframes cardiacPulse {{
        0%, 100% {{ transform: scale(1); filter: brightness(1); }}
        18% {{ transform: scale(1.34); filter: brightness(1.45); }}
        34% {{ transform: scale(1.06); filter: brightness(1.1); }}
        50% {{ transform: scale(1.24); filter: brightness(1.35); }}
        70% {{ transform: scale(1); filter: brightness(1); }}
    }}
    .monitor-bar {{
        background: #0A0A0A;
        color: #FFFFFF;
        border-radius: 16px;
        padding: 14px 22px;
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 16px;
        margin-bottom: 14px;
        border: 1px solid #262626;
    }}
    .metric-box {{
        display: flex;
        align-items: center;
        gap: 14px;
    }}
    .icon-badge {{
        width: 48px;
        height: 48px;
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        font-weight: bold;
    }}
    .heart-anim {{
        display: inline-block;
        animation: cardiacPulse {beat_sec}s infinite ease-in-out;
    }}
    </style>
    <div class="monitor-bar">
        <div class="metric-box">
            <div class="icon-badge" style="background: rgba(220,38,38,0.2); border: 2px solid #ef4444;">
                <span class="heart-anim">❤️</span>
            </div>
            <div>
                <div style="font-size: 11px; font-weight: 800; letter-spacing: 1px; color: #d4d4d4;">VITALITÀ</div>
                <div style="font-size: 12px; font-weight: 800; color: #f87171;">{stato_cuore}</div>
            </div>
        </div>
        <div class="metric-box">
            <div class="icon-badge" style="background: {onc_bg}; border: 2px solid {onc_hex};">
                <span>🛡️</span>
            </div>
            <div>
                <div style="font-size: 11px; font-weight: 800; letter-spacing: 1px; color: #d4d4d4;">ONCOLOGICO</div>
                <div style="font-size: 12px; font-weight: 800; color: {onc_hex};">{onc_nome.upper()}</div>
            </div>
        </div>
        <div class="metric-box">
            <div class="icon-badge" style="background: {qol_bg}; border: 2px solid {qol_hex};">
                <span>✨</span>
            </div>
            <div>
                <div style="font-size: 11px; font-weight: 800; letter-spacing: 1px; color: #d4d4d4;">QUALITÀ VITA</div>
                <div style="font-size: 12px; font-weight: 800; color: {qol_hex};">{qol_nome.upper()}</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- TABS PRINCIPALI ---
tab_sim, tab_val, tab_edit = st.tabs([
    "🎯 Simulatore Sandbox (Test Caso)",
    "✅ Controllo Regole Peppiniello",
    "✏️ Editor Rapido Snodi & T0",
])

with tab_sim:
    col_anamnesi, col_arena = st.columns([1.05, 1.95], gap="large")

    with col_anamnesi:
        st.markdown("### 📋 Anamnesi & Quadro T0")
        st.info(caso.get("paziente_t0", {}).get("scheda_paziente", ""))
        mostra_razionali = st.toggle("Mostra colori e razionali (Modalità Master)", value=False)
        if mostra_razionali:
            st.caption(f"Valori interni: Vitalità {vit}% · Oncologico {onc}% · QoL {qol}%")

    with col_arena:
        esito_key = st.session_state["esito_key"]
        nodo_id = st.session_state["nodo_corrente"]
        nodo = caso.get("nodi", {}).get(nodo_id)

        if not esito_key and nodo:
            passo_num = len(st.session_state["storico"]) + 1
            st.markdown(f"#### SNODO {passo_num} — {nodo.get('titolo', nodo_id)}")
            st.markdown(f"**{nodo.get('testo', '')}**")

            opzioni = nodo.get("opzioni", [])
            lettere = ["A", "B", "C", "D"]
            etichette = []
            for idx, op in enumerate(opzioni):
                lbl = f"{lettere[idx] if idx < 4 else idx+1}) {op.get('testo', '')}"
                if mostra_razionali:
                    lbl += f"  [{op.get('colore', '').upper()}]"
                etichette.append(lbl)

            scelta_idx = st.radio(
                "Seleziona la decisione clinica:",
                options=list(range(len(opzioni))),
                format_func=lambda i: etichette[i],
                index=None,
                key=f"radio_{nodo_id}_{passo_num}",
            )

            if scelta_idx is not None and mostra_razionali:
                st.caption(f"Razionale: {opzioni[scelta_idx].get('razionale', '')}")

            if st.button(
                "Conferma e Procedi ➡️",
                disabled=(scelta_idx is None),
                type="primary",
            ):
                opz = opzioni[scelta_idx]
                rit = bool(opz.get("effetto_ritardato", False))
                nuova_vit = vit + (0 if rit else int(opz.get("d_vit", 0)))
                nuovo_onc = onc + (0 if rit else int(opz.get("d_onc", 0)))
                nuova_qol = qol + (0 if rit else int(opz.get("d
