"""
cadastros.py
Camada de regras de negócio (backend) do CRUD de Categorias e Autores,
montada a partir das telas "Categorias" e "Autores" do protótipo Stitch.

A interface (telas_cadastros.py) não fala direto com o banco: ela chama
CategoriaService / AutorService, que validam os dados, aplicam as regras
(nome único, e-mail válido, não excluir quem tem notícias...) e devolvem
sempre um `Resultado` com a mensagem pronta para exibir ao usuário.

Exemplo:

    servico = CategoriaService(db, logger)
    r = servico.criar("Política", "Cobertura de plenário...", cor="rubro")
    if r.ok:
        messagebox.showinfo("Categorias", r.mensagem)
    else:
        messagebox.showwarning("Categorias", r.mensagem)
"""

import re
from dataclasses import dataclass
from typing import Any

from .database import DatabaseManager, ErroBanco
from .logger import Logger


# ---------------------------------------------------------------------------
# Listas fechadas usadas nos formulários (chave gravada no banco -> rótulo)
# ---------------------------------------------------------------------------
CORES_CATEGORIA = {
    "rubro": "Rubro Manchete (Primário)",
    "azul": "Azul Ultramarino (Diplomacia)",
    "sepia": "Sépia Arquivo (Cultura)",
    "carvao": "Preto Carvão (Opinião & Crônica)",
}
STATUS_CATEGORIA = {"ativa": "Ativa", "em_revisao": "Em Revisão"}

FUNCOES_AUTOR = {
    "reporter": "Repórter",
    "colunista": "Colunista",
    "editor_setorial": "Editor Setorial",
    "correspondente": "Correspondente",
}
# Rótulo no plural, usado nos filtros da tela ("Repórteres (16)")
FUNCOES_AUTOR_PLURAL = {
    "reporter": "Repórteres",
    "colunista": "Colunistas",
    "editor_setorial": "Editores Setoriais",
    "correspondente": "Correspondentes",
}
STATUS_AUTOR = {"ativo": "Ativo na Galé", "em_pauta_externa": "Em Pauta Externa"}


@dataclass
class Resultado:
    """Retorno padrão das operações: sucesso/falha, mensagem para o usuário
    e (quando fizer sentido) os dados — lista de registros, id criado etc."""
    ok: bool
    mensagem: str = ""
    dados: Any = None


def _limpar(texto) -> str:
    """Tira espaços das pontas e junta espaços repetidos no meio."""
    return " ".join((texto or "").split())


class _ServicoBase:
    """Trecho comum aos serviços: banco, logger e tratamento de ErroBanco."""

    def __init__(self, db: DatabaseManager, logger: Logger, midia=None):
        self.db = db
        self.logger = logger
        # GerenciadorMidia (app/midia.py): se vier, o serviço confere se a
        # imagem existe e apaga do disco os arquivos que deixam de ser usados.
        self.midia = midia

    def _checar_imagem(self, caminho):
        """Devolve mensagem de erro se o caminho da imagem for inválido, senão None."""
        if not caminho:
            return None
        if len(caminho) > 255:
            return "Caminho da imagem muito longo."
        if self.midia is not None and not self.midia.existe(caminho):
            return "Arquivo de imagem não encontrado. Escolha a imagem novamente."
        return None

    def _descartar_imagem(self, caminho):
        """Apaga o arquivo da pasta de mídia, a menos que outro registro ainda o use."""
        if not caminho or self.midia is None:
            return
        try:
            if self.db.imagem_em_uso(caminho):
                return
        except ErroBanco:
            return   # na dúvida, não apaga
        self.midia.remover(caminho)

    def _evento(self, funcao, *args, **kwargs):
        """Registra uma notificação (app/notificacoes.py) sem nunca atrapalhar a operação principal."""
        try:
            from . import notificacoes
            getattr(notificacoes, funcao)(self.db, self.logger, *args, **kwargs)
        except Exception as erro:
            self.logger.error("Erro ao registrar notificação", erro)

    def descartar_imagem_orfa(self, caminho):
        """Uso pelas telas: remove uma imagem provisória que não foi para nenhum registro."""
        self._descartar_imagem(caminho)

    def _falha_banco(self, contexto: str, erro: ErroBanco) -> Resultado:
        self.logger.error(contexto, erro.original or erro)
        return Resultado(False, "Não foi possível concluir a operação: erro ao acessar o banco de dados.")


