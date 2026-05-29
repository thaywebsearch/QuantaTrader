"""
╔══════════════════════════════════════════════════════════════╗
║         QuantaTrader — Interface Web (FastAPI + htmx)        ║
║                                                              ║
║  Arranque:                                                   ║
║    pip install fastapi uvicorn jinja2 python-multipart       ║
║    python web_app.py                                         ║
║    → http://localhost:8000                                   ║
╚══════════════════════════════════════════════════════════════╝
"""

import os, json, asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# ── importa o core do QuantaTrader ───────────────────────────
from quanta_trader import (
    get_alpaca_client, get_anthropic_client, get_db,
    AlertManager, SLTPManager, Watchlist, DEFAULT_WATCHLIST,
    QuantaDB, fmt_money, PAPER_MODE,
    _rsi, _macd, _sma, _ema, _bollinger, _fetch_ohlcv,
    conversation_history, SYSTEM_PROMPT,
)
import alpaca_trade_api as tradeapi
import anthropic

load_dotenv()

# ── estado global da app ──────────────────────────────────────
api:           Optional[tradeapi.REST]        = None
ai_client:     Optional[anthropic.Anthropic]  = None
db:            Optional[QuantaDB]             = None
alert_manager: Optional[AlertManager]         = None
sltp_manager:  Optional[SLTPManager]          = None
watchlist:     Optional[Watchlist]            = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global api, ai_client, db, alert_manager, sltp_manager, watchlist
    api       = get_alpaca_client()
    ai_client = get_anthropic_client()
    db        = get_db()
    if api:
        alert_manager = AlertManager(api, interval=30);  alert_manager.start()
        sltp_manager  = SLTPManager(api, interval=15);   sltp_manager.start()
        watchlist     = Watchlist(api, DEFAULT_WATCHLIST, interval=20); watchlist.start()
    yield
    if alert_manager: alert_manager.stop()
    if sltp_manager:  sltp_manager.stop()
    if watchlist:     watchlist.stop()


app = FastAPI(title="QuantaTrader Web", lifespan=lifespan)

