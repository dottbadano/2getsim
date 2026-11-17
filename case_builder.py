import os
import pprint
import streamlit as st


def render_case_builder(case_dir="casi_clinici"):
    st.markdown("## ✍️ Editor Visuale Casi Clinici (Modalità Master)")
    st.caption("Compila i campi in italiano: il sistema genera automaticamente il file nella cartella casi_clinici/.")

    if "builder_caso" not in st.session_state:
        st.session_state.builder_caso = {
            "badge": "CASO 002 — ARENA URO-ONCOLOGICA",
            "titolo": "",
            "sottotitolo": "",
            "nodo_iniziale": "snodo1",
            "vitalita_iniziale": 100,
            "oncologico_iniziale": 100,
            "qol_iniziale": 75,
            "scheda_paziente": "* **Paziente:** Uomo, 70 anni, ECOG PS 0.\n* **Anamnesi:** \n* **Esame obiettivo:** \n* **Esami:** ",
            "nodi": {
                "snodo1": {
                    "titolo": "📍 Snodo 1 — Prima scelta clinica",
                    "testo": "Descrivi la situazione clinica iniziale...",
                    "opzioni": [
                        {"testo": "A) Opzione 1", "d_vit": 0, "d_onc": 10, "d_qol": 0, "next": "esito_vittoria"},
                        {"testo": "B) Opzione 2", "d_vit": -10, "d_onc": -20, "d_qol": -10, "next": "esito_sconfitta"},
                    ],
                }
            },
            "esiti": {
                "esito_vittoria": {
                    "tipo": "bianco",
                    "titolo": "🏆 TAZZA BIANCA CONQUISTATA!",
                    "sottotitolo": '"Failure is not an option."',
                    "descrizione": "Gestione clinica ottimale.",
                },
                "esito_sconfitta": {
                    "tipo": "rosso",
                    "titolo": "❌ TAZZA ROSSA ASSEGNATA!",
                    "sottotitolo": '"Shit... happens."',
                    "descrizione": "Complicanza maggiore o progressione non intercettata.",
                },
            },
        }

    dati = st.session_state.builder_caso

    # 1. Dati Generali e Cartella Paziente
    with st.expander("1️⃣ Intestazione e Cartella Paziente", expanded=True):
        c1, c2 = st.columns([1, 2])
        file_id = c1.text_input("Codice File (es. 002, 003)", value="002").strip()
        dati["badge"] = c2.text_input("Etichetta Badge", value=dati["badge"])
        dati["titolo"] = st.text_input("Titolo del Caso", value=dati["titolo"], placeholder="es. Neoplasia vescicale non muscolo-invasiva ad alto rischio")
        dati["sottotitolo"] = st.text_input("Sottotitolo", value=dati["sottotitolo"])
        dati["scheda_paziente"] = st.text_area("Cartella Paziente (usa * per i punti elenco)", value=dati["scheda_paziente"], height=150)

    # 2. Gestione Snodi Decisionali
    with st.expander("2️⃣ Snodi Decisionali e Bivi", expanded=True):
        c_add1, c_add2 = st.columns([3, 1])
        nuovo_snodo_id = c_add1.text_input("ID nuovo snodo (senza spazi)", placeholder="es. snodo2, snodo3a").strip()
        if c_add2.button("➕ Aggiungi Snodo", use_container_width=True) and nuovo_snodo_id:
            if nuovo_snodo_id not in dati["nodi"]:
                dati["nodi"][nuovo_snodo_id] = {
                    "titolo": f"📍 {nuovo_snodo_id.upper()}",
                    "testo": "Descrivi cosa succede al paziente...",
                    "opzioni": [
                        {"testo": "A) Scelta 1", "d_vit": 0, "d_onc": 10, "d_qol": 0, "next": "esito_vittoria"},
                        {"testo": "B) Scelta 2", "d_vit": -10, "d_onc": -20, "d_qol": -10, "next": "esito_sconfitta"},
                    ],
                }
                st.rerun()

        destinazioni_possibili = list(dati["nodi"].keys()) + list(dati["esiti"].keys())
        dati["nodo_iniziale"] = st.selectbox("Snodo di partenza:", list(dati["nodi"].keys()))

        for s_id in list(dati["nodi"].keys()):
            st.markdown("---")
            col_t, col_del = st.columns([5, 1])
            col_t.markdown(f"#### Snodo: `{s_id}`")
            if len(dati["nodi"]) > 1 and col_del.button("🗑️ Elimina", key=f"del_s_{s_id}"):
                del dati["nodi"][s_id]
                st.rerun()

            snodo = dati["nodi"][s_id]
            snodo["titolo"] = st.text_input("Titolo snodo", value=snodo["titolo"], key=f"t_{s_id}")
            snodo["testo"] = st.text_area("Situazione clinica / Domanda", value=snodo["testo"], key=f"txt_{s_id}", height=90)

            for idx, opt in enumerate(snodo["opzioni"]):
                st.caption(f"Opzione {idx + 1}")
                o1, o2 = st.columns([3, 1.2])
                opt["testo"] = o1.text_input("Testo risposta", value=opt["testo"], key=f"opt_{s_id}_{idx}", label_visibility="collapsed")
                curr_next = opt["next"] if opt["next"] in destinazioni_possibili else destinazioni_possibili[0]
                opt["next"] = o2.selectbox("Porta a:", destinazioni_possibili, index=destinazioni_possibili.index(curr_next), key=f"nxt_{s_id}_{idx}", label_visibility="collapsed")

                p1, p2, p3, p4 = st.columns([1, 1, 1, 0.5])
                opt["d_vit"] = p1.number_input("Δ Vitalità", value=int(opt["d_vit"]), step=5, key=f"vit_{s_id}_{idx}")
                opt["d_onc"] = p2.number_input("Δ Oncologico", value=int(opt["d_onc"]), step=5, key=f"onc_{s_id}_{idx}")
                opt["d_qol"] = p3.number_input("Δ QoL", value=int(opt["d_qol"]), step=5, key=f"qol_{s_id}_{idx}")
                if len(snodo["opzioni"]) > 2 and p4.button("❌", key=f"rm_opt_{s_id}_{idx}"):
                    snodo["opzioni"].pop(idx)
                    st.rerun()

            if st.button(f"➕ Aggiungi Opzione a {s_id}", key=f"add_opt_{s_id}"):
                lettera = chr(65 + len(snodo["opzioni"]))
                snodo["opzioni"].append({"testo": f"{lettera}) Nuova opzione", "d_vit": 0, "d_onc": 0, "d_qol": 0, "next": "esito_vittoria"})
                st.rerun()

    # 3. Personalizzazione Esiti Finali
    with st.expander("3️⃣ Esiti Finali (Tazza Bianca / Gialla / Rossa)", expanded=False):
        for e_id, esito in dati["esiti"].items():
            st.markdown(f"**Esito: `{e_id}`**")
            esito["titolo"] = st.text_input("Titolo esito", value=esito["titolo"], key=f"et_{e_id}")
            esito["descrizione"] = st.text_area("Spiegazione finale per l'aula", value=esito["descrizione"], key=f"ed_{e_id}")

    # 4. Salvataggio e Download per GitHub
    st.divider()
    codice_generato = f"CASO = {pprint.pformat(dati, width=100, sort_dicts=False)}\n"

    c_save, c_dl = st.columns(2)
    with c_save:
        if st.button("💾 Salva subito nella cartella casi_clinici/", use_container_width=True):
            if not file_id or not dati["titolo"]:
                st.error("Inserisci almeno il Codice File (es. 002) e il Titolo del Caso.")
            else:
                os.makedirs(case_dir, exist_ok=True)
                percorso = os.path.join(case_dir, f"{file_id}.py")
                with open(percorso, "w", encoding="utf-8") as f:
                    f.write(codice_generato)
                st.success(f"Caso salvato in '{percorso}'! È già selezionabile nel menu a sinistra.")

    with c_dl:
        st.download_button(
            label=f"⬇️ Scarica {file_id or 'caso'}.py (per GitHub)",
            data=codice_generato,
            file_name=f"{file_id or 'caso'}.py",
            mime="text/x-python",
            use_container_width=True,
        )
