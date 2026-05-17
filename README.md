# ⚡ QuantaTrader — AI-Powered Trading Assistant

> Assistente de trading em Python inspirado no Alpaca, com integração de IA (Claude) para análise de mercado.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Alpaca](https://img.shields.io/badge/Alpaca-API-yellow)
![Claude](https://img.shields.io/badge/Claude-AI-green)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## ✨ Funcionalidades

| Módulo | Descrição |
|---|---|
| 💰 **Portfolio** | Resumo em tempo real da conta (equity, cash, P&L) |
| 📂 **Posições** | Visualização de posições abertas com P&L por activo |
| 📋 **Ordens** | Listagem, criação e cancelamento de ordens |
| 📉 **Cotações** | Preço actual (OHLCV) de qualquer ticker |
| 📜 **Histórico** | Últimos trades com detalhe de execução |
| 🤖 **IA (Claude)** | Chat contextualizado com o teu portfolio para análise de mercado |

---

## 🚀 Instalação

```bash
git clone https://github.com/teu-username/quanta-trader.git
cd quanta-trader
pip install -r requirements.txt
```

### Dependências (`requirements.txt`)

```
alpaca-trade-api
anthropic
rich
prompt_toolkit
python-dotenv
requests
```

---

## ⚙️ Configuração

Cria um ficheiro `.env` na raiz do projecto:

```env
# Alpaca (obtém em https://alpaca.markets)
ALPACA_API_KEY=tua_api_key
ALPACA_SECRET_KEY=tua_secret_key
ALPACA_BASE_URL=https://paper-api.alpaca.markets   # paper trading (sem dinheiro real)
# ALPACA_BASE_URL=https://api.alpaca.markets       # live trading

# Anthropic (obtém em https://console.anthropic.com)
ANTHROPIC_API_KEY=tua_anthropic_key
```

> ⚠️ **Paper Trading** é o modo predefinido — seguro para testar sem risco financeiro.

---

## ▶️ Uso

```bash
python quanta_trader.py
```

### Menu Principal

```
╭──────┬──────────────────────────╮
│  1   │ 💰 Resumo da Conta       │
│  2   │ 📂 Posições Abertas       │
│  3   │ 📋 Ordens Pendentes       │
│  4   │ ➕ Nova Ordem             │
│  5   │ ❌ Cancelar Ordem         │
│  6   │ 📉 Cotação Rápida         │
│  7   │ 📜 Histórico de Trades    │
│  8   │ 🤖 Assistente IA          │
│  0   │ 🚪 Sair                   │
╰──────┴──────────────────────────╯
```

### Assistente IA

O assistente Claude tem contexto do teu portfolio actual e responde em Português:

```
Tu: Qual é a tua análise da AAPL esta semana?

🤖 QuantaTrader AI:
A Apple apresenta uma tendência de consolidação após a máxima recente...
```

---

## 🏗️ Estrutura do Projecto

```
quanta-trader/
├── quanta_trader.py   ← Script principal
├── .env               ← Chaves de API (não commitar!)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🔒 Segurança

- **Nunca** faças commit do `.env`
- Usa sempre **paper trading** para testar
- O assistente IA não dá conselhos financeiros vinculativos

---

## 📄 Licença

MIT © 2025 — QuantaTrader
