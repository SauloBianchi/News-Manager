"""
gui.py
Interface gráfica do NewsManager, construída com Tkinter, seguindo o
layout editorial ("Broadsheet Editorial") do protótipo do Stitch.

Janelas:
- LoginWindow: autenticação com usuário/e-mail + senha, ou com o Google.
- CadastroWindow: criação de conta, com opção de ativar 2FA na hora.
- RecuperarSenhaWindow: fluxo de "esqueci minha senha" (código por e-mail).
- VerificacaoDoisFatoresDialog: pedido do código de 6 dígitos (enviado por
  e-mail) no login, quando o usuário tem 2FA ativado.
- ConfiguracaoDoisFatoresDialog: envia e confirma o código para ativar o 2FA.
- MainWindow: janela principal (cabeçalho com navegação; telas de notícias,
  categorias, autores, gráficos e segurança).
"""

import threading
import tkinter as tk
from tkinter import messagebox

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from .database import DatabaseManager
from .logger import Logger
from .auth import (
    PasswordHasher,
    EmailOTPManager,
    EmailSender,
    GoogleAuthManager,
    DependenciaAusente,
    ConfiguracaoEmailAusente,
)
from . import theme as t
from .telas_cadastros import CategoriasFrame, AutoresFrame, _cabecalho
from .tela_noticias import NoticiasFrame
from .shell import Cabecalho, AreaAbas, Rodape


# =============================================================================
# Auxiliares de login com Google, compartilhados entre Login e Cadastro
# =============================================================================
def _login_google_async(widget, callback):
    """Executa GoogleAuthManager.autenticar() numa thread separada (o fluxo
    OAuth é bloqueante: abre o navegador e sobe um servidor local) e agenda
    o retorno de volta na thread principal do Tkinter via .after()."""

    def tarefa():
        try:
            perfil = GoogleAuthManager.autenticar()
            widget.after(0, lambda: callback(perfil, None))
        except Exception as erro:
            widget.after(0, lambda: callback(None, erro))

    threading.Thread(target=tarefa, daemon=True).start()


def _tratar_erro_google(erro, logger):
    if isinstance(erro, DependenciaAusente):
        messagebox.showerror("Dependência ausente", str(erro))
    elif isinstance(erro, FileNotFoundError):
        messagebox.showerror("Google OAuth não configurado", str(erro))
    else:
        logger.error("Erro no login com Google", erro)
        messagebox.showerror("Erro", "Não foi possível concluir a autenticação com o Google.")


def _buscar_ou_criar_usuario_google(db, perfil):
    """Vincula a Conta Google a um cadastro existente com o mesmo e-mail,
    ou cria uma conta nova se for o primeiro acesso dessa pessoa."""
    usuario = db.buscar_usuario_por_google_id(perfil["google_id"])
    if usuario:
        return usuario
    usuario = db.buscar_usuario_por_email(perfil["email"])
    if usuario:
        db.vincular_google_id(usuario["id"], perfil["google_id"])
        return usuario
    return db.criar_usuario_google(perfil["nome"], perfil["email"], perfil["google_id"])


# =============================================================================
# Auxiliares de envio do código de verificação por e-mail (2FA)
# =============================================================================
def _gerar_e_enviar_codigo_async(widget, usuario, callback, titulo=None, texto_intro=None):
    """Gera o código de 6 dígitos e o envia por e-mail numa thread separada
    (evita travar a janela enquanto o SMTP responde). O callback recebe
    (codigo_hash, expira_em, erro) de volta na thread principal do Tkinter.

    `titulo`/`texto_intro`, quando informados, personalizam o texto do
    e-mail (por padrão é o de verificação em duas etapas); usados, por
    exemplo, no fluxo de "esqueci minha senha"."""

    def tarefa():
        codigo = EmailOTPManager.gerar_codigo()
        codigo_hash = EmailOTPManager.hash_codigo(codigo)
        expira_em = EmailOTPManager.calcular_expiracao()
        kwargs = {}
        if titulo is not None:
            kwargs["titulo"] = titulo
        if texto_intro is not None:
            kwargs["texto_intro"] = texto_intro
        try:
            EmailSender.enviar_codigo_verificacao(
                usuario["email"], usuario.get("nome", ""), codigo, **kwargs
            )
            widget.after(0, lambda: callback(codigo_hash, expira_em, None))
        except Exception as erro:
            widget.after(0, lambda erro=erro : callback(None, None, erro))

    threading.Thread(target=tarefa, daemon=True).start()


def _tratar_erro_email(erro, logger):
    if isinstance(erro, ConfiguracaoEmailAusente):
        messagebox.showerror("E-mail não configurado", str(erro))
    else:
        logger.error("Erro ao enviar e-mail de verificação", erro)
        messagebox.showerror(
            "Erro ao enviar e-mail",
            "Não foi possível enviar o código de verificação por e-mail. "
            "Verifique sua conexão e as credenciais SMTP configuradas.",
        )