# ── HTML inline (sem Jinja2 para zero dependências de template) ──
HTML_BASE = """<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>⚡ QuantaTrader</title>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<script src="https://unpkg.com/htmx.org@1.9.12/dist/ext/json-enc.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg:       #0a0e17;
  --surface:  #111827;
  --border:   #1e2d45;
  --accent:   #00d4ff;
  --green:    #22c55e;
  --red:      #ef4444;
  --yellow:   #f59e0b;
  --text:     #e2e8f0;
  --muted:    #64748b;
  --font-mono: 'Space Mono', monospace;
  --font-sans: 'DM Sans', sans-serif;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  font-size: 14px;
  min-height: 100vh;
}

/* ── layout ── */
.shell   { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
.sidebar {
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 1.5rem 0;
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
}
.main    { padding: 2rem; overflow-y: auto; }

/* ── sidebar ── */
.logo {
  font-family: var(--font-mono);
  font-size: 1rem;
  color: var(--accent);
  padding: 0 1.2rem 1.5rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1rem;
  letter-spacing: .06em;
}
.logo span { color: var(--muted); font-size: .7rem; display: block; margin-top: .2rem; }
.mode-badge {
  display: inline-block;
  font-size: .65rem;
  padding: .15rem .5rem;
  border-radius: 20px;
  background: var(--border);
  color: var(--yellow);
  font-family: var(--font-mono);
  margin-top: .4rem;
}

nav a {
  display: flex; align-items: center; gap: .6rem;
  padding: .65rem 1.2rem;
  color: var(--muted);
  text-decoration: none;
  font-size: .85rem;
  transition: all .15s;
  cursor: pointer;
  border-left: 2px solid transparent;
}
nav a:hover, nav a.active {
  color: var(--text);
  background: rgba(0,212,255,.06);
  border-left-color: var(--accent);
}
nav .section-label {
  font-size: .65rem;
  letter-spacing: .1em;
  color: var(--muted);
  padding: 1rem 1.2rem .3rem;
  text-transform: uppercase;
}

/* ── cards ── */
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.2rem;
  position: relative;
  overflow: hidden;
}
.card::before {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(135deg, rgba(0,212,255,.03) 0%, transparent 60%);
  pointer-events: none;
}
.card-label { font-size: .72rem; color: var(--muted); letter-spacing: .07em; text-transform: uppercase; margin-bottom: .5rem; }
.card-value { font-family: var(--font-mono); font-size: 1.4rem; font-weight: 700; }
.card-sub   { font-size: .75rem; color: var(--muted); margin-top: .25rem; }
.positive   { color: var(--green); }
.negative   { color: var(--red); }
.neutral    { color: var(--accent); }

/* ── tables ── */
.tbl-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.tbl-header { padding: 1rem 1.2rem; border-bottom: 1px solid var(--border); font-size: .85rem; font-weight: 600; display: flex; align-items: center; justify-content: space-between; }
table { width: 100%; border-collapse: collapse; }
th { font-size: .7rem; color: var(--muted); text-transform: uppercase; letter-spacing: .07em; padding: .6rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }
td { padding: .7rem 1rem; border-bottom: 1px solid rgba(30,45,69,.5); font-size: .85rem; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(255,255,255,.02); }
.mono { font-family: var(--font-mono); }
.badge { display: inline-block; padding: .15rem .5rem; border-radius: 20px; font-size: .7rem; font-family: var(--font-mono); }
.badge-buy  { background: rgba(34,197,94,.15);  color: var(--green); }
.badge-sell { background: rgba(239,68,68,.15);  color: var(--red); }
.badge-ok   { background: rgba(0,212,255,.1);   color: var(--accent); }

/* ── section headers ── */
.page-title { font-size: 1.4rem; font-weight: 600; margin-bottom: 1.5rem; display: flex; align-items: center; gap: .5rem; }
.page-title .sub { font-size: .85rem; color: var(--muted); font-weight: 400; }

/* ── forms ── */
.form-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; }
.field { display: flex; flex-direction: column; gap: .4rem; }
.field label { font-size: .75rem; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.field input, .field select {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: .55rem .8rem;
  border-radius: 7px;
  font-family: var(--font-mono);
  font-size: .85rem;
  outline: none;
  transition: border-color .15s;
}
.field input:focus, .field select:focus { border-color: var(--accent); }

.btn {
  padding: .55rem 1.2rem;
  border-radius: 7px;
  border: none;
  cursor: pointer;
  font-family: var(--font-sans);
  font-size: .85rem;
  font-weight: 600;
  transition: all .15s;
}
.btn-primary { background: var(--accent); color: #000; }
.btn-primary:hover { filter: brightness(1.1); }
.btn-danger  { background: rgba(239,68,68,.15); color: var(--red); border: 1px solid var(--red); }
.btn-ghost   { background: transparent; color: var(--muted); border: 1px solid var(--border); }
.btn-ghost:hover { border-color: var(--accent); color: var(--text); }

/* ── chat ── */
.chat-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; display: flex; flex-direction: column; height: 520px; }
.chat-msgs { flex: 1; overflow-y: auto; padding: 1.2rem; display: flex; flex-direction: column; gap: .8rem; }
.msg { max-width: 78%; padding: .7rem 1rem; border-radius: 10px; font-size: .88rem; line-height: 1.55; }
.msg-user { align-self: flex-end; background: rgba(0,212,255,.12); border: 1px solid rgba(0,212,255,.2); }
.msg-ai   { align-self: flex-start; background: var(--bg); border: 1px solid var(--border); }
.msg-ai .sender { font-size: .7rem; color: var(--accent); font-family: var(--font-mono); margin-bottom: .3rem; }
.chat-input { border-top: 1px solid var(--border); padding: .8rem 1rem; display: flex; gap: .6rem; }
.chat-input input { flex: 1; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: .55rem .8rem; border-radius: 7px; font-size: .88rem; outline: none; }
.chat-input input:focus { border-color: var(--accent); }

/* ── watchlist ticker tape ── */
.ticker-row { display: grid; grid-template-columns: 90px 110px 90px 70px 90px 90px 1fr; align-items: center; padding: .6rem 1rem; border-bottom: 1px solid rgba(30,45,69,.5); gap: .5rem; }
.ticker-row:last-child { border-bottom: none; }
.ticker-row:hover { background: rgba(255,255,255,.02); }
.tick-sym { font-family: var(--font-mono); font-weight: 700; color: var(--accent); }
.tick-price { font-family: var(--font-mono); font-size: .95rem; font-weight: 700; }
.spark { font-family: var(--font-mono); letter-spacing: -.1em; font-size: .85rem; }

/* ── alerts / sltp forms ── */
.form-box { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; }
.form-box h3 { font-size: .9rem; font-weight: 600; margin-bottom: 1rem; color: var(--accent); }

/* ── toast / htmx indicator ── */
.htmx-indicator { display: none; }
.htmx-request .htmx-indicator { display: inline-block; }
.spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── scrollbar ── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 5px; }

/* ── responsive ── */
@media (max-width: 768px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar { height: auto; position: relative; }
}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="logo">
      ⚡ QuantaTrader
      <span>AI Trading Assistant</span>
      <div class="mode-badge">{'📄 PAPER' if PAPER_MODE else '💰 LIVE'}</div>
    </div>
    <nav>
      <div class="section-label">Dashboard</div>
      <a hx-get="/partials/account"   hx-target="#content" hx-push-url="false">💰 Conta & Portfolio</a>
      <a hx-get="/partials/positions" hx-target="#content" hx-push-url="false">📂 Posições Abertas</a>
      <a hx-get="/partials/watchlist" hx-target="#content" hx-push-url="false">📡 Watchlist</a>

      <div class="section-label">Análise</div>
      <a hx-get="/partials/technical" hx-target="#content" hx-push-url="false">📊 Indicadores Técnicos</a>
      <a hx-get="/partials/risk"      hx-target="#content" hx-push-url="false">📐 Análise de Risco</a>

      <div class="section-label">Ordens</div>
      <a hx-get="/partials/orders"    hx-target="#content" hx-push-url="false">📋 Ordens Pendentes</a>
      <a hx-get="/partials/new_order" hx-target="#content" hx-push-url="false">➕ Nova Ordem</a>
      <a hx-get="/partials/history"   hx-target="#content" hx-push-url="false">📜 Histórico</a>

      <div class="section-label">Automação</div>
      <a hx-get="/partials/alerts"    hx-target="#content" hx-push-url="false">🔔 Alertas de Preço</a>
      <a hx-get="/partials/sltp"      hx-target="#content" hx-push-url="false">🛡️ Stop-Loss / TP</a>
      <a hx-get="/partials/database"  hx-target="#content" hx-push-url="false">🗄️ Base de Dados</a>

      <div class="section-label">IA</div>
      <a hx-get="/partials/chat"      hx-target="#content" hx-push-url="false">🤖 Assistente IA</a>
    </nav>
  </aside>
  <main class="main" id="content">
    {CONTENT}
  </main>
</div>
</body>
</html>
"""


def page(content: str) -> str:
    return HTML_BASE.replace("{CONTENT}", content)


def money(v: float, sign: bool = True) -> str:
    s = f"{'+' if v>=0 and sign else ''}${v:,.2f}"
    c = "positive" if v >= 0 else "negative"
    return f'<span class="{c} mono">{s}</span>'


def pct(v: float) -> str:
    s = f"{'+' if v>=0 else ''}{v:.2f}%"
    c = "positive" if v >= 0 else "negative"
    return f'<span class="{c} mono">{s}</span>'


# ══════════════════════════════════════════════════════════════
#  ROTAS
# ══════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(page(_account_html()))


# ── account ───────────────────────────────────────────────────

