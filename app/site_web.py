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
import pricing

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
.plano .pcard{font-family:system-ui,sans-serif;font-size:12px;color:var(--suave);margin-top:8px}
.planbtn{display:inline-block;margin-top:16px;font-family:system-ui,sans-serif;font-size:13px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#1a1300;background:linear-gradient(180deg,var(--ouro2),var(--ouro));text-decoration:none;padding:10px 26px;border-radius:100px}
.planbtn:hover{filter:brightness(1.06)}
/* login/forms */
.panel{max-width:440px;margin:40px auto;background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.14);
  border-radius:20px;padding:38px 32px}
.panel h2{font-family:"Cormorant Garamond",Georgia,serif;font-size:34px;color:var(--creme);margin-bottom:6px}
.panel p.hint{color:var(--suave);margin-bottom:22px;font-size:15px}
label{display:block;font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--suave);margin-bottom:8px}
input[type=text],input[type=password],input[type=tel]{width:100%;background:rgba(0,0,0,.25);border:1px solid rgba(233,225,198,.2);border-radius:12px;
  color:var(--creme);font-size:20px;font-family:Georgia,serif;padding:14px 16px;margin-bottom:18px;letter-spacing:.04em}
.infobox{background:rgba(201,162,39,.12);border:1px solid rgba(201,162,39,.4);color:var(--creme);border-radius:10px;padding:12px 14px;margin-bottom:16px;font-family:system-ui,sans-serif;font-size:14px}
.candi{display:flex;gap:14px;align-items:flex-start;background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.14);border-radius:12px;padding:14px 16px;margin-bottom:10px;cursor:pointer;transition:.15s}
.candi:hover{border-color:rgba(201,162,39,.55);background:rgba(255,255,255,.06)}
.candi input[type=checkbox]{margin-top:4px;width:20px;height:20px;flex:none;accent-color:var(--ouro);cursor:pointer}
.cbody{display:flex;flex-direction:column;gap:4px}
.ctitle{font-family:"Cormorant Garamond",Georgia,serif;font-size:19px;color:var(--creme);line-height:1.22}
.cperg{font-family:system-ui,sans-serif;font-size:14px;color:var(--ouro2)}
.cmeta{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--suave)}
.actbtn{font-family:system-ui,sans-serif;font-size:13px;font-weight:700;letter-spacing:.03em;color:#1a1300;background:linear-gradient(180deg,var(--ouro2),var(--ouro));border:none;cursor:pointer;padding:11px 22px;border-radius:100px}
.actbtn.ghost{background:transparent;color:var(--creme);border:1px solid rgba(201,162,39,.5)}
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
/* assinar */
.pick{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin:26px 0}
.pick a{text-decoration:none;background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.14);border-radius:16px;padding:22px;text-align:center;transition:.15s}
.pick a:hover{border-color:var(--ouro);background:rgba(255,255,255,.06)}
.pick .nm{font-family:"Cormorant Garamond",Georgia,serif;font-size:24px;color:var(--ouro2)}
.pick .pr{font-size:26px;color:var(--creme);margin:6px 0 2px}
.pick .pe{font-family:system-ui,sans-serif;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--suave)}
.field{margin-bottom:16px}
.field label{margin-bottom:7px}
select{width:100%;background:rgba(0,0,0,.25);border:1px solid rgba(233,225,198,.2);border-radius:12px;color:var(--creme);font-size:16px;font-family:Georgia,serif;padding:13px 14px}
textarea{width:100%;background:rgba(0,0,0,.25);border:1px solid rgba(233,225,198,.2);border-radius:12px;color:var(--creme);font-size:16px;font-family:Georgia,serif;padding:13px 14px;margin-bottom:16px;resize:vertical}
textarea:focus{outline:none;border-color:var(--ouro)}
.pay{display:flex;gap:10px;margin-bottom:8px;flex-wrap:wrap}
.pay label{display:flex;align-items:center;gap:8px;flex:1;min-width:150px;background:rgba(0,0,0,.2);border:1px solid rgba(233,225,198,.18);border-radius:12px;padding:13px 14px;color:var(--creme);text-transform:none;letter-spacing:0;font-family:Georgia,serif;font-size:15px;cursor:pointer;margin:0}
.pay .sub2{display:block;font-family:system-ui,sans-serif;font-size:12px;color:var(--suave)}
.resumo{background:rgba(201,162,39,.1);border:1px solid rgba(201,162,39,.35);border-radius:12px;padding:14px 16px;margin-bottom:20px;font-family:system-ui,sans-serif;font-size:14px;color:var(--creme)}
"""


def _esc(s):
    return _html.escape(str(s or ""))


def _cta():
    return _esc(config.cta_url())


def _topbar(logado=False):
    direita = ('<a href="/artigos">Arquivo</a> <a href="/minha">Minha conta</a>'
               if logado else '<a href="/entrar">Entrar</a>')
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
        f'<div class="pe">Pix · {_esc(p["periodo"])}</div>'
        + (f'<div class="pn">{_esc(p["nota"])}</div>' if p.get("nota") else "")
        + f'<a class="planbtn" href="/assinar?plano={_esc(p["slug"])}">Assinar</a>'
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
          <form method="post" action="/entrar-codigo">
            <input type="hidden" name="etapa" value="codigo">
            <input type="hidden" name="whatsapp" value="{_esc(whatsapp)}">
            <label>Código</label>
            <input type="text" name="codigo" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000" autofocus>
            <button class="cta" type="submit">Entrar</button>
          </form>
          <p class="hint" style="margin-top:16px"><a href="/entrar-codigo" style="color:var(--ouro2)">Usar outro número</a> &nbsp;·&nbsp; <a href="/entrar" style="color:var(--suave)">Entrar com senha</a></p>
        </div></div>"""
    else:
        corpo = f"""
        <div class="wrap"><div class="panel">
          <h2 class="disp">Entrar com código</h2>
          <p class="hint">Sem acesso à senha? Informe o WhatsApp da sua assinatura e enviamos um código de acesso.</p>
          {erro_html}
          <form method="post" action="/entrar-codigo">
            <input type="hidden" name="etapa" value="numero">
            <label>WhatsApp (com DDD)</label>
            <input type="text" name="whatsapp" inputmode="tel" placeholder="(43) 99999-0000" autofocus>
            <button class="cta" type="submit">Enviar código</button>
          </form>
          <p class="hint" style="margin-top:16px"><a href="/entrar" style="color:var(--ouro2)">← Entrar com senha</a></p>
        </div></div>"""
    return _pagina(f"Entrar · {PRODUTO}", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')


def pagina_login(erro="", sem_senha=False, whatsapp=""):
    """Tela de login principal: WhatsApp + senha (não depende do WhatsApp p/ entrar)."""
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    if sem_senha:
        erro_html += ('<div class="infobox">Você ainda não criou sua senha. Clique em '
                      '<strong>Primeiro acesso / criar senha</strong> abaixo — enviaremos um link por e-mail.</div>')
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Área do assinante</h2>
      <p class="hint">Entre com o WhatsApp da sua assinatura e sua senha.</p>
      {erro_html}
      <form method="post" action="/entrar">
        <label>WhatsApp (com DDD)</label>
        <input type="text" name="whatsapp" inputmode="tel" value="{_esc(whatsapp)}" placeholder="(43) 99999-0000" autofocus>
        <label>Senha</label>
        <input type="password" name="senha" placeholder="sua senha">
        <button class="cta" type="submit">Entrar</button>
      </form>
      <p class="hint" style="margin-top:16px">
        <a href="/primeiro-acesso" style="color:var(--ouro2)">Primeiro acesso / criar senha</a>
        &nbsp;·&nbsp;
        <a href="/esqueci" style="color:var(--suave)">Esqueci minha senha</a>
      </p>
      <p class="hint" style="margin-top:8px;font-size:13px"><a href="/entrar-codigo" style="color:var(--suave)">Problemas? Entrar com código no WhatsApp</a></p>
      <p class="hint" style="margin-top:14px">Ainda não assina? <a href="/" style="color:var(--ouro2)">Conheça o plano</a>.</p>
    </div></div>"""
    return _pagina(f"Entrar · {PRODUTO}", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')


def pagina_recuperar(motivo="esqueci", erro=""):
    """Formulário de 1º acesso / esqueci a senha (informa WhatsApp → link por e-mail)."""
    primeiro = (motivo == "primeiro")
    titulo = "Primeiro acesso" if primeiro else "Esqueci minha senha"
    acao = "/primeiro-acesso" if primeiro else "/esqueci"
    hint = ("Informe o WhatsApp da sua assinatura. Enviaremos um link por e-mail para você "
            + ("criar sua senha de acesso." if primeiro else "redefinir sua senha."))
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">{titulo}</h2>
      <p class="hint">{hint}</p>
      {erro_html}
      <form method="post" action="{acao}">
        <label>WhatsApp (com DDD)</label>
        <input type="text" name="whatsapp" inputmode="tel" placeholder="(43) 99999-0000" autofocus>
        <button class="cta" type="submit">Enviar link</button>
      </form>
      <p class="hint" style="margin-top:16px"><a href="/entrar" style="color:var(--ouro2)">← voltar ao login</a></p>
    </div></div>"""
    return _pagina(f"{titulo} · {PRODUTO}", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')


def pagina_criar_senha(token, erro=""):
    """Tela de definir a senha (aberta pelo link tokenizado)."""
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Crie sua senha</h2>
      <p class="hint">Escolha uma senha com pelo menos 6 caracteres, incluindo letra e número.</p>
      {erro_html}
      <form method="post" action="/criar-senha">
        <input type="hidden" name="token" value="{_esc(token)}">
        <label>Nova senha</label>
        <input type="password" name="senha" autofocus>
        <label>Repita a senha</label>
        <input type="password" name="senha2">
        <button class="cta" type="submit">Salvar e entrar</button>
      </form>
    </div></div>"""
    return _pagina(f"Criar senha · {PRODUTO}", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')


def pagina_msg(titulo, texto, logado=False):
    """Mensagem neutra (confirmação de envio, link inválido, etc.)."""
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">{_esc(titulo)}</h2>
      <p class="hint">{_esc(texto)}</p>
      <p style="margin-top:18px"><a class="cta ghost" href="/entrar">Voltar para o login</a></p>
    </div></div>"""
    return _pagina(f"{titulo} · {PRODUTO}", corpo, logado=logado, meta_extra='<meta name="robots" content="noindex">')


def pagina_admin(assinantes, token=""):
    """Tela de Assinantes no padrão do site (verde/dourado, tabela com status)."""
    import phone
    tk = _esc(token)
    admins = {phone.normalizar(w) for w in (config.ADMIN_WHATSAPPS or [])}
    def badge(st):
        cor = {"ATIVO": "#2f9e6b", "INADIMPLENTE": "#c9a227", "CANCELADO": "#c0562f"}.get(st, "#7a8a84")
        return (f'<span style="font-family:system-ui;font-size:11px;font-weight:700;letter-spacing:.05em;'
                f'padding:4px 11px;border-radius:100px;background:{cor}22;color:{cor};border:1px solid {cor}66">'
                f'{_esc(st or "—")}</span>')
    def cel_curador(s):
        eh_admin = phone.normalizar(s.get("whatsapp", "")) in admins
        if eh_admin:
            return ('<span style="font-family:system-ui;font-size:11px;font-weight:700;letter-spacing:.05em;'
                    'padding:4px 11px;border-radius:100px;background:#c9a22722;color:var(--ouro2);'
                    'border:1px solid #c9a22766">★ sempre</span>')
        ativo = bool(s.get("curador"))
        prox = "0" if ativo else "1"
        rotulo = "✔ curador" if ativo else "tornar curador"
        cls = "actbtn" if ativo else "actbtn ghost"
        return (f'<form method="post" action="/admin" style="margin:0">'
                f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="curador">'
                f'<input type="hidden" name="id" value="{_esc(s.get("id"))}">'
                f'<input type="hidden" name="on" value="{prox}">'
                f'<button class="{cls}" style="padding:6px 13px;font-size:12px">{rotulo}</button></form>')
    linhas = "".join(
        '<tr style="border-top:1px solid rgba(233,225,198,.1)">'
        f'<td style="padding:13px 10px;font-family:\'Cormorant Garamond\',Georgia,serif;font-size:18px;color:var(--creme)">{_esc(s.get("nome") or "—")}</td>'
        f'<td style="padding:13px 10px;font-family:ui-monospace,Menlo,monospace;font-size:13px;color:var(--suave)">{_esc(s.get("whatsapp") or "—")}</td>'
        f'<td style="padding:13px 10px;font-size:13px;color:var(--suave)">{_esc(s.get("email") or "—")}</td>'
        f'<td style="padding:13px 10px;font-size:13px;color:var(--ouro2)">{_esc(s.get("plano") or "—")}</td>'
        f'<td style="padding:13px 10px">{badge(s.get("status"))}</td>'
        f'<td style="padding:13px 10px;font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--suave)">{_esc(s.get("proximo_vencimento") or "—")}</td>'
        f'<td style="padding:13px 10px">{cel_curador(s)}</td>'
        f'<td style="padding:13px 10px"><form method="post" action="/admin" style="margin:0">'
        f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="remover">'
        f'<input type="hidden" name="id" value="{_esc(s.get("id"))}">'
        f'<button class="actbtn ghost" style="padding:6px 13px;font-size:12px">remover</button></form></td></tr>'
        for s in assinantes)
    ativos = sum(1 for s in assinantes if s.get("status") == "ATIVO")
    n_cur = sum(1 for s in assinantes if s.get("curador"))
    corpo = f"""
    <div class="wrap">
      <div class="sectag" style="margin-top:8px">Painel do curador</div>
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:2px 0 4px">Assinantes</h2>
      <p class="hint">{len(assinantes)} no total · {ativos} ativos · {n_cur} curador(es) &nbsp;·&nbsp; <a href="/curadoria" style="color:var(--ouro2)">🔬 ir para a Curadoria</a></p>
      <div class="infobox" style="margin:14px 0"><strong>Curadoria:</strong> quem estiver marcado como <strong>curador</strong> recebe, todo dia útil às <strong>18h</strong>, o resumo do dia com o link para revisar/aprovar antes do envio das 8h. Você (admin) recebe <em>sempre</em>. Marque um médico convidado aqui para ele ajudar na revisão.</div>
      <div style="overflow-x:auto;margin:18px 0">
        <table style="width:100%;border-collapse:collapse;min-width:820px">
          <thead><tr style="font-family:system-ui;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--suave);text-align:left">
            <th style="padding:8px 10px">Nome</th><th style="padding:8px 10px">WhatsApp</th><th style="padding:8px 10px">E-mail</th>
            <th style="padding:8px 10px">Plano</th><th style="padding:8px 10px">Status</th><th style="padding:8px 10px">Vencimento</th><th style="padding:8px 10px">Curadoria</th><th></th></tr></thead>
          <tbody>{linhas or '<tr><td colspan="8" style="padding:22px;color:var(--suave)">Nenhum assinante ainda.</td></tr>'}</tbody>
        </table>
      </div>
      <div class="panel" style="max-width:520px;margin:10px 0">
        <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:10px">Adicionar cortesia</h3>
        <form method="post" action="/admin">
          <input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="adicionar">
          <label>Nome</label><input type="text" name="nome">
          <label>WhatsApp (com DDD)</label><input type="text" name="whatsapp" placeholder="(43) 99999-0000">
          <button class="actbtn" type="submit" style="margin-top:14px">Adicionar</button>
        </form>
      </div>
    </div>"""
    return _pagina("Assinantes · Admin", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


# ── Curadoria / Reserva (admin, token) — banco privado, NÃO publica no arquivo ──
def pagina_curadoria(candidatos, reserva, contagem, token, msg=""):
    from collections import OrderedDict
    tok = _esc(token)
    grupos = OrderedDict()
    for c in candidatos:
        grupos.setdefault(c.get("tema", "—"), []).append(c)
    stats = (f'{contagem.get("novo", 0)} novos · {contagem.get("selecionado", 0)} selecionados · '
             f'{contagem.get("resumido", 0)} já resumidos · {len(reserva)} na reserva')
    msg_html = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""
    acoes = f"""
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 22px">
        <form method="post" action="/curadoria" onsubmit="return confirm('Rodar a varredura de 2026 no Europe PMC (Haiku)? Pode levar 1–2 min.')">
          <input type="hidden" name="token" value="{tok}"><input type="hidden" name="acao" value="varrer">
          <button class="actbtn" type="submit">🔎 Rodar varredura 2026</button>
        </form>
        <form method="post" action="/curadoria" onsubmit="return confirm('Gerar os resumos (padrão de qualidade) dos selecionados? Usa IA.')">
          <input type="hidden" name="token" value="{tok}"><input type="hidden" name="acao" value="gerar">
          <button class="actbtn ghost" type="submit">✍️ Gerar resumos dos selecionados</button>
        </form>
      </div>"""
    blocos = []
    for tema, lst in grupos.items():
        itens = "".join(
            f'<label class="candi">'
            f'<input type="checkbox" name="sel" value="{_esc(c.get("id"))}"{" checked" if c.get("status") == "selecionado" else ""}>'
            f'<span class="cbody"><span class="ctitle">{_esc(c.get("titulo"))}</span>'
            f'<span class="cperg">❓ {_esc(c.get("pergunta") or "—")}</span>'
            f'<span class="cmeta">{_esc(c.get("fonte", ""))} · {_esc(c.get("data", ""))} · score {_esc(round(float(c.get("score") or 0), 1))}'
            f'{" · DOI " + _esc(c.get("doi")) if c.get("doi") else ""}</span></span></label>'
            for c in lst)
        emoji = {"Obesidade": "⚖️", "Hormonal": "⚕️", "Lipedema": "🦵", "Performance": "🏃", "Longevidade": "🧬"}.get(tema, "•")
        blocos.append(f'<div class="sectag" style="margin-top:24px">{emoji} {_esc(tema)} · {len(lst)}</div>{itens}')
    lista = "".join(blocos) or '<p class="hint">Nenhum candidato ainda. Clique em <strong>Rodar varredura 2026</strong>.</p>'
    form_lista = f"""
      <form method="post" action="/curadoria">
        <input type="hidden" name="token" value="{tok}"><input type="hidden" name="acao" value="selecionar">
        {lista}
        <div style="position:sticky;bottom:0;padding:14px 0;margin-top:8px;background:linear-gradient(0deg,var(--verde) 40%,transparent)">
          <button class="actbtn" type="submit">💾 Salvar seleção</button>
        </div>
      </form>"""
    res_html = "".join(
        f'<div class="item"><div class="d">{_esc(r.get("tema"))}</div><div class="t">{_esc(r.get("titulo_pt"))}</div></div>'
        for r in reserva) or '<p class="hint">Reserva vazia. Selecione candidatos e clique em <strong>Gerar resumos</strong>.</p>'
    add_form = f"""
      <div class="panel" style="max-width:none;margin:0 0 24px">
        <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:25px;color:var(--ouro2);margin-bottom:6px">➕ Adicionar meu estudo</h3>
        <p class="hint" style="margin-bottom:14px">Sobe o PDF (ou cola o texto). Gero o resumo e ele entra na <strong>fila, na frente</strong> — vai pros assinantes no próximo dia útil (com seu review das 18h).</p>
        <form method="post" action="/curadoria" enctype="multipart/form-data">
          <input type="hidden" name="token" value="{tok}">
          <label>PDF do estudo</label>
          <input type="file" name="pdf" accept="application/pdf" style="color:var(--suave);font-family:system-ui,sans-serif;margin-bottom:14px">
          <label>…ou cole o texto/resumo (se não tiver PDF)</label>
          <textarea name="texto" rows="3" placeholder="Cole aqui o abstract/texto do estudo…"></textarea>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <input type="text" name="fonte" placeholder="Revista (opcional)" style="flex:1">
            <input type="text" name="doi" placeholder="DOI (opcional)" style="flex:1">
          </div>
          <button class="actbtn" type="submit" style="margin-top:14px">Gerar resumo e adicionar à fila</button>
        </form>
      </div>"""
    corpo = f"""
    <div class="wrap">
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:10px 0 4px">Curadoria · Reserva 2026</h2>
      <p class="hint">{stats}</p>
      {msg_html}{acoes}{add_form}
      <p class="hint">Leia o <strong>título</strong> + a <strong>pergunta</strong> e marque os que valem resumir. Nada vai pro arquivo dos assinantes — é sua reserva privada.</p>
      {form_lista}
      <section class="sec"><h2 class="disp" style="font-size:30px">Reserva pronta</h2>{res_html}</section>
    </div>"""
    return _pagina("Curadoria · Reserva", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')


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


def pagina_minha(sub, admin=False):
    admin_html = ('<div class="infobox" style="margin:16px 0"><strong>Painel do curador</strong><br>'
                  '<a href="/curadoria" style="color:var(--ouro2)">🔬 Curadoria / Reserva</a> &nbsp;·&nbsp; '
                  '<a href="/admin" style="color:var(--ouro2)">👥 Assinantes</a></div>') if admin else ""
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Minha assinatura</h2>
      <p class="hint">Olá, {_esc(sub.get("nome") or "assinante")}. Sua assinatura está ativa.</p>
      {admin_html}
      <p style="margin:18px 0"><a class="cta ghost" href="/artigos">Ir para o arquivo</a></p>
      <p class="hint" style="margin-top:20px"><a href="/sair" style="color:var(--suave)">Sair desta conta</a>
       &nbsp;·&nbsp; <a href="/cancelar" style="color:var(--suave)">Cancelar assinatura</a></p>
    </div></div>"""
    return _pagina(f"Minha assinatura · {PRODUTO}", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_cancelar(erro=""):
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Cancelar assinatura</h2>
      <p class="hint">Que pena que você quer sair. Antes, conta o motivo — é o que nos ajuda a melhorar o produto.</p>
      {erro_html}
      <form method="post" action="/cancelar">
        <label>Por que está cancelando? (obrigatório)</label>
        <textarea name="motivo" rows="4" required placeholder="Escreva aqui..."></textarea>
        <button class="cta" type="submit">Continuar</button>
      </form>
      <p class="hint" style="margin-top:14px"><a href="/minha" style="color:var(--ouro2)">← voltar, quero continuar assinante</a></p>
    </div></div>"""
    return _pagina(f"Cancelar · {PRODUTO}", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_cancelar_oferta(motivo):
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Espera — um presente antes de você ir 🎁</h2>
      <p class="hint">Que tal <strong>mais um mês por nossa conta</strong>? Sem cobrança agora: você continua
      recebendo os estudos e decide com calma depois.</p>
      <form method="post" action="/cancelar/confirmar">
        <input type="hidden" name="motivo" value="{_esc(motivo)}">
        <button class="cta" type="submit" name="acao" value="aceitar">Quero meu mês grátis</button>
        <button class="cta" type="submit" name="acao" value="cancelar"
          style="margin-top:12px;background:transparent;color:var(--suave);border:1px solid rgba(233,225,198,.25);box-shadow:none">
          Não, pode cancelar mesmo assim</button>
      </form>
    </div></div>"""
    return _pagina(f"Cancelar · {PRODUTO}", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_oferta_aceita():
    corpo = ('<div class="wrap"><div class="panel">'
             '<h2 class="disp">Presente aplicado 🎁</h2>'
             '<p class="hint">Você ganhou <strong>+30 dias</strong> por nossa conta — sem cobrança agora. '
             'Continua tudo no ar. Que bom que você ficou!</p>'
             '<p style="margin-top:18px"><a class="cta ghost" href="/artigos">Ir para o arquivo</a></p>'
             '</div></div>')
    return _pagina(f"Obrigado · {PRODUTO}", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_cancelado(acesso_ate=""):
    ate = f" Seu acesso continua até <strong>{_esc(_data_br(acesso_ate))}</strong>." if acesso_ate else ""
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Assinatura cancelada</h2>
      <p class="hint">Pronto — não haverá novas cobranças.{ate} Enviamos um e-mail de confirmação.</p>
      <p class="hint">Mudou de ideia? <a href="/assinar" style="color:var(--ouro2)">Assine de novo quando quiser</a>.</p>
      <p style="margin-top:16px"><a href="/sair" style="color:var(--suave)">Sair</a></p>
    </div></div>"""
    return _pagina(f"Cancelado · {PRODUTO}", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


# ── Assinatura (checkout) ──
def _pick_planos():
    cards = "".join(
        f'<a href="/assinar?plano={_esc(p["slug"])}"><div class="nm">{_esc(p["nome"])}</div>'
        f'<div class="pr">{_esc(p["preco"])}</div><div class="pe">{_esc(p["periodo"])}</div></a>'
        for p in config.PLANOS)
    return (f'<div class="wrap"><section class="sec"><h2 class="disp">Escolha seu plano</h2>'
            f'<p class="sub">O mensal renova sozinho (cancela quando quiser). Os planos maiores '
            f'saem mais barato por mês.</p><div class="pick">{cards}</div>'
            f'<p class="hint">Já é assinante? <a href="/entrar" style="color:var(--ouro2)">Entrar</a></p>'
            f'</section></div>')


def pagina_assinar(plano_slug=None, erro=""):
    plano = config.plano_por_slug(plano_slug) if plano_slug else None
    if not plano:
        return _pagina(f"Assinar · {PRODUTO}", _pick_planos(), logado=False,
                       meta_extra='<meta name="robots" content="noindex">')
    base = float(plano["base"])
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    pix_lab = f"Pix à vista · {pricing.fmt_brl(base)} (não renova)"
    if plano.get("recorrente_pix"):   # mensal (sem parcelamento)
        cartao_lab = f"Cartão · {pricing.fmt_brl(pricing.valor_cartao(base,1))}/mês (renova todo mês)"
        parcelas_html = '<input type="hidden" name="parcelas" value="1">'
    else:
        cartao_lab = "Cartão · renova no fim do período (parcelável)"
        opts = "".join(
            f'<option value="{o["parcelas"]}">{o["parcelas"]}x de {pricing.fmt_brl(o["por_parcela"])} '
            f'— total {pricing.fmt_brl(o["total"])}</option>' for o in pricing.opcoes_parcelas(base))
        parcelas_html = (f'<div class="field"><label>Parcelas (só no cartão)</label>'
                         f'<select name="parcelas">{opts}</select></div>')
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Assinar — {_esc(plano["nome"])}</h2>
      <div class="resumo">Plano {_esc(plano["nome"])} · {_esc(plano["periodo"])} · Pix {_esc(plano["preco"])}</div>
      {erro_html}
      <form method="post" action="/assinar">
        <input type="hidden" name="plano" value="{_esc(plano["slug"])}">
        <div class="field"><label>Nome completo</label><input type="text" name="nome" required></div>
        <div class="field"><label>E-mail</label><input type="text" name="email" inputmode="email" required></div>
        <div class="field"><label>CPF</label><input type="text" name="cpf" inputmode="numeric" required></div>
        <div class="field"><label>WhatsApp (com DDD) — é onde você recebe os artigos e faz login</label>
          <input type="text" name="whatsapp" inputmode="tel" placeholder="(43) 99999-0000" required></div>
        <label>Forma de pagamento</label>
        <div class="pay">
          <label><input type="radio" name="metodo" value="PIX" checked><span>{_esc(pix_lab)}</span></label>
          <label><input type="radio" name="metodo" value="CARTAO"><span>{_esc(cartao_lab)}</span></label>
        </div>
        {parcelas_html}
        <div class="field"><label>Cupom (opcional)</label><input type="text" name="cupom" placeholder="tem um cupom de cortesia?"></div>
        <button class="cta" type="submit">Continuar para o pagamento</button>
      </form>
      <p class="hint" style="margin-top:14px"><a href="/assinar" style="color:var(--suave)">← trocar de plano</a></p>
    </div></div>"""
    return _pagina(f"Assinar {plano['nome']} · {PRODUTO}", corpo, logado=False,
                   meta_extra='<meta name="robots" content="noindex">')


def pagina_obrigado():
    corpo = ('<div class="wrap"><div class="panel">'
             '<h2 class="disp">Quase lá!</h2>'
             '<p class="hint">Recebemos seu pedido. Assim que o pagamento for confirmado, '
             'seu acesso chega no <strong>WhatsApp</strong> que você informou — e a partir do próximo '
             'dia útil começam a chegar os resumos. Pode fechar esta página.</p>'
             '<p style="margin-top:18px"><a class="cta ghost" href="/entrar">Já recebi meu acesso</a></p>'
             '</div></div>')
    return _pagina(f"Obrigado · {PRODUTO}", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')


def robots_txt():
    return ("User-agent: *\nAllow: /$\nAllow: /\nDisallow: /artigos\nDisallow: /entrar\n"
            "Disallow: /minha\nDisallow: /assinar\nDisallow: /obrigado\nDisallow: /admin\n"
            "Disallow: /revisar\nDisallow: /pdf\n")


_MESES = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _data_br(iso):
    try:
        a, m, dd = iso.split("-")
        return f"{int(dd)} {_MESES[int(m)]} {a}"
    except Exception:
        return iso