# =============================================================================
# Janela: Login
# =============================================================================
class LoginWindow(tk.Tk):
    """Primeira janela da aplicação: autenticação do usuário."""

    def __init__(self, db: DatabaseManager, logger: Logger):
        super().__init__()
        self.db = db
        self.logger = logger
        t.Fontes.preparar(self)

        self.title("NewsManager — Terminal da Redação")
        self.configure(bg=t.BG)
        self.geometry("480x660")
        self.minsize(440, 620)

        self._montar_layout()

    # ---------- Layout ----------
    def _montar_layout(self):
        wrapper = tk.Frame(self, bg=t.BG)
        wrapper.pack(expand=True, fill="both", padx=24, pady=32)

        cartao = tk.Frame(wrapper, bg=t.SURFACE, highlightbackground=t.BORDER, highlightthickness=1)
        cartao.pack(fill="x")

        t.double_rule(cartao, bg=t.SURFACE).pack(fill="x")

        interno = tk.Frame(cartao, bg=t.SURFACE, padx=28, pady=24)
        interno.pack(fill="x")

        topo = tk.Frame(interno, bg=t.SURFACE)
        topo.pack(fill="x")
        tk.Label(topo, text="EDIÇÃO DIÁRIA", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(9, "bold")).pack(side="left")
        tk.Label(topo, text="TERMINAL SEGURO", fg=t.TEXT_MUTED, bg=t.SURFACE,
                 font=t.Fontes.corpo(9)).pack(side="right")

        tk.Label(interno, text="NewsManager", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(30)).pack(pady=(10, 0))
        tk.Label(interno, text="TERMINAL DA REDAÇÃO & GESTÃO EDITORIAL", fg=t.TEXT_MUTED,
                 bg=t.SURFACE, font=t.Fontes.corpo(9, "bold")).pack(pady=(2, 18))

        self.campo_login = t.CampoEditorial(interno, "USUÁRIO OU E-MAIL")
        self.campo_login.pack(fill="x", pady=8)

        self.campo_senha = t.CampoEditorial(interno, "SENHA", mostrar="*")
        self.campo_senha.pack(fill="x", pady=8)
        self.campo_senha.entry.bind("<Return>", lambda e: self._entrar())

        linha_esqueceu = tk.Frame(interno, bg=t.SURFACE)
        linha_esqueceu.pack(fill="x")
        t.link_texto(linha_esqueceu, "Esqueceu a senha?", self._abrir_recuperar_senha).pack(side="right")

        t.botao_primario(interno, "Entrar no sistema", self._entrar).pack(fill="x", pady=(18, 10))

        divisor = tk.Frame(interno, bg=t.SURFACE)
        divisor.pack(fill="x", pady=6)
        tk.Frame(divisor, bg=t.BORDER, height=1).pack(side="left", fill="x", expand=True)
        tk.Label(divisor, text="  ou  ", bg=t.SURFACE, fg=t.TEXT_MUTED,
                 font=t.Fontes.corpo(9)).pack(side="left")
        tk.Frame(divisor, bg=t.BORDER, height=1).pack(side="left", fill="x", expand=True)

        self.botao_google_w = t.botao_google(interno, "Entrar com o Google", self._entrar_com_google)
        self.botao_google_w.pack(fill="x", pady=(10, 4))

        rodape = tk.Frame(interno, bg=t.SURFACE)
        rodape.pack(fill="x", pady=(18, 0))
        tk.Label(rodape, text="Ainda não tem conta?", bg=t.SURFACE, fg=t.TEXT_MUTED,
                 font=t.Fontes.corpo(10)).pack(side="left")
        t.link_texto(rodape, " Criar conta", self._abrir_cadastro).pack(side="left")

        t.double_rule(cartao, bg=t.SURFACE).pack(fill="x", side="bottom")

        tk.Label(wrapper, text="NEWSMANAGER • GAZETA EDITORIAL CORP", bg=t.BG,
                 fg=t.TEXT_MUTED, font=t.Fontes.corpo(8, "bold")).pack(pady=(14, 0))

    # ---------- Login tradicional ----------
    def _entrar(self):
        identificador = self.campo_login.get()
        senha = self.campo_senha.get()

        if not identificador or not senha:
            messagebox.showwarning("Atenção", "Preencha usuário/e-mail e senha.")
            return

        if not self.db.connection and not self.db.conectar():
            messagebox.showerror("Erro", "Não foi possível conectar ao banco de dados.")
            return

        try:
            usuario = self.db.buscar_usuario_por_identificador(identificador)
            if not usuario or not usuario.get("senha_hash"):
                self.logger.warning(f"Tentativa de login inválida: {identificador}")
                messagebox.showerror("Erro", "Usuário ou senha inválidos.")
                return

            if not PasswordHasher.verificar(senha, usuario["senha_hash"]):
                self.logger.warning(f"Senha incorreta para: {identificador}")
                messagebox.showerror("Erro", "Usuário ou senha inválidos.")
                return

            self._concluir_autenticacao(usuario)
        except DependenciaAusente as e:
            messagebox.showerror("Dependência ausente", str(e))
        except Exception as e:
            self.logger.error("Erro durante autenticação", e)
            messagebox.showerror("Erro", "Ocorreu um erro ao autenticar.")

    def _concluir_autenticacao(self, usuario):
        """Depois de validar usuário/senha, cobra o código 2FA se estiver ativo."""
        if usuario.get("dois_fatores_ativo"):
            VerificacaoDoisFatoresDialog(self, self.db, self.logger, usuario, self._entrar_na_aplicacao)
        else:
            self._entrar_na_aplicacao(usuario)

    def _entrar_na_aplicacao(self, usuario):
        self.db.atualizar_ultimo_login(usuario["id"])
        self.logger.info(f"Login bem-sucedido: {usuario['usuario']}")
        self.destroy()
        app = MainWindow(self.db, self.logger, usuario)
        app.mainloop()

    # ---------- Login com Google ----------
    def _entrar_com_google(self):
        self.botao_google_w.configure(state="disabled", text="Conectando ao Google…")
        _login_google_async(self, self._pos_login_google)

    def _pos_login_google(self, perfil, erro):
        self.botao_google_w.configure(state="normal", text="G   Entrar com o Google")

        if erro is not None:
            _tratar_erro_google(erro, self.logger)
            return

        if not self.db.connection and not self.db.conectar():
            messagebox.showerror("Erro", "Não foi possível conectar ao banco de dados.")
            return

        try:
            usuario = _buscar_ou_criar_usuario_google(self.db, perfil)
            self.logger.info(f"Login via Google: {perfil['email']}")
            # O login social já prova a identidade através da própria Conta
            # Google, então o 2FA do NewsManager não é cobrado de novo aqui.
            self._entrar_na_aplicacao(usuario)
        except Exception as e:
            self.logger.error("Erro ao concluir login com Google", e)
            messagebox.showerror("Erro", "Não foi possível concluir o login com o Google.")

    # ---------- Navegação ----------
    def _abrir_cadastro(self):
        self.withdraw()
        CadastroWindow(self, self.db, self.logger)

    def _abrir_recuperar_senha(self):
        self.withdraw()
        RecuperarSenhaWindow(self, self.db, self.logger)


