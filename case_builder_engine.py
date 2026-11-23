import base64, io, json, urllib.error, urllib.request, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
import streamlit as st
from google_db import carica_file_drive_su_gemini, elenca_documenti_bibliografia

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


def profondita_minima(dati: Dict[str, Any]) -> Tuple[int, int]:
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


def valida_v2(dati: Dict[str, Any]) -> Tuple[bool, List[str]]:
    err = []
    meta, nodi = dati.get("meta", {}), dati.get("nodi", {})
    if not meta.get("case_id") or not meta.get("titolo"):
        err.append("Mancano Codice Caso o Titolo.")
    if len(nodi) < 8:
        err.append(f"Snodi attuali {len(nodi)}: servono almeno 8-10 snodi.")
    m_all, m_nr = profondita_minima(dati)
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


def normalizza_json_importato(raw_text: str) -> Tuple[bool, Any]:
    try:
        t = raw_text.strip()
        if t.startswith("```"):
            t = t.strip("`").strip()
            if t.lower().startswith("json"):
                t = t[4:].strip()
        dati = json.loads(t)
        if not isinstance(dati, dict) or "nodi" not in dati or not isinstance(dati["nodi"], dict):
            return False, "Il JSON deve contenere la chiave 'nodi'."
        now = datetime.now(timezone.utc).isoformat()
        dati["schema_version"] = "2.0"
        meta = dati.setdefault("meta", {})
        meta.setdefault("case_id", "CASO_IMPORTATO")
        meta.setdefault("area_clinica", "vescica")
        meta["stato"] = "bozza"
        meta.setdefault("versione", 1)
        meta.setdefault("created_at", now)
        meta["updated_at"] = now
        dati.setdefault("nodo_iniziale", list(dati["nodi"].keys())[0])
        dati.setdefault("paziente_t0", {"vitalita_iniziale": 80, "oncologico_iniziale": 55, "qol_iniziale": 75, "scheda_paziente": ""})
        dati.setdefault("esiti", {
            "esito_vittoria": {"tipo": "bianco", "titolo": "ESITO OTTIMALE", "descrizione": "", "debriefing_master": ""},
            "esito_parziale": {"tipo": "giallo", "titolo": "ESITO INTERMEDIO", "descrizione": "", "debriefing_master": ""},
            "esito_sconfitta": {"tipo": "rosso", "titolo": "ESITO CRITICO", "descrizione": "", "debriefing_master": ""},
        })
        dati.setdefault("changelog_finetuning", [])
        return True, dati
    except Exception as e:
        return False, f"Errore lettura JSON: {e}"


