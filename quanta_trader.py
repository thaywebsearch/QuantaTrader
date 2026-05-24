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
  pip install alpaca-trade-api anthropic rich prompt_toolkit requests python-dotenv pandas numpy

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
#  MÓDULO: INDICADORES TÉCNICOS
#  Implementados em pandas puro — sem ta-lib nem pandas-ta
#  Indicadores: SMA, EMA, RSI, MACD, Bollinger Bands
# ══════════════════════════════════════════════════════════════

try:
    import pandas as pd
    import numpy as np
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False


# ── cálculo dos indicadores ───────────────────────────────────

def _sma(series: "pd.Series", period: int) -> "pd.Series":
    return series.rolling(window=period).mean()

def _ema(series: "pd.Series", period: int) -> "pd.Series":
    return series.ewm(span=period, adjust=False).mean()

def _rsi(series: "pd.Series", period: int = 14) -> "pd.Series":
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))

def _macd(series: "pd.Series", fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast   = _ema(series, fast)
    ema_slow   = _ema(series, slow)
    macd_line  = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram

def _bollinger(series: "pd.Series", period: int = 20, std_dev: float = 2.0):
    mid   = _sma(series, period)
    std   = series.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower

def _fetch_ohlcv(api: tradeapi.REST, symbol: str, timeframe, limit: int) -> "Optional[pd.DataFrame]":
    """Obtém dados OHLCV da Alpaca e devolve DataFrame com coluna 'close'."""
    try:
        bars = api.get_bars(symbol, timeframe, limit=limit).df
        if bars.empty:
            return None
        bars.index = pd.to_datetime(bars.index)
        return bars
    except Exception as e:
        console.print(f"  [red]Erro ao obter dados: {e}[/red]")
        return None


# ── display helpers ───────────────────────────────────────────

def _rsi_color(v: float) -> str:
    if v >= 70:  return "red"
    if v <= 30:  return "green"
    return "yellow"

def _rsi_label(v: float) -> str:
    if v >= 70:  return "Sobrecomprado ⚠️"
    if v <= 30:  return "Sobrevendido  ✅"
    return "Neutro"

def _macd_signal(macd: float, sig: float) -> str:
    if macd > sig:  return "[green]Alta (MACD > Signal)[/green]"
    if macd < sig:  return "[red]Baixa (MACD < Signal)[/red]"
    return "[yellow]Cruzamento[/yellow]"

def _bb_position(price: float, upper: float, lower: float, mid: float) -> str:
    width = upper - lower
    if width == 0:
        return "—"
    pct = (price - lower) / width * 100
    if price >= upper:  return f"[red]Acima da banda superior ({pct:.0f}%)[/red]"
    if price <= lower:  return f"[green]Abaixo da banda inferior ({pct:.0f}%)[/green]"
    if pct > 60:        return f"[yellow]Zona alta ({pct:.0f}%)[/yellow]"
    if pct < 40:        return f"[yellow]Zona baixa ({pct:.0f}%)[/yellow]"
    return f"[dim]Zona central ({pct:.0f}%)[/dim]"


# ── display de cada indicador ─────────────────────────────────

def _show_sma_ema(close: "pd.Series", current: float):
    table = Table(box=box.SIMPLE_HEAD, header_style="bold dim", show_edge=False)
    table.add_column("Período", width=10)
    table.add_column("SMA",     width=12, justify="right")
    table.add_column("EMA",     width=12, justify="right")
    table.add_column("Preço vs SMA", width=18, justify="right")

    for p in [9, 20, 50, 200]:
        if len(close) < p:
            continue
        sma = _sma(close, p).iloc[-1]
        ema = _ema(close, p).iloc[-1]
        diff_pct = (current - sma) / sma * 100
        diff_col = "green" if diff_pct >= 0 else "red"
        sign     = "+" if diff_pct >= 0 else ""
        table.add_row(
            f"  {p}",
            f"${sma:,.2f}",
            f"${ema:,.2f}",
            f"[{diff_col}]{sign}{diff_pct:.2f}%[/{diff_col}]",
        )

    console.print(Panel(table, title="[bold]📈 Médias Móveis (SMA / EMA)[/bold]", border_style="blue"))


def _show_rsi(close: "pd.Series", period: int = 14):
    rsi_series = _rsi(close, period)
    val = rsi_series.iloc[-1]
    color = _rsi_color(val)
    label = _rsi_label(val)

    # mini gráfico de barras dos últimos 14 valores
    recent = rsi_series.dropna().tail(14).values
    bar_chars = "▁▂▃▄▅▆▇█"
    mini = ""
    if len(recent) > 0:
        mn, mx = min(recent), max(recent)
        span   = mx - mn if mx != mn else 1
        for v in recent:
            idx  = int((v - mn) / span * 7)
            c    = "green" if v <= 30 else "red" if v >= 70 else "yellow"
            mini += f"[{c}]{bar_chars[idx]}[/{c}]"

    console.print(Panel(
        f"  RSI({period}):  [{color}][bold]{val:.1f}[/bold][/{color}]   {label}\n\n"
        f"  Escala:  [green]≤30 Sobrevendido[/green]  ·  [yellow]30–70 Neutro[/yellow]  ·  [red]≥70 Sobrecomprado[/red]\n\n"
        f"  Últimos 14:  {mini}",
        title="[bold]📊 RSI — Relative Strength Index[/bold]",
        border_style="yellow",
    ))


def _show_macd(close: "pd.Series", fast=12, slow=26, signal=9):
    macd_line, sig_line, hist = _macd(close, fast, slow, signal)
    m  = macd_line.iloc[-1]
    s  = sig_line.iloc[-1]
    h  = hist.iloc[-1]
    h_color = "green" if h >= 0 else "red"
    sign    = "+" if h >= 0 else ""

    # mini histograma
    recent_h = hist.dropna().tail(12).values
    bar_chars = "▁▂▃▄▅▆▇█"
    mini = ""
    if len(recent_h) > 0:
        mx = max(abs(v) for v in recent_h) or 1
        for v in recent_h:
            idx = int(abs(v) / mx * 7)
            c   = "green" if v >= 0 else "red"
            mini += f"[{c}]{bar_chars[idx]}[/{c}]"

    console.print(Panel(
        f"  MACD Line :  [cyan]{m:+.4f}[/cyan]\n"
        f"  Signal    :  [magenta]{s:+.4f}[/magenta]\n"
        f"  Histograma:  [{h_color}]{sign}{h:.4f}[/{h_color}]\n\n"
        f"  Sinal     :  {_macd_signal(m, s)}\n\n"
        f"  Histograma (12 barras):  {mini}",
        title=f"[bold]📉 MACD ({fast},{slow},{signal})[/bold]",
        border_style="magenta",
    ))


def _show_bollinger(close: "pd.Series", current: float, period=20, std_dev=2.0):
    upper_s, mid_s, lower_s = _bollinger(close, period, std_dev)
    upper = upper_s.iloc[-1]
    mid   = mid_s.iloc[-1]
    lower = lower_s.iloc[-1]
    width_pct = (upper - lower) / mid * 100 if mid else 0

    pos = _bb_position(current, upper, lower, mid)

    console.print(Panel(
        f"  Banda Superior:  [red]${upper:,.2f}[/red]\n"
        f"  Banda Média  :  [cyan]${mid:,.2f}[/cyan]  [dim](SMA {period})[/dim]\n"
        f"  Banda Inferior:  [green]${lower:,.2f}[/green]\n\n"
        f"  Largura      :  {width_pct:.1f}%  [dim](volatilidade)[/dim]\n"
        f"  Preço actual :  [bold]${current:,.2f}[/bold]  →  {pos}",
        title=f"[bold]🎯 Bollinger Bands ({period}, {std_dev}σ)[/bold]",
        border_style="red",
    ))


# ── menu de indicadores técnicos ──────────────────────────────

TIMEFRAME_MAP = {
    "1m":  (tradeapi.TimeFrame.Minute,  200),
    "5m":  (tradeapi.TimeFrame.Minute,  200),   # Alpaca não tem 5m nativo; usa 1m e reamostras
    "1h":  (tradeapi.TimeFrame.Hour,    300),
    "1d":  (tradeapi.TimeFrame.Day,     300),
}

def technical_analysis(api: tradeapi.REST):
    """Fluxo completo de análise técnica para um símbolo."""
    if not _PANDAS_OK:
        console.print(
            "[red]❌  pandas e numpy são necessários para os indicadores técnicos.[/red]\n"
            "  Instala com:  [bold]pip install pandas numpy[/bold]"
        )
        return

    console.print(Rule("[bold green]📊 Análise Técnica[/bold green]"))

    symbol = Prompt.ask("  Ticker (ex: AAPL, TSLA, BTC/USD)").upper().strip()
    tf_key = Prompt.ask("  Timeframe", choices=["1m", "1h", "1d"], default="1d")

    tf, limit = TIMEFRAME_MAP[tf_key]

    with console.status(f"[cyan]A descarregar {limit} barras de {symbol} ({tf_key})…[/cyan]"):
        df = _fetch_ohlcv(api, symbol, tf, limit)

    if df is None or df.empty:
        console.print(f"[red]Sem dados para {symbol}.[/red]")
        return

    close   = df["close"]
    current = float(close.iloc[-1])
    n_bars  = len(close)

    console.print(
        f"\n  [bold]{symbol}[/bold]  ·  Preço actual: [bold cyan]${current:,.2f}[/bold cyan]  "
        f"·  {n_bars} barras ({tf_key})  "
        f"·  {str(df.index[0])[:16]} → {str(df.index[-1])[:16]}\n"
    )

    # escolha de indicadores
    console.print(
        "  [bold cyan]1[/bold cyan] Todos os indicadores\n"
        "  [bold cyan]2[/bold cyan] Médias Móveis (SMA / EMA)\n"
        "  [bold cyan]3[/bold cyan] RSI\n"
        "  [bold cyan]4[/bold cyan] MACD\n"
        "  [bold cyan]5[/bold cyan] Bollinger Bands\n"
    )
    choice = Prompt.ask("  Indicadores", choices=["1","2","3","4","5"], default="1")

    console.print()

    if choice in ("1", "2"):
        _show_sma_ema(close, current)
        console.print()

    if choice in ("1", "3"):
        period = int(Prompt.ask("  Período RSI", default="14")) if choice == "3" else 14
        _show_rsi(close, period)
        console.print()

    if choice in ("1", "4"):
        _show_macd(close)
        console.print()

    if choice in ("1", "5"):
        _show_bollinger(close, current)
        console.print()

    # resumo de sinais
    if choice == "1":
        _show_signal_summary(close, current)


def _show_signal_summary(close: "pd.Series", current: float):
    """Tabela de resumo de sinais — Comprar / Neutro / Vender."""
    signals = []

    # SMA 50
    if len(close) >= 50:
        sma50 = _sma(close, 50).iloc[-1]
        signals.append(("SMA 50",
            "COMPRAR" if current > sma50 else "VENDER",
            f"Preço {'acima' if current > sma50 else 'abaixo'} da SMA50 (${sma50:,.2f})"
        ))

    # SMA 200
    if len(close) >= 200:
        sma200 = _sma(close, 200).iloc[-1]
        signals.append(("SMA 200",
            "COMPRAR" if current > sma200 else "VENDER",
            f"Preço {'acima' if current > sma200 else 'abaixo'} da SMA200 (${sma200:,.2f})"
        ))

    # RSI
    if len(close) >= 14:
        rsi_val = _rsi(close, 14).iloc[-1]
        if rsi_val >= 70:
            signals.append(("RSI(14)", "VENDER",  f"Sobrecomprado: {rsi_val:.1f}"))
        elif rsi_val <= 30:
            signals.append(("RSI(14)", "COMPRAR", f"Sobrevendido: {rsi_val:.1f}"))
        else:
            signals.append(("RSI(14)", "NEUTRO",  f"Neutro: {rsi_val:.1f}"))

    # MACD
    if len(close) >= 35:
        ml, sl, _ = _macd(close)
        m, s = ml.iloc[-1], sl.iloc[-1]
        signals.append(("MACD",
            "COMPRAR" if m > s else "VENDER",
            f"MACD {'>' if m > s else '<'} Signal ({m:+.4f} vs {s:+.4f})"
        ))

    # Bollinger
    if len(close) >= 20:
        u, _, l = _bollinger(close)
        if current >= u.iloc[-1]:
            signals.append(("Bollinger", "VENDER",  f"Preço acima da banda superior (${u.iloc[-1]:,.2f})"))
        elif current <= l.iloc[-1]:
            signals.append(("Bollinger", "COMPRAR", f"Preço abaixo da banda inferior (${l.iloc[-1]:,.2f})"))
        else:
            signals.append(("Bollinger", "NEUTRO",  "Dentro das bandas"))

    if not signals:
        return

    # contagem
    buys   = sum(1 for _, s, _ in signals if s == "COMPRAR")
    sells  = sum(1 for _, s, _ in signals if s == "VENDER")
    neutro = sum(1 for _, s, _ in signals if s == "NEUTRO")

    table = Table(box=box.SIMPLE_HEAD, header_style="bold dim", show_edge=False)
    table.add_column("Indicador", width=12)
    table.add_column("Sinal",     width=12, justify="center")
    table.add_column("Razão",     width=42)

    for name, sig, reason in signals:
        if sig == "COMPRAR":
            sig_fmt = "[bold green]▲ COMPRAR[/bold green]"
        elif sig == "VENDER":
            sig_fmt = "[bold red]▼ VENDER[/bold red]"
        else:
            sig_fmt = "[yellow]─ NEUTRO[/yellow]"
        table.add_row(f"  {name}", sig_fmt, f"[dim]{reason}[/dim]")

    if buys > sells:
        overall = f"[bold green]▲ TENDÊNCIA COMPRADORA  ({buys} comprar · {sells} vender · {neutro} neutro)[/bold green]"
    elif sells > buys:
        overall = f"[bold red]▼ TENDÊNCIA VENDEDORA  ({buys} comprar · {sells} vender · {neutro} neutro)[/bold red]"
    else:
        overall = f"[yellow]─ SINAL MISTO  ({buys} comprar · {sells} vender · {neutro} neutro)[/yellow]"

    console.print(Panel(
        table,
        title="[bold]🧭 Resumo de Sinais[/bold]",
        subtitle=overall,
        border_style="dim",
    ))
    console.print("\n  [dim italic]⚠️  Indicadores técnicos são ferramentas de apoio à decisão, não garantias.[/dim italic]")


# ══════════════════════════════════════════════════════════════
#  MÓDULO: BACKTESTING SIMPLES
#
#  Estratégias disponíveis:
#    1. SMA Crossover      — cruza SMA rápida com SMA lenta
#    2. EMA Crossover      — cruza EMA rápida com EMA lenta
#    3. RSI Mean-Reversion — compra em sobrevenda, vende em sobrecompra
#    4. MACD Crossover     — cruza MACD com Signal line
#    5. Bollinger Reversion— compra abaixo da banda inf., vende acima da sup.
#
#  Métricas calculadas:
#    Total Return, Buy & Hold, CAGR, Sharpe Ratio, Max Drawdown,
#    Win Rate, Profit Factor, nº trades, duração média
# ══════════════════════════════════════════════════════════════

@dataclass
class Trade:
    entry_date:  str
    exit_date:   str
    entry_price: float
    exit_price:  float
    direction:   str   # "long" | "short"
    pnl:         float
    pnl_pct:     float
    bars_held:   int


@dataclass
class BacktestResult:
    strategy:       str
    symbol:         str
    timeframe:      str
    start_date:     str
    end_date:       str
    n_bars:         int
    initial_capital: float
    final_capital:  float
    total_return:   float   # %
    bh_return:      float   # % buy & hold
    cagr:           float   # % anualizado
    sharpe:         float
    max_drawdown:   float   # %
    win_rate:       float   # %
    profit_factor:  float
    n_trades:       int
    avg_bars:       float
    trades:         List[Trade] = field(default_factory=list)


# ── motor de backtesting ──────────────────────────────────────

def _run_backtest(
    df:       "pd.DataFrame",
    signals:  "pd.Series",   # +1 = comprar, -1 = vender, 0 = nada
    capital:  float,
    symbol:   str,
    strategy: str,
    timeframe: str,
) -> BacktestResult:
    """
    Motor genérico de backtesting.
    `signals` é uma Series alinhada com df onde:
      +1 = abrir long (ou fechar short)
      -1 = fechar long (ou abrir short)
    Apenas long por simplicidade.
    """
    close      = df["close"].values
    dates      = [str(i)[:16] for i in df.index]
    position   = 0       # shares em carteira
    cash       = capital
    equity_curve: List[float] = []
    trades:       List[Trade] = []
    entry_price  = 0.0
    entry_idx    = 0

    sig_vals = signals.values

    for i in range(len(close)):
        price = close[i]

        # abrir posição
        if sig_vals[i] == 1 and position == 0:
            position    = cash / price
            entry_price = price
            entry_idx   = i
            cash        = 0.0

        # fechar posição
        elif sig_vals[i] == -1 and position > 0:
            proceeds = position * price
            pnl      = proceeds - (position * entry_price)
            pnl_pct  = (price - entry_price) / entry_price * 100
            trades.append(Trade(
                entry_date  = dates[entry_idx],
                exit_date   = dates[i],
                entry_price = entry_price,
                exit_price  = price,
                direction   = "long",
                pnl         = pnl,
                pnl_pct     = pnl_pct,
                bars_held   = i - entry_idx,
            ))
            cash     = proceeds
            position = 0.0

        # equity actual
        equity_curve.append(cash + position * price)

    # fechar posição aberta no final
    if position > 0:
        price    = close[-1]
        proceeds = position * price
        pnl      = proceeds - (position * entry_price)
        pnl_pct  = (price - entry_price) / entry_price * 100
        trades.append(Trade(
            entry_date  = dates[entry_idx],
            exit_date   = dates[-1],
            entry_price = entry_price,
            exit_price  = price,
            direction   = "long",
            pnl         = pnl,
            pnl_pct     = pnl_pct,
            bars_held   = len(close) - 1 - entry_idx,
        ))
        cash     = proceeds
        position = 0.0
        equity_curve[-1] = cash

    import numpy as np

    eq   = np.array(equity_curve) if equity_curve else np.array([capital])
    final = float(eq[-1])

    # métricas
    total_ret = (final - capital) / capital * 100
    bh_ret    = (close[-1] - close[0]) / close[0] * 100

    # CAGR — estima anos com base no timeframe
    tf_to_bars_per_year = {"1m": 252 * 390, "1h": 252 * 6.5, "1d": 252}
    bpy   = tf_to_bars_per_year.get(timeframe, 252)
    years = len(close) / bpy
    cagr  = ((final / capital) ** (1 / max(years, 0.01)) - 1) * 100 if final > 0 else -100.0

    # Sharpe (diário simplificado)
    rets  = np.diff(eq) / eq[:-1]
    sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(bpy)) if len(rets) > 1 and np.std(rets) > 0 else 0.0

    # Max Drawdown
    peak  = np.maximum.accumulate(eq)
    dd    = (eq - peak) / peak * 100
    max_dd = float(np.min(dd))

    # Win rate & profit factor
    winners = [t for t in trades if t.pnl > 0]
    losers  = [t for t in trades if t.pnl <= 0]
    win_rate = len(winners) / len(trades) * 100 if trades else 0.0
    gross_profit = sum(t.pnl for t in winners)
    gross_loss   = abs(sum(t.pnl for t in losers))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_bars = sum(t.bars_held for t in trades) / len(trades) if trades else 0.0

    return BacktestResult(
        strategy       = strategy,
        symbol         = symbol,
        timeframe      = timeframe,
        start_date     = dates[0],
        end_date       = dates[-1],
        n_bars         = len(close),
        initial_capital= capital,
        final_capital  = final,
        total_return   = total_ret,
        bh_return      = bh_ret,
        cagr           = cagr,
        sharpe         = sharpe,
        max_drawdown   = max_dd,
        win_rate       = win_rate,
        profit_factor  = pf,
        n_trades       = len(trades),
        avg_bars       = avg_bars,
        trades         = trades,
    )


