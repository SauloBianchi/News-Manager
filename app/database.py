"""
database.py
Classe responsável pela conexão com o MySQL e pelas operações
CRUD (Create, Read, Update, Delete) do sistema NewsManager.
"""

from datetime import datetime

import mysql.connector
from mysql.connector import Error
from .logger import Logger


class ErroBanco(Exception):
    """Falha ao acessar o banco. `original` guarda a exceção do driver (se houver).
    Usada pelos métodos novos de categorias/autores, para a camada de serviço
    conseguir diferenciar erro de banco de nenhum registro encontrado."""

    def __init__(self, mensagem, original=None):
        super().__init__(mensagem)
        self.original = original


def _padrao_like(termo: str) -> str:
    """Monta o padrão de um LIKE '%termo%' escapando % _ e \\ digitados pelo usuário."""
    escapado = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


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
            self.garantir_esquema()
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

    def _rodar(self, query, params=None, fetch=False, commit=False):
        """Como _executar, mas em caso de erro LANÇA ErroBanco (com rollback)
        em vez de devolver None. Em consultas devolve a lista de linhas; em
        escritas devolve {"id": último id inserido, "linhas": linhas afetadas}."""
        if not self.connection or not self.connection.is_connected():
            if not self.conectar():
                raise ErroBanco("Não foi possível conectar ao banco de dados.")
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(query, params or ())
            if fetch:
                return cursor.fetchall()
            resultado = {"id": cursor.lastrowid, "linhas": cursor.rowcount}
            if commit:
                self.connection.commit()
            return resultado
        except Error as e:
            try:
                self.connection.rollback()
            except Error:
                pass
            self.logger.error(f"Erro ao executar query: {query}", e)
            raise ErroBanco("Erro ao acessar o banco de dados.", e) from e
        finally:
            if cursor is not None:
                cursor.close()

    # ---------- Esquema: colunas extras de categorias/autores ----------
    def _coluna_existe(self, tabela, coluna) -> bool:
        resultado = self._executar(
            """SELECT COUNT(*) AS n FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s""",
            (self.database, tabela, coluna), fetch=True,
        )
        return bool(resultado and resultado[0]["n"])

    def _tipo_coluna(self, tabela, coluna):
        resultado = self._executar(
            """SELECT DATA_TYPE AS tipo FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s""",
            (self.database, tabela, coluna), fetch=True,
        )
        return str(resultado[0]["tipo"]).lower() if resultado else None

    # Tabelas criadas automaticamente em bancos antigos (CREATE TABLE IF NOT EXISTS)
    _TABELAS_EXTRAS = (
        """CREATE TABLE IF NOT EXISTS notificacoes (
               id INT AUTO_INCREMENT PRIMARY KEY,
               tipo VARCHAR(30) NOT NULL,
               titulo VARCHAR(200) NOT NULL,
               mensagem VARCHAR(600) NULL,
               etiqueta VARCHAR(80) NULL,
               rodape VARCHAR(160) NULL,
               urgente TINYINT(1) NOT NULL DEFAULT 0,
               alvo_tipo VARCHAR(20) NULL,
               alvo_id INT NULL,
               usuario_destino INT NULL,
               ator VARCHAR(150) NULL,
               criado_em DATETIME NOT NULL
           )""",
        """CREATE TABLE IF NOT EXISTS notificacoes_lidas (
               usuario_id INT NOT NULL,
               notificacao_id INT NOT NULL,
               lida_em DATETIME NOT NULL,
               PRIMARY KEY (usuario_id, notificacao_id)
           )""",
        """CREATE TABLE IF NOT EXISTS preferencias_usuario (
               usuario_id INT NOT NULL,
               chave VARCHAR(60) NOT NULL,
               valor VARCHAR(255) NOT NULL,
               PRIMARY KEY (usuario_id, chave)
           )""",
        """CREATE TABLE IF NOT EXISTS tempo_cache (
               chave VARCHAR(40) NOT NULL PRIMARY KEY,
               atualizado_em DATETIME NOT NULL,
               payload MEDIUMTEXT NOT NULL
           )""",
        """CREATE TABLE IF NOT EXISTS clipping_itens (
               id INT AUTO_INCREMENT PRIMARY KEY,
               fonte_chave VARCHAR(60) NOT NULL,
               secao VARCHAR(80) NULL,
               guid VARCHAR(255) NOT NULL,
               url VARCHAR(1000) NOT NULL,
               titulo VARCHAR(500) NOT NULL,
               resumo TEXT NULL,
               autor_fonte VARCHAR(200) NULL,
               publicado_em DATETIME NULL,
               imagem_url VARCHAR(1000) NULL,
               coletado_em DATETIME NOT NULL,
               importado_noticia_id INT NULL,
               UNIQUE KEY uq_clipping_fonte_guid (fonte_chave, guid)
           )""",
        """CREATE TABLE IF NOT EXISTS importacoes_salvas (
               id INT AUTO_INCREMENT PRIMARY KEY,
               usuario_id INT NOT NULL,
               nome VARCHAR(120) NOT NULL,
               fontes TEXT NOT NULL,
               secoes TEXT NULL,
               palavras_incluir VARCHAR(500) NULL,
               palavras_excluir VARCHAR(500) NULL,
               periodo_horas INT NOT NULL DEFAULT 24,
               limite_por_fonte INT NOT NULL DEFAULT 10,
               so_com_imagem TINYINT(1) NOT NULL DEFAULT 0,
               ordem VARCHAR(20) NOT NULL DEFAULT 'recentes',
               categoria_id INT NULL,
               autor_id INT NULL,
               status_destino VARCHAR(20) NOT NULL DEFAULT 'em_pauta',
               automatica TINYINT(1) NOT NULL DEFAULT 0,
               ultima_execucao DATETIME NULL
           )""",
        """CREATE TABLE IF NOT EXISTS clipping_historico (
               id INT AUTO_INCREMENT PRIMARY KEY,
               usuario_id INT NULL,
               quando DATETIME NOT NULL,
               origem VARCHAR(20) NOT NULL,
               nome VARCHAR(120) NULL,
               importadas INT NOT NULL DEFAULT 0,
               existentes INT NOT NULL DEFAULT 0,
               falhas INT NOT NULL DEFAULT 0,
               fontes VARCHAR(500) NULL
           )""",
        """CREATE TABLE IF NOT EXISTS clipping_feeds_estado (
               chave CHAR(40) NOT NULL PRIMARY KEY,
               url VARCHAR(1000) NOT NULL,
               etag VARCHAR(255) NULL,
               last_modified VARCHAR(100) NULL,
               ultima_coleta DATETIME NULL,
               ultimo_status VARCHAR(255) NULL
           )""",
        """CREATE TABLE IF NOT EXISTS clipping_feeds_proprios (
               id INT AUTO_INCREMENT PRIMARY KEY,
               usuario_id INT NOT NULL,
               nome VARCHAR(100) NOT NULL,
               url VARCHAR(500) NOT NULL,
               secao VARCHAR(80) NULL,
               criado_em DATETIME NOT NULL
           )""",
    )

    def garantir_esquema(self):
        """Atualiza bancos criados com a versão antiga do schema.sql: adiciona
        as colunas usadas pelas telas de Categorias e Autores (descricao, cor,
        status, bio, funcao, cargo, registro) e de Notícias (subtitulo, status,
        destaque, etiquetas, leituras, imagem, imagem_legenda, imagem_credito), a
        foto dos autores e o perfil do usuário, e cria as tabelas de notificações
        e de preferências, se ainda não existirem. Roda a cada
        conexão, mas só altera a tabela na primeira vez."""
        novas_colunas = [
            ("categorias", "descricao", "VARCHAR(255) NULL"),
            ("categorias", "cor", "VARCHAR(20) NOT NULL DEFAULT 'rubro'"),
            ("categorias", "status", "VARCHAR(20) NOT NULL DEFAULT 'ativa'"),
            ("autores", "bio", "TEXT NULL"),
            ("autores", "funcao", "VARCHAR(30) NOT NULL DEFAULT 'reporter'"),
            ("autores", "cargo", "VARCHAR(120) NULL"),
            ("autores", "registro", "VARCHAR(40) NULL"),
            ("autores", "status", "VARCHAR(30) NOT NULL DEFAULT 'ativo'"),
            ("noticias", "subtitulo", "VARCHAR(300) NULL"),
            ("noticias", "status", "VARCHAR(20) NOT NULL DEFAULT 'publicado'"),
            ("noticias", "destaque", "TINYINT(1) NOT NULL DEFAULT 0"),
            ("noticias", "etiquetas", "VARCHAR(255) NULL"),
            ("noticias", "leituras", "INT NOT NULL DEFAULT 0"),
            ("noticias", "imagem", "VARCHAR(255) NULL"),
            ("noticias", "imagem_legenda", "VARCHAR(255) NULL"),
            ("noticias", "imagem_credito", "VARCHAR(120) NULL"),
            ("autores", "foto", "VARCHAR(255) NULL"),
            # perfil do usuário (tela Perfil)
            ("usuarios", "byline", "VARCHAR(150) NULL"),
            ("usuarios", "telefone", "VARCHAR(60) NULL"),
            ("usuarios", "atribuicao", "TEXT NULL"),
            ("usuarios", "cargo", "VARCHAR(120) NULL"),
            ("usuarios", "matricula", "VARCHAR(40) NULL"),
            ("usuarios", "registro", "VARCHAR(40) NULL"),
            ("usuarios", "conselho", "VARCHAR(120) NULL"),
            ("usuarios", "mesa", "VARCHAR(120) NULL"),
            ("usuarios", "nota_biografica", "TEXT NULL"),
            ("usuarios", "foto", "VARCHAR(255) NULL"),
            ("usuarios", "atualizado_em", "DATETIME NULL"),
            ("usuarios", "atualizado_por", "VARCHAR(150) NULL"),
            # matérias importadas por clipping (conteúdo externo); nulas nas matérias normais
            ("noticias", "fonte_nome", "VARCHAR(120) NULL"),
            ("noticias", "fonte_url", "VARCHAR(1000) NULL"),
            ("noticias", "fonte_guid", "VARCHAR(255) NULL"),
        ]
        for ddl in self._TABELAS_EXTRAS:
            self._executar(ddl, commit=True)
        for tabela, coluna, definicao in novas_colunas:
            if not self._coluna_existe(tabela, coluna):
                self._executar(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}", commit=True)
                self.logger.info(f"Coluna {tabela}.{coluna} adicionada ao banco.")
        # O layout mostra "data e HORA de emissão": data_publicacao passa de DATE para DATETIME.
        if self._tipo_coluna("noticias", "data_publicacao") == "date":
            self._executar("ALTER TABLE noticias MODIFY data_publicacao DATETIME NOT NULL", commit=True)
            self.logger.info("Coluna noticias.data_publicacao convertida para DATETIME.")

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

    def redefinir_senha(self, usuario_id, nova_senha_hash):
        """Usada no fluxo de 'esqueci minha senha': troca o hash da senha
        e invalida qualquer código de verificação pendente."""
        self._executar(
            """UPDATE usuarios
               SET senha_hash = %s, codigo_verificacao = NULL, codigo_expira_em = NULL
               WHERE id = %s""",
            (nova_senha_hash, usuario_id),
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
    # Ordenações aceitas na listagem (whitelist: nunca vai texto do usuário para o ORDER BY)
    _ORDENS_NOTICIA = {
        "recentes": "n.data_publicacao DESC, n.id DESC",
        "antigas": "n.data_publicacao ASC, n.id ASC",
        "lidas": "n.leituras DESC, n.id DESC",
        "titulo": "n.titulo ASC, n.id ASC",
    }

    def listar_noticias(self):
        """Versão simples (compatibilidade). Para as telas use listar_noticias_detalhado."""
        query = """SELECT n.id, n.titulo, c.nome AS categoria, a.nome AS autor,
                          n.data_publicacao
                   FROM noticias n
                   JOIN categorias c ON n.categoria_id = c.id
                   JOIN autores a ON n.autor_id = a.id
                   ORDER BY n.data_publicacao DESC"""
        return self._executar(query, fetch=True) or []

    @staticmethod
    def _filtros_noticias(termo=None, categoria_id=None, status=None):
        condicoes, params = [], []
        if termo:
            condicoes.append(
                "(n.titulo LIKE %s OR n.subtitulo LIKE %s OR n.conteudo LIKE %s "
                "OR n.etiquetas LIKE %s OR a.nome LIKE %s OR c.nome LIKE %s)"
            )
            params += [_padrao_like(termo)] * 6
        if categoria_id:
            condicoes.append("n.categoria_id = %s")
            params.append(categoria_id)
        if status:
            condicoes.append("n.status = %s")
            params.append(status)
        filtro = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
        return filtro, params

    def listar_noticias_detalhado(self, termo=None, categoria_id=None, status=None,
                                  ordem="recentes", limite=None, deslocamento=0):
        """Feed de matérias (sem o texto completo: só um resumo de 400 caracteres).
        Aceita filtros e paginação. Lança ErroBanco em caso de falha."""
        filtro, params = self._filtros_noticias(termo, categoria_id, status)
        ordenacao = self._ORDENS_NOTICIA.get(ordem, self._ORDENS_NOTICIA["recentes"])
        paginacao = ""
        if limite:
            paginacao = "LIMIT %s OFFSET %s"
            params += [int(limite), int(deslocamento)]
        query = f"""SELECT n.id, n.titulo, n.subtitulo, SUBSTR(n.conteudo, 1, 400) AS resumo,
                           n.categoria_id, c.nome AS categoria, c.cor AS categoria_cor,
                           n.autor_id, a.nome AS autor, a.foto AS autor_foto, n.status, n.destaque,
                           n.etiquetas, n.leituras, n.data_publicacao,
                           n.imagem, n.imagem_legenda, n.imagem_credito,
                           n.fonte_nome, n.fonte_url
                    FROM noticias n
                    JOIN categorias c ON c.id = n.categoria_id
                    JOIN autores a ON a.id = n.autor_id
                    {filtro}
                    ORDER BY {ordenacao}
                    {paginacao}"""
        return self._rodar(query, tuple(params), fetch=True)

    def contar_noticias(self, termo=None, categoria_id=None, status=None) -> int:
        """Total de matérias que atendem aos filtros (para a paginação)."""
        filtro, params = self._filtros_noticias(termo, categoria_id, status)
        linhas = self._rodar(
            f"""SELECT COUNT(*) AS total
                FROM noticias n
                JOIN categorias c ON c.id = n.categoria_id
                JOIN autores a ON a.id = n.autor_id
                {filtro}""",
            tuple(params), fetch=True,
        )
        return int(linhas[0]["total"])

    def buscar_noticia_por_id(self, noticia_id):
        """Matéria completa (com o corpo do texto) ou None se não existir."""
        linhas = self._rodar(
            """SELECT n.id, n.titulo, n.subtitulo, n.conteudo, n.categoria_id,
                      c.nome AS categoria, c.cor AS categoria_cor, n.autor_id, a.nome AS autor,
                      a.cargo AS autor_cargo, a.foto AS autor_foto, n.status, n.destaque,
                      n.etiquetas, n.leituras, n.data_publicacao,
                      n.imagem, n.imagem_legenda, n.imagem_credito,
                      n.fonte_nome, n.fonte_url, n.fonte_guid
               FROM noticias n
               JOIN categorias c ON c.id = n.categoria_id
               JOIN autores a ON a.id = n.autor_id
               WHERE n.id = %s""",
            (noticia_id,), fetch=True,
        )
        return linhas[0] if linhas else None

    def criar_noticia(self, titulo, conteudo, categoria_id, autor_id, data_publicacao,
                      subtitulo=None, status="publicado", destaque=False, etiquetas=None,
                      imagem=None, imagem_legenda=None, imagem_credito=None,
                      fonte_nome=None, fonte_url=None, fonte_guid=None):
        """Insere a matéria e devolve o id gerado. Lança ErroBanco em caso de falha.
        fonte_* só são preenchidos em matérias importadas por clipping (conteúdo externo)."""
        r = self._rodar(
            """INSERT INTO noticias (titulo, subtitulo, conteudo, categoria_id, autor_id,
                                     data_publicacao, status, destaque, etiquetas,
                                     imagem, imagem_legenda, imagem_credito,
                                     fonte_nome, fonte_url, fonte_guid)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (titulo, subtitulo, conteudo, categoria_id, autor_id, data_publicacao,
             status, 1 if destaque else 0, etiquetas, imagem, imagem_legenda, imagem_credito,
             fonte_nome, fonte_url, fonte_guid),
            commit=True,
        )
        return r["id"]

    def atualizar_noticia(self, noticia_id, titulo, conteudo, categoria_id, autor_id,
                          data_publicacao, subtitulo=None, status="publicado",
                          destaque=False, etiquetas=None, imagem=None,
                          imagem_legenda=None, imagem_credito=None):
        self._rodar(
            """UPDATE noticias
               SET titulo = %s, subtitulo = %s, conteudo = %s, categoria_id = %s, autor_id = %s,
                   data_publicacao = %s, status = %s, destaque = %s, etiquetas = %s,
                   imagem = %s, imagem_legenda = %s, imagem_credito = %s
               WHERE id = %s""",
            (titulo, subtitulo, conteudo, categoria_id, autor_id, data_publicacao,
             status, 1 if destaque else 0, etiquetas, imagem, imagem_legenda,
             imagem_credito, noticia_id),
            commit=True,
        )

    def excluir_noticia(self, noticia_id):
        self._rodar("DELETE FROM noticias WHERE id = %s", (noticia_id,), commit=True)

    def registrar_leitura(self, noticia_id):
        """Soma 1 ao contador de leituras da matéria."""
        self._rodar(
            "UPDATE noticias SET leituras = leituras + 1 WHERE id = %s", (noticia_id,), commit=True
        )

    def contar_noticias_por_status(self):
        """[{'status': 'publicado', 'total': 12}, ...]"""
        return self._rodar(
            "SELECT status, COUNT(*) AS total FROM noticias GROUP BY status", fetch=True
        )

    def contar_publicadas_por_categoria(self, limite=5):
        """Categorias com mais matérias PUBLICADAS (painel 'Distribuição das Matérias')."""
        return self._rodar(
            """SELECT c.nome AS categoria, c.cor AS cor, COUNT(n.id) AS total
               FROM categorias c
               JOIN noticias n ON n.categoria_id = c.id AND n.status = 'publicado'
               GROUP BY c.id, c.nome, c.cor
               ORDER BY total DESC, c.nome
               LIMIT %s""",
            (int(limite),), fetch=True,
        )

    def listar_noticias_relacionadas(self, noticia_id, categoria_id, limite=3):
        """Outras matérias PUBLICADAS da mesma editoria, das mais recentes para as
        mais antigas ('leituras suplementares')."""
        return self._rodar(
            """SELECT n.id, n.titulo, n.subtitulo, SUBSTR(n.conteudo, 1, 400) AS resumo,
                      c.nome AS categoria, c.cor AS categoria_cor, a.nome AS autor,
                      n.data_publicacao
               FROM noticias n
               JOIN categorias c ON c.id = n.categoria_id
               JOIN autores a ON a.id = n.autor_id
               WHERE n.categoria_id = %s AND n.id <> %s AND n.status = 'publicado'
               ORDER BY n.data_publicacao DESC, n.id DESC
               LIMIT %s""",
            (categoria_id, noticia_id, int(limite)), fetch=True,
        )

    def imagem_em_uso(self, caminho) -> bool:
        """True se algum registro (capa, texto de matéria ou foto de autor) ainda
        usa esse arquivo de imagem. Evita apagar do disco uma imagem referenciada."""
        linhas = self._rodar(
            """SELECT 1 AS usado FROM noticias WHERE imagem = %s OR conteudo LIKE %s
               UNION
               SELECT 1 AS usado FROM autores WHERE foto = %s
               UNION
               SELECT 1 AS usado FROM usuarios WHERE foto = %s
               LIMIT 1""",
            (caminho, _padrao_like(caminho), caminho, caminho), fetch=True,
        )
        return bool(linhas)

    # ---------- Estatísticas (tela de Gráficos) ----------
    # Todas aceitam os mesmos filtros: período (inicio/fim), editoria, autor e
    # estado da matéria. Lançam ErroBanco em caso de falha.
    @staticmethod
    def _condicoes_estat(inicio=None, fim=None, categoria_id=None, autor_id=None, status=None):
        """Condições sobre a tabela `noticias` (alias n) e seus parâmetros."""
        condicoes, params = [], []
        if inicio:
            condicoes.append("n.data_publicacao >= %s")
            params.append(inicio)
        if fim:
            condicoes.append("n.data_publicacao <= %s")
            params.append(fim)
        if categoria_id:
            condicoes.append("n.categoria_id = %s")
            params.append(categoria_id)
        if autor_id:
            condicoes.append("n.autor_id = %s")
            params.append(autor_id)
        if status:
            condicoes.append("n.status = %s")
            params.append(status)
        return condicoes, params

    # Estimativa de palavras direto no SQL: espaços (e quebras de linha) + 1.
    # A quebra de linha vai como parâmetro para funcionar igual em qualquer SQL.
    _PALAVRAS_SQL = (
        "(CASE WHEN n.conteudo IS NULL OR n.conteudo = '' THEN 0 ELSE "
        "LENGTH(REPLACE(n.conteudo, %s, ' ')) - "
        "LENGTH(REPLACE(REPLACE(n.conteudo, %s, ' '), ' ', '')) + 1 END)"
    )

    def estatisticas_resumo(self, **filtros):
        """Totais do recorte: matérias, leituras (soma e média), média de palavras,
        editorias distintas e datas da primeira e da última matéria."""
        condicoes, params = self._condicoes_estat(**filtros)
        where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
        linhas = self._rodar(
            f"""SELECT COUNT(*) AS total,
                       COALESCE(SUM(n.leituras), 0) AS leituras,
                       COALESCE(AVG(n.leituras), 0) AS media_leituras,
                       COALESCE(AVG({self._PALAVRAS_SQL}), 0) AS media_palavras,
                       COUNT(DISTINCT n.categoria_id) AS categorias,
                       MIN(n.data_publicacao) AS primeira,
                       MAX(n.data_publicacao) AS ultima
                FROM noticias n {where}""",
            tuple(["\n", "\n"] + params), fetch=True,
        )
        return linhas[0]

    def estatisticas_por_categoria(self, **filtros):
        """Uma linha por editoria (inclusive as sem matérias no recorte), das mais
        para as menos movimentadas: id, nome, cor, status, total, leituras."""
        categoria_id = filtros.pop("categoria_id", None)
        condicoes, params = self._condicoes_estat(**filtros)
        juncao = "".join(f" AND {c}" for c in condicoes)
        where, params_where = "", []
        if categoria_id:
            where, params_where = "WHERE c.id = %s", [categoria_id]
        return self._rodar(
            f"""SELECT c.id, c.nome, c.cor, c.status,
                       COUNT(n.id) AS total, COALESCE(SUM(n.leituras), 0) AS leituras
                FROM categorias c
                LEFT JOIN noticias n ON n.categoria_id = c.id{juncao}
                {where}
                GROUP BY c.id, c.nome, c.cor, c.status
                ORDER BY total DESC, c.nome""",
            tuple(params + params_where), fetch=True,
        )

    def estatisticas_por_autor(self, limite=None, **filtros):
        """Produção por jornalista no recorte (só quem tem matérias): id, nome,
        cargo, total e soma de leituras. Mais produtivos primeiro."""
        condicoes, params = self._condicoes_estat(**filtros)
        where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
        paginacao = ""
        if limite:
            paginacao, params = "LIMIT %s", params + [int(limite)]
        return self._rodar(
            f"""SELECT a.id, a.nome, a.cargo, COUNT(n.id) AS total,
                       COALESCE(SUM(n.leituras), 0) AS leituras
                FROM noticias n
                JOIN autores a ON a.id = n.autor_id
                {where}
                GROUP BY a.id, a.nome, a.cargo
                ORDER BY total DESC, leituras DESC, a.nome
                {paginacao}""",
            tuple(params), fetch=True,
        )

    def estatisticas_datas(self, **filtros):
        """Datas de emissão das matérias do recorte (para agrupar por dia da
        semana e por período no Python, igual em qualquer banco)."""
        condicoes, params = self._condicoes_estat(**filtros)
        where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
        linhas = self._rodar(
            f"SELECT n.data_publicacao FROM noticias n {where} ORDER BY n.data_publicacao",
            tuple(params), fetch=True,
        )
        return [linha["data_publicacao"] for linha in linhas]

    def estatisticas_por_status(self, **filtros):
        """{estado: total} do recorte (ignora o filtro de estado)."""
        filtros.pop("status", None)
        condicoes, params = self._condicoes_estat(**filtros)
        where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
        linhas = self._rodar(
            f"SELECT n.status, COUNT(*) AS total FROM noticias n {where} GROUP BY n.status",
            tuple(params), fetch=True,
        )
        return {linha["status"]: int(linha["total"]) for linha in linhas}

    def contar_categorias_por_status(self, status="ativa") -> int:
        linhas = self._rodar(
            "SELECT COUNT(*) AS total FROM categorias WHERE status = %s", (status,), fetch=True)
        return int(linhas[0]["total"])

    def ultima_publicacao(self, ate):
        """Data da última matéria publicada até `ate` (None se não houver)."""
        linhas = self._rodar(
            "SELECT MAX(data_publicacao) AS ultima FROM noticias "
            "WHERE status = 'publicado' AND data_publicacao <= %s", (ate,), fetch=True)
        return linhas[0]["ultima"]

    # ---------- Notificações ----------
    # `usuario_id` define o que é "lida" para cada pessoa e quais avisos pessoais
    # (usuario_destino) ela vê. Todos lançam ErroBanco em caso de falha.
    @staticmethod
    def _filtro_notificacoes(filtro):
        base = "(n.usuario_destino IS NULL OR n.usuario_destino = %s)"
        if filtro == "nao_lidas":
            return base + " AND l.notificacao_id IS NULL"
        if filtro == "urgentes":
            return base + " AND n.urgente = 1"
        return base

    def criar_notificacao(self, tipo, titulo, mensagem=None, etiqueta=None, rodape=None, urgente=False,
                          alvo_tipo=None, alvo_id=None, usuario_destino=None, ator=None, criado_em=None):
        r = self._rodar(
            """INSERT INTO notificacoes (tipo, titulo, mensagem, etiqueta, rodape, urgente, alvo_tipo,
                                         alvo_id, usuario_destino, ator, criado_em)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (tipo, titulo, mensagem, etiqueta, rodape, 1 if urgente else 0, alvo_tipo, alvo_id,
             usuario_destino, ator, criado_em or datetime.now().replace(microsecond=0)),
            commit=True,
        )
        return r["id"]

    def listar_notificacoes(self, usuario_id, filtro="todas", limite=20, deslocamento=0):
        return self._rodar(
            f"""SELECT n.id, n.tipo, n.titulo, n.mensagem, n.etiqueta, n.rodape, n.urgente, n.alvo_tipo,
                       n.alvo_id, n.ator, n.criado_em,
                       (CASE WHEN l.notificacao_id IS NULL THEN 0 ELSE 1 END) AS lida
                FROM notificacoes n
                LEFT JOIN notificacoes_lidas l ON l.notificacao_id = n.id AND l.usuario_id = %s
                WHERE {self._filtro_notificacoes(filtro)}
                ORDER BY n.criado_em DESC, n.id DESC
                LIMIT %s OFFSET %s""",
            (usuario_id, usuario_id, int(limite), int(deslocamento)), fetch=True,
        )

    def contar_notificacoes(self, usuario_id, filtro="todas") -> int:
        linhas = self._rodar(
            f"""SELECT COUNT(*) AS total
                FROM notificacoes n
                LEFT JOIN notificacoes_lidas l ON l.notificacao_id = n.id AND l.usuario_id = %s
                WHERE {self._filtro_notificacoes(filtro)}""",
            (usuario_id, usuario_id), fetch=True,
        )
        return int(linhas[0]["total"])

    def buscar_notificacao(self, notificacao_id):
        linhas = self._rodar("SELECT * FROM notificacoes WHERE id = %s", (notificacao_id,), fetch=True)
        return linhas[0] if linhas else None

    def marcar_notificacao_lida(self, usuario_id, notificacao_id):
        existe = self._rodar(
            "SELECT 1 AS ok FROM notificacoes_lidas WHERE usuario_id = %s AND notificacao_id = %s",
            (usuario_id, notificacao_id), fetch=True)
        if not existe:
            self._rodar(
                "INSERT INTO notificacoes_lidas (usuario_id, notificacao_id, lida_em) VALUES (%s, %s, %s)",
                (usuario_id, notificacao_id, datetime.now().replace(microsecond=0)), commit=True)

    def marcar_todas_notificacoes_lidas(self, usuario_id):
        self._rodar(
            """INSERT INTO notificacoes_lidas (usuario_id, notificacao_id, lida_em)
               SELECT %s, n.id, %s
               FROM notificacoes n
               LEFT JOIN notificacoes_lidas l ON l.notificacao_id = n.id AND l.usuario_id = %s
               WHERE l.notificacao_id IS NULL AND (n.usuario_destino IS NULL OR n.usuario_destino = %s)""",
            (usuario_id, datetime.now().replace(microsecond=0), usuario_id, usuario_id), commit=True)

    def ultima_notificacao_urgente_nao_lida(self, usuario_id):
        """id da notificação urgente não lida mais recente (None se não houver)."""
        linhas = self._rodar(
            f"""SELECT MAX(n.id) AS id
                FROM notificacoes n
                LEFT JOIN notificacoes_lidas l ON l.notificacao_id = n.id AND l.usuario_id = %s
                WHERE {self._filtro_notificacoes("nao_lidas")} AND n.urgente = 1""",
            (usuario_id, usuario_id), fetch=True)
        return linhas[0]["id"]

    def purgar_notificacoes(self, antes):
        """Apaga notificações mais antigas que `antes` (e as marcações de leitura delas)."""
        self._rodar("DELETE FROM notificacoes_lidas WHERE notificacao_id IN "
                    "(SELECT id FROM notificacoes WHERE criado_em < %s)", (antes,), commit=True)
        self._rodar("DELETE FROM notificacoes WHERE criado_em < %s", (antes,), commit=True)

    def excluir_notificacoes_do_ator(self, ator):
        """Remove as notificações criadas por um ator (usado pelo seed.py)."""
        self._rodar("DELETE FROM notificacoes_lidas WHERE notificacao_id IN "
                    "(SELECT id FROM notificacoes WHERE ator = %s)", (ator,), commit=True)
        self._rodar("DELETE FROM notificacoes WHERE ator = %s", (ator,), commit=True)

    # ---------- Perfil e preferências do usuário ----------
    CAMPOS_PERFIL = ("nome", "byline", "telefone", "atribuicao", "cargo", "matricula", "registro",
                     "conselho", "mesa", "nota_biografica", "foto")

    def buscar_perfil_usuario(self, usuario_id):
        linhas = self._rodar(
            """SELECT id, nome, usuario, email, dois_fatores_ativo, criado_em, ultimo_login,
                      (CASE WHEN senha_hash IS NULL THEN 0 ELSE 1 END) AS tem_senha,
                      (CASE WHEN google_id IS NULL THEN 0 ELSE 1 END) AS tem_google,
                      byline, telefone, atribuicao, cargo, matricula, registro, conselho, mesa,
                      nota_biografica, foto, atualizado_em, atualizado_por
               FROM usuarios WHERE id = %s""",
            (usuario_id,), fetch=True)
        return linhas[0] if linhas else None

    def atualizar_perfil_usuario(self, usuario_id, campos: dict, atualizado_por=None):
        """Grava só os campos permitidos de CAMPOS_PERFIL e registra quem alterou e quando."""
        nomes = [c for c in self.CAMPOS_PERFIL if c in campos]
        if not nomes:
            return
        atribuicoes = ", ".join(f"{c} = %s" for c in nomes) + ", atualizado_em = %s, atualizado_por = %s"
        valores = [campos[c] for c in nomes] + [datetime.now().replace(microsecond=0), atualizado_por, usuario_id]
        self._rodar(f"UPDATE usuarios SET {atribuicoes} WHERE id = %s", tuple(valores), commit=True)

    def trocar_senha_usuario(self, usuario_id, senha_hash):
        self._rodar(
            """UPDATE usuarios SET senha_hash = %s, codigo_verificacao = NULL, codigo_expira_em = NULL,
                      atualizado_em = %s WHERE id = %s""",
            (senha_hash, datetime.now().replace(microsecond=0), usuario_id), commit=True)

    def obter_preferencias(self, usuario_id) -> dict:
        linhas = self._rodar("SELECT chave, valor FROM preferencias_usuario WHERE usuario_id = %s",
                             (usuario_id,), fetch=True)
        return {l["chave"]: l["valor"] for l in linhas}

    def salvar_preferencias(self, usuario_id, valores: dict):
        for chave, valor in valores.items():
            self._rodar("DELETE FROM preferencias_usuario WHERE usuario_id = %s AND chave = %s",
                        (usuario_id, chave), commit=True)
            self._rodar("INSERT INTO preferencias_usuario (usuario_id, chave, valor) VALUES (%s, %s, %s)",
                        (usuario_id, chave, str(valor)), commit=True)

    def listar_usuarios_com_preferencia(self, chave, valor="1"):
        """Usuários (id, nome, email) que ligaram uma preferência (ex.: e-mail de urgência)."""
        return self._rodar(
            """SELECT u.id, u.nome, u.email FROM usuarios u
               JOIN preferencias_usuario p ON p.usuario_id = u.id AND p.chave = %s AND p.valor = %s""",
            (chave, str(valor)), fetch=True)

    def somar_leituras(self) -> int:
        linhas = self._rodar("SELECT COALESCE(SUM(leituras), 0) AS total FROM noticias", fetch=True)
        return int(linhas[0]["total"])

    # ---------- CRUD: Categorias ----------
    def listar_categorias(self):
        return self._executar("SELECT * FROM categorias ORDER BY nome", fetch=True) or []

    def listar_categorias_detalhado(self, termo=None):
        """Categorias com total de notícias, data da última edição e o autor
        dela; `termo` filtra por nome ou descrição. Ordem: mais matérias
        primeiro. Lança ErroBanco em caso de falha."""
        filtro, params = "", ()
        if termo:
            filtro = "WHERE c.nome LIKE %s OR c.descricao LIKE %s"
            params = (_padrao_like(termo), _padrao_like(termo))
        query = f"""SELECT c.id, c.nome, c.descricao, c.cor, c.status,
                           COUNT(n.id) AS total_noticias,
                           MAX(n.data_publicacao) AS ultima_edicao,
                           (SELECT a2.nome
                              FROM noticias n2 JOIN autores a2 ON a2.id = n2.autor_id
                             WHERE n2.categoria_id = c.id
                             ORDER BY n2.data_publicacao DESC, n2.id DESC
                             LIMIT 1) AS ultimo_autor
                    FROM categorias c
                    LEFT JOIN noticias n ON n.categoria_id = c.id
                    {filtro}
                    GROUP BY c.id, c.nome, c.descricao, c.cor, c.status
                    ORDER BY total_noticias DESC, c.nome"""
        return self._rodar(query, params, fetch=True)

    def buscar_categoria_por_id(self, categoria_id):
        linhas = self._rodar(
            "SELECT id, nome, descricao, cor, status FROM categorias WHERE id = %s",
            (categoria_id,), fetch=True,
        )
        return linhas[0] if linhas else None

    def categoria_nome_em_uso(self, nome, ignorar_id=None) -> bool:
        linhas = self._rodar(
            "SELECT id FROM categorias WHERE nome = %s AND id <> %s LIMIT 1",
            (nome, ignorar_id if ignorar_id is not None else 0), fetch=True,
        )
        return bool(linhas)

    def criar_categoria(self, nome, descricao=None, cor="rubro", status="ativa"):
        """Insere a categoria e devolve o id gerado."""
        r = self._rodar(
            "INSERT INTO categorias (nome, descricao, cor, status) VALUES (%s, %s, %s, %s)",
            (nome, descricao, cor, status), commit=True,
        )
        return r["id"]

    def atualizar_categoria(self, categoria_id, nome, descricao=None, cor="rubro", status="ativa"):
        self._rodar(
            "UPDATE categorias SET nome = %s, descricao = %s, cor = %s, status = %s WHERE id = %s",
            (nome, descricao, cor, status, categoria_id), commit=True,
        )

    def contar_noticias_da_categoria(self, categoria_id) -> int:
        linhas = self._rodar(
            "SELECT COUNT(*) AS total FROM noticias WHERE categoria_id = %s",
            (categoria_id,), fetch=True,
        )
        return int(linhas[0]["total"])

    def excluir_categoria(self, categoria_id):
        self._rodar("DELETE FROM categorias WHERE id = %s", (categoria_id,), commit=True)

    # ---------- CRUD: Autores ----------
    def listar_autores(self):
        return self._executar("SELECT * FROM autores ORDER BY nome", fetch=True) or []

    def listar_autores_detalhado(self, termo=None, funcao=None):
        """Autores com total de notícias e data da última publicação. `termo`
        filtra por nome, e-mail, cargo, registro ou bio; `funcao` filtra por
        função (reporter, colunista...). Lança ErroBanco em caso de falha."""
        condicoes, params = [], []
        if termo:
            condicoes.append(
                "(a.nome LIKE %s OR a.email LIKE %s OR a.cargo LIKE %s "
                "OR a.registro LIKE %s OR a.bio LIKE %s)"
            )
            params += [_padrao_like(termo)] * 5
        if funcao:
            condicoes.append("a.funcao = %s")
            params.append(funcao)
        filtro = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
        query = f"""SELECT a.id, a.nome, a.email, a.bio, a.funcao, a.cargo, a.registro, a.status,
                           a.foto,
                           COUNT(n.id) AS total_noticias,
                           MAX(n.data_publicacao) AS ultima_publicacao
                    FROM autores a
                    LEFT JOIN noticias n ON n.autor_id = a.id
                    {filtro}
                    GROUP BY a.id, a.nome, a.email, a.bio, a.funcao, a.cargo, a.registro, a.status, a.foto
                    ORDER BY a.nome"""
        return self._rodar(query, tuple(params), fetch=True)

    def contar_autores_por_funcao(self):
        """[{'funcao': 'reporter', 'total': 3}, ...] — usado nos filtros da tela."""
        return self._rodar(
            "SELECT funcao, COUNT(*) AS total FROM autores GROUP BY funcao", fetch=True
        )

    def buscar_autor_por_id(self, autor_id):
        linhas = self._rodar(
            """SELECT id, nome, email, bio, funcao, cargo, registro, status, foto
               FROM autores WHERE id = %s""",
            (autor_id,), fetch=True,
        )
        return linhas[0] if linhas else None

    def autor_email_em_uso(self, email, ignorar_id=None) -> bool:
        linhas = self._rodar(
            "SELECT id FROM autores WHERE email = %s AND id <> %s LIMIT 1",
            (email, ignorar_id if ignorar_id is not None else 0), fetch=True,
        )
        return bool(linhas)

    def criar_autor(self, nome, email=None, bio=None, funcao="reporter",
                    cargo=None, registro=None, status="ativo", foto=None):
        """Insere o autor e devolve o id gerado."""
        r = self._rodar(
            """INSERT INTO autores (nome, email, bio, funcao, cargo, registro, status, foto)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (nome, email, bio, funcao, cargo, registro, status, foto), commit=True,
        )
        return r["id"]

    def atualizar_autor(self, autor_id, nome, email=None, bio=None, funcao="reporter",
                        cargo=None, registro=None, status="ativo", foto=None):
        self._rodar(
            """UPDATE autores
               SET nome = %s, email = %s, bio = %s, funcao = %s, cargo = %s,
                   registro = %s, status = %s, foto = %s
               WHERE id = %s""",
            (nome, email, bio, funcao, cargo, registro, status, foto, autor_id), commit=True,
        )

    def contar_noticias_do_autor(self, autor_id) -> int:
        linhas = self._rodar(
            "SELECT COUNT(*) AS total FROM noticias WHERE autor_id = %s",
            (autor_id,), fetch=True,
        )
        return int(linhas[0]["total"])

    def listar_noticias_do_autor(self, autor_id):
        """Matérias de um autor (botão 'Ver matérias' do cartão)."""
        return self._rodar(
            """SELECT n.id, n.titulo, c.nome AS categoria, n.data_publicacao
               FROM noticias n JOIN categorias c ON c.id = n.categoria_id
               WHERE n.autor_id = %s
               ORDER BY n.data_publicacao DESC, n.id DESC""",
            (autor_id,), fetch=True,
        )

    def excluir_autor(self, autor_id):
        self._rodar("DELETE FROM autores WHERE id = %s", (autor_id,), commit=True)

    # ---------- Estatísticas para o gráfico ----------
    def contar_noticias_por_categoria(self):
        query = """SELECT c.nome AS categoria, COUNT(n.id) AS total
                   FROM categorias c
                   LEFT JOIN noticias n ON n.categoria_id = c.id
                   GROUP BY c.nome
                   ORDER BY total DESC"""
        return self._executar(query, fetch=True) or []

    # ---------- Previsão do tempo: cache ----------
    def obter_cache_tempo(self, chave):
        linhas = self._rodar("SELECT atualizado_em, payload FROM tempo_cache WHERE chave = %s", (chave,), fetch=True)
        return linhas[0] if linhas else None

    def salvar_cache_tempo(self, chave, payload, quando):
        self._rodar("DELETE FROM tempo_cache WHERE chave = %s", (chave,), commit=True)
        self._rodar("INSERT INTO tempo_cache (chave, atualizado_em, payload) VALUES (%s, %s, %s)",
                    (chave, quando, payload), commit=True)

    # ---------- Clipping: itens coletados ----------
    def inserir_itens_clipping(self, itens, coletado_em) -> int:
        """Grava os itens novos (os que já existem por fonte+guid são ignorados). Devolve quantos entraram."""
        novos = 0
        for i in range(0, len(itens), 40):
            bloco = itens[i:i + 40]
            valores = ", ".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(bloco))
            params = []
            for it in bloco:
                params += [it["fonte_chave"], it.get("secao"), it["guid"], it["url"], it["titulo"], it.get("resumo"),
                           it.get("autor_fonte"), it.get("publicado_em"), it.get("imagem_url"), coletado_em]
            r = self._rodar(
                "INSERT IGNORE INTO clipping_itens (fonte_chave, secao, guid, url, titulo, resumo, autor_fonte, "
                "publicado_em, imagem_url, coletado_em) VALUES " + valores, tuple(params), commit=True)
            novos += max(0, r["linhas"] or 0)
        return novos

    def listar_itens_clipping(self, fontes, desde, limite=3000):
        """Itens das fontes desde certa data, com `noticia_id` preenchido se a matéria importada ainda existe."""
        if not fontes:
            return []
        marcas = ", ".join(["%s"] * len(fontes))
        return self._rodar(
            f"""SELECT i.id, i.fonte_chave, i.secao, i.guid, i.url, i.titulo, i.resumo, i.autor_fonte,
                       i.publicado_em, i.imagem_url, i.coletado_em, i.importado_noticia_id,
                       n.id AS noticia_id
                FROM clipping_itens i
                LEFT JOIN noticias n ON n.id = i.importado_noticia_id
                WHERE i.fonte_chave IN ({marcas})
                  AND (i.publicado_em >= %s OR (i.publicado_em IS NULL AND i.coletado_em >= %s))
                ORDER BY COALESCE(i.publicado_em, i.coletado_em) DESC
                LIMIT %s""",
            tuple(fontes) + (desde, desde, int(limite)), fetch=True)

    def buscar_item_clipping(self, item_id):
        """Item do clipping com `noticia_id` preenchido só se a matéria importada ainda existe."""
        linhas = self._rodar(
            """SELECT i.id, i.importado_noticia_id, n.id AS noticia_id
               FROM clipping_itens i LEFT JOIN noticias n ON n.id = i.importado_noticia_id
               WHERE i.id = %s""", (item_id,), fetch=True)
        return linhas[0] if linhas else None

    def marcar_item_clipping_importado(self, item_id, noticia_id):
        self._rodar("UPDATE clipping_itens SET importado_noticia_id = %s WHERE id = %s",
                    (noticia_id, item_id), commit=True)

    def purgar_itens_clipping(self, antes):
        """Apaga itens coletados antes da data que nunca viraram matéria."""
        self._rodar("DELETE FROM clipping_itens WHERE importado_noticia_id IS NULL AND coletado_em < %s",
                    (antes,), commit=True)

    def obter_estados_feeds(self, chaves) -> dict:
        if not chaves:
            return {}
        marcas = ", ".join(["%s"] * len(chaves))
        linhas = self._rodar(
            f"SELECT chave, etag, last_modified, ultima_coleta, ultimo_status FROM clipping_feeds_estado "
            f"WHERE chave IN ({marcas})", tuple(chaves), fetch=True)
        return {l["chave"]: l for l in linhas}

    def salvar_estado_feed(self, chave, url, etag, last_modified, quando, status):
        self._rodar("DELETE FROM clipping_feeds_estado WHERE chave = %s", (chave,), commit=True)
        self._rodar(
            "INSERT INTO clipping_feeds_estado (chave, url, etag, last_modified, ultima_coleta, ultimo_status) "
            "VALUES (%s, %s, %s, %s, %s, %s)", (chave, url[:1000], etag, last_modified, quando, (status or "")[:255]),
            commit=True)

    # ---------- Clipping: feeds próprios ----------
    def listar_feeds_proprios(self, usuario_id):
        return self._rodar("SELECT id, nome, url, secao, criado_em FROM clipping_feeds_proprios "
                           "WHERE usuario_id = %s ORDER BY nome", (usuario_id,), fetch=True)

    def criar_feed_proprio(self, usuario_id, nome, url, secao, criado_em):
        return self._rodar(
            "INSERT INTO clipping_feeds_proprios (usuario_id, nome, url, secao, criado_em) VALUES (%s, %s, %s, %s, %s)",
            (usuario_id, nome, url, secao, criado_em), commit=True)["id"]

    def excluir_feed_proprio(self, usuario_id, feed_id):
        self._rodar("DELETE FROM clipping_feeds_proprios WHERE id = %s AND usuario_id = %s",
                    (feed_id, usuario_id), commit=True)

    # ---------- Clipping: importações salvas e histórico ----------
    CAMPOS_IMPORTACAO = ("nome", "fontes", "secoes", "palavras_incluir", "palavras_excluir", "periodo_horas",
                         "limite_por_fonte", "so_com_imagem", "ordem", "categoria_id", "autor_id",
                         "status_destino", "automatica")

    def listar_importacoes_salvas(self, usuario_id):
        return self._rodar("SELECT * FROM importacoes_salvas WHERE usuario_id = %s ORDER BY nome",
                           (usuario_id,), fetch=True)

    def buscar_importacao_salva(self, importacao_id):
        linhas = self._rodar("SELECT * FROM importacoes_salvas WHERE id = %s", (importacao_id,), fetch=True)
        return linhas[0] if linhas else None

    def criar_importacao_salva(self, usuario_id, dados: dict):
        campos = list(self.CAMPOS_IMPORTACAO)
        r = self._rodar(
            f"INSERT INTO importacoes_salvas (usuario_id, {', '.join(campos)}) "
            f"VALUES (%s, {', '.join(['%s'] * len(campos))})",
            (usuario_id,) + tuple(dados.get(c) for c in campos), commit=True)
        return r["id"]

    def atualizar_importacao_salva(self, importacao_id, dados: dict):
        campos = list(self.CAMPOS_IMPORTACAO)
        self._rodar(
            "UPDATE importacoes_salvas SET " + ", ".join(f"{c} = %s" for c in campos) + " WHERE id = %s",
            tuple(dados.get(c) for c in campos) + (importacao_id,), commit=True)

    def excluir_importacao_salva(self, importacao_id):
        self._rodar("DELETE FROM importacoes_salvas WHERE id = %s", (importacao_id,), commit=True)

    def marcar_execucao_importacao(self, importacao_id, quando):
        self._rodar("UPDATE importacoes_salvas SET ultima_execucao = %s WHERE id = %s",
                    (quando, importacao_id), commit=True)

    def registrar_historico_clipping(self, usuario_id, quando, origem, nome, importadas, existentes, falhas, fontes):
        self._rodar(
            "INSERT INTO clipping_historico (usuario_id, quando, origem, nome, importadas, existentes, falhas, fontes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (usuario_id, quando, origem, nome, importadas, existentes, falhas, (fontes or "")[:500]), commit=True)

    def listar_historico_clipping(self, limite=20):
        return self._rodar("SELECT * FROM clipping_historico ORDER BY quando DESC, id DESC LIMIT %s",
                           (int(limite),), fetch=True)

    def buscar_autor_por_nome(self, nome):
        linhas = self._rodar("SELECT id, nome FROM autores WHERE nome = %s LIMIT 1", (nome,), fetch=True)
        return linhas[0] if linhas else None
