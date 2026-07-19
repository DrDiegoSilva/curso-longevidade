# Curso de Longevidade — container isolado (serve o ebook + roda o robô das 08h BRT)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo \
    DSCURSO_BASE=/data/base \
    PORT=3000

# tzdata (08:00 BRT) + chromium (renderiza o PDF) + fonte de emoji (💡📊🧠 no PDF)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata chromium fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Driver Postgres (Supabase) — usado só em produção (quando DATABASE_URL está setada)
RUN pip install --no-cache-dir psycopg2-binary

WORKDIR /app
COPY app/ /app/
COPY seed/ /seed/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 3000
# volume persistente da base de conhecimento (aulas do curso)
VOLUME ["/data"]
ENTRYPOINT ["/entrypoint.sh"]
