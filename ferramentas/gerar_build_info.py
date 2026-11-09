"""
Gera os arquivos que o build precisa:
  _build_info.py     versão e repositório (o app usa para buscar atualizações)
  version_info.txt   propriedades do .exe no Windows (versão, nome, empresa)
Uso: python ferramentas/gerar_build_info.py --versao 1.0.0 --repo usuario/repositorio
"""
import argparse
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("--versao", required=True)
ap.add_argument("--repo", default="")
a = ap.parse_args()

versao = a.versao.strip().lstrip("vV")
if not re.fullmatch(r"\d+\.\d+\.\d+", versao):
    raise SystemExit(f"Versão inválida: {a.versao!r} (use o formato 1.0.0)")
n = [int(x) for x in versao.split(".")] + [0]

with open(os.path.join(RAIZ, "_build_info.py"), "w", encoding="utf-8") as f:
    f.write(f"VERSAO = {versao!r}\nREPO = {a.repo.strip()!r}\n")

with open(os.path.join(RAIZ, "version_info.txt"), "w", encoding="utf-8") as f:
    f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(n)}, prodvers={tuple(n)}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', 'AutoAtack AQW'),
      StringStruct('FileDescription', 'AutoAtack AQW'),
      StringStruct('FileVersion', '{versao}'),
      StringStruct('InternalName', 'AutoAtack AQW'),
      StringStruct('OriginalFilename', 'AutoAtack AQW.exe'),
      StringStruct('ProductName', 'AutoAtack AQW'),
      StringStruct('ProductVersion', '{versao}')])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])
  ]
)
""")
print(f"build info: versão {versao}, repo {a.repo or '(sem atualização automática)'}")
