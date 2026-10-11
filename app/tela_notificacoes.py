"""
tela_notificacoes.py
Painel "Despachos & Notificações" (protótipo Stitch notifica_es_newsmanager).

PainelNotificacoes é uma gaveta que abre sobre o lado direito da janela
principal (botão do envelope no cabeçalho; Esc ou ✕ fecham):
- abas Todas / Não lidas / Urgente (com contagem) e "Marcar lidas";
- cartões com o tipo do despacho, etiqueta, "há quanto tempo", título,
  texto e rodapé; não lidas têm ponto vermelho, e as urgentes ficam em
  destaque;
- clicar num cartão marca como lido e leva ao assunto (matéria, editoria,
  autor ou perfil);
- rodapé com "Configurar alertas do plantão" (abre o Perfil) e "Ver histórico
  completo de notificações" (HistoricoNotificacoes, com paginação).

O backend está em app/notificacoes.py (NotificacaoService).
"""

import tkinter as tk
from tkinter import ttk

from . import theme as t
from .notificacoes import FILTROS, NotificacaoService
from .telas_cadastros import PAINEL, PAINEL_ALTO, PAINEL_BAIXO, RolagemVertical, _link

FUNDO_URGENTE = "#F7F1E3"
COR_AZUL = "#4F5E81"
POR_PAGINA_PAINEL = 30
POR_PAGINA_HISTORICO = 15


def _cartao(pai, item, ao_clicar, largura_texto=380):
    """Cartão de uma notificação (usado no painel)."""
    nao_lida = not item["lida"]
    fundo = FUNDO_URGENTE if (item["urgente"] and nao_lida) else (t.SURFACE if nao_lida else t.BG)
    cartao = tk.Frame(pai, bg=fundo, cursor="hand2")
    corpo = tk.Frame(cartao, bg=fundo, padx=18, pady=14)
    corpo.pack(fill="x")
    partes = [cartao, corpo]

    topo = tk.Frame(corpo, bg=fundo)
    topo.pack(fill="x")
    partes.append(topo)
    ponto = tk.Label(topo, text="●" if nao_lida else " ", fg=t.PRIMARY, bg=fundo, font=t.Fontes.corpo(8))
    ponto.pack(side="left", padx=(0, 8))
    partes.append(ponto)
    if item["tipo"] == "furo":
        selo = tk.Label(topo, text=item["tipo_rotulo"].upper(), fg="#FFFFFF", bg=t.PRIMARY, padx=6, pady=1,
                        font=t.Fontes.corpo(8, "bold"))
        selo.pack(side="left")
        partes.append(selo)
        if item["etiqueta"]:
            lab = tk.Label(topo, text=item["etiqueta"].upper(), fg=t.TEXT_MUTED, bg=fundo,
                           font=t.Fontes.corpo(8, "bold"))
            lab.pack(side="left", padx=(6, 0))
            partes.append(lab)
    else:
        lab = tk.Label(topo, text=item["tipo_rotulo"].upper(), fg=t.PRIMARY if nao_lida else t.TEXT_MUTED,
                       bg=fundo, font=t.Fontes.corpo(8, "bold"))
        lab.pack(side="left")
        partes.append(lab)
        if item["etiqueta"]:
            chip = tk.Label(topo, text=item["etiqueta"].upper(), fg=t.TEXT, bg=PAINEL_ALTO, padx=6, pady=1,
                            font=t.Fontes.corpo(7, "bold"))
            chip.pack(side="left", padx=(6, 0))
            partes.append(chip)
    quando = tk.Label(topo, text=item["tempo"], fg=t.TEXT_MUTED, bg=fundo, font=t.Fontes.corpo(8, "bold"))
    quando.pack(side="right")
    partes.append(quando)

    titulo = tk.Label(corpo, text=item["titulo"], fg=t.TEXT, bg=fundo, anchor="w", justify="left",
                      wraplength=largura_texto, font=t.Fontes.display(15))
    titulo.pack(fill="x", padx=(16, 0), pady=(6, 2))
    partes.append(titulo)
    if item["mensagem"]:
        msg = tk.Label(corpo, text=item["mensagem"], fg=t.TEXT_MUTED, bg=fundo, anchor="w", justify="left",
                       wraplength=largura_texto, font=t.Fontes.corpo(9))
        msg.pack(fill="x", padx=(16, 0))
        partes.append(msg)
    if item["rodape"]:
        rodape = tk.Label(corpo, text=item["rodape"].upper(), anchor="w",
                          fg=t.PRIMARY if item["urgente"] else (COR_AZUL if nao_lida else t.TEXT_MUTED),
                          bg=fundo, font=t.Fontes.corpo(8, "bold"))
        rodape.pack(fill="x", padx=(16, 0), pady=(8, 0))
        partes.append(rodape)
    tk.Frame(cartao, bg=t.BORDER, height=1).pack(fill="x")
    for widget in partes:
        widget.bind("<Button-1>", lambda e, i=item: ao_clicar(i))
    return cartao


