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
        "avg_spesa": round(somma_spesa / denom_runs),
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
        "Postazione_o_Gruppo",
        "Modalita",
        "Scenario",
        "Nodo_Finale",
        "Vitalita_%",
        "Controllo_Onc_%",
        "QoL_%",
        "Spesa_SSN_EUR",
        "Consultazioni_Anamnesi",
        "Scelte_Verdi_Tailored",
        "Scelte_Blu_Subottimali",
        "Scelte_Gialle_Bulldozer",
        "Scelte_Rosse_Critiche",
        "Diagnosi_Comportamentale",
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
                entita,
                modalita,
                case_id,
                v.get("current_node", ""),
                v.get("vitalita", 0),
                v.get("oncologico", 0),
                v.get("qol", 0),
                v.get("spesa_ssn", 0),
                v.get("consultazioni_anamnesi", 0),
                conteggi["verde"],
                conteggi["blu"],
                conteggi["giallo"],
                conteggi["rosso"],
                " | ".join(alerts).replace("**", ""),
            ])
    return output.getvalue().encode("utf-8-sig")


def _genera_report_html_plenario(runs_per_entita, gruppi_attivi):
    """Genera un report HTML completo e stampabile in PDF con grafici a barre."""
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

        righe_medici_html.append(f"""
        <tr>
            <td><strong>Medico {html.escape(m)}</strong><br><small style="color:#64748b;">Gruppo: {html.escape(', '.join(gruppi_m)) if gruppi_m else 'Nessuno'}</small></td>
            <td>🟩 {st_s['pct']['verde']}% | 🟨+🟥 <strong>{err_s}%</strong><br><small>QoL: {st_s['avg_qol']}% | Spesa: {st_s['avg_spesa']:,} €</small></td>
            <td>🟩 {st_g['pct']['verde']}% | 🟨+🟥 <strong>{err_g}%</strong><br><small>QoL: {st_g['avg_qol']}% | Spesa: {st_g['avg_spesa']:,} €</small></td>
            <td>{esito_din}</td>
        </tr>
        """)

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>Report Debriefing 2getSIM — {data_ora}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #0f172a; margin: 32px; background: #ffffff; }}
  .header {{ background: #0f172a; color: white; padding: 20px 24px; border-radius: 12px; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 28px; }}
  .card {{ border: 1px solid #cbd5e1; border-radius: 10px; padding: 18px; background: #f8fafc; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 10px 12px; text-align: left; }}
  th {{ background: #f1f5f9; }}
  @media print {{ body {{ margin: 12px; }} }}
</style>
</head>
<body>
  <div class="header">
    <h1 style="margin:0;color:white;">⚡ 2getSIM — Report Finale di Debriefing Clinico</h1>
    <p style="margin:6px 0 0 0;color:#94a3b8;">Confronto Decisionale: Lavoro Individuale vs Lavoro Congiunto (Coppia / Gruppo) • Generato il {data_ora}</p>
  </div>

  <h2>1. Impatto del Lavoro Congiunto (Media Complessiva Aula)</h2>
  <div class="grid">
    <div class="card">
      <h3>👤 Decisioni Individuali ({agg_s['n_runs']} simulazioni)</h3>
      <p>🟩 Scelte Tailored Ottimali: <strong>{agg_s['pct']['verde']}%</strong></p>{bar_html(agg_s['pct']['verde'], '#16a34a')}
      <p>🟦 Scelte Subottimali: <strong>{agg_s['pct']['blu']}%</strong></p>{bar_html(agg_s['pct']['blu'], '#2563eb')}
      <p>🟨 Effetto Bulldozer (Linee Guida non tailored): <strong>{agg_s['pct']['giallo']}%</strong></p>{bar_html(agg_s['pct']['giallo'], '#ca8a04')}
      <p>🟥 Errori Critici: <strong>{agg_s['pct']['rosso']}%</strong></p>{bar_html(agg_s['pct']['rosso'], '#dc2626')}
      <hr>
      <p>🌿 QoL Media: <strong>{agg_s['avg_qol']}%</strong> &nbsp;|&nbsp; 🎯 Controllo Onc: <strong>{agg_s['avg_onc']}%</strong> &nbsp;|&nbsp; 💶 Spesa Media SSN: <strong>{agg_s['avg_spesa']:,} €</strong></p>
    </div>

    <div class="card">
      <h3>👥 Decisioni in Coppia / Gruppo ({agg_g['n_runs']} simulazioni)</h3>
      <p>🟩 Scelte Tailored Ottimali: <strong>{agg_g['pct']['verde']}%</strong></p>{bar_html(agg_g['pct']['verde'], '#16a34a')}
      <p>🟦 Scelte Subottimali: <strong>{agg_g['pct']['blu']}%</strong></p>{bar_html(agg_g['pct']['blu'], '#2563eb')}
      <p>🟨 Effetto Bulldozer (Linee Guida non tailored): <strong>{agg_g['pct']['giallo']}%</strong></p>{bar_html(agg_g['pct']['giallo'], '#ca8a04')}
      <p>🟥 Errori Critici: <strong>{agg_g['pct']['rosso']}%</strong></p>{bar_html(agg_g['pct']['rosso'], '#dc2626')}
      <hr>
      <p>🌿 QoL Media: <strong>{agg_g['avg_qol']}%</strong> &nbsp;|&nbsp; 🎯 Controllo Onc: <strong>{agg_g['avg_onc']}%</strong> &nbsp;|&nbsp; 💶 Spesa Media SSN: <strong>{agg_g['avg_spesa']:,} €</strong></p>
    </div>
  </div>

  <h2>2. Confronto Individuale vs Coppia per Singolo Partecipante</h2>
  <table>
    <thead>
      <tr>
        <th>Partecipante</th>
        <th>Performance da Solo</th>
        <th>Performance in Coppia / Gruppo</th>
        <th>Dinamica Relazionale Rilevata</th>
      </tr>
    </thead>
    <tbody>
      {''.join(righe_medici_html)}
    </tbody>
  </table>
  <p style="margin-top:20px;color:#64748b;font-size:12px;">Suggerimento: premi Ctrl+P (o Cmd+P su Mac) per salvare questa schermata in formato PDF.</p>
</body>
</html>"""


def _render_confronto_plenario_aula(runs_per_entita, gruppi_attivi):
    st.markdown("### 📽️ Sintesi Plenaria: Dimostrazione dell'Impatto del Lavoro Congiunto")
    st.caption("Confronto aggregato tra le simulazioni svolte individualmente e quelle affrontate in coppia multidisciplinare.")

    tutti_singoli, tutti_gruppi = [], []
    for entita, lista_runs in runs_per_entita.items():
        if entita in gruppi_attivi:
            tutti_gruppi.extend(lista_runs)
        else:
            tutti_singoli.extend(lista_runs)

    agg_s = aggrega_metriche_runs(tutti_singoli)
    agg_g = aggrega_metriche_runs(tutti_gruppi)

    err_s = round(agg_s["pct"]["giallo"] + agg_s["pct"]["rosso"], 1)
    err_g = round(agg_g["pct"]["giallo"] + agg_g["pct"]["rosso"], 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Scelte Tailored (🟩) in Gruppo",
        f"{agg_g['pct']['verde']}%",
        f"{round(agg_g['pct']['verde'] - agg_s['pct']['verde'], 1):+.1f}% vs Singolo" if agg_g["tot_scelte"] > 0 else "In attesa gruppi",
    )
    c2.metric(
        "Errori Bulldozer/Critici (🟨+🟥)",
        f"{err_g}%",
        f"{round(err_g - err_s, 1):+.1f}% vs Singolo" if agg_g["tot_scelte"] > 0 else "In attesa gruppi",
        delta_color="inverse",
    )
    c3.metric(
        "Qualità di Vita Media Finale",
        f"{agg_g['avg_qol']}%",
        f"{round(agg_g['avg_qol'] - agg_s['avg_qol'], 1):+.1f}% vs Singolo" if agg_g["n_runs"] > 0 else "In attesa gruppi",
    )
    c4.metric(
        "Spesa Media SSN per Paziente",
        f"{agg_g['avg_spesa']:,} €".replace(",", "."),
        f"{agg_g['avg_spesa'] - agg_s['avg_spesa']:+,} € vs Singolo".replace(",", ".") if agg_g["n_runs"] > 0 else "In attesa gruppi",
        delta_color="inverse",
    )

    col_p1, col_p2 = st.columns(2, gap="large")
    with col_p1:
        st.markdown("#### Distribuzione Scelte Aula: Singolo vs Coppia")
        st.bar_chart(
            {
                "🟩 Tailored Ottimale": {"Da Solo (Media Aula)": agg_s["pct"]["verde"], "In Coppia/Gruppo": agg_g["pct"]["verde"]},
                "🟦 Subottimale": {"Da Solo (Media Aula)": agg_s["pct"]["blu"], "In Coppia/Gruppo": agg_g["pct"]["blu"]},
                "🟨 Bulldozer Linee Guida": {"Da Solo (Media Aula)": agg_s["pct"]["giallo"], "In Coppia/Gruppo": agg_g["pct"]["giallo"]},
                "🟥 Errore Critico": {"Da Solo (Media Aula)": agg_s["pct"]["rosso"], "In Coppia/Gruppo": agg_g["pct"]["rosso"]},
            },
            use_container_width=True,
        )
    with col_p2:
        st.markdown("#### Outcome Clinici Medi: Singolo vs Coppia")
        st.bar_chart(
            {
                "❤️ Vitalità": {"Da Solo (Media Aula)": agg_s["avg_vit"], "In Coppia/Gruppo": agg_g["avg_vit"]},
                "🎯 Controllo Onc.": {"Da Solo (Media Aula)": agg_s["avg_onc"], "In Coppia/Gruppo": agg_g["avg_onc"]},
                "🌿 Qualità di Vita": {"Da Solo (Media Aula)": agg_s["avg_qol"], "In Coppia/Gruppo": agg_g["avg_qol"]},
            },
            use_container_width=True,
        )


def _render_scheda_grafica_medico(runs_per_entita, gruppi_attivi):
    st.markdown("### 📈 Analisi Grafica per Singolo Medico (Da Solo vs Coppia / Gruppo)")

    medici_set = {e for e in runs_per_entita if e not in gruppi_attivi}
    for membri in gruppi_attivi.values():
        medici_set.update(membri)

    medici_ordinati = sorted(medici_set)
    if not medici_ordinati:
        st.info("Nessun dato individuale o di gruppo disponibile per generare i grafici.")
        return

    medico_sel = st.selectbox(
        "Seleziona il Medico da proiettare / analizzare nel dettaglio:",
        medici_ordinati,
        format_func=lambda m: f"Medico / Postazione {m}",
    )

    runs_singolo = runs_per_entita.get(medico_sel, [])
    gruppi_medico = [g for g, membri in gruppi_attivi.items() if medico_sel in membri]
    runs_gruppo = [r for g in gruppi_medico for r in runs_per_entita.get(g, [])]

    stats_singolo = aggrega_metriche_runs(runs_singolo)
    stats_gruppo = aggrega_metriche_runs(runs_gruppo)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Scenari da Solo", stats_singolo["n_runs"], f"{stats_singolo['tot_scelte']} scelte")
    k2.metric(
        "Scenari in Coppia/Gruppo",
        stats_gruppo["n_runs"],
        f"{', '.join(gruppi_medico)}" if gruppi_medico else "Nessun gruppo assegnato",
    )

    err_sing = stats_singolo["pct"]["giallo"] + stats_singolo["pct"]["rosso"]
    err_grup = stats_gruppo["pct"]["giallo"] + stats_gruppo["pct"]["rosso"]
    delta_err = round(err_grup - err_sing, 1) if stats_gruppo["tot_scelte"] > 0 and stats_singolo["tot_scelte"] > 0 else 0
    k3.metric(
        "Errori Critici (🟨+🟥) Solo",
        f"{err_sing}%",
        f"In gruppo: {err_grup}% ({delta_err:+.1f}%)" if stats_gruppo["tot_scelte"] > 0 else "N/D in gruppo",
        delta_color="inverse",
    )
    k4.metric(
        "Spesa Media SSN (Solo)",
        f"{stats_singolo['avg_spesa']:,} €".replace(",", "."),
        f"In gruppo: {stats_gruppo['avg_spesa']:,} €".replace(",", ".") if stats_gruppo["n_runs"] > 0 else "N/D in gruppo",
        delta_color="inverse",
    )

    g_col1, g_col2 = st.columns(2, gap="large")

    with g_col1:
        st.markdown("#### 1. Profilo Decisionale (% Scelte per Colore)")
        dati_colori = {
            "🟩 Tailored Ottimale": {
                "Da Solo": stats_singolo["pct"]["verde"],
                "In Coppia/Gruppo": stats_gruppo["pct"]["verde"] if stats_gruppo["tot_scelte"] > 0 else 0,
            },
            "🟦 Subottimale / Ragionevole": {
                "Da Solo": stats_singolo["pct"]["blu"],
                "In Coppia/Gruppo": stats_gruppo["pct"]["blu"] if stats_gruppo["tot_scelte"] > 0 else 0,
            },
            "🟨 Bulldozer Linea Guida": {
                "Da Solo": stats_singolo["pct"]["giallo"],
                "In Coppia/Gruppo": stats_gruppo["pct"]["giallo"] if stats_gruppo["tot_scelte"] > 0 else 0,
            },
            "🟥 Errore Critico": {
                "Da Solo": stats_singolo["pct"]["rosso"],
                "In Coppia/Gruppo": stats_gruppo["pct"]["rosso"] if stats_gruppo["tot_scelte"] > 0 else 0,
            },
        }
        st.bar_chart(dati_colori, horizontal=False, use_container_width=True)

    with g_col2:
        st.markdown("#### 2. Esiti Clinici Medi Raggiunti (%)")
        dati_esiti = {
            "❤️ Vitalità": {
                "Da Solo": stats_singolo["avg_vit"] if stats_singolo["n_runs"] > 0 else 0,
                "In Coppia/Gruppo": stats_gruppo["avg_vit"] if stats_gruppo["n_runs"] > 0 else 0,
            },
            "🎯 Controllo Oncologico": {
                "Da Solo": stats_singolo["avg_onc"] if stats_singolo["n_runs"] > 0 else 0,
                "In Coppia/Gruppo": stats_gruppo["avg_onc"] if stats_gruppo["n_runs"] > 0 else 0,
            },
            "🌿 Qualità di Vita": {
                "Da Solo": stats_singolo["avg_qol"] if stats_singolo["n_runs"] > 0 else 0,
                "In Coppia/Gruppo": stats_gruppo["avg_qol"] if stats_gruppo["n_runs"] > 0 else 0,
            },
        }
        st.bar_chart(dati_esiti, horizontal=False, use_container_width=True)

    if gruppi_medico and stats_gruppo["tot_scelte"] > 0:
        st.markdown("#### 3. Diagramma Dinamica di Coppia / Gruppo")
        for g_nome in gruppi_medico:
            membri = gruppi_attivi.get(g_nome, [])
            partner = [m for m in membri if m != medico_sel]
            g_runs = runs_per_entita.get(g_nome, [])
            if not g_runs:
                continue
            g_stats = aggrega_metriche_runs(g_runs)
            g_err = round(g_stats["pct"]["giallo"] + g_stats["pct"]["rosso"], 1)

            if stats_singolo["tot_scelte"] > 0:
                if g_err < err_sing - 10:
                    col_arco, etich_dinamica = "#16a34a", "SINERGIA / APERTO AL CONFRONTO"
                elif g_err > err_sing + 10:
                    col_arco, etich_dinamica = "#dc2626", "CONTAGIO / TRASCINAMENTO"
                elif err_sing >= 25:
                    col_arco, etich_dinamica = "#ea580c", "LEADER DOMINANTE (RIPETE ERRORI)"
                else:
                    col_arco, etich_dinamica = "#2563eb", "STABILITÀ DECISIONALE"
            else:
                col_arco, etich_dinamica = "#64748b", "SOLO PROVA IN GRUPPO"

            dot_dinamica = [
                "digraph D {",
                '  rankdir="LR";',
                '  bgcolor="transparent";',
                '  node [shape=box, style="rounded,filled", fontname="Inter,Arial", fontsize=11, margin="0.18,0.12"];',
                f'  "M" [label="Medico {medico_sel} (Da Solo)\\nErrori 🟨+🟥: {err_sing}% | Tailored 🟩: {stats_singolo["pct"]["verde"]}%\\nAnamnesi aperta: {stats_singolo["avg_anamnesi"]}x", fillcolor="#e0e7ff", color="#4338ca", penwidth=2];',
                f'  "G" [label="{g_nome} (Insieme)\\nErrori 🟨+🟥: {g_err}% | Tailored 🟩: {g_stats["pct"]["verde"]}%\\nAnamnesi aperta: {g_stats["avg_anamnesi"]}x", fillcolor="#f8fafc", color="{col_arco}", penwidth=2.5];',
                f'  "M" -> "G" [label=" {etich_dinamica} ", color="{col_arco}", fontcolor="{col_arco}", penwidth=2.2];',
            ]
            for p in partner:
                p_stats = aggrega_metriche_runs(runs_per_entita.get(p, []))
                p_err = round(p_stats["pct"]["giallo"] + p_stats["pct"]["rosso"], 1)
                dot_dinamica.append(
                    f'  "P_{p}" [label="Partner {p} (Da Solo)\\nErrori 🟨+🟥: {p_err}% | Tailored 🟩: {p_stats["pct"]["verde"]}%\\nAnamnesi aperta: {p_stats["avg_anamnesi"]}x", fillcolor="#f1f5f9", color="#64748b", penwidth=1.5];'
                )
                dot_dinamica.append(f'  "P_{p}" -> "G" [style=dashed, color="#64748b"];')
            dot_dinamica.append("}")
            st.graphviz_chart("\n".join(dot_dinamica), use_container_width=True)


def render_osservatorio_master(room):
    """Punto di ingresso unico chiamato da app.py per mostrare l'Osservatorio Errori, Grafici & Export."""
    st.markdown("## 🧠 Osservatorio Regia Master — Debriefing, Proiezione & Export")

    tutti_stati = room.get("stati_casi", {})
    if not tutti_stati:
        st.info("Nessuna simulazione avviata finora dai discenti o dai gruppi.")
        return

    runs_per_entita = {}
    for chiave, v in tutti_stati.items():
        if "__" not in chiave:
            continue
        case_id, entita = chiave.split("__", 1)
        runs_per_entita.setdefault(entita, []).append((case_id, v))

    gruppi_attivi = room.get("gruppi", {})

    exp1, exp2 = st.columns(2)
    with exp1:
        html_report = _genera_report_html_plenario(runs_per_entita, gruppi_attivi)
        st.download_button(
            label="📄 Scarica Report Grafico Finale (HTML / Stampabile PDF)",
            data=html_report,
            file_name=f"Report_Debriefing_2getSIM_{datetime.date.today()}.html",
            mime="text/html",
            type="primary",
            use_container_width=True,
        )
    with exp2:
        csv_report = _genera_csv_esportazione(runs_per_entita, gruppi_attivi)
        st.download_button(
            label="📊 Scarica Tabella Dati Completa (Excel / CSV)",
            data=csv_report,
            file_name=f"Dati_2getSIM_{datetime.date.today()}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()

    tab_plenario, tab_grafici, tab_dettaglio, tab_coppie = st.tabs(
        [
            "📽️ Proiezione Plenaria (Media Aula)",
            "📊 Grafici Singolo Medico",
            "📋 Registro Errori & Bias",
            "👥 Sintesi Coppie / Gruppi",
        ]
    )

    with tab_plenario:
        _render_confronto_plenario_aula(runs_per_entita, gruppi_attivi)

    with tab_grafici:
        _render_scheda_grafica_medico(runs_per_entita, gruppi_attivi)

    with tab_dettaglio:
        st.markdown("### Profilo Decisionale per Postazione / Gruppo")
        for entita, lista_runs in sorted(runs_per_entita.items()):
            with st.expander(f"👤 **{entita}** ({len(lista_runs)} scenari giocati)", expanded=True):
                for case_id, v in lista_runs:
                    sintesi, alerts = analizza_profilo_comportamentale(v)
                    spesa_fmt = f"{v.get('spesa_ssn', 0):,}".replace(",", ".") + " €"
                    st.markdown(
                        f"**Scenario `{case_id}`** — Nodo: `{v['current_node']}` | ❤️ {v['vitalita']}% | 🎯 {v['oncologico']}% | 🌿 {v['qol']}% | 💶 {spesa_fmt} | Anamnesi aperta: **{v.get('consultazioni_anamnesi', 0)}x**"
                    )
                    st.caption(f"Distribuzione scelte: {sintesi}")
                    for a in alerts:
                        st.markdown(f"- {a}")

                    errori = [s for s in v.get("percorso", []) if s.get("colore") in ("giallo", "rosso", "blu")]
                    if errori:
                        with st.popover(f"🔍 Vedi {len(errori)} deviazioni/errori su Scenario {case_id}"):
                            for err in errori:
                                badge_col = {"blu": "🟦", "giallo": "🟨", "rosso": "🟥"}.get(err.get("colore"), "⬜")
                                st.markdown(f"{badge_col} **{err['nodo']}**: _{err['scelta']}_")

    with tab_coppie:
        st.markdown("### Sintesi Dinamiche di Gruppo (Dominante vs Sinergia)")
        if not gruppi_attivi:
            st.caption("Attiva i gruppi nella Regia Master a sinistra per visualizzare il confronto automatico tra prove singole e di coppia.")
        else:
            for nome_gruppo, membri in gruppi_attivi.items():
                runs_gruppo = runs_per_entita.get(nome_gruppo, [])
                if not runs_gruppo:
                    continue

                st.markdown(f"#### 👥 **{nome_gruppo}** (Membri: {', '.join(membri)})")
                err_gruppo = sum(
                    1
                    for _, r in runs_gruppo
                    for s in r.get("percorso", [])
                    if s.get("colore") in ("giallo", "rosso")
                )
                tot_gruppo = max(1, sum(len(r.get("percorso", [])) for _, r in runs_gruppo))
                rate_gruppo = err_gruppo / tot_gruppo

                for m in membri:
                    runs_m = runs_per_entita.get(m, [])
                    if not runs_m:
                        st.caption(f"• **{m}**: nessuna prova individuale registrata.")
                        continue
                    err_m = sum(
                        1
                        for _, r in runs_m
                        for s in r.get("percorso", [])
                        if s.get("colore") in ("giallo", "rosso")
                    )
                    tot_m = max(1, sum(len(r.get("percorso", [])) for _, r in runs_m))
                    rate_m = err_m / tot_m

                    if rate_gruppo < rate_m - 0.15:
                        st.success(f"✅ **{m}** migliora in gruppo (errori critici: da {int(rate_m*100)}% singolo a {int(rate_gruppo*100)}% in gruppo) → **Aperto al confronto**.")
                    elif rate_gruppo > rate_m + 0.15:
                        st.error(f"⚠️ **{m}** peggiora in gruppo (errori critici: da {int(rate_m*100)}% singolo a {int(rate_gruppo*100)}% in gruppo) → **Possibile trascinamento / figura dominante del partner**.")
                    elif rate_m >= 0.30 and abs(rate_gruppo - rate_m) <= 0.15:
                        st.warning(f"👑 **{m}** mantiene gli stessi errori anche in coppia ({int(rate_gruppo*100)}%) → **Possibile figura dominante che impone il proprio schema**.")
                    else:
                        st.info(f"🤝 **{m}** mantiene un profilo lineare e solido sia da solo ({int(rate_m*100)}%) che in gruppo ({int(rate_gruppo*100)}%).")
