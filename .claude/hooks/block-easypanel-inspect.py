#!/usr/bin/env python3
"""PreToolUse hook: bloqueia chamadas ao EasyPanel que devolvem o env do
servico inteiro em texto puro (ASAAS_API_KEY, DATABASE_URL, OPENAI_API_KEY,
etc.), mesmo quando a chamada da certo. Ja vazou 3x neste projeto (2026-07-29,
2026-07-30, 2026-08-27) -- ver memoria easypanel-deploy-curso / item43-aviso-troca-termina.
"""
import json
import sys

RISKY_TOOLS = {
    "mcp__easypanel__inspect_app",
    "mcp__easypanel__inspect_compose",
    "mcp__easypanel__inspect_database",
}

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # entrada ilegivel: nao bloqueia, so nao atua

tool = payload.get("tool_name", "")
tool_input = payload.get("tool_input") or {}
procedure = str(tool_input.get("procedure", "")).lower()

blocked = tool in RISKY_TOOLS or (
    tool == "mcp__easypanel__trpc_raw" and "inspect" in procedure
)

if blocked:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "BLOQUEADO: esta chamada do EasyPanel devolve o env inteiro do "
                "servico em texto puro (ASAAS_API_KEY, DATABASE_URL, OPENAI_API_KEY "
                "etc.), mesmo em sucesso -- ja vazou 3x neste projeto. Use "
                "mcp__easypanel__list_actions ou get_action_log pra checar status de "
                "deploy em vez disso. Se realmente precisar do env, peca pro Diego "
                "olhar direto no painel."
            ),
        }
    }))
