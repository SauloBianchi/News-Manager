"""
tempo.py
Backend da previsão do tempo (Open-Meteo) mostrada na faixa superior e na tela
"Previsão do Tempo". Segue o padrão dos outros serviços: a tela nunca fala com
o banco nem com a internet; ela chama o TempoService, que devolve `Resultado`.

Fonte dos dados
- Previsão: https://api.open-meteo.com/v1/forecast  (sem chave)
- Cidades:  https://geocoding-api.open-meteo.com/v1/search (language=pt)
- Termos (conferidos em 28/10/2026): uso gratuito só NÃO comercial, menos de
  10.000 chamadas/dia, 5.000/hora e 600/minuto; dados sob CC BY 4.0, exigindo a
  atribuição "Weather data by Open-Meteo.com" com link onde os dados aparecem.
- Localização aproximada por IP (opcional, só com consentimento):
  https://ipapi.co/json/ — gratuito, HTTPS, sem chave, ~1.000 consultas/dia
  (e ~30/min sem cadastro). O IP do usuário é enviado a esse serviço de terceiros.

Concorrência: as funções `baixar_*` e `buscar_cidades_rede` só usam a rede
(podem rodar em thread). Tudo que usa o banco (cache, preferências) roda na
thread principal.
"""

import json
from datetime import date, datetime, timedelta

from . import rede
from .cadastros import Resultado, _ServicoBase
from .database import ErroBanco
from .rede import ErroRede

URL_PREVISAO = "https://api.open-meteo.com/v1/forecast"
URL_GEOCODIFICACAO = "https://geocoding-api.open-meteo.com/v1/search"
URL_IP = "https://ipapi.co/json/"
URL_ATRIBUICAO = "https://open-meteo.com/"
TEXTO_ATRIBUICAO = "Dados meteorológicos: Open-Meteo.com (CC BY 4.0)"

# Cidade usada só se nada der certo (sem cidade salva, sem IP, sem busca)
CIDADE_PADRAO = {"nome": "Santa Maria", "regiao": "Rio Grande do Sul", "pais": "Brasil",
                 "latitude": -29.6842, "longitude": -53.8069, "fuso": "America/Sao_Paulo"}

TTL_CACHE_MIN = 20            # dentro disso, abre direto do cache, sem rede
INTERVALO_ATUALIZACAO_MIN = 25  # atualização automática em segundo plano
TIMEOUT_S = 10

# Regras dos alertas da redação (ajuste aqui)
LIMITES_ALERTA = {"chuva_prob": 70, "vento_kmh": 40, "uv": 8, "calor_c": 35, "frio_c": 5}

CAMPOS_ATUAIS = ("temperature_2m,apparent_temperature,relative_humidity_2m,is_day,precipitation,"
                 "weather_code,wind_speed_10m,wind_direction_10m,surface_pressure")
CAMPOS_HORARIOS = "temperature_2m,precipitation_probability,weather_code"
CAMPOS_DIARIOS = ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                  "precipitation_sum,sunrise,sunset,uv_index_max,wind_speed_10m_max")

# Símbolos Unicode do plano básico (BMP): emojis fora dele quebram o Tk de alguns Windows
_CODIGOS_WMO = {
    0: ("Céu limpo", "☀"), 1: ("Poucas nuvens", "☀"), 2: ("Parcialmente nublado", "☁"), 3: ("Nublado", "☁"),
    45: ("Neblina", "≋"), 48: ("Neblina com geada", "≋"),
    51: ("Garoa fraca", "☂"), 53: ("Garoa", "☂"), 55: ("Garoa forte", "☂"),
    56: ("Garoa congelante", "☂"), 57: ("Garoa congelante forte", "☂"),
    61: ("Chuva fraca", "☂"), 63: ("Chuva", "☂"), 65: ("Chuva forte", "☂"),
    66: ("Chuva congelante", "☂"), 67: ("Chuva congelante forte", "☂"),
    71: ("Neve fraca", "❄"), 73: ("Neve", "❄"), 75: ("Neve forte", "❄"), 77: ("Grãos de neve", "❄"),
    80: ("Pancadas de chuva fracas", "☂"), 81: ("Pancadas de chuva", "☂"), 82: ("Pancadas de chuva fortes", "☂"),
    85: ("Pancadas de neve", "❄"), 86: ("Pancadas de neve fortes", "❄"),
    95: ("Tempestade", "⚡"), 96: ("Tempestade com granizo", "⚡"), 99: ("Tempestade com granizo forte", "⚡"),
}
_PONTOS_CARDEAIS = ("N", "NE", "L", "SE", "S", "SO", "O", "NO")
_UF = {"acre": "AC", "alagoas": "AL", "amapá": "AP", "amazonas": "AM", "bahia": "BA", "ceará": "CE",
       "distrito federal": "DF", "espírito santo": "ES", "goiás": "GO", "maranhão": "MA", "mato grosso": "MT",
       "mato grosso do sul": "MS", "minas gerais": "MG", "pará": "PA", "paraíba": "PB", "paraná": "PR",
       "pernambuco": "PE", "piauí": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
       "rio grande do sul": "RS", "rondônia": "RO", "roraima": "RR", "santa catarina": "SC",
       "são paulo": "SP", "sergipe": "SE", "tocantins": "TO"}


