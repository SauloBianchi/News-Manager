"""
telas_cadastros.py
Telas "Categorias" e "Autores" do NewsManager, reproduzindo em Tkinter o
protótipo do Stitch (design/LayoutStitch/.../categorias_newsmanager e
autores_newsmanager).

- CategoriasFrame: "Caderno de Editorias & Categorias" — cartões de resumo,
  busca, formulário "Cadastrar Nova Editoria", catálogo em tabela (código,
  editoria, descritivo, volume, última edição, status, ações) e exportação
  do relatório em CSV.
- AutoresFrame: "Quadro de Redação & Jornalistas Cadastrados" — busca,
  filtros por função, formulário de credenciamento, cartões em grade 3x2
  com paginação e botão "Ver matérias".

As duas telas só conversam com CategoriaService / AutorService
(app/cadastros.py); nenhuma SQL fica aqui. Cada uma é um tk.Frame para ser
adicionada como aba da janela principal.
"""

import csv
import math
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from . import theme as t
from .midia import TIPOS_ARQUIVO_DIALOGO, ErroMidia
from .midia import midia as midia_global
from .cadastros import (
    CORES_CATEGORIA,
    FUNCOES_AUTOR,
    FUNCOES_AUTOR_PLURAL,
    STATUS_AUTOR,
    STATUS_CATEGORIA,
    AutorService,
    CategoriaService,
)

