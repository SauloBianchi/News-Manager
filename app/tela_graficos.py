"""
tela_graficos.py
Tela "Gráficos & Análise" do NewsManager, reproduzindo em Tkinter o protótipo
do Stitch (gr_ficos_e_an_lise_newsmanager) com os gráficos do matplotlib
embutidos na janela:

- cabeçalho "Caderno de Análise Editorial & Métricas de Cobertura" com os
  botões Exportar relatório (PDF) e Exportar CSV;
- barra de filtros: período (7/30/90 dias, 12 meses, este ano, todo o
  período ou datas personalizadas), editoria, jornalista e estado da matéria.
  Tudo na tela (indicadores, gráficos, tabela e textos) obedece aos filtros;
- quatro indicadores (total, editorias em operação, média de leituras,
  tempo médio de leitura) com comparação com o período anterior;
- gráfico de barras "Notícias por Categoria", evolução no período,
  "Produtividade por Autor" (com tabela completa), "Volume ao Longo da
  Semana" e "Pipeline Redatorial";
- "Leitura dos dados" (frases geradas dos números) e "Meta do período"
  (editável; o valor e o último filtro ficam salvos em config/graficos.json).

Os números vêm de EstatisticasService e os desenhos de app/graficos.py.
"""

import csv
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from . import theme as t
from .estatisticas import (
    ESTADOS,
    PERIODOS,
    EstatisticasService,
    FiltroEstatisticas,
    PreferenciasGraficos,
    abreviar_tempo,
    fmt_dec,
    fmt_int,
    fmt_pct,
    interpretar_data_br,
)
from .graficos import (
    altura_distribuicao,
    descricao_filtros,
    exportar_pdf,
    figura_distribuicao,
    figura_semana,
    figura_serie,
)
from .telas_cadastros import (
    MARGEM,
    PAINEL,
    PAINEL_ALTO,
    PAINEL_BAIXO,
    _cabecalho,
    _filete,
    _link,
    _TelaBase,
)

FUNDO_ROSA = "#F4E1DE"
COR_AZUL = "#4F5E81"
COR_SEPIA = "#5A4426"
META_PADRAO = 100
TIQUE_ATUALIZACAO_MS = 60_000
GRANULARIDADE = {"dia": "por dia", "semana": "por semana", "mes": "por mês"}


