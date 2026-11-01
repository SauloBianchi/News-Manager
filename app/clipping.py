"""
clipping.py
Backend do "Clipping": traz para o NewsManager as notícias do dia de jornais
escolhidos pelo usuário, a partir dos feeds RSS/Atom oficiais, e as importa
como pautas (em_pauta por padrão; NUNCA publicadas sozinhas).

Regras legais e éticas (obrigatórias)
- Só título, resumo curto do próprio feed, data, link e nome da fonte. Nada de
  raspagem de páginas, de texto completo nem de download de imagens.
- Toda matéria importada leva "Fonte: [Jornal](link)" no texto E os campos
  próprios fonte_nome/fonte_url/fonte_guid (selo "Conteúdo externo" nas telas).
- User-Agent identificável (app/rede.py), no máximo UMA coleta por feed a cada
  15 minutos (dentro disso a prévia vem dos itens já guardados), no máximo 2
  conexões simultâneas por servidor e 4 no total.

Camadas e threads
- `coletar_feeds` só usa a rede: pode rodar em thread. NÃO toca no banco.
- Tudo o que usa o banco (ClippingService) roda na thread principal. A tela faz:
  preparar_coleta (banco) -> coletar_feeds (thread) -> concluir_coleta (banco).
  `buscar_agora` junta os três passos para testes, seed e execução síncrona.
"""

import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import rede
from .cadastros import AutorService, Resultado, _ServicoBase, _limpar
from .database import ErroBanco
from .feeds import ErroFeed, interpretar_feed
from .noticias import NoticiaService
from .notificacoes import registrar_evento, silenciar
from .rede import ErroRede, mensagem_http

CAMINHO_CATALOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config",
                                "fontes_noticias.json")
INTERVALO_MIN_COLETA_MIN = 15      # no máximo uma coleta por feed neste intervalo
MAX_CONEXOES = 4
MAX_CONEXOES_POR_SERVIDOR = 2
TENTATIVAS = 2
RETENCAO_ITENS_DIAS = 30
MAX_FEEDS_PROPRIOS = 20
STATUS_DESTINO = {"em_pauta": "Em Pauta", "rascunho": "Rascunho", "revisao": "Revisão"}   # nunca 'publicado'
PERIODOS = {"hoje": ("Hoje", 0), "24h": ("Últimas 24 horas", 24), "48h": ("Últimas 48 horas", 48),
            "7d": ("Últimos 7 dias", 168)}
ORDENS = {"recentes": "Mais recentes", "fonte": "Por jornal", "titulo": "Título (A–Z)"}
AVISO_TERCEIROS = "Conteúdo de terceiros — confira os termos de uso de cada jornal."
PREFIXO_AUTOR = "Clipping — "


def normalizar(texto) -> str:
    """Minúsculas e sem acentos, para comparar palavras."""
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def slug(texto) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-") or "geral"


def chave_url(url) -> str:
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def carregar_catalogo(caminho=None) -> list:
    """Fontes do config/fontes_noticias.json, já com 'chave_feed' em cada feed."""
    with open(caminho or CAMINHO_CATALOGO, encoding="utf-8") as f:
        dados = json.load(f)
    fontes = []
    for fonte in dados.get("fontes", []):
        fonte = dict(fonte)
        fonte["proprio"] = False
        feeds = []
        for feed in fonte.get("feeds", []):
            feed = dict(feed)
            feed["chave_feed"] = f"{fonte['chave']}:{slug(feed['secao'])}"
            feeds.append(feed)
        fonte["feeds"] = feeds
        fontes.append(fonte)
    return fontes


# ---------------------------------------------------------------------------
# Filtros (puros)
# ---------------------------------------------------------------------------
@dataclass
class FiltroClipping:
    fontes: list = field(default_factory=list)       # chaves dos jornais
    feeds: list = field(default_factory=list)        # chave_feed escolhidas (vazio = todas dos jornais)
    incluir: list = field(default_factory=list)      # basta UMA aparecer (aceita 'econom*')
    excluir: list = field(default_factory=list)      # nenhuma pode aparecer
    periodo_horas: int = 24                          # 0 = só hoje
    limite_por_fonte: int = 10
    so_com_imagem: bool = False
    ocultar_importados: bool = True
    ordem: str = "recentes"
    categoria_id: int = None                         # None = editoria sugerida automaticamente
    autor_id: int = None                             # None = "Clipping — <jornal>"
    status_destino: str = "em_pauta"

    def para_dict(self):
        return dict(self.__dict__)

    @classmethod
    def de_dict(cls, dados):
        base = cls()
        for k in base.__dict__:
            if k in (dados or {}):
                setattr(base, k, dados[k])
        return base


def lista_de_palavras(texto) -> list:
    """'Lula, congresso; reforma tributária' -> ['Lula', 'congresso', 'reforma tributária']."""
    if isinstance(texto, (list, tuple)):
        return [p.strip() for p in texto if p and p.strip()]
    return [p.strip() for p in re.split(r"[,;\n]+", texto or "") if p.strip()]


