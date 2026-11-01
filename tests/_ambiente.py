"""
Preparação comum dos testes (rode da raiz do projeto: python -m unittest discover -s tests -t .).

- Garante que `mysql.connector` exista: se o driver não estiver instalado, entra um
  substituto mínimo só para os módulos poderem ser importados (os testes nunca
  conversam com um MySQL real).
- `BancoSqlite`: DatabaseManager de teste que roda as consultas num SQLite em
  memória (traduz %s -> ? e INSERT IGNORE). Serve para exercitar a LÓGICA dos
  serviços; o SQL específico do MySQL/MariaDB NÃO é validado aqui (veja README).
"""

import os
import re
import sqlite3
import sys
import types
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

try:
    import mysql.connector  # noqa: F401
except ImportError:
    mysql = types.ModuleType("mysql")
    conector = types.ModuleType("mysql.connector")

    class Error(Exception):
        pass

    conector.Error = Error
    conector.connect = lambda *a, **k: (_ for _ in ()).throw(Error("sem driver MySQL no ambiente de teste"))
    mysql.connector = conector
    sys.modules["mysql"], sys.modules["mysql.connector"] = mysql, conector

def _usar_tk_falso():
    from tests import _tkfalso
    _tkfalso.instalar()
    return True


if os.environ.get("NM_TK_FALSO") == "1":   # forçado pelo teste de telas (roda em outro processo)
    TK_FALSO = _usar_tk_falso()
else:
    try:
        import tkinter  # noqa: F401
        TK_FALSO = False
    except ImportError:       # ambiente sem Tk (servidor, CI): usa o Tk de mentira de tests/_tkfalso.py
        TK_FALSO = _usar_tk_falso()

from app.database import DatabaseManager, ErroBanco  # noqa: E402
from app.logger import Logger  # noqa: E402

FIXTURES = os.path.join(RAIZ, "tests", "fixtures")


def ler_fixture(nome, binario=True):
    with open(os.path.join(FIXTURES, nome), "rb" if binario else "r", **({} if binario else {"encoding": "utf-8"})) as f:
        return f.read()


class LoggerMudo:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


_ESQUEMA = """
CREATE TABLE categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE, descricao TEXT, cor TEXT DEFAULT 'rubro', status TEXT DEFAULT 'ativa');
CREATE TABLE autores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, email TEXT, bio TEXT, funcao TEXT DEFAULT 'reporter', cargo TEXT, registro TEXT, status TEXT DEFAULT 'ativo', foto TEXT);
CREATE TABLE noticias (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, subtitulo TEXT, conteudo TEXT, categoria_id INT, autor_id INT, data_publicacao TEXT, status TEXT DEFAULT 'publicado', destaque INT DEFAULT 0, etiquetas TEXT, leituras INT DEFAULT 0, imagem TEXT, imagem_legenda TEXT, imagem_credito TEXT, fonte_nome TEXT, fonte_url TEXT, fonte_guid TEXT);
CREATE TABLE preferencias_usuario (usuario_id INT, chave TEXT, valor TEXT, PRIMARY KEY (usuario_id, chave));
CREATE TABLE notificacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, titulo TEXT, mensagem TEXT, etiqueta TEXT, rodape TEXT, urgente INT DEFAULT 0, alvo_tipo TEXT, alvo_id INT, usuario_destino INT, ator TEXT, criado_em TEXT);
CREATE TABLE tempo_cache (chave TEXT PRIMARY KEY, atualizado_em TEXT, payload TEXT);
CREATE TABLE clipping_itens (id INTEGER PRIMARY KEY AUTOINCREMENT, fonte_chave TEXT, secao TEXT, guid TEXT, url TEXT, titulo TEXT, resumo TEXT, autor_fonte TEXT, publicado_em TEXT, imagem_url TEXT, coletado_em TEXT, importado_noticia_id INT, UNIQUE (fonte_chave, guid));
CREATE TABLE importacoes_salvas (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INT, nome TEXT, fontes TEXT, secoes TEXT, palavras_incluir TEXT, palavras_excluir TEXT, periodo_horas INT DEFAULT 24, limite_por_fonte INT DEFAULT 10, so_com_imagem INT DEFAULT 0, ordem TEXT DEFAULT 'recentes', categoria_id INT, autor_id INT, status_destino TEXT DEFAULT 'em_pauta', automatica INT DEFAULT 0, ultima_execucao TEXT);
CREATE TABLE clipping_historico (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INT, quando TEXT, origem TEXT, nome TEXT, importadas INT, existentes INT, falhas INT, fontes TEXT);
CREATE TABLE clipping_feeds_estado (chave TEXT PRIMARY KEY, url TEXT, etag TEXT, last_modified TEXT, ultima_coleta TEXT, ultimo_status TEXT);
CREATE TABLE clipping_feeds_proprios (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INT, nome TEXT, url TEXT, secao TEXT, criado_em TEXT);
"""
_COLUNAS_DATA = {"data_publicacao", "atualizado_em", "criado_em", "publicado_em", "coletado_em", "ultima_coleta",
                 "ultima_execucao", "quando"}


