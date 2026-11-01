import copy
import json
import unittest
from datetime import datetime, timedelta

from tests._ambiente import banco_com_base, ler_fixture, LoggerMudo
from app import tempo
from app.perfil import PerfilService
from app.rede import ErroRede, RespostaHttp
from app.segundo_plano import executar_sincrono
from app.tela_tempo import AtualizadorTempo

SANTA_MARIA = {"nome": "Santa Maria", "regiao": "Rio Grande do Sul", "pais": "Brasil",
               "latitude": -29.6842, "longitude": -53.8069, "fuso": "America/Sao_Paulo"}
AGORA = datetime(2026, 10, 28, 14, 5)


def bruto():
    return json.loads(ler_fixture("open_meteo_santa_maria.json"))


def resp_json(dados, status=200):
    return RespostaHttp(status, json.dumps(dados).encode("utf-8"))


class FakeRede:
    """buscar() de mentira: devolve respostas na ordem; conta chamadas."""
    def __init__(self, *respostas):
        self.respostas, self.chamadas = list(respostas), []

    def __call__(self, url, params=None, timeout=10, cabecalhos=None, max_bytes=0):
        self.chamadas.append((url, params))
        r = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(r, Exception):
            raise r
        return r


class CodigosWmo(unittest.TestCase):
    def test_codigos_principais(self):
        casos = {0: "Céu limpo", 1: "Poucas nuvens", 3: "Nublado", 45: "Neblina", 53: "Garoa", 63: "Chuva",
                 73: "Neve", 81: "Pancadas de chuva", 95: "Tempestade"}
        for codigo, texto in casos.items():
            self.assertEqual(tempo.descrever_codigo(codigo)[0], texto)

    def test_faixas_do_enunciado(self):
        for c in (51, 53, 55, 56, 57):
            self.assertIn("Garoa", tempo.descrever_codigo(c)[0])
        for c in (61, 63, 65, 66, 67):
            self.assertIn("Chuva", tempo.descrever_codigo(c)[0])
        for c in (71, 73, 75, 77):
            self.assertIn("Neve", tempo.descrever_codigo(c)[0].replace("Grãos de neve", "Neve"))
        for c in (95, 96, 99):
            self.assertIn("Tempestade", tempo.descrever_codigo(c)[0])

    def test_simbolos_so_no_plano_basico(self):
        for codigo in list(range(0, 100)):
            simbolo = tempo.descrever_codigo(codigo)[1]
            self.assertTrue(all(ord(ch) <= 0xFFFF for ch in simbolo), codigo)

    def test_noite_e_desconhecido(self):
        self.assertEqual(tempo.descrever_codigo(0, de_dia=False)[1], "☾")
        self.assertEqual(tempo.descrever_codigo(1234), ("Condição desconhecida", "?"))
        self.assertEqual(tempo.descrever_codigo(None), ("Condição desconhecida", "?"))

    def test_direcao_do_vento(self):
        self.assertEqual(tempo.direcao_vento(0), "N")
        self.assertEqual(tempo.direcao_vento(135), "SE")
        self.assertEqual(tempo.direcao_vento(359), "N")
        self.assertEqual(tempo.direcao_vento(270), "O")
        self.assertEqual(tempo.direcao_vento(None), "")


class Interpretacao(unittest.TestCase):
    def test_fixture(self):
        v = tempo.interpretar_previsao(bruto())
        a = v["atual"]
        self.assertEqual((a["temperatura"], a["umidade"], a["vento_kmh"], a["vento_dir"]), (24.6, 52, 15, "SE"))
        self.assertEqual(a["descricao"], "Poucas nuvens")
        self.assertEqual(len(v["horas"]), 24)
        self.assertEqual(v["horas"][0]["hora"], datetime(2026, 10, 28, 14))
        self.assertEqual(len(v["dias"]), 7)
        hoje = v["dias"][0]
        self.assertEqual((hoje["maxima"], hoje["minima"], hoje["uv"]), (27.1, 15.2, 9.1))
        self.assertEqual(hoje["nascer"].strftime("%H:%M"), "05:38")
        self.assertEqual(v["dias"][1]["descricao"], "Tempestade")

    def test_resposta_invalida(self):
        for ruim in (None, {}, {"current": {}}, {"current": {"time": "2026-10-28T14:00"}}):
            with self.assertRaises(tempo.ErroPrevisao):
                tempo.interpretar_previsao(ruim)

    def test_tolera_blocos_ausentes(self):
        b = bruto()
        del b["hourly"], b["daily"]
        v = tempo.interpretar_previsao(b)
        self.assertEqual((v["horas"], v["dias"]), ([], []))
        self.assertEqual(tempo.gerar_alertas(v), [])

    def test_valores_nulos(self):
        b = bruto()
        b["hourly"]["precipitation_probability"][14] = None
        b["current"]["wind_direction_10m"] = None
        v = tempo.interpretar_previsao(b)
        self.assertIsNone(v["horas"][0]["chuva_prob"])
        self.assertEqual(v["atual"]["vento_dir"], "")


