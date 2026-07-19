# Curso de Longevidade — container isolado (serve o ebook + roda o robô das 08h BRT)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo \
    DSCURSO_BASE=/data/base \
    PORT=3000

# tzdata p/ o agendador (08:00 BRT) + chromium p/ renderizar o PDF bonito (HTML+CSS -> PDF)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata chromium \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app
COPY app/ /app/
COPY seed/ /seed/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 3000
# volume persistente da base de conhecimento (aulas do curso)
VOLUME ["/data"]
ENTRYPOINT ["/entrypoint.sh"]