# ── estratégias → signals ─────────────────────────────────────

def _strat_sma_cross(df: "pd.DataFrame", fast: int, slow: int) -> "pd.Series":
    import pandas as pd
    c  = df["close"]
    sf = _sma(c, fast)
    ss = _sma(c, slow)
    sig = pd.Series(0, index=df.index)
    cross_up   = (sf > ss) & (sf.shift(1) <= ss.shift(1))
    cross_down = (sf < ss) & (sf.shift(1) >= ss.shift(1))
    sig[cross_up]   =  1
    sig[cross_down] = -1
    return sig

def _strat_ema_cross(df: "pd.DataFrame", fast: int, slow: int) -> "pd.Series":
    import pandas as pd
    c  = df["close"]
    ef = _ema(c, fast)
    es = _ema(c, slow)
    sig = pd.Series(0, index=df.index)
    cross_up   = (ef > es) & (ef.shift(1) <= es.shift(1))
    cross_down = (ef < es) & (ef.shift(1) >= es.shift(1))
    sig[cross_up]   =  1
    sig[cross_down] = -1
    return sig

def _strat_rsi(df: "pd.DataFrame", period: int, oversold: float, overbought: float) -> "pd.Series":
    import pandas as pd
    rsi = _rsi(df["close"], period)
    sig = pd.Series(0, index=df.index)
    sig[rsi <= oversold]  =  1
    sig[rsi >= overbought] = -1
    return sig

