"""
graficos_tempo.py
Gráfico das próximas 24 horas (temperatura em linha + probabilidade de chuva
em barras) no mesmo estilo de app/graficos.py: matplotlib.figure.Figure, sem
pyplot, pronto para embutir com FigureCanvasTkAgg. Não depende do Tkinter.
"""

from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from .graficos import (FAMILIA_SEM_SERIFA, FAMILIA_SERIFADA, LINHA_GRADE, PAPEL, TINTA, TINTA_SUAVE, TRILHA,
                       VERMELHO, _limpar_eixo, _sem_dados)

AZUL = "#4F5E81"


def desenhar_24h(ax, horas):
    """Temperatura (linha vermelha, eixo esquerdo) e chance de chuva (barras azuis, eixo direito)."""
    if not horas:
        _sem_dados(ax, "Sem previsão horária disponível")
        return None
    x = list(range(len(horas)))
    temps = [h["temperatura"] for h in horas]
    probs = [h["chuva_prob"] or 0 for h in horas]
    rotulos = [f"{h['hora']:%H}h" for h in horas]

    ax.set_facecolor(PAPEL)
    ax.plot(x, temps, color=VERMELHO, linewidth=2.2, marker="o", markersize=4, zorder=3)
    ax.set_ylabel("°C", fontfamily=FAMILIA_SEM_SERIFA, fontsize=9, color=TINTA_SUAVE)
    ax.set_xticks(x[::3])
    ax.set_xticklabels(rotulos[::3], fontfamily=FAMILIA_SEM_SERIFA, fontsize=8, color=TINTA_SUAVE)
    ax.tick_params(axis="y", labelsize=8, colors=TINTA_SUAVE, length=0)
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.grid(axis="y", color=LINHA_GRADE, linewidth=0.8)
    ax.set_axisbelow(True)
    _limpar_eixo(ax, manter_base=True)
    validos = [t for t in temps if t is not None]
    if validos:
        ax.set_ylim(min(validos) - 2, max(validos) + 2)

    chuva = ax.twinx()
    chuva.bar(x, probs, color=AZUL, alpha=0.28, width=0.7, zorder=1)
    chuva.set_ylim(0, 100)
    chuva.set_ylabel("chuva %", fontfamily=FAMILIA_SEM_SERIFA, fontsize=9, color=AZUL)
    chuva.tick_params(axis="y", labelsize=8, colors=AZUL, length=0)
    for lado in ("top", "right", "left", "bottom"):
        chuva.spines[lado].set_visible(False)
    ax.set_zorder(chuva.get_zorder() + 1)   # a linha fica por cima das barras
    ax.patch.set_visible(False)
    return chuva


def figura_24h(horas, largura=7.4, altura=2.7):
    fig = Figure(figsize=(largura, altura), dpi=100, facecolor=PAPEL)
    ax = fig.add_subplot(111)
    desenhar_24h(ax, horas)
    fig.subplots_adjust(left=0.07, right=0.93, top=0.92, bottom=0.14)
    return fig