def _account_html() -> str:
    if not api:
        return "<p style='color:var(--red)'>API Alpaca não configurada.</p>"
    try:
        acct = api.get_account()
        eq   = float(acct.equity)
        cash = float(acct.cash)
        pl   = float(getattr(acct, "unrealized_pl", 0))
        plp  = float(getattr(acct, "unrealized_plpc", 0)) * 100
        bp   = float(acct.buying_power)
    except Exception as e:
        return f"<p style='color:var(--red)'>Erro: {e}</p>"

    return f"""
<div class="page-title">💰 Conta & Portfolio <span class="sub" hx-get="/partials/account" hx-trigger="every 30s" hx-target="closest div" style="cursor:pointer;">↻ auto-refresh 30s</span></div>
<div class="cards">
  <div class="card">
    <div class="card-label">Equity Total</div>
    <div class="card-value neutral">${eq:,.2f}</div>
    <div class="card-sub">valor total da conta</div>
  </div>
  <div class="card">
    <div class="card-label">Cash Disponível</div>
    <div class="card-value">${cash:,.2f}</div>
    <div class="card-sub">liquidez imediata</div>
  </div>
  <div class="card">
    <div class="card-label">P&L Não Realizado</div>
    <div class="card-value {'positive' if pl>=0 else 'negative'}">{'+' if pl>=0 else ''}${pl:,.2f}</div>
    <div class="card-sub">{'+' if plp>=0 else ''}{plp:.2f}% desde entrada</div>
  </div>
  <div class="card">
    <div class="card-label">Buying Power</div>
    <div class="card-value">${bp:,.2f}</div>
    <div class="card-sub">capacidade de compra</div>
  </div>
  <div class="card">
    <div class="card-label">Estado da Conta</div>
    <div class="card-value" style="font-size:1rem">{acct.status.upper()}</div>
    <div class="card-sub">{'📄 Paper Trading' if PAPER_MODE else '💰 Live Trading'}</div>
  </div>
</div>
"""


@app.get("/partials/account", response_class=HTMLResponse)
async def partial_account():
    return HTMLResponse(_account_html())


# ── positions ─────────────────────────────────────────────────

@app.get("/partials/positions", response_class=HTMLResponse)
async def partial_positions():
    if not api:
        return HTMLResponse("<p>API não disponível.</p>")
    try:
        positions = api.list_positions()
    except Exception as e:
        return HTMLResponse(f"<p style='color:var(--red)'>Erro: {e}</p>")

    if not positions:
        return HTMLResponse("<div class='page-title'>📂 Posições Abertas</div><p style='color:var(--muted)'>Sem posições abertas.</p>")

    rows = ""
    for p in positions:
        pl    = float(p.unrealized_pl)
        pl_p  = float(p.unrealized_plpc) * 100
        side  = "buy" if float(p.qty) > 0 else "sell"
        rows += f"""<tr>
          <td class="mono" style="color:var(--accent);font-weight:700">{p.symbol}</td>
          <td class="mono">{p.qty}</td>
          <td class="mono">${float(p.avg_entry_price):,.2f}</td>
          <td class="mono">${float(p.current_price):,.2f}</td>
          <td class="mono">${float(p.market_value):,.2f}</td>
          <td>{money(pl)}</td>
          <td>{pct(pl_p)}</td>
          <td><span class="badge badge-{side}">{side.upper()}</span></td>
        </tr>"""

    return HTMLResponse(f"""
<div class="page-title">📂 Posições Abertas <span class="sub">{len(positions)} posições</span></div>
<div class="tbl-wrap">
  <div class="tbl-header">Posições em carteira <span class="htmx-indicator"><span class="spinner"></span></span></div>
  <table>
    <thead><tr>
      <th>Ticker</th><th>Qtd</th><th>Entrada</th><th>Actual</th>
      <th>Valor</th><th>P&L $</th><th>P&L %</th><th>Lado</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>""")


# ── watchlist ─────────────────────────────────────────────────

@app.get("/partials/watchlist", response_class=HTMLResponse)
async def partial_watchlist():
    if not watchlist:
        return HTMLResponse("<p>Watchlist não iniciada.</p>")

    snaps = watchlist.snaps()
    rows  = ""
    for s in snaps:
        if s.error or s.close == 0:
            rows += f'<div class="ticker-row"><span class="tick-sym">{s.symbol}</span><span style="color:var(--muted)">a carregar…</span></div>'
            continue
        chg  = s.close - s.prev if s.prev else 0
        chgp = chg / s.prev * 100 if s.prev else 0
        c    = "positive" if chgp >= 0 else "negative"
        arr  = "▲" if chgp >= 0 else "▼"
        rows += f"""<div class="ticker-row">
          <span class="tick-sym">{s.symbol}</span>
          <span class="tick-price {c}">${s.close:,.2f}</span>
          <span class="{c} mono">{'+' if chg>=0 else ''}{chg:.2f}</span>
          <span class="{c} mono">{arr} {chgp:+.2f}%</span>
          <span class="mono" style="color:var(--muted)">${s.open:,.2f}</span>
          <span class="mono" style="color:var(--green)">${s.high:,.2f}</span>
          <span class="mono" style="color:var(--muted)">{s.updated}</span>
        </div>"""

    return HTMLResponse(f"""
<div class="page-title">📡 Watchlist <span class="sub" hx-get="/partials/watchlist" hx-trigger="every 20s" hx-target="closest div" style="cursor:pointer;">↻ 20s</span></div>
<div class="tbl-wrap">
  <div class="tbl-header" style="font-size:.75rem;color:var(--muted);display:grid;grid-template-columns:90px 110px 90px 70px 90px 90px 1fr;padding:.5rem 1rem;">
    <span>Ticker</span><span>Preço</span><span>Var $</span><span>Var %</span><span>Abertura</span><span>Máx</span><span>Hora</span>
  </div>
  {rows}
</div>""")


# ── orders ────────────────────────────────────────────────────