# ---------------------------------------------------------------------------
# Cores extras do protótipo (matizes das etiquetas e painéis)
# ---------------------------------------------------------------------------
COR_MATIZ = {"rubro": "#8B1E1E", "azul": "#4F5E81", "sepia": "#5A4426", "carvao": "#1C1C17"}
FUNDO_MATIZ = {"rubro": "#F4E1DE", "azul": "#DCE4F7", "sepia": "#EFE3D0", "carvao": "#E6E2DA"}
MATIZ_DA_FUNCAO = {
    "reporter": "rubro",
    "colunista": "azul",
    "editor_setorial": "sepia",
    "correspondente": "carvao",
}
PAINEL = "#F1EDE5"        # faixas de cabeçalho / painéis (surface-container)
PAINEL_ALTO = "#ECE8E0"   # rodapé dos cartões e trilho das barras
PAINEL_BAIXO = "#F7F3EB"  # caixa de estatística dos cartões
MARGEM = 28

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------
def _como_data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return datetime.strptime(valor[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def data_relativa(valor) -> str:
    """'Hoje', 'Ontem', '22 Mai' (ou '22 Mai 2025' se for de outro ano)."""
    d = _como_data(valor)
    if d is None:
        return "—"
    hoje = date.today()
    if d == hoje:
        return "Hoje"
    if d == hoje - timedelta(days=1):
        return "Ontem"
    texto = f"{d.day:02d} {MESES[d.month - 1]}"
    return texto if d.year == hoje.year else f"{texto} {d.year}"


def _resumir(texto, limite=150) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _paginas_visiveis(atual, total):
    """Números de página a mostrar; None vira '…' quando há muitas páginas."""
    if total <= 7:
        return list(range(1, total + 1))
    paginas = {1, total, atual - 1, atual, atual + 1}
    paginas = sorted(p for p in paginas if 1 <= p <= total)
    resultado = []
    for p in paginas:
        if resultado and p - resultado[-1] > 1:
            resultado.append(None)
        resultado.append(p)
    return resultado


def _etiqueta(parent, texto, cor, fundo=None, borda=True, tamanho=8):
    """Selo de texto em versalete: com contorno (categorias) ou com fundo
    suave (cargo dos autores)."""
    return tk.Label(
        parent, text=texto.upper(), fg=cor, bg=fundo or parent.cget("bg"),
        font=t.Fontes.corpo(tamanho, "bold"), padx=6, pady=2, bd=0,
        highlightthickness=1 if borda else 0,
        highlightbackground=cor, highlightcolor=cor,
    )


def _link(parent, texto, comando, cor=None):
    rotulo = t.link_texto(parent, texto, comando)
    if cor:
        rotulo.configure(fg=cor)
    return rotulo


def _cabecalho(parent, eyebrow, titulo, subtitulo):
    """Bloco de título de página: sobretítulo vermelho, título serifado,
    subtítulo e filete grosso embaixo. Devolve o frame do texto (à esquerda)
    e o frame da linha, para o chamador acrescentar botões à direita."""
    linha = tk.Frame(parent, bg=t.BG)
    linha.pack(fill="x", padx=MARGEM, pady=(22, 0))
    texto = tk.Frame(linha, bg=t.BG)
    texto.pack(side="left", fill="x", expand=True)
    tk.Label(texto, text=eyebrow.upper(), fg=t.PRIMARY, bg=t.BG,
             font=t.Fontes.corpo(9, "bold")).pack(anchor="w")
    tk.Label(texto, text=titulo, fg=t.TEXT, bg=t.BG,
             font=t.Fontes.display(26)).pack(anchor="w", pady=(2, 2))
    tk.Label(texto, text=subtitulo, fg=t.TEXT_MUTED, bg=t.BG, justify="left",
             font=t.Fontes.display(12, "normal", True), wraplength=720).pack(anchor="w")
    return linha


def _filete(parent, espessura=2, bg=None, padx=MARGEM, pady=(14, 0)):
    tk.Frame(parent, bg=bg or t.BORDER_STRONG, height=espessura).pack(fill="x", padx=padx, pady=pady)


def desenhar_paginacao(container, texto, atual, paginas, ao_ir):
    """Barra 'EXIBINDO X DE Y ...  ‹ ANTERIOR 1 2 3 … PRÓXIMA ›' dentro de um
    frame (que é esvaziado antes). `ao_ir(numero)` é chamado ao clicar."""
    for filho in container.winfo_children():
        filho.destroy()
    interno = tk.Frame(container, bg=t.SURFACE, padx=12, pady=10)
    interno.pack(fill="x")
    tk.Label(interno, text=texto, fg=t.TEXT_MUTED, bg=t.SURFACE,
             font=t.Fontes.corpo(8, "bold")).pack(side="left")
    navegacao = tk.Frame(interno, bg=t.SURFACE)
    navegacao.pack(side="right")

    def botao(rotulo_texto, destino=None, ativo=False):
        habilitado = destino is not None
        rotulo = tk.Label(
            navegacao, text=rotulo_texto, padx=10, pady=5,
            bg=t.TEXT if ativo else (PAINEL if habilitado else t.SURFACE),
            fg="#FFFFFF" if ativo else (t.TEXT if habilitado else t.BORDER),
            font=t.Fontes.corpo(8, "bold"), cursor="hand2" if habilitado else "",
        )
        rotulo.pack(side="left", padx=2)
        if habilitado and not ativo:
            rotulo.bind("<Button-1>", lambda e, d=destino: ao_ir(d))

    botao("‹ ANTERIOR", atual - 1 if atual > 1 else None)
    for numero in _paginas_visiveis(atual, paginas):
        if numero is None:
            tk.Label(navegacao, text="…", bg=t.SURFACE, fg=t.TEXT_MUTED).pack(side="left")
        else:
            botao(str(numero), numero, ativo=numero == atual)
    botao("PRÓXIMA ›", atual + 1 if atual < paginas else None)


# ---------------------------------------------------------------------------
# Componentes de formulário (além do CampoEditorial do theme.py)
# ---------------------------------------------------------------------------
class CampoSelecao(tk.Frame):
    """Rótulo + lista suspensa. Trabalha com as CHAVES do dicionário de
    opções (o que vai para o banco), exibindo os rótulos. As opções podem ser
    trocadas depois com definir_opcoes() (ex.: lista de autores do banco)."""

    def __init__(self, parent, rotulo, opcoes: dict):
        super().__init__(parent, bg=t.SURFACE)
        t.Fontes.preparar(parent)
        self._chaves = []
        tk.Label(self, text=rotulo, bg=t.SURFACE, fg=t.TEXT,
                 font=t.Fontes.corpo(11, "bold")).pack(anchor="w")
        self.combo = ttk.Combobox(self, values=[], state="readonly", font=t.Fontes.corpo(11))
        self.combo.pack(fill="x", pady=(4, 0), ipady=3)
        self.definir_opcoes(opcoes)

    def definir_opcoes(self, opcoes: dict):
        """Troca a lista, mantendo a escolha atual quando ela ainda existe."""
        anterior = self.get()
        self._chaves = list(opcoes.keys())
        self.combo.configure(values=list(opcoes.values()))
        if anterior in self._chaves:
            self.set(anterior)
        elif self._chaves:
            self.combo.current(0)
        else:
            self.combo.set("")

    def get(self):
        """Chave escolhida, ou None se a lista estiver vazia."""
        if not self._chaves:
            return None
        indice = self.combo.current()
        return self._chaves[indice if indice >= 0 else 0]

    def set(self, chave):
        if chave in self._chaves:
            self.combo.current(self._chaves.index(chave))


class CampoImagem(tk.Frame):
    """Seletor de imagem: miniatura, botão 'Escolher imagem' e link 'Remover'.

    Ciclo de vida dos arquivos (para não sobrar imagem perdida na pasta):
    - escolher() copia a imagem para a pasta de mídia na hora, mas ela só fica
      "valendo" quando o registro é salvo (o chamador usa confirmar_salvo());
    - se o usuário trocar de imagem, limpar o formulário ou abrir outro
      registro antes de salvar, a cópia provisória é apagada;
    - a imagem ANTIGA de um registro editado é apagada pelo serviço (app/
      cadastros.py e app/noticias.py) quando o novo caminho é gravado.
    """

    def __init__(self, parent, rotulo, pasta, largura=180, altura=100, gerenciador=None):
        super().__init__(parent, bg=t.SURFACE)
        t.Fontes.preparar(parent)
        self.pasta = pasta
        self.largura, self.altura = largura, altura
        self.midia = gerenciador or midia_global
        self._original = None   # caminho gravado no banco para o registro em edição
        self._atual = None      # caminho que está no formulário agora

        tk.Label(self, text=rotulo, bg=t.SURFACE, fg=t.TEXT,
                 font=t.Fontes.corpo(11, "bold")).pack(anchor="w")
        self.moldura = tk.Frame(self, width=largura, height=altura, bg=PAINEL,
                                highlightthickness=1, highlightbackground=t.BORDER)
        self.moldura.pack(anchor="w", pady=(4, 0))
        self.moldura.pack_propagate(False)
        self.preview = tk.Label(self.moldura, text="SEM IMAGEM", bg=PAINEL, fg=t.TEXT_MUTED,
                                font=t.Fontes.corpo(8, "bold"), bd=0, cursor="hand2")
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Button-1>", lambda e: self.escolher())

        botoes = tk.Frame(self, bg=t.SURFACE)
        botoes.pack(anchor="w", pady=(6, 0))
        self.botao_escolher = t.botao_secundario(botoes, "ESCOLHER IMAGEM", self.escolher)
        self.botao_escolher.pack(side="left")
        self.link_remover = _link(botoes, "REMOVER", self.remover, t.ERROR)
        self._atualizar_preview()

    # ---------- estado ----------
    @property
    def caminho(self):
        """Caminho relativo da imagem no formulário (ou None)."""
        return self._atual

    def definir(self, caminho):
        """Carrega a imagem já gravada de um registro (sem mexer em arquivos)."""
        self._descartar_provisoria()
        self._original = self._atual = caminho or None
        self._atualizar_preview()

    def definir_provisoria(self, caminho):
        """Como definir(), mas a imagem ainda NÃO está salva em nenhum registro
        (ex.: veio de outro formulário): se o usuário desistir, o arquivo é apagado."""
        self._descartar_provisoria()
        self._original = None
        self._atual = caminho or None
        self._atualizar_preview()

    def limpar(self):
        self.definir(None)

    def confirmar_salvo(self):
        """Chame depois de salvar com sucesso: a imagem do formulário passa a ser a oficial."""
        self._original = self._atual

    def _descartar_provisoria(self):
        if self._atual and self._atual != self._original:
            self.midia.remover(self._atual)

    # ---------- ações ----------
    def escolher(self):
        origem = filedialog.askopenfilename(
            title="Escolher imagem", filetypes=TIPOS_ARQUIVO_DIALOGO)
        if not origem:
            return
        try:
            novo = self.midia.importar(origem, self.pasta)
        except ErroMidia as erro:
            messagebox.showwarning("Imagem", str(erro))
            return
        self._descartar_provisoria()
        self._atual = novo
        self._atualizar_preview()

    def remover(self):
        self._descartar_provisoria()
        self._atual = None
        self._atualizar_preview()

    def _atualizar_preview(self):
        foto = self.midia.carregar_tk(self._atual, self.largura - 2, self.altura - 2) if self._atual else None
        if foto is not None:
            self.preview.configure(image=foto, text="")
            self.preview.image = foto   # o Tk descarta a imagem se ninguém guardar a referência
        elif self._atual:
            self.preview.configure(image="", text="IMAGEM SELECIONADA")
            self.preview.image = None
        else:
            self.preview.configure(image="", text="SEM IMAGEM")
            self.preview.image = None
        if self._atual:
            self.link_remover.pack(side="left", padx=(10, 0))
        else:
            self.link_remover.pack_forget()


class CampoTextoLongo(tk.Frame):
    """Rótulo + caixa de texto de várias linhas (biografia)."""

    def __init__(self, parent, rotulo, altura=4):
        super().__init__(parent, bg=t.SURFACE)
        t.Fontes.preparar(parent)
        tk.Label(self, text=rotulo, bg=t.SURFACE, fg=t.TEXT,
                 font=t.Fontes.corpo(11, "bold")).pack(anchor="w")
        self.texto = tk.Text(
            self, height=altura, wrap="word", relief="flat", bg=t.SURFACE, fg=t.TEXT,
            insertbackground=t.TEXT, font=t.Fontes.corpo(11), padx=6, pady=6,
            highlightthickness=1, highlightbackground=t.BORDER, highlightcolor=t.BORDER_STRONG,
        )
        self.texto.pack(fill="x", pady=(4, 0))

    def get(self):
        return self.texto.get("1.0", "end").strip()

    def set(self, valor):
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", valor or "")


class RolagemVertical(tk.Frame):
    """Área com barra de rolagem: coloque os widgets da tela em `.conteudo`.
    A roda do mouse só rola quando o ponteiro está sobre esta área."""

    def __init__(self, parent):
        super().__init__(parent, bg=t.BG)
        self.canvas = tk.Canvas(self, bg=t.BG, highlightthickness=0, bd=0)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.barra.set)
        self.barra.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.conteudo = tk.Frame(self.canvas, bg=t.BG)
        self._janela = self.canvas.create_window((0, 0), window=self.conteudo, anchor="nw")
        self.conteudo.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(self._janela, width=e.width)
        )
        for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(evento, self._rolar, add="+")

    def _ponteiro_esta_aqui(self, event):
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return False
        while widget is not None:
            if widget is self:
                return True
            widget = widget.master
        return False

    def _rolar(self, event):
        if not self._ponteiro_esta_aqui(event):
            return
        if self.conteudo.winfo_height() <= self.canvas.winfo_height():
            return
        if getattr(event, "num", None) == 4 or (event.delta and event.delta > 0):
            self.canvas.yview_scroll(-3, "units")
        else:
            self.canvas.yview_scroll(3, "units")


