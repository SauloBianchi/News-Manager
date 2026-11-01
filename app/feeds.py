"""
feeds.py
Leitura de feeds RSS 2.0, RSS 1.0 (RDF) e Atom, sem dependências externas e sem
raspagem de páginas HTML: só o que o próprio feed entrega (título, resumo curto,
data, link, autor e miniatura).

Segurança XML (por que NÃO usamos defusedxml): o ElementTree da biblioteca padrão
só é perigoso quando o documento declara entidades (ataques "billion laughs" e
XXE). Antes de interpretar, rejeitamos qualquer documento com `<!ENTITY` ou com
DOCTYPE que tenha subconjunto interno (`[ ... ]`). Um DOCTYPE simples, só com
identificador público (usado por feeds RSS 0.91 antigos), é aceito porque o
expat não baixa DTDs externas. Assim não é preciso acrescentar uma dependência.

Tudo aqui é puro (sem rede, banco ou Tk) e por isso fácil de testar e seguro
para rodar em thread.
"""

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from .rede import url_valida

TITULO_MAX = 500
RESUMO_MAX = 800
LIMITE_ITENS_PADRAO = 200
TAMANHO_FEED_MAX = 3_000_000   # bytes (a camada de rede já limita; aqui é defesa extra)


class ErroFeed(Exception):
    """Feed inválido ou inseguro; a mensagem já está em português."""


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
_RE_BLOCOS = re.compile(r"<\s*(script|style)\b.*?<\s*/\s*\1\s*>", re.I | re.S)
_RE_QUEBRAS = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6])\b[^>]*>", re.I)
_RE_TAGS = re.compile(r"<[^>]+>")
_RE_TAG_RESTANTE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_RE_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _cortar(texto, limite):
    if len(texto) <= limite:
        return texto
    corte = texto[:limite - 1]
    if " " in corte[limite // 2:]:
        corte = corte[:corte.rfind(" ")]
    return corte.rstrip(" ,;:.-") + "…"


def limpar_html(texto, limite=None) -> str:
    """Tira tags, scripts e estilos, resolve entidades (&amp;, &nbsp;, &#233;) e normaliza espaços."""
    if not texto:
        return ""
    texto = _RE_BLOCOS.sub(" ", texto)
    texto = _RE_QUEBRAS.sub(" ", texto)
    texto = _RE_TAGS.sub(" ", texto)
    texto = html.unescape(texto)
    if _RE_TAG_RESTANTE.search(texto):   # feeds com HTML escapado duas vezes
        texto = html.unescape(_RE_TAGS.sub(" ", texto))
    texto = _RE_CONTROLE.sub("", texto.replace("\xa0", " ").replace("\u200b", ""))
    texto = " ".join(texto.split())
    return _cortar(texto, limite) if limite else texto


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------
def interpretar_data_feed(texto):
    """RFC 822 (RSS) ou ISO 8601 (Atom) -> datetime NAIVE no horário local do computador. None se inválida."""
    texto = (texto or "").strip()
    if not texto:
        return None
    data = None
    try:
        data = parsedate_to_datetime(texto)
    except (TypeError, ValueError, IndexError):
        data = None
    if data is None:
        candidato = re.sub(r"Z$", "+00:00", texto)
        try:
            data = datetime.fromisoformat(candidato)
        except ValueError:
            for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
                try:
                    data = datetime.strptime(texto, formato)
                    break
                except ValueError:
                    continue
    if data is None:
        return None
    if data.tzinfo is not None:
        data = data.astimezone().replace(tzinfo=None)
    return data.replace(microsecond=0)


# ---------------------------------------------------------------------------
# XML
# ---------------------------------------------------------------------------
def _verificar_seguranca(conteudo: bytes):
    baixo = conteudo.lower()
    if b"<!entity" in baixo or re.search(rb"<!doctype[^>]*\[", baixo):
        raise ErroFeed("O feed contém declarações XML não permitidas (DOCTYPE com entidades) e foi rejeitado por segurança.")


def _parse_xml(conteudo: bytes):
    conteudo = conteudo.lstrip(b"\xef\xbb\xbf \t\r\n")
    if not conteudo:
        raise ErroFeed("O endereço respondeu vazio (não é um feed).")
    if len(conteudo) > TAMANHO_FEED_MAX:
        raise ErroFeed("O feed é grande demais.")
    if re.match(rb"(?is)\s*(<!doctype\s+html|<html)", conteudo):
        raise ErroFeed("O endereço devolveu uma página HTML, não um feed RSS/Atom.")
    _verificar_seguranca(conteudo)
    try:
        return ET.fromstring(conteudo)
    except ET.ParseError:
        pass
    # codificação declarada errada, caracteres de controle...: tenta recuperar
    for codificacao in ("utf-8", "cp1252", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
        texto = _RE_CONTROLE.sub("", re.sub(r"^\s*<\?xml[^>]*\?>", "", texto))
        try:
            return ET.fromstring(texto.encode("utf-8"))
        except ET.ParseError:
            continue
    raise ErroFeed("XML inválido: o endereço não devolveu um feed RSS/Atom legível.")


def _ln(tag) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _texto(el):
    return "".join(el.itertext()) if el is not None else ""


def _primeiro(el, *nomes):
    """Texto do primeiro filho cujo nome local esteja em `nomes` (na ordem de preferência)."""
    for nome in nomes:
        for filho in el:
            if _ln(filho.tag) == nome:
                valor = _texto(filho).strip()
                if valor:
                    return valor
    return ""


def _link_atom(entrada):
    escolhido = None
    for filho in entrada:
        if _ln(filho.tag) == "link" and filho.get("href"):
            rel = (filho.get("rel") or "alternate").lower()
            if rel == "alternate":
                return filho.get("href")
            if escolhido is None and rel not in ("enclosure", "self", "edit", "replies"):
                escolhido = filho.get("href")
    return escolhido or ""


def _imagem(el):
    for filho in el.iter():
        nome = _ln(filho.tag)
        url = filho.get("url") or filho.get("href")
        if not url:
            continue
        if nome in ("thumbnail",):
            return url
        if nome == "content" and ((filho.get("medium") or "").lower() == "image"
                                  or (filho.get("type") or "").lower().startswith("image/")):
            return url
        if nome in ("enclosure", "link") and (filho.get("type") or "").lower().startswith("image/") \
                and (filho.get("rel") or "enclosure") == "enclosure":
            return url
    corpo = _primeiro(el, "encoded", "content", "description", "summary")
    achado = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", html.unescape(corpo), re.I) if corpo else None
    return achado.group(1) if achado else ""


def _guid_curto(guid):
    guid = (guid or "").strip()
    return guid if len(guid) <= 255 else "sha1:" + hashlib.sha1(guid.encode("utf-8")).hexdigest()


def _montar_item(el, base, atom):
    titulo = limpar_html(_primeiro(el, "title"), TITULO_MAX)
    link = _link_atom(el) if atom else _primeiro(el, "link")
    if not link and not atom:   # alguns RSS trazem o link em <guid isPermaLink="true">
        guid_el = _primeiro(el, "guid")
        link = guid_el if guid_el.startswith("http") else ""
    link = urljoin(base or "", link.strip()) if link else ""
    if not titulo or not url_valida(link):
        return None
    resumo_bruto = _primeiro(el, "description", "summary") or _primeiro(el, "encoded", "content")
    data = interpretar_data_feed(_primeiro(el, "pubdate", "published", "date", "updated", "issued"))
    autor = _primeiro(el, "creator") or _primeiro(el, "author")
    if atom:
        for filho in el:
            if _ln(filho.tag) == "author":
                autor = _primeiro(filho, "name") or autor
    imagem = _imagem(el)
    imagem = urljoin(base or "", imagem) if imagem else ""
    return {
        "guid": _guid_curto(_primeiro(el, "guid", "id") or link),
        "url": link[:1000],
        "titulo": titulo,
        "resumo": limpar_html(resumo_bruto, RESUMO_MAX) or None,
        "autor_fonte": limpar_html(autor, 200) or None,
        "publicado_em": data,
        "imagem_url": imagem[:1000] if url_valida(imagem) else None,
    }


def interpretar_feed(conteudo: bytes, url_base=None, limite_itens=LIMITE_ITENS_PADRAO) -> dict:
    """Bytes de um feed -> {'titulo', 'itens': [dict]}. Lança ErroFeed.

    Cada item: guid, url, titulo, resumo, autor_fonte, publicado_em (datetime|None), imagem_url.
    Itens sem título ou sem link http/https válido são descartados; sem guid, o link é o identificador."""
    raiz = _parse_xml(conteudo)
    tipo = _ln(raiz.tag)
    if tipo == "rss":
        canal = next((f for f in raiz if _ln(f.tag) == "channel"), None)
        if canal is None:
            raise ErroFeed("Feed RSS sem o elemento <channel>.")
        entradas, atom, titulo = [f for f in canal if _ln(f.tag) == "item"], False, _primeiro(canal, "title")
    elif tipo == "rdf":
        entradas, atom = [f for f in raiz if _ln(f.tag) == "item"], False
        canal = next((f for f in raiz if _ln(f.tag) == "channel"), None)
        titulo = _primeiro(canal, "title") if canal is not None else ""
    elif tipo == "feed":
        entradas, atom, titulo = [f for f in raiz if _ln(f.tag) == "entry"], True, _primeiro(raiz, "title")
    elif tipo in ("html", "!doctype"):
        raise ErroFeed("O endereço devolveu uma página HTML, não um feed RSS/Atom.")
    else:
        raise ErroFeed("O documento não é um feed RSS ou Atom reconhecido.")
    itens, vistos = [], set()
    for el in entradas:
        item = _montar_item(el, url_base, atom)
        if item and item["guid"] not in vistos:
            vistos.add(item["guid"])
            itens.append(item)
        if len(itens) >= limite_itens:
            break
    return {"titulo": limpar_html(titulo, 200), "itens": itens}
