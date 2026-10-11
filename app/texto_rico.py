"""
texto_rico.py
Formatação leve do corpo das matérias (um subconjunto de Markdown) e as
contas que o editor e a página de leitura precisam. Não usa Tkinter, então
tudo aqui é testável sem abrir janela.

Marcadores aceitos no texto da matéria (um bloco por linha):

    ## Intertítulo                 ### Subintertítulo
    > Citação em destaque          > — Fulano de Tal, cargo   (última linha = autoria)
    - item de lista                1. item numerado
    ---                            (filete horizontal)
    ![legenda](noticias/foto.jpg)  (imagem no meio do texto)

E, dentro do texto de um bloco:

    **negrito**   *itálico*   __sublinhado__   [texto do link](https://endereço)

Cada quebra de linha começa um novo parágrafo (é o jeito natural de escrever
no editor). Marcadores que não fecham aparecem como texto normal.
"""

import base64
import html
import mimetypes
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Texto dentro de um bloco
# ---------------------------------------------------------------------------
_INLINE = re.compile(
    r"\*\*(?![\s*])(?P<neg>.+?)(?<![\s*])\*\*"
    r"|__(?![\s_])(?P<sub>.+?)(?<![\s_])__"
    r"|\*(?![\s*])(?P<ita>.+?)(?<![\s*])\*"
    r"|\[(?P<txt>[^\]]+)\]\((?P<url>[^)\s]+)\)"
)


def url_segura(url: str) -> bool:
    """Só links http/https viram links clicáveis."""
    return bool(re.match(r"^https?://\S+$", url or "", re.IGNORECASE))


def tokens_inline(texto, estilos=frozenset(), url=None):
    """Quebra um texto em pedaços [(texto, estilos, url)] onde `estilos` é um
    conjunto com 'negrito', 'italico', 'sublinhado' e/ou 'link'."""
    saida, pos = [], 0
    for m in _INLINE.finditer(texto):
        if m.start() > pos:
            saida.append((texto[pos:m.start()], estilos, url))
        if m.group("neg") is not None:
            saida += tokens_inline(m.group("neg"), estilos | {"negrito"}, url)
        elif m.group("sub") is not None:
            saida += tokens_inline(m.group("sub"), estilos | {"sublinhado"}, url)
        elif m.group("ita") is not None:
            saida += tokens_inline(m.group("ita"), estilos | {"italico"}, url)
        elif url_segura(m.group("url")):
            saida += tokens_inline(m.group("txt"), estilos | {"link"}, m.group("url"))
        else:  # link com endereço estranho: fica só o texto
            saida += tokens_inline(m.group("txt"), estilos, url)
        pos = m.end()
    if pos < len(texto):
        saida.append((texto[pos:], estilos, url))
    return saida


def realces_inline(linha: str):
    """Para o editor: onde ficam os trechos formatados de uma linha.
    Devolve (realces, marcadores): realces = [(tag, inicio, fim)] com tag em
    negrito/italico/sublinhado/link; marcadores = [(inicio, fim)] das letras
    dos próprios marcadores (** __ * [ ](url)), que o editor mostra esmaecidas."""
    realces, marcadores = [], []
    for m in _INLINE.finditer(linha):
        if m.group("neg") is not None:
            realces.append(("negrito", m.start(), m.end()))
            marcadores += [(m.start(), m.start() + 2), (m.end() - 2, m.end())]
        elif m.group("sub") is not None:
            realces.append(("sublinhado", m.start(), m.end()))
            marcadores += [(m.start(), m.start() + 2), (m.end() - 2, m.end())]
        elif m.group("ita") is not None:
            realces.append(("italico", m.start(), m.end()))
            marcadores += [(m.start(), m.start() + 1), (m.end() - 1, m.end())]
        else:
            realces.append(("link", m.start(), m.end()))
            marcadores += [(m.start(), m.start() + 1), (m.start("txt") + len(m.group("txt")), m.end())]
    return realces, marcadores