# =============================================================================
# Janela: Cadastro
# =============================================================================
class CadastroWindow(tk.Toplevel):
    """Ficha de cadastro de uma nova credencial de acesso."""

    def __init__(self, login_window: LoginWindow, db: DatabaseManager, logger: Logger):
        super().__init__(login_window)
        self.login_window = login_window
        self.db = db
        self.logger = logger
        t.Fontes.preparar(self)

        self.title("NewsManager — Nova Credencial")
        self.configure(bg=t.BG)
        self.geometry("480x780")
        self.minsize(440, 720)
        self.protocol("WM_DELETE_WINDOW", self._voltar_ao_login)

        self._montar_layout()

    def _montar_layout(self):
        wrapper = tk.Frame(self, bg=t.BG)
        wrapper.pack(expand=True, fill="both", padx=24, pady=28)

        cartao = tk.Frame(wrapper, bg=t.SURFACE, highlightbackground=t.BORDER, highlightthickness=1)
        cartao.pack(fill="both", expand=True)
        t.double_rule(cartao, bg=t.SURFACE).pack(fill="x")

        interno = tk.Frame(cartao, bg=t.SURFACE, padx=28, pady=22)
        interno.pack(fill="both", expand=True)

        tk.Label(interno, text="FICHA DE CADASTRO", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(9, "bold")).pack(anchor="w")
        tk.Label(interno, text="Nova Credencial de Acesso", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(22)).pack(anchor="w", pady=(2, 14))

        self.campo_nome = t.CampoEditorial(interno, "NOME COMPLETO")
        self.campo_nome.pack(fill="x", pady=6)

        self.campo_email = t.CampoEditorial(interno, "E-MAIL")
        self.campo_email.pack(fill="x", pady=6)

        self.campo_usuario = t.CampoEditorial(interno, "USUÁRIO", dica="MATRÍCULA OU APELIDO")
        self.campo_usuario.pack(fill="x", pady=6)

        self.campo_senha = t.CampoEditorial(interno, "SENHA", mostrar="*")
        self.campo_senha.pack(fill="x", pady=6)

        self.campo_confirmar = t.CampoEditorial(interno, "CONFIRMAR SENHA", mostrar="*")
        self.campo_confirmar.pack(fill="x", pady=6)
        self.campo_confirmar.entry.bind("<Return>", lambda e: self._criar_conta())

        self.var_2fa = tk.BooleanVar(value=True)
        tk.Checkbutton(
            interno, text="Ativar verificação em duas etapas por e-mail (recomendado)",
            variable=self.var_2fa, bg=t.SURFACE, fg=t.TEXT, font=t.Fontes.corpo(10),
            activebackground=t.SURFACE, selectcolor=t.SURFACE,
        ).pack(anchor="w", pady=(10, 4))

        t.botao_primario(interno, "Criar conta", self._criar_conta).pack(fill="x", pady=(10, 8))

        divisor = tk.Frame(interno, bg=t.SURFACE)
        divisor.pack(fill="x", pady=6)
        tk.Frame(divisor, bg=t.BORDER, height=1).pack(side="left", fill="x", expand=True)
        tk.Label(divisor, text="  ou  ", bg=t.SURFACE, fg=t.TEXT_MUTED,
                 font=t.Fontes.corpo(9)).pack(side="left")
        tk.Frame(divisor, bg=t.BORDER, height=1).pack(side="left", fill="x", expand=True)

        self.botao_google_w = t.botao_google(interno, "Cadastrar com o Google", self._cadastrar_com_google)
        self.botao_google_w.pack(fill="x", pady=(6, 4))

        rodape = tk.Frame(interno, bg=t.SURFACE)
        rodape.pack(fill="x", pady=(16, 0))
        tk.Label(rodape, text="Já tem uma credencial?", bg=t.SURFACE, fg=t.TEXT_MUTED,
                 font=t.Fontes.corpo(10)).pack(side="left")
        t.link_texto(rodape, " Entrar", self._voltar_ao_login).pack(side="left")

    # ---------- Navegação ----------
    def _voltar_ao_login(self):
        self.destroy()
        self.login_window.deiconify()

    # ---------- Cadastro tradicional ----------
    def _validar_campos(self):
        nome = self.campo_nome.get()
        email = self.campo_email.get()
        usuario = self.campo_usuario.get()
        senha = self.campo_senha.get()
        confirmar = self.campo_confirmar.get()

        if not all([nome, email, usuario, senha, confirmar]):
            messagebox.showwarning("Atenção", "Preencha todos os campos.")
            return None
        if "@" not in email or "." not in email.split("@")[-1]:
            messagebox.showwarning("Atenção", "Informe um e-mail válido.")
            return None
        if len(senha) < 8:
            messagebox.showwarning("Atenção", "A senha deve ter ao menos 8 caracteres.")
            return None
        if senha != confirmar:
            messagebox.showwarning("Atenção", "As senhas não coincidem.")
            return None
        return nome, email, usuario, senha

    def _criar_conta(self):
        dados = self._validar_campos()
        if not dados:
            return
        nome, email, usuario, senha = dados

        if not self.db.connection and not self.db.conectar():
            messagebox.showerror("Erro", "Não foi possível conectar ao banco de dados.")
            return

        try:
            if self.db.usuario_ou_email_em_uso(usuario, email):
                messagebox.showerror("Erro", "Já existe uma conta com esse usuário ou e-mail.")
                return

            senha_hash = PasswordHasher.gerar_hash(senha)
            usuario_criado = self.db.criar_usuario(nome, usuario, email, senha_hash)
            self.logger.info(f"Conta criada: {usuario}")

            if self.var_2fa.get():
                ConfiguracaoDoisFatoresDialog(
                    self, self.db, self.logger, usuario_criado, self._voltar_ao_login
                )
            else:
                messagebox.showinfo("Conta criada", "Sua conta foi criada. Faça login para continuar.")
                self._voltar_ao_login()
        except DependenciaAusente as e:
            messagebox.showerror("Dependência ausente", str(e))
        except Exception as e:
            self.logger.error("Erro ao criar conta", e)
            messagebox.showerror("Erro", "Não foi possível criar a conta.")

    # ---------- Cadastro com Google ----------
    def _cadastrar_com_google(self):
        self.botao_google_w.configure(state="disabled", text="Conectando ao Google…")
        _login_google_async(self, self._pos_cadastro_google)

    def _pos_cadastro_google(self, perfil, erro):
        self.botao_google_w.configure(state="normal", text="G   Cadastrar com o Google")

        if erro is not None:
            _tratar_erro_google(erro, self.logger)
            return

        if not self.db.connection and not self.db.conectar():
            messagebox.showerror("Erro", "Não foi possível conectar ao banco de dados.")
            return

        try:
            usuario = _buscar_ou_criar_usuario_google(self.db, perfil)
            self.db.atualizar_ultimo_login(usuario["id"])
            self.logger.info(f"Cadastro/login via Google: {perfil['email']}")
            self.destroy()
            self.login_window.destroy()
            app = MainWindow(self.db, self.logger, usuario)
            app.mainloop()
        except Exception as e:
            self.logger.error("Erro ao concluir cadastro com Google", e)
            messagebox.showerror("Erro", "Não foi possível concluir o cadastro com o Google.")


