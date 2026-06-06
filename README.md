# Cost Rental Alerts

Scraper diário para habitação acessível (cost rental) na Irlanda.

**Fontes:** [affordablehomes.ie](https://affordablehomes.ie/rent/), [LDA](https://lda.ie/affordable-homes/lda-cost-rental/), [Tuath Housing](https://tuathhousing.ie/cost-rental/)

**Output:** mensagem WhatsApp (via CallMeBot) no teu número privado — revês e publicas na Community Announcements.

## Setup rápido

### 1. CallMeBot (uma vez)

1. Adiciona `+34 644 31 95 65` aos contactos do telemóvel (nome: CallMeBot)
2. Envia no WhatsApp: `I allow callmebot to send me messages`
3. Recebes uma resposta com o teu `apikey`
4. Guarda o apikey — não commits no código

### 2. Repositório GitHub (privado)

```bash
cd cost-rental-alerts
git init
git add .
git commit -m "Initial cost rental alerts scraper"
gh repo create cost-rental-alerts --private --source=. --push
```

### 3. GitHub Secrets

Em **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Valor |
|---|---|
| `CALLMEBOT_PHONE` | Teu número com código país, ex. `+353871234567` |
| `CALLMEBOT_APIKEY` | Apikey recebida do CallMeBot |

### 4. Testar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 1ª vez: só cria a base (recomendado antes do WhatsApp automático)
python run_daily.py --scrape-only

# Ver mensagem sem enviar
python run_daily.py --dry-run

# Enviar para o teu WhatsApp (exporta secrets localmente)
export CALLMEBOT_PHONE="+353..."
export CALLMEBOT_APIKEY="..."
python run_daily.py
```

### 5. GitHub Actions

O workflow corre automaticamente às **07:00 UTC** (~08:00 Irlanda). Podes também correr manualmente em **Actions → Daily Cost Rental Scrape → Run workflow**.

## Comportamento

- **Com novidades:** lista inscrições abertas hoje + esquemas que abrem nos próximos 14 dias
- **Sem novidades:** envia `✅ Nenhuma novidade hoje.`
- **Base de dados:** `listings.db` (SQLite, commitado no repo após cada run)

## Estrutura

```
run_daily.py          # entrypoint
scrapers/             # affordablehomes, lda, tuath
db.py                 # SQLite
diff.py               # detecta novidades
notify.py             # formata + CallMeBot
.github/workflows/    # cron diário
```
