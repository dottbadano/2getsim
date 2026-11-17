import base64
import importlib
import json
import os
import pprint
import urllib.error
import urllib.request
import streamlit as st

COLORI_CLINICI = {
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

MAPPA_CODICE_TO_LABEL = {v["codice"]: k for k, v in COLORI_CLINICI.items()}


def _salva_su_github(percorso_repo, contenuto_testo, messaggio_commit):
    """Esegue un commit diretto su GitHub usando i Secrets di Streamlit."""
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

    # 1. Verifica se il file esiste già su GitHub per ottenerne lo 'sha' (necessario per sovrascriverlo)
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

    # 2. Invia il nuovo file o l'aggiornamento via PUT
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
    """Calcola automaticamente il codice successivo (es. 002 se esiste 001)."""
    numeri = [int(f) for f in existing_files if f.isdigit()]
    prossimo = max(numeri) + 1 if numeri else 1
    return f"{prossimo:03d}"


def _deduci_colore_da_delta(opt):
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
        "Scrivi l'anamnesi, inserisci le 4 scelte per ogni snodo assegnando il colore clinico (Verde, Blu, Gialla, Rossa) e salva direttamente su GitHub."
    )

    existing_files = sorted(
        [f[:-3] for f in os.listdir(case_dir) if f.endswith(".py") and f != "__init__"]
    )

    if "builder_caso" not in st.session_state:
        st.session_state.builder_caso = _template_vuoto()
    if "builder_file_id" not in st.session_state:
        st.session_state.builder_file_id = _prossimo_codice_disponibile(existing_files)

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
        st.rerun()

    if c_load3.button("🆕 Azzera Tutto", use_container_width=True):
        st.session_state.builder_caso = _template_vuoto()
        st.session_state.builder_file_id = _prossimo_codice_disponibile(existing_files)
        st.rerun()

    dati = st.session_state.builder_caso

    # 1. ANAMNESI E INTESTAZIONE
    with st.expander("1️⃣ Step 1 — Anamnesi Paziente & Dati Caso", expanded=True):
        c1, c2 = st.columns([1, 2])
        file_id = c1.text_input(
            "Codice Scenario (es. 002, 003, 004)", value=st.session_state.builder_file_id
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

    # DIAGRAMMA DI FLUSSO LIVE COLORATO
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

    # 2. SNODI E LE 4 SCELTE COLORATE PER CIASCUNO SNODO
    with st.
