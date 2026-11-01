"""
tela_clipping.py
Tela "Clipping" (estilo editorial): traz as notícias do dia de jornais escolhidos
a partir dos feeds RSS/Atom oficiais, mostra uma prévia e importa como pautas.

Abas: Nova busca (filtros + prévia + importar) • Importações salvas • Histórico •
Fontes (ativar/desativar, feed próprio, testar fontes).

Camadas: a tela só chama ClippingService (banco) e `coletar_feeds`/`validar_feed`
(rede). A rede roda SEMPRE em thread (app/segundo_plano.py) e o resultado volta à
tela pela fila + after(); o banco só é usado na thread principal.
"""

import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import messagebox, simpledialog

from . import rede
from . import theme as t
from .cadastros import CategoriaService, Resultado
from .clipping import (AVISO_TERCEIROS, ORDENS, PERIODOS, STATUS_DESTINO, ClippingService, FiltroClipping,
                       coletar_feeds, sugerir_categoria, validar_feed)
from .notificacoes import registrar_evento
from .segundo_plano import executar_async
from .telas_cadastros import (MARGEM, PAINEL, PAINEL_ALTO, PAINEL_BAIXO, CampoSelecao, _cabecalho, _etiqueta,
                              _filete, _link, _resumir, _TelaBase, desenhar_paginacao)

POR_PAGINA = 12
ABAS = (("busca", "NOVA BUSCA"), ("salvas", "IMPORTAÇÕES SALVAS"), ("historico", "HISTÓRICO"), ("fontes", "FONTES"))
ROTULO_ORIGEM = {"manual": "Manual", "salva": "Importação salva", "auto": "Automática"}
ROTULO_VERIFICACAO = {"indireta": "endereço encontrado em diretório de terceiros",
                      "nao_verificada": "NÃO verificada", "proprio": "feed próprio"}


def _fmt_data(d):
    return f"{d:%d/%m %H:%M}" if isinstance(d, datetime) else "sem data"


