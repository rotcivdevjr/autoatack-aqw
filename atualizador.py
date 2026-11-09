"""
atualizador.py - atualização automática do AutoAtack AQW.

Cada versão publicada no GitHub (aba Releases) tem dois arquivos:
  AutoAtack-AQW-Setup-X.Y.Z.exe   o instalador
  latest.json                     {"versao", "url", "sha256", "notas"}
O app lê o latest.json da versão mais nova, compara com a própria versão e, se houver
uma nova, baixa o instalador, confere o SHA-256 e roda em modo silencioso. O instalador
fecha o app, troca os arquivos e abre o app de novo. As configurações do usuário ficam em
%APPDATA%\\AutoAtack AQW e não são tocadas.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

from versao import APP_NOME, REPO, VERSAO

URL_INFO = "https://github.com/{repo}/releases/latest/download/latest.json"
CABECALHOS = {"User-Agent": f"AutoAtack-AQW/{VERSAO}"}


def _num(v):
    partes = [int(x) for x in re.findall(r"\d+", str(v))[:3]]
    return tuple(partes + [0] * (3 - len(partes)))


def disponivel():
    """Só a versão instalada (criada pelo GitHub Actions) sabe de onde buscar atualizações."""
    return bool(REPO) and getattr(sys, "frozen", False)


def buscar(timeout=8):
    """Retorna o latest.json se houver versão mais nova; senão None. Erros de rede sobem."""
    req = urllib.request.Request(URL_INFO.format(repo=REPO), headers=CABECALHOS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        info = json.loads(r.read().decode("utf-8"))
    if not isinstance(info, dict) or "versao" not in info or "url" not in info:
        raise ValueError("latest.json inválido")
    return info if _num(info["versao"]) > _num(VERSAO) else None


def baixar(info, progresso=None, timeout=30):
    """Baixa o instalador para a pasta temporária e confere o SHA-256. Retorna o caminho."""
    nome = f"AutoAtack-AQW-Setup-{info['versao']}.exe"
    destino = os.path.join(tempfile.gettempdir(), nome)
    parcial = destino + ".part"
    h = hashlib.sha256()
    req = urllib.request.Request(info["url"], headers=CABECALHOS)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(parcial, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        lidos = 0
        while True:
            bloco = r.read(64 * 1024)
            if not bloco:
                break
            f.write(bloco)
            h.update(bloco)
            lidos += len(bloco)
            if progresso:
                progresso(lidos, total)
    esperado = str(info.get("sha256") or "").lower()
    if esperado and h.hexdigest().lower() != esperado:
        os.remove(parcial)
        raise ValueError("o arquivo baixado veio corrompido (SHA-256 não confere)")
    os.replace(parcial, destino)
    return destino


def instalar(caminho):
    """Roda o instalador em modo silencioso, separado do app (o app deve fechar logo depois)."""
    DETACHED_PROCESS = 0x00000008
    subprocess.Popen([caminho, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                      "/CLOSEAPPLICATIONS"], close_fds=True, creationflags=DETACHED_PROCESS)


__all__ = ["APP_NOME", "VERSAO", "disponivel", "buscar", "baixar", "instalar"]
