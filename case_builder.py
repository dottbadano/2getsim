import importlib
import os
import pprint
import streamlit as st

COLORI_CLINICI = {
    "🟩 Verde — Giusta (Tailored ottimale)": {
        "codice": "verde",
        "d_vit": 5,
        "d_onc": 15,
        "d_qol": 5,
        "hex": "#16a34a",
        "bg": "#dcfce7",
    },
    "🟦 Blu — Quasi giusta (Ragionevole / Subottimale)": {
        "codice": "blu",
        "d_vit": 0,
        "d_onc": -5,
        "d_qol": -5,
        "hex": "#2563eb",
        "bg": "#dbeafe",
    },
    "🟨 Gialla — Giusta da Linea Guida ma NON per questo paziente": {
        "codice": "giallo",
        "d_vit": -10,
        "d_onc": -15,
        "d_qol": -25,
        "hex": "#ca8a04",
        "bg": "#fef9c3",
    },
    "🟥 Rossa — Sbagliata / Pericolosa": {
        "codice": "rosso",
        "d_vit": -20,
        "d_onc": -30,
        "d_qol": -20,
        "hex": "#dc2626",
        "bg": "#fee2e2",
    },
}

MAPPA_CODICE_TO_LABEL = {v["codice"]: k for k, v in COLORI_CLINICI.items()}


def _deduci_colore_da_delta(opt):
    """Deduce il colore clinico se si carica un caso vecchio che aveva solo d_vit/d_onc/d_qol."""
    if opt.get("colore") in MAPPA_CODICE_TO_LABEL:
        return MAPPA_CODICE_TO_LABEL[opt["colore"]]
    do, dq, dv = opt.get("d_onc", 0), opt.get("d_qol", 0), opt.get("d_vit", 0)
    if do > 0 and dv >= 0:
        return "🟩 Verde — Giusta (Tailored ottimale)"
    if dq <= -20 and do >= -15:
        return "🟨 Gialla — Giusta da Linea Guida ma NON per questo paziente"
    if dv <= -15 or do <= -25:
        return "🟥 Rossa — Sbagliata / Pericolosa"
    return "🟦 Blu — Quasi giusta (Ragionevole / Subottimale)"