class PainelNotificacoes(tk.Frame):
    LARGURA = 460

    def __init__(self, parent, db, logger, usuario_id, ao_abrir_alvo=None, ao_configurar=None,
                 ao_contagem=None):
        super().__init__(parent, bg=t.BG, highlightthickness=1, highlightbackground=t.TEXT)
        t.Fontes.preparar(parent)
        self.db, self.logger = db, logger
        self.servico = NotificacaoService(db, logger, usuario_id)
        self.ao_abrir_alvo = ao_abrir_alvo
        self.ao_configurar = ao_configurar
        self.ao_contagem = ao_contagem
        self.filtro = "todas"
        self.aberto = False
        self.contagens = {f: 0 for f in FILTROS}
        self._abas = {}
        self._historico = None
        self._montar()

    # ---------- montagem ----------
    def _montar(self):
        topo = tk.Frame(self, bg=t.BG, padx=24, pady=18)
        topo.pack(fill="x")
        linha = tk.Frame(topo, bg=t.BG)
        linha.pack(fill="x")
        tk.Label(linha, text="✉  DESPACHOS OFICIAIS", fg=t.PRIMARY, bg=t.BG,
                 font=t.Fontes.corpo(9, "bold")).pack(side="left")
        _link(linha, "✕", self.fechar, t.TEXT).pack(side="right")
        tk.Label(topo, text="Despachos & Notificações", fg=t.TEXT, bg=t.BG, anchor="w",
                 font=t.Fontes.display(24)).pack(fill="x", pady=(8, 2))
        tk.Label(topo, text="Atualizações de pauta, publicações e comunicados do plantão editorial.",
                 fg=t.TEXT_MUTED, bg=t.BG, anchor="w", justify="left", wraplength=self.LARGURA - 60,
                 font=t.Fontes.corpo(9)).pack(fill="x")

        abas = tk.Frame(self, bg=t.BG, padx=24)
        abas.pack(fill="x")
        for chave in FILTROS:
            quadro = tk.Frame(abas, bg=t.BG, cursor="hand2")
            quadro.pack(side="left", padx=(0, 16))
            rotulo = tk.Label(quadro, text="", bg=t.BG, cursor="hand2", font=t.Fontes.corpo(9, "bold"))
            rotulo.pack()
            sublinhado = tk.Frame(quadro, bg=t.BG, height=2)
            sublinhado.pack(fill="x", pady=(3, 0))
            for w in (quadro, rotulo, sublinhado):
                w.bind("<Button-1>", lambda e, c=chave: self._escolher(c))
            self._abas[chave] = (rotulo, sublinhado)
        _link(abas, "✓✓ MARCAR LIDAS", self._marcar_todas, t.TEXT).pack(side="right", pady=(0, 4))
        tk.Frame(self, bg=t.BORDER, height=1).pack(fill="x", padx=24, pady=(6, 0))
        tk.Frame(self, bg=t.TEXT, height=2).pack(fill="x", pady=(0, 0))

        rodape = tk.Frame(self, bg=PAINEL, padx=18, pady=12)
        rodape.pack(side="bottom", fill="x")
        linha = tk.Frame(rodape, bg=PAINEL)
        linha.pack(fill="x")
        _link(linha, "⚙  CONFIGURAR ALERTAS DO PLANTÃO", self._configurar, t.TEXT).pack(side="left")
        tk.Label(linha, text="TERMINAL GALÉS", fg=t.TEXT_MUTED, bg=PAINEL,
                 font=t.Fontes.corpo(8, "bold")).pack(side="right")
        botao = tk.Label(rodape, text="VER HISTÓRICO COMPLETO DE NOTIFICAÇÕES  →", fg="#FFFFFF", bg=t.TEXT,
                         pady=9, cursor="hand2", font=t.Fontes.corpo(9, "bold"))
        botao.pack(fill="x", pady=(10, 0))
        botao.bind("<Button-1>", lambda e: self._abrir_historico())

        self.rotulo_limite = tk.Label(self, text="", fg=t.TEXT_MUTED, bg=t.BG, font=t.Fontes.corpo(8))
        self.rolagem = RolagemVertical(self)
        self.rolagem.pack(fill="both", expand=True)
        self.lista = self.rolagem.conteudo

    # ---------- abrir / fechar ----------
    def abrir(self):
        self.recarregar()
        self.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne", width=self.LARGURA)
        self.lift()
        self.aberto = True

    def fechar(self):
        self.place_forget()
        self.aberto = False

    def alternar(self):
        self.fechar() if self.aberto else self.abrir()

    # ---------- dados ----------
    def atualizar_contagens(self):
        """Só as contagens (aba e selo do sino); devolve o número de não lidas."""
        resultado = self.servico.contagens()
        if resultado.ok:
            self.contagens = resultado.dados
            self._desenhar_abas()
            if self.ao_contagem:
                self.ao_contagem(self.contagens["nao_lidas"])
        return self.contagens["nao_lidas"]

    def recarregar(self):
        self.atualizar_contagens()
        resultado = self.servico.listar(self.filtro, 1, POR_PAGINA_PAINEL)
        for filho in self.lista.winfo_children():
            filho.destroy()
        if not resultado.ok:
            tk.Label(self.lista, text=resultado.mensagem, fg=t.ERROR, bg=t.BG, padx=24, pady=30,
                     wraplength=self.LARGURA - 60, font=t.Fontes.corpo(10)).pack()
            return
        itens = resultado.dados["itens"]
        if not itens:
            vazio = {"todas": "Nenhum despacho por enquanto.", "nao_lidas": "Você está em dia: nenhum despacho não lido.",
                     "urgentes": "Nenhum despacho urgente."}[self.filtro]
            tk.Label(self.lista, text=vazio, fg=t.TEXT_MUTED, bg=t.BG, pady=40,
                     font=t.Fontes.display(13, "normal", True)).pack(fill="x")
        for item in itens:
            _cartao(self.lista, item, self._abrir_item, self.LARGURA - 90).pack(fill="x")
        if resultado.dados["total"] > len(itens):
            tk.Label(self.lista, text=f"Mostrando os {len(itens)} despachos mais recentes de {resultado.dados['total']}. "
                                      "Veja o histórico completo abaixo.", fg=t.TEXT_MUTED, bg=t.BG, pady=12,
                     wraplength=self.LARGURA - 60, font=t.Fontes.corpo(8)).pack(fill="x")

    def _desenhar_abas(self):
        for chave, (rotulo, sublinhado) in self._abas.items():
            ativa = chave == self.filtro
            rotulo.configure(text=f"{FILTROS[chave]} ({self.contagens.get(chave, 0)})",
                             fg=t.PRIMARY if ativa else t.TEXT_MUTED)
            sublinhado.configure(bg=t.PRIMARY if ativa else t.BG)

    # ---------- ações ----------
    def _escolher(self, chave):
        self.filtro = chave
        self.recarregar()

    def _marcar_todas(self):
        self.servico.marcar_todas_lidas()
        self.recarregar()

    def _abrir_item(self, item):
        self.servico.marcar_lida(item["id"])
        self.atualizar_contagens()
        self.fechar()
        if self.ao_abrir_alvo and item["alvo_tipo"]:
            self.ao_abrir_alvo(item["alvo_tipo"], item["alvo_id"])

    def _configurar(self):
        self.fechar()
        if self.ao_configurar:
            self.ao_configurar()

    def _abrir_historico(self):
        self._historico = HistoricoNotificacoes(
            self, self.servico, self._abrir_item_do_historico, ao_mudar=self.atualizar_contagens)

    def _abrir_item_do_historico(self, item):
        if self._historico is not None:
            self._historico.destroy()
            self._historico = None
        self._abrir_item(item)


