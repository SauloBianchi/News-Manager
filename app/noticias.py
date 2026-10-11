"""
noticias.py
Camada de regras de negócio (backend) do CRUD de Notícias, montada a partir
das telas "Notícias", "Nova Matéria" e "Leitura da Matéria" do protótipo
Stitch.

Segue o mesmo padrão de app/cadastros.py: a interface chama o NoticiaService,
que valida os dados, aplica as regras e devolve sempre um `Resultado` com a
mensagem pronta para mostrar ao usuário.

Regras principais:
- título obrigatório, de 5 a 120 caracteres (o layout mostra "0 / 120");
- categoria e autor precisam existir;
- rascunho pode ter o corpo vazio; matéria em revisão ou publicada precisa
  de pelo menos 30 caracteres de texto;
- só matéria publicada pode ser "manchete de capa" (destaque);
- etiquetas (#Tributação, #Mercado...) são normalizadas: sem repetição,
  no máximo 8, cada uma com até 30 caracteres.

Exemplo:

    servico = NoticiaService(db, logger)
    r = servico.criar("Título da matéria", categoria_id=1, autor_id=2,
                      conteudo="Texto...", status="publicado")
    messagebox.showinfo("Notícias", r.mensagem) if r.ok else messagebox.showwarning("Notícias", r.mensagem)
"""

import math
import re
from datetime import date, datetime

from .cadastros import Resultado, _ServicoBase, _limpar
from .database import ErroBanco
from .texto_rico import caminhos_de_imagens

# chave gravada no banco -> rótulo mostrado na tela
STATUS_NOTICIA = {
    "rascunho": "Rascunho",
    "em_pauta": "Em Pauta",
    "revisao": "Revisão",
    "publicado": "Publicado",
}
ORDENS_NOTICIA = {
    "recentes": "Mais Recentes",
    "antigas": "Mais Antigas",
    "lidas": "Mais Lidas",
    "titulo": "Título (A–Z)",
}

FORMATOS_DATA = ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
FORMATO_DATA_TELA = "%d/%m/%Y %H:%M"


# ---------------------------------------------------------------------------
# Utilitários de texto (também usados pela tela: contador de palavras etc.)
# ---------------------------------------------------------------------------
def contar_palavras(texto: str) -> int:
    return len((texto or "").split())


def tempo_leitura_min(texto: str, palavras_por_minuto: int = 200) -> int:
    """Estimativa de leitura em minutos (mínimo 1)."""
    return max(1, math.ceil(contar_palavras(texto) / palavras_por_minuto))


def lista_etiquetas(etiquetas) -> list:
    """'reforma,mercado' -> ['reforma', 'mercado']."""
    return [e for e in (etiquetas or "").split(",") if e]


def _normalizar_etiquetas(texto):
    """Devolve (etiquetas_em_string|None, erro|None). Aceita vírgula, ponto e
    vírgula ou espaço como separador e '#' opcional."""
    unicas = []
    for pedaco in re.split(r"[,;\s]+", texto or ""):
        etiqueta = pedaco.strip().lstrip("#")
        if not etiqueta:
            continue
        if len(etiqueta) > 30:
            return None, "Cada etiqueta pode ter no máximo 30 caracteres."
        if etiqueta.lower() not in (u.lower() for u in unicas):
            unicas.append(etiqueta)
    if len(unicas) > 8:
        return None, "Use no máximo 8 etiquetas."
    return (",".join(unicas) or None), None


def interpretar_data(valor):
    """Converte texto/date/datetime em datetime (sem segundos). None se inválido."""
    if isinstance(valor, datetime):
        return valor.replace(second=0, microsecond=0)
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    texto = (valor or "").strip() if isinstance(valor, str) else ""
    for formato in FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


