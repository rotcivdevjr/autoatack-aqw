"""
versao.py - nome e versão do AutoAtack AQW.

VERSAO e REPO são substituídos na hora de criar o app (GitHub Actions), pelo arquivo
_build_info.py gerado por ferramentas/gerar_build_info.py. Rodando direto do código,
REPO fica vazio e a atualização automática fica desligada.
"""
APP_NOME = "AutoAtack AQW"
VERSAO = "1.0.0"
REPO = ""  # "usuario/repositorio" no GitHub, de onde vêm as atualizações

try:  # gerado no build; não fica no repositório
    from _build_info import VERSAO, REPO  # noqa: F401,F811
except ImportError:
    pass


def versao_curta(v=None):
    """'1.0.0' -> '1.0'  |  '1.2.3' -> '1.2.3'"""
    v = v or VERSAO
    partes = v.split(".")
    while len(partes) > 2 and partes[-1] == "0":
        partes.pop()
    return ".".join(partes)