class GraficosFrame(_TelaBase):
    def __init__(self, parent, db, logger, ao_alterar=None, preferencias=None):
        super().__init__(parent, db, logger, ao_alterar)
        self.servico = EstatisticasService(db, logger)
        self.preferencias = preferencias or PreferenciasGraficos()
        self.dados = None
        self._canvases = []
        self._carregando = False
        self._chaves_categoria = [None]
        self._chaves_autor = [None]
        self._nomes_categorias = {}
        self._nomes_autores = {}
        self._chaves_periodo = list(PERIODOS)
        self._chaves_estado = list(ESTADOS)
        self.var_inicio = tk.StringVar()
        self.var_fim = tk.StringVar()
        self.var_meta = tk.StringVar(value=str(META_PADRAO))

        guardado = self.preferencias.carregar()
        self._montar()
        self._aplicar_preferencias(guardado)
        self.recarregar()
        self.after(TIQUE_ATUALIZACAO_MS, self._tique)

    # =====================================================================
    # Montagem
    # =====================================================================
    def _montar(self):
        p = self.pagina
        linha = _cabecalho(
            p, "Caderno especial de métricas • Seção V", "Caderno de Análise Editorial & Métricas de Cobertura",
            "Auditoria quantitativa da tiragem digital, vazão de redação por editoria e engajamento leitor consolidado.")
        botoes = tk.Frame(linha, bg=t.BG)
        botoes.pack(side="right", anchor="s")
        t.botao_primario(botoes, "Exportar relatório PDF", self._exportar_pdf).pack(side="top", fill="x")
        t.botao_secundario(botoes, "EXPORTAR CSV", self._exportar_csv).pack(side="top", fill="x", pady=(6, 0))
        _filete(p)

        self._montar_filtros(p)

        self.area_kpis = tk.Frame(p, bg=t.BG)
        self.area_kpis.pack(fill="x", padx=MARGEM, pady=(16, 0))
        for coluna in range(4):
            self.area_kpis.grid_columnconfigure(coluna, weight=1, uniform="kpi")

        corpo = tk.Frame(p, bg=t.BG)
        corpo.pack(fill="x", padx=MARGEM, pady=(16, 0))
        corpo.grid_columnconfigure(0, weight=1)
        corpo.grid_columnconfigure(1, minsize=380)
        esquerda = tk.Frame(corpo, bg=t.BG)
        esquerda.grid(row=0, column=0, sticky="new", padx=(0, 16))
        direita = tk.Frame(corpo, bg=t.BG)
        direita.grid(row=0, column=1, sticky="new")
        self._montar_distribuicao(esquerda)
        self._montar_evolucao(esquerda)
        self._montar_autores(direita)
        self._montar_semana(direita)
        self._montar_pipeline(direita)

        rodape = tk.Frame(p, bg=t.BG)
        rodape.pack(fill="x", padx=MARGEM, pady=(16, 0))
        rodape.grid_columnconfigure(0, weight=3, uniform="rodape")
        rodape.grid_columnconfigure(1, weight=2, uniform="rodape")
        self._montar_leitura(rodape)
        self._montar_meta(rodape)
        tk.Frame(p, bg=t.BG, height=28).pack()

    def _cartao(self, pai, **opcoes):
        cartao = tk.Frame(pai, bg=opcoes.pop("bg", t.SURFACE), highlightthickness=1,
                          highlightbackground=t.BORDER, **opcoes)
        return cartao

    # ---------- filtros ----------
    def _combo(self, pai, rotulo, opcoes, largura, ao_mudar):
        quadro = tk.Frame(pai, bg=t.SURFACE)
        tk.Label(quadro, text=rotulo, fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(7, "bold")).pack(anchor="w")
        combo = ttk.Combobox(quadro, values=list(opcoes), state="readonly", width=largura,
                             font=t.Fontes.corpo(10))
        combo.pack(anchor="w", pady=(2, 0), ipady=2)
        combo.bind("<<ComboboxSelected>>", lambda e: ao_mudar())
        if opcoes:
            combo.current(0)
        return quadro, combo

    def _montar_filtros(self, pai):
        barra = self._cartao(pai)
        barra.pack(fill="x", padx=MARGEM, pady=(16, 0))
        interno = tk.Frame(barra, bg=t.SURFACE, padx=14, pady=10)
        interno.pack(fill="x")
        linha = tk.Frame(interno, bg=t.SURFACE)
        linha.pack(fill="x")
        tk.Label(linha, text="FILTROS", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left", padx=(0, 14), anchor="s", pady=(0, 6))
        q, self.combo_periodo = self._combo(linha, "PERÍODO", list(PERIODOS.values()), 18, self._ao_mudar_periodo)
        q.pack(side="left", padx=(0, 12))
        q, self.combo_categoria = self._combo(linha, "EDITORIA", ["Todas as editorias"], 24, self._ao_mudar_filtro)
        q.pack(side="left", padx=(0, 12))
        q, self.combo_autor = self._combo(linha, "JORNALISTA", ["Todos os jornalistas"], 24, self._ao_mudar_filtro)
        q.pack(side="left", padx=(0, 12))
        q, self.combo_estado = self._combo(linha, "ESTADO DA MATÉRIA", list(ESTADOS.values()), 16, self._ao_mudar_filtro)
        q.pack(side="left", padx=(0, 12))
        _link(linha, "LIMPAR FILTROS", self._limpar_filtros, t.PRIMARY).pack(side="right", anchor="s", pady=(0, 8))
        _link(linha, "↻ ATUALIZAR", self.recarregar, t.TEXT).pack(side="right", anchor="s", pady=(0, 8), padx=(0, 16))

        self.area_personalizado = tk.Frame(interno, bg=t.SURFACE)
        tk.Label(self.area_personalizado, text="DE", fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        for variavel in (self.var_inicio, self.var_fim):
            tk.Entry(self.area_personalizado, textvariable=variavel, width=12, relief="flat", bg=PAINEL,
                     fg=t.TEXT, font=t.Fontes.corpo(10), highlightthickness=1,
                     highlightbackground=t.BORDER).pack(side="left", padx=6, ipady=3)
            if variavel is self.var_inicio:
                tk.Label(self.area_personalizado, text="ATÉ", fg=t.TEXT_MUTED, bg=t.SURFACE,
                         font=t.Fontes.corpo(8, "bold")).pack(side="left")
        tk.Label(self.area_personalizado, text="(dd/mm/aaaa)", fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(8)).pack(side="left", padx=(2, 10))
        t.botao_secundario(self.area_personalizado, "APLICAR PERÍODO", self._ao_mudar_filtro).pack(side="left")

        self.rotulo_resumo = tk.Label(interno, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w",
                                      font=t.Fontes.corpo(8, "bold"))
        self.rotulo_resumo.pack(fill="x", pady=(8, 0))

    # ---------- cartões principais ----------
    def _montar_distribuicao(self, pai):
        cartao = self._cartao(pai)
        cartao.pack(fill="x")
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=20, pady=18)
        interno.pack(fill="x")
        topo = tk.Frame(interno, bg=t.SURFACE)
        topo.pack(fill="x")
        tk.Label(topo, text="MORFOLOGIA DE CONTEÚDO", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        self.rotulo_total_dist = tk.Label(topo, text="", fg=t.TEXT, bg=t.SURFACE,
                                          font=t.Fontes.corpo(8, "bold"))
        self.rotulo_total_dist.pack(side="right")
        tk.Label(interno, text="Distribuição Editorial: Notícias por Categoria", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(20), anchor="w").pack(fill="x", pady=(4, 0))
        self.rotulo_sub_dist = tk.Label(interno, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w",
                                        font=t.Fontes.corpo(9))
        self.rotulo_sub_dist.pack(fill="x", pady=(0, 10))
        self.area_fig_dist = tk.Frame(interno, bg=t.SURFACE)
        self.area_fig_dist.pack(fill="x")
        self.nota_dist = tk.Frame(interno, bg=PAINEL_BAIXO, padx=12, pady=8)
        self.nota_dist.pack(fill="x", pady=(12, 0))
        self.rotulo_nota_dist = tk.Label(self.nota_dist, text="", fg=t.TEXT, bg=PAINEL_BAIXO, anchor="w",
                                         justify="left", font=t.Fontes.corpo(9), wraplength=620)
        self.rotulo_nota_dist.pack(side="left", fill="x", expand=True)
        self.rotulo_escala = tk.Label(self.nota_dist, text="", fg=t.TEXT_MUTED, bg=PAINEL_BAIXO,
                                      font=t.Fontes.corpo(7, "bold"))
        self.rotulo_escala.pack(side="right")

    def _montar_evolucao(self, pai):
        cartao = self._cartao(pai)
        cartao.pack(fill="x", pady=(16, 0))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=20, pady=18)
        interno.pack(fill="x")
        tk.Label(interno, text="SÉRIE TEMPORAL", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        tk.Label(interno, text="Evolução no Período", fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.display(20)).pack(fill="x", pady=(4, 0))
        self.rotulo_sub_serie = tk.Label(interno, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w",
                                         font=t.Fontes.corpo(9))
        self.rotulo_sub_serie.pack(fill="x", pady=(0, 8))
        self.area_fig_serie = tk.Frame(interno, bg=t.SURFACE)
        self.area_fig_serie.pack(fill="x")

    def _montar_autores(self, pai):
        cartao = self._cartao(pai)
        cartao.pack(fill="x")
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=18, pady=16)
        interno.pack(fill="x")
        tk.Label(interno, text="ESCALAÇÃO ATIVA", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        tk.Label(interno, text="Produtividade por Autor", fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.display(17)).pack(fill="x", pady=(2, 8))
        self.area_autores = tk.Frame(interno, bg=t.SURFACE)
        self.area_autores.pack(fill="x")
        rodape = tk.Frame(interno, bg=t.SURFACE)
        rodape.pack(fill="x", pady=(10, 0))
        self.rotulo_equipe = tk.Label(rodape, text="", fg=t.TEXT_MUTED, bg=t.SURFACE,
                                      font=t.Fontes.corpo(7, "bold"))
        self.rotulo_equipe.pack(side="left")
        _link(rodape, "VER TABELA COMPLETA →", self._abrir_tabela_completa, t.PRIMARY).pack(side="right")

    def _montar_semana(self, pai):
        cartao = self._cartao(pai)
        cartao.pack(fill="x", pady=(16, 0))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=18, pady=16)
        interno.pack(fill="x")
        tk.Label(interno, text="CADÊNCIA REDATORIAL", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        tk.Label(interno, text="Volume ao Longo da Semana", fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.display(17)).pack(fill="x", pady=(2, 0))
        tk.Label(interno, text="Média diária de matérias por dia da semana, no período filtrado.",
                 fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left", wraplength=330,
                 font=t.Fontes.corpo(9)).pack(fill="x", pady=(0, 8))
        self.area_fig_semana = tk.Frame(interno, bg=t.SURFACE)
        self.area_fig_semana.pack(fill="x")
        self.caixa_observacao = tk.Frame(interno, bg=PAINEL_BAIXO, padx=10, pady=8)
        self.caixa_observacao.pack(fill="x", pady=(10, 0))
        tk.Label(self.caixa_observacao, text="OBSERVAÇÃO CRÍTICA:", fg=t.PRIMARY, bg=PAINEL_BAIXO,
                 font=t.Fontes.corpo(7, "bold")).pack(anchor="w")
        self.rotulo_observacao = tk.Label(self.caixa_observacao, text="", fg=t.TEXT, bg=PAINEL_BAIXO,
                                          anchor="w", justify="left", wraplength=320, font=t.Fontes.corpo(9))
        self.rotulo_observacao.pack(anchor="w", pady=(2, 0))

    def _montar_pipeline(self, pai):
        cartao = self._cartao(pai, bg=PAINEL)
        cartao.pack(fill="x", pady=(16, 0))
        interno = tk.Frame(cartao, bg=PAINEL, padx=18, pady=14)
        interno.pack(fill="x")
        tk.Label(interno, text="● SINCRONIZAÇÃO EM TEMPO REAL", fg=t.PRIMARY, bg=PAINEL,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        linha = tk.Frame(interno, bg=PAINEL)
        linha.pack(fill="x", pady=(2, 0))
        tk.Label(linha, text="Pipeline Redatorial", fg=t.TEXT, bg=PAINEL, font=t.Fontes.display(16)).pack(side="left")
        self.chip_pipeline = tk.Label(linha, text="", fg=t.TEXT, bg=PAINEL_ALTO, padx=6, pady=2,
                                      font=t.Fontes.corpo(7, "bold"))
        self.chip_pipeline.pack(side="right")
        self.rotulo_pipeline = tk.Label(interno, text="", fg=t.TEXT_MUTED, bg=PAINEL, anchor="w",
                                        justify="left", wraplength=330, font=t.Fontes.corpo(9))
        self.rotulo_pipeline.pack(fill="x", pady=(6, 0))
        self.rotulo_atualizado = tk.Label(interno, text="", fg=t.TEXT_MUTED, bg=PAINEL, anchor="w",
                                          font=t.Fontes.corpo(7, "bold"))
        self.rotulo_atualizado.pack(fill="x", pady=(6, 0))

    def _montar_leitura(self, pai):
        cartao = self._cartao(pai)
        cartao.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=20, pady=16)
        interno.pack(fill="both", expand=True)
        tk.Label(interno, text="LEITURA DOS DADOS", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        tk.Label(interno, text="Nota da Mesa de Análise", fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.display(16)).pack(fill="x", pady=(2, 8))
        self.area_insights = tk.Frame(interno, bg=t.SURFACE)
        self.area_insights.pack(fill="x")

    def _montar_meta(self, pai):
        cartao = self._cartao(pai, bg=PAINEL)
        cartao.grid(row=0, column=1, sticky="nsew")
        interno = tk.Frame(cartao, bg=PAINEL, padx=20, pady=16)
        interno.pack(fill="both", expand=True)
        tk.Label(interno, text="META DO PERÍODO", fg=t.PRIMARY, bg=PAINEL,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        linha = tk.Frame(interno, bg=PAINEL)
        linha.pack(fill="x", pady=(2, 0))
        entrada = tk.Entry(linha, textvariable=self.var_meta, width=7, relief="flat", bg=t.SURFACE, fg=t.TEXT,
                           font=t.Fontes.display(20), highlightthickness=1, highlightbackground=t.BORDER,
                           justify="center")
        entrada.pack(side="left", ipady=2)
        entrada.bind("<Return>", lambda e: self._ao_mudar_meta())
        entrada.bind("<FocusOut>", lambda e: self._ao_mudar_meta())
        tk.Label(linha, text="matérias publicadas", fg=t.TEXT, bg=PAINEL,
                 font=t.Fontes.display(14)).pack(side="left", padx=10)
        self.rotulo_meta = tk.Label(interno, text="", fg=t.TEXT_MUTED, bg=PAINEL, anchor="w", justify="left",
                                    wraplength=300, font=t.Fontes.corpo(9))
        self.rotulo_meta.pack(fill="x", pady=(8, 8))
        self.barra_meta = tk.Canvas(interno, height=8, bg=PAINEL_ALTO, highlightthickness=0, bd=0)
        self.barra_meta.pack(fill="x")
        self.rotulo_meta_pct = tk.Label(interno, text="", fg=t.TEXT, bg=PAINEL, anchor="e",
                                        font=t.Fontes.corpo(8, "bold"))
        self.rotulo_meta_pct.pack(fill="x", pady=(6, 0))

    # =====================================================================
    # Filtros
    # =====================================================================
    def _aplicar_preferencias(self, guardado: dict):
        self._carregando = True
        try:
            periodo = guardado.get("periodo")
            if periodo in self._chaves_periodo and periodo != "personalizado":
                self.combo_periodo.current(self._chaves_periodo.index(periodo))
            else:
                self.combo_periodo.current(self._chaves_periodo.index("30d"))
            estado = guardado.get("status")
            if estado in self._chaves_estado:
                self.combo_estado.current(self._chaves_estado.index(estado))
            meta = guardado.get("meta")
            self.var_meta.set(str(meta) if isinstance(meta, int) and meta > 0 else str(META_PADRAO))
            hoje = date.today()
            self.var_fim.set(f"{hoje:%d/%m/%Y}")
            self.var_inicio.set(f"{hoje - timedelta(days=30):%d/%m/%Y}")
        finally:
            self._carregando = False

    def _filtro_atual(self, avisar=True):
        """Monta o FiltroEstatisticas a partir da tela (None se as datas forem inválidas)."""
        periodo = self._chaves_periodo[max(0, self.combo_periodo.current())]
        inicio = fim = None
        if periodo == "personalizado":
            inicio, fim = interpretar_data_br(self.var_inicio.get()), interpretar_data_br(self.var_fim.get())
            if not inicio or not fim:
                if avisar:
                    messagebox.showwarning("Gráficos", "Informe datas válidas no formato dd/mm/aaaa.")
                return None
            if inicio > fim:
                if avisar:
                    messagebox.showwarning("Gráficos", "A data inicial não pode ser depois da data final.")
                return None
        return FiltroEstatisticas(
            periodo=periodo, inicio=inicio, fim=fim,
            categoria_id=self._chaves_categoria[max(0, self.combo_categoria.current())],
            autor_id=self._chaves_autor[max(0, self.combo_autor.current())],
            status=self._chaves_estado[max(0, self.combo_estado.current())])

    def _ao_mudar_periodo(self):
        personalizado = self._chaves_periodo[max(0, self.combo_periodo.current())] == "personalizado"
        if personalizado:
            self.area_personalizado.pack(fill="x", pady=(8, 0), before=self.rotulo_resumo)
        else:
            self.area_personalizado.pack_forget()
        self._ao_mudar_filtro()

    def _ao_mudar_filtro(self):
        if not self._carregando:
            self.recarregar()

    def _limpar_filtros(self):
        self._carregando = True
        self.combo_periodo.current(self._chaves_periodo.index("30d"))
        self.combo_categoria.current(0)
        self.combo_autor.current(0)
        self.combo_estado.current(0)
        self.area_personalizado.pack_forget()
        self._carregando = False
        self.recarregar()

    def _recarregar_opcoes(self):
        """Atualiza as listas de editorias e jornalistas (mantém a escolha atual)."""
        resultado = self.servico.opcoes_de_filtro()
        if not resultado.ok:
            return
        categoria_atual = self._chaves_categoria[max(0, self.combo_categoria.current())]
        autor_atual = self._chaves_autor[max(0, self.combo_autor.current())]
        categorias = resultado.dados["categorias"]
        autores = resultado.dados["autores"]
        self._nomes_categorias = {c["id"]: c["nome"] for c in categorias}
        self._nomes_autores = {a["id"]: a["nome"] for a in autores}
        self._chaves_categoria = [None] + [c["id"] for c in categorias]
        self._chaves_autor = [None] + [a["id"] for a in autores]
        self.combo_categoria.configure(values=["Todas as editorias"] + [c["nome"] for c in categorias])
        self.combo_autor.configure(values=["Todos os jornalistas"] + [a["nome"] for a in autores])
        self.combo_categoria.current(self._chaves_categoria.index(categoria_atual)
                                     if categoria_atual in self._chaves_categoria else 0)
        self.combo_autor.current(self._chaves_autor.index(autor_atual) if autor_atual in self._chaves_autor else 0)

    # =====================================================================
    # Carregar e desenhar
    # =====================================================================
    def recarregar(self):
        self._recarregar_opcoes()
        filtro = self._filtro_atual()
        if filtro is None:
            return
        resultado = self.servico.consultar(filtro)
        if not resultado.ok:
            messagebox.showerror("Gráficos", resultado.mensagem)
            return
        self.dados = resultado.dados
        self._desenhar(self.dados)
        self.preferencias.salvar(dict(periodo=filtro.periodo if filtro.periodo != "personalizado" else "30d",
                                      status=filtro.status, meta=self._meta()))

    def _tique(self):
        """Atualização automática a cada minuto, só com a tela aberta."""
        try:
            if self.winfo_ismapped() and self._filtro_atual(avisar=False) is not None:
                self.recarregar()
            self.after(TIQUE_ATUALIZACAO_MS, self._tique)
        except tk.TclError:
            pass

    def _desenhar(self, d):
        self._desenhar_resumo(d)
        self._desenhar_kpis(d)
        self._desenhar_distribuicao(d)
        self._desenhar_serie(d)
        self._desenhar_autores(d)
        self._desenhar_semana(d)
        self._desenhar_pipeline(d)
        self._desenhar_insights(d)
        self._desenhar_meta(d)

    def _desenhar_resumo(self, d):
        f = d["filtro"]
        partes = [d["periodo"]["rotulo"], ESTADOS[f.status].lower()]
        if f.categoria_id:
            partes.append("editoria: " + self._nomes_categorias.get(f.categoria_id, "?"))
        if f.autor_id:
            partes.append("jornalista: " + self._nomes_autores.get(f.autor_id, "?"))
        self.rotulo_resumo.configure(
            text=f"MOSTRANDO {fmt_int(d['kpis']['total'])} MATÉRIA(S)  •  " + "  •  ".join(p.upper() for p in partes))

    # ---------- indicadores ----------
    def _cartao_kpi(self, coluna, rotulo, valor, nota, cor_nota, rodape, cor_borda):
        cartao = tk.Frame(self.area_kpis, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        cartao.grid(row=0, column=coluna, sticky="nsew", padx=(0 if coluna == 0 else 8, 0 if coluna == 3 else 0))
        tk.Frame(cartao, bg=cor_borda, width=4).pack(side="left", fill="y")
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=14, pady=12)
        interno.pack(side="left", fill="both", expand=True)
        tk.Label(interno, text=rotulo, fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.corpo(8, "bold")).pack(fill="x")
        tk.Label(interno, text=valor, fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.display(32)).pack(fill="x", pady=(4, 0))
        tk.Label(interno, text=nota, fg=cor_nota, bg=t.SURFACE, anchor="w", font=t.Fontes.corpo(8, "bold")).pack(fill="x")
        tk.Frame(interno, bg=t.BORDER, height=1).pack(fill="x", pady=(8, 6))
        tk.Label(interno, text=rodape, fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left",
                 wraplength=230, font=t.Fontes.corpo(8)).pack(fill="x")

    def _desenhar_kpis(self, d):
        for filho in self.area_kpis.winfo_children():
            filho.destroy()
        k, f = d["kpis"], d["filtro"]
        if k["variacao_total"] is None:
            nota1, cor1 = ("SEM BASE DE COMPARAÇÃO" if k["total_anterior"] == 0 else "SEM COMPARAÇÃO"), t.TEXT_MUTED
        else:
            subiu = k["variacao_total"] >= 0
            nota1 = f"{'↑ +' if subiu else '↓ −'}{fmt_pct(abs(k['variacao_total']))} VS. PERÍODO ANTERIOR"
            cor1 = t.SUCCESS if subiu else t.ERROR
        self._cartao_kpi(0, "TOTAL PUBLICADO" if f.status == "publicado" else "TOTAL DE MATÉRIAS",
                         fmt_int(k["total"]), nota1, cor1,
                         f"{d['periodo']['rotulo']} • média de {fmt_dec(k['total'] / d['periodo']['dias'], 1)} por dia",
                         t.PRIMARY)
        self._cartao_kpi(1, "EDITORIAS EM OPERAÇÃO", str(k["editorias_operacao"]),
                         f"{fmt_pct(k['pct_editorias'], 0)} DAS EDITORIAS ATIVAS", COR_AZUL,
                         f"{k['editorias_operacao']} de {k['editorias_ativas']} editorias ativas com matérias no recorte",
                         COR_AZUL)
        if k["delta_leituras"] is None:
            nota3, cor3 = "SEM COMPARAÇÃO", t.TEXT_MUTED
        else:
            nota3 = f"{'+' if k['delta_leituras'] >= 0 else '−'}{fmt_int(abs(k['delta_leituras']))} LEITURAS VS. ANTERIOR"
            cor3 = t.SUCCESS if k["delta_leituras"] >= 0 else t.ERROR
        self._cartao_kpi(2, "MÉDIA LEITURAS / MATÉRIA", fmt_int(k["media_leituras"]), nota3, cor3,
                         f"{fmt_int(k['soma_leituras'])} leituras somadas no recorte", COR_SEPIA)
        self._cartao_kpi(3, "TEMPO MÉDIO DE LEITURA", abreviar_tempo(k["tempo_leitura"]), k["formato"].upper(),
                         t.TEXT_MUTED, f"Média de {fmt_int(k['media_palavras'])} palavras por matéria", t.TEXT_MUTED)

    # ---------- gráficos do matplotlib ----------
    def _mostrar_figura(self, container, figura):
        """Troca o gráfico exibido num contêiner por uma nova Figure do matplotlib."""
        for filho in container.winfo_children():
            filho.destroy()
        canvas = FigureCanvasTkAgg(figura, master=container)
        widget = canvas.get_tk_widget()
        widget.configure(bg=t.SURFACE, highlightthickness=0)
        widget.pack(fill="x")
        canvas.draw()
        self._canvases = [c for c in self._canvases if c.get_tk_widget().winfo_exists()] + [canvas]

    def _desenhar_distribuicao(self, d):
        total = d["kpis"]["total"]
        self.rotulo_total_dist.configure(text=f"●  TOTAL: {fmt_int(total)} DESPACHOS")
        self.rotulo_sub_dist.configure(
            text=f"Total acumulado por editoria no recorte ({d['periodo']['rotulo'].lower()}, {ESTADOS[d['filtro'].status].lower()}).")
        self._mostrar_figura(self.area_fig_dist, figura_distribuicao(d["categorias"], 6.4))
        com_materias = [c for c in d["categorias"] if c["total"] > 0]
        if com_materias:
            topo = com_materias[0]
            self.rotulo_nota_dist.configure(
                text=f"ⓘ  A editoria de {topo['nome']} absorveu a maior carga: {fmt_int(topo['total'])} matérias "
                     f"({fmt_pct(topo['percentual'])} do volume).")
            self.rotulo_escala.configure(text=f"ESCALA RELATIVA (MÁX. {fmt_int(topo['total'])})")
        else:
            self.rotulo_nota_dist.configure(text="ⓘ  Nenhuma matéria no recorte escolhido.")
            self.rotulo_escala.configure(text="")

    def _desenhar_serie(self, d):
        s = d["serie"]
        self.rotulo_sub_serie.configure(
            text=f"Matérias {GRANULARIDADE[s['granularidade']]} entre {d['periodo']['rotulo'].lower()}; "
                 f"o ponto destacado é o pico do período.")
        self._mostrar_figura(self.area_fig_serie, figura_serie(s, 6.4, 2.6))

    def _desenhar_semana(self, d):
        self._mostrar_figura(self.area_fig_semana, figura_semana(d["semana"], 3.4, 2.35))
        semana = d["semana"]
        if semana["picos"]:
            nomes = [semana["rotulos"][i] for i in semana["picos"][:3]]
            dias = nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]
            media_geral = sum(semana["totais"]) / max(1, d["periodo"]["dias"])
            texto = (f"Picos de publicação concentrados em {dias}. "
                     f"Média geral de {fmt_dec(media_geral, 1)} matéria(s) por dia.")
        else:
            texto = "Sem matérias suficientes para identificar picos no recorte."
        self.rotulo_observacao.configure(text=texto)

    # ---------- autores ----------
    def _desenhar_autores(self, d):
        for filho in self.area_autores.winfo_children():
            filho.destroy()
        autores = d["autores"]
        area = self.area_autores
        area.grid_columnconfigure(1, weight=1)
        for coluna, titulo in ((0, "JORNALISTA"), (2, "MATÉRIAS"), (3, "SCORE")):
            tk.Label(area, text=titulo, fg=t.TEXT, bg=t.SURFACE, font=t.Fontes.corpo(7, "bold")).grid(
                row=0, column=coluna if coluna else 0, columnspan=2 if coluna == 0 else 1, sticky="w" if coluna == 0 else "e",
                padx=(0, 8), pady=(0, 4))
        tk.Frame(area, bg=t.TEXT, height=2).grid(row=1, column=0, columnspan=4, sticky="ew")
        if not autores:
            tk.Label(area, text="Nenhum jornalista com matérias no recorte.", fg=t.TEXT_MUTED, bg=t.SURFACE,
                     font=t.Fontes.corpo(9), pady=14).grid(row=2, column=0, columnspan=4)
        for linha, a in enumerate(autores[:5]):
            r = 2 + linha * 2
            tk.Label(area, text=f"{linha + 1:02d}.", fg=t.TEXT_MUTED, bg=t.SURFACE,
                     font=t.Fontes.corpo(9, "bold")).grid(row=r, column=0, sticky="nw", pady=(8, 8))
            nome = tk.Frame(area, bg=t.SURFACE)
            nome.grid(row=r, column=1, sticky="w", pady=(6, 6))
            tk.Label(nome, text=a["nome"], fg=t.TEXT, bg=t.SURFACE, anchor="w",
                     font=t.Fontes.corpo(10, "bold")).pack(anchor="w")
            tk.Label(nome, text=(a["cargo"] or "—").upper(), fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w",
                     font=t.Fontes.corpo(7)).pack(anchor="w")
            tk.Label(area, text=str(a["total"]), fg=t.TEXT, bg=t.SURFACE,
                     font=t.Fontes.corpo(10, "bold")).grid(row=r, column=2, sticky="e", padx=(0, 8))
            tk.Label(area, text=fmt_dec(a["score"]), fg=t.PRIMARY if linha == 0 else t.TEXT,
                     bg=FUNDO_ROSA if linha == 0 else PAINEL, padx=6, pady=2,
                     font=t.Fontes.corpo(9, "bold")).grid(row=r, column=3, sticky="e")
            tk.Frame(area, bg=t.BORDER, height=1).grid(row=r + 1, column=0, columnspan=4, sticky="ew")
        self.rotulo_equipe.configure(text=f"EQUIPE NO RECORTE: {len(autores)} JORNALISTA(S)")

    def _abrir_tabela_completa(self):
        if not self.dados:
            return
        janela = tk.Toplevel(self)
        janela.title("Produtividade por autor — tabela completa")
        janela.configure(bg=t.SURFACE)
        janela.geometry("760x420")
        janela.transient(self.winfo_toplevel())
        tk.Label(janela, text="Produtividade por Autor", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(18)).pack(anchor="w", padx=18, pady=(14, 0))
        tk.Label(janela, text="Score = 60% quantidade de matérias + 40% média de leituras, relativos ao melhor do recorte.",
                 fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(9)).pack(anchor="w", padx=18, pady=(0, 8))
        colunas = ("pos", "nome", "cargo", "total", "leituras", "media", "score")
        arvore = ttk.Treeview(janela, columns=colunas, show="headings", height=14)
        for coluna, titulo, largura, ancora in (("pos", "#", 36, "center"), ("nome", "Jornalista", 190, "w"),
                                                ("cargo", "Cargo", 190, "w"), ("total", "Matérias", 70, "e"),
                                                ("leituras", "Leituras", 80, "e"), ("media", "Média", 70, "e"),
                                                ("score", "Score", 60, "e")):
            arvore.heading(coluna, text=titulo)
            arvore.column(coluna, width=largura, anchor=ancora)
        for posicao, a in enumerate(self.dados["autores"], start=1):
            arvore.insert("", "end", values=(posicao, a["nome"], a["cargo"] or "", fmt_int(a["total"]),
                                             fmt_int(a["leituras"]), fmt_int(a["media_leituras"]), fmt_dec(a["score"])))
        arvore.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        t.botao_secundario(janela, "FECHAR", janela.destroy).pack(pady=(0, 14))

    # ---------- pipeline, insights, meta ----------
    def _desenhar_pipeline(self, d):
        p = d["pipeline"]
        fila = p["em_revisao"]
        self.chip_pipeline.configure(text="PRONTO P/ RODAGEM" if fila == 0 else f"{fila} NA REVISÃO")
        quando = p["ultima_publicacao"]
        ultimo = (f"Último carimbo registrado em {quando:%d/%m/%Y} às {quando:%H:%M}" if quando
                  else "Nenhuma matéria publicada até agora")
        self.rotulo_pipeline.configure(
            text=f"{ultimo} — {fila} matéria(s) na fila de revisão, {p['em_pauta']} em pauta e "
                 f"{p['rascunhos']} rascunho(s) na galé.")
        self.rotulo_atualizado.configure(text=f"ATUALIZADO ÀS {datetime.now():%H:%M:%S}")

    def _desenhar_insights(self, d):
        for filho in self.area_insights.winfo_children():
            filho.destroy()
        for frase in d["insights"]:
            linha = tk.Frame(self.area_insights, bg=t.SURFACE)
            linha.pack(fill="x", pady=(0, 6))
            tk.Label(linha, text="■", fg=t.PRIMARY, bg=t.SURFACE, font=t.Fontes.corpo(7)).pack(side="left", anchor="n", pady=(4, 0))
            tk.Label(linha, text=frase, fg=t.TEXT, bg=t.SURFACE, anchor="w", justify="left", wraplength=560,
                     font=t.Fontes.display(12)).pack(side="left", padx=(8, 0), fill="x", expand=True)

    def _meta(self) -> int:
        try:
            return max(0, int(self.var_meta.get().strip()))
        except ValueError:
            return 0

    def _ao_mudar_meta(self):
        if not self.dados:
            return
        if self._meta() <= 0:
            self.var_meta.set(str(META_PADRAO))
        self._desenhar_meta(self.dados)
        filtro = self.dados["filtro"]
        self.preferencias.salvar(dict(periodo=filtro.periodo if filtro.periodo != "personalizado" else "30d",
                                      status=filtro.status, meta=self._meta()))

    def _desenhar_meta(self, d):
        meta, total = self._meta(), d["kpis"]["total"]
        canvas = self.barra_meta
        canvas.delete("all")
        if meta <= 0:
            self.rotulo_meta.configure(text="Defina uma meta de matérias para acompanhar o progresso.")
            self.rotulo_meta_pct.configure(text="")
            return
        pct = 100.0 * total / meta
        faltam = max(0, meta - total)
        self.rotulo_meta.configure(
            text=("Meta cumprida! " + f"{fmt_int(total)} matérias no período." if faltam == 0
                  else f"Faltam {fmt_int(faltam)} matéria(s) para fechar a meta de {fmt_int(meta)} no período."))
        self.rotulo_meta_pct.configure(text=f"{fmt_pct(min(pct, 999.9))} CONCLUÍDO")
        real = canvas.winfo_width()
        real = real if isinstance(real, int) else 0
        canvas.create_rectangle(0, 0, int(max(real, 280) * min(pct, 100) / 100), 8, fill=t.PRIMARY, width=0)
        if real <= 1:   # ainda sem tamanho real: redesenha quando a janela aparecer
            canvas.bind("<Configure>", lambda e: self._desenhar_meta(self.dados) if self.dados else None)

    # =====================================================================
    # Exportação
    # =====================================================================
    def _subtitulo_relatorio(self):
        f = self.dados["filtro"]
        return descricao_filtros(self.dados, self._nomes_categorias.get(f.categoria_id),
                                 self._nomes_autores.get(f.autor_id))

    def _exportar_pdf(self):
        if not self.dados:
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar relatório de métricas", defaultextension=".pdf",
            initialfile=f"relatorio_metricas_{date.today():%Y%m%d}.pdf", filetypes=[("PDF", "*.pdf")])
        if not caminho:
            return
        try:
            paginas = exportar_pdf(caminho, self.dados, self._subtitulo_relatorio())
            self.logger.info(f"Relatório de métricas exportado para {caminho}")
            messagebox.showinfo("Relatório", f"Relatório salvo com {paginas} páginas.")
        except (OSError, ValueError, RuntimeError) as erro:
            self.logger.error("Erro ao exportar o relatório em PDF", erro)
            messagebox.showerror("Relatório", "Não foi possível salvar o PDF. Feche o arquivo se ele estiver aberto.")

    def _exportar_csv(self):
        if not self.dados:
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar dados do relatório", defaultextension=".csv",
            initialfile=f"metricas_{date.today():%Y%m%d}.csv", filetypes=[("CSV", "*.csv")])
        if not caminho:
            return
        try:
            with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
                csv.writer(arquivo, delimiter=";").writerows(self.servico.linhas_csv(self.dados))
            self.logger.info(f"Métricas exportadas para {caminho}")
            messagebox.showinfo("Relatório", "Dados salvos com sucesso.")
        except OSError as erro:
            self.logger.error("Erro ao exportar o CSV de métricas", erro)
            messagebox.showerror("Relatório", "Não foi possível salvar o arquivo.")
