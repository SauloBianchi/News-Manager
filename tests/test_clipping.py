import json
import unittest
from datetime import datetime, timedelta

from tests._ambiente import banco_com_base, ler_fixture, LoggerMudo
from app import clipping
from app.clipping import ClippingService, FiltroClipping, aplicar_filtros, coletar_feeds, sugerir_categoria
from app.rede import ErroRede, RespostaHttp

AGORA = datetime(2026, 10, 28, 12, 0)
URL_A, URL_B, URL_C = "https://a.exemplo.com/politica.xml", "https://a.exemplo.com/esporte.xml", "https://b.exemplo.gov.br/feed.atom"


def rss(*itens):
    corpo = "".join(f"<item><title>{t}</title><link>https://x.exemplo.com/{clipping.slug(t)}</link>"
                    f"<guid>g-{clipping.slug(t)}</guid><pubDate>{d}</pubDate><description>{r}</description></item>"
                    for t, d, r in itens)
    return f"<rss version='2.0'><channel><title>c</title>{corpo}</channel></rss>".encode()


def data(horas_atras):
    return (AGORA - timedelta(hours=horas_atras)).strftime("%a, %d %b %Y %H:%M:%S +0000")


CATALOGO = [
    {"chave": "ja", "nome": "Jornal A", "ativo": True, "proprio": False, "feeds": [
        {"secao": "Política", "url": URL_A, "categoria_sugerida": "politica", "chave_feed": "ja:politica", "verificacao": "indireta"},
        {"secao": "Esporte", "url": URL_B, "categoria_sugerida": "esportes", "chave_feed": "ja:esporte", "verificacao": "indireta"}]},
    {"chave": "jb", "nome": "Agência B", "ativo": True, "proprio": False, "feeds": [
        {"secao": "Geral", "url": URL_C, "categoria_sugerida": None, "chave_feed": "jb:geral", "verificacao": "indireta"}]},
    {"chave": "jc", "nome": "Jornal C", "ativo": False, "proprio": False, "feeds": [
        {"secao": "Geral", "url": "https://c.exemplo.com/f.xml", "categoria_sugerida": None, "chave_feed": "jc:geral"}]},
    {"chave": "jd", "nome": "Sem feed", "ativo": True, "proprio": False, "feeds": []},
]


class Rede:
    """buscar() falso, com respostas por URL. Cada valor: RespostaHttp, Exception ou lista (uma por tentativa)."""
    def __init__(self, mapa):
        self.mapa, self.chamadas = mapa, []

    def __call__(self, url, params=None, timeout=10, cabecalhos=None, max_bytes=0):
        self.chamadas.append((url, dict(cabecalhos or {})))
        r = self.mapa[url]
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if isinstance(r, Exception):
            raise r
        return r


def mapa_padrao():
    return {
        URL_A: RespostaHttp(200, rss(("Lula e Congresso fecham acordo da reforma tributária", data(2), "Texto sobre <b>política</b>"),
                                     ("Ministro nega crise elétrica", data(30), "Resumo antigo"),
                                     ("Prefeito inaugura praça", data(1), "Obras na cidade")),
                            {"ETag": '"abc"', "Last-Modified": "Wed, 28 Oct 2026 10:00:00 GMT"}),
        URL_B: RespostaHttp(200, rss(("Inter vence o Gre-Nal por 2 a 1", data(3), "Futebol no Beira-Rio"),
                                     ("Tênis: brasileiro avança em Paris", data(5), "Esporte"))),
        URL_C: RespostaHttp(200, ler_fixture("atom_exemplo.xml")),
    }


class Base(unittest.TestCase):
    def setUp(self):
        self.db = banco_com_base()
        self.s = ClippingService(self.db, LoggerMudo(), catalogo=CATALOGO)
        self.filtro = FiltroClipping(fontes=["ja", "jb"], periodo_horas=48, limite_por_fonte=10)

    def buscar(self, rede=None, filtro=None, agora=AGORA):
        return self.s.buscar_agora(1, filtro or self.filtro, rede or Rede(mapa_padrao()), agora)


