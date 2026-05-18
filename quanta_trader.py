"""
╔══════════════════════════════════════════════════════════════╗
║              QuantaTrader — AI Trading Assistant             ║
║         Inspirado no Alpaca Trading · Feito em Python        ║
╚══════════════════════════════════════════════════════════════╝

GitHub: https://github.com/teu-username/quanta-trader

Funcionalidades:
  • Dashboard de portfolio em tempo real (via Alpaca API)
  • Ordens de compra/venda com gestão de risco
  • Assistente IA integrado (Claude) para análise de mercado
  • Histórico de trades e P&L
  • Alertas de preço configuráveis
  • Paper trading mode (sem dinheiro real)

Dependências:
  pip install alpaca-trade-api anthropic rich prompt_toolkit requests python-dotenv

Configuração (.env):
  ALPACA_API_KEY=...
  ALPACA_SECRET_KEY=...
  ALPACA_BASE_URL=https://paper-api.alpaca.markets   # paper trading
  ANTHROPIC_API_KEY=...
"""

import os
import sys
import json
import time
import threading
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv

# ── Rich TUI ──────────────────────────────────────────────────
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box
from rich.columns import Columns
from rich.rule import Rule

# ── Alpaca ─────────────────────────────────────────────────────
import alpaca_trade_api as tradeapi

# ── Anthropic (Claude AI) ──────────────────────────────────────
import anthropic

# ── Misc ───────────────────────────────────────────────────────
import requests

load_dotenv()

console = Console()

# ══════════════════════════════════════════════════════════════
#  CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

PAPER_MODE = "paper" in ALPACA_BASE_URL

# ══════════════════════════════════════════════════════════════
#  CLIENTE ALPACA
# ══════════════════════════════════════════════════════════════

