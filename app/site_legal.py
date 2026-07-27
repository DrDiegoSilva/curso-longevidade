"""Páginas dos documentos legais. Reaproveita o layout do site_web (_pagina/_esc/PRODUTO)
sem engordar aquele arquivo, que já é o maior do projeto."""
from site_web import _pagina, _esc, PRODUTO


def _secao_legal(i, secao):
    """Renderiza uma cláusula/seção numerada. `secao` é (título, corpo) ou (título,
    corpo, restritiva) — o 3º elemento, quando True, dá destaque visual próprio
    (caixa com borda/fundo dourado, no tema do site) à cláusula, como exige o art. 54
    §4 do CDC pra cláusula que restringe direito do consumidor (ex.: a que nega
    reembolso após o prazo de arrependimento).

    A marcação é lida do próprio dado (`legal.TERMOS`), não por posição na lista nem
    por casar o texto do título — assim continua valendo mesmo se a cláusula for
    reordenada ou o título for reescrito."""
    titulo, corpo = secao[0], secao[1]
    restritiva = secao[2] if len(secao) > 2 else False
    cabecalho = f'<h3 style="color:var(--cream);font-size:19px;margin:0 0 8px">{i}. {_esc(titulo)}</h3>'
    if restritiva:
        return (f'<section class="infobox" style="margin:26px 0;padding:16px 18px">'
                 f'<div style="font-family:system-ui,sans-serif;font-size:11px;letter-spacing:.08em;'
                 f'text-transform:uppercase;color:var(--ouro2);margin-bottom:8px">'
                 f'⚠ Cláusula restritiva de direito</div>{cabecalho}{corpo}</section>')
    return f'<section style="margin:26px 0">{cabecalho}{corpo}</section>'


def _pagina_legal(titulo, secoes):
    """Renderiza um documento legal numerado (termos ou privacidade)."""
    import legal
    itens = "".join(_secao_legal(i, secao) for i, secao in enumerate(secoes, start=1))
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