class ErroPrevisao(ValueError):
    """A resposta do serviço de previsão veio num formato inesperado."""


# ---------------------------------------------------------------------------
# Conversões e textos
# ---------------------------------------------------------------------------
def descrever_codigo(codigo, de_dia=True):
    """(descrição, símbolo) de um weather_code da OMM/WMO. À noite, céu limpo vira lua."""
    try:
        codigo = int(codigo)
    except (TypeError, ValueError):
        return "Condição desconhecida", "?"
    descricao, simbolo = _CODIGOS_WMO.get(codigo, ("Condição desconhecida", "?"))
    if not de_dia and codigo in (0, 1):
        simbolo = "☾"
    return descricao, simbolo


def direcao_vento(graus) -> str:
    """Graus -> ponto cardeal em português (N, NE, L, SE, S, SO, O, NO)."""
    if graus is None:
        return ""
    return _PONTOS_CARDEAIS[int(((float(graus) % 360) + 22.5) // 45) % 8]


def sigla_regiao(local) -> str:
    """'Rio Grande do Sul' -> 'RS' (só para o Brasil); senão devolve a região como veio."""
    regiao = (local.get("regiao") or "").strip()
    if (local.get("pais") or "").lower() in ("brasil", "brazil"):
        return _UF.get(regiao.lower(), regiao)
    return regiao


def rotulo_local(local) -> str:
    """'Santa Maria, RS' / 'Lisboa, Portugal'."""
    nome = local.get("nome") or ""
    if (local.get("pais") or "").lower() in ("brasil", "brazil"):
        regiao = sigla_regiao(local)
        return f"{nome}, {regiao}" if regiao else nome
    pais = local.get("pais") or ""
    return f"{nome}, {pais}" if pais else nome


def rotulo_completo(local) -> str:
    """Para listas de resultados: 'Santa Maria — Rio Grande do Sul, Brasil'."""
    partes = [p for p in (local.get("regiao"), local.get("pais")) if p]
    return f"{local.get('nome', '')} — {', '.join(partes)}" if partes else local.get("nome", "")


def _num(valor, casas=0):
    if valor is None:
        return None
    return round(float(valor), casas) if casas else int(round(float(valor)))


def fmt_temp(valor) -> str:
    return "—" if valor is None else f"{int(round(valor))}°C"


def texto_faixa(local, previsao=None, estado="ok", atualizado_em=None, desatualizada=False) -> str:
    """Texto do item da faixa superior: 'SANTA MARIA • 21°C CÉU LIMPO'.
    estado: 'carregando' -> '…'; 'sem_previsao' -> 'SEM PREVISÃO'."""
    cidade = (local.get("nome") or "").upper()
    if estado == "carregando" and not previsao:
        return f"{cidade} • …"
    if not previsao:
        return "SEM PREVISÃO"
    atual = previsao["atual"]
    texto = f"{cidade} • {fmt_temp(atual['temperatura'])} {atual['descricao'].upper()}"
    texto = f"{atual['simbolo']} {texto}"
    if desatualizada and atualizado_em:
        texto += f" (DADO DE {atualizado_em:%H:%M})"
    return texto


# ---------------------------------------------------------------------------
# Leitura da resposta
# ---------------------------------------------------------------------------
def _hora(texto):
    try:
        return datetime.fromisoformat(texto)
    except (TypeError, ValueError) as erro:
        raise ErroPrevisao("Data inválida na resposta da previsão.") from erro


def _coluna(bloco, nome, tamanho):
    """Lista de `tamanho` valores (None se faltar), tolerante a respostas incompletas."""
    valores = list((bloco or {}).get(nome) or [])
    return (valores + [None] * tamanho)[:tamanho]


def interpretar_previsao(bruto) -> dict:
    """Resposta JSON da Open-Meteo -> dicionário simples para as telas.

    {'atual', 'horas' (24 a partir da hora atual), 'dias' (até 7), 'fuso'}.
    Lança ErroPrevisao se faltar o essencial (bloco 'current')."""
    if not isinstance(bruto, dict) or not isinstance(bruto.get("current"), dict):
        raise ErroPrevisao("Resposta inesperada do serviço de previsão.")
    c = bruto["current"]
    if c.get("temperature_2m") is None:
        raise ErroPrevisao("A resposta da previsão não trouxe a temperatura atual.")
    de_dia = bool(c.get("is_day", 1))
    descricao, simbolo = descrever_codigo(c.get("weather_code"), de_dia)
    agora_local = _hora(c.get("time")) if c.get("time") else datetime.now()
    atual = dict(
        hora=agora_local, temperatura=_num(c.get("temperature_2m"), 1), sensacao=_num(c.get("apparent_temperature"), 1),
        umidade=_num(c.get("relative_humidity_2m")), de_dia=de_dia, precipitacao=_num(c.get("precipitation"), 1),
        codigo=c.get("weather_code"), descricao=descricao, simbolo=simbolo,
        vento_kmh=_num(c.get("wind_speed_10m")), vento_graus=_num(c.get("wind_direction_10m")),
        vento_dir=direcao_vento(c.get("wind_direction_10m")), pressao=_num(c.get("surface_pressure")))

    horas = []
    h = bruto.get("hourly") or {}
    tempos = h.get("time") or []
    n = len(tempos)
    temps, probs, codigos = _coluna(h, "temperature_2m", n), _coluna(h, "precipitation_probability", n), \
        _coluna(h, "weather_code", n)
    inicio = agora_local.replace(minute=0, second=0, microsecond=0)
    for i, texto in enumerate(tempos):
        quando = _hora(texto)
        if quando < inicio or len(horas) >= 24:
            continue
        d, s = descrever_codigo(codigos[i], 6 <= quando.hour < 19)
        horas.append(dict(hora=quando, temperatura=_num(temps[i], 1), chuva_prob=_num(probs[i]),
                          codigo=codigos[i], descricao=d, simbolo=s))

    dias = []
    dd = bruto.get("daily") or {}
    datas = dd.get("time") or []
    m = len(datas)
    cols = {k: _coluna(dd, k, m) for k in ("weather_code", "temperature_2m_max", "temperature_2m_min",
                                            "precipitation_probability_max", "precipitation_sum", "sunrise",
                                            "sunset", "uv_index_max", "wind_speed_10m_max")}
    for i, texto in enumerate(datas[:7]):
        try:
            dia = date.fromisoformat(texto[:10])
        except (TypeError, ValueError) as erro:
            raise ErroPrevisao("Data inválida na previsão diária.") from erro
        d, s = descrever_codigo(cols["weather_code"][i])
        nascer, por = cols["sunrise"][i], cols["sunset"][i]
        dias.append(dict(data=dia, codigo=cols["weather_code"][i], descricao=d, simbolo=s,
                         minima=_num(cols["temperature_2m_min"][i], 1), maxima=_num(cols["temperature_2m_max"][i], 1),
                         chuva_prob=_num(cols["precipitation_probability_max"][i]),
                         chuva_mm=_num(cols["precipitation_sum"][i], 1),
                         nascer=_hora(nascer) if nascer else None, por=_hora(por) if por else None,
                         uv=_num(cols["uv_index_max"][i], 1), vento_max=_num(cols["wind_speed_10m_max"][i])))
    return dict(atual=atual, horas=horas, dias=dias, fuso=bruto.get("timezone"))


def gerar_alertas(previsao, limites=None) -> list:
    """Alertas da redação por regras simples (limites em LIMITES_ALERTA).
    Devolve lista de textos em português (vazia se nada passou do limite)."""
    lim = {**LIMITES_ALERTA, **(limites or {})}
    atual, horas = previsao["atual"], previsao["horas"]
    hoje = previsao["dias"][0] if previsao["dias"] else {}
    alertas = []
    probs = [h["chuva_prob"] for h in horas if h["chuva_prob"] is not None]
    pico = max(probs + ([hoje["chuva_prob"]] if hoje.get("chuva_prob") is not None else []), default=None)
    if pico is not None and pico >= lim["chuva_prob"]:
        alertas.append(f"Alta chance de chuva ({pico}%) nas próximas horas. Avalie coberturas externas e pautas ao ar livre.")
    if any((h["codigo"] or 0) >= 95 for h in horas) or (atual["codigo"] or 0) >= 95:
        alertas.append("Risco de tempestade com raios. Evite equipes em campo aberto.")
    vento = max([v for v in (atual["vento_kmh"], hoje.get("vento_max")) if v is not None], default=None)
    if vento is not None and vento >= lim["vento_kmh"]:
        alertas.append(f"Vento forte, de até {vento} km/h. Cuidado com estruturas e transmissões externas.")
    uv = hoje.get("uv")
    if uv is not None and uv >= lim["uv"]:
        alertas.append(f"Índice UV muito alto ({uv:g}). Reforce a proteção de equipes na rua.")
    maxima = max([v for v in (hoje.get("maxima"), atual["temperatura"]) if v is not None], default=None)
    if maxima is not None and maxima >= lim["calor_c"]:
        alertas.append(f"Calor intenso: máxima de {maxima:g}°C. Hidratação e pausas para quem está em campo.")
    minima = min([v for v in (hoje.get("minima"), atual["temperatura"]) if v is not None], default=None)
    if minima is not None and minima <= lim["frio_c"]:
        alertas.append(f"Frio intenso: mínima de {minima:g}°C. Atenção a geada e a ruas escorregadias.")
    return alertas


def rascunho_pauta(local, previsao) -> tuple:
    """(título, texto) de uma pauta do tempo a partir da previsão (botão 'Criar pauta do tempo')."""
    a, hoje = previsao["atual"], (previsao["dias"] or [{}])[0]
    titulo = f"Previsão do tempo para {local.get('nome', '')}: {a['descricao'].lower()}, {fmt_temp(a['temperatura'])}"
    linhas = [f"Em {rotulo_local(local)}, o tempo agora é de {a['descricao'].lower()}, com {fmt_temp(a['temperatura'])} "
              f"(sensação de {fmt_temp(a['sensacao'])})."]
    if hoje.get("maxima") is not None:
        linhas.append(f"A máxima de hoje é de {fmt_temp(hoje['maxima'])} e a mínima, de {fmt_temp(hoje['minima'])}. "
                      f"Chance de chuva de {hoje.get('chuva_prob') if hoje.get('chuva_prob') is not None else '—'}%.")
    alertas = gerar_alertas(previsao)
    if alertas:
        linhas.append("Pontos de atenção: " + " ".join(alertas))
    linhas.append("Fonte: [Open-Meteo.com](https://open-meteo.com/)")
    return titulo[:120], "\n\n".join(linhas)


# ---------------------------------------------------------------------------
# Rede (sem banco: pode rodar em thread)
# ---------------------------------------------------------------------------
def chave_cache(local) -> str:
    return f"{float(local['latitude']):.2f},{float(local['longitude']):.2f}"


def _json(resposta, servico):
    if resposta.status != 200:
        if resposta.status == 429:
            raise ErroRede(f"Limite de consultas do serviço de {servico} atingido. Tente novamente mais tarde.", 429)
        raise ErroRede(f"O serviço de {servico} respondeu com erro ({resposta.status}).", resposta.status)
    try:
        return json.loads(resposta.conteudo.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as erro:
        raise ErroRede(f"O serviço de {servico} devolveu uma resposta inválida.") from erro


def baixar_previsao(local, buscar=rede.buscar) -> dict:
    """JSON bruto da previsão (current + 24 h + 7 dias). Lança ErroRede."""
    params = {"latitude": local["latitude"], "longitude": local["longitude"], "current": CAMPOS_ATUAIS,
              "hourly": CAMPOS_HORARIOS, "daily": CAMPOS_DIARIOS, "timezone": "auto", "forecast_days": 7}
    return _json(buscar(URL_PREVISAO, params=params, timeout=TIMEOUT_S), "previsão do tempo")


def buscar_cidades_rede(nome, buscar=rede.buscar, quantidade=8) -> list:
    """Geocodificação por nome. Devolve lista de locais (pode ser vazia). Lança ErroRede."""
    params = {"name": nome, "count": quantidade, "language": "pt", "format": "json"}
    dados = _json(buscar(URL_GEOCODIFICACAO, params=params, timeout=TIMEOUT_S), "busca de cidades")
    locais = []
    for r in (dados.get("results") or []):
        if r.get("latitude") is None or r.get("longitude") is None or not r.get("name"):
            continue
        locais.append({"nome": r["name"], "regiao": r.get("admin1") or "", "pais": r.get("country") or "",
                       "latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
                       "fuso": r.get("timezone") or "auto"})
    return locais


def localizar_por_ip_rede(buscar=rede.buscar) -> dict:
    """Local aproximado pelo IP (ipapi.co). Só chamar com consentimento. Lança ErroRede."""
    dados = _json(buscar(URL_IP, timeout=TIMEOUT_S), "localização por IP")
    if not isinstance(dados, dict) or dados.get("error") or dados.get("latitude") is None \
            or dados.get("longitude") is None or not dados.get("city"):
        raise ErroRede("Não foi possível descobrir sua cidade pelo IP. Busque a cidade pelo nome.")
    return {"nome": dados["city"], "regiao": dados.get("region") or "", "pais": dados.get("country_name") or "",
            "latitude": float(dados["latitude"]), "longitude": float(dados["longitude"]),
            "fuso": dados.get("timezone") or "auto"}


# ---------------------------------------------------------------------------
# Serviço (banco: só na thread principal)
# ---------------------------------------------------------------------------
class TempoService(_ServicoBase):
    def ler_cache(self, local):
        """(bruto, atualizado_em) do cache ou None."""
        try:
            linha = self.db.obter_cache_tempo(chave_cache(local))
        except ErroBanco as e:
            self._falha_banco("Erro ao ler o cache da previsão", e)
            return None
        if not linha:
            return None
        try:
            return json.loads(linha["payload"]), linha["atualizado_em"]
        except (ValueError, TypeError):
            return None

    def _resultado_do_cache(self, local, bruto, quando, agora, desatualizada, aviso=""):
        try:
            dados = interpretar_previsao(bruto)
        except ErroPrevisao:
            return None
        dados.update(atualizado_em=quando, desatualizada=desatualizada, origem="cache", local=local)
        return Resultado(True, aviso, dados)

    def cache_fresco(self, local, agora=None):
        """Resultado pronto se o cache tem menos de TTL_CACHE_MIN minutos; senão None."""
        agora = agora or datetime.now()
        cache = self.ler_cache(local)
        if not cache or not isinstance(cache[1], datetime):
            return None
        if agora - cache[1] <= timedelta(minutes=TTL_CACHE_MIN):
            return self._resultado_do_cache(local, cache[0], cache[1], agora, False)
        return None

    def cache_qualquer(self, local, agora=None):
        """Último dado em cache, de qualquer idade (marcado como desatualizado se passou do TTL).
        Usado para abrir a faixa na hora, antes da rede responder."""
        agora = agora or datetime.now()
        cache = self.ler_cache(local)
        if not cache or not isinstance(cache[1], datetime):
            return None
        velho = agora - cache[1] > timedelta(minutes=TTL_CACHE_MIN)
        return self._resultado_do_cache(local, cache[0], cache[1], agora, velho)

    def concluir(self, local, bruto, erro, agora=None) -> Resultado:
        """Fecha a busca: com `bruto` grava o cache e devolve a previsão nova; com `erro`
        cai no cache (marcado como desatualizado) ou devolve falha com mensagem amigável."""
        agora = agora or datetime.now()
        if bruto is not None:
            try:
                dados = interpretar_previsao(bruto)
            except ErroPrevisao as e:
                erro = e
            else:
                try:
                    self.db.salvar_cache_tempo(chave_cache(local), json.dumps(bruto), agora.replace(microsecond=0))
                except ErroBanco as e:
                    self._falha_banco("Erro ao gravar o cache da previsão", e)
                dados.update(atualizado_em=agora, desatualizada=False, origem="rede", local=local)
                return Resultado(True, "", dados)
        cache = self.ler_cache(local)
        motivo = str(erro) if erro else "Falha desconhecida."
        if cache and isinstance(cache[1], datetime):
            r = self._resultado_do_cache(local, cache[0], cache[1], agora, True,
                                         f"Sem conexão com a previsão: mostrando o último dado ({cache[1]:%H:%M}). {motivo}")
            if r:
                return r
        return Resultado(False, f"Sem previsão disponível. {motivo}")

    def obter_previsao(self, local, forcar=False, agora=None, buscar=rede.buscar) -> Resultado:
        """Versão síncrona (testes, seed): cache fresco -> rede -> cache antigo."""
        if not forcar:
            r = self.cache_fresco(local, agora)
            if r:
                return r
        try:
            bruto, erro = baixar_previsao(local, buscar), None
        except ErroRede as e:
            bruto, erro = None, e
        return self.concluir(local, bruto, erro, agora)