def get_alpaca_client() -> Optional[tradeapi.REST]:
    """Inicializa e devolve o cliente Alpaca."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        console.print("[red]❌  Chaves Alpaca não configuradas no .env[/red]")
        return None
    try:
        api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL, api_version="v2")
        api.get_account()  # teste de ligação
        return api
    except Exception as e:
        console.print(f"[red]❌  Erro ao ligar ao Alpaca: {e}[/red]")
        return None


# ══════════════════════════════════════════════════════════════
#  CLIENTE ANTHROPIC (Claude)
# ══════════════════════════════════════════════════════════════

def get_anthropic_client() -> Optional[anthropic.Anthropic]:
    if not ANTHROPIC_API_KEY:
        console.print("[yellow]⚠️   ANTHROPIC_API_KEY não definida. Assistente IA desactivado.[/yellow]")
        return None
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ══════════════════════════════════════════════════════════════
#  HELPERS DE DISPLAY
# ══════════════════════════════════════════════════════════════

def banner():
    console.print(Panel.fit(
        "[bold cyan]⚡ QuantaTrader[/bold cyan]  [dim]|  AI-Powered Trading Assistant[/dim]\n"
        f"[dim]Modo: {'📄 Paper Trading (simulação)' if PAPER_MODE else '💰 Live Trading'}[/dim]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()


def fmt_money(value: float, color: bool = True) -> str:
    """Formata valor monetário com cor."""
    sign = "+" if value >= 0 else ""
    formatted = f"{sign}${value:,.2f}"
    if not color:
        return formatted
    return f"[green]{formatted}[/green]" if value >= 0 else f"[red]{formatted}[/red]"


def fmt_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    s = f"{sign}{value:.2f}%"
    return f"[green]{s}[/green]" if value >= 0 else f"[red]{s}[/red]"


# ══════════════════════════════════════════════════════════════
#  MÓDULO: PORTFOLIO / CONTA
# ══════════════════════════════════════════════════════════════

def show_account(api: tradeapi.REST):
    """Mostra resumo da conta."""
    try:
        acct = api.get_account()
    except Exception as e:
        console.print(f"[red]Erro ao obter conta: {e}[/red]")
        return

    equity   = float(acct.equity)
    cash     = float(acct.cash)
    pl       = float(acct.unrealized_pl) if hasattr(acct, "unrealized_pl") else 0.0
    pl_pct   = float(acct.unrealized_plpc) * 100 if hasattr(acct, "unrealized_plpc") else 0.0
    buying   = float(acct.buying_power)

    table = Table(box=box.ROUNDED, border_style="cyan", show_header=False, padding=(0, 2))
    table.add_column("Campo",  style="bold dim", width=22)
    table.add_column("Valor",  justify="right")

    table.add_row("💼 Equity Total",    fmt_money(equity, color=False))
    table.add_row("💵 Cash Disponível", fmt_money(cash, color=False))
    table.add_row("📈 P&L Não Realizado", fmt_money(pl))
    table.add_row("📊 P&L %",           fmt_pct(pl_pct))
    table.add_row("🛒 Buying Power",    fmt_money(buying, color=False))
    table.add_row("🔒 Status",          f"[green]{acct.status}[/green]")

    console.print(Panel(table, title="[bold cyan]💰 Resumo da Conta[/bold cyan]", border_style="cyan"))


def show_positions(api: tradeapi.REST):
    """Lista posições abertas."""
    try:
        positions = api.list_positions()
    except Exception as e:
        console.print(f"[red]Erro ao obter posições: {e}[/red]")
        return

    if not positions:
        console.print("[yellow]Sem posições abertas.[/yellow]")
        return

    table = Table(box=box.ROUNDED, border_style="cyan", show_header=True, header_style="bold cyan")
    table.add_column("Ticker",   style="bold", width=8)
    table.add_column("Qtd",      justify="right", width=8)
    table.add_column("Preço Méd.", justify="right", width=12)
    table.add_column("Preço Atual", justify="right", width=12)
    table.add_column("Valor",    justify="right", width=12)
    table.add_column("P&L $",   justify="right", width=12)
    table.add_column("P&L %",   justify="right", width=10)

    for p in positions:
        pl     = float(p.unrealized_pl)
        pl_pct = float(p.unrealized_plpc) * 100
        table.add_row(
            p.symbol,
            p.qty,
            f"${float(p.avg_entry_price):,.2f}",
            f"${float(p.current_price):,.2f}",
            f"${float(p.market_value):,.2f}",
            fmt_money(pl),
            fmt_pct(pl_pct),
        )

    console.print(Panel(table, title="[bold cyan]📂 Posições Abertas[/bold cyan]", border_style="cyan"))


# ══════════════════════════════════════════════════════════════
#  MÓDULO: ORDENS
# ══════════════════════════════════════════════════════════════

def show_open_orders(api: tradeapi.REST):
    """Lista ordens abertas/pendentes."""
    try:
        orders = api.list_orders(status="open")
    except Exception as e:
        console.print(f"[red]Erro: {e}[/red]")
        return

    if not orders:
        console.print("[yellow]Sem ordens pendentes.[/yellow]")
        return

    table = Table(box=box.ROUNDED, border_style="yellow", header_style="bold yellow")
    table.add_column("ID",     width=10)
    table.add_column("Ticker", width=8)
    table.add_column("Lado",   width=6)
    table.add_column("Tipo",   width=10)
    table.add_column("Qtd",    justify="right")
    table.add_column("Preço",  justify="right")
    table.add_column("Estado", width=10)

    for o in orders:
        lado_color = "[green]BUY[/green]" if o.side == "buy" else "[red]SELL[/red]"
        table.add_row(
            o.id[:8] + "…",
            o.symbol,
            lado_color,
            o.type,
            o.qty,
            f"${float(o.limit_price):,.2f}" if o.limit_price else "—",
            o.status,
        )

    console.print(Panel(table, title="[bold yellow]📋 Ordens Pendentes[/bold yellow]", border_style="yellow"))


def place_order(api: tradeapi.REST):
    """Fluxo interactivo para colocar uma ordem."""
    console.print(Rule("[bold cyan]➕ Nova Ordem[/bold cyan]"))

    symbol = Prompt.ask("  Ticker (ex: AAPL, TSLA, BTC/USD)").upper().strip()
    side   = Prompt.ask("  Lado", choices=["buy", "sell"], default="buy")
    qty    = Prompt.ask("  Quantidade")
    otype  = Prompt.ask("  Tipo", choices=["market", "limit", "stop", "stop_limit"], default="market")

    limit_price = stop_price = None
    if otype in ("limit", "stop_limit"):
        limit_price = Prompt.ask("  Limit Price ($)")
    if otype in ("stop", "stop_limit"):
        stop_price = Prompt.ask("  Stop Price ($)")

    tif = Prompt.ask("  Time in Force", choices=["day", "gtc", "ioc", "fok"], default="day")

    console.print()
    console.print(Panel(
        f"[bold]Ticker:[/bold] {symbol}\n"
        f"[bold]Lado:[/bold]   {'[green]' if side == 'buy' else '[red]'}{side.upper()}[/]\n"
        f"[bold]Qtd:[/bold]    {qty}\n"
        f"[bold]Tipo:[/bold]   {otype}\n"
        f"[bold]TIF:[/bold]    {tif}",
        title="Confirmar Ordem", border_style="yellow"
    ))

    if not Confirm.ask("  Confirmas esta ordem?"):
        console.print("[dim]Ordem cancelada.[/dim]")
        return

    try:
        kwargs = dict(symbol=symbol, qty=qty, side=side, type=otype, time_in_force=tif)
        if limit_price:
            kwargs["limit_price"] = limit_price
        if stop_price:
            kwargs["stop_price"] = stop_price

        order = api.submit_order(**kwargs)
        console.print(f"\n[green]✅ Ordem submetida![/green]  ID: [bold]{order.id}[/bold]")
    except Exception as e:
        console.print(f"[red]❌ Erro ao submeter ordem: {e}[/red]")


def cancel_order(api: tradeapi.REST):
    """Cancela uma ordem pelo ID."""
    order_id = Prompt.ask("  ID da ordem a cancelar (ou 'all' para todas)").strip()
    try:
        if order_id.lower() == "all":
            api.cancel_all_orders()
            console.print("[green]✅ Todas as ordens canceladas.[/green]")
        else:
            api.cancel_order(order_id)
            console.print(f"[green]✅ Ordem {order_id} cancelada.[/green]")
    except Exception as e:
        console.print(f"[red]❌ Erro: {e}[/red]")


# ══════════════════════════════════════════════════════════════
#  MÓDULO: COTAÇÕES
# ══════════════════════════════════════════════════════════════

def get_quote(api: tradeapi.REST):
    """Obtém cotação de um símbolo."""
    symbol = Prompt.ask("  Ticker").upper().strip()
    try:
        # último bar de 1 minuto
        bars = api.get_bars(symbol, tradeapi.TimeFrame.Minute, limit=1).df
        if bars.empty:
            console.print("[yellow]Sem dados disponíveis.[/yellow]")
            return
        last = bars.iloc[-1]
        console.print(Panel(
            f"[bold]{symbol}[/bold]\n\n"
            f"  Open:  ${last['open']:,.2f}\n"
            f"  High:  ${last['high']:,.2f}\n"
            f"  Low:   ${last['low']:,.2f}\n"
            f"  Close: [bold cyan]${last['close']:,.2f}[/bold cyan]\n"
            f"  Vol:   {int(last['volume']):,}",
            title="📉 Cotação", border_style="cyan"
        ))
    except Exception as e:
        console.print(f"[red]❌ Erro: {e}[/red]")


# ══════════════════════════════════════════════════════════════
#  MÓDULO: ASSISTENTE IA (Claude)
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
És o QuantaTrader AI, um assistente de trading financeiro especializado.
Ajudas traders a analisar mercados, interpretar dados, gerir risco e
tomar decisões informadas. Respondes em Português de Portugal.

Directrizes:
- Fornece análises objectivas e equilibradas
- Destaca sempre os riscos envolvidos
- Não dás conselhos financeiros vinculativos
- Usa terminologia financeira correcta
- Sê conciso mas completo
"""

conversation_history = []

def ai_assistant(ai_client: anthropic.Anthropic, api: Optional[tradeapi.REST] = None):
    """Loop de chat com o assistente IA."""
    console.print(Rule("[bold cyan]🤖 Assistente IA — QuantaTrader AI[/bold cyan]"))
    console.print("[dim]Escreve 'sair' para voltar ao menu principal.[/dim]\n")

    # contexto de portfolio (opcional)
    portfolio_ctx = ""
    if api:
        try:
            acct = api.get_account()
            positions = api.list_positions()
            pos_str = ", ".join([f"{p.symbol} ({p.qty})" for p in positions]) or "nenhuma"
            portfolio_ctx = (
                f"\n\nContexto actual do utilizador:\n"
                f"- Equity: ${float(acct.equity):,.2f}\n"
                f"- Cash: ${float(acct.cash):,.2f}\n"
                f"- Posições abertas: {pos_str}\n"
                f"- Modo: {'Paper Trading' if PAPER_MODE else 'Live Trading'}"
            )
        except Exception:
            pass

    system = SYSTEM_PROMPT + portfolio_ctx

    while True:
        user_input = Prompt.ask("\n  [bold cyan]Tu[/bold cyan]").strip()
        if user_input.lower() in ("sair", "exit", "quit"):
            break
        if not user_input:
            continue

        conversation_history.append({"role": "user", "content": user_input})

        try:
            with console.status("[cyan]QuantaTrader AI a pensar…[/cyan]"):
                response = ai_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1024,
                    system=system,
                    messages=conversation_history,
                )
            reply = response.content[0].text
            conversation_history.append({"role": "assistant", "content": reply})

            console.print(f"\n  [bold green]🤖 QuantaTrader AI[/bold green]")
            console.print(Panel(reply, border_style="green", padding=(0, 2)))

        except Exception as e:
            console.print(f"[red]❌ Erro no assistente IA: {e}[/red]")
            break


