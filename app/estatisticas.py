"""
estatisticas.py
Backend da tela "Gráficos & Análise": transforma os filtros escolhidos pelo
usuário (período, editoria, jornalista, estado) em indicadores, séries e
textos prontos para a interface e para a exportação em PDF/CSV.

A tela não faz conta nenhuma: chama EstatisticasService.consultar(filtro) e
recebe um dicionário com tudo (ver `consultar`). As consultas SQL ficam em
DatabaseManager (métodos estatisticas_*), e este módulo só junta e interpreta
os resultados.

Regras:
- só entram matérias com data de emissão até agora (matéria embargada, com
  data futura, ainda não conta);
- as comparações ("vs. período anterior") usam um intervalo imediatamente
  anterior e do mesmo tamanho; em "Todo o período" não há comparação;
- "score do autor" é um índice de 0 a 100: 60% pela quantidade de matérias e
  40% pela média de leituras por matéria, ambas relativas ao melhor autor do
  recorte.
"""

import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .cadastros import Resultado, _ServicoBase
from .database import ErroBanco
from .midia import RAIZ_PROJETO
from .noticias import STATUS_NOTICIA, interpretar_data
from .texto_rico import tempo_leitura_texto

PERIODOS = {
    "7d": "Últimos 7 dias",
    "30d": "Últimos 30 dias",
    "90d": "Últimos 90 dias",
    "12m": "Últimos 12 meses",
    "ano": "Este ano",
    "tudo": "Todo o período",
    "personalizado": "Personalizado…",
}
_DIAS_DO_PERIODO = {"7d": 7, "30d": 30, "90d": 90, "12m": 365}

ESTADOS = {"publicado": "Publicadas", "todos": "Todos os estados", **{
    k: v for k, v in STATUS_NOTICIA.items() if k != "publicado"}}

DIAS_SEMANA = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
DIAS_SEMANA_LONGOS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                      "sexta-feira", "sábado", "domingo"]
MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MAX_PONTOS_SERIE = 60

CAMINHO_PREFERENCIAS = RAIZ_PROJETO / "config" / "graficos.json"


# ---------------------------------------------------------------------------
# Formatação (pt-BR)
# ---------------------------------------------------------------------------
def fmt_int(numero) -> str:
    return f"{int(round(numero)):,}".replace(",", ".")


def fmt_dec(numero, casas=1) -> str:
    return f"{numero:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(numero, casas=1) -> str:
    return fmt_dec(numero, casas) + "%"


def abreviar_tempo(texto: str) -> str:
    """'3 min 45 seg' -> '3m 45s' (formato curto dos cartões)."""
    return texto.replace(" min ", "m ").replace(" seg", "s") if texto and texto != "—" else "—"


def _como_data(valor):
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    return interpretar_data(valor) if valor else None


# ---------------------------------------------------------------------------
# Filtro
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FiltroEstatisticas:
    periodo: str = "30d"
    inicio: Optional[date] = None        # só para periodo="personalizado"
    fim: Optional[date] = None
    categoria_id: Optional[int] = None
    autor_id: Optional[int] = None
    status: str = "publicado"            # "todos" = qualquer estado

    def status_sql(self):
        return None if self.status in (None, "", "todos") else self.status

    def intervalo(self, agora=None):
        """(inicio, fim, rótulo) do período. `inicio` None = desde sempre; o fim
        nunca passa de `agora` (matéria embargada não conta)."""
        agora = (agora or datetime.now()).replace(microsecond=0)
        if self.periodo in _DIAS_DO_PERIODO:
            dias = _DIAS_DO_PERIODO[self.periodo]
            return agora - timedelta(days=dias), agora, PERIODOS[self.periodo]
        if self.periodo == "ano":
            return datetime(agora.year, 1, 1), agora, f"Este ano ({agora.year})"
        if self.periodo == "personalizado" and self.inicio and self.fim:
            inicio = datetime.combine(self.inicio, datetime.min.time())
            fim = min(datetime.combine(self.fim, datetime.max.time()).replace(microsecond=0), agora)
            return inicio, fim, f"{self.inicio:%d/%m/%Y} a {self.fim:%d/%m/%Y}"
        return None, agora, PERIODOS["tudo"]

    def anterior(self, agora=None):
        """(inicio, fim) do intervalo imediatamente anterior, do mesmo tamanho; None se não houver."""
        inicio, fim, _ = self.intervalo(agora)
        if inicio is None:
            return None
        duracao = fim - inicio
        return inicio - duracao - timedelta(seconds=1), inicio - timedelta(seconds=1)

    def validar(self):
        """Mensagem de erro se o filtro estiver incoerente, senão None."""
        if self.periodo not in PERIODOS:
            return "Período inválido."
        if self.status not in ESTADOS:
            return "Estado inválido."
        if self.periodo == "personalizado":
            if not self.inicio or not self.fim:
                return "Informe a data inicial e a final do período."
            if self.inicio > self.fim:
                return "A data inicial não pode ser depois da data final."
        return None

    def descricao(self, agora=None) -> str:
        return self.intervalo(agora)[2]


