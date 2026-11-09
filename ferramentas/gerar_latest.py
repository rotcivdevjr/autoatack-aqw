"""
Gera o latest.json que o app baixa para saber se há versão nova.
Uso: python ferramentas/gerar_latest.py --versao 1.0.1 --repo usuario/repo
         --instalador saida/AutoAtack-AQW-Setup-1.0.1.exe --notas NOVIDADES.md
"""
import argparse
import hashlib
import json
import os
import re
import time

ap = argparse.ArgumentParser()
ap.add_argument("--versao", required=True)
ap.add_argument("--repo", required=True)
ap.add_argument("--instalador", required=True)
ap.add_argument("--notas", default="")
a = ap.parse_args()

versao = a.versao.strip().lstrip("vV")
h = hashlib.sha256()
with open(a.instalador, "rb") as f:
    for bloco in iter(lambda: f.read(1 << 20), b""):
        h.update(bloco)

notas = ""
if a.notas and os.path.exists(a.notas):
    texto = open(a.notas, encoding="utf-8").read()
    # pega só a seção desta versão: do "## 1.0.1" até o próximo "## "
    m = re.search(rf"^##\s*v?{re.escape(versao)}\b.*?$(.*?)(?=^##\s|\Z)", texto, re.M | re.S)
    notas = (m.group(1) if m else "").strip()

nome = os.path.basename(a.instalador)
info = {
    "versao": versao,
    "url": f"https://github.com/{a.repo}/releases/download/v{versao}/{nome}",
    "sha256": h.hexdigest(),
    "notas": notas,
    "data": time.strftime("%Y-%m-%d"),
}
destino = os.path.join(os.path.dirname(a.instalador), "latest.json")
with open(destino, "w", encoding="utf-8") as f:
    json.dump(info, f, ensure_ascii=False, indent=2)
print(json.dumps(info, ensure_ascii=False, indent=2))
