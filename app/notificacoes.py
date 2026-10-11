"""
notificacoes.py
Backend do painel "Despachos & Notificações" (protótipo Stitch
notifica_es_newsmanager).

Como funciona:
- Os serviços do sistema (matérias, editorias, autores, perfil) chamam as
  funções `evento_*` daqui quando algo importante acontece (matéria
  publicada, enviada à revisão, editoria alterada, senha trocada...). Isso
  grava uma linha em `notificacoes` e NUNCA atrapalha a operação principal:
  se der erro, só vai para o log.
- Matéria publicada com a etiqueta #Urgente ou #Furo vira "Furo de
  reportagem" (urgente). Quem ligou "Receber despachos de urgência por
  e-mail" no Perfil também recebe um e-mail (em segundo plano).
- Cada pessoa tem o próprio "lida / não lida" (tabela notificacoes_lidas).
  Avisos pessoais (ex.: troca de senha) só aparecem para o usuário certo.
- A interface usa NotificacaoService, que devolve sempre um Resultado.
"""

import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from .cadastros import Resultado, _ServicoBase
from .database import ErroBanco
from .noticias import interpretar_data

TIPOS = {
    "furo": "Furo de reportagem",
    "publicacao": "Nova matéria publicada",
    "revisao": "Copydesk & revisão",
    "pauta": "Mesa de pauta",
    "estrutura": "Estrutura editorial",
    "arquivo": "Arquivo & memória",
    "seguranca": "Segurança & acesso",
}
FILTROS = {"todas": "Todas", "nao_lidas": "Não lidas", "urgentes": "Urgente"}
ETIQUETAS_URGENTES = ("urgente", "furo")
RETENCAO_DIAS = 180
MESES_CURTOS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

PREFERENCIAS_PADRAO = {
    "alerta_sonoro": "1",        # toca um sinal quando chega um furo
    "email_urgencia": "0",       # e-mail para despachos urgentes (precisa de config/email_config.json)
    "revisao_automatica": "0",   # realce de problemas de redação no editor
    "polegadas_coluna": "0",     # contadores do editor em polegadas de coluna
}


# ---------------------------------------------------------------------------
# Sessão: quem está usando o sistema (para "autor da ação" e preferências)
# ---------------------------------------------------------------------------
class Sessao:
    usuario: dict = {}
    preferencias: dict = dict(PREFERENCIAS_PADRAO)

    @classmethod
    def definir(cls, usuario, preferencias=None):
        cls.usuario = usuario or {}
        cls.preferencias = {**PREFERENCIAS_PADRAO, **(preferencias or {})}

    @classmethod
    def nome(cls) -> str:
        return cls.usuario.get("nome") or cls.usuario.get("usuario") or "Sistema"

    @classmethod
    def usuario_id(cls):
        return cls.usuario.get("id")

    @classmethod
    def ativa(cls, chave) -> bool:
        return str(cls.preferencias.get(chave, PREFERENCIAS_PADRAO.get(chave, "0"))) == "1"


