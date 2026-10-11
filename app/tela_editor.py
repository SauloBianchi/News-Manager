"""
tela_editor.py
Tela "Nova Matéria / Editor Redacional" do NewsManager (protótipo Stitch
nova_mat_ria_editor_redacional), como tela inteira:

- trilha no topo (← Notícias / Oficina de Redação / Matéria nº), aviso de
  "alterações não salvas" e horário do último auto-salvamento;
- título nobre com contador (x / 120), linha fina / lead editorial;
- barra de ferramentas do texto: negrito, itálico, sublinhado, intertítulos
  (H2/H3), citação, link, listas, imagem no texto e filete — o texto usa
  marcadores simples (veja texto_rico.py) e o editor realça o que foi
  formatado; atalhos Ctrl+B / Ctrl+I / Ctrl+U / Ctrl+S;
- contadores (palavras, caracteres, colunas físicas) e "ficha de rotativa"
  (colunas, legibilidade Flesch, tempo de leitura, embargo);
- "Registro editorial": editoria, jornalista, data e hora de emissão,
  fotografia de capa (legenda e crédito), manchete de capa, estado de
  publicação e etiquetas;
- barra inferior: Cancelar, Salvar rascunho e Publicar matéria;
- auto-salvamento local a cada 20 s (pasta rascunhos/) com recuperação ao
  reabrir a matéria. O auto-salvamento NUNCA grava no banco: uma matéria
  publicada só muda quando você clica em Salvar ou Publicar.

Toda a regra de negócio (validações, imagens) fica em NoticiaService.
"""

import json
import re
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from . import theme as t
from .midia import RAIZ_PROJETO, TIPOS_ARQUIVO_DIALOGO, ErroMidia
from .midia import midia as midia_global
from .noticias import FORMATO_DATA_TELA, STATUS_NOTICIA, NoticiaService, interpretar_data
from .notificacoes import Sessao
from .telas_cadastros import (
    MARGEM,
    PAINEL,
    PAINEL_ALTO,
    PAINEL_BAIXO,
    CampoImagem,
    CampoSelecao,
    _link,
    _TelaBase,
)
from .texto_rico import (
    caminhos_de_imagens,
    classificar_flesch,
    colunas_estimadas,
    contar_palavras,
    envolver,
    indice_flesch,
    inserir_linha,
    inserir_link,
    polegadas_de_coluna,
    prefixar_linhas,
    realces_inline,
    revisar_texto,
    tempo_leitura_texto,
    texto_simples,
    url_segura,
)

PASTA_RASCUNHOS = RAIZ_PROJETO / "rascunhos"
INTERVALO_AUTOSAVE_S = 20
TITULO_RECOMENDADO = 120
COR_LINK = "#2F5D8C"
COR_MARCADOR = "#B3AC9E"

DESCRICAO_ESTADO = {
    "rascunho": "Galé interna",
    "em_pauta": "Fila de apuração",
    "revisao": "Mesa de cópia",
    "publicado": "Acesso geral",
}
CAMPOS_FORM = ("titulo", "subtitulo", "conteudo", "categoria_id", "autor_id", "data", "status",
               "destaque", "etiquetas", "imagem", "imagem_legenda", "imagem_credito")


