import streamlit as st

MASTER_CREDENTIALS = {
    "gbadano": "211280",
    "acavo": "211186",
    "smigone": "090286",
}

DEFAULT_DISCENTI_PASSWORD = "12345678"


@st.cache_resource
def get_global_room():
    """Stato condiviso tra tutti i dispositivi connessi in aula."""
    return {
        "modalita_attiva": "Singolo Discente",  # "Singolo Discente" | "Gruppi / Squadre"
        "caso_attivo_globale": None,
        "utenti_autorizzati": [f"{i:03d}" for i in range(1, 15)],
        "gruppi_personalizzati": {},  # {"Nome Gruppo": ["franco", "002", ...]}
        "stati_casi": {},  # {"001__gruppo_x": {...}}
    }


def _render_login_screen(room):
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
                "Nome Utente / Codice",
                placeholder="Inserisci il nome assegnato dal docente",
            ).strip()
            password_input = st.text_input(
                "Password", type="password", placeholder="Password"
            ).strip()
            submit = st.form_submit_button("Entra in Aula", use_container_width=True)

            if submit:
                # 1. Verifica credenziali Docenti Master
                if username_input in MASTER_CREDENTIALS:
                    if MASTER_CREDENTIALS[username_input] == password_input:
                        st.session_state.authenticated = True
                        st.session_state.user_role = "master"
                        st.session_state.user_id = username_input
                        st.rerun()
                    else:
                        st.error("Password Docente Master errata.")

                # 2. Verifica nella whitelist dinamica dei discenti
                else:
                    mappa_utenti = {u.lower(): u for u in room["utenti_autorizzati"]}
                    chiave_norm = username_input.lower()

                    if chiave_norm in mappa_utenti:
                        if password_input == DEFAULT_DISCENTI_PASSWORD:
                            st.session_state.authenticated = True
                            st.session_state.user_role = "discente"
                            st.session_state.user_id = mappa_utenti[chiave_norm]
                            st.rerun()
                        else:
                            st.error(
                                f"Password errata (Default aula: {DEFAULT_DISCENTI_PASSWORD})."
                            )
                    else:
                        st.error(
                            "Accesso non autorizzato o sessione chiusa dal docente."
                        )


def verifica_accesso():
    """Controlla l'autenticazione, espelle utenti revocati e restituisce (room, role, uid)."""
    room = get_global_room()

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_role" not in st.session_state:
        st.session_state.user_role = None
    if "user_id" not in st.session_state:
        st.session_state.user_id = None

    # Espulsione immediata se il Master revoca l'utente mentre è connesso
    if st.session_state.authenticated and st.session_state.user_role == "discente":
        if st.session_state.user_id not in room["utenti_autorizzati"]:
            st.session_state.authenticated = False
            st.session_state.user_role = None
            st.session_state.user_id = None
            st.warning("Il tuo accesso è stato revocato dalla Control Room.")
            st.stop()

    if not st.session_state.authenticated:
        _render_login_screen(room)
        st.stop()

    return room, st.session_state.user_role, st.session_state.user_id


def risolvi_identita_gioco(room, role, uid):
    """Restituisce (chiave_sessione, etichetta_visiva) in base alla modalità aula attiva."""
    if role == "master":
        return f"master_{uid}", f"Control Room ({uid})"

    if room["modalita_attiva"] == "Gruppi / Squadre":
        for nome_gruppo, membri in room["gruppi_personalizzati"].items():
            if uid in membri:
                slug = "".join(c if c.isalnum() else "_" for c in nome_gruppo.lower())
                return f"gruppo_{slug}", f"{nome_gruppo} ({uid})"
        return f"singolo_{uid}", f"{uid} (Non assegnato ad alcun gruppo)"

    return f"singolo_{uid}", f"{uid} (Individuale)"