def _strat_macd(df: "pd.DataFrame", fast: int, slow: int, signal: int) -> "pd.Series":
    import pandas as pd
    ml, sl, _ = _macd(df["close"], fast, slow, signal)
    sig = pd.Series(0, index=df.index)
    cross_up   = (ml > sl) & (ml.shift(1) <= sl.shift(1))
    cross_down = (ml < sl) & (ml.shift(1) >= sl.shift(1))
    sig[cross_up]   =  1
    sig[cross_down] = -1
    return sig

def _strat_bollinger(df: "pd.DataFrame", period: int, std_dev: float) -> "pd.Series":
    import pandas as pd
    c = df["close"]
    upper, _, lower = _bollinger(c, period, std_dev)
    sig = pd.Series(0, index=df.index)
    sig[c <= lower] =  1
    sig[c >= upper] = -1
    return sig


# ── display de resultados ─────────────────────────────────────

def _show_backtest_result(r: BacktestResult, show_trades: bool = False):
    """Painel de métricas do backtest."""

    ret_color = "green" if r.total_return >= 0 else "red"
    bh_color  = "green" if r.bh_return  >= 0 else "red"
    vs_bh     = r.total_return - r.bh_return
    vs_color  = "green" if vs_bh >= 0 else "red"
    sharpe_c  = "green" if r.sharpe >= 1 else "yellow" if r.sharpe >= 0 else "red"
    dd_color  = "green" if r.max_drawdown > -10 else "yellow" if r.max_drawdown > -20 else "red"
    pf_color  = "green" if r.profit_factor >= 1.5 else "yellow" if r.profit_factor >= 1 else "red"
    wr_color  = "green" if r.win_rate >= 55 else "yellow" if r.win_rate >= 45 else "red"

    # tabela de métricas
    mt = Table(box=box.SIMPLE, show_header=False, show_edge=False, padding=(0, 2))
    mt.add_column("Métrica",  style="bold dim", width=24)
    mt.add_column("Valor",    justify="right",  width=18)
    mt.add_column("Métrica2", style="bold dim", width=24)
    mt.add_column("Valor2",   justify="right",  width=18)

    rows = [
        ("Capital Inicial",   f"${r.initial_capital:,.2f}",
         "Capital Final",     f"[{ret_color}]${r.final_capital:,.2f}[/{ret_color}]"),
        ("Retorno Estratégia",f"[{ret_color}]{r.total_return:+.2f}%[/{ret_color}]",
         "Buy & Hold",        f"[{bh_color}]{r.bh_return:+.2f}%[/{bh_color}]"),
        ("Alpha vs B&H",      f"[{vs_color}]{vs_bh:+.2f}%[/{vs_color}]",
         "CAGR",              f"[{ret_color}]{r.cagr:+.2f}%[/{ret_color}]"),
        ("Sharpe Ratio",      f"[{sharpe_c}]{r.sharpe:.2f}[/{sharpe_c}]",
         "Max Drawdown",      f"[{dd_color}]{r.max_drawdown:.2f}%[/{dd_color}]"),
        ("Win Rate",          f"[{wr_color}]{r.win_rate:.1f}%[/{wr_color}]",
         "Profit Factor",     f"[{pf_color}]{r.profit_factor:.2f}[/{pf_color}]"),
        ("Nº Trades",         str(r.n_trades),
         "Duração Média",     f"{r.avg_bars:.0f} barras"),
        ("Período",           f"{r.start_date[:10]} → {r.end_date[:10]}",
         "Barras",            str(r.n_bars)),
    ]
    for r1, v1, r2, v2 in rows:
        mt.add_row(r1, v1, r2, v2)

    console.print(Panel(
        mt,
        title=f"[bold green]🧪 Backtest — {r.strategy}  ·  {r.symbol}  ·  {r.timeframe}[/bold green]",
        border_style="green",
    ))

    # avaliação qualitativa
    score = 0
    tips  = []
    if r.total_return > r.bh_return:   score += 1
    else:                              tips.append("[yellow]• Estratégia ficou abaixo do Buy & Hold.[/yellow]")
    if r.sharpe >= 1.0:                score += 1
    else:                              tips.append("[yellow]• Sharpe < 1.0 — risco/retorno fraco.[/yellow]")
    if r.max_drawdown > -20:           score += 1
    else:                              tips.append("[yellow]• Drawdown elevado — considera SL mais apertado.[/yellow]")
    if r.win_rate >= 50:               score += 1
    else:                              tips.append("[yellow]• Win rate < 50% — verifica os parâmetros.[/yellow]")
    if r.profit_factor >= 1.5:         score += 1
    else:                              tips.append("[yellow]• Profit factor < 1.5 — ganhos médios baixos.[/yellow]")

    stars   = "★" * score + "☆" * (5 - score)
    s_color = "green" if score >= 4 else "yellow" if score >= 2 else "red"
    console.print(f"  Avaliação: [{s_color}]{stars}[/{s_color}]  ({score}/5)")
    for tip in tips:
        console.print(f"  {tip}")

    # lista de trades (opcional)
    if show_trades and r.trades:
        console.print()
        tt = Table(box=box.SIMPLE_HEAD, header_style="bold dim", show_edge=False)
        tt.add_column("#",          width=4,  justify="right")
        tt.add_column("Entrada",    width=14)
        tt.add_column("Saída",      width=14)
        tt.add_column("P. Entrada", width=12, justify="right")
        tt.add_column("P. Saída",   width=12, justify="right")
        tt.add_column("P&L $",      width=12, justify="right")
        tt.add_column("P&L %",      width=10, justify="right")
        tt.add_column("Barras",     width=8,  justify="right")

        for i, t in enumerate(r.trades, 1):
            c = "green" if t.pnl >= 0 else "red"
            tt.add_row(
                str(i),
                t.entry_date, t.exit_date,
                f"${t.entry_price:,.2f}", f"${t.exit_price:,.2f}",
                f"[{c}]{t.pnl:+,.2f}[/{c}]",
                f"[{c}]{t.pnl_pct:+.2f}%[/{c}]",
                str(t.bars_held),
            )

        console.print(Panel(tt, title="[dim]📋 Lista de Trades[/dim]", border_style="dim"))

    console.print("\n  [dim italic]⚠️  Resultados passados não garantem performance futura.[/dim italic]")


