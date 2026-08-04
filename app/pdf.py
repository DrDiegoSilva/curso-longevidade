"""PDF bonito (visual C): capa ilustrada + resumo + gráfico do achado + gancho +
marca d'água por assinante. HTML+CSS puro (testável) renderizado por Chromium.
Título em português (conteudo['titulo_pt']).
"""
import os
import re
import subprocess
import tempfile
import html as _html

# Capa ilustrada: rede molecular (nós + conexões) + arco dourado sobre o gradiente.
_MOTIF = (
    '<svg viewBox="0 0 760 185" preserveAspectRatio="xMidYMid slice">'
    '<defs>'
    '<radialGradient id="glow" cx="78%" cy="30%" r="60%">'
    '<stop offset="0" stop-color="#ffffff" stop-opacity=".16"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>'
    '<linearGradient id="arc" x1="0" x2="1"><stop offset="0" stop-color="#c9a227" stop-opacity="0"/>'
    '<stop offset=".5" stop-color="#e7c766" stop-opacity=".7"/><stop offset="1" stop-color="#c9a227" stop-opacity="0"/></linearGradient>'
    '</defs>'
    '<rect width="760" height="185" fill="url(#glow)"/>'
    '<path d="M-10,150 C160,120 250,60 400,66 C560,72 620,120 780,96" fill="none" stroke="url(#arc)" stroke-width="3"/>'
    '<g stroke="#dfe8e2" stroke-opacity=".28" stroke-width="1.1">'
    '<line x1="120" y1="52" x2="210" y2="96"/><line x1="210" y1="96" x2="150" y2="140"/>'
    '<line x1="210" y1="96" x2="330" y2="70"/><line x1="330" y1="70" x2="430" y2="118"/>'
    '<line x1="430" y1="118" x2="540" y2="70"/><line x1="540" y1="70" x2="640" y2="112"/>'
    '<line x1="330" y1="70" x2="300" y2="150"/><line x1="540" y1="70" x2="600" y2="44"/>'
    '</g>'
    '<g fill="#f2ead0">'
    '<circle cx="120" cy="52" r="4"/><circle cx="210" cy="96" r="5.5"/><circle cx="150" cy="140" r="3.5"/>'
    '<circle cx="330" cy="70" r="6"/><circle cx="430" cy="118" r="5"/><circle cx="540" cy="70" r="6.5"/>'
    '<circle cx="640" cy="112" r="4"/><circle cx="300" cy="150" r="3"/><circle cx="600" cy="44" r="4.5"/></g>'
    '<g fill="#c9a227">'
    '<circle cx="210" cy="96" r="2.4"/><circle cx="330" cy="70" r="2.6"/><circle cx="540" cy="70" r="2.8"/></g>'
    '</svg>'
)


_SEP_RE = re.compile(r"^[\-_*—–=·•\s]{3,}$")               # linha só de traços/separadores
_HEADER_RE = re.compile(r"\s*(\S{1,3}\s+)?\*([^*]+)\*\s*")   # linha TODA em negrito (emoji opcional) = título de seção
# Seção "🧯 *Vieses e limitações*" (SYS_ESTUDO) ganha bloco próprio — é o que o
# médico confere antes de mudar conduta. Tolerante a acento/variação de escrita.
_LIMITES_RE = re.compile(r"vies|viés|limita", re.I)
# Teto de texto que pode ser colado ao título dentro de um .keep (break-inside:avoid).
# Grupo maior que a página faria o Chromium empurrar tudo -> página em branco.
_MAX_KEEP_CHARS = 900
_MAX_BRACOS = 8