class Alertas(unittest.TestCase):
    def test_so_uv_na_fixture(self):
        alertas = tempo.gerar_alertas(tempo.interpretar_previsao(bruto()))
        self.assertEqual(len(alertas), 1)
        self.assertIn("UV", alertas[0])

    def test_limites_configuraveis(self):
        v = tempo.interpretar_previsao(bruto())
        com_chuva = tempo.gerar_alertas(v, {"chuva_prob": 20, "uv": 99})
        self.assertEqual(len(com_chuva), 1)
        self.assertIn("chuva", com_chuva[0])

    def test_regras(self):
        b = bruto()
        b["current"]["wind_speed_10m"] = 55
        b["current"]["temperature_2m"] = 37
        b["daily"]["temperature_2m_max"][0] = 37
        b["hourly"]["weather_code"][17] = 96
        b["hourly"]["precipitation_probability"][16] = 90
        texto = " ".join(tempo.gerar_alertas(tempo.interpretar_previsao(b)))
        for trecho in ("chuva (90%)", "tempestade", "Vento forte", "UV", "Calor intenso"):
            self.assertIn(trecho, texto)
        self.assertNotIn("Frio", texto)

    def test_frio(self):
        b = bruto()
        b["daily"]["temperature_2m_min"][0] = 2.5
        self.assertIn("Frio intenso", " ".join(tempo.gerar_alertas(tempo.interpretar_previsao(b))))

    def test_rascunho_de_pauta(self):
        titulo, texto = tempo.rascunho_pauta(SANTA_MARIA, tempo.interpretar_previsao(bruto()))
        self.assertLessEqual(len(titulo), 120)
        self.assertIn("Santa Maria", titulo)
        self.assertIn("open-meteo.com", texto)


class TextoDaFaixa(unittest.TestCase):
    def setUp(self):
        self.v = tempo.interpretar_previsao(bruto())

    def test_normal(self):
        t = tempo.texto_faixa(SANTA_MARIA, self.v)
        self.assertIn("SANTA MARIA • 25°C POUCAS NUVENS", t)   # 24,6 arredonda para 25

    def test_carregando_e_sem_previsao(self):
        self.assertEqual(tempo.texto_faixa(SANTA_MARIA, None, "carregando"), "SANTA MARIA • …")
        self.assertEqual(tempo.texto_faixa(SANTA_MARIA, None, "sem_previsao"), "SEM PREVISÃO")

    def test_dado_antigo(self):
        t = tempo.texto_faixa(SANTA_MARIA, self.v, "offline", datetime(2026, 10, 28, 9, 30), True)
        self.assertIn("DADO DE 09:30", t)

    def test_rotulos(self):
        self.assertEqual(tempo.rotulo_local(SANTA_MARIA), "Santa Maria, RS")
        self.assertEqual(tempo.rotulo_local({"nome": "Lisboa", "pais": "Portugal"}), "Lisboa, Portugal")
        self.assertEqual(tempo.rotulo_completo(SANTA_MARIA), "Santa Maria — Rio Grande do Sul, Brasil")


class RedeDoTempo(unittest.TestCase):
    def test_parametros_da_previsao(self):
        f = FakeRede(resp_json(bruto()))
        tempo.baixar_previsao(SANTA_MARIA, f)
        url, params = f.chamadas[0]
        self.assertEqual(url, "https://api.open-meteo.com/v1/forecast")
        self.assertEqual((params["timezone"], params["forecast_days"]), ("auto", 7))
        for campo in ("temperature_2m", "weather_code", "surface_pressure"):
            self.assertIn(campo, params["current"])
        self.assertIn("precipitation_probability", params["hourly"])
        self.assertIn("uv_index_max", params["daily"])

    def test_falhas(self):
        with self.assertRaises(ErroRede) as c:
            tempo.baixar_previsao(SANTA_MARIA, FakeRede(RespostaHttp(429)))
        self.assertEqual(c.exception.codigo, 429)
        with self.assertRaises(ErroRede):
            tempo.baixar_previsao(SANTA_MARIA, FakeRede(RespostaHttp(500)))
        with self.assertRaises(ErroRede):
            tempo.baixar_previsao(SANTA_MARIA, FakeRede(RespostaHttp(200, b"<html>")))
        with self.assertRaises(ErroRede):
            tempo.baixar_previsao(SANTA_MARIA, FakeRede(ErroRede("sem internet")))

    def test_busca_de_cidades(self):
        f = FakeRede(RespostaHttp(200, ler_fixture("geocodificacao_santa_maria.json")))
        locais = tempo.buscar_cidades_rede("Santa Maria", f)
        self.assertEqual(f.chamadas[0][1]["language"], "pt")
        self.assertEqual(len(locais), 3)          # o resultado sem coordenadas é descartado
        self.assertEqual(locais[0]["regiao"], "Rio Grande do Sul")
        self.assertEqual(tempo.rotulo_completo(locais[2]), "Santa Maria — Califórnia, Estados Unidos")

    def test_busca_sem_resultados(self):
        self.assertEqual(tempo.buscar_cidades_rede("xyzxyz", FakeRede(resp_json({"generationtime_ms": 1}))), [])

    def test_ip(self):
        local = tempo.localizar_por_ip_rede(FakeRede(RespostaHttp(200, ler_fixture("ip_localizacao.json"))))
        self.assertEqual((local["nome"], local["regiao"]), ("Porto Alegre", "Rio Grande do Sul"))
        with self.assertRaises(ErroRede):
            tempo.localizar_por_ip_rede(FakeRede(RespostaHttp(200, ler_fixture("ip_limite.json"))))
        with self.assertRaises(ErroRede):
            tempo.localizar_por_ip_rede(FakeRede(RespostaHttp(429)))


