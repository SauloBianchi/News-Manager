"""
tela_tempo.py
Previsão do tempo no NewsManager:

- AtualizadorTempo: estado compartilhado (cidade, última previsão, situação) e
  atualização automática em segundo plano. Alimenta a faixa superior
  (Cabecalho) e a tela maior. Nenhuma chamada de rede acontece na thread da
  interface: a busca roda em thread (app/segundo_plano.py) e o resultado volta
  pela fila + after(). O banco só é usado na thread principal.
- TempoFrame: tela "Caderno de Meteorologia & Condições do Tempo" (agora,
  próximas 24 h com gráfico matplotlib, 7 dias, detalhes, alertas da redação,
  troca de cidade e atribuição à Open-Meteo).
- DialogoEscolherCidade: busca por nome com lista de resultados (cidade,
  estado e país) — usada na tela maior e no Perfil.
- perguntar_localizacao_inicial: pergunta, uma única vez, se pode usar o IP.
"""

import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from . import rede
from . import theme as t
from .graficos_tempo import figura_24h
from .perfil import PerfilService
from .segundo_plano import executar_async
from .telas_cadastros import MARGEM, PAINEL, PAINEL_ALTO, PAINEL_BAIXO, _cabecalho, _filete, _link, _TelaBase
from .tempo import (CIDADE_PADRAO, INTERVALO_ATUALIZACAO_MIN, TEXTO_ATRIBUICAO, URL_ATRIBUICAO, TempoService,
                    buscar_cidades_rede, baixar_previsao, chave_cache, fmt_temp, gerar_alertas,
                    localizar_por_ip_rede, rascunho_pauta, rotulo_completo, rotulo_local, texto_faixa)

AVISO_IP = ("Para descobrir sua cidade aproximada, o NewsManager envia o endereço IP deste computador ao serviço "
            "de terceiros ipapi.co (gratuito, limite de cerca de 1.000 consultas por dia). Nenhum outro dado é "
            "enviado e você pode escolher a cidade pelo nome a qualquer momento.\n\nPermitir?")
DIAS_CURTOS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]


