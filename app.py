import importlib
import os
import streamlit as st

st.set_page_config(
    page_title="2getSIM - Uro-Oncologia Clinica", page_icon="⚡", layout="wide"
)

# ---------------------------------------------------------------------------
# 1. STATO GLOBALE CONDIVISO TRA TUTTI GLI UTENTI CONNESSI (MASTER + 001..014)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_global_room():
    return {
        "modalita_attiva": "Singolo Discente",  # "Singolo Discente", "Arena 2 Squadre", "Coppie / Team"
        "caso_attivo_globale": None,
        # Configurazione Arena 2 Squadre
        "nome_squadra_a": "Squadra Urologi",
        "membri_squadra_a": ["001", "002", "003", "004", "005", "006"],
        "nome_squadra_b": "Squadra Oncologi",
        "membri_squadra_b": ["007", "008", "009", "010", "011", "012"],
        # Configurazione Coppie / Team (es. {"Ospedale A": ["001", "007"], ...})
        "coppie": {
            "Team 1 (Ospedale A)": ["001", "007"],
            "Team 2 (Ospedale B)": ["002", "008"],
            "Team 3 (Ospedale C)": ["003", "009"],
            "Team 4 (Ospedale D)": ["004", "010"],
            "Team 5 (Ospedale E)": ["005", "011"],
            "Team 6 (Ospedale F)": ["006", "012"],
            "Team 7 (Ospedale G)": ["013", "014"],
        },
        # Stati condivisi dei casi clinici indicizzati per (caso_id, chiave_sessione)
        "stati_casi": {},
    }


room = get_global_room()

# ---------------------------------------------------------------------------
# 2. AUTENTICAZIONE (3 MASTER + 14 DISCENTI 001..014)
# ---------------------------------------------------------------------------
MASTER_CREDENTIALS = {
    "gbadano": "211280",
    "acavo": "211186",
    "smigone": "090286",
}

DISCENTI_VALIDI = [f"{i:03d}" for i in range(1, 15)]  # 001 ... 014

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_role" not in st.session_state:
    st.session_state.user_role = None  # "master" | "discente"
if "user_id" not in st.session_state:
    st.session_state.user_id = None