def _estrai_allegati_locali(files: List[Any]) -> Tuple[List[Dict[str, Any]], str]:
    parti_bin, testi = [], []
    for f in files or []:
        nome = f.name.lower()
        raw = f.getvalue()
        if nome.endswith(".pdf"):
            parti_bin.append({"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(raw).decode("utf-8")}})
            testi.append(f"[Allegato PDF: {f.name}]")
        elif nome.endswith(".docx"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    xml_data = z.read("word/document.xml")
                root = ET.fromstring(xml_data)
                txt = " ".join(el.text for el in root.iter() if el.text)
                testi.append(f"--- CONTENUTO WORD ({f.name}) ---\n{txt[:25000]}")
            except Exception:
                pass
        elif nome.endswith(".txt") or nome.endswith(".md"):
            testi.append(f"--- CONTENUTO TESTO ({f.name}) ---\n{raw.decode('utf-8', errors='ignore')[:25000]}")
    return parti_bin, "\n\n".join(testi)


def parti_biblio(ambito: str, api_key: str) -> Tuple[List[Dict[str, Any]], List[str]]:
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


def gemini_json(parti: List[Dict[str, Any]], api_key: str, temp: float = 0.3) -> Tuple[bool, Any]:
    payload = {"contents": [{"parts": parti}], "generationConfig": {"temperature": temp, "responseMimeType": "application/json"}}
    last_err = ""
    for mod in ("gemini-2.5-flash", "gemini-2.5-pro"):
        url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){mod}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=150) as resp:
                txt = json.loads(resp.read().decode("utf-8"))["candidates"][0]["content"]["parts"][0]["text"].strip()
                return normalizza_json_importato(txt)
        except urllib.error.HTTPError as e:
            last_err = f"Errore Gemini ({e.code}): {e.read().decode('utf-8', errors='ignore')[:180]}"
            if e.code != 404:
                break
        except Exception as e:
            last_err = f"Errore Gemini: {e}"
            break
    return False, last_err


def genera_caso_ai(cid: str, ambito: str, spunto: str, n_snodi: int = 9, allegati_locali: List[Any] = None, usa_biblio_drive: bool = True) -> Tuple[bool, Any]:
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False, "Manca GEMINI_API_KEY nei Secrets."
    parti_b, nomi = parti_biblio(ambito, api_key) if usa_biblio_drive else ([], [])
    parti_loc, testi_loc = _estrai_allegati_locali(allegati_locali or [])
    fonti = ", ".join(nomi) if nomi else "Documenti allegati / Linee Guida EAU-ESMO"
    prompt = (
        f"Direttore Scientifico 2getSIM. Genera JSON v2.0 da Fonti ({fonti}).\n"
        f"case_id='{cid}', area_clinica='{ambito}', snodi longitudinali={n_snodi} (min 8, max 10).\n"
        f"TESTO / SPUNTO CLINICO:\n{spunto}\n{testi_loc}\n"
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
    ok, res = gemini_json([*parti_b, *parti_loc, {"text": prompt}], api_key, 0.35)
    if not ok:
        return False, res
    res["meta"]["case_id"] = cid
    res["meta"]["area_clinica"] = ambito
    return True, res


def genera_3_opzioni_snodo(dati: Dict[str, Any], sid: str, verde: str) -> Tuple[bool, Any]:
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False, "Manca GEMINI_API_KEY."
    parti_b, _ = parti_biblio(dati.get("meta", {}).get("area_clinica", "vescica"), api_key)
    sn = dati["nodi"][sid]
    prompt = (
        f"Paziente T0: {dati.get('paziente_t0', {}).get('scheda_paziente', '')}\n"
        f"Snodo ({sn.get('titolo', '')}): {sn.get('testo', '')}\nOpzione VERDE: '{verde}'\n"
        'Genera 3 alternative (blu, gialla, rossa) di 2-6 parole ciascuna + razionale EAU/ESMO/RCP. Rispondi SOLO JSON: {"blu":{"testo":"","razionale":""},"gialla":{"testo":"","razionale":""},"rossa":{"testo":"","razionale":""}}'
    )
    payload = {"contents": [{"parts": [*parti_b, {"text": prompt}]}], "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}}
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=){api_key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            txt = json.loads(resp.read().decode("utf-8"))["candidates"][0]["content"]["parts"][0]["text"].strip().strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
            res = json.loads(txt)
            if all(k in res and "testo" in res[k] for k in ("blu", "gialla", "rossa")):
                return True, res
    except Exception as e:
        return False, f"Errore Gemini: {e}"
    return False, "Risposta AI incompleta."


def dot_graphviz(dati: Dict[str, Any]) -> str:
    r = ['digraph G { rankdir="LR"; bgcolor="transparent"; node [shape=box,style="rounded,filled",fontname="Inter,Arial",fontsize=10]; edge [fontsize=9];']
    for sid, sn in dati.get("nodi", {}).items():
        tit = sn.get("titolo", sid).replace('"', "'")[:28]
        fill = "#e0e7ff" if sid == st.session_state.get("builder_active_node") else "#f8fafc"
        r.append(f'"{sid}" [label="{sid}\\n{tit}",fillcolor="{fill}"];')
    for eid, es in dati.get("esiti", {}).items():
        c = "#dcfce7" if es.get("tipo") == "bianco" else ("#fef9c3" if es.get("tipo") == "giallo" else "#fee2e2")
        r.append(f'"{eid}" [label="{es.get("titolo", eid)[:24]}",shape=oval,fillcolor="{c}"];')
    for sid, sn in dati.get("nodi", {}).items():
        for i, o in enumerate(sn.get("opzioni", []), 1):
            if o.get("testo", "").strip():
                col = COLORI_CLINICI[MAPPA_COD_LBL.get(o.get("colore", "blu"), MAPPA_COD_LBL["blu"])]["hex"]
                r.append(f'"{sid}" -> "{o.get("next", "")}" [label="{i}. {o["testo"].replace(chr(34), chr(39))}",color="{col}",fontcolor="{col}"];')
    return "\n".join(r + ["}"])


def nuovo_snodo(sid: str, nxt: str = "esito_parziale") -> Dict[str, Any]:
    opts = []
    for c in ORDINE_4:
        cfg = COLORI_CLINICI[MAPPA_COD_LBL[c]]
        opts.append({"testo": "", "colore": c, "d_vit": cfg["d_vit"], "d_onc": cfg["d_onc"], "d_qol": cfg["d_qol"], "effetto_ritardato": c in ("blu", "giallo"), "razionale": "", "next": nxt})
    return {"titolo": f"📍 {sid.upper()}", "testo": "", "is_post_rosso": False, "opzioni": opts}


def template_v2(cid: str = "CASO_01", n: int = 8) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    nodi = {f"snodo{i}": nuovo_snodo(f"snodo{i}", f"snodo{i+1}" if i < n else "esito_vittoria") for i in range(1, n + 1)}
    return {
        "schema_version": "2.0",
        "meta": {"case_id": cid, "area_clinica": "vescica", "stato": "bozza", "versione": 1, "titolo": "", "sottotitolo": "", "descrizione_master": "", "audit_clinico": "", "created_at": now, "updated_at": now},
        "paziente_t0": {"vitalita_iniziale": 80, "oncologico_iniziale": 55, "qol_iniziale": 75, "calibrazione_t0": {"vitalita_motivo": "", "oncologico_motivo": "", "qol_motivo": ""}, "scheda_paziente": "", "mine_psicologiche": {"trappola_urologo": "", "trappola_oncologo": ""}},
        "nodo_iniziale": "snodo1",
        "nodi": nodi,
        "esiti": {
            "esito_vittoria": {"tipo": "bianco", "titolo": "ESITO OTTIMALE", "descrizione": "", "debriefing_master": ""},
            "esito_parziale": {"tipo": "giallo", "titolo": "ESITO INTERMEDIO", "descrizione": "", "debriefing_master": ""},
            "esito_sconfitta": {"tipo": "rosso", "titolo": "ESITO CRITICO", "descrizione": "", "debriefing_master": ""},
        },
        "changelog_finetuning": [],
    }
