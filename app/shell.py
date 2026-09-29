"""
shell.py
"Moldura" da janela principal, reproduzindo o cabeçalho do protótipo Stitch:

- Cabecalho: faixa de dateline (data por extenso, edição, status do
  sistema), masthead "NewsManager", botão "+ Nova matéria", bloco do usuário
  logado com "Sair" e a navegação em texto (Notícias, Categorias, Autores,
  Gráficos, Segurança) com filete duplo embaixo.
- AreaAbas: troca de telas (substitui o ttk.Notebook), mostrando uma tela
  por vez.
- Rodape: linha de direitos autorais no pé da janela.
"""

import tkinter as tk
from datetime import date

from . import theme as t

DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

# (chave, rótulo) na ordem da navegação do protótipo
ITENS_NAVEGACAO = [
    ("noticias", "Notícias"),
    ("categorias", "Categorias"),
    ("autores", "Autores"),
    ("graficos", "Gráficos"),
    ("seguranca", "Segurança"),
]

MARGEM = 28
INTERVALO_STATUS_MS = 30_000


def data_por_extenso(dia: date = None) -> str:
    """'Sexta-feira, 24 de Maio de 2024' (sem depender do idioma do sistema)."""
    dia = dia or date.today()
    return f"{DIAS_SEMANA[dia.weekday()]}, {dia.day} de {MESES[dia.month - 1]} de {dia.year}"


def _inicial(nome: str) -> str:
    return (nome or "?").strip()[:1].upper() or "?"


