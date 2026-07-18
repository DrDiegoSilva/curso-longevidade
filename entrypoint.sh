#!/bin/sh
set -e
: "${DSCURSO_BASE:=/data/base}"
mkdir -p "$DSCURSO_BASE"

# 1ª execução: popular a base PERSISTENTE (volume) a partir do seed embutido na imagem.
# Redeploys seguintes NÃO sobrescrevem (a base cresce no volume, sobrevive a deploy).
if [ -z "$(ls -A "$DSCURSO_BASE" 2>/dev/null)" ]; then
  echo "[seed] base vazia -> copiando /seed/base para $DSCURSO_BASE"
  cp -r /seed/base/. "$DSCURSO_BASE"/
fi

cd /app
python ebook_curso.py || true   # gera o ebook inicial (não derruba o container se falhar)
exec python serve.py
