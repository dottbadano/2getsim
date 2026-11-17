APP_TITLE = "2getSIM — Uro-Oncologia Clinica"
APP_SUBTITLE = "Corso Residenziale Uro-Oncologico Multidisciplinare"


def render_header_caso(caso, case_id, etichetta_utente):
    return f"""
    <div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 1.4rem; border-radius: 12px; color: white; margin-bottom: 1.5rem;">
        <span style="background: #3b82f6; padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: bold;">{caso.get('badge', f'CASO {case_id}')}</span>
        <span style="background: #334155; padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; margin-left: 8px;">Postazione: {etichetta_utente}</span>
        <h2 style="margin: 0.5rem 0 0.2rem 0; font-size: 1.45rem;">{caso['titolo']}</h2>
        <p style="margin: 0; color: #94a3b8; font-size: 0.95rem;">{caso.get('sottotitolo', '')}</p>
    </div>
    """


def render_box_esito(esito):
    colori = {
        "bianco": ("#dcfce7", "#22c55e", "#16a34a", "#166534"),
        "giallo": ("#fef9c3", "#eab308", "#ca8a04", "#854d0e"),
        "rosso": ("#fee2e2", "#ef4444", "#dc2626", "#991b1b"),
    }
    bg, border, title_col, text_col = colori.get(
        esito.get("tipo", "rosso"), colori["rosso"]
    )
    return f"""
    <div style="background: {bg}; border: 2px solid {border}; padding: 2rem; border-radius: 12px; text-align: center;">
        <h1 style="color: {title_col}; margin-top: 0;">{esito['titolo']}</h1>
        <h3 style="color: {title_col};"><i>{esito.get('sottotitolo', '')}</i></h3>
        <p style="color: {text_col}; font-size: 1.05rem;">{esito['descrizione']}</p>
    </div>
    """
