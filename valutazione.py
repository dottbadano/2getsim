import csv
import datetime
import html
import io
import streamlit as st


def aggrega_metriche_runs(lista_runs):
    conteggi = {"verde": 0, "blu": 0, "giallo": 0, "rosso": 0}
    tot_scelte = 0
    s_vit, s_onc, s_qol, s_anam = 0, 0, 0, 0
    n_runs = len(lista_runs)
    for _, r in lista_runs:
        s_vit += max(0, min(100, r.get("vitalita", 100)))
        s_onc += max(0, min(100, r.get("oncologico", 100)))
        s_qol += max(0, min(100, r.get("qol", 75)))
        s_anam += r.get("consultazioni_anamnesi", 0)
        for step in r.get("percorso", []):
            col = step.get("colore", "blu")
            conteggi[col] = conteggi.get(col, 0) + 1
            tot_scelte += 1
    d_scelte = max(1, tot_scelte)
    d_runs = max(1, n_runs)
    pct = {k: round((v / d_scelte) * 100, 1) for k, v in conteggi.items()}
    return {
        "n_runs": n_runs,
        "tot_scelte": tot_scelte,
        "conteggi": conteggi,
        "pct": pct,
        "avg_vit": round(s_vit / d_runs, 1),
        "avg_onc": round(s_onc / d_runs, 1),
        "avg_qol": round(s_qol / d_runs, 1),
        "avg_anamnesi": round(s_anam / d_runs, 1),
    }


def analizza_profilo_comportamentale(stato_run):
    percorso = stato_run.get("percorso", [])
    if not percorso:
        return "In attesa della prima scelta", []
    c = {"verde": 0, "blu": 0, "giallo": 0, "rosso": 0}
    for step in percorso:
        col = step.get("colore", "blu")
        c[col] = c.get(col, 0) + 1
    tot = len(percorso)
    cons = stato_run.get("consultazioni_anamnesi", 0)
    alert = []
    if c["giallo"] >= 2 or (c["giallo"] >= 1 and cons == 0 and tot >= 2):
        alert.append("Effetto Bulldozer: scelte standard non adattate alle comorbidità.")
    if c["rosso"] >= 2:
        alert.append("Errori Clinici Critici Ricorrenti.")
    if cons == 0 and tot >= 3:
        alert.append("Anamnesi mai riaperta dopo il primo snodo.")
    if c["verde"] / tot >= 0.75 and cons >= 1:
        alert.append("Approccio Tailored: ragionamento mirato sul paziente.")
    if not alert:
        alert.append("Profilo Misto / Prudente.")
    sintesi = f"🟩 {c['verde']} | 🟦 {c['blu']} | 🟨 {c['giallo']} | 🟥 {c['rosso']}"
    return sintesi, alert


def _genera_csv(runs_per_entita, gruppi_attivi):
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Postazione", "Modalita", "Scenario", "Nodo", "Vit%", "Onc%", "QoL%", "V", "B", "G", "R"])
    for ent, lista in sorted(runs_per_entita.items()):
        mod = "Gruppo" if ent in gruppi_attivi else "Singolo"
        for cid, v in lista:
            c = {"verde": 0, "blu": 0, "giallo": 0, "rosso": 0}
            for s in v.get("percorso", []):
                col = s.get("colore", "blu")
                c[col] = c.get(col, 0) + 1
            w.writerow([
                ent, mod, cid, v.get("current_node", ""),
                v.get("vitalita", 0), v.get("oncologico", 0), v.get("qol", 0),
                c["verde"], c["blu"], c["giallo"], c["rosso"],
            ])
    return out.getvalue().encode("utf-8-sig")


def _genera_html(runs_per_entita, gruppi_attivi):
    ora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    righe = []
    for ent, lista in sorted(runs_per_entita.items()):
        st_e = aggrega_metriche_runs(lista)
        mod = "Gruppo" if ent in gruppi_attivi else "Singolo"
        righe.append(
            f"<tr><td>{html.escape(ent)} ({mod})</td>"
            f"<td>🟩 {st_e['pct']['verde']}% | 🟨 {st_e['pct']['giallo']}% | 🟥 {st_e['pct']['rosso']}%</td>"
            f"<td>Vit {st_e['avg_vit']}% | Onc {st_e['avg_onc']}% | QoL {st_e['avg_qol']}%</td></tr>"
        )
    tabella = "".join(righe)
    return (
        f"<html><head><meta charset='UTF-8'></head><body style='font-family:sans-serif;'>"
        f"<h2>Report 2getSIM ({ora})</h2>"
        f"<table border='1' cellpadding='8' cellspacing='0'><tr><th>Postazione</th><th>Scelte</th><th>Esiti</th></tr>"
        f"{tabella}</table></body></html>"
    )


