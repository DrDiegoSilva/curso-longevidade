"""
Envia uma mensagem de texto (de um arquivo .txt UTF-8) para o WhatsApp via Z-API.
Uso: python enviar_zap.py caminho_da_mensagem.txt
Le credenciais de C:\\Users\\edson\\.zapi-config.json
"""
import sys, io, json, urllib.request
import config  # credenciais portáveis (env no VPS, arquivo no Windows)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

def main():
    if len(sys.argv) < 2:
        raise SystemExit("uso: python enviar_zap.py mensagem.txt")
    msg = open(sys.argv[1], encoding="utf-8").read()
    cfg = config.zapi()
    url = f"https://api.z-api.io/instances/{cfg['instanceId']}/token/{cfg['instanceToken']}/send-text"
    body = json.dumps({"phone": cfg["destinoNumero"], "message": msg}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Client-Token": cfg["clientToken"],
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        print(r.read().decode("utf-8", "replace"))

if __name__ == "__main__":
    main()