class HistoricoNotificacoes(tk.Toplevel):
    """Todas as notificações, com filtro e paginação (duplo clique abre o assunto)."""

    def __init__(self, parent, servico, ao_abrir_item=None, ao_mudar=None):
        super().__init__(parent)
        t.Fontes.preparar(self)
        self.servico = servico
        self.ao_abrir_item = ao_abrir_item
        self.ao_mudar = ao_mudar
        self.filtro = "todas"
        self.pagina = 1
        self._itens = {}
        self.title("Histórico de notificações")
        self.configure(bg=t.SURFACE)
        self.geometry("900x520")
        self.minsize(720, 380)
        self.transient(parent.winfo_toplevel())
        self._montar()
        self.recarregar()

    def _montar(self):
        tk.Label(self, text="Histórico de Despachos", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(20)).pack(anchor="w", padx=20, pady=(16, 0))
        barra = tk.Frame(self, bg=t.SURFACE)
        barra.pack(fill="x", padx=20, pady=(8, 8))
        self.combo = ttk.Combobox(barra, values=list(FILTROS.values()), state="readonly", width=16,
                                  font=t.Fontes.corpo(10))
        self.combo.current(0)
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._mudar_filtro())
        t.botao_secundario(barra, "MARCAR TODAS COMO LIDAS", self._marcar_todas).pack(side="right")
        colunas = ("lida", "tipo", "titulo", "quando", "ator")
        self.arvore = ttk.Treeview(self, columns=colunas, show="headings", height=14)
        for coluna, titulo, largura, ancora in (("lida", "", 30, "center"), ("tipo", "Tipo", 150, "w"),
                                                ("titulo", "Título", 330, "w"), ("quando", "Quando", 130, "w"),
                                                ("ator", "Registrado por", 160, "w")):
            self.arvore.heading(coluna, text=titulo)
            self.arvore.column(coluna, width=largura, anchor=ancora)
        self.arvore.pack(fill="both", expand=True, padx=20)
        self.arvore.bind("<Double-1>", lambda e: self._abrir_selecionado())
        rodape = tk.Frame(self, bg=t.SURFACE)
        rodape.pack(fill="x", padx=20, pady=10)
        self.rotulo_pagina = tk.Label(rodape, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(9, "bold"))
        self.rotulo_pagina.pack(side="left")
        self.botao_proxima = t.botao_secundario(rodape, "PRÓXIMA ›", lambda: self._ir(self.pagina + 1))
        self.botao_proxima.pack(side="right")
        self.botao_anterior = t.botao_secundario(rodape, "‹ ANTERIOR", lambda: self._ir(self.pagina - 1))
        self.botao_anterior.pack(side="right", padx=(0, 6))
        tk.Label(self, text="Dê um duplo clique numa linha para abrir o assunto.", fg=t.TEXT_MUTED,
                 bg=t.SURFACE, font=t.Fontes.corpo(8)).pack(anchor="w", padx=20, pady=(0, 10))

    def recarregar(self):
        resultado = self.servico.listar(self.filtro, self.pagina, POR_PAGINA_HISTORICO)
        for linha in self.arvore.get_children():
            self.arvore.delete(linha)
        self._itens = {}
        if not resultado.ok:
            return
        dados = resultado.dados
        self.pagina = dados["pagina"]
        for item in dados["itens"]:
            self._itens[str(item["id"])] = item
            quando = item["criado_em"].strftime("%d/%m/%Y %H:%M") if hasattr(item["criado_em"], "strftime") else ""
            self.arvore.insert("", "end", iid=str(item["id"]), values=(
                "" if item["lida"] else "●", ("⚠ " if item["urgente"] else "") + item["tipo_rotulo"],
                item["titulo"], quando, item["ator"] or ""))
        self.rotulo_pagina.configure(text=f"Página {dados['pagina']} de {dados['paginas']}  •  {dados['total']} despacho(s)")
        self._paginas = dados["paginas"]

    def _mudar_filtro(self):
        self.filtro = list(FILTROS)[max(0, self.combo.current())]
        self.pagina = 1
        self.recarregar()

    def _ir(self, pagina):
        self.pagina = max(1, min(pagina, getattr(self, "_paginas", 1)))
        self.recarregar()

    def _marcar_todas(self):
        self.servico.marcar_todas_lidas()
        self.recarregar()
        if self.ao_mudar:
            self.ao_mudar()

    def _abrir_selecionado(self):
        selecao = self.arvore.selection()
        item = self._itens.get(selecao[0]) if selecao else None
        if item and self.ao_abrir_item:
            self.ao_abrir_item(item)
