import base64
import importlib
import json
import os
import pprint
import urllib.error
import urllib.request
import streamlit as st

COLORI_CLINICI = {
    "⬜ Da assegnare": {
        "codice": "blu",
        "d_vit": 0,
        "d_onc": -5,
        "d_qol": -5,
        "costo": 3500,
        "hex": "#94a3b8",
        "bg": "#ffffff",
    },
    "🟩 Verde — Giusta (Tailored ottimale)": {
        "codice": "verde",
        "d_vit": 5,
        "d_onc": 15,
        "d_qol": 5,
        "costo": 1200,
        "hex": "#16a34a",
        "bg": "#dcfce7",
    },
    "🟦 Blu — Quasi giusta (Ragionevole / Subottimale)": {
        "codice": "blu",
        "d_vit": 0,
        "d_onc": -5,
        "d_qol": -5,
        "costo": 3500,
        "hex": "#2563eb",
        "bg": "#dbeafe",
    },
    "🟨 Gialla — Giusta da Linea Guida ma NON per questo paziente": {
        "codice": "giallo",
        "d_vit": -10,
        "d_onc": -15,
        "d_qol": -25,
        "costo": 8500,
        "hex": "#ca8a04",
        "bg": "#fef9c3",
    },
    "🟥 Rossa — Sbagliata / Pericolosa": {
        "codice": "rosso",
        "d_vit": -20,
        "d_onc": -30,
        "d_qol": -20,
        "costo": 14000,
        "hex": "#dc2626",
        "bg": "#fee2e2",
    },
}

MAPPA_CODICE_TO_LABEL = {
    "verde": "🟩 Verde — Giusta (Tailored ottimale)",
    "blu": "🟦 Blu — Quasi giusta (Ragionevole / Subottimale)",
    "giallo": "🟨 Gialla — Giusta da Linea Guida ma NON per questo paziente",
    "rosso": "🟥 Rossa — Sbagliata / Pericolosa",
}


def _salva_su_github(percorso_repo, contenuto_testo, messaggio_commit):
    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        branch = st.secrets.get("GITHUB_BRANCH", "main")
    except Exception:
        return False, "Secrets di Streamlit non configurati."

    if not token or not repo:
        return False, "Mancano GITHUB_TOKEN o GITHUB_REPO nei Secrets di Streamlit."

    url = f"https://api.github.com/repos/{repo}/contents/{percorso_repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "2getSIM-App",
    }

    sha_esistente = None
    req_get = urllib.request.Request(f"{url}?ref={branch}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req_get, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            sha_esistente = data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return False, f"Errore lettura GitHub ({e.code}): {e.reason}"
    except Exception as e:
        return False, f"Errore connessione GitHub: {e}"

    payload = {
        "message": messaggio_commit,
        "content": base64.b64encode(contenuto_testo.encode("utf-8")).decode("utf-8"),
        "branch": branch,
    }
    if sha_esistente:
        payload["sha"] = sha_esistente

    req_put = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req_put, timeout=15) as resp:
            if resp.status in (200, 201):
                azione = "aggiornato" if sha_esistente else "creato"
                return True, f"File '{percorso_repo}' {azione} permanentemente su GitHub!"
            return False, f"Risposta imprevista da GitHub: {resp.status}"
    except urllib.error.HTTPError as e:
        dettaglio = e.read().decode("utf-8", errors="ignore")
        return False, f"Errore salvataggio GitHub ({e.code}): {dettaglio[:180]}"
    except Exception as e:
        return False, f"Errore rete durante il commit: {e}"


def _prossimo_codice_disponibile(existing_files):
    numeri = [int(f) for f in existing_files if f.isdigit()]
    prossimo = max(numeri) + 1 if numeri else 1
    return f"{prossimo:03d}"


def _deduci_colore_da_delta(opt):
    if not opt.get("testo", "").strip() and not opt.get("colore"):
        return "⬜ Da assegnare"
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


def _prossimo_id_snodo(nodi_dict):
    i = len(nodi_dict) + 1
    while f"snodo{i}" in nodi_dict:
        i += 1
    return f"snodo{i}"