# =============================================================================
# Janela: Recuperar Senha ("esqueci minha senha")
# =============================================================================
class RecuperarSenhaWindow(tk.Toplevel):
    """Fluxo de 'esqueci minha senha': confirma a identidade com um código
    de 6 dígitos enviado por e-mail e permite definir uma senha nova.
    Reaproveita a mesma infraestrutura de código do 2FA (EmailOTPManager /
    EmailSender e as colunas codigo_verificacao / codigo_expira_em)."""

    def __init__(self, login_window: LoginWindow, db: DatabaseManager, logger: Logger):
        super().__init__(login_window)
        self.login_window = login_window
        self.db = db
        self.logger = logger
        self.usuario = None
        self._codigo_hash = None
        self._codigo_expira_em = None
        self._enviando = False
        t.Fontes.preparar(self)

        self.title("NewsManager — Recuperar Senha")
        self.configure(bg=t.BG)
        self.geometry("480x640")
        self.minsize(440, 600)
        # Não usar transient(login_window): o login está com withdraw() e,
        # no Tk, uma janela transient herda a visibilidade do mestre (fica oculta).
        self.protocol("WM_DELETE_WINDOW", self._voltar_ao_login)

        self._montar_layout()

    def _montar_layout(self):
        wrapper = tk.Frame(self, bg=t.BG)
        wrapper.pack(expand=True, fill="both", padx=24, pady=28)

        cartao = tk.Frame(wrapper, bg=t.SURFACE, highlightbackground=t.BORDER, highlightthickness=1)
        cartao.pack(fill="both", expand=True)
        t.double_rule(cartao, bg=t.SURFACE).pack(fill="x")

        self.interno = tk.Frame(cartao, bg=t.SURFACE, padx=28, pady=22)
        self.interno.pack(fill="both", expand=True)

        tk.Label(self.interno, text="RECUPERAÇÃO DE ACESSO", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(9, "bold")).pack(anchor="w")
        tk.Label(self.interno, text="Esqueceu sua senha?", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(20)).pack(anchor="w", pady=(2, 14))

        # As duas etapas ficam em frames próprios; só um deles fica visível
        # (pack/pack_forget) de cada vez.
        self.etapa_identificacao = tk.Frame(self.interno, bg=t.SURFACE)
        self.etapa_redefinicao = tk.Frame(self.interno, bg=t.SURFACE)
        self._montar_etapa_identificacao(self.etapa_identificacao)
        self._montar_etapa_redefinicao(self.etapa_redefinicao)
        self.etapa_identificacao.pack(fill="both", expand=True)

        rodape = tk.Frame(self.interno, bg=t.SURFACE)
        rodape.pack(fill="x", pady=(18, 0))
        t.link_texto(rodape, "Voltar para o login", self._voltar_ao_login).pack(side="left")

    # ---------- Etapa 1: identificar a conta ----------
    def _montar_etapa_identificacao(self, frame):
        tk.Label(
            frame,
            text=("Informe seu usuário ou e-mail. Vamos enviar um código de\n"
                  "verificação para você redefinir sua senha."),
            fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(10), justify="left",
        ).pack(anchor="w", pady=(0, 14))

        self.campo_identificador = t.CampoEditorial(frame, "USUÁRIO OU E-MAIL")
        self.campo_identificador.pack(fill="x", pady=6)
        self.campo_identificador.entry.bind("<Return>", lambda e: self._solicitar_codigo())

        self.botao_enviar = t.botao_primario(frame, "Enviar código", self._solicitar_codigo)
        self.botao_enviar.pack(fill="x", pady=(14, 0))

    def _solicitar_codigo(self):
        identificador = self.campo_identificador.get()
        if not identificador:
            messagebox.showwarning("Atenção", "Informe seu usuário ou e-mail.")
            return

        if not self.db.connection and not self.db.conectar():
            messagebox.showerror("Erro", "Não foi possível conectar ao banco de dados.")
            return

        usuario = self.db.buscar_usuario_por_identificador(identificador)
        if not usuario:
            messagebox.showerror("Não encontrado", "Não encontramos uma conta com esse usuário ou e-mail.")
            return
        if not usuario.get("senha_hash"):
            messagebox.showinfo(
                "Conta vinculada ao Google",
                "Essa conta faz login apenas com o Google — não existe senha para "
                "redefinir. Use o botão \"Entrar com o Google\".",
            )
            return

        self.usuario = usuario
        self.botao_enviar.configure(state="disabled", text="Enviando…")
        _gerar_e_enviar_codigo_async(
            self, self.usuario, self._apos_envio_codigo,
            titulo="Redefinição de Senha",
            texto_intro="Use o código abaixo para definir uma nova senha para sua conta.",
        )

    def _apos_envio_codigo(self, codigo_hash, expira_em, erro):
        self.botao_enviar.configure(state="normal", text="Enviar código")

        if erro is not None:
            _tratar_erro_email(erro, self.logger)
            return

        self.db.salvar_codigo_verificacao(self.usuario["id"], codigo_hash, expira_em)
        self._codigo_hash = codigo_hash
        self._codigo_expira_em = expira_em

        self.label_status_codigo.configure(
            text=(f"Enviamos um código de 6 dígitos para {self.usuario['email']}. "
                  f"Ele expira em {EmailOTPManager.VALIDADE_MINUTOS} minutos.")
        )
        self.etapa_identificacao.pack_forget()
        self.etapa_redefinicao.pack(fill="both", expand=True)
        self.campo_codigo.focus()

    # ---------- Etapa 2: código + nova senha ----------
    def _montar_etapa_redefinicao(self, frame):
        self.label_status_codigo = tk.Label(
            frame, text="", fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(10),
            justify="left", wraplength=360,
        )
        self.label_status_codigo.pack(anchor="w", pady=(0, 12))

        self.campo_codigo = t.CampoEditorial(frame, "CÓDIGO RECEBIDO POR E-MAIL")
        self.campo_codigo.pack(fill="x", pady=6)

        self.campo_nova_senha = t.CampoEditorial(frame, "NOVA SENHA", mostrar="*")
        self.campo_nova_senha.pack(fill="x", pady=6)

        self.campo_confirmar_senha = t.CampoEditorial(frame, "CONFIRMAR NOVA SENHA", mostrar="*")
        self.campo_confirmar_senha.pack(fill="x", pady=6)
        self.campo_confirmar_senha.entry.bind("<Return>", lambda e: self._redefinir_senha())

        self.botao_redefinir = t.botao_primario(frame, "Redefinir senha", self._redefinir_senha)
        self.botao_redefinir.pack(fill="x", pady=(14, 6))

        self.link_reenviar = t.link_texto(frame, "Reenviar código", self._reenviar_codigo)
        self.link_reenviar.pack(anchor="w")

    def _reenviar_codigo(self):
        if self._enviando or not self.usuario:
            return
        self._enviando = True
        self.link_reenviar.configure(fg=t.TEXT_MUTED)
        self.label_status_codigo.configure(text=f"Reenviando um código para {self.usuario['email']}…")
        _gerar_e_enviar_codigo_async(
            self, self.usuario, self._apos_reenvio_codigo,
            titulo="Redefinição de Senha",
            texto_intro="Use o código abaixo para definir uma nova senha para sua conta.",
        )

    def _apos_reenvio_codigo(self, codigo_hash, expira_em, erro):
        self._enviando = False
        self.link_reenviar.configure(fg=t.SECONDARY)

        if erro is not None:
            _tratar_erro_email(erro, self.logger)
            return

        self.db.salvar_codigo_verificacao(self.usuario["id"], codigo_hash, expira_em)
        self._codigo_hash = codigo_hash
        self._codigo_expira_em = expira_em
        self.label_status_codigo.configure(
            text=(f"Enviamos um novo código para {self.usuario['email']}. "
                  f"Ele expira em {EmailOTPManager.VALIDADE_MINUTOS} minutos.")
        )

    def _redefinir_senha(self):
        codigo = self.campo_codigo.get()
        nova_senha = self.campo_nova_senha.get()
        confirmar = self.campo_confirmar_senha.get()

        if not EmailOTPManager.validar_codigo(codigo, self._codigo_hash, self._codigo_expira_em):
            messagebox.showerror("Código inválido", "O código informado está incorreto ou expirou.")
            return
        if len(nova_senha) < 8:
            messagebox.showwarning("Atenção", "A nova senha deve ter ao menos 8 caracteres.")
            return
        if nova_senha != confirmar:
            messagebox.showwarning("Atenção", "As senhas não coincidem.")
            return

        try:
            nova_senha_hash = PasswordHasher.gerar_hash(nova_senha)
            self.db.redefinir_senha(self.usuario["id"], nova_senha_hash)
            self.logger.info(f"Senha redefinida para: {self.usuario['usuario']}")
            messagebox.showinfo("Senha redefinida", "Sua senha foi alterada. Faça login com a nova senha.")
            self._voltar_ao_login()
        except DependenciaAusente as e:
            messagebox.showerror("Dependência ausente", str(e))

    # ---------- Navegação ----------
    def _voltar_ao_login(self):
        self.destroy()
        self.login_window.deiconify()


