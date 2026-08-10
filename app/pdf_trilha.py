"""HTML da peça da trilha, pronto pra virar PDF por `pdf.gerar_pdf`.

Separado de `pdf.py` de propósito: aquele arquivo carrega o layout do estudo
científico (gráfico, braços, limites, referência) e já passa de 23K. A peça da
trilha é outro objeto — texto, uma tarefa e uma frase de cabeça — e não tem por
que herdar aquele CSS nem fazer aquele arquivo crescer.
"""
import html
import re

import config
import tabela_pipe

_CSS = """
  @page { size: A4; margin: 18mm 16mm; }
  body { font-family: Georgia, 'Times New Roman', serif; color: #1b1b1b; line-height: 1.55; }
  .selo { font-family: system-ui, sans-serif; font-size: 10px; letter-spacing: .18em;
          text-transform: uppercase; color: #8a6a2f; }
  h1 { font-size: 26px; line-height: 1.2; margin: 6px 0 2px; }
  h2 { font-family: system-ui, sans-serif; font-size: 14px; font-weight: 700;
       color: #4a3a12; letter-spacing: .01em; margin: 18px 0 8px; line-height: 1.3; }
  .eixo { font-family: system-ui, sans-serif; font-size: 12px; color: #6b6b6b; margin: 0 0 22px; }
  .abertura { font-style: italic; color: #4a4a4a; border-left: 3px solid #d8c9a6;
              padding-left: 12px; margin: 0 0 22px; }
  .corpo p { margin: 0 0 12px; }
  ul, ol { margin: 0 0 12px; padding-left: 20px; }
  li { margin: 0 0 6px; }
  table { width: 100%; table-layout: fixed; border-collapse: collapse;
          margin: 6px 0 16px; font-family: system-ui, sans-serif; font-size: 11px; }
  th, td { border: 1px solid #e2dccc; padding: 5px 7px; text-align: left;
           overflow-wrap: break-word; font-variant-numeric: tabular-nums; }
  th { font-size: 9px; letter-spacing: .08em; text-transform: uppercase; color: #6b6b6b;
       background: #f7f4ec; font-weight: 600; }
  td.num { text-align: right; }
  .bloco { border: 1px solid #e2dccc; border-radius: 8px; padding: 14px 16px; margin: 22px 0 0; }
  .bloco .rot { font-family: system-ui, sans-serif; font-size: 10px; letter-spacing: .16em;
                text-transform: uppercase; color: #8a6a2f; margin: 0 0 6px; }
  .bloco p { margin: 0; }
  .ferramenta { margin: 22px 0 0; }
  .ferramenta a { font-family: system-ui, sans-serif; font-size: 13px; color: #8a6a2f; }
  .rodape { margin-top: 30px; font-family: system-ui, sans-serif; font-size: 11px; color: #8a8a8a; }
"""

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITEM_NUMERADO_RE = re.compile(r"^\d+\.\s+")


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _negrito(texto_escapado):
    """Troca `**texto**` por <strong>. Roda DEPOIS de `_esc`: o `**` sobrevive ao
    escape (não é caractere especial de HTML), então isto nunca reabre uma tag que
    o escape já tinha fechado -- é o que garante que um <script> no meio do texto
    saia como texto, não como marcação."""
    return _BOLD_RE.sub(r"<strong>\1</strong>", texto_escapado)


def _inline(texto):
    """Escapa e marca `**negrito**`. É o que o `tabela_pipe` chama por célula."""
    return _negrito(_esc(texto))


def _celula_numerica(celula):
    """Célula de valor (R$ ou %) alinha à direita, mesmo dentro de **negrito** --
    checa o texto CRU (antes de escapar/marcar), só decide a classe CSS."""
    c = celula.strip()
    if c.startswith("**") and c.endswith("**") and len(c) > 4:
        c = c[2:-2].strip()
    return c.startswith("R$") or c.endswith("%")


def _lista_html(linhas, tag, extrair):
    itens = "".join(f"<li>{_negrito(_esc(extrair(l)))}</li>" for l in linhas)
    return f"<{tag}>{itens}</{tag}>"


def _bloco_html(bloco):
    """Um bloco (já separado por linha em branco) vira uma peça de HTML. A
    detecção do tipo olha o texto CRU (marcadores como `### `, `- `, `|` não são
    caracteres especiais de HTML, então isso não abre brecha nenhuma); só o
    CONTEÚDO de cada trecho passa por `_esc` antes de virar tag."""
    linhas = bloco.split("\n")
    primeira = linhas[0]

    if primeira.startswith("### "):
        return f"<h2>{_negrito(_esc(primeira[4:].strip()))}</h2>"

    if tabela_pipe.eh_tabela(linhas):
        return tabela_pipe.html(linhas, _inline, num=_celula_numerica)

    if primeira.startswith("- "):
        itens = [l for l in linhas if l.startswith("- ")]
        return _lista_html(itens, "ul", lambda l: l[2:].strip())

    if _ITEM_NUMERADO_RE.match(primeira):
        itens = [l for l in linhas if _ITEM_NUMERADO_RE.match(l)]
        return _lista_html(itens, "ol", lambda l: _ITEM_NUMERADO_RE.sub("", l).strip())

    return f"<p>{_negrito(_esc(bloco))}</p>"


def _paragrafos(texto):
    """Blocos separados por linha em branco viram <p>, com um subconjunto pequeno
    e deliberado de marcação: `### subtítulo`, listas `- ` / `1. `, tabela de cano
    `| a | b |` (2ª linha separadora) e `**negrito**` em qualquer um dos contextos
    acima. Não é markdown genérico -- só o que as peças da trilha usam. Segurança
    não muda: cada trecho de texto passa por `_esc` antes de qualquer marcador
    virar tag (ver `_bloco_html`, `_tabela_html`, `_lista_html`)."""
    blocos = [b.strip() for b in (texto or "").replace("\r\n", "\n").split("\n\n")]
    return "".join(_bloco_html(b) for b in blocos if b)


def montar_html(peca, nome_assinante, abertura="", link_ferramenta=""):
    """HTML completo de uma peça. `link_ferramenta` vazio some com o bloco inteiro —
    peça de mentalidade pura não tem anexo e não pode exibir botão órfão."""
    numero = peca.get("numero", 0)
    abertura_html = (f'<p class="abertura">{_esc(abertura)}</p>' if abertura else "")
    ferramenta_html = ""
    if link_ferramenta:
        ferramenta_html = (f'<p class="ferramenta">📎 <a href="{_esc(link_ferramenta)}">'
                           f'Baixar a ferramenta desta semana</a></p>')
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
  <p class="selo">{_esc(config.TRILHA_NOME)} · Semana {numero} de {config.TRILHA_TOTAL}</p>
  <h1>{_esc(peca.get('titulo'))}</h1>
  <p class="eixo">{_esc(peca.get('eixo'))}</p>
  {abertura_html}
  <div class="corpo">{_paragrafos(peca.get('corpo'))}</div>
  <div class="bloco"><p class="rot">Sua tarefa desta semana</p>
    {_paragrafos(peca.get('micro_resultado')) or '<p></p>'}</div>
  <div class="bloco"><p class="rot">Mentalidade</p>
    {_paragrafos(peca.get('mentalidade')) or '<p></p>'}</div>
  {ferramenta_html}
  <p class="rodape">Para {_esc(nome_assinante)} · {_esc(config.TRILHA_NOME)}</p>
</body></html>"""
