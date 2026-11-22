import base64, json, os, pprint, urllib.error, urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
import streamlit as st
from google_db import (
    carica_caso_drive, carica_file_drive_su_gemini, carica_immagine_drive,
    elenca_casi_drive, elenca_documenti_bibliografia, pubblica_caso_enterprise,
    ritira_caso_in_bozza, salva_caso_drive, scarica_immagine_drive,
)

COLORI_CLINICI = {
    "🟩 Verde — Esatta (Tailored ottimale)": {"codice": "verde", "d_vit": 5, "d_onc": 15, "d_qol": 5, "hex": "#16a34a", "bg": "#dcfce7"},
    "🟦 Blu — Ridondante / Difensiva": {"codice": "blu", "d_vit": 0, "d_onc": -5, "d_qol": -5, "hex": "#2563eb", "bg": "#dbeafe"},
    "🟨 Gialla — Trappola Linea Guida": {"codice": "giallo", "d_vit": -10, "d_onc": -15, "d_qol": -25, "hex": "#ca8a04", "bg": "#fef9c3"},
    "🟥 Rossa — Sbagliata / Pericolosa": {"codice": "rosso", "d_vit": -20, "d_onc": -30, "d_qol": -20, "hex": "#dc2626", "bg": "#fee2e2"},
}
MAPPA_COD_LBL = {v["codice"]: k for k, v in COLORI_CLINICI.items()}
ORDINE_4 = ["verde", "blu", "giallo", "rosso"]
AMBITI = {"vescica": "🫧 Vescica / Urotelio", "prostata": "🩺 Prostata", "rene": "🫘 Rene / UTUC"}
KW_VESCICA = ("vescic", "bladder", "nmibc", "mibc", "urotel", "urothel", "utuc", "enfortumab", "pembrolizumab", "avelumab", "durvalumab", "nivolumab", "erdafitinib", "cisplat", "gemcitab", "bcg", "ev-302", "niagara")
KW_PROSTATA = ("prostat", "mcrpc", "mcspc", "mhspc", "nmcrpc", "apalutamid", "darolutamid", "enzalutamid", "abirateron", "olaparib", "talazoparib", "niraparib", "docetaxel", "cabazitaxel", "relugolix", "radium", "pluvicto", "psma", "peace", "aranote", "arasens", "titan", "embark")


def _profondita_minima(dati: Dict[str, Any]) -> Tuple[int, int]:
    nodi, esiti = dati.get("nodi", {}), set(dati.get("esiti", {}).keys())
    start = dati.get("nodo_iniziale", "snodo1")
    if start not in nodi:
        return 0, 0
    min_all, min_non_red = 999, 999

    def dfs(curr: str, d: int, all_red: bool, vis: set):
        nonlocal min_all, min_non_red
        if curr in esiti:
            min_all = min(min_all, d)
            if not all_red:
                min_non_red = min(min_non_red, d)
            return
        if curr not in nodi or curr in vis or d > 20:
            return
        for o in nodi[curr].get("opzioni", []):
            if o.get("testo", "").strip():
                dfs(o.get("next", ""), d + 1, all_red and (o.get("colore") == "rosso"), vis | {curr})

    dfs(start, 0, True, set())
    return (0 if min_all == 999 else min_all), (0 if min_non_red == 999 else min_non_red)


def _valida_v2(dati: Dict[str, Any]) -> Tuple[bool, List[str]]:
    err = []
    meta, t0, nodi = dati.get("meta", {}), dati.get("paziente_t0", {}), dati.get("nodi", {})
    if not meta.get("case_id") or not meta.get("titolo"):
        err.append("Mancano Codice Caso o Titolo.")
    if len(nodi) < 8:
        err.append(f"Snodi attuali {len(nodi)}: servono almeno 8-10 snodi.")
    m_all, m_nr = _profondita_minima(dati)
    if 0 < m_all < 6:
        err.append(f"Un percorso chiude allo snodo {m_all}: anche sempre Rosso deve durare min. 6 snodi.")
    if 0 < m_nr < 8:
        err.append(f"Un percorso non-Rosso chiude allo snodo {m_nr}: deve durare almeno 8-10 snodi.")
    for sid, sn in nodi.items():
        opts = [o for o in sn.get("opzioni", []) if o.get("testo", "").strip()]
        if len(opts) != 4:
            err.append(f"{sid}: servono 4 opzioni compilate (attuali: {len(opts)}).")
            continue
        cols = [o.get("colore", "") for o in opts]
        if sn.get("is_post_rosso") and not (cols.count("verde") == 0 and cols.count("blu") == 2 and cols.count("giallo") == 1 and cols.count("rosso") == 1):
            err.append(f"{sid} (post-Rosso): richiesti 0V / 2B / 1G / 1R.")
        for i, o in enumerate(opts, 1):
            w = len(o["testo"].split())
            if w < 2 or w > 7:
                err.append(f"{sid} opz.{i} ('{o['testo']}'): target 2-6 parole ({w}).")
    return len(err) == 0, err