# ── menu de backtesting ───────────────────────────────────────

STRATEGIES = {
    "1": "SMA Crossover",
    "2": "EMA Crossover",
    "3": "RSI Mean-Reversion",
    "4": "MACD Crossover",
    "5": "Bollinger Reversion",
}

def backtesting_menu(api: tradeapi.REST):
    """Fluxo completo de backtesting."""
    if not _PANDAS_OK:
        console.print(
            "[red]❌  pandas e numpy são necessários para o backtesting.[/red]\n"
            "  Instala com:  [bold]pip install pandas numpy[/bold]"
        )
        return

    while True:
        console.print(Rule("[bold green]🧪 Backtesting[/bold green]"))
        console.print(
            "  [bold cyan]1[/bold cyan] SMA Crossover\n"
            "  [bold cyan]2[/bold cyan] EMA Crossover\n"
            "  [bold cyan]3[/bold cyan] RSI Mean-Reversion\n"
            "  [bold cyan]4[/bold cyan] MACD Crossover\n"
            "  [bold cyan]5[/bold cyan] Bollinger Reversion\n"
            "  [bold cyan]0[/bold cyan] Voltar\n"
        )
        choice = Prompt.ask("  Estratégia", default="0").strip()
        if choice == "0":
            break
        if choice not in STRATEGIES:
            console.print("[yellow]Opção inválida.[/yellow]")
            continue

        strat = STRATEGIES[choice]
        console.print(Rule(f"[dim]{strat}[/dim]"))

        # parâmetros comuns
        symbol  = Prompt.ask("  Ticker (ex: AAPL, SPY)").upper().strip()
        tf_key  = Prompt.ask("  Timeframe", choices=["1m","1h","1d"], default="1d")
        limit   = int(Prompt.ask("  Nº de barras históricas", default="500"))
        capital = float(Prompt.ask("  Capital inicial ($)", default="10000"))

        # parâmetros específicos por estratégia
        params: dict = {}
        if choice == "1":
            params["fast"] = int(Prompt.ask("  SMA rápida (períodos)", default="20"))
            params["slow"] = int(Prompt.ask("  SMA lenta  (períodos)", default="50"))
        elif choice == "2":
            params["fast"] = int(Prompt.ask("  EMA rápida (períodos)", default="12"))
            params["slow"] = int(Prompt.ask("  EMA lenta  (períodos)", default="26"))
        elif choice == "3":
            params["period"]     = int(Prompt.ask("  Período RSI", default="14"))
            params["oversold"]   = float(Prompt.ask("  Nível sobrevenda", default="30"))
            params["overbought"] = float(Prompt.ask("  Nível sobrecompra", default="70"))
        elif choice == "4":
            params["fast"]   = int(Prompt.ask("  MACD rápido", default="12"))
            params["slow"]   = int(Prompt.ask("  MACD lento",  default="26"))
            params["signal"] = int(Prompt.ask("  Signal line", default="9"))
        elif choice == "5":
            params["period"]  = int(Prompt.ask("  Período Bollinger", default="20"))
            params["std_dev"] = float(Prompt.ask("  Desvios padrão",  default="2.0"))

        tf, _ = TIMEFRAME_MAP[tf_key]

        with console.status(f"[cyan]A descarregar {limit} barras de {symbol}…[/cyan]"):
            df = _fetch_ohlcv(api, symbol, tf, limit)

        if df is None or df.empty:
            console.print(f"[red]Sem dados para {symbol}.[/red]")
        else:
            with console.status("[cyan]A correr backtest…[/cyan]"):
                if choice == "1":
                    sigs = _strat_sma_cross(df, params["fast"], params["slow"])
                elif choice == "2":
                    sigs = _strat_ema_cross(df, params["fast"], params["slow"])
                elif choice == "3":
                    sigs = _strat_rsi(df, params["period"], params["oversold"], params["overbought"])
                elif choice == "4":
                    sigs = _strat_macd(df, params["fast"], params["slow"], params["signal"])
                else:
                    sigs = _strat_bollinger(df, params["period"], params["std_dev"])

                result = _run_backtest(df, sigs, capital, symbol, strat, tf_key)

            console.print()
            show_trades = Confirm.ask("  Mostrar lista de trades individuais?", default=False)
            _show_backtest_result(result, show_trades=show_trades)

        console.print()
        if not Confirm.ask("  Correr outro backtest?", default=False):
            break
        console.print()


