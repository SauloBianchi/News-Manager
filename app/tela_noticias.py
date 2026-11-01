"""
tela_noticias.py
Tela "Notícias" do NewsManager, reproduzindo em Tkinter o protótipo do
Stitch (not_cias_newsmanager, nova_mat_ria_editor_redacional e
leitura_da_mat_ria_newsmanager):

- Editor "Pauta & Redação de Artigo": título (contador 0/120), linha fina,
  seção, jornalista, data/hora, estado de publicação, manchete de capa,
  etiquetas e corpo do texto (contador de palavras e tempo de leitura), com
  os botões Adicionar ao diário / Atualizar registro / Excluir / Limpar.
- Painel "Cadência da Tiragem": distribuição das matérias publicadas por
  seção, matérias em revisão e total em circulação.
- "Edição Corrente & Feed de Matérias": cartões em grade 3x2 com busca,
  filtros (seção, estado), ordenação e paginação; cada cartão tem Editar,
  Ler e Excluir.
- Ler abre a página de leitura (tela_leitura.py); "Abrir no editor completo"
  leva para o editor redacional (tela_editor.py).

Toda a regra de negócio fica em NoticiaService (app/noticias.py).
"""

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from . import theme as t
from .cadastros import AutorService, CategoriaService
from .midia import midia as midia_global
from .noticias import (
    FORMATO_DATA_TELA,
    ORDENS_NOTICIA,
    STATUS_NOTICIA,
    NoticiaService,
    contar_palavras,
    interpretar_data,
    lista_etiquetas,
    tempo_leitura_min,
)
from .shell import MESES as MESES_LONGOS
from .texto_rico import texto_simples
from .telas_cadastros import (
    COR_MATIZ,
    FUNDO_MATIZ,
    MARGEM,
    PAINEL,
    PAINEL_ALTO,
    PAINEL_BAIXO,
    CampoImagem,
    CampoSelecao,
    CampoTextoLongo,
    _cabecalho,
    _como_data,
    _etiqueta,
    _filete,
    _link,
    _resumir,
    _TelaBase,
    desenhar_paginacao,
)

ALTURA_CAPA = 140             # altura da fotografia nos cartões do feed
TINTA_INVERSA = "#31302B"     # fundo do cartão de manchete (inverse-surface)
TEXTO_INVERSO = "#F4F0E8"     # texto sobre fundo escuro


def data_extenso_curta(valor) -> str:
    """'24 DE OUTUBRO, 2024' (ou '' se a data for inválida)."""
    d = _como_data(valor)
    if d is None:
        return ""
    return f"{d.day} de {MESES_LONGOS[d.month - 1]}, {d.year}".upper()


def hora_da_data(valor) -> str:
    """'08:30' se `valor` tiver horário; senão ''."""
    data = interpretar_data(valor) if not isinstance(valor, datetime) else valor
    if data is None or (data.hour == 0 and data.minute == 0):
        return ""
    return data.strftime("%H:%M")


def _para_texto_tela(valor) -> str:
    data = interpretar_data(valor)
    return data.strftime(FORMATO_DATA_TELA) if data else ""


