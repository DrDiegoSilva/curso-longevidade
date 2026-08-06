"""HTML da peça da trilha, pronto pra virar PDF por `pdf.gerar_pdf`.

Separado de `pdf.py` de propósito: aquele arquivo carrega o layout do estudo
científico (gráfico, braços, limites, referência) e já passa de 23K. A peça da
trilha é outro objeto — texto, uma tarefa e uma frase de cabeça — e não tem por
que herdar aquele CSS nem fazer aquele arquivo crescer.
"""
import html

import config

_CSS = """
  @page { size: A4; margin: 18mm 16mm; }
  body { font-family: Georgia, 'Times New Roman', serif; color: #1b1b1b; line-height: 1.55; }
  .selo { font-family: system-ui, sans-serif; font-size: 10px; letter-spacing: .18em;
          text-transform: uppercase; color: #8a6a2f; }
  h1 { font-size: 26px; line-height: 1.2; margin: 6px 0 2px; }
  .eixo { font-family: system-ui, sans-serif; font-size: 12px; color: #6b6b6b; margin: 0 0 22px; }
  .abertura { font-style: italic; color: #4a4a4a; border-left: 3px solid #d8c9a6;
              padding-left: 12px; margin: 0 0 22px; }
  .corpo p { margin: 0 0 12px; }
  .bloco { border: 1px solid #e2dccc; border-radius: 8px; padding: 14px 16px; margin: 22px 0 0; }
  .bloco .rot { font-family: system-ui, sans-serif; font-size: 10px; letter-spacing: .16em;
                text-transform: uppercase; color: #8a6a2f; margin: 0 0 6px; }
  .bloco p { margin: 0; }
  .ferramenta { margin: 22px 0 0; }
  .ferramenta a { font-family: system-ui, sans-serif; font-size: 13px; color: #8a6a2f; }
  .rodape { margin-top: 30px; font-family: system-ui, sans-serif; font-size: 11px; color: #8a8a8a; }
"""


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _paragrafos(texto):
    """Blocos separados por linha em branco viram <p>. Sem markdown: o conteúdo é
    nosso e escrito à mão, não vale carregar um parser pra isso."""
    blocos = [b.strip() for b in (texto or "").replace("\r\n", "\n").split("\n\n")]
    return "".join(f"<p>{_esc(b)}</p>" for b in blocos if b)


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
