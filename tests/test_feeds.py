import os
import time
import unittest
from datetime import datetime

from tests._ambiente import ler_fixture
from app import feeds
from app.feeds import ErroFeed, interpretar_data_feed, interpretar_feed, limpar_html

BASE = "https://jornal.exemplo.com.br/"


class LimpezaDeHtml(unittest.TestCase):
    def test_tags_e_entidades(self):
        self.assertEqual(limpar_html("<p>Ação do <b>governo</b> &amp; da oposi&ccedil;&atilde;o&nbsp;marcou</p>"),
                         "Ação do governo & da oposição marcou")

    def test_script_e_estilo_somem(self):
        self.assertEqual(limpar_html("Oi<script>alert(1)</script><style>.a{}</style> mundo"), "Oi mundo")

    def test_html_escapado_duas_vezes(self):
        self.assertEqual(limpar_html("&lt;p&gt;Texto&lt;/p&gt;"), "Texto")

    def test_espacos_e_quebras(self):
        self.assertEqual(limpar_html("a<br/>b\n\n  c\t\td"), "a b c d")

    def test_limite_corta_em_palavra(self):
        t = limpar_html("palavra " * 50, 40)
        self.assertLessEqual(len(t), 40)
        self.assertTrue(t.endswith("…"))

    def test_vazio(self):
        self.assertEqual(limpar_html(None), "")
        self.assertEqual(limpar_html(""), "")


class Datas(unittest.TestCase):
    def setUp(self):
        self.tz = os.environ.get("TZ")
        if hasattr(time, "tzset"):
            os.environ["TZ"] = "America/Sao_Paulo"
            time.tzset()

    def tearDown(self):
        if hasattr(time, "tzset"):
            if self.tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = self.tz
            time.tzset()

    @unittest.skipUnless(hasattr(time, "tzset"), "fuso só configurável em Unix")
    def test_rfc822_e_iso_viram_horario_local(self):
        esperado = datetime(2026, 10, 28, 10, 15)
        self.assertEqual(interpretar_data_feed("Wed, 28 Oct 2026 10:15:00 -0300"), esperado)
        self.assertEqual(interpretar_data_feed("Wed, 28 Oct 2026 13:15:00 GMT"), esperado)
        self.assertEqual(interpretar_data_feed("2026-10-28T10:15:00-03:00"), esperado)
        self.assertEqual(interpretar_data_feed("2026-10-28T13:15:00Z"), esperado)

    def test_sem_fuso_e_formatos_simples(self):
        self.assertEqual(interpretar_data_feed("2026-10-28T10:15:00"), datetime(2026, 10, 28, 10, 15))
        self.assertEqual(interpretar_data_feed("2026-10-28"), datetime(2026, 10, 28))
        self.assertEqual(interpretar_data_feed("28/10/2026 09:00"), datetime(2026, 10, 28, 9))

    def test_invalidas(self):
        for ruim in (None, "", "ontem à tarde", "32/13/2026"):
            self.assertIsNone(interpretar_data_feed(ruim))