class _TelaBase(tk.Frame):
    """Parte comum às duas telas: rolagem, busca com atraso (debounce) e
    painel de formulário que abre/fecha no topo do conteúdo."""

    def __init__(self, parent, db, logger, ao_alterar=None):
        super().__init__(parent, bg=t.BG)
        t.Fontes.preparar(self)
        self.db = db
        self.logger = logger
        self.midia = midia_global
        self.ao_alterar = ao_alterar
        self._id_edicao = None
        self._busca_agendada = None
        self.var_busca = tk.StringVar()

        self.rolagem = RolagemVertical(self)
        self.rolagem.pack(fill="both", expand=True)
        self.pagina = self.rolagem.conteudo

    # ---------- busca ----------
    def _campo_busca(self, parent, dica):
        caixa = tk.Frame(parent, bg=t.SURFACE, highlightthickness=1,
                         highlightbackground=t.BORDER, highlightcolor=t.BORDER_STRONG)
        tk.Label(caixa, text="BUSCAR", bg=t.SURFACE, fg=t.TEXT_MUTED,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left", padx=(10, 6))
        entrada = tk.Entry(caixa, textvariable=self.var_busca, relief="flat", bd=0, bg=t.SURFACE,
                           fg=t.TEXT, insertbackground=t.TEXT, font=t.Fontes.corpo(11), width=38)
        entrada.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 10))
        tk.Label(caixa, text=dica, bg=t.SURFACE, fg=t.TEXT_MUTED,
                 font=t.Fontes.corpo(8)).pack(side="right", padx=(0, 10))
        entrada.bind("<KeyRelease>", self._busca_mudou)
        return caixa

    def _busca_mudou(self, _evento=None):
        if self._busca_agendada is not None:
            self.after_cancel(self._busca_agendada)
        self._busca_agendada = self.after(250, self._aplicar_busca)

    def _aplicar_busca(self):
        self._busca_agendada = None
        self.recarregar()

    # ---------- mensagens ----------
    def _mostrar(self, resultado, titulo, sucesso_visivel=False):
        """Mostra a mensagem do Resultado; devolve resultado.ok."""
        if resultado.ok:
            if sucesso_visivel:
                messagebox.showinfo(titulo, resultado.mensagem)
        else:
            messagebox.showwarning(titulo, resultado.mensagem)
        return resultado.ok

    def _avisar_alteracao(self):
        if self.ao_alterar:
            self.ao_alterar()

    def recarregar(self):  # implementado nas telas
        raise NotImplementedError


