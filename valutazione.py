import csv
import datetime
import html
import io
import streamlit as st


def aggrega_metriche_runs(lista_runs):
    """Calcola conteggi, percentuali colori e medie cliniche su una lista di run [(case_id, state_dict)]."""
    conteggi = {"verde": 0, "blu": 0, "giallo": 0, "rosso": 0}
    tot_scelte = 0
    somma_vit, somma_onc, somma_qol, somma_spesa, somma_anamnesi = 0, 0, 0, 0, 0
    n_runs = len(lista_runs)

    for _, r in lista_runs:
        somma_vit += max(0, min(100, r.get("vitalita", 100)))
        somma_onc += max(0, min(100, r.get("oncologico", 100)))
        somma_qol += max(0, min(100, r.get("qol", 75)))
        somma_spesa += r.get("spesa_ssn", 0)
        somma_anamnesi += r.get("consultazioni_anamnesi", 0)

        for step in r.get("percorso", []):
            col = step.get("colore", "blu")
            conteggi[col] = conteggi.get(col, 0) + 1
            tot_scelte += 1

    denom_scelte = max(1, tot_scelte)
    denom_runs = max(1, n_runs)
    pct = {k: round((v / denom_scelte) * 100, 1) for k, v in conteggi.items()}

    return {
        "n_runs": n_runs,
        "tot_scelte": tot_scelte,
        "conteggi": conteggi,
        "pct": pct,
        "avg_vit": round(somma_vit / denom_runs, 1),
        "avg_onc": round(somma_onc / denom_runs, 1),
        "avg_qol": round(somma_qol / denom_runs, 1),
        "avg_spesa": round(somma_spesa / denom_runs, 1),
        "avg_anamnesi": round(somma_anamnesi / denom_runs, 1),
    }


def analizza_profilo_comportamentale(stato_run):
    """Restituisce la sintesi delle scelte colorate e i bias cognitivi rilevati."""
    percorso = stato_run.get("percorso", [])
    if not percorso:
        return "⏳ In attesa della prima scelta", []

    conteggi = {"verde": 0, "blu": 0, "giallo": 0, "rosso": 0}
    esami_ridondanti = 0

    for step in percorso:
        col = step.get("colore", "blu")
        conteggi[col] = conteggi.get(col, 0) + 1
        testo_low = step.get("scelta", "").lower()
        if col in ("blu", "giallo", "rosso") and any(
            k in testo_low for k in ("tc", "urs", "stent", "moc", "rm mirata", "biopsie random", "citologie")
        ):
            esami_ridondanti += 1

    tot = len(percorso)
    cons_anamnesi = stato_run.get("consultazioni_anamnesi", 0)
    spesa = stato_run.get("spesa_ssn", 0)
    alert = []

    if conteggi["giallo"] >= 2 or (conteggi["giallo"] >= 1 and cons_anamnesi == 0 and tot >= 2):
        alert.append(
            "🚜 **Effetto Bulldozer (Linee Guida a testa bassa):** applica raccomandazioni standard senza adattarle al paziente o consultare l'anamnesi."
        )
    if esami_ridondanti >= 2 or (conteggi["blu"] >= 2 and spesa >= 7000):
        alert.append(
            "🔬 **Iper-prescrizione / Medicina Difensiva:** tende ad accumulare esami o procedure intermedie prima di decidere."
        )
    if conteggi["rosso"] >= 2:
        alert.append("🚨 **Errori Clinici Critici Ricorrenti:** scelte ad alto rischio di tossicità o sottotrattamento.")
    if cons_anamnesi == 0 and tot >= 3:
        alert.append("🙈 **Anamnesi Mai Riaperta:** non ha mai verificato comorbilità/familiarità dopo il primo snodo.")
    if