# Paleta semântica do gráfico (Mudança 1): comparador cinza, intervenção verde,
# melhor resultado dourado.
_CINZA_FILL, _CINZA_VAL = "#b9c2ba", "#6f7d78"
_OURO_FILL, _OURO_STRIPE, _OURO_VAL = "linear-gradient(90deg,#c9a227,#e7c766)", "#c9a227", "#8a6a06"
_VERDES = ("#4f9a7d", "#3d8a6e", "#2f7a5f")
_VERDE_VAL = "#20543f"
# Legado (conteúdo salvo antes da flag `comparador`): barra 0 verde-escuro, resto cinza.
_LEGADO_FILL, _LEGADO_STRIPE, _LEGADO_VAL = "linear-gradient(90deg,#14332a,#2f7a5f)", "#2f7a5f", "#14332a"


def _inline(texto):
    """Escapa e converte *negrito* do WhatsApp em <strong>."""
    return re.sub(r"\*([^*]+)\*", r"<strong>\1</strong>", _html.escape(texto))


def _tokens_resumo(resumo):
    """Quebra o resumo em tokens ('sep'|'h'|'p', texto_plano, html). Nenhuma linha
    é descartada — o que não é separador nem título vira parágrafo, como sempre."""
    toks = []
    for linha in (resumo or "").split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        if _SEP_RE.fullmatch(linha):
            toks.append(("sep", "", ""))
        elif _HEADER_RE.fullmatch(linha):                   # ex.: "💡 *Em resumo*"
            plano = re.sub(r"\*([^*]+)\*", r"\1", linha)
            toks.append(("h", plano, _html.escape(plano)))
        else:
            toks.append(("p", linha, _inline(linha)))
    return toks


def _keep(titulo_html, paragrafos, classe_titulo="h"):
    """Título + 1º parágrafo num invólucro que não pode ser partido (Mudança 4).
    Só agrupa se o parágrafo for curto o bastante para o par caber numa página;
    senão degrada para o comportamento antigo (nada de página em branco)."""
    if not paragrafos:
        return f'<p class="{classe_titulo}">{titulo_html}</p>'
    plano, html_p = paragrafos[0]
    resto = "".join(f"<p>{h}</p>" for _, h in paragrafos[1:])
    par = f"<p>{html_p}</p>"
    cabeca = f'<p class="{classe_titulo}">{titulo_html}</p>'
    if len(plano) > _MAX_KEEP_CHARS:
        return cabeca + par + resto
    return f'<div class="keep">{cabeca}{par}</div>{resto}'


def _limites_html(titulo_html, paragrafos):
    """Bloco destacado (borda âmbar) dos vieses/limitações. O bloco em si PODE
    quebrar entre páginas — só o rótulo + 1º parágrafo ficam colados."""
    plano, html_p = paragrafos[0]
    resto = "".join(f"<p>{h}</p>" for _, h in paragrafos[1:])
    lab = f'<div class="lab">{titulo_html}</div>'
    par = f"<p>{html_p}</p>"
    topo = lab + par if len(plano) > _MAX_KEEP_CHARS else f'<div class="keep">{lab}{par}</div>'
    return f'<div class="limites">{topo}{resto}</div>'


def _resumo_html(resumo):
    """Converte o resumo (estilo WhatsApp: *negrito*, --- separadores, emojis de
    seção) em HTML. Título de seção viaja colado ao 1º parágrafo (invólucro
    .keep, break-inside:avoid) para nunca ficar órfão no pé da página; a seção de
    vieses/limitações vira bloco próprio. Se o texto não tiver a forma esperada,
    cai no render plano de sempre — nenhum trecho do resumo se perde."""
    toks = _tokens_resumo(resumo)
    out, i = [], 0
    while i < len(toks):
        tipo, plano, corpo = toks[i]
        if tipo == "sep":
            out.append('<hr class="rule">')
            i += 1
        elif tipo == "p":
            out.append(f"<p>{corpo}</p>")
            i += 1
        else:                                               # título de seção
            j = i + 1
            segs = []
            while j < len(toks) and toks[j][0] == "p":
                segs.append((toks[j][1], toks[j][2]))
                j += 1
            if segs and _LIMITES_RE.search(plano):
                out.append(_limites_html(corpo, segs))
            else:
                out.append(_keep(corpo, segs))
            i = j
    return "".join(out)


