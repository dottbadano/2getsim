import base64
import json
import os
import pprint
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
        docs_filtrati =