# ══════════════════════════════════════════════════════════════
#  MÓDULO: HISTÓRICO
# ══════════════════════════════════════════════════════════════

def show_history(api: tradeapi.REST, limit: int = 20):
    """Mostra histórico de trades."""
    try:
        orders = api.list_orders(status="closed", limit=limit, direction="desc")
    except Exception as e:
        console.print(f"[red]Erro: {e}[/red]")
        return

    if not orders:
        console.print("[yellow]Sem histórico de trades.[/yellow]")
        return

    table = Table(box=box.SIMPLE, border_style="dim", header_style="bold dim")
    table.add_column("Data",    width=12)
    table.add_column("Ticker",  width=8)
    table.add_column("Lado",    width=6)
    table.add_column("Qtd",     justify="right")
    table.add_column("Preço",   justify="right")
    table.add_column("Estado",  width=12)

    for o in orders:
        dt = o.submitted_at[:10] if o.submitted_at else "—"
        lado = "[green]BUY[/green]" if o.side == "buy" else "[red]SELL[/red]"
        price = f"${float(o.filled_avg_price):,.2f}" if o.filled_avg_price else "—"
        table.add_row(dt, o.symbol, lado, o.qty or "—", price, o.status)

    console.print(Panel(table, title=f"[dim]📜 Últimos {limit} Trades[/dim]", border_style="dim"))


# ══════════════════════════════════════════════════════════════
#  MÓDULO: ALERTAS DE PREÇO
# ══════════════════════════════════════════════════════════════

@dataclass
class PriceAlert:
    """Representa um alerta de preço."""
    id:        int
    symbol:    str
    condition: str        # "above" | "below"
    target:    float
    note:      str = ""
    triggered: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    triggered_at: str = ""


class AlertManager:
    """
    Gere alertas de preço em background.
    Corre uma thread dedicada que verifica os preços a cada `interval` segundos.
    """

    def __init__(self, api: tradeapi.REST, interval: int = 30):
        self.api       = api
        self.interval  = interval
        self.alerts: List[PriceAlert] = []
        self._lock     = threading.Lock()
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_id  = 1

    # ── CRUD ──────────────────────────────────────────────────

    def add_alert(self, symbol: str, condition: str, target: float, note: str = "") -> PriceAlert:
        with self._lock:
            alert = PriceAlert(
                id=self._next_id,
                symbol=symbol.upper(),
                condition=condition,
                target=target,
                note=note,
            )
            self.alerts.append(alert)
            self._next_id += 1
        return alert

    def remove_alert(self, alert_id: int) -> bool:
        with self._lock:
            before = len(self.alerts)
            self.alerts = [a for a in self.alerts if a.id != alert_id]
            return len(self.alerts) < before

    def clear_triggered(self):
        with self._lock:
            self.alerts = [a for a in self.alerts if not a.triggered]

    def list_alerts(self) -> List[PriceAlert]:
        with self._lock:
            return list(self.alerts)

    # ── VERIFICAÇÃO ───────────────────────────────────────────

    def _get_price(self, symbol: str) -> Optional[float]:
        try:
            bars = self.api.get_bars(symbol, tradeapi.TimeFrame.Minute, limit=1).df
            if not bars.empty:
                return float(bars.iloc[-1]["close"])
        except Exception:
            pass
        return None

    def _check_alerts(self):
        """Verifica todos os alertas activos e dispara os que foram atingidos."""
        with self._lock:
            active = [a for a in self.alerts if not a.triggered]

        # agrupa por símbolo para minimizar chamadas à API
        symbols = list({a.symbol for a in active})
        prices = {s: self._get_price(s) for s in symbols}

        for alert in active:
            price = prices.get(alert.symbol)
            if price is None:
                continue

            fired = (
                (alert.condition == "above" and price >= alert.target) or
                (alert.condition == "below" and price <= alert.target)
            )

            if fired:
                with self._lock:
                    alert.triggered = True
                    alert.triggered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # notificação no terminal (visível mesmo durante o menu)
                icon = "🔴" if alert.condition == "below" else "🟢"
                console.print(
                    f"\n  {icon} [bold yellow]ALERTA DISPARADO![/bold yellow]  "
                    f"[bold]{alert.symbol}[/bold] "
                    f"{'≥' if alert.condition == 'above' else '≤'} "
                    f"${alert.target:,.2f}  "
                    f"→  Preço actual: [bold cyan]${price:,.2f}[/bold cyan]"
                    + (f"  [dim]({alert.note})[/dim]" if alert.note else "")
                )

    # ── THREAD ────────────────────────────────────────────────

    def _run(self):
        while not self._stop_evt.is_set():
            self._check_alerts()
            self._stop_evt.wait(self.interval)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="AlertMonitor")
        self._thread.start()

    def stop(self):
        self._stop_evt.set()


# ── UI de Alertas ──────────────────────────────────────────────

def show_alerts(manager: AlertManager):
    """Lista todos os alertas configurados."""
    alerts = manager.list_alerts()

    if not alerts:
        console.print("[yellow]Sem alertas configurados.[/yellow]")
        return

    table = Table(box=box.ROUNDED, border_style="yellow", header_style="bold yellow")
    table.add_column("ID",        width=4,  justify="center")
    table.add_column("Ticker",    width=8)
    table.add_column("Condição",  width=10)
    table.add_column("Alvo",      width=12, justify="right")
    table.add_column("Estado",    width=12)
    table.add_column("Nota",      width=20)
    table.add_column("Criado em", width=14)

    for a in alerts:
        cond_str = (
            f"[green]≥ Acima[/green]" if a.condition == "above"
            else f"[red]≤ Abaixo[/red]"
        )
        if a.triggered:
            estado = f"[dim]✅ Disparado\n{a.triggered_at}[/dim]"
        else:
            estado = "[cyan]⏳ Activo[/cyan]"

        table.add_row(
            str(a.id),
            a.symbol,
            cond_str,
            f"${a.target:,.2f}",
            estado,
            a.note or "—",
            a.created_at,
        )

    total   = len(alerts)
    activos = sum(1 for a in alerts if not a.triggered)
    console.print(Panel(
        table,
        title=f"[bold yellow]🔔 Alertas de Preço  [dim]({activos} activos / {total} total)[/dim][/bold yellow]",
        border_style="yellow",
    ))