class CacheEServico(unittest.TestCase):
    def setUp(self):
        self.db = banco_com_base()
        self.s = tempo.TempoService(self.db, LoggerMudo())

    def test_grava_cache_e_reaproveita_dentro_do_ttl(self):
        f = FakeRede(resp_json(bruto()))
        r1 = self.s.obter_previsao(SANTA_MARIA, agora=AGORA, buscar=f)
        self.assertTrue(r1.ok)
        self.assertEqual((r1.dados["origem"], r1.dados["desatualizada"]), ("rede", False))
        r2 = self.s.obter_previsao(SANTA_MARIA, agora=AGORA + timedelta(minutes=10), buscar=f)
        self.assertEqual(len(f.chamadas), 1)
        self.assertEqual(r2.dados["origem"], "cache")
        self.assertEqual(r2.dados["atualizado_em"], AGORA.replace(second=0, microsecond=0))

    def test_ttl_vencido_busca_de_novo(self):
        f = FakeRede(resp_json(bruto()))
        self.s.obter_previsao(SANTA_MARIA, agora=AGORA, buscar=f)
        self.s.obter_previsao(SANTA_MARIA, agora=AGORA + timedelta(minutes=tempo.TTL_CACHE_MIN + 1), buscar=f)
        self.assertEqual(len(f.chamadas), 2)

    def test_forcar_ignora_cache(self):
        f = FakeRede(resp_json(bruto()))
        self.s.obter_previsao(SANTA_MARIA, agora=AGORA, buscar=f)
        self.s.obter_previsao(SANTA_MARIA, forcar=True, agora=AGORA, buscar=f)
        self.assertEqual(len(f.chamadas), 2)

    def test_offline_usa_cache_antigo_com_a_hora(self):
        self.s.obter_previsao(SANTA_MARIA, agora=AGORA, buscar=FakeRede(resp_json(bruto())))
        r = self.s.obter_previsao(SANTA_MARIA, agora=AGORA + timedelta(hours=3),
                                  buscar=FakeRede(ErroRede("Sem conexão.")))
        self.assertTrue(r.ok)
        self.assertTrue(r.dados["desatualizada"])
        self.assertIn("14:05", r.mensagem)   # carimbo do dado
        self.assertIn("Sem conexão", r.mensagem)

    def test_offline_sem_cache_nao_quebra(self):
        r = self.s.obter_previsao(SANTA_MARIA, agora=AGORA, buscar=FakeRede(ErroRede("Sem conexão.")))
        self.assertFalse(r.ok)
        self.assertIn("Sem previsão", r.mensagem)

    def test_resposta_estranha_nao_envenena_o_cache(self):
        r = self.s.obter_previsao(SANTA_MARIA, agora=AGORA, buscar=FakeRede(resp_json({"current": {}})))
        self.assertFalse(r.ok)
        self.assertIsNone(self.s.ler_cache(SANTA_MARIA))

    def test_cache_por_cidade(self):
        outra = dict(SANTA_MARIA, latitude=-30.03, longitude=-51.23, nome="Porto Alegre")
        f = FakeRede(resp_json(bruto()))
        self.s.obter_previsao(SANTA_MARIA, agora=AGORA, buscar=f)
        self.s.obter_previsao(outra, agora=AGORA, buscar=f)
        self.assertEqual(len(f.chamadas), 2)

    def test_cache_qualquer_marca_velho(self):
        self.s.obter_previsao(SANTA_MARIA, agora=AGORA, buscar=FakeRede(resp_json(bruto())))
        self.assertFalse(self.s.cache_qualquer(SANTA_MARIA, AGORA + timedelta(minutes=5)).dados["desatualizada"])
        self.assertTrue(self.s.cache_qualquer(SANTA_MARIA, AGORA + timedelta(hours=2)).dados["desatualizada"])