class ArmazemRascunho:
    """Guarda o auto-salvamento do editor em arquivos JSON locais (um por matéria)."""

    def __init__(self, base=None):
        self.base = Path(base) if base else PASTA_RASCUNHOS

    def _arquivo(self, chave) -> Path:
        return self.base / f"autosave_{chave}.json"

    def salvar(self, chave, dados) -> bool:
        try:
            self.base.mkdir(parents=True, exist_ok=True)
            self._arquivo(chave).write_text(
                json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
            return True
        except OSError:
            return False

    def ler(self, chave):
        try:
            dados = json.loads(self._arquivo(chave).read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else None
        except (OSError, ValueError):
            return None

    def apagar(self, chave):
        try:
            self._arquivo(chave).unlink()
        except OSError:
            pass


class EditorFrame(_TelaBase):
    def __init__(self, parent, db, logger, ao_ler=None, ao_voltar=None, ao_alterar=None,
                 armazem=None):
        super().__init__(parent, db, logger, ao_alterar)
        self.servico = NoticiaService(db, logger, midia_global)
        self.ao_ler = ao_ler
        self.ao_voltar = ao_voltar
        self.armazem = armazem or ArmazemRascunho()

        self._id = None                  # None = matéria nova
        self._status_original = None     # estado gravado no banco (para avisar ao despublicar)
        self._carregando = False
        self._snap_salvo = None
        self._ultimo_estado = None
        self._imagens_sessao = set()     # imagens inseridas no texto nesta sessão
        self._etiquetas = []
        self._tique = 0
        self._after_digitar = None
        self._apontamentos = []          # problemas de redação (preferência "revisão automática")

        self.var_titulo = tk.StringVar()
        self.var_subtitulo = tk.StringVar()
        self.var_destaque = tk.BooleanVar(value=False)
        self.var_status = tk.StringVar(value="rascunho")

        self._montar()
        self._montar_barra_inferior()
        self._recarregar_opcoes()
        self.carregar(None, oferecer_recuperacao=False)   # sem perguntas na abertura do programa
        self.after(1000, self._tique_periodico)

    # =====================================================================
    # Montagem
    # =====================================================================
    def _montar(self):
        p = self.pagina
        self._montar_trilha(p)
        corpo = tk.Frame(p, bg=t.BG)
        corpo.pack(fill="x", padx=MARGEM, pady=(14, 0))
        corpo.grid_columnconfigure(0, weight=1)
        corpo.grid_columnconfigure(1, minsize=340)
        esquerda = tk.Frame(corpo, bg=t.BG)
        esquerda.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        direita = tk.Frame(corpo, bg=t.BG)
        direita.grid(row=0, column=1, sticky="nsew")
        self._montar_titulo(esquerda)
        self._montar_ferramentas(esquerda)
        self._montar_texto(esquerda)
        self._montar_registro(direita)
        self._montar_ficha(direita)
        tk.Frame(p, bg=t.BG, height=24).pack()

    def _montar_trilha(self, pai):
        trilha = tk.Frame(pai, bg=t.BG)
        trilha.pack(fill="x", padx=MARGEM, pady=(14, 0))
        _link(trilha, "← NOTÍCIAS", self._cancelar, t.TEXT).pack(side="left")
        tk.Label(trilha, text="  /  OFICINA DE REDAÇÃO • GALÉ DIGITAL  /  ", fg=t.TEXT_MUTED, bg=t.BG,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        self.rotulo_materia = tk.Label(trilha, text="NOVA MATÉRIA", fg=t.PRIMARY, bg=t.BG,
                                       font=t.Fontes.corpo(8, "bold"))
        self.rotulo_materia.pack(side="left")
        direita = tk.Frame(trilha, bg=t.BG)
        direita.pack(side="right")
        self.chip_alteracoes = tk.Label(direita, text="", fg=t.TEXT, bg=t.BG, padx=8, pady=3,
                                        font=t.Fontes.corpo(8, "bold"))
        self.chip_alteracoes.pack(side="left", padx=(0, 12))
        self.rotulo_autosave = tk.Label(direita, text="AUTO-SALVAMENTO: AINDA NÃO REALIZADO",
                                        fg=t.TEXT_MUTED, bg=t.BG, font=t.Fontes.corpo(8, "bold"))
        self.rotulo_autosave.pack(side="left", padx=(0, 12))
        self.link_leitura = _link(direita, "VER LEITURA", self._ver_leitura, t.TEXT)
        tk.Frame(pai, bg=t.BORDER, height=1).pack(fill="x", padx=MARGEM, pady=(8, 0))

    def _montar_titulo(self, pai):
        cartao = tk.Frame(pai, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        cartao.pack(fill="x")
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=22, pady=16)
        interno.pack(fill="x")
        topo = tk.Frame(interno, bg=t.SURFACE)
        topo.pack(fill="x")
        tk.Label(topo, text="TÍTULO NOBRE • 1ª PÁGINA", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        self.rotulo_titulo_contador = tk.Label(topo, text="", fg=t.TEXT_MUTED, bg=t.SURFACE,
                                               font=t.Fontes.corpo(8, "bold"))
        self.rotulo_titulo_contador.pack(side="right")
        self.entrada_titulo = tk.Entry(
            interno, textvariable=self.var_titulo, relief="flat", bd=0, bg=t.SURFACE, fg=t.TEXT,
            insertbackground=t.TEXT, font=t.Fontes.display(24))
        self.entrada_titulo.pack(fill="x", pady=(6, 4), ipady=6)
        tk.Frame(interno, bg=t.BORDER, height=1).pack(fill="x")
        sub = tk.Frame(interno, bg=t.SURFACE)
        sub.pack(fill="x", pady=(12, 0))
        tk.Label(sub, text="LINHA FINA / LEAD EDITORIAL", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        tk.Label(sub, text="Síntese de pauta", fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "normal italic")).pack(side="right")
        self.entrada_subtitulo = tk.Entry(
            interno, textvariable=self.var_subtitulo, relief="flat", bd=0, bg=t.SURFACE, fg=t.TEXT_MUTED,
            insertbackground=t.TEXT, font=t.Fontes.display(14, "normal", True))
        self.entrada_subtitulo.pack(fill="x", pady=(6, 4), ipady=4)
        tk.Frame(interno, bg=t.BORDER, height=1).pack(fill="x")

    def _montar_ferramentas(self, pai):
        barra = tk.Frame(pai, bg=PAINEL, highlightthickness=1, highlightbackground=t.BORDER)
        barra.pack(fill="x", pady=(14, 0))
        linha = tk.Frame(barra, bg=PAINEL, padx=8, pady=6)
        linha.pack(fill="x")
        fam = t.Fontes._corpo
        grupos = [
            [("B", "Negrito (Ctrl+B)", lambda: self._acao_envolver("**"), (fam, 10, "bold")),
             ("I", "Itálico (Ctrl+I)", lambda: self._acao_envolver("*"), (fam, 10, "italic")),
             ("U", "Sublinhado (Ctrl+U)", lambda: self._acao_envolver("__"), (fam, 10, "underline"))],
            [("H2", "Intertítulo", lambda: self._acao_prefixo("h2"), None),
             ("H3", "Subintertítulo", lambda: self._acao_prefixo("h3"), None)],
            [("“ ”", "Citação em destaque", lambda: self._acao_prefixo("citacao"), None),
             ("LINK", "Inserir link", self._acao_link, None)],
            [("•", "Lista", lambda: self._acao_prefixo("lista"), None),
             ("1.", "Lista numerada", lambda: self._acao_prefixo("numerada"), None),
             ("IMG", "Inserir imagem no texto", self._acao_imagem, None),
             ("—", "Filete horizontal", self._acao_filete, None)],
        ]
        self.botoes_ferramenta = {}
        for indice, grupo in enumerate(grupos):
            if indice:
                tk.Frame(linha, bg=t.BORDER, width=1).pack(side="left", fill="y", padx=6)
            for rotulo, dica, comando, fonte in grupo:
                b = tk.Label(linha, text=rotulo, bg=t.SURFACE, fg=t.TEXT, padx=9, pady=4,
                             cursor="hand2", font=fonte or t.Fontes.corpo(9, "bold"),
                             highlightthickness=1, highlightbackground=t.BORDER)
                b.pack(side="left", padx=2)
                b.bind("<Button-1>", lambda e, c=comando: c())
                self.botoes_ferramenta[rotulo] = b
        self.rotulo_contadores = tk.Label(barra, text="", fg=t.PRIMARY, bg=PAINEL, anchor="w",
                                          font=t.Fontes.corpo(8, "bold"), padx=10, pady=4)
        self.rotulo_contadores.pack(fill="x")
        self.rotulo_contadores.bind("<Button-1>", lambda e: self._mostrar_apontamentos())

    def _montar_texto(self, pai):
        quadro = tk.Frame(pai, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        quadro.pack(fill="x")
        self.texto = tk.Text(
            quadro, wrap="word", undo=True, relief="flat", bd=0, bg=t.SURFACE, fg=t.TEXT,
            insertbackground=t.TEXT, font=t.Fontes.display(13, "normal"), height=24,
            padx=22, pady=16, spacing1=2, spacing3=6, highlightthickness=0)
        self.texto.pack(fill="x")
        f = t.Fontes
        x = self.texto
        x.tag_configure("md_negrito", font=f.display(13, "bold"))
        x.tag_configure("md_italico", font=f.display(13, "normal", True))
        x.tag_configure("md_sublinhado", underline=True)
        x.tag_configure("md_link", foreground=COR_LINK, underline=True)
        x.tag_configure("md_h2", font=f.display(18, "bold"), foreground=t.PRIMARY)
        x.tag_configure("md_h3", font=f.display(15, "bold"), foreground=t.PRIMARY)
        x.tag_configure("md_citacao", font=f.display(13, "normal", True), foreground=t.TEXT_MUTED,
                        lmargin1=16, lmargin2=16, background=PAINEL_BAIXO)
        x.tag_configure("md_marcador", foreground=COR_MARCADOR)
        x.tag_configure("md_revisao", background="#FFE9A8")
        x.bind("<KeyRelease>", lambda e: self._corpo_mudou())
        x.bind("<Control-b>", lambda e: self._atalho(lambda: self._acao_envolver("**")))
        x.bind("<Control-i>", lambda e: self._atalho(lambda: self._acao_envolver("*")))
        x.bind("<Control-u>", lambda e: self._atalho(lambda: self._acao_envolver("__")))
        x.bind("<Control-s>", lambda e: self._atalho(lambda: self._salvar("rascunho")))
        rodape = tk.Frame(pai, bg=PAINEL_BAIXO, highlightthickness=1, highlightbackground=t.BORDER)
        rodape.pack(fill="x")
        tk.Label(rodape, text="■ MARCADORES: **negrito**  *itálico*  __sublinhado__  ## intertítulo  > citação",
                 fg=t.TEXT_MUTED, bg=PAINEL_BAIXO, font=t.Fontes.corpo(7, "bold"), padx=10, pady=5).pack(
            side="left")
        tk.Label(rodape, text="CTRL+B  CTRL+I  CTRL+U  CTRL+S", fg=t.TEXT_MUTED, bg=PAINEL_BAIXO,
                 font=t.Fontes.corpo(7, "bold"), padx=10).pack(side="right")

    # ---------- coluna direita ----------
    def _montar_registro(self, pai):
        cartao = tk.Frame(pai, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        cartao.pack(fill="x")
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=16, pady=14)
        interno.pack(fill="x")
        tk.Label(interno, text="REGISTRO EDITORIAL", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(15)).pack(anchor="w")
        tk.Frame(interno, bg=t.TEXT, height=2).pack(fill="x", pady=(4, 10))

        self.campo_categoria = CampoSelecao(interno, "CADERNO / EDITORIA *", {})
        self.campo_categoria.pack(fill="x", pady=(0, 8))
        self.campo_autor = CampoSelecao(interno, "ASSINATURA / JORNALISTA *", {})
        self.campo_autor.pack(fill="x", pady=(0, 8))

        quando = tk.Frame(interno, bg=t.SURFACE)
        quando.pack(fill="x", pady=(0, 8))
        quando.grid_columnconfigure(0, weight=3)
        quando.grid_columnconfigure(1, weight=2)
        self.campo_data = t.CampoEditorial(quando, "DATA DE EMISSÃO", dica="DD/MM/AAAA")
        self.campo_data.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.campo_hora = t.CampoEditorial(quando, "HORÁRIO", dica="HH:MM")
        self.campo_hora.grid(row=0, column=1, sticky="ew")

        self.campo_imagem = CampoImagem(interno, "FOTOGRAFIA DE CAPA", "noticias", largura=290, altura=140)
        self.campo_imagem.pack(anchor="w", pady=(2, 6))
        self.campo_legenda = t.CampoEditorial(interno, "LEGENDA DA FOTOGRAFIA")
        self.campo_legenda.pack(fill="x", pady=(0, 6))
        self.campo_credito = t.CampoEditorial(interno, "CRÉDITO")
        self.campo_credito.pack(fill="x", pady=(0, 8))

        destaque = tk.Frame(interno, bg=PAINEL_BAIXO, padx=10, pady=8)
        destaque.pack(fill="x", pady=(0, 10))
        tk.Checkbutton(
            destaque, text="MANCHETE DE CAPA • DESTAQUE ABSOLUTO", variable=self.var_destaque,
            bg=PAINEL_BAIXO, fg=t.PRIMARY, activebackground=PAINEL_BAIXO, selectcolor=t.SURFACE,
            font=t.Fontes.corpo(8, "bold"), anchor="w", cursor="hand2").pack(anchor="w")
        tk.Label(destaque, text="Posiciona a notícia em destaque no feed. Só vale para matérias publicadas.",
                 fg=t.TEXT_MUTED, bg=PAINEL_BAIXO, font=t.Fontes.corpo(8), wraplength=270,
                 justify="left").pack(anchor="w", pady=(2, 0))

        tk.Label(interno, text="ESTADO DE PUBLICAÇÃO", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        grade = tk.Frame(interno, bg=t.SURFACE)
        grade.pack(fill="x", pady=(4, 10))
        grade.grid_columnconfigure(0, weight=1, uniform="estado")
        grade.grid_columnconfigure(1, weight=1, uniform="estado")
        for indice, (chave, rotulo) in enumerate(STATUS_NOTICIA.items()):
            caixa = tk.Frame(grade, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER,
                             padx=6, pady=4)
            caixa.grid(row=indice // 2, column=indice % 2, sticky="ew", padx=2, pady=2)
            tk.Radiobutton(caixa, text=rotulo.upper(), variable=self.var_status, value=chave,
                           bg=t.SURFACE, activebackground=t.SURFACE, selectcolor=t.SURFACE,
                           font=t.Fontes.corpo(8, "bold"), anchor="w", cursor="hand2").pack(anchor="w")
            tk.Label(caixa, text=DESCRICAO_ESTADO[chave], fg=t.TEXT_MUTED, bg=t.SURFACE,
                     font=t.Fontes.corpo(7)).pack(anchor="w", padx=20)

        tk.Label(interno, text="ETIQUETAS / INDEXAÇÃO TEMÁTICA", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        self.area_etiquetas = tk.Frame(interno, bg=t.SURFACE)
        self.area_etiquetas.pack(fill="x", pady=(4, 4))
        linha = tk.Frame(interno, bg=t.SURFACE)
        linha.pack(fill="x")
        self.campo_etiqueta = t.CampoEditorial(linha, "", dica="")
        self.campo_etiqueta.pack(side="left", fill="x", expand=True)
        self.campo_etiqueta.entry.bind("<Return>", lambda e: self._adicionar_etiqueta())
        t.botao_secundario(linha, "+", self._adicionar_etiqueta).pack(side="left", padx=(6, 0), anchor="s")

    def _montar_ficha(self, pai):
        cartao = tk.Frame(pai, bg=PAINEL, highlightthickness=1, highlightbackground=t.BORDER)
        cartao.pack(fill="x", pady=(14, 0))
        interno = tk.Frame(cartao, bg=PAINEL, padx=16, pady=12)
        interno.pack(fill="x")
        topo = tk.Frame(interno, bg=PAINEL)
        topo.pack(fill="x")
        tk.Label(topo, text="FICHA DE ROTATIVA", fg=t.TEXT, bg=PAINEL,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        self.valores_ficha = {}
        for chave, rotulo in (("colunas", "Estimativa de colunas:"),
                              ("flesch", "Índice de legibilidade Flesch:"),
                              ("leitura", "Tempo médio de leitura:"),
                              ("embargo", "Bloqueio de galé (embargo):")):
            linha = tk.Frame(interno, bg=PAINEL)
            linha.pack(fill="x", pady=(6, 0))
            tk.Label(linha, text=rotulo, fg=t.TEXT_MUTED, bg=PAINEL, font=t.Fontes.corpo(9)).pack(side="left")
            valor = tk.Label(linha, text="—", fg=t.TEXT, bg=PAINEL, font=t.Fontes.corpo(9, "bold"))
            valor.pack(side="right")
            self.valores_ficha[chave] = valor

    def _montar_barra_inferior(self):
        # A barra fica fora da área rolável, sempre visível no pé da tela
        self.rolagem.pack_forget()
        barra = tk.Frame(self, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        barra.pack(side="bottom", fill="x")
        interno = tk.Frame(barra, bg=t.SURFACE, padx=MARGEM, pady=10)
        interno.pack(fill="x")
        self.rotulo_feedback = tk.Label(
            interno, text="Rascunhos são guardados automaticamente neste computador a cada 20 segundos.",
            fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(8, "bold"))
        self.rotulo_feedback.pack(side="left")
        t.botao_primario(interno, "Publicar matéria", lambda: self._salvar("publicar")).pack(side="right")
        t.botao_secundario(interno, "SALVAR RASCUNHO", lambda: self._salvar("rascunho")).pack(
            side="right", padx=(0, 8))
        _link(interno, "CANCELAR", self._cancelar, t.TEXT).pack(side="right", padx=(0, 16))
        self.rolagem.pack(fill="both", expand=True)

    # =====================================================================
    # Dados do formulário
    # =====================================================================
    def _recarregar_opcoes(self):
        self.campo_categoria.definir_opcoes({c["id"]: c["nome"] for c in self.db.listar_categorias()})
        self.campo_autor.definir_opcoes({a["id"]: a["nome"] for a in self.db.listar_autores()})

    def recarregar(self):
        self._recarregar_opcoes()

    def _corpo(self) -> str:
        return self.texto.get("1.0", "end-1c")

    def _data_hora_texto(self) -> str:
        return f"{self.campo_data.get().strip()} {self.campo_hora.get().strip()}".strip()

    def _form_dict(self) -> dict:
        return dict(
            titulo=self.var_titulo.get(), subtitulo=self.var_subtitulo.get(), conteudo=self._corpo(),
            categoria_id=self.campo_categoria.get(), autor_id=self.campo_autor.get(),
            data=self._data_hora_texto(), status=self.var_status.get(),
            destaque=bool(self.var_destaque.get()),
            etiquetas=", ".join("#" + e for e in self._etiquetas),
            imagem=self.campo_imagem.caminho, imagem_legenda=self.campo_legenda.get(),
            imagem_credito=self.campo_credito.get(),
        )

    def _snapshot(self):
        d = self._form_dict()
        return tuple((k, d[k] if d[k] is not None else "") for k in CAMPOS_FORM)

    def _aplicar_dict(self, d: dict, imagem_provisoria=False):
        self._carregando = True
        try:
            self.var_titulo.set(d.get("titulo") or "")
            self.var_subtitulo.set(d.get("subtitulo") or "")
            self.texto.delete("1.0", "end")
            self.texto.insert("1.0", d.get("conteudo") or "")
            self.texto.edit_reset()   # Ctrl+Z não deve "desfazer" o carregamento da matéria
            if d.get("categoria_id") is not None:
                self.campo_categoria.set(d["categoria_id"])
            if d.get("autor_id") is not None:
                self.campo_autor.set(d["autor_id"])
            data = interpretar_data(d.get("data")) if d.get("data") else None
            self.campo_data.set(data.strftime("%d/%m/%Y") if data else "")
            self.campo_hora.set(data.strftime("%H:%M") if data else "")
            self.var_status.set(d.get("status") or "rascunho")
            self.var_destaque.set(bool(d.get("destaque")))
            self._etiquetas = []
            for bruto in re.split(r"[,;\s]+", d.get("etiquetas") or ""):
                etiqueta = bruto.strip().lstrip("#")
                if etiqueta and etiqueta.lower() not in (e.lower() for e in self._etiquetas):
                    self._etiquetas.append(etiqueta)
            self._desenhar_etiquetas()
            if imagem_provisoria:
                self.campo_imagem.definir_provisoria(d.get("imagem"))
            else:
                self.campo_imagem.definir(d.get("imagem"))
            self.campo_legenda.set(d.get("imagem_legenda") or "")
            self.campo_credito.set(d.get("imagem_credito") or "")
        finally:
            self._carregando = False
        self._realcar()

    # =====================================================================
    # Abrir uma matéria
    # =====================================================================
    def carregar(self, noticia_id=None, dados_iniciais=None, oferecer_recuperacao=True):
        """Abre o editor com uma matéria existente, em branco ou com dados iniciais
        (por exemplo, vindos do editor rápido da tela de Notícias). Se houver um
        auto-salvamento dessa matéria, pergunta se o usuário quer recuperá-lo."""
        self._recarregar_opcoes()
        self._id = None
        self._status_original = None
        self._imagens_sessao = set()
        base = None
        if noticia_id is not None:
            resultado = self.servico.obter(noticia_id)
            if not resultado.ok:
                messagebox.showwarning("Editor", resultado.mensagem)
                if self.ao_voltar:
                    self.ao_voltar()
                return False
            n = resultado.dados
            self._id = n["id"]
            self._status_original = n["status"]
            base = dict(
                titulo=n["titulo"], subtitulo=n["subtitulo"], conteudo=n["conteudo"],
                categoria_id=n["categoria_id"], autor_id=n["autor_id"],
                data=interpretar_data(n["data_publicacao"]).strftime(FORMATO_DATA_TELA)
                if interpretar_data(n["data_publicacao"]) else "",
                status=n["status"], destaque=bool(n["destaque"]), etiquetas=n["etiquetas"] or "",
                imagem=n["imagem"], imagem_legenda=n["imagem_legenda"],
                imagem_credito=n["imagem_credito"])
            base["etiquetas"] = ", ".join("#" + e for e in (n["etiquetas"] or "").split(",") if e)
        else:
            base = dict(titulo="", subtitulo="", conteudo="",
                        categoria_id=self.campo_categoria.get(), autor_id=self.campo_autor.get(),
                        data=datetime.now().strftime(FORMATO_DATA_TELA), status="rascunho",
                        destaque=False, etiquetas="", imagem=None, imagem_legenda="", imagem_credito="")
        provisoria = False
        if dados_iniciais:
            base.update({k: v for k, v in dados_iniciais.items() if k != "imagem_provisoria"})
            provisoria = bool(dados_iniciais.get("imagem_provisoria"))
        self._aplicar_dict(base, imagem_provisoria=provisoria)
        self._snap_salvo = self._snapshot()
        if dados_iniciais:
            self._snap_salvo = None   # veio de fora: conta como alteração ainda não salva
        elif oferecer_recuperacao:
            self._oferecer_recuperacao()
        self._ultimo_estado = None
        self.rotulo_materia.configure(
            text="NOVA MATÉRIA" if self._id is None else f"MATÉRIA Nº {self._id:04d}")
        if self._id is None:
            self.link_leitura.pack_forget()
        else:
            self.link_leitura.pack(side="left")
        self.rotulo_autosave.configure(text="AUTO-SALVAMENTO: AINDA NÃO REALIZADO")
        self.rotulo_feedback.configure(
            text="Rascunhos são guardados automaticamente neste computador a cada 20 segundos.")
        self._atualizar_estado()
        self.entrada_titulo.focus_set()
        return True

    def _chave(self) -> str:
        return str(self._id) if self._id is not None else "novo"

    def _oferecer_recuperacao(self):
        guardado = self.armazem.ler(self._chave())
        if not guardado:
            return
        atual = self._form_dict()
        igual = all((guardado.get(k) or "") == (atual.get(k) or "") for k in CAMPOS_FORM
                    if k not in ("categoria_id", "autor_id", "destaque"))
        if igual:
            self.armazem.apagar(self._chave())
            return
        quando = ""
        try:
            quando = datetime.fromisoformat(guardado.get("_salvo_em", "")).strftime("%d/%m/%Y às %H:%M")
        except ValueError:
            pass
        if messagebox.askyesno(
                "Recuperar rascunho",
                f"Há um auto-salvamento desta matéria{' de ' + quando if quando else ''}.\n"
                "Deseja recuperá-lo? (Ele ainda não foi gravado no banco.)"):
            self._aplicar_dict(guardado)
        else:
            self.armazem.apagar(self._chave())

    # =====================================================================
    # Estado: alterações, contadores, ficha, auto-salvamento
    # =====================================================================
    def tem_alteracoes(self) -> bool:
        return self._snap_salvo is None or self._snapshot() != self._snap_salvo

    def _corpo_mudou(self):
        if self._carregando:
            return
        if self._after_digitar is not None:
            self.after_cancel(self._after_digitar)
        self._after_digitar = self.after(250, self._apos_digitar)

    def _apos_digitar(self):
        self._after_digitar = None
        self._realcar()
        self._atualizar_estado()

    def _tique_periodico(self):
        try:
            if self.winfo_ismapped():
                self._atualizar_estado()
                self._tique += 1
                if self._tique % INTERVALO_AUTOSAVE_S == 0:
                    self._autosalvar()
            self.after(1000, self._tique_periodico)
        except tk.TclError:
            pass   # a janela foi fechada

    def _atualizar_estado(self):
        corpo = self._corpo()
        form = self._form_dict()
        chave = (corpo, form["titulo"], form["data"], form["status"], self._snap_salvo is None,
                 Sessao.ativa("polegadas_coluna"))
        simples = texto_simples(corpo)
        palavras = contar_palavras(simples)

        tamanho = len(" ".join(self.var_titulo.get().split()))
        self.rotulo_titulo_contador.configure(
            text=f"{tamanho} / {TITULO_RECOMENDADO} CARACTERES RECOMENDADOS",
            fg=t.ERROR if tamanho > TITULO_RECOMENDADO else t.TEXT_MUTED)
        def milhar(numero):
            return f"{numero:,}".replace(",", ".")
        medida = (polegadas_de_coluna(palavras).upper() + " DE COLUNA" if Sessao.ativa("polegadas_coluna")
                  else f"{milhar(len(corpo))} CARACTERES")
        revisao = ""
        if Sessao.ativa("revisao_automatica"):
            n = len(self._apontamentos)
            revisao = f"  •  REVISÃO: {n} APONTAMENTO(S)" + (" (CLIQUE PARA VER)" if n else " ✓")
        self.rotulo_contadores.configure(
            text=f"{milhar(palavras)} PALAVRAS  •  {medida}  •  "
                 f"~{colunas_estimadas(palavras).upper()} FÍSICAS{revisao}")
        if chave != self._ultimo_estado:   # a ficha é a parte mais "cara": só recalcula se mudou
            self._ultimo_estado = chave
            flesch = indice_flesch(simples)
            colunas = colunas_estimadas(palavras)
            self.valores_ficha["colunas"].configure(
                text=f"{colunas} ({polegadas_de_coluna(palavras)})" if Sessao.ativa("polegadas_coluna") else colunas)
            self.valores_ficha["flesch"].configure(
                text="—" if flesch is None else f"{flesch}/100 ({classificar_flesch(flesch)})")
            self.valores_ficha["leitura"].configure(text=tempo_leitura_texto(palavras))
            self.valores_ficha["embargo"].configure(text=self._texto_embargo(form))
        if self.tem_alteracoes():
            self.chip_alteracoes.configure(text="● ALTERAÇÕES NÃO SALVAS", bg=PAINEL, fg=t.PRIMARY)
        else:
            self.chip_alteracoes.configure(text="✓ TUDO SALVO", bg=t.BG, fg=t.TEXT_MUTED)

    @staticmethod
    def _texto_embargo(form) -> str:
        """Matéria publicada com data de emissão no futuro fica sob embargo até lá."""
        quando = interpretar_data(form["data"]) if form["data"] else None
        if form["status"] == "publicado" and quando and quando > datetime.now():
            return "Ativo até " + quando.strftime("%d/%m %H:%M")
        return "Desativado"

    def _autosalvar(self):
        if not self.tem_alteracoes():
            return False
        d = self._form_dict()
        if not (d["titulo"].strip() or d["conteudo"].strip()):
            return False
        d["_salvo_em"] = datetime.now().isoformat(timespec="seconds")
        if self.armazem.salvar(self._chave(), d):
            self.rotulo_autosave.configure(
                text="ÚLTIMO AUTO-SALVAMENTO: " + datetime.now().strftime("%H:%M:%S"))
            return True
        return False

    # =====================================================================
    # Realce do texto
    # =====================================================================
    def _realcar(self):
        x = self.texto
        for tag in ("md_negrito", "md_italico", "md_sublinhado", "md_link", "md_h2", "md_h3",
                    "md_citacao", "md_marcador", "md_revisao"):
            x.tag_remove(tag, "1.0", "end")
        for numero, linha in enumerate(self._corpo().split("\n"), start=1):
            if linha.startswith("### "):
                x.tag_add("md_h3", f"{numero}.0", f"{numero}.end")
                x.tag_add("md_marcador", f"{numero}.0", f"{numero}.4")
            elif linha.startswith("## "):
                x.tag_add("md_h2", f"{numero}.0", f"{numero}.end")
                x.tag_add("md_marcador", f"{numero}.0", f"{numero}.3")
            elif linha.startswith(">"):
                x.tag_add("md_citacao", f"{numero}.0", f"{numero}.end")
                x.tag_add("md_marcador", f"{numero}.0", f"{numero}.1")
            realces, marcadores = realces_inline(linha)
            for tag, ini, fim in realces:
                x.tag_add(f"md_{tag}", f"{numero}.{ini}", f"{numero}.{fim}")
            for ini, fim in marcadores:
                x.tag_add("md_marcador", f"{numero}.{ini}", f"{numero}.{fim}")
        x.tag_raise("md_marcador")
        self._apontamentos = revisar_texto(self._corpo()) if Sessao.ativa("revisao_automatica") else []
        for a in self._apontamentos:
            x.tag_add("md_revisao", f"{a['linha']}.{a['inicio']}", f"{a['linha']}.{a['fim']}")
        x.tag_lower("md_revisao")

    def _mostrar_apontamentos(self):
        """Lista os problemas encontrados pela revisão automática (clique no contador)."""
        if not Sessao.ativa("revisao_automatica") or not self._apontamentos:
            return
        linhas = self._corpo().split("\n")
        itens = []
        for a in self._apontamentos[:15]:
            trecho = linhas[a["linha"] - 1][a["inicio"]:a["fim"]].strip() or "…"
            itens.append(f"Linha {a['linha']}: {a['mensagem']}  →  “{trecho[:40]}”")
        extra = f"\n… e mais {len(self._apontamentos) - 15}." if len(self._apontamentos) > 15 else ""
        messagebox.showinfo("Revisão automática", "\n".join(itens) + extra)

    # =====================================================================
    # Barra de ferramentas
    # =====================================================================
    def _atalho(self, acao):
        acao()
        return "break"

    def _posicao(self, indice) -> int:
        """'linha.coluna' do Tk -> número de caracteres desde o início do texto."""
        return len(self.texto.get("1.0", indice))

    def _selecao(self):
        texto = self._corpo()
        try:
            a, b = self._posicao("sel.first"), self._posicao("sel.last")
        except tk.TclError:
            a = b = self._posicao("insert")
        return texto, a, b

    def _aplicar_edicao(self, edicao):
        inicio, fim, novo, sel_a, sel_b = edicao
        x = self.texto
        x.delete(f"1.0+{inicio}c", f"1.0+{fim}c")
        if novo:
            x.insert(f"1.0+{inicio}c", novo)
        x.tag_remove("sel", "1.0", "end")
        if sel_a != sel_b:
            x.tag_add("sel", f"1.0+{sel_a}c", f"1.0+{sel_b}c")
        x.mark_set("insert", f"1.0+{sel_b}c")
        x.focus_set()
        x.see("insert")
        self._corpo_mudou()

    def _acao_envolver(self, marcador):
        texto, a, b = self._selecao()
        self._aplicar_edicao(envolver(texto, a, b, marcador))

    def _acao_prefixo(self, tipo):
        texto, a, b = self._selecao()
        self._aplicar_edicao(prefixar_linhas(texto, a, b, tipo))

    def _acao_filete(self):
        texto, a, _b = self._selecao()
        self._aplicar_edicao(inserir_linha(texto, a, "---"))

    def _acao_link(self):
        url = simpledialog.askstring("Inserir link", "Endereço do link (começa com https://):", parent=self)
        if not url:
            return
        url = url.strip()
        if not url_segura(url):
            messagebox.showwarning("Link", "Use um endereço que comece com http:// ou https://")
            return
        texto, a, b = self._selecao()
        self._aplicar_edicao(inserir_link(texto, a, b, url))

    def _acao_imagem(self):
        origem = filedialog.askopenfilename(title="Escolher imagem para o texto",
                                            filetypes=TIPOS_ARQUIVO_DIALOGO)
        if not origem:
            return
        try:
            caminho = midia_global.importar(origem, "noticias")
        except ErroMidia as erro:
            messagebox.showwarning("Imagem", str(erro))
            return
        legenda = simpledialog.askstring("Legenda", "Legenda da imagem (opcional):", parent=self) or ""
        legenda = re.sub(r"[\[\]()\n]", " ", legenda).strip()
        self._imagens_sessao.add(caminho)
        texto, a, _b = self._selecao()
        self._aplicar_edicao(inserir_linha(texto, a, f"![{legenda}]({caminho})"))

    # =====================================================================
    # Etiquetas
    # =====================================================================
    def _adicionar_etiqueta(self):
        for bruto in re.split(r"[,;\s]+", self.campo_etiqueta.get()):
            etiqueta = bruto.strip().lstrip("#")
            if not etiqueta:
                continue
            if len(etiqueta) > 30:
                messagebox.showwarning("Etiquetas", "Cada etiqueta pode ter no máximo 30 caracteres.")
                return
            if etiqueta.lower() in (e.lower() for e in self._etiquetas):
                continue
            if len(self._etiquetas) >= 8:
                messagebox.showwarning("Etiquetas", "Use no máximo 8 etiquetas.")
                break
            self._etiquetas.append(etiqueta)
        self.campo_etiqueta.set("")
        self._desenhar_etiquetas()

    def _remover_etiqueta(self, etiqueta):
        self._etiquetas = [e for e in self._etiquetas if e != etiqueta]
        self._desenhar_etiquetas()

    def _desenhar_etiquetas(self):
        for filho in self.area_etiquetas.winfo_children():
            filho.destroy()
        for etiqueta in self._etiquetas:
            chip = tk.Frame(self.area_etiquetas, bg=PAINEL_ALTO)
            chip.pack(side="left", padx=(0, 4), pady=2)
            tk.Label(chip, text="#" + etiqueta, fg=t.TEXT, bg=PAINEL_ALTO, padx=6, pady=2,
                     font=t.Fontes.corpo(8, "bold")).pack(side="left")
            remover = tk.Label(chip, text="×", fg=t.TEXT_MUTED, bg=PAINEL_ALTO, padx=4, cursor="hand2",
                               font=t.Fontes.corpo(9, "bold"))
            remover.pack(side="left")
            remover.bind("<Button-1>", lambda e, tag=etiqueta: self._remover_etiqueta(tag))

    # =====================================================================
    # Salvar, cancelar, sair
    # =====================================================================
    def _dados_servico(self, status) -> dict:
        d = self._form_dict()
        return dict(
            titulo=d["titulo"], categoria_id=d["categoria_id"], autor_id=d["autor_id"],
            conteudo=d["conteudo"], subtitulo=d["subtitulo"], status=status,
            destaque=bool(d["destaque"]) and status == "publicado",
            etiquetas=d["etiquetas"], data=d["data"], imagem=d["imagem"],
            imagem_legenda=d["imagem_legenda"], imagem_credito=d["imagem_credito"],
        )

    def _salvar(self, modo):
        """modo 'rascunho': grava no estado escolhido (menos 'Publicado', que vira
        rascunho); modo 'publicar': grava como publicada."""
        escolhido = self.var_status.get()
        status = "publicado" if modo == "publicar" else (escolhido if escolhido != "publicado" else "rascunho")
        if modo == "rascunho" and self._status_original == "publicado" and status != "publicado":
            if not messagebox.askyesno(
                    "Despublicar matéria",
                    "Esta matéria está publicada. Salvar como rascunho a tira da edição.\nContinuar?"):
                return False
        dados = self._dados_servico(status)
        if self._id is None:
            resultado = self.servico.criar(**dados)
        else:
            resultado = self.servico.atualizar(self._id, **dados)
        if not resultado.ok:
            messagebox.showwarning("Editor", resultado.mensagem)
            return False

        self._id = resultado.dados
        self._status_original = status
        self.campo_imagem.confirmar_salvo()
        for caminho in self._imagens_sessao - caminhos_de_imagens(dados["conteudo"]):
            self.servico.descartar_imagem_orfa(caminho)   # inserida e depois removida do texto
        self._imagens_sessao.clear()
        self.armazem.apagar("novo")
        self.armazem.apagar(str(self._id))
        self.var_status.set(status)
        self._snap_salvo = self._snapshot()
        self._ultimo_estado = None
        self.rotulo_materia.configure(text=f"MATÉRIA Nº {self._id:04d}")
        self.link_leitura.pack(side="left")
        self.rotulo_feedback.configure(
            text=f"✓ {resultado.mensagem}  ({datetime.now().strftime('%H:%M:%S')})", fg=t.SUCCESS)
        self._atualizar_estado()
        self._avisar_alteracao()
        if modo == "publicar" and self.ao_ler:
            self.ao_ler(self._id, False)
        return True

    def descartar(self):
        """Joga fora o que não foi salvo: cópias provisórias de imagem e auto-salvamento."""
        for caminho in list(self._imagens_sessao):
            self.servico.descartar_imagem_orfa(caminho)
        self._imagens_sessao.clear()
        self.campo_imagem.limpar()
        self.armazem.apagar(self._chave())
        self._snap_salvo = self._snapshot()   # marca como "sem alterações"

    def confirmar_saida(self) -> bool:
        """Chamado antes de sair da tela. Se houver alterações, pergunta; devolve
        False se o usuário preferir continuar editando."""
        if self.tem_alteracoes():
            if not messagebox.askyesno(
                    "Alterações não salvas",
                    "Há alterações que não foram salvas. Sair e descartá-las?"):
                return False
        self.descartar()
        return True

    def _cancelar(self):
        if self.confirmar_saida() and self.ao_voltar:
            self.ao_voltar()

    def _ver_leitura(self):
        if self._id is not None and self.ao_ler and self.confirmar_saida():
            self.ao_ler(self._id, False)
