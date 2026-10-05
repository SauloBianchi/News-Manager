"""
theme.py
Paleta de cores, tipografia e pequenos componentes visuais reutilizáveis
que reproduzem, dentro do Tkinter, o estilo "Broadsheet Editorial" definido
no protótipo do Stitch (ver LayoutStitch/.../login_newsmanager/code.html e
o arquivo DESIGN.md que acompanha o pacote de telas).

A ideia geral do estilo:
- Fundo "papel jornal" (bege claro), cartões brancos, cantos retos (sem
  arredondamento), filetes finos separando seções.
- Tipografia serifada (Playfair Display) para títulos e sans-serif (Inter)
  para rótulos/formulários — com fallback automático para fontes já
  instaladas no computador, caso essas não existam.
- Vermelho editorial como cor de ação primária; azul jornal como cor
  secundária/links.
"""

import tkinter as tk
import tkinter.font as tkfont

# ---------------------------------------------------------------------------
# Paleta de cores (extraída do DESIGN.md do protótipo Stitch)
# ---------------------------------------------------------------------------
BG = "#F4F0E8"             # fundo / papel jornal
SURFACE = "#FFFFFF"        # cartões / campos de formulário
SURFACE_LOW = "#FAF7F0"    # painéis e listras secundárias
TEXT = "#1C1C17"           # texto principal (tinta preta)
TEXT_MUTED = "#58413F"     # texto secundário / legendas
PRIMARY = "#8B1E1E"        # vermelho editorial (ação primária)
PRIMARY_HOVER = "#701616"
SECONDARY = "#1B2A4A"      # azul jornal (links / ações secundárias)
BORDER = "#D5CEBF"         # filete fino
BORDER_STRONG = "#1C1C17"  # filete grosso / estado de foco
ERROR = "#BA1A1A"
SUCCESS = "#2E6B3E"


def _primeira_fonte_disponivel(root, preferidas):
    disponiveis = set(tkfont.families(root))
    for nome in preferidas:
        if nome in disponiveis:
            return nome
    return preferidas[-1]


class Fontes:
    """Resolve as famílias tipográficas uma única vez (com fallback seguro
    caso 'Playfair Display' / 'Inter' não estejam instaladas no sistema)."""

    _display = None
    _corpo = None

    @classmethod
    def preparar(cls, root):
        if cls._display is None:
            cls._display = _primeira_fonte_disponivel(
                root, ["Playfair Display", "Georgia", "Times New Roman"]
            )
            cls._corpo = _primeira_fonte_disponivel(
                root, ["Inter", "Segoe UI", "Helvetica", "Arial"]
            )

    @classmethod
    def display(cls, tamanho, peso="bold", italico=False):
        estilo = peso + (" italic" if italico else "")
        return (cls._display, tamanho, estilo)

    @classmethod
    def corpo(cls, tamanho, peso="normal"):
        return (cls._corpo, tamanho, peso)


# ---------------------------------------------------------------------------
# Componentes visuais reutilizáveis
# ---------------------------------------------------------------------------
def double_rule(parent, bg=None):
    """Filete duplo clássico de masthead de jornal (usado no topo/rodapé
    dos cartões de login e cadastro)."""
    bg = bg or parent.cget("bg")
    frame = tk.Frame(parent, bg=bg)
    tk.Frame(frame, bg=BORDER_STRONG, height=2).pack(fill="x")
    tk.Frame(frame, bg=bg, height=2).pack(fill="x")
    tk.Frame(frame, bg=BORDER_STRONG, height=1).pack(fill="x")
    return frame