def _casa(palavra, texto_norm) -> bool:
    p = normalizar(palavra).strip()
    if not p:
        return False
    prefixo = p.endswith("*")
    p = p.rstrip("*")
    padrao = r"(?<!\w)" + re.escape(p) + ("" if prefixo else r"(?!\w)")
    return re.search(padrao, texto_norm) is not None


def _inicio_periodo(periodo_horas, agora):
    if not periodo_horas:
        return agora.replace(hour=0, minute=0, second=0, microsecond=0)
    return agora - timedelta(hours=periodo_horas)


def _ts(data):
    try:
        return data.timestamp()
    except (OverflowError, OSError, ValueError):
        return 0.0


def _data_do_item(item):
    return item.get("publicado_em") or item.get("coletado_em") or datetime.min


def _url_norm(url):
    return re.sub(r"[?#].*$", "", (url or "").strip().lower()).rstrip("/")


def aplicar_filtros(itens, filtro: FiltroClipping, agora=None, secoes_por_fonte=None) -> list:
    """Aplica período, seções, palavras (incluir/excluir), imagem, deduplicação, 'já importado',
    limite por jornal e ordem. `itens` são dicts (fonte_chave, secao, titulo, resumo, publicado_em,
    coletado_em, imagem_url, url, guid, noticia_id). Devolve nova lista, sem alterar a original."""
    agora = agora or datetime.now()
    inicio = _inicio_periodo(filtro.periodo_horas, agora)
    incluir, excluir = lista_de_palavras(filtro.incluir), lista_de_palavras(filtro.excluir)
    saida, vistos_url, vistos_id = [], set(), set()
    for item in sorted(itens, key=_data_do_item, reverse=True):
        if filtro.fontes and item["fonte_chave"] not in filtro.fontes:
            continue
        permitidas = (secoes_por_fonte or {}).get(item["fonte_chave"])
        if permitidas is not None and item.get("secao") not in permitidas:
            continue
        data = _data_do_item(item)
        if data < inicio or data > agora + timedelta(days=1):
            continue
        texto = normalizar(f"{item['titulo']} {item.get('resumo') or ''}")
        if incluir and not any(_casa(p, texto) for p in incluir):
            continue
        if excluir and any(_casa(p, texto) for p in excluir):
            continue
        if filtro.so_com_imagem and not item.get("imagem_url"):
            continue
        ja = bool(item.get("noticia_id"))
        if ja and filtro.ocultar_importados:
            continue
        chave_id = (item["fonte_chave"], item["guid"])
        url = _url_norm(item["url"])
        if chave_id in vistos_id or url in vistos_url:
            continue
        vistos_id.add(chave_id)
        vistos_url.add(url)
        saida.append({**item, "ja_importado": ja})
    contagem, limitados = {}, []
    for item in saida:   # já está do mais novo para o mais antigo
        n = contagem.get(item["fonte_chave"], 0)
        if filtro.limite_por_fonte and n >= filtro.limite_por_fonte:
            continue
        contagem[item["fonte_chave"]] = n + 1
        limitados.append(item)
    if filtro.ordem == "fonte":
        limitados.sort(key=lambda i: (i["fonte_chave"], -_ts(_data_do_item(i))))
    elif filtro.ordem == "titulo":
        limitados.sort(key=lambda i: normalizar(i["titulo"]))
    return limitados


# ---------------------------------------------------------------------------
# Seção/palavras -> editoria
# ---------------------------------------------------------------------------
_GRUPOS = {
    "politica": (("polit", "governo"), ["politica", "governo", "congresso", "senado", "camara", "eleicao", "eleicoes",
                                        "presidente", "ministro", "stf", "partido", "planalto", "deputado", "lula",
                                        "prefeito", "governador", "tse"]),
    "esportes": (("esport",), ["esporte", "futebol", "gol", "campeonato", "copa", "olimpiada", "tenis", "formula 1",
                               "gremio", "inter", "flamengo", "palmeiras", "gre-nal", "brasileirao", "jogo", "atleta"]),
    "tecnologia": (("tecnolog", "ciencia"), ["tecnologia", "inteligencia artificial", "software", "aplicativo", "internet",
                                              "ciberseguranca", "smartphone", "startup", "google", "apple", "games",
                                              "supercomputador", "robo", "ciencia"]),
    "economia": (("econom", "negoc", "mercado", "financ"), ["economia", "inflacao", "dolar", "bolsa", "juros", "pib",
                                                           "mercado", "imposto", "tributaria", "banco central", "selic",
                                                           "emprego", "ibge", "negocios"]),
    "mundo": (("mundo", "internacional"), ["mundo", "internacional", "eua", "estados unidos", "china", "guerra", "onu",
                                            "europa", "russia", "ucrania", "israel", "gaza", "argentina"]),
    "cultura": (("cultur", "arte", "entreten"), ["cultura", "cinema", "musica", "show", "filme", "serie", "teatro",
                                                 "festival", "livro", "pop"]),
    "saude": (("saude",), ["saude", "vacina", "hospital", "doenca", "sus", "medico", "anvisa"]),
}


