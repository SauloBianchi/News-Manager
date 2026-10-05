"""
tela_leitura.py
Página "Leitura da Matéria" do NewsManager (protótipo Stitch
leitura_da_mat_ria_newsmanager), como tela inteira:

- barra de ações: voltar ao feed, estado da matéria, tempo de leitura,
  copiar referência, exportar HTML (para imprimir / salvar em PDF no
  navegador), editar e excluir;
- título centralizado, linha fina, faixa de autoria, fotografia de capa com
  legenda e crédito;
- coluna lateral "Nesta edição" (sumário clicável dos intertítulos) e
  "Registro de arquivo";
- corpo do texto formatado (capitular, intertítulos numerados com §,
  citações em destaque, listas, filetes, imagens, links e negrito/itálico);
- bloco do autor, palavras-chave e "Leituras suplementares da mesma editoria".

A regra de negócio fica em NoticiaService; a formatação, em texto_rico.py.
"""

import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox

from . import theme as t
from .midia import midia as midia_global
from .noticias import STATUS_NOTICIA, NoticiaService, interpretar_data, lista_etiquetas
from .tela_noticias import data_extenso_curta, hora_da_data
from .telas_cadastros import (
    COR_MATIZ,
    FUNDO_MATIZ,
    MARGEM,
    PAINEL,
    PAINEL_ALTO,
    PAINEL_BAIXO,
    RolagemVertical,
    _como_data,
    _etiqueta,
    _link,
    _resumir,
    data_relativa,
)
from .texto_rico import (
    blocos,
    contar_palavras,
    intertitulos,
    pagina_html,
    sem_marcadores,
    texto_simples,
    tempo_leitura_texto,
    tokens_inline,
)
from .cadastros import FUNCOES_AUTOR

LARGURA_TEXTO = 760            # largura máxima da coluna do artigo
COR_LINK = "#2F5D8C"


