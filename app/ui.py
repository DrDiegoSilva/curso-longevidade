"""Componentes de UI reutilizáveis — mini design system do site.

Markup consistente num lugar só: mudar o componente aqui muda em TODAS as páginas
que o usam. O CSS das classes (.btn, .panel, .field...) vive no <style> central de
`_pagina` (site_web.py); aqui fica só a montagem do HTML.

Uso:
    import ui
    ui.btn("Enviar código")                                  # botão de form (submit), dourado, 100%
    ui.btn("Entrar com senha", href="/entrar", variant="ghost")  # link/ação, contorno
"""


def btn(label, href=None, *, variant="solid", full=True, extra="", type_="submit"):
    """Botão do design system.

    - `variant`: 'solid' (dourado cheio) ou 'ghost' (contorno dourado).
    - `href` definido -> vira `<a>` (navegação/ação de link); senão -> `<button type=...>` (form).
    - `full`: ocupa 100% da largura (padrão em formulários/painéis estreitos).
    - `extra`: CSS inline adicional (ex.: "margin-top:12px").
    - `type_`: tipo do `<button>` quando não é link (default "submit").
    """
    cls = "btn ghost" if variant == "ghost" else "btn solid"
    partes = []
    if full:
        partes.append("display:block;width:100%;text-align:center")
    if extra:
        partes.append(extra)
    style = f' style="{";".join(partes)}"' if partes else ""
    if href is not None:
        return f'<a class="{cls}" href="{href}"{style}>{label}</a>'
    return f'<button class="{cls}" type="{type_}"{style}>{label}</button>'


# Segundos a partir dos quais o texto para de prometer "até 1 min" e admite a demora.
_DEMORA_LONGA = 75


def progresso_upload(fid):
    """Painel de progresso + JS pro upload de estudo do formulário `fid`.

    O upload é SÍNCRONO e passa por várias chamadas de IA: dezenas de segundos com a
    tela muda. Sem isto o único sinal de vida é o spinner da aba do navegador — e o
    Diego aperta de novo, o que gera o estudo DUPLICADO na fila.

    Honestidade é o ponto: nada de barra de progresso falsa. Só dois estados que o
    cliente REALMENTE sabe (o corpo terminou de subir; ainda esperando resposta), um
    cronômetro de verdade, e um texto que admite a demora em vez de seguir prometendo
    "até 1 min".

    Melhoria progressiva: se o JS não rodar (ou o markup mudar e os ids sumirem), o
    `<form>` volta a submeter normal — o upload continua funcionando, só sem retorno.
    """
    painel = (
        f'<div id="{fid}-prog" style="display:none;margin-top:14px;padding:12px 14px;'
        f'border:1px solid rgba(201,162,39,.45);border-radius:10px;'
        f'background:rgba(201,162,39,.08)">'
        f'<div style="font-weight:600">⏳ Lendo o PDF e gerando o resumo</div>'
        f'<div id="{fid}-passo" style="margin-top:6px">Enviando o arquivo…</div>'
        f'<div style="margin-top:6px;opacity:.75;font-size:13px">'
        f'decorrido <span id="{fid}-crono">0:00</span> · '
        f'costuma levar até 1 min. <b>Não feche esta aba</b> — fechar cancela a geração.'
        f'</div></div>')
    js = f"""<script>
(function(){{
  var f = document.getElementById('{fid}');
  if (!f || !window.XMLHttpRequest) return;
  var painel = document.getElementById('{fid}-prog');
  var passo  = document.getElementById('{fid}-passo');
  var crono  = document.getElementById('{fid}-crono');
  var btn    = f.querySelector('button[type=submit]');
  if (!painel || !passo || !crono || !btn) return;   // markup mudou: deixa o POST normal
  var rotulo = btn.textContent, voando = false, t0 = 0, tick = null;
  function mmss(s){{ var m = Math.floor(s / 60), r = s % 60; return m + ':' + (r < 10 ? '0' : '') + r; }}
  function parar(){{ if (tick) {{ clearInterval(tick); tick = null; }} voando = false; }}
  f.addEventListener('submit', function(ev){{
    ev.preventDefault();
    if (voando) return;                              // 2o clique geraria estudo DUPLICADO
    voando = true;
    btn.disabled = true; btn.textContent = 'Enviando…';
    painel.style.display = 'block';
    passo.textContent = 'Enviando o arquivo…';
    t0 = Date.now(); crono.textContent = '0:00';
    tick = setInterval(function(){{
      var s = Math.floor((Date.now() - t0) / 1000);
      crono.textContent = mmss(s);
      if (s === {_DEMORA_LONGA}) passo.textContent =
        'Está demorando mais que o normal — ainda estou esperando a resposta. Não feche a aba.';
    }}, 1000);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', f.getAttribute('action'), true);
    xhr.upload.addEventListener('load', function(){{
      passo.textContent = 'Arquivo recebido. A IA está lendo o estudo e escrevendo o resumo…';
    }});
    xhr.addEventListener('load', function(){{
      parar();
      window.location.href = xhr.responseURL || f.getAttribute('action');
    }});
    xhr.addEventListener('error', function(){{
      parar();
      passo.textContent = 'Não consegui enviar — confira a conexão e tente de novo.';
      btn.disabled = false; btn.textContent = rotulo;
    }});
    xhr.send(new FormData(f));
  }});
  window.addEventListener('beforeunload', function(ev){{
    if (!voando) return;                             // só atrapalha durante a geração
    ev.preventDefault(); ev.returnValue = '';
  }});
}})();
</script>"""
    return painel + js
