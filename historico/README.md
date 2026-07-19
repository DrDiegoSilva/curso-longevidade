# Histórico de atualizações (resumos já enviados)

`resumos.json` guarda os **resumos científicos semanais** dos temas de atualização (Obesidade, Hormônios, Lipedema, Performance) que já foram enviados no WhatsApp do Dr. Diego. **Não** inclui o curso de Longevidade (esse é o ebook, na raiz).

## Estrutura
```json
{
  "gerado_em": "AAAA-MM-DD",
  "temas": ["Hormonios", "Obesidade", "Performance", ...],
  "total": 6,
  "resumos": [
    { "data": "2026-07-06", "dia": "segunda", "tema": "Obesidade", "texto": "..." }
  ]
}
```
`texto` está em **formato WhatsApp**: `*negrito*` com asteriscos, `🗓️ mês/ano` abrindo cada estudo, emojis de seção (📊 ⚠️ 🛠️ 🔬 🧠).

## Como publicar no site (sugestão p/ o Claude do Mac)
Renderizar como uma página **"Atualizações"** — agrupar por tema, ordenar por data desc, converter `*x*` e `**x**` em `<strong>` e cabeçalhos `##` em títulos (a mesma lógica do `md_to_html` em `app/ebook_curso.py` já faz isso). Pode ser uma rota nova no mesmo container do curso (ex.: `/atualizacoes`) ou uma aba dentro do ebook.

_Fonte: extraído do `logs/resumo.log` do PC (texto integral de cada envio). Atualizável: rodar de novo o extrator conforme novas semanas forem enviadas._