def item(n, fonte="ja", secao="Política", titulo="Título de teste", resumo="", horas=1, imagem=None, noticia=None, url=None):
    return {"id": n, "fonte_chave": fonte, "secao": secao, "guid": f"g{n}", "url": url or f"https://x.com/{n}",
            "titulo": titulo, "resumo": resumo, "publicado_em": AGORA - timedelta(hours=horas), "coletado_em": AGORA,
            "imagem_url": imagem, "noticia_id": noticia}


class Filtros(unittest.TestCase):
    def aplicar(self, itens, **kw):
        return aplicar_filtros(itens, FiltroClipping(fontes=[], **kw), AGORA)

    def test_periodo(self):
        itens = [item(1, horas=1), item(2, horas=30), item(3, horas=200)]
        self.assertEqual([i["id"] for i in self.aplicar(itens, periodo_horas=24)], [1])
        self.assertEqual([i["id"] for i in self.aplicar(itens, periodo_horas=48)], [1, 2])
        self.assertEqual(len(self.aplicar(itens, periodo_horas=168)), 2)
        self.assertEqual([i["id"] for i in self.aplicar([item(1, horas=1), item(2, horas=20)], periodo_horas=0)], [1])  # "hoje" = desde 00:00

    def test_incluir_ignora_acento_e_caixa(self):
        itens = [item(1, titulo="Reforma TRIBUTÁRIA avança"), item(2, titulo="Futebol"), item(3, resumo="trata da reforma tributaria")]
        self.assertEqual({i["id"] for i in self.aplicar(itens, incluir=["reforma tributária"])}, {1, 3})

    def test_incluir_basta_uma_palavra(self):
        itens = [item(1, titulo="Lula viaja"), item(2, titulo="Congresso vota"), item(3, titulo="Chuva forte")]
        self.assertEqual({i["id"] for i in self.aplicar(itens, incluir=["lula", "congresso"])}, {1, 2})

    def test_palavra_inteira_e_curinga(self):
        itens = [item(1, titulo="Economia em alta"), item(2, titulo="Uma economista fala"), item(3, titulo="Gol do Inter")]
        self.assertEqual({i["id"] for i in self.aplicar(itens, incluir=["economia"])}, {1})
        self.assertEqual({i["id"] for i in self.aplicar(itens, incluir=["econom*"])}, {1, 2})
        self.assertEqual({i["id"] for i in self.aplicar(itens, incluir=["gol"])}, {3})
        self.assertEqual(self.aplicar([item(1, titulo="Golpe de estado")], incluir=["gol"]), [])

    def test_excluir(self):
        itens = [item(1, titulo="Futebol e política"), item(2, titulo="Só política")]
        self.assertEqual([i["id"] for i in self.aplicar(itens, excluir=["futebol"])], [2])

    def test_texto_de_palavras(self):
        self.assertEqual(clipping.lista_de_palavras("Lula, congresso; reforma tributária\n  "), ["Lula", "congresso", "reforma tributária"])

    def test_so_com_imagem(self):
        itens = [item(1, imagem="https://i.com/a.jpg"), item(2)]
        self.assertEqual([i["id"] for i in self.aplicar(itens, so_com_imagem=True)], [1])

    def test_limite_por_jornal_fica_com_os_mais_novos(self):
        itens = [item(n, fonte="ja", horas=n) for n in range(1, 6)] + [item(10 + n, fonte="jb", horas=n) for n in range(1, 4)]
        r = self.aplicar(itens, limite_por_fonte=2)
        self.assertEqual(sorted(i["id"] for i in r), [1, 2, 11, 12])

    def test_importados_ocultos_ou_marcados(self):
        itens = [item(1, noticia=77), item(2)]
        self.assertEqual([i["id"] for i in self.aplicar(itens, ocultar_importados=True)], [2])
        r = self.aplicar(itens, ocultar_importados=False)
        self.assertEqual({i["id"]: i["ja_importado"] for i in r}, {1: True, 2: False})

    def test_deduplica_por_guid_e_por_link(self):
        itens = [item(1), {**item(2), "guid": "g1"}, {**item(3), "fonte_chave": "jb", "url": "https://x.com/1/?utm=1"}]
        self.assertEqual(len(self.aplicar(itens)), 1)

    def test_secoes_escolhidas(self):
        itens = [item(1, secao="Política"), item(2, secao="Esporte")]
        r = aplicar_filtros(itens, FiltroClipping(fontes=[]), AGORA, {"ja": {"Esporte"}})
        self.assertEqual([i["id"] for i in r], [2])

    def test_ordens(self):
        itens = [item(1, titulo="Zebra", horas=1), item(2, titulo="Árvore", horas=5), item(3, fonte="jb", titulo="Mouse", horas=3)]
        self.assertEqual([i["id"] for i in self.aplicar(itens, ordem="recentes")], [1, 3, 2])
        self.assertEqual([i["id"] for i in self.aplicar(itens, ordem="titulo")], [2, 3, 1])
        self.assertEqual([i["id"] for i in self.aplicar(itens, ordem="fonte")], [1, 2, 3])

    def test_item_sem_data_usa_coleta(self):
        sem = {**item(1), "publicado_em": None}
        self.assertEqual(len(self.aplicar([sem], periodo_horas=24)), 1)

    def test_nao_altera_a_lista_original(self):
        itens = [item(1), item(2)]
        copia = [dict(i) for i in itens]
        self.aplicar(itens)
        self.assertEqual(itens, copia)

    def test_serializacao_do_filtro(self):
        f = FiltroClipping(fontes=["ja"], incluir=["a"], periodo_horas=7)
        self.assertEqual(FiltroClipping.de_dict(f.para_dict()), f)