class AtualizadorTempo:
    """Estado e atualização automática da previsão (sem widgets: testável com executor síncrono)."""

    def __init__(self, widget, db, logger, usuario_id, buscar=rede.buscar, executor=executar_async,
                 agora=datetime.now):
        self.widget = widget
        self.usuario_id = usuario_id
        self.tempo = TempoService(db, logger)
        self.perfil = PerfilService(db, logger)
        self.buscar = buscar
        self.executor = executor
        self.agora = agora
        self.previsao = None
        self.estado = "carregando"        # carregando | ok | offline | sem_previsao
        self.mensagem = ""
        self.atualizado_em = None
        self.desatualizada = False
        self._ocupado = False
        self._ouvintes = []

    # ---------- ouvintes ----------
    def adicionar_ouvinte(self, funcao):
        self._ouvintes.append(funcao)

    def _avisar(self):
        for f in list(self._ouvintes):
            try:
                f()
            except tk.TclError:
                pass

    # ---------- cidade ----------
    def local(self) -> dict:
        """Cidade salva do usuário; sem ela, a cidade padrão."""
        return (self.perfil.obter_local(self.usuario_id) if self.usuario_id else None) or dict(CIDADE_PADRAO)

    def tem_cidade_salva(self) -> bool:
        return bool(self.usuario_id and self.perfil.obter_local(self.usuario_id))

    def trocar_local(self, local):
        """Salva a cidade do usuário e atualiza a faixa na hora."""
        resultado = self.perfil.salvar_local(self.usuario_id, local)
        if resultado.ok:
            self.previsao, self.estado = None, "carregando"
            self.iniciar_leitura_do_cache()
            self.atualizar()
        return resultado

    # ---------- atualização ----------
    def iniciar_leitura_do_cache(self):
        """Mostra o último dado guardado imediatamente (a rede só confirma depois)."""
        r = self.tempo.cache_qualquer(self.local(), self.agora())
        if r:
            self._aplicar(r, notificar=True)
        else:
            self._avisar()

    def iniciar(self):
        """Chamado na abertura da janela: cache na hora, rede em segundo plano e tique periódico."""
        self.iniciar_leitura_do_cache()
        self.atualizar()
        self._agendar()

    def _agendar(self):
        try:
            self.widget.after(INTERVALO_ATUALIZACAO_MIN * 60_000, self._tique)
        except tk.TclError:
            pass

    def _tique(self):
        self.atualizar(forcar=True)
        self._agendar()

    def atualizar(self, forcar=False):
        if self._ocupado:
            return
        local = self.local()
        if not forcar:
            fresco = self.tempo.cache_fresco(local, self.agora())
            if fresco:
                self._aplicar(fresco)
                return
        self._ocupado = True
        if not self.previsao:
            self.estado = "carregando"
        self._avisar()
        self.executor(self.widget, lambda: baixar_previsao(local, self.buscar),
                      lambda ok, valor: self._concluir(local, ok, valor))

    def _concluir(self, local, ok, valor):
        self._ocupado = False
        if chave_cache(local) != chave_cache(self.local()):   # a cidade mudou durante a busca
            self.atualizar()
            return
        r = self.tempo.concluir(local, valor if ok else None, None if ok else valor, self.agora())
        self._aplicar(r)

    def _aplicar(self, r, notificar=True):
        if r.ok:
            self.previsao = r.dados
            self.atualizado_em = r.dados["atualizado_em"]
            self.desatualizada = r.dados["desatualizada"]
            self.estado = "offline" if self.desatualizada else "ok"
            self.mensagem = r.mensagem
        else:
            self.previsao, self.atualizado_em = None, None
            self.estado, self.mensagem = "sem_previsao", r.mensagem
        if notificar:
            self._avisar()

    def texto_faixa(self) -> str:
        return texto_faixa(self.local(), self.previsao, self.estado, self.atualizado_em, self.desatualizada)

    # ---------- buscas assíncronas (só rede) ----------
    def buscar_cidades(self, nome, ao_concluir):
        self.executor(self.widget, lambda: buscar_cidades_rede(nome, self.buscar), ao_concluir)

    def localizar_por_ip(self, ao_concluir):
        self.executor(self.widget, lambda: localizar_por_ip_rede(self.buscar), ao_concluir)


def perguntar_localizacao_inicial(janela, atualizador):
    """Fluxo da primeira abertura: se não há cidade salva nem decisão anterior, pergunta UMA vez
    se pode usar o IP. A decisão (aceita/recusa) é guardada e respeitada."""
    if not atualizador.usuario_id or atualizador.tem_cidade_salva():
        return
    if atualizador.perfil.decisao_localizacao_ip(atualizador.usuario_id):
        return
    aceitou = messagebox.askyesno("Previsão do tempo", "Quer ver a previsão do tempo da sua cidade?\n\n" + AVISO_IP,
                                  parent=janela)
    atualizador.perfil.registrar_decisao_ip(atualizador.usuario_id, aceitou)
    if aceitou:
        usar_localizacao_por_ip(janela, atualizador, avisar_privacidade=False)


def usar_localizacao_por_ip(janela, atualizador, avisar_privacidade=True):
    """Descobre a cidade pelo IP (com consentimento) e a salva. Em falha, orienta a buscar pelo nome."""
    if avisar_privacidade:
        if not messagebox.askyesno("Localização aproximada", AVISO_IP, parent=janela):
            return
        atualizador.perfil.registrar_decisao_ip(atualizador.usuario_id, True)

    def pronto(ok, valor):
        if not ok:
            messagebox.showinfo("Localização aproximada",
                                f"{valor}\n\nUsando {rotulo_local(atualizador.local())}. Você pode escolher a cidade "
                                "pelo nome na tela de previsão ou no Perfil.", parent=janela)
            return
        r = atualizador.trocar_local(valor)
        if not r.ok:
            messagebox.showwarning("Localização aproximada", r.mensagem, parent=janela)

    atualizador.localizar_por_ip(pronto)