def _cores_barras(barras):
    """Cor de cada barra. Com a flag `comparador` (novo): comparador=cinza,
    intervenção=verde, melhor resultado=dourado. Sem flag nenhuma (conteúdo
    antigo já salvo): mantém exatamente o de hoje — 1ª barra verde, resto cinza."""
    if not any(b.get("comparador") for b in barras):
        return [{"fill": _LEGADO_FILL, "val": _LEGADO_VAL, "stripe": _LEGADO_STRIPE, "papel": ""} if i == 0
                else {"fill": _CINZA_FILL, "val": _CINZA_VAL, "stripe": _CINZA_FILL, "papel": ""}
                for i, _ in enumerate(barras)]
    idx_interv = [i for i, b in enumerate(barras) if not b.get("comparador")]
    melhor = max(idx_interv, key=lambda i: abs(float(barras[i]["valor"])), default=None)
    ordem = sorted((i for i in idx_interv if i != melhor),
                   key=lambda i: abs(float(barras[i]["valor"])))
    verde = {i: _VERDES[min(pos, len(_VERDES) - 1)] for pos, i in enumerate(ordem)}
    cores = []
    for i, b in enumerate(barras):
        if b.get("comparador"):
            cores.append({"fill": _CINZA_FILL, "val": _CINZA_VAL, "stripe": _CINZA_FILL, "papel": "comparador"})
        elif i == melhor:
            cores.append({"fill": _OURO_FILL, "val": _OURO_VAL, "stripe": _OURO_STRIPE, "papel": "melhor"})
        else:
            c = verde[i]
            cores.append({"fill": c, "val": _VERDE_VAL, "stripe": c, "papel": "intervencao"})
    return cores


def _grafico_html(grafico):
    if not grafico or not grafico.get("barras"):
        return ""
    esc = _html.escape
    barras = grafico["barras"]
    cores = _cores_barras(barras)
    semantico = any(b.get("comparador") for b in barras)
    mx = max((abs(float(b["valor"])) for b in barras), default=0) or 1
    linhas = []
    for b, c in zip(barras, cores):
        val = float(b["valor"])
        w = max(6, round(abs(val) / mx * 100))
        sub = "<i>comparador</i>" if c["papel"] == "comparador" else ""
        txt = f"{val:g}{esc(grafico.get('unidade',''))}"
        linhas.append(
            f'<div class="bar-row"><div class="bar-lab">{esc(str(b["rotulo"]))}{sub}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{w}%;background:{c["fill"]}"></div></div>'
            f'<div class="bar-val" style="color:{c["val"]}">{txt}</div></div>')
    extra = ""
    chamada = (grafico.get("chamada") or "").strip()
    if chamada:                                             # frase de efeito relativo — só se a IA mandou
        extra += f'<div class="chamada">{_inline(chamada)}</div>'
    if semantico:
        extra += ('<div class="leg">'
                  f'<span><i style="background:{_CINZA_FILL}"></i>comparador</span>'
                  f'<span><i style="background:{_VERDES[-1]}"></i>interven&ccedil;&atilde;o</span>'
                  f'<span><i style="background:{_OURO_STRIPE}"></i>melhor resultado</span></div>')
    return (f'<div class="chart"><div class="ct">{esc(grafico.get("titulo",""))}</div>'
            f'{"".join(linhas)}{extra}</div>')