CATEGORIAS = [{"id": 1, "nome": "Política"}, {"id": 2, "nome": "Esportes"}, {"id": 3, "nome": "Tecnologia"},
              {"id": 4, "nome": "Economia"}, {"id": 5, "nome": "Mundo"}]


class MapeamentoDeEditoria(unittest.TestCase):
    def test_dica_do_catalogo(self):
        self.assertEqual(sugerir_categoria("Qualquer coisa", "", "Geral", "economia", CATEGORIAS), 4)

    def test_nome_da_secao(self):
        self.assertEqual(sugerir_categoria("Algo", "", "Esporte", None, CATEGORIAS), 2)
        self.assertEqual(sugerir_categoria("Algo", "", "Poder e Política", None, CATEGORIAS), 1)

    def test_palavras_do_titulo(self):
        self.assertEqual(sugerir_categoria("Inter vence o Gre-Nal no Beira-Rio", "", "Geral", None, CATEGORIAS), 2)
        self.assertEqual(sugerir_categoria("Dólar fecha em alta e juros sobem", "", "Últimas", None, CATEGORIAS), 4)
        self.assertEqual(sugerir_categoria("Startup lança inteligência artificial", "", "Últimas", None, CATEGORIAS), 3)

    def test_sem_pista_devolve_none(self):
        self.assertIsNone(sugerir_categoria("Gato adota cachorro", "Fofura", "Geral", None, CATEGORIAS))

    def test_editoria_inexistente_cai_no_proximo_criterio(self):
        so_politica = [{"id": 1, "nome": "Política"}]
        self.assertIsNone(sugerir_categoria("Inter vence o Gre-Nal", "", "Geral", "esportes", so_politica))