# =============================================================================
# Diálogo: escolher cidade por nome
# =============================================================================
class DialogoEscolherCidade(tk.Toplevel):
    def __init__(self, parent, atualizador, ao_escolher=None):
        super().__init__(parent, bg=t.SURFACE)
        t.Fontes.preparar(self)
        self.title("Escolher cidade")
        self.resizable(False, False)
        self.transient(parent)
        self.atualizador = atualizador
        self.ao_escolher = ao_escolher
        self._resultados = []

        corpo = tk.Frame(self, bg=t.SURFACE, padx=22, pady=18)
        corpo.pack(fill="both", expand=True)
        tk.Label(corpo, text="Cidade da previsão do tempo", fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.display(18)).pack(fill="x")
        tk.Label(corpo, text="Digite o nome e escolha o resultado certo (cidade, estado e país).", fg=t.TEXT_MUTED,
                 bg=t.SURFACE, anchor="w", font=t.Fontes.corpo(9)).pack(fill="x", pady=(2, 10))
        linha = tk.Frame(corpo, bg=t.SURFACE)
        linha.pack(fill="x")
        self.campo = t.CampoEditorial(linha, "Nome da cidade")
        self.campo.pack(side="left", fill="x", expand=True)
        self.campo.entry.bind("<Return>", lambda e: self._buscar())
        t.botao_secundario(linha, "BUSCAR", self._buscar).pack(side="left", padx=(10, 0), anchor="s")
        self.lista = tk.Listbox(corpo, height=8, width=58, relief="flat", bg=t.SURFACE, fg=t.TEXT,
                                highlightthickness=1, highlightbackground=t.BORDER, font=t.Fontes.corpo(11),
                                activestyle="none", selectbackground=t.PRIMARY, selectforeground="#FFFFFF")
        self.lista.pack(fill="x", pady=(12, 0))
        self.lista.bind("<Double-Button-1>", lambda e: self._usar())
        self.status = tk.Label(corpo, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left",
                               wraplength=420, font=t.Fontes.corpo(9))
        self.status.pack(fill="x", pady=(6, 0))
        botoes = tk.Frame(corpo, bg=t.SURFACE)
        botoes.pack(fill="x", pady=(12, 0))
        t.botao_primario(botoes, "Usar esta cidade", self._usar).pack(side="right")
        t.botao_secundario(botoes, "CANCELAR", self.destroy).pack(side="right", padx=(0, 8))
        self.campo.focus()

    def _buscar(self):
        nome = self.campo.get()
        if len(nome) < 2:
            self.status.configure(text="Digite pelo menos 2 letras.", fg=t.ERROR)
            return
        self.status.configure(text="Buscando…", fg=t.TEXT_MUTED)
        self.atualizador.buscar_cidades(nome, self._recebeu)

    def _recebeu(self, ok, valor):
        self.lista.delete(0, "end")
        if not ok:
            self._resultados = []
            self.status.configure(text=str(valor), fg=t.ERROR)
            return
        self._resultados = valor
        if not valor:
            self.status.configure(text="Nenhuma cidade encontrada. Confira a grafia.", fg=t.ERROR)
            return
        for local in valor:
            self.lista.insert("end", rotulo_completo(local))
        self.lista.selection_set(0)
        self.status.configure(text=f"{len(valor)} resultado(s).", fg=t.TEXT_MUTED)

    def _usar(self):
        selecao = self.lista.curselection()
        if not selecao or not self._resultados:
            self.status.configure(text="Escolha uma cidade da lista.", fg=t.ERROR)
            return
        local = self._resultados[selecao[0]]
        r = self.atualizador.trocar_local(local)
        if not r.ok:
            self.status.configure(text=r.mensagem, fg=t.ERROR)
            return
        if self.ao_escolher:
            self.ao_escolher(local)
        self.destroy()