def sem_marcadores(texto: str) -> str:
    """O texto de um bloco sem os marcadores de negrito/itálico/link."""
    return "".join(pedaco for pedaco, _e, _u in tokens_inline(texto))


# ---------------------------------------------------------------------------
# Blocos
# ---------------------------------------------------------------------------
@dataclass
class Bloco:
    tipo: str        # paragrafo | h2 | h3 | citacao | item | item_num | regra | imagem
    texto: str = ""  # imagem: legenda; citacao: texto da citação
    extra: str = ""  # imagem: caminho; citacao: autoria; item_num: o número


_IMAGEM = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<caminho>[^)\s]+)\)$")
_ITEM_NUM = re.compile(r"^(?P<n>\d+)\.\s+(?P<t>.+)$")
_ITEM = re.compile(r"^[-*]\s+(?P<t>.+)$")


def blocos(conteudo: str):
    """Converte o texto da matéria numa lista de Bloco."""
    linhas = (conteudo or "").replace("\r\n", "\n").split("\n")
    saida, i = [], 0
    while i < len(linhas):
        linha = linhas[i].strip()
        i += 1
        if not linha:
            continue
        if re.fullmatch(r"-{3,}", linha):
            saida.append(Bloco("regra"))
        elif linha.startswith("### "):
            saida.append(Bloco("h3", linha[4:].strip()))
        elif linha.startswith("## "):
            saida.append(Bloco("h2", linha[3:].strip()))
        elif _IMAGEM.match(linha):
            m = _IMAGEM.match(linha)
            saida.append(Bloco("imagem", m.group("alt").strip(), m.group("caminho")))
        elif linha.startswith(">"):
            citacao = [linha[1:].strip()]
            while i < len(linhas) and linhas[i].strip().startswith(">"):
                citacao.append(linhas[i].strip()[1:].strip())
                i += 1
            autoria = ""
            if len(citacao) > 1 and re.match(r"^(—|--|–)\s*\S", citacao[-1]):
                autoria = re.sub(r"^(—|--|–)\s*", "", citacao.pop())
            saida.append(Bloco("citacao", " ".join(c for c in citacao if c), autoria))
        elif _ITEM_NUM.match(linha):
            m = _ITEM_NUM.match(linha)
            saida.append(Bloco("item_num", m.group("t"), m.group("n")))
        elif _ITEM.match(linha):
            saida.append(Bloco("item", _ITEM.match(linha).group("t")))
        else:
            saida.append(Bloco("paragrafo", linha))
    return saida


def texto_simples(conteudo: str) -> str:
    """O texto da matéria sem nenhum marcador (para contar palavras, gerar
    resumos e calcular legibilidade). Imagens e filetes são ignorados."""
    partes = []
    for b in blocos(conteudo):
        if b.tipo in ("regra", "imagem"):
            continue
        partes.append(sem_marcadores(b.texto))
        if b.tipo == "citacao" and b.extra:
            partes.append(b.extra)
    return "\n".join(p for p in partes if p)


def intertitulos(conteudo: str):
    """Títulos de seção (##) na ordem em que aparecem — o 'Nesta edição' da leitura."""
    return [sem_marcadores(b.texto) for b in blocos(conteudo) if b.tipo == "h2"]


def caminhos_de_imagens(conteudo: str) -> set:
    """Caminhos das imagens inseridas no meio do texto."""
    return {b.extra for b in blocos(conteudo) if b.tipo == "imagem"}


# ---------------------------------------------------------------------------
# Números da "ficha de rotativa"
# ---------------------------------------------------------------------------
PALAVRAS_POR_COLUNA = 260     # uma coluna impressa de jornal
PALAVRAS_POR_MINUTO = 225     # leitura silenciosa


def contar_palavras(texto: str) -> int:
    return len((texto or "").split())


