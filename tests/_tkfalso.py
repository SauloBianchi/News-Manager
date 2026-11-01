"""
Tk de mentira para testes SEM janela real.

Instala módulos `tkinter`, `tkinter.ttk`, `tkinter.font`, `tkinter.filedialog`,
`tkinter.messagebox` e `matplotlib.backends.backend_tkagg` falsos, em que todo
widget aceita qualquer chamada e não desenha nada. Serve para:
- importar os módulos de tela e exercitar a LÓGICA de montagem/atualização
  (erros de nome, atributo ausente, ordem de chamadas);
- NÃO valida aparência, layout, rolagem, foco nem eventos reais do Tk.
"""

import sys
import types


class _Qualquer:
    def __init__(self, *args, **kwargs):
        self.master = args[0] if args else kwargs.get("master")
        self._cfg = dict(kwargs)
        self._filhos = []
        self.chamadas = []
        if isinstance(self.master, _Qualquer):
            self.master._filhos.append(self)

    def __getattr__(self, nome):
        if nome.startswith("__"):
            raise AttributeError(nome)

        def chamada(*a, **k):
            self.chamadas.append((nome, a, k))
            if nome in ("configure", "config"):
                self._cfg.update(k)
            if nome == "destroy":
                if isinstance(self.master, _Qualquer) and self in self.master._filhos:
                    self.master._filhos.remove(self)
                return None
            if nome in ("curselection",):
                return (0,)
            if nome in ("get", "cget"):
                return self._cfg.get(a[0] if a else "", "")
            if nome in ("after",):
                return "after#1"
            if nome in ("winfo_ismapped",):
                return True
            if nome in ("winfo_width", "winfo_height"):
                return 800
            return _Qualquer(self)
        return chamada

    def cget(self, chave):
        return self._cfg.get(chave, "#FFFFFF")

    def winfo_children(self):
        return list(self._filhos)

    def winfo_ismapped(self):
        return True

    def __getitem__(self, chave):
        return self._cfg.get(chave, "normal")

    def __setitem__(self, chave, valor):
        self._cfg[chave] = valor

    def current(self, *a):
        return 0 if not a else None


class _Var:
    def __init__(self, master=None, value=None, **k):
        self._v = value

    def get(self):
        return self._v if self._v is not None else ""

    def set(self, v):
        self._v = v

    def trace_add(self, *a, **k):
        return None


class _BooleanVar(_Var):
    def get(self):
        return bool(self._v)


class TclErrorFalso(Exception):
    pass


def instalar():
    tk = types.ModuleType("tkinter")
    for nome in ("Frame", "Label", "Button", "Entry", "Canvas", "Text", "Toplevel", "Tk", "Listbox", "Checkbutton",
                 "Radiobutton", "Scrollbar", "LabelFrame", "PanedWindow", "Menu", "Scale", "Spinbox", "Message"):
        setattr(tk, nome, type(nome, (_Qualquer,), {}))
    tk.StringVar, tk.IntVar, tk.DoubleVar, tk.BooleanVar = _Var, _Var, _Var, _BooleanVar
    tk.TclError = TclErrorFalso
    for const in ("END", "LEFT", "RIGHT", "BOTH", "X", "Y", "W", "E", "N", "S", "NW", "WORD", "NORMAL", "DISABLED",
                  "INSERT", "SEL", "TOP", "BOTTOM", "CENTER"):
        setattr(tk, const, const.lower())
    ttk = types.ModuleType("tkinter.ttk")
    for nome in ("Combobox", "Scrollbar", "Style", "Treeview", "Progressbar", "Notebook", "Separator", "Button",
                 "Label", "Frame", "Entry", "Checkbutton"):
        setattr(ttk, nome, type(nome, (_Qualquer,), {}))
    fonte = types.ModuleType("tkinter.font")
    fonte.families = lambda root=None: []
    fonte.Font = type("Font", (_Qualquer,), {"measure": lambda self, t: len(t) * 7})
    dialogo = types.ModuleType("tkinter.filedialog")
    dialogo.askopenfilename = lambda *a, **k: ""
    dialogo.asksaveasfilename = lambda *a, **k: ""
    caixa = types.ModuleType("tkinter.messagebox")
    caixa.respostas = []
    caixa.mostradas = []

    def _registra(nome, padrao):
        def f(titulo=None, mensagem=None, **k):
            caixa.mostradas.append((nome, titulo, mensagem))
            return caixa.respostas.pop(0) if caixa.respostas else padrao
        return f
    for nome, padrao in (("showinfo", "ok"), ("showwarning", "ok"), ("showerror", "ok"), ("askyesno", True),
                         ("askokcancel", True), ("askquestion", "yes")):
        setattr(caixa, nome, _registra(nome, padrao))
    simples = types.ModuleType("tkinter.simpledialog")
    simples.askstring = lambda *a, **k: "Nome de teste"
    tk.ttk, tk.font, tk.filedialog, tk.messagebox, tk.simpledialog = ttk, fonte, dialogo, caixa, simples
    sys.modules.update({"tkinter": tk, "tkinter.ttk": ttk, "tkinter.font": fonte, "tkinter.filedialog": dialogo,
                        "tkinter.messagebox": caixa, "tkinter.simpledialog": simples})
    agg = types.ModuleType("matplotlib.backends.backend_tkagg")

    class FigureCanvasTkAgg(_Qualquer):
        def __init__(self, figura, master=None):
            super().__init__(master)
            self.figura = figura

        def get_tk_widget(self):
            return _Qualquer(self.master)

    agg.FigureCanvasTkAgg = FigureCanvasTkAgg
    sys.modules["matplotlib.backends.backend_tkagg"] = agg
    return tk
