"""
database.py
Classe responsável pela conexão com o MySQL e pelas operações
CRUD (Create, Read, Update, Delete) do sistema NewsManager.
"""

import mysql.connector
from mysql.connector import Error
from .logger import Logger


class DatabaseManager:
    """Gerencia a conexão e as operações com o banco de dados MySQL."""

    def __init__(self, host="localhost", user="root", password="", database="newsmanager"):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.connection = None
        self.logger = Logger()

    # ---------- Conexão ----------
    def conectar(self):
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
            )
            self.logger.info("Conexão com o banco de dados estabelecida.")
            return True
        except Error as e:
            self.logger.error("Falha ao conectar ao banco de dados", e)
            return False

    def desconectar(self):
        if self.connection and self.connection.is_connected():
            self.connection.close()
            self.logger.info("Conexão com o banco de dados encerrada.")

    def _executar(self, query, params=None, fetch=False, commit=False):
        """Método auxiliar central para executar queries com tratamento de erro."""
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(query, params or ())
            resultado = None
            if fetch:
                resultado = cursor.fetchall()
            if commit:
                self.connection.commit()
            cursor.close()
            return resultado
        except Error as e:
            self.logger.error(f"Erro ao executar query: {query}", e)
            return None

    # ---------- Usuários: consulta ----------
    def buscar_usuario_por_identificador(self, identificador: str):
        """Busca um usuário pelo campo 'usuario' OU pelo 'email' (login flexível)."""
        query = "SELECT * FROM usuarios WHERE usuario = %s OR email = %s LIMIT 1"
        resultado = self._executar(query, (identificador, identificador), fetch=True)
        return resultado[0] if resultado else None

    def buscar_usuario_por_email(self, email: str):
        resultado = self._executar(
            "SELECT * FROM usuarios WHERE email = %s LIMIT 1", (email,), fetch=True
        )
        return resultado[0] if resultado else None

    def buscar_usuario_por_google_id(self, google_id: str):
        if not google_id:
            return None
        resultado = self._executar(
            "SELECT * FROM usuarios WHERE google_id = %s LIMIT 1", (google_id,), fetch=True
        )
        return resultado[0] if resultado else None

    def buscar_usuario_por_id(self, usuario_id: int):
        resultado = self._executar(
            "SELECT * FROM usuarios WHERE id = %s LIMIT 1", (usuario_id,), fetch=True
        )
        return resultado[0] if resultado else None

    def usuario_ou_email_em_uso(self, usuario: str, email: str) -> bool:
        query = "SELECT id FROM usuarios WHERE usuario = %s OR email = %s LIMIT 1"
        resultado = self._executar(query, (usuario, email), fetch=True)
        return bool(resultado)

    # ---------- Usuários: cadastro e manutenção ----------
    def criar_usuario(self, nome, usuario, email, senha_hash):
        """Cria uma conta tradicional (usuário + senha com hash bcrypt)."""
        query = """INSERT INTO usuarios (nome, usuario, email, senha_hash)
                   VALUES (%s, %s, %s, %s)"""
        self._executar(query, (nome, usuario, email, senha_hash), commit=True)
        return self.buscar_usuario_por_email(email)

    def criar_usuario_google(self, nome, email, google_id):
        """Cria uma conta a partir de um primeiro login com o Google
        (sem senha local; usa o e-mail também como 'usuario')."""
        query = """INSERT INTO usuarios (nome, usuario, email, google_id)
                   VALUES (%s, %s, %s, %s)"""
        self._executar(query, (nome, email, email, google_id), commit=True)
        return self.buscar_usuario_por_email(email)

    def vincular_google_id(self, usuario_id, google_id):
        """Associa uma Conta Google a um cadastro tradicional já existente
        com o mesmo e-mail (permite logar tanto com senha quanto com Google)."""
        self._executar(
            "UPDATE usuarios SET google_id = %s WHERE id = %s",
            (google_id, usuario_id),
            commit=True,
        )

    def salvar_codigo_verificacao(self, usuario_id, codigo_hash, expira_em):
        """Guarda o hash do código de 6 dígitos enviado por e-mail e sua validade."""
        self._executar(
            "UPDATE usuarios SET codigo_verificacao = %s, codigo_expira_em = %s WHERE id = %s",
            (codigo_hash, expira_em, usuario_id),
            commit=True,
        )

    def limpar_codigo_verificacao(self, usuario_id):
        """Invalida o código depois de usado (ou cancelado), evitando reuso."""
        self._executar(
            "UPDATE usuarios SET codigo_verificacao = NULL, codigo_expira_em = NULL WHERE id = %s",
            (usuario_id,),
            commit=True,
        )

    def ativar_dois_fatores(self, usuario_id):
        self._executar(
            "UPDATE usuarios SET dois_fatores_ativo = TRUE WHERE id = %s",
            (usuario_id,),
            commit=True,
        )

    def desativar_dois_fatores(self, usuario_id):
        self._executar(
            """UPDATE usuarios
               SET dois_fatores_ativo = FALSE, codigo_verificacao = NULL, codigo_expira_em = NULL
               WHERE id = %s""",
            (usuario_id,),
            commit=True,
        )

    def atualizar_ultimo_login(self, usuario_id):
        self._executar(
            "UPDATE usuarios SET ultimo_login = NOW() WHERE id = %s",
            (usuario_id,),
            commit=True,
        )

    # ---------- CRUD: Notícias ----------
    def criar_noticia(self, titulo, conteudo, categoria_id, autor_id, data_publicacao):
        query = """INSERT INTO noticias (titulo, conteudo, categoria_id, autor_id, data_publicacao)
                   VALUES (%s, %s, %s, %s, %s)"""
        return self._executar(
            query, (titulo, conteudo, categoria_id, autor_id, data_publicacao), commit=True
        )

    def listar_noticias(self):
        query = """SELECT n.id, n.titulo, c.nome AS categoria, a.nome AS autor,
                          n.data_publicacao
                   FROM noticias n
                   JOIN categorias c ON n.categoria_id = c.id
                   JOIN autores a ON n.autor_id = a.id
                   ORDER BY n.data_publicacao DESC"""
        return self._executar(query, fetch=True) or []

    def atualizar_noticia(self, noticia_id, titulo, conteudo, categoria_id, autor_id, data_publicacao):
        query = """UPDATE noticias
                   SET titulo=%s, conteudo=%s, categoria_id=%s, autor_id=%s, data_publicacao=%s
                   WHERE id=%s"""
        return self._executar(
            query,
            (titulo, conteudo, categoria_id, autor_id, data_publicacao, noticia_id),
            commit=True,
        )

    def excluir_noticia(self, noticia_id):
        query = "DELETE FROM noticias WHERE id = %s"
        return self._executar(query, (noticia_id,), commit=True)

    # ---------- CRUD: Categorias ----------
    def listar_categorias(self):
        return self._executar("SELECT * FROM categorias ORDER BY nome", fetch=True) or []

    def criar_categoria(self, nome):
        return self._executar(
            "INSERT INTO categorias (nome) VALUES (%s)", (nome,), commit=True
        )

    # ---------- CRUD: Autores ----------
    def listar_autores(self):
        return self._executar("SELECT * FROM autores ORDER BY nome", fetch=True) or []

    def criar_autor(self, nome, email=None):
        return self._executar(
            "INSERT INTO autores (nome, email) VALUES (%s, %s)", (nome, email), commit=True
        )

    # ---------- Estatísticas para o gráfico ----------
    def contar_noticias_por_categoria(self):
        query = """SELECT c.nome AS categoria, COUNT(n.id) AS total
                   FROM categorias c
                   LEFT JOIN noticias n ON n.categoria_id = c.id
                   GROUP BY c.nome
                   ORDER BY total DESC"""
        return self._executar(query, fetch=True) or []