# =============================================================================
# Categorias
# =============================================================================
class CategoriaService(_ServicoBase):
    NOME_MIN, NOME_MAX = 2, 80
    DESCRICAO_MIN, DESCRICAO_MAX = 5, 255

    def _validar(self, nome, descricao, cor, status, ignorar_id=None):
        """Devolve (nome, descricao, mensagem_de_erro|None)."""
        nome = _limpar(nome)
        descricao = _limpar(descricao)
        if not nome:
            return nome, descricao, "Informe o nome do caderno / editoria."
        if not self.NOME_MIN <= len(nome) <= self.NOME_MAX:
            return nome, descricao, f"O nome deve ter entre {self.NOME_MIN} e {self.NOME_MAX} caracteres."
        if not descricao:
            return nome, descricao, "Informe o resumo editorial da seção."
        if not self.DESCRICAO_MIN <= len(descricao) <= self.DESCRICAO_MAX:
            return nome, descricao, (
                f"O resumo editorial deve ter entre {self.DESCRICAO_MIN} e {self.DESCRICAO_MAX} caracteres."
            )
        if cor not in CORES_CATEGORIA:
            return nome, descricao, "Escolha uma cor (matiz tipográfica) válida."
        if status not in STATUS_CATEGORIA:
            return nome, descricao, "Escolha um status válido."
        if self.db.categoria_nome_em_uso(nome, ignorar_id):
            return nome, descricao, f"Já existe uma categoria chamada \"{nome}\"."
        return nome, descricao, None

    def listar(self, termo: str = "") -> Resultado:
        """Categorias com total de notícias; `termo` filtra por nome/descrição."""
        try:
            linhas = self.db.listar_categorias_detalhado(_limpar(termo) or None)
            return Resultado(True, f"{len(linhas)} categoria(s).", linhas)
        except ErroBanco as e:
            return self._falha_banco("Erro ao listar categorias", e)

    def resumo(self) -> Resultado:
        """Números dos três cartões do topo da tela: editorias ativas,
        caderno mais ativo e média de matérias por caderno."""
        r = self.listar()
        if not r.ok:
            return r
        linhas = r.dados
        total_noticias = sum(int(c["total_noticias"]) for c in linhas)
        mais_ativa = None
        if linhas and total_noticias:
            top = max(linhas, key=lambda c: int(c["total_noticias"]))
            mais_ativa = {
                "nome": top["nome"],
                "total": int(top["total_noticias"]),
                "percentual": round(100 * int(top["total_noticias"]) / total_noticias, 1),
            }
        dados = {
            "total": len(linhas),
            "ativas": sum(1 for c in linhas if c["status"] == "ativa"),
            "em_revisao": sum(1 for c in linhas if c["status"] == "em_revisao"),
            "total_noticias": total_noticias,
            "mais_ativa": mais_ativa,
            "media_por_caderno": round(total_noticias / len(linhas)) if linhas else 0,
        }
        return Resultado(True, "", dados)

    def obter(self, categoria_id: int) -> Resultado:
        try:
            categoria = self.db.buscar_categoria_por_id(categoria_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao buscar categoria", e)
        if not categoria:
            return Resultado(False, "Categoria não encontrada.")
        return Resultado(True, "", categoria)

    def criar(self, nome: str, descricao: str, cor: str = "rubro", status: str = "ativa") -> Resultado:
        try:
            nome, descricao, erro = self._validar(nome, descricao, cor, status)
            if erro:
                return Resultado(False, erro)
            novo_id = self.db.criar_categoria(nome, descricao, cor, status)
        except ErroBanco as e:
            return self._falha_banco("Erro ao criar categoria", e)
        self.logger.info(f"Categoria criada: {nome} (id {novo_id})")
        self._evento("evento_estrutura", "criada", "categoria", nome, "categoria", novo_id)
        return Resultado(True, f"Editoria \"{nome}\" cadastrada.", novo_id)

    def atualizar(self, categoria_id: int, nome: str, descricao: str,
                  cor: str = "rubro", status: str = "ativa") -> Resultado:
        try:
            if not self.db.buscar_categoria_por_id(categoria_id):
                return Resultado(False, "Categoria não encontrada.")
            nome, descricao, erro = self._validar(nome, descricao, cor, status, ignorar_id=categoria_id)
            if erro:
                return Resultado(False, erro)
            self.db.atualizar_categoria(categoria_id, nome, descricao, cor, status)
        except ErroBanco as e:
            return self._falha_banco("Erro ao atualizar categoria", e)
        self.logger.info(f"Categoria {categoria_id} atualizada: {nome}")
        self._evento("evento_estrutura", "atualizada", "categoria", nome, "categoria", categoria_id)
        return Resultado(True, f"Editoria \"{nome}\" atualizada.", categoria_id)

    def excluir(self, categoria_id: int) -> Resultado:
        """Não exclui categorias que ainda têm notícias (a FK impediria de qualquer forma)."""
        try:
            categoria = self.db.buscar_categoria_por_id(categoria_id)
            if not categoria:
                return Resultado(False, "Categoria não encontrada.")
            total = self.db.contar_noticias_da_categoria(categoria_id)
            if total:
                return Resultado(
                    False,
                    f"A editoria \"{categoria['nome']}\" tem {total} matéria(s) e não pode ser "
                    "excluída. Reatribua ou exclua essas matérias primeiro.",
                )
            self.db.excluir_categoria(categoria_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao excluir categoria", e)
        self.logger.info(f"Categoria {categoria_id} excluída: {categoria['nome']}")
        self._evento("evento_estrutura", "excluida", "categoria", categoria["nome"])
        return Resultado(True, f"Editoria \"{categoria['nome']}\" excluída.")


# =============================================================================
# Autores
# =============================================================================
class AutorService(_ServicoBase):
    NOME_MIN, NOME_MAX = 2, 120
    EMAIL_MAX = 150
    CARGO_MAX = 120
    REGISTRO_MAX = 40
    BIO_MAX = 1000
    _REGEX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def _validar(self, dados: dict, ignorar_id=None):
        """Normaliza os campos e devolve (dados_limpos, mensagem_de_erro|None).
        E-mail, cargo, registro e bio são opcionais."""
        d = {
            "nome": _limpar(dados.get("nome")),
            "email": (dados.get("email") or "").strip().lower() or None,
            "funcao": dados.get("funcao") or "reporter",
            "cargo": _limpar(dados.get("cargo")) or None,
            "registro": _limpar(dados.get("registro")) or None,
            "status": dados.get("status") or "ativo",
            "bio": (dados.get("bio") or "").strip() or None,
            "foto": dados.get("foto") or None,
        }
        if not d["nome"]:
            return d, "Informe o nome completo do jornalista."
        if not self.NOME_MIN <= len(d["nome"]) <= self.NOME_MAX:
            return d, f"O nome deve ter entre {self.NOME_MIN} e {self.NOME_MAX} caracteres."
        if d["email"]:
            if len(d["email"]) > self.EMAIL_MAX or not self._REGEX_EMAIL.match(d["email"]):
                return d, "Informe um e-mail válido (ex.: nome@dominio.com)."
            if self.db.autor_email_em_uso(d["email"], ignorar_id):
                return d, "Já existe um autor cadastrado com esse e-mail."
        if d["funcao"] not in FUNCOES_AUTOR:
            return d, "Escolha uma função válida."
        if d["status"] not in STATUS_AUTOR:
            return d, "Escolha um status válido."
        if d["cargo"] and len(d["cargo"]) > self.CARGO_MAX:
            return d, f"O cargo pode ter no máximo {self.CARGO_MAX} caracteres."
        if d["registro"] and len(d["registro"]) > self.REGISTRO_MAX:
            return d, f"O registro profissional pode ter no máximo {self.REGISTRO_MAX} caracteres."
        if d["bio"] and len(d["bio"]) > self.BIO_MAX:
            return d, f"A biografia pode ter no máximo {self.BIO_MAX} caracteres."
        erro_foto = self._checar_imagem(d["foto"])
        if erro_foto:
            return d, erro_foto
        return d, None

    def listar(self, termo: str = "", funcao: str = "") -> Resultado:
        """Autores com total de matérias e última publicação. `termo` filtra
        por nome/e-mail/cargo/registro/bio; `funcao` (opcional) por função."""
        try:
            linhas = self.db.listar_autores_detalhado(_limpar(termo) or None, funcao or None)
            return Resultado(True, f"{len(linhas)} autor(es).", linhas)
        except ErroBanco as e:
            return self._falha_banco("Erro ao listar autores", e)

    def contagem_por_funcao(self) -> Resultado:
        """Contagens dos filtros da tela: {'todos': 34, 'reporter': 16, ...}."""
        try:
            linhas = self.db.contar_autores_por_funcao()
        except ErroBanco as e:
            return self._falha_banco("Erro ao contar autores", e)
        contagem = {chave: 0 for chave in FUNCOES_AUTOR}
        for linha in linhas:
            contagem[linha["funcao"]] = int(linha["total"])
        contagem["todos"] = sum(contagem.values())
        return Resultado(True, "", contagem)

    def obter(self, autor_id: int) -> Resultado:
        try:
            autor = self.db.buscar_autor_por_id(autor_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao buscar autor", e)
        if not autor:
            return Resultado(False, "Autor não encontrado.")
        return Resultado(True, "", autor)

    def materias_do_autor(self, autor_id: int) -> Resultado:
        try:
            return Resultado(True, "", self.db.listar_noticias_do_autor(autor_id))
        except ErroBanco as e:
            return self._falha_banco("Erro ao listar matérias do autor", e)

    def criar(self, nome: str, email: str = "", funcao: str = "reporter", cargo: str = "",
              registro: str = "", status: str = "ativo", bio: str = "", foto: str = None) -> Resultado:
        try:
            d, erro = self._validar(dict(nome=nome, email=email, funcao=funcao, cargo=cargo,
                                         registro=registro, status=status, bio=bio, foto=foto))
            if erro:
                return Resultado(False, erro)
            novo_id = self.db.criar_autor(d["nome"], d["email"], d["bio"], d["funcao"],
                                          d["cargo"], d["registro"], d["status"], d["foto"])
        except ErroBanco as e:
            return self._falha_banco("Erro ao criar autor", e)
        self.logger.info(f"Autor criado: {d['nome']} (id {novo_id})")
        self._evento("evento_estrutura", "criada", "autor", d["nome"], "autor", novo_id)
        return Resultado(True, f"Credencial de \"{d['nome']}\" registrada.", novo_id)

    def atualizar(self, autor_id: int, nome: str, email: str = "", funcao: str = "reporter",
                  cargo: str = "", registro: str = "", status: str = "ativo",
                  bio: str = "", foto: str = None) -> Resultado:
        try:
            atual = self.db.buscar_autor_por_id(autor_id)
            if not atual:
                return Resultado(False, "Autor não encontrado.")
            d, erro = self._validar(dict(nome=nome, email=email, funcao=funcao, cargo=cargo,
                                         registro=registro, status=status, bio=bio, foto=foto),
                                    ignorar_id=autor_id)
            if erro:
                return Resultado(False, erro)
            self.db.atualizar_autor(autor_id, d["nome"], d["email"], d["bio"], d["funcao"],
                                    d["cargo"], d["registro"], d["status"], d["foto"])
        except ErroBanco as e:
            return self._falha_banco("Erro ao atualizar autor", e)
        if atual.get("foto") != d["foto"]:
            self._descartar_imagem(atual.get("foto"))   # a foto antiga deixou de ser usada
        self.logger.info(f"Autor {autor_id} atualizado: {d['nome']}")
        self._evento("evento_estrutura", "atualizada", "autor", d["nome"], "autor", autor_id)
        return Resultado(True, f"Credencial de \"{d['nome']}\" atualizada.", autor_id)

    def excluir(self, autor_id: int) -> Resultado:
        """Não exclui autores que ainda têm matérias publicadas."""
        try:
            autor = self.db.buscar_autor_por_id(autor_id)
            if not autor:
                return Resultado(False, "Autor não encontrado.")
            total = self.db.contar_noticias_do_autor(autor_id)
            if total:
                return Resultado(
                    False,
                    f"O jornalista \"{autor['nome']}\" tem {total} matéria(s) e não pode ser "
                    "excluído. Reatribua ou exclua essas matérias primeiro.",
                )
            self.db.excluir_autor(autor_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao excluir autor", e)
        self._descartar_imagem(autor.get("foto"))
        self.logger.info(f"Autor {autor_id} excluído: {autor['nome']}")
        self._evento("evento_estrutura", "excluida", "autor", autor["nome"])
        return Resultado(True, f"Jornalista \"{autor['nome']}\" excluído.")
