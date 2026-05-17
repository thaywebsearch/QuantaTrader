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
#  MENU PRINCIPAL
# ══════════════════════════════════════════════════════════════

MENU_OPTIONS = {
    "1": ("💰 Resumo da Conta",      "account"),
    "2": ("📂 Posições Abertas",     "positions"),
    "3": ("📋 Ordens Pendentes",     "orders"),
    "4": ("➕ Nova Ordem",           "place"),
    "5": ("❌ Cancelar Ordem",       "cancel"),
    "6": ("📉 Cotação Rápida",       "quote"),
    "7": ("📜 Histórico de Trades",  "history"),
    "8": ("🔔 Alertas de Preço",     "alerts"),
    "9": ("🤖 Assistente IA",        "ai"),
    "0": ("🚪 Sair",                 "exit"),
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
            console.print("[dim]Até logo! 👋[/dim]")
            break
        elif action == "account":
            show_account(api)
        elif action == "positions":
            show_positions(api)
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