def colunas_estimadas(palavras: int) -> str:
    """'3,2 colunas' — quanto espaço o texto ocuparia na página impressa."""
    return f"{palavras / PALAVRAS_POR_COLUNA:.1f}".replace(".", ",") + " colunas"


def tempo_leitura_texto(palavras: int) -> str:
    """'3 min 45 seg'."""
    segundos = round(palavras / PALAVRAS_POR_MINUTO * 60)
    minutos, resto = divmod(segundos, 60)
    return f"{minutos} min {resto:02d} seg" if minutos else f"{resto} seg"


def _silabas(palavra: str) -> int:
    """Estimativa: cada grupo de vogais seguidas conta como uma sílaba."""
    return max(1, len(re.findall(r"[aeiouáéíóúâêôãõàü]+", palavra.lower())))


def indice_flesch(texto: str):
    """Índice de legibilidade Flesch adaptado ao português (0 a 100; quanto
    maior, mais fácil). Devolve None se o texto ainda for curto demais (<30
    palavras). É uma estimativa: as sílabas são contadas por aproximação."""
    palavras = re.findall(r"[^\W\d_]+", texto or "")
    frases = [f for f in re.split(r"(?<=[.!?…])\s+|\n+", texto or "") if f.strip()]
    if len(palavras) < 30 or not frases:
        return None
    silabas = sum(_silabas(p) for p in palavras)
    valor = 248.835 - 1.015 * (len(palavras) / len(frases)) - 84.6 * (silabas / len(palavras))
    return max(0, min(100, round(valor)))


def classificar_flesch(valor) -> str:
    if valor is None:
        return "—"
    if valor >= 75:
        return "Muito fácil"
    if valor >= 50:
        return "Fácil"
    if valor >= 25:
        return "Difícil"
    return "Muito difícil"


PALAVRAS_POR_POLEGADA = 29    # uma polegada de coluna impressa comporta ~29 palavras (≈ 260 por coluna de 9 pol.)


def polegadas_de_coluna(palavras: int) -> str:
    """'9,0 pol.' — espaço que o texto ocuparia na coluna do jornal (opção do Perfil)."""
    return f"{palavras / PALAVRAS_POR_POLEGADA:.1f}".replace(".", ",") + " pol."


# ---------------------------------------------------------------------------
# Revisão automática de redação (opção "modo de revisão automática" do Perfil)
# Não é um corretor ortográfico (não há dicionário): aponta problemas de forma
# que o Manual de Redação costuma proibir.
# ---------------------------------------------------------------------------
_ABREVIACOES = {"sr", "sra", "srta", "dr", "dra", "prof", "profa", "ex", "etc", "av", "pág", "pag", "vs",
                "cia", "ltda", "exmo", "exma", "ilmo", "ilma", "min", "cap", "fig", "obs", "pp", "ed"}
_PROTEGIDO = re.compile(r"!\[[^\]]*\]\([^)]*\)|\]\([^)]*\)|https?://\S+|www\.\S+", re.IGNORECASE)
FRASE_LONGA_PALAVRAS = 60