# =============================================================================
# Diálogo: Verificação em Duas Etapas (login) — código por e-mail
# =============================================================================
class VerificacaoDoisFatoresDialog(tk.Toplevel):
    """Envia um código de 6 dígitos para o e-mail do usuário e pede que ele
    seja digitado, para contas com verificação em duas etapas ativada."""

    def __init__(self, parent, db, logger, usuario, ao_confirmar):
        super().__init__(parent)
        self.db = db
        self.logger = logger
        self.usuario = usuario
        self.ao_confirmar = ao_confirmar
        t.Fontes.preparar(self)

        self.title("Verificação em Duas Etapas")
        self.configure(bg=t.SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancelar)

        self._codigo_hash = None
        self._codigo_expira_em = None
        self._enviando = False

        interno = tk.Frame(self, bg=t.SURFACE, padx=26, pady=22)
        interno.pack(fill="both", expand=True)

        tk.Label(interno, text="VERIFICAÇÃO EM DUAS ETAPAS", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(9, "bold")).pack(anchor="w")
        tk.Label(interno, text="Confirme sua identidade", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(18)).pack(anchor="w", pady=(2, 6))

        self.label_status = tk.Label(
            interno, text=f"Enviando um código para {self.usuario['email']}…",
            fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(10), justify="left", wraplength=340,
        )
        self.label_status.pack(anchor="w", pady=(0, 14))

        self.campo_codigo = t.CampoEditorial(interno, "CÓDIGO RECEBIDO POR E-MAIL")
        self.campo_codigo.pack(fill="x")
        self.campo_codigo.entry.bind("<Return>", lambda e: self._confirmar())

        self.botao_confirmar = t.botao_primario(interno, "Confirmar", self._confirmar)
        self.botao_confirmar.pack(fill="x", pady=(16, 6))
        self.botao_confirmar.configure(state="disabled")

        linha_rodape = tk.Frame(interno, bg=t.SURFACE)
        linha_rodape.pack(fill="x")
        self.link_reenviar = t.link_texto(linha_rodape, "Reenviar código", self._reenviar)
        self.link_reenviar.pack(side="left")

        t.botao_secundario(interno, "Cancelar", self._cancelar).pack(fill="x", pady=(10, 0))

        self._enviar_codigo()

    def _enviar_codigo(self):
        if self._enviando:
            return
        self._enviando = True
        self.botao_confirmar.configure(state="disabled")
        self.link_reenviar.configure(fg=t.TEXT_MUTED)
        self.label_status.configure(text=f"Enviando um código para {self.usuario['email']}…")
        _gerar_e_enviar_codigo_async(self, self.usuario, self._apos_envio)

    def _apos_envio(self, codigo_hash, expira_em, erro):
        self._enviando = False
        self.link_reenviar.configure(fg=t.SECONDARY)

        if erro is not None:
            self.label_status.configure(
                text="Não foi possível enviar o e-mail. Tente novamente.", fg=t.ERROR
            )
            _tratar_erro_email(erro, self.logger)
            return

        self.db.salvar_codigo_verificacao(self.usuario["id"], codigo_hash, expira_em)
        self._codigo_hash = codigo_hash
        self._codigo_expira_em = expira_em
        self.label_status.configure(
            text=(f"Enviamos um código de 6 dígitos para {self.usuario['email']}. "
                  f"Ele expira em {EmailOTPManager.VALIDADE_MINUTOS} minutos."),
            fg=t.TEXT_MUTED,
        )
        self.botao_confirmar.configure(state="normal")
        self.campo_codigo.focus()

    def _reenviar(self):
        self._enviar_codigo()

    def _confirmar(self):
        codigo = self.campo_codigo.get()
        if EmailOTPManager.validar_codigo(codigo, self._codigo_hash, self._codigo_expira_em):
            self.db.limpar_codigo_verificacao(self.usuario["id"])
            self.destroy()
            self.ao_confirmar(self.usuario)
        else:
            messagebox.showerror("Código inválido", "O código informado está incorreto ou expirou.")

    def _cancelar(self):
        self.destroy()