class Coleta(Base):
    def test_previa_basica(self):
        r = self.buscar()
        self.assertTrue(r.ok)
        titulos = [i["titulo"] for i in r.dados["itens"]]
        self.assertIn("Inter vence o Gre-Nal por 2 a 1", titulos)
        self.assertIn("Economia cresce 0,6% no trimestre — IBGE", titulos)
        self.assertEqual(r.dados["falhas"], [])
        self.assertFalse(any(i["ja_importado"] for i in r.dados["itens"]))

    def test_so_pede_jornais_ativos_e_escolhidos(self):
        rede = Rede(mapa_padrao())
        self.buscar(rede, FiltroClipping(fontes=["ja"]))
        self.assertEqual({u for u, _ in rede.chamadas}, {URL_A, URL_B})
        rede = Rede(mapa_padrao())
        self.s.buscar_agora(1, FiltroClipping(fontes=["jc"]), rede, AGORA)   # inativo, nada a buscar
        self.assertEqual(rede.chamadas, [])

    def test_escolha_de_secoes(self):
        rede = Rede(mapa_padrao())
        r = self.buscar(rede, FiltroClipping(fontes=["ja"], feeds=["ja:esporte"], periodo_horas=48))
        self.assertEqual([u for u, _ in rede.chamadas], [URL_B])
        self.assertTrue(all(i["secao"] == "Esporte" for i in r.dados["itens"]))

    def test_nada_escolhido(self):
        self.assertFalse(self.s.buscar_agora(1, FiltroClipping(fontes=["jd"]), Rede({}), AGORA).ok)

    def test_filtros_na_previa(self):
        f = FiltroClipping(fontes=["ja"], incluir=["lula", "gre-nal"], excluir=["praça"], periodo_horas=24)
        r = self.buscar(filtro=f)
        self.assertEqual(sorted(i["titulo"] for i in r.dados["itens"]),
                         ["Inter vence o Gre-Nal por 2 a 1", "Lula e Congresso fecham acordo da reforma tributária"])

    def test_um_feed_fora_do_ar_nao_derruba_os_outros(self):
        m = mapa_padrao()
        m[URL_A] = RespostaHttp(404)
        m[URL_B] = [ErroRede("O servidor demorou demais para responder (tempo esgotado).")]
        m[URL_C] = RespostaHttp(200, b"<html><body>manutencao</body></html>")
        r = self.buscar(Rede(m))
        motivos = {f["secao"]: f["motivo"] for f in r.dados["falhas"]}
        self.assertEqual(len(motivos), 3)
        self.assertIn("404", motivos["Política"])
        self.assertIn("tempo esgotado", motivos["Esporte"])
        self.assertIn("HTML", motivos["Geral"])
        self.assertIn("3 fonte(s) com erro", r.mensagem)

    def test_falha_parcial_mantem_o_que_funcionou(self):
        m = mapa_padrao()
        m[URL_A] = RespostaHttp(500)
        r = self.buscar(Rede(m))
        self.assertEqual(len(r.dados["falhas"]), 1)
        self.assertTrue(any(i["fonte_chave"] == "ja" and i["secao"] == "Esporte" for i in r.dados["itens"]))
        self.assertTrue(any(i["fonte_chave"] == "jb" for i in r.dados["itens"]))

    def test_tenta_duas_vezes_em_erro_de_rede_e_500_mas_nao_em_404(self):
        m = {URL_A: [ErroRede("falha"), RespostaHttp(200, mapa_padrao()[URL_A].conteudo)]}
        rede = Rede(m)
        r = coletar_feeds([{"fonte_chave": "ja", "fonte_nome": "A", "secao": "P", "url": URL_A}], {}, rede, AGORA, pausa=0)
        self.assertEqual((r[0]["status"], len(rede.chamadas)), ("ok", 2))
        rede = Rede({URL_A: RespostaHttp(404)})
        r = coletar_feeds([{"fonte_chave": "ja", "fonte_nome": "A", "secao": "P", "url": URL_A}], {}, rede, AGORA, pausa=0)
        self.assertEqual((r[0]["status"], len(rede.chamadas)), ("erro", 1))
        rede = Rede({URL_A: RespostaHttp(503)})
        r = coletar_feeds([{"fonte_chave": "ja", "fonte_nome": "A", "secao": "P", "url": URL_A}], {}, rede, AGORA, pausa=0)
        self.assertEqual((r[0]["status"], len(rede.chamadas)), ("erro", 2))

    def test_intervalo_minimo_de_15_minutos(self):
        rede = Rede(mapa_padrao())
        self.buscar(rede)
        feitas = len(rede.chamadas)
        r = self.buscar(rede, agora=AGORA + timedelta(minutes=10))
        self.assertEqual(len(rede.chamadas), feitas)            # nenhuma requisição nova
        self.assertTrue(any(i["fonte_chave"] == "ja" for i in r.dados["itens"]))   # prévia vem dos itens guardados
        self.assertTrue(all(x["status"] == "em_cache" for x in r.dados["resultados"]))
        self.buscar(rede, agora=AGORA + timedelta(minutes=16))
        self.assertEqual(len(rede.chamadas), feitas * 2)

    def test_get_condicional(self):
        rede = Rede(mapa_padrao())
        self.buscar(rede)
        rede2 = Rede({**mapa_padrao(), URL_A: RespostaHttp(304)})
        r = self.buscar(rede2, agora=AGORA + timedelta(minutes=30))
        enviado = dict(rede2.chamadas)[URL_A]
        self.assertEqual(enviado["If-None-Match"], '"abc"')
        self.assertEqual(enviado["If-Modified-Since"], "Wed, 28 Oct 2026 10:00:00 GMT")
        self.assertEqual(r.dados["falhas"], [])
        self.assertTrue(any(x["status"] == "nao_modificado" for x in r.dados["resultados"]))

    def test_sem_duplicados_entre_execucoes(self):
        self.buscar()
        r = self.buscar(agora=AGORA + timedelta(minutes=20))
        titulos = [i["titulo"] for i in r.dados["itens"]]
        self.assertEqual(len(titulos), len(set(titulos)))
        n = self.db._rodar("SELECT COUNT(*) AS n FROM clipping_itens", fetch=True)[0]["n"]
        self.assertEqual(n, 3 + 2 + 2)

    def test_testar_fontes(self):
        m = mapa_padrao()
        m[URL_B] = RespostaHttp(404)
        r = self.s.testar_fontes(1, Rede(m), AGORA)
        estados = {l["secao"]: l["ok"] for l in r.dados}
        self.assertEqual(estados, {"Política": True, "Esporte": False, "Geral": True})
        self.assertIn("2 de 3", r.mensagem)

    def test_fontes_ativas_por_usuario(self):
        self.assertTrue(next(f for f in self.s.fontes(1) if f["chave"] == "ja")["ativo"])
        self.s.definir_fonte_ativa(1, "ja", False)
        self.s.definir_fonte_ativa(1, "jc", True)
        f = {x["chave"]: x["ativo"] for x in self.s.fontes(1)}
        self.assertFalse(f["ja"])
        self.assertTrue(f["jc"])
        self.assertFalse(f["jd"])                                   # sem feeds nunca fica ativa
        self.assertTrue({x["chave"]: x["ativo"] for x in self.s.fontes(2)}["ja"])   # é por usuário

    def test_feed_proprio(self):
        self.assertFalse(self.s.salvar_feed_proprio(1, "X", "https://a.com/f.xml").ok)          # nome curto
        self.assertFalse(self.s.salvar_feed_proprio(1, "Meu jornal", "ftp://a.com/f.xml").ok)    # esquema
        self.assertFalse(self.s.salvar_feed_proprio(1, "Meu jornal", "javascript:alert(1)").ok)
        r = self.s.salvar_feed_proprio(1, "Meu jornal", "https://meu.exemplo.com/rss.xml", "Cidade")
        self.assertTrue(r.ok)
        self.assertFalse(self.s.salvar_feed_proprio(1, "Meu jornal", "https://meu.exemplo.com/rss.xml").ok)  # repetido
        meu = next(f for f in self.s.fontes(1) if f.get("proprio"))
        self.assertEqual((meu["nome"], meu["feeds"][0]["secao"], meu["ativo"]), ("Meu jornal", "Cidade", True))
        self.assertEqual(self.s.feeds_do_filtro(2, FiltroClipping(fontes=[meu["chave"]])), [])   # outro usuário não vê
        self.assertTrue(self.s.remover_feed_proprio(1, r.dados).ok)
        self.assertFalse(any(f.get("proprio") for f in self.s.fontes(1)))

    def test_validar_feed_proprio(self):
        ok = clipping.validar_feed("https://x.exemplo.com/f.xml", Rede({"https://x.exemplo.com/f.xml": mapa_padrao()[URL_A]}))
        self.assertEqual(ok["total"], 3)
        for url, resp, erro in (("ftp://x.com/f", None, ErroRede), ("https://x.com/a", RespostaHttp(404), ErroRede),
                                ("https://x.com/b", RespostaHttp(200, b"<html></html>"), clipping.ErroFeed)):
            with self.assertRaises(erro):
                clipping.validar_feed(url, Rede({url: resp}))


