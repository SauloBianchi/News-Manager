"""
graficos.py
Gráficos da tela "Gráficos & Análise" feitos com matplotlib, no visual do
Stitch (fundo de papel, serifa nos rótulos, vermelho editorial), e a
exportação do relatório em PDF.

As funções `desenhar_*` recebem um `Axes` e desenham nele; as `figura_*`
criam a Figure pronta para embutir no Tkinter (FigureCanvasTkAgg). O mesmo
código desenha a tela e o PDF. Nada aqui depende do Tkinter nem do pyplot,
então funciona em testes e em computadores sem interface gráfica.
"""

from datetime import datetime

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator

from .estatisticas import ESTADOS, abreviar_tempo, fmt_dec, fmt_int, fmt_pct

# ---------------------------------------------------------------------------
# Estilo
# ---------------------------------------------------------------------------
FAMILIA_SERIFADA = ["Georgia", "Times New Roman", "DejaVu Serif"]
FAMILIA_SEM_SERIFA = ["Segoe UI", "Arial", "DejaVu Sans"]

PAPEL = "#FFFFFF"
PAPEL_SUAVE = "#F7F2E8"
TRILHA = "#EFE9DD"
TINTA = "#1C1C17"
TINTA_SUAVE = "#58413F"
VERMELHO = "#8B1E1E"
LINHA_GRADE = "#E4DDCE"
# Uma cor por barra (as 6 primeiras seguem o protótipo: vinho, vermelho, azul, marrom, azul claro, areia)
PALETA = ["#6B0F0F", "#8B1E1E", "#4F5E81", "#5A4426", "#9DB0D6", "#D9B382",
          "#7A6A5A", "#B04A4A", "#3E4E6E", "#A98B5F"]
LIMITE_BARRAS = 10


def _nova_figura(largura, altura, fundo=PAPEL):
    return Figure(figsize=(largura, altura), dpi=100, facecolor=fundo)


def _sem_dados(ax, mensagem="Sem matérias no recorte escolhido"):
    ax.clear()
    ax.set_axis_off()
    ax.text(0.5, 0.5, mensagem, ha="center", va="center", transform=ax.transAxes,
            fontfamily=FAMILIA_SERIFADA, fontstyle="italic", fontsize=12, color=TINTA_SUAVE)


def _limpar_eixo(ax, manter_base=False):
    for lado in ("top", "right", "left", "bottom"):
        ax.spines[lado].set_visible(manter_base and lado == "bottom")
    if manter_base:
        ax.spines["bottom"].set_color(LINHA_GRADE)


# ---------------------------------------------------------------------------
# Distribuição por editoria (barras horizontais)
# ---------------------------------------------------------------------------
def _encurtar(nome, limite=26):
    return nome if len(nome) <= limite else nome[:limite - 1].rstrip() + "…"


def altura_distribuicao(categorias) -> float:
    n = min(LIMITE_BARRAS, sum(1 for c in categorias if c["total"] > 0))
    return max(2.4, 0.56 * n + 0.5)


def desenhar_distribuicao(ax, categorias):
    dados = [c for c in categorias if c["total"] > 0][:LIMITE_BARRAS]
    if not dados:
        return _sem_dados(ax)
    ax.clear()
    ax.set_facecolor(PAPEL)
    n, maximo = len(dados), max(c["total"] for c in dados)
    posicoes = list(range(n))
    ax.barh(posicoes, [maximo] * n, color=TRILHA, height=0.46, zorder=1)
    ax.barh(posicoes, [c["total"] for c in dados], height=0.46, zorder=2,
            color=[PALETA[i % len(PALETA)] for i in range(n)])
    ax.set_yticks(posicoes)
    ax.set_yticklabels([_encurtar(c["nome"]) for c in dados], fontfamily=FAMILIA_SERIFADA, fontsize=11, color=TINTA)
    ax.invert_yaxis()
    ax.set_xlim(0, maximo * 1.34)
    ax.set_xticks([])
    ax.tick_params(left=False, pad=8)
    _limpar_eixo(ax)
    for i, c in enumerate(dados):
        ax.text(maximo * 1.025, i, fmt_int(c["total"]), ha="left", va="center", zorder=3,
                fontfamily=FAMILIA_SERIFADA, fontsize=13, fontweight="bold", color=TINTA)
        ax.text(maximo * 1.025 + maximo * 0.10, i, f"({fmt_pct(c['percentual'])})", ha="left", va="center",
                fontfamily=FAMILIA_SEM_SERIFA, fontsize=8.5, color=TINTA_SUAVE)