@app.get("/partials/orders", response_class=HTMLResponse)
async def partial_orders():
    if not api:
        return HTMLResponse("<p>API não disponível.</p>")
    try:
        orders = api.list_orders(status="open")
    except Exception as e:
        return HTMLResponse(f"<p style='color:var(--red)'>Erro: {e}</p>")

    if not orders:
        return HTMLResponse("<div class='page-title'>📋 Ordens Pendentes</div><p style='color:var(--muted)'>Sem ordens pendentes.</p>")

    rows = ""
    for o in orders:
        price = f"${float(o.limit_price):,.2f}" if o.limit_price else "—"
        rows += f"""<tr>
          <td class="mono" style="font-size:.75rem;color:var(--muted)">{o.id[:8]}…</td>
          <td style="color:var(--accent);font-weight:700">{o.symbol}</td>
          <td><span class="badge badge-{o.side}">{o.side.upper()}</span></td>
          <td class="mono">{o.qty}</td>
          <td class="mono">{o.type}</td>
          <td class="mono">{price}</td>
          <td class="mono" style="color:var(--muted)">{o.status}</td>
          <td>
            <button class="btn btn-danger" style="padding:.25rem .6rem;font-size:.75rem"
              hx-delete="/orders/{o.id}" hx-target="closest tr" hx-swap="outerHTML"
              hx-confirm="Cancelar ordem {o.id[:8]}?">✕</button>
          </td>
        </tr>"""

    return HTMLResponse(f"""
<div class="page-title">📋 Ordens Pendentes <span class="sub">{len(orders)} abertas</span></div>
<div class="tbl-wrap">
  <table>
    <thead><tr><th>ID</th><th>Ticker</th><th>Lado</th><th>Qtd</th><th>Tipo</th><th>Preço</th><th>Estado</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>""")


@app.delete("/orders/{order_id}", response_class=HTMLResponse)
async def cancel_order(order_id: str):
    try:
        api.cancel_order(order_id)
        return HTMLResponse("")  # htmx remove a row
    except Exception as e:
        return HTMLResponse(f"<tr><td colspan='8' style='color:var(--red)'>Erro: {e}</td></tr>")


# ── nova ordem ────────────────────────────────────────────────

@app.get("/partials/new_order", response_class=HTMLResponse)
async def partial_new_order():
    return HTMLResponse("""
<div class="page-title">➕ Nova Ordem</div>
<div class="form-box">
  <h3>Submeter Ordem</h3>
  <form hx-post="/orders" hx-target="#order-result" hx-swap="innerHTML">
    <div class="form-grid" style="margin-bottom:1rem">
      <div class="field">
        <label>Ticker</label>
        <input name="symbol" placeholder="ex: AAPL" required style="text-transform:uppercase">
      </div>
      <div class="field">
        <label>Lado</label>
        <select name="side">
          <option value="buy">BUY</option>
          <option value="sell">SELL</option>
        </select>
      </div>
      <div class="field">
        <label>Quantidade</label>
        <input name="qty" type="number" step="0.001" placeholder="1" required>
      </div>
      <div class="field">
        <label>Tipo</label>
        <select name="order_type">
          <option value="market">Market</option>
          <option value="limit">Limit</option>
          <option value="stop">Stop</option>
        </select>
      </div>
      <div class="field">
        <label>Limit Price ($)</label>
        <input name="limit_price" type="number" step="0.01" placeholder="opcional">
      </div>
      <div class="field">
        <label>Time in Force</label>
        <select name="tif">
          <option value="day">Day</option>
          <option value="gtc">GTC</option>
          <option value="ioc">IOC</option>
        </select>
      </div>
    </div>
    <button class="btn btn-primary" type="submit">Submeter Ordem <span class="htmx-indicator"><span class="spinner"></span></span></button>
  </form>
  <div id="order-result" style="margin-top:1rem"></div>
</div>""")


@app.post("/orders", response_class=HTMLResponse)
async def submit_order(
    symbol: str = Form(...), side: str = Form(...),
    qty: str = Form(...), order_type: str = Form(...),
    limit_price: str = Form(""), tif: str = Form("day"),
):
    try:
        kwargs = dict(symbol=symbol.upper(), qty=qty, side=side,
                      type=order_type, time_in_force=tif)
        if limit_price.strip():
            kwargs["limit_price"] = limit_price
        order = api.submit_order(**kwargs)
        return HTMLResponse(
            f"<div style='color:var(--green);font-family:var(--font-mono)'>"
            f"✅ Ordem submetida — ID: {order.id[:12]}…</div>"
        )
    except Exception as e:
        return HTMLResponse(f"<div style='color:var(--red)'>❌ {e}</div>")


# ── histórico ─────────────────────────────────────────────────

@app.get("/partials/history", response_class=HTMLResponse)
async def partial_history():
    if not api:
        return HTMLResponse("<p>API não disponível.</p>")
    try:
        orders = api.list_orders(status="closed", limit=30, direction="desc")
    except Exception as e:
        return HTMLResponse(f"<p style='color:var(--red)'>Erro: {e}</p>")

    rows = ""
    for o in orders:
        price = f"${float(o.filled_avg_price):,.2f}" if o.filled_avg_price else "—"
        date  = str(o.filled_at or o.submitted_at or "")[:10]
        rows += f"""<tr>
          <td class="mono" style="color:var(--muted)">{date}</td>
          <td style="color:var(--accent);font-weight:700">{o.symbol}</td>
          <td><span class="badge badge-{o.side}">{o.side.upper()}</span></td>
          <td class="mono">{o.qty or '—'}</td>
          <td class="mono">{price}</td>
          <td class="mono" style="color:var(--muted)">{o.status}</td>
        </tr>"""

    return HTMLResponse(f"""
<div class="page-title">📜 Histórico de Trades <span class="sub">últimos 30</span></div>
<div class="tbl-wrap">
  <table>
    <thead><tr><th>Data</th><th>Ticker</th><th>Lado</th><th>Qtd</th><th>Preço</th><th>Estado</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>""")


# ── alertas ───────────────────────────────────────────────────