def _categoria_do_grupo(grupo, categorias):
    trechos = _GRUPOS[grupo][0]
    for c in categorias:
        nome = slug(c["nome"])
        if any(t in nome for t in trechos):
            return c["id"]
    return None


def sugerir_categoria(titulo, resumo, secao, categoria_sugerida, categorias):
    """id da editoria sugerida ou None. 1) dica do catálogo; 2) nome da seção; 3) palavras do título/resumo."""
    if categoria_sugerida in _GRUPOS:
        achada = _categoria_do_grupo(categoria_sugerida, categorias)
        if achada:
            return achada
    secao_n = normalizar(secao)
    for grupo, (_, palavras) in _GRUPOS.items():
        if any(_casa(p, secao_n) for p in palavras[:1]):
            achada = _categoria_do_grupo(grupo, categorias)
            if achada:
                return achada
    titulo_n, resumo_n = normalizar(titulo), normalizar(resumo)
    pontos = {}
    for grupo, (_, palavras) in _GRUPOS.items():
        pontos[grupo] = sum(2 for p in palavras if _casa(p, titulo_n)) + sum(1 for p in palavras if _casa(p, resumo_n))
    for grupo in sorted(pontos, key=pontos.get, reverse=True):
        if pontos[grupo] < 2:
            break
        achada = _categoria_do_grupo(grupo, categorias)
        if achada:
            return achada
    return None