# ══════════════════════════════════════════════════════════════
#  MÓDULO: ANÁLISE DE RISCO & POSITION SIZING
#
#  Modelos de position sizing:
#    1. Risco Fixo por Trade    — % do capital em risco
#    2. Kelly Criterion         — fracção óptima baseada em win rate / R:R
#    3. ATR-Based Sizing        — stop dinâmico baseado na volatilidade
#    4. Volatility Targeting    — ajusta tamanho para atingir vol. alvo
#
#  Extras:
#    • Análise de correlação entre posições abertas
#    • Concentração de portfolio por posição
#    • Simulação Monte Carlo de trajectórias de capital
# ══════════════════════════════════════════════════════════════

# ── modelos de position sizing ────────────────────────────────

@dataclass
class SizeResult:
    model:         str
    symbol:        str
    entry_price:   float
    stop_price:    float
    capital:       float
    risk_amount:   float      # $ em risco
    risk_pct:      float      # % do capital
    shares:        float      # quantidade a comprar
    position_value: float     # valor total da posição
    position_pct:  float      # % do capital alocado
    rr_ratio:      Optional[float] = None
    target_price:  Optional[float] = None
    notes:         str = ""


def _atr(df: "pd.DataFrame", period: int = 14) -> "pd.Series":
    """Average True Range."""
    import pandas as pd
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _model_fixed_risk(
    capital: float, risk_pct: float,
    entry: float, stop: float,
    target: Optional[float] = None,
) -> SizeResult:
    """Risco fixo: arrisca X% do capital por trade."""
    risk_amount  = capital * risk_pct / 100
    risk_per_shr = abs(entry - stop)
    shares       = risk_amount / risk_per_shr if risk_per_shr > 0 else 0
    pos_val      = shares * entry
    pos_pct      = pos_val / capital * 100
    rr = abs(target - entry) / risk_per_shr if target and risk_per_shr > 0 else None
    return SizeResult(
        model="Risco Fixo",
        symbol="", entry_price=entry, stop_price=stop,
        capital=capital, risk_amount=risk_amount, risk_pct=risk_pct,
        shares=shares, position_value=pos_val, position_pct=pos_pct,
        rr_ratio=rr, target_price=target,
        notes=f"Risco de ${risk_amount:,.2f} por trade ({risk_pct}% do capital)",
    )