def add_alert_ui(manager: AlertManager):
    """Fluxo interactivo para criar um alerta."""
    console.print(Rule("[bold yellow]➕ Novo Alerta de Preço[/bold yellow]"))

    symbol    = Prompt.ask("  Ticker (ex: AAPL, TSLA)").upper().strip()
    condition = Prompt.ask("  Condição", choices=["above", "below"], default="above")
    target    = float(Prompt.ask("  Preço alvo ($)"))
    note      = Prompt.ask("  Nota (opcional)", default="").strip()

    arrow = "≥" if condition == "above" else "≤"
    console.print(
        f"\n  Alerta: [bold]{symbol}[/bold] quando preço {arrow} [bold cyan]${target:,.2f}[/bold cyan]"
        + (f"  [dim]— {note}[/dim]" if note else "")
    )

    if Confirm.ask("  Confirmas?"):
        alert = manager.add_alert(symbol, condition, target, note)
        console.print(f"[green]✅ Alerta #{alert.id} criado! A monitorizar a cada {manager.interval}s.[/green]")
    else:
        console.print("[dim]Cancelado.[/dim]")


def remove_alert_ui(manager: AlertManager):
    """Remove um alerta pelo ID."""
    show_alerts(manager)
    if not manager.list_alerts():
        return
    alert_id = Prompt.ask("  ID do alerta a remover").strip()
    try:
        if manager.remove_alert(int(alert_id)):
            console.print(f"[green]✅ Alerta #{alert_id} removido.[/green]")
        else:
            console.print(f"[yellow]Alerta #{alert_id} não encontrado.[/yellow]")
    except ValueError:
        console.print("[red]ID inválido.[/red]")


def alerts_menu(manager: AlertManager):
    """Submenu de gestão de alertas."""
    while True:
        console.print(Rule("[bold yellow]🔔 Alertas de Preço[/bold yellow]"))
        console.print(
            "  [bold cyan]1[/bold cyan] Ver alertas\n"
            "  [bold cyan]2[/bold cyan] Criar alerta\n"
            "  [bold cyan]3[/bold cyan] Remover alerta\n"
            "  [bold cyan]4[/bold cyan] Limpar disparados\n"
            "  [bold cyan]0[/bold cyan] Voltar\n"
        )
        op = Prompt.ask("  Opção", default="0").strip()

        if op == "0":
            break
        elif op == "1":
            show_alerts(manager)
        elif op == "2":
            add_alert_ui(manager)
        elif op == "3":
            remove_alert_ui(manager)
        elif op == "4":
            manager.clear_triggered()
            console.print("[green]✅ Alertas disparados removidos.[/green]")

        console.print()
        input("  ↩  Prima Enter para continuar…")


# ══════════════════════════════════════════════════════════════
#  MÓDULO: STOP-LOSS / TAKE-PROFIT (OCO)
# ══════════════════════════════════════════════════════════════

@dataclass
class SLTPGuard:
    """
    Representa um conjunto SL/TP associado a uma posição.
    Pode usar ordens nativas da Alpaca (bracket/OCO) ou ser
    monitorizado em software pela thread de background.
    """
    id:            int
    symbol:        str
    qty:           str              # quantidade a fechar
    side:          str              # "sell" para long, "buy" para short
    entry_price:   float
    stop_loss:     Optional[float]  # preço absoluto de SL
    take_profit:   Optional[float]  # preço absoluto de TP
    sl_pct:        Optional[float]  # % usada para calcular SL (apenas display)
    tp_pct:        Optional[float]  # % usada para calcular TP (apenas display)
    mode:          str = "native"   # "native" | "software"
    status:        str = "active"   # "active" | "sl_hit" | "tp_hit" | "cancelled"
    order_ids:     List[str] = field(default_factory=list)
    created_at:    str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    closed_at:     str = ""
    closed_price:  float = 0.0


