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


def pagina_aceite_termos(destino="/minha"):
    """Tela de re-aceite. Bloqueia a área de conta — NÃO interrompe o envio diário:
    o assinante continua recebendo o que pagou."""
    import legal
    corpo = f"""
    <div class="wrap"><div class="panel" style="max-width:560px">
      <h2 class="disp">Atualizamos nossos termos</h2>
      <p class="hint">Publicamos os <strong>Termos de Assinatura</strong> e a
        <strong>Política de Privacidade</strong> do serviço. Para continuar usando sua conta,
        confirme que leu e concorda. Seus envios diários seguem normalmente.</p>
      <p class="hint">
        <a href="/termos" target="_blank" style="color:var(--ouro2)">Ler os Termos</a> ·
        <a href="/privacidade" target="_blank" style="color:var(--ouro2)">Ler a Política de Privacidade</a>
      </p>
      <form method="post" action="/aceitar-termos">
        <input type="hidden" name="destino" value="{_esc(destino)}">
        <label class="section-label" style="display:flex;gap:10px;align-items:flex-start;margin:18px 0">
          <input type="checkbox" name="aceito" value="1" required>
          <span>Li e aceito os Termos de Assinatura e a Política de Privacidade
            (versão {_esc(legal.VERSAO)}).</span>
        </label>
        <button class="cta" type="submit">Continuar</button>
      </form>
      <p class="hint" style="margin-top:18px">
        <a href="/cancelar" style="color:var(--suave)">Não concordo — cancelar minha assinatura</a>
      </p>
    </div></div>"""
    return _pagina(f"Atualizamos nossos termos · {PRODUTO}", corpo, logado=True)