def figura_distribuicao(categorias, largura=7.4):
    fig = _nova_figura(largura, altura_distribuicao(categorias))
    ax = fig.add_axes([0.335, 0.03, 0.645, 0.94])
    desenhar_distribuicao(ax, categorias)
    return fig


# ---------------------------------------------------------------------------
# Volume ao longo da semana (linha com área)
# ---------------------------------------------------------------------------
def desenhar_semana(ax, semana):
    medias = semana["medias"]
    if not any(medias):
        return _sem_dados(ax, "Sem matérias no recorte")
    ax.clear()
    ax.set_facecolor(PAPEL_SUAVE)
    x = list(range(len(medias)))
    ax.fill_between(x, medias, color=VERMELHO, alpha=0.13, zorder=1)
    ax.plot(x, medias, color=VERMELHO, linewidth=2.2, zorder=3)
    ax.scatter(x, medias, s=34, color=VERMELHO, zorder=4)
    teto = max(medias) * 1.5 or 1
    ax.set_ylim(0, teto)
    ax.set_xlim(-0.4, len(medias) - 0.6)
    ax.set_yticks([])
    ax.set_xticks(x)
    ax.set_xticklabels(semana["rotulos"], fontfamily=FAMILIA_SEM_SERIFA, fontsize=8, color=TINTA_SUAVE)
    for i, rotulo in enumerate(ax.get_xticklabels()):
        if i in semana["picos"]:
            rotulo.set_fontweight("bold")
            rotulo.set_color(VERMELHO)
    ax.tick_params(bottom=False, pad=6)
    _limpar_eixo(ax)
    for i in semana["picos"]:
        ax.annotate(fmt_dec(medias[i], 1), (i, medias[i]), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=8.5, fontweight="bold", color=VERMELHO,
                    fontfamily=FAMILIA_SEM_SERIFA)


def figura_semana(semana, largura=4.2, altura=2.35):
    fig = _nova_figura(largura, altura)
    ax = fig.add_axes([0.03, 0.17, 0.94, 0.78])
    desenhar_semana(ax, semana)
    return fig


# ---------------------------------------------------------------------------
# Evolução no período (linha com área)
# ---------------------------------------------------------------------------
def desenhar_serie(ax, serie):
    valores = serie["valores"]
    if not any(valores):
        return _sem_dados(ax, "Sem matérias no recorte")
    ax.clear()
    ax.set_facecolor(PAPEL)
    x = list(range(len(valores)))
    ax.grid(axis="y", color=LINHA_GRADE, linewidth=0.8, linestyle=(0, (3, 3)), zorder=0)
    ax.fill_between(x, valores, color=VERMELHO, alpha=0.12, zorder=1)
    ax.plot(x, valores, color=VERMELHO, linewidth=2, zorder=3)
    if len(valores) <= 32:
        ax.scatter(x, valores, s=22, color=VERMELHO, zorder=4)
    melhor = max(range(len(valores)), key=lambda i: valores[i])
    ax.scatter([melhor], [valores[melhor]], s=60, color=PAPEL, edgecolor=VERMELHO, linewidth=2, zorder=5)
    ax.annotate(f"{valores[melhor]}", (melhor, valores[melhor]), textcoords="offset points", xytext=(0, 10),
                ha="center", fontsize=9, fontweight="bold", color=VERMELHO, fontfamily=FAMILIA_SEM_SERIFA)
    passo = max(1, len(valores) // 8)
    marcas = list(range(0, len(valores), passo))
    ax.set_xticks(marcas)
    ax.set_xticklabels([serie["rotulos"][i] for i in marcas], fontfamily=FAMILIA_SEM_SERIFA,
                       fontsize=8, color=TINTA_SUAVE)
    ax.set_ylim(0, max(valores) * 1.3)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=4))
    ax.tick_params(axis="y", labelsize=8, labelcolor=TINTA_SUAVE, length=0, pad=6)
    ax.tick_params(axis="x", length=0, pad=6)
    ax.set_xlim(-0.5, len(valores) - 0.5)
    _limpar_eixo(ax, manter_base=True)