@app.get("/partials/alerts", response_class=HTMLResponse)
async def partial_alerts():
    alerts = alert_manager.list_alerts() if alert_manager else []

    rows = ""
    for a in alerts:
        icon = "🟢" if a.condition == "above" else "🔴"
        st   = "✅ Disparado" if a.triggered else "⏳ Activo"
        rows += f"""<tr>
          <td class="mono">{a.id}</td>
          <td style="color:var(--accent);font-weight:700">{a.symbol}</td>
          <td>{icon} {'≥' if a.condition=='above' else '≤'} ${a.target:,.2f}</td>
          <td class="mono" style="color:{'var(--muted)' if a.triggered else 'var(--green)'}">{st}</td>
          <td style="color:var(--muted)">{a.note or '—'}</td>
          <td>
            <button class="btn btn-ghost" style="padding:.25rem .6rem;font-size:.75rem"
              hx-delete="/alerts/{a.id}" hx-target="closest tr" hx-swap="outerHTML">✕</button>
          </td>
        </tr>"""

    return HTMLResponse(f"""
<div class="page-title">🔔 Alertas de Preço <span class="sub">{sum(1 for a in alerts if not a.triggered)} activos</span></div>
<div class="form-box">
  <h3>Novo Alerta</h3>
  <form hx-post="/alerts" hx-target="#alert-result" hx-swap="innerHTML" hx-on::after-request="htmx.find('#alert-result').scrollIntoView()">
    <div class="form-grid" style="margin-bottom:1rem">
      <div class="field"><label>Ticker</label><input name="symbol" placeholder="AAPL" required></div>
      <div class="field"><label>Condição</label>
        <select name="condition"><option value="above">Preço ≥ (above)</option><option value="below">Preço ≤ (below)</option></select>
      </div>
      <div class="field"><label>Preço Alvo ($)</label><input name="target" type="number" step="0.01" required></div>
      <div class="field"><label>Nota (opcional)</label><input name="note" placeholder="ex: resistência"></div>
    </div>
    <button class="btn btn-primary" type="submit">Criar Alerta</button>
  </form>
  <div id="alert-result" style="margin-top:.8rem"></div>
</div>
<div class="tbl-wrap">
  <table><thead><tr><th>ID</th><th>Ticker</th><th>Condição</th><th>Estado</th><th>Nota</th><th></th></tr></thead>
    <tbody>{rows if rows else "<tr><td colspan='6' style='color:var(--muted);text-align:center;padding:1.5rem'>Sem alertas</td></tr>"}</tbody>
  </table>
</div>""")


@app.post("/alerts", response_class=HTMLResponse)
async def create_alert(
    symbol: str = Form(...), condition: str = Form(...),
    target: float = Form(...), note: str = Form(""),
):
    if not alert_manager:
        return HTMLResponse("<div style='color:var(--red)'>Alert manager não iniciado.</div>")
    a = alert_manager.add_alert(symbol.upper(), condition, target, note)
    return HTMLResponse(
        f"<div style='color:var(--green)'>✅ Alerta #{a.id} criado — "
        f"{symbol.upper()} {'≥' if condition=='above' else '≤'} ${target:,.2f}</div>"
    )


@app.delete("/alerts/{alert_id}", response_class=HTMLResponse)
async def delete_alert(alert_id: int):
    if alert_manager:
        alert_manager.remove_alert(alert_id)
    return HTMLResponse("")


# ── SL/TP ─────────────────────────────────────────────────────

@app.get("/partials/sltp", response_class=HTMLResponse)
async def partial_sltp():
    guards = sltp_manager.list_guards() if sltp_manager else []

    rows = ""
    for g in guards:
        sl  = f"${g.stop_loss:,.2f}"   if g.stop_loss   else "—"
        tp  = f"${g.take_profit:,.2f}" if g.take_profit else "—"
        st_color = {"active":"var(--accent)","sl_hit":"var(--red)","tp_hit":"var(--green)","cancelled":"var(--muted)"}.get(g.status,"var(--muted)")
        rows += f"""<tr>
          <td class="mono">{g.id}</td>
          <td style="color:var(--accent);font-weight:700">{g.symbol}</td>
          <td class="mono">{g.qty}</td>
          <td class="mono">${g.entry_price:,.2f}</td>
          <td class="mono" style="color:var(--red)">{sl}</td>
          <td class="mono" style="color:var(--green)">{tp}</td>
          <td class="mono" style="color:var(--muted)">{g.mode}</td>
          <td style="color:{st_color}">{g.status}</td>
        </tr>"""

    return HTMLResponse(f"""
<div class="page-title">🛡️ Stop-Loss / Take-Profit <span class="sub">{sum(1 for g in guards if g.status=='active')} activos</span></div>
<div class="form-box">
  <h3>Nova Protecção SL/TP</h3>
  <form hx-post="/sltp" hx-target="#sltp-result" hx-swap="innerHTML">
    <div class="form-grid" style="margin-bottom:1rem">
      <div class="field"><label>Ticker</label><input name="symbol" placeholder="AAPL" required></div>
      <div class="field"><label>Quantidade</label><input name="qty" type="number" step="0.001" placeholder="1" required></div>
      <div class="field"><label>Preço Entrada ($)</label><input name="entry" type="number" step="0.01" required></div>
      <div class="field"><label>Stop-Loss ($)</label><input name="stop_loss" type="number" step="0.01" placeholder="opcional"></div>
      <div class="field"><label>Take-Profit ($)</label><input name="take_profit" type="number" step="0.01" placeholder="opcional"></div>
      <div class="field"><label>Lado de Fecho</label>
        <select name="side"><option value="sell">SELL (long)</option><option value="buy">BUY (short)</option></select>
      </div>
    </div>
    <button class="btn btn-primary" type="submit">Activar Protecção</button>
  </form>
  <div id="sltp-result" style="margin-top:.8rem"></div>
</div>
<div class="tbl-wrap">
  <table><thead><tr><th>ID</th><th>Ticker</th><th>Qtd</th><th>Entrada</th><th>SL</th><th>TP</th><th>Modo</th><th>Estado</th></tr></thead>
    <tbody>{rows if rows else "<tr><td colspan='8' style='color:var(--muted);text-align:center;padding:1.5rem'>Sem protecções</td></tr>"}</tbody>
  </table>
</div>""")


@app.post("/sltp", response_class=HTMLResponse)
async def create_sltp(
    symbol: str = Form(...), qty: str = Form(...),
    entry: float = Form(...), side: str = Form("sell"),
    stop_loss: str = Form(""), take_profit: str = Form(""),
):
    if not sltp_manager:
        return HTMLResponse("<div style='color:var(--red)'>SL/TP manager não iniciado.</div>")
    try:
        sl = float(stop_loss)   if stop_loss.strip()   else None
        tp = float(take_profit) if take_profit.strip() else None
        g  = sltp_manager.add(symbol.upper(), qty, side, entry,
                              stop_loss=sl, take_profit=tp)
        return HTMLResponse(
            f"<div style='color:var(--green)'>✅ Protecção #{g.id} activa — "
            f"{symbol.upper()}  SL: {f'${sl:,.2f}' if sl else '—'}  "
            f"TP: {f'${tp:,.2f}' if tp else '—'}  Modo: {g.mode}</div>"
        )
    except Exception as e:
        return HTMLResponse(f"<div style='color:var(--red)'>❌ {e}</div>")