# =============================================================================
# Serviço
# =============================================================================
class NoticiaService(_ServicoBase):
    TITULO_MIN, TITULO_MAX = 5, 120
    SUBTITULO_MAX = 300
    LEGENDA_MAX = 255
    CREDITO_MAX = 120
    CONTEUDO_MIN_PUBLICACAO = 30
    CONTEUDO_MAX = 50000

    # ---------- validação ----------
    def _validar(self, dados: dict):
        """Normaliza os campos e devolve (dados_limpos, mensagem_de_erro|None)."""
        d = {
            "titulo": _limpar(dados.get("titulo")),
            "subtitulo": _limpar(dados.get("subtitulo")) or None,
            "conteudo": (dados.get("conteudo") or "").replace("\r\n", "\n").strip(),
            "status": dados.get("status") or "rascunho",
            "destaque": bool(dados.get("destaque")),
            "imagem": dados.get("imagem") or None,
        }
        d["imagem_legenda"] = (_limpar(dados.get("imagem_legenda")) or None) if d["imagem"] else None
        d["imagem_credito"] = (_limpar(dados.get("imagem_credito")) or None) if d["imagem"] else None
        if not d["titulo"]:
            return d, "Informe o título da matéria."
        if not self.TITULO_MIN <= len(d["titulo"]) <= self.TITULO_MAX:
            return d, f"O título deve ter entre {self.TITULO_MIN} e {self.TITULO_MAX} caracteres."
        if d["subtitulo"] and len(d["subtitulo"]) > self.SUBTITULO_MAX:
            return d, f"A linha fina pode ter no máximo {self.SUBTITULO_MAX} caracteres."
        if d["status"] not in STATUS_NOTICIA:
            return d, "Escolha um estado de publicação válido."
        if len(d["conteudo"]) > self.CONTEUDO_MAX:
            return d, f"O texto pode ter no máximo {self.CONTEUDO_MAX} caracteres."
        if d["status"] in ("revisao", "publicado") and len(d["conteudo"]) < self.CONTEUDO_MIN_PUBLICACAO:
            return d, (f"Para enviar à revisão ou publicar, o texto precisa ter pelo menos "
                       f"{self.CONTEUDO_MIN_PUBLICACAO} caracteres. Salve como rascunho para continuar depois.")
        if d["destaque"] and d["status"] != "publicado":
            return d, "Só matérias publicadas podem ser manchete de capa."

        try:
            d["categoria_id"] = int(dados.get("categoria_id"))
            d["autor_id"] = int(dados.get("autor_id"))
        except (TypeError, ValueError):
            return d, "Escolha a seção editorial e o jornalista da matéria."
        categoria = self.db.buscar_categoria_por_id(d["categoria_id"])
        if not categoria:
            return d, "A seção editorial escolhida não existe mais."
        autor = self.db.buscar_autor_por_id(d["autor_id"])
        if not autor:
            return d, "O jornalista escolhido não existe mais."
        d["_categoria"], d["_autor"] = categoria["nome"], autor["nome"]

        data_informada = dados.get("data")
        if data_informada in (None, ""):
            d["data"] = datetime.now().replace(second=0, microsecond=0)
        else:
            d["data"] = interpretar_data(data_informada)
            if d["data"] is None:
                return d, "Data inválida. Use o formato dd/mm/aaaa hh:mm (ex.: 24/10/2024 08:30)."

        d["etiquetas"], erro = _normalizar_etiquetas(dados.get("etiquetas"))
        if erro:
            return d, erro

        if d["imagem_legenda"] and len(d["imagem_legenda"]) > self.LEGENDA_MAX:
            return d, f"A legenda da fotografia pode ter no máximo {self.LEGENDA_MAX} caracteres."
        if d["imagem_credito"] and len(d["imagem_credito"]) > self.CREDITO_MAX:
            return d, f"O crédito da fotografia pode ter no máximo {self.CREDITO_MAX} caracteres."
        erro_imagem = self._checar_imagem(d["imagem"])
        if erro_imagem:
            return d, erro_imagem
        return d, None

    @staticmethod
    def _montar_dados(titulo, categoria_id, autor_id, conteudo, subtitulo, status,
                      destaque, etiquetas, data, imagem=None, imagem_legenda="",
                      imagem_credito=""):
        return dict(titulo=titulo, categoria_id=categoria_id, autor_id=autor_id,
                    conteudo=conteudo, subtitulo=subtitulo, status=status,
                    destaque=destaque, etiquetas=etiquetas, data=data, imagem=imagem,
                    imagem_legenda=imagem_legenda, imagem_credito=imagem_credito)

    @staticmethod
    def _mensagem_sucesso(d, acao):
        if d["status"] == "publicado":
            return f"Matéria \"{d['titulo']}\" {'publicada' if acao == 'criada' else 'atualizada'}."
        return f"Matéria \"{d['titulo']}\" salva como {STATUS_NOTICIA[d['status']].lower()}."

    # ---------- leitura ----------
    def listar(self, termo: str = "", categoria_id=None, status: str = "",
               ordem: str = "recentes", pagina: int = 1, por_pagina: int = 6) -> Resultado:
        """Feed paginado. `dados` = {itens, total, pagina, paginas, por_pagina}.
        Se `pagina` passar do limite, é ajustada para a última."""
        termo = _limpar(termo) or None
        categoria_id = int(categoria_id) if categoria_id else None
        status = status or None
        por_pagina = max(1, int(por_pagina))
        try:
            total = self.db.contar_noticias(termo, categoria_id, status)
            paginas = max(1, math.ceil(total / por_pagina))
            pagina = min(max(1, int(pagina)), paginas)
            itens = self.db.listar_noticias_detalhado(
                termo, categoria_id, status, ordem, por_pagina, (pagina - 1) * por_pagina)
        except ErroBanco as e:
            return self._falha_banco("Erro ao listar notícias", e)
        dados = dict(itens=itens, total=total, pagina=pagina, paginas=paginas, por_pagina=por_pagina)
        return Resultado(True, f"{total} matéria(s).", dados)

    def obter(self, noticia_id: int) -> Resultado:
        try:
            noticia = self.db.buscar_noticia_por_id(noticia_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao buscar notícia", e)
        if not noticia:
            return Resultado(False, "Matéria não encontrada.")
        return Resultado(True, "", noticia)

    def relacionadas(self, noticia_id: int, limite: int = 3) -> Resultado:
        """Leituras suplementares: outras matérias publicadas da mesma editoria."""
        try:
            noticia = self.db.buscar_noticia_por_id(noticia_id)
            if not noticia:
                return Resultado(False, "Matéria não encontrada.")
            itens = self.db.listar_noticias_relacionadas(noticia_id, noticia["categoria_id"], limite)
        except ErroBanco as e:
            return self._falha_banco("Erro ao buscar leituras suplementares", e)
        return Resultado(True, "", itens)

    def resumo(self) -> Resultado:
        """Números do painel lateral 'Cadência da Tiragem'."""
        try:
            por_status = {chave: 0 for chave in STATUS_NOTICIA}
            for linha in self.db.contar_noticias_por_status():
                por_status[linha["status"]] = int(linha["total"])
            distribuicao = self.db.contar_publicadas_por_categoria(5)
            leituras = self.db.somar_leituras()
        except ErroBanco as e:
            return self._falha_banco("Erro ao calcular o resumo das notícias", e)
        dados = dict(
            total=sum(por_status.values()),
            publicadas=por_status["publicado"],
            pendentes_revisao=por_status["revisao"],
            por_status=por_status,
            distribuicao=[dict(categoria=l["categoria"], cor=l["cor"], total=int(l["total"]))
                          for l in distribuicao],
            leituras=leituras,
        )
        return Resultado(True, "", dados)

    # ---------- escrita ----------
    def criar(self, titulo: str, categoria_id, autor_id, conteudo: str = "", subtitulo: str = "",
              status: str = "rascunho", destaque: bool = False, etiquetas: str = "",
              data=None, imagem: str = None, imagem_legenda: str = "",
              imagem_credito: str = "") -> Resultado:
        try:
            d, erro = self._validar(self._montar_dados(
                titulo, categoria_id, autor_id, conteudo, subtitulo, status, destaque, etiquetas,
                data, imagem, imagem_legenda, imagem_credito))
            if erro:
                return Resultado(False, erro)
            novo_id = self.db.criar_noticia(
                d["titulo"], d["conteudo"], d["categoria_id"], d["autor_id"], d["data"],
                d["subtitulo"], d["status"], d["destaque"], d["etiquetas"],
                d["imagem"], d["imagem_legenda"], d["imagem_credito"])
        except ErroBanco as e:
            return self._falha_banco("Erro ao criar notícia", e)
        self.logger.info(f"Notícia criada: {d['titulo']} (id {novo_id}, {d['status']})")
        self._evento("evento_materia", novo_id, d["titulo"], d["status"], d["_categoria"], d["_autor"], d["etiquetas"])
        return Resultado(True, self._mensagem_sucesso(d, "criada"), novo_id)

    def atualizar(self, noticia_id: int, titulo: str, categoria_id, autor_id, conteudo: str = "",
                  subtitulo: str = "", status: str = "rascunho", destaque: bool = False,
                  etiquetas: str = "", data=None, imagem: str = None,
                  imagem_legenda: str = "", imagem_credito: str = "") -> Resultado:
        try:
            atual = self.db.buscar_noticia_por_id(noticia_id)
            if not atual:
                return Resultado(False, "Matéria não encontrada.")
            if data in (None, ""):
                data = atual["data_publicacao"]  # editar sem mexer na data mantém a original
            d, erro = self._validar(self._montar_dados(
                titulo, categoria_id, autor_id, conteudo, subtitulo, status, destaque, etiquetas,
                data, imagem, imagem_legenda, imagem_credito))
            if erro:
                return Resultado(False, erro)
            self.db.atualizar_noticia(
                noticia_id, d["titulo"], d["conteudo"], d["categoria_id"], d["autor_id"], d["data"],
                d["subtitulo"], d["status"], d["destaque"], d["etiquetas"],
                d["imagem"], d["imagem_legenda"], d["imagem_credito"])
        except ErroBanco as e:
            return self._falha_banco("Erro ao atualizar notícia", e)
        if atual.get("imagem") != d["imagem"]:
            self._descartar_imagem(atual.get("imagem"))   # a capa antiga deixou de ser usada
        # imagens do meio do texto que saíram da matéria
        for caminho in caminhos_de_imagens(atual.get("conteudo")) - caminhos_de_imagens(d["conteudo"]):
            self._descartar_imagem(caminho)
        self.logger.info(f"Notícia {noticia_id} atualizada: {d['titulo']} ({d['status']})")
        if atual.get("status") != d["status"]:   # só avisa quando o estado da matéria muda
            self._evento("evento_materia", noticia_id, d["titulo"], d["status"], d["_categoria"], d["_autor"],
                         d["etiquetas"])
        return Resultado(True, self._mensagem_sucesso(d, "atualizada"), noticia_id)

    def excluir(self, noticia_id: int) -> Resultado:
        try:
            noticia = self.db.buscar_noticia_por_id(noticia_id)
            if not noticia:
                return Resultado(False, "Matéria não encontrada.")
            self.db.excluir_noticia(noticia_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao excluir notícia", e)
        self._descartar_imagem(noticia.get("imagem"))
        for caminho in caminhos_de_imagens(noticia.get("conteudo")):
            self._descartar_imagem(caminho)
        self.logger.info(f"Notícia {noticia_id} excluída: {noticia['titulo']}")
        self._evento("evento_materia_excluida", noticia["titulo"], noticia.get("categoria"))
        return Resultado(True, f"Matéria \"{noticia['titulo']}\" excluída.")

    def registrar_leitura(self, noticia_id: int) -> Resultado:
        """Chamado quando alguém abre a matéria para ler."""
        try:
            self.db.registrar_leitura(noticia_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao registrar leitura", e)
        return Resultado(True)
