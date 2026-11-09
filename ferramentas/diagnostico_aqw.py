"""
Diagnóstico do cliente do AQW (somente Windows, só Python 3, não instala nada).
Só LÊ informações: classe da janela, programa que a criou, tipos de arquivo da pasta
e se a captura da janela funciona mesmo com outra janela por cima.
Gera o arquivo diagnostico_aqw.txt na mesma pasta: cole o conteúdo dele no chat.
"""
import ctypes
import os
import socket
import sys
import time

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                                ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint)]
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
linhas = []


def p(texto=""):
    print(texto)
    linhas.append(str(texto))


def titulo_de(h):
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def classe_de(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, buf, 256)
    return buf.value


def listar_janelas():
    achadas = []

    def cb(h, _):
        if user32.IsWindowVisible(h) and user32.GetWindowTextLengthW(h) > 0:
            achadas.append((titulo_de(h).strip(), h))
        return True

    user32.EnumWindows(Proc(cb), 0)
    return [a for a in achadas if a[0]]


def exe_do_processo(hwnd):
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return pid.value, None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        tam = ctypes.c_uint(1024)
        ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam))
        return pid.value, (buf.value if ok else None)
    finally:
        kernel32.CloseHandle(h)


def classes_filhas(hwnd):
    cont = {}

    def cb(h, _):
        c = classe_de(h)
        cont[c] = cont.get(c, 0) + 1
        return True

    user32.EnumChildWindows(hwnd, Proc(cb), 0)
    return cont


class BIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("a", ctypes.c_int32), ("b", ctypes.c_int32),
                ("c", ctypes.c_uint32), ("d", ctypes.c_uint32)]


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long),
                ("b", ctypes.c_long)]


def capturar_janela(hwnd):
    """PrintWindow com PW_RENDERFULLCONTENT: tenta pegar a janela mesmo coberta."""
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.r - r.l, r.b - r.t
    if w < 10 or h < 10:
        return None
    tela = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(tela)
    bmp = gdi32.CreateCompatibleBitmap(tela, w, h)
    antigo = gdi32.SelectObject(mem, bmp)
    try:
        ok = user32.PrintWindow(hwnd, mem, 2)
        bih = BIH()
        bih.biSize = ctypes.sizeof(BIH)
        bih.biWidth, bih.biHeight, bih.biPlanes, bih.biBitCount = w, -h, 1, 32
        buf = (ctypes.c_ubyte * (w * h * 4))()
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0)
        dados = bytes(buf)
    finally:
        gdi32.SelectObject(mem, antigo)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(0, tela)
    amostra = dados[::4 * 11]
    n = max(1, len(amostra))
    brilho = sum(amostra) / n
    nao_preto = sum(1 for v in amostra if v > 12) * 100.0 / n
    return bool(ok), w, h, brilho, nao_preto


MARCAS = {
    "app.asar": "Electron (app empacotado)",
    "libcef.dll": "CEF (Chromium embutido)",
    "chrome_100_percent.pak": "Chromium/Electron",
    "WebView2Loader.dll": "WebView2 (Edge embutido)",
    "EBWebView": "WebView2 (pasta de dados)",
    "UnityPlayer.dll": "Unity",
    "flash.ocx": "Flash",
    "ruffle": "Ruffle (Flash em Rust/WebAssembly)",
    "electron.exe": "Electron",
}


def varrer_pasta(base):
    achados = {}
    swfs = 0
    total = 0
    for raiz, dirs, arqs in os.walk(base):
        prof = raiz[len(base):].count(os.sep)
        if prof > 3:
            dirs[:] = []
            continue
        for nome in dirs + arqs:
            total += 1
            baixo = nome.lower()
            if baixo.endswith(".swf"):
                swfs += 1
            for marca, desc in MARCAS.items():
                if marca.lower() in baixo:
                    achados.setdefault(desc, os.path.join(raiz, nome))
    return achados, swfs, total


def main():
    p("=== DIAGNÓSTICO AQW ===")
    janelas = listar_janelas()
    for i, (t, h) in enumerate(janelas):
        p(f"[{i}] {t[:80]}")
    try:
        escolha = int(input("\nDigite o número da janela do JOGO: "))
        hwnd = janelas[escolha][1]
    except Exception:
        p("Número inválido.")
        return

    p(f"\nTítulo: {titulo_de(hwnd)}")
    p(f"Classe da janela: {classe_de(hwnd)}")
    pid, exe = exe_do_processo(hwnd)
    p(f"PID: {pid}")
    p(f"Programa: {exe}")

    p("\nJanelas filhas (classe: quantidade):")
    for c, n in sorted(classes_filhas(hwnd).items(), key=lambda x: -x[1])[:25]:
        p(f"  {c}: {n}")

    if exe:
        base = os.path.dirname(exe)
        p(f"\nPasta do programa: {base}")
        try:
            itens = sorted(os.listdir(base))
            p(f"Itens na pasta ({len(itens)}), primeiros 60:")
            for it in itens[:60]:
                p(f"  {it}")
            achados, swfs, total = varrer_pasta(base)
            p(f"\nArquivos/pastas olhados: {total}  |  arquivos .swf: {swfs}")
            if achados:
                p("Pistas encontradas:")
                for desc, caminho in achados.items():
                    p(f"  {desc}  ->  {caminho}")
            else:
                p("Nenhuma pista conhecida encontrada.")
        except Exception as e:
            p(f"Não consegui ler a pasta: {e}")

    p("\nPorta de depuração do Chromium (9222) aberta?")
    try:
        s = socket.create_connection(("127.0.0.1", 9222), timeout=0.6)
        s.close()
        p("  SIM, há algo escutando na porta 9222.")
    except Exception:
        p("  Não (normal; só abre se o app for iniciado com essa opção).")

    p("\n--- Teste de captura da janela ---")
    a = capturar_janela(hwnd)
    if not a:
        p("Não consegui capturar a janela (minimizada?).")
    else:
        p(f"Captura 1 (janela como está): ok={a[0]} {a[1]}x{a[2]} brilho={a[3]:.1f} "
          f"pixels não-pretos={a[4]:.0f}%")
        input("\nAGORA coloque outra janela (Bloco de Notas, etc.) POR CIMA do jogo, "
              "cobrindo bem, e aperte ENTER aqui... ")
        print("Capturando em 3 segundos (volte a cobrir o jogo se precisar)...")
        time.sleep(3)
        b = capturar_janela(hwnd)
        if b:
            p(f"Captura 2 (jogo COBERTO): ok={b[0]} brilho={b[3]:.1f} "
              f"pixels não-pretos={b[4]:.0f}%")
            if a[4] > 20 and b[4] > 20:
                p("RESULTADO: dá para ler o jogo mesmo coberto.")
            elif b[4] <= 5:
                p("RESULTADO: capturou preto/vazio; leitura em 2º plano não funciona assim.")
            else:
                p("RESULTADO: inconclusivo.")

    caminho = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "diagnostico_aqw.txt")
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas))
        p(f"\nRelatório salvo em: {caminho}")
    except Exception:
        pass
    input("\nAperte ENTER para fechar.")


if __name__ == "__main__":
    main()