# =============================================================================
# Tela maior
# =============================================================================
class TempoFrame(_TelaBase):
    def __init__(self, parent, db, logger, atualizador, ao_voltar=None, ao_criar_pauta=None):
        super().__init__(parent, db, logger, None)
        self.atualizador = atualizador
        self.ao_voltar = ao_voltar
        self.ao_criar_pauta = ao_criar_pauta
        self._canvas = None
        self._sujo = True
        self._montar()
        atualizador.adicionar_ouvinte(self._ao_mudar)

    # ---------- montagem ----------
    def _montar(self):
        p = self.pagina
        linha = _cabecalho(
            p, "Caderno de meteorologia • Serviço de plantão", "Caderno de Meteorologia & Condições do Tempo",
            "Condições atuais, próximas 24 horas e semana para apoiar a cobertura, a pauta e a equipe de campo.")
        botoes = tk.Frame(linha, bg=t.BG)
        botoes.pack(side="right", anchor="s")
        topo = tk.Frame(botoes, bg=t.BG)
        topo.pack(side="top", fill="x")
        t.botao_secundario(topo, "← VOLTAR", self._voltar).pack(side="left", padx=(0, 8))
        t.botao_primario(topo, "Atualizar", self._atualizar).pack(side="left")
        self.rotulo_carimbo = tk.Label(botoes, text="", fg=t.TEXT_MUTED, bg=t.BG, font=t.Fontes.corpo(8, "bold"))
        self.rotulo_carimbo.pack(side="top", anchor="e", pady=(6, 0))
        _filete(p)
        self.faixa_aviso = tk.Label(p, text="", fg=t.PRIMARY, bg=t.BG, anchor="w", justify="left", wraplength=1000,
                                    font=t.Fontes.corpo(9, "bold"))
        self.faixa_aviso.pack(fill="x", padx=MARGEM, pady=(10, 0))
        self.corpo = tk.Frame(p, bg=t.BG)
        self.corpo.pack(fill="x", padx=MARGEM, pady=(12, 0))
        self._montar_cidade(p)
        rodape = tk.Frame(p, bg=t.BG)
        rodape.pack(fill="x", padx=MARGEM, pady=(14, 0))
        _link(rodape, TEXTO_ATRIBUICAO.upper(), lambda: webbrowser.open(URL_ATRIBUICAO)).pack(side="left")
        tk.Label(rodape, text="Weather data by Open-Meteo.com  •  uso não comercial",
                 fg=t.TEXT_MUTED, bg=t.BG, font=t.Fontes.corpo(8)).pack(side="right")
        tk.Frame(p, bg=t.BG, height=28).pack()

    def _cartao(self, pai, titulo, rotulo=None):
        cartao = tk.Frame(pai, bg=t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=18, pady=14)
        interno.pack(fill="both", expand=True)
        if rotulo:
            tk.Label(interno, text=rotulo.upper(), fg=t.PRIMARY, bg=t.SURFACE, anchor="w",
                     font=t.Fontes.corpo(8, "bold")).pack(fill="x")
        tk.Label(interno, text=titulo, fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.display(17)).pack(fill="x", pady=(0, 8))
        return cartao, interno

    def _montar_cidade(self, p):
        cartao, interno = self._cartao(p, "Cidade da previsão", "Local de referência")
        cartao.pack(fill="x", padx=MARGEM, pady=(14, 0))
        linha = tk.Frame(interno, bg=t.SURFACE)
        linha.pack(fill="x")
        self.rotulo_cidade = tk.Label(linha, text="", fg=t.TEXT, bg=t.SURFACE, anchor="w", font=t.Fontes.display(14, "normal", True))
        self.rotulo_cidade.pack(side="left")
        t.botao_secundario(linha, "BUSCAR OUTRA CIDADE…", self._trocar_cidade).pack(side="right")
        t.botao_secundario(linha, "USAR LOCALIZAÇÃO APROXIMADA (POR IP)", self._usar_ip).pack(side="right", padx=(0, 8))
        tk.Label(interno, text="Ao usar a localização por IP, o endereço IP é enviado a um serviço de terceiros "
                               "(ipapi.co) somente depois da sua confirmação.", fg=t.TEXT_MUTED, bg=t.SURFACE,
                 anchor="w", justify="left", wraplength=980, font=t.Fontes.corpo(8)).pack(fill="x", pady=(6, 0))
        if self.ao_criar_pauta:
            tk.Frame(interno, bg=t.BORDER, height=1).pack(fill="x", pady=10)
            t.botao_secundario(interno, "CRIAR PAUTA DO TEMPO", self._criar_pauta).pack(anchor="w")

    # ---------- ciclo de vida ----------
    def mostrar(self):
        """Chamada pela janela ao abrir a tela: redesenha e atualiza se o dado estiver velho."""
        self._redesenhar()
        self.atualizador.atualizar()

    def _ao_mudar(self):
        if self.winfo_ismapped():
            self._redesenhar()
        else:
            self._sujo = True

    def _voltar(self):
        if self.ao_voltar:
            self.ao_voltar()

    def _atualizar(self):
        self.atualizador.atualizar(forcar=True)

    def _trocar_cidade(self):
        DialogoEscolherCidade(self, self.atualizador, ao_escolher=lambda l: self._redesenhar())

    def _usar_ip(self):
        usar_localizacao_por_ip(self, self.atualizador)

    def _criar_pauta(self):
        previsao = self.atualizador.previsao
        if not previsao:
            messagebox.showinfo("Previsão do tempo", "Ainda não há previsão para gerar a pauta.", parent=self)
            return
        titulo, texto = rascunho_pauta(self.atualizador.local(), previsao)
        if self.ao_criar_pauta:
            self.ao_criar_pauta({"titulo": titulo, "conteudo": texto, "status": "rascunho"})

    # ---------- desenho ----------
    def _redesenhar(self):
        self._sujo = False
        a = self.atualizador
        local = a.local()
        self.rotulo_cidade.configure(text=f"{rotulo_local(local)}" + ("" if a.tem_cidade_salva() else "  (cidade padrão)"))
        self.rotulo_carimbo.configure(
            text=f"ATUALIZADO ÀS {a.atualizado_em:%H:%M}" + ("  •  DADO EM CACHE" if a.desatualizada else "")
            if a.atualizado_em else ("CARREGANDO…" if a.estado == "carregando" else "SEM PREVISÃO"))
        self.faixa_aviso.configure(text=a.mensagem if a.estado in ("offline", "sem_previsao") else "")
        if self._canvas is not None:
            self._canvas.get_tk_widget().destroy()
            self._canvas = None
        for filho in self.corpo.winfo_children():
            filho.destroy()
        if not a.previsao:
            texto = ("Buscando a previsão…" if a.estado == "carregando"
                     else "Sem previsão no momento. Verifique a conexão e use ATUALIZAR.")
            tk.Label(self.corpo, text=texto, fg=t.TEXT_MUTED, bg=t.BG, font=t.Fontes.display(14, "normal", True)).pack(pady=30)
            return
        v = a.previsao
        topo = tk.Frame(self.corpo, bg=t.BG)
        topo.pack(fill="x")
        topo.grid_columnconfigure(0, weight=3, uniform="topo")
        topo.grid_columnconfigure(1, weight=2, uniform="topo")
        self._desenhar_agora(topo, v)
        self._desenhar_alertas(topo, v)
        self._desenhar_horas(v)
        self._desenhar_grafico(v)
        self._desenhar_semana(v)
        self._desenhar_detalhes(v)

    def _desenhar_agora(self, pai, v):
        c = v["atual"]
        hoje = v["dias"][0] if v["dias"] else {}
        cartao, i = self._cartao(pai, "Agora", "Condição atual")
        cartao.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        linha = tk.Frame(i, bg=t.SURFACE)
        linha.pack(fill="x")
        tk.Label(linha, text=c["simbolo"], fg=t.PRIMARY, bg=t.SURFACE, font=t.Fontes.display(54)).pack(side="left", padx=(0, 14))
        bloco = tk.Frame(linha, bg=t.SURFACE)
        bloco.pack(side="left")
        tk.Label(bloco, text=fmt_temp(c["temperatura"]), fg=t.TEXT, bg=t.SURFACE, font=t.Fontes.display(46)).pack(anchor="w")
        tk.Label(bloco, text=c["descricao"], fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.display(15, "normal", True)).pack(anchor="w")
        faixa = tk.Frame(i, bg=PAINEL_BAIXO)
        faixa.pack(fill="x", pady=(12, 0))
        for rotulo, valor in (("SENSAÇÃO", fmt_temp(c["sensacao"])), ("MÁXIMA", fmt_temp(hoje.get("maxima"))),
                              ("MÍNIMA", fmt_temp(hoje.get("minima")))):
            col = tk.Frame(faixa, bg=PAINEL_BAIXO, padx=14, pady=8)
            col.pack(side="left")
            tk.Label(col, text=rotulo, fg=t.TEXT_MUTED, bg=PAINEL_BAIXO, font=t.Fontes.corpo(7, "bold")).pack(anchor="w")
            tk.Label(col, text=valor, fg=t.TEXT, bg=PAINEL_BAIXO, font=t.Fontes.display(16)).pack(anchor="w")

    def _desenhar_alertas(self, pai, v):
        cartao, i = self._cartao(pai, "Alertas da redação", "Pontos de atenção")
        cartao.grid(row=0, column=1, sticky="nsew")
        alertas = gerar_alertas(v)
        if not alertas:
            tk.Label(i, text="Nenhum alerta: o tempo está dentro dos limites de atenção da redação.", fg=t.SUCCESS,
                     bg=t.SURFACE, anchor="w", justify="left", wraplength=360, font=t.Fontes.corpo(10)).pack(fill="x")
        for texto in alertas:
            linha = tk.Frame(i, bg=t.SURFACE)
            linha.pack(fill="x", pady=3)
            tk.Label(linha, text="▲", fg=t.PRIMARY, bg=t.SURFACE, font=t.Fontes.corpo(9, "bold")).pack(side="left", anchor="n")
            tk.Label(linha, text=texto, fg=t.TEXT, bg=t.SURFACE, anchor="w", justify="left", wraplength=340,
                     font=t.Fontes.corpo(10)).pack(side="left", padx=(8, 0), fill="x")

    def _desenhar_horas(self, v):
        cartao, i = self._cartao(self.corpo, "Próximas 24 horas", "Faixa horária")
        cartao.pack(fill="x", pady=(14, 0))
        linha = tk.Frame(i, bg=t.SURFACE)
        linha.pack(fill="x")
        passos = v["horas"][::3][:8]
        for n, h in enumerate(passos):
            linha.grid_columnconfigure(n, weight=1, uniform="hora")
            col = tk.Frame(linha, bg=PAINEL_BAIXO if n % 2 == 0 else t.SURFACE, padx=6, pady=8)
            col.grid(row=0, column=n, sticky="nsew")
            fundo = col.cget("bg")
            tk.Label(col, text=f"{h['hora']:%H}h", fg=t.TEXT_MUTED, bg=fundo, font=t.Fontes.corpo(8, "bold")).pack()
            tk.Label(col, text=h["simbolo"], fg=t.PRIMARY, bg=fundo, font=t.Fontes.display(18)).pack()
            tk.Label(col, text=fmt_temp(h["temperatura"]), fg=t.TEXT, bg=fundo, font=t.Fontes.display(13)).pack()
            tk.Label(col, text="" if h["chuva_prob"] is None else f"☂ {h['chuva_prob']}%", fg=t.SECONDARY, bg=fundo,
                     font=t.Fontes.corpo(8)).pack()

    def _desenhar_grafico(self, v):
        cartao, i = self._cartao(self.corpo, "Temperatura e chance de chuva", "Gráfico • próximas 24 h")
        cartao.pack(fill="x", pady=(14, 0))
        self._canvas = FigureCanvasTkAgg(figura_24h(v["horas"], largura=9.4, altura=2.7), master=i)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill="x")

    def _desenhar_semana(self, v):
        cartao, i = self._cartao(self.corpo, "Previsão para 7 dias", "Semana")
        cartao.pack(fill="x", pady=(14, 0))
        tabela = tk.Frame(i, bg=t.SURFACE)
        tabela.pack(fill="x")
        cab = ("DIA", "CONDIÇÃO", "MÍN", "MÁX", "CHANCE DE CHUVA", "CHUVA (MM)")
        for col, texto in enumerate(cab):
            tabela.grid_columnconfigure(col, weight=2 if col == 1 else 1)
            tk.Label(tabela, text=texto, fg=t.TEXT, bg=PAINEL_ALTO, anchor="w", padx=8, pady=6,
                     font=t.Fontes.corpo(8, "bold")).grid(row=0, column=col, sticky="ew")
        for n, d in enumerate(v["dias"], start=1):
            fundo = t.SURFACE if n % 2 else PAINEL_BAIXO
            rotulo_dia = "HOJE" if n == 1 else f"{DIAS_CURTOS[d['data'].weekday()]} {d['data']:%d/%m}"
            celulas = (rotulo_dia, f"{d['simbolo']}  {d['descricao']}", fmt_temp(d["minima"]), fmt_temp(d["maxima"]),
                       "—" if d["chuva_prob"] is None else f"{d['chuva_prob']}%",
                       "—" if d["chuva_mm"] is None else f"{d['chuva_mm']:g}")
            for col, texto in enumerate(celulas):
                tk.Label(tabela, text=texto, fg=t.TEXT, bg=fundo, anchor="w", padx=8, pady=6,
                         font=t.Fontes.corpo(10, "bold" if col == 0 else "normal")).grid(row=n, column=col, sticky="ew")

    def _desenhar_detalhes(self, v):
        c = v["atual"]
        hoje = v["dias"][0] if v["dias"] else {}
        cartao, i = self._cartao(self.corpo, "Detalhes de hoje", "Condições")
        cartao.pack(fill="x", pady=(14, 0))
        grade = tk.Frame(i, bg=t.SURFACE)
        grade.pack(fill="x")
        hora = lambda d: "—" if not d else f"{d:%H:%M}"   # noqa: E731
        itens = (("UMIDADE", "—" if c["umidade"] is None else f"{c['umidade']}%"),
                 ("VENTO", "—" if c["vento_kmh"] is None else f"{c['vento_kmh']} km/h {c['vento_dir']}".strip()),
                 ("PRESSÃO", "—" if c["pressao"] is None else f"{c['pressao']} hPa"),
                 ("ÍNDICE UV (MÁX.)", "—" if hoje.get("uv") is None else f"{hoje['uv']:g}"),
                 ("NASCER DO SOL", hora(hoje.get("nascer"))), ("PÔR DO SOL", hora(hoje.get("por"))))
        for n, (rotulo, valor) in enumerate(itens):
            grade.grid_columnconfigure(n % 3, weight=1, uniform="det")
            caixa = tk.Frame(grade, bg=PAINEL_BAIXO, padx=14, pady=10)
            caixa.grid(row=n // 3, column=n % 3, sticky="nsew", padx=3, pady=3)
            tk.Label(caixa, text=rotulo, fg=t.TEXT_MUTED, bg=PAINEL_BAIXO, font=t.Fontes.corpo(7, "bold")).pack(anchor="w")
            tk.Label(caixa, text=valor, fg=t.TEXT, bg=PAINEL_BAIXO, font=t.Fontes.display(16)).pack(anchor="w")