def _model_kelly(
    capital: float, win_rate: float, avg_win_pct: float, avg_loss_pct: float,
    entry: float, stop: float,
) -> SizeResult:
    """Kelly Criterion: fracção óptima f* = W/L - (1-W)/W_pct."""
    w   = win_rate / 100
    b   = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 1
    kelly_full = w - (1 - w) / b if b > 0 else 0
    kelly_half = max(kelly_full / 2, 0)   # half-Kelly para segurança
    risk_amount  = capital * kelly_half
    risk_per_shr = abs(entry - stop)
    shares       = risk_amount / risk_per_shr if risk_per_shr > 0 else 0
    pos_val      = shares * entry
    pos_pct      = pos_val / capital * 100
    note = (
        f"Kelly completo: {kelly_full*100:.1f}%  →  Half-Kelly: {kelly_half*100:.1f}%"
        if kelly_full > 0 else "Kelly negativo — estratégia desfavorável com estes parâmetros"
    )
    return SizeResult(
        model="Kelly Criterion (Half)",
        symbol="", entry_price=entry, stop_price=stop,
        capital=capital, risk_amount=risk_amount, risk_pct=kelly_half * 100,
        shares=shares, position_value=pos_val, position_pct=pos_pct,
        notes=note,
    )


def _model_atr(
    api: tradeapi.REST, symbol: str,
    capital: float, risk_pct: float, entry: float,
    atr_mult: float = 2.0, period: int = 14,
) -> SizeResult:
    """ATR-Based: stop = entry - N × ATR."""
    try:
        df = _fetch_ohlcv(api, symbol, tradeapi.TimeFrame.Day, 60)
        if df is None or df.empty:
            raise ValueError("sem dados")
        atr_val   = float(_atr(df, period).iloc[-1])
        stop      = entry - atr_mult * atr_val
        risk_per  = entry - stop
        risk_amt  = capital * risk_pct / 100
        shares    = risk_amt / risk_per if risk_per > 0 else 0
        pos_val   = shares * entry
        pos_pct   = pos_val / capital * 100
        return SizeResult(
            model="ATR-Based",
            symbol=symbol, entry_price=entry, stop_price=stop,
            capital=capital, risk_amount=risk_amt, risk_pct=risk_pct,
            shares=shares, position_value=pos_val, position_pct=pos_pct,
            notes=f"ATR({period}) = ${atr_val:.2f}  ·  Stop = Entrada − {atr_mult}×ATR = ${stop:.2f}",
        )
    except Exception as e:
        return SizeResult(
            model="ATR-Based", symbol=symbol, entry_price=entry, stop_price=entry * 0.98,
            capital=capital, risk_amount=0, risk_pct=0,
            shares=0, position_value=0, position_pct=0,
            notes=f"Erro ao calcular ATR: {e}",
        )


def _model_vol_target(
    api: tradeapi.REST, symbol: str,
    capital: float, vol_target_pct: float, entry: float,
) -> SizeResult:
    """Volatility Targeting: ajusta posição para atingir vol. anual alvo."""
    try:
        import numpy as np
        df   = _fetch_ohlcv(api, symbol, tradeapi.TimeFrame.Day, 60)
        if df is None or df.empty:
            raise ValueError("sem dados")
        rets     = df["close"].pct_change().dropna()
        daily_vol = float(rets.std())
        ann_vol   = daily_vol * (252 ** 0.5) * 100
        weight    = vol_target_pct / ann_vol if ann_vol > 0 else 0
        weight    = min(weight, 1.0)           # cap a 100% do capital
        pos_val   = capital * weight
        shares    = pos_val / entry
        risk_per  = entry * daily_vol * 2      # ~2σ daily como proxy de risco
        risk_amt  = shares * risk_per
        stop      = entry - risk_per
        return SizeResult(
            model="Volatility Targeting",
            symbol=symbol, entry_price=entry, stop_price=stop,
            capital=capital, risk_amount=risk_amt, risk_pct=risk_amt / capital * 100,
            shares=shares, position_value=pos_val, position_pct=weight * 100,
            notes=(
                f"Vol. histórica anual: {ann_vol:.1f}%  ·  "
                f"Alvo: {vol_target_pct}%  ·  "
                f"Peso: {weight*100:.1f}% do capital"
            ),
        )
    except Exception as e:
        return SizeResult(
            model="Volatility Targeting", symbol=symbol, entry_price=entry, stop_price=0,
            capital=capital, risk_amount=0, risk_pct=0,
            shares=0, position_value=0, position_pct=0,
            notes=f"Erro: {e}",
        )


# ── display de result ─────────────────────────────────────────

