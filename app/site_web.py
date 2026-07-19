"""Render HTML do site artigos (stdlib, inline CSS). Dark-luxury verde+dourado,
marca Dr. Diego Silva · CRM-PR 54310. Reusa o gráfico/gancho/resumo do pdf.py (DRY).

Camadas:
- landing()            público (SEO)
- pagina_entrar(...)   login OTP (2 passos)
- hub_temas / lista_tema / pagina_digest / pagina_minha   protegidos
"""
import json
import html as _html
import config
import pdf

MARCA = "Dr. Diego Silva"
CRM = "CRM-PR 54310"
PRODUTO = "Atualização Científica"

_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&display=swap" rel="stylesheet">')

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--verde:#0e211a;--verde2:#14332a;--verde3:#1e5045;--ouro:#c9a227;--ouro2:#e7c766;
  --creme:#f4f1e7;--creme2:#ece4c6;--texto:#e8efe9;--suave:#a9bcb2}
body{background:radial-gradient(120% 80% at 80% -10%,#1a3a2e 0%,var(--verde) 55%,#0a1a14 100%);
  color:#e8efe9;font-family:Georgia,"Times New Roman",serif;line-height:1.65;min-height:100vh;
  -webkit-font-smoothing:antialiased}
.disp{font-family:"Cormorant Garamond",Georgia,serif;font-weight:600;line-height:1.1}
.wrap{max-width:960px;margin:0 auto;padding:0 24px}
a{color:inherit}
/* top bar */
.top{display:flex;align-items:center;justify-content:space-between;padding:22px 0;gap:12px;flex-wrap:wrap}
.brand{display:flex;flex-direction:column;line-height:1.15}
.brand .m{font-family:"Cormorant Garamond",Georgia,serif;font-size:22px;color:var(--creme);font-weight:700}
.brand .c{font-family:system-ui,sans-serif;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--suave)}
.nav a{font-family:system-ui,sans-serif;font-size:13px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--creme);text-decoration:none;border:1px solid rgba(201,162,39,.5);border-radius:100px;padding:9px 18px;transition:.2s}
.nav a:hover{background:var(--ouro);color:#1a1300;border-color:var(--ouro)}
/* hero */
.hero{padding:56px 0 40px}
.eyebrow{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.28em;text-transform:uppercase;color:var(--ouro2);margin-bottom:20px}
.hero h1{font-size:clamp(40px,7vw,74px);color:var(--creme);letter-spacing:-.01em;text-wrap:balance;margin-bottom:22px}
.hero h1 em{font-style:normal;color:var(--ouro2)}
.lead{font-size:20px;color:var(--suave);max-width:620px;margin-bottom:34px}
.cta{display:inline-block;background:linear-gradient(180deg,var(--ouro2),var(--ouro));color:#1a1300;
  font-family:system-ui,sans-serif;font-weight:700;font-size:16px;letter-spacing:.02em;text-decoration:none;
  padding:16px 34px;border-radius:100px;box-shadow:0 10px 30px -8px rgba(201,162,39,.5);transition:.2s}
.cta:hover{transform:translateY(-2px);box-shadow:0 16px 38px -8px rgba(201,162,39,.6)}
.cta.ghost{background:transparent;color:var(--creme);border:1px solid rgba(201,162,39,.55);box-shadow:none}
/* seções */
.sec{padding:46px 0;border-top:1px solid rgba(233,225,198,.1)}
.sec h2{font-size:clamp(28px,4vw,40px);color:var(--creme);margin-bottom:10px}
.sec .sub{color:var(--suave);margin-bottom:30px;max-width:640px}
.grid{display:grid;gap:16px}
.g3{grid-template-columns:repeat(auto-fit,minmax(210px,1fr))}
.g4{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.card{background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.12);border-radius:16px;padding:24px}
.card h3{font-family:"Cormorant Garamond",Georgia,serif;font-size:24px;color:var(--creme);margin-bottom:8px}
.card p{color:var(--suave);font-size:15.5px}
.chip{display:flex;align-items:center;gap:12px;background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.12);
  border-radius:14px;padding:16px 18px}