class SLTPManager:
    """
    Gere proteções SL/TP para posições abertas.

    Modos:
      • native  — submete ordens bracket/OCO directamente na Alpaca.
                  A corretora gere o cancelamento automaticamente.
      • software — monitoriza preços em background e envia ordem
                  de mercado quando SL ou TP é atingido.
                  Útil quando a Alpaca não suporta bracket (ex: crypto).
    """

    def __init__(self, api: tradeapi.REST, interval: int = 15):
        self.api      = api
        self.interval = interval
        self.guards:  List[SLTPGuard] = []
        self._lock    = threading.Lock()
        self._stop    = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_id = 1

    # ── CÁLCULO DE PREÇOS ─────────────────────────────────────

    @staticmethod
    def calc_sl(entry: float, pct: float, side: str) -> float:
        """Calcula preço de stop-loss a partir de percentagem."""
        return round(entry * (1 - pct / 100) if side == "sell" else entry * (1 + pct / 100), 4)

    @staticmethod
    def calc_tp(entry: float, pct: float, side: str) -> float:
        """Calcula preço de take-profit a partir de percentagem."""
        return round(entry * (1 + pct / 100) if side == "sell" else entry * (1 - pct / 100), 4)

    # ── SUBMISSÃO NATIVA (bracket order) ──────────────────────

    def _submit_native(self, guard: SLTPGuard) -> bool:
        """
        Tenta submeter uma ordem bracket OCO na Alpaca.
        Devolve True se tiver sucesso, False caso contrário.
        """
        try:
            order_class = "oco" if (guard.stop_loss and guard.take_profit) else (
                "stop"  if guard.stop_loss else "limit"
            )

            kwargs: dict = dict(
                symbol=guard.symbol,
                qty=guard.qty,
                side=guard.side,
                type="market",
                time_in_force="gtc",
                order_class=order_class,
            )

            if guard.stop_loss and guard.take_profit:
                kwargs["stop_loss"]   = {"stop_price": str(round(guard.stop_loss, 2))}
                kwargs["take_profit"] = {"limit_price": str(round(guard.take_profit, 2))}
            elif guard.stop_loss:
                kwargs["stop_loss"]   = {"stop_price": str(round(guard.stop_loss, 2))}
            elif guard.take_profit:
                kwargs["take_profit"] = {"limit_price": str(round(guard.take_profit, 2))}

            order = self.api.submit_order(**kwargs)
            guard.order_ids.append(order.id)
            return True

        except Exception as e:
            console.print(f"  [yellow]⚠️  Modo nativo falhou ({e}). A usar modo software.[/yellow]")
            return False

    # ── ADICIONAR GUARD ───────────────────────────────────────

    def add(
        self,
        symbol: str,
        qty: str,
        side: str,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        sl_pct: Optional[float] = None,
        tp_pct: Optional[float] = None,
        prefer_native: bool = True,
    ) -> SLTPGuard:

        guard = SLTPGuard(
            id=self._next_id,
            symbol=symbol.upper(),
            qty=qty,
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            sl_pct=sl_pct,
            tp_pct=tp_pct,
        )
        self._next_id += 1

        if prefer_native:
            success = self._submit_native(guard)
            guard.mode = "native" if success else "software"
        else:
            guard.mode = "software"

        with self._lock:
            self.guards.append(guard)

        return guard

    # ── CANCELAR GUARD ────────────────────────────────────────

    def cancel(self, guard_id: int) -> bool:
        with self._lock:
            guard = next((g for g in self.guards if g.id == guard_id), None)
            if not guard or guard.status != "active":
                return False
            guard.status = "cancelled"

        # tenta cancelar ordens nativas pendentes
        for oid in guard.order_ids:
            try:
                self.api.cancel_order(oid)
            except Exception:
                pass
        return True

    def list_guards(self) -> List[SLTPGuard]:
        with self._lock:
            return list(self.guards)

    def clear_closed(self):
        with self._lock:
            self.guards = [g for g in self.guards if g.status == "active"]

    # ── MONITOR SOFTWARE ──────────────────────────────────────

    def _get_price(self, symbol: str) -> Optional[float]:
        try:
            bars = self.api.get_bars(symbol, tradeapi.TimeFrame.Minute, limit=1).df
            if not bars.empty:
                return float(bars.iloc[-1]["close"])
        except Exception:
            pass
        return None

    def _execute_close(self, guard: SLTPGuard, reason: str, price: float):
        """Envia ordem de mercado para fechar posição (modo software)."""
        try:
            order = self.api.submit_order(
                symbol=guard.symbol,
                qty=guard.qty,
                side=guard.side,
                type="market",
                time_in_force="gtc",
            )
            guard.order_ids.append(order.id)
            guard.status       = reason          # "sl_hit" | "tp_hit"
            guard.closed_at    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            guard.closed_price = price

            icon  = "🔴" if reason == "sl_hit" else "🟢"
            label = "STOP-LOSS" if reason == "sl_hit" else "TAKE-PROFIT"
            console.print(
                f"\n  {icon} [bold]{'red' if reason == 'sl_hit' else 'green'}[/bold]"
                f"[bold]{label} EXECUTADO![/bold]  "
                f"[bold]{guard.symbol}[/bold]  "
                f"Preço: [bold cyan]${price:,.2f}[/bold cyan]  "
                f"Qty: {guard.qty}"
            )
        except Exception as e:
            console.print(f"  [red]❌ Erro ao executar {reason} para {guard.symbol}: {e}[/red]")

    def _check_software(self):
        """Verifica guards em modo software."""
        with self._lock:
            sw_guards = [g for g in self.guards if g.mode == "software" and g.status == "active"]

        symbols = list({g.symbol for g in sw_guards})
        prices  = {s: self._get_price(s) for s in symbols}

        for guard in sw_guards:
            price = prices.get(guard.symbol)
            if price is None:
                continue

            is_long = guard.side == "sell"  # posição long fecha com sell

            if guard.stop_loss and (
                (is_long  and price <= guard.stop_loss) or
                (not is_long and price >= guard.stop_loss)
            ):
                self._execute_close(guard, "sl_hit", price)

            elif guard.take_profit and (
                (is_long  and price >= guard.take_profit) or
                (not is_long and price <= guard.take_profit)
            ):
                self._execute_close(guard, "tp_hit", price)

    def _run(self):
        while not self._stop.is_set():
            self._check_software()
            self._stop.wait(self.interval)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="SLTPMonitor")
        self._thread.start()

    def stop(self):
        self._stop.set()


# ── UI de SL/TP ───────────────────────────────────────────────

def _fmt_status(status: str) -> str:
    return {
        "active":    "[cyan]⚡ Activo[/cyan]",
        "sl_hit":    "[red]🔴 SL Exec.[/red]",
        "tp_hit":    "[green]🟢 TP Exec.[/green]",
        "cancelled": "[dim]❌ Cancelado[/dim]",
    }.get(status, status)


def show_sltp(manager: SLTPManager):
    """Lista todas as proteções SL/TP."""
    guards = manager.list_guards()

    if not guards:
        console.print("[yellow]Sem proteções SL/TP configuradas.[/yellow]")
        return

    table = Table(box=box.ROUNDED, border_style="magenta", header_style="bold magenta")
    table.add_column("ID",      width=4,  justify="center")
    table.add_column("Ticker",  width=8)
    table.add_column("Qty",     width=6,  justify="right")
    table.add_column("Entrada", width=10, justify="right")
    table.add_column("Stop-Loss", width=14, justify="right")
    table.add_column("Take-Profit", width=14, justify="right")
    table.add_column("Modo",    width=10)
    table.add_column("Estado",  width=14)

    for g in guards:
        sl_str = (
            f"[red]${g.stop_loss:,.2f}[/red]"
            + (f" [dim](-{g.sl_pct:.1f}%)[/dim]" if g.sl_pct else "")
            if g.stop_loss else "[dim]—[/dim]"
        )
        tp_str = (
            f"[green]${g.take_profit:,.2f}[/green]"
            + (f" [dim](+{g.tp_pct:.1f}%)[/dim]" if g.tp_pct else "")
            if g.take_profit else "[dim]—[/dim]"
        )
        mode_str = "[cyan]nativo[/cyan]" if g.mode == "native" else "[yellow]software[/yellow]"

        table.add_row(
            str(g.id),
            g.symbol,
            g.qty,
            f"${g.entry_price:,.2f}",
            sl_str,
            tp_str,
            mode_str,
            _fmt_status(g.status),
        )

    activos = sum(1 for g in guards if g.status == "active")
    console.print(Panel(
        table,
        title=f"[bold magenta]🛡️  Stop-Loss / Take-Profit  [dim]({activos} activos)[/dim][/bold magenta]",
        border_style="magenta",
    ))