def figura_serie(serie, largura=7.4, altura=2.6):
    fig = _nova_figura(largura, altura)
    ax = fig.add_axes([0.06, 0.16, 0.92, 0.78])
    desenhar_serie(ax, serie)
    return fig


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
A4_PAISAGEM = (11.69, 8.27)


def _cabecalho_pagina(fig, titulo, subtitulo, pagina, total_paginas):
    fig.text(0.05, 0.94, titulo, fontfamily=FAMILIA_SERIFADA, fontsize=22, fontweight="bold", color=TINTA)
    fig.text(0.05, 0.905, subtitulo, fontfamily=FAMILIA_SERIFADA, fontsize=11, fontstyle="italic", color=TINTA_SUAVE)
    fig.add_artist(Line2D([0.05, 0.95], [0.89, 0.89], color=TINTA, linewidth=1.6, transform=fig.transFigure))
    fig.text(0.05, 0.03, "NewsManager • Gazeta Editorial Impressa & Digital", fontfamily=FAMILIA_SEM_SERIFA,
             fontsize=7.5, color=TINTA_SUAVE)
    fig.text(0.95, 0.03, f"Página {pagina} de {total_paginas}", ha="right", fontfamily=FAMILIA_SEM_SERIFA,
             fontsize=7.5, color=TINTA_SUAVE)


def descricao_filtros(dados, nome_categoria=None, nome_autor=None) -> str:
    filtro = dados["filtro"]
    partes = [f"Período: {dados['periodo']['rotulo']}",
              f"Estado: {ESTADOS.get(filtro.status, filtro.status)}",
              f"Editoria: {nome_categoria or 'todas'}", f"Jornalista: {nome_autor or 'todos'}"]
    return "  •  ".join(partes)


