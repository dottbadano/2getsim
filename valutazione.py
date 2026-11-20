import csv
import datetime
import html
import io
import streamlit as st


def aggrega_metriche_runs(lista_runs):
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
        alert.append("🚜 **Effetto Bulldozer (Linee Guida a testa bassa):** applica raccomandazioni standard senza adattarle al paziente o consultare l'anamnesi.")
    if esami_ridondanti >= 2 or (conteggi["blu"] >= 2 and spesa >= 7000):
        alert.append("🔬 **Iper-prescrizione / Medicina Difensiva:** tende ad accumulare esami o procedure intermedie prima di decidere.")
    if conteggi["rosso"] >= 2:
        alert.append("🚨 **Errori Clinici Critici Ricorrenti:** scelte ad alto rischio di tossicità o sottotrattamento.")
    if cons_anamnesi == 0 and tot >= 3:
        alert.append("🙈 **Anamnesi Mai Riaperta:** non ha mai verificato comorbilità/familiarità dopo il primo snodo.")
    if conteggi["verde"] / tot >= 0.75 and cons_anamnesi >= 1:
        alert.append("🎯 **Approccio Tailored:** ragionamento mirato sul paziente e verifica attiva della cartella.")
    if not alert:
        alert.append("⚖️ **Profilo Misto / Prudente:** alterna scelte corrette a passaggi interlocutori.")
    sintesi = f"🟩 {conteggi['verde']} | 🟦 {conteggi['blu']} | 🟨 {conteggi['giallo']} | 🟥 {conteggi['rosso']}"
    return sintesi, alert


def _genera_csv_esportazione(runs_per_entita, gruppi_attivi):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Postazione_o_Gruppo", "Modalita", "Scenario", "Nodo_Finale",
        "Vitalita_%", "Controllo_Onc_%", "QoL_%", "Spesa_SSN_EUR",
        "Consultazioni_Anamnesi", "Scelte_Verdi_Tailored", "Scelte_Blu_Subottimali",
        "Scelte_Gialle_Bulldozer", "Scelte_Rosse_Critiche", "Diagnosi_Comportamentale",
    ])
    for entita, lista_runs in sorted(runs_per_entita.items()):
        modalita = "Gruppo/Coppia" if entita in gruppi_attivi else "Singolo"
        for case_id, v in lista_runs:
            _, alerts = analizza_profilo_comportamentale(v)
            conteggi = {"verde": 0, "blu": 0, "giallo": 0, "rosso": 0}
            for s in v.get("percorso", []):
                c = s.get("colore", "blu")
                conteggi[c] = conteggi.get(c, 0) + 1
            writer.writerow([
                entita, modalita, case_id, v.get("current_node", ""),
                v.get("vitalita", 0), v.get("oncologico", 0), v.get("qol", 0),
                v.get("spesa_ssn", 0), v.get("consultazioni_anamnesi", 0),
                conteggi["verde"], conteggi["blu"], conteggi["giallo"], conteggi["rosso"],
                " | ".join(alerts).replace("**", ""),
            ])
    return output.getvalue().encode("utf-8-sig")


def _genera_report_html_plenario(runs_per_entita, gruppi_attivi):
    data_ora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    tutti_singoli, tutti_gruppi = [], []
    for entita, lista_runs in runs_per_entita.items():
        if entita in gruppi_attivi:
            tutti_gruppi.extend(lista_runs)
        else:
            tutti_singoli.extend(lista_runs)
    agg_s = aggrega_metriche_runs(tutti_singoli)
    agg_g = aggrega_metriche_runs(tutti_gruppi)

    def bar_html(val, color):
        w = max(2, min(100, val))
        return f'<div style="background:#e2e8f0;border-radius:6px;height:14px;width:100%;overflow:hidden;"><div style="background:{color};height:100%;width:{w}%;"></div></div>'

    righe_medici_html = []
    medici_set = {e for e in runs_per_entita if e not in gruppi_attivi}
    for membri in gruppi_attivi.values():
        medici_set.update(membri)
    for m in sorted(medici_set):
        st_s = aggrega_metriche_runs(runs_per_entita.get(m, []))
        gruppi_m = [g for g, mem in gruppi_attivi.items() if m in mem]
        runs_g = [r for g in gruppi_m for r in runs_per_entita.get(g, [])]
        st_g = aggrega_metriche_runs(runs_g)
        err_s = round(st_s["pct"]["giallo"] + st_s["pct"]["rosso"], 1)
        err_g = round(st_g["pct"]["giallo"] + st_g["pct"]["rosso"], 1)
        if st_s["tot_scelte"] > 0 and st_g["tot_scelte"] > 0:
            if err_g < err_s - 10:
                esito_din = '<span style="color:#15803d;font-weight:700;">✅ Sinergia / Aperto al confronto</span>'
            elif err_g > err_s + 10:
                esito_din = '<span style="color:#b91c1c;font-weight:700;">⚠️ Contagio / Trascinamento</span>'
            elif err_s >= 25:
                esito_din = '<span style="color:#c2410c;font-weight:700;">👑 Leader Dominante</span>'
            else:
                esito_din = '<span style="color:#1d4ed8;font-weight:700;">🤝 Stabilità Decisionale</span>'
        else:
            esito_din = '<span style="color:#64748b;">— Dati parziali</span>'
        righe_medici_html.append(
            f"<tr><td><strong>Medico {html.escape(m)}</strong><br><small style='color:#64748b;'>Gruppo: {html.escape(', '.join(gruppi_m)) if gruppi_m else 'Nessuno'}</small></td>"
            f"<td>🟩 {st_s['pct']['verde']}% | 🟨+🟥 <strong>{err_s}%</strong><br><small>QoL: {st_s['avg_qol']}% | Spesa: {st_s['avg_spesa']:,} €</small></td>"
            f"<td>🟩 {st_g['pct']['verde']}% | 🟨+🟥 <strong>{err_g}%</strong><br><small>QoL: {st_g['avg_qol']}% | Spesa: {st_g['avg_spesa']:,} €</small></td>"
            f"<td>{esito_din}</td></tr>"
        )
    return f"""<!DOCTYPE html><html lang="it"><head><meta charset="UTF-8"><title>Report Debriefing 2getSIM — {data_ora}</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#0f172a;margin:32px;background:#fff;}}
.header{{background:#0f172a;color:#fff;padding:20px 24px;border-radius:12px;margin-bottom:24px;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:28px;}}
.card{{border:1px solid #cbd5e1;border-radius:10px;padding:18px;background:#f8fafc;}}
table{{width:100%;border-collapse:collapse;margin-top:12px;font-size:14px;}}th,td{{border:1px solid #cbd5e1;padding:10px 12px;text-align:left;}}th{{background:#f1f5f9;}}</style></head><body>
<div class="header"><h1 style="margin:0;color:white;">⚡ 2getSIM — Report Finale di Debriefing Clinico</h1>
<p style="margin:6px 0 0 0;color:#94a3b8;">Individuale vs Lavoro Congiunto (Coppia / Gruppo) • {data_ora}</p></div>
<h2>1. Impatto del Lavoro Congiunto (Media Aula)</h2><div class="grid">