class NoticiasFrame(_TelaBase):
    POR_PAGINA = 6
    COLUNAS_GRADE = 3

    def __init__(self, parent, db, logger, ao_alterar=None, ao_ler=None, ao_editar_completo=None):
        super().__init__(parent, db, logger, ao_alterar)
        self.ao_ler = ao_ler                          # ao_ler(noticia_id): abre a página de leitura
        self.ao_editar_completo = ao_editar_completo  # (noticia_id, dados_iniciais): editor completo
        self.servico = NoticiaService(db, logger, midia_global)
        self._pagina_atual = 1
        self._filtro_categoria = None
        self._filtro_status = ""
        self._ordem = "recentes"
        self._chaves_filtro_categoria = [None]
        self._montar()
        self._recarregar_opcoes()
        self._limpar_form()
        self.recarregar()

    # =====================================================================
    # Montagem
    # =====================================================================
    def _montar(self):
        p = self.pagina
        topo = tk.Frame(p, bg=t.BG)
        topo.pack(fill="x", padx=MARGEM, pady=(20, 0))
        topo.grid_columnconfigure(0, weight=1)
        topo.grid_columnconfigure(1, minsize=290)
        self._montar_editor(topo)
        self._montar_painel_lateral(topo)
        self._montar_feed(p)
        tk.Frame(p, bg=t.BG, height=24).pack()

    # ---------- editor ----------
    def _montar_editor(self, pai):
        cartao = tk.Frame(pai, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        cartao.grid(row=0, column=0, sticky="nsew", padx=(0, 16))

        cab = tk.Frame(cartao, bg=t.SURFACE)
        cab.pack(fill="x", padx=18, pady=(14, 2))
        tk.Label(cab, text="■", fg=t.PRIMARY, bg=t.SURFACE, font=t.Fontes.corpo(10)).pack(side="left")
        tk.Label(cab, text="Pauta & Redação de Artigo", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(16)).pack(side="left", padx=(6, 8))
        tk.Label(cab, text="GABINETE DE IMPRENSA", fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        self.chip_estado = tk.Label(cab, text="", fg=t.TEXT, bg=PAINEL, padx=6, pady=2,
                                    font=t.Fontes.corpo(8, "bold"))
        self.chip_estado.pack(side="right")

        self.campo_titulo = t.CampoEditorial(cartao, "TÍTULO DA MATÉRIA *", dica="0 / 120")
        self.campo_titulo.pack(fill="x", padx=18, pady=(8, 0))
        self.campo_subtitulo = t.CampoEditorial(cartao, "LINHA FINA / LEAD EDITORIAL")
        self.campo_subtitulo.pack(fill="x", padx=18, pady=(6, 0))

        grade = tk.Frame(cartao, bg=t.SURFACE)
        grade.pack(fill="x", padx=10, pady=(6, 0))
        for coluna in range(3):
            grade.grid_columnconfigure(coluna, weight=1, uniform="campo_noticia")
        self.campo_categoria = CampoSelecao(grade, "SEÇÃO EDITORIAL *", {})
        self.campo_autor = CampoSelecao(grade, "JORNALISTA CREDENCIADO *", {})
        self.campo_data = t.CampoEditorial(grade, "DATA E HORÁRIO DE EMISSÃO", dica="DD/MM/AAAA HH:MM")
        self.campo_status = CampoSelecao(grade, "ESTADO DE PUBLICAÇÃO", STATUS_NOTICIA)
        self.campo_etiquetas = t.CampoEditorial(grade, "ETIQUETAS", dica="SEPARE POR VÍRGULA")
        self.var_destaque = tk.BooleanVar(value=False)
        caixa_destaque = tk.Frame(grade, bg=t.SURFACE)
        tk.Label(caixa_destaque, text=" ", bg=t.SURFACE, font=t.Fontes.corpo(11, "bold")).pack(anchor="w")
        tk.Checkbutton(
            caixa_destaque, text="MANCHETE DE CAPA • DESTAQUE", variable=self.var_destaque,
            bg=t.SURFACE, fg=t.PRIMARY, activebackground=t.SURFACE, activeforeground=t.PRIMARY,
            selectcolor=t.SURFACE, font=t.Fontes.corpo(9, "bold"), anchor="w", cursor="hand2",
        ).pack(anchor="w", pady=(8, 0))
        campos = (self.campo_categoria, self.campo_autor, self.campo_data,
                  self.campo_status, self.campo_etiquetas, caixa_destaque)
        for indice, campo in enumerate(campos):
            campo.grid(row=indice // 3, column=indice % 3, sticky="ew", padx=8, pady=6)

        bloco_foto = tk.Frame(cartao, bg=t.SURFACE)
        bloco_foto.pack(fill="x", padx=18, pady=(8, 0))
        self.campo_imagem = CampoImagem(bloco_foto, "FOTOGRAFIA DE CAPA", "noticias",
                                        largura=220, altura=124)
        self.campo_imagem.pack(side="left", anchor="n")
        textos_foto = tk.Frame(bloco_foto, bg=t.SURFACE)
        textos_foto.pack(side="left", fill="x", expand=True, padx=(16, 0), anchor="n")
        self.campo_legenda = t.CampoEditorial(textos_foto, "LEGENDA DA FOTOGRAFIA", dica="OPCIONAL")
        self.campo_legenda.pack(fill="x")
        self.campo_credito = t.CampoEditorial(textos_foto, "CRÉDITO", dica="EX.: ARQUIVO EPA / IMAGENS OFICIAIS")
        self.campo_credito.pack(fill="x", pady=(6, 0))

        self.campo_corpo = CampoTextoLongo(cartao, "GALÉ DE REDAÇÃO [CORPO DA MATÉRIA]", altura=9)
        self.campo_corpo.pack(fill="x", padx=18, pady=(10, 0))
        self.contador_corpo = tk.Label(cartao, text="", fg=t.TEXT_MUTED, bg=t.SURFACE,
                                       font=t.Fontes.corpo(8, "bold"), anchor="w")
        self.contador_corpo.pack(fill="x", padx=18, pady=(4, 0))

        self.campo_titulo.entry.bind("<KeyRelease>", self._atualizar_contadores)
        self.campo_corpo.texto.bind("<KeyRelease>", self._atualizar_contadores)

        botoes = tk.Frame(cartao, bg=t.SURFACE)
        botoes.pack(fill="x", padx=18, pady=(12, 6))
        t.botao_primario(botoes, "Adicionar ao diário", self._adicionar).pack(side="left")
        self.botao_atualizar = t.botao_secundario(botoes, "ATUALIZAR REGISTRO", self._atualizar)
        self.botao_atualizar.pack(side="left", padx=(8, 0))
        self.botao_excluir = t.botao_secundario(botoes, "EXCLUIR", self._excluir_em_edicao)
        self.botao_excluir.configure(fg=t.ERROR)
        self.botao_excluir.pack(side="left", padx=(8, 0))
        _link(botoes, "LIMPAR CAMPOS", self._limpar_form, t.TEXT).pack(side="right")
        _link(botoes, "ABRIR NO EDITOR COMPLETO →", self._abrir_editor_completo, t.PRIMARY).pack(
            side="right", padx=(0, 18))

        self.rotulo_feedback = tk.Label(cartao, text="", fg=t.SUCCESS, bg=t.SURFACE,
                                        font=t.Fontes.corpo(9, "bold"), anchor="w")
        self.rotulo_feedback.pack(fill="x", padx=18, pady=(0, 12))

    # ---------- painel lateral ----------
    def _montar_painel_lateral(self, pai):
        painel = tk.Frame(pai, bg=PAINEL, highlightthickness=1, highlightbackground=t.BORDER)
        painel.grid(row=0, column=1, sticky="nsew")
        interno = tk.Frame(painel, bg=PAINEL, padx=16, pady=16)
        interno.pack(fill="both", expand=True)

        cab = tk.Frame(interno, bg=PAINEL)
        cab.pack(fill="x")
        tk.Label(cab, text="CADÊNCIA DA TIRAGEM", fg=t.TEXT, bg=PAINEL,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")

        grafico = tk.Frame(interno, bg=t.SURFACE, padx=12, pady=10)
        grafico.pack(fill="x", pady=(10, 0))
        tk.Label(grafico, text="Distribuição das Matérias", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(13)).pack(anchor="w")
        tk.Label(grafico, text="Matérias publicadas por seção.", fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(8)).pack(anchor="w", pady=(0, 6))
        self.canvas_distribuicao = tk.Canvas(grafico, width=230, height=120, bg=t.SURFACE,
                                             highlightthickness=0, bd=0)
        self.canvas_distribuicao.pack()

        self.caixa_plantao = tk.Frame(interno, bg=PAINEL_ALTO, padx=12, pady=10)
        self.caixa_plantao.pack(fill="x", pady=(12, 0))
        tk.Label(self.caixa_plantao, text="! PLANTÃO DO TELÉGRAFO", fg=t.PRIMARY, bg=PAINEL_ALTO,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        self.rotulo_plantao = tk.Label(self.caixa_plantao, text="", fg=t.TEXT, bg=PAINEL_ALTO,
                                       font=t.Fontes.corpo(9), justify="left", wraplength=230)
        self.rotulo_plantao.pack(anchor="w", pady=(4, 0))

        tk.Frame(interno, bg=t.BORDER, height=1).pack(fill="x", pady=(14, 8))
        total = tk.Frame(interno, bg=PAINEL)
        total.pack(fill="x")
        tk.Label(total, text="TOTAL EM CIRCULAÇÃO", fg=t.TEXT, bg=PAINEL,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        self.rotulo_total = tk.Label(total, text="0 Artigos", fg=t.TEXT, bg=PAINEL,
                                     font=t.Fontes.display(15))
        self.rotulo_total.pack(side="right")

    # ---------- feed ----------
    def _montar_feed(self, pagina):
        cab = tk.Frame(pagina, bg=t.BG)
        cab.pack(fill="x", padx=MARGEM, pady=(26, 0))
        tk.Label(cab, text="FEED DE APURAÇÕES & GALÉS", fg=t.PRIMARY, bg=t.BG,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        tk.Label(cab, text="Edição Corrente & Feed de Matérias", fg=t.TEXT, bg=t.BG,
                 font=t.Fontes.display(24)).pack(anchor="w", pady=(2, 0))

        barra = tk.Frame(pagina, bg=t.BG)
        barra.pack(fill="x", padx=MARGEM, pady=(10, 0))
        self._campo_busca(barra, "título, autor ou etiqueta").pack(side="left")
        _link(barra, "↻ ATUALIZAR", self.recarregar, t.TEXT).pack(side="right", padx=(12, 0))
        self.combo_ordem, self._chaves_ordem = self._combo_filtro(
            barra, ORDENS_NOTICIA, self._ao_mudar_ordem)
        self.combo_status, self._chaves_status = self._combo_filtro(
            barra, {"": "Todos os Estados", **STATUS_NOTICIA}, self._ao_mudar_status)
        self.combo_categoria, _ = self._combo_filtro(
            barra, {None: "Todas as Seções"}, self._ao_mudar_categoria)

        self.area_cartoes = tk.Frame(pagina, bg=t.BG)
        self.area_cartoes.pack(fill="x", padx=MARGEM - 8, pady=(10, 0))
        for coluna in range(self.COLUNAS_GRADE):
            self.area_cartoes.grid_columnconfigure(coluna, weight=1, uniform="cartao_noticia")

        self.area_paginacao = tk.Frame(pagina, bg=t.SURFACE, highlightthickness=1,
                                       highlightbackground=t.BORDER)
        self.area_paginacao.pack(fill="x", padx=MARGEM, pady=(10, 0))

    def _combo_filtro(self, pai, opcoes: dict, ao_mudar):
        combo = ttk.Combobox(pai, values=list(opcoes.values()), state="readonly",
                             font=t.Fontes.corpo(10), width=20)
        combo.pack(side="right", padx=(8, 0), ipady=3)
        combo.current(0)
        combo.bind("<<ComboboxSelected>>", lambda e: ao_mudar())
        return combo, list(opcoes.keys())

    # =====================================================================
    # Dados
    # =====================================================================
    def _recarregar_opcoes(self):
        """Atualiza as listas de seções e jornalistas (podem ter mudado nas outras abas)."""
        categorias = self.db.listar_categorias()
        autores = self.db.listar_autores()
        self.campo_categoria.definir_opcoes({c["id"]: c["nome"] for c in categorias})
        self.campo_autor.definir_opcoes({a["id"]: a["nome"] for a in autores})

        atual = self._filtro_categoria
        opcoes = {None: "Todas as Seções", **{c["id"]: c["nome"] for c in categorias}}
        self._chaves_filtro_categoria = list(opcoes.keys())
        self.combo_categoria.configure(values=list(opcoes.values()))
        if atual in self._chaves_filtro_categoria:
            self.combo_categoria.current(self._chaves_filtro_categoria.index(atual))
        else:
            self._filtro_categoria = None
            self.combo_categoria.current(0)

    def recarregar(self):
        self._recarregar_opcoes()
        resumo = self.servico.resumo()
        lista = self.servico.listar(
            self.var_busca.get(), self._filtro_categoria, self._filtro_status,
            self._ordem, self._pagina_atual, self.POR_PAGINA)
        if not resumo.ok or not lista.ok:
            messagebox.showerror("Notícias", (resumo if not resumo.ok else lista).mensagem)
            return
        self._pagina_atual = lista.dados["pagina"]
        self._desenhar_painel(resumo.dados)
        self._desenhar_cartoes(lista.dados)

    # ---------- filtros ----------
    def _aplicar_busca(self):
        self._pagina_atual = 1
        super()._aplicar_busca()

    def _ao_mudar_categoria(self):
        indice = self.combo_categoria.current()
        self._filtro_categoria = self._chaves_filtro_categoria[max(0, indice)]
        self._pagina_atual = 1
        self.recarregar()

    def _ao_mudar_status(self):
        self._filtro_status = self._chaves_status[max(0, self.combo_status.current())]
        self._pagina_atual = 1
        self.recarregar()

    def _ao_mudar_ordem(self):
        self._ordem = self._chaves_ordem[max(0, self.combo_ordem.current())]
        self._pagina_atual = 1
        self.recarregar()

    def _ir_para_pagina(self, numero):
        self._pagina_atual = numero
        self.recarregar()

    # =====================================================================
    # Painel lateral
    # =====================================================================
    def _desenhar_painel(self, r):
        self.rotulo_total.configure(text=f"{r['publicadas']} Artigos")
        pendentes = r["pendentes_revisao"]
        if pendentes:
            texto = (f"{pendentes} matéria(s) pendente(s) de aprovação na mesa de cópia "
                     "antes do envio para as chapas rotativas.")
        else:
            texto = "Nenhuma matéria aguardando revisão no momento."
        self.rotulo_plantao.configure(text=texto)

        canvas = self.canvas_distribuicao
        canvas.delete("all")
        dados = r["distribuicao"]
        if not dados:
            canvas.create_text(115, 55, text="Sem matérias publicadas", fill=t.TEXT_MUTED,
                               font=t.Fontes.corpo(9))
            return
        maior = max(d["total"] for d in dados) or 1
        largura_coluna = 230 // max(len(dados), 1)
        for indice, d in enumerate(dados):
            x0 = indice * largura_coluna + 10
            x1 = x0 + largura_coluna - 20
            altura = max(4, int(80 * d["total"] / maior))
            cor = COR_MATIZ.get(d["cor"], COR_MATIZ["rubro"])
            canvas.create_rectangle(x0, 90 - altura, x1, 90, fill=cor, width=0)
            canvas.create_text((x0 + x1) / 2, 84 - altura, text=str(d["total"]),
                               fill=t.TEXT, font=t.Fontes.corpo(8, "bold"))
            canvas.create_text((x0 + x1) / 2, 104, text=d["categoria"][:3].upper(),
                               fill=t.TEXT_MUTED, font=t.Fontes.corpo(8, "bold"))

    # =====================================================================
    # Feed de cartões
    # =====================================================================
    def _desenhar_cartoes(self, dados):
        for filho in self.area_cartoes.winfo_children():
            filho.destroy()
        itens = dados["itens"]
        if not itens:
            tk.Label(self.area_cartoes, text="Nenhuma matéria encontrada.", fg=t.TEXT_MUTED,
                     bg=t.BG, font=t.Fontes.corpo(11), pady=40).grid(
                row=0, column=0, columnspan=self.COLUNAS_GRADE)
        for posicao, noticia in enumerate(itens):
            cartao = self._cartao_noticia(self.area_cartoes, noticia)
            cartao.grid(row=posicao // self.COLUNAS_GRADE, column=posicao % self.COLUNAS_GRADE,
                        sticky="nsew", padx=8, pady=8)
        desenhar_paginacao(
            self.area_paginacao,
            f"MOSTRANDO {len(itens)} DE {dados['total']} PAUTAS REGISTRADAS",
            dados["pagina"], dados["paginas"], self._ir_para_pagina)

    def _largura_cartao(self) -> int:
        """Largura aproximada de um cartão do feed (a capa ocupa toda a largura)."""
        janela = self.winfo_toplevel().winfo_width()
        if not isinstance(janela, int) or janela < 400:
            janela = 1280
        return max(300, (janela - 2 * MARGEM) // self.COLUNAS_GRADE - 28)

    def _cartao_noticia(self, pai, n):
        destaque = bool(n["destaque"])
        fundo = TINTA_INVERSA if destaque else t.SURFACE
        texto = TEXTO_INVERSO if destaque else t.TEXT
        suave = "#C9C4B8" if destaque else t.TEXT_MUTED
        matiz = n["categoria_cor"] if n["categoria_cor"] in COR_MATIZ else "rubro"

        cartao = tk.Frame(pai, bg=fundo, highlightthickness=1, highlightbackground=t.BORDER)

        hora = hora_da_data(n["data_publicacao"])
        if n["status"] == "publicado":
            direita = f"FECHADO ÀS {hora}" if hora else "PUBLICADO"
        else:
            direita = STATUS_NOTICIA.get(n["status"], "").upper()

        largura_capa = self._largura_cartao()
        capa = self.midia.carregar_tk(n.get("imagem"), largura_capa, ALTURA_CAPA)
        if capa is not None:
            # fotografia de capa com a seção e o fechamento sobrepostos, como no protótipo
            topo = tk.Frame(cartao, width=largura_capa, height=ALTURA_CAPA, bg=fundo)
            topo.pack(fill="x")
            topo.pack_propagate(False)
            foto = tk.Label(topo, image=capa, bd=0)
            foto.image = capa
            foto.place(x=0, y=0, relwidth=1, relheight=1)
            tk.Label(topo, text=n["categoria"].upper(), fg="#FFFFFF", bg=COR_MATIZ[matiz],
                     padx=8, pady=2, font=t.Fontes.corpo(8, "bold")).place(x=10, y=10)
            tk.Label(topo, text=direita, fg=t.TEXT, bg="#FFFFFF", padx=6, pady=2,
                     font=t.Fontes.corpo(7, "bold")).place(relx=1.0, rely=1.0, x=-10, y=-10, anchor="se")
        else:
            faixa = tk.Frame(cartao, bg=COR_MATIZ[matiz], padx=12, pady=8)
            faixa.pack(fill="x")
            tk.Label(faixa, text=n["categoria"].upper(), fg="#FFFFFF", bg=COR_MATIZ[matiz],
                     font=t.Fontes.corpo(8, "bold")).pack(side="left")
            tk.Label(faixa, text=direita, fg="#FFFFFF", bg=COR_MATIZ[matiz],
                     font=t.Fontes.corpo(7, "bold")).pack(side="right")

        corpo = tk.Frame(cartao, bg=fundo, padx=14, pady=12)
        corpo.pack(fill="both", expand=True)
        tk.Label(corpo, text=f"{data_extenso_curta(n['data_publicacao'])} • {n['categoria'].upper()}",
                 fg=suave, bg=fundo, font=t.Fontes.corpo(7, "bold"), anchor="w",
                 justify="left", wraplength=280).pack(anchor="w")
        if n.get("fonte_nome"):   # matéria importada por clipping: sempre marcada como conteúdo externo
            _etiqueta(corpo, f"Conteúdo externo • {n['fonte_nome']}", suave, fundo, tamanho=7).pack(anchor="w", pady=(6, 0))
        tk.Label(corpo, text=n["titulo"], fg=texto, bg=fundo, font=t.Fontes.display(14),
                 anchor="w", justify="left", wraplength=280).pack(anchor="w", pady=(6, 4))
        resumo = _resumir(n["subtitulo"] or texto_simples(n["resumo"]), 140) or "Sem texto ainda."
        tk.Label(corpo, text=resumo, fg=texto, bg=fundo, font=t.Fontes.corpo(9), anchor="w",
                 justify="left", wraplength=280).pack(anchor="w", pady=(0, 10))

        linha_autor = tk.Frame(corpo, bg=fundo)
        linha_autor.pack(fill="x", side="bottom", pady=(8, 0))
        rodape = tk.Frame(corpo, bg=fundo)
        rodape.pack(fill="x", side="bottom")

        avatar = self.midia.carregar_tk(n.get("autor_foto"), 24, 24)
        if avatar is not None:
            rotulo_avatar = tk.Label(linha_autor, image=avatar, bd=0)
            rotulo_avatar.image = avatar
            rotulo_avatar.pack(side="left")
        else:
            tk.Label(linha_autor, text=(n["autor"][:1] or "?").upper(), fg="#FFFFFF",
                     bg=COR_MATIZ[matiz], width=2, font=t.Fontes.corpo(8, "bold")).pack(side="left")
        tk.Label(linha_autor, text=n["autor"], fg=texto, bg=fundo,
                 font=t.Fontes.corpo(9)).pack(side="left", padx=(6, 0))
        selo = "DESTAQUE" if destaque else STATUS_NOTICIA.get(n["status"], "").upper()
        tk.Label(linha_autor, text=selo, padx=6, pady=1, font=t.Fontes.corpo(7, "bold"),
                 fg="#FFFFFF" if destaque else t.TEXT,
                 bg=t.PRIMARY if destaque else PAINEL).pack(side="right")

        tk.Label(rodape, text=f"{int(n['leituras'])} LEITURAS", fg=suave, bg=fundo,
                 font=t.Fontes.corpo(7, "bold")).pack(side="left")
        acoes = tk.Frame(rodape, bg=fundo)
        acoes.pack(side="right")
        cor_link = TEXTO_INVERSO if destaque else t.SECONDARY
        _link(acoes, "EDITAR", lambda i=n["id"]: self._editar_do_cartao(i), cor_link).pack(side="left")
        _link(acoes, "LER", lambda x=n: self._ler(x), cor_link).pack(side="left", padx=(8, 0))
        _link(acoes, "EXCLUIR", lambda x=n: self._excluir_do_feed(x),
              "#FF9D95" if destaque else t.ERROR).pack(side="left", padx=(8, 0))
        return cartao

    # =====================================================================
    # Editor: formulário
    # =====================================================================
    def _atualizar_contadores(self, _evento=None):
        tamanho = len(" ".join(self.campo_titulo.get().split()))
        if self.campo_titulo.dica_label is not None:
            self.campo_titulo.dica_label.configure(
                text=f"{tamanho} / 120", fg=t.ERROR if tamanho > 120 else t.TEXT_MUTED)
        corpo = self.campo_corpo.get()
        palavras = contar_palavras(corpo)
        self.contador_corpo.configure(
            text=f"CONTADOR: {palavras} palavras • {len(corpo)} caracteres • "
                 f"aprox. {tempo_leitura_min(corpo)} min de leitura")

    def _limpar_form(self):
        self._id_edicao = None
        self.campo_titulo.set("")
        self.campo_subtitulo.set("")
        self.campo_data.set(datetime.now().strftime(FORMATO_DATA_TELA))
        self.campo_etiquetas.set("")
        self.campo_corpo.set("")
        self.campo_imagem.limpar()   # apaga a cópia provisória de uma imagem não salva
        self.campo_legenda.set("")
        self.campo_credito.set("")
        self.campo_status.set("rascunho")
        self.var_destaque.set(False)
        self.rotulo_feedback.configure(text="")
        self.chip_estado.configure(text="NOVA MATÉRIA")
        self.botao_atualizar.configure(state="disabled")
        self.botao_excluir.configure(state="disabled")
        self._atualizar_contadores()

    def nova_materia(self):
        """Chamado pelo botão '+ Nova matéria' do cabeçalho."""
        self._limpar_form()
        self.campo_titulo.focus()

    def _editar_do_cartao(self, noticia_id):
        """EDITAR no cartão abre a matéria no editor completo (antes carregava o editor rápido, que fica
        fora da vista e parecia que o botão não fazia nada). Sem editor completo, usa o rápido."""
        if self.ao_editar_completo:
            self.ao_editar_completo(noticia_id, None)
        else:
            self._editar(noticia_id)

    def _editar(self, noticia_id):
        resultado = self.servico.obter(noticia_id)
        if not self._mostrar(resultado, "Notícias"):
            return
        n = resultado.dados
        self._id_edicao = n["id"]
        self.campo_titulo.set(n["titulo"])
        self.campo_subtitulo.set(n["subtitulo"] or "")
        self.campo_categoria.set(n["categoria_id"])
        self.campo_autor.set(n["autor_id"])
        self.campo_data.set(_para_texto_tela(n["data_publicacao"]))
        self.campo_status.set(n["status"])
        self.campo_etiquetas.set(", ".join("#" + e for e in lista_etiquetas(n["etiquetas"])))
        self.var_destaque.set(bool(n["destaque"]))
        self.campo_corpo.set(n["conteudo"] or "")
        self.campo_imagem.definir(n["imagem"])
        self.campo_legenda.set(n["imagem_legenda"] or "")
        self.campo_credito.set(n["imagem_credito"] or "")
        self.rotulo_feedback.configure(text="")
        self.chip_estado.configure(text=f"EDITANDO • ID: #NW-{int(n['id']):04d}")
        self.botao_atualizar.configure(state="normal")
        self.botao_excluir.configure(state="normal")
        self._atualizar_contadores()
        self.campo_titulo.focus()

    def _dados_form(self) -> dict:
        return dict(
            titulo=self.campo_titulo.get(),
            categoria_id=self.campo_categoria.get(),
            autor_id=self.campo_autor.get(),
            conteudo=self.campo_corpo.get(),
            subtitulo=self.campo_subtitulo.get(),
            status=self.campo_status.get(),
            destaque=self.var_destaque.get(),
            etiquetas=self.campo_etiquetas.get(),
            data=self.campo_data.get(),
            imagem=self.campo_imagem.caminho,
            imagem_legenda=self.campo_legenda.get(),
            imagem_credito=self.campo_credito.get(),
        )

    def _concluir(self, resultado):
        """Trata o retorno de criar/atualizar/excluir; True se deu certo."""
        if not self._mostrar(resultado, "Notícias"):
            return False
        mensagem = resultado.mensagem
        self.campo_imagem.confirmar_salvo()   # a imagem do formulário passa a ser a oficial
        self._limpar_form()
        self.rotulo_feedback.configure(text=mensagem)
        self.recarregar()
        self._avisar_alteracao()
        return True

    def _adicionar(self):
        self._concluir(self.servico.criar(**self._dados_form()))

    def _atualizar(self):
        if self._id_edicao is None:
            messagebox.showwarning(
                "Notícias", "Para alterar uma matéria existente, clique em EDITAR no cartão dela no feed (abre o editor completo).")
            return
        self._concluir(self.servico.atualizar(self._id_edicao, **self._dados_form()))

    def _excluir_em_edicao(self):
        if self._id_edicao is None:
            return
        resultado = self.servico.obter(self._id_edicao)
        if self._mostrar(resultado, "Notícias"):
            self._excluir_do_feed(resultado.dados)

    def _excluir_do_feed(self, noticia):
        if not messagebox.askyesno(
                "Excluir matéria",
                f"Excluir a matéria \"{noticia['titulo']}\"?\nEssa ação não pode ser desfeita."):
            return
        resultado = self.servico.excluir(noticia["id"])
        if not self._mostrar(resultado, "Notícias"):
            return
        if self._id_edicao == noticia["id"]:
            self._limpar_form()
        self.rotulo_feedback.configure(text=resultado.mensagem)
        self.recarregar()
        self._avisar_alteracao()

    # =====================================================================
    # Leitura
    # =====================================================================
    def _ler(self, noticia):
        """Abre a página de leitura (ela registra a leitura se a matéria estiver publicada)."""
        if self.ao_ler:
            self.ao_ler(noticia["id"])

    def _abrir_editor_completo(self):
        """Leva o que está no editor rápido para o editor redacional completo."""
        if not self.ao_editar_completo:
            return
        if self._id_edicao is not None:
            self.ao_editar_completo(self._id_edicao, None)
            return
        dados = dict(
            titulo=self.campo_titulo.get(), subtitulo=self.campo_subtitulo.get(),
            conteudo=self.campo_corpo.get(), categoria_id=self.campo_categoria.get(),
            autor_id=self.campo_autor.get(), data=self.campo_data.get(),
            status=self.campo_status.get(), destaque=bool(self.var_destaque.get()),
            etiquetas=self.campo_etiquetas.get(), imagem=self.campo_imagem.caminho,
            imagem_legenda=self.campo_legenda.get(), imagem_credito=self.campo_credito.get(),
            imagem_provisoria=True,
        )
        self.campo_imagem.confirmar_salvo()   # a imagem segue com o editor completo
        self._limpar_form()
        self.ao_editar_completo(None, dados)

    # ---------- atalhos usados por outras telas ----------
    def buscar(self, termo):
        """Mostra o feed filtrado por um texto (ex.: nome de autor ou etiqueta)."""
        self.var_busca.set(termo or "")
        self._pagina_atual = 1
        self.recarregar()

    def filtrar_categoria(self, categoria_id):
        """Mostra o feed só com as matérias de uma editoria."""
        self._recarregar_opcoes()
        self._filtro_categoria = categoria_id if categoria_id in self._chaves_filtro_categoria else None
        self.combo_categoria.current(self._chaves_filtro_categoria.index(self._filtro_categoria))
        self.var_busca.set("")
        self._pagina_atual = 1
        self.recarregar()