# ---------------------------------------------------------------------------
# Coleta (só rede: pode rodar em thread)
# ---------------------------------------------------------------------------
def _coletar_um(feed, estado, buscar, agora, intervalo_min, tentativas, pausa, semaforo):
    """Resultado de um feed: status ok | nao_modificado | em_cache | erro."""
    base = {"feed": feed, "itens": [], "etag": None, "last_modified": None, "motivo": "", "quando": agora}
    ultima = (estado or {}).get("ultima_coleta")
    if isinstance(ultima, datetime) and agora - ultima < timedelta(minutes=intervalo_min):
        minutos = max(0, int((agora - ultima).total_seconds() // 60))
        return {**base, "status": "em_cache", "etag": estado.get("etag"), "last_modified": estado.get("last_modified"),
                "motivo": f"coletado há {minutos} min (mínimo de {intervalo_min} min entre coletas)"}
    cabecalhos = {"Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"}
    if (estado or {}).get("etag"):
        cabecalhos["If-None-Match"] = estado["etag"]
    if (estado or {}).get("last_modified"):
        cabecalhos["If-Modified-Since"] = estado["last_modified"]
    ultimo_erro = "Falha desconhecida."
    for tentativa in range(1, tentativas + 1):
        try:
            with semaforo:
                resposta = buscar(feed["url"], timeout=rede.TIMEOUT_PADRAO, cabecalhos=cabecalhos)
        except ErroRede as e:
            ultimo_erro = str(e)
            if tentativa < tentativas:
                time.sleep(pausa)
            continue
        etag, modificado = resposta.cabecalho("ETag"), resposta.cabecalho("Last-Modified")
        if resposta.status == 304:
            return {**base, "status": "nao_modificado", "etag": etag or (estado or {}).get("etag"),
                    "last_modified": modificado or (estado or {}).get("last_modified"), "motivo": "sem novidades"}
        if resposta.status == 200:
            try:
                lido = interpretar_feed(resposta.conteudo, url_base=feed["url"])
            except ErroFeed as e:
                return {**base, "status": "erro", "motivo": str(e)}
            return {**base, "status": "ok", "itens": lido["itens"], "etag": etag, "last_modified": modificado,
                    "motivo": f"{len(lido['itens'])} item(ns)"}
        ultimo_erro = mensagem_http(resposta.status)
        if resposta.status < 500 and resposta.status != 429:
            break   # 404/403: repetir não adianta
        if tentativa < tentativas:
            time.sleep(pausa)
    return {**base, "status": "erro", "motivo": ultimo_erro}


def coletar_feeds(feeds, estados=None, buscar=rede.buscar, agora=None, intervalo_min=INTERVALO_MIN_COLETA_MIN,
                  tentativas=TENTATIVAS, pausa=1.0, max_conexoes=MAX_CONEXOES) -> list:
    """Coleta os feeds em paralelo limitado. Um feed com problema não atrapalha os outros.
    Devolve a lista de resultados (um por feed, na mesma ordem). NÃO usa banco nem Tk."""
    agora = agora or datetime.now()
    estados = estados or {}
    if not feeds:
        return []
    semaforos, trava = {}, threading.Lock()

    def semaforo_de(url):
        host = re.sub(r"^https?://([^/]+).*$", r"\1", url.lower())
        with trava:
            return semaforos.setdefault(host, threading.Semaphore(MAX_CONEXOES_POR_SERVIDOR))

    def tarefa(feed):
        try:
            return _coletar_um(feed, estados.get(chave_url(feed["url"])), buscar, agora, intervalo_min, tentativas,
                               pausa, semaforo_de(feed["url"]))
        except Exception as e:   # defesa final: nunca derruba a coleta toda
            return {"feed": feed, "status": "erro", "itens": [], "etag": None, "last_modified": None,
                    "motivo": f"Erro inesperado: {type(e).__name__}", "quando": agora}

    with ThreadPoolExecutor(max_workers=max(1, min(max_conexoes, len(feeds)))) as pool:
        return list(pool.map(tarefa, feeds))


def validar_feed(url, buscar=rede.buscar) -> dict:
    """Confere um endereço de feed próprio: http/https, resposta XML RSS/Atom, tamanho limitado.
    Só rede (thread). Lança ErroRede/ErroFeed com mensagem em português."""
    if not rede.url_valida(url):
        raise ErroRede("Endereço inválido: use um link http:// ou https://.")
    resposta = buscar(url.strip(), timeout=rede.TIMEOUT_PADRAO)
    if resposta.status != 200:
        raise ErroRede(mensagem_http(resposta.status), resposta.status)
    lido = interpretar_feed(resposta.conteudo, url_base=url.strip())
    return {"titulo": lido["titulo"], "total": len(lido["itens"]), "itens": lido["itens"]}


# ---------------------------------------------------------------------------
# Serviço (usa o banco: thread principal)
# ---------------------------------------------------------------------------
class ClippingService(_ServicoBase):
    def __init__(self, db, logger, midia=None, catalogo=None):
        super().__init__(db, logger, midia)
        self._catalogo = catalogo
        self.noticias = NoticiaService(db, logger, midia)
        self.autores = AutorService(db, logger, midia)

    # ---------- fontes ----------
    def catalogo(self):
        if self._catalogo is None:
            self._catalogo = carregar_catalogo()
        return self._catalogo

    def fontes(self, usuario_id) -> list:
        """Catálogo + feeds próprios do usuário, com 'ativo' conforme a preferência dele."""
        try:
            prefs = self.db.obter_preferencias(usuario_id)
            proprios = self.db.listar_feeds_proprios(usuario_id)
        except ErroBanco as e:
            self._falha_banco("Erro ao carregar as fontes de clipping", e)
            prefs, proprios = {}, []
        fontes = [dict(f) for f in self.catalogo()]
        for p in proprios:
            chave = f"proprio-{p['id']}"
            fontes.append({"chave": chave, "nome": p["nome"], "pais": "", "idioma": "", "site": p["url"], "ativo": True,
                           "proprio": True, "proprio_id": p["id"], "nota": "Feed adicionado por você.",
                           "feeds": [{"secao": p.get("secao") or "Geral", "url": p["url"], "categoria_sugerida": None,
                                      "verificado_em": None, "verificacao": "proprio",
                                      "chave_feed": f"{chave}:{slug(p.get('secao') or 'Geral')}"}]})
        for f in fontes:
            guardado = prefs.get(f"clip_fonte_{f['chave']}"[:60])
            if guardado is not None:
                f["ativo"] = guardado == "1"
            if not f["feeds"]:
                f["ativo"] = False
        return fontes

    def definir_fonte_ativa(self, usuario_id, chave, ativo) -> Resultado:
        try:
            self.db.salvar_preferencias(usuario_id, {f"clip_fonte_{chave}"[:60]: "1" if ativo else "0"})
        except ErroBanco as e:
            return self._falha_banco("Erro ao salvar a fonte", e)
        return Resultado(True)

    def salvar_feed_proprio(self, usuario_id, nome, url, secao="") -> Resultado:
        nome, url, secao = _limpar(nome), (url or "").strip(), _limpar(secao)
        if not 2 <= len(nome) <= 100:
            return Resultado(False, "Informe o nome do jornal (2 a 100 caracteres).")
        if not rede.url_valida(url) or len(url) > 500:
            return Resultado(False, "Informe um endereço válido (http:// ou https://, até 500 caracteres).")
        if len(secao) > 80:
            return Resultado(False, "A seção pode ter no máximo 80 caracteres.")
        try:
            existentes = self.db.listar_feeds_proprios(usuario_id)
            if len(existentes) >= MAX_FEEDS_PROPRIOS:
                return Resultado(False, f"Limite de {MAX_FEEDS_PROPRIOS} feeds próprios atingido.")
            if any(e["url"] == url for e in existentes):
                return Resultado(False, "Este feed já foi adicionado.")
            novo = self.db.criar_feed_proprio(usuario_id, nome, url, secao or None, datetime.now().replace(microsecond=0))
        except ErroBanco as e:
            return self._falha_banco("Erro ao salvar o feed", e)
        return Resultado(True, f"Feed de \"{nome}\" adicionado.", novo)

    def remover_feed_proprio(self, usuario_id, feed_id) -> Resultado:
        try:
            self.db.excluir_feed_proprio(usuario_id, feed_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao remover o feed", e)
        return Resultado(True, "Feed removido.")

    def feeds_do_filtro(self, usuario_id, filtro: FiltroClipping) -> list:
        """Feeds (dicts prontos para coletar) dos jornais ativos escolhidos no filtro."""
        feeds = []
        for fonte in self.fontes(usuario_id):
            if not fonte["ativo"] or (filtro.fontes and fonte["chave"] not in filtro.fontes):
                continue
            for feed in fonte["feeds"]:
                if filtro.feeds and feed["chave_feed"] not in filtro.feeds:
                    continue
                feeds.append({"fonte_chave": fonte["chave"], "fonte_nome": fonte["nome"], "secao": feed["secao"],
                              "url": feed["url"], "chave_feed": feed["chave_feed"],
                              "categoria_sugerida": feed.get("categoria_sugerida"),
                              "verificacao": feed.get("verificacao")})
        return feeds

    # ---------- coleta em três passos ----------
    def preparar_coleta(self, usuario_id, filtro: FiltroClipping):
        """Passo 1 (banco): (feeds, estados) que a thread vai usar."""
        feeds = self.feeds_do_filtro(usuario_id, filtro)
        try:
            estados = self.db.obter_estados_feeds([chave_url(f["url"]) for f in feeds])
        except ErroBanco as e:
            self._falha_banco("Erro ao carregar o estado dos feeds", e)
            estados = {}
        return feeds, estados

    def registrar_coleta(self, resultados, agora=None) -> dict:
        """Passo 3a (banco): guarda os itens novos e o estado (ETag, Last-Modified, última coleta)."""
        agora = (agora or datetime.now()).replace(microsecond=0)
        novos = 0
        for r in resultados:
            feed = r["feed"]
            try:
                if r["itens"]:
                    novos += self.db.inserir_itens_clipping(
                        [{**i, "fonte_chave": feed["fonte_chave"], "secao": feed["secao"]} for i in r["itens"]], agora)
                if r["status"] in ("ok", "nao_modificado"):   # erro e cache não contam como coleta
                    self.db.salvar_estado_feed(chave_url(feed["url"]), feed["url"], r["etag"], r["last_modified"],
                                               agora, "OK")
            except ErroBanco as e:
                self._falha_banco("Erro ao guardar a coleta", e)
        return {"novos": novos}

    def concluir_coleta(self, usuario_id, filtro, resultados, agora=None) -> Resultado:
        """Passo 3 (banco): registra a coleta e monta a prévia filtrada.
        dados = {itens, falhas, resumo_fontes, total_coletado}."""
        agora = agora or datetime.now()
        info = self.registrar_coleta(resultados, agora)
        falhas = [{"fonte": r["feed"]["fonte_nome"], "secao": r["feed"]["secao"], "url": r["feed"]["url"],
                   "motivo": r["motivo"]} for r in resultados if r["status"] == "erro"]
        previa = self.previa(usuario_id, filtro, agora)
        if not previa.ok:
            return previa
        previa.dados.update(falhas=falhas, novos=info["novos"], resultados=[
            {"fonte": r["feed"]["fonte_nome"], "secao": r["feed"]["secao"], "status": r["status"],
             "motivo": r["motivo"]} for r in resultados])
        total = len(previa.dados["itens"])
        previa.mensagem = f"{total} matéria(s) na prévia." + (f" {len(falhas)} fonte(s) com erro." if falhas else "")
        return previa

    def previa(self, usuario_id, filtro: FiltroClipping, agora=None) -> Resultado:
        """Itens já guardados, filtrados. dados = {itens, falhas: []}."""
        agora = agora or datetime.now()
        feeds = self.feeds_do_filtro(usuario_id, filtro)
        if not feeds:
            return Resultado(False, "Escolha pelo menos um jornal ativo para buscar.")
        fontes = sorted({f["fonte_chave"] for f in feeds})
        secoes = {}
        for f in feeds:
            secoes.setdefault(f["fonte_chave"], set()).add(f["secao"])
        try:
            linhas = self.db.listar_itens_clipping(fontes, _inicio_periodo(filtro.periodo_horas, agora))
        except ErroBanco as e:
            return self._falha_banco("Erro ao listar os itens do clipping", e)
        nomes = {f["fonte_chave"]: f["fonte_nome"] for f in feeds}
        dicas = {(f["fonte_chave"], f["secao"]): f.get("categoria_sugerida") for f in feeds}
        itens = aplicar_filtros(
            [{**l, "fonte_nome": nomes.get(l["fonte_chave"], l["fonte_chave"]),
              "categoria_sugerida": dicas.get((l["fonte_chave"], l.get("secao")))} for l in linhas],
            filtro, agora, secoes)
        return Resultado(True, f"{len(itens)} matéria(s).", {"itens": itens, "falhas": []})

    def buscar_agora(self, usuario_id, filtro, buscar=rede.buscar, agora=None, pausa=0.0) -> Resultado:
        """Os três passos juntos, de forma síncrona (testes, seed, execução de importações salvas)."""
        agora = agora or datetime.now()
        feeds, estados = self.preparar_coleta(usuario_id, filtro)
        if not feeds:
            return Resultado(False, "Escolha pelo menos um jornal ativo para buscar.")
        resultados = coletar_feeds(feeds, estados, buscar, agora, pausa=pausa)
        return self.concluir_coleta(usuario_id, filtro, resultados, agora)

    def testar_fontes(self, usuario_id, buscar=rede.buscar, agora=None, pausa=0.0, resultados=None) -> Resultado:
        """Coleta todos os feeds ativos e diz OK/falha de cada um (respeitando o intervalo mínimo)."""
        agora = agora or datetime.now()
        if resultados is None:
            feeds, estados = self.preparar_coleta(usuario_id, FiltroClipping())
            resultados = coletar_feeds(feeds, estados, buscar, agora, pausa=pausa)
        self.registrar_coleta(resultados, agora)
        linhas = [{"fonte": r["feed"]["fonte_nome"], "secao": r["feed"]["secao"], "url": r["feed"]["url"],
                   "ok": r["status"] != "erro", "status": r["status"], "detalhe": r["motivo"],
                   "verificacao": r["feed"].get("verificacao")} for r in resultados]
        ok = sum(1 for l in linhas if l["ok"])
        return Resultado(True, f"{ok} de {len(linhas)} feed(s) funcionando.", linhas)

    def purgar_antigos(self, agora=None):
        try:
            self.db.purgar_itens_clipping((agora or datetime.now()) - timedelta(days=RETENCAO_ITENS_DIAS))
        except ErroBanco as e:
            self._falha_banco("Erro ao limpar itens antigos do clipping", e)

    # ---------- importação ----------
    def _autor_do_jornal(self, nome_jornal, cache):
        nome = (PREFIXO_AUTOR + nome_jornal)[:120]
        if nome in cache:
            return cache[nome]
        existente = self.db.buscar_autor_por_nome(nome)
        if existente:
            cache[nome] = existente["id"]
            return existente["id"]
        r = self.autores.criar(nome, "", "correspondente", "Conteúdo externo (clipping)", "", "ativo",
                               f"Autor técnico do clipping: reúne as pautas importadas dos feeds de {nome_jornal}.")
        if not r.ok:
            raise ValueError(r.mensagem)
        cache[nome] = r.dados
        return r.dados

    @staticmethod
    def _montar_texto(item, nome_jornal):
        nome = re.sub(r"[\[\]]", "", nome_jornal)
        url = item["url"].replace(")", "%29").replace("(", "%28").replace(" ", "%20")
        partes = []
        if item.get("resumo"):
            partes.append(item["resumo"])
        partes.append(f"Fonte: [{nome}]({url})")
        partes.append("Conteúdo de terceiros: resumo fornecido pelo feed do veículo. Leia a matéria completa na fonte.")
        return "\n\n".join(partes)

    @staticmethod
    def _titulo(item):
        t = item["titulo"]
        return t if len(t) <= 120 else t[:119].rstrip() + "…"

    def importar(self, usuario_id, itens, categoria_id=None, status_destino="em_pauta", autor_id=None,
                 origem="manual", nome=None, falhas_fontes=0, agora=None, fontes_texto=None,
                 avisar=True) -> Resultado:
        """Cria as matérias dos `itens` da prévia (dicts com 'id' do clipping_itens). Nunca publica.
        Itens já importados são pulados. dados = {importadas, existentes, erros, ids}."""
        if status_destino not in STATUS_DESTINO:
            return Resultado(False, "Matérias de clipping só podem entrar como Rascunho, Em Pauta ou Revisão — "
                                    "nada é publicado automaticamente.")
        if not itens:
            return Resultado(False, "Nenhuma matéria selecionada.")
        agora = agora or datetime.now()
        try:
            categorias = self.db.listar_categorias()
        except ErroBanco as e:
            return self._falha_banco("Erro ao carregar as editorias", e)
        if not categorias:
            return Resultado(False, "Cadastre ao menos uma editoria antes de importar.")
        validas = {c["id"] for c in categorias}
        if categoria_id and int(categoria_id) not in validas:
            return Resultado(False, "A editoria escolhida não existe mais.")
        importadas, existentes, erros, ids, cache_autor = 0, 0, [], [], {}
        with silenciar():   # uma notificação-resumo no fim, em vez de uma por matéria
            for item in itens:
                try:
                    if item.get("noticia_id") or item.get("ja_importado"):
                        existentes += 1
                        continue
                    atual = self.db.buscar_item_clipping(item["id"])
                    if atual and atual.get("noticia_id"):
                        existentes += 1
                        continue
                    destino = categoria_id and int(categoria_id) or sugerir_categoria(
                        item["titulo"], item.get("resumo"), item.get("secao") or "", item.get("categoria_sugerida"),
                        categorias) or categorias[0]["id"]
                    nome_jornal = item.get("fonte_nome") or item["fonte_chave"]
                    autor = autor_id or self._autor_do_jornal(nome_jornal, cache_autor)
                    secao = item.get("secao")
                    r = self.noticias.criar(
                        self._titulo(item), destino, autor, self._montar_texto(item, nome_jornal),
                        subtitulo=f"Via {nome_jornal}" + (f" • {secao}" if secao and secao != "Geral" else ""),
                        status=status_destino, destaque=False, etiquetas="Clipping",
                        data=item.get("publicado_em") or agora, fonte_nome=nome_jornal[:120],
                        fonte_url=item["url"][:1000], fonte_guid=item["guid"][:255])
                    if not r.ok:
                        erros.append(f"{self._titulo(item)[:60]}: {r.mensagem}")
                        continue
                    self.db.marcar_item_clipping_importado(item["id"], r.dados)
                    importadas += 1
                    ids.append(r.dados)
                except (ErroBanco, ValueError) as e:
                    erros.append(f"{self._titulo(item)[:60]}: {e}")
        partes = [f"{importadas} importada(s)", f"{existentes} já existia(m)"]
        if falhas_fontes:
            partes.append(f"{falhas_fontes} fonte(s) com erro")
        if erros:
            partes.append(f"{len(erros)} com problema")
        resumo = ", ".join(partes) + "."
        self._registrar_resumo(usuario_id, origem, nome, importadas, existentes, falhas_fontes + len(erros), resumo,
                               status_destino, agora, fontes_texto, avisar)
        return Resultado(importadas > 0 or existentes > 0, resumo,
                         {"importadas": importadas, "existentes": existentes, "erros": erros, "ids": ids})

    def _registrar_resumo(self, usuario_id, origem, nome, importadas, existentes, falhas, resumo, status, agora, fontes,
                          avisar=True):
        try:
            self.db.registrar_historico_clipping(usuario_id, agora.replace(microsecond=0), origem, nome, importadas,
                                                 existentes, falhas, fontes)
        except ErroBanco as e:
            self._falha_banco("Erro ao registrar o histórico do clipping", e)
        if importadas and avisar:
            registrar_evento(self.db, self.logger, "pauta",
                             f"Clipping: {importadas} matéria(s) em pauta" if status == "em_pauta"
                             else f"Clipping: {importadas} matéria(s) importada(s)",
                             f"{resumo} Conteúdo de terceiros: confira a fonte e os termos de cada jornal antes de usar.",
                             "Clipping", "CONTEÚDO DE TERCEIROS")

    def historico(self, limite=20) -> Resultado:
        try:
            return Resultado(True, "", self.db.listar_historico_clipping(limite))
        except ErroBanco as e:
            return self._falha_banco("Erro ao carregar o histórico", e)

    # ---------- importações salvas ----------
    def _validar_salva(self, usuario_id, nome, filtro: FiltroClipping, ignorar_id=None):
        nome = _limpar(nome)
        if not 2 <= len(nome) <= 120:
            return None, "Dê um nome à importação (2 a 120 caracteres)."
        if not filtro.fontes:
            return None, "Escolha pelo menos um jornal."
        if filtro.status_destino not in STATUS_DESTINO:
            return None, "Estado de destino inválido (nunca 'publicado')."
        if filtro.ordem not in ORDENS:
            return None, "Ordem inválida."
        if any(r["nome"].lower() == nome.lower() and r["id"] != ignorar_id
               for r in self.db.listar_importacoes_salvas(usuario_id)):
            return None, f"Já existe uma importação salva chamada \"{nome}\"."
        return nome, None

    @staticmethod
    def _linha_da_salva(nome, filtro: FiltroClipping, automatica):
        return {"nome": nome, "fontes": json.dumps(filtro.fontes), "secoes": json.dumps(filtro.feeds),
                "palavras_incluir": ", ".join(lista_de_palavras(filtro.incluir))[:500] or None,
                "palavras_excluir": ", ".join(lista_de_palavras(filtro.excluir))[:500] or None,
                "periodo_horas": int(filtro.periodo_horas), "limite_por_fonte": int(filtro.limite_por_fonte),
                "so_com_imagem": 1 if filtro.so_com_imagem else 0, "ordem": filtro.ordem,
                "categoria_id": filtro.categoria_id, "autor_id": filtro.autor_id,
                "status_destino": filtro.status_destino, "automatica": 1 if automatica else 0}

    @staticmethod
    def filtro_da_salva(linha) -> FiltroClipping:
        def lista(texto):
            try:
                return list(json.loads(texto or "[]"))
            except ValueError:
                return []
        return FiltroClipping(
            fontes=lista(linha["fontes"]), feeds=lista(linha.get("secoes")),
            incluir=lista_de_palavras(linha.get("palavras_incluir")), excluir=lista_de_palavras(linha.get("palavras_excluir")),
            periodo_horas=int(linha.get("periodo_horas") or 24), limite_por_fonte=int(linha.get("limite_por_fonte") or 10),
            so_com_imagem=bool(linha.get("so_com_imagem")), ocultar_importados=True,
            ordem=linha.get("ordem") or "recentes", categoria_id=linha.get("categoria_id"),
            autor_id=linha.get("autor_id"), status_destino=linha.get("status_destino") or "em_pauta")

    def salvar_importacao(self, usuario_id, nome, filtro: FiltroClipping, automatica=False, importacao_id=None) -> Resultado:
        try:
            nome, erro = self._validar_salva(usuario_id, nome, filtro, importacao_id)
            if erro:
                return Resultado(False, erro)
            linha = self._linha_da_salva(nome, filtro, automatica)
            if importacao_id:
                if not self.db.buscar_importacao_salva(importacao_id):
                    return Resultado(False, "Importação salva não encontrada.")
                self.db.atualizar_importacao_salva(importacao_id, linha)
                return Resultado(True, f"Importação \"{nome}\" atualizada.", importacao_id)
            novo = self.db.criar_importacao_salva(usuario_id, linha)
        except ErroBanco as e:
            return self._falha_banco("Erro ao salvar a importação", e)
        return Resultado(True, f"Importação \"{nome}\" salva.", novo)

    def listar_importacoes(self, usuario_id) -> Resultado:
        try:
            linhas = self.db.listar_importacoes_salvas(usuario_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao listar as importações salvas", e)
        return Resultado(True, f"{len(linhas)} importação(ões) salva(s).",
                         [{**l, "filtro": self.filtro_da_salva(l)} for l in linhas])

    def excluir_importacao(self, importacao_id) -> Resultado:
        try:
            self.db.excluir_importacao_salva(importacao_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao excluir a importação", e)
        return Resultado(True, "Importação excluída.")

    def importar_da_salva(self, usuario_id, importacao, previa: Resultado, origem="salva", agora=None,
                          avisar=True) -> Resultado:
        """Importa tudo o que a prévia da importação salva trouxe (a prévia já veio filtrada, sem os
        já importados e com o limite por jornal) e marca a execução."""
        agora = agora or datetime.now()
        filtro = importacao["filtro"]
        itens = previa.dados["itens"] if previa.ok else []
        falhas = len(previa.dados.get("falhas", [])) if previa.ok else 0
        if itens:
            r = self.importar(usuario_id, itens, filtro.categoria_id, filtro.status_destino, filtro.autor_id, origem,
                              importacao["nome"], falhas, agora, ", ".join(filtro.fontes), avisar)
        else:
            r = Resultado(True, "Nada de novo para importar." + (f" {falhas} fonte(s) com erro." if falhas else ""),
                          {"importadas": 0, "existentes": 0, "erros": [], "ids": []})
            self._registrar_resumo(usuario_id, origem, importacao["nome"], 0, 0, falhas, r.mensagem,
                                   filtro.status_destino, agora, ", ".join(filtro.fontes), avisar)
        try:
            self.db.marcar_execucao_importacao(importacao["id"], agora.replace(microsecond=0))
        except ErroBanco as e:
            self._falha_banco("Erro ao marcar a execução", e)
        return r

    def executar_importacao(self, usuario_id, importacao_id, buscar=rede.buscar, origem="salva", agora=None,
                            pausa=0.0) -> Resultado:
        """'Rodar agora' de forma síncrona: busca, filtra e importa."""
        agora = agora or datetime.now()
        try:
            linha = self.db.buscar_importacao_salva(importacao_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao carregar a importação", e)
        if not linha:
            return Resultado(False, "Importação salva não encontrada.")
        importacao = {**linha, "filtro": self.filtro_da_salva(linha)}
        previa = self.buscar_agora(usuario_id, importacao["filtro"], buscar, agora, pausa)
        return self.importar_da_salva(usuario_id, importacao, previa, origem, agora)

    def automaticas_pendentes(self, usuario_id, hoje=None) -> list:
        """Importações marcadas como automáticas que ainda não rodaram hoje (1 vez por dia)."""
        hoje = hoje or datetime.now().date()
        r = self.listar_importacoes(usuario_id)
        if not r.ok:
            return []
        pendentes = []
        for imp in r.dados:
            if not imp.get("automatica"):
                continue
            ultima = imp.get("ultima_execucao")
            if isinstance(ultima, datetime) and ultima.date() >= hoje:
                continue
            pendentes.append(imp)
        return pendentes