def montar_paginas_pdf(dados, subtitulo):
    """Cria as Figures (uma por página) do relatório."""
    k = dados["kpis"]
    paginas = []

    # ---- página 1: indicadores, leitura dos dados e autores
    p1 = _nova_figura(*A4_PAISAGEM)
    _cabecalho_pagina(p1, "Análise Editorial & Métricas de Cobertura", subtitulo, 1, 3)
    cartoes = [
        ("TOTAL DE MATÉRIAS", fmt_int(k["total"]),
         "sem comparação" if k["variacao_total"] is None else
         f"{'+' if k['variacao_total'] >= 0 else '−'}{fmt_pct(abs(k['variacao_total']))} vs. período anterior"),
        ("EDITORIAS EM OPERAÇÃO", str(k["editorias_operacao"]), f"{fmt_pct(k['pct_editorias'], 0)} das ativas"),
        ("MÉDIA DE LEITURAS / MATÉRIA", fmt_int(k["media_leituras"]),
         "sem comparação" if k["delta_leituras"] is None else
         f"{'+' if k['delta_leituras'] >= 0 else '−'}{fmt_int(abs(k['delta_leituras']))} vs. período anterior"),
        ("TEMPO MÉDIO DE LEITURA", abreviar_tempo(k["tempo_leitura"]), k["formato"]),
    ]
    for i, (rotulo, valor, nota) in enumerate(cartoes):
        x = 0.05 + i * 0.2325
        p1.add_artist(Rectangle((x, 0.69), 0.215, 0.145, transform=p1.transFigure,
                                facecolor=PAPEL_SUAVE, edgecolor=LINHA_GRADE))
        p1.text(x + 0.012, 0.805, rotulo, fontfamily=FAMILIA_SEM_SERIFA, fontsize=7.5, fontweight="bold", color=TINTA)
        p1.text(x + 0.012, 0.735, valor, fontfamily=FAMILIA_SERIFADA, fontsize=24, fontweight="bold", color=TINTA)
        p1.text(x + 0.012, 0.703, nota, fontfamily=FAMILIA_SEM_SERIFA, fontsize=7.5, color=VERMELHO)
    p1.text(0.05, 0.64, "LEITURA DOS DADOS", fontfamily=FAMILIA_SEM_SERIFA, fontsize=8, fontweight="bold", color=VERMELHO)
    y = 0.60
    for frase in dados["insights"]:
        p1.text(0.05, y, "•  " + frase, fontfamily=FAMILIA_SERIFADA, fontsize=10.5, color=TINTA, wrap=True)
        y -= 0.04
    p1.text(0.05, 0.37, "PRODUTIVIDADE POR AUTOR", fontfamily=FAMILIA_SEM_SERIFA, fontsize=8, fontweight="bold", color=VERMELHO)
    p1.text(0.05, 0.34, "JORNALISTA", fontfamily=FAMILIA_SEM_SERIFA, fontsize=7.5, fontweight="bold", color=TINTA_SUAVE)
    for x, rotulo in ((0.45, "MATÉRIAS"), (0.55, "LEITURAS"), (0.65, "MÉDIA"), (0.75, "SCORE")):
        p1.text(x, 0.34, rotulo, fontfamily=FAMILIA_SEM_SERIFA, fontsize=7.5, fontweight="bold", color=TINTA_SUAVE)
    y = 0.305
    for posicao, a in enumerate(dados["autores"][:8], start=1):
        p1.text(0.05, y, f"{posicao:02d}.  {a['nome']}", fontfamily=FAMILIA_SERIFADA, fontsize=10, color=TINTA)
        for x, valor in ((0.45, fmt_int(a["total"])), (0.55, fmt_int(a["leituras"])),
                         (0.65, fmt_int(a["media_leituras"])), (0.75, fmt_dec(a["score"]))):
            p1.text(x, y, valor, fontfamily=FAMILIA_SEM_SERIFA, fontsize=9.5, color=TINTA)
        y -= 0.034
    paginas.append(p1)

    # ---- página 2: distribuição por editoria
    p2 = _nova_figura(*A4_PAISAGEM)
    _cabecalho_pagina(p2, "Distribuição Editorial: Notícias por Categoria", subtitulo, 2, 3)
    ax = p2.add_axes([0.24, 0.10, 0.62, 0.74])
    desenhar_distribuicao(ax, dados["categorias"])
    paginas.append(p2)

    # ---- página 3: semana e evolução
    p3 = _nova_figura(*A4_PAISAGEM)
    _cabecalho_pagina(p3, "Cadência Redatorial", subtitulo, 3, 3)
    p3.text(0.05, 0.84, "Média diária de matérias por dia da semana", fontfamily=FAMILIA_SERIFADA, fontsize=12, color=TINTA)
    desenhar_semana(p3.add_axes([0.06, 0.52, 0.88, 0.28]), dados["semana"])
    p3.text(0.05, 0.43, f"Evolução no período ({dados['serie']['granularidade']})", fontfamily=FAMILIA_SERIFADA,
            fontsize=12, color=TINTA)
    desenhar_serie(p3.add_axes([0.07, 0.10, 0.87, 0.28]), dados["serie"])
    paginas.append(p3)
    return paginas


def exportar_pdf(caminho, dados, subtitulo="") -> int:
    """Grava o relatório em PDF (3 páginas A4 paisagem). Devolve o número de páginas."""
    paginas = montar_paginas_pdf(dados, subtitulo or f"Gerado em {datetime.now():%d/%m/%Y às %H:%M}")
    with PdfPages(caminho) as pdf:
        for figura in paginas:
            pdf.savefig(figura)
    return len(paginas)
