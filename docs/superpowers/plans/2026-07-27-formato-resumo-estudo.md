# Novo formato do resumo de estudo (SYS_ESTUDO) — Plano

**Goal:** máquina de conteúdo gera resumo de UM estudo no formato aprovado (🎯 direto no topo + apreciação crítica), via novo `SYS_ESTUDO`, sem tocar no digest (`SYS_APROF`).

**Base:** feat/formato-resumo-estudo (8823a61). Spec: `docs/superpowers/specs/2026-07-27-formato-resumo-estudo-design.md`.

## Task 1: `SYS_ESTUDO` + rewire dos geradores de um estudo (TDD)

**Arquivos:** `app/resumo_diario.py`, `app/curadoria.py`, `app/tests/test_formato_estudo.py` (novo).

- [ ] **Step 1 — teste que falha** (`app/tests/test_formato_estudo.py`):

```python
"""Testes do formato SYS_ESTUDO (estrutural + rewire). Standalone."""
import os, sys, tempfile, importlib, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestFormatoEstudo(unittest.TestCase):
    def setUp(self):
        os.environ["DSCURSO_ARTIGOS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
        import resumo_diario as rd; importlib.reload(rd); self.rd = rd

    def test_sys_estudo_tem_secoes_e_guardrails(self):
        s = self.rd.SYS_ESTUDO
        for m in ["RESUMO DIRETO", "RESUMO COMPLETO", "O que o estudo perguntou",
                  "Vieses e limita", "Pontos fortes", "Conflito de interesse",
                  "não declarado", "NÃO repita o título"]:
            self.assertIn(m, s)
        self.assertTrue("nunca invente" in s.lower() or "não invente" in s.lower())

    def test_sys_aprof_segue_para_o_digest(self):
        self.assertTrue(hasattr(self.rd, "SYS_APROF"))
        self.assertNotEqual(self.rd.SYS_ESTUDO, self.rd.SYS_APROF)

    def test_gerar_texto_usa_sys_estudo(self):
        cap = {}
        orig = self.rd.claude
        self.rd.claude = lambda model, prompt, system="", **k: cap.update(system=system, prompt=prompt) or ""
        try:
            self.rd.gerar_texto_do_artigo({"titulo": "T", "resumo": "ABSTRACT-XYZ",
                                           "data": "2026", "fonte": "F", "doi": "d"})
        finally:
            self.rd.claude = orig
        self.assertEqual(cap["system"], self.rd.SYS_ESTUDO)
        self.assertIn("ABSTRACT-XYZ", cap["prompt"])

    def test_curadoria_usa_sys_estudo(self):
        import curadoria; importlib.reload(curadoria)
        cap = {}
        orig = self.rd.claude
        self.rd.claude = lambda model, prompt, system="", **k: cap.update(system=system) or ""
        try:
            curadoria.gerar_resumo(
                {"titulo": "T", "abstract": "X", "data": "", "fonte": "", "doi": ""},
                gerar_gancho=lambda a: "", gerar_grafico_json=lambda a: "", gerar_titulo=lambda a: "T")
        finally:
            self.rd.claude = orig
        self.assertEqual(cap.get("system"), self.rd.SYS_ESTUDO)


if __name__ == "__main__":
    unittest.main()
```

Run: `cd app && python3 -m unittest tests.test_formato_estudo -v` → FAIL (`SYS_ESTUDO` não existe).

- [ ] **Step 2 — adicionar `SYS_ESTUDO`** em `app/resumo_diario.py`, logo antes de `def gerar_texto_do_artigo` (após `SYS_CURSO`): usar o texto EXATO do spec (bloco `SYS_ESTUDO = (...)`).

- [ ] **Step 3 — apontar `gerar_texto_do_artigo` pro novo prompt.** Trocar em `gerar_texto_do_artigo`:
```python
    return claude(OPUS, f"Aprofunde ESTE estudo para o médico (abra pela data de publicação):\n\n{blob}",
                  system=SYS_APROF, max_tokens=3200)
```
por:
```python
    return claude(OPUS, f"Resuma ESTE estudo para o médico:\n\n{blob}",
                  system=SYS_ESTUDO, max_tokens=3600)
```

- [ ] **Step 4 — `curadoria.gerar_resumo` usa `SYS_ESTUDO`.** Em `app/curadoria.py`, no ramo `if f_resumo is None:` (linhas 182-189): trocar `SYS_APROF` por `SYS_ESTUDO` no import e no `system=`, e `max_tokens=3200` → `3600`. Manter o resto.

- [ ] **Step 5 — rodar:** `cd app && python3 -m unittest tests.test_formato_estudo -v` (PASS 4) e `cd app && python3 -m unittest discover -s tests` (suíte verde).

- [ ] **Step 6 — commit:** `git add app/resumo_diario.py app/curadoria.py app/tests/test_formato_estudo.py && git commit -m "feat(formato): SYS_ESTUDO (🎯 direto + apreciação crítica) nos geradores de um estudo"`

## Smoke ao vivo (manual, precisa da chave Anthropic — não bloqueia merge)

`cd app && python3 -c "import os,resumo_diario as rd; print(rd.gerar_texto_do_artigo({'titulo':'TRT em mulheres','fonte':'J Pers Med','data':'2026-04','doi':'','resumo': open('/caminho/estudo.txt').read()[:14000]}))"` (com `ANTHROPIC_API_KEY`/config setada). Comparar com o mockup. Se a saída divergir do formato, refinar o texto do `SYS_ESTUDO`.

## Self-review
- Cobre: novo prompt + rewire dos 2 geradores de um estudo + digest intocado + testes estruturais/rewire. Sem placeholders. `SYS_ESTUDO`/`SYS_APROF` consistentes entre spec e plano.
