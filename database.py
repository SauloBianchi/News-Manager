"""
database.py
Classe responsável pela conexão com o MySQL e pelas operações
CRUD (Create, Read, Update, Delete) do sistema NewsManager.
"""

import mysql.connector
from mysql.connector import Error
from logger import Logger


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

    # ---------- Usuários (login) ----------
    def validar_login(self, usuario: str, senha: str):
        query = "SELECT * FROM usuarios WHERE usuario = %s AND senha = %s"
        resultado = self._executar(query, (usuario, senha), fetch=True)
        return resultado[0] if resultado else None

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
