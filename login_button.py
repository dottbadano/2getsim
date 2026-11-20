import streamlit.components.v1 as components

def render_login_button(trigger_error: bool = False):
    error_js = "triggerLoginError();" if trigger_error else ""
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      :root {{
        --bg-dark: #181818;
        --brand-red: #8e1b18;
        --brand-red-bright: #b8231f;
        --brand-white: #f4f4f4;
      }}
      body {{
        background: transparent;
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 0;
        height: 190px;
        overflow: hidden;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      }}
      .login-btn {{
        background: transparent;
        border: none;
        padding: 0;
        cursor: pointer;
        outline: none;
        width: 170px;
        height: 170px;
        transition: transform 0.2s cubic-bezier(0.22, 1, 0.36, 1);
      }}
      .login-btn:hover:not(.is-loading) {{ transform: scale(1.03); }}
      .login-btn:active:not(.is-loading) {{ transform: scale(0.97); }}
      .login-btn svg {{ width: 100%; height: 100%; overflow: visible; }}

      .frame-outer {{
        fill: var(--bg-dark);
        stroke: var(--brand-red);
        stroke-width: 2.5;
        transition: stroke 0.4s ease;
      }}
      .login-btn:hover .frame-outer {{ stroke: var(--brand-red-bright); }}
      .frame-inner {{ fill: none; stroke: var(--brand-white); stroke-width: 1.5; }}

      .bar {{
        fill: var(--brand-red);
        transform-origin: 100px 92px;
        transition: transform 0.85s cubic-bezier(0.65, 0, 0.35, 1), fill 0.4s ease;
      }}
      .login-btn:hover .bar {{ fill: var(--brand-red-bright); }}

      .login-btn.is-cross .bar-left {{ transform: translateX(13px) rotate(45deg); }}
      .login-btn.is-cross .bar-right {{ transform: translateX(-13px) rotate(-45deg); }}
      .login-btn.is-equal .bar-left {{ transform: translateX(13px) rotate(90deg); }}
      .login-btn.is-equal .bar-right {{ transform: translateX(-13px) rotate(-90deg); }}

      .symbol-q, .symbol-2 {{
        fill: var(--brand-white);
        font-weight: 800;
        font-size: 74px;
        text-anchor: middle;
        dominant-baseline: central;
        transform-origin: 100px 94px;
        transition: opacity 0.45s ease, transform 0.55s cubic-bezier(0.22, 1, 0.36, 1);
      }}
      .symbol-q {{ opacity: 1; transform: scale(1); }}
      .symbol-2 {{ opacity: 0; transform: scale(0.65); }}

      .login-btn.is-cross .symbol-q,
      .login-btn.is-equal .symbol-q {{ opacity: 0; transform: scale(0.6); }}
      .login-btn.is-equal .symbol-2 {{ opacity: 1; transform: scale(1); }}

      .try-label {{
        fill: var(--brand-white);
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.38em;
        text-anchor: middle;
        opacity: 0.9;
        transition: opacity 0.25s ease, transform 0.25s ease;
      }}
      .login-btn.is-loading .try-label {{ opacity: 0; transform: translateY(4px); }}

      @keyframes shake {{
        0%, 100% {{ transform: translateX(0); }}
        20%, 60% {{ transform: translateX(-7px); }}
        40%, 80% {{ transform: translateX(7px); }}
      }}
      .login-btn.is-error {{ animation: shake 0.4s ease; }}
    </style>
    </head>
    <body>
      <button id="loginBtn" class="login-btn" type="button">
        <svg viewBox="0 0 200 200">
          <rect class="frame-outer" x="10" y="10" width="180" height="180" />
          <rect class="frame-inner" x="18" y="18" width="164" height="164" />
          <rect class="bar bar-left"  x="80"  y="42" width="14" height="100" />
          <rect class="bar bar-right" x="106" y="42" width="14" height="100" />
          <text class="symbol-q" x="100" y="96">?</text>
          <text class="symbol-2" x="100" y="96">2</text>
          <text class="try-label" x="103" y="168">TRY</text>
        </svg>
      </button>

      <script>
        const btn = document.getElementById('loginBtn');

        function clickStreamlitSubmit() {{
          const buttons = window.parent.document.querySelectorAll('button');
          for (const b of buttons) {{
            if (b.innerText.trim() === 'SUBMIT_HIDDEN') {{
              b.click();
              break;
            }}
          }}
        }}

        function triggerLoginSuccess() {{
          if (btn.classList.contains('is-loading')) return;
          btn.classList.add('is-loading', 'is-cross');

          setTimeout(() => {{
            btn.classList.remove('is-cross');
            btn.classList.add('is-equal');
          }}, 850);

          setTimeout(() => {{
            clickStreamlitSubmit();
          }}, 1750);
        }}

        function triggerLoginError() {{
          btn.classList.add('is-loading', 'is-cross');
          setTimeout(() => {{
            btn.classList.add('is-error');
            setTimeout(() => {{
              btn.classList.remove('is-loading', 'is-cross', 'is-error');
            }}, 650);
          }}, 500);
        }}

        btn.addEventListener('click', triggerLoginSuccess);
        {error_js}
      </script>
    </body>
    </html>
    """
    components.html(html_code, height=195)