class CampoEditorial(tk.Frame):
    """Campo de formulário no estilo 'galé de jornal': rótulo em versalete
    acima, filete fino que engrossa ao ganhar foco, com suporte a campo de
    senha com alternância de mostrar/ocultar."""

    def __init__(self, parent, rotulo, mostrar=None, dica=None):
        super().__init__(parent, bg=SURFACE)
        Fontes.preparar(parent)

        topo = tk.Frame(self, bg=SURFACE)
        topo.pack(fill="x")
        tk.Label(
            topo, text=rotulo, bg=SURFACE, fg=TEXT,
            font=Fontes.corpo(11, "bold"),
        ).pack(side="left")
        self.dica_label = None  # fica acessível para textos dinâmicos (ex.: "12 / 120")
        if dica:
            self.dica_label = tk.Label(
                topo, text=dica, bg=SURFACE, fg=TEXT_MUTED,
                font=Fontes.corpo(9),
            )
            self.dica_label.pack(side="right")

        container = tk.Frame(self, bg=SURFACE)
        container.pack(fill="x", pady=(4, 0))

        self.var = tk.StringVar()
        self.entry = tk.Entry(
            container, textvariable=self.var, relief="flat",
            bg=SURFACE, fg=TEXT, insertbackground=TEXT,
            font=Fontes.corpo(12), show=mostrar or "", bd=0,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(2, 2))

        self._eh_senha = mostrar == "*"
        self._senha_visivel = False
        if self._eh_senha:
            self.botao_olho = tk.Label(
                container, text="mostrar", fg=SECONDARY, bg=SURFACE,
                font=Fontes.corpo(9, "bold"), cursor="hand2",
            )
            self.botao_olho.pack(side="right", padx=(4, 4))
            self.botao_olho.bind("<Button-1>", self._alternar_senha)

        self._linha = tk.Frame(self, bg=BORDER, height=1)
        self._linha.pack(fill="x")

        self.entry.bind("<FocusIn>", self._focar)
        self.entry.bind("<FocusOut>", self._desfocar)

    def _focar(self, _event=None):
        self._linha.configure(bg=BORDER_STRONG, height=2)

    def _desfocar(self, _event=None):
        self._linha.configure(bg=BORDER, height=1)

    def _alternar_senha(self, _event=None):
        self._senha_visivel = not self._senha_visivel
        self.entry.configure(show="" if self._senha_visivel else "*")
        self.botao_olho.configure(text="ocultar" if self._senha_visivel else "mostrar")

    def get(self):
        return self.var.get().strip()

    def set(self, valor):
        self.var.set(valor)

    def focus(self):
        self.entry.focus_set()


def _botao(parent, texto, comando, bg, fg, bg_hover, borda, **kwargs):
    Fontes.preparar(parent)
    botao = tk.Button(
        parent, text=texto, command=comando, bg=bg, fg=fg,
        activebackground=bg_hover, activeforeground=fg,
        relief="flat", bd=1, highlightthickness=1,
        highlightbackground=borda, highlightcolor=borda,
        font=Fontes.corpo(11, "bold"), cursor="hand2", padx=14, pady=9,
        **kwargs
    )

    def _entrar(_e):
        if botao["state"] != "disabled":
            botao.configure(bg=bg_hover)

    def _sair(_e):
        if botao["state"] != "disabled":
            botao.configure(bg=bg)

    botao.bind("<Enter>", _entrar)
    botao.bind("<Leave>", _sair)
    return botao


def botao_primario(parent, texto, comando, **kwargs):
    return _botao(parent, texto.upper(), comando, PRIMARY, "#FFFFFF", PRIMARY_HOVER, PRIMARY, **kwargs)


def botao_secundario(parent, texto, comando, **kwargs):
    return _botao(parent, texto, comando, SURFACE, TEXT, SURFACE_LOW, BORDER_STRONG, **kwargs)


def botao_google(parent, texto, comando, **kwargs):
    return _botao(parent, "G   " + texto, comando, "#FFFFFF", TEXT, SURFACE_LOW, BORDER, **kwargs)


def link_texto(parent, texto, comando):
    Fontes.preparar(parent)
    lbl = tk.Label(
        parent, text=texto, fg=SECONDARY, bg=parent.cget("bg"),
        font=Fontes.corpo(10, "bold"), cursor="hand2",
    )
    lbl.bind("<Button-1>", lambda e: comando())
    return lbl