class Cabecalho(tk.Frame):
    """Faixa superior fixa: dateline + masthead + navegação."""

    def __init__(self, parent, usuario, ao_navegar, ao_nova_materia, ao_sair,
                 verificar_conexao=None):
        super().__init__(parent, bg=t.BG)
        t.Fontes.preparar(parent)
        self.usuario = usuario or {}
        self.ao_navegar = ao_navegar
        self.verificar_conexao = verificar_conexao
        self._itens = {}
        self._ativo = None

        self._montar_dateline()
        self._montar_masthead(ao_nova_materia, ao_sair)
        self._montar_navegacao()
        if self.verificar_conexao:
            self._atualizar_status()

    # ---------- dateline ----------
    def _montar_dateline(self):
        faixa = tk.Frame(self, bg=t.BG)
        faixa.pack(fill="x", padx=MARGEM, pady=(8, 6))
        hoje = date.today()
        esquerda = (f"{data_por_extenso(hoje)}   |   EDIÇÃO DIÁRIA • Nº {hoje.timetuple().tm_yday:03d}")
        tk.Label(faixa, text=esquerda.upper(), fg=t.TEXT, bg=t.BG,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        self.rotulo_status = tk.Label(faixa, text="● SISTEMA REDATORIAL ATIVO", fg=t.PRIMARY,
                                      bg=t.BG, font=t.Fontes.corpo(8, "bold"))
        self.rotulo_status.pack(side="right")
        tk.Frame(self, bg=t.BORDER, height=1).pack(fill="x", padx=MARGEM)

    def _atualizar_status(self):
        try:
            conectado = bool(self.verificar_conexao())
        except Exception:
            conectado = False
        self.rotulo_status.configure(
            text="● SISTEMA REDATORIAL ATIVO" if conectado else "● BANCO DE DADOS DESCONECTADO",
            fg=t.PRIMARY if conectado else t.ERROR,
        )
        self.after(INTERVALO_STATUS_MS, self._atualizar_status)

    # ---------- masthead ----------
    def _montar_masthead(self, ao_nova_materia, ao_sair):
        linha = tk.Frame(self, bg=t.BG)
        linha.pack(fill="x", padx=MARGEM, pady=(12, 10))

        marca = tk.Frame(linha, bg=t.BG)
        marca.pack(side="left")
        tk.Label(marca, text="NewsManager", fg=t.TEXT, bg=t.BG,
                 font=t.Fontes.display(26)).pack(anchor="w")
        tk.Label(marca, text="GAZETA EDITORIAL IMPRESSA & DIGITAL", fg=t.TEXT, bg=t.BG,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")

        direita = tk.Frame(linha, bg=t.BG)
        direita.pack(side="right")
        t.botao_primario(direita, "+ Nova matéria", ao_nova_materia).pack(side="left", padx=(0, 18))

        nome = self.usuario.get("nome") or self.usuario.get("usuario") or "Redação"
        tk.Label(direita, text=_inicial(nome), fg="#FFFFFF", bg=t.PRIMARY, width=3, height=1,
                 font=t.Fontes.display(14)).pack(side="left")
        dados = tk.Frame(direita, bg=t.BG)
        dados.pack(side="left", padx=(8, 12))
        tk.Label(dados, text=nome, fg=t.TEXT, bg=t.BG, font=t.Fontes.corpo(10, "bold")).pack(anchor="w")
        apelido = self.usuario.get("usuario")
        tk.Label(dados, text=(f"@{apelido}" if apelido else "REDAÇÃO").upper(), fg=t.TEXT_MUTED,
                 bg=t.BG, font=t.Fontes.corpo(7, "bold")).pack(anchor="w")
        t.link_texto(direita, "SAIR", ao_sair).pack(side="left")

    # ---------- navegação ----------
    def _montar_navegacao(self):
        tk.Frame(self, bg=t.TEXT, height=2).pack(fill="x", padx=MARGEM)
        tk.Frame(self, bg=t.BG, height=2).pack(fill="x", padx=MARGEM)
        tk.Frame(self, bg=t.TEXT, height=1).pack(fill="x", padx=MARGEM)

        barra = tk.Frame(self, bg=t.BG)
        barra.pack(fill="x", padx=MARGEM, pady=(6, 0))
        for chave, rotulo in ITENS_NAVEGACAO:
            item = tk.Frame(barra, bg=t.BG, cursor="hand2")
            item.pack(side="left", padx=(0, 26))
            texto = tk.Label(item, text=rotulo, fg=t.TEXT, bg=t.BG, cursor="hand2",
                             font=t.Fontes.display(14, "normal"))
            texto.pack()
            sublinhado = tk.Frame(item, bg=t.BG, height=2)
            sublinhado.pack(fill="x", pady=(2, 0))
            for widget in (item, texto, sublinhado):
                widget.bind("<Button-1>", lambda e, c=chave: self.ao_navegar(c))
            self._itens[chave] = (texto, sublinhado)
        tk.Frame(self, bg=t.BORDER, height=1).pack(fill="x", padx=MARGEM)

    def definir_ativa(self, chave):
        """Destaca o item da navegação (vermelho + sublinhado)."""
        self._ativo = chave
        for k, (texto, sublinhado) in self._itens.items():
            ativo = k == chave
            texto.configure(fg=t.PRIMARY if ativo else t.TEXT)
            sublinhado.configure(bg=t.PRIMARY if ativo else t.BG)


class AreaAbas(tk.Frame):
    """Mostra uma tela por vez. As telas devem ser criadas com esta área como
    'parent' e registradas com adicionar()."""

    def __init__(self, parent):
        super().__init__(parent, bg=t.BG)
        self._telas = {}
        self.atual = None

    def adicionar(self, chave, tela):
        self._telas[chave] = tela

    def tela(self, chave):
        return self._telas[chave]

    def mostrar(self, chave):
        if self.atual is not None and self.atual in self._telas:
            self._telas[self.atual].pack_forget()
        self.atual = chave
        self._telas[chave].pack(fill="both", expand=True)


class Rodape(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=t.BG)
        t.Fontes.preparar(parent)
        tk.Frame(self, bg=t.BORDER, height=1).pack(fill="x", padx=MARGEM)
        linha = tk.Frame(self, bg=t.BG)
        linha.pack(fill="x", padx=MARGEM, pady=8)
        tk.Label(linha, text="NewsManager", fg=t.TEXT, bg=t.BG,
                 font=t.Fontes.display(12)).pack(side="left")
        tk.Label(linha, text=f"© {date.today().year} GAZETA EDITORIAL IMPRESSA & DIGITAL. "
                             "TODOS OS DIREITOS RESERVADOS.", fg=t.TEXT, bg=t.BG,
                 font=t.Fontes.corpo(7, "bold")).pack(side="left", padx=(12, 0))
        tk.Label(linha, text="TERMINAL REDATORIAL  •  MECANISMO DE GALÉS  •  UTF-8", fg=t.TEXT,
                 bg=t.BG, font=t.Fontes.corpo(7, "bold")).pack(side="right")