def _converter(valor):
    return valor.strftime("%Y-%m-%d %H:%M:%S") if isinstance(valor, datetime) else valor


class BancoSqlite(DatabaseManager):
    """Banco de teste em memória. Só implementa o necessário para os serviços novos."""

    def __init__(self):
        super().__init__()
        self.logger = LoggerMudo()
        self.conexao_sqlite = sqlite3.connect(":memory:")
        self.conexao_sqlite.row_factory = sqlite3.Row
        self.conexao_sqlite.executescript(_ESQUEMA)
        self.connection = object()

    def conectar(self):
        return True

    def _rodar(self, query, params=None, fetch=False, commit=False):
        sql = query.replace("%s", "?").replace("INSERT IGNORE", "INSERT OR IGNORE")
        sql = re.sub(r"\bLIKE\b", "LIKE", sql)
        try:
            cur = self.conexao_sqlite.execute(sql, tuple(_converter(p) for p in (params or ())))
            if fetch:
                linhas = []
                for r in cur.fetchall():
                    d = dict(r)
                    for k in list(d):
                        if k in _COLUNAS_DATA and isinstance(d[k], str):
                            try:
                                d[k] = datetime.strptime(d[k][:19], "%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                pass
                    linhas.append(d)
                return linhas
            if commit:
                self.conexao_sqlite.commit()
            return {"id": cur.lastrowid, "linhas": cur.rowcount}
        except sqlite3.Error as e:
            raise ErroBanco("Erro no banco de teste.", e) from e

    # consultas de apoio dos serviços existentes, só o que os testes novos usam
    def buscar_categoria_por_id(self, categoria_id):
        l = self._rodar("SELECT * FROM categorias WHERE id = %s", (categoria_id,), fetch=True)
        return l[0] if l else None

    def buscar_autor_por_id(self, autor_id):
        l = self._rodar("SELECT * FROM autores WHERE id = %s", (autor_id,), fetch=True)
        return l[0] if l else None

    def listar_categorias(self):
        return self._rodar("SELECT * FROM categorias ORDER BY nome", fetch=True)

    def criar_autor(self, nome, email=None, bio=None, funcao="reporter", cargo=None, registro=None,
                    status="ativo", foto=None):
        return self._rodar("INSERT INTO autores (nome, email, bio, funcao, cargo, registro, status, foto) "
                           "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                           (nome, email, bio, funcao, cargo, registro, status, foto), commit=True)["id"]

    def autor_email_em_uso(self, email, ignorar_id=None):
        return False

    def criar_notificacao(self, tipo, titulo, mensagem=None, etiqueta=None, rodape=None, urgente=False,
                          alvo_tipo=None, alvo_id=None, usuario_destino=None, ator=None, criado_em=None):
        return self._rodar(
            "INSERT INTO notificacoes (tipo, titulo, mensagem, etiqueta, rodape, urgente, alvo_tipo, alvo_id, "
            "usuario_destino, ator, criado_em) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (tipo, titulo, mensagem, etiqueta, rodape, 1 if urgente else 0, alvo_tipo, alvo_id, usuario_destino,
             ator, criado_em or datetime.now()), commit=True)["id"]

    def criar_noticia(self, titulo, conteudo, categoria_id, autor_id, data_publicacao, subtitulo=None,
                      status="publicado", destaque=False, etiquetas=None, imagem=None, imagem_legenda=None,
                      imagem_credito=None, fonte_nome=None, fonte_url=None, fonte_guid=None):
        return self._rodar(
            "INSERT INTO noticias (titulo, subtitulo, conteudo, categoria_id, autor_id, data_publicacao, status, "
            "destaque, etiquetas, imagem, imagem_legenda, imagem_credito, fonte_nome, fonte_url, fonte_guid) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (titulo, subtitulo, conteudo, categoria_id, autor_id, data_publicacao, status, 1 if destaque else 0,
             etiquetas, imagem, imagem_legenda, imagem_credito, fonte_nome, fonte_url, fonte_guid), commit=True)["id"]

    def excluir_noticia(self, noticia_id):
        self._rodar("DELETE FROM noticias WHERE id = %s", (noticia_id,), commit=True)


def banco_com_base():
    """BancoSqlite com 4 editorias e 1 autor, como o schema.sql."""
    db = BancoSqlite()
    for nome in ("Política", "Esportes", "Tecnologia", "Economia", "Mundo"):
        db.conexao_sqlite.execute("INSERT INTO categorias (nome, descricao) VALUES (?, ?)", (nome, "Editoria de teste"))
    db.conexao_sqlite.execute("INSERT INTO autores (nome) VALUES ('Ernesto')")
    db.conexao_sqlite.commit()
    return db