def revisar_texto(texto: str):
    """Lista de apontamentos [{linha, inicio, fim, mensagem}] (linha começa em 1; colunas em 0).
    Ignora endereços, imagens e a parte do endereço dos links."""
    achados = []
    for numero, bruta in enumerate((texto or "").replace("\r\n", "\n").split("\n"), start=1):
        # troca o que não deve ser revisado por um caractere neutro do mesmo tamanho (mantém as posições)
        linha = _PROTEGIDO.sub(lambda m: "·" * len(m.group(0)), bruta)
        if not linha.strip() or re.fullmatch(r"\s*-{3,}\s*", linha):
            continue

        def achar(inicio, fim, mensagem):
            achados.append(dict(linha=numero, inicio=inicio, fim=max(fim, inicio + 1), mensagem=mensagem))

        for m in re.finditer(r"(?<=\S)  +(?=\S)", linha):
            achar(m.start(), m.end(), "Espaço duplo")
        for m in re.finditer(r"\b([A-Za-zÀ-ÿ]{2,})\s+\1\b", linha, re.IGNORECASE):
            achar(m.start(), m.end(), f"Palavra repetida: \"{m.group(1)}\"")
        for m in re.finditer(r"(?<=\S)\s+(?=[,;:!?]|\.(?!\.))", linha):
            achar(m.start(), m.end() + 1, "Espaço antes da pontuação")
        for m in re.finditer(r"(?<=[A-Za-zÀ-ÿ])[,;:](?=[A-Za-zÀ-ÿ])", linha):
            achar(m.start(), m.end() + 1, "Falta espaço depois da pontuação")
        for m in re.finditer(r"(?<=[a-zà-ÿ])[.!?](?=[A-ZÀ-Ý])", linha):
            achar(m.start(), m.end() + 1, "Falta espaço entre as frases")
        for m in re.finditer(r"([A-Za-zÀ-ÿ0-9]+)([.!?…]+)\s+([a-zà-ÿ])", linha):
            palavra = m.group(1)
            if palavra.lower() in _ABREVIACOES or len(palavra) <= 2 or palavra.isdigit():
                continue
            achar(m.start(3), m.end(3), "Frase iniciada com letra minúscula")
        primeira = re.match(r"^\s*(?:#{2,3}\s+|>\s*|[-*]\s+|\d+\.\s+)?([A-Za-zÀ-ÿ])", linha)
        if primeira and primeira.group(1).islower():
            achar(primeira.start(1), primeira.end(1), "Parágrafo iniciado com letra minúscula")
        if linha.count("(") != linha.count(")"):
            achar(len(linha.rstrip()) - 1, len(linha.rstrip()), "Parênteses sem par")
        if linha.count("“") != linha.count("”") or linha.count('"') % 2:
            achar(len(linha.rstrip()) - 1, len(linha.rstrip()), "Aspas sem par")
        for m in re.finditer(r"[^.!?…]+(?:[.!?…]+|$)", linha):
            tamanho = len(m.group(0).split())
            if tamanho > FRASE_LONGA_PALAVRAS:
                achar(m.start(), m.end(), f"Frase longa ({tamanho} palavras): considere dividir")
    achados.sort(key=lambda a: (a["linha"], a["inicio"]))
    return achados


# ---------------------------------------------------------------------------
# Operações da barra de ferramentas do editor
# Todas recebem o texto inteiro e as posições (em caracteres) da seleção e
# devolvem (inicio, fim, novo_trecho, sel_inicio, sel_fim): troque
# texto[inicio:fim] por novo_trecho e selecione sel_inicio..sel_fim (posições
# no texto já alterado).
# ---------------------------------------------------------------------------
_PREFIXO_BLOCO = re.compile(r"^(?:#{2,3} |> |[-*] |\d+\. )")


def envolver(texto, a, b, marcador):
    """Negrito/itálico/sublinhado: envolve a seleção com o marcador; se ela
    já estiver envolvida, remove (alterna)."""
    if a > b:
        a, b = b, a
    m, sel = len(marcador), texto[a:b]
    antes = texto[a - m:a] if a >= m else ""
    depois = texto[b:b + m]
    char = marcador[0]
    fora_antes = texto[a - m - 1] if a - m - 1 >= 0 else ""
    fora_depois = texto[b + m] if b + m < len(texto) else ""
    if antes == marcador and depois == marcador and fora_antes != char and fora_depois != char:
        return (a - m, b + m, sel, a - m, a - m + len(sel))
    if len(sel) >= 2 * m and sel.startswith(marcador) and sel.endswith(marcador):
        interno = sel[m:-m]
        return (a, b, interno, a, a + len(interno))
    if not sel:
        return (a, b, marcador * 2, a + m, a + m)
    return (a, b, marcador + sel + marcador, a + m, a + m + len(sel))


