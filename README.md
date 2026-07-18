# Curso de Longevidade — Dr. Diego

App **isolado** (não encosta no clinicdspro) que:
- **serve o ebook** do curso em `curso.drdiegosilva.com.br`, e
- **roda o robô das 08h BRT** (resumo/aula do dia → WhatsApp via Z-API), regenerando o ebook a cada módulo novo.

Tudo em **um container Python** (stdlib apenas, sem pip). A base de conhecimento (aulas) fica num **volume persistente** `/data` — sobrevive a redeploys e cresce sozinha.

## Estrutura
```
app/            scripts do sistema (resumo_diario, ebook_curso, buscar_estudos, enviar_zap, config, serve, temas_config)
seed/base/      aulas iniciais (semeadas no volume na 1ª subida)
Dockerfile      imagem
entrypoint.sh   semeia o volume + gera ebook + sobe o serve.py
```

## Deploy no EasyPanel (VPS) — passo a passo

1. **Criar app**: painel EasyPanel → novo serviço → **Source = GitHub** → este repositório, branch `main`, **Build = Dockerfile**.
2. **Volume**: adicionar volume persistente montado em **`/data`** (guarda as aulas).
3. **Domínio**: adicionar **`curso.drdiegosilva.com.br`** → porta **3000** (SSL Let's Encrypt automático).
4. **Variáveis de ambiente** (aba Environment do serviço):

   | Variável | Valor | De onde tirar |
   |---|---|---|
   | `DSCURSO_ANTHROPIC_KEY` | *(a chave dedicada dos resumos)* | seu `~/.anthropic-resumos.json` (campo `apiKey`) |
   | `ZAPI_INSTANCE_ID` | *(id da instância Z-API)* | seu `~/.zapi-config.json` |
   | `ZAPI_INSTANCE_TOKEN` | *(token da instância)* | idem |
   | `ZAPI_CLIENT_TOKEN` | *(client-token)* | idem |
   | `ZAPI_DESTINO` | *(número destino, DDI+DDD+numero)* | idem |

   Já vêm por padrão na imagem (não precisa setar): `DSCURSO_BASE=/data/base`, `PORT=3000`, `TZ=America/Sao_Paulo`.

5. **DNS (Cloudflare)**: registro **A** `curso` → IP do VPS (o mesmo do EasyPanel). Pode deixar **DNS-only** (nuvem cinza) para o Let's Encrypt do EasyPanel emitir o certificado sem atrito.
6. **Deploy** → aguardar build. Testar `https://curso.drdiegosilva.com.br` (ebook) e `.../health` (deve responder `ok`).

## Depois que estiver no ar
- **Desligar a Tarefa Agendada do Windows** `ResumoDiario_DrDiego` neste PC (senão o WhatsApp chega em dobro).
- O robô das 08h passa a rodar aqui no container; o ebook fica sempre atualizado no subdomínio.

## Notas (v1)
- Log e cache de dedupe ficam em `/app` (efêmeros a cada redeploy). Impacto mínimo (no máximo um estudo repetido após um redeploy). Migrar p/ `/data` numa v1.1 se incomodar.
- Sem segredos no repositório — todas as credenciais entram por variável de ambiente no painel.
