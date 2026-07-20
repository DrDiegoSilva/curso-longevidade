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
.c-a{grid-column:span 3}.c-b{grid-column:span 3}.c-c{grid-column:span 2}.c-d{grid-column:span 2}.c-e{grid-column:span 2}
.card.big{background:linear-gradient(150deg,rgba(30,80,69,.5),rgba(20,51,42,.35));border-color:rgba(201,162,39,.25)}
/* planos (redesign) */
.plans{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}
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
.doc{background:var(--creme);color:#20302b;border-radius:16px;padding:40px 44px;margin:8px auto 26px;max-width:860px;box-shadow:0 20px 60px -20px rgba(0,0,0,.6)}
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
@media(max-width:820px){
  .hero{grid-template-columns:1fr;gap:30px}
  .themes{grid-template-columns:repeat(2,1fr)}
  .bento{grid-template-columns:1fr}.c-a,.c-b,.c-c,.c-d,.c-e{grid-column:auto}
  .plans{grid-template-columns:repeat(2,1fr)}
  .entry{grid-template-columns:1fr;gap:4px}
  .doc{padding:28px 22px}
}
"""


def _esc(s):
    return _html.escape(str(s or ""))


def _cta():
    return _esc(config.cta_url())


def _topbar(logado=False):
    direita = ('<a class="plain" href="/artigos">Arquivo</a>'
               '<a class="plain" href="/minha">Minha conta</a>'
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
            f'<div class="cfm">Conteúdo de caráter científico-educacional, destinado a médicos. '
            f'Não substitui o julgamento clínico individual nem constitui recomendação de conduta.</div>'
            f'</div></div>')


def _pagina(titulo, corpo, logado=False, meta_extra=""):
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
            f'<title>{_esc(titulo)}</title>{meta_extra}{_FONTS}<style>{_CSS}</style></head><body>'
            f'{_topbar(logado)}{corpo}{_foot()}</body></html>')


# ── Landing (pública) ──
def landing():
    temas = [("⚖️", "Obesidade"), ("⚕️", "Menopausa & Reposição"),
             ("🦵", "Lipedema"), ("🏃", "Performance"), ("🧬", "Longevidade")]
    themes = "".join(
        f'<div class="theme"><div class="e">{_esc(e)}</div>'
        f'<div class="t">{_esc(t)}</div><div class="n">estudo do dia</div></div>'
        for e, t in temas)
    valores = [
        ("01 · curadoria", "Curadoria + revisão médica", "Uma IA tria a literatura da semana; o Dr. Diego revisa antes de sair. Você recebe o que importa, sem ruído.", "card big c-a"),
        ("02 · cadência", "1 estudo por dia útil", "De segunda a sexta, um artigo relevante — resumo clínico direto ao ponto, no seu WhatsApp.", "card c-b"),
        ("03 · redes", "Pronto para as redes", "Cada edição traz um gancho para levar o tema aos seus pacientes.", "card c-c"),
        ("04 · pdf", "PDF elegante", "Um documento assinado, com gráfico e fonte — pronto para guardar ou compartilhar.", "card c-d"),
        ("05 · arquivo", "Arquivo consultável", "Tudo por tema e data, sempre à mão neste portal.", "card c-e"),
    ]
    bento = "".join(
        f'<div class="{cls}"><span class="k">{_esc(k)}</span><h3>{_esc(n)}</h3><p>{_esc(d)}</p></div>'
        for k, n, d, cls in valores)
    planos = "".join(
        f'<a class="plan{" best" if p["slug"] == "anual" else ""}" href="/assinar?plano={_esc(p["slug"])}">'
        + ('<div class="badge">Melhor preço</div>' if p["slug"] == "anual" else "")
        + f'<div class="nm">{_esc(p["nome"])}</div>'
        f'<div class="pr">{_esc(p["preco"]) if p.get("preco") else "sob consulta"}</div>'
        f'<div class="pe">Pix · {_esc(p["periodo"])}</div>'
        + (f'<div class="pn">{_esc(p["nota"])}</div>' if p.get("nota") else "")
        + '<span class="pick2">Assinar</span></a>' for p in config.PLANOS if not p.get("oculto"))
    corpo = f"""
    <div class="wrap">
      <section class="hero">
        <div>
          <div class="eyebrow">{_esc(PRODUTO)}</div>
          <h1 class="disp">A ciência que move a sua <em>prática clínica</em> — todo dia útil.</h1>
          <p class="lead">Um estudo relevante por dia, com resumo clínico objetivo, gancho para as suas redes e um PDF elegante. Curado por IA, revisado por médico.</p>
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
        </aside>
      </section>

      <section class="sec" style="border-top:none;padding-top:16px">
        <div class="sectag">Cinco frentes, uma rotina</div>
        <div class="themes">{themes}</div>
      </section>

      <section class="sec">
        <h2 class="disp">O que chega até você</h2>
        <p class="sub">A fila varia os temas para você não receber dois dias seguidos do mesmo assunto — e tudo fica guardado no seu arquivo.</p>
        <div class="bento">{bento}</div>
      </section>

      <section class="sec" id="planos">
        <h2 class="disp">Planos</h2>
        <p class="sub">Escolha a recorrência que faz sentido. Renova automaticamente até você cancelar.</p>
        <div class="plans">{planos}</div>
        <div style="margin-top:28px"><a class="btn solid" href="{_cta()}">Quero assinar</a>
        <a class="btn ghost" href="/entrar" style="margin-left:10px">Já sou assinante</a></div>
      </section>

      <section class="sec">
        <div class="auth">
          <div class="big">"Leio a literatura para que você não precise abrir <em>vinte abas</em> — e chego com o que muda a conduta."</div>
          <div class="sig">curadoria e revisão<b>{_esc(MARCA)}</b>{_esc(CRM)}</div>
        </div>
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
            + lk("/admin/whatsapp", "📱 WhatsApp", "whatsapp")
            + '<a class="actbtn ghost" href="/minha" style="text-decoration:none;padding:8px 15px;font-size:13px">← Minha conta</a>'
            + '</div>')


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
      {_admin_nav(token, "assinantes")}
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
    prontos = sum(1 for r in reserva if r.get("status") == "pronto")
    enviados = sum(1 for r in reserva if r.get("status") == "enviado")
    stats = (
        f'<strong>Candidatos da varredura</strong> <span style="color:var(--suave)">(estudos encontrados, ainda sem resumo)</span>: '
        f'{contagem.get("novo", 0)} novos · {contagem.get("selecionado", 0)} selecionados · {contagem.get("resumido", 0)} já resumidos<br>'
        f'<strong>Fila de envio (reserva)</strong> <span style="color:var(--suave)">(resumos prontos, inclui o que você subiu)</span>: '
        f'{prontos} prontos p/ enviar · {enviados} já enviados = {len(reserva)} no total')
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
    def _reserva_item(r):
        rid = _esc(r.get("id"))
        prio = ' · <span style="color:var(--ouro2)">★ prioridade</span>' if r.get("prioridade") else ""
        return (
            f'<div class="item">'
            f'<div class="d">{_esc(r.get("tema"))} · {_esc(r.get("status"))}{prio}</div>'
            f'<div class="t">{_esc(r.get("titulo_pt"))}</div>'
            f'<details style="margin-top:8px">'
            f'<summary style="cursor:pointer;color:var(--ouro2);font-family:system-ui,sans-serif;font-size:13px">✏️ editar / remover</summary>'
            f'<form method="post" action="/curadoria" style="margin-top:12px">'
            f'<input type="hidden" name="token" value="{tok}">'
            f'<input type="hidden" name="acao" value="editar_reserva">'
            f'<input type="hidden" name="id" value="{rid}">'
            f'<label>Título</label>'
            f'<input type="text" name="titulo_pt" value="{_esc(r.get("titulo_pt"))}" style="width:100%">'
            f'<label style="margin-top:10px">Resumo (pode ajustar o texto que a IA gerou)</label>'
            f'<textarea name="resumo" rows="10">{_esc(r.get("resumo"))}</textarea>'
            f'<button class="actbtn" type="submit">Salvar alterações</button>'
            f'</form>'
            f'<form method="post" action="/curadoria" onsubmit="return confirm(\'Remover este item da reserva?\')" style="margin-top:10px">'
            f'<input type="hidden" name="token" value="{tok}">'
            f'<input type="hidden" name="acao" value="remover_reserva">'
            f'<input type="hidden" name="id" value="{rid}">'
            f'<button class="actbtn ghost" type="submit">🗑️ Remover da reserva</button>'
            f'</form>'
            f'</details></div>')
    res_html = "".join(_reserva_item(r) for r in reserva) or '<p class="hint">Reserva vazia. Selecione candidatos e clique em <strong>Gerar resumos</strong>.</p>'
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
          <input type="text" name="titulo" placeholder="Título do estudo (opcional — se vazio, eu crio a partir do texto)" style="width:100%;margin-bottom:10px">
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <input type="text" name="fonte" placeholder="Revista (opcional)" style="flex:1">
            <input type="text" name="doi" placeholder="DOI (opcional)" style="flex:1">
          </div>
          <button class="actbtn" type="submit" style="margin-top:14px">Gerar resumo e adicionar à fila</button>
        </form>
      </div>"""
    corpo = f"""
    <div class="wrap">
      {_admin_nav(token, "curadoria")}
      <h2 class="disp" style="font-size:40px;color:var(--creme);margin:6px 0 4px">Curadoria · Reserva 2026</h2>
      <p class="hint">{stats}</p>
      {msg_html}{acoes}{add_form}
      <p class="hint">Leia o <strong>título</strong> + a <strong>pergunta</strong> e marque os que valem resumir. Nada vai pro arquivo dos assinantes — é sua reserva privada.</p>
      {form_lista}
      <section class="sec"><h2 class="disp" style="font-size:30px">Reserva pronta</h2>{res_html}</section>
    </div>"""
    return _pagina("Curadoria · Reserva", corpo, logado=True, meta_extra='<meta name="robots" content="noindex">')


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
                 f'<div class="meta">{_esc(d.get("fonte",""))} · {_esc(_data_br(d["data"]))} · DOI {_esc(d.get("doi","") or "—")}</div>'
                 f'<div class="corpo">{pdf._resumo_html(d.get("resumo",""))}</div>'
                 f'{pdf._grafico_html(grafico)}{pdf._gancho_html(d.get("gancho",""))}')
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
    admin_html = ('<div class="infobox" style="margin:16px 0"><strong>Painel do curador</strong><br>'
                  '<a href="/curadoria" style="color:var(--ouro2)">🔬 Curadoria / Reserva</a> &nbsp;·&nbsp; '
                  '<a href="/admin" style="color:var(--ouro2)">👥 Assinantes</a> &nbsp;·&nbsp; '
                  '<a href="/admin/whatsapp" style="color:var(--ouro2)">📱 WhatsApp</a></div>') if admin else ""
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
        for p in config.PLANOS if not p.get("oculto"))
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
    erro_html = f'<div class="erro" style="margin-bottom:16px">{_esc(erro)}</div>' if erro else ""
    pix_desc = f"{pricing.fmt_brl(base)} à vista"
    if plano.get("recorrente_pix"):   # mensal (sem parcelamento)
        cartao_desc = f"{pricing.fmt_brl(pricing.valor_cartao(base,1))}/mês · renova"
        parcelas_html = '<input type="hidden" name="parcelas" value="1">'
    else:
        cartao_desc = "parcelável · renova no fim"
        opts = "".join(
            f'<option value="{o["parcelas"]}">{o["parcelas"]}x de {pricing.fmt_brl(o["por_parcela"])} '
            f'— total {pricing.fmt_brl(o["total"])}</option>' for o in pricing.opcoes_parcelas(base))
        parcelas_html = (f'<div class="field"><label>Parcelas (só no cartão)</label>'
                         f'<select name="parcelas">{opts}</select></div>')
    inclui = "".join(f'<li><b>✓</b><span>{v}</span></li>' for v in (
        "1 estudo por dia útil, no seu WhatsApp",
        "Curadoria por IA + revisão médica",
        "PDF elegante de cada edição",
        "Arquivo completo no portal do assinante"))
    corpo = f"""
    <div class="wrap">
      <div class="sectag" style="margin-top:8px">Finalizar assinatura</div>
      <h2 class="disp" style="font-size:clamp(30px,4vw,42px);color:var(--cream);margin:2px 0 4px">Você está quase lá</h2>
      <div class="checkout">
        <aside class="summary">
          <div class="sum-eyebrow">{_esc(PRODUTO)}</div>
          <div class="sum-plan">Plano {_esc(plano["nome"])}</div>
          <div class="sum-price">{_esc(plano["preco"])}<span>{_esc(plano["periodo"])}</span></div>
          <ul class="sum-list">{inclui}</ul>
          <div class="sum-trust">🔒 Pagamento 100% seguro · seus dados protegidos.<br>Cancele quando quiser, sem multa.</div>
        </aside>
        <div class="form-side">
          {erro_html}
          <form method="post" action="/assinar">
            <input type="hidden" name="plano" value="{_esc(plano["slug"])}">
            <div class="field"><label>Nome completo</label><input type="text" name="nome" required></div>
            <div class="field"><label>E-mail</label><input type="text" name="email" inputmode="email" required></div>
            <div class="field"><label>CPF</label><input type="text" name="cpf" inputmode="numeric" required></div>
            <div class="field"><label>WhatsApp (com DDD) — onde você recebe os estudos e faz login</label>
              <input type="text" name="whatsapp" inputmode="tel" placeholder="(43) 99999-0000" required></div>
            <label class="section-label">Forma de pagamento</label>
            <div class="paytiles">
              <label class="paytile"><input type="radio" name="metodo" value="PIX" checked>
                <span class="pt-ico">⚡</span><span class="pt-nome">Pix</span><span class="pt-desc">{_esc(pix_desc)}</span></label>
              <label class="paytile"><input type="radio" name="metodo" value="CARTAO">
                <span class="pt-ico">💳</span><span class="pt-nome">Cartão</span><span class="pt-desc">{_esc(cartao_desc)}</span></label>
            </div>
            {parcelas_html}
            <div class="field"><label>Cupom (opcional)</label><input type="text" name="cupom" placeholder="tem um cupom de cortesia?"></div>
            <button class="btn-pay" type="submit">Continuar para o pagamento →</button>
            <div class="securow">🔒 Ambiente de pagamento seguro</div>
          </form>
          <p class="hint" style="margin-top:16px;text-align:center"><a href="/assinar" style="color:var(--suave)">← trocar de plano</a></p>
        </div>
      </div>
    </div>"""
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
_MESES_LONGO = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
_DIAS_ABREV = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _data_br(iso):
    try:
        a, m, dd = iso.split("-")
        return f"{int(dd)} {_MESES[int(m)]} {a}"
    except Exception:
        return iso


def _mes_nome(m):
    try:
        return _MESES_LONGO[int(m)]
    except Exception:
        return str(m)


def _data_br_curto(dt):
    """date -> '10 jul · sex'."""
    return f"{dt.day:02d} {_MESES[dt.month]} · {_DIAS_ABREV[dt.weekday()]}"


def _semana_label(seg):
    """seg (segunda-feira, date) -> 'Semana 07–11 jul' (ou cruzando o mês)."""
    from datetime import timedelta
    sex = seg + timedelta(days=4)
    if seg.month == sex.month:
        return f"Semana {seg.day:02d}–{sex.day:02d} {_MESES[seg.month]}"
    return f"Semana {seg.day:02d} {_MESES[seg.month]}–{sex.day:02d} {_MESES[sex.month]}"
