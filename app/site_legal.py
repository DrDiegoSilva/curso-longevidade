"""Páginas dos documentos legais. Reaproveita o layout do site_web (_pagina/_esc/PRODUTO)
sem engordar aquele arquivo, que já é o maior do projeto."""
from site_web import _pagina, _esc, PRODUTO


def _pagina_legal(titulo, secoes):
    """Renderiza um documento legal numerado (termos ou privacidade)."""
    import legal
    itens = "".join(
        f'<section style="margin:26px 0"><h3 style="color:var(--cream);font-size:19px;'
        f'margin:0 0 8px">{i}. {_esc(tit)}</h3>{corpo}</section>'
        for i, (tit, corpo) in enumerate(secoes, start=1))
    corpo = (f'<div class="wrap"><div class="panel" style="max-width:760px;line-height:1.65">'
             f'<h2 class="disp">{_esc(titulo)}</h2>'
             f'<p class="hint">Versão {_esc(legal.VERSAO)}</p>'
             f'{itens}'
             f'<p class="hint" style="margin-top:28px">'
             f'<a href="/termos" style="color:var(--ouro2)">Termos de Assinatura</a> · '
             f'<a href="/privacidade" style="color:var(--ouro2)">Política de Privacidade</a>'
             f'</p></div></div>')
    return _pagina(f"{titulo} · {PRODUTO}", corpo, logado=False)


def pagina_termos():
    import legal
    return _pagina_legal("Termos de Assinatura", legal.TERMOS)


def pagina_privacidade():
    import legal
    return _pagina_legal("Política de Privacidade", legal.PRIVACIDADE)