def prefixar_linhas(texto, a, b, tipo):
    """Intertítulos, citação e listas: aplica o prefixo do `tipo` (h2, h3,
    citacao, lista, numerada) nas linhas tocadas pela seleção; se todas já
    tiverem esse prefixo, remove (alterna)."""
    if a > b:
        a, b = b, a
    inicio = texto.rfind("\n", 0, a) + 1
    ref = b - 1 if (b > a and texto[b - 1] == "\n") else b
    fim = texto.find("\n", ref)
    fim = len(texto) if fim == -1 else fim
    linhas = texto[inicio:fim].split("\n")
    unica = len(linhas) == 1

    def tem(linha):
        return {
            "h2": linha.startswith("## "), "h3": linha.startswith("### "),
            "citacao": linha.startswith("> "), "lista": linha.startswith("- "),
            "numerada": bool(re.match(r"^\d+\. ", linha)),
        }[tipo]

    alvo = [l for l in linhas if l.strip() or unica]
    remover = bool(alvo) and all(tem(l) for l in alvo)
    novas, n = [], 0
    for linha in linhas:
        if not linha.strip() and not unica:
            novas.append(linha)
            continue
        n += 1
        limpa = _PREFIXO_BLOCO.sub("", linha, count=1)
        if remover:
            novas.append(limpa)
            continue
        prefixo = {"h2": "## ", "h3": "### ", "citacao": "> ", "lista": "- ",
                   "numerada": f"{n}. "}[tipo]
        novas.append(prefixo + limpa)
    novo = "\n".join(novas)
    if unica:
        return (inicio, fim, novo, inicio + len(novo), inicio + len(novo))
    return (inicio, fim, novo, inicio, inicio + len(novo))


def inserir_linha(texto, pos, linha):
    """Insere `linha` (filete, imagem...) em uma linha própria, na posição do cursor."""
    antes = "" if pos == 0 or texto[pos - 1] == "\n" else "\n"
    depois = "" if pos < len(texto) and texto[pos] == "\n" else "\n"
    novo = antes + linha + depois
    return (pos, pos, novo, pos + len(novo), pos + len(novo))


def inserir_link(texto, a, b, url):
    """Transforma a seleção (ou o endereço) em [texto](url)."""
    if a > b:
        a, b = b, a
    rotulo = texto[a:b] or url
    novo = f"[{rotulo}]({url})"
    return (a, b, novo, a, a + len(novo))


# ---------------------------------------------------------------------------
# Exportação para HTML (para abrir no navegador e imprimir / salvar em PDF)
# ---------------------------------------------------------------------------
def _inline_html(texto: str) -> str:
    partes = []
    for pedaco, estilos, url in tokens_inline(texto):
        bruto = html.escape(pedaco)
        if "negrito" in estilos:
            bruto = f"<strong>{bruto}</strong>"
        if "italico" in estilos:
            bruto = f"<em>{bruto}</em>"
        if "sublinhado" in estilos:
            bruto = f"<u>{bruto}</u>"
        if "link" in estilos and url:
            bruto = f'<a href="{html.escape(url, quote=True)}">{bruto}</a>'
        partes.append(bruto)
    return "".join(partes)


