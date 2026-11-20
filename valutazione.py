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
    esami_rid = 0
    for step in percorso:
        col = step.get("colore", "blu")
        conteggi[col] = conteggi.get(col, 0) + 1
        t_low = step.get("scelta", "").lower()
        if col in ("blu", "giallo", "rosso") and any(k in t_low for k in ("tc", "urs", "stent", "moc", "rm mirata", "biopsie random")):
            esami_rid += 1
    tot = len(percorso)
    cons = stato_run.get("consultazioni_anamnesi", 0)
    alert = []
    if conteggi["giallo"] >= 2 or (conteggi["giallo"] >= 1 and cons == 0 and tot >= 2):
        alert.append("🚜 **Effetto Bulldozer:** applica scelte standard senza adattarle alle comorbidità del paziente.")
    if esami_rid >= 2:
        alert.append("🔬 **Iper-prescrizione / Medicina Difensiva:** accumula esami intermedi prima di decidere.")
    if conteggi["rosso"] >= 2:
        alert.append("🚨 **Errori Clinici Critici Ricorrenti:** scelte ad alto rischio di tossicità o sottotrattamento.")
    if cons == 0 and tot >= 3:
        alert.append("🙈 **Anamnesi Mai Riaperta:** non ha verificato comorbidità/terapie dopo il primo snodo.")
    if conteggi["verde"] / tot >= 0.75 and cons >= 1:
        alert.append("🎯 **Approccio Tailored:** ragionamento mirato sul paziente e verifica attiva della cartella.")
    if not alert:
        alert.append("⚖️ **Profilo Misto / Prudente:** alterna scelte ottimali a passaggi interlocutori.")
    sintesi = f"🟩 {conteggi['verde']} | 🟦 {conteggi['blu']} | 🟨 {conteggi['giallo']} | 🟥 {conteggi['rosso']}"
    return sintesi, alert


def _genera_csv_esportazione(runs_per_entita, gruppi_attivi):
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Postazione", "Modalita", "Scenario", "Nodo_Finale", "Vitalita_%", "Controllo_Onc_%", "QoL_%", "Anamnesi", "Verdi", "Blu", "Gialli", "Rossi", "Profilo"])
    for ent, lista in sorted(runs_per_entita.items()):
        mod = "Gruppo" if ent in gruppi_attivi else "Singolo"
        for cid, v in lista:
            _, alerts = analizza_profilo_comportamentale(v)
            c = {"verde": 0, "blu": 0, "giallo": 0, "rosso": 0}
            for s in v.get("percorso", []):
                c[s.get("colore", "blu")] = c.get(s.get("colore", "blu"), 0) + 1
            w.writerow([ent, mod, cid, v.get("current_node", ""), v.get("vitalita", 0), v.get("oncologico", 0), v.get("qol", 0), v.get("consultazioni_anamnesi", 0), c["verde"], c["blu"], c["giallo"], c["rosso"], " | ".join(alerts).replace("**", "")])
    return out.getvalue().encode("utf-8-sig")