class Importacao(Base):
    def previa(self, **kw):
        return self.buscar(filtro=FiltroClipping(fontes=["ja", "jb"], periodo_horas=48, **kw)).dados["itens"]

    def test_cria_materias_em_pauta_com_atribuicao_e_selo(self):
        itens = self.previa()
        r = self.s.importar(1, itens, agora=AGORA)
        self.assertTrue(r.ok)
        self.assertEqual(r.dados["importadas"], len(itens))
        noticias = self.db._rodar("SELECT * FROM noticias", fetch=True)
        self.assertEqual(len(noticias), len(itens))
        self.assertTrue(all(n["status"] == "em_pauta" for n in noticias))
        for n in noticias:
            self.assertTrue(n["fonte_nome"] and n["fonte_url"].startswith("https://") and n["fonte_guid"])
            self.assertIn(f"Fonte: [{n['fonte_nome']}](", n["conteudo"])
            self.assertIn("Conteúdo de terceiros", n["conteudo"])
            self.assertIsNone(n["imagem"])                     # nada de baixar imagens
            self.assertEqual(n["etiquetas"], "Clipping")

    def test_autor_clipping_criado_uma_vez(self):
        self.s.importar(1, self.previa(), agora=AGORA)
        nomes = [a["nome"] for a in self.db._rodar("SELECT nome FROM autores", fetch=True)]
        self.assertIn("Clipping — Jornal A", nomes)
        self.assertIn("Clipping — Agência B", nomes)
        self.assertEqual(len(nomes), len(set(nomes)))

    def test_editoria_automatica_e_manual(self):
        itens = self.previa()
        self.s.importar(1, itens, agora=AGORA)
        cat = {n["titulo"]: n["categoria_id"] for n in self.db._rodar("SELECT titulo, categoria_id FROM noticias", fetch=True)}
        self.assertEqual(cat["Inter vence o Gre-Nal por 2 a 1"], 2)
        self.assertEqual(cat["Lula e Congresso fecham acordo da reforma tributária"], 1)
        self.assertEqual(cat["Economia cresce 0,6% no trimestre — IBGE"], 4)
        db2 = banco_com_base()
        s2 = ClippingService(db2, LoggerMudo(), catalogo=CATALOGO)
        previa = s2.buscar_agora(1, self.filtro, Rede(mapa_padrao()), AGORA).dados["itens"]
        s2.importar(1, previa, categoria_id=3, agora=AGORA)
        self.assertEqual({n["categoria_id"] for n in db2._rodar("SELECT categoria_id FROM noticias", fetch=True)}, {3})

    def test_nunca_publica(self):
        itens = self.previa()
        for ruim in ("publicado", "qualquer"):
            r = self.s.importar(1, itens, status_destino=ruim, agora=AGORA)
            self.assertFalse(r.ok)
        self.assertEqual(self.db._rodar("SELECT COUNT(*) AS n FROM noticias", fetch=True)[0]["n"], 0)
        self.assertTrue(self.s.importar(1, itens[:1], status_destino="rascunho", agora=AGORA).ok)

    def test_nao_importa_duas_vezes(self):
        itens = self.previa()
        self.s.importar(1, itens, agora=AGORA)
        r = self.s.importar(1, itens, agora=AGORA)           # mesma lista de novo
        self.assertEqual((r.dados["importadas"], r.dados["existentes"]), (0, len(itens)))
        self.assertEqual(self.db._rodar("SELECT COUNT(*) AS n FROM noticias", fetch=True)[0]["n"], len(itens))
        nova = self.buscar(agora=AGORA + timedelta(minutes=20)).dados["itens"]
        self.assertEqual(nova, [])                            # importados ficam ocultos na prévia seguinte
        todos = self.buscar(filtro=FiltroClipping(fontes=["ja", "jb"], periodo_horas=48, ocultar_importados=False),
                            agora=AGORA + timedelta(minutes=40)).dados["itens"]
        self.assertTrue(all(i["ja_importado"] for i in todos))

    def test_materia_apagada_pode_ser_importada_de_novo(self):
        itens = self.previa()
        r = self.s.importar(1, itens[:1], agora=AGORA)
        self.db.excluir_noticia(r.dados["ids"][0])
        outra = self.s.importar(1, itens[:1], agora=AGORA)
        self.assertEqual(outra.dados["importadas"], 1)

    def test_titulo_longo_e_caracteres_do_link(self):
        longo = {**item(901, fonte="ja", titulo="T" * 300, resumo="resumo"), "fonte_nome": "Jornal [A]",
                 "url": "https://x.com/a_(b) c"}
        self.db.inserir_itens_clipping([{**longo, "guid": "g901"}], AGORA)
        real = self.db._rodar("SELECT id FROM clipping_itens", fetch=True)[0]["id"]
        longo["id"] = real
        r = self.s.importar(1, [longo], agora=AGORA)
        self.assertTrue(r.ok, r.mensagem)
        n = self.db._rodar("SELECT * FROM noticias", fetch=True)[0]
        self.assertLessEqual(len(n["titulo"]), 120)
        self.assertIn("[Jornal A](https://x.com/a_%28b%29%20c)", n["conteudo"])

    def test_resumo_na_notificacao_e_historico(self):
        itens = self.previa()
        r = self.s.importar(1, itens, nome="Teste", falhas_fontes=1, agora=AGORA)
        self.assertIn("1 fonte(s) com erro", r.mensagem)
        notificacoes = self.db._rodar("SELECT * FROM notificacoes", fetch=True)
        self.assertEqual(len(notificacoes), 1)            # só o resumo; nada de uma por matéria
        self.assertIn("Clipping", notificacoes[0]["titulo"])
        h = self.s.historico().dados
        self.assertEqual((h[0]["importadas"], h[0]["falhas"], h[0]["origem"]), (len(itens), 1, "manual"))

    def test_sem_itens_e_sem_editoria(self):
        self.assertFalse(self.s.importar(1, [], agora=AGORA).ok)
        self.assertFalse(self.s.importar(1, self.previa(), categoria_id=999, agora=AGORA).ok)