def interpretar_data_br(texto):
    """'24/05/2024' -> date (None se inválida)."""
    try:
        return datetime.strptime((texto or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Preferências (último filtro e meta), guardadas em config/graficos.json
# ---------------------------------------------------------------------------
class PreferenciasGraficos:
    def __init__(self, caminho=None):
        self.caminho = Path(caminho) if caminho else CAMINHO_PREFERENCIAS

    def carregar(self) -> dict:
        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    def salvar(self, dados: dict) -> bool:
        try:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            self.caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
            return True
        except OSError:
            return False


# ---------------------------------------------------------------------------
# Serviço
# ---------------------------------------------------------------------------
class EstatisticasService(_ServicoBase):
    def opcoes_de_filtro(self) -> Resultado:
        """Editorias e jornalistas para preencher as listas de filtro."""
        try:
            categorias = [{"id": c["id"], "nome": c["nome"]} for c in self.db.listar_categorias()]
            autores = [{"id": a["id"], "nome": a["nome"]} for a in self.db.listar_autores()]
        except ErroBanco as e:
            return self._falha_banco("Erro ao carregar os filtros", e)
        return Resultado(True, "", {"categorias": categorias, "autores": autores})

    # ---------- consulta principal ----------
    def consultar(self, filtro: FiltroEstatisticas, agora=None, limite_autores=None) -> Resultado:
        """Tudo o que a tela precisa para o filtro dado.

        dados = {
          filtro, periodo{inicio, fim, rotulo, dias},
          kpis{total, total_anterior, variacao_total, editorias_operacao,
               editorias_ativas, pct_editorias, media_leituras, media_leituras_anterior,
               delta_leituras, soma_leituras, media_palavras, tempo_leitura, formato},
          categorias[{id, nome, cor, status, total, percentual, leituras, media_leituras}],
          autores[{id, nome, cargo, total, leituras, media_leituras, score}],
          semana{rotulos, totais, medias, picos}, serie{rotulos, valores, granularidade},
          estados{estado: total}, pipeline{ultima_publicacao, em_revisao, em_pauta, rascunhos},
          insights[str]
        }"""
        erro = filtro.validar()
        if erro:
            return Resultado(False, erro)
        agora = (agora or datetime.now()).replace(microsecond=0)
        inicio, fim, rotulo = filtro.intervalo(agora)
        base = dict(categoria_id=filtro.categoria_id, autor_id=filtro.autor_id, status=filtro.status_sql())
        try:
            resumo = self.db.estatisticas_resumo(inicio=inicio, fim=fim, **base)
            por_categoria = self.db.estatisticas_por_categoria(inicio=inicio, fim=fim, **base)
            por_autor = self.db.estatisticas_por_autor(limite_autores, inicio=inicio, fim=fim, **base)
            datas = self.db.estatisticas_datas(inicio=inicio, fim=fim, **base)
            estados = self.db.estatisticas_por_status(
                inicio=inicio, fim=fim, categoria_id=filtro.categoria_id, autor_id=filtro.autor_id)
            ativas = self.db.contar_categorias_por_status("ativa")
            ultima = self.db.ultima_publicacao(agora)
            anterior = None
            intervalo_anterior = filtro.anterior(agora)
            if intervalo_anterior:
                anterior = self.db.estatisticas_resumo(
                    inicio=intervalo_anterior[0], fim=intervalo_anterior[1], **base)
            fila = self.db.contar_noticias_por_status()
        except ErroBanco as e:
            return self._falha_banco("Erro ao calcular as estatísticas", e)

        total = int(resumo["total"])
        primeira = _como_data(resumo["primeira"])
        inicio_real = inicio or primeira or agora
        dias = max(1, (fim.date() - inicio_real.date()).days + 1)

        categorias = [
            dict(id=c["id"], nome=c["nome"], cor=c["cor"], status=c["status"], total=int(c["total"]),
                 leituras=int(c["leituras"]),
                 percentual=(100.0 * int(c["total"]) / total) if total else 0.0,
                 media_leituras=(float(c["leituras"]) / int(c["total"])) if int(c["total"]) else 0.0)
            for c in por_categoria]
        autores = self._pontuar_autores(por_autor)
        dados = dict(
            filtro=filtro,
            periodo=dict(inicio=inicio, fim=fim, rotulo=rotulo, dias=dias),
            kpis=self._kpis(resumo, anterior, total, ativas, categorias),
            categorias=categorias,
            autores=autores,
            semana=self._semana(datas, inicio_real, fim),
            serie=self._serie(datas, inicio_real, fim),
            estados={k: estados.get(k, 0) for k in STATUS_NOTICIA},
            pipeline=dict(
                ultima_publicacao=_como_data(ultima),
                em_revisao=sum(int(l["total"]) for l in fila if l["status"] == "revisao"),
                em_pauta=sum(int(l["total"]) for l in fila if l["status"] == "em_pauta"),
                rascunhos=sum(int(l["total"]) for l in fila if l["status"] == "rascunho")),
        )
        dados["insights"] = self._insights(dados)
        return Resultado(True, f"{total} matéria(s) no recorte.", dados)

    # ---------- partes ----------
    @staticmethod
    def _kpis(resumo, anterior, total, ativas, categorias):
        media = float(resumo["media_leituras"])
        palavras = float(resumo["media_palavras"])
        total_ant = int(anterior["total"]) if anterior is not None else None
        # sem comparação quando o período anterior não tinha matérias (a média dele não existe)
        media_ant = float(anterior["media_leituras"]) if (anterior is not None and total_ant) else None
        variacao = None   # sem comparação quando não há período anterior ou ele estava vazio
        if total_ant:
            variacao = 100.0 * (total - total_ant) / total_ant
        operacao = sum(1 for c in categorias if c["total"] > 0 and c["status"] == "ativa")
        if palavras <= 0:
            formato = "Sem texto"
        elif palavras < 300:
            formato = "Formato ágil"
        elif palavras < 800:
            formato = "Formato analítico"
        else:
            formato = "Formato investigativo"
        return dict(
            total=total, total_anterior=total_ant, variacao_total=variacao,
            editorias_operacao=operacao, editorias_ativas=ativas,
            pct_editorias=(100.0 * operacao / ativas) if ativas else 0.0,
            media_leituras=media, media_leituras_anterior=media_ant,
            delta_leituras=(media - media_ant) if media_ant is not None else None,
            soma_leituras=int(resumo["leituras"]), media_palavras=palavras,
            tempo_leitura=tempo_leitura_texto(int(palavras)) if palavras > 0 else "—", formato=formato)

    @staticmethod
    def _pontuar_autores(linhas):
        """Score 0–100 (60% quantidade, 40% média de leituras), relativo ao melhor do recorte."""
        base = [dict(id=a["id"], nome=a["nome"], cargo=a["cargo"], total=int(a["total"]),
                     leituras=int(a["leituras"]),
                     media_leituras=float(a["leituras"]) / int(a["total"])) for a in linhas]
        maximo_total = max((a["total"] for a in base), default=0)
        maximo_media = max((a["media_leituras"] for a in base), default=0)
        for a in base:
            parte_total = a["total"] / maximo_total if maximo_total else 0
            parte_media = a["media_leituras"] / maximo_media if maximo_media else 0
            a["score"] = round(100 * (0.6 * parte_total + 0.4 * parte_media), 1) if maximo_media else \
                round(100 * parte_total, 1)
        base.sort(key=lambda a: (-a["score"], -a["total"], a["nome"]))
        return base

    @staticmethod
    def _semana(datas, inicio, fim):
        """Total e média por dia da semana (média = total / quantas vezes aquele dia ocorreu no período)."""
        totais = [0] * 7
        for valor in datas:
            d = _como_data(valor)
            if d:
                totais[d.weekday()] += 1
        ocorrencias = [0] * 7
        dia = inicio.date()
        while dia <= fim.date():
            ocorrencias[dia.weekday()] += 1
            dia += timedelta(days=1)
        medias = [totais[i] / ocorrencias[i] if ocorrencias[i] else 0.0 for i in range(7)]
        maximo = max(medias) if medias else 0
        picos = [i for i, m in enumerate(medias) if maximo > 0 and m >= maximo * 0.85 and m > 0]
        return dict(rotulos=list(DIAS_SEMANA), totais=totais, medias=medias, picos=picos)

    @staticmethod
    def _serie(datas, inicio, fim):
        """Matérias ao longo do tempo, agrupadas por dia, semana ou mês conforme o tamanho do período."""
        dias = max(1, (fim.date() - inicio.date()).days + 1)
        granularidade = "dia" if dias <= 31 else ("semana" if dias <= 180 else "mes")
        contagem = {}
        for valor in datas:
            d = _como_data(valor)
            if not d:
                continue
            dia = d.date()
            if granularidade == "semana":
                dia = dia - timedelta(days=dia.weekday())
            elif granularidade == "mes":
                dia = dia.replace(day=1)
            contagem[dia] = contagem.get(dia, 0) + 1

        # eixo contínuo, com zeros nos períodos sem matérias
        chaves, atual = [], inicio.date()
        if granularidade == "semana":
            atual -= timedelta(days=atual.weekday())
        elif granularidade == "mes":
            atual = atual.replace(day=1)
        while atual <= fim.date():
            chaves.append(atual)
            if granularidade == "dia":
                atual += timedelta(days=1)
            elif granularidade == "semana":
                atual += timedelta(days=7)
            else:
                atual = (atual.replace(day=28) + timedelta(days=4)).replace(day=1)
        chaves = chaves[-MAX_PONTOS_SERIE:]
        rotulos = [(f"{c:%d/%m}" if granularidade != "mes" else f"{MESES_CURTOS[c.month - 1]}/{c:%y}") for c in chaves]
        return dict(rotulos=rotulos, valores=[contagem.get(c, 0) for c in chaves], granularidade=granularidade)

    # ---------- leitura automática ----------
    @staticmethod
    def _insights(d):
        """Frases geradas a partir dos números (sem texto fixo): o 'bilhete do secretário'."""
        k, linhas = d["kpis"], []
        if not k["total"]:
            return ["Nenhuma matéria no recorte escolhido. Amplie o período ou limpe os filtros para ver a análise."]
        top = d["categorias"][0] if d["categorias"] else None
        if top and top["total"]:
            linhas.append(f"A editoria de {top['nome']} concentrou {fmt_pct(top['percentual'])} "
                          f"do volume do recorte ({fmt_int(top['total'])} de {fmt_int(k['total'])} matérias).")
        if k["total_anterior"] == 0:
            linhas.append("Não houve matérias no período anterior, então não há base de comparação.")
        elif k["variacao_total"] is not None and k["total_anterior"] is not None:
            if k["variacao_total"] > 0.05:
                linhas.append(f"O volume cresceu {fmt_pct(k['variacao_total'])} em relação ao período anterior "
                              f"({fmt_int(k['total_anterior'])} matérias).")
            elif k["variacao_total"] < -0.05:
                linhas.append(f"O volume recuou {fmt_pct(abs(k['variacao_total']))} em relação ao período anterior "
                              f"({fmt_int(k['total_anterior'])} matérias).")
            else:
                linhas.append("O volume ficou estável em relação ao período anterior.")
        semana = d["semana"]
        if semana["picos"]:
            dias = " e ".join(DIAS_SEMANA_LONGOS[i] for i in semana["picos"][:2])
            linhas.append(f"{'O dia mais movimentado é' if len(semana['picos']) == 1 else 'Os dias mais movimentados são'} {dias}.")
        lidas = [c for c in d["categorias"] if c["total"] and c["leituras"]]
        if lidas:
            melhor = max(lidas, key=lambda c: c["media_leituras"])
            linhas.append(f"{melhor['nome']} tem a maior média de leituras por matéria ({fmt_int(melhor['media_leituras'])}).")
        vazias = [c["nome"] for c in d["categorias"] if c["total"] == 0 and c["status"] == "ativa"]
        if vazias and not d["filtro"].categoria_id:
            linhas.append("Sem matérias no recorte: " + ", ".join(vazias[:3]) + ("…" if len(vazias) > 3 else "") +
                          ". Vale equilibrar a pauta entre as editorias.")
        if d["autores"] and len(linhas) < 5:
            a = d["autores"][0]
            linhas.append(f"{a['nome']} lidera a produção, com {fmt_int(a['total'])} matéria(s) e score {fmt_dec(a['score'])}.")
        return linhas[:5]

    # ---------- exportação de dados ----------
    @staticmethod
    def linhas_csv(dados) -> list:
        """Linhas para o CSV do relatório (distribuição por editoria, autores, semana, série)."""
        linhas = [["Relatório de métricas editoriais"],
                  ["Período", dados["periodo"]["rotulo"]], ["Estado", ESTADOS.get(dados["filtro"].status, "")], [],
                  ["Indicador", "Valor"],
                  ["Total de matérias", dados["kpis"]["total"]],
                  ["Editorias em operação", dados["kpis"]["editorias_operacao"]],
                  ["Média de leituras por matéria", fmt_dec(dados["kpis"]["media_leituras"])],
                  ["Tempo médio de leitura", dados["kpis"]["tempo_leitura"]], [],
                  ["Editoria", "Matérias", "% do total", "Leituras", "Média de leituras"]]
        linhas += [[c["nome"], c["total"], fmt_dec(c["percentual"]), c["leituras"], fmt_dec(c["media_leituras"])]
                   for c in dados["categorias"]]
        linhas += [[], ["Jornalista", "Matérias", "Leituras", "Média de leituras", "Score"]]
        linhas += [[a["nome"], a["total"], a["leituras"], fmt_dec(a["media_leituras"]), fmt_dec(a["score"])]
                   for a in dados["autores"]]
        linhas += [[], ["Dia da semana", "Matérias", "Média por dia"]]
        linhas += [[r, t, fmt_dec(m, 2)] for r, t, m in zip(
            dados["semana"]["rotulos"], dados["semana"]["totais"], dados["semana"]["medias"])]
        linhas += [[], [f"Evolução ({dados['serie']['granularidade']})", "Matérias"]]
        linhas += [[r, v] for r, v in zip(dados["serie"]["rotulos"], dados["serie"]["valores"])]
        return linhas


def com_periodo(filtro: FiltroEstatisticas, **mudancas) -> FiltroEstatisticas:
    return replace(filtro, **mudancas)