class ClippingFrame(_TelaBase):
    def __init__(self, parent, db, logger, usuario, ao_alterar=None):
        super().__init__(parent, db, logger, ao_alterar)
        self.usuario_id = usuario.get("id")
        self.servico = ClippingService(db, logger)
        self.categorias = CategoriaService(db, logger)
        self.ao_alterar = ao_alterar
        self._previa, self._falhas = [], []
        self._selecionados = set()
        self._pagina = 1
        self._editando_id = None
        self._ocupado = False
        self._fila_auto = []
        self._resumo_auto = {"importacoes": 0, "materias": 0, "falhas": 0}
        self._var_fonte, self._var_feed = {}, {}
        self._cats = []
        self._montar()

    # =========================================================================
    # Montagem
    # =========================================================================
    def _montar(self):
        p = self.pagina
        linha = _cabecalho(p, "Mesa de apuração externa • Clipping", "Caderno de Clipping & Fontes Externas",
                           "Traga as notícias do dia dos jornais que você escolher, confira a prévia e importe como pauta.")
        self.rotulo_estado = tk.Label(linha, text="", fg=t.TEXT_MUTED, bg=t.BG, font=t.Fontes.corpo(8, "bold"))
        self.rotulo_estado.pack(side="right", anchor="s")
        _filete(p)
        aviso = tk.Frame(p, bg=PAINEL, highlightthickness=1, highlightbackground=t.BORDER)
        aviso.pack(fill="x", padx=MARGEM, pady=(12, 0))
        tk.Label(aviso, text="▲  " + AVISO_TERCEIROS + " Importamos só título, resumo do feed, data, link e fonte; "
                             "imagens não são baixadas.", fg=t.TEXT, bg=PAINEL, anchor="w", justify="left", wraplength=980,
                 padx=12, pady=8, font=t.Fontes.corpo(9, "bold")).pack(fill="x")
        barra = tk.Frame(p, bg=t.BG)
        barra.pack(fill="x", padx=MARGEM, pady=(14, 0))
        self._rotulos_abas = {}
        for chave, rotulo in ABAS:
            r = tk.Label(barra, text=rotulo, cursor="hand2", padx=14, pady=7, font=t.Fontes.corpo(9, "bold"))
            r.pack(side="left", padx=(0, 4))
            r.bind("<Button-1>", lambda e, c=chave: self._mostrar_aba(c))
            self._rotulos_abas[chave] = r
        self.area_abas = tk.Frame(p, bg=t.BG)
        self.area_abas.pack(fill="x", padx=MARGEM, pady=(0, 0))
        self._abas = {c: tk.Frame(self.area_abas, bg=t.BG) for c, _ in ABAS}
        self._montar_busca(self._abas["busca"])
        self._montar_salvas(self._abas["salvas"])
        self._montar_historico(self._abas["historico"])
        self._montar_fontes(self._abas["fontes"])
        tk.Frame(p, bg=t.BG, height=30).pack()
        self._aba_atual = None
        self._mostrar_aba("busca")

    def _cartao(self, pai, titulo, rotulo=None):
        cartao = tk.Frame(pai, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=16, pady=14)
        interno.pack(fill="both", expand=True)
        if rotulo:
            tk.Label(interno, text=rotulo.upper(), fg=t.PRIMARY, bg=t.SURFACE, anchor="w",
                     font=t.Fontes.corpo(8, "bold")).pack(fill="x")
        tk.Label(interno, text=titulo, fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.display(16)).pack(fill="x", pady=(0, 8))
        return cartao, interno

    def _mostrar_aba(self, chave):
        if self._aba_atual:
            self._abas[self._aba_atual].pack_forget()
        self._aba_atual = chave
        self._abas[chave].pack(fill="x", pady=(0, 0))
        for c, r in self._rotulos_abas.items():
            r.configure(fg="#FFFFFF" if c == chave else t.TEXT, bg=t.TEXT if c == chave else PAINEL)
        if chave == "salvas":
            self._desenhar_salvas()
        elif chave == "historico":
            self._desenhar_historico()
        elif chave == "fontes":
            self._desenhar_fontes()

    def mostrar(self):
        """Chamada pela janela ao abrir a tela."""
        self.servico.purgar_antigos()
        self._montar_fontes_filtro()
        self._recarregar_editorias()
        self._mostrar_aba(self._aba_atual or "busca")

    def recarregar(self):
        self.mostrar()

    # ---------- aba: nova busca ----------
    def _montar_busca(self, aba):
        aba.grid_columnconfigure(0, weight=0)
        aba.grid_columnconfigure(1, weight=1)
        cartao, f = self._cartao(aba, "O que importar", "Filtros")
        cartao.grid(row=0, column=0, sticky="nw", padx=(0, 14), pady=(14, 0))
        tk.Label(f, text="JORNAIS E SEÇÕES", fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.corpo(8, "bold")).pack(fill="x")
        self.caixa_fontes = tk.Frame(f, bg=t.SURFACE, width=300)
        self.caixa_fontes.pack(fill="x", pady=(4, 10))
        self.campo_incluir = t.CampoEditorial(f, "Palavras que devem aparecer", dica="basta uma • econom* = curinga")
        self.campo_incluir.pack(fill="x", pady=(0, 8))
        self.campo_excluir = t.CampoEditorial(f, "Palavras que NÃO devem aparecer")
        self.campo_excluir.pack(fill="x", pady=(0, 8))
        self.campo_periodo = CampoSelecao(f, "Período", {k: v[0] for k, v in PERIODOS.items()})
        self.campo_periodo.pack(fill="x", pady=(0, 8))
        self.campo_periodo.set("24h")
        self.campo_limite = t.CampoEditorial(f, "Máximo por jornal")
        self.campo_limite.pack(fill="x", pady=(0, 8))
        self.campo_limite.set("10")
        self.campo_ordem = CampoSelecao(f, "Ordem", ORDENS)
        self.campo_ordem.pack(fill="x", pady=(0, 8))
        self.var_imagem, self.var_ocultar, self.var_auto = tk.BooleanVar(value=False), tk.BooleanVar(value=True), tk.BooleanVar(value=False)
        for var, texto in ((self.var_imagem, "Somente itens com imagem"), (self.var_ocultar, "Ocultar já importados"),
                           (self.var_auto, "Importar automaticamente 1 vez por dia ao abrir (vale ao salvar)")):
            tk.Checkbutton(f, text=texto, variable=var, bg=t.SURFACE, fg=t.TEXT, activebackground=t.SURFACE,
                           anchor="w", wraplength=290, justify="left", selectcolor=t.SURFACE,
                           font=t.Fontes.corpo(9)).pack(fill="x")
        self.rotulo_edicao = tk.Label(f, text="", fg=t.PRIMARY, bg=t.SURFACE, anchor="w", wraplength=290,
                                      justify="left", font=t.Fontes.corpo(8, "bold"))
        self.rotulo_edicao.pack(fill="x", pady=(8, 0))
        self.botao_buscar = t.botao_primario(f, "Buscar agora", self._buscar)
        self.botao_buscar.pack(fill="x", pady=(8, 0))
        t.botao_secundario(f, "SALVAR FILTROS…", self._salvar_filtros).pack(fill="x", pady=(6, 0))
        t.botao_secundario(f, "LIMPAR FILTROS", self._limpar_filtros).pack(fill="x", pady=(6, 0))

        direita = tk.Frame(aba, bg=t.BG)
        direita.grid(row=0, column=1, sticky="nsew", pady=(14, 0))
        cab = tk.Frame(direita, bg=t.BG)
        cab.pack(fill="x")
        self.rotulo_contagem = tk.Label(cab, text="Nenhuma busca feita ainda.", fg=t.TEXT, bg=t.BG, anchor="w",
                                        font=t.Fontes.display(14))
        self.rotulo_contagem.pack(side="left")
        self.var_todos = tk.BooleanVar(value=False)
        tk.Checkbutton(cab, text="Selecionar todos", variable=self.var_todos, command=self._alternar_todos, bg=t.BG,
                       fg=t.TEXT, activebackground=t.BG, selectcolor=t.SURFACE,
                       font=t.Fontes.corpo(9, "bold")).pack(side="right")
        self.caixa_falhas = tk.Frame(direita, bg=t.BG)
        self.caixa_falhas.pack(fill="x", pady=(8, 0))
        self.caixa_itens = tk.Frame(direita, bg=t.BG)
        self.caixa_itens.pack(fill="x", pady=(8, 0))
        self.caixa_paginacao = tk.Frame(direita, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        self.caixa_importar = tk.Frame(direita, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        self.caixa_importar.pack(fill="x", pady=(10, 0))
        interno = tk.Frame(self.caixa_importar, bg=t.SURFACE, padx=14, pady=12)
        interno.pack(fill="x")
        interno.grid_columnconfigure(0, weight=1)
        interno.grid_columnconfigure(1, weight=1)
        self.campo_editoria = CampoSelecao(interno, "Editoria", {"auto": "Automática (pela seção e palavras)"})
        self.campo_editoria.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.campo_status = CampoSelecao(interno, "Estado das matérias", STATUS_DESTINO)
        self.campo_status.grid(row=0, column=1, sticky="ew")
        self.campo_status.set("em_pauta")
        tk.Label(interno, text="Autor: “Clipping — <jornal>” (criado se não existir). Nada é publicado automaticamente.",
                 fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", font=t.Fontes.corpo(8)).grid(row=1, column=0, columnspan=2,
                                                                                     sticky="w", pady=(6, 0))
        self.botao_importar = t.botao_primario(interno, "Importar selecionadas", self._importar_selecionadas)
        self.botao_importar.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))

    def _montar_fontes_filtro(self):
        """Marcadores de jornais/seções do filtro, a partir das fontes ativas do usuário."""
        marcados_f = {k: v.get() for k, v in self._var_fonte.items()}
        marcados_s = {k: v.get() for k, v in self._var_feed.items()}
        for filho in self.caixa_fontes.winfo_children():
            filho.destroy()
        self._var_fonte, self._var_feed = {}, {}
        ativas = [f for f in self.servico.fontes(self.usuario_id) if f["ativo"] and f["feeds"]]
        if not ativas:
            tk.Label(self.caixa_fontes, text="Nenhum jornal ativo. Ative fontes na aba FONTES.", fg=t.ERROR,
                     bg=t.SURFACE, anchor="w", wraplength=290, font=t.Fontes.corpo(9)).pack(fill="x")
        for f in ativas:
            var = tk.BooleanVar(value=marcados_f.get(f["chave"], True))
            self._var_fonte[f["chave"]] = var
            tk.Checkbutton(self.caixa_fontes, text=f["nome"], variable=var, bg=t.SURFACE, fg=t.TEXT, anchor="w",
                           activebackground=t.SURFACE, selectcolor=t.SURFACE,
                           font=t.Fontes.corpo(10, "bold")).pack(fill="x")
            if len(f["feeds"]) > 1 or f["feeds"][0]["secao"] not in ("Geral", "Últimas notícias"):
                for feed in f["feeds"]:
                    v = tk.BooleanVar(value=marcados_s.get(feed["chave_feed"], True))
                    self._var_feed[feed["chave_feed"]] = v
                    texto = feed["secao"] + ("  (não verificada)" if feed.get("verificacao") == "nao_verificada" else "")
                    tk.Checkbutton(self.caixa_fontes, text=texto, variable=v, bg=t.SURFACE, fg=t.TEXT_MUTED,
                                   anchor="w", activebackground=t.SURFACE, selectcolor=t.SURFACE,
                                   font=t.Fontes.corpo(9)).pack(fill="x", padx=(22, 0))
            else:
                self._var_feed[f["feeds"][0]["chave_feed"]] = tk.BooleanVar(value=True)

    def _recarregar_editorias(self):
        r = self.categorias.listar()
        self._cats = r.dados if r.ok else []
        opcoes = {"auto": "Automática (pela seção e palavras)"}
        if r.ok:
            opcoes.update({str(c["id"]): c["nome"] for c in r.dados})
        self.campo_editoria.definir_opcoes(opcoes)

    # ---------- filtros <-> formulário ----------
    def _filtro_atual(self) -> FiltroClipping:
        fontes = [k for k, v in self._var_fonte.items() if v.get()]
        feeds = [k for k, v in self._var_feed.items() if v.get() and k.split(":")[0] in fontes]
        todas = [k for k in self._var_feed if k.split(":")[0] in fontes]
        try:
            limite = max(1, min(100, int(self.campo_limite.get() or 10)))
        except ValueError:
            limite = 10
        editoria = self.campo_editoria.get()
        return FiltroClipping(
            fontes=fontes, feeds=[] if len(feeds) == len(todas) else feeds, incluir=self.campo_incluir.get(),
            excluir=self.campo_excluir.get(), periodo_horas=PERIODOS[self.campo_periodo.get() or "24h"][1],
            limite_por_fonte=limite, so_com_imagem=bool(self.var_imagem.get()),
            ocultar_importados=bool(self.var_ocultar.get()), ordem=self.campo_ordem.get() or "recentes",
            categoria_id=int(editoria) if editoria and editoria != "auto" else None,
            status_destino=self.campo_status.get() or "em_pauta")

    def _aplicar_filtro(self, f: FiltroClipping):
        for k, v in self._var_fonte.items():
            v.set(k in f.fontes)
        for k, v in self._var_feed.items():
            v.set(not f.feeds or k in f.feeds)
        self.campo_incluir.set(", ".join(f.incluir))
        self.campo_excluir.set(", ".join(f.excluir))
        chave = next((k for k, (_, h) in PERIODOS.items() if h == f.periodo_horas), "24h")
        self.campo_periodo.set(chave)
        self.campo_limite.set(str(f.limite_por_fonte))
        self.campo_ordem.set(f.ordem)
        self.var_imagem.set(f.so_com_imagem)
        self.var_ocultar.set(f.ocultar_importados)
        self.campo_editoria.set(str(f.categoria_id) if f.categoria_id else "auto")
        self.campo_status.set(f.status_destino)

    def _limpar_filtros(self):
        self._editando_id = None
        self.rotulo_edicao.configure(text="")
        self.var_auto.set(False)
        for v in list(self._var_fonte.values()) + list(self._var_feed.values()):
            v.set(True)
        self._aplicar_filtro(FiltroClipping(fontes=list(self._var_fonte)))

    # ---------- buscar ----------
    def _definir_ocupado(self, ocupado, texto=""):
        self._ocupado = ocupado
        self.rotulo_estado.configure(text=texto)
        estado = "disabled" if ocupado else "normal"
        for b in (self.botao_buscar, self.botao_importar):
            b.configure(state=estado)

    def _buscar(self):
        if self._ocupado:
            return
        filtro = self._filtro_atual()
        feeds, estados = self.servico.preparar_coleta(self.usuario_id, filtro)
        if not feeds:
            messagebox.showinfo("Clipping", "Escolha pelo menos um jornal ativo para buscar.", parent=self)
            return
        self._filtro_da_busca = filtro
        self._definir_ocupado(True, f"BUSCANDO EM {len(feeds)} FEED(S)…")
        executar_async(self, lambda: coletar_feeds(feeds, estados, rede.buscar),
                       lambda ok, valor: self._buscou(filtro, ok, valor))

    def _buscou(self, filtro, ok, valor):
        self._definir_ocupado(False)
        if not ok:
            messagebox.showwarning("Clipping", f"A busca falhou: {valor}", parent=self)
            return
        r = self.servico.concluir_coleta(self.usuario_id, filtro, valor)
        if not r.ok:
            messagebox.showwarning("Clipping", r.mensagem, parent=self)
            return
        self._previa, self._falhas = r.dados["itens"], r.dados["falhas"]
        self._selecionados, self._pagina = set(), 1
        self.var_todos.set(False)
        self._desenhar_previa()
        self.rotulo_estado.configure(text=f"BUSCA ÀS {datetime.now():%H:%M}")

    # ---------- prévia ----------
    def _desenhar_previa(self):
        total = len(self._previa)
        self.rotulo_contagem.configure(
            text=f"{total} matéria(s) na prévia" if total else "Nenhuma matéria atende aos filtros.")
        for filho in self.caixa_falhas.winfo_children():
            filho.destroy()
        if self._falhas:
            tk.Label(self.caixa_falhas, text="FONTES COM PROBLEMA (as demais funcionaram)", fg=t.ERROR, bg=t.BG,
                     anchor="w", font=t.Fontes.corpo(8, "bold")).pack(fill="x")
            for f in self._falhas:
                tk.Label(self.caixa_falhas, text=f"• {f['fonte']} — {f['secao']}: {f['motivo']}", fg=t.ERROR,
                         bg=t.BG, anchor="w", justify="left", wraplength=640,
                         font=t.Fontes.corpo(9)).pack(fill="x")
        for filho in self.caixa_itens.winfo_children():
            filho.destroy()
        paginas = max(1, -(-total // POR_PAGINA))
        self._pagina = min(self._pagina, paginas)
        inicio = (self._pagina - 1) * POR_PAGINA
        for item in self._previa[inicio:inicio + POR_PAGINA]:
            self._linha_item(item)
        if total > POR_PAGINA:
            self.caixa_paginacao.pack(fill="x", pady=(8, 0), before=self.caixa_importar)
            fim = min(total, inicio + POR_PAGINA)
            desenhar_paginacao(self.caixa_paginacao, f"EXIBINDO {inicio + 1}–{fim} DE {total}", self._pagina, paginas,
                               self._ir_para)
        else:
            self.caixa_paginacao.pack_forget()
        self._atualizar_botao_importar()

    def _ir_para(self, pagina):
        self._pagina = pagina
        self._desenhar_previa()

    def _linha_item(self, item):
        ja = item.get("ja_importado")
        cartao = tk.Frame(self.caixa_itens, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        cartao.pack(fill="x", pady=(0, 6))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=12, pady=10)
        interno.pack(fill="x")
        topo = tk.Frame(interno, bg=t.SURFACE)
        topo.pack(fill="x")
        var = tk.BooleanVar(value=item["id"] in self._selecionados)
        tk.Checkbutton(topo, variable=var, bg=t.SURFACE, activebackground=t.SURFACE, selectcolor=t.SURFACE,
                       state="disabled" if ja else "normal",
                       command=lambda i=item["id"], v=var: self._marcar(i, v.get())).pack(side="left")
        meta = f"{item['fonte_nome']}  •  {item.get('secao') or 'Geral'}  •  {_fmt_data(item.get('publicado_em'))}"
        tk.Label(topo, text=meta.upper(), fg=t.PRIMARY, bg=t.SURFACE, font=t.Fontes.corpo(8, "bold")).pack(side="left")
        if ja:
            _etiqueta(topo, "Já importado", t.SUCCESS, t.SURFACE).pack(side="right")
        tk.Label(interno, text=item["titulo"], fg=t.TEXT, bg=t.SURFACE, anchor="w", justify="left", wraplength=620,
                 font=t.Fontes.display(14)).pack(fill="x", padx=(26, 0), pady=(4, 2))
        if item.get("resumo"):
            tk.Label(interno, text=_resumir(item["resumo"], 260), fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w",
                     justify="left", wraplength=620, font=t.Fontes.corpo(9)).pack(fill="x", padx=(26, 0))
        rodape = tk.Frame(interno, bg=t.SURFACE)
        rodape.pack(fill="x", padx=(26, 0), pady=(6, 0))
        _link(rodape, "ABRIR NA FONTE ↗", lambda u=item["url"]: self._abrir_link(u)).pack(side="left")
        if item.get("imagem_url"):
            tk.Label(rodape, text="• tem imagem (não será baixada)", fg=t.TEXT_MUTED, bg=t.SURFACE,
                     font=t.Fontes.corpo(8)).pack(side="left", padx=10)
        sugestao = self._nome_editoria_sugerida(item)
        if sugestao:
            tk.Label(rodape, text=f"Editoria sugerida: {sugestao}", fg=t.TEXT_MUTED, bg=t.SURFACE,
                     font=t.Fontes.corpo(8)).pack(side="right")

    def _nome_editoria_sugerida(self, item):
        cats = self._cats
        cid = sugerir_categoria(item["titulo"], item.get("resumo"), item.get("secao") or "",
                                item.get("categoria_sugerida"), cats)
        return next((c["nome"] for c in cats if c["id"] == cid), "")

    def _abrir_link(self, url):
        if url.lower().startswith(("http://", "https://")):   # nunca abre outro esquema
            webbrowser.open(url)

    def _marcar(self, item_id, marcado):
        (self._selecionados.add if marcado else self._selecionados.discard)(item_id)
        self._atualizar_botao_importar()

    def _alternar_todos(self):
        if self.var_todos.get():
            self._selecionados = {i["id"] for i in self._previa if not i.get("ja_importado")}
        else:
            self._selecionados = set()
        self._desenhar_previa()

    def _atualizar_botao_importar(self):
        self.botao_importar.configure(text=f"IMPORTAR SELECIONADAS ({len(self._selecionados)})")

    # ---------- importar ----------
    def _importar_selecionadas(self):
        if self._ocupado:
            return
        itens = [i for i in self._previa if i["id"] in self._selecionados]
        if not itens:
            messagebox.showinfo("Clipping", "Marque ao menos uma matéria da prévia.", parent=self)
            return
        filtro = self._filtro_atual()
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            r = self.servico.importar(self.usuario_id, itens, filtro.categoria_id, filtro.status_destino,
                                      falhas_fontes=len(self._falhas), fontes_texto=", ".join(filtro.fontes))
        finally:
            self.configure(cursor="")
        (messagebox.showinfo if r.ok else messagebox.showwarning)("Clipping", r.mensagem + (
            "\n\n" + "\n".join(r.dados["erros"][:5]) if r.ok and r.dados["erros"] else ""), parent=self)
        if r.ok:
            self._depois_de_importar(filtro)

    def _depois_de_importar(self, filtro):
        novo = self.servico.previa(self.usuario_id, getattr(self, "_filtro_da_busca", filtro))
        if novo.ok:
            self._previa = novo.dados["itens"]
        self._selecionados = set()
        self.var_todos.set(False)
        self._desenhar_previa()
        if self.ao_alterar:
            self.ao_alterar()

    # ---------- salvar filtros ----------
    def _salvar_filtros(self):
        filtro = self._filtro_atual()
        if not filtro.fontes:
            messagebox.showinfo("Clipping", "Escolha pelo menos um jornal antes de salvar.", parent=self)
            return
        atual = None
        if self._editando_id:
            atual = next((i for i in (self.servico.listar_importacoes(self.usuario_id).dados or [])
                          if i["id"] == self._editando_id), None)
        nome = simpledialog.askstring("Salvar importação", "Nome da importação (ex.: Política do dia – G1 + Folha):",
                                      initialvalue=atual["nome"] if atual else "", parent=self)
        if nome is None:
            return
        r = self.servico.salvar_importacao(self.usuario_id, nome, filtro, bool(self.var_auto.get()),
                                           self._editando_id)
        (messagebox.showinfo if r.ok else messagebox.showwarning)("Clipping", r.mensagem, parent=self)
        if r.ok:
            self._editando_id = None
            self.rotulo_edicao.configure(text="")
            self._mostrar_aba("salvas")

    # ---------- aba: importações salvas ----------
    def _montar_salvas(self, aba):
        self.caixa_salvas = tk.Frame(aba, bg=t.BG)
        self.caixa_salvas.pack(fill="x", pady=(14, 0))
        self.rotulo_resultado_salva = tk.Label(aba, text="", fg=t.TEXT, bg=t.BG, anchor="w", justify="left",
                                               wraplength=980, font=t.Fontes.corpo(10, "bold"))
        self.rotulo_resultado_salva.pack(fill="x", pady=(8, 0))

    def _desenhar_salvas(self):
        for filho in self.caixa_salvas.winfo_children():
            filho.destroy()
        r = self.servico.listar_importacoes(self.usuario_id)
        if not r.ok or not r.dados:
            tk.Label(self.caixa_salvas, text=r.mensagem if not r.ok else
                     "Nenhuma importação salva. Monte os filtros em NOVA BUSCA e use SALVAR FILTROS.",
                     fg=t.TEXT_MUTED, bg=t.BG, font=t.Fontes.display(13, "normal", True)).pack(pady=24)
            return
        nomes = {f["chave"]: f["nome"] for f in self.servico.fontes(self.usuario_id)}
        for imp in r.dados:
            f = imp["filtro"]
            cartao = tk.Frame(self.caixa_salvas, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
            cartao.pack(fill="x", pady=(0, 8))
            interno = tk.Frame(cartao, bg=t.SURFACE, padx=16, pady=12)
            interno.pack(fill="x")
            topo = tk.Frame(interno, bg=t.SURFACE)
            topo.pack(fill="x")
            tk.Label(topo, text=imp["nome"], fg=t.TEXT, bg=t.SURFACE, font=t.Fontes.display(15)).pack(side="left")
            if imp.get("automatica"):
                _etiqueta(topo, "Automática 1×/dia", t.PRIMARY, t.SURFACE).pack(side="left", padx=10)
            ultima = imp.get("ultima_execucao")
            tk.Label(topo, text="ÚLTIMA EXECUÇÃO: " + (f"{ultima:%d/%m/%Y %H:%M}" if isinstance(ultima, datetime) else "nunca"),
                     fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(8, "bold")).pack(side="right")
            resumo = (f"Jornais: {', '.join(nomes.get(c, c) for c in f.fontes)} • período: "
                      f"{next((v[0] for v in PERIODOS.values() if v[1] == f.periodo_horas), str(f.periodo_horas) + ' h')} • "
                      f"máx. {f.limite_por_fonte} por jornal • destino: {STATUS_DESTINO.get(f.status_destino, f.status_destino)}")
            if f.incluir:
                resumo += f" • com: {', '.join(f.incluir)}"
            if f.excluir:
                resumo += f" • sem: {', '.join(f.excluir)}"
            tk.Label(interno, text=resumo, fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left", wraplength=900,
                     font=t.Fontes.corpo(9)).pack(fill="x", pady=(4, 8))
            acoes = tk.Frame(interno, bg=t.SURFACE)
            acoes.pack(fill="x")
            t.botao_primario(acoes, "Rodar agora", lambda i=imp: self._rodar_salva(i)).pack(side="left")
            t.botao_secundario(acoes, "EDITAR", lambda i=imp: self._editar_salva(i)).pack(side="left", padx=8)
            t.botao_secundario(acoes, "EXCLUIR", lambda i=imp: self._excluir_salva(i)).pack(side="left")

    def _editar_salva(self, imp):
        self._montar_fontes_filtro()
        self._aplicar_filtro(imp["filtro"])
        self.var_auto.set(bool(imp.get("automatica")))
        self._editando_id = imp["id"]
        self.rotulo_edicao.configure(text=f"EDITANDO “{imp['nome']}”. Ajuste e use SALVAR FILTROS para gravar.")
        self._mostrar_aba("busca")

    def _excluir_salva(self, imp):
        if messagebox.askyesno("Excluir importação", f"Excluir a importação salva “{imp['nome']}”?", parent=self):
            r = self.servico.excluir_importacao(imp["id"])
            if not r.ok:
                messagebox.showwarning("Clipping", r.mensagem, parent=self)
            self._desenhar_salvas()

    def _rodar_salva(self, imp, origem="salva", ao_fim=None, avisar=True):
        """Fluxo em três passos (banco -> rede em thread -> banco), como a busca manual."""
        if self._ocupado:
            if ao_fim:
                ao_fim(None)
            return
        filtro = imp["filtro"]
        feeds, estados = self.servico.preparar_coleta(self.usuario_id, filtro)
        self._definir_ocupado(True, f"RODANDO “{imp['nome'].upper()}”…")

        def concluido(ok, valor):
            self._definir_ocupado(False)
            previa = (self.servico.concluir_coleta(self.usuario_id, filtro, valor) if ok
                      else Resultado(False, f"A busca falhou: {valor}"))
            resultado = self.servico.importar_da_salva(self.usuario_id, imp, previa, origem, avisar=avisar)
            if ao_fim:
                ao_fim(resultado)
            else:
                self.rotulo_resultado_salva.configure(text=f"“{imp['nome']}”: {resultado.mensagem}")
                self._desenhar_salvas()
                if self.ao_alterar:
                    self.ao_alterar()

        if not feeds:
            concluido(True, [])
            return
        executar_async(self, lambda: coletar_feeds(feeds, estados, rede.buscar), concluido)

    # ---------- importação automática (1 vez por dia, ao abrir) ----------
    def executar_automaticas(self):
        """Chamada pela janela pouco depois de abrir: roda, em segundo plano, as importações salvas
        marcadas como automáticas que ainda não rodaram hoje, e registra um aviso-resumo no fim."""
        self._fila_auto = self.servico.automaticas_pendentes(self.usuario_id)
        self._resumo_auto = {"importacoes": 0, "materias": 0, "falhas": 0}
        self._proxima_auto()

    def _proxima_auto(self):
        if not self._fila_auto:
            if self._resumo_auto["importacoes"]:
                s = self._resumo_auto
                registrar_evento(self.db, self.logger, "pauta",
                                 f"Clipping automático: {s['materias']} matéria(s) em {s['importacoes']} importação(ões)",
                                 "Importação diária concluída ao abrir o programa"
                                 + (f"; {s['falhas']} fonte(s) com erro." if s["falhas"] else ".")
                                 + " Conteúdo de terceiros: confira a fonte e os termos de cada jornal.",
                                 "Clipping", "CONTEÚDO DE TERCEIROS")
                if self.ao_alterar:
                    self.ao_alterar()
            return
        imp = self._fila_auto.pop(0)

        def fim(resultado):
            if resultado is not None:
                self._resumo_auto["importacoes"] += 1
                if resultado.dados:
                    self._resumo_auto["materias"] += resultado.dados.get("importadas", 0)
                    self._resumo_auto["falhas"] += len(resultado.dados.get("erros", []))
            self.after(300, self._proxima_auto)
        self._rodar_salva(imp, origem="auto", ao_fim=fim, avisar=False)

    # ---------- aba: histórico ----------
    def _montar_historico(self, aba):
        self.caixa_historico = tk.Frame(aba, bg=t.BG)
        self.caixa_historico.pack(fill="x", pady=(14, 0))

    def _desenhar_historico(self):
        for filho in self.caixa_historico.winfo_children():
            filho.destroy()
        r = self.servico.historico(20)
        linhas = r.dados if r.ok else []
        if not linhas:
            tk.Label(self.caixa_historico, text="Nenhuma importação registrada ainda.", fg=t.TEXT_MUTED, bg=t.BG,
                     font=t.Fontes.display(13, "normal", True)).pack(pady=24)
            return
        tabela = tk.Frame(self.caixa_historico, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        tabela.pack(fill="x")
        for col, texto in enumerate(("QUANDO", "ORIGEM", "IMPORTAÇÃO / JORNAIS", "IMPORTADAS", "JÁ EXISTIAM", "FALHAS")):
            tabela.grid_columnconfigure(col, weight=3 if col == 2 else 1)
            tk.Label(tabela, text=texto, fg=t.TEXT, bg=PAINEL_ALTO, anchor="w", padx=8, pady=6,
                     font=t.Fontes.corpo(8, "bold")).grid(row=0, column=col, sticky="ew")
        for n, h in enumerate(linhas, start=1):
            fundo = t.SURFACE if n % 2 else PAINEL_BAIXO
            quando = h["quando"]
            celulas = (f"{quando:%d/%m/%Y %H:%M}" if isinstance(quando, datetime) else str(quando),
                       ROTULO_ORIGEM.get(h["origem"], h["origem"]), h.get("nome") or (h.get("fontes") or "—"),
                       str(h["importadas"]), str(h["existentes"]), str(h["falhas"]))
            for col, texto in enumerate(celulas):
                tk.Label(tabela, text=texto, fg=t.TEXT, bg=fundo, anchor="w", padx=8, pady=6, wraplength=420,
                         justify="left", font=t.Fontes.corpo(10)).grid(row=n, column=col, sticky="ew")

    # ---------- aba: fontes ----------
    def _montar_fontes(self, aba):
        topo = tk.Frame(aba, bg=t.BG)
        topo.pack(fill="x", pady=(14, 0))
        t.botao_primario(topo, "Testar fontes", self._testar_fontes).pack(side="left")
        tk.Label(topo, text="Verifica cada feed ativo e mostra OK/falha (útil em redes de faculdade). Respeita o "
                            "intervalo de 15 min entre coletas.", fg=t.TEXT_MUTED, bg=t.BG, wraplength=700,
                 justify="left", font=t.Fontes.corpo(9)).pack(side="left", padx=12)
        self.caixa_teste = tk.Frame(aba, bg=t.BG)
        self.caixa_teste.pack(fill="x", pady=(10, 0))
        self.caixa_lista_fontes = tk.Frame(aba, bg=t.BG)
        self.caixa_lista_fontes.pack(fill="x", pady=(10, 0))
        cartao, f = self._cartao(aba, "Adicionar feed próprio", "Seu jornal")
        cartao.pack(fill="x", pady=(10, 0))
        linha = tk.Frame(f, bg=t.SURFACE)
        linha.pack(fill="x")
        self.campo_novo_nome = t.CampoEditorial(linha, "Nome do jornal")
        self.campo_novo_nome.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.campo_nova_url = t.CampoEditorial(linha, "Endereço do feed (http/https)")
        self.campo_nova_url.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.campo_nova_secao = t.CampoEditorial(linha, "Seção (opcional)")
        self.campo_nova_secao.pack(side="left", fill="x", expand=True)
        self.rotulo_novo = tk.Label(f, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", wraplength=900,
                                    justify="left", font=t.Fontes.corpo(9))
        self.rotulo_novo.pack(fill="x", pady=(8, 0))
        t.botao_secundario(f, "VALIDAR E ADICIONAR", self._adicionar_feed).pack(anchor="e", pady=(6, 0))

    def _desenhar_fontes(self):
        for filho in self.caixa_lista_fontes.winfo_children():
            filho.destroy()
        self._vars_ativas = {}
        for f in self.servico.fontes(self.usuario_id):
            cartao = tk.Frame(self.caixa_lista_fontes, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
            cartao.pack(fill="x", pady=(0, 6))
            interno = tk.Frame(cartao, bg=t.SURFACE, padx=14, pady=10)
            interno.pack(fill="x")
            topo = tk.Frame(interno, bg=t.SURFACE)
            topo.pack(fill="x")
            var = tk.BooleanVar(value=f["ativo"])
            self._vars_ativas[f["chave"]] = var
            tk.Checkbutton(topo, text=f["nome"], variable=var, bg=t.SURFACE, fg=t.TEXT, activebackground=t.SURFACE,
                           selectcolor=t.SURFACE, font=t.Fontes.display(14),
                           state="normal" if f["feeds"] else "disabled",
                           command=lambda c=f["chave"]: self._alternar_fonte(c)).pack(side="left")
            if f.get("idioma"):
                _etiqueta(topo, f"{f.get('pais', '')} • {f['idioma']}".strip(" •"), t.TEXT_MUTED, t.SURFACE).pack(side="left", padx=8)
            if f.get("proprio"):
                _link(topo, "REMOVER", lambda i=f["proprio_id"]: self._remover_feed(i), t.ERROR).pack(side="right")
            elif f.get("site"):
                _link(topo, "SITE ↗", lambda u=f["site"]: self._abrir_link(u)).pack(side="right")
            if f.get("nota"):
                tk.Label(interno, text=f["nota"], fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left",
                         wraplength=900, font=t.Fontes.corpo(9)).pack(fill="x", pady=(2, 4))
            for feed in f["feeds"]:
                v = feed.get("verificacao")
                tk.Label(interno, text=f"•  {feed['secao']}  —  {ROTULO_VERIFICACAO.get(v, v or '')}",
                         fg=t.ERROR if v == "nao_verificada" else t.TEXT_MUTED, bg=t.SURFACE, anchor="w",
                         font=t.Fontes.corpo(9)).pack(fill="x")

    def _alternar_fonte(self, chave):
        r = self.servico.definir_fonte_ativa(self.usuario_id, chave, bool(self._vars_ativas[chave].get()))
        if not r.ok:
            messagebox.showwarning("Clipping", r.mensagem, parent=self)
        self._montar_fontes_filtro()

    def _testar_fontes(self):
        if self._ocupado:
            return
        feeds, estados = self.servico.preparar_coleta(self.usuario_id, FiltroClipping())
        if not feeds:
            messagebox.showinfo("Clipping", "Nenhuma fonte ativa para testar.", parent=self)
            return
        self._definir_ocupado(True, f"TESTANDO {len(feeds)} FEED(S)…")

        def pronto(ok, valor):
            self._definir_ocupado(False)
            for filho in self.caixa_teste.winfo_children():
                filho.destroy()
            if not ok:
                messagebox.showwarning("Clipping", f"O teste falhou: {valor}", parent=self)
                return
            r = self.servico.testar_fontes(self.usuario_id, resultados=valor)
            tk.Label(self.caixa_teste, text=r.mensagem.upper(), fg=t.TEXT, bg=t.BG, anchor="w",
                     font=t.Fontes.corpo(9, "bold")).pack(fill="x")
            for l in r.dados:
                tk.Label(self.caixa_teste, text=f"{'✔ OK ' if l['ok'] else '✖ FALHA'}   {l['fonte']} — {l['secao']}: {l['detalhe']}",
                         fg=t.SUCCESS if l["ok"] else t.ERROR, bg=t.BG, anchor="w", justify="left", wraplength=900,
                         font=t.Fontes.corpo(9)).pack(fill="x")
            self._montar_fontes_filtro()
        executar_async(self, lambda: coletar_feeds(feeds, estados, rede.buscar), pronto)

    def _adicionar_feed(self):
        nome, url, secao = self.campo_novo_nome.get(), self.campo_nova_url.get(), self.campo_nova_secao.get()
        if not rede.url_valida(url):
            self.rotulo_novo.configure(text="Informe um endereço válido (http:// ou https://).", fg=t.ERROR)
            return
        self.rotulo_novo.configure(text="Validando o feed…", fg=t.TEXT_MUTED)

        def pronto(ok, valor):
            if not ok:
                self.rotulo_novo.configure(text=f"Não foi possível validar o feed: {valor}", fg=t.ERROR)
                return
            r = self.servico.salvar_feed_proprio(self.usuario_id, nome or valor["titulo"], url, secao)
            self.rotulo_novo.configure(text=r.mensagem + (f" ({valor['total']} item(ns) encontrados)" if r.ok else ""),
                                       fg=t.SUCCESS if r.ok else t.ERROR)
            if r.ok:
                for c in (self.campo_novo_nome, self.campo_nova_url, self.campo_nova_secao):
                    c.set("")
                self._desenhar_fontes()
                self._montar_fontes_filtro()
        executar_async(self, lambda: validar_feed(url), pronto)

    def _remover_feed(self, feed_id):
        if messagebox.askyesno("Remover feed", "Remover este feed próprio?", parent=self):
            self.servico.remover_feed_proprio(self.usuario_id, feed_id)
            self._desenhar_fontes()
            self._montar_fontes_filtro()
