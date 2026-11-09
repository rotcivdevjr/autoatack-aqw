"""
ui_tema.py - tema vermelho e preto do AutoAtack AQW
Cores, widgets desenhados (botão, interruptor, selo, degradê, cartão), estilo dos widgets ttk
e os sons da interface. Não mexe em nenhuma mecânica do programa.
"""
import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

try:  # só existe no Windows
    import winsound
except ImportError:  # pragma: no cover
    winsound = None


# ---------- pasta dos arquivos de imagem e som ----------
def _pasta_assets():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS  # executável criado pelo PyInstaller
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets")


ASSETS = _pasta_assets()


def asset(*partes):
    return os.path.join(ASSETS, *partes)


# ---------- cores ----------
BG = "#0b0b0e"          # fundo da janela
SURFACE = "#131318"     # cartões
SURFACE2 = "#1b1b22"    # botões secundários, abas
INPUT_BG = "#0e0e12"    # campos de texto
BORDER = "#2a1519"      # borda avermelhada bem escura
BORDER_SOFT = "#25252d"
RED = "#e0161f"
RED_HOVER = "#ff2d38"
RED_DARK = "#9c0e15"
TEXT = "#f4f4f6"
MUTED = "#8d8d99"
DIM = "#575762"
PANEL = SURFACE        # nome antigo, mantido por compatibilidade

FONTE = "Segoe UI"


def _hex_para_rgb(cor):
    cor = cor.lstrip("#")
    return tuple(int(cor[i:i + 2], 16) for i in (0, 2, 4))


