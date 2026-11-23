import os, pprint
from datetime import datetime, timezone
import streamlit as st
from case_builder_engine import (
    AMBITI, COLORI_CLINICI, MAPPA_COD_LBL, ORDINE_4, dot_graphviz,
    genera_3_opzioni_snodo, genera_caso_ai, normalizza_json_importato,
    nuovo_snodo, template_v2, valida_v2,
)
from google_db import (
    carica_caso_drive, carica_immagine_drive, elenca_casi_drive,
    pubblica_caso_enterprise, ritira_caso_in_bozza, salva_caso_drive, scarica_immagine_drive,
)


def render_case_builder(case_dir: str = "storycase"):
    st.markdown("## ✍️ Studio Autoriale 2getSIM · Case Builder v2.0")
    st.caption("Master su Google Drive · Pubblicazione Real-Time su Supabase · Durata 8-10 snodi (min. 6 se sempre Rosso)")
    if "builder_v2" not in st.session_state:
        st.session_state.builder_v2 = template_v2()
    if "builder_active_node" not in st.session_state:
        st.session_state.builder_active_node = "snodo1"

    casi = elenca_casi_drive()
    labels = ["-- Nuovo Caso (8 snodi) --"] + [f"{'🟢' if c['stato']=='pubblicato' else '🟡'} {c['case_id']} (v{c['versione']}) — {c['titolo'][:30]}" for c in casi]
    m_id = {labels[i + 1]: casi[i]["case_id"] for i in range(len(casi))}

    c1, c2, c3 = st.columns([2.4, 0.8, 0.8])
    sel = c1.selectbox("Archivio Drive", labels, label_visibility="collapsed")
    if c2.button("📂 Carica", use_container_width=True):
        st.session_state.builder_v2 = template_v2(f"CASO_{len(casi)+1:02d}") if sel.startswith("--") else (carica_caso_drive(m_id[sel]) or template_v2())
        st.session_state.builder_active_node = st.session_state.builder_v2.get("nodo_iniziale", "snodo1")
        st.rerun()
    if c3.button("🆕 Nuovo", use_container_width=True):
        st.session_state.builder_v2 = template_v2(f"CASO_{len(casi)+1:02d}")
        st.session_state.builder_active_node = "snodo1"
        st.rerun()

    st.divider()
    st.markdown("### 1. Scegli la modalità di creazione iniziale")
    modalita_input = st.radio(
        "Modalità di avvio caso clinico:",
        [
            "📋 Importa JSON (generato su Gemini Chat — Gratuito)",
            "🧠 Genera con AI Studio (Testo libero + PDF / Word / Biblioteca Drive)",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )

    if modalita_input.startswith("📋"):
        with st.container(border=True):
            st.caption("Incolla qui il JSON generato dalla tua chat Gemini: verrà caricato nell'editor sottostante per qualsiasi modifica e salvataggio su Drive/Supabase.")
            raw_json = st.text_area("Codice JSON v2.0:", height=140, placeholder='{"schema_version": "2.0", "meta": ...}', key="import_json_box")
            if st.button("⬆️ Carica JSON nell'Editor e Salva Bozza su Drive", type="primary"):
                if not raw_json.strip():
                    st.warning("Incolla prima il codice JSON.")
                else:
                    ok_j, res_j = normalizza_json_importato(raw_json)
                    if ok_j:
                        st.session_state.builder_v2 = salva_caso_drive(res_j)
                        st.session_state.builder_active_node = st.session_state.builder_v2.get("nodo_iniziale", "snodo1")
                        st.success(f"✅ Caso `{res_j['meta']['case_id']}` importato e salvato in Bozza su Drive! Modificalo qui sotto o premi PUBBLICA.")
                        st.rerun()
                    else:
                        st.error(res_j)
    else:
        with st.container(border=True):
            g1, g2, g3 = st.columns([1.2, 1, 0.8])
            ncid = g1.text_input("Codice Caso", value=st.session_state.builder_v2["meta"]["case_id"]).strip().upper()
            amb = g2.selectbox("Organo", list(AMBITI.keys()), format_func=lambda k: AMBITI[k])
            nsn = g3.number_input("Snodi (8-10)", 8, 12, 9)
            spunto = st.text_area("Testo libero (caso reale, referto, comorbidità, trappole da inserire):", height=95)
            f1, f2 = st.columns([2.2, 1])
            files_loc = f1.file_uploader("Allega file extra (PDF, Word .docx, TXT — opzionale):", type=["pdf", "docx", "txt", "md"], accept_multiple_files=True)
            usa_biblio = f2.checkbox("Includi anche Biblioteca PDF Drive", value=True)
            if st.button("🧠 Genera Caso Clinico con AI Studio", type="primary"):
                if not ncid or (not spunto.strip() and not files_loc):
                    st.warning("Inserisci il Codice Caso e almeno un testo libero o un file allegato.")
                else:
                    with st.spinner("Analisi testi/allegati e generazione albero clinico 8-10 snodi..."):
                        ok_g, res_g = genera_caso_ai(ncid, amb, spunto, int(nsn), files_loc, usa_biblio)
                    if ok_g:
                        st.session_state.builder_v2 = salva_caso_drive(res_g)
                        st.session_state.builder_active_node = "snodo1"
                        st.success("✅ Caso generato e salvato in Bozza su Drive! Rifiniscilo qui sotto o premi PUBBLICA.")
                        st.rerun()
                    else:
                        st.error(res_g)

    dati = st.session_state.builder_v2
    meta = dati["meta"]

    st.divider()
    b1, b2, b3, b4 = st.columns([1.8, 1.1, 1.3, 0.9])
    b1.markdown(f"**`{meta['case_id']}`** · v{meta.get('versione', 1)} · {'🟢 PUBBLICATO' if meta.get('stato')=='pubblicato' else '🟡 BOZZA'}")
    if b2.button("💾 Salva Bozza", use_container_width=True):
        if meta.get("case_id") and meta.get("titolo"):
            st.session_state.builder_v2 = salva_caso_drive(dati)
            st.success("Bozza salvata su Drive.")
        else:
            st.error("Inserisci Codice Caso e Titolo.")
    if b3.button("🚀 PUBBLICA", type="primary", use_container_width=True):
        ok_v, avv = valida_v2(dati)
        if not ok_v:
            for a in avv:
                st.error(a)
        else:
            with st.spinner("Pubblicazione su Drive e Supabase..."):
                ok_p, msg_p, d_agg = pubblica_caso_enterprise(dati)
                st.session_state.builder_v2 = d_agg
                if ok_p:
                    try:
                        os.makedirs(case_dir, exist_ok=True)
                        t0 = d_agg.get("paziente_t0", {})
                        leg = {"titolo": meta["titolo"], "sottotitolo": meta.get("sottotitolo", ""), "descrizione_master": meta.get("descrizione_master", ""), "nodo_iniziale": "snodo1", "vitalita_iniziale": t0.get("vitalita_iniziale", 80), "oncologico_iniziale": t0.get("oncologico_iniziale", 55), "qol_iniziale": t0.get("qol_iniziale", 75), "scheda_paziente": t0.get("scheda_paziente", ""), "nodi": d_agg["nodi"], "esiti": d_agg["esiti"]}
                        with open(os.path.join(case_dir, f"{meta['case_id']}.py"), "w", encoding="utf-8") as f:
                            f.write(f"CASO = {pprint.pformat(leg, width=100, sort_dicts=False)}\n")
                    except Exception:
                        pass
                    st.success(msg_p)
                else:
                    st.error(msg_p)
    if meta.get("stato") == "pubblicato" and b4.button("⏸️ Bozza", use_container_width=True):
        _, msg_r, d_agg = ritira_caso_in_bozza(dati)
        st.session_state.builder_v2 = d_agg
        st.warning(msg_r)

    t1, t2, t3, t4 = st.tabs(["1️⃣ Paziente T0 & Mine", "2️⃣ Grafo & Snodi", "3️⃣ Esiti", "4️⃣ Fine-Tuning & JSON"])
    with t1:
        x1, x2 = st.columns([1, 2])
        meta["case_id"] = x1.text_input("Codice", value=meta["case_id"], key="m_id").strip().upper()
        meta["area_clinica"] = x2.selectbox("Area", list(AMBITI.keys()), index=list(AMBITI.keys()).index(meta.get("area_clinica", "vescica")), format_func=lambda k: AMBITI[k], key="m_ar")
        meta["titolo"] = st.text_input("Titolo", value=meta.get("titolo", ""))
        meta["sottotitolo"] = st.text_input("Sottotitolo", value=meta.get("sottotitolo", ""))
        meta["descrizione_master"] = st.text_input("Note Regia", value=meta.get("descrizione_master", ""))
        t0 = dati.setdefault("paziente_t0", {})
        cal = t0.setdefault("calibrazione_t0", {})
        k1, k2, k3 = st.columns(3)
        t0["vitalita_iniziale"] = k1.slider("❤️ Vitalità T0", 0, 100, int(t0.get("vitalita_iniziale", 80)))
        cal["vitalita_motivo"] = k1.text_input("Motivo Vit.", value=cal.get("vitalita_motivo", ""))
        t0["oncologico_iniziale"] = k2.slider("🎯 Oncologico T0", 0, 100, int(t0.get("oncologico_iniziale", 55)))
        cal["oncologico_motivo"] = k2.text_input("Motivo Onc.", value=cal.get("oncologico_motivo", ""))
        t0["qol_iniziale"] = k3.slider("🌿 QoL T0", 0, 100, int(t0.get("qol_iniziale", 75)))
        cal["qol_motivo"] = k3.text_input("Motivo QoL", value=cal.get("qol_motivo", ""))
        t0["scheda_paziente"] = st.text_area("Cartella Paziente T0", value=t0.get("scheda_paziente", ""), height=120)
        mine = t0.setdefault("mine_psicologiche", {})
        m1, m2 = st.columns(2)
        mine["trappola_urologo"] = m1.text_area("🔪 Mina Urologo", value=mine.get("trappola_urologo", ""), height=70)
        mine["trappola_oncologo"] = m2.text_area("💉 Mina Oncologo", value=mine.get("trappola_oncologo", ""), height=70)

    with t2:
        st.graphviz_chart(dot_graphviz(dati), use_container_width=True)
        lnodi = list(dati["nodi"].keys())
        if st.session_state.builder_active_node not in lnodi:
            st.session_state.builder_active_node = lnodi[0]
        n1, n2, n3 = st.columns([2.6, 0.7, 0.7])
        sid = n1.selectbox("Snodo", lnodi, index=lnodi.index(st.session_state.builder_active_node), format_func=lambda x: f"{x} — {dati['nodi'][x].get('titolo', '')}")
        st.session_state.builder_active_node = sid
        if n2.button("➕ Snodo", use_container_width=True):
            nid = f"snodo{len(lnodi)+1}"
            dati["nodi"][nid] = nuovo_snodo(nid)
            st.session_state.builder_active_node = nid
            st.rerun()
        if len(lnodi) > 1 and n3.button("🗑️ Elimina", use_container_width=True):
            del dati["nodi"][sid]
            st.session_state.builder_active_node = list(dati["nodi"].keys())[0]
            st.rerun()

        sn = dati["nodi"][sid]
        sn["titolo"] = st.text_input("Titolo snodo", value=sn.get("titolo", ""), key=f"t_{sid}")
        sn["testo"] = st.text_area("Testo snodo", value=sn.get("testo", ""), key=f"x_{sid}", height=80)
        sn["is_post_rosso"] = st.checkbox("⚠️ Post-errore Rosso (0V / 2B / 1G / 1R)", value=bool(sn.get("is_post_rosso", False)), key=f"pr_{sid}")

        up = st.file_uploader("Allega immagine diagnostica", type=["png", "jpg", "jpeg", "webp"], key=f"u_{sid}")
        if up and st.button("☁️ Carica su Drive", key=f"su_{sid}"):
            sn["immagine"] = carica_immagine_drive(up, meta["case_id"], sid)
            salva_caso_drive(dati)
            st.success("Immagine collegata.")
        if sn.get("immagine", "").startswith("drive:"):
            try:
                st.image(scarica_immagine_drive(sn["immagine"]), width=280)
            except Exception:
                pass

        while len(sn["opzioni"]) < 4:
            c = ORDINE_4[len(sn["opzioni"])]
            cfg = COLORI_CLINICI[MAPPA_COD_LBL[c]]
            sn["opzioni"].append({"testo": "", "colore": c, "d_vit": cfg["d_vit"], "d_onc": cfg["d_onc"], "d_qol": cfg["d_qol"], "effetto_ritardato": False, "razionale": "", "next": "esito_parziale"})

        dests = [n for n in lnodi if n != sid] + list(dati["esiti"].keys())
        for i in range(4):
            o = sn["opzioni"][i]
            lbl = MAPPA_COD_LBL.get(o.get("colore", ORDINE_4[i]), MAPPA_COD_LBL["blu"])
            ic = COLORI_CLINICI[lbl]
            st.markdown(f"<div style='border-left:5px solid {ic['hex']};background:{ic['bg']};padding:4px 10px;border-radius:4px;margin-top:8px;color:#0f172a'><b>Opz. {i+1}</b> · {lbl}</div>", unsafe_allow_html=True)
            ct, cc, cn = st.columns([2.2, 1.3, 1.3])
            old = o.get("testo", "")
            o["testo"] = ct.text_input("Comando", value=old, key=f"ot_{sid}_{i}", label_visibility="collapsed")
            if o["testo"] != old and old.strip():
                why = st.text_input(f"💡 Perché hai cambiato '{old}' → '{o['testo']}'?", key=f"w_{sid}_{i}")
                if why:
                    dati.setdefault("changelog_finetuning", []).append({"ts": datetime.now(timezone.utc).isoformat(), "snodo": sid, "prima": old, "dopo": o["testo"], "perche": why})
            slbl = cc.selectbox("Col", list(COLORI_CLINICI.keys()), index=list(COLORI_CLINICI.keys()).index(lbl), key=f"oc_{sid}_{i}", label_visibility="collapsed")
            o["colore"] = COLORI_CLINICI[slbl]["codice"]
            curr_n = o.get("next") if o.get("next") in dests else dests[0]
            o["next"] = cn.selectbox("Next", dests, index=dests.index(curr_n), key=f"on_{sid}_{i}", label_visibility="collapsed")
            d1, d2, d3, d4, d5 = st.columns([0.7, 0.7, 0.7, 1.0, 2.5])
            o["d_vit"] = d1.number_input("ΔVit", value=int(o.get("d_vit", 0)), key=f"dv_{sid}_{i}")
            o["d_onc"] = d2.number_input("ΔOnc", value=int(o.get("d_onc", 0)), key=f"do_{sid}_{i}")
            o["d_qol"] = d3.number_input("ΔQoL", value=int(o.get("d_qol", 0)), key=f"dq_{sid}_{i}")
            o["effetto_ritardato"] = d4.checkbox("Ritardato", value=bool(o.get("effetto_ritardato", False)), key=f"er_{sid}_{i}")
            o["razionale"] = d5.text_input("Razionale", value=o.get("razionale", ""), key=f"rz_{sid}_{i}")
            if i == 0 and st.button("✨ Genera Blu/Gialla/Rossa snodo", key=f"ai_{sid}") and o["testo"].strip():
                ok_s, rs = genera_3_opzioni_snodo(dati, sid, o["testo"].strip())
                if ok_s:
                    for j, ck in enumerate(("blu", "gialla", "rossa"), 1):
                        sn["opzioni"][j]["testo"], sn["opzioni"][j]["razionale"] = rs[ck]["testo"], rs[ck].get("razionale", "")
                    st.rerun()
                else:
                    st.error(rs)

    with t3:
        for eid, es in dati.get("esiti", {}).items():
            es["titolo"] = st.text_input(f"Titolo {eid}", value=es.get("titolo", ""), key=f"et_{eid}")
            es["descrizione"] = st.text_area(f"Descrizione {eid}", value=es.get("descrizione", ""), key=f"ed_{eid}", height=68)
            es["debriefing_master"] = st.text_area(f"Debriefing Master {eid}", value=es.get("debriefing_master", ""), key=f"eb_{eid}", height=68)

    with t4:
        st.json(dati.get("changelog_finetuning", []))
        st.json(dati)