def _genera_report_html_plenario(runs_per_entita, gruppi_attivi):
    data_ora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    singoli, gruppi = [], []
    for ent, lista in runs_per_entita.items():
        (gruppi if ent in gruppi_attivi else singoli).extend(lista)
    agg_s, agg_g = aggrega_metriche_runs(singoli), aggrega_metriche_runs(gruppi)
    righe = []
    medici = {e for e in runs_per_entita if e not in gruppi_attivi}
    for mem in gruppi_attivi.values():
        medici.update(mem)
    for m in sorted(medici):
        st_s = aggrega_metriche_runs(runs_per_entita.get(m, []))
        gm = [g for g, mem in gruppi_attivi.items() if m in mem]
        st_g = aggrega_metriche_runs([r for g in gm for r in runs_per_entita.get(g, [])])
        es, eg = round(st_s["pct"]["giallo"] + st_s["pct"]["rosso"], 1), round(st_g["pct"]["giallo"] + st_g["pct"]["rosso"], 1)
        righe.append(f"<tr><td><b>{html.escape(m)}</b></td><td>🟩 {st_s['pct']['verde']}% | 🟨+🟥 {es}%</td><td>🟩 {st_g['pct']['verde']}% | 🟨+🟥 {eg}%</td></tr>")
    return f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Report 2getSIM</title><style>body{{font-family:sans-serif;margin:24px;}}table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid #cbd5e1;padding:8px;text-align:left;}}</style></head><body><h2>⚡ 2getSIM — Debriefing ({data_ora})</h2><p><b>Singoli ({agg_s['n_runs']}):</b> 🟩 {agg_s['pct']['verde']}% | QoL {agg_s['avg_qol']}% — <b>Gruppi ({agg_g['n_runs']}):</b> 🟩 {agg_g['pct']['verde']}% | QoL {agg_g['avg_qol']}%</p><table><thead><tr><th>Partecipante</th><th>Da Solo</th><th>In Gruppo</th></tr></thead><tbody>{''.join(righe)}</tbody></table></body></html>"


def render_osservatorio_master(room, role="master"):
    st.markdown("## 🧠 Osservatorio Regia Master — Debriefing, Proiezione & Export")
    tutti_stati = room.get("stati_casi", {})
    if not tutti_stati:
        st.info("Nessuna simulazione avviata finora dai discenti o dai gruppi.")
        return

    gruppi_raw = room.get("gruppi_personalizzati", {})
    gruppi_attivi, slug_to_gruppo = {}, {}
    for nome_g, membri in gruppi_raw.items():
        slug = "gruppo_" + "".join(c if c.isalnum() else "_" for c in nome_g.lower())
        gruppi_attivi[nome_g] = list(membri)
        slug_to_gruppo[slug] = nome_g

    runs_per_entita = {}
    for chiave, v in tutti_stati.items():
        if "__" not in chiave:
            continue
        case_id, bucket = chiave.split("__", 1)
        if bucket.startswith("master_"):
            continue
        if bucket in slug_to_gruppo:
            ent = slug_to_gruppo[bucket]
        elif bucket.startswith("singolo_"):
            ent = bucket[len("singolo_"):]
        else:
            ent = bucket
        runs_per_entita.setdefault(ent, []).append((case_id, v))

    if not runs_per_entita:
        st.info("Nessuna simulazione discente attiva da analizzare (le prove della Control Room sono escluse).")
        return

    c1, c2 = st.columns(2)
    c1.download_button("📄 Scarica Report HTML / PDF", data=_genera_report_html_plenario(runs_per_entita, gruppi_attivi), file_name=f"Report_2getSIM_{datetime.date.today()}.html", mime="text/html", type="primary", use_container_width=True)
    c2.download_button("📊 Scarica Tabella CSV", data=_genera_csv_esportazione(runs_per_entita, gruppi_attivi), file_name=f"Dati_2getSIM_{datetime.date.today()}.csv", mime="text/csv", use_container_width=True)
    st.divider()

    t1, t2, t3, t4 = st.tabs(["📽️ Proiezione Plenaria", "📊 Grafici Singolo Medico", "📋 Registro Errori & Bias", "👥 Sintesi Coppie / Gruppi"])

    with t1:
        singoli, gruppi = [], []
        for ent, lista in runs_per_entita.items():
            (gruppi if ent in gruppi_attivi else singoli).extend(lista)
        agg_s, agg_g = aggrega_metriche_runs(singoli), aggrega_metriche_runs(gruppi)
        m1, m2, m3 = st.columns(3)
        m1.metric("🟩 Tailored (Singolo vs Gruppo)", f"{agg_s['pct']['verde']}%", f"Gruppo: {agg_g['pct']['verde']}%" if agg_g["
