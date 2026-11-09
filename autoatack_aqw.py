"""
AutoAtack AQW  -  abas por classe + precisão de lançamento
- Uma aba por classe (renomeável), com skills 1-5, ordem de PRIORIDADE ABSOLUTA
  (a skill de cima, se estiver pronta, sempre é usada primeiro).
- Aba "Cura": autocura pela leitura da barra de vida.
- Aba "Precisão": lê os ícones da barra de skills na tela para saber quando cada skill está
  realmente pronta e CONFIRMA se o cast aconteceu (se não aconteceu, tenta de novo).
  A leitura captura a própria JANELA do jogo (PrintWindow): ela pode ficar atrás de outras
  janelas, só não pode estar minimizada.
Interface: veja ui_tema.py (cores, botões, sons). Imagens e sons ficam na pasta assets/.
Somente Windows. Não precisa instalar nada além do Python 3.
"""
import collections
import base64
import ctypes
import json
import os
import shutil
import sys
import threading
import time
import traceback
import tkinter as tk
from ctypes import wintypes
from tkinter import messagebox, ttk

import atualizador
from versao import APP_NOME, VERSAO, versao_curta

# Faz as coordenadas do tkinter/mouse serem iguais às da tela (pixels reais)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# Timer do Windows com 1 ms (sem isso o sleep() tem passos de ~15 ms)
try:
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass

# tipos corretos (evita erro em Python 64 bits)
user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetForegroundWindow.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.BitBlt.restype = ctypes.c_int
gdi32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                         ctypes.c_uint32]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                            ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_uint]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_ACTIVATE = 0x0006
WM_SETFOCUS = 0x0007
WM_ACTIVATEAPP = 0x001C
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
SRCCOPY = 0x00CC0020
VK_F8 = 0x77
ICONE_RAIO = 10  # o programa olha um quadrado de 21x21 px no centro de cada ícone

DIRETORIO_APP = (os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False)
                 else os.path.dirname(os.path.abspath(__file__)))
# Configurações ficam em %APPDATA%\AutoAtack AQW (atualizar o app não apaga nada)
PASTA_DADOS = os.path.join(os.environ.get("APPDATA") or DIRETORIO_APP, APP_NOME)
os.makedirs(PASTA_DADOS, exist_ok=True)
CONFIG_PATH = os.path.join(PASTA_DADOS, "autoatack_config.json")
_CONFIG_ANTIGO = os.path.join(DIRETORIO_APP, "autoatack_config.json")
if not os.path.exists(CONFIG_PATH) and os.path.exists(_CONFIG_ANTIGO):
    try:  # aproveita a configuração da versão antiga (arquivo ao lado do programa)
        shutil.copy2(_CONFIG_ANTIGO, CONFIG_PATH)
    except Exception:
        pass


def registrar_erro(tipo, valor, tb):
    """O app não tem janela de console: erros vão para %APPDATA%/AutoAtack AQW/erros.log."""
    try:
        with open(os.path.join(PASTA_DADOS, "erros.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  v{VERSAO}\n")
            f.write("".join(traceback.format_exception(tipo, valor, tb)) + "\n")
    except Exception:
        pass


sys.excepthook = registrar_erro
threading.excepthook = lambda a: registrar_erro(a.exc_type, a.exc_value, a.exc_traceback)

# ---------- tema (cores, botões, sons) ----------
from ui_tema import (BG, SURFACE, INPUT_BG, BORDER, RED, RED_HOVER, TEXT, MUTED, DIM, PANEL,
                     FONTE, SOM, asset, botao, campo, caixa_marcar, titulo, Cartao, Degrade,
                     Selo, aplicar_estilo_ttk)

NENHUMA = "Nenhuma"


# ---------- utilitários de janela ----------
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def listar_janelas():
    janelas = []

    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            tamanho = user32.GetWindowTextLengthW(hwnd)
            if tamanho > 0:
                buf = ctypes.create_unicode_buffer(tamanho + 1)
                user32.GetWindowTextW(hwnd, buf, tamanho + 1)
                titulo = buf.value.strip()
                if titulo:
                    janelas.append((titulo, hwnd))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return janelas


def achar_janela_input(hwnd):
    """
    Chrome/Edge só entregam teclado à página pela janela filha
    'Chrome_RenderWidgetHostHWND'. Mandar para a janela principal costuma ser ignorado.
    Se não achar (outro navegador/app), usa a própria janela.
    """
    achados = []

    def callback(h, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if buf.value == "Chrome_RenderWidgetHostHWND" and user32.IsWindowVisible(h):
            achados.append(h)
            return False
        return True

    user32.EnumChildWindows(hwnd, EnumWindowsProc(callback), 0)
    return achados[0] if achados else hwnd


def enviar_tecla_background(alvo, vk, simular_foco=False, topo=None):
    """
    Posta a tecla direto na janela, SEM mexer no foco real do Windows.
    Com simular_foco, antes avisa a janela do jogo de que ela está ativa/focada (mensagens
    WM_ACTIVATEAPP, WM_ACTIVATE e WM_SETFOCUS), porque muitos programas ignoram teclado
    enquanto acham que estão em segundo plano. O foco de verdade continua onde você está.
    """
    topo = topo or alvo
    if simular_foco:
        user32.PostMessageW(topo, WM_ACTIVATEAPP, 1, 0)
        user32.PostMessageW(topo, WM_ACTIVATE, 1, 0)
        user32.PostMessageW(alvo, WM_SETFOCUS, 0, 0)
    scan = user32.MapVirtualKeyW(vk, 0)
    lparam_down = 1 | (scan << 16)
    lparam_up = 1 | (scan << 16) | (1 << 30) | (1 << 31)
    user32.PostMessageW(alvo, WM_KEYDOWN, vk, lparam_down)
    user32.PostMessageW(alvo, WM_CHAR, vk, lparam_down)
    time.sleep(0.06)
    user32.PostMessageW(alvo, WM_KEYUP, vk, lparam_up)


# --- SendInput (tecla "de verdade", exige a janela em primeiro plano) ---
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUT_UNION)]


user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint


def _send_input_tecla(vk, soltar):
    scan = user32.MapVirtualKeyW(vk, 0)
    entrada = INPUT()
    entrada.type = 1  # INPUT_KEYBOARD
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if soltar else 0)
    entrada.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(entrada), ctypes.sizeof(INPUT))


def ativar_janela(hwnd):
    """Traz a janela para frente (com AttachThreadInput, que o Windows costuma aceitar)."""
    if user32.GetForegroundWindow() == hwnd:
        return True
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    fg = user32.GetForegroundWindow()
    tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    tid_eu = kernel32.GetCurrentThreadId()
    ligou = False
    if tid_fg and tid_fg != tid_eu:
        ligou = bool(user32.AttachThreadInput(tid_eu, tid_fg, True))
    user32.SetForegroundWindow(hwnd)
    if ligou:
        user32.AttachThreadInput(tid_eu, tid_fg, False)
    time.sleep(0.03)
    return user32.GetForegroundWindow() == hwnd


def enviar_tecla_foco(hwnd, vk, devolver_foco=False):
    """Foca o jogo, aperta a tecla com SendInput e (opcional) devolve o foco à janela anterior."""
    anterior = user32.GetForegroundWindow()
    ativar_janela(hwnd)
    _send_input_tecla(vk, False)
    time.sleep(0.045)
    _send_input_tecla(vk, True)
    if devolver_foco and anterior and anterior != hwnd and user32.IsWindow(anterior):
        time.sleep(0.03)
        ativar_janela(anterior)


# ---------- digitar no chat do jogo (teleporte) ----------
VK_RETURN = 0x0D
VK_SHIFT = 0x10
KEYEVENTF_UNICODE = 0x0004
user32.VkKeyScanW.restype = ctypes.c_short


def _send_input_unicode(ch):
    """Envia um caractere pelo código Unicode (serve para qualquer letra/símbolo)."""
    for soltar in (False, True):
        e = INPUT()
        e.type = 1
        e.u.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if soltar else 0),
                            0, 0)
        user32.SendInput(1, ctypes.byref(e), ctypes.sizeof(INPUT))


def _digitar_char_foco(ch, atraso):
    """Digita um caractere com SendInput, usando a tecla do layout do teclado (ABNT2 etc.)."""
    r = user32.VkKeyScanW(ord(ch))
    mods = (r >> 8) & 0xFF if r != -1 else 0
    if r == -1 or mods & 0x06:  # sem tecla própria ou precisa de Ctrl/AltGr: vai por Unicode
        _send_input_unicode(ch)
    else:
        vk = r & 0xFF
        if mods & 1:
            _send_input_tecla(VK_SHIFT, False)
        _send_input_tecla(vk, False)
        time.sleep(0.012)
        _send_input_tecla(vk, True)
        if mods & 1:
            _send_input_tecla(VK_SHIFT, True)
    time.sleep(atraso)


def _enter_foco():
    _send_input_tecla(VK_RETURN, False)
    time.sleep(0.04)
    _send_input_tecla(VK_RETURN, True)


def digitar_chat_foco(hwnd, texto, passo, atraso=0.02, devolver_para=None):
    """
    Traz o jogo para a frente, aperta ENTER (abre o chat), digita o texto, ENTER (envia)
    e devolve o foco para a janela de antes. Retorna False se o jogo não veio para a frente.
    """
    ativar_janela(hwnd)
    time.sleep(passo)
    if user32.GetForegroundWindow() != hwnd:
        ativar_janela(hwnd)
        time.sleep(passo)
        if user32.GetForegroundWindow() != hwnd:
            return False
    _enter_foco()
    time.sleep(passo)
    for ch in texto:
        _digitar_char_foco(ch, atraso)
    time.sleep(passo)
    _enter_foco()
    if devolver_para and devolver_para != hwnd and user32.IsWindow(devolver_para):
        time.sleep(0.08)
        ativar_janela(devolver_para)
    return True


def _post_enter(alvo):
    scan = user32.MapVirtualKeyW(VK_RETURN, 0)
    user32.PostMessageW(alvo, WM_KEYDOWN, VK_RETURN, 1 | (scan << 16))
    user32.PostMessageW(alvo, WM_CHAR, 13, 1 | (scan << 16))
    time.sleep(0.04)
    user32.PostMessageW(alvo, WM_KEYUP, VK_RETURN, 1 | (scan << 16) | (1 << 30) | (1 << 31))


def digitar_chat_background(alvo, topo, texto, passo, atraso=0.02, simular_foco=True):
    """Mesma sequência (ENTER, texto, ENTER) postada direto na janela, sem mexer no foco."""
    if simular_foco:
        user32.PostMessageW(topo, WM_ACTIVATEAPP, 1, 0)
        user32.PostMessageW(topo, WM_ACTIVATE, 1, 0)
        user32.PostMessageW(alvo, WM_SETFOCUS, 0, 0)
    _post_enter(alvo)
    time.sleep(passo)
    for ch in texto:
        user32.PostMessageW(alvo, WM_CHAR, ord(ch), 1)
        time.sleep(atraso)
    time.sleep(passo)
    _post_enter(alvo)
    return True


# ---------- captura rápida da tela ----------
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


def posicao_mouse():
    p = POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long),
                ("b", ctypes.c_long)]


user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]


# ---------- calibragem por clique (gancho de mouse de baixo nível) ----------
WH_MOUSE_LL = 14
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_QUIT = 0x0012
VK_ESCAPE = 0x1B
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", POINT), ("mouseData", ctypes.c_ulong), ("flags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, ctypes.c_uint]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t,
                                  ctypes.c_ssize_t]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_size_t,
                                      ctypes.c_ssize_t]
user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.GetAncestor.restype = ctypes.c_void_p
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p


