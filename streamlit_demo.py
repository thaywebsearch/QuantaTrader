"""
╔══════════════════════════════════════════════════════════════╗
║       QuantaTrader — Demo Interactivo (Streamlit)            ║
║       Sem chaves de API · Dados simulados realistas          ║
║                                                              ║
║  Arranque:                                                   ║
║    pip install streamlit pandas numpy plotly                 ║
║    streamlit run streamlit_demo.py                           ║
╚══════════════════════════════════════════════════════════════╝
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import random
import json

# ══════════════════════════════════════════════════════════════
#  CONFIGURAÇÃO DA PÁGINA
# ══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="⚡ QuantaTrader Demo",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS personalizado ─────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

/* fundo escuro */
.stApp { background: #0a0e17; }

/* sidebar */
section[data-testid="stSidebar"] {
    background: #111827;
    border-right: 1px solid #1e2d45;
}
section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }

/* métricas */
div[data-testid="metric-container"] {
    background: #111827;
    border: 1px solid #1e2d45;
    border-radius: 10px;
    padding: 1rem 1.2rem;
}
div[data-testid="metric-container"] label { color: #64748b !important; font-size: .75rem !important; text-transform: uppercase; letter-spacing: .07em; }
div[data-testid="metric-container"] div[data-testid="stMetricValue"] { font-family: 'Space Mono', monospace; font-size: 1.3rem !important; color: #00d4ff !important; }

/* títulos */
h1, h2, h3 { font-family: 'Space Mono', monospace !important; color: #00d4ff !important; }
h1 { font-size: 1.4rem !important; letter-spacing: .04em; }
h2 { font-size: 1.1rem !important; color: #94a3b8 !important; }
h3 { font-size: .95rem !important; }

/* tabelas */
.stDataFrame { background: #111827; border-radius: 10px; }
thead th { background: #1e2d45 !important; color: #94a3b8 !important; font-size: .75rem !important; }

/* botões */
.stButton > button {
    background: #00d4ff;
    color: #000;
    font-weight: 700;
    border: none;
    border-radius: 7px;
    padding: .5rem 1.2rem;
    font-family: 'DM Sans', sans-serif;
}
.stButton > button:hover { filter: brightness(1.1); }

/* selectbox / input */
.stSelectbox > div > div, .stNumberInput > div > div > input, .stTextInput > div > div > input {
    background: #0a0e17 !important;
    border: 1px solid #1e2d45 !important;
    color: #e2e8f0 !important;
    border-radius: 7px !important;
    font-family: 'Space Mono', monospace !important;
}

/* banner demo */
.demo-banner {
    background: linear-gradient(90deg, rgba(245,158,11,.15), rgba(245,158,11,.05));
    border: 1px solid rgba(245,158,11,.3);
    border-radius: 8px;
    padding: .6rem 1rem;
    color: #f59e0b;
    font-size: .82rem;
    margin-bottom: 1.2rem;
    font-family: 'Space Mono', monospace;
}

/* positivo / negativo */
.pos { color: #22c55e; font-family: 'Space Mono', monospace; }
.neg { color: #ef4444; font-family: 'Space Mono', monospace; }
.neu { color: #00d4ff; font-family: 'Space Mono', monospace; }

/* card de sinal */
.signal-card {
    background: #111827;
    border: 1px solid #1e2d45;
    border-radius: 10px;
    padding: .8rem 1rem;
    text-align: center;
    margin-bottom: .5rem;
}
.signal-buy  { border-color: #22c55e; }
.signal-sell { border-color: #ef4444; }
.signal-neu  { border-color: #64748b; }

/* divider */
hr { border-color: #1e2d45; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  DADOS SIMULADOS
# ══════════════════════════════════════════════════════════════

TICKERS = {
    "AAPL":  {"name": "Apple Inc.",           "price": 213.45, "sector": "Technology"},
    "MSFT":  {"name": "Microsoft Corp.",       "price": 415.20, "sector": "Technology"},
    "NVDA":  {"name": "NVIDIA Corp.",          "price": 924.10, "sector": "Technology"},
    "TSLA":  {"name": "Tesla Inc.",            "price": 178.32, "sector": "Consumer"},
    "AMZN":  {"name": "Amazon.com Inc.",       "price": 187.54, "sector": "Consumer"},
    "META":  {"name": "Meta Platforms",        "price": 512.33, "sector": "Technology"},
    "GOOGL": {"name": "Alphabet Inc.",         "price": 171.89, "sector": "Technology"},
    "JPM":   {"name": "JPMorgan Chase",        "price": 198.76, "sector": "Finance"},
    "SPY":   {"name": "S&P 500 ETF",           "price": 524.10, "sector": "ETF"},
    "QQQ":   {"name": "Nasdaq 100 ETF",        "price": 445.67, "sector": "ETF"},
}


@st.cache_data(ttl=60)
def gen_price_series(symbol: str, n: int = 500, tf: str = "1d") -> pd.DataFrame:
    """Gera série OHLCV simulada realista com GBM."""
    rng    = np.random.default_rng(abs(hash(symbol)) % (2**32))
    base   = TICKERS.get(symbol, {}).get("price", 100.0)
    mu     = 0.0003
    sigma  = 0.018 if tf == "1d" else 0.004

    rets   = rng.normal(mu, sigma, n)
    prices = base * np.cumprod(1 + rets)

    # OHLCV realista
    opens  = np.roll(prices, 1); opens[0] = prices[0]
    highs  = np.maximum(prices, opens) * (1 + rng.uniform(0, .008, n))
    lows   = np.minimum(prices, opens) * (1 - rng.uniform(0, .008, n))
    vols   = rng.integers(500_000, 8_000_000, n).astype(float)

    freq   = {"1d": "B", "1h": "h", "1m": "min"}.get(tf, "B")
    idx    = pd.date_range(end=datetime.now(), periods=n, freq=freq)

    return pd.DataFrame({"open": opens, "high": highs,
                         "low": lows,   "close": prices,
                         "volume": vols}, index=idx)


def gen_account() -> dict:
    return {
        "equity":       127_430.55,
        "cash":          32_150.20,
        "unrealized_pl":  4_230.18,
        "unrealized_plpc": 0.0342,
        "buying_power":  64_300.40,
        "status":        "ACTIVE",
        "day_pl":         312.44,
    }


def gen_positions() -> list[dict]:
    return [
        {"symbol":"AAPL","qty":150,"avg_entry":195.20,"current":213.45,"market_value":32_017.50,"pl":2_737.50,"pl_pct":0.0937},
        {"symbol":"NVDA","qty":30, "avg_entry":880.00,"current":924.10,"market_value":27_723.00,"pl":1_323.00,"pl_pct":0.0501},
        {"symbol":"MSFT","qty":80, "avg_entry":408.50,"current":415.20,"market_value":33_216.00,"pl":  536.00,"pl_pct":0.0164},
        {"symbol":"TSLA","qty":60, "avg_entry":192.00,"current":178.32,"market_value":10_699.20,"pl":-820.80,"pl_pct":-0.0713},
        {"symbol":"SPY", "qty":45, "avg_entry":518.00,"current":524.10,"market_value":23_584.50,"pl":  274.50,"pl_pct":0.0118},
    ]


def gen_orders() -> list[dict]:
    return [
        {"id":"a1b2c3d4","symbol":"AMZN","side":"buy", "type":"limit","qty":20,"limit_price":183.00,"status":"pending","submitted":"2026-05-30 09:31"},
        {"id":"e5f6g7h8","symbol":"META","side":"sell","type":"stop", "qty":10,"limit_price":505.00,"status":"pending","submitted":"2026-05-30 10:15"},
        {"id":"i9j0k1l2","symbol":"JPM", "side":"buy", "type":"limit","qty":50,"limit_price":195.50,"status":"pending","submitted":"2026-05-30 11:02"},
    ]


def gen_history() -> list[dict]:
    trades = []
    syms   = list(TICKERS.keys())
    rng    = random.Random(42)
    for i in range(30):
        sym  = rng.choice(syms)
        base = TICKERS[sym]["price"]
        side = rng.choice(["buy","sell"])
        qty  = rng.randint(5, 100)
        fp   = base * rng.uniform(.94, 1.06)
        dt   = (datetime.now() - timedelta(days=rng.randint(0,90))).strftime("%Y-%m-%d")
        pnl  = rng.uniform(-500, 800)
        trades.append({"date":dt,"symbol":sym,"side":side,"qty":qty,
                       "filled_price":fp,"pnl":pnl,"status":"filled"})
    return sorted(trades, key=lambda x: x["date"], reverse=True)


def gen_equity_curve(days: int = 90) -> pd.DataFrame:
    rng    = np.random.default_rng(7)
    eq     = [100_000.0]
    for _ in range(days - 1):
        eq.append(eq[-1] * (1 + rng.normal(0.0005, 0.008)))
    dates = pd.date_range(end=datetime.now(), periods=days, freq="B")
    return pd.DataFrame({"date": dates, "equity": eq})


# ══════════════════════════════════════════════════════════════
#  INDICADORES TÉCNICOS (pandas puro)
# ══════════════════════════════════════════════════════════════

def sma(s, p):  return s.rolling(p).mean()
def ema(s, p):  return s.ewm(span=p, adjust=False).mean()

def rsi(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(p).mean()
    l = (-d.clip(upper=0)).rolling(p).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))

def macd(s, f=12, sl=26, sig=9):
    ml = ema(s,f) - ema(s,sl)
    si = ema(ml, sig)
    return ml, si, ml - si

def bollinger(s, p=20, k=2.0):
    m = sma(s, p)
    std = s.rolling(p).std()
    return m + k*std, m, m - k*std

def atr(df, p=14):
    h,l,c = df["high"], df["low"], df["close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(p).mean()


# ══════════════════════════════════════════════════════════════
#  GRÁFICOS PLOTLY
# ══════════════════════════════════════════════════════════════

CHART_LAYOUT = dict(
    paper_bgcolor="#0a0e17",
    plot_bgcolor="#111827",
    font=dict(family="Space Mono, monospace", color="#94a3b8", size=11),
    xaxis=dict(gridcolor="#1e2d45", showgrid=True, zeroline=False),
    yaxis=dict(gridcolor="#1e2d45", showgrid=True, zeroline=False),
    margin=dict(l=10, r=10, t=35, b=10),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#1e2d45"),
)


def candlestick_chart(df: pd.DataFrame, symbol: str,
                      show_sma: bool = True, show_bb: bool = False) -> go.Figure:
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[.55, .25, .20],
                        vertical_spacing=.02)

    # candlestick
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"],  close=df["close"],
        increasing_line_color="#22c55e",
        decreasing_line_color="#ef4444",
        name=symbol, showlegend=False,
    ), row=1, col=1)

    c = df["close"]
    if show_sma:
        for p, col in [(20,"#00d4ff"),(50,"#f59e0b"),(200,"#a855f7")]:
            if len(c) >= p:
                fig.add_trace(go.Scatter(x=df.index, y=sma(c,p),
                    name=f"SMA{p}", line=dict(color=col, width=1.2),
                    opacity=.8), row=1, col=1)

    if show_bb:
        u,m,l = bollinger(c)
        fig.add_trace(go.Scatter(x=df.index, y=u, name="BB Upper",
            line=dict(color="#64748b", dash="dot", width=1), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=l, name="BB Lower",
            line=dict(color="#64748b", dash="dot", width=1),
            fill="tonexty", fillcolor="rgba(100,116,139,.07)", showlegend=False), row=1, col=1)

    # volume
    colors = ["#22c55e" if c >= o else "#ef4444"
              for c, o in zip(df["close"], df["open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume",
        marker_color=colors, opacity=.6, showlegend=False), row=2, col=1)

    # RSI
    rsi_s = rsi(c)
    fig.add_trace(go.Scatter(x=df.index, y=rsi_s, name="RSI",
        line=dict(color="#00d4ff", width=1.5), showlegend=False), row=3, col=1)
    fig.add_hline(y=70, line_color="#ef4444", line_dash="dot", opacity=.5, row=3, col=1)
    fig.add_hline(y=30, line_color="#22c55e", line_dash="dot", opacity=.5, row=3, col=1)

    fig.update_layout(
        **CHART_LAYOUT,
        height=560,
        xaxis_rangeslider_visible=False,
        title=dict(text=f"⚡ {symbol}", font=dict(color="#00d4ff", size=13)),
    )
    fig.update_yaxes(title_text="RSI", row=3, col=1, range=[0,100])
    return fig


def equity_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["equity"],
        fill="tozeroy",
        fillcolor="rgba(0,212,255,.08)",
        line=dict(color="#00d4ff", width=2),
        name="Equity",
    ))
    fig.update_layout(**CHART_LAYOUT, height=280,
                      title=dict(text="Evolução de Equity", font=dict(color="#00d4ff", size=12)))
    return fig


def portfolio_pie(positions: list) -> go.Figure:
    labels = [p["symbol"] for p in positions]
    values = [p["market_value"] for p in positions]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=.55,
        marker=dict(colors=["#00d4ff","#22c55e","#f59e0b","#a855f7","#ef4444"]),
        textfont=dict(family="Space Mono", color="#e2e8f0"),
    ))
    fig.update_layout(**CHART_LAYOUT, height=280,
                      title=dict(text="Alocação", font=dict(color="#00d4ff", size=12)),
                      showlegend=True)
    return fig


# ══════════════════════════════════════════════════════════════
#  BACKTESTING (pandas puro)
# ══════════════════════════════════════════════════════════════

def run_backtest_demo(df, signals, capital=10_000):
    close = df["close"].values
    pos   = 0; cash = capital; equity = []
    trades = []
    ep = ei = 0

    for i, price in enumerate(close):
        if signals[i] == 1 and pos == 0:
            pos = cash / price; ep = price; ei = i; cash = 0
        elif signals[i] == -1 and pos > 0:
            pnl = pos * (price - ep)
            trades.append({"entry": ep, "exit": price,
                           "pnl": pnl, "pnl_pct": (price-ep)/ep*100,
                           "bars": i - ei})
            cash = pos * price; pos = 0
        equity.append(cash + pos * price)

    if pos > 0:
        price = close[-1]
        trades.append({"entry": ep, "exit": price,
                       "pnl": pos*(price-ep),
                       "pnl_pct": (price-ep)/ep*100,
                       "bars": len(close)-1-ei})
        cash = pos * price; pos = 0

    eq  = np.array(equity)
    ret = (eq[-1] - capital) / capital * 100
    bh  = (close[-1] - close[0]) / close[0] * 100
    rets = np.diff(eq) / eq[:-1]
    sh   = np.mean(rets) / np.std(rets) * np.sqrt(252) if np.std(rets) > 0 else 0
    peak = np.maximum.accumulate(eq)
    dd   = float(np.min((eq - peak) / peak * 100))
    wins = [t for t in trades if t["pnl"] > 0]
    wr   = len(wins) / len(trades) * 100 if trades else 0
    gp   = sum(t["pnl"] for t in wins)
    gl   = abs(sum(t["pnl"] for t in trades if t["pnl"] <= 0))
    pf   = gp / gl if gl > 0 else float("inf")

    return {"return": ret, "bh": bh, "sharpe": sh, "max_dd": dd,
            "win_rate": wr, "profit_factor": pf,
            "n_trades": len(trades), "final": eq[-1],
            "equity_curve": eq, "trades": trades}


# ══════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="font-family:'Space Mono',monospace;color:#00d4ff;font-size:1.1rem;
                padding-bottom:1rem;border-bottom:1px solid #1e2d45;margin-bottom:1rem">
      ⚡ QuantaTrader
      <div style="font-size:.7rem;color:#64748b;margin-top:.2rem">AI Trading Assistant</div>
      <div style="font-size:.65rem;background:#1e2d45;color:#f59e0b;
                  display:inline-block;padding:.15rem .5rem;border-radius:20px;margin-top:.4rem">
        📄 DEMO MODE
      </div>
    </div>
    """, unsafe_allow_html=True)

    page = st.selectbox("", [
        "💰  Dashboard",
        "📡  Watchlist",
        "📊  Indicadores Técnicos",
        "🧪  Backtesting",
        "📐  Análise de Risco",
        "📋  Ordens & Histórico",
        "🔔  Alertas & SL/TP",
        "📈  Performance",
    ], label_visibility="collapsed")

    st.markdown("---")
    st.markdown("""
    <div style="font-size:.72rem;color:#64748b;line-height:1.6">
      <b style="color:#94a3b8">Sobre o Demo</b><br>
      Dados 100% simulados.<br>
      Nenhuma chave de API necessária.<br><br>
      <b style="color:#94a3b8">Versão completa</b><br>
      Requer chaves Alpaca + Anthropic.<br>
      Ver <code style="color:#00d4ff">quanta_trader.py</code>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  BANNER DEMO
# ══════════════════════════════════════════════════════════════

st.markdown("""
<div class="demo-banner">
  📄 MODO DEMO — Dados simulados · Nenhuma ordem real é executada ·
  Para trading real usa <code>quanta_trader.py</code> ou <code>web_app.py</code>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  PÁGINAS
# ══════════════════════════════════════════════════════════════

# ── 1. Dashboard ──────────────────────────────────────────────
if "Dashboard" in page:
    st.markdown("# 💰 Dashboard")

    acct = gen_account()
    pos  = gen_positions()

    # métricas
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Equity Total",    f"${acct['equity']:,.2f}")
    c2.metric("Cash",            f"${acct['cash']:,.2f}")
    c3.metric("P&L Não Realizado",
              f"${acct['unrealized_pl']:+,.2f}",
              f"{acct['unrealized_plpc']*100:+.2f}%")
    c4.metric("P&L Hoje",        f"${acct['day_pl']:+,.2f}")
    c5.metric("Buying Power",    f"${acct['buying_power']:,.2f}")

    st.markdown("---")
    col_left, col_right = st.columns([3,2])

    with col_left:
        st.markdown("### 📂 Posições Abertas")
        rows = []
        for p in pos:
            rows.append({
                "Ticker":  p["symbol"],
                "Qtd":     p["qty"],
                "Entrada": f"${p['avg_entry']:,.2f}",
                "Actual":  f"${p['current']:,.2f}",
                "Valor":   f"${p['market_value']:,.2f}",
                "P&L $":   f"{p['pl']:+,.2f}",
                "P&L %":   f"{p['pl_pct']*100:+.2f}%",
            })
        df_pos = pd.DataFrame(rows)
        st.dataframe(df_pos, use_container_width=True, hide_index=True)

    with col_right:
        st.markdown("### 🥧 Alocação")
        st.plotly_chart(portfolio_pie(pos), use_container_width=True)

    # equity curve
    st.markdown("### 📈 Evolução de Equity (90 dias)")
    eq_df = gen_equity_curve(90)
    st.plotly_chart(equity_chart(eq_df), use_container_width=True)


# ── 2. Watchlist ──────────────────────────────────────────────
elif "Watchlist" in page:
    st.markdown("# 📡 Watchlist em Tempo Real")

    if st.button("↻ Actualizar"):
        st.cache_data.clear()

    cols = st.columns(5)
    for i, (sym, info) in enumerate(TICKERS.items()):
        rng     = np.random.default_rng(abs(hash(sym + str(datetime.now().minute))) % (2**32))
        chg_pct = float(rng.normal(0, 1.2))
        chg_abs = info["price"] * chg_pct / 100
        price   = info["price"] + chg_abs
        arrow   = "▲" if chg_pct >= 0 else "▼"
        c       = "pos" if chg_pct >= 0 else "neg"
        with cols[i % 5]:
            st.markdown(f"""
            <div style="background:#111827;border:1px solid {'#22c55e' if chg_pct>=0 else '#ef4444'}22;
                        border-radius:10px;padding:.8rem;margin-bottom:.8rem">
              <div style="font-family:'Space Mono',monospace;color:#00d4ff;font-weight:700;font-size:.9rem">{sym}</div>
              <div style="font-size:.7rem;color:#64748b;margin-bottom:.4rem">{info['name'][:18]}</div>
              <div style="font-family:'Space Mono',monospace;font-size:1.1rem;
                          color:{'#22c55e' if chg_pct>=0 else '#ef4444'};font-weight:700">${price:,.2f}</div>
              <div style="font-size:.75rem;color:{'#22c55e' if chg_pct>=0 else '#ef4444'}">{arrow} {chg_pct:+.2f}%</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    sym_sel = st.selectbox("Ver gráfico de", list(TICKERS.keys()))
    tf_sel  = st.radio("Timeframe", ["1d","1h","1m"], horizontal=True, index=0)
    df      = gen_price_series(sym_sel, 300, tf_sel)
    show_bb = st.checkbox("Bollinger Bands", value=False)
    st.plotly_chart(candlestick_chart(df, sym_sel, show_bb=show_bb), use_container_width=True)


# ── 3. Indicadores Técnicos ───────────────────────────────────
elif "Indicadores" in page:
    st.markdown("# 📊 Indicadores Técnicos")

    c1, c2, c3 = st.columns(3)
    sym = c1.selectbox("Ticker", list(TICKERS.keys()))
    tf  = c2.selectbox("Timeframe", ["1d","1h","1m"])
    n   = c3.slider("Barras", 100, 500, 300)

    df    = gen_price_series(sym, n, tf)
    close = df["close"]
    cur   = float(close.iloc[-1])

    st.plotly_chart(candlestick_chart(df, sym, show_bb=True), use_container_width=True)

    st.markdown("### 📐 Painel de Indicadores")
    tab1, tab2, tab3, tab4 = st.tabs(["Médias Móveis","RSI","MACD","Bollinger"])

    with tab1:
        rows = []
        for p in [9,20,50,200]:
            if len(close) >= p:
                sv = float(sma(close,p).iloc[-1])
                ev = float(ema(close,p).iloc[-1])
                diff = (cur - sv) / sv * 100
                rows.append({"Período": p, "SMA": f"${sv:,.2f}",
                             "EMA": f"${ev:,.2f}",
                             "Preço vs SMA": f"{diff:+.2f}%",
                             "Sinal": "▲ Acima" if diff >= 0 else "▼ Abaixo"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    with tab2:
        rsi_v = float(rsi(close,14).iloc[-1]) if len(close) >= 14 else 50
        col1, col2 = st.columns(2)
        col1.metric("RSI (14)", f"{rsi_v:.1f}",
                    "Sobrecomprado ⚠️" if rsi_v>=70 else "Sobrevendido ✅" if rsi_v<=30 else "Neutro")
        rsi_ser = rsi(close, 14).dropna().tail(60)
        fig_rsi = go.Figure(go.Scatter(x=rsi_ser.index, y=rsi_ser,
            fill="tozeroy", fillcolor="rgba(0,212,255,.08)",
            line=dict(color="#00d4ff", width=1.5)))
        fig_rsi.add_hline(y=70, line_color="#ef4444", line_dash="dot")
        fig_rsi.add_hline(y=30, line_color="#22c55e", line_dash="dot")
        fig_rsi.update_layout(**CHART_LAYOUT, height=220, yaxis=dict(range=[0,100]))
        st.plotly_chart(fig_rsi, use_container_width=True)

    with tab3:
        if len(close) >= 35:
            ml, sl_l, hist = macd(close)
            fig_m = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                  row_heights=[.6,.4], vertical_spacing=.05)
            fig_m.add_trace(go.Scatter(x=close.index, y=ml,  name="MACD",   line=dict(color="#00d4ff")), row=1, col=1)
            fig_m.add_trace(go.Scatter(x=close.index, y=sl_l,name="Signal", line=dict(color="#f59e0b")), row=1, col=1)
            colors_m = ["#22c55e" if v >= 0 else "#ef4444" for v in hist]
            fig_m.add_trace(go.Bar(x=close.index, y=hist, marker_color=colors_m, name="Histograma"), row=2, col=1)
            fig_m.update_layout(**CHART_LAYOUT, height=340)
            st.plotly_chart(fig_m, use_container_width=True)
        else:
            st.info("Precisas de mais barras para o MACD.")

    with tab4:
        if len(close) >= 20:
            u,m,l = bollinger(close)
            fig_b = go.Figure()
            fig_b.add_trace(go.Scatter(x=close.index, y=u, name="Superior", line=dict(color="#ef4444", dash="dot")))
            fig_b.add_trace(go.Scatter(x=close.index, y=m, name="Média",    line=dict(color="#00d4ff")))
            fig_b.add_trace(go.Scatter(x=close.index, y=l, name="Inferior", line=dict(color="#22c55e", dash="dot"),
                                       fill="tonexty", fillcolor="rgba(34,197,94,.05)"))
            fig_b.add_trace(go.Scatter(x=close.index, y=close, name="Preço", line=dict(color="#f59e0b", width=1.5)))
            fig_b.update_layout(**CHART_LAYOUT, height=320)
            st.plotly_chart(fig_b, use_container_width=True)

    # resumo de sinais
    st.markdown("### 🧭 Resumo de Sinais")
    sigs = []
    if len(close)>=50:  sigs.append(("SMA 50",  "▲ COMPRAR" if cur>float(sma(close,50).iloc[-1]) else "▼ VENDER"))
    if len(close)>=200: sigs.append(("SMA 200", "▲ COMPRAR" if cur>float(sma(close,200).iloc[-1]) else "▼ VENDER"))
    if len(close)>=14:
        rv = float(rsi(close).iloc[-1])
        sigs.append(("RSI(14)", "▲ COMPRAR" if rv<=30 else "▼ VENDER" if rv>=70 else "─ NEUTRO"))
    if len(close)>=35:
        mv, sv2, _ = macd(close)
        sigs.append(("MACD", "▲ COMPRAR" if float(mv.iloc[-1])>float(sv2.iloc[-1]) else "▼ VENDER"))
    if len(close)>=20:
        uv,_,lv = bollinger(close)
        sigs.append(("Bollinger", "▼ VENDER" if cur>=float(uv.iloc[-1]) else "▲ COMPRAR" if cur<=float(lv.iloc[-1]) else "─ NEUTRO"))

    sig_cols = st.columns(len(sigs))
    for i,(name,sig) in enumerate(sigs):
        color = "#22c55e" if "COMPRAR" in sig else "#ef4444" if "VENDER" in sig else "#64748b"
        sig_cols[i].markdown(f"""
        <div style="background:#111827;border:1px solid {color}55;border-radius:10px;
                    padding:.8rem;text-align:center">
          <div style="font-size:.72rem;color:#64748b;margin-bottom:.3rem">{name}</div>
          <div style="font-family:'Space Mono',monospace;color:{color};font-weight:700;font-size:.85rem">{sig}</div>
        </div>""", unsafe_allow_html=True)


# ── 4. Backtesting ────────────────────────────────────────────
elif "Backtesting" in page:
    st.markdown("# 🧪 Backtesting")

    c1,c2,c3,c4 = st.columns(4)
    sym     = c1.selectbox("Ticker", list(TICKERS.keys()))
    tf      = c2.selectbox("Timeframe", ["1d","1h"])
    strat   = c3.selectbox("Estratégia", ["SMA Crossover","EMA Crossover","RSI Mean-Reversion","MACD Crossover","Bollinger Reversion"])
    capital = c4.number_input("Capital ($)", value=10_000.0, step=1000.0)

    with st.expander("⚙️ Parâmetros da Estratégia"):
        pc1,pc2,pc3 = st.columns(3)
        if "SMA" in strat:
            fast = pc1.number_input("SMA Rápida", value=20, min_value=5)
            slow = pc2.number_input("SMA Lenta",  value=50, min_value=10)
        elif "EMA" in strat:
            fast = pc1.number_input("EMA Rápida", value=12, min_value=5)
            slow = pc2.number_input("EMA Lenta",  value=26, min_value=10)
        elif "RSI" in strat:
            rp   = pc1.number_input("Período RSI", value=14, min_value=5)
            over_s = pc2.number_input("Sobrevenda",  value=30.0)
            over_b = pc3.number_input("Sobrecompra", value=70.0)
        elif "MACD" in strat:
            fast = pc1.number_input("MACD Rápido", value=12)
            slow = pc2.number_input("MACD Lento",  value=26)
            sig  = pc3.number_input("Signal",       value=9)
        else:
            bp   = pc1.number_input("Período BB",   value=20)
            bk   = pc2.number_input("Desvios",      value=2.0, step=0.1)

    if st.button("▶ Correr Backtest", type="primary"):
        df    = gen_price_series(sym, 500, tf)
        close = df["close"]

        with st.spinner("A simular…"):
            sigs = pd.Series(0, index=df.index)

            if "SMA" in strat:
                sf = sma(close,int(fast)); ss = sma(close,int(slow))
                sigs[(sf>ss)&(sf.shift(1)<=ss.shift(1))]  =  1
                sigs[(sf<ss)&(sf.shift(1)>=ss.shift(1))]  = -1
            elif "EMA" in strat:
                ef = ema(close,int(fast)); es = ema(close,int(slow))
                sigs[(ef>es)&(ef.shift(1)<=es.shift(1))]  =  1
                sigs[(ef<es)&(ef.shift(1)>=es.shift(1))]  = -1
            elif "RSI" in strat:
                rv = rsi(close, int(rp))
                sigs[rv<=over_s] = 1; sigs[rv>=over_b] = -1
            elif "MACD" in strat:
                ml,sl_l,_ = macd(close,int(fast),int(slow),int(sig))
                sigs[(ml>sl_l)&(ml.shift(1)<=sl_l.shift(1))] =  1
                sigs[(ml<sl_l)&(ml.shift(1)>=sl_l.shift(1))] = -1
            else:
                u,_,l = bollinger(close,int(bp),float(bk))
                sigs[close<=l] = 1; sigs[close>=u] = -1

            res = run_backtest_demo(df, sigs.values, capital)

        st.markdown("---")
        m1,m2,m3,m4,m5,m6 = st.columns(6)
        ret_d = f"{res['bh']:+.1f}% B&H"
        m1.metric("Retorno",       f"{res['return']:+.2f}%",   ret_d)
        m2.metric("Capital Final", f"${res['final']:,.0f}")
        sh_d = "excelente" if res['sharpe']>=1 else "fraco"
        m3.metric("Sharpe",        f"{res['sharpe']:.2f}",     sh_d)
        m4.metric("Max Drawdown",  f"{res['max_dd']:.1f}%")
        m5.metric("Win Rate",      f"{res['win_rate']:.1f}%")
        m6.metric("Nº Trades",     str(res['n_trades']))

        # curva de equity
        eq_series = pd.Series(res["equity_curve"], index=df.index[:len(res["equity_curve"])])
        bh_series = capital * df["close"] / df["close"].iloc[0]

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=eq_series.index, y=eq_series,
            name="Estratégia", line=dict(color="#00d4ff", width=2)))
        fig_eq.add_trace(go.Scatter(x=bh_series.index, y=bh_series.values,
            name="Buy & Hold", line=dict(color="#f59e0b", width=1.5, dash="dot")))
        fig_eq.add_hline(y=capital, line_color="#64748b", line_dash="dot", opacity=.4)
        fig_eq.update_layout(**CHART_LAYOUT, height=300,
                             title=dict(text="Curva de Equity vs Buy & Hold",
                                        font=dict(color="#00d4ff")))
        st.plotly_chart(fig_eq, use_container_width=True)

        if res["trades"] and st.checkbox("Ver trades individuais"):
            trade_df = pd.DataFrame(res["trades"])
            trade_df["pnl"]     = trade_df["pnl"].map(lambda x: f"{x:+.2f}")
            trade_df["pnl_pct"] = trade_df["pnl_pct"].map(lambda x: f"{x:+.2f}%")
            st.dataframe(trade_df, hide_index=True, use_container_width=True)


# ── 5. Análise de Risco ───────────────────────────────────────
elif "Risco" in page:
    st.markdown("# 📐 Análise de Risco & Position Sizing")

    tab1, tab2, tab3 = st.tabs(["Risco Fixo","Kelly Criterion","Monte Carlo"])

    with tab1:
        st.markdown("### Calculadora de Risco Fixo")
        c1,c2,c3,c4,c5 = st.columns(5)
        capital   = c1.number_input("Capital ($)", value=25_000.0, step=1000.0)
        risk_pct  = c2.number_input("% a Arriscar", value=1.0, step=0.1, min_value=0.1, max_value=10.0)
        entry     = c3.number_input("Entrada ($)", value=213.45, step=0.01)
        stop_l    = c4.number_input("Stop-Loss ($)", value=208.00, step=0.01)
        tp        = c5.number_input("Take-Profit ($)", value=224.00, step=0.01)

        risk_amt  = capital * risk_pct / 100
        risk_per  = abs(entry - stop_l)
        shares    = risk_amt / risk_per if risk_per > 0 else 0
        pos_val   = shares * entry
        pos_pct   = pos_val / capital * 100
        rr        = abs(tp - entry) / risk_per if risk_per > 0 else 0

        st.markdown("---")
        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("Quantidade",    f"{shares:.3f} shares")
        m2.metric("Valor Posição", f"${pos_val:,.2f}", f"{pos_pct:.1f}% capital")
        m3.metric("Risco $",       f"${risk_amt:,.2f}", f"{risk_pct}% capital")
        m4.metric("Risk/Reward",   f"{rr:.2f}R",
                  "✅ Bom" if rr>=2 else "⚠️ Fraco")
        m5.metric("Perda Máx",     f"${risk_amt:,.2f}", "se SL for atingido")

        # gauge RR
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number", value=rr,
            number={"suffix":"R","font":{"color":"#00d4ff","family":"Space Mono"}},
            gauge={"axis":{"range":[0,4]},
                   "bar":{"color":"#00d4ff"},
                   "steps":[{"range":[0,1],"color":"#ef444433"},
                             {"range":[1,2],"color":"#f59e0b33"},
                             {"range":[2,4],"color":"#22c55e33"}],
                   "threshold":{"line":{"color":"#22c55e","width":2},"value":2}},
        ))
        fig_g.update_layout(**CHART_LAYOUT, height=220)
        st.plotly_chart(fig_g, use_container_width=True)

    with tab2:
        st.markdown("### Kelly Criterion")
        c1,c2,c3 = st.columns(3)
        wr_k  = c1.slider("Win Rate histórico (%)", 30, 80, 55) / 100
        avg_w = c2.number_input("Ganho médio (%)", value=3.0, step=0.5)
        avg_l = c3.number_input("Perda média (%)",  value=1.5, step=0.5)

        b     = avg_w / avg_l if avg_l > 0 else 1
        kelly = wr_k - (1-wr_k)/b
        half  = max(kelly/2, 0)
        cap_k = st.number_input("Capital ($)", value=25_000.0, step=1000.0, key="kelly_cap")

        st.markdown("---")
        k1,k2,k3 = st.columns(3)
        k1.metric("Kelly Completo",  f"{kelly*100:.1f}%")
        k2.metric("Half-Kelly",      f"{half*100:.1f}%", "recomendado")
        k3.metric("Montante",        f"${cap_k*half:,.2f}")

        if kelly <= 0:
            st.warning("⚠️ Kelly negativo — esta estratégia não é matematicamente favorável com estes parâmetros.")

    with tab3:
        st.markdown("### Simulação Monte Carlo")
        c1,c2,c3,c4 = st.columns(4)
        sym_mc  = c1.selectbox("Ticker", list(TICKERS.keys()), key="mc_sym")
        cap_mc  = c2.number_input("Capital ($)", value=10_000.0, step=1000.0, key="mc_cap")
        days_mc = c3.number_input("Dias", value=252, step=10)
        sims_mc = c4.number_input("Simulações", value=500, step=100)

        if st.button("▶ Simular", type="primary"):
            with st.spinner("A correr simulações…"):
                df_mc  = gen_price_series(sym_mc, 252, "1d")
                rets_mc = df_mc["close"].pct_change().dropna().values
                mu_mc   = float(np.mean(rets_mc))
                sig_mc  = float(np.std(rets_mc))
                rng_mc  = np.random.default_rng(99)
                paths   = []
                for _ in range(int(sims_mc)):
                    dr    = rng_mc.normal(mu_mc, sig_mc, int(days_mc))
                    paths.append(float(cap_mc * np.prod(1+dr)))
                paths = sorted(paths)

            p5,p25,p50,p75,p95 = [np.percentile(paths,p) for p in [5,25,50,75,95]]
            prob_loss = sum(1 for p in paths if p < cap_mc) / len(paths) * 100

            mp1,mp2,mp3,mp4,mp5 = st.columns(5)
            mp1.metric("P5  (pessimista)", f"${p5:,.0f}",  f"{(p5-cap_mc)/cap_mc*100:+.1f}%")
            mp2.metric("P25",              f"${p25:,.0f}", f"{(p25-cap_mc)/cap_mc*100:+.1f}%")
            mp3.metric("P50 (mediana)",    f"${p50:,.0f}", f"{(p50-cap_mc)/cap_mc*100:+.1f}%")
            mp4.metric("P75",              f"${p75:,.0f}", f"{(p75-cap_mc)/cap_mc*100:+.1f}%")
            mp5.metric("P95 (optimista)",  f"${p95:,.0f}", f"{(p95-cap_mc)/cap_mc*100:+.1f}%")
            st.metric("Probabilidade de Perda", f"{prob_loss:.1f}%")

            fig_mc = go.Figure()
            fig_mc.add_trace(go.Histogram(x=paths, nbinsx=60,
                marker_color=["#22c55e" if p>=cap_mc else "#ef4444" for p in paths],
                name="Distribuição"))
            fig_mc.add_vline(x=cap_mc, line_color="#f59e0b", line_dash="dot",
                             annotation_text="Capital inicial")
            fig_mc.add_vline(x=p50,    line_color="#00d4ff", line_dash="dot",
                             annotation_text="Mediana")
            fig_mc.update_layout(**CHART_LAYOUT, height=280,
                                 title=dict(text=f"Monte Carlo · {int(sims_mc)} simulações · {int(days_mc)} dias",
                                            font=dict(color="#00d4ff")))
            st.plotly_chart(fig_mc, use_container_width=True)


# ── 6. Ordens & Histórico ─────────────────────────────────────
elif "Ordens" in page:
    st.markdown("# 📋 Ordens & Histórico")

    tab1, tab2, tab3 = st.tabs(["Ordens Pendentes","Nova Ordem","Histórico"])

    with tab1:
        orders = gen_orders()
        for o in orders:
            c1,c2,c3,c4,c5,c6 = st.columns([1,1,1,1,1,1])
            c1.markdown(f"**{o['symbol']}**")
            side_color = "#22c55e" if o["side"]=="buy" else "#ef4444"
            c2.markdown(f"<span style='color:{side_color}'>{o['side'].upper()}</span>", unsafe_allow_html=True)
            c3.write(f"{o['qty']} units")
            c4.write(o["type"])
            c5.write(f"${o['limit_price']:,.2f}")
            c6.markdown(f"<span style='color:#f59e0b'>{o['status']}</span>", unsafe_allow_html=True)
            st.divider()

    with tab2:
        st.markdown("#### Submeter Ordem (Simulado)")
        c1,c2,c3 = st.columns(3)
        sym_o  = c1.selectbox("Ticker",     list(TICKERS.keys()))
        side_o = c2.radio("Lado",           ["buy","sell"], horizontal=True)
        type_o = c3.selectbox("Tipo",       ["market","limit","stop"])
        qty_o  = st.number_input("Quantidade", value=10, min_value=1)
        if type_o != "market":
            lp_o = st.number_input("Limit Price ($)", value=TICKERS[sym_o]["price"])

        if st.button("📤 Submeter Ordem (Demo)", type="primary"):
            st.success(f"✅ Ordem simulada: {side_o.upper()} {qty_o}× {sym_o} @ "
                       f"{'MARKET' if type_o=='market' else f'${lp_o:,.2f}'}")
            st.info("Em modo demo as ordens não são executadas. Usa `quanta_trader.py` para trading real.")

    with tab3:
        hist    = gen_history()
        df_hist = pd.DataFrame(hist)
        total_pnl = df_hist["pnl"].sum()
        winners   = (df_hist["pnl"] > 0).sum()
        wr_h      = winners / len(df_hist) * 100
        st.metric("P&L Total", f"${total_pnl:+,.2f}")
        st.metric("Win Rate",  f"{wr_h:.1f}%")
        display = df_hist[["date","symbol","side","qty","filled_price","pnl","status"]].copy()
        display["filled_price"] = display["filled_price"].map(lambda x: f"${x:,.2f}")
        display["pnl"]          = display["pnl"].map(lambda x: f"{x:+,.2f}")
        st.dataframe(display, hide_index=True, use_container_width=True)


# ── 7. Alertas & SL/TP ───────────────────────────────────────
elif "Alertas" in page:
    st.markdown("# 🔔 Alertas & 🛡️ Stop-Loss / Take-Profit")

    if "alerts" not in st.session_state:
        st.session_state.alerts = [
            {"id":1,"symbol":"AAPL","condition":"above","target":220.0,"note":"resistência","active":True},
            {"id":2,"symbol":"NVDA","condition":"below","target":900.0,"note":"suporte","active":True},
        ]
    if "sltp" not in st.session_state:
        st.session_state.sltp = [
            {"id":1,"symbol":"AAPL","entry":195.20,"sl":190.00,"tp":225.00,"qty":150,"status":"active"},
            {"id":2,"symbol":"TSLA","entry":192.00,"sl":185.00,"tp":210.00,"qty":60, "status":"active"},
        ]

    tab1, tab2 = st.tabs(["🔔 Alertas de Preço","🛡️ Stop-Loss / TP"])

    with tab1:
        with st.form("new_alert"):
            st.markdown("#### Novo Alerta")
            c1,c2,c3,c4 = st.columns(4)
            al_sym  = c1.selectbox("Ticker",    list(TICKERS.keys()))
            al_cond = c2.selectbox("Condição",  ["above (≥)","below (≤)"])
            al_tgt  = c3.number_input("Alvo ($)", value=TICKERS[al_sym]["price"]*1.05, step=0.01)
            al_note = c4.text_input("Nota")
            if st.form_submit_button("➕ Criar Alerta"):
                nid = len(st.session_state.alerts) + 1
                st.session_state.alerts.append({
                    "id": nid, "symbol": al_sym,
                    "condition": al_cond.split()[0],
                    "target": al_tgt, "note": al_note, "active": True,
                })
                st.success(f"✅ Alerta #{nid} criado!")

        st.markdown("#### Alertas Activos")
        for a in st.session_state.alerts:
            c1,c2,c3,c4,c5 = st.columns([1,2,2,2,1])
            c1.write(f"#{a['id']}")
            c2.markdown(f"**{a['symbol']}**")
            icon = "🟢" if a["condition"]=="above" else "🔴"
            c3.write(f"{icon} {'≥' if a['condition']=='above' else '≤'} ${a['target']:,.2f}")
            c4.write(a["note"] or "—")
            if c5.button("✕", key=f"del_alert_{a['id']}"):
                st.session_state.alerts = [x for x in st.session_state.alerts if x["id"]!=a["id"]]
                st.rerun()

    with tab2:
        with st.form("new_sltp"):
            st.markdown("#### Nova Protecção SL/TP")
            c1,c2,c3,c4,c5 = st.columns(5)
            st_sym = c1.selectbox("Ticker",    list(TICKERS.keys()))
            st_qty = c2.number_input("Qtd",    value=10, min_value=1)
            st_ent = c3.number_input("Entrada ($)", value=TICKERS[st_sym]["price"], step=0.01)
            st_sl  = c4.number_input("Stop-Loss ($)", value=TICKERS[st_sym]["price"]*0.97, step=0.01)
            st_tp  = c5.number_input("Take-Profit ($)", value=TICKERS[st_sym]["price"]*1.05, step=0.01)
            if st.form_submit_button("🛡️ Activar Protecção"):
                rr = abs(st_tp-st_ent)/abs(st_ent-st_sl) if abs(st_ent-st_sl)>0 else 0
                nid = len(st.session_state.sltp) + 1
                st.session_state.sltp.append({
                    "id":nid,"symbol":st_sym,"entry":st_ent,
                    "sl":st_sl,"tp":st_tp,"qty":st_qty,"status":"active",
                })
                st.success(f"✅ Protecção #{nid} activa! R/R: {rr:.2f}")

        st.markdown("#### Protecções Activas")
        for g in st.session_state.sltp:
            risk   = abs(g["entry"]-g["sl"])*g["qty"]
            reward = abs(g["tp"]-g["entry"])*g["qty"]
            rr     = reward/risk if risk>0 else 0
            c1,c2,c3,c4,c5,c6 = st.columns([1,1,1,1,1,1])
            c1.write(f"#{g['id']}")
            c2.markdown(f"**{g['symbol']}**")
            c3.markdown(f"<span style='color:#ef4444'>SL ${g['sl']:,.2f}</span>", unsafe_allow_html=True)
            c4.markdown(f"<span style='color:#22c55e'>TP ${g['tp']:,.2f}</span>", unsafe_allow_html=True)
            c5.write(f"{rr:.2f}R")
            if c6.button("✕", key=f"del_sltp_{g['id']}"):
                st.session_state.sltp = [x for x in st.session_state.sltp if x["id"]!=g["id"]]
                st.rerun()


# ── 8. Performance ────────────────────────────────────────────
elif "Performance" in page:
    st.markdown("# 📈 Dashboard de Performance")

    hist    = gen_history()
    df_h    = pd.DataFrame(hist)
    eq_df   = gen_equity_curve(90)

    # KPIs globais
    total_pnl   = df_h["pnl"].sum()
    winners     = (df_h["pnl"] > 0).sum()
    wr          = winners / len(df_h) * 100
    avg_win     = df_h[df_h["pnl"]>0]["pnl"].mean()
    avg_loss    = df_h[df_h["pnl"]<0]["pnl"].mean()
    pf          = abs(avg_win/avg_loss) if avg_loss != 0 else 0
    best_trade  = df_h.loc[df_h["pnl"].idxmax()]
    worst_trade = df_h.loc[df_h["pnl"].idxmin()]

    k1,k2,k3,k4,k5,k6 = st.columns(6)
    k1.metric("P&L Total",      f"${total_pnl:+,.2f}")
    k2.metric("Nº Trades",      str(len(df_h)))
    k3.metric("Win Rate",       f"{wr:.1f}%")
    k4.metric("Profit Factor",  f"{pf:.2f}")
    k5.metric("Melhor Trade",   f"${best_trade['pnl']:+,.2f}", best_trade["symbol"])
    k6.metric("Pior Trade",     f"${worst_trade['pnl']:+,.2f}", worst_trade["symbol"])

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Equity Curve (90 dias)")
        st.plotly_chart(equity_chart(eq_df), use_container_width=True)

    with col2:
        st.markdown("#### P&L por Ticker")
        pnl_sym = df_h.groupby("symbol")["pnl"].sum().reset_index().sort_values("pnl")
        colors  = ["#22c55e" if v>=0 else "#ef4444" for v in pnl_sym["pnl"]]
        fig_bar = go.Figure(go.Bar(x=pnl_sym["symbol"], y=pnl_sym["pnl"],
            marker_color=colors, text=pnl_sym["pnl"].map(lambda x: f"{x:+,.0f}"),
            textposition="outside"))
        fig_bar.update_layout(**CHART_LAYOUT, height=280,
                              title=dict(text="P&L por Ticker", font=dict(color="#00d4ff")))
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("#### Distribuição de P&L por Trade")
    fig_dist = go.Figure(go.Histogram(
        x=df_h["pnl"], nbinsx=20,
        marker_color=["#22c55e" if v>=0 else "#ef4444" for v in df_h["pnl"]],
    ))
    fig_dist.add_vline(x=0, line_color="#f59e0b", line_dash="dot")
    fig_dist.update_layout(**CHART_LAYOUT, height=240,
                           title=dict(text="Distribuição de P&L", font=dict(color="#00d4ff")))
    st.plotly_chart(fig_dist, use_container_width=True)

    # tabela de top performers
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("#### Top 5 Tickers")
        top = df_h.groupby("symbol").agg(
            trades=("pnl","count"), pnl=("pnl","sum"), wr=("pnl",lambda x:(x>0).mean()*100)
        ).sort_values("pnl", ascending=False).head(5).reset_index()
        top["pnl"] = top["pnl"].map(lambda x: f"${x:+,.2f}")
        top["wr"]  = top["wr"].map(lambda x: f"{x:.0f}%")
        st.dataframe(top, hide_index=True, use_container_width=True)

    with col4:
        st.markdown("#### Trades por Dia da Semana")
        df_h["weekday"] = pd.to_datetime(df_h["date"]).dt.day_name()
        by_day  = df_h.groupby("weekday")["pnl"].sum().reindex(
            ["Monday","Tuesday","Wednesday","Thursday","Friday"])
        colors2 = ["#22c55e" if v>=0 else "#ef4444" for v in by_day.values]
        fig_wd  = go.Figure(go.Bar(x=by_day.index, y=by_day.values, marker_color=colors2))
        fig_wd.update_layout(**CHART_LAYOUT, height=240,
                             title=dict(text="P&L por Dia da Semana", font=dict(color="#00d4ff")))
        st.plotly_chart(fig_wd, use_container_width=True)


# ── footer ────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:3rem;padding:1rem;border-top:1px solid #1e2d45;
            text-align:center;font-size:.72rem;color:#475569;font-family:'Space Mono',monospace">
  ⚡ QuantaTrader Demo · Dados 100% simulados · Sem risco financeiro ·
  <a href="https://github.com/teu-username/quanta-trader" style="color:#00d4ff">GitHub</a>
</div>
""", unsafe_allow_html=True)
