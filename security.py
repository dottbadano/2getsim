import streamlit as st
from text import APP_SUBTITLE, APP_TITLE

MASTER_CREDENTIALS = {
    "gbadano": "211280",
    "acavo": "211186",
    "smigone": "090286",
}
DEFAULT_PASS = "12345678"


@st.cache_resource
def get_global_room():
    return {
        "modalita_attiva": "Singolo Discente",
        "caso_attivo_globale": None,
        "utenti_autorizzati": [f"{i:03d}" for i in range(1, 15)],
        "gruppi_personalizzati": {},
        "stati_casi": {},
    }


def verifica_accesso():
    room = get_global_room()
    for k, v in [("authenticated", False), ("user_role", None), ("user_id", None)]:
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state.authenticated and st.session_state.user_role == "discente":
        if st.session_state.user_id not in room["utenti_autorizzati"]:
            st.session_state.update(authenticated=False, user_role=None, user_id=None)
            st.warning("Accesso revocato dalla Control Room.")
            st.stop()

    if not st.session_state.authenticated:
        _login_screen(room)
        st.stop()

    return room, st.session_state.user_role, st.session_state.user_id


def _login_screen(room):
    st.markdown(
        f"<div style='text-align:center; padding:1.5rem 0;'><h1>⚡ {APP_TITLE}</h1><p style='color:#666;'>{APP_SUBTITLE}</p></div>",
        unsafe_allow_html=True,
    )
    _, col, _ = st.columns([1, 2, 1])
    with col:
        with st.form("login_form"):
            user = st.text_input("Nome Utente / Codice").strip()
            pwd = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Entra in Aula", use_container_width=True):
                if user in MASTER_CREDENTIALS and MASTER_CREDENTIALS[user] == pwd:
                    st.session_state.update(authenticated=True, user_role="master", user_id=user)
                    st.rerun()
                mappa = {u.lower(): u for u in room["utenti_autorizzati"]}
                if user.lower() in mappa and pwd == DEFAULT_PASS:
                    st.session_state.update(authenticated=True, user_role="discente", user_id=mappa[user.lower()])
                    st.rerun()
                st.error("Credenziali errate o accesso non abilitato.")


def risolvi_identita_gioco(room, role, uid):
    if role == "master":
        return f"master_{uid}", f"Control Room ({uid})"
    if room["modalita_attiva"] == "Gruppi / Squadre":
        for nome_g, membri in room["gruppi_personalizzati"].items():
            if uid in membri:
                slug = "".join(c if c.isalnum() else "_" for c in nome_g.lower())
                return f"gruppo_{slug}", f"{nome_g} ({uid})"
        return f"singolo_{uid}", f"{uid} (Non assegnato)"
    return f"singolo_{uid}", f"{uid} (Individuale)"


def render_regia_master(room, selected_case_id):
    st.divider()
    st.markdown("### 🎛️ Regia Master")

    if st.button("📌 Sincronizza caso per tutta l'aula", use_container_width=True):
        room["caso_attivo_globale"] = selected_case_id
        st.success(f"Caso {selected_case_id} attivo!")

    with st.expander("🔑 Gestione Accessi Discenti"):
        nuovo = st.text_input("Aggiungi partecipante", placeholder="es. franco").strip()
        if st.button("➕ Abilita Utente", use_container_width=True) and nuovo:
            if nuovo.lower() not in [u.lower() for u in room["utenti_autorizzati"]]:
                room["utenti_autorizzati"].append(nuovo)
                st.rerun()

        if room["utenti_autorizzati"]:
            sel = st.selectbox("Utente attivo", room["utenti_autorizzati"])
            rinomina = st.text_input("Rinomina in", value=sel).strip()
            c1, c2 = st.columns(2)
            if c1.button("✏️ Rinomina", use_container_width=True) and rinomina and rinomina != sel:
                idx = room["utenti_autorizzati"].index(sel)
                room["utenti_autorizzati"][idx] = rinomina
                for g, m in room["gruppi_personalizzati"].items():
                    room["gruppi_personalizzati"][g] = [rinomina if x == sel else x for x in m]
                st.rerun()
            if c2.button("🚫 Revoca", use_container_width=True):
                room["utenti_autorizzati"].remove(sel)
                for g in room["gruppi_personalizzati"]:
                    room["gruppi_personalizzati"][g] = [x for x in room["gruppi_personalizzati"][g] if x != sel]
                st.rerun()
            if st.button("🔒 Chiudi Aula (Cancella tutti)", use_container_width=True):
                room["utenti_autorizzati"] = []
                room["gruppi_personalizzati"] = {}
                st.rerun()
        elif st.button("🔄 Ripristina 001–014", use_container_width=True):
            room["utenti_autorizzati"] = [f"{i:03d}" for i in range(1, 15)]
            st.rerun()

    mod = st.radio(
        "Modalità Sessione:",
        ["Singolo Discente", "Gruppi / Squadre"],
        index=0 if room["modalita_attiva"] == "Singolo Discente" else 1,
    )
    if mod != room["modalita_attiva"]:
        room["modalita_attiva"] = mod
        st.rerun()

    if room["modalita_attiva"] == "Gruppi / Squadre":
        with st.expander("🧩 Costruttore Libero Gruppi", expanded=True):
            utenti = room["utenti_autorizzati"]
            g_nome = st.text_input("Nome nuovo gruppo", placeholder="es. Urologi, Osp. X").strip()
            g_membri = st.multiselect("Seleziona partecipanti", utenti)
            if st.button("➕ Crea Gruppo", use_container_width=True) and g_nome:
                for g in room["gruppi_personalizzati"]:
                    room["gruppi_personalizzati"][g] = [u for u in room["gruppi_personalizzati"][g] if u not in g_membri]
                room["gruppi_personalizzati"][g_nome] = list(g_membri)
                st.rerun()

            for g in list(room["gruppi_personalizzati"].keys()):
                c_txt, c_del = st.columns([4, 1])
                c_txt.caption(f"**{g}**: {', '.join(room['gruppi_personalizzati'][g])}")
                if c_del.button("🗑️", key=f"del_{g}"):
                    del room["gruppi_personalizzati"][g]
                    st.rerun()