def _raccogli_opzioni_note(dati):
    """Mappa ogni testo d'opzione già scritto al suo colore e snodo successivo."""
    mappa = {}
    for s_id, snodo in dati.get("nodi", {}).items():
        for opt in snodo.get("opzioni", []):
            txt = opt.get("testo", "").strip()
            if txt and txt not in mappa:
                mappa[txt] = {
                    "colore": opt.get("colore", "blu"),
                    "next": opt.get("next", "esito_parziale"),
                }
    return mappa


def render_case_builder(case_dir="storycase"):
    st.markdown("## ✍️ Editor Casi Clinici — Scrittura Guidata a 4 Caselle")
    st.caption(
        "1. Scrivi l'anamnesi • 2. Compila le 4 caselle bianche e assegna il colore • 3. Scegli per ciascuna 'Fine Caso' oppure 'Prossimo Snodo' (nuovo o già esistente)."
    )

    existing_files = sorted(
        [f[:-3] for f in os.listdir(case_dir) if f.endswith(".py") and f != "__init__"]
    )

    if "builder_caso" not in st.session_state:
        st.session_state.builder_caso = _template_vuoto()
    if "builder_file_id" not in st.session_state:
        st.session_state.builder_file_id = _prossimo_codice_disponibile(existing_files)
    if "builder_active_node" not in st.session_state:
        st.session_state.builder_active_node = "snodo1"

    # Barra caricamento caso esistente / nuovo
    c_load1, c_load2, c_load3 = st.columns([2, 1, 1])
    sel_load = c_load1.selectbox(
        "Carica caso:",
        ["-- Nuovo Caso Vuoto --"] + existing_files,
        label_visibility="collapsed",
    )
    if c_load2.button("📂 Carica nell'Editor", use_container_width=True):
        if sel_load == "-- Nuovo Caso Vuoto --":
            st.session_state.builder_caso = _template_vuoto()
            st.session_state.builder_file_id = _prossimo_codice_disponibile(existing_files)
        else:
            mod = importlib.import_module(f"{case_dir}.{sel_load}")
            importlib.reload(mod)
            st.session_state.builder_caso = mod.CASO
            st.session_state.builder_file_id = sel_load
        st.session_state.builder_active_node = st.session_state.builder_caso.get("nodo_iniziale", "snodo1")
        st.rerun()

    if c_load3.button("🆕 Azzera Tutto", use_container_width=True):
        st.session_state.builder_caso = _template_vuoto()
        st.session_state.builder_file_id = _prossimo_codice_disponibile(existing_files)
        st.session_state.builder_active_node = "snodo1"
        st.rerun()

    dati = st.session_state.builder_caso
    lista_nodi = list(dati["nodi"].keys())
    if st.session_state.builder_active_node not in lista_nodi:
        st.session_state.builder_active_node = lista_nodi[0]

    # -----------------------------------------------------------------------
    # 1. ANAMNESI E INTESTAZIONE
    # -----------------------------------------------------------------------
    with st.expander("1️⃣ Anamnesi & Intestazione Caso", expanded=True):
        c1, c2 = st.columns([1, 2])
        file_id = c1.text_input(
            "Codice Scenario (es. 002, 003)", value=st.session_state.builder_file_id
        ).strip()
        st.session_state.builder_file_id = file_id
        dati["descrizione_master"] = c2.text_input(
            "Promemoria per Regia Master (visibile solo ai docenti)",
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
            "Anamnesi & Cartella Clinica (si chiude dopo la prima scelta in aula)",
            value=dati.get("scheda_paziente", ""),
            height=140,
        )

    # -----------------------------------------------------------------------
    # 2. DIAGRAMMA DI FLUSSO LIVE + SELETTORE RAPIDO DELLO SNODO DA COMPILARE
    # -----------------------------------------------------------------------
    with st.expander("🕸️ Mappa del Flusso Clinico (Panoramica Live)", expanded=True):
        st.graphviz_chart(_genera_graphviz_dot(dati, rankdir="LR"), use_container_width=True)
        st.caption(
            "🟩 Giusta | 🟦 Quasi giusta | 🟨 Trappola Linea Guida (no per questo pz) | 🟥 Sbagliata"
        )

    # -----------------------------------------------------------------------
    # 3. EDITOR DELLO SNODO CORRENTE (4 CASELLE BIANCHE -> COLORE -> DESTINAZIONE)
    # -----------------------------------------------------------------------
    st.markdown("### 🔀 Compilazione Snodo Decisionale")

    # Barra di navigazione tra tutti gli snodi esistenti
    nav1, nav2 = st.columns([3, 1])
    s_id = nav1.selectbox(
        "Snodo che stai scrivendo ora:",
        lista_nodi,
        index=lista_nodi.index(st.session_state.builder_active_node),
        format_func=lambda x: f"{x} — {dati['nodi'][x].get('titolo', '')}",
    )
    st.session_state.builder_active_node = s_id

    if len(lista_nodi) > 1 and nav2.button("🗑️ Elimina questo snodo", use_container_width=True):
        del dati["nodi"][s_id]
        st.session_state.builder_active_node = list(dati["nodi"].keys())[0]
        st.rerun()

    snodo = dati["nodi"][s_id]
    snodo["titolo"] = st.text_input("Titolo dello snodo", value=snodo["titolo"], key=f"t_{s_id}")
    snodo["testo"] = st.text_area(
        "Situazione clinica / Evoluzione del paziente",
        value=snodo["testo"],
        key=f"txt_{s_id}",
        height=95,
    )

    # Garantisce sempre 4 caselle
    while len(snodo["opzioni"]) < 4:
        snodo["opzioni"].append(
            {
                "testo": "",
                "colore": "",
                "d_vit": 0,
                "d_onc": -5,
                "d_qol": -5,
                "costo": 3500,
                "next": "esito_parziale",
            }
        )

    opzioni_note = _raccogli_opzioni_note(dati)
    esiti_ids = list(dati["esiti"].keys())
    esiti_labels = {
        "esito_vittoria": "🏆 Tazza Bianca (Successo Tailored)",
        "esito_parziale": "⚠️ Risultato Intermedio (Cronicizzazione / Sequele)",
        "esito_sconfitta": "❌ Tazza Rossa (Fallimento / Complicanza)",
    }

    st.markdown("#### Le 4 Caselle di Scelta")
    for idx in range(4):
        opt = snodo["opzioni"][idx]
        label_colore_att = _deduci_colore_da_delta(opt)
        info_col = COLORI_CLINICI[label_colore_att]

        # Contenitore visivo che parte bianco e si colora appena selezioni il colore
        st.markdown(
            f"""
            <div style="border: 2px solid {info_col['hex']}; background-color: {info_col['bg']}; padding: 10px 14px; border-radius: 10px; margin-top: 10px; margin-bottom: 6px; color: #0f172a;">
                <strong>Casella {idx + 1}</strong> &nbsp;•&nbsp; {label_colore_att}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Riga 1: Casella di testo bianca + Selezione colore
        col_txt, col_color = st.columns([2.5, 1.5])
        testo_precedente = opt.get("testo", "").strip()
        nuovo_testo = col_txt.text_input(
            f"Testo opzione {idx + 1}",
            value=opt.get("testo", ""),
            placeholder="Scrivi qui la scelta clinica...",
            key=f"opt_txt_{s_id}_{idx}",
            label_visibility="collapsed",
        )
        opt["testo"] = nuovo_testo

        # Se l'utente scrive un testo identico a un'opzione già esistente in un altro snodo, eredita automaticamente colore e snodo successivo!
        testo_pulito = nuovo_testo.strip()
        if testo_pulito and testo_pulito != testo_precedente and testo_pulito in opzioni_note:
            opt["colore"] = opzioni_note[testo_pulito]["colore"]
            opt["next"] = opzioni_note[testo_pulito]["next"]
            st.toast(f"Collegamento ereditato dallo snodo già esistente → {opt['next']}")
            st.rerun()

        scelta_colore = col_color.selectbox(
            f"Colore casella {idx + 1}",
            list(COLORI_CLINICI.keys()),
            index=list(COLORI_CLINICI.keys()).index(label_colore_att),
            key=f"opt_col_{s_id}_{idx}",
            label_visibility="collapsed",
        )
        cfg = COLORI_CLINICI[scelta_colore]
        if scelta_colore != "⬜ Da assegnare":
            opt["colore"] = cfg["codice"]
        opt["d_vit"] = cfg["d_vit"]
        opt["d_onc"] = cfg["d_onc"]
        opt["d_qol"] = cfg["d_qol"]
        opt["costo"] = cfg["costo"]

        # Riga 2: Dopo aver scritto e colorato -> scegli "Fine Caso" oppure "Prossimo Snodo"
        is_fine_caso = opt.get("next") in esiti_ids
        c_mode, c_dest, c_go = st.columns([1.3, 2.0, 0.9])

        modo = c_mode.radio(
            "Azione:",
            ["➡️ Prossimo Snodo", "🏁 Fine Caso"],
            index=1 if is_fine_caso else 0,
            horizontal=True,
            key=f"mode_{s_id}_{idx}",
            label_visibility="collapsed",
        )

        if modo == "🏁 Fine Caso":
            curr_esito = opt["next"] if opt.get("next") in esiti_ids else "esito_vittoria"
            opt["next"] = c_dest.selectbox(
                "Esito finale:",
                esiti_ids,
                index=esiti_ids.index(curr_esito),
                format_func=lambda e: esiti_labels.get(e, e),
                key=f"esito_sel_{s_id}_{idx}",
                label_visibility="collapsed",
            )
        else:
            CREA_NUOVO = "➕ Crea un nuovo snodo (4 nuove opzioni)..."
            altri_snodi = [n for n in lista_nodi if n != s_id]
            scelte_snodo = [CREA_NUOVO] + altri_snodi

            if opt.get("next") in altri_snodi:
                idx_dest = scelte_snodo.index(opt["next"])
            else:
                idx_dest = 0

            dest_scelta = c_dest.selectbox(
                "Snodo successivo:",
                scelte_snodo,
                index=idx_dest,
                format_func=lambda n: n if n == CREA_NUOVO else f"Collegato a: {n} ({dati['nodi'][n].get('titolo', '')[:30]})",
                key=f"snodo_sel_{s_id}_{idx}",
                label_visibility="collapsed",
            )

            if dest_scelta == CREA_NUOVO:
                if c_go.button("Crea & Apri ➡️", key=f"btn_crea_{s_id}_{idx}", use_container_width=True):
                    nuovo_id = _prossimo_id_snodo(dati["nodi"])
                    dati["nodi"][nuovo_id] = _nuovo_snodo_vuoto(nuovo_id, opt["testo"])
                    opt["next"] = nuovo_id
                    st.session_state.builder_active_node = nuovo_id
                    st.rerun()
            else:
                opt["next"] = dest_scelta
                if c_go.button("Apri Snodo ✏️", key=f"btn_apri_{s_id}_{idx}", use_container_width=True):
                    st.session_state.builder_active_node = dest_scelta
                    st.rerun()

    # -----------------------------------------------------------------------
    # 4. PERSONALIZZAZIONE TESTI ESITI FINALI
    # -----------------------------------------------------------------------
    with st.expander("🏁 Personalizza Commenti Finali (Tazza Bianca / Gialla / Rossa)", expanded=False):
        for e_id, esito in dati["esiti"].items():
            st.markdown(f"**{esiti_labels.get(e_id, e_id)}**")
            esito["descrizione"] = st.text_area(
                "Commento conclusivo per l'aula",
                value=esito["descrizione"],
                key=f"ed_{e_id}",
                height=70,
            )

    # -----------------------------------------------------------------------
    # 5. SALVATAGGIO SU GITHUB
    # -----------------------------------------------------------------------
    st.divider()
    # Filtra eventuali caselle lasciate completamente vuote prima di salvare
    dati_puliti = _pulisci_caselle_vuote(dati)
    codice_generato = f"CASO = {pprint.pformat(dati_puliti, width=100, sort_dicts=False)}\n"

    c_save, c_dl = st.columns(2)
    with c_save:
        if st.button("🚀 Salva su GitHub e Attiva in Aula", type="primary", use_container_width=True):
            if not file_id or not dati["titolo"]:
                st.error("Inserisci almeno il Codice Scenario (es. 002) e il Titolo.")
            else:
                os.makedirs(case_dir, exist_ok=True)
                percorso_locale = os.path.join(case_dir, f"{file_id}.py")
                with open(percorso_locale, "w", encoding="utf-8") as f:
                    f.write(codice_generato)

                percorso_repo = f"{case_dir}/{file_id}.py"
                ok, msg = _salva_su_github(
                    percorso_repo,
                    codice_generato,
                    f"Salvataggio caso clinico {file_id} da 2getSIM Editor",
                )
                if ok:
                    st.success(f"✅ {msg} Ora è selezionabile in aula.")
                else:
                    st.warning(f"⚠️ Salvato in locale nella sessione attuale, ma non su GitHub: {msg}")

    with c_dl:
        st.download_button(
            label=f"⬇️ Scarica copia {file_id or 'caso'}.py",
            data=codice_generato,
            file_name=f"{file_id or 'caso'}.py",
            mime="text/x-python",
            use_container_width=True,
        )


def _pulisci_caselle_vuote(dati):
    copia = json.loads(json.dumps(dati))
    for s_id, snodo in copia["nodi"].items():
        valide = [o for o in snodo["opzioni"] if o.get("testo", "").strip()]
        if valide:
            snodo["opzioni"] = valide
    return copia


def _genera_graphviz_dot(dati, rankdir="LR"):
    nodo_init = dati.get("nodo_iniziale", "snodo1")
    righe = [
        "digraph G {",
        f'  rankdir="{rankdir}";',
        '  bgcolor="transparent";',
        '  node [shape=box, style="rounded,filled", fontname="Inter,Arial", fontsize=11, margin="0.16,0.10"];',
        '  edge [fontname="Inter,Arial", fontsize=9, penwidth=1.6];',
    ]

    for s_id, snodo in dati.get("nodi", {}).items():
        titolo_breve = snodo.get("titolo", s_id).replace('"', "'")
        if len(titolo_breve) > 32:
            titolo_breve = titolo_breve[:29] + "..."
        label = f"{s_id}\\n{titolo_breve}"

        if s_id == st.session_state.get("builder_active_node"):
            fill, border, fontcol = "#e0e7ff", "#4338ca", "#1e1b4b"
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
        label = f"{esito.get('titolo', e_id)[:26]}"
        righe.append(
            f'  "{e_id}" [label="{label}", shape=oval, fillcolor="{fill}", color="{border}", penwidth=2, fontcolor="{fontcol}"];'
        )

    for s_id, snodo in dati.get("nodi", {}).items():
        for idx, opt in enumerate(snodo.get("opzioni", []), 1):
            txt = opt.get("testo", "").strip()
            if not txt:
                continue
            dest = opt.get("next", "")
            testo_opt = txt.replace('"', "'")
            if len(testo_opt) > 24:
                testo_opt = testo_opt[:21] + "..."
            label_col = _deduci_colore_da_delta(opt)
            edge_color = COLORI_CLINICI[label_col]["hex"]
            righe.append(
                f'  "{s_id}" -> "{dest}" [label="{idx}. {testo_opt}", color="{edge_color}", fontcolor="{edge_color}"];'
            )

    righe.append("}")
    return "\n".join(righe)


def _nuovo_snodo_vuoto(snodo_id, origine_testo=""):
    titolo_default = f"📍 {snodo_id.upper()}"
    if origine_testo:
        titolo_default += f" — Dopo: {origine_testo[:35]}"
    return {
        "titolo": titolo_default,
        "testo": "Descrivi cosa succede al paziente dopo questa scelta...",
        "opzioni": [
            {"testo": "", "colore": "", "d_vit": 0, "d_onc": -5, "d_qol": -5, "costo": 3500, "next": "esito_parziale"}
            for _ in range(4)
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
            "snodo1": _nuovo_snodo_vuoto("snodo1"),
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
