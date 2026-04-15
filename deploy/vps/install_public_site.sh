#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/analise-dados-app"
SERVICE_NAME="engclinica"

if [[ "$EUID" -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/vps/install_public_site.sh"
  exit 1
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "Diretorio $APP_DIR nao encontrado."
  echo "Copie o projeto para esse caminho antes de executar."
  exit 1
fi

cd "$APP_DIR"

apt update
apt install -y python3 python3-venv python3-pip nginx

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

# Aplicar patch apenas no servidor: manter o espaco do botao PDF visivel
# (substitui dinamicamente o bloco de exportacao PDF no app após o deploy)
python3 - <<PY
import re
from pathlib import Path

p = Path("$APP_DIR") / "app.py"
try:
  s = p.read_text(encoding="utf-8")
except Exception as e:
  print(f"Aviso: nao foi possivel ler {p}: {e}")
  exit(0)

pattern = re.compile(r"(^\\s*# PDF export\\n).*?(?=\\n\\s*# ── Envio de e-mail)", re.DOTALL | re.MULTILINE)

new_block = '''        # PDF export
    try:
      if HAS_REPORTLAB:
        pdf_bytes = gerar_relatorio_chamados_abertos_pdf(open_df)
        if pdf_bytes:
          d3.download_button(
            label="Baixar relatorio de abertos (PDF)",
            data=pdf_bytes,
            file_name=f"relatorio_chamados_abertos_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf",
            use_container_width=True,
          )
        else:
          d3.button("Baixar relatorio de abertos (PDF) — indisponivel", key="btn_pdf_none")
          d3.info("Nenhum PDF foi gerado para os filtros atuais.")
      else:
        d3.button("Baixar relatorio de abertos (PDF) — indisponivel", key="btn_pdf_unavailable")
        d3.info("Instale reportlab para habilitar exportacao PDF (pip install reportlab)")
    except Exception as exc:
      # Em caso de erro na geracao, exibe a mensagem para o usuario no mesmo espaco
      d3.info(f"Erro ao gerar PDF: {exc}")
'''

if pattern.search(s):
  s2 = pattern.sub(new_block, s)
  p.write_text(s2, encoding='utf-8')
  print('Patch aplicado em', p)
else:
  print('Trecho alvo nao encontrado; nenhum patch aplicado.')
PY

cp deploy/vps/engclinica.service /etc/systemd/system/${SERVICE_NAME}.service
cp deploy/vps/nginx-engclinica.conf /etc/nginx/sites-available/${SERVICE_NAME}
ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/${SERVICE_NAME}

if [[ -f /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi

systemctl daemon-reload
systemctl enable --now ${SERVICE_NAME}
nginx -t
systemctl restart nginx

if command -v ufw >/dev/null 2>&1; then
  ufw allow 22 || true
  ufw allow 80 || true
fi

echo "Deploy publico concluido."
echo "URL: http://$(curl -s ifconfig.me || echo '<IP_DA_VPS>')"
echo "Status app: systemctl status ${SERVICE_NAME} --no-pager"
