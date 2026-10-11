"""
tela_perfil.py
Tela "Registro Funcional & Perfil do Editor" (protótipo Stitch perfil_newsmanager):

- cartão lateral com o crachá (foto, nome, cargo, matrícula, registro, conselho,
  mesa, nota biográfica e números de fechamento) e o botão de sair do sistema;
- Módulo 01: informações básicas do jornalista (nome, assinatura, ramal,
  cargo, matrícula, registro, conselho, mesa, atribuição e nota biográfica),
  com "alterado por ... em ...";
- Módulo 02: segurança — troca de senha com a lista de regras em tempo real e
  a verificação em duas etapas (2FA) por e-mail;
- Módulo 03: preferências do operador (alerta sonoro de furo, e-mail de
  urgência, revisão automática de redação e polegadas de coluna).

As regras ficam em app/perfil.py (PerfilService).
"""

import tkinter as tk
from tkinter import filedialog, messagebox

from . import theme as t
from .midia import TIPOS_ARQUIVO_DIALOGO, ErroMidia
from .midia import midia as midia_global
from .noticias import interpretar_data
from .perfil import ROTULOS_PREFERENCIA, SENHA_MIN, PerfilService, avaliar_senha
from .telas_cadastros import (
    MARGEM,
    PAINEL,
    PAINEL_ALTO,
    PAINEL_BAIXO,
    CampoTextoLongo,
    _link,
    _TelaBase,
)

FUNDO_ROSA = "#F4E1DE"


def mascarar_email(email: str) -> str:
    """'diogo@gazeta.com' -> 'd***@gazeta.com'."""
    if not email or "@" not in email:
        return email or "—"
    usuario, dominio = email.split("@", 1)
    return f"{usuario[:1]}{'*' * max(3, len(usuario) - 1)}@{dominio}"