# =============================================================================
# Diálogo: Configuração (ativação) do 2FA — código por e-mail
# =============================================================================
class ConfiguracaoDoisFatoresDialog(tk.Toplevel):
    """Envia um código de confirmação para o e-mail cadastrado e ativa a
    verificação em duas etapas assim que o código é confirmado."""

    def __init__(self, parent, db, logger, usuario, ao_concluir):
        super().__init__(parent)
        self.db = db
        self.logger = logger
        self.usuario = usuario
        self.ao_concluir = ao_concluir
        t.Fontes.preparar(self)

        self.title("Ativar Autenticação em Duas Etapas")
        self.configure(bg=t.SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._pular)

        self._codigo_hash = None
        self._codigo_expira_em = None
        self._enviando = False

        interno = tk.Frame(self, bg=t.SURFACE, padx=26, pady=22)
        interno.pack(fill="both", expand=True)

        tk.Label(interno, text="SEGURANÇA DA CONTA", fg=t.PRIMARY, bg=t.SURFACE,
                 font=t.Fontes.corpo(9, "bold")).pack(anchor="w")
        tk.Label(interno, text="Confirme seu e-mail", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.display(18)).pack(anchor="w", pady=(2, 6))

        self.label_status = tk.Label(
            interno, text=f"Enviando um código para {self.usuario['email']}…",
            fg=t.TEXT_MUTED, bg=t.SURFACE, font=t.Fontes.corpo(10), justify="left", wraplength=340,
        )
        self.label_status.pack(anchor="w", pady=(0, 14))

        self.campo_codigo = t.CampoEditorial(interno, "CÓDIGO DE CONFIRMAÇÃO")
        self.campo_codigo.pack(fill="x")
        self.campo_codigo.entry.bind("<Return>", lambda e: self._confirmar())

        self.botao_confirmar = t.botao_primario(interno, "Ativar e continuar", self._confirmar)
        self.botao_confirmar.pack(fill="x", pady=(16, 6))
        self.botao_confirmar.configure(state="disabled")

        linha_rodape = tk.Frame(interno, bg=t.SURFACE)
        linha_rodape.pack(fill="x")
        self.link_reenviar = t.link_texto(linha_rodape, "Reenviar código", self._reenviar)
        self.link_reenviar.pack(side="left")

        t.botao_secundario(interno, "Configurar mais tarde", self._pular).pack(fill="x", pady=(10, 0))

        self._enviar_codigo()

    def _enviar_codigo(self):
        if self._enviando:
            return
        self._enviando = True
        self.botao_confirmar.configure(state="disabled")
        self.link_reenviar.configure(fg=t.TEXT_MUTED)
        self.label_status.configure(text=f"Enviando um código para {self.usuario['email']}…", fg=t.TEXT_MUTED)
        _gerar_e_enviar_codigo_async(self, self.usuario, self._apos_envio)

    def _apos_envio(self, codigo_hash, expira_em, erro):
        self._enviando = False
        self.link_reenviar.configure(fg=t.SECONDARY)

        if erro is not None:
            self.label_status.configure(
                text="Não foi possível enviar o e-mail. Tente novamente.", fg=t.ERROR
            )
            _tratar_erro_email(erro, self.logger)
            return

        # Aqui ainda não gravamos no banco: só confirma a ativação depois
        # que a pessoa provar que recebeu o código nesse e-mail.
        self._codigo_hash = codigo_hash
        self._codigo_expira_em = expira_em
        self.label_status.configure(
            text=(f"Enviamos um código de 6 dígitos para {self.usuario['email']}. "
                  f"Ele expira em {EmailOTPManager.VALIDADE_MINUTOS} minutos."),
            fg=t.TEXT_MUTED,
        )
        self.botao_confirmar.configure(state="normal")
        self.campo_codigo.focus()

    def _reenviar(self):
        self._enviar_codigo()

    def _confirmar(self):
        codigo = self.campo_codigo.get()
        if EmailOTPManager.validar_codigo(codigo, self._codigo_hash, self._codigo_expira_em):
            self.db.ativar_dois_fatores(self.usuario["id"])
            self.db.limpar_codigo_verificacao(self.usuario["id"])
            self.usuario["dois_fatores_ativo"] = True
            self.logger.info(f"2FA (e-mail) ativado para: {self.usuario['usuario']}")
            messagebox.showinfo("Tudo certo!", "Verificação em duas etapas ativada com sucesso.")
            self.destroy()
            self.ao_concluir()
        else:
            messagebox.showerror("Código inválido", "O código não confere ou expirou. Tente reenviar.")

    def _pular(self):
        messagebox.showinfo(
            "Tudo bem",
            "Você pode ativar a verificação em duas etapas mais tarde, na aba Segurança.",
        )
        self.destroy()
        self.ao_concluir()


