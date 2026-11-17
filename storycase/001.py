CASO = {
    "badge": "CASO 001 — ARENA URO-ONCOLOGICA",
    "titolo": "Il Paziente con RAU, Macroematuria e PSA 12",
    "sottotitolo": "Gestione integrata tra ostruzione meccanica, imaging e target molecolari.",
    "nodo_iniziale": "snodo1",
    "vitalita_iniziale": 100,
    "oncologico_iniziale": 100,
    "qol_iniziale": 75,
    "scheda_paziente": """
* **Paziente:** Uomo, 67 anni, ECOG PS 0.
* **Anamnesi:** Ipertensione arteriosa in olmesartan 20 mg; dislipidemia in rosuvastatina 10 mg.
* **Anamnesi familiare:** Madre deceduta per carcinoma mammario a 58 anni; fratello operato per carcinoma prostatico a 62 anni.
* **Esordio:** Accesso in PS 10 giorni fa per **ritenzione acuta d'urina (RAU)** risolta con catetere Foley 18 Ch + tamsulosina. Giunge oggi in ambulatorio per comparsa da 3 giorni di **macroematuria intermittente con piccoli coaguli**.
* **Esame obiettivo:** DRE negativa (prostata ~65 cc liscia, parenchimatosa, indolente, cT1c).
* **Esami ematochimici:** **PSA 12,0 ng/ml**, Hb 13,2 g/dl, Creatinina 1,02 mg/dl, urinocoltura negativa.
""",
    "nodi": {
        "snodo1": {
            "titolo": "📍 Snodo 1 — La prima scelta in ambulatorio",
            "testo": "Il paziente si presenta con catetere a dimora, macroematuria intermittente, DRE negativa e PSA 12,0 ng/ml. Qual è la tua mossa diagnostica primaria?",
            "opzioni": [
                {
                    "testo": "A) rM multiparametrica della prostata + Uretrocistoscopia ambulatoriale",
                    "d_vit": 0,
                    "d_onc": 10,
                    "d_qol": 0,
                    "next": "snodo3",
                },
                {
                    "testo": "B) Uro-TC torace-addome-pelvi con mdc per sospetta neoplasia uroteliale",
                    "d_vit": 0,
                    "d_onc": -5,
                    "d_qol": 0,
                    "next": "snodo2_urotc",
                },
                {
                    "testo": "C) TURP + TURB disostruttiva ed emostatica immediata in sala operatoria",
                    "d_vit": -5,
                    "d_onc": -25,
                    "d_qol": -10,
                    "next": "snodo2_post_turp",
                },
                {
                    "testo": "D) Cistoclisi continua e rivalutazione del PSA a 2 mesi a catetere rimosso",
                    "d_vit": -5,
                    "d_onc": -20,
                    "d_qol": -15,
                    "next": "snodo3",
                },
            ],
        },
        "snodo2_urotc": {
            "titolo": "📍 Snodo 2A — La trappola della Uro-TC e della vescica da sforzo",
            "testo": "La Uro-TC mostra minima ectasia pielocaliceale destra di I grado e **pareti vescicali diffusamente ispessite, trabecolate e disomogenee (vescica da sforzo)** attorno al Foley, senza difetti di riempimento ureterali. Come procedi?",
            "opzioni": [
                {
                    "testo": "A) Ureterorenoscopia (URS) diagnostica destra + biopsie vescicali random e citologia",
                    "d_vit": -10,
                    "d_onc": -20,
                    "d_qol": -15,
                    "next": "snodo3",
                },
                {
                    "testo": "B) Uretrocistoscopia ambulatoriale + rM multiparametrica della prostata",
                    "d_vit": 0,
                    "d_onc": 5,
                    "d_qol": 0,
                    "next": "snodo3",
                },
                {
                    "testo": "C) Nefroureterectomia destra / posizionamento stent ureterale permanente",
                    "d_vit": -35,
                    "d_onc": -45,
                    "d_qol": -40,
                    "next": "esito_sconfitta",
                },
                {
                    "testo": "D) Sola sorveglianza ecografica a 6 mesi",
                    "d_vit": -15,
                    "d_onc": -35,
                    "d_qol": -20,
                    "next": "snodo3",
                },
            ],
        },
        "snodo2_post_turp": {
            "titolo": "📍 Snodo 2B — Binario Complicato: Riscontro Incidentale Post-TURP",
            "testo": "L'istologico sui frustoli di TURP rivela un **Adenocarcinoma prostatico ISUP 5 (Gleason 4+5) sul 65% del tessuto**. Il paziente ha rimosso il catetere ma presenta incontinenza da urgenza (2 pad/die) e il PSA a 30 giorni è ancora **6,8 ng/ml**. La rM post-TURP mostra artefatti ematici e residuo anteriore cT3a; PET-PSMA: miN0 M0. Come procedi?",
            "opzioni": [
                {
                    "testo": "A) Prostatectomia radicale di completamento + linfadenectomia pelvica estesa",
                    "d_vit": -5,
                    "d_onc": 5,
                    "d_qol": -10,
                    "next": "snodo4a",
                },
                {
                    "testo": "B) Radioterapia radicale pelvica + LHRH + ARSI (Abiraterone) per 24 mesi",
                    "d_vit": -10,
                    "d_onc": 0,
                    "d_qol": -20,
                    "next": "esito_sconfitta",
                },
                {
                    "testo": "C) Sola ADT (LHRH) continuativa",
                    "d_vit": -15,
                    "d_onc": -30,
                    "d_qol": -15,
                    "next": "esito_sconfitta",
                },
            ],
        },
        "snodo3": {
            "titolo": "📍 Snodo 3 — rM Prostata Anteriore PI-RADS 5 e Scelta Terapeutica Primaria",
            "testo": "La rM svela una lesione anteriore di **23 mm PI-RADS 5 con invasione extracapsulare anteriore nello spazio di Retzius (cT3a)** (zona posteriore liscia). Biopsia fusion: **Adenocarcinoma ISUP 5 (Gleason 4+5)**. PET-PSMA: `miN0 M0`. Fallito tentativo di scateteramento (catetere a permanenza). Qual è la strategia primaria?",
            "opzioni": [
                {
                    "testo": "A) Prostatectomia radicale + linfadenectomia pelvica estesa (approccio multimodale)",
                    "d_vit": 0,
                    "d_onc": 10,
                    "d_qol": 20,
                    "next": "snodo4a",
                },
                {
                    "testo": "B) Radioterapia radicale pelvica + LHRH + ARSI (Abiraterone) per 24 mesi",
                    "d_vit": -5,
                    "d_onc": 5,
                    "d_qol": -25,
                    "next": "esito_sconfitta",
                },
                {
                    "testo": "C) TURP disostruttiva + Radioterapia immediata",
                    "d_vit": -10,
                    "d_onc": -15,
                    "d_qol": -20,
                    "next": "esito_sconfitta",
                },
                {
                    "testo": "D) Sola ADT (LHRH) in attesa di riduzione volumetrica",
                    "d_vit": -10,
                    "d_onc": -30,
                    "d_qol": -20,
                    "next": "esito_sconfitta",
                },
            ],
        },
        "snodo4a": {
            "titolo": "📍 Snodo 4 — Ripresa Biochimica Post-Prostatectomia (PSA 0,42 ng/ml)",
            "testo": "Il paziente urina spontaneamente senza catetere. Dopo iniziale azzeramento post-operatorio, a 6 mesi il PSA risale a **0,42 ng/ml** (PSA-DT 4 mesi). Come procedi?",
            "opzioni": [
                {
                    "testo": "A) Eseguire PET-PSMA di ristadiazione prima di impostare il trattamento",
                    "d_vit": 0,
                    "d_onc": 10,
                    "d_qol": 0,
                    "next": "snodo5a",
                },
                {
                    "testo": "B) Radioterapia di salvataggio cieca sulla sola loggia prostatica senza PET",
                    "d_vit": 0,
                    "d_onc": -15,
                    "d_qol": -5,
                    "next": "snodo6",
                },
                {
                    "testo": "C) Avviare direttamente ADT (LHRH) continuativa senza imaging né RT",
                    "d_vit": -5,
                    "d_onc": -20,
                    "d_qol": -10,
                    "next": "snodo6",
                },
                {
                    "testo": "D) Sorveglianza del solo PSA fino a valori > 2,0 ng/ml",
                    "d_vit": -10,
                    "d_onc": -25,
                    "d_qol": 0,
                    "next": "snodo6",
                },
            ],
        },
        "snodo5a": {
            "titolo": "📍 Snodo 5 — PET-PSMA di Ristadiazione: Linfonodo Iliaco Comune",
            "testo": "La PET-PSMA mostra lieve iperaccumulo in loggia prostatica e un **linfonodo iliaco comune destro di 9 mm intensamente captante**. Qual è la scelta terapeutica?",
            "opzioni": [
                {
                    "testo": "A) RT di salvataggio su loggia e pelvi con boost sul linfonodo captante + ADT breve",
                    "d_vit": 0,
                    "d_onc": 15,
                    "d_qol": 0,
                    "next": "snodo6",
                },
                {
                    "testo": "B) Radioterapia sulla sola loggia prostatica ignorando il linfonodo iliaco",
                    "d_vit": -5,
                    "d_onc": -20,
                    "d_qol": -5,
                    "next": "snodo6",
                },
                {
                    "testo": "C) Linfadenectomia di salvataggio isolata senza irradiare la loggia",
                    "d_vit": -10,
                    "d_onc": -15,
                    "d_qol": -15,
                    "next": "snodo6",
                },
                {
                    "testo": "D) Chemioterapia sistemica con Docetaxel",
                    "d_vit": -10,
                    "d_onc": -20,
                    "d_qol": -20,
                    "next": "snodo6",
                },
            ],
        },
        "snodo6": {
            "titolo": "📍 Snodo 6 — Ripartenza Tardiva a 20 Mesi (3 Linfonodi Retroperitoneali)",
            "testo": "Dopo 20 mesi di PSA indosabile, il PSA risale a 1,9 ng/ml. La nuova PET-PSMA evidenzia **3 linfonodi retroperitoneali para-aortici** (mHSPC basso volume, paziente naïve agli ARSI). Come procedi?",
            "opzioni": [
                {
                    "testo": "A) Terapia sistemica con ADT (LHRH) + ARSI (Apalutamide / Enzalutamide / Darolutamide)",
                    "d_vit": 5,
                    "d_onc": 10,
                    "d_qol": 0,
                    "next": "snodo7",
                },
                {
                    "testo": "B) Sola ADT (LHRH) in monoterapia",
                    "d_vit": -10,
                    "d_onc": -20,
                    "d_qol": 0,
                    "next": "snodo7",
                },
                {
                    "testo": "C) Re-irradiazione pelvica e retroperitoneale estesa",
                    "d_vit": -20,
                    "d_onc": -25,
                    "d_qol": -30,
                    "next": "snodo7",
                },
                {
                    "testo": "D) Sospensione terapie attive e sole cure palliative",
                    "d_vit": -40,
                    "d_onc": -45,
                    "d_qol": -25,
                    "next": "esito_sconfitta",
                },
            ],
        },
        "snodo7": {
            "titolo": "📍 Snodo 7 — Il PSA Basso che Inganna (PSA 0,18 ng/ml + Dolenzia Ossea)",
            "testo": "A 10 mesi dall'avvio di ADT + ARSI il paziente è senza catetere. Esami: **PSA 0,18 ng/ml** (stabile). Riferisce però da 3 settimane **dolenzia sorda all'anca destra e al rachide lombare (VAS 3-4/10)**. Ematochimici: Hb 12,1 g/dl, **Fosfatasi Alcalina (ALP) 178 U/L** (basale 72 U/L). Come agisci?",
            "opzioni": [
                {
                    "testo": "A) Ristadiazione strumentale immediata con TC torace-addome + Scintigrafia ossea",
                    "d_vit": 5,
                    "d_onc": 10,
                    "d_qol": 0,
                    "next": "snodo8",
                },
                {
                    "testo": "B) Rassicurare il paziente visto il PSA a 0,18 ng/ml, prescrivere FANS + MOC/DEXA e controllo a 3 mesi",
                    "d_vit": -40,
                    "d_onc": -45,
                    "d_qol": -45,
                    "next": "esito_sconfitta",
                },
                {
                    "testo": "C) Sospendere l'ARSI per sospetta mialgia/artralgia iatrogena da farmaco",
                    "d_vit": -35,
                    "d_onc": -45,
                    "d_qol": -35,
                    "next": "esito_sconfitta",
                },
                {
                    "testo": "D) Radioterapia antalgica cieca sull'anca destra senza ristadiazione sistemica",
                    "d_vit": -20,
                    "d_onc": -30,
                    "d_qol": -20,
                    "next": "esito_sconfitta",
                },
            ],
        },
        "snodo8": {
            "titolo": "📍 Snodo 8 — Il Bivio Finale sulle Lesioni Ossee a PSA Soppresso",
            "testo": "La TC e la Scintigrafia ossea documentano **3 nuove metastasi ossee** (ala iliaca destra, corpo di L3 e VII costa destra) con **PSA confermato a 0,19 ng/ml**. Qual è la tua scelta?",
            "opzioni": [
                {
                    "testo": "A) Studio genetico BRCA1/2 per impostare terapia mirata",
                    "d_vit": 5,
                    "d_onc": 15,
                    "d_qol": 5,
                    "next": "esito_vittoria",
                },
                {
                    "testo": "B) Chemioterapia sistemica con Docetaxel",
                    "d_vit": -10,
                    "d_onc": -15,
                    "d_qol": -15,
                    "next": "esito_parziale",
                },
                {
                    "testo": "C) Terapia con Lutezio-177-PSMA (radioligando)",
                    "d_vit": -15,
                    "d_onc": -25,
                    "d_qol": -10,
                    "next": "esito_sconfitta",
                },
                {
                    "testo": "D) Sola radioterapia mirata (SBRT) sulle lesioni ossee senza cambio sistemico",
                    "d_vit": -25,
                    "d_onc": -30,
                    "d_qol": -20,
                    "next": "esito_sconfitta",
                },
            ],
        },
    },
    "esiti": {
        "esito_vittoria": {
            "tipo": "bianco",
            "titolo": "🏆 TAZZA BIANCA CONQUISTATA!",
            "sottotitolo": '"Failure is not an option."',
            "descrizione": "Hai unito chirurgia primaria (liberando il paziente dal catetere), PET-PSMA di precisione sulla ripresa oligometastatica e test BRCA2 davanti alla progressione ossea a PSA soppresso (coerente con madre k mammella e fratello k prostata). Avviato PARP-inibitore con controllo clinico completo.",
        },
        "esito_parziale": {
            "tipo": "giallo",
            "titolo": "⚠️ RISULTATO INTERMEDIO",
            "sottotitolo": "Opportunità target mancata",
            "descrizione": "Il paziente riceve chemioterapia standard con Docetaxel ma non hai richiesto il test genetico BRCA1/2 davanti alla progressione radiologica PSA-discordante, perdendo la terapia mirata con PARP-inibitore.",
        },
        "esito_sconfitta": {
            "tipo": "rosso",
            "titolo": "❌ TAZZA ROSSA ASSEGNATA!",
            "sottotitolo": '"Shit... happens."',
            "descrizione": "Il paziente è andato incontro a una complicanza maggiore (catetere a permanenza con cistiti attiniche, progressione precoce o crollo vertebrale da progressione BRCA2 non intercettata). Rivedi i bivi decisionali con l'aula.",
        },
    },
}