def login_screen():
    st.markdown(
        """
        <div style="text-align: center; padding: 2rem 0;">
            <h1>⚡ 2getSIM — Accesso Sessione</h1>
            <p style="color: #666; font-size: 1.1rem;">Corso Residenziale Uro-Oncologico Multidisciplinare</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username_input = st.text_input(
                "Codice Utente / Username",
                placeholder="Discenti: 001 ... 014 | Docenti: gbadano, acavo, smigone",
            ).strip()
            password_input = st.text_input(
                "Password", type="password", placeholder="Password"
            ).strip()
            submit = st.form_submit_button(
                "Entra in Aula", use_container_width=True
            )

            if submit:
                if username_input in MASTER_CREDENTIALS:
                    if MASTER_CREDENTIALS[username_input] == password_input:
                        st.session_state.authenticated = True
                        st.session_state.user_role = "master"
                        st.session_state.user_id = username_input
                        st.rerun()
                    else:
                        st.error("Password Docente Master errata.")
                else:
                    codice_norm = username_input.zfill(3) if username_input.isdigit() else username_input
                    if codice_norm in DISCENTI_VALIDI:
                        if password_input == "12345678":
                            st.session_state.authenticated = True
                            st.session_state.user_role = "discente"
                            st.session_state.user_id = codice_norm
                            st.rerun()
                        else:
                            st.error("Password errata (Default discenti: 12345678).")
                    else:
                        st.error("Codice non valido. Usa 001-014 oppure le credenziali Master.")


if not st.session_state.authenticated:
    login_screen()
    st.stop()


# ---------------------------------------------------------------------------
# 3. FUNZIONE DI RISOLUZIONE DEL GRUPPO / SQUADRA PER L'UTENTE CONNESSO
# ---------------------------------------------------------------------------
def risolvi_identita_gioco(role, uid):
    modalita = room["modalita_attiva"]

    if role == "master":
        return f"master_{uid}", f"Control Room ({uid})"

    if modalita == "Singolo Discente":
        return f"singolo_{uid}", f"Discente {uid} (Individuale)"

    elif modalita == "Arena 2 Squadre":
        if uid in room["membri_squadra_a"]:
            return "arena_squadra_a", f"{room['nome_squadra_a']} (ID {uid})"
        elif uid in room["membri_squadra_b"]:
            return "arena_squadra_b", f"{room['nome_squadra_b']} (ID {uid})"
        else:
            return f"singolo_{uid}", f"Discente {uid} (Non assegnato a squadra)"

    elif modalita == "Coppie / Team":
        for nome_team, membri in room["coppie"].items():
            if uid in membri:
                chiave = f"team_{nome_team.lower().replace(' ', '_')}"
                return chiave, f"{nome_team} (ID {uid})"
        return f"singolo_{uid}", f"Discente {uid} (Non assegnato a coppia)"

    return f"singolo_{uid}", f"Discente {uid}"


session_bucket, etichetta_utente = risolvi_identita_gioco(
    st.session_state.user_role, st.session_state.user_id
)

# ---------------------------------------------------------------------------
# 4. CARICAMENTO CASI CLINICI DALLA CARTELLA 'casi_clinici/'
# ---------------------------------------------------------------------------
CASE_DIR = "casi_clinici"
if not os.path.exists(CASE_DIR):
    os.makedirs(CASE_DIR)
    st.warning(f"Cartella '{CASE_DIR}/' creata. Inserisci i file dei casi (es. 001.py).")
    st.stop()

case_files = sorted(
    [f[:-3] for f in os.listdir(CASE_DIR) if f.endswith(".py") and f != "__init__"]
)

if not case_files:
    st.error(f"Nessun caso clinico trovato in '{CASE_DIR}/'.")
    st.stop()

# ---------------------------------------------------------------------------
# 5. SIDEBAR & PANNELLO REGIA MASTER (ACCOPPIAMENTI E MODALITÀ)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### 👤 **{etichetta_utente}**")
    st.caption(f"Modalità Aula: **{room['modalita_attiva']}**")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 Aggiorna", use_container_width=True):
            st.rerun()
    with col_btn2:
        if st.button("Esci", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_role = None
            st.session_state.user_id = None
            st.rerun()

    st.divider()

    # Selettore Caso Clinico
    default_idx = 0
    if room["caso_attivo_globale"] in case_files:
        default_idx = case_files.index(room["caso_attivo_globale"])

    selected_case_id = st.selectbox(
        "Seleziona Caso Clinico",
        case_files,
        index=default_idx,
        format_func=lambda x: f"Caso {x}",
    )

    # PANNELLO DI CONFIGURAZIONE SQUADRE RISERVATO AI 3 MASTER
    if st.session_state.user_role == "master":
        st.divider()
        st.markdown("### 🎛️ Regia Master (Aula)")

        if st.button("📌 Imposta questo caso per tutta l'aula", use_container_width=True):
            room["caso_attivo_globale"] = selected_case_id
            st.success(f"Caso {selected_case_id} sincronizzato!")

        nuova_mod = st.radio(
            "Modalità di Lavoro Aula:",
            ["Singolo Discente", "Arena 2 Squadre", "Coppie / Team"],
            index=["Singolo Discente", "Arena 2 Squadre", "Coppie / Team"].index(
                room["modalita_attiva"]
            ),
        )
        if nuova_mod != room["modalita_attiva"]:
            room["modalita_attiva"] = nuova_mod
            st.rerun()

        # Configurazione Arena 2 Squadre
        if room["modalita_attiva"] == "Arena 2 Squadre":
            with st.expander("⚔️ Configura 2 Squadre Arena", expanded=True):
                room["nome_squadra_a"] = st.text_input(
                    "Nome Squadra A", value=room["nome_squadra_a"]
                )
                room["membri_squadra_a"] = st.multiselect(
                    "Partecipanti Squadra A",
                    DISCENTI_VALIDI,
                    default=[m for m in room["membri_squadra_a"] if m in DISCENTI_VALIDI],
                )
                room["nome_squadra_b"] = st.text_input(
                    "Nome Squadra B", value=room["nome_squadra_b"]
                )
                disponibili_b = [d for d in DISCENTI_VALIDI if d not in room["membri_squadra_a"]]
                room["membri_squadra_b"] = st.multiselect(
                    "Partecipanti Squadra B",
                    disponibili_b,
                    default=[m for m in room["membri_squadra_b"] if m in disponibili_b],
                )

        # Configurazione Coppie / Team Ospedalieri
        elif room["modalita_attiva"] == "Coppie / Team":
            with st.expander("🤝 Configura Coppie / Team", expanded=True):
                nomi_team = list(room["coppie"].keys())
                team_edit = st.selectbox("Seleziona Team da modificare", nomi_team)
                nuovo_nome_team = st.text_input("Rinomina Team", value=team_edit)
                membri_attuali = [m for m in room["coppie"][team_edit] if m in DISCENTI_VALIDI]
                nuovi_membri = st.multiselect(
                    "Membri del Team (codici 001-014)",
                    DISCENTI_VALIDI,
                    default=membri_attuali,
                )
                if st.button("Salva Team", use_container_width=True):
                    if nuovo_nome_team != team_edit:
                        del room["coppie"][team_edit]
                    room["coppie"][nuovo_nome_team] = nuovi_membri
                    st.success(f"Salvato {nuovo_nome_team}: {', '.join(nuovi_membri)}")
                    st.rerun()

                nuovo_gruppo = st.text_input("Oppure crea nuovo Team", placeholder="es. Ospedale San Martino")
                if st.button("➕ Aggiungi Team", use_container_width=True) and nuovo_gruppo.strip():
                    room["coppie"][nuovo_gruppo.strip()] = []
                    st.rerun()

# ---------------------------------------------------------------------------
# 6. CARICAMENTO MODULO CASO E STATO CONDIVISO DEL GRUPPO
# ---------------------------------------------------------------------------
try:
    module = importlib.import_module(f"{CASE_DIR}.{selected_case_id}")
    importlib.reload(module)
except Exception as e:
    st.error(f"Errore nel caricamento di '{selected_case_id}.py': {e}")
    st.stop()

caso = module.CASO
chiave_stato = f"{selected_case_id}__{session_bucket}"

if chiave_stato not in room["stati_casi"]:
    room["stati_casi"][chiave_stato] = {
        "current_node": caso["nodo_iniziale"],
        "vitalita": caso.get("vitalita_iniziale", 100),
        "oncologico": caso.get("oncologico_iniziale", 100),
        "qol": caso.get("qol_iniziale", 75),
        "percorso": [],
    }

state = room["stati_casi"][chiave_stato]

# Header Caso
st.markdown(
    f"""
    <div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 1.4rem; border-radius: 12px; color: white; margin-bottom: 1.5rem;">
        <span style="background: #3b82f6; padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: bold;">{caso.get('badge', f'CASO {selected_case_id}')}</span>
        <span style="background: #334155; padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; margin-left: 8px;">Postazione: {etichetta_utente}</span>
        <h2 style="margin: 0.5rem 0 0.2rem 0; font-size: 1.45rem;">{caso['titolo']}</h2>
        <p style="margin: 0; color: #94a3b8; font-size: 0.95rem;">{caso.get('sottotitolo', '')}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_left, col_right = st.columns([1, 1.8], gap="large")

with col_left:
    st.markdown("### 📋 Cartella Paziente")
    st.info(caso["scheda_paziente"])

    st.markdown("### 📊 Stato Paziente")
    m1, m2, m3 = st.columns(3)
    m1.metric("Vitalità", f"{max(0, min(100, state['vitalita']))}%")
    m2.metric("Controllo Onc.", f"{max(0, min(100, state['oncologico']))}%")
    m3.metric("Qualità di Vita", f"{max(0, min(100, state['qol']))}%")

    # Vista live per i Master sull'andamento di tutte le squadre/coppie attive
    if st.session_state.user_role == "master":
        with st.expander("📡 Monitor Live Aula & Debug Nodo", expanded=True):
            st.write(f"**Nodo attuale:** `{state['current_node']}`")
            tutti_i_nodi = list(caso["nodi"].keys()) + list(caso["esiti"].keys())
            salto = st.selectbox(
                "Salta al nodo (solo tua vista Master):",
                tutti_i_nodi,
                index=tutti_i_nodi.index(state["current_node"]),
            )
            if st.button("Vai al nodo", use_container_width=True):
                state["current_node"] = salto
                st.rerun()

            st.divider()
            st.markdown("**Stato Squadre / Utenti su questo caso:**")
            prefisso = f"{selected_case_id}__"
            attivi = {k[len(prefisso):]: v for k, v in room["stati_casi"].items() if k.startswith(prefisso)}
            for gruppo, st_grp in attivi.items():
                st.caption(
                    f"• **{gruppo}** → `{st_grp['current_node']}` | Vit {st_grp['vitalita']}% | Onc {st_grp['oncologico']}% | QoL {st_grp['qol']}%"
                )

with col_right:
    node_id = state["current_node"]

    if node_id in caso["nodi"]:
        nodo = caso["nodi"][node_id]
        st.markdown(f"### {nodo['titolo']}")
        st.write(nodo["testo"])

        if nodo.get("immagine") and os.path.exists(nodo["immagine"]):
            st.image(
                nodo["immagine"],
                caption=nodo.get("didascalia_immagine", ""),
                use_container_width=True,
            )

        with st.form(key=f"form_{chiave_stato}_{node_id}"):
            etichette_opzioni = [opt["testo"] for opt in nodo["opzioni"]]
            scelta_testo = st.radio("Seleziona la condotta clinica:", etichette_opzioni)
            conferma = st.form_submit_button("Conferma Scelta ➡️", use_container_width=True)

            if conferma:
                opzione_scelta = next(
                    opt for opt in nodo["opzioni"] if opt["testo"] == scelta_testo
                )
                state["vitalita"] += opzione_scelta.get("d_vit", 0)
                state["oncologico"] += opzione_scelta.get("d_onc", 0)
                state["qol"] += opzione_scelta.get("d_qol", 0)
                state["percorso"].append(
                    {"nodo": nodo["titolo"], "scelta": opzione_scelta["testo"]}
                )
                state["current_node"] = opzione_scelta["next"]
                st.rerun()

    elif node_id in caso["esiti"]:
        esito = caso["esiti"][node_id]
        tipo = esito.get("tipo", "rosso")

        colori = {
            "bianco": ("#dcfce7", "#22c55e", "#16a34a", "#166534"),
            "giallo": ("#fef9c3", "#eab308", "#ca8a04", "#854d0e"),
            "rosso": ("#fee2e2", "#ef4444", "#dc2626", "#991b1b"),
        }
        bg, border, title_col, text_col = colori.get(tipo, colori["rosso"])

        st.markdown(
            f"""
            <div style="background: {bg}; border: 2px solid {border}; padding: 2rem; border-radius: 12px; text-align: center;">
                <h1 style="color: {title_col}; margin-top: 0;">{esito['titolo']}</h1>
                <h3 style="color: {title_col};"><i>{esito.get('sottotitolo', '')}</i></h3>
                <p style="color: {text_col}; font-size: 1.05rem;">{esito['descrizione']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### 🧭 Riepilogo del percorso clinico")
        for idx, step in enumerate(state["percorso"], 1):
            st.markdown(f"**{idx}. {step['nodo']}** → `{step['scelta']}`")

        if st.button("🔄 Ripeti il Caso", use_container_width=True):
            del room["stati_casi"][chiave_stato]
            st.rerun()
