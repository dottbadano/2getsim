import base64
import json
import os
import pprint
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import streamlit as st

from google_db import (
    carica_caso_drive,
    carica_file_drive_su_gemini,
    carica_immagine_drive,
    elenca_casi_drive,
    elenca_documenti_bibliografia,
    pubblica_caso_enterprise,
    ritira_caso_in_bozza,
    salva_caso_drive,
    scarica_immagine_drive,
)

COLORI_CLINICI = {
    "🟩 Verde — Esatta (Condotta tailored ottimale)": {
        "codice": "verde",
        "d_vit": 5,
        "d_onc": 15,
        "d_qol": 5,
        "hex": "#16a34a",
        "bg": "#dcfce7",
    },
    "🟦 Blu — Ridondante / Difensiva (Esame in più, fa perdere tempo)": {
        "codice": "blu",
        "d_vit": 0,
        "d_onc": -5,
        "d_qol": -5,
        "hex": "#2563eb",
        "bg": "#dbeafe",
    },
    "🟨 Gialla — Trappola Linea Guida (Ammessa da LG, ma tossica/inadeguata qui)": {
        "codice": "giallo",
        "d_vit": -10,
        "d_onc": -15,
        "d_qol": -25,
        "hex": "#ca8a04",
        "bg": "#fef9c3",
    },
    "🟥 Rossa — Sbagliata (Errore clinico grave / Pericolosa)": {
        "codice": "rosso",
        "d_vit": -20,
        "d_onc": -30,
        "d_qol": -20,
        "hex": "#dc2626",
        "bg": "#fee2e2",
    },
}

MAPPA_CODICE_TO_LABEL = {v["codice"]: k for k, v in COLORI_CLINICI.items()}
ORDINE_DEFAULT_4 = ["verde", "blu", "giallo", "rosso"]

AMBITI_PATOLOGIA = {
    "vescica": "🫧 Vescica / Carcinoma Uroteliale",
    "prostata": "🩺 Prostata",
    "rene": "🫘 Rene / Urotelio Alto",
}

KEYWORDS_VESCICA = (
    "vescic", "bladder", "nmibc", "mibc", "urotel", "urothel", "utuc",
    "enfortumab", "padcev", "pembrolizumab", "keytruda", "avelumab", "bavencio",
    "durvalumab", "imfinzi", "nivolumab", "opdivo", "erdafitinib", "balversa",
    "cisplat", "carboplat", "gemcitab", "mitomicin", "mitomycin", "bcg",
    "nadofaragene", "cretostimogene", "nogapendekin", "ev-302", "niagara",
    "checkmate-274", "javelin", "ambassador", "thor", "sunrise",
)

KEYWORDS_PROSTATA = (
    "prostat", "mcrpc", "mcspc", "mhspc", "nmcrpc", "bcr",
    "apalutamid", "erleada", "darolutamid", "nubeqa", "enzalutamid", "xtandi",
    "abirateron", "zytiga", "olaparib", "lynparza", "talazoparib", "talzenna",
    "niraparib", "akeega", "docetaxel", "taxotere", "cabazitaxel", "jevtana",
    "eligard", "leuprorelin", "enantone", "decapeptyl", "triptorelin",
    "degarelix", "firmagon", "relugolix", "orgovyx", "bicalutamid", "casodex",
    "xofigo", "radium", "radio-223", "pluvicto", "lutezio", "lutetium", "psma",
    "peace", "aranote", "arasens", "titan", "latitude", "stampede", "propel",
    "magnitude", "talapro", "vision", "psmafore", "proteus", "dasl", "embark",
    "capitello", "capivasertib",
)


# ==============================================================================
# 1. VALIDAZIONE CONTRATTO JSON v2.0 (INCLUSA PROFONDITÀ 8-10 / MIN 6 ROSSO)
# ==============================================================================