# ── base de dados ─────────────────────────────────────────────

@app.get("/partials/database", response_class=HTMLResponse)
async def partial_database():
    if not db:
        return HTMLResponse("<p>DB não iniciada.</p>")
    s = db.get_stats()
    pnl_c = "positive" if s["total_pnl"] >= 0 else "negative"
    wr_c  = "positive" if s["win_rate"] >= 50 else "negative"

    top_rows = ""
    for sym in s["top_symbols"]:
        c = "positive" if sym["total_pnl"] >= 0 else "negative"
        top_rows += f"<tr><td style='color:var(--accent);font-weight:700'>{sym['symbol']}</td><td class='mono'>{sym['n']}</td><td class='mono {c}'>{sym['total_pnl']:+,.2f}</td></tr>"

    return HTMLResponse(f"""
<div class="page-title">🗄️ Base de Dados Local <span class="sub">{DB_PATH}</span></div>
<div class="cards" style="margin-bottom:1.5rem">
  <div class="card"><div class="card-label">Total Trades</div><div class="card-value neutral">{s['total_trades']}</div></div>
  <div class="card"><div class="card-label">P&L Total</div><div class="card-value {pnl_c}">{'+' if s['total_pnl']>=0 else ''}${s['total_pnl']:,.2f}</div></div>
  <div class="card"><div class="card-label">Win Rate</div><div class="card-value {wr_c}">{s['win_rate']:.1f}%</div><div class="card-sub">{s['win_count']} ganhos</div></div>
  <div class="card"><div class="card-label">Alertas Disparados</div><div class="card-value">{s['n_alerts']}</div></div>
  <div class="card"><div class="card-label">Snapshots Diários</div><div class="card-value">{s['n_snapshots']}</div></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
  <div class="tbl-wrap">
    <div class="tbl-header">Top Tickers</div>
    <table><thead><tr><th>Ticker</th><th>Trades</th><th>P&L</th></tr></thead>
    <tbody>{top_rows or "<tr><td colspan='3' style='color:var(--muted);text-align:center;padding:1rem'>Sem dados</td></tr>"}</tbody></table>
  </div>
  <div class="form-box">
    <h3>Sincronizar & Snapshot</h3>
    <div style="display:flex;flex-direction:column;gap:.8rem;margin-top:.5rem">
      <button class="btn btn-primary" hx-post="/db/sync" hx-target="#db-msg" hx-swap="innerHTML">↻ Sincronizar Alpaca</button>
      <button class="btn btn-ghost"   hx-post="/db/snapshot" hx-target="#db-msg" hx-swap="innerHTML">📸 Guardar Snapshot Hoje</button>
    </div>
    <div id="db-msg" style="margin-top:.8rem"></div>
  </div>
</div>""")


@app.post("/db/sync", response_class=HTMLResponse)
async def db_sync():
    if not db or not api:
        return HTMLResponse("<div style='color:var(--red)'>Não disponível.</div>")
    n = db.sync_from_alpaca(api, 200)
    return HTMLResponse(f"<div style='color:var(--green)'>✅ {n} ordens sincronizadas.</div>")


@app.post("/db/snapshot", response_class=HTMLResponse)
async def db_snapshot():
    if not db or not api:
        return HTMLResponse("<div style='color:var(--red)'>Não disponível.</div>")
    try:
        acct = api.get_account()
        pos  = api.list_positions()
        snap = json.dumps([{"symbol": p.symbol, "qty": p.qty,
                            "value": float(p.market_value)} for p in pos])
        db.save_snapshot(
            date=datetime.now().strftime("%Y-%m-%d"),
            equity=float(acct.equity), cash=float(acct.cash),
            pl_day=float(getattr(acct, "unrealized_pl", 0)),
            n_pos=len(pos), snapshot_json=snap,
        )
        return HTMLResponse(f"<div style='color:var(--green)'>✅ Snapshot guardado — Equity ${float(acct.equity):,.2f}</div>")
    except Exception as e:
        return HTMLResponse(f"<div style='color:var(--red)'>Erro: {e}</div>")


# ── indicadores técnicos ──────────────────────────────────────

@app.get("/partials/technical", response_class=HTMLResponse)
async def partial_technical():
    return HTMLResponse("""
<div class="page-title">📊 Indicadores Técnicos</div>
<div class="form-box">
  <h3>Analisar Ticker</h3>
  <form hx-post="/technical" hx-target="#tech-result" hx-swap="innerHTML" hx-indicator="#tech-spin">
    <div class="form-grid" style="margin-bottom:1rem">
      <div class="field"><label>Ticker</label><input name="symbol" placeholder="AAPL" required></div>
      <div class="field"><label>Timeframe</label>
        <select name="timeframe"><option value="1d">Diário (1d)</option><option value="1h">Horário (1h)</option><option value="1m">Minuto (1m)</option></select>
      </div>
      <div class="field"><label>Barras</label><input name="limit" type="number" value="300"></div>
    </div>
    <button class="btn btn-primary" type="submit">Analisar <span id="tech-spin" class="htmx-indicator"><span class="spinner"></span></span></button>
  </form>
</div>
<div id="tech-result"></div>""")


