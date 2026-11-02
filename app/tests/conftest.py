"""Setup que roda ANTES de qualquer teste importar `config` -- `os.environ` é lido na
hora do `import`/`importlib.reload(config)` de cada teste, então setar aqui (carregado
pelo pytest antes de qualquer módulo de teste) garante que todo teste veja o mesmo valor,
mesmo os que nunca tocam em `config` diretamente.

`SEND_DELAY_SEC` (pausa real entre mensagens de WhatsApp, inclusive dentro do envio de UM
assinante -- ver daily._enviar_estudo_para e trilha._enviar_uma_peca) tem que ser real em
produção (evita rajada que provedores de WhatsApp tratam como automação suspeita), mas
zerado em teste: sem isso, qualquer teste que exercite o envio completo soma vários
`time.sleep(4.0)` reais e a suíte inteira passa a levar minutos em vez de segundos."""
import os

os.environ.setdefault("DSCURSO_SEND_DELAY_SEC", "0")
