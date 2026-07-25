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
