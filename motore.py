import json
from collections import deque
import streamlit as st


def normalizza_json(raw_text: str):
    """Pulisce il testo incollato (anche con blocchi markdown) e normalizza v1 -> v2.0."""
    if not raw_text or not raw_text.strip():
        return None, "Incolla un JSON oppure carica un file .json dalla barra laterale."

    testo = raw_text.strip()
    if testo.startswith("```"):
        righe = testo.splitlines()
        if righe[0].startswith("```"):
            righe = righe[1:]
        if righe and righe[-1].strip().startswith("```"):
            righe = righe[:-1]
        testo = "\n".join(righe).strip()

    try:
        dati = json.loads(testo)
    except json.JSONDecodeError as e:
        return None, f"Errore di sintassi JSON alla riga {e.lineno}, colonna {e.colno}: {e.msg}"

    if not isinstance(dati, dict):
        return None, "Il JSON deve essere un oggetto principale con parentesi graffe { ... }."

    # Retrocompatibilita: se 'nodi' e una lista (vecchio formato v1), la converte in dizionario v2.0
    nodi_raw = dati.get("nodi")
    if isinstance(nodi_raw, list):
        nodi_dict = {}
        for i, item in enumerate(nodi_raw, start=1):
            key = item.get("id") or f"snodo{i}"
            opzioni_norm = []
            for j, op in enumerate(item.get("opzioni", [])):
                next_id = op.get("next")
                if not next_id:
                    next_id = f"snodo{i+1}" if i < len(nodi_raw) else "esito_vittoria"
                opzioni_norm.append({
                    "testo": op.get("testo", f"Opzione {j+1}"),
                    "colore": op.get("colore", "blu"),
                    "d_vit": int(op.get("d_vit", 0)),
                    "d_onc": int(op.get("d_onc", 0)),
                    "d_qol": int(op.get("d_qol", 0)),
                    "effetto_ritardato": bool(op.get("effetto_ritardato", False)),
                    "razionale": op.get("razionale", ""),
                    "next": next_id,
                })
            nodi_dict[key] = {
                "titolo": item.get("titolo", f"Snodo {i}"),
                "testo": item.get("testo", ""),
                "opzioni": opzioni_norm,
            }
        dati["nodi"] = nodi_dict
        if not dati.get("nodo_iniziale") and nodi_dict:
            dati["nodo_iniziale"] = list(nodi_dict.keys())[0]

    if not isinstance(dati.get("nodi"), dict) or not dati["nodi"]:
        return None, "Manca la sezione 'nodi' oppure e vuota."

    dati.setdefault("meta", {
        "case_id": "CASO_2GETSIM",
        "titolo": "Nuovo Caso Clinico",
        "sottotitolo": "Simulazione Uro-Oncologica",
        "area_clinica": "urologia",
    })
    dati.setdefault("paziente_t0", {
        "vitalita_iniziale": 85,
        "oncologico_iniziale": 65,
        "qol_iniziale": 85,
        "scheda_paziente": "Inserisci anamnesi ed esami generici T0.",
        "mine_psicologiche": {
            "trappola_urologo": "",
            "trappola_oncologo": "",
        },
    })
    dati.setdefault("esiti", {
        "esito_vittoria": {
            "titolo": "Esito Ottimale",
            "descrizione": "Percorso diagnostico-terapeutico appropriato.",
            "debriefing_master": "Messaggio chiave per l'aula.",
        },
        "esito_parziale": {
            "titolo": "Esito Intermedio",
            "descrizione": "Controllo parziale con margine di miglioramento.",
            "debriefing_master": "Discussione sulle alternative.",
        },
        "esito_sconfitta": {
            "titolo": "Esito Sfavorevole",
            "descrizione": "Complicanza grave o progressione.",
            "debriefing_master": "Analisi degli errori critici.",
        },
    })

    chiavi = list(dati["nodi"].keys())
    if dati.get("nodo_iniziale") not in dati["nodi"]:
        dati["nodo_iniziale"] = chiavi[0]

    return dati, None