def _show_size_result(r: SizeResult):
    pos_color = "green" if r.position_pct <= 20 else "yellow" if r.position_pct <= 40 else "red"
    rsk_color = "green" if r.risk_pct <= 2 else "yellow" if r.risk_pct <= 5 else "red"

    lines = [
        f"  [bold]Modelo:[/bold]           {r.model}",
        f"  [bold]Capital:[/bold]          ${r.capital:>12,.2f}",
        f"  [bold]Preço de Entrada:[/bold] ${r.entry_price:>12,.2f}",
        f"  [bold]Preço de Stop:[/bold]    [red]${r.stop_price:>12,.2f}[/red]",
    ]
    if r.target_price:
        lines.append(f"  [bold]Preço Alvo (TP):[/bold]  [green]${r.target_price:>12,.2f}[/green]")
    if r.rr_ratio is not None:
        rr_c = "green" if r.rr_ratio >= 2 else "yellow" if r.rr_ratio >= 1 else "red"
        lines.append(f"  [bold]Risk/Reward:[/bold]      [{rr_c}]{r.rr_ratio:.2f}R[/{rr_c}]")

    lines += [
        "",
        f"  [bold]Quantidade:[/bold]       [bold cyan]{r.shares:.4f}[/bold cyan]  shares / unidades",
        f"  [bold]Valor Posição:[/bold]    [bold cyan]${r.position_value:>12,.2f}[/bold cyan]",
        f"  [bold]% do Capital:[/bold]     [{pos_color}]{r.position_pct:.1f}%[/{pos_color}]",
        f"  [bold]Risco $:[/bold]          [{rsk_color}]${r.risk_amount:>12,.2f}[/{rsk_color}]",
        f"  [bold]Risco %:[/bold]          [{rsk_color}]{r.risk_pct:.2f}%[/{rsk_color}]",
        "",
        f"  [dim]{r.notes}[/dim]",
    ]

    console.print(Panel(
        "\n".join(lines),
        title=f"[bold magenta]📐 Position Sizing — {r.model}[/bold magenta]",
        border_style="magenta",
    ))

    # avisos de concentração
    if r.position_pct > 40:
        console.print("  [red]⚠️  Posição > 40% do capital — risco de concentração elevado.[/red]")
    if r.risk_pct > 5:
        console.print("  [red]⚠️  Risco por trade > 5% — considera reduzir o stop ou o tamanho.[/red]")
    if r.rr_ratio is not None and r.rr_ratio < 1:
        console.print("  [red]⚠️  Risk/Reward < 1 — potencial ganho inferior ao risco assumido.[/red]")


# ── análise do portfolio ──────────────────────────────────────

def _show_portfolio_risk(api: tradeapi.REST):
    """Análise de concentração e risco do portfolio actual."""
    try:
        positions = api.list_positions()
        acct      = api.get_account()
    except Exception as e:
        console.print(f"[red]Erro: {e}[/red]")
        return

    if not positions:
        console.print("[yellow]Sem posições abertas.[/yellow]")
        return

    equity = float(acct.equity)
    total_exposure = sum(abs(float(p.market_value)) for p in positions)

    table = Table(box=box.ROUNDED, border_style="magenta", header_style="bold magenta")
    table.add_column("Ticker",       width=8)
    table.add_column("Valor",        width=12, justify="right")
    table.add_column("% Portfolio",  width=13, justify="right")
    table.add_column("P&L $",        width=12, justify="right")
    table.add_column("P&L %",        width=10, justify="right")
    table.add_column("Risco (2%SL)", width=14, justify="right")
    table.add_column("Concentração", width=14)

    for p in positions:
        val    = abs(float(p.market_value))
        pct    = val / equity * 100
        pl     = float(p.unrealized_pl)
        pl_pct = float(p.unrealized_plpc) * 100
        risk2  = val * 0.02        # risco implícito com SL de 2%

        if pct > 30:
            conc = "[red]Alta ⚠️[/red]"
        elif pct > 15:
            conc = "[yellow]Média[/yellow]"
        else:
            conc = "[green]Normal[/green]"

        table.add_row(
            p.symbol,
            f"${val:,.2f}",
            f"{pct:.1f}%",
            fmt_money(pl),
            fmt_pct(pl_pct),
            f"[red]${risk2:,.2f}[/red]",
            conc,
        )

    # linha de totais
    total_pl = sum(float(p.unrealized_pl) for p in positions)
    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]${total_exposure:,.2f}[/bold]",
        f"[bold]{total_exposure/equity*100:.1f}%[/bold]",
        fmt_money(total_pl),
        fmt_pct(total_pl / equity * 100),
        "", "",
    )

    herfindahl = sum((abs(float(p.market_value)) / total_exposure * 100) ** 2 for p in positions) / 100
    diversif   = "Alta" if herfindahl < 10 else "Média" if herfindahl < 25 else "Baixa"
    div_color  = "green" if herfindahl < 10 else "yellow" if herfindahl < 25 else "red"

    console.print(Panel(
        table,
        title="[bold magenta]📊 Análise de Risco do Portfolio[/bold magenta]",
        subtitle=f"  Diversificação: [{div_color}]{diversif}[/{div_color}]  [dim](HHI={herfindahl:.1f})[/dim]",
        border_style="magenta",
    ))


# ── simulação Monte Carlo ─────────────────────────────────────

def _monte_carlo(api: tradeapi.REST, symbol: str, capital: float, days: int, sims: int = 500):
    """Simula trajectórias de capital por Monte Carlo com retornos históricos."""
    if not _PANDAS_OK:
        return

    import numpy as np

    with console.status(f"[cyan]A simular {sims} trajectórias de {days} dias…[/cyan]"):
        df = _fetch_ohlcv(api, symbol, tradeapi.TimeFrame.Day, 252)
        if df is None or df.empty:
            console.print("[red]Sem dados para simulação.[/red]")
            return

        rets   = df["close"].pct_change().dropna().values
        mu     = float(np.mean(rets))
        sigma  = float(np.std(rets))

        results = []
        for _ in range(sims):
            daily  = np.random.normal(mu, sigma, days)
            path   = capital * np.cumprod(1 + daily)
            results.append(float(path[-1]))

        results = sorted(results)
        p5   = float(np.percentile(results, 5))
        p25  = float(np.percentile(results, 25))
        p50  = float(np.percentile(results, 50))
        p75  = float(np.percentile(results, 75))
        p95  = float(np.percentile(results, 95))
        prob_loss = sum(1 for r in results if r < capital) / sims * 100

    # mini histograma ASCII
    buckets    = 20
    mn, mx     = results[0], results[-1]
    span       = mx - mn if mx != mn else 1
    hist       = [0] * buckets
    for v in results:
        idx = min(int((v - mn) / span * buckets), buckets - 1)
        hist[idx] += 1
    max_h  = max(hist) or 1
    bars   = "▁▂▃▄▅▆▇█"
    mini_h = ""
    for h in hist:
        idx  = int(h / max_h * 7)
        pv   = mn + (hist.index(h) / buckets) * span
        c    = "green" if pv >= capital else "red"
        mini_h += f"[{c}]{bars[idx]}[/{c}]"

    ret_50 = (p50 - capital) / capital * 100
    r_color = "green" if ret_50 >= 0 else "red"

    console.print(Panel(
        f"  [bold]{symbol}[/bold]  ·  {sims} simulações  ·  {days} dias  ·  Capital: ${capital:,.2f}\n\n"
        f"  P5  (pessimista):  [red]${p5:>12,.2f}[/red]  ({(p5-capital)/capital*100:+.1f}%)\n"
        f"  P25              : [yellow]${p25:>12,.2f}[/yellow]  ({(p25-capital)/capital*100:+.1f}%)\n"
        f"  P50 (mediana)    : [{r_color}]${p50:>12,.2f}[/{r_color}]  ({ret_50:+.1f}%)\n"
        f"  P75              : [green]${p75:>12,.2f}[/green]  ({(p75-capital)/capital*100:+.1f}%)\n"
        f"  P95 (optimista)  : [green]${p95:>12,.2f}[/green]  ({(p95-capital)/capital*100:+.1f}%)\n\n"
        f"  Probabilidade de perda: [{'red' if prob_loss>40 else 'yellow' if prob_loss>20 else 'green'}]{prob_loss:.1f}%[/]\n\n"
        f"  Distribuição: {mini_h}",
        title="[bold magenta]🎲 Simulação Monte Carlo[/bold magenta]",
        border_style="magenta",
    ))