class LeituraFrame(tk.Frame):
    def __init__(self, parent, db, logger, ao_voltar=None, ao_editar=None, ao_abrir=None,
                 ao_buscar=None, ao_categoria=None, ao_alterar=None):
        super().__init__(parent, bg=t.BG)
        t.Fontes.preparar(self)
        self.db = db
        self.logger = logger
        self.midia = midia_global
        self.servico = NoticiaService(db, logger, midia_global)
        self.ao_voltar = ao_voltar
        self.ao_editar = ao_editar
        self.ao_abrir = ao_abrir
        self.ao_buscar = ao_buscar
        self.ao_categoria = ao_categoria
        self.ao_alterar = ao_alterar
        self.noticia = None
        self._marcas = []          # marcas do Text para o sumário
        self._tags_criadas = set()

        self.rolagem = RolagemVertical(self)
        self.rolagem.pack(fill="both", expand=True)
        self.pagina = self.rolagem.conteudo

    # =====================================================================
    # Carregamento
    # =====================================================================
    def carregar(self, noticia_id, contar_leitura=True):
        """Mostra a matéria. Só matérias publicadas somam uma leitura."""
        resultado = self.servico.obter(noticia_id)
        if not resultado.ok:
            messagebox.showwarning("Leitura", resultado.mensagem)
            if self.ao_voltar:
                self.ao_voltar()
            return False
        if contar_leitura and resultado.dados["status"] == "publicado":
            self.servico.registrar_leitura(noticia_id)
            resultado = self.servico.obter(noticia_id)   # já com a leitura contada
        self.noticia = resultado.dados
        self._desenhar()
        self.rolagem.canvas.yview_moveto(0)
        return True

    def recarregar(self):
        if self.noticia:
            self.carregar(self.noticia["id"], contar_leitura=False)

    # =====================================================================
    # Desenho da página
    # =====================================================================
    def _desenhar(self):
        for filho in self.pagina.winfo_children():
            filho.destroy()
        self._marcas = []
        n = self.noticia
        matiz = n["categoria_cor"] if n["categoria_cor"] in COR_MATIZ else "rubro"
        corpo_texto = n["conteudo"] or ""
        palavras = contar_palavras(texto_simples(corpo_texto))

        self._barra_acoes(n, palavras)
        self._cabecalho_materia(n, matiz)
        self._faixa_autoria(n)
        self._capa(n)

        miolo = tk.Frame(self.pagina, bg=t.BG)
        miolo.pack(fill="x", padx=MARGEM, pady=(20, 0))
        miolo.grid_columnconfigure(0, minsize=230)
        miolo.grid_columnconfigure(1, weight=1)
        self._coluna_lateral(miolo, n, corpo_texto)
        coluna = tk.Frame(miolo, bg=t.BG)
        coluna.grid(row=0, column=1, sticky="n", padx=(24, 0))
        self._artigo(coluna, corpo_texto)
        self._rodape_artigo(coluna, n)
        self._leituras_suplementares(n)
        tk.Frame(self.pagina, bg=t.BG, height=28).pack()

    # ---------- barra de ações ----------
    def _barra_acoes(self, n, palavras):
        barra = tk.Frame(self.pagina, bg=t.BG)
        barra.pack(fill="x", padx=MARGEM, pady=(14, 0))
        _link(barra, "← VOLTAR AO FEED DE NOTÍCIAS", self._voltar, t.TEXT).pack(side="left")
        estado = ("PUBLICADO EM EDIÇÃO DIGITAL" if n["status"] == "publicado"
                  else STATUS_NOTICIA.get(n["status"], "").upper())
        tk.Label(barra, text=estado, fg=t.PRIMARY if n["status"] == "publicado" else t.TEXT,
                 bg=FUNDO_MATIZ["rubro"] if n["status"] == "publicado" else PAINEL,
                 padx=8, pady=3, font=t.Fontes.corpo(8, "bold")).pack(side="left", padx=(14, 8))
        tk.Label(barra, text=f"⏱ {tempo_leitura_texto(palavras).upper()} DE LEITURA", fg=t.TEXT_MUTED,
                 bg=t.BG, font=t.Fontes.corpo(8, "bold")).pack(side="left")

        acoes = tk.Frame(barra, bg=t.BG)
        acoes.pack(side="right")
        _link(acoes, "COPIAR REFERÊNCIA", self._copiar_referencia, t.TEXT).pack(side="left", padx=8)
        _link(acoes, "EXPORTAR HTML / IMPRIMIR", self._exportar_html, t.TEXT).pack(side="left", padx=8)
        _link(acoes, "EDITAR MATÉRIA", self._editar, t.PRIMARY).pack(side="left", padx=8)
        _link(acoes, "EXCLUIR", self._excluir, t.ERROR).pack(side="left", padx=(8, 0))
        tk.Frame(self.pagina, bg=t.BORDER, height=1).pack(fill="x", padx=MARGEM, pady=(10, 0))

    # ---------- cabeçalho da matéria ----------
    def _cabecalho_materia(self, n, matiz):
        bloco = tk.Frame(self.pagina, bg=t.BG)
        bloco.pack(fill="x", padx=MARGEM, pady=(22, 0))
        etiquetas = lista_etiquetas(n["etiquetas"])
        eyebrow = n["categoria"].upper() + (f" • {etiquetas[0].upper()}" if etiquetas else "")
        tk.Label(bloco, text=eyebrow, fg=COR_MATIZ[matiz], bg=t.BG,
                 font=t.Fontes.corpo(9, "bold")).pack()
        tk.Label(bloco, text=n["titulo"], fg=t.TEXT, bg=t.BG, font=t.Fontes.display(32),
                 wraplength=900, justify="center").pack(pady=(8, 6))
        if n["subtitulo"]:
            tk.Label(bloco, text=n["subtitulo"], fg=t.TEXT_MUTED, bg=t.BG,
                     font=t.Fontes.display(14, "normal", True), wraplength=780,
                     justify="center").pack(pady=(0, 6))
        tk.Frame(self.pagina, bg=t.TEXT, height=2).pack(fill="x", padx=MARGEM + 120, pady=(8, 0))

    # ---------- autoria ----------
    def _faixa_autoria(self, n):
        faixa = tk.Frame(self.pagina, bg=PAINEL_BAIXO, highlightthickness=1,
                         highlightbackground=t.BORDER)
        faixa.pack(fill="x", padx=MARGEM + 120, pady=(0, 0))
        interno = tk.Frame(faixa, bg=PAINEL_BAIXO, padx=14, pady=10)
        interno.pack(fill="x")
        self._avatar(interno, n, 40).pack(side="left")
        textos = tk.Frame(interno, bg=PAINEL_BAIXO)
        textos.pack(side="left", padx=(10, 0))
        tk.Label(textos, text=f"Por {n['autor']}", fg=t.TEXT, bg=PAINEL_BAIXO,
                 font=t.Fontes.corpo(11, "bold")).pack(anchor="w")
        if n.get("autor_cargo"):
            tk.Label(textos, text=n["autor_cargo"], fg=t.TEXT_MUTED, bg=PAINEL_BAIXO,
                     font=t.Fontes.corpo(9)).pack(anchor="w")

        direita = tk.Frame(interno, bg=PAINEL_BAIXO)
        direita.pack(side="right")
        tk.Label(direita, text=f"{int(n['leituras'])} LEITURAS", fg=t.TEXT, bg=PAINEL_BAIXO,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="e")
        data = data_extenso_curta(n["data_publicacao"])
        hora = hora_da_data(n["data_publicacao"])
        tk.Label(direita, text=f"{data}{' • ' + hora if hora else ''}", fg=t.TEXT_MUTED,
                 bg=PAINEL_BAIXO, font=t.Fontes.corpo(8, "bold")).pack(anchor="e")

    def _avatar(self, pai, n, tamanho):
        """Foto do autor (ou a inicial num quadrado colorido)."""
        foto = self.midia.carregar_tk(n.get("autor_foto"), tamanho, tamanho)
        if foto is not None:
            rotulo = tk.Label(pai, image=foto, bd=0)
            rotulo.image = foto
            return rotulo
        return tk.Label(pai, text=(n["autor"][:1] or "?").upper(), fg="#FFFFFF", bg=t.PRIMARY,
                        width=2, font=t.Fontes.display(max(12, tamanho // 2)))

    # ---------- capa ----------
    def _capa(self, n):
        largura = self._largura_capa()
        foto = self.midia.carregar_tk(n.get("imagem"), largura, 340)
        if foto is None:
            return
        quadro = tk.Frame(self.pagina, bg=t.BG)
        quadro.pack(pady=(16, 0))
        rotulo = tk.Label(quadro, image=foto, bd=0)
        rotulo.image = foto
        rotulo.pack()
        legenda, credito = n.get("imagem_legenda") or "", n.get("imagem_credito") or ""
        if legenda or credito:
            texto = legenda + (f"   |   CRÉDITO: {credito.upper()}" if credito else "")
            tk.Label(quadro, text=texto.strip(" |"), fg=t.TEXT_MUTED, bg=PAINEL_BAIXO,
                     font=t.Fontes.corpo(8, "normal italic"), wraplength=largura - 20,
                     justify="left", anchor="w", padx=10, pady=6).pack(fill="x")

    def _largura_util(self):
        janela = self.winfo_toplevel().winfo_width()
        if not isinstance(janela, int) or janela < 400:
            janela = 1280
        return janela

    def _largura_capa(self):
        return max(520, min(1000, self._largura_util() - 2 * MARGEM - 240))

    # ---------- coluna lateral ----------
    def _coluna_lateral(self, miolo, n, conteudo):
        lateral = tk.Frame(miolo, bg=t.BG)
        lateral.grid(row=0, column=0, sticky="nw")

        sumario = tk.Frame(lateral, bg=PAINEL, padx=14, pady=12, width=230)
        sumario.pack(fill="x")
        tk.Label(sumario, text="NESTA EDIÇÃO", fg=t.TEXT, bg=PAINEL,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        titulos = intertitulos(conteudo)
        if not titulos:
            tk.Label(sumario, text="Esta matéria não tem intertítulos.", fg=t.TEXT_MUTED,
                     bg=PAINEL, font=t.Fontes.corpo(9), wraplength=200, justify="left").pack(
                anchor="w", pady=(6, 0))
        for indice, titulo in enumerate(titulos):
            item = _link(sumario, f"§ {indice + 1}. {titulo}", lambda i=indice: self._ir_para_secao(i), t.TEXT)
            item.configure(wraplength=200, justify="left", anchor="w")
            item.pack(anchor="w", pady=(6, 0))

        registro = tk.Frame(lateral, bg=PAINEL_ALTO, padx=14, pady=12, width=230)
        registro.pack(fill="x", pady=(14, 0))
        tk.Label(registro, text="REGISTRO DE ARQUIVO", fg=t.TEXT, bg=PAINEL_ALTO,
                 font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        data = interpretar_data(n["data_publicacao"])
        emissao = data.strftime("%d/%m/%Y às %H:%M") if data else "—"
        texto = (f"Protocolo #NW-{int(n['id']):04d}\nEstado: {STATUS_NOTICIA.get(n['status'], '')}\n"
                 f"Emissão: {emissao}\nEditoria: {n['categoria']}")
        tk.Label(registro, text=texto, fg=t.TEXT, bg=PAINEL_ALTO, font=t.Fontes.corpo(9),
                 justify="left", wraplength=200, anchor="w").pack(anchor="w", pady=(6, 0))

    def _ir_para_secao(self, indice):
        """Rola a página até o intertítulo clicado no sumário."""
        try:
            if indice >= len(self._marcas):
                return
            texto = self._texto
            y = texto.bbox(self._marcas[indice])[1] + texto.winfo_rooty() - self.rolagem.conteudo.winfo_rooty()
            total = max(1, self.rolagem.conteudo.winfo_height())
            self.rolagem.canvas.yview_moveto(max(0.0, (y - 24) / total))
        except (TypeError, tk.TclError):
            pass

    # ---------- corpo do artigo ----------
    def _artigo(self, pai, conteudo):
        self._texto = tk.Text(
            pai, wrap="word", relief="flat", bd=0, highlightthickness=0, bg=t.BG, fg=t.TEXT,
            font=t.Fontes.display(13, "normal"), width=86, height=10, padx=4, pady=4,
            cursor="arrow", spacing1=2, spacing3=8, takefocus=0)
        self._texto.pack(anchor="n")
        self._tags_criadas = set()
        self._configurar_tags()
        self._preencher_texto(conteudo)
        self._texto.configure(state="disabled")
        self._ajustar_altura()
        self._texto.bind("<Configure>", lambda e: self._ajustar_altura(False))

    def _configurar_tags(self):
        f = t.Fontes
        x = self._texto
        x.tag_configure("capitular", font=f.display(34, "bold"), foreground=t.PRIMARY)
        x.tag_configure("h2", font=f.display(20, "bold"), spacing1=16, spacing3=8, foreground=t.TEXT)
        x.tag_configure("h3", font=f.display(15, "bold"), spacing1=10, spacing3=4)
        x.tag_configure("citacao", font=f.display(15, "normal", True), background=PAINEL,
                        lmargin1=24, lmargin2=24, rmargin=24, spacing1=10, spacing3=10)
        x.tag_configure("autoria_citacao", font=f.corpo(8, "bold"), background=PAINEL,
                        lmargin1=24, lmargin2=24, foreground=t.TEXT_MUTED, spacing3=14)
        x.tag_configure("item", lmargin1=22, lmargin2=40, spacing3=4)
        x.tag_configure("legenda", font=f.corpo(8, "normal italic"), foreground=t.TEXT_MUTED,
                        justify="center", spacing3=12)
        x.tag_configure("centro", justify="center")

    def _tag_inline(self, base, estilos):
        """Tag combinada (ex.: parágrafo + negrito + itálico), criada sob demanda."""
        if not estilos:
            return base
        nome = f"{base}|{'+'.join(sorted(estilos))}"
        if nome not in self._tags_criadas:
            tamanho = {"citacao": 15, "h2": 20, "h3": 15}.get(base, 13)
            peso = "bold" if ("negrito" in estilos or base in ("h2", "h3")) else "normal"
            if "italico" in estilos or base == "citacao":
                peso += " italic"
            opcoes = {"font": t.Fontes.display(tamanho, peso.split()[0], "italic" in peso)}
            if "sublinhado" in estilos or "link" in estilos:
                opcoes["underline"] = True
            if "link" in estilos:
                opcoes["foreground"] = COR_LINK
            if base == "citacao":
                opcoes["background"] = PAINEL
            self._texto.tag_configure(nome, **opcoes)
            self._tags_criadas.add(nome)
        return nome

    def _inserir_inline(self, texto, base, tags_extra=()):
        for pedaco, estilos, url in tokens_inline(texto):
            tags = [self._tag_inline(base, estilos), *tags_extra]
            if url:
                nome_link = f"url::{url}"
                tags.append(nome_link)
                if nome_link not in self._tags_criadas:
                    self._texto.tag_bind(nome_link, "<Button-1>", lambda e, u=url: webbrowser.open(u))
                    self._texto.tag_bind(nome_link, "<Enter>", lambda e: self._texto.configure(cursor="hand2"))
                    self._texto.tag_bind(nome_link, "<Leave>", lambda e: self._texto.configure(cursor="arrow"))
                    self._tags_criadas.add(nome_link)
            self._texto.insert("end", pedaco, tuple(tags))

    def _preencher_texto(self, conteudo):
        x = self._texto
        lista = blocos(conteudo)
        if not lista:
            x.insert("end", "Esta matéria ainda não tem texto.", ("legenda",))
            return
        primeiro_paragrafo = True
        secao = 0
        for b in lista:
            if b.tipo == "h2":
                secao += 1
                marca = f"secao_{secao}"
                x.mark_set(marca, "end-1c")
                x.mark_gravity(marca, "left")
                self._marcas.append(marca)
                self._inserir_inline(f"§ {secao}. {b.texto}", "h2")
            elif b.tipo == "h3":
                self._inserir_inline(b.texto, "h3")
            elif b.tipo == "citacao":
                self._inserir_inline(f"“{b.texto}”", "citacao")
                if b.extra:
                    x.insert("end", "\n", ("citacao",))
                    x.insert("end", f"— {b.extra}".upper(), ("autoria_citacao",))
            elif b.tipo == "item":
                self._inserir_inline("•  " + b.texto, "paragrafo", ("item",))
            elif b.tipo == "item_num":
                self._inserir_inline(f"{b.extra}.  " + b.texto, "paragrafo", ("item",))
            elif b.tipo == "regra":
                filete = tk.Frame(x, bg=t.BORDER, height=1, width=520)
                x.window_create("end", window=filete)
            elif b.tipo == "imagem":
                self._inserir_imagem(b)
            else:
                if primeiro_paragrafo and b.texto[:1].isalpha():
                    x.insert("end", b.texto[0], ("capitular",))
                    resto = b.texto[1:]
                else:
                    resto = b.texto
                self._inserir_inline(resto, "paragrafo")
                primeiro_paragrafo = False
            x.insert("end", "\n")

    def _inserir_imagem(self, b):
        x = self._texto
        foto = self.midia.carregar_tk(b.extra, 640, 400, "caber")
        if foto is None:
            x.insert("end", f"[imagem indisponível: {b.texto or b.extra}]", ("legenda",))
            return
        rotulo = tk.Label(x, image=foto, bd=0, bg=t.BG)
        rotulo.image = foto
        x.insert("end", "\n", ("centro",))
        x.window_create("end", window=rotulo)
        if b.texto:
            x.insert("end", "\n" + b.texto, ("legenda",))

    def _ajustar_altura(self, atualizar=True):
        """O Text mostra o artigo inteiro (a rolagem é da página), então a altura
        acompanha o número de linhas depois de quebradas."""
        try:
            if atualizar:
                self.update_idletasks()
            linhas = self._texto.count("1.0", "end", "displaylines")
            if linhas:
                self._texto.configure(height=int(linhas[0]) + 1)
        except (TypeError, ValueError, IndexError, tk.TclError):
            pass

    # ---------- rodapé do artigo ----------
    def _rodape_artigo(self, pai, n):
        etiquetas = lista_etiquetas(n["etiquetas"])
        if etiquetas:
            linha = tk.Frame(pai, bg=t.BG)
            linha.pack(fill="x", pady=(20, 0))
            tk.Label(linha, text="PALAVRAS-CHAVE:", fg=t.TEXT_MUTED, bg=t.BG,
                     font=t.Fontes.corpo(8, "bold")).pack(side="left", padx=(0, 6))
            for etiqueta in etiquetas:
                chip = tk.Label(linha, text=etiqueta.upper(), fg=t.TEXT, bg=PAINEL, padx=8, pady=3,
                                font=t.Fontes.corpo(8, "bold"), cursor="hand2")
                chip.pack(side="left", padx=(0, 4))
                chip.bind("<Button-1>", lambda e, tag=etiqueta: self._buscar(tag))

        caixa = tk.Frame(pai, bg=PAINEL_BAIXO, highlightthickness=1, highlightbackground=t.BORDER)
        caixa.pack(fill="x", pady=(20, 0))
        interno = tk.Frame(caixa, bg=PAINEL_BAIXO, padx=16, pady=14)
        interno.pack(fill="x")
        self._avatar(interno, n, 56).pack(side="left", anchor="n")
        dados = tk.Frame(interno, bg=PAINEL_BAIXO)
        dados.pack(side="left", padx=(12, 0), fill="x", expand=True)
        topo = tk.Frame(dados, bg=PAINEL_BAIXO)
        topo.pack(fill="x")
        tk.Label(topo, text=n["autor"], fg=t.TEXT, bg=PAINEL_BAIXO,
                 font=t.Fontes.display(15)).pack(side="left")
        if n.get("autor_cargo"):
            tk.Label(topo, text=n["autor_cargo"].upper(), fg=t.PRIMARY, bg=FUNDO_MATIZ["rubro"],
                     padx=6, pady=1, font=t.Fontes.corpo(7, "bold")).pack(side="left", padx=8)
        autor = self.db.buscar_autor_por_id(n["autor_id"])
        bio = (autor or {}).get("bio") or ""
        if bio:
            tk.Label(dados, text=_resumir(bio, 260), fg=t.TEXT, bg=PAINEL_BAIXO,
                     font=t.Fontes.corpo(9), wraplength=520, justify="left", anchor="w").pack(
                anchor="w", pady=(4, 0))
        links = tk.Frame(dados, bg=PAINEL_BAIXO)
        links.pack(anchor="w", pady=(8, 0))
        _link(links, "TODAS AS MATÉRIAS DESTE REPÓRTER →",
              lambda nome=n["autor"]: self._buscar(nome), t.PRIMARY).pack(side="left")
        _link(links, "CONTATO VIA DESPACHO", lambda a=autor: self._contato(a), t.TEXT).pack(
            side="left", padx=(16, 0))

        t.botao_primario(pai, "Modificar esta publicação", self._editar).pack(anchor="e", pady=(16, 0))

    # ---------- leituras suplementares ----------
    def _leituras_suplementares(self, n):
        resultado = self.servico.relacionadas(n["id"], 3)
        itens = resultado.dados if resultado.ok else []
        tk.Frame(self.pagina, bg=t.TEXT, height=2).pack(fill="x", padx=MARGEM, pady=(28, 0))
        cab = tk.Frame(self.pagina, bg=t.BG)
        cab.pack(fill="x", padx=MARGEM, pady=(8, 0))
        tk.Label(cab, text="LEITURAS SUPLEMENTARES DA MESMA EDITORIA", fg=t.TEXT, bg=t.BG,
                 font=t.Fontes.corpo(9, "bold")).pack(side="left")
        _link(cab, "VER TODO O ACERVO →", lambda cid=n["categoria_id"]: self._acervo(cid),
              t.PRIMARY).pack(side="right")

        grade = tk.Frame(self.pagina, bg=t.BG)
        grade.pack(fill="x", padx=MARGEM - 8, pady=(10, 0))
        for coluna in range(3):
            grade.grid_columnconfigure(coluna, weight=1, uniform="suplementar")
        if not itens:
            tk.Label(grade, text="Ainda não há outras matérias publicadas nesta editoria.",
                     fg=t.TEXT_MUTED, bg=t.BG, font=t.Fontes.corpo(10), pady=16).grid(
                row=0, column=0, columnspan=3)
            return
        for coluna, outro in enumerate(itens):
            cartao = tk.Frame(grade, bg=t.SURFACE, highlightthickness=1,
                              highlightbackground=t.BORDER, cursor="hand2", padx=14, pady=12)
            cartao.grid(row=0, column=coluna, sticky="nsew", padx=8, pady=8)
            matiz = outro["categoria_cor"] if outro["categoria_cor"] in COR_MATIZ else "rubro"
            partes = [
                tk.Label(cartao, text=outro["categoria"].upper(), fg=COR_MATIZ[matiz], bg=t.SURFACE,
                         font=t.Fontes.corpo(8, "bold"), anchor="w"),
                tk.Label(cartao, text=outro["titulo"], fg=t.TEXT, bg=t.SURFACE,
                         font=t.Fontes.display(13), wraplength=300, justify="left", anchor="w"),
                tk.Label(cartao, text=_resumir(outro["subtitulo"] or texto_simples(outro["resumo"]), 110),
                         fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(9), wraplength=300,
                         justify="left", anchor="w"),
                tk.Label(cartao, text=f"POR {outro['autor'].upper()}  •  {data_relativa(outro['data_publicacao']).upper()}",
                         fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(7, "bold"), anchor="w"),
            ]
            for indice, rotulo in enumerate(partes):
                rotulo.pack(anchor="w", pady=(0 if indice == 0 else 5, 0))
            for widget in (cartao, *partes):
                widget.bind("<Button-1>", lambda e, i=outro["id"]: self._abrir(i))

    # =====================================================================
    # Ações
    # =====================================================================
    def _voltar(self):
        if self.ao_voltar:
            self.ao_voltar()

    def _editar(self):
        if self.ao_editar and self.noticia:
            self.ao_editar(self.noticia["id"])

    def _abrir(self, noticia_id):
        if self.ao_abrir:
            self.ao_abrir(noticia_id)

    def _buscar(self, termo):
        if self.ao_buscar:
            self.ao_buscar(termo)

    def _acervo(self, categoria_id):
        if self.ao_categoria:
            self.ao_categoria(categoria_id)

    def _excluir(self):
        n = self.noticia
        if not n:
            return
        if not messagebox.askyesno(
                "Excluir matéria",
                f"Excluir a matéria \"{n['titulo']}\"?\nEssa ação não pode ser desfeita."):
            return
        resultado = self.servico.excluir(n["id"])
        if not resultado.ok:
            messagebox.showwarning("Leitura", resultado.mensagem)
            return
        self.noticia = None
        if self.ao_alterar:
            self.ao_alterar()
        self._voltar()

    def _referencia(self) -> str:
        n = self.noticia
        return f"#NW-{int(n['id']):04d} — {n['titulo']} ({n['categoria']}, por {n['autor']})"

    def _copiar_referencia(self):
        if not self.noticia:
            return
        self.clipboard_clear()
        self.clipboard_append(self._referencia())
        messagebox.showinfo("Leitura", "Referência da matéria copiada para a área de transferência.")

    def _contato(self, autor):
        email = (autor or {}).get("email")
        if not email:
            messagebox.showinfo("Contato", "Este jornalista não tem e-mail cadastrado.")
            return
        self.clipboard_clear()
        self.clipboard_append(email)
        messagebox.showinfo("Contato", f"E-mail copiado: {email}")

    def _ler_imagem(self, relativo):
        alvo = self.midia.caminho_absoluto(relativo)
        if alvo and alvo.is_file():
            try:
                return alvo.read_bytes()
            except OSError:
                return None
        return None

    def html_da_materia(self) -> str:
        """HTML completo da matéria aberta (usado pela exportação)."""
        n = self.noticia
        data = interpretar_data(n["data_publicacao"])
        quando = data.strftime("%d/%m/%Y %H:%M") if data else ""
        meta = f"{n['categoria']} • Por {n['autor']} • {quando}"
        return pagina_html(n["titulo"], n["subtitulo"] or "", meta, n["conteudo"] or "",
                           self._ler_imagem, n.get("imagem"), n.get("imagem_legenda") or "",
                           n.get("imagem_credito") or "")

    def _exportar_html(self):
        if not self.noticia:
            return
        caminho = filedialog.asksaveasfilename(
            title="Exportar matéria", defaultextension=".html",
            initialfile=f"materia_{int(self.noticia['id']):04d}.html",
            filetypes=[("Página HTML", "*.html")])
        if not caminho:
            return
        try:
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write(self.html_da_materia())
            self.logger.info(f"Matéria {self.noticia['id']} exportada para {caminho}")
            messagebox.showinfo(
                "Exportar", "Arquivo salvo. Abra-o no navegador e use Imprimir para gerar o PDF.")
        except OSError as erro:
            self.logger.error("Erro ao exportar matéria", erro)
            messagebox.showerror("Exportar", "Não foi possível salvar o arquivo.")