def _bracos_html(grafico):
    """Braços/doses em cartões compactos, com a faixa do topo na MESMA cor da
    barra daquele braço no gráfico. Sem dados de braço, não renderiza nada."""
    if not grafico:
        return ""
    bracos = [b for b in (grafico.get("bracos") or [])
              if isinstance(b, dict) and str(b.get("nome") or "").strip()][:_MAX_BRACOS]
    if not bracos:
        return ""
    esc = _html.escape
    barras = grafico.get("barras") or []
    cores = _cores_barras(barras)
    mapa = {str(b.get("rotulo", "")).strip().lower(): c["stripe"] for b, c in zip(barras, cores)}
    cards = []
    for b in bracos:
        nome = str(b["nome"]).strip()
        stripe = mapa.get(nome.lower(), _CINZA_FILL)
        dose = str(b.get("dose") or "").strip()
        n = str(b.get("n") or "").strip()
        dentro = f'<div class="nome">{esc(nome)}</div>'
        if dose:
            dentro += f'<div class="dose">{esc(dose)}</div>'
        if n:
            dentro += f'<div class="n">n = {esc(n)}</div>'
        cards.append(f'<div class="braco"><div class="top" style="background:{stripe}"></div>'
                     f'<div class="in">{dentro}</div></div>')
    return f'<div class="bracos">{"".join(cards)}</div>'


def _kit_html(gancho_bruto, artigo):
    """Kit de post no rodape: recorte do paper + a frase + as pautas de Reels.

    Os dois primeiros blocos sao pensados para PRINT RECORTADO -- o medico ja fazia
    isso na mao, printando o PDF do artigo. Por isso nao levam a marca do Diego: quem
    posta e o assinante. O terceiro e briefing, e por isso e visualmente diferente:
    se parecesse com os outros, alguem recortaria a instrucao junto e postaria.
    """
    import content
    esc = _html.escape
    dados = content.parse_gancho(gancho_bruto)
    titulo = (artigo.get("titulo_original") or artigo.get("titulo") or "").strip()
    blocos = []

    if titulo:
        revista = " · ".join(x for x in [(artigo.get("fonte") or "").strip(),
                                         (artigo.get("data") or "").strip()] if x)
        doi = (artigo.get("doi") or "").strip()
        blocos.append(
            f'<div class="kit-paper"><div class="kit-rot">1 &middot; O estudo</div>'
            f'<div class="paper-box">'
            f'<div class="paper-rev">{esc(revista)}</div>'
            f'<p class="paper-tit">{esc(titulo)}</p>'
            + (f'<div class="paper-doi">DOI {esc(doi)}</div>' if doi else "")
            + '</div></div>')

    if dados["frase"]:
        blocos.append(
            f'<div class="kit-frase"><div class="kit-rot">2 &middot; A frase</div>'
            f'<div class="frase-box"><p>{esc(dados["frase"])}</p></div></div>')

    if dados["reels"]:
        itens = []
        for i, r in enumerate(dados["reels"], 1):
            apoio = f' <span class="reel-apoio">{esc(r["apoio"])}</span>' if r["apoio"] else ""
            itens.append(f'<li class="reel"><span class="reel-n">{i}</span>'
                         f'<span><b>{esc(r["angulo"])}</b>{apoio}</span></li>')
        blocos.append(
            f'<div class="kit-brief"><div class="kit-rot">Reels que saem deste estudo</div>'
            f'<ul class="reels">{"".join(itens)}</ul></div>')

    if not blocos:
        return ""
    return f'<div class="kit">{"".join(blocos)}</div>'


def _rodape_direitos():
    """Nota de direitos fixa no rodapé — o PDF é único (mesmo arquivo p/ todos os
    assinantes), com a marca do curso no lugar do nome individual."""
    from datetime import datetime
    return (f"© {datetime.now().year} Atualização Científica · Dr. Diego Silva · "
            f"CRM-PR 54310 — conteúdo exclusivo para assinantes")