# ── menu principal de risco ───────────────────────────────────

def risk_menu(api: tradeapi.REST):
    """Menu de análise de risco e position sizing."""
    while True:
        console.print(Rule("[bold magenta]📐 Análise de Risco & Position Sizing[/bold magenta]"))
        console.print(
            "  [bold cyan]1[/bold cyan] Position Sizing — Risco Fixo\n"
            "  [bold cyan]2[/bold cyan] Position Sizing — Kelly Criterion\n"
            "  [bold cyan]3[/bold cyan] Position Sizing — ATR-Based\n"
            "  [bold cyan]4[/bold cyan] Position Sizing — Volatility Targeting\n"
            "  [bold cyan]5[/bold cyan] Análise de Concentração do Portfolio\n"
            "  [bold cyan]6[/bold cyan] Simulação Monte Carlo\n"
            "  [bold cyan]0[/bold cyan] Voltar\n"
        )
        op = Prompt.ask("  Opção", default="0").strip()

        if op == "0":
            break

        elif op in ("1", "2", "3", "4"):
            console.print(Rule("[dim]Parâmetros[/dim]"))

            if op in ("3", "4"):
                symbol = Prompt.ask("  Ticker").upper().strip()
            else:
                symbol = Prompt.ask("  Ticker (opcional, só para referência)", default="").upper().strip()

            try:
                # tenta preencher preço actual automaticamente
                price_default = ""
                if symbol:
                    bars = api.get_bars(symbol, tradeapi.TimeFrame.Minute, limit=1).df
                    if not bars.empty:
                        price_default = str(round(float(bars.iloc[-1]["close"]), 2))
            except Exception:
                price_default = ""

            entry  = float(Prompt.ask("  Preço de entrada ($)", default=price_default or "100"))

            try:
                acct    = api.get_account()
                cap_def = str(round(float(acct.equity), 2))
            except Exception:
                cap_def = "10000"
            capital = float(Prompt.ask("  Capital disponível ($)", default=cap_def))

            result = None

            if op == "1":
                stop      = float(Prompt.ask("  Preço de Stop-Loss ($)"))
                risk_pct  = float(Prompt.ask("  % do capital a arriscar", default="1.0"))
                target    = Prompt.ask("  Preço alvo / Take-Profit ($, opcional)", default="")
                tp        = float(target) if target.strip() else None
                result    = _model_fixed_risk(capital, risk_pct, entry, stop, tp)

            elif op == "2":
                stop     = float(Prompt.ask("  Preço de Stop-Loss ($)"))
                win_rate = float(Prompt.ask("  Win rate histórico (%)", default="50"))
                avg_win  = float(Prompt.ask("  Ganho médio por trade (%)", default="3.0"))
                avg_loss = float(Prompt.ask("  Perda média por trade (%)", default="1.5"))
                result   = _model_kelly(capital, win_rate, avg_win, avg_loss, entry, stop)

            elif op == "3":
                risk_pct = float(Prompt.ask("  % do capital a arriscar", default="1.0"))
                atr_mult = float(Prompt.ask("  Multiplicador ATR para stop", default="2.0"))
                with console.status("[cyan]A calcular ATR…[/cyan]"):
                    result = _model_atr(api, symbol, capital, risk_pct, entry, atr_mult)

            elif op == "4":
                vol_tgt = float(Prompt.ask("  Volatilidade anual alvo (%)", default="15"))
                with console.status("[cyan]A calcular volatilidade histórica…[/cyan]"):
                    result = _model_vol_target(api, symbol, capital, vol_tgt, entry)

            if result:
                result.symbol = symbol
                console.print()
                _show_size_result(result)

        elif op == "5":
            _show_portfolio_risk(api)

        elif op == "6":
            symbol  = Prompt.ask("  Ticker").upper().strip()
            try:
                acct    = api.get_account()
                cap_def = str(round(float(acct.equity), 2))
            except Exception:
                cap_def = "10000"
            capital = float(Prompt.ask("  Capital ($)", default=cap_def))
            days    = int(Prompt.ask("  Dias a simular", default="252"))
            sims    = int(Prompt.ask("  Nº de simulações", default="1000"))
            _monte_carlo(api, symbol, capital, days, sims)

        console.print()
        input("  ↩  Prima Enter para continuar…")


# ══════════════════════════════════════════════════════════════
#  MENU PRINCIPAL
# ══════════════════════════════════════════════════════════════

MENU_OPTIONS = {
    "1":  ("💰 Resumo da Conta",                "account"),
    "2":  ("📂 Posições Abertas",               "positions"),
    "3":  ("📡 Watchlist ao Vivo",              "watchlist"),
    "4":  ("📊 Indicadores Técnicos",           "technical"),
    "5":  ("🧪 Backtesting",                    "backtest"),
    "6":  ("📐 Análise de Risco & Sizing",      "risk"),
    "7":  ("📋 Ordens Pendentes",               "orders"),
    "8":  ("➕ Nova Ordem",                     "place"),
    "9":  ("❌ Cancelar Ordem",                 "cancel"),
    "10": ("📉 Cotação Rápida",                 "quote"),
    "11": ("📜 Histórico de Trades",            "history"),
    "12": ("🔔 Alertas de Preço",               "alerts"),
    "13": ("🛡️  Stop-Loss / Take-Profit",       "sltp"),
    "14": ("🤖 Assistente IA",                  "ai"),
    "0":  ("🚪 Sair",                           "exit"),
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
        elif action == "technical":
            technical_analysis(api)
        elif action == "backtest":
            backtesting_menu(api)
        elif action == "risk":
            risk_menu(api)
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