class Rss(unittest.TestCase):
    def setUp(self):
        self.r = interpretar_feed(ler_fixture("rss_exemplo.xml"), BASE)
        self.itens = {i["titulo"]: i for i in self.r["itens"]}

    def test_titulo_do_canal_e_quantidade(self):
        self.assertEqual(self.r["titulo"], "Jornal Exemplo — Política")
        self.assertEqual(len(self.r["itens"]), 4)   # javascript:, sem título e guid duplicado ficam de fora

    def test_campos_do_primeiro_item(self):
        i = self.r["itens"][0]
        self.assertEqual(i["guid"], "exemplo-politica-0001")
        self.assertEqual(i["autor_fonte"], "Maria da Conceição")
        self.assertEqual(i["imagem_url"], "https://img.exemplo.com.br/capa1.jpg")
        self.assertTrue(i["resumo"].startswith("O plenário aprovou"))
        self.assertIn("Ação do governo & da oposição", i["resumo"])
        self.assertNotIn("<", i["resumo"])
        self.assertIsInstance(i["publicado_em"], datetime)

    def test_cdata_no_titulo_e_html_escapado_no_resumo(self):
        i = self.itens["Ministro diz que “não há crise” no setor elétrico"]
        self.assertEqual(i["resumo"], "Resumo com entidades escapadas: Segundo o ministro, o abastecimento está "
                                      "garantido até o fim do ano.")

    def test_sem_guid_usa_o_link_e_sem_data_fica_nula(self):
        i = self.itens["Item sem data nem guid: o link vira o identificador"]
        self.assertEqual(i["guid"], i["url"])
        self.assertIsNone(i["publicado_em"])

    def test_link_relativo_e_content_encoded(self):
        i = next(x for x in self.r["itens"] if "Gre-Nal" in x["titulo"])
        self.assertEqual(i["url"], "https://jornal.exemplo.com.br/esporte/2026/10/gre-nal.html")
        self.assertEqual(i["resumo"], "Clássico Gre-Nal terminou com vitória colorada no Beira-Rio.")

    def test_nenhum_link_perigoso(self):
        for i in self.r["itens"]:
            self.assertTrue(i["url"].startswith(("http://", "https://")))

    def test_codificacoes(self):
        for nome in ("rss_latin1.xml", "rss_codificacao_errada.xml"):
            r = interpretar_feed(ler_fixture(nome), BASE)
            self.assertEqual(len(r["itens"]), 4, nome)
            self.assertIn("reforma tributária", r["itens"][0]["titulo"], nome)
            self.assertIn("Maria da Conceição", r["itens"][0]["autor_fonte"], nome)

    def test_limite_de_itens(self):
        self.assertEqual(len(interpretar_feed(ler_fixture("rss_exemplo.xml"), BASE, limite_itens=2)["itens"]), 2)


class Atom(unittest.TestCase):
    def setUp(self):
        self.r = interpretar_feed(ler_fixture("atom_exemplo.xml"), "https://agencia.exemplo.gov.br/")

    def test_entradas(self):
        self.assertEqual(self.r["titulo"], "Agência Exemplo — Últimas")
        self.assertEqual(len(self.r["itens"]), 2)          # a entrada sem link é descartada

    def test_campos(self):
        a, b = self.r["itens"]
        self.assertEqual(a["titulo"], "Economia cresce 0,6% no trimestre — IBGE")
        self.assertEqual(a["url"], "https://agencia.exemplo.gov.br/economia/pib-trimestre")
        self.assertEqual(a["autor_fonte"], "Equipe de Economia")
        self.assertEqual(a["resumo"], "O Produto Interno Bruto avançou 0,6% no terceiro trimestre.")
        self.assertEqual(a["imagem_url"], "https://agencia.exemplo.gov.br/img/pib.jpg")
        self.assertEqual(a["guid"], "tag:agencia.exemplo.gov.br,2026:materia-100")
        self.assertEqual(b["imagem_url"], "https://agencia.exemplo.gov.br/img/super.jpg")
        self.assertEqual(b["resumo"], "Máquina entra em operação em 2027.")   # <content> sem <summary>
        self.assertIsInstance(b["publicado_em"], datetime)  # veio de <updated> com Z


class Seguranca(unittest.TestCase):
    def test_entidades_sao_rejeitadas(self):
        with self.assertRaises(ErroFeed) as c:
            interpretar_feed(ler_fixture("feed_malicioso.xml"))
        self.assertIn("segurança", str(c.exception))

    def test_doctype_simples_e_aceito(self):
        r = interpretar_feed(ler_fixture("feed_doctype_simples.xml"))
        self.assertEqual(len(r["itens"]), 1)

    def test_html_nao_e_feed(self):
        with self.assertRaises(ErroFeed) as c:
            interpretar_feed(ler_fixture("pagina_html.html"))
        self.assertIn("HTML", str(c.exception))

    def test_lixo_e_vazio(self):
        for ruim in (b"", b"   ", b"nao e xml", b"<outra><coisa/></outra>", b"<rss version='2.0'></rss>"):
            with self.assertRaises(ErroFeed):
                interpretar_feed(ruim)

    def test_grande_demais(self):
        with self.assertRaises(ErroFeed):
            interpretar_feed(b"<rss>" + b"a" * (feeds.TAMANHO_FEED_MAX + 1))

    def test_guid_longo_vira_hash(self):
        xml = ("<rss version='2.0'><channel><item><title>Titulo ok</title><link>https://a.com/x</link>"
               f"<guid>{'g' * 400}</guid></item></channel></rss>").encode()
        guid = interpretar_feed(xml)["itens"][0]["guid"]
        self.assertTrue(guid.startswith("sha1:"))
        self.assertLessEqual(len(guid), 255)


if __name__ == "__main__":
    unittest.main()
