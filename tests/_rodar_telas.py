"""
Roda as telas novas com o Tk DE MENTIRA (tests/_tkfalso.py), em processo separado.
Exercita montagem, redesenho e fluxos (tempo, clipping, importação) contra um banco
SQLite em memória e rede simulada. NÃO valida aparência nem eventos reais do Tk.
"""
import os
import sys

os.environ["NM_TK_FALSO"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json  # noqa: E402
from datetime import datetime  # noqa: E402

from tests import _ambiente as amb  # noqa: E402
assert amb.TK_FALSO

import tkinter as tk  # noqa: E402
from tkinter import messagebox  # noqa: E402

from app import rede, segundo_plano  # noqa: E402
from app import tela_clipping, tela_tempo  # noqa: E402
from app.rede import RespostaHttp  # noqa: E402
from app.tela_perfil import PerfilFrame  # noqa: E402

tela_clipping.executar_async = segundo_plano.executar_sincrono
from app import clipping as _clip  # noqa: E402
tela_clipping.validar_feed = lambda url: _clip.validar_feed(url, falsa)   # rede simulada
USUARIO = {"id": 1, "nome": "Teste", "email": "t@t.com", "criado_em": datetime.now()}


def falsa(url, params=None, timeout=10, cabecalhos=None, max_bytes=0):
    if "open-meteo" in url and "geocoding" not in url:
        return RespostaHttp(200, amb.ler_fixture("open_meteo_santa_maria.json"))
    if "geocoding" in url:
        return RespostaHttp(200, amb.ler_fixture("geocodificacao_santa_maria.json"))
    if "ipapi" in url:
        return RespostaHttp(200, amb.ler_fixture("ip_localizacao.json"))
    return RespostaHttp(200, amb.ler_fixture("rss_exemplo.xml"))


rede.buscar = falsa
db = amb.banco_com_base()
raiz = tk.Frame()
log = amb.LoggerMudo()

# ---------- tempo ----------
at = tela_tempo.AtualizadorTempo(raiz, db, log, 1, buscar=falsa, executor=segundo_plano.executar_sincrono,
                                 agora=lambda: datetime(2026, 10, 28, 14, 5))
faixa = []
at.adicionar_ouvinte(lambda: faixa.append(at.texto_faixa()))
at.iniciar()
assert "SANTA MARIA" in faixa[-1], faixa
tela = tela_tempo.TempoFrame(raiz, db, log, at, ao_voltar=lambda: None, ao_criar_pauta=lambda d: faixa.append(d["titulo"]))
tela.mostrar()
tela._criar_pauta()
assert "Previsão do tempo para" in faixa[-1]
for estado in ("offline", "sem_previsao", "carregando"):
    at.estado = estado
    if estado != "offline":
        at.previsao = None
    tela._redesenhar()
at.atualizar(forcar=True)
tela._redesenhar()
dlg = tela_tempo.DialogoEscolherCidade(raiz, at, ao_escolher=lambda l: faixa.append(l["nome"]))
dlg.campo.set("Santa Maria")
dlg._buscar()
assert len(dlg._resultados) == 3
dlg._usar()
assert at.perfil.obter_local(1)["nome"] == "Santa Maria"
messagebox.respostas[:] = [True]
tela_tempo.perguntar_localizacao_inicial(raiz, at)          # já tem cidade salva: não pergunta
assert not messagebox.mostradas
db2 = amb.banco_com_base()
at2 = tela_tempo.AtualizadorTempo(raiz, db2, log, 1, buscar=falsa, executor=segundo_plano.executar_sincrono)
messagebox.respostas[:] = [False]
tela_tempo.perguntar_localizacao_inicial(raiz, at2)          # recusa é guardada e respeitada
assert at2.perfil.decisao_localizacao_ip(1) == "recusa" and not at2.tem_cidade_salva()
n = len(messagebox.mostradas)
tela_tempo.perguntar_localizacao_inicial(raiz, at2)
assert len(messagebox.mostradas) == n, "perguntou de novo depois de recusar"
db3 = amb.banco_com_base()
at3 = tela_tempo.AtualizadorTempo(raiz, db3, log, 1, buscar=falsa, executor=segundo_plano.executar_sincrono)
messagebox.respostas[:] = [True]
tela_tempo.perguntar_localizacao_inicial(raiz, at3)          # aceita: descobre pelo IP
assert at3.perfil.obter_local(1)["nome"] == "Porto Alegre"

# ---------- perfil (cidade) ----------
try:
    PerfilFrame(raiz, db, log, USUARIO, atualizador_tempo=at)
    print("perfil: montou")
except Exception as e:           # o Perfil depende de muitos métodos do banco real; só registramos
    print("perfil: não montou no ambiente falso:", type(e).__name__, e)

# ---------- clipping ----------
cf = tela_clipping.ClippingFrame(raiz, db, log, USUARIO, ao_alterar=lambda: faixa.append("alterou"))
cf.mostrar()
cf._buscar()
assert cf._previa, "prévia vazia"
cf.var_todos.set(True)
cf._alternar_todos()
assert cf._selecionados
total = len(cf._selecionados)
cf._importar_selecionadas()
n_noticias = db._rodar("SELECT COUNT(*) AS n FROM noticias", fetch=True)[0]["n"]
assert n_noticias == total, (n_noticias, total)
assert db._rodar("SELECT DISTINCT status FROM noticias", fetch=True) == [{"status": "em_pauta"}]
assert "alterou" in faixa
cf._salvar_filtros()
cf._mostrar_aba("salvas")
imp = cf.servico.listar_importacoes(1).dados[0]
cf.var_auto.set(True)
cf._editar_salva(imp)
cf._salvar_filtros()                                       # edição (mesmo nome)
cf._mostrar_aba("historico")
cf._mostrar_aba("fontes")
cf._testar_fontes()
cf.campo_novo_nome.set("Meu jornal")
cf.campo_nova_url.set("https://meu.exemplo.com/rss.xml")
cf._adicionar_feed()
assert any(f.get("proprio") for f in cf.servico.fontes(1))
cf._rodar_salva(cf.servico.listar_importacoes(1).dados[0])
cf.executar_automaticas()
cf._limpar_filtros()
# ---------- regressões de bugs corrigidos (lógica; o efeito visual precisa ser visto na janela real) ----------
from app.telas_cadastros import _TelaBase, RolagemVertical  # noqa: E402
from app.tela_noticias import NoticiasFrame  # noqa: E402


class _Reg:
    def __init__(self):
        self.chamadas = []

    def __getattr__(self, nome):
        return lambda *a, **k: self.chamadas.append((nome, a, k))


stub = _Reg()
stub.painel_form, stub.area_form, stub.rolagem = _Reg(), _Reg(), _Reg()
stub.rolagem.canvas = _Reg()
_TelaBase._esconder_form(stub)
assert ("pack_forget", (), {}) in stub.painel_form.chamadas
assert ("configure", (), {"height": 1}) in stub.area_form.chamadas, "contêiner do formulário não foi encolhido"
assert any(c[0] == "ajustar" for c in stub.rolagem.chamadas)
_TelaBase._exibir_form(stub)
assert any(c[0] == "pack" for c in stub.painel_form.chamadas)

abertos = []
card = _Reg()
card.ao_editar_completo = lambda i, d: abertos.append((i, d))
NoticiasFrame._editar_do_cartao(card, 7)
assert abertos == [(7, None)], "EDITAR do cartão deve abrir o editor completo"
card2 = _Reg()
card2.ao_editar_completo = None
NoticiasFrame._editar_do_cartao(card2, 7)
assert ("_editar", (7,), {}) in card2.chamadas

# roda do mouse: campo de texto que ainda rola não move a página
class _Texto(tk.Text):
    def __init__(self, vista):
        super().__init__()
        self._vista = vista

    def yview(self, *a):
        return self._vista


class _Evento:
    x_root = y_root = 0
    num = None
    delta = -120


for vista, cima, esperado in (((0.0, 0.4), False, True), ((0.6, 1.0), False, False),
                              ((0.6, 1.0), True, True), ((0.0, 0.4), True, False), ((0.0, 1.0), False, False)):
    rol = _Reg()
    rol.winfo_containing = lambda x, y, v=vista: _Texto(v)
    assert RolagemVertical._texto_rolavel_sob_o_ponteiro(rol, _Evento(), cima) is esperado, (vista, cima)
print("telas: OK (Tk falso)")