# =============================================================================
# Tela: Categorias
# =============================================================================
class CategoriasFrame(_TelaBase):
    COLUNAS = ["CÓDIGO", "EDITORIA / CADERNO", "DESCRITIVO EDITORIAL", "VOLUME & CARGA",
               "ÚLTIMA EDIÇÃO", "STATUS", "AÇÕES"]

    def __init__(self, parent, db, logger, ao_alterar=None):
        super().__init__(parent, db, logger, ao_alterar)
        self.servico = CategoriaService(db, logger)
        self._montar()
        self.recarregar()

    # ---------- montagem ----------
    def _montar(self):
        p = self.pagina
        _cabecalho(
            p, "Secretaria de Redação • Arquivo Central", "Caderno de Editorias & Categorias",
            "Gerenciamento da taxonomia editorial, cadernos temáticos e distribuição de "
            "matérias arquivadas no acervo do jornal.",
        )
        _filete(p)

        self.area_resumo = tk.Frame(p, bg=t.BG)
        self.area_resumo.pack(fill="x", padx=MARGEM, pady=(18, 0))

        barra = tk.Frame(p, bg=t.BG)
        barra.pack(fill="x", padx=MARGEM, pady=(22, 0))
        self._campo_busca(barra, "editoria, código ou termo").pack(side="left")
        t.botao_secundario(barra, "RELATÓRIO GERAL (CSV)", self._exportar_csv).pack(side="right")
        t.botao_primario(barra, "+ Adicionar categoria", lambda: self._abrir_form(None)).pack(
            side="right", padx=(0, 10))

        self.area_form = tk.Frame(p, bg=t.BG)
        self.area_form.pack(fill="x", padx=MARGEM)
        self._montar_form()

        self.cartao_tabela = tk.Frame(p, bg=t.SURFACE, highlightthickness=1,
                                      highlightbackground=t.BORDER)
        self.cartao_tabela.pack(fill="x", padx=MARGEM, pady=(18, 0))

        self._montar_nota(p)
        tk.Frame(p, bg=t.BG, height=24).pack()

    def _montar_form(self):
        self.painel_form = tk.Frame(self.area_form, bg=t.SURFACE, highlightthickness=1,
                                    highlightbackground=t.BORDER_STRONG)
        topo = tk.Frame(self.painel_form, bg=t.SURFACE)
        topo.pack(fill="x", padx=18, pady=(14, 4))
        self.titulo_form = tk.Label(topo, text="Cadastrar Nova Editoria", fg=t.TEXT, bg=t.SURFACE,
                                    font=t.Fontes.display(16))
        self.titulo_form.pack(side="left")
        _etiqueta(topo, "Entrada de galé", t.TEXT, t.SURFACE, tamanho=7).pack(side="left", padx=10)
        _link(topo, "FECHAR", self._fechar_form, t.TEXT_MUTED).pack(side="right")

        grade = tk.Frame(self.painel_form, bg=t.SURFACE)
        grade.pack(fill="x", padx=10, pady=(6, 0))
        for coluna in range(4):
            grade.grid_columnconfigure(coluna, weight=1, uniform="campo_cat")

        self.campo_nome = t.CampoEditorial(grade, "NOME DO CADERNO / EDITORIA *")
        self.campo_descricao = t.CampoEditorial(grade, "RESUMO EDITORIAL DA SEÇÃO *")
        self.campo_cor = CampoSelecao(grade, "LACRE / MATIZ TIPOGRÁFICA", CORES_CATEGORIA)
        self.campo_status = CampoSelecao(grade, "STATUS", STATUS_CATEGORIA)
        for coluna, campo in enumerate(
                (self.campo_nome, self.campo_descricao, self.campo_cor, self.campo_status)):
            campo.grid(row=0, column=coluna, sticky="ew", padx=8, pady=4)
        self.campo_descricao.entry.bind("<Return>", lambda e: self._salvar())
        self.campo_nome.entry.bind("<Return>", lambda e: self._salvar())

        botoes = tk.Frame(self.painel_form, bg=t.SURFACE)
        botoes.pack(fill="x", padx=18, pady=(10, 14))
        t.botao_primario(botoes, "Salvar editoria", self._salvar).pack(side="right")
        t.botao_secundario(botoes, "DESCARTAR", self._fechar_form).pack(side="right", padx=(0, 8))

    def _montar_nota(self, pai):
        nota = tk.Frame(pai, bg=PAINEL)
        nota.pack(fill="x", padx=MARGEM, pady=(22, 0))
        tk.Frame(nota, bg=t.TEXT, width=4).pack(side="left", fill="y")
        texto = tk.Frame(nota, bg=PAINEL)
        texto.pack(side="left", fill="x", padx=16, pady=12)
        tk.Label(texto, text="Manual de Padronização de Editorias", fg=t.TEXT, bg=PAINEL,
                 font=t.Fontes.display(13)).pack(anchor="w")
        tk.Label(
            texto, bg=PAINEL, fg=t.TEXT_MUTED, font=t.Fontes.corpo(9), justify="left", wraplength=820,
            text=("Um caderno só pode ser excluído depois que todas as matérias forem reatribuídas "
                  "a outra editoria. Enquanto isso, use o status \"Em Revisão\" para sinalizar "
                  "cadernos que aguardam validação do Editor-Chefe."),
        ).pack(anchor="w")

    # ---------- dados ----------
    def recarregar(self):
        resumo = self.servico.resumo()
        lista = self.servico.listar(self.var_busca.get())
        if not resumo.ok or not lista.ok:
            messagebox.showerror("Categorias", (resumo if not resumo.ok else lista).mensagem)
            return
        self._desenhar_resumo(resumo.dados)
        self._desenhar_tabela(lista.dados, resumo.dados)

    def _cartao_resumo(self, coluna, rotulo, selo, destaque, complemento, linha_final,
                       destaque_vermelho=False):
        cartao = tk.Frame(self.area_resumo, bg=t.SURFACE, highlightthickness=1,
                          highlightbackground=t.BORDER)
        cartao.grid(row=0, column=coluna, sticky="nsew", padx=(0 if coluna == 0 else 8, 0))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=16, pady=14)
        interno.pack(fill="both", expand=True)
        topo = tk.Frame(interno, bg=t.SURFACE)
        topo.pack(fill="x")
        tk.Label(topo, text=rotulo.upper(), fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        tk.Label(topo, text=selo.upper(), fg=t.PRIMARY, bg=FUNDO_MATIZ["rubro"], padx=5,
                 font=t.Fontes.corpo(7, "bold")).pack(side="right")
        valor = tk.Frame(interno, bg=t.SURFACE)
        valor.pack(fill="x", pady=(6, 6))
        tk.Label(valor, text=destaque, fg=t.PRIMARY if destaque_vermelho else t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(26)).pack(side="left")
        tk.Label(valor, text=complemento, fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(9)).pack(side="left", padx=(8, 0), anchor="s", pady=(0, 6))
        tk.Frame(interno, bg=t.BORDER, height=1).pack(fill="x")
        tk.Label(interno, text=linha_final, fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(9)).pack(anchor="w", pady=(6, 0))

    def _desenhar_resumo(self, r):
        for filho in self.area_resumo.winfo_children():
            filho.destroy()
        for coluna in range(3):
            self.area_resumo.grid_columnconfigure(coluna, weight=1, uniform="resumo")

        self._cartao_resumo(
            0, "Total de editorias ativas", "Registro ativo", f"{r['ativas']:02d}",
            "cadernos em circulação", f"{r['em_revisao']:02d} caderno(s) em revisão",
        )
        mais = r["mais_ativa"]
        if mais:
            self._cartao_resumo(
                1, "Caderno mais ativo", "Tempo real", mais["nome"], f"{mais['total']} matérias",
                f"{mais['percentual']:.1f}% do volume global da redação".replace(".", ","),
                destaque_vermelho=True,
            )
        else:
            self._cartao_resumo(1, "Caderno mais ativo", "Tempo real", "—", "sem matérias",
                                "Nenhuma matéria publicada ainda", destaque_vermelho=True)
        self._cartao_resumo(
            2, "Média de produção / caderno", "Média ponderada", f"{r['media_por_caderno']}",
            "matérias por caderno", f"{r['total_noticias']} matérias catalogadas no total",
        )

    def _desenhar_tabela(self, categorias, resumo):
        for filho in self.cartao_tabela.winfo_children():
            filho.destroy()

        faixa = tk.Frame(self.cartao_tabela, bg=PAINEL)
        faixa.pack(fill="x")
        tk.Label(faixa, text="CATÁLOGO OFICIAL DE CADERNOS  •  ORDENAÇÃO POR RELEVÂNCIA EDITORIAL",
                 fg=t.TEXT, bg=PAINEL, font=t.Fontes.corpo(8, "bold"), pady=8).pack(side="left", padx=14)
        tk.Label(faixa, text=f"■ {resumo['total_noticias']} Matérias Catalogadas", fg=t.TEXT,
                 bg=PAINEL, font=t.Fontes.corpo(8, "bold")).pack(side="right", padx=14)

        tabela = tk.Frame(self.cartao_tabela, bg=t.SURFACE)
        tabela.pack(fill="x")
        tabela.grid_columnconfigure(2, weight=1)
        minimos = [80, 190, 300, 170, 130, 110, 120]
        for coluna, minimo in enumerate(minimos):
            tabela.grid_columnconfigure(coluna, minsize=minimo)

        for coluna, titulo in enumerate(self.COLUNAS):
            tk.Label(tabela, text=titulo, fg=t.TEXT, bg=t.SURFACE, font=t.Fontes.corpo(8, "bold"),
                     anchor="w").grid(row=0, column=coluna, sticky="w", padx=12, pady=(10, 8))
        tk.Frame(tabela, bg=t.TEXT, height=2).grid(row=1, column=0, columnspan=7, sticky="ew")

        if not categorias:
            tk.Label(tabela, text="Nenhuma editoria encontrada.", fg=t.TEXT_MUTED, bg=t.SURFACE,
                     font=t.Fontes.corpo(11), pady=28).grid(row=2, column=0, columnspan=7)
            proxima_linha = 3
        else:
            maior = max(int(c["total_noticias"]) for c in categorias) or 1
            total_geral = resumo["total_noticias"] or 1
            linha = 2
            for cat in categorias:
                self._linha_categoria(tabela, linha, cat, maior, total_geral)
                tk.Frame(tabela, bg=t.BORDER, height=1).grid(
                    row=linha + 1, column=0, columnspan=7, sticky="ew")
                linha += 2
            proxima_linha = linha

        rodape = tk.Frame(self.cartao_tabela, bg=PAINEL_BAIXO)
        rodape.pack(fill="x")
        tk.Label(rodape, bg=PAINEL_BAIXO, fg=t.TEXT, font=t.Fontes.corpo(8, "bold"), pady=8,
                 text=f"Mostrando {len(categorias)} de {resumo['total']} editorias no catálogo",
                 ).pack(side="left", padx=14)

    def _linha_categoria(self, tabela, linha, cat, maior, total_geral):
        def celula(coluna, **opcoes):
            opcoes.setdefault("sticky", "w")
            opcoes.setdefault("padx", 12)
            opcoes.setdefault("pady", 12)
            return dict(row=linha, column=coluna, **opcoes)

        matiz = cat["cor"] if cat["cor"] in COR_MATIZ else "rubro"
        total = int(cat["total_noticias"])

        tk.Label(tabela, text=f"#CAT-{int(cat['id']):02d}", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.corpo(9, "bold")).grid(**celula(0, sticky="nw"))
        _etiqueta(tabela, cat["nome"], COR_MATIZ[matiz], t.SURFACE, tamanho=8).grid(
            **celula(1, sticky="nw"))
        tk.Label(tabela, text=cat["descricao"] or "—", fg=t.TEXT, bg=t.SURFACE, justify="left",
                 font=t.Fontes.corpo(10), wraplength=290, anchor="w").grid(**celula(2, sticky="nw"))

        volume = tk.Frame(tabela, bg=t.SURFACE)
        volume.grid(**celula(3, sticky="nw"))
        topo = tk.Frame(volume, bg=t.SURFACE)
        topo.pack(fill="x")
        tk.Label(topo, text=f"{total} matérias", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.corpo(9, "bold")).pack(side="left")
        tk.Label(topo, text=f"{round(100 * total / total_geral)}%", fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(8)).pack(side="right")
        barra = tk.Canvas(volume, width=140, height=6, bg=PAINEL_ALTO, highlightthickness=0, bd=0)
        barra.pack(pady=(4, 0))
        barra.create_rectangle(0, 0, int(140 * total / maior), 6, fill=COR_MATIZ[matiz], width=0)

        edicao = tk.Frame(tabela, bg=t.SURFACE)
        edicao.grid(**celula(4, sticky="nw"))
        tk.Label(edicao, text=data_relativa(cat["ultima_edicao"]).upper(), fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.corpo(9, "bold")).pack(anchor="w")
        por = f"Por {cat['ultimo_autor']}" if cat.get("ultimo_autor") else "Sem matérias"
        tk.Label(edicao, text=por, fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(8)).pack(anchor="w")

        em_revisao = cat["status"] == "em_revisao"
        cor_status = t.TEXT_MUTED if em_revisao else t.TEXT
        _etiqueta(tabela, ("" if em_revisao else "■ ") + STATUS_CATEGORIA.get(cat["status"], "Ativa"),
                  cor_status, t.SURFACE, tamanho=7).grid(**celula(5, sticky="nw"))

        acoes = tk.Frame(tabela, bg=t.SURFACE)
        acoes.grid(**celula(6, sticky="nw"))
        _link(acoes, "EDITAR", lambda c=cat: self._abrir_form(c)).pack(side="left")
        _link(acoes, "EXCLUIR", lambda c=cat: self._excluir(c), t.ERROR).pack(side="left", padx=(10, 0))

    # ---------- formulário ----------
    def _abrir_form(self, categoria):
        self._id_edicao = categoria["id"] if categoria else None
        if categoria:
            self.titulo_form.configure(text=f"Editar Editoria — #CAT-{int(categoria['id']):02d}")
            self.campo_nome.set(categoria["nome"])
            self.campo_descricao.set(categoria["descricao"] or "")
            self.campo_cor.set(categoria["cor"])
            self.campo_status.set(categoria["status"])
        else:
            self.titulo_form.configure(text="Cadastrar Nova Editoria")
            self.campo_nome.set("")
            self.campo_descricao.set("")
            self.campo_cor.set("rubro")
            self.campo_status.set("ativa")
        self.painel_form.pack(fill="x", pady=(18, 0))
        self.campo_nome.focus()

    def _fechar_form(self):
        self._id_edicao = None
        self.painel_form.pack_forget()

    def _salvar(self):
        dados = (self.campo_nome.get(), self.campo_descricao.get(),
                 self.campo_cor.get(), self.campo_status.get())
        if self._id_edicao is None:
            resultado = self.servico.criar(*dados)
        else:
            resultado = self.servico.atualizar(self._id_edicao, *dados)
        if self._mostrar(resultado, "Categorias"):
            self._fechar_form()
            self.recarregar()
            self._avisar_alteracao()

    def _excluir(self, categoria):
        if not messagebox.askyesno(
                "Excluir editoria",
                f"Excluir a editoria \"{categoria['nome']}\"?\nEssa ação não pode ser desfeita."):
            return
        if self._mostrar(self.servico.excluir(categoria["id"]), "Categorias"):
            self.recarregar()
            self._avisar_alteracao()

    # ---------- relatório ----------
    def _exportar_csv(self):
        resultado = self.servico.listar()
        if not self._mostrar(resultado, "Relatório"):
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar relatório geral de categorias", defaultextension=".csv",
            initialfile="relatorio_categorias.csv", filetypes=[("CSV", "*.csv")])
        if not caminho:
            return
        try:
            with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
                escritor = csv.writer(arquivo, delimiter=";")
                escritor.writerow(["Código", "Editoria", "Descritivo", "Matérias", "Status",
                                   "Última edição", "Último autor"])
                for c in resultado.dados:
                    ultima = _como_data(c["ultima_edicao"])
                    escritor.writerow([
                        f"#CAT-{int(c['id']):02d}", c["nome"], c["descricao"] or "",
                        c["total_noticias"], STATUS_CATEGORIA.get(c["status"], c["status"]),
                        ultima.strftime("%d/%m/%Y") if ultima else "", c["ultimo_autor"] or "",
                    ])
            self.logger.info(f"Relatório de categorias exportado para {caminho}")
            messagebox.showinfo("Relatório", "Relatório geral salvo com sucesso.")
        except OSError as erro:
            self.logger.error("Erro ao exportar relatório de categorias", erro)
            messagebox.showerror("Relatório", "Não foi possível salvar o arquivo.")