class Interruptor(tk.Canvas):
    """Chave liga/desliga no estilo do protótipo (vermelha ligada, cinza desligada)."""

    LARGURA, ALTURA = 52, 26

    def __init__(self, parent, valor=False, ao_mudar=None, bg=t.SURFACE):
        super().__init__(parent, width=self.LARGURA, height=self.ALTURA, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.valor = bool(valor)
        self.ao_mudar = ao_mudar
        self.bind("<Button-1>", lambda e: self.alternar())
        self._desenhar()

    def get(self) -> bool:
        return self.valor

    def set(self, valor: bool):
        self.valor = bool(valor)
        self._desenhar()

    def alternar(self):
        self.set(not self.valor)
        if self.ao_mudar:
            self.ao_mudar(self.valor)

    def _desenhar(self):
        self.delete("all")
        l, a = self.LARGURA, self.ALTURA
        self.create_rectangle(1, 1, l - 1, a - 1, fill=t.PRIMARY if self.valor else PAINEL_ALTO, width=0)
        x = l - a + 3 if self.valor else 3
        self.create_rectangle(x, 3, x + a - 6, a - 3, fill="#FFFFFF", width=0)


class PerfilFrame(_TelaBase):
    def __init__(self, parent, db, logger, usuario, ao_sair=None, ao_perfil_alterado=None, abrir_2fa=None):
        super().__init__(parent, db, logger, None)
        self.usuario = usuario            # dicionário compartilhado com a janela principal
        self.servico = PerfilService(db, logger, midia_global)
        self.ao_sair = ao_sair
        self.ao_perfil_alterado = ao_perfil_alterado
        self.abrir_2fa = abrir_2fa        # abrir_2fa(ao_concluir): fluxo de ativação do 2FA
        self.perfil = None
        self.interruptores = {}
        self._montar()
        self.recarregar()

    # =====================================================================
    # Montagem
    # =====================================================================
    def _montar(self):
        p = self.pagina
        self._montar_cabecalho(p)
        corpo = tk.Frame(p, bg=t.BG)
        corpo.pack(fill="x", padx=MARGEM, pady=(16, 0))
        corpo.grid_columnconfigure(0, minsize=320)
        corpo.grid_columnconfigure(1, weight=1)
        esquerda = tk.Frame(corpo, bg=t.BG)
        esquerda.grid(row=0, column=0, sticky="new", padx=(0, 16))
        direita = tk.Frame(corpo, bg=t.BG)
        direita.grid(row=0, column=1, sticky="new")
        self._montar_cracha(esquerda)
        self._montar_sessao(esquerda)
        self._montar_modulo1(direita)
        self._montar_modulo2(direita)
        self._montar_modulo3(direita)
        tk.Frame(p, bg=t.BG, height=28).pack()

    def _cartao(self, pai, bg=None):
        return tk.Frame(pai, bg=bg or t.SURFACE, highlightthickness=1, highlightbackground=t.BORDER)

    def _montar_cabecalho(self, p):
        cartao = self._cartao(p)
        cartao.pack(fill="x", padx=MARGEM, pady=(18, 0))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=20, pady=16)
        interno.pack(fill="x")
        esquerda = tk.Frame(interno, bg=t.SURFACE)
        esquerda.pack(side="left", fill="x", expand=True)
        linha = tk.Frame(esquerda, bg=t.SURFACE)
        linha.pack(anchor="w")
        tk.Label(linha, text="GABINETE DE REDAÇÃO", fg="#FFFFFF", bg=t.PRIMARY, padx=6, pady=1,
                 font=t.Fontes.corpo(8, "bold")).pack(side="left")
        self.rotulo_prontuario = tk.Label(linha, text="", fg=t.TEXT_MUTED, bg=t.SURFACE,
                                          font=t.Fontes.corpo(8, "bold"))
        self.rotulo_prontuario.pack(side="left", padx=8)
        tk.Label(esquerda, text="Registro Funcional & Perfil do Editor", fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.display(26)).pack(fill="x", pady=(4, 2))
        tk.Label(esquerda, text="Gestão de credenciais de acesso, dados biográficos e preferências de segurança "
                                "da Gazeta. Todas as alterações ficam registradas com o nome de quem as fez.",
                 fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left", wraplength=760,
                 font=t.Fontes.corpo(10)).pack(fill="x")
        self.selo_2fa = tk.Label(interno, text="", fg=t.TEXT, bg=PAINEL, padx=10, pady=6,
                                 font=t.Fontes.corpo(8, "bold"))
        self.selo_2fa.pack(side="right", anchor="s")

    # ---------- crachá ----------
    def _montar_cracha(self, pai):
        cartao = self._cartao(pai)
        cartao.pack(fill="x")
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=12, pady=12)
        interno.pack(fill="x")
        self.moldura_foto = tk.Frame(interno, bg=t.TEXT, width=280, height=300)
        self.moldura_foto.pack()
        self.moldura_foto.pack_propagate(False)
        self.foto_label = tk.Label(self.moldura_foto, bg=t.TEXT, fg="#FFFFFF", font=t.Fontes.display(72))
        self.foto_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.legenda_foto = tk.Label(self.moldura_foto, text="", fg="#FFFFFF", bg="#2B2A25", justify="left",
                                     anchor="w", padx=10, pady=6, font=t.Fontes.corpo(7, "bold"))
        self.legenda_foto.place(relx=0, rely=1.0, relwidth=1, anchor="sw")
        acoes = tk.Frame(interno, bg=t.SURFACE)
        acoes.pack(fill="x", pady=(8, 0))
        _link(acoes, "TROCAR FOTO", self._trocar_foto, t.PRIMARY).pack(side="left")
        self.link_remover_foto = _link(acoes, "REMOVER", self._remover_foto, t.ERROR)

        status = tk.Frame(cartao, bg=PAINEL, padx=12, pady=6)
        status.pack(fill="x")
        tk.Label(status, text="CREDENCIAMENTO ATIVO", fg=t.TEXT, bg=PAINEL, font=t.Fontes.corpo(7, "bold")).pack(side="left")
        tk.Label(status, text="●", fg=t.PRIMARY, bg=PAINEL, font=t.Fontes.corpo(8)).pack(side="right")

        dados = tk.Frame(cartao, bg=t.SURFACE, padx=14, pady=12)
        dados.pack(fill="x")
        self.rotulo_nome = tk.Label(dados, text="", fg=t.TEXT, bg=t.SURFACE, anchor="w", justify="left",
                                    wraplength=280, font=t.Fontes.display(22))
        self.rotulo_nome.pack(fill="x")
        self.rotulo_cargo = tk.Label(dados, text="", fg=t.PRIMARY, bg=t.SURFACE, anchor="w", justify="left",
                                     wraplength=280, font=t.Fontes.display(13, "normal", True))
        self.rotulo_cargo.pack(fill="x", pady=(2, 10))
        self.linhas_info = {}
        tabela = tk.Frame(dados, bg=t.SURFACE)
        tabela.pack(fill="x")
        tabela.grid_columnconfigure(1, weight=1)
        for indice, (chave, rotulo) in enumerate((("matricula", "MATRÍCULA"), ("registro", "REGISTRO PROFISSIONAL (MTB)"),
                                                  ("conselho", "CONSELHO EDITORIAL"), ("mesa", "MESA DE OPERAÇÃO"))):
            fundo = PAINEL_BAIXO
            tk.Label(tabela, text=rotulo, fg=t.TEXT, bg=fundo, anchor="w", padx=8, pady=5,
                     font=t.Fontes.corpo(7, "bold")).grid(row=indice, column=0, sticky="ew", pady=1)
            valor = tk.Label(tabela, text="—", fg=t.TEXT, bg=fundo, anchor="e", padx=8, pady=5, wraplength=150,
                             justify="right", font=t.Fontes.corpo(8))
            valor.grid(row=indice, column=1, sticky="ew", pady=1)
            self.linhas_info[chave] = valor
        tk.Label(dados, text="NOTA BIOGRÁFICA DOS ARQUIVOS", fg=t.TEXT, bg=t.SURFACE, anchor="w",
                 font=t.Fontes.corpo(7, "bold")).pack(fill="x", pady=(12, 2))
        self.rotulo_nota = tk.Label(dados, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left",
                                    wraplength=280, font=t.Fontes.corpo(8))
        self.rotulo_nota.pack(fill="x")

        numeros = tk.Frame(cartao, bg=PAINEL_ALTO, padx=14, pady=10)
        numeros.pack(fill="x")
        self.numeros = {}
        for chave, rotulo in (("fechamento", "ÚLTIMO FECHAMENTO IMPRESSO"), ("acervo", "MATÉRIAS NO ACERVO")):
            linha = tk.Frame(numeros, bg=PAINEL_ALTO)
            linha.pack(fill="x", pady=1)
            tk.Label(linha, text=rotulo, fg=t.TEXT, bg=PAINEL_ALTO, font=t.Fontes.corpo(7, "bold")).pack(side="left")
            valor = tk.Label(linha, text="—", fg=t.TEXT, bg=PAINEL_ALTO, font=t.Fontes.corpo(8, "bold"))
            valor.pack(side="right")
            self.numeros[chave] = valor

    def _montar_sessao(self, pai):
        cartao = self._cartao(pai)
        cartao.pack(fill="x", pady=(16, 0))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=14, pady=12)
        interno.pack(fill="x")
        tk.Label(interno, text="SESSÃO DA REDAÇÃO", fg=t.TEXT, bg=t.SURFACE, font=t.Fontes.corpo(8, "bold")).pack(anchor="w")
        tk.Label(interno, text="A desconexão manual invalida as chaves de estampa deste terminal e volta para o login.",
                 fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left", wraplength=280,
                 font=t.Fontes.corpo(8)).pack(fill="x", pady=(2, 8))
        t.botao_secundario(interno, "SAIR DO SISTEMA / DESCONECTAR TERMINAL",
                           lambda: self.ao_sair() if self.ao_sair else None).pack(fill="x")

    # ---------- módulos ----------
    def _cabecalho_modulo(self, pai, rotulo, titulo, descricao):
        tk.Label(pai, text=rotulo, fg=t.PRIMARY, bg=t.SURFACE, anchor="w", font=t.Fontes.corpo(8, "bold")).pack(fill="x")
        tk.Label(pai, text=titulo, fg=t.TEXT, bg=t.SURFACE, anchor="w", font=t.Fontes.display(20)).pack(fill="x", pady=(2, 4))
        tk.Label(pai, text=descricao, fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left", wraplength=640,
                 font=t.Fontes.corpo(10)).pack(fill="x", pady=(0, 10))

    def _montar_modulo1(self, pai):
        cartao = self._cartao(pai)
        cartao.pack(fill="x")
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=22, pady=18)
        interno.pack(fill="x")
        self._cabecalho_modulo(interno, "MÓDULO 01 • CADASTRO DE EXPEDIENTE", "Informações Básicas do Jornalista",
                               "Estas referências são replicadas no cabeçalho do expediente impresso diário e nas "
                               "assinaturas padronizadas das agências de notícias conveniadas.")
        grade = tk.Frame(interno, bg=t.SURFACE)
        grade.pack(fill="x")
        grade.grid_columnconfigure(0, weight=1, uniform="perfil")
        grade.grid_columnconfigure(1, weight=1, uniform="perfil")
        self.campos = {}
        especificacao = [("nome", "NOME COMPLETO CIVIL *", 0, 0, 1), ("byline", "NOME EM ASSINATURA DE GALÉ (BYLINE)", 0, 1, 1),
                         ("email", "E-MAIL INSTITUCIONAL 🔒", 1, 0, 1), ("telefone", "RAMAL DIRETO DA REDAÇÃO CENTRAL", 1, 1, 1),
                         ("cargo", "CARGO / TÍTULO NO EXPEDIENTE", 2, 0, 1), ("matricula", "MATRÍCULA", 2, 1, 1),
                         ("registro", "REGISTRO PROFISSIONAL (MTB)", 3, 0, 1), ("conselho", "CONSELHO EDITORIAL", 3, 1, 1),
                         ("mesa", "MESA DE OPERAÇÃO", 4, 0, 2)]
        for chave, rotulo, linha, coluna, span in especificacao:
            campo = t.CampoEditorial(grade, rotulo)
            campo.grid(row=linha, column=coluna, columnspan=span, sticky="ew", padx=(0 if coluna == 0 else 8, 8 if coluna == 0 and span == 1 else 0), pady=5)
            self.campos[chave] = campo
        self.campos["email"].entry.configure(state="readonly")
        self.campo_atribuicao = CampoTextoLongo(interno, "ATRIBUIÇÃO REGIMENTAL", 3)
        self.campo_atribuicao.pack(fill="x", pady=(6, 0))
        self.campo_nota = CampoTextoLongo(interno, "NOTA BIOGRÁFICA DOS ARQUIVOS", 3)
        self.campo_nota.pack(fill="x", pady=(8, 0))
        rodape = tk.Frame(interno, bg=t.SURFACE)
        rodape.pack(fill="x", pady=(12, 0))
        self.rotulo_alterado = tk.Label(rodape, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(8, "bold"))
        self.rotulo_alterado.pack(side="left")
        t.botao_secundario(rodape, "SALVAR DADOS BIOGRÁFICOS", self._salvar_dados).pack(side="right")

    def _montar_modulo2(self, pai):
        cartao = self._cartao(pai)
        cartao.pack(fill="x", pady=(16, 0))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=22, pady=18)
        interno.pack(fill="x")
        self._cabecalho_modulo(interno, "MÓDULO 02 • AUTENTICAÇÃO E PROTOCOLO", "Segurança & Alteração de Senha",
                               "A alteração da senha mestre vale para os próximos acessos deste e de outros terminais. "
                               "Contas que entram pelo Google não têm senha própria.")
        self.campo_senha_atual = t.CampoEditorial(interno, "SENHA ATUAL DO TERMINAL", mostrar="*")
        self.campo_senha_atual.pack(fill="x", pady=(0, 6))
        duplas = tk.Frame(interno, bg=t.SURFACE)
        duplas.pack(fill="x")
        duplas.grid_columnconfigure(0, weight=1, uniform="senha")
        duplas.grid_columnconfigure(1, weight=1, uniform="senha")
        self.campo_senha_nova = t.CampoEditorial(duplas, "NOVA SENHA FORTE", mostrar="*")
        self.campo_senha_nova.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=4)
        self.campo_senha_confirma = t.CampoEditorial(duplas, "CONFIRMAR NOVA SENHA", mostrar="*")
        self.campo_senha_confirma.grid(row=0, column=1, sticky="ew", pady=4)
        for campo in (self.campo_senha_atual, self.campo_senha_nova, self.campo_senha_confirma):
            campo.entry.bind("<KeyRelease>", lambda e: self._atualizar_regras())
        self.caixa_regras = tk.Frame(interno, bg=PAINEL_BAIXO, padx=12, pady=10)
        self.caixa_regras.pack(fill="x", pady=(8, 0))
        tk.Label(self.caixa_regras, text="REGRAS MANDATÓRIAS DE COMPLEXIDADE TIPOGRÁFICA:", fg=t.TEXT,
                 bg=PAINEL_BAIXO, font=t.Fontes.corpo(7, "bold")).pack(anchor="w")
        self.area_regras = tk.Frame(self.caixa_regras, bg=PAINEL_BAIXO)
        self.area_regras.pack(fill="x", pady=(4, 0))
        self.nota_senha = tk.Label(interno, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left",
                                   wraplength=640, font=t.Fontes.corpo(9))
        rodape = tk.Frame(interno, bg=t.SURFACE)
        rodape.pack(fill="x", pady=(12, 0))
        self.rotulo_2fa = tk.Label(rodape, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(8, "bold"))
        self.rotulo_2fa.pack(side="left")
        self.botao_senha = t.botao_primario(rodape, "Atualizar senha & credenciais", self._alterar_senha)
        self.botao_senha.pack(side="right")
        self.botao_2fa = t.botao_secundario(rodape, "ATIVAR 2FA", self._alternar_2fa)
        self.botao_2fa.pack(side="right", padx=(0, 8))
        self._atualizar_regras()

    def _montar_modulo3(self, pai):
        cartao = self._cartao(pai)
        cartao.pack(fill="x", pady=(16, 0))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=22, pady=18)
        interno.pack(fill="x")
        self._cabecalho_modulo(interno, "MÓDULO 03 • PARÂMETROS DE TRABALHO", "Preferências do Terminal de Notícias",
                               "Configure a experiência do terminal para plantões de cobertura ao vivo e recepção de "
                               "furos jornalísticos. Cada operador tem as suas preferências.")
        for chave, (titulo, descricao) in ROTULOS_PREFERENCIA.items():
            linha = tk.Frame(interno, bg=t.SURFACE)
            linha.pack(fill="x")
            texto = tk.Frame(linha, bg=t.SURFACE)
            texto.pack(side="left", fill="x", expand=True, pady=10)
            tk.Label(texto, text=titulo, fg=t.TEXT, bg=t.SURFACE, anchor="w", font=t.Fontes.display(14)).pack(fill="x")
            tk.Label(texto, text=descricao, fg=t.TEXT_MUTED, bg=t.SURFACE, anchor="w", justify="left",
                     wraplength=560, font=t.Fontes.corpo(8)).pack(fill="x")
            if chave == "email_urgencia" and not self._email_configurado():
                tk.Label(texto, text="Envio de e-mail não configurado neste computador (config/email_config.json).",
                         fg=t.ERROR, bg=t.SURFACE, anchor="w", font=t.Fontes.corpo(8, "bold")).pack(fill="x")
            interruptor = Interruptor(linha)
            interruptor.pack(side="right")
            self.interruptores[chave] = interruptor
            tk.Frame(interno, bg=t.BORDER, height=1).pack(fill="x")
        rodape = tk.Frame(interno, bg=t.SURFACE)
        rodape.pack(fill="x", pady=(14, 0))
        t.botao_secundario(rodape, "PRESERVAR PREFERÊNCIAS DO OPERADOR", self._salvar_preferencias).pack(side="right")

    @staticmethod
    def _email_configurado() -> bool:
        try:
            from .auth import EmailSender
            return bool(EmailSender.configuracao_disponivel())
        except Exception:
            return False

    # =====================================================================
    # Dados
    # =====================================================================
    def recarregar(self):
        resultado = self.servico.obter(self.usuario.get("id"))
        if not resultado.ok:
            messagebox.showerror("Perfil", resultado.mensagem)
            return
        self.perfil = resultado.dados
        self._preencher(self.perfil)
        preferencias = self.servico.preferencias(self.usuario["id"])
        for chave, interruptor in self.interruptores.items():
            interruptor.set(preferencias.get(chave, False))

    def _preencher(self, p):
        self.rotulo_prontuario.configure(text=f"PRONTUÁRIO NO. {p['prontuario']}")
        for chave, campo in self.campos.items():
            campo.set(p.get(chave) or "")
        self.campo_atribuicao.set(p.get("atribuicao") or "")
        self.campo_nota.set(p.get("nota_biografica") or "")
        quando = p.get("atualizado_em")
        quando = interpretar_data(quando) if isinstance(quando, str) else quando
        data = quando.strftime("%d/%m/%Y") if hasattr(quando, "strftime") else ""
        self.rotulo_alterado.configure(
            text=(f"↺ ALTERADO POR {(p.get('atualizado_por') or 'DESCONHECIDO').upper()} EM {data}" if data
                  else "↺ NENHUMA ALTERAÇÃO REGISTRADA"))
        # crachá
        self.rotulo_nome.configure(text=p["nome"])
        self.rotulo_cargo.configure(text=p.get("cargo") or "Jornalista da redação")
        for chave in ("matricula", "registro", "conselho", "mesa"):
            self.linhas_info[chave].configure(text=p.get(chave) or "—")
        self.rotulo_nota.configure(text=p.get("nota_biografica") or "Sem nota biográfica cadastrada.")
        ultimo = p.get("ultimo_fechamento")
        ultimo = interpretar_data(ultimo) if isinstance(ultimo, str) else ultimo
        self.numeros["fechamento"].configure(
            text=f"{ultimo:%d/%m/%Y, %H:%M}" if hasattr(ultimo, "strftime") else "—")
        self.numeros["acervo"].configure(text=f"{p['materias_publicadas']:,}".replace(",", ".") + " matérias")
        self._desenhar_foto(p)
        self._atualizar_seguranca(p)

    def _desenhar_foto(self, p):
        foto = midia_global.carregar_tk(p.get("foto"), 280, 300)
        if foto is not None:
            self.foto_label.configure(image=foto, text="")
            self.foto_label.image = foto
            self.link_remover_foto.pack(side="left", padx=(12, 0))
        else:
            self.foto_label.configure(image="", text=(p["nome"][:1] or "?").upper())
            self.foto_label.image = None
            self.link_remover_foto.pack_forget()
        self.legenda_foto.configure(text=f"PASSE DE IMPRENSA OFICIAL\nMATRÍCULA: {p.get('matricula') or '—'}")

    def _atualizar_seguranca(self, p):
        ativo = bool(p.get("dois_fatores_ativo"))
        tem_senha = bool(p.get("tem_senha"))
        self.selo_2fa.configure(text=f"■  VERIFICAÇÃO EM DUAS ETAPAS: {'ATIVA' if ativo else 'INATIVA'}",
                                fg=t.PRIMARY if ativo else t.TEXT_MUTED)
        self.rotulo_2fa.configure(text=f"DISPOSITIVO 2FA VINCULADO: E-MAIL {mascarar_email(p.get('email'))}" if ativo
                                  else "VERIFICAÇÃO EM DUAS ETAPAS: DESATIVADA")
        self.botao_2fa.configure(text="DESATIVAR 2FA" if ativo else "ATIVAR 2FA")
        estado = "normal" if tem_senha else "disabled"
        for campo in (self.campo_senha_atual, self.campo_senha_nova, self.campo_senha_confirma):
            campo.entry.configure(state=estado)
        self.botao_senha.configure(state=estado)
        if tem_senha:
            self.nota_senha.pack_forget()
        else:
            self.nota_senha.configure(text="Esta conta entra pelo Google e não tem senha própria. "
                                           "Para criar uma, use \"Esqueci minha senha\" na tela de login.")
            self.nota_senha.pack(fill="x", pady=(8, 0), before=self.rotulo_2fa.master)
        self.usuario["dois_fatores_ativo"] = ativo

    def _atualizar_regras(self):
        for filho in self.area_regras.winfo_children():
            filho.destroy()
        nova = self.campo_senha_nova.get()
        for texto, cumprida in avaliar_senha(nova, self.campo_senha_atual.get(), self.campo_senha_confirma.get()
                                             if self.campo_senha_confirma.get() else None):
            tk.Label(self.area_regras, text=("✓  " if cumprida and nova else "○  ") + texto,
                     fg=t.SUCCESS if (cumprida and nova) else t.TEXT_MUTED, bg=PAINEL_BAIXO,
                     font=t.Fontes.corpo(8, "bold")).pack(side="left", padx=(0, 16))

    # =====================================================================
    # Ações
    # =====================================================================
    def _aplicar_ao_usuario(self, dados):
        if dados.get("nome"):
            self.usuario["nome"] = dados["nome"]
        if self.ao_perfil_alterado:
            self.ao_perfil_alterado()

    def _salvar_dados(self):
        dados = {c: self.campos[c].get() for c in self.campos if c != "email"}
        dados["atribuicao"] = self.campo_atribuicao.get()
        dados["nota_biografica"] = self.campo_nota.get()
        resultado = self.servico.salvar_dados(self.usuario["id"], dados)
        if not self._mostrar(resultado, "Perfil", sucesso_visivel=True):
            return
        self._aplicar_ao_usuario(resultado.dados)
        self.recarregar()

    def _trocar_foto(self):
        origem = filedialog.askopenfilename(title="Escolher foto do crachá", filetypes=TIPOS_ARQUIVO_DIALOGO)
        if not origem:
            return
        try:
            caminho = midia_global.importar(origem, "autores")
        except ErroMidia as erro:
            messagebox.showwarning("Foto", str(erro))
            return
        resultado = self.servico.salvar_foto(self.usuario["id"], caminho)
        if not resultado.ok:
            self.servico.descartar_imagem_orfa(caminho)
            messagebox.showwarning("Foto", resultado.mensagem)
            return
        self.recarregar()
        if self.ao_perfil_alterado:
            self.ao_perfil_alterado()

    def _remover_foto(self):
        if self.servico.salvar_foto(self.usuario["id"], None).ok:
            self.recarregar()

    def _alterar_senha(self):
        resultado = self.servico.alterar_senha(
            self.usuario["id"], self.campo_senha_atual.get(), self.campo_senha_nova.get(),
            self.campo_senha_confirma.get())
        if not self._mostrar(resultado, "Segurança", sucesso_visivel=True):
            return
        for campo in (self.campo_senha_atual, self.campo_senha_nova, self.campo_senha_confirma):
            campo.set("")
        self._atualizar_regras()
        if self.ao_perfil_alterado:
            self.ao_perfil_alterado()

    def _alternar_2fa(self):
        if self.perfil and self.perfil.get("dois_fatores_ativo"):
            if not messagebox.askyesno("Desativar verificação em duas etapas",
                                       "Tem certeza que deseja desativar a verificação em duas etapas por e-mail?"):
                return
            resultado = self.servico.desativar_dois_fatores(self.usuario["id"])
            if self._mostrar(resultado, "Segurança"):
                self.logger.info(f"2FA (e-mail) desativado para: {self.usuario.get('usuario')}")
                self.recarregar()
                if self.ao_perfil_alterado:
                    self.ao_perfil_alterado()
        elif self.abrir_2fa:
            self.abrir_2fa(self._depois_de_ativar_2fa)

    def _depois_de_ativar_2fa(self):
        self.servico.avisar_dois_fatores_ativado(self.usuario["id"])
        self.recarregar()
        if self.ao_perfil_alterado:
            self.ao_perfil_alterado()

    def _salvar_preferencias(self):
        valores = {c: i.get() for c, i in self.interruptores.items()}
        resultado = self.servico.salvar_preferencias(self.usuario["id"], valores)
        self._mostrar(resultado, "Preferências", sucesso_visivel=True)
        if self.ao_perfil_alterado:
            self.ao_perfil_alterado()