class CidadePorUsuario(unittest.TestCase):
    def setUp(self):
        self.db = banco_com_base()
        self.p = PerfilService(self.db, LoggerMudo())

    def test_salvar_e_ler(self):
        self.assertIsNone(self.p.obter_local(1))
        self.assertTrue(self.p.salvar_local(1, SANTA_MARIA).ok)
        local = self.p.obter_local(1)
        self.assertEqual((local["nome"], local["regiao"], round(local["latitude"], 2)),
                         ("Santa Maria", "Rio Grande do Sul", -29.68))
        self.assertIsNone(self.p.obter_local(2))     # é por usuário

    def test_validacao(self):
        for ruim in ({}, {"nome": "X", "latitude": 99, "longitude": 0}, {"nome": "", "latitude": 1, "longitude": 1},
                     {"nome": "X", "latitude": "abc", "longitude": 1}):
            self.assertFalse(self.p.salvar_local(1, ruim).ok)

    def test_decisao_do_ip_e_guardada(self):
        self.assertIsNone(self.p.decisao_localizacao_ip(1))
        self.p.registrar_decisao_ip(1, False)
        self.assertEqual(self.p.decisao_localizacao_ip(1), "recusa")
        self.p.registrar_decisao_ip(1, True)
        self.assertEqual(self.p.decisao_localizacao_ip(1), "aceita")

    def test_nao_atrapalha_as_preferencias_existentes(self):
        self.p.salvar_local(1, SANTA_MARIA)
        prefs = self.p.preferencias(1)
        self.assertTrue(all(isinstance(v, bool) for v in prefs.values()))


class Atualizador(unittest.TestCase):
    """AtualizadorTempo com executor síncrono e widget falso (sem Tk)."""
    class Widget:
        def __init__(self):
            self.agendados = []

        def after(self, ms, f=None):
            self.agendados.append((ms, f))

    def montar(self, buscar):
        self.db = banco_com_base()
        self.w = self.Widget()
        self.a = AtualizadorTempo(self.w, self.db, LoggerMudo(), 1, buscar=buscar, executor=executar_sincrono,
                                  agora=lambda: AGORA)
        self.avisos = 0
        self.a.adicionar_ouvinte(lambda: setattr(self, "avisos", self.avisos + 1))
        return self.a

    def test_abre_com_cidade_padrao_e_atualiza(self):
        a = self.montar(FakeRede(resp_json(bruto())))
        a.iniciar()
        self.assertEqual(a.estado, "ok")
        self.assertIn("SANTA MARIA •", a.texto_faixa())
        self.assertEqual(self.w.agendados[0][0], tempo.INTERVALO_ATUALIZACAO_MIN * 60_000)
        self.assertGreater(self.avisos, 0)

    def test_sem_internet_e_sem_cache(self):
        a = self.montar(FakeRede(ErroRede("Sem conexão.")))
        a.iniciar()
        self.assertEqual((a.estado, a.texto_faixa()), ("sem_previsao", "SEM PREVISÃO"))

    def test_sem_internet_com_cache_mostra_o_dado(self):
        a = self.montar(FakeRede(resp_json(bruto())))
        a.iniciar()
        a.buscar = FakeRede(ErroRede("Sem conexão."))
        a.agora = lambda: AGORA + timedelta(hours=1)
        a.atualizar(forcar=True)
        self.assertEqual(a.estado, "offline")
        self.assertIn("DADO DE", a.texto_faixa())

    def test_trocar_cidade_vale_na_hora(self):
        f = FakeRede(resp_json(bruto()))
        a = self.montar(f)
        a.iniciar()
        r = a.trocar_local({"nome": "Porto Alegre", "regiao": "Rio Grande do Sul", "pais": "Brasil",
                            "latitude": -30.03, "longitude": -51.23, "fuso": "auto"})
        self.assertTrue(r.ok)
        self.assertIn("PORTO ALEGRE •", a.texto_faixa())
        self.assertEqual(len(f.chamadas), 2)
        self.assertEqual(a.perfil.obter_local(1)["nome"], "Porto Alegre")

    def test_tique_periodico_reagenda(self):
        a = self.montar(FakeRede(resp_json(bruto())))
        a.iniciar()
        n = len(self.w.agendados)
        self.w.agendados[0][1]()
        self.assertEqual(len(self.w.agendados), n + 1)


if __name__ == "__main__":
    unittest.main()