# =============================================================================
# Tela: Autores
# =============================================================================
class AutoresFrame(_TelaBase):
    POR_PAGINA = 6
    COLUNAS_GRADE = 3

    def __init__(self, parent, db, logger, ao_alterar=None):
        super().__init__(parent, db, logger, ao_alterar)
        self.servico = AutorService(db, logger, midia_global)
        self._funcao = ""          # "" = Todos
        self._pagina_atual = 1
        self._autores = []
        self._contagem = {"todos": 0}
        self._montar()
        self.recarregar()

    # ---------- montagem ----------
    def _montar(self):
        p = self.pagina
        linha = _cabecalho(
            p, "Corpo Editorial Permanente", "Quadro de Redação & Jornalistas Cadastrados",
            "Gestão dos repórteres, colunistas, editores setoriais e correspondentes da Gazeta.",
        )
        t.botao_primario(linha, "+ Adicionar autor", lambda: self._abrir_form(None)).pack(
            side="right", anchor="s")

        self.area_form = tk.Frame(p, bg=t.BG)
        self.area_form.pack(fill="x", padx=MARGEM)
        self._montar_form()

        filtros = tk.Frame(p, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        filtros.pack(fill="x", padx=MARGEM, pady=(18, 0))
        interno = tk.Frame(filtros, bg=t.SURFACE, padx=12, pady=10)
        interno.pack(fill="x")
        self._campo_busca(interno, "nome, editoria ou credencial").pack(side="left")
        self.area_chips = tk.Frame(interno, bg=t.SURFACE)
        self.area_chips.pack(side="left", padx=(16, 0))

        self.area_cartoes = tk.Frame(p, bg=t.BG)
        self.area_cartoes.pack(fill="x", padx=MARGEM - 8, pady=(10, 0))
        for coluna in range(self.COLUNAS_GRADE):
            self.area_cartoes.grid_columnconfigure(coluna, weight=1, uniform="cartao_autor")

        self.area_paginacao = tk.Frame(p, bg=t.SURFACE, highlightthickness=1,
                                       highlightbackground=t.BORDER)
        self.area_paginacao.pack(fill="x", padx=MARGEM, pady=(10, 0))
        tk.Frame(p, bg=t.BG, height=24).pack()

    def _montar_form(self):
        self.painel_form = tk.Frame(self.area_form, bg=t.SURFACE, highlightthickness=1,
                                    highlightbackground=t.BORDER_STRONG)
        topo = tk.Frame(self.painel_form, bg=t.SURFACE)
        topo.pack(fill="x", padx=18, pady=(14, 4))
        self.titulo_form = tk.Label(topo, text="Novo Credenciamento de Jornalista", fg=t.TEXT,
                                    bg=t.SURFACE, font=t.Fontes.display(16))
        self.titulo_form.pack(side="left")
        _link(topo, "FECHAR", self._fechar_form, t.TEXT_MUTED).pack(side="right")

        grade = tk.Frame(self.painel_form, bg=t.SURFACE)
        grade.pack(fill="x", padx=10, pady=(6, 0))
        for coluna in range(3):
            grade.grid_columnconfigure(coluna, weight=1, uniform="campo_autor")

        self.campo_nome = t.CampoEditorial(grade, "NOME COMPLETO *")
        self.campo_email = t.CampoEditorial(grade, "E-MAIL INSTITUCIONAL")
        self.campo_funcao = CampoSelecao(grade, "FUNÇÃO", FUNCOES_AUTOR)
        self.campo_cargo = t.CampoEditorial(grade, "CARGO / EDITORIA PRINCIPAL",
                                            dica="EX.: EDITORA DE POLÍTICA • BRASÍLIA")
        self.campo_registro = t.CampoEditorial(grade, "REGISTRO PROFISSIONAL (MTB / CÉDULA)")
        self.campo_status = CampoSelecao(grade, "STATUS", STATUS_AUTOR)
        campos = (self.campo_nome, self.campo_email, self.campo_funcao,
                  self.campo_cargo, self.campo_registro, self.campo_status)
        for indice, campo in enumerate(campos):
            campo.grid(row=indice // 3, column=indice % 3, sticky="ew", padx=8, pady=6)

        self.campo_foto = CampoImagem(self.painel_form, "FOTO DO JORNALISTA", "autores",
                                      largura=110, altura=110)
        self.campo_foto.pack(anchor="w", padx=18, pady=(4, 0))
        self.campo_bio = CampoTextoLongo(self.painel_form, "BIOGRAFIA CURTA & LINHA EDITORIAL", 3)
        self.campo_bio.pack(fill="x", padx=18, pady=(8, 0))

        botoes = tk.Frame(self.painel_form, bg=t.SURFACE)
        botoes.pack(fill="x", padx=18, pady=(12, 14))
        self.botao_salvar = t.botao_primario(botoes, "Registrar credencial", self._salvar)
        self.botao_salvar.pack(side="right")
        t.botao_secundario(botoes, "CANCELAR", self._fechar_form).pack(side="right", padx=(0, 8))

    # ---------- dados ----------
    def recarregar(self):
        contagem = self.servico.contagem_por_funcao()
        lista = self.servico.listar(self.var_busca.get(), self._funcao)
        if not contagem.ok or not lista.ok:
            messagebox.showerror("Autores", (contagem if not contagem.ok else lista).mensagem)
            return
        self._contagem = contagem.dados
        self._autores = lista.dados
        self._desenhar_chips()
        self._desenhar_cartoes()

    def _desenhar_chips(self):
        for filho in self.area_chips.winfo_children():
            filho.destroy()
        opcoes = [("", f"Todos ({self._contagem['todos']})")] + [
            (chave, f"{FUNCOES_AUTOR_PLURAL[chave]} ({self._contagem.get(chave, 0)})")
            for chave in FUNCOES_AUTOR
        ]
        for chave, rotulo in opcoes:
            ativo = chave == self._funcao
            chip = tk.Label(
                self.area_chips, text=rotulo.upper(), cursor="hand2", padx=10, pady=6,
                bg=t.TEXT if ativo else PAINEL, fg="#FFFFFF" if ativo else t.TEXT,
                font=t.Fontes.corpo(8, "bold"),
            )
            chip.pack(side="left", padx=(0, 4))
            chip.bind("<Button-1>", lambda e, c=chave: self._filtrar_funcao(c))

    def _filtrar_funcao(self, chave):
        self._funcao = chave
        self._pagina_atual = 1
        self.recarregar()

    def _aplicar_busca(self):
        self._pagina_atual = 1
        super()._aplicar_busca()

    # ---------- cartões ----------
    def _desenhar_cartoes(self):
        for filho in self.area_cartoes.winfo_children():
            filho.destroy()

        total = len(self._autores)
        paginas = max(1, math.ceil(total / self.POR_PAGINA))
        self._pagina_atual = min(max(1, self._pagina_atual), paginas)
        inicio = (self._pagina_atual - 1) * self.POR_PAGINA
        visiveis = self._autores[inicio:inicio + self.POR_PAGINA]

        if not visiveis:
            tk.Label(self.area_cartoes, text="Nenhum jornalista encontrado.", fg=t.TEXT_MUTED,
                     bg=t.BG, font=t.Fontes.corpo(11), pady=40).grid(
                row=0, column=0, columnspan=self.COLUNAS_GRADE)
        for posicao, autor in enumerate(visiveis):
            cartao = self._cartao_autor(self.area_cartoes, autor)
            cartao.grid(row=posicao // self.COLUNAS_GRADE, column=posicao % self.COLUNAS_GRADE,
                        sticky="nsew", padx=8, pady=8)
        self._desenhar_paginacao(len(visiveis), total, paginas)

    def _cartao_autor(self, pai, autor):
        matiz = MATIZ_DA_FUNCAO.get(autor["funcao"], "rubro")
        cor = COR_MATIZ[matiz]
        cartao = tk.Frame(pai, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)

        corpo = tk.Frame(cartao, bg=t.SURFACE, padx=16, pady=14)
        corpo.pack(fill="both", expand=True)

        topo = tk.Frame(corpo, bg=t.SURFACE)
        topo.pack(fill="x")
        inicial = (autor["nome"][:1] or "?").upper()
        foto = self.midia.carregar_tk(autor.get("foto"), 56, 56)
        if foto is not None:
            # foto com a inicial num selo no canto, como no protótipo
            moldura = tk.Frame(topo, width=56, height=56, bg=cor)
            moldura.pack(side="left")
            moldura.pack_propagate(False)
            imagem = tk.Label(moldura, image=foto, bd=0)
            imagem.image = foto
            imagem.place(x=0, y=0, relwidth=1, relheight=1)
            tk.Label(moldura, text=inicial, fg="#FFFFFF", bg=cor, width=2,
                     font=t.Fontes.corpo(8, "bold")).place(relx=1.0, rely=1.0, anchor="se")
        else:
            tk.Label(topo, text=inicial, fg="#FFFFFF", bg=cor, width=3, height=1,
                     font=t.Fontes.display(20)).pack(side="left")
        acoes = tk.Frame(topo, bg=t.SURFACE)
        acoes.pack(side="right", anchor="n")
        _link(acoes, "EDITAR", lambda a=autor: self._abrir_form(a)).pack(side="left")
        _link(acoes, "EXCLUIR", lambda a=autor: self._excluir(a), t.ERROR).pack(side="left", padx=(8, 0))

        cargo = autor["cargo"] or FUNCOES_AUTOR.get(autor["funcao"], "")
        _etiqueta(corpo, cargo, cor, FUNDO_MATIZ[matiz], borda=False, tamanho=7).pack(
            anchor="w", pady=(12, 0))
        tk.Label(corpo, text=autor["nome"], fg=t.TEXT, bg=t.SURFACE, anchor="w", justify="left",
                 font=t.Fontes.display(16), wraplength=280).pack(anchor="w", pady=(4, 2))
        identificacao = " • ".join(x for x in (autor["registro"], autor["email"]) if x)
        tk.Label(corpo, text=identificacao or "Sem registro nem e-mail cadastrados",
                 fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(8, "bold"), anchor="w",
                 justify="left", wraplength=280).pack(anchor="w")
        tk.Label(corpo, text=_resumir(autor["bio"]) or "Sem biografia cadastrada.", fg=t.TEXT,
                 bg=t.SURFACE, font=t.Fontes.corpo(9), anchor="w", justify="left",
                 wraplength=280).pack(anchor="w", pady=(6, 10))

        caixa = tk.Frame(corpo, bg=PAINEL_BAIXO, padx=10, pady=8)
        caixa.pack(fill="x", side="bottom")
        for lado, rotulo, valor, destaque in (
                ("left", "VOLUME PUBLICADO", f"{int(autor['total_noticias'])} Matérias", False),
                ("right", "ÚLTIMA PUBLICAÇÃO", data_relativa(autor["ultima_publicacao"]), True)):
            bloco = tk.Frame(caixa, bg=PAINEL_BAIXO)
            bloco.pack(side=lado)
            tk.Label(bloco, text=rotulo, fg=t.TEXT, bg=PAINEL_BAIXO,
                     font=t.Fontes.corpo(7, "bold")).pack(anchor="w" if lado == "left" else "e")
            tk.Label(bloco, text=valor, fg=t.PRIMARY if destaque else t.TEXT, bg=PAINEL_BAIXO,
                     font=t.Fontes.display(13)).pack(anchor="w" if lado == "left" else "e")

        rodape = tk.Frame(cartao, bg=PAINEL_ALTO, padx=16, pady=8)
        rodape.pack(fill="x")
        tk.Label(rodape, text=f"STATUS: {STATUS_AUTOR.get(autor['status'], '').upper()}", fg=t.TEXT,
                 bg=PAINEL_ALTO, font=t.Fontes.corpo(8, "bold")).pack(side="left")
        _link(rodape, "VER MATÉRIAS →", lambda a=autor: self._ver_materias(a), t.PRIMARY).pack(side="right")
        return cartao

    def _desenhar_paginacao(self, exibindo, total, paginas):
        for filho in self.area_paginacao.winfo_children():
            filho.destroy()
        interno = tk.Frame(self.area_paginacao, bg=t.SURFACE, padx=12, pady=10)
        interno.pack(fill="x")
        tk.Label(interno, text=f"EXIBINDO {exibindo} DE {total} JORNALISTAS CREDENCIADOS",
                 fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(8, "bold")).pack(side="left")

        navegacao = tk.Frame(interno, bg=t.SURFACE)
        navegacao.pack(side="right")

        def botao(texto, destino=None, ativo=False):
            """destino=None deixa o botão desabilitado (cinza, sem clique)."""
            habilitado = destino is not None
            rotulo = tk.Label(
                navegacao, text=texto, padx=10, pady=5,
                bg=t.TEXT if ativo else (PAINEL if habilitado else t.SURFACE),
                fg="#FFFFFF" if ativo else (t.TEXT if habilitado else t.BORDER),
                font=t.Fontes.corpo(8, "bold"), cursor="hand2" if habilitado else "",
            )
            rotulo.pack(side="left", padx=2)
            if habilitado and not ativo:
                rotulo.bind("<Button-1>", lambda e, d=destino: self._ir_para_pagina(d))

        atual = self._pagina_atual
        botao("‹ ANTERIOR", atual - 1 if atual > 1 else None)
        for numero in _paginas_visiveis(atual, paginas):
            if numero is None:
                tk.Label(navegacao, text="…", bg=t.SURFACE, fg=t.TEXT_MUTED).pack(side="left")
            else:
                botao(str(numero), numero, ativo=numero == atual)
        botao("PRÓXIMA ›", atual + 1 if atual < paginas else None)

    def _ir_para_pagina(self, numero):
        self._pagina_atual = numero
        self._desenhar_cartoes()

    # ---------- formulário ----------
    def _abrir_form(self, autor):
        self._id_edicao = autor["id"] if autor else None
        if autor:
            self.titulo_form.configure(text=f"Editar Credencial — {autor['nome']}")
            self.botao_salvar.configure(text="SALVAR ALTERAÇÕES")
        else:
            self.titulo_form.configure(text="Novo Credenciamento de Jornalista")
            self.botao_salvar.configure(text="REGISTRAR CREDENCIAL")
        self.campo_nome.set(autor["nome"] if autor else "")
        self.campo_email.set(autor["email"] or "" if autor else "")
        self.campo_funcao.set(autor["funcao"] if autor else "reporter")
        self.campo_cargo.set(autor["cargo"] or "" if autor else "")
        self.campo_registro.set(autor["registro"] or "" if autor else "")
        self.campo_status.set(autor["status"] if autor else "ativo")
        self.campo_bio.set(autor["bio"] or "" if autor else "")
        self.campo_foto.definir(autor["foto"] if autor else None)
        self.painel_form.pack(fill="x", pady=(18, 0))
        self.campo_nome.focus()

    def _fechar_form(self):
        self._id_edicao = None
        self.campo_foto.limpar()   # apaga a cópia provisória de uma foto não salva
        self.painel_form.pack_forget()

    def _salvar(self):
        dados = dict(
            nome=self.campo_nome.get(), email=self.campo_email.get(),
            funcao=self.campo_funcao.get(), cargo=self.campo_cargo.get(),
            registro=self.campo_registro.get(), status=self.campo_status.get(),
            bio=self.campo_bio.get(), foto=self.campo_foto.caminho,
        )
        if self._id_edicao is None:
            resultado = self.servico.criar(**dados)
        else:
            resultado = self.servico.atualizar(self._id_edicao, **dados)
        if self._mostrar(resultado, "Autores"):
            self.campo_foto.confirmar_salvo()
            self._fechar_form()
            self.recarregar()
            self._avisar_alteracao()

    def _excluir(self, autor):
        if not messagebox.askyesno(
                "Excluir jornalista",
                f"Excluir o cadastro de \"{autor['nome']}\"?\nEssa ação não pode ser desfeita."):
            return
        if self._mostrar(self.servico.excluir(autor["id"]), "Autores"):
            self.recarregar()
            self._avisar_alteracao()

    # ---------- ver matérias ----------
    def _ver_materias(self, autor):
        resultado = self.servico.materias_do_autor(autor["id"])
        if not self._mostrar(resultado, "Autores"):
            return
        janela = tk.Toplevel(self)
        janela.title(f"Matérias de {autor['nome']}")
        janela.configure(bg=t.SURFACE)
        janela.geometry("640x380")
        janela.transient(self.winfo_toplevel())
        tk.Label(janela, text=f"Matérias de {autor['nome']}", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(16)).pack(anchor="w", padx=18, pady=(16, 8))
        colunas = ("titulo", "categoria", "data")
        arvore = ttk.Treeview(janela, columns=colunas, show="headings", height=10)
        for coluna, titulo, largura in (("titulo", "Título", 340), ("categoria", "Editoria", 150),
                                        ("data", "Publicação", 100)):
            arvore.heading(coluna, text=titulo)
            arvore.column(coluna, width=largura, anchor="w")
        for materia in resultado.dados:
            data = _como_data(materia["data_publicacao"])
            arvore.insert("", "end", values=(
                materia["titulo"], materia["categoria"], data.strftime("%d/%m/%Y") if data else ""))
        arvore.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        if not resultado.dados:
            tk.Label(janela, text="Este jornalista ainda não publicou matérias.", fg=t.TEXT_MUTED,
                     bg=t.SURFACE, font=t.Fontes.corpo(10)).pack(pady=(0, 8))
        t.botao_secundario(janela, "FECHAR", janela.destroy).pack(pady=(0, 14))