def valida_regole_peppiniello(caso: dict) -> list:
    """Verifica tutte le regole cliniche e strutturali richieste per 2getSIM."""
    controlli = []
    nodi = caso.get("nodi", {})
    start = caso.get("nodo_iniziale")

    # 1. Verifica 4 opzioni per ogni snodo
    nodi_non_4 = [k for k, v in nodi.items() if len(v.get("opzioni", [])) != 4]
    if not nodi_non_4:
        controlli.append(("ok", f"Tutti i {len(nodi)} snodi hanno esattamente 4 opzioni."))
    else:
        controlli.append(("err", f"Snodi senza 4 opzioni: {', '.join(nodi_non_4)}."))

    # 2. Verifica collegamenti 'next' validi
    link_rotti = []
    for k, v in nodi.items():
        for idx, op in enumerate(v.get("opzioni", []), start=1):
            nxt = op.get("next", "")
            if not nxt.startswith("esito_") and nxt not in nodi:
                link_rotti.append(f"{k} (opz {idx} -> '{nxt}')")
    if not link_rotti:
        controlli.append(("ok", "Tutti i collegamenti tra snodi ed esiti sono integri."))
    else:
        controlli.append(("err", f"Collegamenti inesistenti: {', '.join(link_rotti)}."))

    # 3. Verifica divieto di opzione 'verde' subito dopo una scelta 'rosso'
    violazioni_rosso = []
    for k, v in nodi.items():
        for op in v.get("opzioni", []):
            if op.get("colore") == "rosso":
                nxt = op.get("next", "")
                if nxt in nodi:
                    colori_next = [o.get("colore") for o in nodi[nxt].get("opzioni", [])]
                    if "verde" in colori_next:
                        violazioni_rosso.append(f"{k} (rosso) -> {nxt} contiene opzione verde")
    if not violazioni_rosso:
        controlli.append(("ok", "Regola post-errore rispettata: nessuna opzione verde dopo una rossa."))
    else:
        controlli.append(("err", f"Violazione post-rosso: {'; '.join(violazioni_rosso)}."))

    # 4. Calcolo percorso piu breve (BFS) per verificare minimo 8 snodi
    if start in nodi:
        coda = deque([(start, 1, {start})])
        min_passi = None
        while coda:
            curr, passi, visitati = coda.popleft()
            for op in nodi.get(curr, {}).get("opzioni", []):
                nxt = op.get("next", "")
                if nxt.startswith("esito_") or nxt not in nodi:
                    if min_passi is None or passi < min_passi:
                        min_passi = passi
                elif nxt not in visitati:
                    coda.append((nxt, passi + 1, visitati | {nxt}))
        if min_passi is not None and min_passi >= 8:
            controlli.append(("ok", f"Profondita minima verificata: {min_passi} snodi prima dell'esito."))
        elif min_passi is not None:
            controlli.append(("warn", f"Percorso piu breve di soli {min_passi} snodi (consigliati almeno 8)."))

    return controlli


def salva_su_drive(caso: dict, filename: str):
    """Salva il JSON su Google Drive se le credenziali sono presenti in st.secrets."""
    try:
        if "gcp_service_account" not in st.secrets:
            return False, "Credenziali Google Drive non configurate nei Secrets di Streamlit. Usa il pulsante 'Scarica JSON v2.0'."

        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload

        creds_info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=["[https://www.googleapis.com/auth/drive.file](https://www.googleapis.com/auth/drive.file)"]
        )
        service = build("drive", "v3", credentials=creds)

        file_metadata = {"name": filename}
        folder_id = st.secrets.get("drive_folder_id")
        if folder_id:
            file_metadata["parents"] = [folder_id]

        contenuto = json.dumps(caso, ensure_ascii=False, indent=2).encode("utf-8")
        media = MediaInMemoryUpload(contenuto, mimetype="application/json", resumable=False)

        created = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        return True, f"Salvato su Google Drive (ID: {created.get('id')})."
    except Exception as e:
        return False, f"Errore salvataggio Drive: {e}"