def render_regia_master(room, selected_case_id):
    """Disegna nella sidebar i controlli riservati ai 3 docenti Master."""
    st.divider()
    st.markdown("### 🎛️ Regia Master")

    if st.button("📌 Sincronizza caso per tutta l'aula", use_container_width=True):
        room["caso_attivo_globale"] = selected_case_id
        st.success(f"Caso {selected_case_id} impostato per l'aula!")

    # 1. Gestione Whitelist Utenti (Aggiungi / Rinomina / Revoca / Chiudi Aula)
    with st.expander("🔑 Gestione Accessi Discenti", expanded=False):
        nuovo_utente = st.text_input(
            "Aggiungi nuovo partecipante",
            placeholder="es. franco, rossi, 001...",
        ).strip()
        if st.button("➕ Abilita Utente", use_container_width=True):
            if not nuovo_utente:
                st.warning("Scrivi un nome o codice.")
            elif nuovo_utente.lower() in [
                u.lower() for u in room["utenti_autorizzati"]
            ]:
                st.warning("Utente già presente.")
            else:
                room["utenti_autorizzati"].append(nuovo_utente)
                st.rerun()

        if room["utenti_autorizzati"]:
            st.divider()
            st.markdown("**Rinomina o Revoca Accesso:**")
            utente_sel = st.selectbox(
                "Seleziona utente attivo",
                room["utenti_autorizzati"],
                key="sel_utente_edit",
            )
            nuovo_nome = st.text_input(
                "Nuovo nome per questo utente",
                value=utente_sel,
                key="txt_rinomina_utente",
            ).strip()

            c_ren, c_del_u = st.columns(2)
            with c_ren:
                if st.button("✏️ Rinomina", use_container_width=True):
                    if nuovo_nome and nuovo_nome != utente_sel:
                        if nuovo_nome.lower() in [
                            u.lower() for u in room["utenti_autorizzati"]
                        ]:
                            st.error("Nome già in uso.")
                        else:
                            idx_u = room["utenti_autorizzati"].index(utente_sel)
                            room["utenti_autorizzati"][idx_u] = nuovo_nome
                            for g_nome, membri in room["gruppi_personalizzati"].items():
                                room["gruppi_personalizzati"][g_nome] = [
                                    nuovo_nome if m == utente_sel else m for m in membri
                                ]
                            st.rerun()
            with c_del_u:
                if st.button("🚫 Revoca", use_container_width=True):
                    room["utenti_autorizzati"].remove(utente_sel)
                    for g_nome in room["gruppi_personalizzati"]:
                        room["gruppi_personalizzati"][g_nome] = [
                            m
                            for m in room["gruppi_personalizzati"][g_nome]
                            if m != utente_sel
                        ]
                    st.rerun()

            st.divider()
            if st.button(
                "🔒 Chiudi Aula (Cancella tutti gli utenti)",
                use_container_width=True,
            ):
                room["utenti_autorizzati"] = []
                room["gruppi_personalizzati"] = {}
                st.rerun()
        else:
            st.warning("Nessun discente abilitato (Aula chiusa).")
            if st.button("🔄 Ripristina 001–014", use_container_width=True):
                room["utenti_autorizzati"] = [f"{i:03d}" for i in range(1, 15)]
                st.rerun()

    # 2. Modalità Sessione e Costruttore Libero Gruppi
    nuova_mod = st.radio(
        "Modalità Sessione:",
        ["Singolo Discente", "Gruppi / Squadre"],
        index=["Singolo Discente", "Gruppi / Squadre"].index(
            room["modalita_attiva"]
        ),
    )
    if nuova_mod != room["modalita_attiva"]:
        room["modalita_attiva"] = nuova_mod
        st.rerun()

    if room["modalita_attiva"] == "Gruppi / Squadre":
        with st.expander("🧩 Costruttore Libero Gruppi", expanded=True):
            utenti_disp = room["utenti_autorizzati"]
            nome_nuovo = st.text_input(
                "Nome nuovo gruppo / squadra",
                placeholder="es. Urologi, Oncologi, Osp. X...",
            ).strip()
            membri_nuovi = st.multiselect(
                "Seleziona partecipanti",
                utenti_disp,
                key="ms_nuovo_gruppo",
            )
            if st.button("➕ Crea / Aggiungi Gruppo", use_container_width=True):
                if not nome_nuovo:
                    st.warning("Inserisci un nome per il gruppo.")
                else:
                    for g in room["gruppi_personalizzati"]:
                        room["gruppi_personalizzati"][g] = [
                            u
                            for u in room["gruppi_personalizzati"][g]
                            if u not in membri_nuovi
                        ]
                    room["gruppi_personalizzati"][nome_nuovo] = list(membri_nuovi)
                    st.rerun()

            if room["gruppi_personalizzati"]:
                st.divider()
                st.markdown("**Gruppi Attivi:**")
                for g_nome in list(room["gruppi_personalizzati"].keys()):
                    membri_g = [
                        m
                        for m in room["gruppi_personalizzati"][g_nome]
                        if m in utenti_disp
                    ]
                    st.markdown(
                        f"**{g_nome}**: `{', '.join(membri_g) if membri_g else 'nessun membro'}`"
                    )
                    c_edit, c_del = st.columns([3, 1])
                    with c_edit:
                        aggiornati = st.multiselect(
                            f"Modifica {g_nome}",
                            utenti_disp,
                            default=membri_g,
                            key=f"edit_{g_nome}",
                            label_visibility="collapsed",
                        )
                        if aggiornati != membri_g:
                            for altro_g in room["gruppi_personalizzati"]:
                                if altro_g != g_nome:
                                    room["gruppi_personalizzati"][altro_g] = [
                                        u
                                        for u in room["gruppi_personalizzati"][altro_g]
                                        if u not in aggiornati
                                    ]
                            room["gruppi_personalizzati"][g_nome] = list(aggiornati)
                            st.rerun()
                    with c_del:
                        if st.button(
                            "🗑️", key=f"del_{g_nome}", help=f"Elimina {g_nome}"
                        ):
                            del room["gruppi_personalizzati"][g_nome]
                            st.rerun()

                assegnati = {
                    u
                    for m_list in room["gruppi_personalizzati"].values()
                    for u in m_list
                }
                liberi = [d for d in utenti_disp if d not in assegnati]
                if liberi:
                    st.caption(f"Non assegnati: {', '.join(liberi)}")
                else:
                    st.caption("Tutti i partecipanti abilitati sono assegnati.")

                if st.button("🧹 Svuota tutti i gruppi", use_container_width=True):
                    room["gruppi_personalizzati"] = {}
                    st.rerun()