def render_case_builder(case_dir="storycase"):
    st.markdown("## ✍️ Editor Visuale Casi Clinici — Diagramma a 4 Colori")
    st.caption(
        "Scrivi l'anamnesi, inserisci le 4 scelte per ogni snodo assegnando il colore clinico (Verde, Blu, Gialla, Rossa) e collega gli snodi successivi."
    )

    if "builder_caso" not in st.session_state:
        st.session_state.builder_caso = _template_vuoto()
    if "builder_file_id" not in st.session_state:
        st.session_state.builder_file_id = "002"

    # Barra caricamento caso esistente / nuovo
    existing_files = sorted(
        [f[:-3] for f in os.listdir(case_dir) if f.endswith(".py") and f != "__init__"]
    )
    c_load1, c_load2, c_load3 = st.columns([2, 1, 1])
    sel_load = c_load1.selectbox(
        "Carica caso:",
        ["-- Nuovo Caso Vuoto --"] + existing_files,
        label_visibility="collapsed",
    )
    if c_load2.button("📂 Carica nell'Editor", use_container_width=True):
        if sel_load == "-- Nuovo Caso Vuoto --":
            st.session_state.builder_caso = _template_vuoto()
            st.session_state.builder_file_id = "002"
        else:
            mod = importlib.import_module(f"{case_dir}.{sel_load}")
            importlib.reload(mod)
            st.session_state.builder_caso = mod.CASO
            st.session_state.builder_file_id = sel_load
        st.rerun()

    if c_load3.button("🆕 Azzera Tutto", use_container_width=True):
        st.session_state.builder_caso = _template_vuoto()
        st.session_state.builder_file_id = "002"
        st.rerun()

    dati = st.session_state.builder_caso

    # -----------------------------------------------------------------------
    # 1. ANAMNESI E INTESTAZIONE (PRIMO STEP OBBLIGATORIO)
    # -----------------------------------------------------------------------
    with st.expander("1️⃣ Step 1 — Anamnesi Paziente & Dati Caso", expanded=True):
        c1, c2 = st.columns([1, 2])
        file_id = c1.text_input(
            "Codice Scenario (es. 002, 003)", value=st.session_state.builder_file_id
        ).strip()
        st.session_state.builder_file_id = file_id
        dati["descrizione_master"] = c2.text_input(
            "Promemoria per Regia Master (invisibile ai discenti)",
            value=dati.get("descrizione_master", ""),
            placeholder="es. K vescica NMIBC BCG-unresponsive in paziente cardiopatico",
        )
        dati["titolo"] = st.text_input(
            "Titolo mostrato in aula",
            value=dati.get("titolo", ""),
            placeholder="es. Paziente con ematuria recidivante dopo induzione BCG",
        )
        dati["sottotitolo"] = st.text_input(
            "Sottotitolo", value=dati.get("sottotitolo", "")
        )
        dati["scheda_paziente"] = st.text_area(
            "Anamnesi & Cartella Clinica (si nasconde dopo la prima scelta; inserisci qui eventuali controindicazioni o familiarità)",
            value=dati.get("scheda_paziente", ""),
            height=160,
        )

    # -----------------------------------------------------------------------
    # DIAGRAMMA DI FLUSSO LIVE COLORATO
    # -----------------------------------------------------------------------
    with st.expander("🕸️ Diagramma di Flusso Live (Colori Clinici)", expanded=True):
        orientamento = st.radio(
            "Orientamento grafico:",
            ["Verticale (Dall'alto in basso)", "Orizzontale (Da sinistra a destra)"],
            horizontal=True,
        )
        rankdir = "TB" if orientamento.startswith("Verticale") else "LR"
        st.graphviz_chart(_genera_graphviz_dot(dati, rankdir=rankdir), use_container_width=True)
        st.caption(
            "Frecce: 🟩 Giusta | 🟦 Quasi giusta | 🟨 Trappola Linea Guida (no per questo pz) | 🟥 Sbagliata"
        )

    # -----------------------------------------------------------------------
    # 2. SNODI E LE 4 SCELTE COLORATE PER CIASCUNO SNODO
    # -----------------------------------------------------------------------
    with st.expander("2️⃣ Step 2 — Snodi Decisionali (4 Scelte per Snodo)", expanded=True):
        c_add1, c_add2 = st.columns([3, 1])
        nuovo_snodo_id = c_add1.text_input(
            "Aggiungi nuovo snodo (es. snodo2a, snodo2b, snodo3)",
            placeholder="es. snodo2a",
        ).strip()
        if c_add2.button("➕ Crea Snodo", use_container_width=True) and nuovo_snodo_id:
            if nuovo_snodo_id not in dati["nodi"]:
                dati["nodi"][nuovo_snodo_id] = _nuovo_snodo_default(nuovo_snodo_id)
                st.rerun()

        lista_nodi = list(dati["nodi"].keys())
        idx_init = (
            lista_nodi.index(dati["nodo_iniziale"])
            if dati.get("nodo_iniziale") in lista_nodi
            else 0
        )
        dati["nodo_iniziale"] = st.selectbox(
            "Snodo iniziale:", lista_nodi, index=idx_init
        )

        CREA_NUOVO_LABEL = "➕ [Crea nuovo snodo per questa scelta...]"
        destinazioni_base = list(dati["nodi"].keys()) + list(dati["esiti"].keys())
        opzioni_tendina = destinazioni_base + [CREA_NUOVO_LABEL]

        for s_id in list(dati["nodi"].keys()):
            st.markdown("---")
            col_t, col_del = st.columns([5, 1])
            col_t.markdown(f"### 🔀 Snodo: `{s_id}`")
            if len(dati["nodi"]) > 1 and col_del.button("🗑️ Elimina", key=f"del_s_{s_id}"):
                del dati["nodi"][s_id]
                st.rerun()

            snodo = dati["nodi"][s_id]
            snodo["titolo"] = st.text_input(
                "Titolo snodo", value=snodo["titolo"], key=f"t_{s_id}"
            )
            snodo["testo"] = st.text_area(
                "Quadro clinico / Evoluzione",
                value=snodo["testo"],
                key=f"txt_{s_id}",
                height=85,
            )

            # Garantisce sempre 4 caselle di scelta per ogni snodo
            while len(snodo["opzioni"]) < 4:
                snodo["opzioni"].append(
                    {
                        "testo": f"Opzione {len(snodo['opzioni']) + 1}",
                        "colore": "blu",
                        "d_vit": 0,
                        "d_onc": -5,
                        "d_qol": -5,
                        "next": destinazioni_base[0],
                    }
                )

            for idx, opt in enumerate(snodo["opzioni"]):
                label_colore_att = _deduci_colore_da_delta(opt)
                info_col = COLORI_CLINICI[label_colore_att]

                st.markdown(
                    f"""
                    <div style="border-left: 6px solid {info_col['hex']}; background-color: {info_col['bg']}; padding: 6px 12px; border-radius: 6px; margin-top: 8px; margin-bottom: 4px; color: #0f172a; font-weight: 600; font-size: 0.9rem;">
                        Scelta {idx + 1} — {label_colore_att}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                c_txt, c_col, c_nxt = st.columns([2.4, 1.5, 1.3])
                opt["testo"] = c_txt.text_input(
                    "Testo scelta",
                    value=opt["testo"],
                    key=f"opt_{s_id}_{idx}",
                    label_visibility="collapsed",
                )

                scelta_colore = c_col.selectbox(
                    "Colore casella",
                    list(COLORI_CLINICI.keys()),
                    index=list(COLORI_CLINICI.keys()).index(label_colore_att),
                    key=f"col_{s_id}_{idx}",
                    label_visibility="collapsed",
                )
                # Aggiorna automaticamente i punteggi in base al colore scelto
                cfg = COLORI_CLINICI[scelta_colore]
                opt["colore"] = cfg["codice"]
                opt["d_vit"] = cfg["d_vit"]
                opt["d_onc"] = cfg["d_onc"]
                opt["d_qol"] = cfg["d_qol"]

                curr_next = (
                    opt["next"] if opt["next"] in destinazioni_base else destinazioni_base[0]
                )
                scelta_dest = c_nxt.selectbox(
                    "Snodo successivo",
                    opzioni_tendina,
                    index=opzioni_tendina.index(curr_next),
                    key=f"nxt_{s_id}_{idx}",
                    label_visibility="collapsed",
                )

                if scelta_dest == CREA_NUOVO_LABEL:
                    c_new1, c_new2 = st.columns([3, 1])
                    nome_ramo_volo = c_new1.text_input(
                        "Nome nuovo snodo (es. snodo2b):",
                        key=f"new_branch_{s_id}_{idx}",
                        placeholder="es. snodo2b",
                    ).strip()
                    if (
                        c_new2.button(
                            "Crea e Collega",
                            key=f"btn_branch_{s_id}_{idx}",
                            use_container_width=True,
                        )
                        and nome_ramo_volo
                    ):
                        if nome_ramo_volo not in dati["nodi"]:
                            dati["nodi"][nome_ramo_volo] = _nuovo_snodo_default(
                                nome_ramo_volo
                            )
                        opt["next"] = nome_ramo_volo
                        st.rerun()
                else:
                    opt["next"] = scelta_dest

    # -----------------------------------------------------------------------
    # 3. ESITI FINALI
    # -----------------------------------------------------------------------
    with st.expander("🏁 Step 3 — Esiti Finali (Tazza Bianca / Gialla / Rossa)", expanded=False):
        for e_id, esito in dati["esiti"].items():
            st.markdown(f"**Esito: `{e_id}`**")
            esito["titolo"] = st.text_input(
                "Titolo esito", value=esito["titolo"], key=f"et_{e_id}"
            )
            esito["descrizione"] = st.text_area(
                "Spiegazione finale",
                value=esito["descrizione"],
                key=f"ed_{e_id}",
            )

    # -----------------------------------------------------------------------
    # 4. SALVATAGGIO E DOWNLOAD PER GITHUB
    # -----------------------------------------------------------------------
    st.divider()
    codice_generato = f"CASO = {pprint.pformat(dati, width=100, sort_dicts=False)}\n"

    c_save, c_dl = st.columns(2)
    with c_save:
        if st.button("💾 Salva subito nella cartella storycase/", use_container_width=True):
            if not file_id or not dati["titolo"]:
                st.error("Inserisci almeno il Codice Scenario (es. 002) e il Titolo.")
            else:
                os.makedirs(case_dir, exist_ok=True)
                percorso = os.path.join(case_dir, f"{file_id}.py")
                with open(percorso, "w", encoding="utf-8") as f:
                    f.write(codice_generato)
                st.success(f"Salvato in '{percorso}'! Ora è selezionabile in aula.")

    with c_dl:
        st.download_button(
            label=f"⬇️ Scarica {file_id or 'caso'}.py (per GitHub)",
            data=codice_generato,
            file_name=f"{file_id or 'caso'}.py",
            mime="text/x-python",
            use_container_width=True,
        )


def _genera_graphviz_dot(dati, rankdir="TB"):
    nodo_init = dati.get("nodo_iniziale", "")
    raggiungibili = {nodo_init}
    for s_id, snodo in dati.get("nodi", {}).items():
        for opt in snodo.get("opzioni", []):
            raggiungibili.add(opt.get("next"))

    righe = [
        "digraph G {",
        f'  rankdir="{rankdir}";',
        '  bgcolor="transparent";',
        '  node [shape=box, style="rounded,filled", fontname="Inter,Arial", fontsize=11, margin="0.16,0.10"];',
        '  edge [fontname="Inter,Arial", fontsize=9, penwidth=1.6];',
    ]

    for s_id, snodo in dati.get("nodi", {}).items():
        titolo_breve = snodo.get("titolo", s_id).replace('"', "'")
        if len(titolo_breve) > 36:
            titolo_breve = titolo_breve[:33] + "..."
        label = f"{s_id}\\n{titolo_breve}"

        if s_id == nodo_init:
            fill, border, fontcol = "#e0e7ff", "#4338ca", "#1e1b4b"
        elif s_id not in raggiungibili:
            fill, border, fontcol = "#ffedd5", "#ea580c", "#7c2d12"
        else:
            fill, border, fontcol = "#f8fafc", "#475569", "#0f172a"

        righe.append(
            f'  "{s_id}" [label="{label}", fillcolor="{fill}", color="{border}", penwidth=1.8, fontcolor="{fontcol}"];'
        )

    for e_id, esito in dati.get("esiti", {}).items():
        tipo = esito.get("tipo", "rosso")
        if tipo == "bianco":
            fill, border, fontcol = "#dcfce7", "#16a34a", "#14532d"
        elif tipo == "giallo":
            fill, border, fontcol = "#fef9c3", "#ca8a04", "#713f12"
        else:
            fill, border, fontcol = "#fee2e2", "#dc2626", "#7f1d1d"
        label = f"{e_id}\\n{esito.get('titolo', e_id)[:28]}"
        righe.append(
            f'  "{e_id}" [label="{label}", shape=oval, fillcolor="{fill}", color="{border}", penwidth=2, fontcolor="{fontcol}"];'
        )

    for s_id, snodo in dati.get("nodi", {}).items():
        for idx, opt in enumerate(snodo.get("opzioni", []), 1):
            dest = opt.get("next", "")
            testo_opt = opt.get("testo", "").replace('"', "'")
            if len(testo_opt) > 28:
                testo_opt = testo_opt[:25] + "..."
            label_col = _deduci_colore_da_delta(opt)
            edge_color = COLORI_CLINICI[label_col]["hex"]
            edge_label = f"{idx}. {testo_opt}"
            righe.append(
                f'  "{s_id}" -> "{dest}" [label="{edge_label}", color="{edge_color}", fontcolor="{edge_color}"];'
            )

    righe.append("}")
    return "\n".join(righe)


def _nuovo_snodo_default(snodo_id):
    return {
        "titolo": f"📍 {snodo_id.upper()} — Evoluzione Clinica",
        "testo": "Descrivi il quadro clinico su questo snodo...",
        "opzioni": [
            {"testo": "Scelta 1 (Giusta tailored)", "colore": "verde", "d_vit": 5, "d_onc": 15, "d_qol": 5, "next": "esito_vittoria"},
            {"testo": "Scelta 2 (Quasi giusta)", "colore": "blu", "d_vit": 0, "d_onc": -5, "d_qol": -5, "next": "esito_parziale"},
            {"testo": "Scelta 3 (Linea guida ma no per questo pz)", "colore": "giallo", "d_vit": -10, "d_onc": -15, "d_qol": -25, "next": "esito_parziale"},
            {"testo": "Scelta 4 (Sbagliata)", "colore": "rosso", "d_vit": -20, "d_onc": -30, "d_qol": -20, "next": "esito_sconfitta"},
        ],
    }


def _template_vuoto():
    return {
        "badge": "ARENA URO-ONCOLOGICA",
        "descrizione_master": "",
        "titolo": "",
        "sottotitolo": "",
        "nodo_iniziale": "snodo1",
        "vitalita_iniziale": 100,
        "oncologico_iniziale": 100,
        "qol_iniziale": 75,
        "scheda_paziente": "* **Paziente:** \n* **Anamnesi patologica:** \n* **Terapia domiciliare:** \n* **Anamnesi familiare:** \n* **Esordio & Esami:** ",
        "nodi": {
            "snodo1": _nuovo_snodo_default("snodo1"),
        },
        "esiti": {
            "esito_vittoria": {
                "tipo": "bianco",
                "titolo": "🏆 TAZZA BIANCA CONQUISTATA!",
                "sottotitolo": '"Failure is not an option."',
                "descrizione": "Gestione clinica tailored ottimale.",
            },
            "esito_parziale": {
                "tipo": "giallo",
                "titolo": "⚠️ RISULTATO INTERMEDIO",
                "sottotitolo": "Cronicizzazione con sequele",
                "descrizione": "Controllo parziale di malattia o scelta non ritagliata sul paziente.",
            },
            "esito_sconfitta": {
                "tipo": "rosso",
                "titolo": "❌ TAZZA ROSSA ASSEGNATA!",
                "sottotitolo": '"Shit... happens."',
                "descrizione": "Complicanza maggiore o progressione non intercettata.",
            },
        },
    }
