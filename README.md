# Sistema de Engenharia Clinica (Streamlit)

## Rodando local igual ao ambiente web

Para simular o ambiente de produção localmente, execute o app com as variáveis de ambiente:

No Windows PowerShell:

```powershell
$env:ENG_CLINICA_EXTERNAL=1
$env:ENG_CLINICA_PORT=3001
streamlit run run_app.py
```

No Linux/Mac:

```bash
export ENG_CLINICA_EXTERNAL=1
export ENG_CLINICA_PORT=3001
streamlit run run_app.py
```

Assim o app rodará igual ao ambiente web (porta 3001 e modo externo).

Aplicacao local em Python + Streamlit para analise de chamados de Engenharia Clinica a partir de planilha Excel (`.xlsx`).

## Funcionalidades

- Upload de planilha `.xlsx` pela sidebar.
- Saneamento de dados:
- Padroniza colunas para maiusculo e formato com `_`.
- Remove espacos extras e converte textos para maiusculo.
- Trata datas com parse em duas etapas (padrao + fallback `dayfirst=True`).
- Tres abas principais:
- `Dashboard Gerencial`
- `Relatorio Detalhado (Abertos)`
- `Fiabilidade e Historico (MTBF)`
- KPI cards (6 indicadores):
- Abertos
- Fechados
- Total
- Cancelados (com percentual)
- Alta criticidade (abertos)
- MTTR
- Graficos Plotly:
- Aging de chamados abertos por faixa de dias
- Pareto de falhas (donut)
- Filtros dinamicos na sidebar:
- Regiao
- Quadro de Trabalho
- Criticidade
- Tabela de chamados abertos ordenada por `Tipo de Equipamento`.
- Visualizacao adicional em cartoes para leitura operacional.

## Colunas esperadas na planilha

Obrigatorias:

- `Regiao`
- `Quadro`
- `Status`
- `Tipo_Equipamento`
- `Tag`
- `Modelo`
- `Fabricante`
- `Data_Abertura`
- `Falha`
- `Criticidade`

Opcional (para MTTR):

- `Data_Fechamento`

## Executar localmente

1. Criar e ativar ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instalar dependencias:

```powershell
pip install -r requirements.txt
```

3. Rodar aplicacao:

```powershell
streamlit run app.py
```

Opcional (mesmo bootstrap usado no executavel, com fallback automatico de porta quando 3000 estiver ocupada):

```powershell
python run_app.py
```

Para forcar porta inicial diferente da 3000:

```powershell
$env:ENG_CLINICA_PORT=3010
python run_app.py
```

## Health check rapido

Para revisar automaticamente arquivos, imports, compilacao e fallback de porta:

```powershell
python health_check.py
```

## Checklist de pre-entrega (1 comando)

Para rodar validacoes completas antes de publicar/gerar exe:

```powershell
.\pre_entrega.ps1
```

Para validar e ja gerar o executavel no final:

```powershell
.\pre_entrega.ps1 -BuildExe
```

## Acesso externo (1 comando)

Para subir app + tunel externo automaticamente:

```powershell
.\acesso_externo.ps1
```

Observacao: agora o padrao usa Cloudflare Quick Tunnel (mais estavel para web).
Para usar o localtunnel (`loca.lt`) manualmente:

```powershell
.\acesso_externo.ps1 -UseLocalTunnel
```

Comandos uteis:

```powershell
# Somente subir app local (sem tunel)
.\acesso_externo.ps1 -NoTunnel

# Apenas ver status atual (processos/porta/log de URL)
.\acesso_externo.ps1 -StatusOnly

# Encerrar app e tunel
.\acesso_externo.ps1 -StopOnly
```

## Acesso seguro na web (gratuito) com Cloudflare

Script pronto para subir app local + tunel seguro Cloudflare:

```powershell
.\acesso_seguro_cloudflare.ps1 -TunnelName engclinica -Hostname app.seudominio.com
```

Comandos uteis:

```powershell
# Apenas subir app local (sem tunel)
.\acesso_seguro_cloudflare.ps1 -NoTunnel

# Ver status de app e cloudflared
.\acesso_seguro_cloudflare.ps1 -StatusOnly -Hostname app.seudominio.com

# Encerrar app e cloudflared
.\acesso_seguro_cloudflare.ps1 -StopOnly
```

Pre-requisito (1x) para tunel nomeado:

```powershell
cloudflared tunnel login
cloudflared tunnel create engclinica
```

## Publicar como site na VPS (Hostinger)

Arquivos prontos de deploy foram adicionados em `deploy/vps/`:

- `deploy/vps/engclinica.service`
- `deploy/vps/nginx-engclinica.conf`
- `deploy/vps/install_public_site.sh`

### Passo a passo rapido

1. Copie o projeto para a VPS em `/opt/analise-dados-app`.
2. Na VPS, execute:

```bash
cd /opt/analise-dados-app
sudo bash deploy/vps/install_public_site.sh
```

3. Acesse publicamente por IP:

```text
http://SEU_IP_DA_VPS
```

### Comandos de operacao

```bash
sudo systemctl status engclinica --no-pager
sudo systemctl restart engclinica
sudo systemctl restart nginx
```

### Deploy automatico via SSH (Windows)

Script pronto para enviar e publicar com um comando:

```powershell
.\deploy_to_vps.ps1 -ServerIp 187.77.34.11 -User root
```

Se usar chave privada:

```powershell
.\deploy_to_vps.ps1 -ServerIp 187.77.34.11 -User root -KeyPath "C:\caminho\sua-chave.pem"
```

## Gerar executavel (.exe) com PyInstaller (Windows)

### 1) Instale o PyInstaller (se necessario)

```powershell
pip install pyinstaller
```

### 2) Gere o executavel

Sem icone:

```powershell
pyinstaller --noconfirm --clean --onefile --name EngenhariaClinica --collect-all streamlit --collect-all plotly --add-data "app.py;." run_app.py
```

Com icone (`icone.ico` na raiz do projeto):

```powershell
pyinstaller --noconfirm --clean --onefile --name EngenhariaClinica --icon icone.ico --collect-all streamlit --collect-all plotly --add-data "app.py;." run_app.py
```

### 3) Executar

- O executavel sera criado em `dist\EngenhariaClinica.exe`.
- Ao abrir, o Streamlit inicia localmente e abre no navegador.

## Estrutura do projeto

- `app.py`: aplicacao principal Streamlit.
- `run_app.py`: bootstrap para executar o Streamlit via `.exe`.
- `requirements.txt`: dependencias.