def add_sltp_ui(sltp_manager: SLTPManager, api: tradeapi.REST):
    """Fluxo interactivo para configurar SL/TP numa posição."""
    console.print(Rule("[bold magenta]🛡️  Novo Stop-Loss / Take-Profit[/bold magenta]"))

    # mostra posições abertas para contexto
    try:
        positions = api.list_positions()
    except Exception:
        positions = []

    if positions:
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
        table.add_column("Ticker", width=8)
        table.add_column("Qty",    width=8, justify="right")
        table.add_column("Entrada", width=12, justify="right")
        table.add_column("Actual",  width=12, justify="right")
        table.add_column("P&L %",   width=10, justify="right")
        for p in positions:
            pl_pct = float(p.unrealized_plpc) * 100
            table.add_row(
                p.symbol, p.qty,
                f"${float(p.avg_entry_price):,.2f}",
                f"${float(p.current_price):,.2f}",
                fmt_pct(pl_pct),
            )
        console.print(Panel(table, title="Posições abertas", border_style="dim"))
    else:
        console.print("[yellow]Sem posições abertas. Podes ainda configurar um SL/TP para uma ordem futura.[/yellow]")

    # inputs
    symbol = Prompt.ask("  Ticker").upper().strip()

    # preenche entrada automaticamente se houver posição
    entry_default = ""
    pos_match = next((p for p in positions if p.symbol == symbol), None)
    if pos_match:
        entry_default = str(round(float(pos_match.avg_entry_price), 2))
        qty_default   = pos_match.qty
        side_default  = "sell" if float(pos_match.qty) > 0 else "buy"
    else:
        qty_default  = "1"
        side_default = "sell"

    entry_price = float(Prompt.ask("  Preço de entrada ($)", default=entry_default or "0"))
    qty         = Prompt.ask("  Quantidade", default=qty_default)
    side        = Prompt.ask("  Lado de fecho", choices=["sell", "buy"], default=side_default)

    # SL
    use_sl = Confirm.ask("  Configurar Stop-Loss?", default=True)
    sl_price = sl_pct = None
    if use_sl:
        sl_mode = Prompt.ask("  Definir SL por", choices=["percentagem", "preço"], default="percentagem")
        if sl_mode == "percentagem":
            sl_pct   = float(Prompt.ask("  SL % abaixo da entrada", default="2.0"))
            sl_price = SLTPManager.calc_sl(entry_price, sl_pct, side)
            console.print(f"  → Stop-Loss: [red]${sl_price:,.2f}[/red]  [dim](-{sl_pct}%)[/dim]")
        else:
            sl_price = float(Prompt.ask("  Preço absoluto de SL ($)"))

    # TP
    use_tp = Confirm.ask("  Configurar Take-Profit?", default=True)
    tp_price = tp_pct = None
    if use_tp:
        tp_mode = Prompt.ask("  Definir TP por", choices=["percentagem", "preço"], default="percentagem")
        if tp_mode == "percentagem":
            tp_pct   = float(Prompt.ask("  TP % acima da entrada", default="4.0"))
            tp_price = SLTPManager.calc_tp(entry_price, tp_pct, side)
            console.print(f"  → Take-Profit: [green]${tp_price:,.2f}[/green]  [dim](+{tp_pct}%)[/dim]")
        else:
            tp_price = float(Prompt.ask("  Preço absoluto de TP ($)"))

    if not sl_price and not tp_price:
        console.print("[yellow]Nenhum SL nem TP definido. Operação cancelada.[/yellow]")
        return

    # risco/recompensa
    if sl_price and tp_price and entry_price:
        risk   = abs(entry_price - sl_price)
        reward = abs(tp_price - entry_price)
        rr     = reward / risk if risk else 0
        color  = "green" if rr >= 2 else "yellow" if rr >= 1 else "red"
        console.print(
            f"\n  📐 Risk/Reward: [{color}]{rr:.1f}R[/{color}]  "
            f"[dim](Risco ${risk:,.2f}  →  Recompensa ${reward:,.2f})[/dim]"
        )

    prefer_native = Confirm.ask("  Usar ordens nativas da Alpaca? (recomendado)", default=True)

    console.print()
    if not Confirm.ask("  Confirmas a proteção?"):
        console.print("[dim]Cancelado.[/dim]")
        return

    guard = sltp_manager.add(
        symbol=symbol,
        qty=qty,
        side=side,
        entry_price=entry_price,
        stop_loss=sl_price,
        take_profit=tp_price,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        prefer_native=prefer_native,
    )

    console.print(
        f"\n[green]✅ Proteção #{guard.id} activada![/green]  "
        f"Modo: [cyan]{guard.mode}[/cyan]"
        + (f"  IDs Alpaca: {', '.join(guard.order_ids)}" if guard.order_ids else "")
    )


def sltp_menu(sltp_manager: SLTPManager, api: tradeapi.REST):
    """Submenu de gestão SL/TP."""
    while True:
        console.print(Rule("[bold magenta]🛡️  Stop-Loss / Take-Profit[/bold magenta]"))
        console.print(
            "  [bold cyan]1[/bold cyan] Ver proteções activas\n"
            "  [bold cyan]2[/bold cyan] Nova proteção SL/TP\n"
            "  [bold cyan]3[/bold cyan] Cancelar proteção\n"
            "  [bold cyan]4[/bold cyan] Limpar encerradas\n"
            "  [bold cyan]0[/bold cyan] Voltar\n"
        )
        op = Prompt.ask("  Opção", default="0").strip()

        if op == "0":
            break
        elif op == "1":
            show_sltp(sltp_manager)
        elif op == "2":
            add_sltp_ui(sltp_manager, api)
        elif op == "3":
            show_sltp(sltp_manager)
            guards = sltp_manager.list_guards()
            if not any(g.status == "active" for g in guards):
                console.print("[yellow]Sem proteções activas para cancelar.[/yellow]")
            else:
                gid = Prompt.ask("  ID da proteção a cancelar").strip()
                try:
                    if sltp_manager.cancel(int(gid)):
                        console.print(f"[green]✅ Proteção #{gid} cancelada.[/green]")
                    else:
                        console.print(f"[yellow]Proteção #{gid} não encontrada ou já inactiva.[/yellow]")
                except ValueError:
                    console.print("[red]ID inválido.[/red]")
        elif op == "4":
            sltp_manager.clear_closed()
            console.print("[green]✅ Proteções encerradas removidas.[/green]")

        console.print()
        input("  ↩  Prima Enter para continuar…")


# ══════════════════════════════════════════════════════════════
#  MÓDULO: WATCHLIST (ticker tape ao vivo)
# ══════════════════════════════════════════════════════════════