def _calcola_profondita_minima_esiti(dati: Dict[str, Any]) -> Tuple[int, int]:
    """Restituisce (profondita_minima_assoluta, profondita_minima_non_rosso) dal nodo iniziale."""
    nodi = dati.get("nodi", {})
    esiti = set(dati.get("esiti", {}).keys())
    start = dati.get("nodo_iniziale", "snodo1")
    if start not in nodi:
        return 0, 0

    min_assoluta = 999
    min_non_rosso = 999

    def _dfs(curr: str, depth: int, solo_rosso: bool, visited: set):
        nonlocal min_assoluta, min_non_rosso
        if curr in esiti:
            min_assoluta = min(min_assoluta, depth)
            if not solo_rosso:
                min_non_rosso = min(min_non_rosso, depth)
            return
        if curr not in nodi or curr in visited or depth > 20:
            return
        visited_next = visited | {curr}
        for opt in nodi[curr].get("opzioni", []):
            if not opt.get("testo", "").strip():
                continue
            nxt = opt.get("next", "")
            is_red = opt.get("colore") == "rosso"
            _dfs(nxt, depth + 1, solo_rosso and is_red, visited_next)

    _dfs(start, 0, True, set())
    return (0 if min_assoluta == 999 else min_assoluta), (0 if min_non_rosso == 999 else min_non_rosso)


def _valida_contratto_v2(dati: Dict[str, Any]) -> Tuple[bool, List[str]]:
    avvisi: List[str] = []
    meta = dati.get("meta", {})
    if not meta.get("case_id") or not meta.get("titolo"):
        avvisi.append("Mancano `Codice Caso` o `Titolo` nei metadati.")

    t0 = dati.get("paziente_t0", {})
    for k in ("vitalita_iniziale", "oncologico_iniziale", "qol_iniziale"):
        val = t0.get(k)
        if not isinstance(val, (int, float)) or not (0 <= val <= 100):
            avvisi.append(f"Parametro T0 `{k}` fuori scala 0-100.")

    nodi = dati.get("nodi", {})
    if len(nodi) < 8:
        avvisi.append(f"Numero snodi insufficiente ({len(nodi)}): il caso deve svilupparsi su almeno 8-10 snodi.")

    min_ass, min_non_red = _calcola_profondita_minima_esiti(dati)
    if 0 < min_ass < 6:
        avvisi.append(f"Un percorso termina troppo presto allo snodo {min_ass}: anche scegliendo sempre Rosso il caso deve durare almeno 6 snodi.")
    if 0 < min_non_red < 8:
        avvisi.append(f"Un percorso non-Rosso termina allo snodo {min_non_red}: i percorsi standard devono durare almeno 8-10 snodi.")

    for sid, snodo in nodi.items():
        opzioni = [o for o in snodo.get("opzioni", []) if o.get("testo", "").strip()]
        if len(opzioni) != 4:
            avvisi.append(f"Snodo `{sid}`: servono esattamente 4 opzioni compilate (attuali: {len(opzioni)}).")
            continue

        colori = [o.get("colore", "") for o in opzioni]
        if snodo.get("is_post_rosso", False):
            if not (colori.count("verde") == 0 and colori.count("blu") == 2 and colori.count("giallo") == 1 and colori.count("rosso") == 1):
                avvisi.append(
                    f"Snodo `{sid}` (post-errore grave): distribuzione colori richiesta 0V / 2B / 1G / 1R (attuale: {colori})."
                )

        for idx, o in enumerate(opzioni, 1):
            parole = len(o["testo"].split())
            if parole < 2 or parole > 7:
                avvisi.append(f"Snodo `{sid}` opz. {idx} ('{o['testo']}'): target 2-6 parole (attuali: {parole}).")

    return len(avvisi) == 0, avvisi


# ==============================================================================
# 2. MOTORE AI v2.0 (GEMINI + BIBLIOTECA PDF DRIVE)
# ==============================================================================

