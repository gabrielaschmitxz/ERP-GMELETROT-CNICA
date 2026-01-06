# Como Manter a Instância do Render Sempre Ativa (Plano Gratuito)

## Problema
O plano gratuito do Render desativa a instância após 15 minutos de inatividade, causando delay de ~50 segundos na primeira requisição.

## Solução: Serviços de Ping Automático

### Opção 1: UptimeRobot (Recomendado - Gratuito)

1. Acesse: https://uptimerobot.com/
2. Crie uma conta gratuita
3. Clique em "Add New Monitor"
4. Configure:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: ERP Eletrotecnica Keep Alive
   - **URL**: `https://seu-app.onrender.com/health`
   - **Monitoring Interval**: 5 minutes (mínimo no plano gratuito)
5. Salve e ative

**Limite do plano gratuito**: 50 monitors, intervalo mínimo de 5 minutos

### Opção 2: cron-job.org (Gratuito)

1. Acesse: https://cron-job.org/
2. Crie uma conta gratuita
3. Clique em "Create cronjob"
4. Configure:
   - **Title**: Keep Alive Render
   - **Address**: `https://seu-app.onrender.com/health`
   - **Schedule**: A cada 10 minutos (ex: `*/10 * * * *`)
5. Salve e ative

**Limite do plano gratuito**: 2 cronjobs simultâneos

### Opção 3: EasyCron (Gratuito)

1. Acesse: https://www.easycron.com/
2. Crie uma conta gratuita
3. Adicione um novo cron job:
   - **Cron Job Name**: Render Keep Alive
   - **URL**: `https://seu-app.onrender.com/health`
   - **Schedule**: A cada 10 minutos
4. Salve e ative

**Limite do plano gratuito**: 1 cronjob

### Opção 4: Python Script Local (Se você tiver um computador sempre ligado)

Crie um arquivo `keep_alive.py`:

```python
import requests
import time
from datetime import datetime

URL = "https://seu-app.onrender.com/health"
INTERVAL = 600  # 10 minutos em segundos

while True:
    try:
        response = requests.get(URL, timeout=30)
        print(f"[{datetime.now()}] Status: {response.status_code}")
    except Exception as e:
        print(f"[{datetime.now()}] Erro: {e}")
    time.sleep(INTERVAL)
```

Execute: `python keep_alive.py`

## Endpoints Disponíveis

- `/health` - Retorna status OK (recomendado para ping)
- `/ping` - Alias para `/health`

## Importante

- O intervalo mínimo recomendado é **10 minutos** (para não sobrecarregar)
- O Render permite até **750 horas/mês** no plano gratuito
- Com ping a cada 10 minutos = ~4.320 requisições/mês (muito abaixo do limite)

## Verificação

Após configurar, você pode verificar se está funcionando:
1. Acesse o painel do Render
2. Veja os logs - deve aparecer requisições GET em `/health` a cada 10 minutos
3. Teste acessar o site - não deve mais ter delay de 50 segundos