class ImportacoesSalvas(Base):
    def test_crud_e_validacao(self):
        f = FiltroClipping(fontes=["ja"], incluir=["lula"], excluir=["praça"], periodo_horas=24, limite_por_fonte=5,
                           so_com_imagem=True, ordem="titulo", status_destino="revisao", feeds=["ja:politica"])
        self.assertFalse(self.s.salvar_importacao(1, "", f).ok)
        self.assertFalse(self.s.salvar_importacao(1, "Vazia", FiltroClipping()).ok)
        self.assertFalse(self.s.salvar_importacao(1, "Publica", FiltroClipping(fontes=["ja"], status_destino="publicado")).ok)
        r = self.s.salvar_importacao(1, "Política do dia – A", f, automatica=True)
        self.assertTrue(r.ok)
        self.assertFalse(self.s.salvar_importacao(1, "política do dia – a", f).ok)           # nome repetido
        lista = self.s.listar_importacoes(1).dados
        self.assertEqual(lista[0]["filtro"], FiltroClipping(**{**f.para_dict(), "ocultar_importados": True}))
        self.assertTrue(lista[0]["automatica"])
        f.limite_por_fonte = 3
        self.assertTrue(self.s.salvar_importacao(1, "Política do dia – A", f, False, r.dados).ok)   # edição mantém o nome
        self.assertEqual(self.s.listar_importacoes(1).dados[0]["limite_por_fonte"], 3)
        self.assertEqual(self.s.listar_importacoes(2).dados, [])
        self.assertTrue(self.s.excluir_importacao(r.dados).ok)
        self.assertEqual(self.s.listar_importacoes(1).dados, [])

    def test_rodar_agora(self):
        r = self.s.salvar_importacao(1, "Tudo", FiltroClipping(fontes=["ja", "jb"], periodo_horas=48))
        res = self.s.executar_importacao(1, r.dados, Rede(mapa_padrao()), agora=AGORA)
        self.assertTrue(res.ok)
        self.assertGreater(res.dados["importadas"], 0)
        self.assertTrue(all(n["status"] == "em_pauta" for n in self.db._rodar("SELECT status FROM noticias", fetch=True)))
        again = self.s.executar_importacao(1, r.dados, Rede(mapa_padrao()), agora=AGORA + timedelta(minutes=20))
        self.assertEqual(again.dados["importadas"], 0)
        self.assertIn("Nada de novo", again.mensagem)
        self.assertEqual(self.s.listar_importacoes(1).dados[0]["ultima_execucao"], AGORA + timedelta(minutes=20))

    def test_rodar_agora_com_fonte_com_erro(self):
        r = self.s.salvar_importacao(1, "Tudo", FiltroClipping(fontes=["ja", "jb"], periodo_horas=48))
        m = mapa_padrao()
        m[URL_A] = RespostaHttp(404)
        res = self.s.executar_importacao(1, r.dados, Rede(m), agora=AGORA)
        self.assertTrue(res.ok)
        self.assertIn("1 fonte(s) com erro", res.mensagem)

    def test_automatica_uma_vez_por_dia(self):
        a = self.s.salvar_importacao(1, "Auto", FiltroClipping(fontes=["ja"], periodo_horas=48), automatica=True).dados
        self.s.salvar_importacao(1, "Manual", FiltroClipping(fontes=["ja"], periodo_horas=48), automatica=False)
        hoje = AGORA.date()
        self.assertEqual([i["nome"] for i in self.s.automaticas_pendentes(1, hoje)], ["Auto"])
        self.s.executar_importacao(1, a, Rede(mapa_padrao()), "auto", AGORA)
        self.assertEqual(self.s.automaticas_pendentes(1, hoje), [])
        self.assertEqual(len(self.s.automaticas_pendentes(1, hoje + timedelta(days=1))), 1)
        self.assertEqual(self.s.historico().dados[0]["origem"], "auto")