@app.post("/technical", response_class=HTMLResponse)
async def run_technical(
    symbol: str = Form(...), timeframe: str = Form("1d"), limit: int = Form(300)
):
    tf_map = {"1m": tradeapi.TimeFrame.Minute, "1h": tradeapi.TimeFrame.Hour, "1d": tradeapi.TimeFrame.Day}
    tf = tf_map.get(timeframe, tradeapi.TimeFrame.Day)
    try:
        import pandas as pd
        df = _fetch_ohlcv(api, symbol.upper(), tf, limit)
        if df is None or df.empty:
            return HTMLResponse(f"<div style='color:var(--red)'>Sem dados para {symbol}.</div>")
        close   = df["close"]
        current = float(close.iloc[-1])
        rows    = ""
        signals = []

        for p in [9, 20, 50, 200]:
            if len(close) < p:
                continue
            sma_v = float(_sma(close, p).iloc[-1])
            ema_v = float(_ema(close, p).iloc[-1])
            diff  = (current - sma_v) / sma_v * 100
            c     = "positive" if diff >= 0 else "negative"
            rows += f"<tr><td class='mono'>{p}</td><td class='mono'>${sma_v:,.2f}</td><td class='mono'>${ema_v:,.2f}</td><td class='mono {c}'>{diff:+.2f}%</td></tr>"

        rsi_val = float(_rsi(close, 14).iloc[-1]) if len(close) >= 14 else None
        ml, sl_line, _ = _macd(close) if len(close) >= 35 else (None, None, None)
        u, m, l = _bollinger(close) if len(close) >= 20 else (None, None, None)

        rsi_html = ""
        if rsi_val is not None:
            rc = "positive" if rsi_val <= 30 else "negative" if rsi_val >= 70 else "neutral"
            lb = "Sobrevendido ✅" if rsi_val <= 30 else "Sobrecomprado ⚠️" if rsi_val >= 70 else "Neutro"
            rsi_html = f"<div class='card'><div class='card-label'>RSI (14)</div><div class='card-value {rc}'>{rsi_val:.1f}</div><div class='card-sub'>{lb}</div></div>"
            signals.append(("RSI(14)", "COMPRAR" if rsi_val<=30 else "VENDER" if rsi_val>=70 else "NEUTRO"))

        macd_html = ""
        if ml is not None:
            mv, sv = float(ml.iloc[-1]), float(sl_line.iloc[-1])
            mc = "positive" if mv > sv else "negative"
            macd_html = f"<div class='card'><div class='card-label'>MACD</div><div class='card-value {mc}'>{mv:+.4f}</div><div class='card-sub'>Signal: {sv:+.4f}</div></div>"
            signals.append(("MACD", "COMPRAR" if mv > sv else "VENDER"))

        bb_html = ""
        if u is not None:
            uv, mv2, lv = float(u.iloc[-1]), float(m.iloc[-1]), float(l.iloc[-1])
            bb_html = f"<div class='card'><div class='card-label'>Bollinger Bands</div><div class='card-value neutral'>${mv2:,.2f}</div><div class='card-sub'>↑${uv:,.2f}  ↓${lv:,.2f}</div></div>"
            if current >= uv: signals.append(("Bollinger", "VENDER"))
            elif current <= lv: signals.append(("Bollinger", "COMPRAR"))
            else: signals.append(("Bollinger", "NEUTRO"))

        sma50 = float(_sma(close, 50).iloc[-1]) if len(close) >= 50 else None
        if sma50: signals.append(("SMA50", "COMPRAR" if current > sma50 else "VENDER"))

        buys  = sum(1 for _, s in signals if s == "COMPRAR")
        sells = sum(1 for _, s in signals if s == "VENDER")
        total = len(signals)
        overall_c = "positive" if buys > sells else "negative" if sells > buys else "neutral"
        overall_l = "▲ COMPRADORA" if buys > sells else "▼ VENDEDORA" if sells > buys else "─ MISTA"

        sig_rows = "".join(
            f"<tr><td>{n}</td><td class='{'positive' if s=='COMPRAR' else 'negative' if s=='VENDER' else 'neutral'} mono'>"
            f"{'▲ COMPRAR' if s=='COMPRAR' else '▼ VENDER' if s=='VENDER' else '─ NEUTRO'}</td></tr>"
            for n, s in signals
        )

        return HTMLResponse(f"""
<div class="cards" style="margin-bottom:1.5rem">
  <div class="card"><div class="card-label">Preço Actual</div><div class="card-value neutral">${current:,.2f}</div><div class="card-sub">{symbol.upper()} · {timeframe} · {len(close)} barras</div></div>
  {rsi_html}{macd_html}{bb_html}
  <div class="card"><div class="card-label">Sinal Global</div><div class="card-value {overall_c}">{overall_l}</div><div class="card-sub">{buys} comprar · {sells} vender · {total-buys-sells} neutro</div></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
  <div class="tbl-wrap">
    <div class="tbl-header">Médias Móveis</div>
    <table><thead><tr><th>Período</th><th>SMA</th><th>EMA</th><th>Preço vs SMA</th></tr></thead>
    <tbody>{rows}</tbody></table>
  </div>
  <div class="tbl-wrap">
    <div class="tbl-header">Resumo de Sinais</div>
    <table><thead><tr><th>Indicador</th><th>Sinal</th></tr></thead>
    <tbody>{sig_rows}</tbody></table>
  </div>
</div>""")
    except Exception as e:
        return HTMLResponse(f"<div style='color:var(--red)'>Erro: {e}</div>")


# ── análise de risco ──────────────────────────────────────────

@app.get("/partials/risk", response_class=HTMLResponse)
async def partial_risk():
    return HTMLResponse("""
<div class="page-title">📐 Análise de Risco & Position Sizing</div>
<div class="form-box">
  <h3>Calculadora de Position Sizing — Risco Fixo</h3>
  <form hx-post="/risk/size" hx-target="#risk-result" hx-swap="innerHTML">
    <div class="form-grid" style="margin-bottom:1rem">
      <div class="field"><label>Capital ($)</label><input name="capital" type="number" step="0.01" placeholder="10000" required></div>
      <div class="field"><label>% Capital a Arriscar</label><input name="risk_pct" type="number" step="0.1" value="1.0" required></div>
      <div class="field"><label>Preço de Entrada ($)</label><input name="entry" type="number" step="0.01" required></div>
      <div class="field"><label>Preço de Stop-Loss ($)</label><input name="stop" type="number" step="0.01" required></div>
      <div class="field"><label>Take-Profit ($, opcional)</label><input name="tp" type="number" step="0.01" placeholder="opcional"></div>
    </div>
    <button class="btn btn-primary" type="submit">Calcular</button>
  </form>
  <div id="risk-result" style="margin-top:1rem"></div>
</div>""")