def render_osservatorio_master(room, role="master"):
    st.markdown("## 🧠 Osservatorio Regia Master — Debriefing & Export")
    tutti_stati = room.get("stati_casi", {})
    if not tutti_stati:
        st.info("Nessuna simulazione avviata finora.")
        return

    gruppi_raw = room.get("gruppi_personalizzati", {})
    gruppi_attivi = {}
    slug_to_gruppo = {}
    for nome_g, membri in gruppi_raw.items():
        slug = "gruppo_" + "".join(ch if ch.isalnum() else "_" for ch in nome_g.lower())
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
        st.info("Nessuna simulazione discente attiva (le prove Master sono escluse).")
        return

    c1, c2 = st.columns(2)
    c1.download_button(
        "📄 Scarica Report HTML / PDF",
        data=_genera_html(runs_per_entita, gruppi_attivi),
        file_name=f"Report_2getSIM_{datetime.date.today()}.html",
        mime="text/html",
        use_container_width=True,
    )
    c2.download_button(
        "📊 Scarica CSV",
        data=_genera_csv(runs_per_entita, gruppi_attivi),
        file_name=f"Dati_2getSIM_{datetime.date.today()}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.divider()

    t1, t2, t3 = st.tabs(["📽️ Sintesi Aula", "📋 Registro Errori & Bias", "👥 Confronto Gruppi"])

    with t1:
        singoli, gruppi = [], []
        for ent, lista in runs_per_entita.items():
            (gruppi if ent in gruppi_attivi else singoli).extend(lista)
        agg_s = aggrega_metriche_runs(singoli)
        agg_g = aggrega_metriche_runs(gruppi)
        st.bar_chart({
            "🟩 Tailored": {"Da Solo": agg_s["pct"]["verde"], "In Gruppo": agg_g["pct"]["verde"]},
            "🟦 Subottimale": {"Da Solo": agg_s["pct"]["blu"], "In Gruppo": agg_g["pct"]["blu"]},
            "🟨 Bulldozer": {"Da Solo": agg_s["pct"]["giallo"], "In Gruppo": agg_g["pct"]["giallo"]},
            "🟥 Critico": {"Da Solo": agg_s["pct"]["rosso"], "In Gruppo": agg_g["pct"]["rosso"]},
        }, use_container_width=True)

    with t2:
        for ent, lista in sorted(runs_per_entita.items()):
            with st.expander(f"👤 **{ent}** ({len(lista)} scenari)", expanded=True):
                for cid, v in lista:
                    sintesi, alerts = analizza_profilo_comportamentale(v)
                    st.markdown(f"**Scenario `{cid}`** — `{v['current_node']}` | ❤️ {v['vitalita']}% | 🎯 {v['oncologico']}% | 🌿 {v['qol']}%")
                    st.caption(f"Distribuzione: {sintesi} — {' | '.join(alerts)}")
                    errori = [s for s in v.get("percorso", []) if s.get("colore") in ("giallo", "rosso", "blu")]
                    for err in errori:
                        dot = {"blu": "🟦", "giallo": "🟨", "rosso": "🟥"}.get(err.get("colore"), "⬜")
                        st.markdown(f"- {dot} **{err['nodo']}**: _{err['scelta']}_")
                        if err.get("razionale"):
                            st.caption(f"  💡 {err['razionale']}")

    with t3:
        if not gruppi_attivi:
            st.caption("Attiva i gruppi nella Regia Master per visualizzare il confronto.")
        else:
            for nome_g, membri in gruppi_attivi.items():
                runs_g = runs_per_entita.get(nome_g, [])
                if not runs_g:
                    continue
                st.markdown(f"#### 👥 **{nome_g}** ({', '.join(membri)})")
                err_g = sum(1 for _, r in runs_g for s in r.get("percorso", []) if s.get("colore") in ("giallo", "rosso"))
                tot_g = max(1, sum(len(r.get("percorso", [])) for _, r in runs_g))
                rate_g = err_g / tot_g
                for m in membri:
                    runs_m = runs_per_entita.get(m, [])
                    if not runs_m:
                        st.caption(f"• **{m}**: nessuna prova individuale.")
                        continue
                    err_m = sum(1 for _, r in runs_m for s in r.get("percorso", []) if s.get("colore") in ("giallo", "rosso"))
                    tot_m = max(1, sum(len(r.get("percorso", [])) for _, r in runs_m))
                    rate_m = err_m / tot_m
                    if rate_g < rate_m - 0.15:
                        st.success(f"✅ **{m}** migliora in gruppo ({int(rate_m*100)}% → {int(rate_g*100)}%)")
                    elif rate_g > rate_m + 0.15:
                        st.error(f"⚠️ **{m}** peggiora in gruppo ({int(rate_m*100)}% → {int(rate_g*100)}%)")
                    else:
                        st.info(f"🤝 **{m}** stabile ({int(rate_m*100)}% vs {int(rate_g*100)}%)")
