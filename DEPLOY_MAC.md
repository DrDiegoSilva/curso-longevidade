# DEPLOY — instruções para o Claude Code (Mac)

> **Diego:** no Mac, é só abrir o Claude Code e dizer *"leia o DEPLOY_MAC.md e execute"*. Tudo que ele precisa está aqui.

## Tarefa
Publicar **este app** (`curso-longevidade`) no meu VPS (EasyPanel Campinas) como um serviço **novo e isolado**, servido em **`curso.drdiegosilva.com.br`**, com deploy automático a partir do GitHub.

O que o app é: container Docker (Python, só stdlib) que **serve um ebook de longevidade** e **roda um robô diário às 08h BRT** (manda resumo/aula no meu WhatsApp via Z-API e regenera o ebook). Repo: `github.com/DrDiegoSilva/curso-longevidade`.

## ⚠️ Isolamento (regra dura)
Este app é **totalmente separado do clinicdspro** — outro serviço, outro subdomínio. **NÃO** altere o clinicdspro, o banco, nem toque em dados de paciente. É só criar um app novo ao lado.

## Infra
Os detalhes da minha infra (SSH do VPS, EasyPanel Campinas, painel, token da API do EasyPanel, Cloudflare) estão no **`CLAUDE.md` do repo clinicdspro** (`~/dev/clinicdspro`). Use-os.

## Passos

1. **EasyPanel** — criar serviço App novo chamado `curso`:
   - **Source:** GitHub → `DrDiegoSilva/curso-longevidade`, branch `main`, build por **Dockerfile**
   - **Porta interna:** `3000`
   - **Volume persistente:** montado em **`/data`** (guarda as aulas do curso)
   - **Domínio:** `curso.drdiegosilva.com.br` → porta `3000`, **Let's Encrypt**
   - **Variáveis de ambiente:**
     | Variável | Valor |
     |---|---|
     | `DSCURSO_ANTHROPIC_KEY` | **eu colo** — chave Anthropic dedicada dos resumos (separada da chave do clinicdspro; está no meu PC Windows em `C:\Users\edson\.anthropic-resumos.json`, campo `apiKey`) |
     | `ZAPI_INSTANCE_ID` | mesma credencial Z-API que o clinicdspro já usa |
     | `ZAPI_INSTANCE_TOKEN` | idem |
     | `ZAPI_CLIENT_TOKEN` | idem |
     | `ZAPI_DESTINO` | meu número (mesmo destino do Z-API) |

     As 4 do Z-API estão no **Supabase, tabela `Clinic`** da "Instituto Diego Silva" (ou no painel Z-API). A `DSCURSO_ANTHROPIC_KEY` **eu forneço** — pergunte se não tiver.

2. **Cloudflare** — registro **A**: nome `curso` → IP do VPS **`187.77.58.74`** → Proxy **DNS only** (nuvem cinza, pro cert LE sair sem atrito).

3. **Deploy** e **confirme**:
   - `https://curso.drdiegosilva.com.br` mostra o ebook
   - `https://curso.drdiegosilva.com.br/health` responde `ok`

4. **Me lembre de desligar** a Tarefa Agendada do Windows `ResumoDiario_DrDiego` no meu PC (senão o resumo das 08h chega **em dobro**: o do PC + o do VPS).

## Referência
O `README.md` deste repo explica a estrutura (app/ = scripts, seed/base = aulas iniciais, entrypoint semeia o volume `/data`). Sem segredos no repo — tudo por env var no painel. Se faltar algum valor, **pergunte antes de inventar**.