def _parti_biblio(ambito: str, api_key: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    parti, nomi = [], []
    try:
        for d in elenca_documenti_bibliografia():
            nl = d["name"].lower()
            v, p = any(k in nl for k in KW_VESCICA), any(k in nl for k in KW_PROSTATA)
            if (ambito == "vescica" and not v and p) or (ambito == "prostata" and not p and v):
                continue
            try:
                uri = carica_file_drive_su_gemini(d["id"], d["name"], d["mimeType"], api_key)
                parti.append({"file_data": {"mime_type": d["mimeType"], "file_uri": uri}})
                nomi.append(f"[{d['categoria']}] {d['name']}")
            except Exception:
                pass
    except Exception:
        pass
    return parti, nomi


def _gemini_json(parti: List[Dict[str, Any]], api_key: str, temp: float = 0.3) -> Tuple[bool, Any]:
    payload = {"contents": [{"parts": parti}], "generationConfig": {"temperature": temp, "responseMimeType": "application/json"}}
    last_err = ""
    for mod in ("gemini-2.5-pro", "gemini-2.5-flash"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=150) as resp:
                txt = json.loads(resp.read().decode("utf-8"))["candidates"][0]["content"]["parts"][0]["text"].strip()
                if txt.startswith("```"):
                    txt = txt.strip("`").strip()
                    if txt.lower().startswith("json"):
                        txt = txt[4:].strip()
                return True, json.loads(txt)
        except urllib.error.HTTPError as e:
            last_err = f"Errore Gemini ({e.code}): {e.read().decode('utf-8', errors='ignore')[:180]}"
            if e.code != 404:
                break
        except Exception as e:
            last_err = f"Errore Gemini: {e}"
            break
    return False, last_err


def _genera_caso_ai(cid: str, ambito: str, spunto: str, n_snodi: int = 9) -> Tuple[bool, Any]:
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False, "Manca GEMINI_API_KEY nei Secrets."
    parti_b, nomi = _parti_biblio(ambito, api_key)
    fonti = ", ".join(nomi) if nomi else "Linee Guida EAU/ESMO"
    prompt = (
        f"Direttore Scientifico 2getSIM. Genera JSON v2.0 da Biblioteca PDF ({fonti}).\n"
        f"case_id='{cid}', area_clinica='{ambito}', snodi longitudinali={n_snodi} (min 8, max 10). Spunto: {spunto}\n"
        "REGOLE INDEROGABILI:\n"
        f"1. DURATA: percorsi verde/blu/giallo DEVONO durare 8-10 snodi (snodo1..snodo{n_snodi}); NESSUN esito_* prima di snodo8. Anche scegliendo sempre rosso, passaggio su snodi is_post_rosso=true e chiusura esito_sconfitta solo dal 6° snodo in poi.\n"
        "2. T0 (30enne sano=100/100/100): sottrai punti reali per età/eGFR/comorbidità/carico e documenta in calibrazione_t0.\n"
        "3. MINE PSICOLOGICHE: trappola_urologo e trappola_oncologo; opzioni giallo e blu con effetto_ritardato=true.\n"
        "4. OPZIONI: 4 per snodo (verde,blu,giallo,rosso), comando operativo secco 2-6 parole, zero parentesi, con razionale.\n"
        "5. POST-ROSSO (is_post_rosso=true): 0 verde, 2 blu, 1 giallo, 1 rosso.\n"
        'Schema JSON esatto: {"schema_version":"2.0","meta":{"case_id":"","area_clinica":"","stato":"bozza","versione":1,"titolo":"","sottotitolo":"","descrizione_master":"","audit_clinico":""},'
        '"paziente_t0":{"vitalita_iniziale":80,"oncologico_iniziale":55,"qol_iniziale":75,"calibrazione_t0":{"vitalita_motivo":"","oncologico_motivo":"","qol_motivo":""},"scheda_paziente":"","mine_psicologiche":{"trappola_urologo":"","trappola_oncologo":""}},'
        '"nodo_iniziale":"snodo1","nodi":{"snodo1":{"titolo":"","testo":"","is_post_rosso":false,"opzioni":[{"testo":"2-6 parole","colore":"verde","d_vit":5,"d_onc":15,"d_qol":5,"effetto_ritardato":false,"razionale":"","next":"snodo2"}]}},'
        '"esiti":{"esito_vittoria":{"tipo":"bianco","titolo":"ESITO OTTIMALE","descrizione":"","debriefing_master":""},"esito_parziale":{"tipo":"giallo","titolo":"ESITO INTERMEDIO","descrizione":"","debriefing_master":""},"esito_sconfitta":{"tipo":"rosso","titolo":"ESITO CRITICO","descrizione":"","debriefing_master":""}}}'
    )
    ok, res = _gemini