def caso_esempio_v2() -> dict:
    """Restituisce un caso base v2.0 valido per test immediato."""
    return {
        "meta": {
            "case_id": "DEMO_2GETSIM_01",
            "titolo": "Ematuria e Terapia Tailored",
            "sottotitolo": "Percorso diagnostico-terapeutico in 8 snodi",
            "area_clinica": "urologia",
        },
        "paziente_t0": {
            "vitalita_iniziale": 85,
            "oncologico_iniziale": 65,
            "qol_iniziale": 85,
            "scheda_paziente": "Uomo di 71 anni, ex fumatore (35 pack-years). Giunge per macroematuria monosintomatica.\nAnamnesi: cardiopatia ischemica con stent medicato (in doppia antiaggregazione), eGFR 42 ml/min.\nEsami generici: Hb 12.4 g/dL, creatinina 1.65 mg/dL. Nessuna diagnosi istologica ancora eseguita.",
            "mine_psicologiche": {
                "trappola_urologo": "Procedere a chirurgia demolitiva o resettiva senza gestire la doppia antiaggregazione e senza stadiazione corretta.",
                "trappola_oncologo": "Proporre chemioterapia sistemica cisplatin-based nonostante eGFR 42 ml/min e cardiopatia.",
            },
        },
        "nodo_iniziale": "snodo1",
        "nodi": {
            f"snodo{i}": {
                "titolo": f"Snodo {i}",
                "testo": f"Snodo {i} di esempio: seleziona la condotta clinica piu appropriata per il paziente.",
                "opzioni": [
                    {
                        "testo": "Condotta ottimale personalizzata sul paziente",
                        "colore": "verde",
                        "d_vit": 0,
                        "d_onc": 5,
                        "d_qol": 0,
                        "effetto_ritardato": False,
                        "razionale": "Scelta coerente con funzione renale e assetto cardiovascolare.",
                        "next": f"snodo{i+1}" if i < 8 else "esito_vittoria",
                    },
                    {
                        "testo": "Condotta prudente ma subottimale",
                        "colore": "blu",
                        "d_vit": 0,
                        "d_onc": 0,
                        "d_qol": -5,
                        "effetto_ritardato": False,
                        "razionale": "Rallenta leggermente l'iter senza creare danni maggiori.",
                        "next": f"snodo{i+1}" if i < 8 else "esito_parziale",
                    },
                    {
                        "testo": "Applicazione meccanica linea guida senza adattamento",
                        "colore": "giallo",
                        "d_vit": -10,
                        "d_onc": 0,
                        "d_qol": -10,
                        "effetto_ritardato": False,
                        "razionale": "Espone a tossicita renale o emorragica.",
                        "next": f"snodo{i+1}" if i < 8 else "esito_parziale",
                    },
                    {
                        "testo": "Scelta controindicata per anamnesi T0",
                        "colore": "rosso",
                        "d_vit": -20,
                        "d_onc": -15,
                        "d_qol": -15,
                        "effetto_ritardato": False,
                        "razionale": "Ignora le comorbidita critiche segnalate in T0.",
                        "next": f"snodo{i+1}" if i < 8 else "esito_sconfitta",
                    },
                ],
            }
            for i in range(1, 9)
        },
        "esiti": {
            "esito_vittoria": {
                "titolo": "Gestione Tailored Ottimale",
                "descrizione": "Diagnosi accurata e terapia adattata alle comorbidita del paziente.",
                "debriefing_master": "La personalizzazione sull'anamnesi T0 ha evitato tossicita gravi.",
            },
            "esito_parziale": {
                "titolo": "Gestione Parziale",
                "descrizione": "Controllo oncologico raggiunto ma con impatto evitabile su vitalita o QoL.",
                "debriefing_master": "Rivedere le controindicazioni relative in T0.",
            },
            "esito_sconfitta": {
                "titolo": "Complicanza Grave / Progressione",
                "descrizione": "Le scelte non calibrate sull'anamnesi hanno compromesso il quadro clinico.",
                "debriefing_master": "Confronto tra linea guida astratta e paziente reale.",
            },
        },
    }