# =============================================================================
# Janela: Principal
# =============================================================================
class MainWindow(tk.Tk):
    """Janela principal: cabeçalho/masthead com navegação (Notícias,
    Categorias, Autores, Gráficos e Segurança) e a tela de cada seção."""

    def __init__(self, db: DatabaseManager, logger: Logger, usuario: dict = None):
        super().__init__()
        self.db = db
        self.logger = logger
        self.usuario = usuario or {}
        t.Fontes.preparar(self)

        titulo_usuario = f" — {self.usuario.get('nome')}" if self.usuario.get("nome") else ""
        self.title(f"NewsManager - Sistema de Gerenciamento e Análise de Notícias{titulo_usuario}")
        self.configure(bg=t.BG)
        self.geometry("1280x860")
        self.minsize(1100, 700)

        self._montar_layout()
        self.mostrar_aba("noticias")

    # ---------- Layout geral ----------
    def _montar_layout(self):
        self.cabecalho = Cabecalho(
            self, self.usuario,
            ao_navegar=self.mostrar_aba,
            ao_nova_materia=self._nova_materia,
            ao_sair=self._sair,
            verificar_conexao=self._banco_conectado,
        )
        self.cabecalho.pack(fill="x")
        Rodape(self).pack(side="bottom", fill="x")
        self.area = AreaAbas(self)
        self.area.pack(fill="both", expand=True)

        # Telas do layout Stitch (app/tela_noticias.py e app/telas_cadastros.py)
        self.aba_noticias = NoticiasFrame(
            self.area, self.db, self.logger, ao_alterar=self._apos_alterar_cadastros)
        self.aba_categorias = CategoriasFrame(
            self.area, self.db, self.logger, ao_alterar=self._apos_alterar_cadastros)
        self.aba_autores = AutoresFrame(
            self.area, self.db, self.logger, ao_alterar=self._apos_alterar_cadastros)
        self.aba_grafico = tk.Frame(self.area, bg=t.BG)
        self.aba_seguranca = tk.Frame(self.area, bg=t.BG)

        # Mesma ordem da navegação do protótipo
        self.area.adicionar("noticias", self.aba_noticias)
        self.area.adicionar("categorias", self.aba_categorias)
        self.area.adicionar("autores", self.aba_autores)
        self.area.adicionar("graficos", self.aba_grafico)
        self.area.adicionar("seguranca", self.aba_seguranca)

        self._montar_aba_grafico()
        self._montar_aba_seguranca()

    # ---------- Navegação ----------
    def mostrar_aba(self, chave):
        """Troca de tela e recarrega os dados dela (as contagens de matérias
        por categoria/autor podem ter mudado em outra aba)."""
        self.area.mostrar(chave)
        self.cabecalho.definir_ativa(chave)
        if chave in ("noticias", "categorias", "autores"):
            self.area.tela(chave).recarregar()
        elif chave == "graficos":
            self._desenhar_grafico()

    def _nova_materia(self):
        self.mostrar_aba("noticias")
        self.aba_noticias.nova_materia()

    def _banco_conectado(self):
        conexao = getattr(self.db, "connection", None)
        return bool(conexao and conexao.is_connected())

    def _apos_alterar_cadastros(self):
        """Chamado quando uma notícia, categoria ou autor muda."""
        try:
            self._desenhar_grafico()
        except Exception as e:
            self.logger.error("Erro ao atualizar o gráfico", e)

    def _sair(self):
        """Encerra a sessão e volta para a tela de login."""
        if not messagebox.askyesno("Sair", "Deseja encerrar a sessão e voltar ao login?"):
            return
        self.logger.info(f"Logout: {self.usuario.get('usuario')}")
        self.destroy()
        LoginWindow(self.db, self.logger).mainloop()

    def _montar_aba_grafico(self):
        _cabecalho(
            self.aba_grafico, "Mesa de Análise", "Gráficos & Análise",
            "Distribuição das matérias por editoria no acervo do jornal.",
        )
        barra = tk.Frame(self.aba_grafico, bg=t.BG)
        barra.pack(fill="x", padx=28, pady=(14, 0))
        t.botao_secundario(barra, "ATUALIZAR GRÁFICO", self._desenhar_grafico).pack(side="right")

        self.figura = Figure(figsize=(6, 4), facecolor=t.BG)
        self.canvas = FigureCanvasTkAgg(self.figura, master=self.aba_grafico)
        self.canvas.get_tk_widget().configure(bg=t.BG, highlightthickness=0)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=28, pady=14)
        self._desenhar_grafico()

    def _desenhar_grafico(self):
        try:
            dados = self.db.contar_noticias_por_categoria()
            self.figura.clear()
            ax = self.figura.add_subplot(111)
            ax.set_facecolor(t.SURFACE)

            categorias = [d["categoria"] for d in dados]
            totais = [d["total"] for d in dados]

            ax.bar(categorias, totais, color=t.PRIMARY)
            ax.set_title("Notícias por Categoria", color=t.TEXT)
            ax.set_ylabel("Quantidade", color=t.TEXT_MUTED)
            ax.tick_params(colors=t.TEXT_MUTED)
            for lado in ("top", "right"):
                ax.spines[lado].set_visible(False)
            self.figura.autofmt_xdate(rotation=30)
            self.canvas.draw()
        except Exception as e:
            self.logger.error("Erro ao gerar gráfico", e)

    # ---------- Aba de Segurança (2FA) ----------
    def _montar_aba_seguranca(self):
        _cabecalho(
            self.aba_seguranca, "Credenciais & Acesso", "Segurança da Conta",
            "Verificação em duas etapas por e-mail para proteger o acesso à redação.",
        )
        cartao = tk.Frame(self.aba_seguranca, bg=t.SURFACE, highlightthickness=1,
                          highlightbackground=t.BORDER)
        cartao.pack(fill="x", padx=28, pady=(18, 0))
        interno = tk.Frame(cartao, bg=t.SURFACE, padx=20, pady=18)
        interno.pack(fill="x")

        nome = self.usuario.get("nome", "—")
        email = self.usuario.get("email", "—")
        tk.Label(interno, text=f"Usuário logado: {nome} ({email})", fg=t.TEXT, bg=t.SURFACE,
                 font=t.Fontes.corpo(11, "bold")).pack(anchor="w", pady=(0, 12))

        self.label_status_2fa = tk.Label(interno, text="", fg=t.TEXT_MUTED, bg=t.SURFACE,
                                         font=t.Fontes.corpo(10))
        self.label_status_2fa.pack(anchor="w", pady=(0, 12))

        self.botao_2fa = t.botao_primario(interno, "Ativar 2FA", self._alternar_2fa)
        self.botao_2fa.pack(anchor="w")

        self._atualizar_status_2fa()

    def _alternar_2fa(self):
        if not self.usuario.get("id"):
            return
        if self.usuario.get("dois_fatores_ativo"):
            if messagebox.askyesno(
                "Desativar verificação em duas etapas",
                "Tem certeza que deseja desativar a verificação em duas etapas por e-mail?",
            ):
                self.db.desativar_dois_fatores(self.usuario["id"])
                self.usuario["dois_fatores_ativo"] = False
                self.logger.info(f"2FA (e-mail) desativado para: {self.usuario.get('usuario')}")
                self._atualizar_status_2fa()
        else:
            ConfiguracaoDoisFatoresDialog(self, self.db, self.logger, self.usuario, self._atualizar_status_2fa)

    def _atualizar_status_2fa(self):
        ativo = bool(self.usuario.get("dois_fatores_ativo"))
        self.label_status_2fa.configure(
            text=f"Verificação em duas etapas (por e-mail): {'ATIVADA' if ativo else 'DESATIVADA'}"
        )
        self.botao_2fa.configure(text=("DESATIVAR 2FA" if ativo else "ATIVAR 2FA"))