def montar_html(artigo, conteudo, tema_meta):
    esc = _html.escape
    cor = tema_meta.get("cor", "#14332a")
    rotulo = tema_meta.get("rotulo", artigo.get("tema", ""))
    emoji = tema_meta.get("emoji", "")
    titulo = conteudo.get("titulo_pt") or artigo.get("titulo", "")
    resumo_html = _resumo_html(conteudo.get("resumo", ""))
    bracos_html = _bracos_html(conteudo.get("grafico"))
    grafico_html = _grafico_html(conteudo.get("grafico"))
    kit_html = _kit_html(conteudo.get("gancho", ""), artigo)
    url = (artigo.get("url") or "").strip()
    # Link de verdade: o Chromium (--print-to-pdf, `gerar_pdf`) preserva hyperlink como
    # anotacao no PDF. Como texto puro, o medico tinha que copiar o DOI na mao.
    ref_html = (f'Refer&ecirc;ncia: <a href="{esc(url)}">{esc(url)}</a>' if url
                else 'Refer&ecirc;ncia: &mdash;')
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 15mm 0 13mm; }}
  /* A capa sangra de borda a borda: só a 1a página abre mão da margem de topo.
     Sem isto, o texto que vira para a página 2 nasce colado no corte do papel. */
  @page :first {{ margin-top: 0; }}
  *{{box-sizing:border-box}}
  body {{ font-family: Georgia, "Times New Roman", serif; color:#20302b; margin:0; font-size:20px; line-height:1.7; }}
  h1, h2 {{ break-after:avoid; }}
  .cover {{ position:relative; height:185px; background:linear-gradient(120deg,#0e211a,{cor} 60%,#20543f); }}
  .cover svg {{ position:absolute; inset:0; width:100%; height:100%; }}
  .brand {{ position:absolute; left:34px; top:28px; z-index:2; }}
  .brand .mark {{ font-family:system-ui,sans-serif; font-size:12px; letter-spacing:.22em; text-transform:uppercase; color:#ece4c6; font-weight:600; }}
  .brand .sig {{ color:#fbf7ea; font-size:26px; margin-top:5px; }}
  .brand .crm {{ font-family:system-ui,sans-serif; font-size:11px; letter-spacing:.1em; color:#cbd8cf; margin-top:3px; }}
  .tag {{ position:absolute; right:34px; top:28px; z-index:2; background:#c9a227; color:#1a1300; font-family:system-ui,sans-serif;
          font-size:12px; letter-spacing:.12em; text-transform:uppercase; font-weight:700; padding:7px 15px; border-radius:100px; }}
  .body {{ padding:34px 48px 26px; }}
  .title {{ font-size:28px; line-height:1.22; color:{cor}; margin:0 0 14px; }}
  .meta {{ font-family:ui-monospace,Menlo,monospace; font-size:15px; color:#6f7d78; border-bottom:2px solid #c9a227; padding-bottom:13px; margin-bottom:22px; }}
  .corpo p {{ margin:.7em 0; font-size:16.5px; color:#2b3a35; orphans:3; widows:3; }}
  /* Invólucro do par título+1º parágrafo: o par não pode ser partido, então o
     título nunca fica sozinho no pé da página. É deliberadamente PEQUENO — grupo
     maior que a página faria o Chromium empurrar tudo e abrir página em branco. */
  .corpo .keep {{ break-inside:avoid; }}
  .corpo strong {{ color:{cor}; }}
  .corpo .h {{ font-size:17.5px; font-weight:700; color:{cor}; margin:22px 0 4px; line-height:1.3; break-after:avoid; break-inside:avoid; }}
  .corpo hr.rule {{ border:none; border-top:1px solid #e2ddcb; margin:16px 0 14px; break-after:avoid; }}
  .chart {{ margin:26px 0; background:#f4f1e7; border:1px solid #e7e2d6; border-radius:10px; padding:20px 22px; break-inside:avoid; }}
  .chart .ct {{ font-family:system-ui,sans-serif; font-size:14px; letter-spacing:.08em; text-transform:uppercase; color:#6f7d78; margin-bottom:14px; font-weight:600; }}
  .bar-row {{ display:flex; align-items:center; gap:14px; margin:12px 0; }}
  .bar-lab {{ width:132px; font-family:system-ui,sans-serif; font-size:14.5px; color:#2b3a35; flex:none; }}
  .bar-track {{ flex:1; background:#e7e2d3; border-radius:100px; height:26px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:100px; }}
  .bar-val {{ font-family:ui-monospace,monospace; font-size:14.5px; font-weight:700; width:78px; text-align:right; flex:none; }}
  .bar-lab i {{ display:block; font-style:normal; font-size:13px; color:#8a948e; }}
  .chart .chamada {{ margin-top:15px; padding-top:13px; border-top:1px solid #e7e2d6;
           font-family:system-ui,sans-serif; font-size:16px; line-height:1.5; color:#3a2f10; }}
  .chart .chamada strong {{ color:#8a6a06; }}
  .chart .leg {{ display:flex; flex-wrap:wrap; gap:16px; margin-top:11px; font-family:system-ui,sans-serif; font-size:13px; color:#6f7d78; }}
  .chart .leg i {{ display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:6px; vertical-align:-2px; }}
  /* Braços/doses em cartões — cada cartão é indivisível; a grade PODE quebrar
     entre linhas de cartões (degrada em vez de empurrar página em branco). */
  .bracos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(165px,1fr)); gap:12px; margin:18px 0 4px; }}
  .braco {{ border:1px solid #e7e2d6; border-radius:10px; background:#f4f1e7; overflow:hidden; break-inside:avoid; }}
  .braco .top {{ height:6px; }}
  .braco .in {{ padding:12px 14px 14px; font-family:system-ui,sans-serif; }}
  .braco .nome {{ font-size:14px; font-weight:700; color:{cor}; line-height:1.3; }}
  .braco .dose {{ font-size:14px; color:#6f7d78; margin-top:4px; line-height:1.4; }}
  .braco .n {{ font-size:14px; color:#20543f; margin-top:8px; font-variant-numeric:tabular-nums; }}
  /* Vieses e limitações em bloco próprio (sem break-inside:avoid de propósito:
     se for longo, quebra entre páginas em vez de gerar página em branco). */
  .corpo .limites {{ margin:26px 0 8px; border:1px solid #e0d9c4; border-left:4px solid #b9a24a;
           border-radius:10px; background:#fdfaf0; padding:18px 20px; }}
  .corpo .limites .lab {{ font-family:system-ui,sans-serif; font-size:14.5px; letter-spacing:.08em; text-transform:uppercase;
           color:#8a6a06; font-weight:700; margin-bottom:9px; }}
  .corpo .limites p {{ margin:.4em 0; font-size:15.5px; line-height:1.6; color:#4a4634; orphans:3; widows:3; }}
  .kit {{ margin:28px 0 8px; display:flex; flex-direction:column; gap:22px; }}
  .kit-rot {{ font-family:system-ui,sans-serif; font-size:13px; letter-spacing:.08em;
           text-transform:uppercase; color:#8a6a06; font-weight:700; margin-bottom:9px; }}
  .paper-box {{ border:1px solid #d8ddd7; border-top:3px solid #14332a; background:#fcfdfc;
           padding:18px 20px; break-inside:avoid; }}
  .paper-rev {{ font-family:system-ui,sans-serif; font-size:11.5px; letter-spacing:.13em;
           text-transform:uppercase; color:#14332a; font-weight:700; margin-bottom:9px; }}
  .paper-tit {{ margin:0 0 11px; font-size:20px; line-height:1.28; color:#16211c; }}
  .paper-doi {{ font-family:ui-monospace,Menlo,monospace; font-size:13px; color:#6f7d78; }}
  .frase-box {{ border:2px solid #c9a227; border-radius:12px; padding:22px 24px;
           background:linear-gradient(180deg,#fff9e9,#fbf3d9); break-inside:avoid; }}
  .frase-box p {{ margin:0; font-size:21px; line-height:1.4; color:#3a2f10; }}
  .kit-brief {{ break-inside:avoid; }}
  .kit-brief .kit-rot {{ color:#6f7d78; }}
  .reels {{ list-style:none; margin:0; padding:15px 18px; border-left:3px solid #c8cfca;
           background:#f6f8f6; border-radius:0 8px 8px 0; }}
  .reel {{ display:flex; gap:10px; align-items:flex-start; margin-bottom:9px;
           font-family:system-ui,sans-serif; font-size:14px; line-height:1.55; color:#4d5a54; }}
  .reel:last-child {{ margin-bottom:0; }}
  .reel b {{ color:#33403a; }}
  .reel-n {{ flex:0 0 20px; height:20px; display:inline-flex; align-items:center;
           justify-content:center; border:1px solid #c3ccc6; border-radius:50%;
           font-size:11.5px; font-weight:700; color:#6f7d78; }}
  .foot {{ margin-top:22px; border-top:1px solid #e7e2d6; padding-top:14px; display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;
           break-inside:avoid; font-family:system-ui,sans-serif; font-size:13px; color:#6f7d78; }}
  .foot a {{ color:#1b6b4f; }}
  .foot .wm {{ font-style:italic; color:#9aa8a0; }}
</style></head><body>
  <div class="cover">{_MOTIF}
    <div class="brand"><div class="mark">Atualiza&ccedil;&atilde;o cient&iacute;fica</div><div class="sig">Dr. Diego Silva</div><div class="crm">CRM-PR 54310</div></div>
    <div class="tag">{esc(emoji)} {esc(rotulo)}</div>
  </div>
  <div class="body">
    <h1 class="title">{esc(titulo)}</h1>
    <div class="meta">{esc(artigo.get('fonte',''))} &middot; {esc(artigo.get('data',''))} &middot; DOI {esc(artigo.get('doi','') or '—')}</div>
    <div class="corpo">{resumo_html}</div>
    {bracos_html}
    {grafico_html}
    {kit_html}
    <div class="foot">
      <span>{ref_html}</span>
      <span class="wm">{_rodape_direitos()}</span>
    </div>
  </div>
</body></html>"""


def _chromium_bin():
    for b in ("chromium", "chromium-browser", "google-chrome"):
        if subprocess.run(["which", b], capture_output=True).returncode == 0:
            return b
    raise RuntimeError("Chromium não encontrado na imagem")


def gerar_pdf(html, out_path, tentativas=3):
    """Renderiza HTML->PDF via Chromium. Em container o Chromium crasha de forma
    TRANSITÓRIA (pressão de RAM do host) e sai sem gerar o arquivo; então tenta
    algumas vezes antes de desistir — automatiza o 'regerar na mão' que funciona."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        src = f.name
    cmd = [_chromium_bin(), "--headless", "--no-sandbox", "--disable-gpu",
           "--disable-dev-shm-usage", "--disable-software-rasterizer",
           "--disable-extensions", "--disable-crash-reporter",
           f"--print-to-pdf={out_path}", "--no-pdf-header-footer", f"file://{src}"]
    ultimo = None
    try:
        for i in range(1, int(tentativas) + 1):
            try:
                if os.path.exists(out_path):
                    os.unlink(out_path)                  # começa limpo cada tentativa
            except OSError:
                pass
            try:
                subprocess.run(cmd, check=True, timeout=120, capture_output=True)
            except Exception as e:                       # crash/timeout -> tenta de novo
                ultimo = e
            # Chromium às vezes retorna 0 sem gerar o arquivo; confere de verdade:
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                return out_path
            print(f"[pdf] tentativa {i}/{tentativas} falhou (Chromium sem saída), retry…", flush=True)
    finally:
        try:
            os.unlink(src)
        except OSError:
            pass
    raise RuntimeError(f"Chromium não gerou o PDF após {tentativas} tentativas: {ultimo}")