.chip .e{font-size:26px}
.chip .t{font-family:"Cormorant Garamond",Georgia,serif;font-size:20px;color:var(--creme)}
.chip .n{font-family:system-ui,sans-serif;font-size:12px;color:var(--suave)}
/* planos */
.plano{position:relative;text-align:center}
.plano .nm{font-family:"Cormorant Garamond",Georgia,serif;font-size:26px;color:var(--ouro2);margin-bottom:4px}
.plano .pr{font-size:30px;color:var(--creme);margin:8px 0 2px}
.plano .pe{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--suave)}
.plano .pn{font-family:system-ui,sans-serif;font-size:12.5px;color:var(--ouro2);margin-top:10px}
/* login/forms */
.panel{max-width:440px;margin:40px auto;background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.14);
  border-radius:20px;padding:38px 32px}
.panel h2{font-family:"Cormorant Garamond",Georgia,serif;font-size:34px;color:var(--creme);margin-bottom:6px}
.panel p.hint{color:var(--suave);margin-bottom:22px;font-size:15px}
label{display:block;font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--suave);margin-bottom:8px}
input[type=text]{width:100%;background:rgba(0,0,0,.25);border:1px solid rgba(233,225,198,.2);border-radius:12px;
  color:var(--creme);font-size:20px;font-family:Georgia,serif;padding:14px 16px;margin-bottom:18px;letter-spacing:.04em}
input:focus{outline:none;border-color:var(--ouro)}
button.cta{border:none;cursor:pointer;width:100%;font-size:16px}
.erro{background:rgba(180,40,40,.18);border:1px solid rgba(220,90,90,.4);color:#ffd9d9;border-radius:10px;padding:12px 14px;margin-bottom:16px;font-family:system-ui,sans-serif;font-size:14px}
/* arquivo */
.crumb{font-family:system-ui,sans-serif;font-size:13px;color:var(--suave);margin:8px 0 24px}
.crumb a{color:var(--ouro2);text-decoration:none}
.item{display:block;text-decoration:none;background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.12);
  border-radius:14px;padding:20px 22px;margin-bottom:12px;transition:.15s}