class GanchoMouse:
    """
    Só fica ligado durante a calibragem. Pega os cliques feitos DENTRO da janela do jogo e não
    os entrega ao jogo (clicar no ícone usaria a skill e estragaria a calibragem).
    Cliques fora do jogo, ou em cima do próprio AutoAtack, passam normalmente.
    Botão esquerdo = marcar o ponto. Botão direito = cancelar.
    """

    def __init__(self):
        self.cliques = collections.deque()
        self.hwnd_jogo = None
        self.hwnd_app = None
        self.ativo = False
        self._tid = None
        self._proc = None

    @staticmethod
    def _dentro(hwnd, x, y):
        if not hwnd:
            return False
        r = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return False
        return r.l <= x < r.r and r.t <= y < r.b

    def ligar(self, hwnd_jogo, hwnd_app):
        if self.ativo:
            self.hwnd_jogo, self.hwnd_app = hwnd_jogo, hwnd_app
            return True
        self.hwnd_jogo, self.hwnd_app = hwnd_jogo, hwnd_app
        self.cliques.clear()
        pronto = threading.Event()
        threading.Thread(target=self._rodar, args=(pronto,), daemon=True).start()
        pronto.wait(1.5)
        return self.ativo

    def _rodar(self, pronto):
        self._tid = kernel32.GetCurrentThreadId()

        def proc(n, wparam, lparam):
            try:
                if n == 0 and wparam in (WM_LBUTTONDOWN, WM_LBUTTONUP,
                                         WM_RBUTTONDOWN, WM_RBUTTONUP):
                    info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    x, y = info.pt.x, info.pt.y
                    if (not self._dentro(self.hwnd_app, x, y)
                            and self._dentro(self.hwnd_jogo, x, y)):
                        if wparam == WM_LBUTTONDOWN:
                            self.cliques.append(("esq", x, y))
                        elif wparam == WM_RBUTTONDOWN:
                            self.cliques.append(("dir", x, y))
                        return 1  # engole o clique: o jogo não recebe
            except Exception:
                pass
            return user32.CallNextHookEx(None, n, wparam, lparam)

        self._proc = HOOKPROC(proc)  # guardar a referência (senão o Python apaga)
        h = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not h:
            pronto.set()
            return
        self.ativo = True
        pronto.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(h)
        self.ativo = False

    def desligar(self):
        if self.ativo and self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self.ativo = False


def _copiar_regiao(hdc_origem, x, y, w, h):
    """Copia um retângulo de um DC (bitmap da janela). Retorna bytes BGRA (ou None)."""
    hdc_mem = gdi32.CreateCompatibleDC(hdc_origem)
    bmp = gdi32.CreateCompatibleBitmap(hdc_origem, w, h)
    antigo = gdi32.SelectObject(hdc_mem, bmp)
    try:
        if not gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_origem, x, y, SRCCOPY):
            return None
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # de cima para baixo
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        buf = (ctypes.c_ubyte * (w * h * 4))()
        if not gdi32.GetDIBits(hdc_mem, bmp, 0, h, buf, ctypes.byref(bmi), 0):
            return None
        return bytes(buf)
    finally:
        gdi32.SelectObject(hdc_mem, antigo)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(hdc_mem)