def _seleziona_documenti_per_ambito(tutti_docs: List[Dict[str, str]], ambito: str) -> List[Dict[str, str]]:
    selezionati = []
    for doc in tutti_docs:
        nome_low = doc["name"].lower()
        is_vescica = any(k in nome_low for k in KEYWORDS_VESCICA)
        is_prostata = any(k in nome_low for k in KEYWORDS_PROSTATA)
        if ambito == "vescica":
            if is_vescica or not is_prostata:
                selezionati.append(doc)
        elif ambito == "prostata":
            if is_prostata or not is_vescica:
                selezionati.append(doc)
        else:
            selezionati.append(doc)
    return selezionati


def _prepara_parti_biblioteca(ambito: str, api_key: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    parti: List[Dict[str, Any]] = []
    nomi: List[str] = []
    try:
        tutti_docs = elenca_documenti_bibliografia()
        docs_filtrati = _seleziona_documenti_per_ambito(tutti_docs, ambito)
        for doc in docs_filtrati:
            try:
                f_uri = carica_file_drive_su_gemini(doc["id"], doc["name"], doc["mimeType"], api_key)
                parti.append({"file_data": {"mime_type": doc["mimeType"], "file_uri": f_uri}})
                nomi.append(f"[{doc['categoria']}] {doc['name']}")
            except Exception:
                continue
    except Exception:
        pass
    return parti, nomi


def _chiama_gemini_json(parti_contenuto: List[Dict[str, Any]], api_key: str, temperature: float = 0.3) -> Tuple[bool, Any]:
    payload = {
        "contents": [{"parts": parti_contenuto}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    ultimo_errore = ""
    for modello in ("gemini-2.5-pro", "gemini-2.5-flash"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=150) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                testo = raw["candidates"][0]["content"]["parts"][0]["text"].strip()
                testo = re.sub(r"^```json\s*|\s*```$", "", testo)
                return True, json.loads(testo)
        except urllib.error.HTTPError as e:
            dettaglio = e.read().decode("utf-8", errors="ignore")
            ultimo_errore = f"Errore Gemini ({e.code}): {dettaglio[:200]}"
            if e.code != 404:
                break
        except Exception as e:
            ultimo_errore = f"Errore chiamata Gemini: {e}"
            break
    return False, ultimo_errore


def _genera_intero_caso_v2(case_id: str, ambito: str, spunto_clinico: str, num_snodi: int = 9) -> Tuple[bool, Any]:
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False, "Manca GEMINI_API_KEY nei Secrets di Streamlit."

    parti_biblio, nomi_fonti = _prepara_parti_biblioteca(ambito, api_key)
    fonti_txt = "\n- ".join(nomi_fonti) if nomi_fonti else "Nessun PDF trovato nella cartella Biblioteca."

    prompt = f"""Sei il Direttore Scientifico di 2getSIM, simulatore clinico uro-oncologico ad alta fedeltà progettato per rompere l'inerzia specialistica di urologi e oncologi.

Genera un intero caso clinico completo nel formato JSON v2.0 basandoti sulla biblioteca PDF allegata (Linee Guida EAU, ESMO, Schede Tecniche RCP e Studi Clinici) e sullo spunto clinico fornito.

BIBLIOTECA PDF CARICATA:
- {fonti_txt}

SPECIFICHE DEL CASO:
- case_id: "{case_id}"
- area_clinica: "{ambito}"
- Lunghezza longitudinale del percorso principale: {num_snodi} snodi (minimo 8, massimo 10 snodi)
- Spunto clinico dell'autore:
{spunto_clinico}

REGOLE CLINICHE, STRUTTURALI E PSICOLOGICHE INDEROGABILI:
1. ARCHITETTURA LONGITUDINALE (8-10 SNODI / MINIMO 6 SOLO SE SEMPRE ROSSO):
   - Il percorso clinico principale (scelte `verde`, `blu`, `giallo`) DEVE svilupparsi per **almeno 8-10 snodi** consecutivi (`snodo1` -> `snodo2` -> ... -> `snodo{num_snodi}`) seguendo l'intera storia naturale della malattia (diagnosi/stadiazione, prima linea, gestione tossicità/complicanze, rivalutazione strumentale, seconda linea/salvataggio).
   - NESSUNA opzione `verde`, `blu` o `giallo` può puntare a un `esito_*` prima dello snodo 8.
   - Anche se il discente sceglie ripetutamente `rosso`, il caso NON può terminare subito: deve attraversare snodi di deterioramento (`is_post_rosso: true`) e può chiudersi in `esito_sconfitta` **solo dal 6° snodo in poi**.
2. BENCHMARK T0 (30enne sano = 100/100/100):
   - Calibra `vitalita_iniziale`, `oncologico_iniziale` e `qol_iniziale` sottraendo punti reali in base a età, eGFR, comorbidità, fragilità e carico tumorale. Documenta i motivi in `calibrazione_t0`.
3. MINE PSICOLOGICHE SILENZIOSE:
   - Inserisci trappole specifiche per l'urologo e per l'oncologo in `mine_psicologiche`.
   - Le opzioni `giallo` (formalmente ammessa da Linea Guida ma tossica/inadeguata in questo paziente per RCP/comorbidità) e `blu` (difensiva/ridondante) devono sembrare ragionevoli e avere `effetto_ritardato: true` (danno evidente 2-3 snodi dopo, effetto "Cuore rivelatore").
4. SIMMETRIA LESSICALE DELLE OPZIONI:
   - Ogni snodo ha ESATTAMENTE 4 opzioni.
   - Ogni opzione (`testo`) deve essere un comando operativo secco di **2-6 parole**, senza aggettivi qualificativi, senza parentesi esplicative e senza suggerire la risposta corretta tramite la lunghezza.
5. VINCOLO POST-ROSSO:
   - Negli snodi successivi a un errore `rosso` (`is_post_rosso: true`), la guarigione piena non è più raggiungibile: le 4 opzioni devono essere `0 verde`, `2 blu` (salvataggio/palliazione), `1 giallo`, `1 rosso`.
6. GRAFO COERENTE:
   - Chiavi nodi: `"snodo1"`, `"snodo2"`, ..., `"snodo{num_snodi}"` (più eventuali snodi dedicati `is_post_rosso`) con `nodo_iniziale: "snodo1"`.
   - Ogni `next` deve puntare a uno snodo esistente o a uno degli esiti: `"esito_vittoria"`, `"esito_parziale"`, `"esito_sconfitta"`.

Restituisci ESCLUSIVAMENTE questo oggetto JSON valido:
{{
  "schema_version": "2.0",
  "meta": {{
    "case_id": "{case_id}",
    "area_clinica": "{ambito}",
    "stato": "bozza",
    "versione": 1,
    "titolo": "...",
    "sottotitolo": "...",
    "descrizione_master": "...",
    "audit_clinico": "..."
  }},
  "paziente_t0": {{
    "vitalita_iniziale": 80,
    "oncologico_iniziale": 55,
    "qol_iniziale": 75,
    "calibrazione_t0": {{
      "vitalita_motivo": "...",
      "oncologico_motivo": "...",
      "qol_motivo": "..."
    }},
    "scheda_paziente": "...",
    "mine_psicologiche": {{
      "trappola_urologo": "...",
      "trappola_oncologo": "..."
    }}
  }},
  "nodo_iniziale": "snodo1",
  "nodi": {{
    "snodo1": {{
      "titolo": "...",
      "testo": "...",
      "is_post_rosso": false,
      "opzioni": [
        {{"testo": "Comando 2-6 parole", "colore": "verde", "d_vit": 5, "d_onc": 15, "d_qol": 5, "effetto_ritardato": false, "razionale": "...", "next": "snodo2"}},
        {{"testo": "Comando 2-6 parole", "colore": "blu", "d_vit": 0, "d_onc": -5, "d_qol": -5, "effetto_ritardato": true, "razionale": "...", "next": "snodo2"}},
        {{"testo": "Comando 2-6 parole", "colore": "giallo", "d_vit": -10, "d_onc": -15, "d_qol": -25, "effetto_ritardato": true, "razionale": "...", "next": "snodo2"}},
        {{"testo": "Comando 2-6 parole", "colore": "rosso", "d_vit": -20, "d_onc": -30, "d_qol": -20, "effetto_ritardato": false, "razionale": "...", "next": "snodo2"}}
      ]
    }}
  }},
  "esiti": {{
    "esito_vittoria": {{"tipo": "bianco", "titolo": "ESITO OTTIMALE", "descrizione": "...", "debriefing_master": "..."}},
    "esito_parziale": {{"tipo": "giallo", "titolo": "ESITO INTERMEDIO", "descrizione": "...", "debriefing_master": "..."}},
    "esito_sconfitta": {{"tipo": "rosso", "titolo": "ESITO CRITICO", "descrizione": "...", "debriefing_master": "..."}}
  }}
}}"""

    parti_contenuto = [*parti_biblio, {"text": prompt}]
    ok, res = _chiama_gemini_json(parti_contenuto, api_key, temperature=0.35)
    if not ok:
        return False, res

    now_iso = datetime.now(timezone.utc).isoformat()
    res["schema_version"] = "2.0"
    meta = res.setdefault("meta", {})
    meta["case_id"] = case_id
    meta["area_clinica"] = ambito
    meta["stato"] = "bozza"
    meta.setdefault("versione", 1)
    meta.setdefault("created_at", now_iso)
    meta["updated_at"] = now_iso
    res.setdefault("changelog_finetuning", [])
    return True, res


def _genera_distrattori_snodo_v2(dati: Dict[str, Any], s_id: str, testo_verde: str) -> Tuple[bool, Any]:
    """Genera le 3 opzioni Blu/Gialla/Rossa (2-6 parole + razionale) per un singolo snodo."""
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False, "Manca GEMINI_API_KEY nei Secrets di Streamlit."

    ambito = dati.get("meta", {}).get("area_clinica", "vescica")
    parti_biblio, nomi_fonti = _prepara_parti_biblioteca(ambito, api_key)
    snodo = dati["nodi"][s_id]
    scheda = dati.get("paziente_t0", {}).get("scheda_paziente", "")
    provenienza = _ricostruisci_contesto_provenienza(dati, s_id)

    prompt = f"""Sei un uro-oncologo senior esperto di Linee Guida EAU/ESMO e RCP farmaci.
Completa le 3 alternative (blu, gialla, rossa) dello snodo corrente partendo dall'opzione VERDE già scritta dall'autore.

BIBLIOTECA DISPONIBILE: {", ".join(nomi_fonti) if nomi_fonti else "Linee Guida EAU/ESMO"}
CARTELLA PAZIENTE T0: {scheda}
CONTESTO RAMO: {provenienza}
SNODO CORRENTE ({snodo.get('titolo', '')}): {snodo.get('testo', '')}
OPZIONE VERDE: "{testo_verde}"

VINCOLO FERREO DI STILE:
- Ogni testo opzione deve essere un comando secco di **2-6 parole** (simmetrico alla verde, zero parentesi o aggettivi).
- Per ciascuna opzione fornisci anche il `razionale` clinico (1 frase sintetica con riferimento a EAU/ESMO/RCP/studi).

Rispondi SOLO con questo JSON:
{{
  "blu": {{"testo": "2-6 parole", "razionale": "..."}},
  "gialla": {{"testo": "2-6 parole", "razionale": "..."}},
  "rossa": {{"testo": "2-6 parole", "razionale": "..."}}
}}"""

    parti_contenuto = [*parti_biblio, {"text": prompt}]
    ok, res = _chiama_gemini_json(parti_contenuto, api_key, temperature=0.3)
    if not ok:
        return False, res
    if all(k in res and "testo" in res[k] for k in ("blu", "gialla", "rossa")):
        return True, res
    return False, "Risposta AI incompleta sullo snodo."


# ==============================================================================
# 3. UTILITY GRAFO, COMPATIBILITÀ STORYCASE (.PY) E GITHUB
# ==============================================================================

def _ricostruisci_contesto_provenienza(dati: Dict[str, Any], target_node_id: str) -> str:
    if target_node_id == dati.get("nodo_iniziale", "snodo1"):
        return "Snodo iniziale del caso clinico."
    provenienze = []
    for s_id, snodo in dati.get("nodi", {}).items():
        for opt in snodo.get("opzioni", []):
            if opt.get("next") == target_node_id and opt.get("testo", "").strip():
                col = opt.get("colore", "").upper()
                provenienze.append(f"Da '{snodo.get('titolo', s_id)}' dopo [{col}]: \"{opt['testo']}\"")
    return " | ".join(provenienze) if provenienze else "Snodo intermedio."


def _esporta_dict_legacy_app_py(dati_v2: Dict[str, Any]) -> Dict[str, Any]:
    """Converte il contratto JSON v2.0 nel dizionario CASO compatibile con app.py (anteprima rapida)."""
    meta = dati_v2.get("meta", {})
    t0 = dati_v2.get("paziente_t0", {})
    return {
        "badge": "ARENA URO-ONCOLOGICA",
        "ambito_patologia": meta.get("area_clinica", "vescica"),
        "descrizione_master": meta.get("descrizione_master", ""),
        "titolo": meta.get("titolo", ""),
        "sottotitolo": meta.get("sottotitolo", ""),
        "nodo_iniziale": dati_v2.get("nodo_iniziale", "snodo1"),
        "vitalita_iniziale": t0.get("vitalita_iniziale", 80),
        "oncologico_iniziale": t0.get("oncologico_iniziale", 55),
        "qol_iniziale": t0.get("qol_iniziale", 75),
        "scheda_paziente": t0.get("scheda_paziente", ""),
        "nodi": dati_v2.get("nodi", {}),
        "esiti": dati_v2.get("esiti", {}),
    }


def _salva_su_github(percorso_repo: str, contenuto_testo: str, messaggio_commit: str) -> Tuple[bool, str]:
    token = st.secrets.get("GITHUB_TOKEN", "").strip()
    repo = st.secrets.get("GITHUB_REPO", "").strip()
    branch = st.secrets.get("GITHUB_BRANCH", "main").strip()
    if not token or not repo or token.startswith("incolla"):
        return False, "GITHUB_TOKEN non impostato nei Secrets."

    url = f"https://api.github.com/repos/{repo}/contents/{percorso_repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "2getSIM-App",
    }

    sha_esistente = None
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{url}?ref={branch}", headers=headers), timeout=10) as resp:
            sha_esistente = json.loads(resp.read().decode("utf-8")).get("sha")
    except Exception:
        pass

    payload: Dict[str, Any] = {
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
                return True, f"Copia anteprima '{percorso_repo}' aggiornata su GitHub."
    except Exception as e:
        return False, str(e)
    return False, "Risposta imprevista da GitHub."


def _genera_graphviz_dot(dati: Dict[str, Any], rankdir: str = "LR") -> str:
    righe = [
        "digraph G {",
        f'  rankdir="{rankdir}";',
        '  bgcolor="transparent";',
        '  node [shape=box, style="rounded,filled", fontname="Inter,Arial", fontsize=11, margin="0.16,0.10"];',
        '  edge [fontname="Inter,Arial", fontsize=9, penwidth=1.6];',
    ]

    for s_id, snodo in dati.get