# Tickers pré-definidos por categoria (editável pelo utilizador)
DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "SPY", "QQQ", "BTC/USD"]

@dataclass
class TickerSnap:
    """Snapshot de um ticker num dado instante."""
    symbol:  str
    open:    float = 0.0
    high:    float = 0.0
    low:     float = 0.0
    close:   float = 0.0
    prev:    float = 0.0   # fecho anterior (para calcular variação do dia)
    volume:  int   = 0
    updated: str   = ""
    error:   bool  = False


class Watchlist:
    """
    Mantém uma lista de tickers e actualiza os preços em background.
    Expõe os dados para o Live display do Rich.
    """

    def __init__(self, api: tradeapi.REST, symbols: List[str], interval: int = 20):
        self.api      = api
        self.interval = interval
        self._lock    = threading.Lock()
        self._stop    = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._snaps: dict[str, TickerSnap] = {s.upper(): TickerSnap(symbol=s.upper()) for s in symbols}

    # ── gestão de símbolos ────────────────────────────────────

    def add(self, symbol: str):
        s = symbol.upper()
        with self._lock:
            if s not in self._snaps:
                self._snaps[s] = TickerSnap(symbol=s)

    def remove(self, symbol: str):
        with self._lock:
            self._snaps.pop(symbol.upper(), None)

    def symbols(self) -> List[str]:
        with self._lock:
            return list(self._snaps.keys())

    def snaps(self) -> List[TickerSnap]:
        with self._lock:
            return list(self._snaps.values())

    # ── fetch de preços ───────────────────────────────────────

    def _fetch_one(self, symbol: str) -> TickerSnap:
        snap = TickerSnap(symbol=symbol)
        try:
            # barra de 1 minuto (preço actual)
            bars = self.api.get_bars(symbol, tradeapi.TimeFrame.Minute, limit=2).df
            if bars.empty:
                snap.error = True
                return snap
            last = bars.iloc[-1]
            snap.open   = float(last["open"])
            snap.high   = float(last["high"])
            snap.low    = float(last["low"])
            snap.close  = float(last["close"])
            snap.volume = int(last["volume"])

            # barra diária para calcular variação face ao dia anterior
            daily = self.api.get_bars(symbol, tradeapi.TimeFrame.Day, limit=2).df
            if len(daily) >= 2:
                snap.prev = float(daily.iloc[-2]["close"])
            elif len(daily) == 1:
                snap.prev = float(daily.iloc[0]["open"])

            snap.updated = datetime.now().strftime("%H:%M:%S")
        except Exception:
            snap.error = True
        return snap

    def _refresh(self):
        syms = self.symbols()
        for sym in syms:
            snap = self._fetch_one(sym)
            with self._lock:
                self._snaps[sym] = snap

    # ── thread ────────────────────────────────────────────────

    def _run(self):
        self._refresh()          # primeira actualização imediata
        while not self._stop.is_set():
            self._stop.wait(self.interval)
            if not self._stop.is_set():
                self._refresh()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="WatchlistFeed")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def force_refresh(self):
        """Actualização manual imediata (bloqueante)."""
        self._refresh()


# ── helpers de formatação ─────────────────────────────────────

def _chg_color(chg_pct: float) -> str:
    if chg_pct > 0:
        return "green"
    if chg_pct < 0:
        return "red"
    return "dim"

def _arrow(chg_pct: float) -> str:
    if chg_pct > 1:   return "▲"
    if chg_pct > 0:   return "↑"
    if chg_pct < -1:  return "▼"
    if chg_pct < 0:   return "↓"
    return "─"

def _build_watchlist_table(wl: Watchlist) -> Table:
    """Constrói a tabela Rich com os dados actuais."""
    table = Table(
        box=box.SIMPLE_HEAD,
        border_style="cyan",
        header_style="bold cyan",
        show_edge=True,
        padding=(0, 1),
    )
    table.add_column("  Ticker",  width=10, style="bold")
    table.add_column("Preço",     width=12, justify="right")
    table.add_column("Var $",     width=10, justify="right")
    table.add_column("Var %",     width=9,  justify="right")
    table.add_column("Abertura",  width=10, justify="right")
    table.add_column("Máx",       width=10, justify="right")
    table.add_column("Mín",       width=10, justify="right")
    table.add_column("Volume",    width=12, justify="right")
    table.add_column("Actualiz.", width=10, justify="right")

    for snap in wl.snaps():
        if snap.error or snap.close == 0:
            table.add_row(
                snap.symbol, "[dim]—[/dim]", "[dim]—[/dim]", "[dim]—[/dim]",
                "[dim]—[/dim]", "[dim]—[/dim]", "[dim]—[/dim]",
                "[dim]—[/dim]", "[dim]a carregar…[/dim]",
            )
            continue

        chg_abs = snap.close - snap.prev if snap.prev else 0.0
        chg_pct = (chg_abs / snap.prev * 100) if snap.prev else 0.0
        color   = _chg_color(chg_pct)
        arrow   = _arrow(chg_pct)
        sign    = "+" if chg_abs >= 0 else ""

        table.add_row(
            f"  {snap.symbol}",
            f"[bold {color}]${snap.close:,.2f}[/bold {color}]",
            f"[{color}]{sign}{chg_abs:+.2f}[/{color}]",
            f"[{color}]{arrow} {sign}{chg_pct:.2f}%[/{color}]",
            f"${snap.open:,.2f}",
            f"[green]${snap.high:,.2f}[/green]",
            f"[red]${snap.low:,.2f}[/red]",
            f"{snap.volume:,}",
            f"[dim]{snap.updated}[/dim]",
        )

    return table


# ── UI da Watchlist ───────────────────────────────────────────

def watchlist_live(wl: Watchlist):
    """
    Mostra a watchlist em modo Live (actualiza em tempo real).
    Prima 'q' + Enter ou Ctrl-C para sair.
    """
    console.print(
        f"[dim]  A actualizar cada {wl.interval}s · Prima [bold]Ctrl-C[/bold] ou escreve [bold]q[/bold] + Enter para sair[/dim]\n"
    )

    stop_live = threading.Event()

    def _input_listener():
        while not stop_live.is_set():
            try:
                v = input()
                if v.strip().lower() == "q":
                    stop_live.set()
            except EOFError:
                stop_live.set()

    listener = threading.Thread(target=_input_listener, daemon=True)
    listener.start()

    try:
        with Live(console=console, refresh_per_second=1, screen=False) as live:
            while not stop_live.is_set():
                now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
                table = _build_watchlist_table(wl)
                panel = Panel(
                    table,
                    title=f"[bold cyan]📡 Watchlist  [dim]{now}[/dim][/bold cyan]",
                    border_style="cyan",
                    subtitle=f"[dim]{len(wl.symbols())} tickers · intervalo {wl.interval}s[/dim]",
                )
                live.update(panel)
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_live.set()


