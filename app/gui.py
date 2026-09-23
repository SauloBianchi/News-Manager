"""
gui.py
Interface gráfica do NewsManager, construída com Tkinter, seguindo o
layout editorial ("Broadsheet Editorial") do protótipo do Stitch.

Janelas:
- LoginWindow: autenticação com usuário/e-mail + senha, ou com o Google.
- CadastroWindow: criação de conta, com opção de ativar 2FA na hora.
- VerificacaoDoisFatoresDialog: pedido do código de 6 dígitos (enviado por
  e-mail) no login, quando o usuário tem 2FA ativado.
- ConfiguracaoDoisFatoresDialog: envia e confirma o código para ativar o 2FA.
- MainWindow: janela principal (CRUD de notícias, gráfico e segurança).
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date

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
def _gerar_e_enviar_codigo_async(widget, usuario, callback):
    """Gera o código de 6 dígitos e o envia por e-mail numa thread separada
    (evita travar a janela enquanto o SMTP responde). O callback recebe
    (codigo_hash, expira_em, erro) de volta na thread principal do Tkinter."""

    def tarefa():
        codigo = EmailOTPManager.gerar_codigo()
        codigo_hash = EmailOTPManager.hash_codigo(codigo)
        expira_em = EmailOTPManager.calcular_expiracao()
        try:
            EmailSender.enviar_codigo_verificacao(
                usuario["email"], usuario.get("nome", ""), codigo
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
    """Janela principal: cadastro de notícias, categorias, autores, gráfico
    e uma aba simples de segurança da conta (2FA)."""

    def __init__(self, db: DatabaseManager, logger: Logger, usuario: dict = None):
        super().__init__()
        self.db = db
        self.logger = logger
        self.usuario = usuario or {}

        titulo_usuario = f" — {self.usuario.get('nome')}" if self.usuario.get("nome") else ""
        self.title(f"NewsManager - Sistema de Gerenciamento e Análise de Notícias{titulo_usuario}")
        self.geometry("900x600")

        self._montar_layout()
        self._carregar_noticias()

    # ---------- Layout geral ----------
    def _montar_layout(self):
        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True)

        self.aba_noticias = ttk.Frame(abas)
        self.aba_grafico = ttk.Frame(abas)
        self.aba_seguranca = ttk.Frame(abas)

        abas.add(self.aba_noticias, text="Notícias")
        abas.add(self.aba_grafico, text="Gráficos")
        abas.add(self.aba_seguranca, text="Segurança")

        self._montar_aba_noticias()
        self._montar_aba_grafico()
        self._montar_aba_seguranca()

    # ---------- Aba de Notícias (CRUD) ----------
    def _montar_aba_noticias(self):
        frame_form = ttk.LabelFrame(self.aba_noticias, text="Nova / Editar Notícia")
        frame_form.pack(fill="x", padx=10, pady=10)

        tk.Label(frame_form, text="Título").grid(row=0, column=0, sticky="w")
        self.entry_titulo = tk.Entry(frame_form, width=50)
        self.entry_titulo.grid(row=0, column=1, padx=5, pady=3)

        tk.Label(frame_form, text="Categoria ID").grid(row=1, column=0, sticky="w")
        self.entry_categoria = tk.Entry(frame_form)
        self.entry_categoria.grid(row=1, column=1, sticky="w", padx=5, pady=3)

        tk.Label(frame_form, text="Autor ID").grid(row=2, column=0, sticky="w")
        self.entry_autor = tk.Entry(frame_form)
        self.entry_autor.grid(row=2, column=1, sticky="w", padx=5, pady=3)

        tk.Label(frame_form, text="Conteúdo").grid(row=3, column=0, sticky="nw")
        self.text_conteudo = tk.Text(frame_form, width=50, height=4)
        self.text_conteudo.grid(row=3, column=1, padx=5, pady=3)

        botoes = ttk.Frame(frame_form)
        botoes.grid(row=4, column=1, sticky="w", pady=5)
        ttk.Button(botoes, text="Adicionar", command=self._adicionar_noticia).pack(side="left", padx=3)
        ttk.Button(botoes, text="Atualizar", command=self._atualizar_noticia).pack(side="left", padx=3)
        ttk.Button(botoes, text="Excluir", command=self._excluir_noticia).pack(side="left", padx=3)

        colunas = ("id", "titulo", "categoria", "autor", "data_publicacao")
        self.tree = ttk.Treeview(self.aba_noticias, columns=colunas, show="headings")
        for col in colunas:
            self.tree.heading(col, text=col.capitalize())
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.bind("<<TreeviewSelect>>", self._selecionar_noticia)

    def _carregar_noticias(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for noticia in self.db.listar_noticias():
                self.tree.insert("", "end", values=(
                    noticia["id"], noticia["titulo"], noticia["categoria"],
                    noticia["autor"], noticia["data_publicacao"],
                ))
        except Exception as e:
            self.logger.error("Erro ao carregar notícias", e)

    def _adicionar_noticia(self):
        try:
            self.db.criar_noticia(
                self.entry_titulo.get(),
                self.text_conteudo.get("1.0", "end").strip(),
                int(self.entry_categoria.get()),
                int(self.entry_autor.get()),
                date.today(),
            )
            self._carregar_noticias()
            self.logger.info("Notícia adicionada.")
        except Exception as e:
            self.logger.error("Erro ao adicionar notícia", e)
            messagebox.showerror("Erro", "Não foi possível adicionar a notícia.")

    def _selecionar_noticia(self, event):
        selecionado = self.tree.focus()
        if selecionado:
            self._id_selecionado = self.tree.item(selecionado)["values"][0]

    def _atualizar_noticia(self):
        if not getattr(self, "_id_selecionado", None):
            messagebox.showwarning("Atenção", "Selecione uma notícia na lista.")
            return
        try:
            self.db.atualizar_noticia(
                self._id_selecionado,
                self.entry_titulo.get(),
                self.text_conteudo.get("1.0", "end").strip(),
                int(self.entry_categoria.get()),
                int(self.entry_autor.get()),
                date.today(),
            )
            self._carregar_noticias()
            self.logger.info(f"Notícia {self._id_selecionado} atualizada.")
        except Exception as e:
            self.logger.error("Erro ao atualizar notícia", e)
            messagebox.showerror("Erro", "Não foi possível atualizar a notícia.")

    def _excluir_noticia(self):
        if not getattr(self, "_id_selecionado", None):
            messagebox.showwarning("Atenção", "Selecione uma notícia na lista.")
            return
        try:
            self.db.excluir_noticia(self._id_selecionado)
            self._carregar_noticias()
            self.logger.info(f"Notícia {self._id_selecionado} excluída.")
        except Exception as e:
            self.logger.error("Erro ao excluir notícia", e)
            messagebox.showerror("Erro", "Não foi possível excluir a notícia.")

    # ---------- Aba de Gráficos ----------
    def _montar_aba_grafico(self):
        ttk.Button(
            self.aba_grafico, text="Atualizar gráfico", command=self._desenhar_grafico
        ).pack(pady=10)

        self.figura = Figure(figsize=(6, 4))
        self.canvas = FigureCanvasTkAgg(self.figura, master=self.aba_grafico)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self._desenhar_grafico()

    def _desenhar_grafico(self):
        try:
            dados = self.db.contar_noticias_por_categoria()
            self.figura.clear()
            ax = self.figura.add_subplot(111)

            categorias = [d["categoria"] for d in dados]
            totais = [d["total"] for d in dados]

            ax.bar(categorias, totais, color="#2b6cb0")
            ax.set_title("Notícias por Categoria")
            ax.set_ylabel("Quantidade")
            self.figura.autofmt_xdate(rotation=30)
            self.canvas.draw()
        except Exception as e:
            self.logger.error("Erro ao gerar gráfico", e)

    # ---------- Aba de Segurança (2FA) ----------
    def _montar_aba_seguranca(self):
        frame = ttk.Frame(self.aba_seguranca, padding=20)
        frame.pack(fill="both", expand=True)

        nome = self.usuario.get("nome", "—")
        email = self.usuario.get("email", "—")
        ttk.Label(
            frame, text=f"Usuário logado: {nome} ({email})", font=("Arial", 11, "bold")
        ).pack(anchor="w", pady=(0, 14))

        self.label_status_2fa = ttk.Label(frame, text="")
        self.label_status_2fa.pack(anchor="w", pady=(0, 8))

        self.botao_2fa = ttk.Button(frame, text="", command=self._alternar_2fa)
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
        self.botao_2fa.configure(text=("Desativar 2FA" if ativo else "Ativar 2FA"))