class JanelaCapturada:
    """
    Captura a JANELA do jogo com PrintWindow (PW_RENDERFULLCONTENT), então funciona mesmo com
    outras janelas por cima. Não funciona com a janela minimizada.
    Todas as regiões são relativas ao canto superior esquerdo da janela (inclui a borda).
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.mem = None
        self.bmp = None
        self.antigo = None
        self.w = 0
        self.h = 0
        self.hwnd = None
        self.valida = False
        self.ultimo = 0.0
        self.ultimo_ms = 0.0

    def _liberar(self):
        if self.mem:
            if self.antigo:
                gdi32.SelectObject(self.mem, self.antigo)
            if self.bmp:
                gdi32.DeleteObject(self.bmp)
            gdi32.DeleteDC(self.mem)
        self.mem = self.bmp = self.antigo = None
        self.w = self.h = 0

    def atualizar(self, hwnd, min_intervalo=0.0):
        with self.lock:
            agora = time.monotonic()
            if (hwnd == self.hwnd and self.valida and self.mem
                    and agora - self.ultimo < min_intervalo):
                return True
            if not hwnd or user32.IsIconic(hwnd):
                self.valida = False
                return False
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            w, h = r.r - r.l, r.b - r.t
            if w < 50 or h < 50:
                self.valida = False
                return False
            if self.mem is None or w != self.w or h != self.h:
                self._liberar()
                tela = user32.GetDC(0)
                try:
                    self.mem = gdi32.CreateCompatibleDC(tela)
                    self.bmp = gdi32.CreateCompatibleBitmap(tela, w, h)
                    self.antigo = gdi32.SelectObject(self.mem, self.bmp)
                finally:
                    user32.ReleaseDC(0, tela)
                self.w, self.h = w, h
            ok = bool(user32.PrintWindow(hwnd, self.mem, 2))
            self.hwnd = hwnd
            self.valida = ok
            self.ultimo = time.monotonic()
            self.ultimo_ms = (self.ultimo - agora) * 1000
            return ok

    def regiao(self, reg):
        """Bytes BGRA de uma região (x1, y1, x2, y2) relativa à janela, do último quadro."""
        with self.lock:
            if not self.valida or not self.mem:
                return None
            x1, y1, x2, y2 = reg
            w, h = x2 - x1 + 1, y2 - y1 + 1
            if w < 1 or h < 1 or x1 < 0 or y1 < 0 or x1 + w > self.w or y1 + h > self.h:
                return None
            return _copiar_regiao(self.mem, x1, y1, w, h)

    def quadro_completo(self):
        with self.lock:
            if not self.valida or not self.mem:
                return None
            return self.w, self.h, _copiar_regiao(self.mem, 0, 0, self.w, self.h)


def ler_vida_percent(regiao, minimo_vermelho, captura):
    """
    Lê a vida em % (0-100) procurando o ÚLTIMO pixel vermelho da barra,
    da direita para a esquerda. Assim o degradê da barra e o número
    escrito em cima dela não atrapalham.
    """
    x1, y1, x2, y2 = regiao
    w = x2 - x1 + 1
    h = y2 - y1 + 1
    if w < 10 or h < 1:
        return None
    dados = captura.regiao(regiao)
    if dados is None:
        return None
    for col in range(w - 1, -1, -1):
        for row in range(h):
            i = (row * w + col) * 4
            b, g, r = dados[i], dados[i + 1], dados[i + 2]
            if r >= minimo_vermelho and r > g * 2 and r > b * 2:
                return (col + 1) * 100.0 / w
    return 0.0


def brilho_regiao(regiao, captura):
    """Brilho médio (0-255) de um pedaço da janela. Ícone em recarga = mais escuro."""
    x1, y1, x2, y2 = regiao
    w = x2 - x1 + 1
    h = y2 - y1 + 1
    dados = captura.regiao(regiao)
    if not dados:
        return None
    n = w * h
    return (sum(dados[0::4]) + sum(dados[1::4]) + sum(dados[2::4])) / (3.0 * n)


def alvo_na_tela(regiao, captura, minimo_vermelho):
    """
    True se o painel do ALVO (mob/boss) está aberto e com vida. Esse painel só aparece no topo
    do jogo quando há algo selecionado, e some quando o alvo morre.
    Exige duas coisas, para o fundo do mapa (ex.: uma lua vermelha) não enganar:
      1) vermelho na barra de vida do alvo;
      2) a barra AZUL de mana logo abaixo dela.
    None = não deu para ler (janela minimizada etc.).
    """
    hp = ler_vida_percent(regiao, minimo_vermelho, captura)
    if hp is None:
        return None
    if hp <= 0:
        return False
    x1, y1, x2, y2 = regiao
    yc = (y1 + y2) // 2
    colunas = max(8, (x2 - x1) // 8)
    abaixo = captura.regiao((x1, yc + 4, x1 + colunas - 1, yc + 45))
    if not abaixo:
        return None
    azuis = 0
    for i in range(0, len(abaixo), 4):
        b, g, r = abaixo[i], abaixo[i + 1], abaixo[i + 2]
        if b >= 110 and b > r * 1.8 and b >= g * 1.2:
            azuis += 1
    return azuis >= colunas


def cinza_regiao(regiao, captura):
    """Tons de cinza (0-255) de cada pixel da região, como bytes. None se não deu para ler."""
    dados = captura.regiao(regiao)
    if not dados:
        return None
    return bytes((dados[i] + dados[i + 1] + dados[i + 2]) // 3 for i in range(0, len(dados), 4))


def fracao_escura(atual, base):
    """
    Que parte do ícone está ESCURECIDA em relação ao ícone pronto (0.0 a 1.0).
    O AQW escurece o ícone com uma "varredura" durante a recarga; contando pixel por pixel,
    o ícone só volta a ~0% quando a varredura termina de verdade. (A média de brilho,
    usada antes, passava do limite antes da hora e o programa apertava cedo demais.)
    """
    total = escuros = 0
    for a, b in zip(atual, base):
        if b > 30:  # pixels que já eram pretos no ícone pronto não contam
            total += 1
            if a < b * 0.72:
                escuros += 1
    if total < 25:  # ícone quase todo escuro: usa a média como reserva
        sa, sb = sum(atual), max(1, sum(base))
        return max(0.0, min(1.0, (1.0 - sa / sb) * 3))
    return escuros / total


def salvar_bmp(caminho, w, h, dados, regioes_vermelhas):
    """Salva o quadro capturado como BMP, com as regiões calibradas contornadas em vermelho."""
    import struct
    buf = bytearray(dados)
    for (x1, y1, x2, y2) in regioes_vermelhas:
        for x in range(max(0, x1 - 1), min(w, x2 + 2)):
            for y in (y1 - 1, y2 + 1):
                if 0 <= y < h:
                    i = (y * w + x) * 4
                    buf[i:i + 4] = b"\x00\x00\xff\xff"
        for y in range(max(0, y1 - 1), min(h, y2 + 2)):
            for x in (x1 - 1, x2 + 1):
                if 0 <= x < w:
                    i = (y * w + x) * 4
                    buf[i:i + 4] = b"\x00\x00\xff\xff"
    cab = b"BM" + struct.pack("<IHHI", 54 + len(buf), 0, 0, 54)
    cab += struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, len(buf), 2835, 2835, 0, 0)
    with open(caminho, "wb") as f:
        f.write(cab + bytes(buf))


# (os widgets de interface agora ficam em ui_tema.py)


def padrao_perfil(n):
    return {
        "nome": f"Classe {n}",
        "intervalo": "500",
        "cura_skill": NENHUMA,
        "precisao": None,
        "ordem": [0, 1, 2, 3, 4],
        "skills": [{"ativa": i == 0, "cd": "0", "espera": False} for i in range(5)],
    }


# ---------- aba de uma classe ----------
class PerfilFrame(tk.Frame):
    def __init__(self, app, dados):
        super().__init__(app.notebook, bg=BG)
        self.app = app
        d = padrao_perfil(1)
        d.update({k: v for k, v in (dados or {}).items() if k in d})

        self.nome = tk.StringVar(value=str(d["nome"]))
        self.intervalo = tk.StringVar(value=str(d["intervalo"]))
        pr = d["precisao"]
        self.precisao = pr if (isinstance(pr, dict) and len(pr.get("centros", [])) == 5
                               and len(pr.get("base", [])) == 5) else None
        self.cura_skill = tk.StringVar(value=str(d["cura_skill"]))

        ordem = d["ordem"]
        if not (isinstance(ordem, list) and sorted(ordem) == [0, 1, 2, 3, 4]):
            ordem = [0, 1, 2, 3, 4]
        self.ordem = list(ordem)

        skills = d["skills"] if isinstance(d["skills"], list) else []
        skills = (skills + padrao_perfil(1)["skills"])[:5]
        self.ativa = [tk.BooleanVar(value=bool(s.get("ativa", False))) for s in skills]
        self.cd = [tk.StringVar(value=str(s.get("cd", "0"))) for s in skills]
        self.espera = [tk.BooleanVar(value=bool(s.get("espera", False))) for s in skills]

        self._montar()
        self.nome.trace_add("write", lambda *a: app.atualizar_titulo_aba(self))

    def _montar(self):
        cartao = Cartao(self)
        cartao.pack(fill="x", padx=10, pady=(10, 6))
        l1 = tk.Frame(cartao, bg=SURFACE)
        l1.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(l1, text="Nome da classe", bg=SURFACE, fg=MUTED, font=(FONTE, 9)).pack(side="left")
        campo(l1, self.nome, 22).pack(side="right", ipady=3)
        l2 = tk.Frame(cartao, bg=SURFACE)
        l2.pack(fill="x", padx=12, pady=(2, 10))
        tk.Label(l2, text="Intervalo (ms, mín. 500) sem leitura de tela", bg=SURFACE, fg=MUTED,
                 font=(FONTE, 9)).pack(side="left")
        campo(l2, self.intervalo, 7).pack(side="right", ipady=3)

        self.lista = Cartao(self)
        self.lista.pack(fill="x", padx=10, pady=6)
        self._desenhar_lista()

        tk.Label(self, bg=BG, fg=DIM, font=(FONTE, 8), justify="left", wraplength=450,
                 text="A ORDEM é o seu combo: com tudo pronto, ele sai de cima para baixo "
                      "(ex.: 4 > 2 > 3 > 5). Depois, NENHUMA skill fica esperando: a que está "
                      "pronta há mais tempo vai primeiro; se empatar, vale a ordem da lista. "
                      "Com a leitura de tela (aba Precisão) vale o ícone do jogo e a recarga em "
                      "segundos é ignorada. A skill de cura (aba Cura) fica fora da rotação."
                 ).pack(fill="x", padx=12, pady=(2, 4))

        botao(self, "Excluir esta aba", lambda: self.app.excluir_perfil(self),
              estilo="perigo", largura=150, altura=30).pack(anchor="e", padx=10, pady=(2, 10))

    def _desenhar_lista(self):
        for w in self.lista.winfo_children():
            w.destroy()
        titulos = ["Ordem", "Usar", "Skill", "Recarga (s)", "Espera 1º uso", "Mover"]
        for c, t in enumerate(titulos):
            tk.Label(self.lista, text=t, bg=SURFACE, fg=DIM, font=(FONTE, 8, "bold")).grid(
                row=0, column=c, padx=6, pady=(8, 2))
        for pos, idx in enumerate(self.ordem):
            r = pos + 1
            tk.Label(self.lista, text=f"{pos + 1}º", bg=SURFACE, fg=RED_HOVER,
                     font=(FONTE, 11, "bold")).grid(row=r, column=0, padx=6)
            caixa_marcar(self.lista, var=self.ativa[idx], bg=SURFACE).grid(row=r, column=1, padx=4)

            skill = tk.Frame(self.lista, bg=SURFACE)
            skill.grid(row=r, column=2, sticky="w", padx=6, pady=3)
            Selo(skill, str(idx + 1), bg=SURFACE).pack(side="left")
            tk.Label(skill, text="Skill", bg=SURFACE, fg=TEXT,
                     font=(FONTE, 11, "bold")).pack(side="left", padx=(6, 0))

            campo(self.lista, self.cd[idx], 6).grid(row=r, column=3, padx=6, pady=2, ipady=2)
            caixa_marcar(self.lista, var=self.espera[idx], bg=SURFACE).grid(row=r, column=4, padx=4)

            setas = tk.Frame(self.lista, bg=SURFACE)
            setas.grid(row=r, column=5, padx=6)
            b_cima = botao(setas, "▲", lambda p=pos: self.mover(p, -1), estilo="secundario",
                           largura=30, altura=26, tam=8)
            b_baixo = botao(setas, "▼", lambda p=pos: self.mover(p, 1), estilo="secundario",
                            largura=30, altura=26, tam=8)
            if pos == 0:
                b_cima.config(state="disabled")
            if pos == len(self.ordem) - 1:
                b_baixo.config(state="disabled")
            b_cima.pack(side="left", padx=1)
            b_baixo.pack(side="left", padx=1)
        tk.Frame(self.lista, bg=SURFACE, height=6).grid(row=7, column=0)

    def mover(self, pos, delta):
        novo = pos + delta
        if 0 <= novo < len(self.ordem):
            self.ordem[pos], self.ordem[novo] = self.ordem[novo], self.ordem[pos]
            self._desenhar_lista()

    def indice_cura(self):
        v = self.cura_skill.get()
        return int(v) - 1 if v in ("1", "2", "3", "4", "5") else None

    def exportar(self):
        return {
            "nome": self.nome.get(),
            "intervalo": self.intervalo.get(),
            "cura_skill": self.cura_skill.get(),
            "precisao": self.precisao,
            "ordem": list(self.ordem),
            "skills": [{"ativa": self.ativa[i].get(), "cd": self.cd[i].get(),
                        "espera": self.espera[i].get()} for i in range(5)],
        }


# ---------- aplicativo ----------
class AutoAtack(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NOME} v{versao_curta()}")
        self.report_callback_exception = registrar_erro
        self.configure(bg=BG)
        self.geometry("520x900")
        self._largura = int(520 * max(1.0, self.winfo_fpixels("1i") / 96.0))
        self.resizable(True, False)
        try:  # ícone certo na barra de tarefas (em vez do ícone do Python)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Alois.AutoAtackAQW")
        except Exception:
            pass
        try:
            self.iconbitmap(default=asset("icone.ico"))
        except Exception:
            try:
                self._icone_img = tk.PhotoImage(file=asset("logo.png"))
                self.iconphoto(True, self._icone_img)
            except Exception:
                pass

        self.ligado = False
        self.thread = None
        self.janelas = []
        self.hotkey_vk = 0x75  # F6
        self.hotkey_nome = "F6"
        self.capturando_tecla = False
        self._hotkey_pressionada = False
        self._lock_teclas = threading.Lock()
        self._cache_input = {}
        self.captura = JanelaCapturada()

        # cura (a barra NÃO é salva: precisa selecionar toda vez que abrir)
        self.regiao_vida = None
        self.hp_atual = None
        self.precisa_curar = False
        self.curas_usadas = 0
        self.ultima_skill = None

        # ícones das skills: a calibragem fica salva em CADA classe (preset)
        self.preset_atual = None  # {"regs", "base", "janela"} da classe ativa
        self.icones = None        # atalho: as 5 regiões do preset atual
        self.icones_base = None
        self._tamanho_errado = False
        self._geracao = 0         # impede dois motores rodando juntos
        self.gap_extra_ms = 0
        self._lbl_preset_txt = ""
        self.confirmados = 0
        self.falhas_cast = 0
        self.log = collections.deque(maxlen=30)

        # calibragem (clique no jogo; F8 continua funcionando como reserva)
        self.gancho = GanchoMouse()
        self._esc_pressionada = False
        # atualizações
        self._upd_estado = None      # None | "buscando" | "baixando"
        self._upd_resultado = None   # resposta das threads de atualização
        self._upd_pct = None
        self.calib_modo = None  # None | "barra" | "icones"
        self.calib_etapa = 0    # 0 = parado
        self.calib_pontos = []
        self._f8_pressionada = False

        self.foco_var = tk.BooleanVar(value=False)
        self.sons_var = tk.BooleanVar(value=True)
        self.cura_ativa = tk.BooleanVar(value=False)
        self.cura_pct = tk.StringVar(value="50")
        self.cura_retry = tk.StringVar(value="600")
        self.cura_min = tk.StringVar(value="100")

        self.tela_ativa = tk.BooleanVar(value=True)
        self.tela_tol = tk.StringVar(value="3")
        self.tela_gap = tk.StringVar(value="120")
        self.tela_confirma = tk.StringVar(value="600")
        self.retry_foco = tk.BooleanVar(value=False)
        self.simular_foco = tk.BooleanVar(value=True)
        self.devolver_foco = tk.BooleanVar(value=False)

        # teleporte
        self.teleportes = []
        self.teleportando = False
        self._tp_fim = 0.0
        self._tp_msg = None
        self.tp_nome = tk.StringVar()
        self.tp_cmd = tk.StringVar()
        self.tp_bg = tk.BooleanVar(value=False)
        self.tp_parar = tk.BooleanVar(value=True)
        self.tp_passo = tk.StringVar(value="150")

        # só atacar com alvo (o painel do mob/boss aparece no topo do jogo)
        self.regiao_alvo = None     # barra de vida do ALVO, relativa à janela do jogo
        self.alvo_janela = None     # tamanho da janela quando foi marcada
        self.alvo_agora = None      # True / False / None (lido no _tick)
        self.sem_alvo = False       # o motor está esperando um alvo
        self.so_alvo = tk.BooleanVar(value=False)
        self.alvo_procura = tk.StringVar(value="2")
        self.alvo_tecla = tk.StringVar(value="1")

        self.perfis = []
        self.perfil_ativo = None
        self.cfg = {}
        self._ultimo_json = ""
        self._contador_tick = 0

        dados = self._ler_config()
        self._aplicar_config_global(dados)

        self._estilo()
        self._montar_ui()
        perfis_salvos = dados.get("perfis") if isinstance(dados.get("perfis"), list) else []
        if not perfis_salvos:
            perfis_salvos = [padrao_perfil(1)]
        for p in perfis_salvos:
            self.adicionar_perfil(p, selecionar=False)
        sel = dados.get("perfil_selecionado", 0)
        if not isinstance(sel, int) or not (0 <= sel < len(self.perfis)):
            sel = 0
        self.notebook.select(self.perfis[sel])
        self.perfil_ativo = self.perfis[sel]
        self._carregar_preset()

        self.atualizar_janelas()
        self._atualizar_label_barra()
        self._atualizar_label_icones()
        self._atualizar_cfg()
        self.after(30, self._checar_teclas)
        self.after(150, self._tick)
        self.after(2500, self._checar_atualizacao)
        self.bind("<Key>", self._tecla_capturada)
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        # a altura da janela se ajusta ao conteúdo (sem cortar nem sobrar espaço)
        self.update_idletasks()
        altura = min(self.winfo_reqheight(), self.winfo_screenheight() - 80)
        self.geometry(f"{self._largura}x{altura}")
        self.minsize(self._largura, altura)

    # ---------- config ----------
    def _ler_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _aplicar_config_global(self, d):
        cura = d.get("cura", {}) if isinstance(d.get("cura"), dict) else {}
        self.cura_ativa.set(bool(cura.get("ativa", False)))
        self.cura_pct.set(str(cura.get("pct", "50")))
        self.cura_retry.set(str(cura.get("retry", "600")))
        self.cura_min.set(str(cura.get("min", "100")))
        pr = d.get("precisao", {}) if isinstance(d.get("precisao"), dict) else {}
        self.tela_ativa.set(bool(pr.get("tela_ativa", True)))
        self.tela_tol.set(str(pr.get("tol", "3")))
        self.tela_gap.set(str(pr.get("gap", "120")))
        self.tela_confirma.set(str(pr.get("confirma", "600")))
        self.retry_foco.set(bool(pr.get("retry_foco2", False)))
        self.simular_foco.set(bool(pr.get("simular_foco", True)))
        self.devolver_foco.set(bool(pr.get("devolver_foco", False)))
        self.foco_var.set(bool(pr.get("foco", False)))
        tps = d.get("teleportes")
        if isinstance(tps, list):
            self.teleportes = [{"nome": str(t.get("nome", "")), "cmd": str(t.get("cmd", ""))}
                               for t in tps if isinstance(t, dict) and t.get("cmd")]
        else:
            self.teleportes = [{"nome": "Shadowfall War", "cmd": "/join shadowfallwar"}]
        tpo = d.get("teleporte", {}) if isinstance(d.get("teleporte"), dict) else {}
        self.tp_bg.set(bool(tpo.get("bg", False)))
        self.tp_parar.set(bool(tpo.get("parar", True)))
        self.tp_passo.set(str(tpo.get("passo", "150")))
        al = d.get("alvo", {}) if isinstance(d.get("alvo"), dict) else {}
        self.so_alvo.set(bool(al.get("ativo", False)))
        self.alvo_procura.set(str(al.get("procura", "2")))
        self.alvo_tecla.set(str(al.get("tecla", "1")))
        try:
            if al.get("regiao") and al.get("janela"):
                self.regiao_alvo = tuple(int(v) for v in al["regiao"])
                self.alvo_janela = tuple(int(v) for v in al["janela"])
        except Exception:
            self.regiao_alvo = self.alvo_janela = None
        self.hotkey_vk = d.get("hotkey_vk", self.hotkey_vk)
        self.hotkey_nome = d.get("hotkey_nome", self.hotkey_nome)
        self.sons_var.set(bool(d.get("sons", True)))
        SOM.ativo = self.sons_var.get()

    def _montar_dados(self):
        idx = self.perfis.index(self.perfil_ativo) if self.perfil_ativo in self.perfis else 0
        return {
            "hotkey_vk": self.hotkey_vk,
            "hotkey_nome": self.hotkey_nome,
            "sons": self.sons_var.get(),
            "cura": {"ativa": self.cura_ativa.get(), "pct": self.cura_pct.get(),
                     "retry": self.cura_retry.get(), "min": self.cura_min.get()},
            "precisao": {"tela_ativa": self.tela_ativa.get(), "tol": self.tela_tol.get(),
                         "gap": self.tela_gap.get(), "confirma": self.tela_confirma.get(),
                         "retry_foco2": self.retry_foco.get(),
                         "simular_foco": self.simular_foco.get(),
                         "devolver_foco": self.devolver_foco.get(),
                         "foco": self.foco_var.get()},
            "perfis": [p.exportar() for p in self.perfis],
            "teleportes": self.teleportes,
            "alvo": {"ativo": self.so_alvo.get(), "procura": self.alvo_procura.get(),
                     "tecla": self.alvo_tecla.get(),
                     "regiao": list(self.regiao_alvo) if self.regiao_alvo else None,
                     "janela": list(self.alvo_janela) if self.alvo_janela else None},
            "teleporte": {"bg": self.tp_bg.get(), "parar": self.tp_parar.get(),
                          "passo": self.tp_passo.get()},
            "perfil_selecionado": idx,
        }

    def _salvar_config(self):
        try:
            texto = json.dumps(self._montar_dados(), ensure_ascii=False, indent=1)
            if texto == self._ultimo_json:
                return
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(texto)
            self._ultimo_json = texto
        except Exception:
            pass

    # ---------- visual ----------
    def _estilo(self):
        aplicar_estilo_ttk(self)
        s = ttk.Style(self)
        s.configure("Vermelha.Vertical.TScrollbar", background="#2a1519", troughcolor=SURFACE,
                    bordercolor=SURFACE, lightcolor="#2a1519", darkcolor="#2a1519",
                    arrowcolor=RED_HOVER, gripcount=0)
        s.map("Vermelha.Vertical.TScrollbar", background=[("active", RED)])

    def _titulo(self, pai, texto, topo=8):
        titulo(pai, texto).pack(anchor="w", padx=22, pady=(topo, 4))

    def _mudou_som(self):
        SOM.ativo = self.sons_var.get()
        if SOM.ativo:
            SOM.clique()

    def _montar_ui(self):
        # ----- cabeçalho com a logo -----
        cab = tk.Frame(self, bg=BG)
        cab.pack(fill="x", padx=20, pady=(14, 0))
        try:
            self._logo_img = tk.PhotoImage(file=asset("logo_72.png"))
            tk.Label(cab, image=self._logo_img, bg=BG).pack(side="left")
        except Exception:
            self._logo_img = None
        textos = tk.Frame(cab, bg=BG)
        textos.pack(side="left", padx=(12, 0))
        linha_t = tk.Frame(textos, bg=BG)
        linha_t.pack(anchor="w")
        tk.Label(linha_t, text="AUTOATACK ", bg=BG, fg=TEXT,
                 font=("Segoe UI Black", 20)).pack(side="left")
        tk.Label(linha_t, text="AQW", bg=BG, fg=RED,
                 font=("Segoe UI Black", 20)).pack(side="left")
        tk.Label(textos, text="Rotação de skills  •  Autocura  •  Precisão", bg=BG, fg=MUTED,
                 font=(FONTE, 9)).pack(anchor="w")
        self.lbl_versao = tk.Label(textos, text=f"v{versao_curta()}  •  verificar atualizações",
                                   bg=BG, fg=DIM, font=(FONTE, 8, "underline"), cursor="hand2")
        self.lbl_versao.pack(anchor="w")
        self.lbl_versao.bind("<Button-1>", lambda e: (SOM.clique(),
                                                      self._checar_atualizacao(manual=True)))
        caixa_marcar(cab, "Sons", self.sons_var, bg=BG, font=(FONTE, 9),
                     comando=self._mudou_som).pack(side="right", anchor="n")
        Degrade(self).pack(fill="x", padx=20, pady=(12, 0))

        # ----- jogo e tecla de atalho -----
        self._titulo(self, "JOGO E TECLA DE ATALHO", 10)
        ctrl = Cartao(self)
        ctrl.pack(fill="x", padx=20)
        l1 = tk.Frame(ctrl, bg=SURFACE)
        l1.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(l1, text="Janela do jogo", bg=SURFACE, fg=MUTED, font=(FONTE, 9),
                 width=13, anchor="w").pack(side="left")
        self.combo = ttk.Combobox(l1, state="readonly", width=30)
        self.combo.pack(side="left", fill="x", expand=True)
        botao(l1, "⟳", self.atualizar_janelas, estilo="secundario", largura=34,
              altura=28).pack(side="left", padx=(6, 0))
        caixa_marcar(ctrl, "Forçar foco (mais confiável, mas PUXA o jogo para a frente)",
                     self.foco_var, bg=SURFACE, font=(FONTE, 8)).pack(anchor="w", padx=12, pady=(2, 2))
        l2 = tk.Frame(ctrl, bg=SURFACE)
        l2.pack(fill="x", padx=12, pady=(4, 10))
        tk.Label(l2, text="Ligar / desligar", bg=SURFACE, fg=MUTED, font=(FONTE, 9),
                 width=13, anchor="w").pack(side="left")
        self.lbl_hotkey = tk.Label(l2, text=self.hotkey_nome, bg=INPUT_BG, fg=TEXT,
                                   font=(FONTE, 11, "bold"), width=9,
                                   highlightbackground=BORDER, highlightthickness=1)
        self.lbl_hotkey.pack(side="left", ipady=3)
        self.btn_vincular = botao(l2, "Vincular tecla", self.vincular_tecla,
                                  estilo="secundario", largura=130, altura=30)
        self.btn_vincular.pack(side="left", padx=8)

        # ----- abas -----
        cab2 = tk.Frame(self, bg=BG)
        cab2.pack(fill="x", padx=20, pady=(12, 4))
        titulo(cab2, "CLASSES  (UMA ABA PARA CADA)").pack(side="left")
        botao(cab2, "+ Nova aba", lambda: self.adicionar_perfil(None, selecionar=True),
              largura=110, altura=28).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="x", padx=16)
        self.notebook.bind("<<NotebookTabChanged>>", self._ao_trocar_aba)
        self.notebook.bind("<ButtonPress-1>", self._clique_aba, add="+")

        self.aba_cura = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.aba_cura, text="❤  Cura")
        self._montar_aba_cura()

        self.aba_precisao = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.aba_precisao, text="◎  Precisão")
        self._montar_aba_precisao()

        self.aba_tp = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.aba_tp, text="✈  Teleporte")
        self._montar_aba_teleporte()

        # ----- liga / desliga e status -----
        self.btn_toggle = botao(self, "LIGAR", self.alternar, estilo="primario",
                                altura=48, tam=15)
        self.btn_toggle.pack(fill="x", padx=20, pady=(14, 6))

        status = Cartao(self)
        status.pack(fill="x", padx=20, pady=(0, 14))
        self.lbl_status = tk.Label(status, text="● DESLIGADO", bg=SURFACE, fg=MUTED,
                                   font=(FONTE, 10, "bold"), wraplength=440, justify="left")
        self.lbl_status.pack(fill="x", padx=12, pady=8)

    def _montar_aba_cura(self):
        f = self.aba_cura
        cartao = Cartao(f)
        cartao.pack(fill="x", padx=10, pady=(10, 6))
        caixa_marcar(cartao, "Autocura ligada", self.cura_ativa, bg=SURFACE,
                     font=(FONTE, 11, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
        grade = tk.Frame(cartao, bg=SURFACE)
        grade.pack(fill="x", padx=12, pady=(0, 10))
        grade.columnconfigure(0, weight=1)
        itens = [("Curar com vida ≤ (%)", self.cura_pct),
                 ("Repetir a cura a cada (ms)", self.cura_retry),
                 ("Vermelho mínimo (0-255)", self.cura_min)]
        for r, (txt, var) in enumerate(itens):
            tk.Label(grade, text=txt, bg=SURFACE, fg=MUTED, font=(FONTE, 9)).grid(
                row=r, column=0, sticky="w", pady=2)
            campo(grade, var, 7).grid(row=r, column=1, padx=(10, 0), pady=2, ipady=2)

        titulo(f, "SKILL DE CURA DE CADA CLASSE").pack(anchor="w", padx=12, pady=(6, 3))
        self.tabela_cura = Cartao(f)
        self.tabela_cura.pack(fill="x", padx=10)

        tk.Label(f, bg=BG, fg=DIM, font=(FONTE, 8), justify="left", wraplength=450,
                 text="A skill escolhida como cura nunca entra na rotação de ataque daquela classe. "
                      "Use \"Nenhuma\" para a classe que não precisa de cura. Com a leitura de "
                      "tela ligada, a cura só é apertada quando o ícone dela estiver pronto."
                 ).pack(fill="x", padx=12, pady=(4, 4))

        self.btn_barra = botao(f, "Selecionar barra de vida", self.selecionar_barra, altura=36)
        self.btn_barra.pack(fill="x", padx=10, pady=(6, 2))
        self.lbl_barra = tk.Label(f, text="", bg=BG, fg=MUTED, font=(FONTE, 9),
                                  wraplength=450, justify="center")
        self.lbl_barra.pack(padx=10)
        self.lbl_hp = tk.Label(f, text="Vida lida: --", bg=BG, fg=TEXT, font=(FONTE, 12, "bold"))
        self.lbl_hp.pack(pady=(2, 4))

        # ----- só atacar com alvo -----
        titulo(f, "ALVO (MOB / BOSS)").pack(anchor="w", padx=12, pady=(4, 3))
        al = Cartao(f)
        al.pack(fill="x", padx=10, pady=(0, 8))
        caixa_marcar(al, "Só atacar quando houver alvo na tela", self.so_alvo, bg=SURFACE,
                     font=(FONTE, 10, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        l1 = tk.Frame(al, bg=SURFACE)
        l1.pack(fill="x", padx=12, pady=2)
        self.btn_alvo = botao(l1, "Selecionar barra do alvo", self.selecionar_alvo,
                              estilo="secundario", altura=30)
        self.btn_alvo.pack(side="left", fill="x", expand=True)
        self.lbl_alvo = tk.Label(l1, text="Alvo: --", bg=SURFACE, fg=MUTED, width=18,
                                 font=(FONTE, 10, "bold"))
        self.lbl_alvo.pack(side="left", padx=(8, 0))
        l2 = tk.Frame(al, bg=SURFACE)
        l2.pack(fill="x", padx=12, pady=(2, 8))
        tk.Label(l2, text="Sem alvo: apertar a tecla", bg=SURFACE, fg=MUTED,
                 font=(FONTE, 9)).pack(side="left")
        ttk.Combobox(l2, textvariable=self.alvo_tecla, state="readonly", width=3,
                     values=["1", "2", "3", "4", "5"]).pack(side="left", padx=6)
        tk.Label(l2, text="a cada (s, 0 = nunca)", bg=SURFACE, fg=MUTED,
                 font=(FONTE, 9)).pack(side="left")
        campo(l2, self.alvo_procura, 5).pack(side="right", ipady=1)

    def _montar_aba_precisao(self):
        f = self.aba_precisao
        cartao = Cartao(f)
        cartao.pack(fill="x", padx=10, pady=(10, 6))
        caixa_marcar(cartao, "Ler os ícones das skills (detecta recarga e confirma o cast)",
                     self.tela_ativa, bg=SURFACE, font=(FONTE, 10, "bold")).pack(
            anchor="w", padx=12, pady=(10, 2))
        self.lbl_preset = tk.Label(cartao, text="", bg=SURFACE, fg=TEXT, font=(FONTE, 10, "bold"),
                                   wraplength=430, justify="left", anchor="w")
        self.lbl_preset.pack(fill="x", padx=12, pady=(2, 4))
        self.btn_icones = botao(cartao, "Calibrar ícones desta classe (5 cliques)",
                                self.calibrar_icones, altura=34)
        self.btn_icones.pack(fill="x", padx=12, pady=(0, 4))
        self.lbl_icones = tk.Label(cartao, text="", bg=SURFACE, fg=MUTED, font=(FONTE, 9),
                                   wraplength=430, justify="center")
        self.lbl_icones.pack(padx=12)
        linha_b = tk.Frame(cartao, bg=SURFACE)
        linha_b.pack(fill="x", padx=12, pady=(6, 3))
        botao(linha_b, "Ícones de agora = PRONTOS", self.rebase_icones, estilo="secundario",
              altura=30).pack(side="left", fill="x", expand=True, padx=(0, 3))
        botao(linha_b, "Salvar imagem de teste", self.salvar_imagem_teste, estilo="secundario",
              altura=30).pack(side="left", fill="x", expand=True, padx=(3, 0))
        botao(cartao, "Apagar a calibragem desta classe", self.apagar_preset, estilo="perigo",
              altura=28, tam=9).pack(fill="x", padx=12, pady=(3, 6))
        self.lbl_live = tk.Label(cartao, text="Ícones: --", bg=INPUT_BG, fg=TEXT,
                                 font=("Consolas", 9, "bold"), highlightbackground=BORDER,
                                 highlightthickness=1)
        self.lbl_live.pack(fill="x", padx=12, pady=(0, 10), ipady=4)

        cartao2 = Cartao(f)
        cartao2.pack(fill="x", padx=10, pady=(0, 6))
        grade = tk.Frame(cartao2, bg=SURFACE)
        grade.pack(fill="x", padx=12, pady=(10, 4))
        grade.columnconfigure(0, weight=1)
        itens = [("Pronta com até (% do ícone escurecido)", self.tela_tol),
                 ("Espera mínima entre teclas (ms)", self.tela_gap),
                 ("Confirmar o cast em até (ms)", self.tela_confirma)]
        for r, (txt, var) in enumerate(itens):
            tk.Label(grade, text=txt, bg=SURFACE, fg=MUTED, font=(FONTE, 9)).grid(
                row=r, column=0, sticky="w", pady=1)
            campo(grade, var, 7).grid(row=r, column=1, padx=(10, 0), pady=1, ipady=1)
        caixa_marcar(cartao2, "Simular foco no jogo (tecla sem roubar o teclado)",
                     self.simular_foco, bg=SURFACE, font=(FONTE, 9, "bold")).pack(
            anchor="w", padx=12, pady=(4, 0))
        caixa_marcar(cartao2, "Não confirmou? Repetir com foco forçado (PUXA o jogo)",
                     self.retry_foco, bg=SURFACE, font=(FONTE, 9)).pack(anchor="w", padx=12)
        caixa_marcar(cartao2, "Modo foco: devolver o foco à outra janela depois",
                     self.devolver_foco, bg=SURFACE, font=(FONTE, 9)).pack(
            anchor="w", padx=12, pady=(0, 8))

        titulo(f, "REGISTRO").pack(anchor="w", padx=12, pady=(2, 2))
        self.lbl_log = tk.Label(f, text="", bg=INPUT_BG, fg=MUTED, font=("Consolas", 8),
                                justify="left", anchor="nw", height=4, wraplength=450,
                                highlightbackground=BORDER, highlightthickness=1)
        self.lbl_log.pack(fill="x", padx=10, pady=(0, 8))

    def _montar_aba_teleporte(self):
        f = self.aba_tp
        k = max(1.0, self.winfo_fpixels("1i") / 96.0)

        # ----- adicionar local -----
        novo = Cartao(f)
        novo.pack(fill="x", padx=10, pady=(10, 6))
        grade = tk.Frame(novo, bg=SURFACE)
        grade.pack(fill="x", padx=12, pady=(10, 4))
        grade.columnconfigure(1, weight=1)
        tk.Label(grade, text="Nome", bg=SURFACE, fg=MUTED, font=(FONTE, 9)).grid(
            row=0, column=0, sticky="w", pady=2)
        campo(grade, self.tp_nome, 20).grid(row=0, column=1, sticky="we", padx=(10, 0), pady=2,
                                            ipady=2)
        tk.Label(grade, text="Mapa ou comando", bg=SURFACE, fg=MUTED, font=(FONTE, 9)).grid(
            row=1, column=0, sticky="w", pady=2)
        e_cmd = campo(grade, self.tp_cmd, 20)
        e_cmd.grid(row=1, column=1, sticky="we", padx=(10, 0), pady=2, ipady=2)
        e_cmd.bind("<Return>", lambda e: self.salvar_teleporte())
        botoes = tk.Frame(novo, bg=SURFACE)
        botoes.pack(fill="x", padx=12, pady=(4, 6))
        botao(botoes, "+ Salvar local", self.salvar_teleporte, altura=30).pack(
            side="left", fill="x", expand=True, padx=(0, 3))
        botao(botoes, "Ir agora (sem salvar)", self.ir_agora, estilo="secundario",
              altura=30).pack(side="left", fill="x", expand=True, padx=(3, 0))
        tk.Label(novo, bg=SURFACE, fg=DIM, font=(FONTE, 8), justify="left", wraplength=430,
                 text="Pode escrever só o mapa (shadowfallwar) ou o comando inteiro "
                      "(/join shadowfallwar-12345). Sem a barra, o programa coloca \"/join\" "
                      "na frente."
                 ).pack(fill="x", padx=12, pady=(0, 8))

        # ----- lista com rolagem -----
        titulo(f, "LOCAIS SALVOS").pack(anchor="w", padx=12, pady=(4, 3))
        caixa = Cartao(f)
        caixa.pack(fill="x", padx=10)
        self.tp_canvas = tk.Canvas(caixa, bg=SURFACE, highlightthickness=0, bd=0,
                                   height=int(4 * 42 * k))
        barra = ttk.Scrollbar(caixa, orient="vertical", command=self.tp_canvas.yview,
                              style="Vermelha.Vertical.TScrollbar")
        self.tp_canvas.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.tp_canvas.pack(side="left", fill="both", expand=True)
        self.tp_lista = tk.Frame(self.tp_canvas, bg=SURFACE)
        janela = self.tp_canvas.create_window(0, 0, window=self.tp_lista, anchor="nw")
        self.tp_lista.bind("<Configure>", lambda e: self.tp_canvas.configure(
            scrollregion=self.tp_canvas.bbox("all")))
        self.tp_canvas.bind("<Configure>", lambda e: self.tp_canvas.itemconfigure(
            janela, width=e.width))

        def rolar(e):
            self.tp_canvas.yview_scroll(int(-e.delta / 120), "units")

        self.tp_canvas.bind("<Enter>", lambda e: self.tp_canvas.bind_all("<MouseWheel>", rolar))
        self.tp_canvas.bind("<Leave>", lambda e: self.tp_canvas.unbind_all("<MouseWheel>"))
        self._desenhar_lista_tp()

        # ----- opções -----
        opc = Cartao(f)
        opc.pack(fill="x", padx=10, pady=(8, 6))
        caixa_marcar(opc, "Desligar o auto-ataque ao teleportar", self.tp_parar, bg=SURFACE,
                     font=(FONTE, 9, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        caixa_marcar(opc, "Enviar em 2º plano (não puxa o jogo; pode falhar)", self.tp_bg,
                     bg=SURFACE, font=(FONTE, 9)).pack(anchor="w", padx=12)
        lp = tk.Frame(opc, bg=SURFACE)
        lp.pack(fill="x", padx=12, pady=(2, 8))
        tk.Label(lp, text="Espera entre ENTER / texto / ENTER (ms)", bg=SURFACE, fg=MUTED,
                 font=(FONTE, 9)).pack(side="left")
        campo(lp, self.tp_passo, 7).pack(side="right", ipady=1)

        self.lbl_tp = tk.Label(f, text="", bg=BG, fg=MUTED, font=(FONTE, 9, "bold"),
                               wraplength=450)
        self.lbl_tp.pack(pady=(0, 8))

    def _desenhar_lista_tp(self):
        for w in self.tp_lista.winfo_children():
            w.destroy()
        if not self.teleportes:
            tk.Label(self.tp_lista, text="Nenhum local salvo ainda.", bg=SURFACE, fg=DIM,
                     font=(FONTE, 9)).pack(pady=14)
            return
        for i, item in enumerate(self.teleportes):
            linha = tk.Frame(self.tp_lista, bg=SURFACE)
            linha.pack(fill="x", padx=10, pady=4)
            botao(linha, "✕", lambda i=i: self.remover_teleporte(i), estilo="perigo",
                  largura=30, altura=28, tam=9).pack(side="right")
            botao(linha, "Ir", lambda it=item: self.teleportar(it["cmd"], it["nome"]),
                  largura=64, altura=28).pack(side="right", padx=(0, 6))
            textos = tk.Frame(linha, bg=SURFACE)
            textos.pack(side="left", fill="x", expand=True)
            tk.Label(textos, text=item["nome"], bg=SURFACE, fg=TEXT, anchor="w",
                     font=(FONTE, 10, "bold")).pack(fill="x")
            tk.Label(textos, text=item["cmd"], bg=SURFACE, fg=MUTED, anchor="w",
                     font=("Consolas", 9)).pack(fill="x")
        self.tp_canvas.yview_moveto(0)

    @staticmethod
    def _comando_de(texto):
        t = " ".join(texto.split())
        if not t:
            return ""
        return t if t.startswith("/") else "/join " + t

    def salvar_teleporte(self):
        cmd = self._comando_de(self.tp_cmd.get())
        if not cmd:
            self.lbl_tp.config(text="Escreva o mapa ou o comando.", fg=RED_HOVER)
            return
        nome = self.tp_nome.get().strip() or cmd.split()[-1]
        for item in self.teleportes:
            if item["nome"].lower() == nome.lower():
                item["cmd"] = cmd  # mesmo nome: só atualiza o comando
                break
        else:
            self.teleportes.append({"nome": nome, "cmd": cmd})
        self.tp_nome.set("")
        self.tp_cmd.set("")
        self._desenhar_lista_tp()
        self._salvar_config()
        self.lbl_tp.config(text=f"\"{nome}\" salvo.", fg=TEXT)

    def remover_teleporte(self, i):
        if not (0 <= i < len(self.teleportes)):
            return
        nome = self.teleportes[i]["nome"]
        if not messagebox.askyesno("AutoAtack AQW", f"Remover \"{nome}\" dos locais salvos?"):
            return
        del self.teleportes[i]
        self._desenhar_lista_tp()
        self._salvar_config()

    def ir_agora(self):
        cmd = self._comando_de(self.tp_cmd.get())
        if not cmd:
            self.lbl_tp.config(text="Escreva o mapa ou o comando.", fg=RED_HOVER)
            return
        self.teleportar(cmd, cmd.split()[-1])

    def teleportar(self, cmd, nome):
        if self.teleportando:
            return
        hwnd = self._exigir_janela()
        if hwnd is None:
            return
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # restaura se estiver minimizado
        if self.ligado and self.tp_parar.get():
            self.alternar()  # desliga o auto-ataque
        opts = {
            "bg": self.tp_bg.get(),
            "simular": self.simular_foco.get(),
            "passo": self._num(self.tp_passo, 150, 50, 2000) / 1000,
            "anterior": user32.GetForegroundWindow(),
        }
        self.teleportando = True  # pausa a rotação (as teclas 1-5 iriam para o chat)
        self.lbl_tp.config(text=f"Indo para {nome}...", fg=RED_HOVER)
        threading.Thread(target=self._executar_teleporte, args=(hwnd, cmd, nome, opts),
                         daemon=True).start()

    def _executar_teleporte(self, hwnd, cmd, nome, o):
        ok = False
        try:
            time.sleep(0.1)  # deixa o último aperto de skill terminar
            with self._lock_teclas:
                if o["bg"]:
                    ok = digitar_chat_background(self._alvo_input(hwnd), hwnd, cmd, o["passo"],
                                                 simular_foco=o["simular"])
                else:
                    ok = digitar_chat_foco(hwnd, cmd, o["passo"], devolver_para=o["anterior"])
        except Exception:
            ok = False
        finally:
            self._tp_fim = time.monotonic()
            self.teleportando = False
        if ok:
            self._tp_msg = (f"Enviado: {cmd}", TEXT)
            self._log(f"Teleporte: {cmd}")
        else:
            self._tp_msg = ("Não consegui trazer o jogo para a frente. Tente de novo.", RED_HOVER)

    def _desenhar_tabela_cura(self):
        for w in self.tabela_cura.winfo_children():
            w.destroy()
        self.tabela_cura.columnconfigure(0, weight=1)
        for r, p in enumerate(self.perfis):
            tk.Label(self.tabela_cura, textvariable=p.nome, bg=SURFACE, fg=TEXT, anchor="w",
                     font=(FONTE, 10, "bold")).grid(row=r, column=0, padx=10, pady=4, sticky="we")
            ttk.Combobox(self.tabela_cura, textvariable=p.cura_skill, state="readonly",
                         values=[NENHUMA, "1", "2", "3", "4", "5"], width=9).grid(
                row=r, column=1, padx=10, pady=4)

    # ---------- abas / perfis ----------
    def adicionar_perfil(self, dados, selecionar=True):
        if dados is None:
            dados = padrao_perfil(len(self.perfis) + 1)
        frame = PerfilFrame(self, dados)
        pos = self.notebook.index(self.aba_cura)
        self.notebook.insert(pos, frame, text=frame.nome.get() or "Sem nome")
        self.perfis.append(frame)
        self._desenhar_tabela_cura()
        if selecionar:
            self.notebook.select(frame)

    def excluir_perfil(self, frame):
        if len(self.perfis) <= 1:
            messagebox.showinfo("AutoAtack AQW", "Precisa existir pelo menos uma aba de classe.")
            return
        if not messagebox.askyesno("AutoAtack AQW",
                                   f"Excluir a aba \"{frame.nome.get()}\"?"):
            return
        self.perfis.remove(frame)
        self.notebook.forget(frame)
        frame.destroy()
        if self.perfil_ativo is frame or self.perfil_ativo not in self.perfis:
            self.perfil_ativo = self.perfis[0]
            self.notebook.select(self.perfil_ativo)
            self._carregar_preset()
        self._desenhar_tabela_cura()

    def _clique_aba(self, e):
        """Toca o som quando o clique cai em cima de uma aba (e não no conteúdo)."""
        try:
            self.notebook.index(f"@{e.x},{e.y}")
        except tk.TclError:
            return
        SOM.clique()

    def atualizar_titulo_aba(self, frame):
        try:
            self.notebook.tab(frame, text=frame.nome.get() or "Sem nome")
        except tk.TclError:
            pass

    def _ao_trocar_aba(self, _event=None):
        try:
            atual = self.nametowidget(self.notebook.select())
        except Exception:
            return
        if isinstance(atual, PerfilFrame) and atual is not self.perfil_ativo:
            self.perfil_ativo = atual
            self._carregar_preset()

    # ---------- janelas ----------
    def atualizar_janelas(self):
        atual = self.combo.get()
        self.janelas = listar_janelas()
        titulos = [t[:70] for t, _ in self.janelas]
        self.combo["values"] = titulos
        if atual in titulos:
            self.combo.set(atual)
        else:
            ruins = ("visual studio", "explorador", "explorer", "claude", "opera", "chrome",
                     "edge", "firefox", "notepad", "bloco de notas")
            melhor = None
            for i, t in enumerate(titulos):
                tl = t.lower()
                if tl.startswith("aqw") or tl.startswith("adventurequest"):
                    melhor = i
                    break
                if melhor is None and ("aqw" in tl or "adventurequest" in tl) \
                        and not any(r in tl for r in ruins):
                    melhor = i
            if melhor is not None:
                self.combo.current(melhor)

    def _hwnd_alvo(self):
        idx = self.cfg.get("janela_idx", -1)
        if idx < 0 or idx >= len(self.janelas):
            return None
        hwnd = self.janelas[idx][1]
        return hwnd if user32.IsWindow(hwnd) else None

    # ---------- calibragens por clique (F8 = reserva) ----------
    def _ligar_gancho(self, hwnd):
        app = user32.GetAncestor(self.winfo_id(), 2)  # GA_ROOT: a janela do AutoAtack
        if not self.gancho.ligar(hwnd, app):
            self._log("Não consegui capturar cliques; use o F8 com o mouse em cima do ponto")
        self._esc_pressionada = True

    def _cancelar_calib(self):
        self.calib_etapa = 0
        self.calib_modo = None
        self.calib_pontos = []
        self.btn_barra.config(text="Selecionar barra de vida")
        self.btn_alvo.config(text="Selecionar barra do alvo")
        self.btn_icones.config(text="Calibrar ícones desta classe (5 cliques)")
        self.gancho.desligar()
        self._atualizar_label_barra()
        self._atualizar_label_icones()

    def selecionar_alvo(self):
        if self.calib_etapa != 0:
            self._cancelar_calib()
            return
        if self._exigir_janela() is None:
            return
        self.calib_modo = "alvo"
        self.calib_etapa = 1
        self.calib_pontos = []
        self._f8_pressionada = True
        self._ligar_gancho(self._hwnd_alvo())
        self.btn_alvo.config(text="Cancelar")
        self.lbl_barra.config(
            text="ALVO 1/2: selecione um mob no jogo (o painel dele aparece no topo) e CLIQUE no "
                 "INÍCIO (esquerda) da barra VERMELHA dele. Botão direito ou Esc cancela.",
            fg=RED_HOVER)

    def selecionar_barra(self):
        if self.calib_etapa != 0:  # clicar de novo cancela
            self._cancelar_calib()
            return
        if self._exigir_janela() is None:
            return
        self.regiao_vida = None
        self.hp_atual = None
        self.calib_modo = "barra"
        self.calib_etapa = 1
        self.calib_pontos = []
        self._f8_pressionada = True  # ignora F8 já apertada
        self._ligar_gancho(self._hwnd_alvo())
        self.btn_barra.config(text="Cancelar seleção")
        self.lbl_barra.config(
            text="PASSO 1/2: CLIQUE no INÍCIO (esquerda) da barra vermelha, na altura do meio "
                 "dela. (O clique não chega ao jogo. Botão direito ou Esc cancela.)",
            fg=RED_HOVER)

    def calibrar_icones(self):
        if self.calib_etapa != 0:
            self._cancelar_calib()
            return
        if self._exigir_janela() is None:
            return
        self.calib_modo = "icones"
        self.calib_etapa = 1
        self.calib_pontos = []
        self._f8_pressionada = True
        self._ligar_gancho(self._hwnd_alvo())
        self.btn_icones.config(text="Cancelar calibragem")
        self.lbl_icones.config(
            text="PASSO 1/5: com o jogo VISÍVEL e as skills PRONTAS, CLIQUE no CENTRO do ícone "
                 "da SKILL 1. (O clique não usa a skill. Botão direito ou Esc cancela.)",
            fg=RED_HOVER)

    # ---------- preset de cada classe ----------
    @staticmethod
    def _regs_de(centros):
        return [(x - ICONE_RAIO, y - ICONE_RAIO, x + ICONE_RAIO, y + ICONE_RAIO)
                for x, y in centros]

    def _carregar_preset(self):
        """Usa a calibragem salva na classe ativa (ou nenhuma)."""
        p = self.perfil_ativo
        pre = None
        if p is not None and p.precisao:
            try:
                pre = {"regs": self._regs_de(p.precisao["centros"]),
                       "base": [base64.b64decode(b) for b in p.precisao["base"]],
                       "janela": tuple(p.precisao["janela"])}
            except Exception:
                pre = None
        self.preset_atual = pre
        self.icones = pre["regs"] if pre else None
        self.icones_base = pre["base"] if pre else None
        self._tamanho_errado = False
        self._atualizar_label_icones()

    def _gravar_preset(self, centros, bases):
        """Salva a calibragem na classe ativa e já passa a usá-la."""
        p = self.perfil_ativo
        if p is None:
            return
        p.precisao = {"centros": [list(c) for c in centros],
                      "janela": [self.captura.w, self.captura.h],
                      "base": [base64.b64encode(b).decode("ascii") for b in bases]}
        self._carregar_preset()
        self._salvar_config()

    def _ler_bases(self, centros):
        self._atualizar_captura()
        bases = [cinza_regiao(r, self.captura) for r in self._regs_de(centros)]
        if any(b is None or sum(b) / len(b) < 12 for b in bases):
            return None
        return bases

    def rebase_icones(self):
        """Registra a aparência de agora como PRONTA (usa as posições já marcadas)."""
        if self._exigir_janela() is None:
            return
        p = self.perfil_ativo
        centros = p.precisao["centros"] if (p and p.precisao) else None
        if centros is None:  # classe sem calibragem: pega as posições de outra classe
            for outro in self.perfis:
                if outro.precisao:
                    centros = outro.precisao["centros"]
                    break
        if centros is None:
            messagebox.showinfo("AutoAtack AQW", "Calibre os ícones (5 cliques) uma primeira vez.")
            return
        bases = self._ler_bases(centros)
        if bases is None:
            messagebox.showinfo("AutoAtack AQW",
                                "Não consegui ler os ícones (janela minimizada ou tamanho mudou?).")
            return
        self._gravar_preset(centros, bases)
        self._log(f"Ícones de \"{p.nome.get()}\" registrados como PRONTOS")
        SOM.confirmar()

    def apagar_preset(self):
        p = self.perfil_ativo
        if not p or not p.precisao:
            return
        if not messagebox.askyesno("AutoAtack AQW",
                                   f"Apagar a calibragem dos ícones de \"{p.nome.get()}\"?"):
            return
        p.precisao = None
        self._carregar_preset()
        self._salvar_config()

    def _processar_f8(self, pos=None):
        """Marca um ponto da calibragem. pos = onde foi o clique (ou o mouse, no F8)."""
        pos = pos or posicao_mouse()
        SOM.clique()
        hwnd = self._hwnd_alvo()
        if hwnd is None:
            self._cancelar_calib()
            return
        # guarda tudo RELATIVO à janela do jogo (assim ela pode ser movida/coberta)
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        pos = (pos[0] - r.l, pos[1] - r.t)

        if self.calib_modo in ("barra", "alvo"):
            alvo = self.calib_modo == "alvo"
            if self.calib_etapa == 1:
                self.calib_pontos = [pos]
                self.calib_etapa = 2
                self.lbl_barra.config(
                    text=("ALVO 2/2: agora CLIQUE no FIM (direita) da barra vermelha do alvo."
                          if alvo else "PASSO 2/2: agora CLIQUE no FIM (direita) da barra."),
                    fg=RED_HOVER)
                return
            p1, p2 = self.calib_pontos[0], pos
            x1, x2 = sorted((p1[0], p2[0]))
            y = (p1[1] + p2[1]) // 2
            self._cancelar_calib()
            if x2 - x1 < 20:
                self.lbl_barra.config(text="Seleção muito pequena. Tente de novo.", fg=RED_HOVER)
                return
            if alvo:
                self.regiao_alvo = (x1, y - 3, x2, y + 3)
                self._atualizar_captura()
                self.alvo_janela = (self.captura.w, self.captura.h)
                self._salvar_config()
                if alvo_na_tela(self.regiao_alvo, self.captura, 100):
                    self.lbl_barra.config(text="Barra do alvo marcada e salva.", fg=TEXT)
                else:
                    self.lbl_barra.config(
                        text="Barra marcada, mas não reconheci o painel do alvo agora. Confira se "
                             "havia um mob selecionado e use a imagem de teste.", fg=RED_HOVER)
            else:
                self.regiao_vida = (x1, y - 3, x2, y + 3)
                self._atualizar_label_barra()
            SOM.confirmar()  # barra configurada
            return

        if self.calib_modo == "icones":
            self.calib_pontos.append(pos)
            n = len(self.calib_pontos)
            if n < 5:
                self.calib_etapa = n + 1
                self.lbl_icones.config(
                    text=f"PASSO {n + 1}/5: CLIQUE no CENTRO do ícone da SKILL {n + 1}.",
                    fg=RED_HOVER)
                return
            centros = list(self.calib_pontos)
            bases = self._ler_bases(centros)
            self._cancelar_calib()
            if bases is None:
                self.lbl_icones.config(
                    text="Não consegui ler os ícones (muito escuros ou jogo minimizado). "
                         "Tente de novo.", fg=RED_HOVER)
                return
            self._gravar_preset(centros, bases)
            self._log(f"Ícones de \"{self.perfil_ativo.nome.get()}\" calibrados e salvos")
            SOM.confirmar()

    def _atualizar_label_barra(self):
        if self.regiao_vida:
            x1, y1, x2, y2 = self.regiao_vida
            self.lbl_barra.config(
                text=f"Barra definida  •  {x2 - x1 + 1} px de largura", fg=TEXT)
        else:
            self.lbl_barra.config(
                text="Barra NÃO definida (precisa selecionar toda vez que abrir)",
                fg=RED_HOVER)

    def _atualizar_label_icones(self):
        if self.preset_atual:
            self.lbl_icones.config(text="Calibragem salva nesta classe (5 ícones). Trocou de "
                                        "classe no jogo? É só trocar a aba aqui.", fg=TEXT)
        else:
            self.lbl_icones.config(
                text="Esta classe ainda NÃO tem calibragem. Calibre com o jogo visível e as skills "
                     "prontas (fica salvo). Sem isso o programa usa só os tempos.", fg=RED_HOVER)

    # ---------- captura da janela ----------
    def _exigir_janela(self):
        hwnd = self._hwnd_alvo()
        if hwnd is None:
            messagebox.showinfo("AutoAtack AQW", "Escolha primeiro a janela do jogo em "
                                                 "\"JANELA ALVO\" (ex.: AQWBR).")
        return hwnd

    def _atualizar_captura(self, min_intervalo=0.0):
        hwnd = self._hwnd_alvo()
        if hwnd is None:
            return False
        return self.captura.atualizar(hwnd, min_intervalo)

    def salvar_imagem_teste(self):
        """Salva o que o programa enxerga, com as regiões calibradas em vermelho."""
        if self._exigir_janela() is None:
            return
        if not self._atualizar_captura():
            messagebox.showinfo("AutoAtack AQW", "Não consegui capturar a janela (minimizada?).")
            return
        quadro = self.captura.quadro_completo()
        if not quadro:
            return
        w, h, dados = quadro
        regs = list(self.icones or [])
        if self.regiao_vida:
            regs.append(self.regiao_vida)
        if self.regiao_alvo:
            regs.append(self.regiao_alvo)
        caminho = os.path.join(PASTA_DADOS, "captura_teste.bmp")
        try:
            salvar_bmp(caminho, w, h, dados, regs)
            self._log("Imagem salva: captura_teste.bmp")
            messagebox.showinfo("AutoAtack AQW",
                                f"Salvei {caminho}\nAbra e confira se os retângulos vermelhos "
                                "estão em cima dos ícones das skills e da barra de vida.")
        except Exception as e:
            messagebox.showinfo("AutoAtack AQW", f"Não consegui salvar: {e}")

    # ---------- leitura dos ícones ----------
    def _ler_icones(self, indices):
        """{idx: fração escurecida do ícone}. ~0 = pronta, alta = em recarga."""
        pre = self.preset_atual
        res = {}
        if not pre or not self.captura.valida:
            return res
        if (self.captura.w, self.captura.h) != pre["janela"]:
            self._tamanho_errado = True  # posições/imagens não valem mais
            return res
        self._tamanho_errado = False
        for idx in indices:
            g = cinza_regiao(pre["regs"][idx], self.captura)
            if g is not None and len(g) == len(pre["base"][idx]):
                res[idx] = fracao_escura(g, pre["base"][idx])
        return res

    def _ler_alvo(self, minimo):
        """True/False = alvo sim/não. None = sem como ler (aí o motor ataca como antes)."""
        if not self.regiao_alvo or not self.captura.valida:
            return None
        if self.alvo_janela and (self.captura.w, self.captura.h) != self.alvo_janela:
            return None
        return alvo_na_tela(self.regiao_alvo, self.captura, minimo)

    def _log(self, texto):
        self.log.append(f"{time.strftime('%H:%M:%S')}  {texto}")

    # ---------- configurações que a thread lê ----------
    @staticmethod
    def _num(var, padrao, minimo, maximo):
        try:
            v = float(var.get().replace(",", "."))
        except ValueError:
            return padrao
        return max(minimo, min(maximo, v))

    def _atualizar_cfg(self):
        p = self.perfil_ativo
        if p is None:
            return
        cura_idx = p.indice_cura()
        ordem = []
        for idx in p.ordem:
            if not p.ativa[idx].get():
                continue
            if cura_idx is not None and idx == cura_idx:
                continue  # skill de cura não entra na rotação
            ordem.append({"idx": idx,
                          "cd": self._num(p.cd[idx], 0, 0, 3600),
                          "espera": p.espera[idx].get()})
        self.cfg = {
            "janela_idx": self.combo.current(),
            "foco": self.foco_var.get(),
            "perfil_id": id(p),
            "perfil_nome": p.nome.get(),
            "intervalo": self._num(p.intervalo, 500, 500, 60000) / 1000,
            "ordem": ordem,
            "cura_skill": cura_idx,
            "cura_ativa": self.cura_ativa.get(),
            "cura_pct": self._num(self.cura_pct, 50, 1, 99),
            "cura_retry": self._num(self.cura_retry, 600, 100, 60000) / 1000,
            "cura_min": int(self._num(self.cura_min, 100, 30, 255)),
            "so_alvo": self.so_alvo.get(),
            "alvo_procura": self._num(self.alvo_procura, 2, 0, 60),
            "alvo_tecla": int(self.alvo_tecla.get() or 1) - 1,
            "tela_ativa": self.tela_ativa.get(),
            "tol": self._num(self.tela_tol, 3, 1, 40) / 100,
            "gap_tela": self._num(self.tela_gap, 120, 30, 5000) / 1000,
            "confirma": self._num(self.tela_confirma, 600, 150, 3000) / 1000,
            "retry_foco": self.retry_foco.get(),
            "simular_foco": self.simular_foco.get(),
            "devolver_foco": self.devolver_foco.get(),
        }

    def _tick(self):
        """Thread principal: atualiza configs e os textos da tela."""
        self._atualizar_cfg()
        c = self.cfg
        if not self.ligado and (self.regiao_vida or self.preset_atual):
            self._atualizar_captura()  # com o programa ligado, quem atualiza é o motor
        if c and self.regiao_vida and self.calib_etapa == 0:
            self.hp_atual = ler_vida_percent(self.regiao_vida, c["cura_min"], self.captura)
        else:
            self.hp_atual = None

        if self.hp_atual is None:
            self.lbl_hp.config(text="Vida lida: --", fg=MUTED)
        else:
            baixa = self.hp_atual <= c["cura_pct"]
            self.lbl_hp.config(text=f"Vida lida: {self.hp_atual:.0f}%",
                               fg=RED_HOVER if baixa else TEXT)

        # ícones ao vivo (serve para conferir se a calibragem está boa)
        if self.preset_atual and self.calib_etapa == 0:
            tol = c.get("tol", 0.03)
            leit = self._ler_icones(range(5))
            if self._tamanho_errado:
                self.lbl_live.config(text="Tamanho da janela do jogo mudou: recalibre", fg=RED_HOVER)
            else:
                partes = []
                for i in range(5):
                    if i in leit:
                        partes.append(f"{i + 1}:{'OK' if leit[i] <= tol else 'CD'} "
                                      f"{(1 - leit[i]) * 100:3.0f}%")
                    else:
                        partes.append(f"{i + 1}: --")
                self.lbl_live.config(text="  ".join(partes), fg=TEXT)
        else:
            self.lbl_live.config(text="Ícones: --", fg=TEXT)
        if self.perfil_ativo is not None:
            txt = (f"Classe: {self.perfil_ativo.nome.get()}  •  "
                   + ("calibragem salva" if self.preset_atual else "sem calibragem"))
            if txt != self._lbl_preset_txt:
                self._lbl_preset_txt = txt
                self.lbl_preset.config(text=txt, fg=TEXT if self.preset_atual else RED_HOVER)
        self.lbl_log.config(text="\n".join(list(self.log)[-4:]))

        self._processar_atualizacao()
        if self._tp_msg:
            texto_tp, cor_tp = self._tp_msg
            self._tp_msg = None
            self.lbl_tp.config(text=texto_tp, fg=cor_tp)
        if self.calib_etapa == 0 and c:
            if not self.regiao_alvo:
                self.lbl_alvo.config(text="Alvo: não marcado", fg=MUTED)
            else:
                if not self.ligado:
                    self.alvo_agora = self._ler_alvo(c["cura_min"])
                if self.alvo_agora is None:
                    self.lbl_alvo.config(text="Alvo: sem leitura", fg=MUTED)
                elif self.alvo_agora:
                    self.lbl_alvo.config(text="Alvo: DETECTADO", fg=RED_HOVER)
                else:
                    self.lbl_alvo.config(text="Alvo: nenhum", fg=TEXT)
        if self.teleportando:
            self.lbl_status.config(text="● TELEPORTANDO...", fg=RED_HOVER)
        elif self.ligado and c:
            texto = ("● CURANDO!" if self.precisa_curar
                     else "● AGUARDANDO ALVO" if self.sem_alvo else "● LIGADO")
            texto += f"  •  {c['perfil_nome']}"
            if self.ultima_skill:
                texto += f"  •  última skill: {self.ultima_skill}"
            if c["cura_ativa"] and c["cura_skill"] is not None:
                texto += f"  •  curas: {self.curas_usadas}"
            if c["tela_ativa"] and self.preset_atual:
                texto += (f"  •  casts ok: {self.confirmados} / recusados: {self.falhas_cast}"
                          f"  •  captura {self.captura.ultimo_ms:.0f} ms")
                if self.gap_extra_ms:
                    texto += f"  •  espera aprendida +{self.gap_extra_ms} ms"
            self.lbl_status.config(text=texto, fg=RED_HOVER)
        else:
            self.lbl_status.config(text="● DESLIGADO", fg=MUTED)

        # salva sozinho de tempos em tempos
        self._contador_tick += 1
        if self._contador_tick % 20 == 0:
            self._salvar_config()
        self.after(150, self._tick)

    # ---------- teclas globais ----------
    def vincular_tecla(self):
        self.capturando_tecla = True
        self.lbl_hotkey.config(text="Aperte...", fg=RED)
        self.btn_vincular.config(text="Aguardando...")
        self.focus_force()

    def _tecla_capturada(self, event):
        if not self.capturando_tecla:
            return
        self.capturando_tecla = False
        self.hotkey_vk = event.keycode  # no Windows, keycode = código VK
        self.hotkey_nome = event.keysym.upper()
        self.lbl_hotkey.config(text=self.hotkey_nome, fg=TEXT)
        self.btn_vincular.config(text="Vincular tecla")
        self._hotkey_pressionada = True
        self._salvar_config()

    def _checar_teclas(self):
        # durante a calibragem: cliques no jogo (F8 como reserva, Esc cancela)
        if self.calib_etapa != 0:
            while self.gancho.cliques and self.calib_etapa != 0:
                botao_mouse, x, y = self.gancho.cliques.popleft()
                if botao_mouse == "dir":
                    self._cancelar_calib()
                else:
                    self._processar_f8((x, y))
            esc = bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)
            if esc and not self._esc_pressionada and self.calib_etapa != 0:
                self._cancelar_calib()
            self._esc_pressionada = esc
            f8 = bool(user32.GetAsyncKeyState(VK_F8) & 0x8000)
            if f8 and not self._f8_pressionada and self.calib_etapa != 0:
                self._processar_f8()
            self._f8_pressionada = f8
        elif not self.capturando_tecla:
            apertada = bool(user32.GetAsyncKeyState(self.hotkey_vk) & 0x8000)
            if apertada and not self._hotkey_pressionada:
                self.alternar()
            self._hotkey_pressionada = apertada
        self.after(30, self._checar_teclas)

    # ---------- liga / desliga ----------
    def alternar(self):
        self.ligado = not self.ligado
        if self.ligado:
            self._salvar_config()
            self._atualizar_cfg()
            self.curas_usadas = 0
            self.confirmados = 0
            self.falhas_cast = 0
            self.ultima_skill = None
            self.precisa_curar = False
            self.log.clear()
            c0 = self.cfg
            if c0:
                self._log("Rotação: " + " > ".join(str(x["idx"] + 1) for x in c0["ordem"]))
                if c0["tela_ativa"] and self.preset_atual:
                    self._log("Leitura de tela: ligada (calibragem desta classe)")
                else:
                    self._log("Leitura de tela: desligada/sem calibragem -> usando os tempos")
                p0 = self.perfil_ativo
                if c0["cura_skill"] is not None and p0 and p0.ativa[c0["cura_skill"]].get():
                    self._log(f"Skill {c0['cura_skill'] + 1} é a CURA desta classe: fora da rotação")
            self.btn_toggle.config(text="DESLIGAR", estilo="ligado")
            self._geracao += 1
            self.gap_extra_ms = 0
            self.thread = threading.Thread(target=self._loop, args=(self._geracao,), daemon=True)
            self.thread.start()
        else:
            self.precisa_curar = False
            self.btn_toggle.config(text="LIGAR", estilo="primario")

    def _alvo_input(self, hwnd):
        """Janela que realmente recebe o teclado (no Chrome/Edge é uma janela filha)."""
        agora = time.monotonic()
        item = self._cache_input.get(hwnd)
        if item and agora - item[1] < 5 and user32.IsWindow(item[0]):
            return item[0]
        alvo = achar_janela_input(hwnd)
        self._cache_input[hwnd] = (alvo, agora)
        return alvo

    def _pressionar(self, hwnd, indice, forcar_foco=False):
        vk = 0x31 + indice  # '1'..'5'
        with self._lock_teclas:
            if self.cfg.get("foco") or forcar_foco:
                enviar_tecla_foco(hwnd, vk, self.cfg.get("devolver_foco", False))
            else:
                enviar_tecla_background(self._alvo_input(hwnd), vk,
                                        self.cfg.get("simular_foco", True), hwnd)

    # ---------- motor ----------
    def _skill_pronta(self, s, agora, leitura, tol, proxima_vez, espera_ate):
        idx = s["idx"]
        if espera_ate.get(idx, 0) > agora:  # o jogo acabou de recusar: dá um respiro
            return False
        if idx in leitura:
            return leitura[idx] <= tol
        return agora >= proxima_vez.get(idx, agora)

    def _loop(self, geracao):
        """
        ROTAÇÃO ÚNICA (combo + ninguém fica sem vez):
          - Pronta = ícone sem escurecido (leitura de tela) ou recarga em segundos (sem leitura).
          - Entre as prontas, vai a que está pronta HÁ MAIS TEMPO (contado em "vezes que ficou
            pronta e outra foi usada"). Empate = ordem da lista. Com tudo pronto, o combo sai na
            ordem (4 > 2 > 3 > 5) e, depois, nenhuma skill passa mais de uma rodada esperando.
          - Depois de apertar, confere se o ícone escureceu (= o jogo aceitou). Se o jogo recusou
            (ex.: recarga global), a skill espera um pouco e o programa aumenta sozinho a espera
            mínima entre teclas. Nada fica "bloqueado" por muito tempo.
          - Cura tem prioridade sobre tudo.
        """
        pid = None
        proxima_vez = {}   # sem leitura: quando cada skill volta (estimado pelos segundos)
        espera_ate = {}    # skill -> não tentar antes disso (o jogo recusou)
        passou = {}        # skill -> quantas vezes ficou pronta e outra foi usada
        falhas = {}        # recusas seguidas por skill
        pend = None        # {"idx", "t"}: apertada, esperando o ícone escurecer
        prox_acao = 0.0
        ultima_cura = -1e9
        ultima_leitura = 0.0
        ultimo_ok = -1e9
        ultimo_uso = time.monotonic()
        gap_extra = 0.0
        hp = None
        aviso_captura = aviso_tamanho = aviso_parado = False
        ultima_procura = -1e9
        tinha_alvo = True
        aviso_alvo = False

        while self.ligado and self._geracao == geracao:
            # teleporte em andamento (ou acabou agora): não aperta nada
            if self.teleportando or time.monotonic() - self._tp_fim < 0.5:
                pend = None
                time.sleep(0.05)
                continue
            c = self.cfg
            hwnd = self._hwnd_alvo()
            if not c or hwnd is None:
                time.sleep(0.3)
                continue
            agora = time.monotonic()
            ordem = c["ordem"]

            # trocou de aba/classe: zera tudo
            if c["perfil_id"] != pid:
                pid = c["perfil_id"]
                proxima_vez = {s["idx"]: (agora + s["cd"] if (s["espera"] and s["cd"] > 0) else agora)
                               for s in ordem}
                espera_ate, passou, falhas = {}, {}, {}
                pend = None
                prox_acao = agora
                ultimo_uso = agora
                gap_extra = 0.0
                aviso_parado = False
            for s in ordem:
                proxima_vez.setdefault(s["idx"], agora)

            # ---------- captura da janela do jogo ----------
            quer_tela = bool(c["tela_ativa"] and self.preset_atual)
            if quer_tela or (c["cura_ativa"] and self.regiao_vida):
                if self._atualizar_captura(0.02):
                    aviso_captura = False
                elif not aviso_captura:
                    aviso_captura = True
                    self._log("Sem captura (janela minimizada?): usando só os tempos")

            idxs = [s["idx"] for s in ordem]
            if c["cura_skill"] is not None:
                idxs.append(c["cura_skill"])
            leitura = self._ler_icones(idxs) if quer_tela else {}
            if quer_tela and self._tamanho_errado and not aviso_tamanho:
                aviso_tamanho = True
                self._log("A janela do jogo mudou de tamanho: recalibre (usando só os tempos)")
            usar_tela = bool(leitura)
            tol = c["tol"]
            tol_cd = max(0.15, tol * 2.5)  # "escureceu de verdade" para confirmar o cast

            # ---------- confirmação do último aperto ----------
            if pend is not None:
                i = pend["idx"]
                if i not in leitura:
                    pend = None
                elif leitura[i] >= tol_cd:  # escureceu: o jogo aceitou
                    self.confirmados += 1
                    falhas[i] = 0
                    ultimo_ok = agora
                    gap_extra = max(0.0, gap_extra - 0.01)
                    self.gap_extra_ms = int(gap_extra * 1000)
                    pend = None
                elif agora - pend["t"] > c["confirma"]:  # não escureceu: recusado
                    falhas[i] = falhas.get(i, 0) + 1
                    self.falhas_cast += 1
                    if agora - ultimo_ok < 2.0:  # logo depois de outra skill: recarga global
                        gap_extra = min(1.5, gap_extra + 0.05)
                        self.gap_extra_ms = int(gap_extra * 1000)
                    espera_ate[i] = agora + min(0.25 * falhas[i], 1.0)
                    if falhas[i] == 4:
                        self._log(f"Skill {i + 1} recusada 4x seguidas: confira o ícone dela "
                                  "(imagem de teste) ou use 'Ícones de agora = PRONTOS'")
                    pend = None
                else:
                    time.sleep(0.01)
                    continue

            # ---------- cura (prioridade máxima) ----------
            regiao = self.regiao_vida
            cura_valida = bool(c["cura_ativa"] and regiao and c["cura_skill"] is not None)
            if cura_valida:
                if agora - ultima_leitura >= 0.08:
                    hp = ler_vida_percent(regiao, c["cura_min"], self.captura)
                    ultima_leitura = agora
            else:
                hp = None
            if cura_valida and hp is not None and 0 < hp <= c["cura_pct"]:
                self.precisa_curar = True
                ci = c["cura_skill"]
                if espera_ate.get(ci, 0) > agora:
                    cura_pronta = False
                elif ci in leitura:
                    cura_pronta = leitura[ci] <= tol
                else:
                    cura_pronta = agora - ultima_cura >= c["cura_retry"]
                if cura_pronta and agora >= prox_acao:
                    forcar = bool(c["retry_foco"] and falhas.get(ci, 0) >= 1)
                    self._pressionar(hwnd, ci, forcar)
                    ultima_cura = ultimo_uso = time.monotonic()
                    self.curas_usadas += 1
                    self.ultima_skill = ci + 1
                    if ci in leitura:
                        pend = {"idx": ci, "t": ultima_cura}
                    prox_acao = ultima_cura + (c["gap_tela"] + gap_extra if usar_tela else 0.25)
                    continue
            else:
                self.precisa_curar = False

            # ---------- só atacar com alvo ----------
            if c["so_alvo"] and self.regiao_alvo:
                if not (quer_tela or (c["cura_ativa"] and self.regiao_vida)):
                    self._atualizar_captura(0.02)
                tem_alvo = self._ler_alvo(c["cura_min"])
                self.alvo_agora = tem_alvo
                if tem_alvo is None:
                    if not aviso_alvo:
                        aviso_alvo = True
                        self._log("Não consigo ver o painel do alvo (janela minimizada ou mudou "
                                  "de tamanho): atacando normalmente")
                    tem_alvo = True
                else:
                    aviso_alvo = False
                if not tem_alvo:
                    if tinha_alvo:
                        self._log("Sem alvo: rotação pausada")
                    tinha_alvo = False
                    self.sem_alvo = True
                    # de tempos em tempos aperta uma tecla para o jogo pegar o mob mais próximo
                    if (c["alvo_procura"] > 0 and agora >= prox_acao and pend is None
                            and agora - ultima_procura >= c["alvo_procura"]):
                        self._pressionar(hwnd, c["alvo_tecla"])
                        ultima_procura = time.monotonic()
                        prox_acao = ultima_procura + 0.3
                    time.sleep(0.03)
                    continue
                if not tinha_alvo:
                    self._log("Alvo encontrado: combo do começo")
                    passou = {}  # o combo recomeça na ordem da lista
                tinha_alvo = True
            self.sem_alvo = False

            # ---------- rotação ----------
            if agora >= prox_acao and pend is None and ordem:
                prontas = [s for s in ordem
                           if self._skill_pronta(s, agora, leitura, tol, proxima_vez, espera_ate)]
                for s in ordem:
                    if s not in prontas:
                        passou[s["idx"]] = 0
                if prontas:
                    # a que espera há mais tempo; empate -> a primeira na ordem da lista
                    escolhida = max(prontas, key=lambda s: passou.get(s["idx"], 0))
                    idx = escolhida["idx"]
                    for s in prontas:
                        if s is not escolhida:
                            passou[s["idx"]] = passou.get(s["idx"], 0) + 1
                    passou[idx] = 0
                    forcar = bool(c["retry_foco"] and falhas.get(idx, 0) >= 1)
                    self._pressionar(hwnd, idx, forcar)
                    t = time.monotonic()
                    self.ultima_skill = idx + 1
                    ultimo_uso = t
                    aviso_parado = False
                    if idx in leitura:
                        pend = {"idx": idx, "t": t}
                    proxima_vez[idx] = t + escolhida["cd"]
                    prox_acao = t + (c["gap_tela"] + gap_extra if usar_tela
                                     else max(0.5, c["intervalo"]))
                elif usar_tela and agora - ultimo_uso > 10 and not aviso_parado:
                    aviso_parado = True
                    self._log("Nenhuma skill parece pronta há 10 s: confira a calibragem "
                              "desta classe (painel de ícones / imagem de teste)")

            time.sleep(0.015)

        self.precisa_curar = False
        self.sem_alvo = False

    # ---------- atualizações ----------
    def _checar_atualizacao(self, manual=False):
        if not atualizador.disponivel():
            if manual:
                messagebox.showinfo(APP_NOME, "A atualização automática só funciona no app "
                                              "instalado (não rodando direto do código).")
            return
        if self._upd_estado:
            return
        self._upd_estado = "buscando"

        def tarefa():
            try:
                self._upd_resultado = ("info", atualizador.buscar(), manual)
            except Exception as e:
                self._upd_resultado = ("erro", str(e), manual)

        threading.Thread(target=tarefa, daemon=True).start()

    def _processar_atualizacao(self):
        """Chamado no _tick (thread principal): mostra perguntas e progresso."""
        if self._upd_estado == "baixando":
            pct = f" {self._upd_pct}%" if self._upd_pct is not None else ""
            self.lbl_versao.config(text=f"Baixando atualização...{pct}", fg=RED_HOVER)
        r = self._upd_resultado
        if not r:
            return
        self._upd_resultado = None
        tipo, dado, manual = r
        rotulo = f"v{versao_curta()}  •  verificar atualizações"

        if tipo == "erro":
            self._upd_estado = None
            if manual:
                messagebox.showinfo(APP_NOME, "Não consegui verificar atualizações agora. "
                                              f"Confira a internet.\n\n({dado})")
            return
        if tipo == "falha":
            self._upd_estado = None
            self.lbl_versao.config(text=rotulo, fg=DIM)
            messagebox.showinfo(APP_NOME, f"A atualização não foi baixada.\n\n({dado})")
            return
        if tipo == "baixado":
            try:
                atualizador.instalar(dado)
            except Exception as e:
                self._upd_estado = None
                self.lbl_versao.config(text=rotulo, fg=DIM)
                messagebox.showinfo(APP_NOME, f"Não consegui abrir o instalador.\n\n({e})")
                return
            self._fechar()  # o instalador troca os arquivos e abre o app de novo
            return

        info = dado
        if info is None:
            self._upd_estado = None
            if manual:
                messagebox.showinfo(APP_NOME, f"Você já está na versão mais nova "
                                              f"(v{versao_curta()}).")
            return
        notas = str(info.get("notas") or "").strip()
        texto = f"Nova versão disponível: v{versao_curta(info['versao'])}\n\n"
        if notas:
            texto += f"Novidades:\n{notas[:700]}\n\n"
        texto += "Atualizar agora? O app fecha, atualiza e abre de novo sozinho."
        if not messagebox.askyesno(APP_NOME, texto):
            self._upd_estado = None
            return
        if self.ligado:
            self.alternar()
        self._upd_estado = "baixando"
        self._upd_pct = None

        def progresso(lidos, total):
            self._upd_pct = int(lidos * 100 / total) if total else None

        def tarefa():
            try:
                self._upd_resultado = ("baixado", atualizador.baixar(info, progresso), True)
            except Exception as e:
                self._upd_resultado = ("falha", str(e), True)

        threading.Thread(target=tarefa, daemon=True).start()

    def _fechar(self):
        self.ligado = False
        self.gancho.desligar()
        self._salvar_config()
        try:
            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass
        self.destroy()


def ja_esta_aberto():
    """Impede duas cópias abertas (as duas apertariam teclas ao mesmo tempo)."""
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    globals()["_MUTEX"] = kernel32.CreateMutexW(None, False, "Local\\AutoAtackAQW_instancia")
    return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    if ja_esta_aberto():
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(APP_NOME, f"O {APP_NOME} já está aberto.")
        r.destroy()
    else:
        AutoAtack().mainloop()
