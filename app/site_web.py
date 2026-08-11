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
import ui

MARCA = "Dr. Diego Silva"
CRM = "CRM-PR 54310"
PRODUTO = "Atualização Científica"

# Favicon SVG (verde-escuro + monograma dourado). Servido em /favicon.svg e /favicon.ico.
FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='14' fill='#0e211a'/>"
    "<text x='32' y='43' text-anchor='middle' font-family='Georgia,\"Times New Roman\",serif' "
    "font-size='36' font-weight='700' fill='#e7c766'>D</text>"
    "<rect x='21' y='49' width='22' height='3' rx='1.5' fill='#c9a227'/></svg>")

_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&display=swap" rel="stylesheet">')

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  /* legado (telas de login/checkout/curadoria/digest usam estes nomes) */
  --verde:#0e211a;--verde2:#14332a;--verde3:#1e5045;--ouro:#c9a227;--ouro2:#e7c766;
  --creme:#f4f1e7;--creme2:#ece4c6;--texto:#e8efe9;--suave:#a9bcb2;
  /* redesign */
  --ink:#0a1712;--g900:#0e211a;--g800:#14332a;--g700:#1e5045;--g600:#2c6656;
  --gold:#c9a227;--gold2:#e7c766;--cream:#f4f1e7;--paper:#f7f4ec;--inkpaper:#16302a;
  --muted:#9fb3a9;--line:rgba(233,225,198,.14);
  /* score-chip (severidade semântica: alto/médio/baixo — cores deliberadas, não decorativas) */
  --score-hi-bg1:#22705a;--score-hi-bg2:#1a5344;--score-hi-tx:#eafaf3;--score-hi-bd:rgba(127,208,173,.5);
  --score-md-bg:rgba(201,162,39,.16);--score-md-tx:var(--ouro2);--score-md-bd:rgba(201,162,39,.45);
  --score-lo-bg:rgba(255,255,255,.05);--score-lo-tx:var(--suave);--score-lo-bd:rgba(233,225,198,.16);
  --disp:"Hoefler Text","Iowan Old Style","Cormorant Garamond",Georgia,serif;
  --body:Georgia,"Times New Roman",serif;--ui:system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace}