def watchlist_menu(wl: Watchlist):
    """Submenu de gestão da Watchlist."""
    while True:
        console.print(Rule("[bold cyan]📡 Watchlist[/bold cyan]"))
        syms = wl.symbols()
        console.print(
            f"  [dim]Tickers actuais:[/dim] "
            + ("  ".join(f"[bold]{s}[/bold]" for s in syms) if syms else "[dim]nenhum[/dim]")
        )
        console.print()
        console.print(
            "  [bold cyan]1[/bold cyan] Ver watchlist ao vivo\n"
            "  [bold cyan]2[/bold cyan] Adicionar ticker\n"
            "  [bold cyan]3[/bold cyan] Remover ticker\n"
            "  [bold cyan]4[/bold cyan] Actualizar agora\n"
            "  [bold cyan]0[/bold cyan] Voltar\n"
        )
        op = Prompt.ask("  Opção", default="0").strip()

        if op == "0":
            break

        elif op == "1":
            console.clear()
            banner()
            watchlist_live(wl)

        elif op == "2":
            raw = Prompt.ask("  Ticker(s) a adicionar [dim](separa por vírgula)[/dim]")
            added = []
            for s in raw.split(","):
                s = s.strip().upper()
                if s:
                    wl.add(s)
                    added.append(s)
            if added:
                console.print(f"[green]✅ Adicionado(s): {', '.join(added)}[/green]")
                console.print("[dim]  A actualizar preços…[/dim]")
                threading.Thread(target=wl.force_refresh, daemon=True).start()

        elif op == "3":
            if not syms:
                console.print("[yellow]Watchlist vazia.[/yellow]")
            else:
                raw = Prompt.ask("  Ticker(s) a remover [dim](separa por vírgula)[/dim]")
                removed = []
                for s in raw.split(","):
                    s = s.strip().upper()
                    if s in wl.symbols():
                        wl.remove(s)
                        removed.append(s)
                if removed:
                    console.print(f"[green]✅ Removido(s): {', '.join(removed)}[/green]")
                else:
                    console.print("[yellow]Nenhum ticker encontrado na lista.[/yellow]")

        elif op == "4":
            with console.status("[cyan]A actualizar preços…[/cyan]"):
                wl.force_refresh()
            console.print("[green]✅ Preços actualizados.[/green]")

        console.print()
        input("  ↩  Prima Enter para continuar…")


# ══════════════════════════════════════════════════════════════
#  MENU PRINCIPAL
# ══════════════════════════════════════════════════════════════

MENU_OPTIONS = {
    "1":  ("💰 Resumo da Conta",           "account"),
    "2":  ("📂 Posições Abertas",          "positions"),
    "3":  ("📡 Watchlist ao Vivo",         "watchlist"),
    "4":  ("📋 Ordens Pendentes",          "orders"),
    "5":  ("➕ Nova Ordem",                "place"),
    "6":  ("❌ Cancelar Ordem",            "cancel"),
    "7":  ("📉 Cotação Rápida",            "quote"),
    "8":  ("📜 Histórico de Trades",       "history"),
    "9":  ("🔔 Alertas de Preço",          "alerts"),
    "10": ("🛡️  Stop-Loss / Take-Profit",  "sltp"),
    "11": ("🤖 Assistente IA",             "ai"),
    "0":  ("🚪 Sair",                      "exit"),
}

def print_menu():
    table = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0, 2))
    table.add_column("Opção", style="bold cyan", width=4)
    table.add_column("Acção")
    for key, (label, _) in MENU_OPTIONS.items():
        table.add_row(key, label)
    console.print(table)


def main():
    console.clear()
    banner()

    # Inicializar clientes
    api       = get_alpaca_client()
    ai_client = get_anthropic_client()

    if api is None:
        console.print("[red]Não foi possível ligar ao Alpaca. Verifica o .env e tenta novamente.[/red]")
        sys.exit(1)

    console.print(f"[green]✅ Ligação ao Alpaca estabelecida[/green]  [dim]({'Paper' if PAPER_MODE else 'Live'})[/dim]")
    if ai_client:
        console.print("[green]✅ Assistente IA (Claude) activo[/green]")

    # Iniciar gestor de alertas em background (verifica a cada 30s)
    alert_manager = AlertManager(api, interval=30)
    alert_manager.start()
    console.print("[green]✅ Monitor de alertas activo[/green]  [dim](intervalo: 30s)[/dim]")

    # Iniciar gestor SL/TP em background (verifica a cada 15s)
    sltp_manager = SLTPManager(api, interval=15)
    sltp_manager.start()
    console.print("[green]✅ Monitor SL/TP activo[/green]  [dim](intervalo: 15s)[/dim]")

    # Iniciar watchlist em background (actualiza a cada 20s)
    watchlist = Watchlist(api, DEFAULT_WATCHLIST, interval=20)
    watchlist.start()
    console.print("[green]✅ Watchlist activa[/green]  [dim](intervalo: 20s · 10 tickers)[/dim]")
    console.print()

    while True:
        print_menu()
        choice = Prompt.ask("  Escolhe uma opção", default="1").strip()

        if choice not in MENU_OPTIONS:
            console.print("[yellow]Opção inválida.[/yellow]")
            continue

        _, action = MENU_OPTIONS[choice]
        console.print()

        if action == "exit":
            alert_manager.stop()
            sltp_manager.stop()
            watchlist.stop()
            console.print("[dim]Até logo! 👋[/dim]")
            break
        elif action == "account":
            show_account(api)
        elif action == "positions":
            show_positions(api)
        elif action == "watchlist":
            watchlist_menu(watchlist)
        elif action == "orders":
            show_open_orders(api)
        elif action == "place":
            place_order(api)
        elif action == "cancel":
            cancel_order(api)
        elif action == "quote":
            get_quote(api)
        elif action == "history":
            show_history(api)
        elif action == "alerts":
            alerts_menu(alert_manager)
        elif action == "sltp":
            sltp_menu(sltp_manager, api)
        elif action == "ai":
            if ai_client:
                ai_assistant(ai_client, api)
            else:
                console.print("[yellow]Assistente IA não disponível. Configura ANTHROPIC_API_KEY no .env[/yellow]")

        console.print()
        input("  ↩  Prima Enter para continuar…")
        console.clear()
        banner()


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
