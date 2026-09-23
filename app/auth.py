"""
auth.py
Camada de autenticação do NewsManager: hashing de senha (bcrypt),
autenticação em duas etapas via código enviado por e-mail (SMTP)
e login social com o Google (fluxo OAuth 2.0 para aplicativo desktop).

Este módulo isola as dependências externas para que o restante da
aplicação (gui.py) não precise conhecer os detalhes de cada mecanismo.
Se alguma biblioteca opcional não estiver instalada, ou se o SMTP não
estiver configurado, os métodos correspondentes levantam uma exceção
explicando o que fazer — em vez de derrubar a aplicação inteira.
"""

import hashlib
import json
import os
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

try:
    import bcrypt
    _BCRYPT_DISPONIVEL = True
except ImportError:
    _BCRYPT_DISPONIVEL = False


class DependenciaAusente(Exception):
    """Lançada quando uma biblioteca opcional necessária não está instalada."""


class ConfiguracaoEmailAusente(Exception):
    """Lançada quando o arquivo de configuração do SMTP não existe/está incompleto."""


# ---------------------------------------------------------------------------
# Senhas
# ---------------------------------------------------------------------------
class PasswordHasher:
    """Gera e verifica hashes de senha com bcrypt (nunca armazenamos a
    senha em texto puro no banco)."""

    @staticmethod
    def gerar_hash(senha: str) -> str:
        if not _BCRYPT_DISPONIVEL:
            raise DependenciaAusente(
                "A biblioteca 'bcrypt' não está instalada. Rode: pip install bcrypt"
            )
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(senha.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def verificar(senha: str, hash_armazenado: str) -> bool:
        if not _BCRYPT_DISPONIVEL:
            raise DependenciaAusente(
                "A biblioteca 'bcrypt' não está instalada. Rode: pip install bcrypt"
            )
        if not hash_armazenado:
            return False
        try:
            return bcrypt.checkpw(senha.encode("utf-8"), hash_armazenado.encode("utf-8"))
        except (ValueError, AttributeError):
            return False


# ---------------------------------------------------------------------------
# Autenticação em Duas Etapas (código de 6 dígitos por e-mail)
# ---------------------------------------------------------------------------
class EmailOTPManager:
    """Gera o código de verificação de 6 dígitos, calcula sua validade e
    confere se um código informado ainda é válido. O código nunca é
    guardado em texto puro no banco — só o hash (SHA-256) dele."""

    VALIDADE_MINUTOS = 10

    @staticmethod
    def gerar_codigo() -> str:
        # secrets.randbelow é criptograficamente seguro (diferente de random).
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def hash_codigo(codigo: str) -> str:
        return hashlib.sha256(codigo.encode("utf-8")).hexdigest()

    @staticmethod
    def calcular_expiracao() -> datetime:
        return datetime.now() + timedelta(minutes=EmailOTPManager.VALIDADE_MINUTOS)

    @staticmethod
    def validar_codigo(codigo_informado: str, hash_armazenado: str, expira_em) -> bool:
        if not hash_armazenado or not expira_em:
            return False
        # expira_em pode vir do MySQL como datetime ou como string, dependendo do driver.
        if isinstance(expira_em, str):
            expira_em = datetime.fromisoformat(expira_em)
        if datetime.now() > expira_em:
            return False
        codigo_informado = (codigo_informado or "").strip()
        if not codigo_informado:
            return False
        return EmailOTPManager.hash_codigo(codigo_informado) == hash_armazenado


# ---------------------------------------------------------------------------
# Envio do código por e-mail (SMTP)
# ---------------------------------------------------------------------------
# As credenciais do servidor de e-mail ficam em config/email_config.json
# (nunca commitado). Veja config/email_config.json e o passo a
# passo no README para configurar com uma conta do Gmail (ou outro SMTP).
EMAIL_CONFIG_FILE = os.path.join("config", "email_config.json")


class EmailSender:
    """Envia o e-mail com o código de verificação usando smtplib (biblioteca
    nativa do Python — não é necessário instalar nada além do que já vem
    no requirements.txt)."""

    @staticmethod
    def configuracao_disponivel() -> bool:
        return os.path.exists(EMAIL_CONFIG_FILE)

    @staticmethod
    def _carregar_configuracao() -> dict:
        if not EmailSender.configuracao_disponivel():
            raise ConfiguracaoEmailAusente(
                f"Arquivo '{EMAIL_CONFIG_FILE}' não encontrado. Veja no README "
                "como configurar o envio de e-mail (SMTP) para o 2FA."
            )
        with open(EMAIL_CONFIG_FILE, "r", encoding="utf-8") as arquivo:
            config = json.load(arquivo)

        campos_obrigatorios = ["smtp_host", "smtp_porta", "smtp_usuario", "smtp_senha"]
        faltando = [campo for campo in campos_obrigatorios if not config.get(campo)]
        if faltando:
            raise ConfiguracaoEmailAusente(
                f"O arquivo '{EMAIL_CONFIG_FILE}' está incompleto. "
                f"Faltam os campos: {', '.join(faltando)}."
            )
        return config

    @staticmethod
    def enviar_codigo_verificacao(destinatario: str, nome: str, codigo: str):
        config = EmailSender._carregar_configuracao()

        mensagem = EmailMessage()
        mensagem["Subject"] = "Seu código de verificação — NewsManager"
        remetente_nome = config.get("remetente_nome", "NewsManager")
        mensagem["From"] = f"{remetente_nome} <{config['smtp_usuario']}>"
        mensagem["To"] = destinatario
        mensagem.set_content(
            f"Olá, {nome or destinatario}!\n\n"
            f"Seu código de verificação do NewsManager é: {codigo}\n\n"
            f"Esse código expira em {EmailOTPManager.VALIDADE_MINUTOS} minutos. "
            "Se você não tentou fazer login ou criar uma conta, pode ignorar "
            "este e-mail."
        )

        try:
            porta = int(config["smtp_porta"])
            contexto = ssl.create_default_context()
            with smtplib.SMTP(config["smtp_host"], porta, timeout=15) as servidor:
                servidor.starttls(context=contexto)
                servidor.login(config["smtp_usuario"], config["smtp_senha"])
                servidor.send_message(mensagem)
        except smtplib.SMTPException as exc:
            raise RuntimeError(f"Falha ao enviar o e-mail de verificação: {exc}") from exc
        except OSError as exc:
            raise RuntimeError(
                f"Não foi possível conectar ao servidor de e-mail: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Login social com Google (OAuth 2.0 - fluxo "Aplicativo instalado")
# ---------------------------------------------------------------------------
# Para funcionar, é necessário gerar credenciais OAuth do tipo "Aplicativo
# para computador" no Google Cloud Console e salvar o arquivo baixado como
# "client_secret.json" dentro da pasta config/. Veja o passo a passo no README.
CLIENT_SECRET_FILE = os.path.join("config", "client_secret.json")
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleAuthManager:
    """Abre o navegador padrão do usuário para autenticação com a Conta
    Google e devolve os dados básicos do perfil autenticado."""

    @staticmethod
    def credenciais_configuradas() -> bool:
        return os.path.exists(CLIENT_SECRET_FILE)

    @staticmethod
    def autenticar() -> dict:
        """
        Executa o fluxo OAuth 2.0 completo:
        1. Abre uma aba do navegador com a tela de login/consentimento do Google.
        2. Sobe um servidor HTTP local temporário só para capturar o retorno.
        3. Usa o token de acesso para buscar e-mail, nome e ID do usuário.

        Retorna: {"google_id": str, "email": str, "nome": str}

        Levanta:
        - DependenciaAusente se as libs do Google não estiverem instaladas.
        - FileNotFoundError se o client_secret.json não existir.
        """
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            import requests
        except ImportError as exc:
            raise DependenciaAusente(
                "As bibliotecas do login com Google não estão instaladas. Rode: "
                "pip install google-auth-oauthlib requests"
            ) from exc

        if not GoogleAuthManager.credenciais_configuradas():
            raise FileNotFoundError(
                f"Arquivo '{CLIENT_SECRET_FILE}' não encontrado. Veja no "
                "README como gerar as credenciais OAuth ('Aplicativo para "
                "computador') no Google Cloud Console e salvá-las em config/."
            )

        fluxo = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, GOOGLE_SCOPES)
        # port=0 escolhe uma porta local livre automaticamente.
        credenciais = fluxo.run_local_server(port=0, prompt="select_account")

        resposta = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {credenciais.token}"},
            timeout=10,
        )
        resposta.raise_for_status()
        perfil = resposta.json()

        if not perfil.get("email"):
            raise RuntimeError("O Google não retornou um e-mail para esta conta.")

        return {
            "google_id": perfil.get("sub"),
            "email": perfil["email"],
            "nome": perfil.get("name") or perfil["email"],
        }