@app.post("/risk/size", response_class=HTMLResponse)
async def calc_risk(
    capital: float = Form(...), risk_pct: float = Form(...),
    entry: float = Form(...), stop: float = Form(...),
    tp: str = Form(""),
):
    risk_amt  = capital * risk_pct / 100
    risk_per  = abs(entry - stop)
    shares    = risk_amt / risk_per if risk_per > 0 else 0
    pos_val   = shares * entry
    pos_pct   = pos_val / capital * 100
    tp_val    = float(tp) if tp.strip() else None
    rr        = abs(tp_val - entry) / risk_per if tp_val and risk_per > 0 else None
    rr_c      = "positive" if rr and rr >= 2 else "negative" if rr and rr < 1 else "neutral"
    pos_c     = "positive" if pos_pct <= 20 else "negative" if pos_pct > 40 else "neutral"
    rsk_c     = "positive" if risk_pct <= 2 else "negative" if risk_pct > 5 else "neutral"

    return HTMLResponse(f"""
<div class="cards">
  <div class="card"><div class="card-label">Quantidade</div><div class="card-value neutral">{shares:.4f}</div><div class="card-sub">shares / unidades</div></div>
  <div class="card"><div class="card-label">Valor Posição</div><div class="card-value {pos_c}">${pos_val:,.2f}</div><div class="card-sub">{pos_pct:.1f}% do capital</div></div>
  <div class="card"><div class="card-label">Risco $</div><div class="card-value {rsk_c}">${risk_amt:,.2f}</div><div class="card-sub">{risk_pct}% do capital</div></div>
  {f'<div class="card"><div class="card-label">Risk/Reward</div><div class="card-value {rr_c}">{rr:.2f}R</div><div class="card-sub">{"✅ bom" if rr and rr>=2 else "⚠️ fraco"}</div></div>' if rr else ""}
</div>""")


# ── chat IA ───────────────────────────────────────────────────

@app.get("/partials/chat", response_class=HTMLResponse)
async def partial_chat():
    msgs_html = ""
    for m in conversation_history[-20:]:
        role = m["role"]
        cls  = "msg-user" if role == "user" else "msg-ai"
        sender = '<div class="sender">⚡ QuantaTrader AI</div>' if role == "assistant" else ""
        msgs_html += f'<div class="msg {cls}">{sender}{m["content"]}</div>'

    return HTMLResponse(f"""
<div class="page-title">🤖 Assistente IA <span class="sub">Claude · QuantaTrader AI</span></div>
<div class="chat-wrap">
  <div class="chat-msgs" id="chat-msgs">{msgs_html or '<div style="color:var(--muted);text-align:center;margin:auto">Faz uma pergunta sobre os teus trades ou o mercado…</div>'}</div>
  <div class="chat-input">
    <input id="chat-in" placeholder="Pergunta algo ao assistente IA…"
      hx-post="/chat" hx-target="#chat-msgs" hx-swap="beforeend"
      hx-trigger="keydown[keyCode==13]"
      hx-include="#chat-in"
      hx-on::after-request="this.value='';document.getElementById('chat-msgs').scrollTop=99999"
      name="message">
    <button class="btn btn-primary"
      hx-post="/chat" hx-target="#chat-msgs" hx-swap="beforeend"
      hx-include="#chat-in"
      hx-on::after-request="document.getElementById('chat-in').value='';document.getElementById('chat-msgs').scrollTop=99999">
      Enviar
    </button>
  </div>
</div>""")


@app.post("/chat", response_class=HTMLResponse)
async def chat(message: str = Form(...)):
    if not message.strip():
        return HTMLResponse("")
    if not ai_client:
        return HTMLResponse("<div class='msg msg-ai'><div class='sender'>⚡ QuantaTrader AI</div>Assistente IA não disponível. Configura ANTHROPIC_API_KEY no .env.</div>")

    conversation_history.append({"role": "user", "content": message})

    # contexto do portfolio
    ctx = ""
    if api:
        try:
            acct = api.get_account()
            pos  = api.list_positions()
            pos_str = ", ".join(f"{p.symbol}({p.qty})" for p in pos) or "nenhuma"
            ctx = f"\n\nPortfolio actual: Equity ${float(acct.equity):,.2f} · Posições: {pos_str} · {'Paper' if PAPER_MODE else 'Live'}"
        except Exception:
            pass

    try:
        resp = ai_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT + ctx,
            messages=conversation_history,
        )
        reply = resp.content[0].text
        conversation_history.append({"role": "assistant", "content": reply})
        return HTMLResponse(
            f'<div class="msg msg-user">{message}</div>'
            f'<div class="msg msg-ai"><div class="sender">⚡ QuantaTrader AI</div>{reply}</div>'
        )
    except Exception as e:
        return HTMLResponse(f'<div class="msg msg-ai"><div class="sender">⚡ QuantaTrader AI</div><span style="color:var(--red)">Erro: {e}</span></div>')


# ── API JSON (para integrações externas) ─────────────────────

@app.get("/api/account")
async def api_account():
    if not api: raise HTTPException(503)
    try:
        a = api.get_account()
        return {"equity": float(a.equity), "cash": float(a.cash),
                "buying_power": float(a.buying_power), "status": a.status}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/positions")
async def api_positions():
    if not api: raise HTTPException(503)
    return [{"symbol": p.symbol, "qty": p.qty,
             "market_value": float(p.market_value),
             "unrealized_pl": float(p.unrealized_pl)} for p in api.list_positions()]

@app.get("/api/watchlist")
async def api_watchlist():
    if not watchlist: raise HTTPException(503)
    return [{"symbol": s.symbol, "price": s.close, "updated": s.updated}
            for s in watchlist.snaps()]


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    host = os.getenv("QT_HOST", "0.0.0.0")
    port = int(os.getenv("QT_PORT", "8000"))
    print(f"\n  ⚡ QuantaTrader Web  →  http://localhost:{port}\n")
    uvicorn.run("web_app:app", host=host, port=port,
                reload="--reload" in sys.argv, log_level="warning")