.item:hover{border-color:var(--ouro);background:rgba(255,255,255,.06)}
.item .d{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.06em;color:var(--ouro2);margin-bottom:6px}
.item .t{font-family:"Cormorant Garamond",Georgia,serif;font-size:23px;color:var(--creme);line-height:1.2}
/* documento (papel claro sobre o fundo escuro) — reusa estilos do PDF */
.doc{background:var(--creme);color:#20302b;border-radius:16px;padding:40px 44px;margin:8px 0 26px;box-shadow:0 20px 60px -20px rgba(0,0,0,.6)}
.doc .title{font-family:"Cormorant Garamond",Georgia,serif;font-size:34px;line-height:1.18;color:#14332a;margin-bottom:12px}
.doc .meta{font-family:ui-monospace,Menlo,monospace;font-size:13px;color:#6f7d78;border-bottom:2px solid var(--ouro);padding-bottom:12px;margin-bottom:20px}
.doc .corpo p{margin:.8em 0;font-size:17px;color:#2b3a35}
.doc .corpo strong{color:#14332a}
.chart{margin:24px 0;background:#f4f1e7;border:1px solid #e7e2d6;border-radius:10px;padding:18px 20px}
.chart .ct{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#6f7d78;margin-bottom:12px;font-weight:600}
.bar-row{display:flex;align-items:center;gap:12px;margin:10px 0}
.bar-lab{width:120px;font-family:system-ui,sans-serif;font-size:14px;color:#2b3a35;flex:none}
.bar-track{flex:1;background:#e7e2d3;border-radius:100px;height:22px;overflow:hidden}
.bar-fill{height:100%;border-radius:100px}
.bar-val{font-family:ui-monospace,monospace;font-size:14px;font-weight:700;width:66px;text-align:right;flex:none}
.social{margin:24px 0 6px;border:2px solid var(--ouro);border-radius:12px;padding:18px 20px;background:linear-gradient(180deg,#fff9e9,#fbf3d9)}
.social .lab{font-family:system-ui,sans-serif;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#8a6a06;font-weight:700;margin-bottom:8px}
.social .post{font-size:17px;color:#3a2f10;font-style:italic;line-height:1.6}
.docbtn{display:inline-block;margin-top:6px;font-family:system-ui,sans-serif;font-size:14px;color:var(--ouro2);text-decoration:none;border:1px solid rgba(201,162,39,.5);border-radius:100px;padding:10px 20px}
.foot{padding:40px 0 60px;border-top:1px solid rgba(233,225,198,.1);color:var(--suave);font-family:system-ui,sans-serif;font-size:13px;margin-top:20px}
.foot .cfm{max-width:640px;margin-top:8px;font-size:12px;opacity:.8}
"""


def _esc(s):
    return _html.escape(str(s or ""))


def _cta():
    return _esc(config.cta_url())


def _topbar(logado=False):
    direita = ('<a href="/artigos">Arquivo</a>' if logado else '<a href="/entrar">Entrar</a>')
    return (f'<div class="wrap"><div class="top">'
            f'<a href="/" style="text-decoration:none"><div class="brand">'
            f'<span class="m">{_esc(MARCA)}</span><span class="c">{_esc(CRM)}</span></div></a>'
            f'<nav class="nav">{direita}</nav></div></div>')


def _foot():
    return (f'<div class="wrap"><div class="foot">'
            f'{_esc(MARCA)} · {_esc(CRM)} · {_esc(PRODUTO)}'
            f'<div class="cfm">Conteúdo de caráter científico-educacional, destinado a médicos. '
            f'Não substitui o julgamento clínico individual nem constitui recomendação de conduta.</div>'
            f'</div></div>')


def _pagina(titulo, corpo, logado=False, meta_extra=""):
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{_esc(titulo)}</title>{meta_extra}{_FONTS}<style>{_CSS}</style></head><body>'
            f'{_topbar(logado)}{corpo}{_foot()}</body></html>')


# ── Landing (pública) ──
def landing():
    temas = [("⚖️", "Obesidade"), ("⚕️", "Menopausa & Reposição Hormonal"),
             ("🦵", "Lipedema"), ("🏃", "Performance"), ("🧬", "Longevidade")]
    chips = "".join(
        f'<div class="chip"><span class="e">{_esc(e)}</span>'
        f'<div><div class="t">{_esc(t)}</div><div class="n">estudo do dia</div></div></div>'
        for e, t in temas)
    valores = [
        ("Curadoria + revisão médica", "Uma IA tria a literatura da semana; o Dr. Diego revisa antes de sair. Você recebe o que importa, sem ruído."),
        ("1 estudo por dia útil", "De segunda a sexta, um artigo relevante — resumo clínico direto ao ponto, no seu WhatsApp."),
        ("Pronto para as redes", "Cada edição traz uma dica de como levar o tema para os seus pacientes nas redes sociais."),
        ("Arquivo consultável", "Tudo que você recebeu fica organizado por tema e data, sempre à mão neste portal."),
    ]
    cards = "".join(f'<div class="card"><h3>{_esc(n)}</h3><p>{_esc(d)}</p></div>' for n, d in valores)
    planos = "".join(
        f'<div class="card plano"><div class="nm">{_esc(p["nome"])}</div>'
        f'<div class="pr">{_esc(p["preco"]) if p.get("preco") else "sob consulta"}</div>'
        f'<div class="pe">{_esc(p["periodo"])}</div>'
        + (f'<div class="pn">{_esc(p["nota"])}</div>' if p.get("nota") else "")
        + '</div>' for p in config.PLANOS)
    corpo = f"""
    <div class="wrap">
      <section class="hero">
        <div class="eyebrow">{_esc(PRODUTO)}</div>
        <h1 class="disp">A ciência que move a sua <em>prática clínica</em> — todo dia útil, no seu WhatsApp.</h1>
        <p class="lead">Um estudo relevante por dia, com resumo clínico objetivo, gancho para as suas redes e um PDF elegante. Curado por IA, revisado por médico.</p>
        <a class="cta" href="{_cta()}">Quero assinar</a>
      </section>
      <section class="sec"><h2 class="disp">O que você recebe</h2>
        <div class="grid g4">{cards}</div></section>
      <section class="sec"><h2 class="disp">Cinco frentes, uma rotina</h2>
        <p class="sub">A fila varia os temas para você não receber dois dias seguidos do mesmo assunto.</p>
        <div class="grid g3">{chips}</div></section>
      <section class="sec"><h2 class="disp">Planos</h2>
        <p class="sub">Escolha a recorrência que faz sentido para você. Renova automaticamente até você cancelar.</p>
        <div class="grid g4">{planos}</div>
        <div style="margin-top:26px"><a class="cta" href="{_cta()}">Quero assinar</a>
        <a class="cta ghost" href="/entrar" style="margin-left:10px">Já sou assinante</a></div>
      </section>
    </div>"""
    return _pagina(f"{PRODUTO} · {MARCA}", corpo, logado=False)


# ── Login OTP ──
def pagina_entrar(etapa="numero", whatsapp="", erro=""):
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    if etapa == "codigo":
        corpo = f"""
        <div class="wrap"><div class="panel">
          <h2 class="disp">Digite o código</h2>
          <p class="hint">Enviamos um código de 6 dígitos no seu WhatsApp. Ele vale por 10 minutos.</p>
          {erro_html}
          <form method="post" action="/entrar">
            <input type="hidden" name="etapa" value="codigo">
            <input type="hidden" name="whatsapp" value="{_esc(whatsapp)}">
            <label>Código</label>
            <input type="text" name="codigo" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000" autofocus>
            <button class="cta" type="submit">Entrar</button>
          </form>
          <p class="hint" style="margin-top:16px"><a href="/entrar" style="color:var(--ouro2)">Usar outro número</a></p>
        </div></div>"""
    else:
        corpo = f"""
        <div class="wrap"><div class="panel">
          <h2 class="disp">Área do assinante</h2>
          <p class="hint">Informe o WhatsApp da sua assinatura. Vamos te enviar um código de acesso.</p>
          {erro_html}
          <form method="post" action="/entrar">
            <input type="hidden" name="etapa" value="numero">
            <label>WhatsApp (com DDD)</label>
            <input type="text" name="whatsapp" inputmode="tel" placeholder="(43) 99999-0000" autofocus>
            <button class="cta" type="submit">Enviar código</button>
          </form>
          <p class="hint" style="margin-top:16px">Ainda não assina? <a href="/" style="color:var(--ouro2)">Conheça o plano</a>.</p>
        </div></div>"""
    return _pagina(f"Entrar · {PRODUTO}", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')


# ── Arquivo (protegido) ──
def hub_temas(temas):
    if not temas:
        corpo = ('<div class="wrap"><section class="sec"><h2 class="disp">Arquivo</h2>'
                 '<p class="sub">Ainda não há edições publicadas. Assim que a primeira for enviada, ela aparece aqui.</p></section></div>')
        return _pagina(f"Arquivo · {PRODUTO}", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')
    cards = "".join(
        f'<a class="item" href="/artigos/{_esc(t["slug"])}" style="display:flex;align-items:center;gap:16px">'
        f'<span style="font-size:30px">{_esc(t["emoji"])}</span>'
        f'<span><span class="t">{_esc(t["rotulo"])}</span><br>'
        f'<span class="d">{t["total"]} edi{"ção" if t["total"]==1 else "ções"}</span></span></a>'
        for t in temas)
    corpo = (f'<div class="wrap"><section class="sec"><h2 class="disp">Arquivo por tema</h2>'
             f'<p class="sub">Tudo que você já recebeu, organizado por frente e por data.</p>{cards}</section></div>')
    return _pagina(f"Arquivo · {PRODUTO}", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def lista_tema(meta, digests):
    itens = "".join(
        f'<a class="item" href="/artigos/{_esc(meta["slug"])}/{_esc(d["data"])}">'
        f'<div class="d">{_esc(_data_br(d["data"]))}</div>'
        f'<div class="t">{_esc(d["titulo_pt"])}</div></a>'
        for d in digests) or '<p class="sub">Nenhuma edição neste tema ainda.</p>'
    corpo = (f'<div class="wrap"><div class="crumb"><a href="/artigos">Arquivo</a> › {_esc(meta["rotulo"])}</div>'
             f'<section style="padding-bottom:40px"><h2 class="disp" style="font-size:38px;color:var(--creme)">'
             f'{_esc(meta["emoji"])} {_esc(meta["rotulo"])}</h2>'
             f'<p class="sub">{len(digests)} edi{"ção" if len(digests)==1 else "ções"}</p>{itens}</section></div>')
    return _pagina(f'{meta["rotulo"]} · {PRODUTO}', corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_digest(meta, d):
    try:
        grafico = json.loads(d.get("grafico") or "null")
    except Exception:
        grafico = None
    corpo_doc = (f'<div class="doc">'
                 f'<h1 class="title">{_esc(d["titulo_pt"])}</h1>'
                 f'<div class="meta">{_esc(d.get("fonte",""))} · {_esc(_data_br(d["data"]))} · DOI {_esc(d.get("doi","") or "—")}</div>'
                 f'<div class="corpo">{pdf._resumo_html(d.get("resumo",""))}</div>'
                 f'{pdf._grafico_html(grafico)}{pdf._gancho_html(d.get("gancho",""))}')
    if d.get("url"):
        corpo_doc += f'<div style="margin-top:22px"><a class="docbtn" href="{_esc(d["url"])}" target="_blank" rel="noopener">Ver o estudo original ↗</a></div>'
    corpo_doc += '</div>'
    corpo = (f'<div class="wrap"><div class="crumb">'
             f'<a href="/artigos">Arquivo</a> › <a href="/artigos/{_esc(meta["slug"])}">{_esc(meta["rotulo"])}</a> › {_esc(_data_br(d["data"]))}</div>'
             f'{corpo_doc}</div>')
    return _pagina(f'{d["titulo_pt"]} · {PRODUTO}', corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_minha(sub):
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Minha assinatura</h2>
      <p class="hint">Olá, {_esc(sub.get("nome") or "assinante")}. Sua assinatura está ativa.</p>
      <p style="margin:18px 0"><a class="cta ghost" href="/artigos">Ir para o arquivo</a></p>
      <p class="hint">Para cancelar ou trocar de plano, <a href="{_cta()}" style="color:var(--ouro2)">fale com a gente</a>.</p>
      <p class="hint" style="margin-top:20px"><a href="/sair" style="color:var(--suave)">Sair desta conta</a></p>
    </div></div>"""
    return _pagina(f"Minha assinatura · {PRODUTO}", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def robots_txt():
    return ("User-agent: *\nAllow: /$\nAllow: /\nDisallow: /artigos\nDisallow: /entrar\n"
            "Disallow: /minha\nDisallow: /admin\nDisallow: /revisar\nDisallow: /pdf\n")


_MESES = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _data_br(iso):
    try:
        a, m, dd = iso.split("-")
        return f"{int(dd)} {_MESES[int(m)]} {a}"
    except Exception:
        return iso