# ---------------------------------------------------------------------------
# Tempo relativo ("HÁ 12 MIN")
# ---------------------------------------------------------------------------
def tempo_relativo(quando, agora=None) -> str:
    if isinstance(quando, str):          # alguns bancos devolvem texto em vez de datetime
        quando = interpretar_data(quando)
    if not isinstance(quando, datetime):
        return ""
    agora = agora or datetime.now()
    segundos = (agora - quando).total_seconds()
    if segundos < 60:
        return "AGORA"
    if segundos < 3600:
        return f"HÁ {int(segundos // 60)} MIN"
    if segundos < 86400 and quando.date() == agora.date():
        horas = int(segundos // 3600)
        return f"HÁ {horas} {'HORA' if horas == 1 else 'HORAS'}"
    if quando.date() == agora.date() - timedelta(days=1):
        return f"ONTEM ÀS {quando:%H:%M}"
    if quando.year == agora.year:
        return f"{quando.day:02d} {MESES_CURTOS[quando.month - 1]}"
    return f"{quando.day:02d} {MESES_CURTOS[quando.month - 1]} {quando.year}"


# ---------------------------------------------------------------------------
# Registro de eventos
# ---------------------------------------------------------------------------
_silenciadas = 0


@contextmanager
def silenciar():
    """Dentro do bloco nenhuma notificação é criada (usado pelo seed.py em cargas grandes)."""
    global _silenciadas
    _silenciadas += 1
    try:
        yield
    finally:
        _silenciadas -= 1


def eh_urgente(etiquetas) -> bool:
    return any(e.strip().lstrip("#").lower() in ETIQUETAS_URGENTES for e in (etiquetas or "").replace(";", ",").split(","))


def registrar_evento(db, logger, tipo, titulo, mensagem=None, etiqueta=None, rodape=None, urgente=False,
                     alvo_tipo=None, alvo_id=None, usuario_destino=None, criado_em=None):
    """Grava a notificação. Devolve o id ou None (em silêncio ou se falhar)."""
    if _silenciadas:
        return None
    try:
        novo_id = db.criar_notificacao(
            tipo, (titulo or "")[:200], (mensagem or None) and mensagem[:600], etiqueta, rodape, urgente,
            alvo_tipo, alvo_id, usuario_destino, Sessao.nome(), criado_em)
    except ErroBanco as erro:
        logger.error("Erro ao registrar notificação", erro.original or erro)
        return None
    if urgente:
        _enviar_emails_de_urgencia(db, logger, titulo, mensagem)
    return novo_id


def _enviar_emails_de_urgencia(db, logger, titulo, mensagem):
    """Manda o despacho por e-mail a quem ligou a preferência, em segundo plano."""
    try:
        from .auth import EmailSender
        if not EmailSender.configuracao_disponivel():
            return
        destinatarios = db.listar_usuarios_com_preferencia("email_urgencia", "1")
    except Exception as erro:  # sem auth/SMTP configurado: tudo bem, é opcional
        logger.error("Despacho por e-mail não enviado", erro)
        return
    if not destinatarios:
        return

    def trabalho():
        for usuario in destinatarios:
            try:
                EmailSender.enviar_despacho(usuario["email"], usuario["nome"], titulo, mensagem or "")
            except Exception as erro:
                logger.error(f"Falha ao enviar despacho para {usuario['email']}", erro)

    threading.Thread(target=trabalho, daemon=True).start()


# ---- eventos prontos (textos no tom do jornal) ----
def evento_materia(db, logger, noticia_id, titulo, status, categoria, autor, etiquetas=None):
    """Matéria publicada, enviada à revisão ou colocada em pauta."""
    alvo = dict(alvo_tipo="noticia", alvo_id=noticia_id)
    if status == "publicado":
        if eh_urgente(etiquetas):
            return registrar_evento(
                db, logger, "furo", titulo,
                f"{autor} registrou um furo na editoria de {categoria}. Prioridade máxima na mesa de edição.",
                "Telégrafo", "URGENTE • PRIORIDADE ZERO", True, **alvo)
        return registrar_evento(
            db, logger, "publicacao", titulo,
            f"A peça de {autor} acabou de ser carimbada para circulação digital na editoria de {categoria}.",
            categoria, f"AUTOR: {autor.upper()}", **alvo)
    if status == "revisao":
        return registrar_evento(
            db, logger, "revisao", titulo,
            f"{autor} enviou a matéria à mesa de cópia. Ela aguarda a revisão antes de ir para a circulação.",
            None, "AGUARDANDO LIBERAÇÃO", **alvo)
    if status == "em_pauta":
        return registrar_evento(
            db, logger, "pauta", titulo,
            f"Nova pauta aberta na editoria de {categoria}, sob responsabilidade de {autor}.",
            categoria, "FILA DE APURAÇÃO", **alvo)
    return None


def evento_materia_excluida(db, logger, titulo, categoria=None):
    return registrar_evento(
        db, logger, "arquivo", "Matéria Removida do Acervo",
        f"A matéria “{titulo}” foi excluída por {Sessao.nome()}.", categoria, "ARQUIVO & MEMÓRIA")


_ACOES = {"criada": "foi criada", "atualizada": "teve sua taxonomia revisada", "excluida": "foi removida do mastro"}


def evento_estrutura(db, logger, acao, item, nome, alvo_tipo=None, alvo_id=None):
    """Mudança em editorias ('categoria') ou no quadro de jornalistas ('autor')."""
    if item == "categoria":
        titulo = {"criada": "Nova Editoria no Mastro", "atualizada": "Categoria Atualizada no Mastro",
                  "excluida": "Editoria Removida do Mastro"}[acao]
        mensagem = f"A editoria {nome} {_ACOES[acao]} por {Sessao.nome()}."
        etiqueta = None
    else:
        titulo = {"criada": "Novo Jornalista no Quadro", "atualizada": "Credencial Atualizada",
                  "excluida": "Jornalista Desligado do Quadro"}[acao]
        mensagem = {"criada": f"{nome} foi credenciado(a) por {Sessao.nome()}.",
                    "atualizada": f"A credencial de {nome} foi revisada por {Sessao.nome()}.",
                    "excluida": f"{nome} foi removido(a) do quadro de redação por {Sessao.nome()}."}[acao]
        etiqueta = "Quadro de redação"
    return registrar_evento(db, logger, "estrutura", titulo, mensagem, etiqueta, "DESPACHO DA CHEFIA",
                            alvo_tipo=alvo_tipo if acao != "excluida" else None,
                            alvo_id=alvo_id if acao != "excluida" else None)


def evento_seguranca(db, logger, usuario_id, titulo, mensagem):
    """Aviso pessoal de segurança: só o próprio usuário vê."""
    return registrar_evento(db, logger, "seguranca", titulo, mensagem, None, "REGISTRO DE SEGURANÇA",
                            alvo_tipo="perfil", alvo_id=usuario_id, usuario_destino=usuario_id)


# ---------------------------------------------------------------------------
# Serviço usado pela interface
# ---------------------------------------------------------------------------
class NotificacaoService(_ServicoBase):
    def __init__(self, db, logger, usuario_id, midia=None):
        super().__init__(db, logger, midia)
        self.usuario_id = usuario_id

    def _enriquecer(self, linha, agora):
        criado = linha["criado_em"]
        criado = interpretar_data(criado) if isinstance(criado, str) else criado
        linha = {**linha, "criado_em": criado}
        return dict(
            id=linha["id"], tipo=linha["tipo"], tipo_rotulo=TIPOS.get(linha["tipo"], linha["tipo"]),
            titulo=linha["titulo"], mensagem=linha["mensagem"] or "", etiqueta=linha["etiqueta"],
            rodape=linha["rodape"], urgente=bool(linha["urgente"]), lida=bool(linha["lida"]),
            alvo_tipo=linha["alvo_tipo"], alvo_id=linha["alvo_id"], ator=linha["ator"],
            criado_em=linha["criado_em"], tempo=tempo_relativo(linha["criado_em"], agora))

    def contagens(self) -> Resultado:
        """{'todas': n, 'nao_lidas': n, 'urgentes': n} para as abas e o selo do sino."""
        try:
            dados = {f: self.db.contar_notificacoes(self.usuario_id, f) for f in FILTROS}
        except ErroBanco as e:
            return self._falha_banco("Erro ao contar notificações", e)
        return Resultado(True, "", dados)

    def listar(self, filtro="todas", pagina=1, por_pagina=20, agora=None) -> Resultado:
        """Página de notificações (mais recentes primeiro). `dados` = {itens, total, pagina, paginas}."""
        if filtro not in FILTROS:
            filtro = "todas"
        agora = agora or datetime.now()
        try:
            total = self.db.contar_notificacoes(self.usuario_id, filtro)
            paginas = max(1, -(-total // por_pagina))
            pagina = min(max(1, int(pagina)), paginas)
            linhas = self.db.listar_notificacoes(self.usuario_id, filtro, por_pagina, (pagina - 1) * por_pagina)
        except ErroBanco as e:
            return self._falha_banco("Erro ao listar notificações", e)
        itens = [self._enriquecer(l, agora) for l in linhas]
        return Resultado(True, f"{total} notificação(ões).", dict(itens=itens, total=total, pagina=pagina, paginas=paginas))

    def marcar_lida(self, notificacao_id) -> Resultado:
        try:
            if not self.db.buscar_notificacao(notificacao_id):
                return Resultado(False, "Notificação não encontrada.")
            self.db.marcar_notificacao_lida(self.usuario_id, notificacao_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao marcar notificação como lida", e)
        return Resultado(True)

    def marcar_todas_lidas(self) -> Resultado:
        try:
            self.db.marcar_todas_notificacoes_lidas(self.usuario_id)
        except ErroBanco as e:
            return self._falha_banco("Erro ao marcar notificações como lidas", e)
        return Resultado(True, "Todas as notificações foram marcadas como lidas.")

    def urgente_pendente(self):
        """id da notificação urgente não lida mais recente, ou None (para o sinal sonoro)."""
        try:
            return self.db.ultima_notificacao_urgente_nao_lida(self.usuario_id)
        except ErroBanco:
            return None

    def purgar_antigas(self, dias=RETENCAO_DIAS, agora=None):
        try:
            self.db.purgar_notificacoes((agora or datetime.now()) - timedelta(days=dias))
        except ErroBanco as e:
            self._falha_banco("Erro ao limpar notificações antigas", e)
