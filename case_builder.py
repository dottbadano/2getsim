import base64
import importlib
import json
import os
import pprint
import urllib.error
import urllib.request
import streamlit as st

try:
    from google_db import carica_immagine_drive, scarica_immagine_drive
    GDRIVE_IMG_ATTIVO = True
except Exception:
    GDRIVE_IMG_ATTIVO = False

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

    # -----------------------------------------------------------------------
    # IMMAGINE RADIOLOGICA / CLINICA DELLO SNODO (SALVATA SU GOOGLE DRIVE)
    # -----------------------------------------------------------------------
    img_attuale = snodo.get("immagine", "")
    with st.expander(
        "🖼️ Immagine collegata a questo snodo ✅" if img_attuale else "➕ Allega immagine radiologica / clinica (salvata su Drive)",
        expanded=bool(img_attuale),
    ):
        if img_attuale:
            if img_attuale.startswith("drive:") and GDRIVE_IMG_ATTIVO:
                try:
                    st.image(scarica_immagine_drive(img_attuale), width=320)
                except Exception:
                    st.caption(f"Riferimento salvato: `{img_attuale}`")
            elif os.path.exists(img_attuale):
                st.image(img_attuale, width=320)

            if st.button("🗑️ Rimuovi immagine da questo snodo", key=f"rm_img_{s_id}"):
                snodo.pop("immagine", None)
                st.rerun()

        if GDRIVE_IMG_ATTIVO:
            up_file = st.file_uploader(
                "Seleziona RM, TC, endoscopia o schema (PNG, JPG, WEBP)",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"up_img_{s_id}",
            )
            if up_file is not None:
                st.image(up_file, width=260, caption="Anteprima file pronto per l'upload")
                if st.button("☁️ Carica su Drive e collega allo snodo", type="primary", key=f"save_img_{s_id}"):
                    with st.spinner("Salvataggio immagine su Google Drive in corso..."):
                        try:
                            ref_drive = carica_immagine_drive(up_file, file_id or "caso", s_id)
                            snodo["immagine"] = ref_drive
                            st.success("✅ Immagine salvata su Drive e collegata allo snodo!")
                            st.rerun()
                        except Exception as err:
                            st.error(f"Errore durante il caricamento su Drive: {err}")
        else:
            st.warning("⚠️ Modulo google_db.py non attivo: verifica la connessione Google Drive.")

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
                esiti_