class CatalogoReal(unittest.TestCase):
    def test_catalogo_versionado_e_valido(self):
        fontes = clipping.carregar_catalogo()
        chaves = [f["chave"] for f in fontes]
        self.assertEqual(len(chaves), len(set(chaves)))
        for nome in ("g1", "folha", "estadao", "agencia_brasil", "uol", "correio_do_povo", "gzh", "bbc_brasil",
                     "dw_brasil", "guardian", "bbc_news"):
            self.assertIn(nome, chaves)
        urls = []
        for f in fontes:
            for feed in f["feeds"]:
                self.assertTrue(feed["url"].startswith("https://"), feed["url"])
                self.assertIn(feed["verificacao"], ("indireta", "nao_verificada"))
                self.assertEqual(bool(feed["verificado_em"]), feed["verificacao"] == "indireta")
                urls.append(feed["url"])
            if not f["feeds"] or all(x["verificacao"] == "nao_verificada" for x in f["feeds"]):
                self.assertFalse(f["ativo"], f["chave"])   # nada não verificado vem ligado
        self.assertEqual(len(urls), len(set(urls)))
        chaves_feed = [x["chave_feed"] for f in fontes for x in f["feeds"]]
        self.assertEqual(len(chaves_feed), len(set(chaves_feed)))


if __name__ == "__main__":
    unittest.main()