def corpo_para_html(conteudo: str, ler_imagem=None) -> str:
    """HTML do corpo. `ler_imagem(caminho)` devolve os bytes de uma imagem do
    texto (ou None); as imagens vão embutidas no próprio arquivo."""
    saida, lista = [], None   # lista = "ul" | "ol" quando há uma lista aberta

    def fechar_lista():
        nonlocal lista
        if lista:
            saida.append(f"</{lista}>")
            lista = None

    for b in blocos(conteudo):
        if b.tipo in ("item", "item_num"):
            desejada = "ul" if b.tipo == "item" else "ol"
            if lista != desejada:
                fechar_lista()
                saida.append(f"<{desejada}>")
                lista = desejada
            saida.append(f"<li>{_inline_html(b.texto)}</li>")
            continue
        fechar_lista()
        if b.tipo == "h2":
            saida.append(f"<h2>{_inline_html(b.texto)}</h2>")
        elif b.tipo == "h3":
            saida.append(f"<h3>{_inline_html(b.texto)}</h3>")
        elif b.tipo == "regra":
            saida.append("<hr>")
        elif b.tipo == "citacao":
            autoria = f"<cite>— {html.escape(b.extra)}</cite>" if b.extra else ""
            saida.append(f"<blockquote><p>{_inline_html(b.texto)}</p>{autoria}</blockquote>")
        elif b.tipo == "imagem":
            dados = ler_imagem(b.extra) if ler_imagem else None
            if dados:
                tipo = mimetypes.guess_type(b.extra)[0] or "image/jpeg"
                uri = f"data:{tipo};base64,{base64.b64encode(dados).decode()}"
                legenda = f"<figcaption>{html.escape(b.texto)}</figcaption>" if b.texto else ""
                saida.append(f'<figure><img src="{uri}" alt="{html.escape(b.texto, quote=True)}">{legenda}</figure>')
        else:
            saida.append(f"<p>{_inline_html(b.texto)}</p>")
    fechar_lista()
    return "\n".join(saida)


def pagina_html(titulo, subtitulo, meta, conteudo, ler_imagem=None, capa=None,
                legenda_capa="", credito_capa=""):
    """Documento HTML completo da matéria (layout de jornal, pronto para imprimir)."""
    cab_capa = ""
    if capa and ler_imagem:
        dados = ler_imagem(capa)
        if dados:
            tipo = mimetypes.guess_type(capa)[0] or "image/jpeg"
            uri = f"data:{tipo};base64,{base64.b64encode(dados).decode()}"
            texto = html.escape(legenda_capa or "")
            if credito_capa:
                texto += f" <small>Crédito: {html.escape(credito_capa)}</small>"
            cab_capa = f'<figure class="capa"><img src="{uri}" alt="">' + (
                f"<figcaption>{texto}</figcaption>" if texto.strip() else "") + "</figure>"
    sub = f'<p class="linha-fina">{html.escape(subtitulo)}</p>' if subtitulo else ""
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>{html.escape(titulo)}</title>
<style>
body{{font-family:Georgia,'Times New Roman',serif;color:#1c1c17;background:#fdf9f0;margin:0}}
main{{max-width:760px;margin:0 auto;padding:40px 24px;line-height:1.65;font-size:18px}}
h1{{font-size:40px;line-height:1.15;text-align:center;margin:8px 0}}
.meta{{font:12px Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#5a4426;text-align:center}}
.linha-fina{{font-style:italic;text-align:center;color:#5d3f3c;font-size:20px}}
h2{{font-size:26px;border-left:4px solid #8b1e1e;padding-left:12px;margin-top:36px}}
h3{{font-size:20px}} blockquote{{background:#f1ede5;border-left:4px solid #8b1e1e;margin:24px 0;padding:12px 20px;font-style:italic;font-size:21px}}
cite{{display:block;font:12px Arial,sans-serif;font-style:normal;text-transform:uppercase;margin-top:8px}}
figure{{margin:24px 0;text-align:center}} img{{max-width:100%}} figcaption{{font:13px Arial,sans-serif;color:#5d3f3c}}
hr{{border:0;border-top:1px solid #c9c4b8;margin:28px 0}}
@media print{{body{{background:#fff}}}}
</style></head><body><main>
<p class="meta">{html.escape(meta)}</p>
<h1>{html.escape(titulo)}</h1>
{sub}
{cab_capa}
{corpo_para_html(conteudo, ler_imagem)}
</main></body></html>
"""