html{scroll-behavior:smooth}
body{background:
    radial-gradient(120% 80% at 82% -8%,#1c4638 0%,rgba(14,33,26,0) 55%),
    radial-gradient(90% 60% at 0% 0%,#123027 0%,rgba(10,23,18,0) 50%),
    var(--ink);
  color:var(--cream);font-family:var(--body);line-height:1.65;min-height:100vh;-webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.05;
  background-image:radial-gradient(rgba(255,255,255,.5) .5px,transparent .5px);background-size:3px 3px}
.disp{font-family:var(--disp);font-weight:600;line-height:1.08;letter-spacing:-.01em}
.wrap{max-width:1200px;margin:0 auto;padding:0 28px;position:relative;z-index:1}
a{color:inherit;text-decoration:none}
.mono{font-family:var(--mono)}
/* top bar */
.top{display:flex;align-items:center;justify-content:space-between;padding:24px 0;gap:14px;flex-wrap:wrap}
.brand{display:flex;flex-direction:column;line-height:1.13}
.brand .m{font-family:var(--disp);font-size:23px;color:var(--cream);font-weight:700}
.brand .c{font-family:var(--ui);font-size:9.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted)}
.nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.nav a{font-family:var(--ui);font-size:12.5px;letter-spacing:.05em;color:var(--cream);padding:9px 15px;border-radius:100px;transition:.18s}
.nav a.pill{border:1px solid rgba(201,162,39,.55)}
.nav a.pill:hover{background:var(--gold);color:#1a1300;border-color:var(--gold)}
.nav a.plain:hover{color:var(--gold2)}
.nav a.here{color:var(--gold2)}
/* hero */
.hero{display:grid;grid-template-columns:1.05fr .95fr;gap:44px;align-items:center;padding:40px 0 30px}
.eyebrow{font-family:var(--ui);font-size:11.5px;letter-spacing:.3em;text-transform:uppercase;color:var(--gold2);margin-bottom:16px}
.hero h1{font-size:clamp(42px,6.2vw,76px);color:var(--cream);text-wrap:balance;margin:6px 0 20px}
.hero h1 em{font-style:normal;color:var(--gold2)}
.lead{font-size:19.5px;color:var(--muted);max-width:34ch;margin-bottom:26px}
.ctas{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.btn{font-family:var(--ui);font-weight:700;font-size:15px;letter-spacing:.01em;padding:15px 30px;border-radius:100px;transition:.18s;display:inline-block}
.btn.solid{background:linear-gradient(180deg,var(--gold2),var(--gold));color:#1a1300;box-shadow:0 12px 30px -10px rgba(201,162,39,.55)}
.btn.solid:hover{transform:translateY(-2px);box-shadow:0 18px 40px -10px rgba(201,162,39,.65)}
.btn.ghost{color:var(--cream);border:1px solid rgba(201,162,39,.5)}
.btn.ghost:hover{border-color:var(--gold);color:var(--gold2)}
button.btn{border:none;cursor:pointer}
.trust{margin-top:20px;font-family:var(--ui);font-size:12.5px;color:var(--muted);display:flex;gap:8px;align-items:center}
.trust b{color:var(--cream);font-weight:600}
/* sample dispatch (papel) */
.dispatch{background:var(--paper);color:var(--inkpaper);border-radius:14px;padding:26px 28px;
  box-shadow:0 30px 70px -24px rgba(0,0,0,.7);position:relative;transform:rotate(.5deg)}
.dtag{display:inline-flex;align-items:center;gap:7px;background:var(--g800);color:var(--gold2);
  font-family:var(--ui);font-size:10.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;padding:5px 11px;border-radius:100px}
.dmeta{font-family:var(--mono);font-size:11.5px;color:#6f7d78;margin:14px 0 6px;border-bottom:2px solid var(--gold);padding-bottom:10px;letter-spacing:.02em}
.dtitle{font-family:var(--disp);font-size:26px;line-height:1.14;color:var(--g800);margin:12px 0 10px}
.dbody{font-size:15px;color:#33443e}.dbody p{margin:.55em 0}
.dispatch .chart{margin:16px 0 6px;background:none;border:none;padding:0}
.crow{display:flex;align-items:center;gap:10px;margin:7px 0}
.clab{width:88px;font-family:var(--ui);font-size:12px;color:#3a4c46;flex:none}
.ctrack{flex:1;background:#e6e0d0;border-radius:100px;height:16px;overflow:hidden}
.cfill{height:100%;border-radius:100px;background:linear-gradient(90deg,var(--g700),var(--g600))}
.cval{font-family:var(--mono);font-size:12px;font-weight:700;width:56px;text-align:right;flex:none;color:var(--g800)}
.hook{margin-top:14px;border:1.5px solid var(--gold);border-radius:11px;background:linear-gradient(180deg,#fff8e8,#fbf2d6);padding:13px 15px}
.hook .hl{font-family:var(--ui);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:#8a6a06;font-weight:800;margin-bottom:5px}
.hook .ht{font-size:14.5px;color:#3a2f10;font-style:italic}
/* seções */
.sec{padding:54px 0;border-top:1px solid var(--line)}
.sec h2{font-size:clamp(28px,4vw,42px);color:var(--cream);margin-bottom:10px}
.sec .sub{color:var(--muted);margin-bottom:30px;max-width:56ch;font-size:17px}
.sectag{font-family:var(--ui);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:var(--gold2);margin-bottom:14px}
/* themes strip */
.themes{display:grid;grid-template-columns:repeat(5,1fr);gap:16px}
.theme{background:rgba(255,255,255,.035);border:1px solid var(--line);border-radius:16px;padding:26px 20px;transition:.18s;display:block}
.theme:hover{border-color:rgba(201,162,39,.5);transform:translateY(-3px);background:rgba(255,255,255,.06)}
.theme .e{font-size:26px}
.theme .t{font-family:var(--disp);font-size:19px;color:var(--cream);margin-top:8px;line-height:1.15}
.theme .n{font-family:var(--ui);font-size:11px;color:var(--muted);margin-top:3px}
/* value bento */
.bento{display:grid;grid-template-columns:repeat(6,1fr);gap:20px}
.card{background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:18px;padding:32px 30px}
.card h3{font-family:var(--disp);font-size:24px;color:var(--cream);margin-bottom:8px}
.card p{color:var(--muted);font-size:15px}
.card .k{font-family:var(--mono);font-size:12px;color:var(--gold2);letter-spacing:.04em;margin-bottom:12px;display:block}
.c-a{grid-column:span 2}.c-b{grid-column:span 2}.c-c{grid-column:span 2}.c-d{grid-column:span 2}.c-e{grid-column:span 2}.c-f{grid-column:span 2}
.card.big{background:linear-gradient(150deg,rgba(30,80,69,.5),rgba(20,51,42,.35));border-color:rgba(201,162,39,.25)}
/* planos (redesign) */
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,300px));justify-content:center;gap:18px}
.plan{background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:18px;padding:34px 24px;text-align:center;position:relative;transition:.18s;display:block}
.plan:hover{transform:translateY(-4px);border-color:rgba(201,162,39,.5)}
.plan.best{border-color:var(--gold);background:linear-gradient(160deg,rgba(201,162,39,.14),rgba(20,51,42,.4))}
.plan .badge{position:absolute;top:-11px;left:50%;transform:translateX(-50%);background:linear-gradient(180deg,var(--gold2),var(--gold));color:#1a1300;font-family:var(--ui);font-size:10px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;padding:5px 13px;border-radius:100px}
.plan .nm{font-family:var(--disp);font-size:25px;color:var(--gold2)}
.plan .pr{font-size:34px;color:var(--cream);margin:8px 0 0}
.plan .pe{font-family:var(--ui);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-top:2px}
.plan .pn{font-family:var(--ui);font-size:12.5px;color:var(--gold2);margin-top:12px}
.plan .pick2{display:inline-block;margin-top:16px;font-family:var(--ui);font-size:12.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#1a1300;background:linear-gradient(180deg,var(--gold2),var(--gold));padding:10px 24px;border-radius:100px}
/* autoridade */
.auth{display:flex;gap:26px;align-items:center;flex-wrap:wrap;background:rgba(255,255,255,.035);border:1px solid var(--line);border-radius:18px;padding:26px 30px}
.auth .big{font-family:var(--disp);font-size:clamp(26px,3.4vw,38px);color:var(--cream);flex:1;min-width:280px;line-height:1.2}
.auth .big em{font-style:normal;color:var(--gold2)}
.auth .sig{font-family:var(--ui);font-size:13px;color:var(--muted);text-align:right}
.auth .sig b{display:block;font-family:var(--disp);font-size:22px;color:var(--cream);font-weight:700}
/* chip/plano legado (mantidos p/ compat) */
.chip{display:flex;align-items:center;gap:12px;background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.chip .e{font-size:26px}.chip .t{font-family:var(--disp);font-size:20px;color:var(--cream)}.chip .n{font-family:var(--ui);font-size:12px;color:var(--muted)}
.plano{position:relative;text-align:center}
.plano .nm{font-family:var(--disp);font-size:26px;color:var(--gold2);margin-bottom:4px}
.plano .pr{font-size:30px;color:var(--cream);margin:8px 0 2px}
.plano .pe{font-family:var(--ui);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.plano .pn{font-family:var(--ui);font-size:12.5px;color:var(--gold2);margin-top:10px}
/* login/forms */
.panel{max-width:440px;margin:40px auto;background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.14);
  border-radius:20px;padding:38px 32px}
.panel h2{font-family:"Cormorant Garamond",Georgia,serif;font-size:34px;color:var(--creme);margin-bottom:6px}
.panel p.hint{color:var(--suave);margin-bottom:22px;font-size:15px}
.plabel{font-family:system-ui,sans-serif;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ouro2)}
label{display:block;font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--suave);margin-bottom:8px}
input[type=text],input[type=password],input[type=tel]{width:100%;background:rgba(0,0,0,.25);border:1px solid rgba(233,225,198,.2);border-radius:12px;
  color:var(--creme);font-size:20px;font-family:Georgia,serif;padding:14px 16px;margin-bottom:18px;letter-spacing:.04em}
.infobox{background:rgba(201,162,39,.12);border:1px solid rgba(201,162,39,.4);color:var(--creme);border-radius:10px;padding:12px 14px;margin-bottom:16px;font-family:system-ui,sans-serif;font-size:14px}
.curgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:6px 0 4px}
.curbtn{display:flex;gap:12px;align-items:flex-start;text-decoration:none;background:rgba(201,162,39,.06);
  border:1px solid rgba(201,162,39,.28);border-radius:14px;padding:14px 15px;color:var(--creme);
  transition:transform .14s,border-color .14s,background .14s}
.curbtn:hover{transform:translateY(-2px);border-color:rgba(201,162,39,.65);background:rgba(201,162,39,.12)}
.curbtn:focus-visible{outline:2px solid var(--ouro2);outline-offset:2px}
.curbtn .ic{font-size:20px;line-height:1.1;flex:none}
.curbtn .nm{font-family:system-ui,sans-serif;font-size:14.5px;font-weight:700;color:var(--creme);display:block;margin-bottom:2px}
.curbtn .ds{font-family:system-ui,sans-serif;font-size:12px;color:var(--suave);line-height:1.4;display:block}
@media(max-width:520px){.curgrid{grid-template-columns:1fr}}
.candi{display:flex;gap:14px;align-items:flex-start;background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.14);border-radius:12px;padding:14px 16px;margin-bottom:10px;cursor:pointer;transition:.15s}
.candi:hover{border-color:rgba(201,162,39,.55);background:rgba(255,255,255,.06)}
.candi input[type=checkbox]{margin-top:4px;width:20px;height:20px;flex:none;accent-color:var(--ouro);cursor:pointer}
.cbody{display:flex;flex-direction:column;gap:4px}
.ctitle{font-family:"Cormorant Garamond",Georgia,serif;font-size:19px;color:var(--creme);line-height:1.22}
.cperg{font-family:system-ui,sans-serif;font-size:14px;color:var(--ouro2)}
.cmeta{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--suave)}
.statgroup{margin:0 0 16px}
.statgroup .gh{font-family:system-ui,sans-serif;font-size:13px;font-weight:700;color:var(--creme);margin:0 0 3px}
.statgroup .gsub{font-family:system-ui,sans-serif;font-size:12.5px;color:var(--suave);margin:0 0 10px}
.statcards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.statcard{background:rgba(255,255,255,.035);border:1px solid rgba(233,225,198,.14);border-radius:14px;padding:15px 16px;position:relative;overflow:hidden}
.statcard.key::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(180deg,var(--ouro2),var(--ouro))}
.statcard .num{font-family:var(--mono);font-size:28px;font-weight:700;color:var(--creme);font-variant-numeric:tabular-nums;line-height:1}
.statcard.key .num{color:var(--ouro2)}
.statcard .lb{font-family:system-ui,sans-serif;font-size:12.5px;font-weight:600;color:var(--creme);margin-top:6px}
.statcard .hp{font-family:system-ui,sans-serif;font-size:11.5px;color:var(--suave);margin-top:2px;line-height:1.35}
.legend{display:flex;gap:12px 18px;flex-wrap:wrap;align-items:center;background:rgba(255,255,255,.03);
  border:1px solid rgba(233,225,198,.14);border-radius:12px;padding:10px 14px;margin:14px 0;font-family:system-ui,sans-serif;font-size:12.5px;color:var(--suave)}
.faixa{font-family:var(--ui);font-size:13.5px;color:var(--creme);background:rgba(255,255,255,.04);
       border:1px solid var(--line);border-radius:12px;padding:11px 15px;margin:4px 0 14px}
.faixa.baixo{color:#eaa982;background:rgba(200,120,60,.13);border-color:rgba(200,120,60,.34)}
.amanha{background:linear-gradient(180deg,rgba(201,162,39,.10),rgba(255,255,255,.02));
        border:1px solid rgba(201,162,39,.30);border-radius:14px;padding:13px 16px;margin:0 0 18px}
.am-t{font-family:var(--ui);font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ouro2)}
.am-tit{font-size:15px;color:var(--creme);line-height:1.35;margin:6px 0 10px}
.am-rod{display:flex;align-items:center;justify-content:space-between;gap:10px;
        font-family:var(--ui);font-size:12.5px;color:var(--muted)}
.temachips{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 14px}
.temachip{font-family:var(--ui);font-size:12.5px;color:var(--muted);background:rgba(255,255,255,.05);
      border:1px solid var(--line);border-radius:100px;padding:6px 13px;text-decoration:none;transition:.15s}
.temachip:hover{color:var(--creme);border-color:rgba(201,162,39,.35)}
.temachip.on{color:var(--ouro2);background:rgba(201,162,39,.15);border-color:rgba(201,162,39,.38)}
.temachip b{font-family:var(--mono);font-weight:700}
/* Reserva em cards por tema (acordeão exclusivo nativo: <details name>) */
.temacard{border:1px solid var(--line);border-radius:12px;margin:10px 0;background:rgba(255,255,255,.02);
      overflow:hidden}
.temacard[open]{border-color:rgba(201,162,39,.32);background:rgba(201,162,39,.04)}
.temacard>summary{cursor:pointer;list-style:none;padding:14px 16px;font-family:var(--ui);
      font-size:14.5px;color:var(--creme);display:flex;align-items:center;gap:10px;transition:.15s}
.temacard>summary::-webkit-details-marker{display:none}
.temacard>summary:hover{color:var(--ouro2)}
.temacard>summary::after{content:"▸";margin-left:auto;color:var(--muted);transition:transform .18s}
.temacard[open]>summary::after{transform:rotate(90deg)}
.temacard .cnt{font-family:var(--mono);font-size:12.5px;color:var(--muted);
      background:rgba(255,255,255,.06);border-radius:100px;padding:2px 9px}
.temacard[open] .cnt{color:var(--ouro2);background:rgba(201,162,39,.15)}
.temacard-corpo{padding:0 16px 14px}
.cacts{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}
.scorechip{font-family:var(--mono);font-size:12px;font-weight:700;padding:3px 9px;border-radius:100px;display:inline-flex;align-items:center;gap:4px;font-variant-numeric:tabular-nums}
.scorechip.hi{background:linear-gradient(180deg,var(--score-hi-bg1),var(--score-hi-bg2));color:var(--score-hi-tx);border:1px solid var(--score-hi-bd)}
.scorechip.md{background:var(--score-md-bg);color:var(--score-md-tx);border:1px solid var(--score-md-bd)}
.scorechip.lo{background:var(--score-lo-bg);color:var(--score-lo-tx);border:1px solid var(--score-lo-bd)}
@media(max-width:560px){.statcards{grid-template-columns:1fr}}
.actbtn{font-family:system-ui,sans-serif;font-size:13px;font-weight:700;letter-spacing:.03em;color:#1a1300;background:linear-gradient(180deg,var(--ouro2),var(--ouro));border:none;cursor:pointer;padding:11px 22px;border-radius:100px}
.actbtn.ghost{background:transparent;color:var(--creme);border:1px solid rgba(201,162,39,.5)}
input:focus{outline:none;border-color:var(--ouro)}
button.cta{border:none;cursor:pointer;width:100%;font-size:16px;font-family:var(--ui);font-weight:700;letter-spacing:.02em;color:#1a1300;background:linear-gradient(180deg,var(--ouro2),var(--ouro));padding:15px 28px;border-radius:100px;box-shadow:0 12px 30px -10px rgba(201,162,39,.5);transition:transform .18s,box-shadow .18s}
button.cta:hover{transform:translateY(-2px);box-shadow:0 18px 40px -10px rgba(201,162,39,.62)}
button.cta.ghost{background:transparent;color:var(--creme);border:1px solid rgba(201,162,39,.5);box-shadow:none}
button.cta.ghost:hover{border-color:var(--ouro);color:var(--ouro2);transform:none}
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
.doc{background:var(--creme);color:#20302b;border-radius:16px;padding:40px 44px;margin:8px auto 26px;max-width:860px;box-shadow:0 20px 60px -20px rgba(0,0,0,.6)}
.doc .title{font-family:"Cormorant Garamond",Georgia,serif;font-size:34px;line-height:1.18;color:#14332a;margin-bottom:12px}
.doc .meta{font-family:ui-monospace,Menlo,monospace;font-size:13px;color:#6f7d78;border-bottom:2px solid var(--ouro);padding-bottom:12px;margin-bottom:20px}
/* Estudo subido na mao nao tem fonte/DOI: fica so a regua, sem o "· · DOI —". */
.doc .meta:empty{padding-bottom:0}
.doc .corpo p{margin:.8em 0;font-size:17px;color:#2b3a35}
.doc .corpo strong{color:#14332a}
/* Tabela do resumo (mesmo `pdf._resumo_html` do PDF) — o site tem copia PROPRIA
   do CSS, entao sem estas regras a tabela sai default de browser. `table-layout:
   fixed` + quebra de palavra e o que segura a tabela dentro da tela no celular. */
.doc .corpo table{width:100%;table-layout:fixed;border-collapse:collapse;margin:16px 0 20px;
  font-family:system-ui,sans-serif;font-size:14px;line-height:1.45}
.doc .corpo th,.doc .corpo td{padding:9px 11px;text-align:left;vertical-align:top;
  overflow-wrap:break-word;border-bottom:1px solid #e7e2d6}
/* Tarja do cabecalho um tom ABAIXO do card: no PDF o fundo e branco e #f4f1e7 ja
   destaca, mas aqui o card JA e --creme (#f4f1e7) e a tarja sumiria. */
.doc .corpo th{font-size:11.5px;letter-spacing:.09em;text-transform:uppercase;color:#6f7d78;
  font-weight:700;background:#eae3d1;border-bottom:2px solid var(--ouro)}
.doc .corpo tbody tr:nth-child(even) td{background:#faf8f2}
.doc .corpo td.num{text-align:right;font-variant-numeric:tabular-nums}
.chart{margin:24px 0;background:#f4f1e7;border:1px solid #e7e2d6;border-radius:10px;padding:18px 20px}
.chart .ct{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#6f7d78;margin-bottom:12px;font-weight:600}
.bar-row{display:flex;align-items:center;gap:12px;margin:10px 0}
.bar-lab{width:120px;font-family:system-ui,sans-serif;font-size:14px;color:#2b3a35;flex:none}
.bar-track{flex:1;background:#e7e2d3;border-radius:100px;height:22px;overflow:hidden}
.bar-fill{height:100%;border-radius:100px}
.bar-val{font-family:ui-monospace,monospace;font-size:14px;font-weight:700;width:66px;text-align:right;flex:none}
/* Kit de redes (mesmo bloco do PDF, via pdf._kit_html) — o site tem copia propria
   do CSS do PDF, entao as classes precisam existir aqui tambem. */
.kit{margin:24px 0 6px;display:flex;flex-direction:column;gap:20px}
.kit-rot{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#8a6a06;font-weight:700;margin-bottom:8px}
.paper-box{border:1px solid #d8ddd7;border-top:3px solid #14332a;background:#fcfdfc;padding:16px 18px}
.paper-rev{font-family:system-ui,sans-serif;font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:#14332a;font-weight:700;margin-bottom:8px}
.paper-tit{margin:0 0 10px;font-size:19px;line-height:1.28;color:#16211c}
.paper-doi{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:#6f7d78;word-break:break-word}
.frase-box{border:2px solid var(--ouro);border-radius:12px;padding:20px 22px;background:linear-gradient(180deg,#fff9e9,#fbf3d9)}
.frase-box p{margin:0;font-size:20px;line-height:1.4;color:#3a2f10}
.kit-brief .kit-rot{color:#6f7d78}
.paciente{border:1px solid #d8ddd7;border-left:4px solid var(--ouro);background:#f7faf8;padding:16px 18px;margin:22px 0 0;border-radius:0 8px 8px 0}
.pac-rot{font-family:system-ui,sans-serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7a4b2b;font-weight:700;margin-bottom:8px}
.paciente p{margin:0;font-size:17px;line-height:1.62;color:#20302b}
.reel-cards{display:flex;flex-direction:column;gap:12px}
.reel-card{border:1px solid #d8ddd7;border-radius:8px;background:#f8faf9;padding:15px 17px}
.reel-top{display:flex;align-items:center;gap:9px;margin-bottom:10px}
.reel-n{flex:0 0 22px;height:22px;border-radius:50%;background:#7a4b2b;color:#fff;font-family:system-ui,sans-serif;font-size:12px;font-weight:700;display:inline-flex;align-items:center;justify-content:center}
.reel-tit{font-family:system-ui,sans-serif;font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:#6f7d78;font-weight:700}
.reel-mini{font-family:system-ui,sans-serif;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#6f7d78;font-weight:700;margin:0 0 6px}
.reel-gancho{font-size:18px;line-height:1.36;color:#16211c;margin:0 0 12px;padding-left:11px;border-left:3px solid var(--ouro)}
.reel-roteiro{margin:0 0 12px;padding-left:20px}
.reel-roteiro li{font-size:16px;line-height:1.55;margin-bottom:5px;color:#2c3a34}
.reel-apoio{background:#eef3f0;border-radius:6px;padding:9px 12px;font-size:14.5px;line-height:1.5;color:#46544e;font-family:system-ui,sans-serif;margin:0}
.reel-apoio b{color:#24332c}
.kit-limites{border:1px solid #e6d6d2;border-left:4px solid #9c3226;background:#fdf7f6;padding:15px 18px;border-radius:0 8px 8px 0}
.kit-limites .kit-rot{color:#9c3226}
.kit-limites ul{margin:0;padding-left:20px}
.kit-limites li{font-size:15.5px;line-height:1.55;margin-bottom:7px;color:#4a3a37}
.docbtn{display:inline-block;margin-top:6px;font-family:system-ui,sans-serif;font-size:14px;color:var(--ouro2);text-decoration:none;border:1px solid rgba(201,162,39,.5);border-radius:100px;padding:10px 20px}
.foot{padding:40px 0 60px;border-top:1px solid rgba(233,225,198,.1);color:var(--suave);font-family:system-ui,sans-serif;font-size:13px;margin-top:20px}
.foot .flinks{margin-top:10px;font-size:12px}
.foot .flinks a{color:var(--suave);text-decoration:underline;text-underline-offset:2px}
.foot .flinks a:hover{color:var(--ouro2)}
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
/* checkout premium */
.checkout{display:grid;grid-template-columns:.82fr 1.18fr;gap:26px;align-items:start;margin:26px 0 10px}
.summary{background:linear-gradient(160deg,rgba(201,162,39,.15),rgba(20,51,42,.55));border:1px solid rgba(201,162,39,.32);border-radius:20px;padding:30px 28px;position:sticky;top:20px}
.summary .sum-eyebrow{font-family:var(--ui);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:var(--gold2);margin-bottom:10px}
.summary .sum-plan{font-family:var(--disp);font-size:30px;color:var(--cream);line-height:1.08}
.summary .sum-price{font-family:var(--disp);font-size:46px;color:var(--gold2);margin:16px 0 0;line-height:1}
.summary .sum-price span{display:block;font-family:var(--ui);font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-top:8px}
.summary .sum-list{list-style:none;margin:20px 0;padding:18px 0 0;border-top:1px solid rgba(233,225,198,.16)}
.summary .sum-list li{font-family:var(--ui);font-size:14px;color:var(--cream);margin:11px 0;display:flex;gap:10px;align-items:flex-start;line-height:1.4}
.summary .sum-list li b{color:var(--gold2);flex:none;font-weight:700}
.summary .sum-trust{font-family:var(--ui);font-size:12.5px;color:var(--muted);border-top:1px solid rgba(233,225,198,.16);padding-top:16px;line-height:1.5}
.form-side{background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:20px;padding:30px 28px}
.section-label{display:block;font-family:var(--ui);font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:6px 0 11px}
.paytiles{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}
.paytile{position:relative;display:flex;flex-direction:column;gap:4px;background:rgba(0,0,0,.22);border:1.5px solid rgba(233,225,198,.18);border-radius:14px;padding:16px 16px 15px;cursor:pointer;transition:.16s}
.paytile input{position:absolute;opacity:0;pointer-events:none}
.paytile .pt-ico{font-size:22px}
.paytile .pt-nome{font-family:var(--disp);font-size:20px;color:var(--cream)}
.paytile .pt-desc{font-family:var(--ui);font-size:12px;color:var(--muted);line-height:1.35}
.paytile:hover{border-color:rgba(201,162,39,.5)}
.paytile:has(input:checked){border-color:var(--gold);background:linear-gradient(160deg,rgba(201,162,39,.17),rgba(0,0,0,.22));box-shadow:inset 0 0 0 1px var(--gold)}
.paytile:has(input:checked)::after{content:"✓";position:absolute;top:11px;right:13px;color:var(--gold2);font-weight:800;font-family:var(--ui)}
.btn-pay{width:100%;border:none;cursor:pointer;margin-top:6px;font-family:var(--ui);font-weight:800;font-size:16px;letter-spacing:.02em;color:#1a1300;background:linear-gradient(180deg,var(--gold2),var(--gold));padding:17px 30px;border-radius:100px;box-shadow:0 14px 34px -10px rgba(201,162,39,.6);transition:.18s}
.btn-pay:hover{transform:translateY(-2px);box-shadow:0 20px 46px -10px rgba(201,162,39,.72)}
.securow{display:flex;align-items:center;gap:8px;justify-content:center;margin-top:14px;font-family:var(--ui);font-size:12px;color:var(--muted)}
.check-termos{display:flex;gap:10px;align-items:flex-start;margin:16px 0 8px;font-family:var(--ui);font-size:13px;line-height:1.5;color:var(--muted);cursor:pointer}
.check-termos input{margin-top:3px;flex:none}
.check-termos a{color:var(--ouro2);text-decoration:underline}
@media(max-width:760px){.checkout{grid-template-columns:1fr}.summary{position:static}.paytiles{grid-template-columns:1fr}}
/* ===== arquivo (redesign: abas por tema + mês/semana + leitura) ===== */
.back{display:inline-flex;align-items:center;gap:8px;font-family:var(--ui);font-size:13px;font-weight:600;color:var(--cream);border:1px solid var(--line);border-radius:100px;padding:9px 18px;margin-bottom:22px;transition:.18s}
.back:hover{border-color:var(--gold);color:var(--gold2)}
.tabs{display:flex;gap:6px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:2px;margin-bottom:26px}
.tab{display:inline-flex;align-items:center;gap:9px;font-family:var(--ui);font-size:13.5px;color:var(--muted);padding:12px 16px;border-radius:12px 12px 0 0;position:relative;transition:.15s}
.tab .cnt{font-family:var(--mono);font-size:11px;background:rgba(255,255,255,.07);padding:2px 8px;border-radius:100px;color:var(--muted)}
.tab:hover{color:var(--cream)}
.tab.on{color:var(--gold2)}
.tab.on .cnt{background:rgba(201,162,39,.18);color:var(--gold2)}
.tab.on::after{content:"";position:absolute;left:14px;right:14px;bottom:-2px;height:2px;background:var(--gold)}
.entry{display:grid;grid-template-columns:132px 1fr;gap:18px;align-items:baseline;border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin-bottom:10px;transition:.15s;background:rgba(255,255,255,.02)}
.entry:hover{border-color:rgba(201,162,39,.5);background:rgba(255,255,255,.05)}
.entry .date{font-family:var(--mono);font-size:12.5px;color:var(--gold2);letter-spacing:.02em}
.entry .etag{font-family:var(--ui);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-top:6px}
.entry .etitle{font-family:var(--disp);font-size:22px;color:var(--cream);line-height:1.2;margin-top:2px}
.entry .esrc{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-top:8px}
.month{border:1px solid var(--line);border-radius:14px;margin-bottom:14px;overflow:hidden;background:rgba(255,255,255,.02)}
.month-h{display:flex;align-items:center;justify-content:space-between;padding:15px 20px;cursor:pointer;user-select:none}
.month-h .mt{font-family:var(--disp);font-size:22px;color:var(--cream)}
.month-h .rt{display:flex;align-items:center;gap:12px}
.month-h .mc{font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.month-h .chev{color:var(--gold2);transition:.2s;font-size:13px}
.month.collapsed .month-body{display:none}
.month.collapsed .chev{transform:rotate(-90deg)}
.month-body{padding:2px 16px 14px}
.week-h{font-family:var(--ui);font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--gold2);margin:16px 0 10px;display:flex;align-items:center;gap:12px}
.week-h::after{content:"";flex:1;height:1px;background:var(--line)}
.empty-note{font-family:var(--ui);font-size:13px;color:var(--muted);padding:16px 2px}
.rtag{display:inline-flex;gap:7px;align-items:center;background:var(--g800);color:var(--gold2);font-family:var(--ui);font-size:10.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;padding:5px 11px;border-radius:100px;margin-bottom:12px}
.prevnext{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;max-width:860px;margin:0 auto}
.pn-btn{flex:1;min-width:200px;background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:12px;padding:14px 18px;transition:.15s}
.pn-btn:hover{border-color:var(--gold);background:rgba(255,255,255,.06)}
.pn-btn .k{font-family:var(--ui);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.pn-btn .v{font-family:var(--disp);font-size:16.5px;color:var(--cream);margin-top:3px}
.pn-btn.next{text-align:right}
/* badges + botão de slot (curadoria + agenda) */
.badge{font-family:var(--ui);font-size:10px;font-weight:700;letter-spacing:.03em;padding:3px 9px;border-radius:100px;white-space:nowrap}
.badge-reserva{color:#9fe6c2;background:rgba(70,190,130,.14);border:1px solid rgba(70,190,130,.32)}
.badge-fila{color:#ecd691;background:rgba(201,162,39,.15);border:1px solid rgba(201,162,39,.34)}
.badge-pulado{color:var(--muted);background:rgba(255,255,255,.05);border:1px solid var(--line)}
.badge-vazio{color:#eaa982;background:rgba(200,120,60,.15);border:1px solid rgba(200,120,60,.34)}
.slot-btn,.slot-sel{font-family:var(--ui);font-size:11.5px;font-weight:600;letter-spacing:.01em;
      padding:6px 11px;border-radius:100px;border:1px solid rgba(233,225,198,.22);
      background:rgba(0,0,0,.22);color:var(--creme);cursor:pointer;transition:.14s;line-height:1}
.slot-btn:hover,.slot-sel:hover{border-color:var(--ouro);color:var(--ouro2);background:rgba(201,162,39,.1)}
.slot-btn:active{transform:translateY(1px)}
@media(max-width:820px){
  .hero{grid-template-columns:1fr;gap:28px;padding:28px 0 18px}
  .sec{padding:40px 0}
  .themes{grid-template-columns:repeat(2,1fr)}
  .theme:last-child:nth-child(odd){grid-column:1/-1}
  .bento{grid-template-columns:1fr}.c-a,.c-b,.c-c,.c-d,.c-e,.c-f{grid-column:auto}
  .plans{grid-template-columns:1fr;max-width:340px;margin-inline:auto}
  .entry{grid-template-columns:1fr;gap:4px}
  .doc{padding:28px 22px}
  .dispatch{transform:none}
}
@media(max-width:480px){
  .wrap{padding:0 20px}
  .hero h1{font-size:36px}
  .lead{font-size:17px}
  .dtitle{font-size:22px}
  .sec{padding:34px 0}
}
"""


def _esc(s):
    return _html.escape(str(s or ""))


def _seletor_pais(selecionado="BR"):
    """<select name="pais_dial"> com paises.PAISES; opção de `selecionado` marcada."""
    import paises
    opts = "".join(
        f'<option value="{dial}"{" selected" if iso == selecionado else ""}>{bandeira} {nome} (+{dial})</option>'
        for iso, nome, bandeira, dial in paises.PAISES)
    return f'<select name="pais_dial">{opts}</select>'


def _cta():
    return _esc(config.cta_url())


def _topbar(logado=False, atual=""):
    minha = '' if atual == "/minha" else '<a class="plain" href="/minha">Minha conta</a>'
    direita = ('<a class="plain" href="/artigos">Arquivo</a>' + minha +
               '<a class="pill" href="/sair">Sair</a>'
               if logado else
               '<a class="plain" href="/#planos">Planos</a>'
               '<a class="pill" href="/entrar">Entrar</a>')
    return (f'<div class="wrap"><div class="top">'
            f'<a href="/"><div class="brand">'
            f'<span class="m">{_esc(MARCA)}</span><span class="c">{_esc(CRM)}</span></div></a>'
            f'<nav class="nav">{direita}</nav></div></div>')


def _foot():
    return (f'<div class="wrap"><div class="foot">'
            f'{_esc(MARCA)} · {_esc(CRM)} · {_esc(PRODUTO)}'
            f'<div class="flinks"><a href="/termos">Termos de assinatura</a> · '
            f'<a href="/privacidade">Política de privacidade</a></div>'
            f'<div class="cfm">Conteúdo de caráter científico-educacional, destinado a médicos. '
            f'Não substitui o julgamento clínico individual nem constitui recomendação de conduta.</div>'
            f'</div></div>')


def _pagina(titulo, corpo, logado=False, meta_extra="", atual=""):
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
            f'<title>{_esc(titulo)}</title>{meta_extra}{_FONTS}<style>{_CSS}</style></head><body>'
            f'{_topbar(logado, atual)}{corpo}{_foot()}</body></html>')


# ── Landing (pública) ──
def landing():
    temas = [("⚖️", "Obesidade"), ("⚕️", "Menopausa & Reposição"),
             ("🦵", "Lipedema"), ("🏃", "Performance"), ("🧬", "Longevidade")]
    themes = "".join(
        f'<div class="theme"><div class="e">{_esc(e)}</div>'
        f'<div class="t">{_esc(t)}</div></div>'
        for e, t in temas)
    valores = [
        ("01 · curadoria", "Curadoria + revisão médica", "Curadoria criteriosa da literatura da semana; o Dr. Diego revisa antes de sair — você recebe o que importa, sem ruído.", "card big c-a"),
        ("02 · cadência", "1 estudo por dia útil", "De segunda a sexta, um artigo relevante — resumo clínico direto ao ponto, no seu WhatsApp.", "card c-b"),
        ("03 · áudio", "Áudio-resumo", "Prefere ouvir? Cada edição vem com um áudio narrado de ~2 minutos — perfeito pro trânsito ou entre atendimentos.", "card c-c"),
        ("04 · redes", "Você nas redes sociais", "Cada edição traz um gancho forte, já pronto, para levar o tema aos seus seguidores. Sem perder tempo pensando 'o que postar hoje?'.", "card c-d"),
        ("05 · pdf", "PDF Objetivo", "Um PDF objetivo e visual, com gráficos e tabelas, organizado para facilitar a leitura, o entendimento e a organização das ideias.", "card c-e"),
        ("06 · arquivo", "Arquivo consultável", "Tudo por tema e data, sempre à mão neste portal.", "card c-f"),
    ]
    bento = "".join(
        f'<div class="{cls}"><span class="k">{_esc(k)}</span><h3>{_esc(n)}</h3><p>{_esc(d)}</p></div>'
        for k, n, d, cls in valores)
    import subscribers
    n_ativos = len(subscribers.ativos())
    planos = "".join(
        f'<a class="plan{" best" if p["slug"] == "anual" else ""}" href="/assinar?plano={_esc(p["slug"])}">'
        + ('<div class="badge">melhor preço</div>' if p["slug"] == "anual" else "")
        + f'<div class="nm">{_esc(p["nome"])}</div>'
        f'<div class="pr">{_esc(pricing.preco_str_vigente(p, n_ativos)) if p.get("preco") else "sob consulta"}</div>'
        f'<div class="pe">{_esc(p["periodo"])}</div>'
        + (f'<div class="pn">{_esc(pricing.nota_str_vigente(p, n_ativos))}</div>' if pricing.nota_str_vigente(p, n_ativos) else "")
        + '<span class="pick2">Assinar</span></a>' for p in config.planos_venda())
    corpo = f"""
    <div class="wrap">
      <section class="hero">
        <div>
          <div class="eyebrow">{_esc(PRODUTO)}</div>
          <h1 class="disp">A ciência que move a sua <em>prática clínica</em> — na palma da mão.</h1>
          <p class="lead">Um estudo relevante por dia, no formato que você preferir: resumo clínico em texto, <em>áudio-resumo</em> pra ouvir no trânsito ou PDF objetivo. E de bônus, um gancho forte para falar do assunto nas suas redes sociais. Revisado e aprovado por médico.</p>
          <div class="ctas">
            <a class="btn solid" href="{_cta()}">Quero assinar</a>
            <a class="btn ghost" href="/entrar">Já sou assinante</a>
          </div>
          <div class="trust">✳︎ <span>De segunda a sexta · <b>revisão médica</b> antes de cada envio</span></div>
        </div>
        <aside class="dispatch">
          <span class="dtag">⚖️ Obesidade · edição do dia</span>
          <div class="dmeta">NEJM · 18 JUL 2026 · DOI 10.1056/NEJMoa2410000</div>
          <div class="dtitle">Tirzepatida sustenta a perda de peso em 3 anos — extensão do SURMOUNT-1</div>
          <div class="dbody"><p>Na extensão aberta, a perda ponderal se manteve com <strong>boa tolerância</strong>; descontinuação por eventos GI ficou abaixo de 6%.</p></div>
          <div class="chart">
            <div class="crow"><span class="clab">15 mg</span><span class="ctrack"><span class="cfill" style="width:92%"></span></span><span class="cval">−22,5%</span></div>
            <div class="crow"><span class="clab">10 mg</span><span class="ctrack"><span class="cfill" style="width:78%"></span></span><span class="cval">−19,1%</span></div>
            <div class="crow"><span class="clab">5 mg</span><span class="ctrack"><span class="cfill" style="width:62%"></span></span><span class="cval">−15,0%</span></div>
          </div>
          <div class="hook"><div class="hl">Para as suas redes</div><div class="ht">"Manter o resultado é tão importante quanto alcançá-lo — e os dados de 3 anos reforçam isso."</div></div>
          <div style="margin-top:14px;font-family:var(--ui);font-size:11.5px;letter-spacing:.04em;color:var(--inkpaper);opacity:.62">🎧 Áudio de ~2 min · 📄 PDF · direto no seu WhatsApp</div>
        </aside>
      </section>

      <section class="sec" style="border-top:none;padding-top:16px">
        <div class="sectag">Cinco frentes, uma rotina</div>
        <div class="themes">{themes}</div>
      </section>

      <section class="sec">
        <h2 class="disp">O que chega até você</h2>
        <p class="sub">Os temas são variados para você não receber dois dias seguidos do mesmo assunto — e tudo fica guardado no seu arquivo.</p>
        <div class="bento">{bento}</div>
      </section>

      <section class="sec" id="planos">
        <h2 class="disp">Planos</h2>
        <p class="sub">Escolha a recorrência que faz sentido. Renova automaticamente até você cancelar.</p>
        <div class="plans">{planos}</div>
        <div style="margin-top:28px;text-align:center"><a class="btn solid" href="{_cta()}">Quero assinar</a>
        <a class="btn ghost" href="/entrar" style="margin-left:10px">Já sou assinante</a></div>
      </section>

      <section class="sec">
        <div class="auth">
          <div class="big">"Filtro os artigos relevantes para que você não perca tempo abrindo <em>vinte abas</em> — e chego com o que atualiza a sua conduta."</div>
          <div class="sig">curadoria e revisão<b>{_esc(MARCA)}</b>{_esc(CRM)}</div>
        </div>
      </section>
    </div>"""
    return _pagina(f"{PRODUTO} · {MARCA}", corpo, logado=False)


# ── Login OTP ──
def pagina_entrar(etapa="numero", whatsapp="", erro="", via="whatsapp"):
    """Login por código (OTP). via='whatsapp' (padrão) ou 'cpf'.
    `whatsapp` = valor do identificador a repreencher/embutir (é o CPF quando via='cpf')."""
    cpf_mode = (via == "cpf")
    campo = "cpf" if cpf_mode else "whatsapp"
    action = "/entrar-cpf-codigo" if cpf_mode else "/entrar-codigo"
    senha_href = "/entrar-cpf" if cpf_mode else "/entrar"
    recomecar_txt = "Usar outro CPF" if cpf_mode else "Usar outro número"
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    if etapa == "codigo":
        corpo = f"""
        <div class="wrap"><div class="panel">
          <h2 class="disp">Digite o código</h2>
          <p class="hint">Enviamos um código de 6 dígitos no seu WhatsApp. Ele vale por 10 minutos.</p>
          {erro_html}
          <form method="post" action="{action}">
            <input type="hidden" name="etapa" value="codigo">
            <input type="hidden" name="{campo}" value="{_esc(whatsapp)}">
            <label>Código</label>
            <input type="text" name="codigo" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000" autofocus>
            {ui.btn('Entrar')}
          </form>
          <p class="hint" style="margin-top:16px"><a href="{action}" style="color:var(--ouro2)">{recomecar_txt}</a> &nbsp;·&nbsp; <a href="{senha_href}" style="color:var(--suave)">Entrar com senha</a></p>
        </div></div>"""
    else:
        label = "CPF" if cpf_mode else "WhatsApp (com DDD)"
        imode = "numeric" if cpf_mode else "tel"
        ph = "000.000.000-00" if cpf_mode else "(43) 99999-0000"
        hint = ("Informe o CPF do seu cadastro e enviamos um código de acesso ao WhatsApp da assinatura."
                if cpf_mode else
                "Sem acesso à senha? Informe o WhatsApp da sua assinatura e enviamos um código de acesso.")
        corpo = f"""
        <div class="wrap"><div class="panel">
          <h2 class="disp">Entrar com código</h2>
          <p class="hint">{hint}</p>
          {erro_html}
          <form method="post" action="{action}">
            <input type="hidden" name="etapa" value="numero">
            <label>{label}</label>
            <input type="text" name="{campo}" inputmode="{imode}" placeholder="{ph}" autofocus>
            {ui.btn('Enviar código')}
          </form>
          {ui.btn('Entrar com senha', href=senha_href, variant='ghost', extra='margin-top:12px')}
        </div></div>"""
    return _pagina(f"Entrar · {PRODUTO}", corpo, logado=False, meta_extra='<meta name="robots" content="noindex">')


def pagina_login(erro="", sem_senha=False, whatsapp="", via="whatsapp"):
    """Tela de login principal: identificador + senha. via='whatsapp' (padrão) ou 'cpf'.
    `whatsapp` = valor do identificador a repreencher (é o CPF quando via='cpf')."""
    cpf_mode = (via == "cpf")
    label = "CPF" if cpf_mode else "WhatsApp (com DDD)"
    campo = "cpf" if cpf_mode else "whatsapp"
    imode = "numeric" if cpf_mode else "tel"
    ph = "000.000.000-00" if cpf_mode else "(43) 99999-0000"
    action = "/entrar-cpf" if cpf_mode else "/entrar"
    codigo_href = "/entrar-cpf-codigo" if cpf_mode else "/entrar-codigo"
    titulo_hint = ("Entre com o CPF do seu cadastro e sua senha." if cpf_mode
                   else "Entre com o WhatsApp da sua assinatura e sua senha.")
    erro_html = f'<div class="erro">{_esc(erro)}</div>' if erro else ""
    if sem_senha:
        if cpf_mode:
            erro_html += ('<div class="infobox">Você ainda não criou sua senha. Use '
                          '<strong>Entrar com código no WhatsApp</strong> abaixo (ou peça seu link de acesso).</div>')
        else:
            erro_html += ('<div class="infobox">Você ainda não criou sua senha. Clique em '
                          '<strong>Primeiro acesso / criar senha</strong> abaixo — enviaremos um link por e-mail.</div>')
    if cpf_mode:
        aux = (ui.btn('Sem senha? Entrar com código', href=codigo_href, variant='ghost',
                      extra='margin-top:12px')
               + '<p class="hint" style="margin-top:12px;font-size:13px">'
                 '<a href="/entrar" style="color:var(--suave)">← Entrar com WhatsApp</a></p>')
    else:
        aux = (ui.btn('Entrar com código no WhatsApp', href='/entrar-codigo', variant='ghost',
                      extra='margin-top:12px')
               + '<p class="hint" style="margin-top:16px">'
                 '<a href="/primeiro-acesso" style="color:var(--ouro2)">Primeiro acesso / criar senha</a>'
                 '&nbsp;·&nbsp;'
                 '<a href="/esqueci" style="color:var(--suave)">Esqueci minha senha</a></p>'
                 '<p class="hint" style="margin-top:8px;font-size:13px"><a href="/entrar-cpf" style="color:var(--suave)">Assinante fora do Brasil / sem WhatsApp brasileiro? Entrar com CPF</a></p>')
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Área do assinante</h2>
      <p class="hint">{titulo_hint}</p>
      {erro_html}
      <form method="post" action="{action}">
        <label>{label}</label>
        <input type="text" name="{campo}" inputmode="{imode}" value="{_esc(whatsapp)}" placeholder="{ph}" autofocus>
        <label>Senha</label>
        <input type="password" name="senha" placeholder="sua senha">
        {ui.btn('Entrar')}
      </form>
      {aux}
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


def _admin_nav(token="", atual=""):
    """Barra de navegação entre as telas de admin (Assinantes · Curadoria · Minha conta)."""
    tk = f"?token={_esc(token)}" if token else ""
    def lk(href, rot, key):
        cls = "actbtn" if key == atual else "actbtn ghost"
        return (f'<a class="{cls}" href="{href}{tk}" '
                f'style="text-decoration:none;padding:8px 15px;font-size:13px">{rot}</a>')
    return ('<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:4px 0 18px">'
            + lk("/admin", "👥 Assinantes", "assinantes")
            + lk("/curadoria", "🔬 Curadoria", "curadoria")
            + lk("/agenda", "📅 Agenda", "agenda")
            + lk("/series", "🎬 Séries", "series")
            + lk("/admin/precos", "💰 Preços", "precos")
            + lk("/admin/envio", "🗓️ Dias", "envio")
            + lk("/admin/trilha", "📘 Trilha", "trilha")
            + lk("/admin/afiliados", "🤝 Afiliados", "afiliados")
            + lk("/admin/mensagens", "📝 Mensagens", "mensagens")
            + lk("/admin/whatsapp", "📱 WhatsApp", "whatsapp")
            + '</div>')


def pagina_admin_afiliados(afiliados, comissoes, token="", editar_id=None):
    """Tela de Afiliados: cadastro, tabela com agregados e comissões pendentes."""
    import pricing
    tk = _esc(token)

    def row_af(a):
        on = bool(a.get("ativo"))
        cor = "#2f9e6b" if on else "#7a8a84"
        prox = "0" if on else "1"
        rot = "desativar" if on else "ativar"
        return (
            '<tr style="border-top:1px solid rgba(233,225,198,.1)">'
            f'<td style="padding:11px 10px;font-family:ui-monospace,Menlo,monospace;font-size:14px;color:var(--ouro2)">{_esc(a.get("codigo"))}</td>'
            f'<td style="padding:11px 10px;color:var(--creme)">{_esc(a.get("nome") or "—")}</td>'
            f'<td style="padding:11px 10px;font-size:13px;color:var(--suave)">{_esc(a.get("contato") or "—")}</td>'
            f'<td style="padding:11px 10px;font-size:13px;color:var(--suave)">{_esc(str(a.get("pct_desconto")))}% / {_esc(str(a.get("pct_comissao")))}%</td>'
            f'<td style="padding:11px 10px;color:var(--creme)">{a.get("n_vendas", 0)}</td>'
            f'<td style="padding:11px 10px;color:var(--suave)">{_esc(pricing.fmt_brl(a.get("comissao_total", 0)))}</td>'
            f'<td style="padding:11px 10px;color:var(--ouro2)">{_esc(pricing.fmt_brl(a.get("comissao_pendente", 0)))}</td>'
            f'<td style="padding:11px 10px"><div style="display:flex;gap:6px;align-items:center">'
            f'<a class="actbtn ghost" href="/admin/afiliados?token={tk}&editar={_esc(a.get("id"))}" '
            f'style="text-decoration:none;padding:6px 12px;font-size:12px">editar</a>'
            f'<form method="post" action="/admin/afiliados" style="margin:0">'
            f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="toggle_afiliado">'
            f'<input type="hidden" name="id" value="{_esc(a.get("id"))}"><input type="hidden" name="on" value="{prox}">'
            f'<button class="actbtn ghost" style="padding:6px 12px;font-size:12px;color:{cor}">{rot}</button></form>'
            f'</div></td></tr>')

    linhas = "".join(row_af(a) for a in (afiliados or [])) or \
        '<tr><td colspan="8" style="padding:20px;color:var(--suave)">Nenhum afiliado ainda.</td></tr>'

    nome_af = {a.get("id"): a.get("nome") for a in (afiliados or [])}

    def row_com(c):
        """Comissão estornada (venda devolvida) NÃO some da lista — fica marcada (etiqueta +
        riscado + esmaecida), sem botão de pagar e sem entrar em nenhum total: o agregado
        `comissao_pendente` (tabela acima) já vem sem ela direto do db.listar_afiliados."""
        estornada = bool(c.get("estornada_em"))
        etiqueta = ('<span style="font-family:system-ui;font-size:10px;font-weight:700;'
                    'letter-spacing:.06em;padding:3px 9px;border-radius:100px;background:#c0562f22;'
                    'color:#c0562f;border:1px solid #c0562f66;margin-left:8px">ESTORNADA</span>'
                    ) if estornada else ""
        conteudo_style = ' style="text-decoration:line-through;opacity:.55"' if estornada else ""
        acao = ('' if estornada else
                '<form method="post" action="/admin/afiliados" style="margin:0">'
                f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="marcar_comissao_paga">'
                f'<input type="hidden" name="id" value="{_esc(c.get("id"))}">'
                '<button class="actbtn" style="padding:6px 13px;font-size:12px">marcar como paga</button></form>')
        return (
            '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 0;border-top:1px solid rgba(233,225,198,.1)">'
            f'<div{conteudo_style}><span style="color:var(--creme)">{_esc(nome_af.get(c.get("afiliado_id"), "—"))}</span>{etiqueta}'
            f'<div style="font-family:system-ui;font-size:12px;color:var(--suave)">{_esc(c.get("plano") or "—")} · venda {_esc(pricing.fmt_brl(c.get("valor_venda", 0)))} · '
            f'comissão <b style="color:var(--ouro2)">{_esc(pricing.fmt_brl(c.get("valor_comissao", 0)))}</b></div></div>'
            f'{acao}</div>')

    comis_lista = "".join(row_com(c) for c in (comissoes or [])) or \
        '<p class="hint" style="margin-top:8px">Nenhuma comissão pendente.</p>'

    alvo = next((a for a in (afiliados or []) if str(a.get("id")) == str(editar_id)), None) if editar_id else None
    editar_html = ""
    if alvo:
        editar_html = (
            '<div class="panel" style="max-width:none;margin:14px 0;border-color:#c9a22766">'
            '<h3 style="font-family:\'Cormorant Garamond\',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:6px">'
            f'Editar afiliado — <span style="font-family:ui-monospace,Menlo,monospace">{_esc(alvo.get("codigo"))}</span></h3>'
            '<form method="post" action="/admin/afiliados">'
            f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="editar_afiliado">'
            f'<input type="hidden" name="id" value="{_esc(alvo.get("id"))}">'
            f'<label>Nome</label><input type="text" name="nome" value="{_esc(alvo.get("nome") or "")}">'
            f'<label style="margin-top:10px">Contato</label><input type="text" name="contato" value="{_esc(alvo.get("contato") or "")}">'
            f'<label style="margin-top:10px">Código do cupom</label><input type="text" name="codigo" value="{_esc(alvo.get("codigo") or "")}">'
            '<div style="display:flex;gap:10px">'
            f'<div style="flex:1"><label style="margin-top:10px">% desconto</label><input type="number" step="0.1" name="pct_desconto" value="{_esc(str(alvo.get("pct_desconto")))}"></div>'
            f'<div style="flex:1"><label style="margin-top:10px">% comissão</label><input type="number" step="0.1" name="pct_comissao" value="{_esc(str(alvo.get("pct_comissao")))}"></div>'
            '</div>'
            '<div style="display:flex;gap:10px;margin-top:14px">'
            '<button class="actbtn" type="submit">Salvar alterações</button>'
            f'<a class="actbtn ghost" href="/admin/afiliados?token={tk}" style="text-decoration:none;padding:8px 16px">Cancelar</a>'
            '</div></form></div>')

    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "afiliados")}
      <div class="sectag" style="margin-top:8px">Painel do curador</div>
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:2px 0 4px">Afiliados</h2>
      <p class="hint">Código dá <strong>desconto na 1ª venda</strong> ao assinante e gera <strong>comissão</strong> pro afiliado. Pagamento da comissão é manual.</p>
      {editar_html}
      <div style="overflow-x:auto;margin:18px 0">
        <table style="width:100%;border-collapse:collapse;min-width:760px">
          <thead><tr style="font-family:system-ui;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--suave);text-align:left">
            <th style="padding:8px 10px">Código</th><th style="padding:8px 10px">Nome</th><th style="padding:8px 10px">Contato</th>
            <th style="padding:8px 10px">Desc./Com.</th><th style="padding:8px 10px">Vendas</th>
            <th style="padding:8px 10px">Comissão total</th><th style="padding:8px 10px">Pendente</th><th></th></tr></thead>
          <tbody>{linhas}</tbody>
        </table>
      </div>
      <div style="display:flex;gap:18px;flex-wrap:wrap;margin:10px 0">
        <div class="panel" style="max-width:none;margin:0;flex:1;min-width:300px">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:6px">Cadastrar afiliado</h3>
          <form method="post" action="/admin/afiliados">
            <input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="criar_afiliado">
            <label>Nome</label><input type="text" name="nome" placeholder="Dra. Maria">
            <label style="margin-top:10px">Contato (e-mail/WhatsApp p/ pagar)</label><input type="text" name="contato">
            <label style="margin-top:10px">Código do cupom</label><input type="text" name="codigo" placeholder="DRAMARIA">
            <div style="display:flex;gap:10px">
              <div style="flex:1"><label style="margin-top:10px">% desconto</label><input type="number" step="0.1" name="pct_desconto" value="10"></div>
              <div style="flex:1"><label style="margin-top:10px">% comissão</label><input type="number" step="0.1" name="pct_comissao" value="3"></div>
            </div>
            <button class="actbtn" type="submit" style="margin-top:14px">➕ Cadastrar afiliado</button>
          </form>
        </div>
        <div class="panel" style="max-width:none;margin:0;flex:1;min-width:300px">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:6px">Comissões pendentes</h3>
          <p class="hint" style="margin-bottom:6px">Pague por fora e clique em "marcar como paga" pra dar baixa. Vendas estornadas (cancelamento no arrependimento) aparecem aqui só como registro — marcadas, sem entrar em pendente nem poder ser pagas.</p>
          <div style="margin-top:10px">{comis_lista}</div>
        </div>
      </div>
    </div>"""
    return _pagina("Afiliados · Admin", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_admin_envio(dias_ativos, token="", msg=""):
    """Escolhe em quais dias da semana os estudos são enviados (e a agenda materializa slots)."""
    tk = _esc(token)
    ativos = set(dias_ativos or [])
    aviso = (f'<div class="infobox" style="margin:14px 0;border-color:#2f9e6b66;background:#2f9e6b18">{_esc(msg)}</div>'
             if msg else "")
    rotulos = [("segunda", "Segunda"), ("terca", "Terça"), ("quarta", "Quarta"), ("quinta", "Quinta"),
               ("sexta", "Sexta"), ("sabado", "Sábado"), ("domingo", "Domingo")]
    checks = "".join(
        f'<label style="display:flex;align-items:center;gap:10px;padding:11px 14px;'
        f'border:1px solid rgba(233,225,198,.14);border-radius:12px;margin-bottom:8px;cursor:pointer">'
        f'<input type="checkbox" name="dia" value="{slug}"{" checked" if slug in ativos else ""}>'
        f'<span style="color:var(--creme);font-size:16px">{rot}</span></label>'
        for slug, rot in rotulos)
    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "envio")}
      <div class="sectag" style="margin-top:8px">Painel do curador</div>
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:2px 0 4px">Dias de envio</h2>
      <p class="hint">Em quais dias os estudos são enviados no WhatsApp (e a agenda reserva slots). Desmarcar um dia = nada é enviado nele.</p>
      {aviso}
      <form method="post" action="/admin/envio">
        <input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="salvar_dias">
        <div class="panel" style="max-width:420px;margin:14px 0">{checks}
          <button class="actbtn" type="submit" style="margin-top:12px">Salvar dias</button>
        </div>
      </form>
    </div>"""
    return _pagina("Dias de envio · Admin", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_admin_trilha(linhas, token="", pecas=None, ativa=False, msg=""):
    """Painel do admin: quem está em qual semana da trilha, quanto recebeu e
    quanto executou. Cartões (não tabela: `.tbl` não existe no CSS deste repo, e
    a tela de Assinantes já foi redesenhada em cartões por causa disso no celular).
    Cada linha: nome, proxima_peca, enviadas, feitas, concluiu:bool.

    `pecas` alimenta a prévia sob demanda: um link por peça pra
    `/admin/trilha/peca/<n>`, que renderiza com a MESMA função que gera o PDF
    enviado no WhatsApp -- assim a prévia não pode divergir do envio real.
    Default `None` de propósito: chamadores antigos (sem essa lista) continuam
    funcionando."""
    pecas = pecas or []
    if not pecas:
        bloco_pecas = '<p class="hint">Nenhuma peça carregada.</p>'
    else:
        itens = []
        for p in pecas:
            itens.append(
                f'<p style="margin:0 0 6px"><a class="cta ghost" '
                f'href="/admin/trilha/peca/{int(p["numero"])}?token={_esc(token)}">'
                f'Semana {int(p["numero"])} · {_esc(p.get("titulo") or "")}</a></p>')
        bloco_pecas = "".join(itens)
    msg_html = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""
    # O interruptor mestre. Fica no topo porque é a única coisa nesta tela que muda o
    # que o assinante recebe -- o resto é leitura.
    if ativa:
        bloco_switch = (
            '<div class="panel" style="max-width:680px;margin:0 0 12px;padding:16px 20px;'
            'border-color:var(--ouro2)">'
            '<p class="plabel" style="color:var(--ouro2)">Trilha LIGADA</p>'
            '<p class="hint" style="margin:6px 0 12px">Todo sábado os assinantes recebem a '
            'peça da vez, cada um no horário que escolheu.</p>'
            f'<form method="post" action="/admin/trilha">'
            f'<input type="hidden" name="token" value="{_esc(token)}">'
            '<input type="hidden" name="acao" value="desligar">'
            '<button class="actbtn ghost" type="submit">Desligar a trilha</button></form></div>')
    else:
        bloco_switch = (
            '<div class="panel" style="max-width:680px;margin:0 0 12px;padding:16px 20px">'
            '<p class="plabel">Trilha desligada</p>'
            '<p class="hint" style="margin:6px 0 12px">Nenhum assinante recebe nada. Leia as '
            f'{config.TRILHA_TOTAL} peças abaixo antes de ligar — depois de ligada, a primeira '
            'sai no próximo sábado e não tem como voltar atrás no que já saiu.</p>'
            f'<form method="post" action="/admin/trilha">'
            f'<input type="hidden" name="token" value="{_esc(token)}">'
            '<input type="hidden" name="acao" value="ligar">'
            '<button class="actbtn" type="submit">Ligar a trilha</button></form></div>')
    if not linhas:
        corpo_lista = '<p class="hint">Ninguém entrou na trilha ainda.</p>'
    else:
        cards = []
        for l in linhas:
            estado = "Concluiu" if l.get("concluiu") else f"Semana {int(l['proxima_peca'])}"
            cards.append(
                # .panel padrão é feito p/ 1 caixa centralizada (login/forms), não p/ lista
                # repetida -- max-width/margin sobrescritos aqui, mesma técnica já usada em
                # pagina_admin_envio logo acima (senão dezenas de assinantes viram uma coluna
                # estreita e centralizada com 40px de vão entre cada cartão).
                f'<div class="panel" style="max-width:680px;margin:0 0 12px;padding:16px 20px">'
                f'<h3 style="margin:0;font-family:var(--disp);color:var(--creme);font-size:20px">'
                f'{_esc(l.get("nome") or "—")}</h3>'
                f'<p class="hint" style="margin:6px 0 0">{_esc(estado)} · '
                f'{int(l.get("enviadas", 0))} recebida(s) · {int(l.get("feitas", 0))} feita(s)</p>'
                f'</div>')
        corpo_lista = "".join(cards)
    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "trilha")}
      <div class="sectag" style="margin-top:8px">Painel do curador</div>
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:2px 0 4px">{_esc(config.TRILHA_NOME)}</h2>
      <p class="hint">{len(linhas)} assinante(s) na trilha · {config.TRILHA_TOTAL} peças no total.</p>
      {msg_html}
      {bloco_switch}
      <div class="panel" style="max-width:680px;margin:0 0 12px;padding:16px 20px">
        <p class="plabel">As {config.TRILHA_TOTAL} peças</p>
        <p class="hint">Abra cada uma pra ver exatamente o que vira PDF no WhatsApp.</p>
        {bloco_pecas}</div>
      {corpo_lista}
    </div>"""
    return _pagina(f"{config.TRILHA_NOME} · {PRODUTO}", corpo, logado=True, atual="trilha",
                   meta_extra='<meta name="robots" content="noindex">')


def pagina_admin_mensagens(wa, email_assunto, email_corpo, email_renov_assunto="",
                           email_renov_corpo="", token="", msg="", automacoes=None,
                           bonus_resgate_dias=30):
    """Editor das mensagens de boas-vindas (WhatsApp + e-mail), da confirmação de
    renovação/recontratação (só e-mail — texto único pros dois casos) e da régua de
    renovação (automações por dias-do-vencimento, criadas/editadas/removidas aqui —
    sem depender de programador — e o bônus de resgate em dias)."""
    tk = _esc(token)
    aviso = (f'<div class="infobox" style="margin:14px 0;border-color:#2f9e6b66;background:#2f9e6b18">{_esc(msg)}</div>'
             if msg else "")
    ta = ("width:100%;font-family:ui-monospace,Menlo,monospace;font-size:13px;line-height:1.5;"
          "padding:12px;border-radius:10px;box-sizing:border-box")

    # Uma <form> por automação existente (id oculto identifica qual linha o POST atualiza)
    # mais uma <form> extra de criação (id vazio → db.salvar_automacao gera um id novo).
    linhas_auto = "".join(
        f'<form method="post" action="/admin/mensagens" style="border:1px solid #2a4a3c;'
        f'border-radius:10px;padding:12px;margin:10px 0">'
        f'<input type="hidden" name="token" value="{tk}">'
        f'<input type="hidden" name="id" value="{_esc(a["id"])}">'
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">'
        f'<label>Dias <input type="number" name="dias" value="{int(a["dias"])}" '
        f'style="width:80px"></label>'
        f'<label>Canal <select name="canal">'
        f'<option value="whatsapp"{" selected" if a["canal"] == "whatsapp" else ""}>WhatsApp</option>'
        f'<option value="email"{" selected" if a["canal"] == "email" else ""}>E-mail</option>'
        f'</select></label>'
        f'<label><input type="checkbox" name="ativo" value="1"'
        f'{" checked" if a["ativo"] else ""}> ativa</label>'
        f'</div>'
        f'<textarea name="texto" rows="3" style="width:100%;margin-top:8px">{_esc(a["texto"])}</textarea>'
        f'<button class="cta" type="submit" name="acao" value="salvar_automacao">Salvar</button> '
        f'<button type="submit" name="acao" value="remover_automacao" '
        f'onclick="return confirm(\'Remover esta automação?\')">Remover</button>'
        f'</form>' for a in (automacoes or []))

    nova_auto = (
        f'<form method="post" action="/admin/mensagens" style="border:1px dashed #2a4a3c;'
        f'border-radius:10px;padding:12px;margin:10px 0">'
        f'<input type="hidden" name="token" value="{tk}">'
        f'<input type="hidden" name="id" value="">'
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">'
        f'<label>Dias <input type="number" name="dias" value="-7" style="width:80px"></label>'
        f'<label>Canal <select name="canal">'
        f'<option value="whatsapp">WhatsApp</option><option value="email">E-mail</option>'
        f'</select></label>'
        f'<label><input type="checkbox" name="ativo" value="1" checked> ativa</label></div>'
        f'<textarea name="texto" rows="3" style="width:100%;margin-top:8px" '
        f'placeholder="Texto da mensagem"></textarea>'
        f'<button class="cta" type="submit" name="acao" value="salvar_automacao">Adicionar</button>'
        f'</form>')

    secao_bonus = (
        f'<form method="post" action="/admin/mensagens" style="border:1px solid #2a4a3c;'
        f'border-radius:10px;padding:12px;margin:10px 0 18px">'
        f'<input type="hidden" name="token" value="{tk}">'
        f'<input type="hidden" name="acao" value="salvar_bonus_resgate">'
        f'<label>🎁 Bônus de resgate <input type="number" min="0" name="bonus_resgate_dias" '
        f'value="{int(bonus_resgate_dias)}" style="width:90px"> dias</label>'
        f'<p class="hint" style="margin-top:6px">Só vale pra quem paga <b>depois</b> de já ter '
        f'perdido o acesso — esses dias são somados ao período comprado. Quem renova em dia '
        f'não ganha nada.</p>'
        f'<button class="cta" type="submit">Salvar bônus</button>'
        f'</form>')

    secao_auto = (
        f'<h3 style="color:var(--creme);margin-top:28px">Régua de renovação</h3>'
        f'<p class="hint">Só alcança o plano anual sem renovação automática (Pix e cartão '
        f'parcelado). <b>Dias</b>: negativo antes do vencimento (-7 = sete dias antes), '
        f'0 no dia, positivo depois (+15 = quinze dias depois). '
        f'Marcadores: <code>{{nome}}</code>, <code>{{ate}}</code>, <code>{{link}}</code>.</p>'
        f'{secao_bonus}'
        f'{linhas_auto}{nova_auto}')
    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "mensagens")}
      <div class="sectag" style="margin-top:8px">Painel do curador</div>
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:2px 0 4px">Mensagens de boas-vindas</h2>
      <p class="hint">O que o novo assinante recebe quando o pagamento confirma. Marcadores:
        <code>{{link}}</code> = link de criar senha (<strong>obrigatório</strong> — se remover, é re-adicionado sozinho) ·
        <code>{{nome}}</code> = nome do assinante.</p>
      {aviso}
      <form method="post" action="/admin/mensagens">
        <input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="salvar_mensagens">
        <div class="panel" style="max-width:none;margin:14px 0">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:8px">📲 WhatsApp</h3>
          <textarea name="wa" rows="13" style="{ta}">{_esc(wa)}</textarea>
        </div>
        <div class="panel" style="max-width:none;margin:14px 0">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:8px">✉️ E-mail — boas-vindas (cliente novo)</h3>
          <label>Assunto</label><input type="text" name="email_assunto" value="{_esc(email_assunto)}">
          <label style="margin-top:12px">Corpo (o <code>{{link}}</code> vira um botão)</label>
          <textarea name="email_corpo" rows="9" style="{ta}">{_esc(email_corpo)}</textarea>
        </div>
        <div class="panel" style="max-width:none;margin:14px 0">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:8px">✉️ E-mail — confirmação de renovação/recontratação</h3>
          <p class="hint">Enviado quando um pagamento renova sozinho (cartão à vista) ou quando um assinante cujo
            acesso já tinha expirado paga de novo — nos dois casos o mesmo texto. <strong>Nunca</strong> vai por
            WhatsApp. Marcadores: <code>{{nome}}</code> · <code>{{ate}}</code> = data até quando o acesso vale
            (<strong>obrigatório</strong> — se remover, é re-adicionado sozinho) ·
            <code>{{link}}</code> = link de entrar na conta (<strong>obrigatório</strong>, também re-adicionado sozinho).</p>
          <label>Assunto</label><input type="text" name="email_renov_assunto" value="{_esc(email_renov_assunto)}">
          <label style="margin-top:12px">Corpo (o <code>{{link}}</code> vira um botão)</label>
          <textarea name="email_renov_corpo" rows="9" style="{ta}">{_esc(email_renov_corpo)}</textarea>
        </div>
        <button class="actbtn" type="submit" style="margin-top:6px">Salvar mensagens</button>
      </form>
      {secao_auto}
    </div>"""
    return _pagina("Mensagens · Admin", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_whatsapp(info_dict, conn, token=""):
    """Tela de conexão do WhatsApp do curso (status + QR/código + reconectar)."""
    tk = _esc(token)
    conectado = info_dict.get("estado") == "open"
    if conectado:
        num = _esc(info_dict.get("numero") or "?")
        prof = f' · {_esc(info_dict.get("profile"))}' if info_dict.get("profile") else ""
        status = (
            f'<div class="infobox" style="background:rgba(47,158,107,.14);border-color:#2f9e6b66;color:var(--creme)">'
            f'✅ <strong>Conectado</strong> — número <span class="mono">{num}</span>{prof}</div>'
            f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">'
            f'<form method="post" action="/admin/whatsapp" onsubmit="return confirm(\'Reiniciar a conexão do WhatsApp?\')" style="margin:0">'
            f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="reiniciar">'
            f'<button class="actbtn ghost" type="submit">🔄 Reiniciar conexão</button></form>'
            f'<form method="post" action="/admin/whatsapp" onsubmit="return confirm(\'Desconectar este número? Vai precisar parear de novo pra enviar.\')" style="margin:0">'
            f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="desconectar">'
            f'<button class="actbtn ghost" type="submit">🔌 Desconectar</button></form></div>')
        refresh = ""
    else:
        qr = (conn or {}).get("qr")
        pc = (conn or {}).get("pairingCode")
        qr_html = (f'<img src="{_esc(qr)}" alt="QR de conexão" style="width:260px;height:260px;background:#fff;border-radius:12px;padding:8px">'
                   if qr else '<p class="hint">Gerando o QR… a página atualiza sozinha em instantes.</p>')
        pc_html = (f'<div style="font-family:ui-monospace,monospace;font-size:27px;letter-spacing:.16em;color:var(--ouro2);margin-top:8px">{_esc(pc)}</div>'
                   if pc else "")
        status = (
            f'<div class="infobox">⚠️ <strong>Desconectado</strong> — pareie o número que vai enviar o curso (no celular desse número).</div>'
            f'<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start;margin-top:18px">'
            f'<div>{qr_html}</div>'
            f'<div style="flex:1;min-width:250px">'
            f'<p class="hint"><strong>Jeito 1 — QR:</strong> WhatsApp do número novo → <em>Aparelhos conectados → Conectar um aparelho</em> → aponte a câmera pro QR ao lado.</p>'
            f'<p class="hint" style="margin-top:14px"><strong>Jeito 2 — código:</strong> na mesma tela, toque em <em>"Conectar com número de telefone"</em> e digite:</p>{pc_html}'
            f'<p class="hint" style="margin-top:16px">Esta página se atualiza sozinha — quando conectar, aparece o ✅ verde.</p>'
            f'</div></div>')
        refresh = '<meta http-equiv="refresh" content="10">'
    corpo = (f'<div class="wrap">{_admin_nav(token, "whatsapp")}'
             f'<div class="sectag" style="margin-top:8px">Painel do curador</div>'
             f'<h2 class="disp" style="font-size:40px;color:var(--creme);margin:2px 0 10px">WhatsApp do curso</h2>'
             f'<p class="hint">É por esta conexão que os estudos são enviados aos assinantes. '
             f'Instância <span class="mono">{_esc(info_dict.get("instance"))}</span>.</p>'
             f'{status}</div>')
    return _pagina("WhatsApp · Admin", corpo, logado=True, meta_extra=refresh + '<meta name="robots" content="noindex">')


def pagina_admin(assinantes, token="", cupons=None, confirmar_id=None, erro="",
                 reenviar_id=None, sucesso="", contagem_slots=None):
    """Tela de Assinantes no padrão do site (verde/dourado, cards com filtros)."""
    import phone
    import subscribers
    tk = _esc(token)
    admins = {phone.normalizar(w) for w in (config.ADMIN_WHATSAPPS or [])}
    erro_html = f'<div class="erro" style="margin:14px 0">{_esc(erro)}</div>' if erro else ""
    sucesso_html = (f'<div class="infobox" style="border-color:#2f9e6b66;background:#2f9e6b18;margin:14px 0">'
                    f'{_esc(sucesso)}</div>') if sucesso else ""
    alvo = next((s for s in assinantes if str(s.get("id")) == str(confirmar_id)), None) if confirmar_id else None
    confirm_html = ""
    if alvo:
        confirm_html = (
            '<div class="infobox" style="border-color:#c0562f66;background:#c0562f18;margin:14px 0">'
            f'<strong>Remover {_esc(alvo.get("nome") or alvo.get("whatsapp") or "este assinante")}?</strong> '
            f'Esta ação é permanente e apaga o cadastro ({_esc(alvo.get("whatsapp") or "—")}).'
            '<div style="display:flex;gap:10px;margin-top:12px">'
            '<form method="post" action="/admin" style="margin:0">'
            f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="remover_confirmar">'
            f'<input type="hidden" name="id" value="{_esc(alvo.get("id"))}">'
            '<button class="actbtn" style="background:#c0562f;color:#fff;padding:8px 16px">Confirmar remoção</button></form>'
            f'<a class="actbtn ghost" href="/admin?token={tk}" style="padding:8px 16px;text-decoration:none">Cancelar</a>'
            '</div></div>')
    alvo_re = next((s for s in assinantes if str(s.get("id")) == str(reenviar_id)), None) if reenviar_id else None
    reenviar_html = ""
    if alvo_re:
        reenviar_html = (
            '<div class="infobox" style="border-color:#c9a22766;background:#c9a22718;margin:14px 0">'
            f'<strong>Reenviar boas-vindas (WhatsApp) para '
            f'{_esc(alvo_re.get("nome") or alvo_re.get("whatsapp") or "este assinante")}?</strong> '
            f'Vai um link novo de criar-senha para {_esc(alvo_re.get("whatsapp") or "—")}.'
            '<div style="display:flex;gap:10px;margin-top:12px">'
            '<form method="post" action="/admin" style="margin:0">'
            f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="reenviar_confirmar">'
            f'<input type="hidden" name="id" value="{_esc(alvo_re.get("id"))}">'
            '<button class="actbtn" style="background:#2f9e6b;color:#fff;padding:8px 16px">Confirmar reenvio</button></form>'
            f'<a class="actbtn ghost" href="/admin?token={tk}" style="padding:8px 16px;text-decoration:none">Cancelar</a>'
            '</div></div>')
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
    def cel_editar_numero(s):
        return (f'<form method="post" action="/admin" '
                f'style="display:flex;flex-direction:column;gap:5px;min-width:170px">'
                f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="editar_numero">'
                f'<input type="hidden" name="id" value="{_esc(s.get("id"))}">'
                f'{_seletor_pais()}'
                f'<input type="text" name="numero" placeholder="novo número" required>'
                f'<button class="actbtn ghost" style="padding:6px 13px;font-size:12px" type="submit">✏️ Salvar número</button></form>')
    def cel_reenviar(s):
        return (f'<form method="post" action="/admin" style="margin:0">'
                f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="reenviar">'
                f'<input type="hidden" name="id" value="{_esc(s.get("id"))}">'
                f'<button class="actbtn ghost" style="padding:6px 13px;font-size:12px" type="submit">📨 Reenviar</button></form>')
    def cel_horario(s):
        import subscribers
        atual = subscribers.slot_de(s)
        opts = "".join(f'<option value="{sl}"{" selected" if sl == atual else ""}>{sl}</option>'
                       for sl in config.SLOTS)
        return (f'<form method="post" action="/admin" style="display:flex;gap:5px;align-items:center">'
                f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="definir_slot">'
                f'<input type="hidden" name="id" value="{_esc(s.get("id"))}">'
                f'<select name="slot" style="padding:5px 8px;font-size:12px;background:#0e211a;color:var(--creme);border:1px solid rgba(233,225,198,.2);border-radius:8px">{opts}</select>'
                f'<button class="actbtn ghost" style="padding:6px 12px;font-size:12px;white-space:nowrap;flex-shrink:0" type="submit">Salvar</button></form>')
    def _cel_remover(s):
        return (f'<form method="post" action="/admin" style="margin:0">'
                f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="remover">'
                f'<input type="hidden" name="id" value="{_esc(s.get("id"))}">'
                f'<button class="actbtn ghost" style="padding:6px 12px;font-size:12px">remover</button></form>')

    def card(s):
        atual = subscribers.slot_de(s)
        return (
            f'<div class="subcard" data-nome="{_esc((s.get("nome") or "").lower())}" data-slot="{_esc(atual)}" data-status="{_esc(s.get("status") or "")}">'
            f'<div class="subcard-top"><span class="subcard-nome">{_esc(s.get("nome") or "—")}</span>{badge(s.get("status"))}</div>'
            f'<div class="subrow"><span class="k">WhatsApp</span><span class="v mono">{_esc(s.get("whatsapp") or "—")}</span></div>'
            f'<details class="edit-num"><summary>✏️ editar número</summary>{cel_editar_numero(s)}</details>'
            f'<div class="subrow"><span class="k">E-mail</span><span class="v">{_esc(s.get("email") or "—")}</span></div>'
            f'<div class="subrow"><span class="k">Plano</span><span class="v gold">{_esc(s.get("plano") or "—")}</span></div>'
            f'<div class="subrow"><span class="k">Vencimento</span><span class="v mono">{_esc(s.get("proximo_vencimento") or "—")}</span></div>'
            f'<div class="subrow"><span class="k">Horário</span><span class="v">{cel_horario(s)}</span></div>'
            f'<div class="subcard-actions">{cel_curador(s)}{cel_reenviar(s)}{_cel_remover(s)}</div>'
            '</div>')
    cards = "".join(card(s) for s in assinantes)
    ativos = sum(1 for s in assinantes if s.get("status") == "ATIVO")
    n_cur = sum(1 for s in assinantes if s.get("curador"))
    def _cel_toggle_cupom(c):
        on = bool(c.get("ativo"))
        prox = "0" if on else "1"
        rotulo = "Desativar" if on else "Ativar"
        cls = "actbtn ghost" if on else "actbtn"
        return (f'<form method="post" action="/admin" style="margin:0">'
                f'<input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="toggle_cupom">'
                f'<input type="hidden" name="codigo" value="{_esc(c.get("codigo"))}">'
                f'<input type="hidden" name="on" value="{prox}">'
                f'<button class="{cls}" style="padding:6px 13px;font-size:12px" type="submit">{rotulo}</button></form>')
    def _cupom_row(c):
        on = bool(c.get("ativo"))
        # USADO só quando é de fato uso único CONSUMIDO (usos>0). Um cupom multi-uso
        # desativado pelo admin, ou um uso-único desativado ANTES de qualquer uso, nunca
        # foi "usado" — dizer isso engana quem lê esta tela pra saber o que está no ar.
        usado = bool(c.get("uso_unico")) and (c.get("usos") or 0) > 0 and not on
        if on:
            label, cor = "ATIVO", "#2f9e6b"
        elif usado:
            label, cor = "USADO", "#7a8a84"
        else:
            label, cor = "DESATIVADO", "#c0562f"
        uu = "uso único" if c.get("uso_unico") else "multi-uso"
        dur = "acesso p/ sempre" if not c.get("dias_acesso") else f"{c.get('dias_acesso')} dias de acesso"
        return (f'<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 0;border-top:1px solid rgba(233,225,198,.1)">'
                f'<div><span style="font-family:ui-monospace,Menlo,monospace;font-size:16px;color:var(--ouro2);letter-spacing:.06em">{_esc(c.get("codigo"))}</span>'
                f'<div style="font-family:system-ui;font-size:12px;color:var(--suave)">{_esc(c.get("descricao") or "sem descrição")} · {uu} · {dur} · {c.get("usos", 0)} uso(s)</div></div>'
                f'<div style="display:flex;align-items:center;gap:8px;flex-shrink:0">'
                f'<span style="font-family:system-ui;font-size:11px;font-weight:700;padding:4px 11px;border-radius:100px;background:{cor}22;color:{cor};border:1px solid {cor}66">{label}</span>'
                f'{_cel_toggle_cupom(c)}'
                f'</div></div>')
    cupons_lista = "".join(_cupom_row(c) for c in (cupons or [])) or '<p class="hint" style="margin-top:8px">Nenhum cupom gerado ainda.</p>'
    resumo_slots = ""
    if contagem_slots:
        itens = " · ".join(f"{sl}: {contagem_slots.get(sl, 0)}" for sl in config.SLOTS)
        resumo_slots = f'<p class="hint" style="margin-top:2px">Envio por horário — {itens}</p>'
    # contador de vendas ativas por plano (mensal vs anual; o resto vira "Outros")
    _pl = {"Mensal": 0, "Anual": 0, "Outros": 0}
    for s in assinantes:
        if s.get("status") != "ATIVO":
            continue
        sl = (s.get("plano") or "").strip()
        _pl["Mensal" if sl == "mensal" else "Anual" if sl == "anual" else "Outros"] += 1
    plano_cont = f'Ativos por plano — Mensal: {_pl["Mensal"]} · Anual: {_pl["Anual"]}'
    if _pl["Outros"]:
        plano_cont += f' · Outros: {_pl["Outros"]}'
    plano_cont_html = f'<p class="hint" style="margin-top:2px">{plano_cont}</p>'
    # filtros client-side: busca por nome + chips de status + chips de horário (rótulos com contagem)
    n_total = len(assinantes)
    slot_chips = ['<button type="button" class="f-slot on" data-slot="">Todos</button>']
    for sl in config.SLOTS:
        n = (contagem_slots or {}).get(sl)
        rotulo = sl + (f" ({n})" if n is not None else "")
        slot_chips.append(f'<button type="button" class="f-slot" data-slot="{sl}">{rotulo}</button>')
    _st = {"ATIVO": 0, "INADIMPLENTE": 0, "CANCELADO": 0}
    for s in assinantes:
        if s.get("status") in _st:
            _st[s.get("status")] += 1
    st_defs = [("", "Todos", n_total), ("ATIVO", "Ativos", _st["ATIVO"]),
               ("INADIMPLENTE", "Inadimplentes", _st["INADIMPLENTE"]), ("CANCELADO", "Cancelados", _st["CANCELADO"])]
    st_chips = "".join(
        f'<button type="button" class="f-status{" on" if v == "" else ""}" data-status="{v}">{lbl} ({n})</button>'
        for v, lbl, n in st_defs)
    filtros_html = (
        '<div class="subtools">'
        '<input id="f-nome" class="f-busca" type="search" placeholder="buscar por nome…" autocomplete="off">'
        f'<span id="f-count" class="f-count">mostrando {n_total} de {n_total}</span>'
        '</div>'
        f'<div class="subtools tight"><span class="f-lbl">Status</span><div class="f-chips">{st_chips}</div></div>'
        f'<div class="subtools tight"><span class="f-lbl">Horário</span><div class="f-chips">{"".join(slot_chips)}</div></div>')
    card_css = """<style>
    .subtools{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;margin:16px 0}
    .f-busca{flex:1;min-width:220px;background:var(--verde2);border:1px solid rgba(233,225,198,.2);border-radius:10px;
      color:var(--creme);font-family:system-ui,sans-serif;font-size:14px;padding:9px 13px}
    .f-busca:focus{outline:2px solid var(--ouro2);outline-offset:1px}
    .f-chips{display:flex;flex-wrap:wrap;gap:6px}
    .subtools.tight{margin:2px 0;gap:8px 10px}
    .f-lbl{font-family:system-ui,sans-serif;font-size:10px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--suave);min-width:52px}
    .f-count{font-family:system-ui,sans-serif;font-size:12.5px;color:var(--suave);white-space:nowrap}
    .f-slot,.f-status{cursor:pointer;font-family:system-ui,sans-serif;font-size:12px;font-weight:700;letter-spacing:.03em;
      padding:6px 12px;border-radius:100px;background:transparent;color:var(--suave);border:1px solid rgba(233,225,198,.24)}
    .f-slot.on,.f-status.on{background:#c9a22722;color:var(--ouro2);border-color:#c9a22766}
    .subgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px;margin:6px 0 24px}
    .subcard{background:rgba(255,255,255,.04);border:1px solid rgba(233,225,198,.14);border-radius:14px;padding:15px 16px}
    .subcard.hide{display:none}
    .subcard-top{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px}
    .subcard-nome{font-family:"Cormorant Garamond",Georgia,serif;font-size:22px;color:var(--creme);line-height:1.12;word-break:break-word}
    .subcard .subrow{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:6px 0;
      border-top:1px solid rgba(233,225,198,.08);font-family:system-ui,sans-serif;font-size:13px}
    .subcard .subrow .k{color:var(--suave);text-transform:uppercase;font-size:10px;letter-spacing:.09em;white-space:nowrap}
    .subcard .subrow .v{color:var(--texto);text-align:right;word-break:break-word;min-width:0}
    .subcard .subrow .v.gold{color:var(--ouro2)}
    .subcard .subrow .v.mono{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:var(--suave)}
    .edit-num{margin:2px 0}
    .edit-num>summary{cursor:pointer;list-style:none;color:var(--ouro2);font-family:system-ui,sans-serif;font-size:12.5px;padding:2px 0}
    .edit-num>summary::-webkit-details-marker{display:none}
    .edit-num[open]>summary{margin-bottom:8px}
    .subcard-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;padding-top:11px;border-top:1px solid rgba(233,225,198,.14)}
    </style>"""
    filtro_js = """<script>
    (function(){
      var busca=document.getElementById('f-nome');
      var cnt=document.getElementById('f-count');
      var slotChips=document.querySelectorAll('.f-slot');
      var stChips=document.querySelectorAll('.f-status');
      var cards=document.querySelectorAll('.subcard');
      var slot='',status='';
      function apply(){
        var q=((busca&&busca.value)||'').toLowerCase().trim();
        var vis=0;
        cards.forEach(function(c){
          var ok=(!q||(c.getAttribute('data-nome')||'').indexOf(q)>=0)
               &&(!slot||c.getAttribute('data-slot')===slot)
               &&(!status||c.getAttribute('data-status')===status);
          c.classList.toggle('hide',!ok); if(ok)vis++;
        });
        if(cnt)cnt.textContent='mostrando '+vis+' de '+cards.length;
      }
      function wire(list,set){list.forEach(function(ch){ch.addEventListener('click',function(){
        list.forEach(function(x){x.classList.remove('on')});ch.classList.add('on');set(ch);apply();
      });});}
      if(busca)busca.addEventListener('input',apply);
      wire(slotChips,function(ch){slot=ch.getAttribute('data-slot')||'';});
      wire(stChips,function(ch){status=ch.getAttribute('data-status')||'';});
    })();
    </script>"""
    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "assinantes")}
      <div class="sectag" style="margin-top:8px">Painel do curador</div>
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:2px 0 4px">Assinantes</h2>
      <p class="hint">{len(assinantes)} no total · {ativos} ativos · {n_cur} curador(es) &nbsp;·&nbsp; <a href="/curadoria" style="color:var(--ouro2)">🔬 ir para a Curadoria</a></p>
      {plano_cont_html}
      {resumo_slots}
      {erro_html}
      {sucesso_html}
      {confirm_html}
      {reenviar_html}
      <div class="infobox" style="margin:14px 0"><strong>Curadoria:</strong> quem estiver marcado como <strong>curador</strong> recebe, todo dia útil às <strong>18h</strong>, o resumo do dia com o link para revisar/aprovar antes do envio das 8h. Você (admin) recebe <em>sempre</em>. Marque um médico convidado aqui para ele ajudar na revisão.</div>
      {card_css}
      {filtros_html}
      <div class="subgrid">{cards or '<p class="hint" style="grid-column:1/-1">Nenhum assinante ainda.</p>'}</div>
      {filtro_js}
      <div style="display:flex;gap:18px;flex-wrap:wrap;margin:10px 0">
        <div class="panel" style="max-width:none;margin:0;flex:1;min-width:280px">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;color:var(--ouro2);margin-bottom:6px">Cupons de cortesia</h3>
          <p class="hint" style="margin-bottom:12px">Gere um cupom de <strong>uso único</strong>. Quem digitar no cadastro entra grátis; depois de 1 uso, ele desativa sozinho.</p>
          <form method="post" action="/admin">
            <input type="hidden" name="token" value="{tk}"><input type="hidden" name="acao" value="gerar_cupom">
            <label>Descrição (opcional — pra você lembrar de quem é)</label>
            <input type="text" name="descricao" placeholder="ex.: Dr. Fulano, cortesia evento">
            <label style="margin-top:10px">Tempo de acesso</label>
            <select name="dias">
              <option value="0">Para sempre</option>
              <option value="7">7 dias</option>
              <option value="15">15 dias</option>
              <option value="30">30 dias</option>
              <option value="90">90 dias</option>
              <option value="365">1 ano</option>
            </select>
            <button class="actbtn" type="submit" style="margin-top:14px">➕ Gerar cupom de uso único</button>
          </form>
          <div style="margin-top:16px">{cupons_lista}</div>
        </div>
      </div>
    </div>"""
    return _pagina("Assinantes · Admin", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


# ── Curadoria / Reserva (admin, token) — banco privado, NÃO publica no arquivo ──
def _chip_score(score):
    v = round(float(score or 0), 1)
    cls = "hi" if v >= 7 else ("md" if v >= 4 else "lo")
    estrela = "★ " if v >= 7 else ""
    return f'<span class="scorechip {cls}">{estrela}{v:g}</span>'


def _curadoria_faixa(estado):
    """Uma linha respondendo 'vou ficar sem conteúdo?'. Laranja quando o estoque é baixo."""
    n = estado.get("envios", 0)
    ate = estado.get("ate")
    if not n:
        txt = "Sem estoque — nenhum envio coberto"
    else:
        quando = f"{ate[8:10]}/{ate[5:7]}" if ate else "—"
        txt = f"Conteúdo garantido até {quando} · {n} envio{'s' if n != 1 else ''}"
    cls = "faixa baixo" if estado.get("baixo") else "faixa"
    return f'<div class="{cls}">📦 {_esc(txt)}</div>'


_AMANHA_ROT = {"APPROVED": "✅ aprovado", "EDITED": "✏️ editado", "SKIPPED": "🚫 bloqueado",
               "SENT": "📤 enviado"}


def _curadoria_amanha(amanha):
    """Cartão do estudo preparado p/ amanhã, com atalho pra revisão. None => nada."""
    if not amanha:
        return ""
    tok = _esc(amanha.get("review_token") or "")
    rot = _AMANHA_ROT.get(amanha.get("status"), "aguardando sua revisão")
    botao = (f'<a class="actbtn ghost" href="/revisar/{tok}" style="text-decoration:none;'
             f'padding:7px 14px;font-size:12.5px">Revisar</a>') if tok else ""
    return (f'<div class="amanha"><div class="am-t">📋 Amanhã sai</div>'
            f'<div class="am-tit">{_esc(amanha.get("titulo") or "—")}</div>'
            f'<div class="am-rod"><span>{_esc(rot)}</span>{botao}</div></div>')


def _curadoria_abas(aba, contagens, token, tema=""):
    """Abas de 1º nível (triagem/reserva/classicos) por querystring — sem JS."""
    from urllib.parse import quote
    tk = _esc(token)
    out = []
    for chave, rotulo in (("triagem", "Triagem"), ("reserva", "Reserva"), ("classicos", "Clássicos")):
        on = " on" if chave == aba else ""
        q = f"?token={tk}&aba={chave}"
        if chave == "triagem" and tema:
            q += f"&tema={quote(tema)}"
        out.append(f'<a class="tab{on}" href="/curadoria{q}" style="text-decoration:none">'
                   f'{rotulo} <span class="cnt">{contagens.get(chave, 0)}</span></a>')
    return f'<div class="tabs">{"".join(out)}</div>'


def _curadoria_item(c, token, aba="triagem", tema=""):
    """Um candidato da triagem: título linkado pro estudo, pergunta, meta e as ações
    imediatas (priorizar/descartar, ou desfazer se já priorizado)."""
    tk, cid = _esc(token), _esc(c.get("id"))
    alvo = c.get("url") or (f"https://doi.org/{c.get('doi')}" if c.get("doi") else "")
    tit = _esc(c.get("titulo"))
    titulo = (f'<a class="ctitle" href="{_esc(alvo)}" target="_blank" rel="noopener">{tit} ↗</a>'
              if alvo else f'<span class="ctitle">{tit}</span>')

    def _acao(acao, label):
        return (f'<form method="post" action="/curadoria" style="display:inline">'
                f'<input type="hidden" name="token" value="{tk}">'
                f'<input type="hidden" name="acao" value="{acao}">'
                f'<input type="hidden" name="id" value="{cid}">'
                f'<input type="hidden" name="aba" value="{_esc(aba)}">'
                f'<input type="hidden" name="tema" value="{_esc(tema)}">'
                f'<button class="slot-btn" type="submit">{label}</button></form>')

    if c.get("status") == "selecionado":
        acoes = ('<span class="badge badge-fila">⏳ gera hoje à noite</span>'
                 + _acao("desfazer", "↩️ Desfazer"))
    else:
        acoes = _acao("priorizar", "⬆️ Priorizar") + _acao("descartar", "🗑️ Descartar")
    return (f'<div class="candi" id="cand-{cid}"><span class="cbody">'
            f'<span style="display:flex;align-items:center;gap:8px;justify-content:space-between">'
            f'{titulo}{_chip_score(c.get("score"))}</span>'
            f'<span class="cperg">❓ {_esc(c.get("pergunta") or "—")}</span>'
            f'<span class="cmeta">{_esc(c.get("fonte", ""))} · {_esc(c.get("data", ""))}'
            f'{" · DOI " + _esc(c.get("doi")) if c.get("doi") else ""}</span>'
            f'<span class="cacts">{acoes}</span></span></div>')


_CUR_EMOJI = {"Obesidade": "⚖️", "Hormonal": "⚕️", "Lipedema": "🦵",
              "Performance": "🏃", "Longevidade": "🧬"}
_CUR_ORDEM = ["Obesidade", "Hormonal", "Lipedema", "Performance", "Longevidade"]


def _curadoria_chips(candidatos, token, tema=""):
    """Filtro por tema dentro da triagem. Mostra as 5 frentes sempre (inclusive com 0)."""
    from urllib.parse import quote
    tk = _esc(token)
    n = {}
    for c in candidatos:
        k = c.get("tema", "—")
        n[k] = n.get(k, 0) + 1
    temas = _CUR_ORDEM + [t for t in n if t not in _CUR_ORDEM]
    chips = [f'<a class="temachip{"" if tema else " on"}" href="/curadoria?token={tk}&aba=triagem">'
             f'Todos <b>{len(candidatos)}</b></a>']
    for t in temas:
        on = " on" if t == tema else ""
        chips.append(f'<a class="temachip{on}" href="/curadoria?token={tk}&aba=triagem&tema={quote(t)}">'
                     f'{_CUR_EMOJI.get(t, "•")} {_esc(t)} <b>{n.get(t, 0)}</b></a>')
    return f'<div class="temachips">{"".join(chips)}</div>'


def _curadoria_reserva_cards(prontos, resto, token):
    """Reserva agrupada em cards por tema — tema no nível de cima, status dentro.

    Antes eram ~51 itens numa lista corrida (medido em produção): scroll infinito e
    nenhuma noção de onde o estoque está seco.

    `<details name="reserva-tema">` faz o navegador tratar os cards como acordeão
    EXCLUSIVO — abrir um fecha o anterior — sem uma linha de JavaScript. Navegador
    antigo ignora o `name` e vira acordeão comum: degrada, não quebra.

    Tema com 0 aparece mesmo assim, igual aos chips da Triagem: é justamente o card
    vazio que mostra onde falta varredura.
    """
    porTema = {}
    for r in prontos:
        porTema.setdefault(r.get("tema") or "—", ([], []))[0].append(r)
    for r in resto:
        porTema.setdefault(r.get("tema") or "—", ([], []))[1].append(r)
    temas = _CUR_ORDEM + [t for t in porTema if t not in _CUR_ORDEM]

    cards = []
    for t in temas:
        ok, fora = porTema.get(t, ([], []))
        total = len(ok) + len(fora)
        corpo = ""
        if ok:
            corpo += (f'<div class="sectag">Prontos · {len(ok)}</div>'
                      + "".join(_curadoria_reserva_item(r, token) for r in ok))
        if fora:
            # "Fora do estoque" (neutro) e não "Já enviados": a maior parte desse grupo
            # numa instalação saudável é `agendado`, que ainda vai sair.
            corpo += (f'<div class="sectag" style="margin-top:18px">📦 Fora do estoque · '
                      f'{len(fora)}</div>'
                      + "".join(_curadoria_reserva_item(r, token) for r in fora))
        if not corpo:
            corpo = '<p class="hint">Nada neste tema. Rode a varredura ou priorize na Triagem.</p>'
        cards.append(
            f'<details name="reserva-tema" class="temacard">'
            f'<summary>{_CUR_EMOJI.get(t, "•")} {_esc(t)} <span class="cnt">{total}</span></summary>'
            f'<div class="temacard-corpo">{corpo}</div></details>')
    return "".join(cards)


def _curadoria_reserva_item(r, token):
    """Item da Reserva: título + <details> pra editar/remover (comportamento original)."""
    tok, rid = _esc(token), _esc(r.get("id"))
    prio = ' · <span style="color:var(--ouro2)">★ prioridade</span>' if r.get("prioridade") else ""
    return (
        f'<div class="item">'
        f'<div class="d">{_esc(r.get("tema"))} · {_esc(r.get("status"))}{prio}</div>'
        f'<div class="t">{_esc(r.get("titulo_pt"))}</div>'
        f'<details style="margin-top:8px">'
        f'<summary style="cursor:pointer;color:var(--ouro2);font-family:system-ui,sans-serif;'
        f'font-size:13px">✏️ editar / remover</summary>'
        f'<form method="post" action="/curadoria" style="margin-top:12px">'
        f'<input type="hidden" name="token" value="{tok}">'
        f'<input type="hidden" name="acao" value="editar_reserva">'
        f'<input type="hidden" name="id" value="{rid}">'
        f'<input type="hidden" name="aba" value="reserva">'
        f'<label>Título</label>'
        f'<input type="text" name="titulo_pt" value="{_esc(r.get("titulo_pt"))}" style="width:100%">'
        f'<label style="margin-top:10px">Resumo (pode ajustar o texto que a IA gerou)</label>'
        f'<textarea name="resumo" rows="10">{_esc(r.get("resumo"))}</textarea>'
        f'<button class="actbtn" type="submit">Salvar alterações</button>'
        f'</form>'
        f'<form method="post" action="/curadoria" '
        f'onsubmit="return confirm(\'Remover este item da reserva?\')" style="margin-top:10px">'
        f'<input type="hidden" name="token" value="{tok}">'
        f'<input type="hidden" name="acao" value="remover_reserva">'
        f'<input type="hidden" name="id" value="{rid}">'
        f'<input type="hidden" name="aba" value="reserva">'
        f'<button class="actbtn ghost" type="submit">🗑️ Remover da reserva</button>'
        f'</form></details></div>')


def _curadoria_ferramentas(token):
    """Ações raras, recolhidas: adicionar meu estudo (PDF) e as duas varreduras."""
    tok = _esc(token)
    def _varredura(acao, label, pergunta):
        return (f'<form method="post" action="/curadoria" style="display:inline" '
                f'onsubmit="return confirm(\'{pergunta}\')">'
                f'<input type="hidden" name="token" value="{tok}">'
                f'<input type="hidden" name="acao" value="{acao}">'
                f'<button class="actbtn ghost" type="submit">{label}</button></form>')
    return f"""
      <details style="margin-top:26px">
        <summary style="cursor:pointer;color:var(--ouro2);font-family:var(--ui);font-size:13px">
          ⚙️ Ferramentas</summary>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 18px">
          {_varredura("varrer", "🔎 Varrer agora",
                      "Rodar a varredura no Europe PMC (Haiku)? Pode levar 1–2 min.")}
          {_varredura("varrer_classicos", "🏛️ Varrer clássicos",
                      "Buscar estudos-marco por citações? Pode levar 1–2 min.")}
          {_varredura("backfill_tags", "🏷️ Etiquetar estudos (tags)",
                      "Etiquetar estudos existentes sem tags? Pode levar alguns segundos.")}
          {_varredura("varrer_presos", "🧹 Liberar candidatos presos",
                      "Liberar candidatos travados em agendado sem slot na agenda de volta pro pool? "
                      "Seguro rodar mais de uma vez.")}
          {_varredura("encorpar_corpus", "📚 Encorpar a base",
                      "Varrer os últimos 6 meses mês a mês e guardar na MEMÓRIA (não entra "
                      "na triagem). Leva alguns minutos e roda em segundo plano — o aviso "
                      "chega no seu WhatsApp. Seguro rodar mais de uma vez.")}
          {_varredura("limpar_nome", "🪪 Tirar meu nome do estoque",
                      "Os estudos gerados antes do conserto abrem com \\'Mensagem prática para "
                      "Dr. Diego\\' — e isso vai pro assinante. Tirar o endereçamento dos resumos "
                      "já na fila? A conduta clínica não muda. Seguro rodar mais de uma vez.")}
        </div>
        <div class="panel" style="max-width:none;margin:0">
          <h3 style="font-family:'Cormorant Garamond',Georgia,serif;font-size:23px;
                     color:var(--ouro2);margin-bottom:6px">➕ Adicionar meu estudo</h3>
          <p class="hint" style="margin-bottom:14px">Sobe o PDF (ou cola o texto). Gero o resumo
            e ele entra na <strong>fila, na frente</strong> — vai pros assinantes no próximo dia
            útil (com seu review das 18h).</p>
          <form method="post" action="/curadoria" enctype="multipart/form-data" id="up-curadoria">
            <input type="hidden" name="token" value="{tok}">
            <label>PDF do estudo</label>
            <input type="file" name="pdf" accept="application/pdf"
                   style="color:var(--suave);font-family:system-ui,sans-serif;margin-bottom:14px">
            <label>…ou cole o texto/resumo (se não tiver PDF)</label>
            <textarea name="texto" rows="3" placeholder="Cole aqui o abstract do estudo…"></textarea>
            <input type="text" name="titulo"
                   placeholder="Título (opcional — se vazio, eu crio a partir do texto)"
                   style="width:100%;margin-bottom:10px">
            <div style="display:flex;gap:10px;flex-wrap:wrap">
              <input type="text" name="fonte" placeholder="Revista (opcional)" style="flex:1">
              <input type="text" name="doi" placeholder="DOI (opcional)" style="flex:1">
            </div>
            <button class="actbtn" type="submit" style="margin-top:14px">
              Gerar resumo e adicionar à fila</button>
          </form>
          {ui.progresso_upload("up-curadoria")}
        </div>
      </details>"""


def pagina_curadoria(estado, amanha, candidatos, reserva, classicos, token,
                     aba="triagem", tema="", msg=""):
    """Bancada de triagem: faixa de estoque + o que sai amanhã + abas
    (Triagem · Reserva · Clássicos) + ferramentas recolhidas."""
    aba = aba if aba in ("triagem", "reserva", "classicos") else "triagem"
    # defesa: um "classico" nunca aparece na triagem, mesmo que a rota regrida e
    # pare de separar `candidatos` por tipo ao montar a lista (ver curadoria.
    # montar_candidatos_triagem, que já faz esse filtro — isto é só um segundo freio).
    candidatos = [c for c in candidatos if c.get("tipo") != "classico"]
    prontos = [r for r in reserva if r.get("status") == "pronto"]
    resto_reserva = [r for r in reserva if r.get("status") != "pronto"]
    cl_cands = (classicos or {}).get("candidatos", [])
    cl_banco = (classicos or {}).get("banco", [])
    contagens = {"triagem": len(candidatos), "reserva": len(prontos), "classicos": len(cl_cands)}
    msg_html = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""

    if aba == "reserva":
        corpo_aba = (_curadoria_reserva_cards(prontos, resto_reserva, token)
                     if (prontos or resto_reserva) else
                     '<p class="hint">Reserva vazia. Priorize candidatos na '
                     'Triagem — os resumos são gerados automaticamente à noite.</p>')
    elif aba == "classicos":
        lista = "".join(_curadoria_item(c, token, "classicos", "") for c in cl_cands)
        banco = "".join(
            f'<div class="item"><div class="d">{_esc(c.get("tema"))} · '
            f'{_esc(str(c.get("citacoes", 0)))} citações</div>'
            f'<div class="t">{_esc(c.get("titulo_pt"))}</div></div>' for c in cl_banco)
        corpo_aba = (
            '<p class="hint">Estudos-marco (evergreen), ranqueados por citações. '
            'Servem de piso quando falta conteúdo fresco.</p>'
            + (lista or '<p class="hint">Nenhum clássico aguardando aprovação. '
                        'Rode <strong>🏛️ Varrer clássicos</strong> em Ferramentas.</p>')
            + (f'<div class="sectag" style="margin-top:24px">🏛️ No banco · {len(cl_banco)}</div>{banco}'
               if cl_banco else ""))
    else:
        vis = [c for c in candidatos if not tema or c.get("tema") == tema]
        # Filtro de tema ativo e vazio => aponta pro ajuste da busca DAQUELE tema
        # (mensagem preservada da versão anterior da tela, que tinha abas por tema).
        vazio = ('<p class="hint">Nenhum candidato neste tema. Rode a varredura ou '
                 'ajuste a busca deste tema.</p>' if tema else
                 '<p class="hint">Nada aguardando triagem aqui. A máquina segue '
                 'escolhendo e enviando sozinha — você decide às 18h.</p>')
        corpo_aba = (_curadoria_chips(candidatos, token, tema)
                     + ("".join(_curadoria_item(c, token, "triagem", tema) for c in vis) or vazio))

    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "curadoria")}
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:6px 0 10px">Curadoria</h2>
      {_curadoria_faixa(estado)}
      {_curadoria_amanha(amanha)}
      {msg_html}
      {_curadoria_abas(aba, contagens, token, tema)}
      {corpo_aba}
      {_curadoria_ferramentas(token)}
    </div>"""
    return _pagina("Curadoria", corpo, logado=True,
                   meta_extra='<meta name="robots" content="noindex">')


# ── Agenda de envios (admin, token) — grade de 3 semanas, arrastar-e-soltar ──
_BADGE = {"reserva": "✓ pronto", "fila": "⏳ gera 18h", "pulado": "💤 folga", "vazio": "⚠️ vazio"}
_DIA_BR = {0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sáb", 6: "dom"}


def _slot_card(s, token, opcoes_html):
    """Card de um dia da agenda (com ações). `s` tem data/tipo/tema/titulo/fixado."""
    from datetime import datetime
    dt = datetime.strptime(s["data"], "%Y-%m-%d")
    dia = _DIA_BR[dt.weekday()]
    de = _esc(s["data"])
    tipo = s.get("tipo") or "vazio"
    fixado = s.get("fixado")
    titulo = _esc(s.get("titulo") or "—")
    tema = _esc(s.get("tema") or "")
    badge = _esc(_BADGE.get(tipo, tipo))
    badge_cls = tipo
    if s.get("passado"):        # dia já passado: histórico (mostra o tema/estudo enviado)
        tem_estudo = bool(s.get("titulo"))
        badge = "enviado" if tem_estudo else "—"
        badge_cls = "reserva" if tem_estudo else "pulado"   # verde p/ 'enviado'
    cab = (f'<div class="slot-h"><span class="slot-dia">{dia} · {s["data"][8:10]}/{s["data"][5:7]}</span>'
           f'<span class="badge badge-{badge_cls}">{badge}</span></div>'
           f'<div class="slot-tema">{tema}</div>'
           f'<div class="slot-tit">{titulo}</div>')
    if s.get("passado"):        # dia já passado nesta semana: histórico, só leitura
        return f'<div class="slot passado" data-data="{de}">{cab}</div>'
    def _acao(acao, label):
        return (f'<form method="post" action="/agenda" style="display:inline">'
                f'<input type="hidden" name="token" value="{_esc(token)}">'
                f'<input type="hidden" name="acao" value="{acao}">'
                f'<input type="hidden" name="data" value="{de}">'
                f'<button class="slot-btn" type="submit">{label}</button></form>')
    b_fixar = _acao("desafixar", "📌 Fixado") if fixado else _acao("fixar", "📌 Fixar")
    b_pular = _acao("despular", "☀️ Reativar") if tipo == "pulado" else _acao("pular", "💤 Folga")
    mover = (f'<form method="post" action="/agenda" style="display:inline" class="slot-mv">'
             f'<input type="hidden" name="token" value="{_esc(token)}">'
             f'<input type="hidden" name="acao" value="mover">'
             f'<input type="hidden" name="data" value="{de}">'
             f'<select name="dest" class="slot-sel" title="Trocar este estudo com outro dia" '
             f'onchange="if(this.value)this.form.submit()">'
             f'<option value="">⇄ Trocar…</option>{opcoes_html}</select>'
             f'<noscript><button class="slot-btn" type="submit">ok</button></noscript></form>')
    cls = "slot fixado" if fixado else "slot"
    return (f'<div class="{cls}" draggable="true" data-data="{de}">{cab}'
            f'<div class="slot-acts">{b_fixar}{b_pular}{mover}</div></div>')


def pagina_precos(planos, token, msg=""):
    """Admin: editar o preço (base) de cada plano. planos = dicts vigentes."""
    import pricing
    tk = _esc(token)
    aviso = f'<p class="hint">{_esc(msg)}</p>' if msg else ""
    linhas = ""
    for p in planos:
        slug = _esc(p["slug"])
        base = float(p.get("base") or 0)
        extra = ""
        if p.get("slug") == "anual":
            ops = pricing.opcoes_parcelas(base)
            extra = f' · 12x de {_esc(pricing.fmt_brl(ops[-1]["por_parcela"]))}'
        preview = f'{_esc(p.get("preco") or "")} <span class=hint>{_esc(p.get("nota") or "")}{extra}</span>'
        linhas += (
            f'<div style="margin:14px 0;padding:12px;border:1px solid #333;border-radius:8px">'
            f'<b>{_esc(p.get("nome") or slug)}</b> — vigente: {preview}<br>'
            f'<form method="post" action="/admin/precos" style="display:inline-block;margin-top:6px">'
            f'<input type="hidden" name="acao" value="salvar_preco">'
            f'<input type="hidden" name="token" value="{tk}">'
            f'<input type="hidden" name="slug" value="{slug}">'
            f'R$ <input name="preco" inputmode="decimal" value="{_esc(f"{base:.0f}" if base == int(base) else base)}" '
            f'style="padding:6px;width:120px"> '
            f'<button type="submit">Salvar</button></form> '
            f'<form method="post" action="/admin/precos" style="display:inline">'
            f'<input type="hidden" name="acao" value="resetar_preco">'
            f'<input type="hidden" name="token" value="{tk}">'
            f'<input type="hidden" name="slug" value="{slug}">'
            f'<button type="submit">Voltar ao padrão</button></form></div>')
    corpo = (f'<div class="wrap">{_admin_nav(token, "precos")}'
             f'<h2>💰 Preços dos planos</h2>{aviso}'
             f'<p class=hint>O valor editado vale nas vendas novas. Assinantes atuais mantêm o valor '
             f'que contrataram.</p>{linhas}</div>')
    return _pagina("Preços · Admin", corpo, logado=True, atual="precos",
                   meta_extra='<meta name="robots" content="noindex">')


def pagina_agenda(semanas, estoque, token, msg=""):
    opcoes = "".join(
        f'<option value="{_esc(s["data"])}">{_esc(s["data"][8:10])}/{_esc(s["data"][5:7])}</option>'
        for sem in semanas for s in sem if not s.get("passado"))
    blocos = ""
    for i, sem in enumerate(semanas):
        cards = "".join(_slot_card(s, token, opcoes) for s in sem)
        blocos += f'<h3 class="sem-h">Semana {i+1}</h3><div class="sem-row">{cards}</div>'
    aviso = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""
    rematerializar = (f'<form method="post" action="/agenda" style="display:inline">'
                      f'<input type="hidden" name="token" value="{_esc(token)}">'
                      f'<input type="hidden" name="acao" value="rematerializar">'
                      f'<button class="actbtn">↻ Rematerializar</button></form>')
    css = """<style>
    .sem-h{color:var(--ouro2);font-family:var(--ui);font-size:12px;font-weight:700;letter-spacing:.08em;
          text-transform:uppercase;margin:22px 0 8px}
    .sem-row{display:flex;gap:12px;flex-wrap:wrap}
    .slot{flex:1;min-width:200px;background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.02));
          border:1px solid var(--line);border-radius:14px;padding:13px 15px 14px;cursor:grab;transition:.16s}
    .slot:hover{border-color:rgba(201,162,39,.35)}
    .slot.dragover{border-color:var(--ouro);box-shadow:0 0 0 2px rgba(201,162,39,.28)}
    .slot.fixado{border-color:rgba(201,162,39,.5);background:linear-gradient(180deg,rgba(201,162,39,.09),rgba(255,255,255,.02))}
    .slot-h{display:flex;justify-content:space-between;align-items:center;gap:8px}
    .slot-dia{font-family:var(--ui);font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--creme);opacity:.65}
    .slot-tema{font-family:var(--ui);font-size:12px;font-weight:600;letter-spacing:.02em;color:var(--ouro2);margin:10px 0 3px}
    .slot-tit{font-size:13.5px;color:var(--creme);line-height:1.35;min-height:37px}
    .slot-acts{display:flex;gap:6px;margin-top:12px;flex-wrap:wrap;align-items:center}
    .slot-mv{display:inline}
    .slot-sel{appearance:none;-webkit-appearance:none}
    .slot.fixado .slot-btn{border-color:rgba(201,162,39,.4)}
    .slot.passado{opacity:.42;cursor:default;background:rgba(255,255,255,.015);border-style:dashed}
    .slot.passado .slot-tit{min-height:0}
    </style>"""
    js = """<script>
    (function(){
      let orig=null;
      document.querySelectorAll('.slot:not(.passado)').forEach(function(el){
        el.addEventListener('dragstart',function(){orig=el.dataset.data;});
        el.addEventListener('dragover',function(e){e.preventDefault();el.classList.add('dragover');});
        el.addEventListener('dragleave',function(){el.classList.remove('dragover');});
        el.addEventListener('drop',function(e){
          e.preventDefault();el.classList.remove('dragover');
          var dest=el.dataset.data; if(!orig||orig===dest)return;
          var f=document.createElement('form'); f.method='post'; f.action='/agenda';
          f.innerHTML='<input name="token" value="'+TOKEN+'"><input name="acao" value="mover">'+
            '<input name="data" value="'+orig+'"><input name="dest" value="'+dest+'">';
          document.body.appendChild(f); f.submit();
        });
      });
    })();
    </script>"""
    corpo = ('<div class="wrap">' + _admin_nav(token, "agenda") + css +
             f'<h2 class="disp" style="font-size:34px;color:var(--creme);margin:6px 0 4px">Agenda de envios</h2>'
             f'<p style="color:var(--creme);opacity:.75;font-size:13px">Arraste um dia sobre outro pra trocar. '
             f'Estoque pronto: <strong>{int(estoque)}</strong>. {rematerializar}</p>'
             f'{aviso}{blocos}'
             + js.replace("TOKEN", '"' + _esc(token) + '"')
             + '</div>')
    return _pagina("Agenda · Admin", corpo, logado=True,
                   meta_extra='<meta name="robots" content="noindex">')


def pagina_series(ctx, token, serie_aberta_id="", dia_min="", msg="", confirmar_cancelar=""):
    """Montador de séries: lista + (rascunho aberto) busca por tag + itens ordenados
    + adicionar meu estudo + ativar com data de início."""
    tk = _esc(token)
    aviso = f'<p class="hint">{_esc(msg)}</p>' if msg else ""

    def _badge(st):
        cor = {"rascunho": "#8a7", "ativa": "var(--ouro2)", "concluida": "#999"}.get(st, "#999")
        return f'<span style="color:{cor};font-size:12px;text-transform:uppercase">{_esc(st)}</span>'

    linhas = ""
    for s in ctx.get("series", []):
        linhas += (f'<li style="margin:6px 0"><a href="/series?serie={_esc(s["id"])}&token={tk}" '
                   f'style="color:var(--ouro2);text-decoration:none">{_esc(s.get("nome") or "(sem nome)")}</a> '
                   f'&nbsp;{_badge(s.get("status",""))}</li>')
    lista = f'<ul style="list-style:none;padding:0">{linhas or "<li class=hint>Nenhuma série ainda.</li>"}</ul>'

    nova = (f'<form method="post" action="/series" style="margin:10px 0">'
            f'<input type="hidden" name="acao" value="criar">'
            f'<input type="hidden" name="token" value="{tk}">'
            f'<input name="nome" placeholder="Nome da nova série (ex.: Série GLP1)" '
            f'style="padding:8px;min-width:280px">'
            f'<button type="submit">➕ Criar série</button></form>')

    montador = ""
    aberta = ctx.get("aberta")
    if aberta:
        sid = _esc(aberta["serie"]["id"])
        st = aberta["serie"].get("status", "")
        # itens da série
        its = ""
        for it in aberta.get("itens", []):
            iid = _esc(it["id"])
            dia = f' · <b>{_esc(it["data"])}</b>' if it.get("data") else ""
            its += (f'<li style="margin:5px 0;display:flex;gap:6px;align-items:center">'
                    f'<span>{_esc(it.get("titulo") or it.get("ref_id"))} '
                    f'<span class=hint>({_esc(it.get("ref_tipo"))}{dia})</span></span>')
            if st == "rascunho":
                for direc, seta in (("cima", "↑"), ("baixo", "↓")):
                    its += (f'<form method="post" action="/series" style="display:inline">'
                            f'<input type="hidden" name="acao" value="reordenar">'
                            f'<input type="hidden" name="token" value="{tk}">'
                            f'<input type="hidden" name="serie" value="{sid}">'
                            f'<input type="hidden" name="item" value="{iid}">'
                            f'<input type="hidden" name="direcao" value="{direc}">'
                            f'<button type="submit">{seta}</button></form>')
                its += (f'<form method="post" action="/series" style="display:inline">'
                        f'<input type="hidden" name="acao" value="remover_item">'
                        f'<input type="hidden" name="token" value="{tk}">'
                        f'<input type="hidden" name="serie" value="{sid}">'
                        f'<input type="hidden" name="item" value="{iid}">'
                        f'<button type="submit">🗑️</button></form>')
            its += "</li>"
        itens_html = f'<ul style="list-style:none;padding:0">{its or "<li class=hint>Vazia.</li>"}</ul>'

        cancelar_html = ""
        if st in ("ativa", "incompleta"):
            if str(confirmar_cancelar) == str(aberta["serie"]["id"]):
                n_dias = sum(1 for i in aberta.get("itens", []) if i.get("data"))
                cancelar_html = (
                    f'<div style="margin:12px 0;padding:10px;border:1px solid var(--ouro2)">'
                    f'<p>Cancelar libera os dias <b>futuros</b> que ainda não foram preparados '
                    f'e devolve esses estudos pro estoque. Esta série tem {n_dias} dia(s) '
                    f'marcado(s) — os já enviados, com rascunho pronto ou já ocupados por '
                    f'outro estudo ficam como estão. A série volta pra rascunho.</p>'
                    f'<form method="post" action="/series" style="display:inline">'
                    f'<input type="hidden" name="acao" value="cancelar_confirmar">'
                    f'<input type="hidden" name="token" value="{tk}">'
                    f'<input type="hidden" name="serie" value="{sid}">'
                    f'<button type="submit">🚫 Confirmar cancelamento</button></form>'
                    f'&nbsp;<a href="/series?serie={sid}&token={tk}">Voltar</a></div>')
            else:
                cancelar_html = (
                    f'<form method="post" action="/series" style="display:inline">'
                    f'<input type="hidden" name="acao" value="cancelar">'
                    f'<input type="hidden" name="token" value="{tk}">'
                    f'<input type="hidden" name="serie" value="{sid}">'
                    f'<button type="submit">🚫 Cancelar série</button></form>')

        if st == "rascunho":
            # busca por tag
            busca = (f'<form method="post" action="/series" style="margin:10px 0">'
                     f'<input type="hidden" name="acao" value="buscar">'
                     f'<input type="hidden" name="token" value="{tk}">'
                     f'<input type="hidden" name="serie" value="{sid}">'
                     f'<input name="termo" placeholder="Buscar no estoque por tag (ex.: glp1)" '
                     f'style="padding:8px;min-width:260px">'
                     f'<button type="submit">🔎 Buscar</button></form>')
            res = ""
            for r in ctx.get("resultados", []):
                res += (f'<li style="margin:4px 0">'
                        f'<form method="post" action="/series" style="display:inline">'
                        f'<input type="hidden" name="acao" value="add_item">'
                        f'<input type="hidden" name="token" value="{tk}">'
                        f'<input type="hidden" name="serie" value="{sid}">'
                        f'<input type="hidden" name="tipo" value="{_esc(r.get("tipo"))}">'
                        f'<input type="hidden" name="id" value="{_esc(r.get("id"))}">'
                        f'<input type="hidden" name="titulo" value="{_esc(r.get("titulo"))}">'
                        f'<input type="hidden" name="tema" value="{_esc(r.get("tema"))}">'
                        f'<button type="submit">➕</button> {_esc(r.get("titulo"))} '
                        f'<span class=hint>({_esc(r.get("tipo"))} · {_esc(", ".join(r.get("tags", [])))})</span>'
                        f'</form></li>')
            resultados_html = (f'<ul style="list-style:none;padding:0">{res}</ul>' if res else "")

            # adicionar meu estudo (upload) — multipart, mesmo campo do /curadoria
            meu = (f'<form method="post" action="/series" enctype="multipart/form-data" '
                   f'id="up-serie" '
                   f'style="margin:12px 0;padding:10px;border:1px solid #333;border-radius:8px">'
                   f'<b>➕ Adicionar meu estudo</b><br>'
                   f'<input type="hidden" name="acao" value="add_meu_estudo">'
                   f'<input type="hidden" name="token" value="{tk}">'
                   f'<input type="hidden" name="serie" value="{sid}">'
                   f'<input name="titulo" placeholder="Título (opcional)" style="padding:6px"><br>'
                   f'<input type="file" name="pdf" accept="application/pdf"><br>'
                   f'<textarea name="texto" placeholder="…ou cole o resumo" '
                   f'style="width:100%;height:70px"></textarea>'
                   f'<button type="submit">Enviar</button></form>'
                   f'{ui.progresso_upload("up-serie")}')

            ativar = (f'<form method="post" action="/series" style="margin:12px 0">'
                      f'<input type="hidden" name="acao" value="ativar">'
                      f'<input type="hidden" name="token" value="{tk}">'
                      f'<input type="hidden" name="serie" value="{sid}">'
                      f'<label>Data de início: '
                      f'<input type="date" name="data_inicio" min="{_esc(dia_min)}" '
                      f'value="{_esc(dia_min)}" required></label> '
                      f'<button type="submit">🚀 Ativar série</button>'
                      f'<span class=hint> (ocupa os próximos dias úteis livres, em ordem)</span></form>')
            montador = (f'<h3>{_esc(aberta["serie"].get("nome"))} {_badge(st)}</h3>'
                        f'{itens_html}{busca}{resultados_html}{meu}{ativar}')
        else:
            montador = (f'<h3>{_esc(aberta["serie"].get("nome"))} {_badge(st)}</h3>'
                        f'<p class=hint>Início: {_esc(aberta["serie"].get("data_inicio") or "—")}. '
                        f'Série já ativada/concluída — edição de itens é fora do MVP.</p>'
                        f'{itens_html}{cancelar_html}')

    corpo = (f'<div class="wrap">{_admin_nav(token, "series")}'
             f'<h2>🎬 Séries de estudos</h2>{aviso}{nova}{lista}{montador}</div>')
    return _pagina("Séries · Admin", corpo, logado=True, atual="series")


# ── Arquivo (protegido) ──
def _arquivo_tabs(temas, ativo):
    """Barra de abas por tema (links). ativo = slug destacado."""
    if not temas:
        return ""
    tabs = "".join(
        f'<a class="tab{" on" if t["slug"] == ativo else ""}" href="/artigos/{_esc(t["slug"])}">'
        f'{_esc(t.get("emoji",""))} {_esc(t["rotulo"])} <span class="cnt">{t["total"]}</span></a>'
        for t in temas)
    return f'<div class="tabs">{tabs}</div>'


def _entry_html(meta, d, dt):
    fonte = _esc(d.get("fonte", "") or "")
    doi = f' · DOI {_esc(d.get("doi"))}' if d.get("doi") else ""
    return (f'<a class="entry" href="/artigos/{_esc(meta["slug"])}/{_esc(d["data"])}">'
            f'<div class="date">{_esc(_data_br_curto(dt))}</div>'
            f'<div><div class="etag">{_esc(meta["rotulo"])}</div>'
            f'<div class="etitle">{_esc(d["titulo_pt"])}</div>'
            f'<div class="esrc">{fonte}{doi}</div></div></a>')


def _agrupar_por_mes_semana(meta, digests):
    """Agrupa as edições por MÊS (mais recente aberto) e, dentro, por SEMANA.
    Evita o scroll gigante: meses antigos vêm recolhidos."""
    from datetime import date, timedelta
    from collections import OrderedDict
    parsed = []
    for d in digests:
        try:
            dt = date.fromisoformat(d["data"])
        except Exception:
            continue
        parsed.append((dt, d))
    parsed.sort(key=lambda x: x[0], reverse=True)
    meses = OrderedDict()
    for dt, d in parsed:
        meses.setdefault((dt.year, dt.month), []).append((dt, d))
    blocos = []
    for idx, (mk, itens) in enumerate(meses.items()):
        semanas = OrderedDict()
        for dt, d in itens:
            seg = dt - timedelta(days=dt.weekday())
            semanas.setdefault(seg, []).append((dt, d))
        corpo_sem = "".join(
            f'<div class="week-h">{_esc(_semana_label(seg))}</div>'
            + "".join(_entry_html(meta, d, dt) for dt, d in ents)
            for seg, ents in semanas.items())
        n = len(itens)
        cls = "month" if idx == 0 else "month collapsed"
        blocos.append(
            f'<div class="{cls}"><div class="month-h" onclick="this.parentElement.classList.toggle(\'collapsed\')">'
            f'<span class="mt disp">{_esc(_mes_nome(mk[1]))} {mk[0]}</span>'
            f'<span class="rt"><span class="mc">{n} edi{"ção" if n == 1 else "ções"}</span>'
            f'<span class="chev">▾</span></span></div>'
            f'<div class="month-body">{corpo_sem}</div></div>')
    return "".join(blocos)


def hub_temas(temas):
    """Estado vazio do arquivo (quando há temas, o serve chama lista_tema no 1º)."""
    corpo = ('<div class="wrap">'
             '<div class="sectag" style="margin-top:8px">Portal do assinante</div>'
             '<h2 class="disp" style="font-size:clamp(30px,4.4vw,44px);color:var(--cream);margin-bottom:6px">Arquivo</h2>'
             '<p class="sub">Ainda não há edições publicadas. Assim que a primeira for enviada, ela aparece '
             'aqui — organizada por tema, mês e semana.</p></div>')
    return _pagina(f"Arquivo · {PRODUTO}", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def lista_tema(meta, digests, temas=None):
    tabs = _arquivo_tabs(temas, meta["slug"])
    grupos = (_agrupar_por_mes_semana(meta, digests) if digests
              else '<div class="empty-note">Nenhuma edição neste tema ainda.</div>')
    corpo = (f'<div class="wrap">'
             f'<div class="sectag" style="margin-top:8px">Portal do assinante</div>'
             f'<h2 class="disp" style="font-size:clamp(30px,4.4vw,44px);color:var(--cream);margin-bottom:6px">Arquivo por tema</h2>'
             f'<p class="sub" style="margin-bottom:22px">Tudo que você já recebeu, organizado por frente, por mês e por semana.</p>'
             f'{tabs}{grupos}</div>')
    return _pagina(f'{meta["rotulo"]} · {PRODUTO}', corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_digest(meta, d, vizinhos=None):
    try:
        grafico = json.loads(d.get("grafico") or "null")
    except Exception:
        grafico = None
    tag = f'{_esc(meta.get("emoji",""))} {_esc(meta["rotulo"])} · edição'.strip()
    corpo_doc = (f'<div class="doc">'
                 f'<span class="rtag">{tag}</span>'
                 f'<h1 class="title">{_esc(d["titulo_pt"])}</h1>'
                 f'<div class="meta">{pdf._meta_linha(d.get("fonte"), _data_br(d["data"]), d.get("doi"))}</div>'
                 f'<div class="corpo">{pdf._resumo_html(d.get("resumo",""))}</div>'
                 f'{pdf._grafico_html(grafico)}{pdf._kit_html(d.get("gancho",""), d)}')
    if d.get("url"):
        corpo_doc += f'<div style="margin-top:22px"><a class="docbtn" href="{_esc(d["url"])}" target="_blank" rel="noopener">Ver o estudo original ↗</a></div>'
    corpo_doc += '</div>'
    pn = ""
    if vizinhos and (vizinhos[0] or vizinhos[1]):
        ant, prox = vizinhos
        esq = (f'<a class="pn-btn prev" href="/artigos/{_esc(meta["slug"])}/{_esc(ant["data"])}">'
               f'<div class="k">← Edição anterior</div><div class="v">{_esc(_data_br(ant["data"]))}</div></a>'
               ) if ant else '<span class="pn-btn" style="visibility:hidden"></span>'
        dire = (f'<a class="pn-btn next" href="/artigos/{_esc(meta["slug"])}/{_esc(prox["data"])}">'
                f'<div class="k">Próxima edição →</div><div class="v">{_esc(_data_br(prox["data"]))}</div></a>'
                ) if prox else '<span class="pn-btn" style="visibility:hidden"></span>'
        pn = f'<div class="prevnext">{esq}{dire}</div>'
    corpo = (f'<div class="wrap"><div class="crumb">'
             f'<a href="/artigos">Arquivo</a> › <a href="/artigos/{_esc(meta["slug"])}">{_esc(meta["rotulo"])}</a> › {_esc(_data_br(d["data"]))}</div>'
             f'<a class="back" href="/artigos/{_esc(meta["slug"])}">← Voltar ao arquivo</a>'
             f'{corpo_doc}{pn}</div>')
    return _pagina(f'{d["titulo_pt"]} · {PRODUTO}', corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


def pagina_minha(sub, admin=False):
    def card(href, ic, nm, ds):
        return (f'<a class="curbtn" href="{href}"><span class="ic">{ic}</span>'
                f'<span><span class="nm">{nm}</span><span class="ds">{ds}</span></span></a>')
    admin_html = ('<p class="plabel" style="margin-top:18px">Painel do curador</p>'
                  '<div class="curgrid">'
                  + card("/curadoria", "🔬", "Curadoria &amp; Estoque", "Varredura, seleção e fila de resumos")
                  + card("/agenda", "📅", "Agenda de envios", "O que sai cada dia da semana")
                  + card("/admin", "👥", "Assinantes", "Quem recebe e status das contas")
                  + card("/admin/whatsapp", "📱", "WhatsApp", "Conexão e envio das mensagens")
                  + '</div>') if admin else ""
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Minha assinatura</h2>
      <p class="hint">Olá, {_esc(sub.get("nome") or "assinante")}. Sua assinatura está ativa.</p>
      {admin_html}
      <p style="margin:22px 0 0"><a class="cta ghost" href="/trilha">Minha trilha</a>
      <a class="cta ghost" href="/meus-dados">Meus dados</a></p>
    </div></div>"""
    return _pagina(f"Minha assinatura · {PRODUTO}", corpo, logado=True, atual="/minha",
                   meta_extra='<meta name="robots" content="noindex">')


def pagina_trilha(sub, itens, msg=""):
    """Trilha do assinante: peça da semana no topo, anteriores abaixo.

    `itens` já vem pronto do serve (mais recente primeiro), com numero, titulo,
    feito, ferramenta_slug e entregue. `entregue=False` é a peça de prévia que
    `serve._pagina_trilha` insere quando o assinante ainda não recebeu aquela peça
    pelo WhatsApp — sem botão de "fiz" (clicar antes do envio real sempre devolveria
    False em silêncio, porque não existe linha em trilha_envios ainda) e com um
    aviso de que ela chega no sábado. Item sem a chave `entregue` é tratado como
    entregue (True), pra não quebrar dado antigo. A página não consulta banco."""
    import config as _cfg
    nome = _esc(sub.get("nome") or "assinante")
    msg_html = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""
    if not itens:
        linhas = ('<p class="hint">Sua primeira peça chega no próximo sábado, '
                  'no mesmo horário em que você recebe os estudos.</p>')
    else:
        partes = []
        for i, it in enumerate(itens):
            ferramenta = ""
            if it.get("ferramenta_slug"):
                ferramenta = (f'<p style="margin:8px 0 0"><a class="cta ghost" '
                              f'href="/ferramentas/{_esc(it["ferramenta_slug"])}">'
                              f'📎 Baixar a ferramenta</a></p>')
            if not it.get("entregue", True):
                acao = ('<p class="hint" style="margin:8px 0 0">Ainda não chegou — '
                        'você recebe esta peça no seu WhatsApp no próximo sábado.</p>')
            elif it.get("feito"):
                acao = '<p class="hint" style="margin:8px 0 0">✅ Você marcou como feita.</p>'
            else:
                acao = (f'<form method="post" action="/trilha" style="margin:8px 0 0">'
                        f'<input type="hidden" name="acao" value="marcar_feito">'
                        f'<input type="hidden" name="numero" value="{int(it["numero"])}">'
                        f'<button class="actbtn" type="submit">✅ Fiz a tarefa desta semana</button>'
                        f'</form>')
            destaque = ' style="border-color:var(--ouro2)"' if i == 0 else ""
            partes.append(
                f'<div class="panel"{destaque}>'
                f'<p class="plabel">Semana {int(it["numero"])} de {_cfg.TRILHA_TOTAL}</p>'
                f'<h3 style="margin:4px 0 0">{_esc(it["titulo"])}</h3>'
                f'{ferramenta}{acao}</div>')
        linhas = "".join(partes)
    corpo = f"""
    <div class="wrap">
      <h2 class="disp">{_esc(_cfg.TRILHA_NOME)}</h2>
      <p class="hint">Olá, {nome}. Uma peça por sábado — cada uma tem uma tarefa pequena, é ela que faz a diferença.</p>
      {msg_html}
      {linhas}
      <p style="margin:22px 0 0"><a class="cta ghost" href="/minha">Voltar</a></p>
    </div>"""
    return _pagina(f"{_cfg.TRILHA_NOME} · {PRODUTO}", corpo, logado=True, atual="/trilha",
                   meta_extra='<meta name="robots" content="noindex">')


def pagina_meus_dados(sub, msg="", etapa_troca=None, novo_num="", slots=None, slot_atual=None):
    msg_html = f'<div class="infobox">{_esc(msg)}</div>' if msg else ""
    if etapa_troca == "codigo":
        troca = f"""
        <p class="hint">Enviei um código por WhatsApp para <strong>{_esc(novo_num)}</strong>. Digite abaixo para confirmar.</p>
        <form method="post" action="/meus-dados">
          <input type="hidden" name="acao" value="confirmar_troca">
          <input type="hidden" name="novo_numero" value="{_esc(novo_num)}">
          <label>Código recebido</label>
          <input type="text" name="codigo" inputmode="numeric" maxlength="6" required>
          <button class="actbtn" type="submit">Confirmar novo número</button>
        </form>"""
    else:
        troca = f"""
        <p class="hint" style="margin-top:4px">Número atual: <strong>{_esc(sub.get("whatsapp",""))}</strong> — é onde você recebe os estudos e faz login.</p>
        <form method="post" action="/meus-dados">
          <input type="hidden" name="acao" value="iniciar_troca">
          <label>Novo número (com DDD)</label>
          <input type="tel" name="novo_numero" placeholder="5543999990000" required>
          <button class="actbtn ghost" type="submit">Trocar número</button>
          <p class="hint" style="margin-top:8px;font-size:13px">Enviaremos um código ao número novo para confirmar.</p>
        </form>"""
    slots = slots if slots is not None else []
    slot_atual = slot_atual or ""
    opts_slot = "".join(
        f'<option value="{_esc(s)}"{" selected" if s == slot_atual else ""}>{_esc(s)}</option>'
        for s in slots) or '<option>—</option>'
    horario_html = (
        '<h3 class="disp" style="font-size:22px;color:var(--ouro2);margin:26px 0 6px">Horário de recebimento</h3>'
        '<p class="hint" style="margin-top:0">Escolha quando receber o estudo do dia no WhatsApp.</p>'
        '<form method="post" action="/meus-dados" style="margin-bottom:8px">'
        '<input type="hidden" name="acao" value="salvar_horario">'
        f'<select name="slot">{opts_slot}</select>'
        '<button class="actbtn" type="submit" style="margin-left:8px">Salvar horário</button>'
        '</form>')
    corpo = f"""
    <div class="wrap"><div class="panel">
      <h2 class="disp">Meus dados</h2>
      {msg_html}
      <form method="post" action="/meus-dados" style="margin-bottom:26px">
        <input type="hidden" name="acao" value="salvar_contato">
        <label>Nome</label>
        <input type="text" name="nome" value="{_esc(sub.get("nome",""))}" required>
        <label>E-mail</label>
        <input type="text" name="email" value="{_esc(sub.get("email",""))}">
        <button class="actbtn" type="submit">Salvar</button>
      </form>
      <h3 class="disp" style="font-size:22px;color:var(--ouro2);margin:0 0 6px">Celular (WhatsApp)</h3>
      {troca}
      {horario_html}
      <hr style="border:none;border-top:1px solid rgba(233,225,198,.12);margin:30px 0 16px">
      <p class="hint" style="font-size:13px;color:var(--suave)">Não quer mais receber?
        <a href="/cancelar" style="color:#d69a8a">Cancelar assinatura</a></p>
    </div></div>"""
    return _pagina(f"Meus dados · {PRODUTO}", corpo, logado=True, atual="/meus-dados",
                   meta_extra='<meta name="robots" content="noindex">')


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
        for p in config.planos_venda())
    return (f'<div class="wrap"><section class="sec"><h2 class="disp">Escolha seu plano</h2>'
            f'<p class="sub">O mensal renova sozinho (cancela quando quiser). O anual '
            f'sai mais barato por mês.</p><div class="pick">{cards}</div>'
            f'<p class="hint">Já é assinante? <a href="/entrar" style="color:var(--ouro2)">Entrar</a></p>'
            f'</section></div>')


def pagina_assinar(plano_slug=None, erro=""):
    plano = config.plano_por_slug(plano_slug) if plano_slug else None
    if not plano:
        return _pagina(f"Assinar · {PRODUTO}", _pick_planos(), logado=False,
                       meta_extra='<meta name="robots" content="noindex">')
    base = float(plano["base"])
    erro_html = f'<div class="erro" style="margin-bottom:16px">{_esc(erro)}</div>' if erro else ""
    # UMA fonte pra todas as figuras de dinheiro desta tela — a MESMA que a prévia do
    # cupom usa em `POST /assinar/cupom` (ver pricing.figuras_assinar). Antes cada figura
    # tinha a sua própria conta aqui, e a prévia atualizava só o resumo: o tile do Pix e
    # o dropdown de parcelas ficavam mostrando valores sem o cupom (bug ao vivo,
    # 2026-07-29). `figs["preco"]` NÃO é usado aqui de propósito: o resumo abre com o
    # preço de tabela (`plano["preco"]`, sem centavos), como sempre — é a prévia que
    # passa a mostrar o valor com desconto.
    figs = pricing.figuras_assinar(plano, "CARTAO", base)
    pix_desc = figs["pix_desc"]
    cartao_desc = figs["cartao_desc"]
    if plano.get("recorrente_pix"):   # mensal (sem parcelamento)
        parcelas_html = '<input type="hidden" name="parcelas" value="1">'
    else:
        # DUAS ofertas de contrato, não 12 (2026-07-30). O que vai pro Asaas é
        # `installment.maxInstallmentCount`, um TETO: quem escolhe o número final de
        # parcelas é o cliente, na tela de pagamento. Um dropdown de 1 a 12 aqui seria
        # escolher duas vezes, valendo só a segunda — e o rótulo daqui viraria promessa
        # vazia. O que ESTA tela decide de verdade é o TIPO de contrato: à vista recorre
        # (RECURRENT), parcelado não (INSTALLMENT) — ver `asaas.montar_checkout`.
        # id no CAMPO (não nos rádios): o JS esconde o campo inteiro quando o método é
        # Pix — à vista não tem parcela. Sem `disabled`, pro `POST /assinar` continuar
        # lendo `parcelas` exatamente como hoje (1 ou 12).
        parc_desc = figs["parcelado_desc"]
        parcelas_html = (
            f'<label class="section-label">No cartão</label>'
            f'<div class="paytiles" id="parcelas-field">'
            f'<label class="paytile"><input type="radio" name="parcelas" value="1" checked>'
            f'<span class="pt-ico">1️⃣</span><span class="pt-nome">À vista</span>'
            f'<span class="pt-desc">cobrança única</span></label>'
            f'<label class="paytile"><input type="radio" name="parcelas" value="12">'
            f'<span class="pt-ico">🗓️</span><span class="pt-nome">Parcelado</span>'
            f'<span class="pt-desc" id="pt-desc-parcelado" data-base="{_esc(parc_desc)}">'
            f'{_esc(parc_desc)}</span></label></div>')
    inclui = "".join(f'<li><b>✓</b><span>{v}</span></li>' for v in (
        "1 estudo por dia útil, no seu WhatsApp",
        "Curadoria criteriosa + revisão médica",
        "PDF Objetivo de cada edição",
        "Arquivo completo no portal do assinante"))
    # mensal saiu do Pix (2026-07-26): sem o tile, o rádio do cartão precisa vir
    # `checked` — senão o formulário abriria sem forma de pagamento selecionada.
    sem_pix = plano.get("aceita_pix") is False
    # `data-base`: o valor que o SERVIDOR renderizou. É a ele que o JS volta quando não
    # há cupom aplicado (caixa vazia ou última tentativa recusada) — assim uma troca de
    # método sem cupom não precisa falar com o servidor (não gasta cota de tentativas) e
    # nenhuma conta de preço acontece no cliente.
    tile_pix = ("" if sem_pix else
                f'<label class="paytile"><input type="radio" name="metodo" value="PIX" checked>'
                f'<span class="pt-ico">⚡</span><span class="pt-nome">Pix</span>'
                f'<span class="pt-desc" id="pt-desc-pix" data-base="{_esc(pix_desc)}">'
                f'{_esc(pix_desc)}</span></label>')
    cartao_checked = " checked" if sem_pix else ""
    # Prévia do cupom sem recarregar a página (Task 2, spec 2026-07-29-cupom-previa).
    # Degradação sem JS: o campo continua um <input name="cupom"> normal dentro do
    # <form> — sem JS, digitar o código e enviar o formulário aplica o desconto no
    # servidor exatamente como antes (o botão Aplicar é só conveniência). String
    # plana (não f-string) de propósito: o JS tem chaves `{}` demais pra escapar.
    cupom_js = """<script>
    (function(){
      var btn = document.getElementById('cupom-aplicar');
      if (!btn) return;
      var input = document.getElementById('cupom-input');
      var msg = document.getElementById('cupom-msg');
      var sumPrice = document.getElementById('sum-price');
      // As OUTRAS DUAS figuras de dinheiro da tela. O bug ao vivo (2026-07-29): a
      // prévia mexia só no resumo, então o tile do Pix ficava com o valor SEM o
      // cupom e o dropdown chegou a oferecer o valor do Pix parcelado (que não
      // existe). Toda figura que a tela mostra é repintada pela resposta do
      // servidor — nenhuma conta de preço acontece aqui.
      var pixDesc = document.getElementById('pt-desc-pix');
      var cartaoDesc = document.getElementById('pt-desc-cartao');
      // QUARTA figura de dinheiro: a oferta "parcelado" mostra "até 12x de R$ X". Sem
      // repintar aqui, ela fica com o valor SEM o cupom — a mesma mentira que o tile do
      // Pix contava em 2026-07-29. Vem PRONTA do servidor (`parcelado_desc`), então é
      // só pintar: nenhum rótulo é montado e nenhuma divisão acontece no navegador.
      var parceladoDesc = document.getElementById('pt-desc-parcelado');
      // guarda o <span> do período (ex.: "por ano") pra reencaixar depois — nunca
      // via innerHTML, só a mesma referência de nó (sem risco de injeção nenhuma).
      var periodoSpan = sumPrice ? sumPrice.querySelector('span') : null;
      var campoParcelas = document.getElementById('parcelas-field');
      var planoInput = document.querySelector('input[name="plano"]');
      var radios = document.querySelectorAll('input[name="metodo"]');
      // Código que a última prévia APROVOU (em maiúsculas, como o servidor normaliza).
      // Vazio = nenhum cupom aplicado -> trocar de método NÃO chama o servidor, só
      // restaura o baseline. É o que impede um código inválido na caixa de queimar
      // uma tentativa por clique no rádio: com 5 trocas de método o visitante se
      // trancaria fora (a cota é compartilhada com o fechamento) e o cupom BOM dele
      // seria recusado na compra.
      var aplicado = '';
      // Nº da conferência em voo. Trocar o método duas vezes rápido deixa DUAS
      // requisições no ar, e elas podem voltar fora de ordem — a resposta do método
      // ANTIGO chegando por último repintaria a tela com o valor do outro método (o
      // mesmíssimo "a tela segura uma resposta velha" que este fix existe pra matar).
      // Só a resposta da conferência mais recente pode pintar.
      var vez = 0;
      function digitado(){ return (input.value || '').trim(); }
      function ehOaplicado(){ return !!aplicado && digitado().toUpperCase() === aplicado; }
      function aviso(texto, ok){
        msg.textContent = texto;
        msg.style.color = ok ? 'var(--gold2)' : '#e08a8a';
      }
      function metodoAtual(){
        var el = document.querySelector('input[name="metodo"]:checked');
        return el ? el.value : '';
      }
      function pintar(el, valor){
        // valor ausente é NO-OP: uma resposta incompleta não pode apagar dinheiro da
        // tela nem escrever "undefined" onde havia um preço.
        if (el && valor) el.textContent = valor;
      }
      function pintarPreco(valor){
        if (!sumPrice || !valor) return;
        sumPrice.textContent = valor;                          // some com o <span> junto
        if (periodoSpan) sumPrice.appendChild(periodoSpan);    // reencaixa o mesmo nó
      }
      function mostrarParcelas(){
        // Pix é À VISTA: parcelamento não existe nesse método (decisão do dono). Só
        // ESCONDE o campo — sem `disabled` e sem mexer em name/value, pro POST
        // /assinar continuar lendo `parcelas` como hoje (no Pix o servidor já ignora
        // esse campo: ver asaas.montar_checkout).
        if (campoParcelas)
          campoParcelas.style.display = (metodoAtual() === 'PIX') ? 'none' : '';
      }
      function restaurar(){
        // Só strings que o SERVIDOR renderizou (data-base + as <option> originais):
        // volta a tela pro preço de tabela sem gastar requisição nem cota.
        if (sumPrice) pintarPreco(sumPrice.getAttribute('data-base'));
        pintar(pixDesc, pixDesc ? pixDesc.getAttribute('data-base') : '');
        pintar(cartaoDesc, cartaoDesc ? cartaoDesc.getAttribute('data-base') : '');
        pintar(parceladoDesc, parceladoDesc ? parceladoDesc.getAttribute('data-base') : '');
      }
      function aplicar(){
        var codigo = digitado();
        if (!codigo) {
          // Campo em branco não vira requisição: no servidor ele nem conta tentativa,
          // e aqui evita gastar uma ida ao servidor pra dizer o óbvio.
          aviso('Digite um cupom.', false);
          return;
        }
        var body = new URLSearchParams({
          plano: planoInput ? planoInput.value : '',
          cupom: codigo,
          metodo: metodoAtual()
        });
        btn.disabled = true;
        msg.textContent = '';
        var minhaVez = ++vez;
        fetch('/assinar/cupom', {
          method: 'POST',
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: body
        }).then(function(r){ return r.json(); }).then(function(d){
          if (minhaVez !== vez) return;   // já existe conferência mais nova em voo
          btn.disabled = false;
          if (!d.ok) {
            // Recusado AGORA (ex.: o cupom foi desativado no admin entre dois
            // cliques): a tela não pode ficar com o desconto de antes, senão promete
            // menos do que o fechamento vai cobrar.
            aplicado = '';
            restaurar();
            aviso(d.msg || '', false);
            return;
          }
          aplicado = codigo.toUpperCase();
          aviso(d.msg || '', true);
          pintarPreco(d.preco);
          pintar(pixDesc, d.pix_desc);
          pintar(cartaoDesc, d.cartao_desc);
          pintar(parceladoDesc, d.parcelado_desc);
        }).catch(function(){
          if (minhaVez !== vez) return;
          btn.disabled = false;
          // Falhou a conferência (rede/resposta ilegível) — a tela volta pro preço de
          // tabela em vez de manter o valor de antes. Numa TROCA DE MÉTODO, manter
          // seria mostrar o valor do método anterior: com Pix aplicado e cartão
          // marcado, R$ 947,15 na tela e R$ 997,00 na cobrança.
          aplicado = '';
          restaurar();
          aviso('Não foi possível conferir o cupom agora. Tente de novo.', false);
        });
      }
      btn.addEventListener('click', aplicar);
      // Enter no campo do cupom = clicar em Aplicar (Minor da revisão): sem isto o
      // Enter submetia o PEDIDO INTEIRO em vez de conferir o cupom.
      input.addEventListener('keydown', function(e){
        if (e.key === 'Enter' || e.keyCode === 13) {
          e.preventDefault();
          aplicar();
        }
      });
      // Mexer na caixa depois de aplicar volta a tela pro preço de tabela: sem isto,
      // quem aplicava o cupom e depois APAGAVA o código fechava a compra olhando um
      // valor MENOR do que o cobrado.
      input.addEventListener('input', function(){
        if (aplicado && !ehOaplicado()) {
          aplicado = '';
          msg.textContent = '';
          restaurar();
        }
      });
      // Trocar a forma de pagamento reprecifica TUDO — nenhuma figura pode sobrar do
      // método anterior (era o bug ao vivo: Pix marcado, tela com o preço do cartão e
      // vice-versa). Com um cupom já aplicado refaz a prévia no servidor (código
      // válido não gasta cota: a rota devolve a tentativa); sem cupom aplicado só
      // restaura o baseline, sem requisição nenhuma.
      Array.prototype.forEach.call(radios, function(r){
        r.addEventListener('change', function(){
          mostrarParcelas();
          if (ehOaplicado()) aplicar();
          else restaurar();
        });
      });
      mostrarParcelas();     // estado inicial (no anual o Pix já vem marcado)
    })();
    </script>"""
    corpo = f"""
    <div class="wrap">
      <div class="sectag" style="margin-top:8px">Finalizar assinatura</div>
      <h2 class="disp" style="font-size:clamp(30px,4vw,42px);color:var(--cream);margin:2px 0 4px">Você está quase lá</h2>
      <div class="checkout">
        <aside class="summary">
          <div class="sum-eyebrow">{_esc(PRODUTO)}</div>
          <div class="sum-plan">Plano {_esc(plano["nome"])}</div>
          <div class="sum-price" id="sum-price" data-base="{_esc(plano["preco"])}">{_esc(plano["preco"])}<span>{_esc(plano["periodo"])}</span></div>
          <ul class="sum-list">{inclui}</ul>
          <div class="sum-trust">🔒 Pagamento 100% seguro · seus dados protegidos.<br>7 dias de garantia com reembolso integral.</div>
        </aside>
        <div class="form-side">
          {erro_html}
          <form method="post" action="/assinar">
            <input type="hidden" name="plano" value="{_esc(plano["slug"])}">
            <div class="field"><label>Nome completo</label><input type="text" name="nome" style="text-transform:uppercase" required></div>
            <div class="field"><label>E-mail</label><input type="text" name="email" inputmode="email" required></div>
            <div class="field"><label>CPF</label><input type="text" name="cpf" inputmode="numeric" placeholder="000.000.000-00" maxlength="14" required></div>
            <div class="field"><label>País</label>{_seletor_pais()}</div>
            <div class="field"><label>WhatsApp (com DDD) — onde você recebe os estudos e faz login</label>
              <input type="text" name="whatsapp" inputmode="tel" placeholder="(43) 99999-0000" required></div>
            <label class="section-label">Forma de pagamento</label>
            <div class="paytiles">
              {tile_pix}
              <label class="paytile"><input type="radio" name="metodo" value="CARTAO"{cartao_checked}>
                <span class="pt-ico">💳</span><span class="pt-nome">Cartão</span><span class="pt-desc" id="pt-desc-cartao" data-base="{_esc(cartao_desc)}">{_esc(cartao_desc)}</span></label>
            </div>
            {parcelas_html}
            <div class="field">
              <label>Cupom (opcional)</label>
              <div style="display:flex;gap:8px">
                <input type="text" id="cupom-input" name="cupom" style="text-transform:uppercase" placeholder="cupom">
                <button type="button" id="cupom-aplicar" style="flex:none;font-family:var(--ui);font-weight:700;font-size:13px;letter-spacing:.02em;color:var(--gold2);background:transparent;border:1px solid rgba(201,162,39,.5);border-radius:100px;padding:0 20px;cursor:pointer">Aplicar</button>
              </div>
              <div style="margin-top:7px;font-family:var(--ui);font-size:11.5px;color:var(--muted);line-height:1.4">Conferir o cupom aqui é só uma prévia — o valor final é sempre calculado no fechamento da compra.</div>
              <span id="cupom-msg" style="display:block;margin-top:4px;font-family:var(--ui);font-size:12.5px"></span>
            </div>
            <label class="check-termos">
              <input type="checkbox" name="aceito" value="1" required>
              <span>Li e aceito os <a href="/termos" target="_blank" rel="noopener">Termos de Assinatura</a>
                e a <a href="/privacidade" target="_blank" rel="noopener">Política de Privacidade</a>.</span>
            </label>
            <button class="btn-pay" type="submit">Continuar para o pagamento →</button>
            <div class="securow">🔒 Ambiente de pagamento seguro</div>
          </form>
          <p class="hint" style="margin-top:16px;text-align:center"><a href="/assinar" style="color:var(--suave)">← trocar de plano</a></p>
        </div>
      </div>
    </div>""" + cupom_js
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
            "Disallow: /minha\nDisallow: /meus-dados\nDisallow: /assinar\nDisallow: /obrigado\nDisallow: /admin\n"
            "Disallow: /revisar\nDisallow: /pdf\n")


_MESES = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
_MESES_LONGO = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
_DIAS_ABREV = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _data_br(iso):
    try:
        a, m, dd = iso.split("-")
        return f"{int(dd)} {_MESES[int(m)]} {a}"
    except Exception:
        return iso


def _sem_html(texto):
    """Texto plano a partir do corpo HTML — WhatsApp não renderiza tags (o corpo da
    confirmação de renovação foi escrito para e-mail; mandar HTML cru pro WhatsApp
    entrega tags cruas na cara do assinante).

    ACHADO 1 (revisão): o fim de QUALQUER elemento de bloco vira quebra de parágrafo
    — não só `</p>`. O corpo real (mensagens.email_renovacao) começa com um `<h1>`
    seguido de `<p>`; tratando só `</p>` o título ficava colado no primeiro parágrafo
    ("Pagamento confirmadoOlá, João!"). `<a>`/`<span>` (inline) não geram quebra —
    já vêm cercados de `<br>` no template quando precisam de uma."""
    import re
    t = re.sub(r"<br\s*/?>", "\n", texto or "", flags=re.IGNORECASE)
    t = re.sub(r"</(p|div|h[1-6]|li|ul|ol|table|tr|blockquote|section|article|header|footer)\s*>",
               "\n\n", t, flags=re.IGNORECASE)
    t = _html.unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"\n{3,}", "\n\n", t)   # nunca 3+ quebras seguidas
    return t.strip()


def _mes_nome(m):
    try:
        return _MESES_LONGO[int(m)]
    except Exception:
        return str(m)


def _data_br_curto(dt):
    """date -> '10 jul · sex'."""
    return f"{dt.day:02d} {_MESES[dt.month]} · {_DIAS_ABREV[dt.weekday()]}"


def pagina_renovar(sub, plano, preco_pix, preco_cartao, vencimento, bonus=False, erro=""):
    """Tela de renovação do assinante logado. Sem campo de cupom de propósito: o desconto de
    afiliado vale só na 1ª venda. O bônus de +1 mês só aparece para quem já perdeu o acesso."""
    erro_html = f'<div class="erro" style="margin-bottom:16px">{_esc(erro)}</div>' if erro else ""
    bonus_html = ('<p class="hint" style="color:var(--ouro2)"><strong>Volte agora e ganhe '
                  '1 mês extra</strong> — 13 meses pelo preço de 12.</p>') if bonus else ""
    corpo = f"""
    <div class="wrap"><div class="panel" style="max-width:520px">
      <h2 class="disp">Renovar assinatura</h2>
      {erro_html}
      <p class="hint">Plano <strong>{_esc(plano.get("nome") or "")}</strong> ·
         {"acesso encerrado em" if bonus else "vence em"}
         <strong>{_esc(_data_br(vencimento))}</strong></p>
      {bonus_html}
      <form method="post" action="/renovar">
        <label class="section-label">Forma de pagamento</label>
        <div class="paytiles">
          <label class="paytile"><input type="radio" name="metodo" value="PIX" checked>
            <span class="pt-ico">⚡</span><span class="pt-nome">Pix</span>
            <span class="pt-desc">{_esc(pricing.fmt_brl(preco_pix))}</span></label>
          <label class="paytile"><input type="radio" name="metodo" value="CARTAO">
            <span class="pt-ico">💳</span><span class="pt-nome">Cartão</span>
            <span class="pt-desc">{_esc(pricing.fmt_brl(preco_cartao))}</span></label>
        </div>
        <button class="btn-pay" type="submit">Continuar para o pagamento →</button>
      </form>
    </div></div>"""
    return _pagina(f"Renovar · {PRODUTO}", corpo, logado=True)


def _semana_label(seg):
    """seg (segunda-feira, date) -> 'Semana 07–11 jul' (ou cruzando o mês)."""
    from datetime import timedelta
    sex = seg + timedelta(days=4)
    if seg.month == sex.month:
        return f"Semana {seg.day:02d}–{sex.day:02d} {_MESES[seg.month]}"
    return f"Semana {seg.day:02d} {_MESES[seg.month]}–{sex.day:02d} {_MESES[sex.month]}"