def misturar(cor1, cor2, t):
    a, b = _hex_para_rgb(cor1), _hex_para_rgb(cor2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ---------- sons ----------
class Som:
    """Toca arquivos .wav da pasta assets/sons sem travar a interface."""

    def __init__(self):
        self.ativo = True

    def _tocar(self, nome):
        if not self.ativo or winsound is None:
            return
        try:
            winsound.PlaySound(asset("sons", nome), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass

    def clique(self):
        self._tocar("click.wav")

    def confirmar(self):
        self._tocar("confirmar.wav")


SOM = Som()


# ---------- escala da tela (Windows com 125%, 150%...) ----------
def escala():
    """1.0 em tela de 96 dpi (100%); maior em telas com zoom do Windows."""
    try:
        return max(1.0, tk._default_root.winfo_fpixels("1i") / 96.0)
    except Exception:
        return 1.0


# ---------- desenho ----------
def _retangulo_arredondado(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


ESTILOS_BOTAO = {
    "primario":   dict(fill=RED, hover=RED_HOVER, press=RED_DARK, borda=RED, fg="#ffffff"),
    "secundario": dict(fill=SURFACE2, hover="#2a1519", press="#160b0d", borda=BORDER, fg=TEXT),
    "ligado":     dict(fill="#1e0a0d", hover="#2b0d11", press="#150709", borda=RED, fg=RED_HOVER),
    "perigo":     dict(fill=SURFACE, hover="#2b0d11", press="#150709", borda=RED_DARK, fg="#ff6b73"),
}


class Botao(tk.Canvas):
    """Botão com cantos arredondados, efeito ao passar o mouse e som de clique."""

    def __init__(self, pai, texto, comando=None, estilo="primario", altura=34, largura=None,
                 tam=10, som=True, raio=8):
        k = escala()
        altura = int(altura * k)
        largura = int(largura * k) if largura else 20
        raio = int(raio * k)
        super().__init__(pai, height=altura, width=largura, bg=pai.cget("bg"),
                         highlightthickness=0, bd=0, cursor="hand2")
        self._texto = texto
        self._comando = comando
        self._estilo = estilo
        self._estado = "normal"
        self._hover = False
        self._press = False
        self._altura = altura
        self._raio = raio
        self._som = som
        self._fonte = (FONTE, tam, "bold")
        self.bind("<Configure>", lambda e: self._desenhar())
        self.bind("<Enter>", self._ao_entrar)
        self.bind("<Leave>", self._ao_sair)
        self.bind("<ButtonPress-1>", self._ao_apertar)
        self.bind("<ButtonRelease-1>", self._ao_soltar)
        self._desenhar()

    # --- aparência ---
    def _desenhar(self):
        try:
            self.delete("all")
            w = max(self.winfo_width(), int(self.cget("width")), 4)
            h = self._altura
            est = ESTILOS_BOTAO.get(self._estilo, ESTILOS_BOTAO["primario"])
            if self._estado == "disabled":
                fill, borda, fg = SURFACE, BORDER_SOFT, DIM
            elif self._press:
                fill, borda, fg = est["press"], est["borda"], est["fg"]
            elif self._hover:
                fill, borda, fg = est["hover"], est["borda"], est["fg"]
            else:
                fill, borda, fg = est["fill"], est["borda"], est["fg"]
            _retangulo_arredondado(self, 1, 1, w - 1, h - 1, self._raio,
                                   fill=fill, outline=borda, width=1)
            self.create_text(w / 2, h / 2, text=self._texto, fill=fg, font=self._fonte)
        except tk.TclError:
            pass

    def _ao_entrar(self, _e):
        self._hover = True
        self._desenhar()

    def _ao_sair(self, _e):
        self._hover = False
        self._press = False
        self._desenhar()

    def _ao_apertar(self, _e):
        if self._estado == "disabled":
            return
        self._press = True
        self._desenhar()

    def _ao_soltar(self, e):
        if self._estado == "disabled" or not self._press:
            return
        self._press = False
        dentro = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self._altura
        self._desenhar()
        if dentro:
            if self._som:
                SOM.clique()
            if self._comando:
                self._comando()  # por último: o comando pode recriar a tela

    # --- compatível com .config(text=..., state=...) ---
    def configure(self, cnf=None, **kw):
        mudou = False
        if "text" in kw:
            self._texto = kw.pop("text")
            mudou = True
        if "state" in kw:
            self._estado = kw.pop("state")
            tk.Canvas.configure(self, cursor="arrow" if self._estado == "disabled" else "hand2")
            mudou = True
        if "estilo" in kw:
            self._estilo = kw.pop("estilo")
            mudou = True
        if "command" in kw:
            self._comando = kw.pop("command")
        for velho in ("bg", "fg", "activebackground", "activeforeground"):
            kw.pop(velho, None)
        resultado = None
        if cnf or kw:
            resultado = tk.Canvas.configure(self, cnf, **kw)
        if mudou:
            self._desenhar()
        return resultado

    config = configure


class Chave(tk.Canvas):
    """Interruptor (liga/desliga) ligado a uma BooleanVar, com texto opcional ao lado."""

    def __init__(self, pai, texto="", var=None, comando=None, fonte=(FONTE, 10),
                 cor_texto=TEXT, bg=None, som=False):
        bg = bg or pai.cget("bg")
        medidor = tkfont.Font(font=fonte)
        k = escala()
        self._k = k
        largura = int(46 * k) + ((int(10 * k) + medidor.measure(texto)) if texto else 0)
        super().__init__(pai, width=largura, height=int(26 * k), bg=bg, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.var = var if var is not None else tk.BooleanVar(value=False)
        self._texto = texto
        self._fonte = fonte
        self._cor_texto = cor_texto
        self._comando = comando
        self._som = som
        self._tid = self.var.trace_add("write", lambda *a: self._desenhar())
        self.bind("<ButtonRelease-1>", self._ao_clicar)
        self.bind("<Destroy>", self._ao_destruir)
        self._desenhar()

    def _desenhar(self):
        try:
            self.delete("all")
            ligado = bool(self.var.get())
            k = self._k

            def u(v):
                return int(v * k)

            _retangulo_arredondado(self, u(1), u(3), u(43), u(23), u(10),
                                   fill=RED if ligado else SURFACE2,
                                   outline=RED_DARK if ligado else BORDER_SOFT, width=1)
            x = 33 if ligado else 13
            self.create_oval(u(x - 7), u(6), u(x + 7), u(20),
                             fill="#ffffff" if ligado else MUTED, outline="")
            if self._texto:
                self.create_text(u(54), u(13), text=self._texto, fill=self._cor_texto,
                                 font=self._fonte, anchor="w")
        except tk.TclError:
            pass

    def _ao_clicar(self, e):
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.var.set(not self.var.get())
            if self._som:
                SOM.clique()
            if self._comando:
                self._comando()

    def _ao_destruir(self, e):
        if e.widget is self:
            try:
                self.var.trace_remove("write", self._tid)
            except Exception:
                pass


class Selo(tk.Canvas):
    """Bolinha vermelha com o número da skill."""

    def __init__(self, pai, texto, bg=None, tamanho=26):
        tamanho = int(tamanho * escala())
        super().__init__(pai, width=tamanho, height=tamanho, bg=bg or pai.cget("bg"),
                         highlightthickness=0, bd=0)
        self.create_oval(1, 1, tamanho - 1, tamanho - 1, fill=RED, outline=RED_DARK)
        self.create_text(tamanho / 2, tamanho / 2, text=texto, fill="#ffffff",
                         font=(FONTE, 10, "bold"))


class Degrade(tk.Canvas):
    """Linha fina com degradê do vermelho para o fundo."""

    def __init__(self, pai, altura=3, cor1=RED, cor2=BG):
        super().__init__(pai, height=altura, bg=cor2, highlightthickness=0, bd=0)
        self._cor1, self._cor2, self._altura = cor1, cor2, altura
        self.bind("<Configure>", lambda e: self._desenhar())

    def _desenhar(self):
        try:
            self.delete("all")
            w = max(self.winfo_width(), 2)
            for x in range(0, w, 2):
                self.create_line(x, 0, x, self._altura,
                                 fill=misturar(self._cor1, self._cor2, x / (w - 1)), width=2)
        except tk.TclError:
            pass


class Cartao(tk.Frame):
    """Painel escuro com borda fina avermelhada."""

    def __init__(self, pai, bg=SURFACE, borda=BORDER, **kw):
        super().__init__(pai, bg=bg, highlightbackground=borda, highlightthickness=1, **kw)


# ---------- atalhos usados pelo programa ----------
def botao(pai, texto, comando, estilo="primario", largura=None, altura=34, tam=10):
    return Botao(pai, texto, comando, estilo=estilo, altura=altura, largura=largura, tam=tam)


def campo(pai, var, largura=8):
    return tk.Entry(pai, textvariable=var, bg=INPUT_BG, fg=TEXT, insertbackground=RED_HOVER,
                    relief="flat", font=(FONTE, 11), highlightbackground=BORDER,
                    highlightcolor=RED, highlightthickness=1, justify="center",
                    width=largura, selectbackground=RED_DARK, selectforeground="#ffffff")


def caixa_marcar(pai, texto="", var=None, bg=None, font=None, comando=None, **_ignorado):
    return Chave(pai, texto, var, comando, fonte=font or (FONTE, 10), bg=bg)


def titulo(pai, texto, bg=BG):
    return tk.Label(pai, text=texto, bg=bg, fg=RED, font=(FONTE, 9, "bold"))


def aplicar_estilo_ttk(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure("TCombobox", fieldbackground=INPUT_BG, background=SURFACE2, foreground=TEXT,
                arrowcolor=RED_HOVER, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                padding=4, selectbackground=INPUT_BG, selectforeground=TEXT)
    s.map("TCombobox",
          fieldbackground=[("readonly", INPUT_BG)],
          foreground=[("readonly", TEXT)],
          background=[("active", "#2a1519")],
          bordercolor=[("focus", RED)])
    s.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BORDER,
                lightcolor=BG, darkcolor=BG, tabmargins=(2, 0, 2, 0))
    s.configure("TNotebook.Tab", background=SURFACE2, foreground=MUTED, padding=(14, 7),
                font=(FONTE, 9, "bold"), borderwidth=0)
    s.map("TNotebook.Tab",
          background=[("selected", RED), ("active", "#2a1519")],
          foreground=[("selected", "#ffffff"), ("active", TEXT)])
    root.option_add("*TCombobox*Listbox.background", SURFACE2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", RED)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.font", (FONTE, 10))
