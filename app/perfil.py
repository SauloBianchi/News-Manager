"""
perfil.py
Backend da tela "Registro Funcional & Perfil do Editor" (protótipo Stitch
perfil_newsmanager): dados biográficos, foto, troca de senha e preferências
do operador.

- Dados do módulo 01 e do cartão lateral ficam na tabela `usuarios` (colunas
  criadas automaticamente por DatabaseManager.garantir_esquema). Cada gravação
  registra quem alterou e quando ("Alterado por ... em ...").
- Troca de senha: confere a senha atual (bcrypt), exige 12+ caracteres com
  símbolo e diferente da atual, e encerra qualquer código de verificação
  pendente. Contas só-Google (sem senha) não têm senha para trocar.
- Preferências (tabela preferencias_usuario): alerta sonoro de furo, e-mail de
  urgência, revisão automática de redação e polegadas de coluna. Valem para
  cada usuário e são aplicadas na hora (Sessao.preferencias).
"""

import re

from .cadastros import Resultado, _ServicoBase, _limpar
from .database import ErroBanco
from .notificacoes import PREFERENCIAS_PADRAO, Sessao, evento_seguranca

SENHA_MIN, SENHA_MAX = 12, 128

LIMITES = {"nome": (2, 150), "byline": (0, 150), "telefone": (0, 60), "atribuicao": (0, 1000),
           "cargo": (0, 120), "matricula": (0, 40), "registro": (0, 40), "conselho": (0, 120),
           "mesa": (0, 120), "nota_biografica": (0, 1500)}
ROTULOS = {"nome": "O nome completo", "byline": "O nome em assinatura", "telefone": "O ramal/telefone",
           "atribuicao": "A atribuição regimental", "cargo": "O cargo", "matricula": "A matrícula",
           "registro": "O registro profissional", "conselho": "O conselho editorial", "mesa": "A mesa de operação",
           "nota_biografica": "A nota biográfica"}
ROTULOS_PREFERENCIA = {
    "alerta_sonoro": ("Alertas sonoros de furo de reportagem",
                      "Toca um sinal quando chega um despacho urgente não lido."),
    "email_urgencia": ("Receber despachos de urgência por e-mail",
                       "Envia o despacho em texto simples para o e-mail da sua conta (exige o envio de e-mail configurado)."),
    "revisao_automatica": ("Modo de revisão automática ao digitar",
                           "Destaca no editor espaços duplos, palavras repetidas, pontuação e frases longas."),
    "polegadas_coluna": ("Exibir contadores em polegadas de coluna",
                         "Troca a contagem de caracteres do editor pelo espaço equivalente na página impressa."),
}


def avaliar_senha(nova: str, atual: str = "", confirmacao=None):
    """Regras de complexidade como lista [(texto, cumprida)], para a lista de verificação da tela."""
    nova = nova or ""
    regras = [
        (f"Mínimo de {SENHA_MIN} caracteres", len(nova) >= SENHA_MIN),
        ("Símbolos e pontuações", bool(re.search(r"[^\w\s]|_", nova))),
        ("Letras e números", bool(re.search(r"[A-Za-zÀ-ÿ]", nova)) and bool(re.search(r"\d", nova))),
        ("Diferente da senha atual", bool(nova) and nova != (atual or "")),
    ]
    if confirmacao is not None:
        regras.append(("Confirmação igual à nova senha", bool(nova) and nova == confirmacao))
    return regras


def prontuario(perfil) -> str:
    """Número de prontuário no estilo do protótipo: NM-0042/2024."""
    criado = perfil.get("criado_em")
    ano = getattr(criado, "year", None) or ""
    return f"NM-{int(perfil['id']):04d}/{ano}".rstrip("/")


class PerfilService(_ServicoBase):
    # ---------- leitura ----------
    def obter(self, usuario_id) -> Resultado:
        """Perfil completo + números do cartão lateral."""
        from datetime import datetime
        try:
            perfil = self.db.buscar_perfil_usuario(usuario_id)
            if not perfil:
                return Resultado(False, "Usuário não encontrado.")
            ultima = self.db.ultima_publicacao(datetime.now())
            por_estado = self.db.contar_noticias_por_status()
        except ErroBanco as e:
            return self._falha_banco("Erro ao carregar o perfil", e)
        dados = dict(perfil)
        dados["prontuario"] = prontuario(perfil)
        dados["ultimo_fechamento"] = ultima
        dados["materias_publicadas"] = sum(int(l["total"]) for l in por_estado if l["status"] == "publicado")
        return Resultado(True, "", dados)

    # ---------- dados biográficos ----------
    def salvar_dados(self, usuario_id, dados: dict) -> Resultado:
        limpos, erro = {}, None
        for campo, (minimo, maximo) in LIMITES.items():
            if campo not in dados:
                continue
            valor = _limpar(dados[campo]) if campo not in ("atribuicao", "nota_biografica") else (dados[campo] or "").strip()
            if len(valor) < minimo:
                return Resultado(False, f"{ROTULOS[campo]} é obrigatório.")
            if len(valor) > maximo:
                return Resultado(False, f"{ROTULOS[campo]} pode ter no máximo {maximo} caracteres.")
            limpos[campo] = valor or None
        if "nome" in limpos and not limpos["nome"]:
            return Resultado(False, "O nome completo é obrigatório.")
        try:
            if not self.db.buscar_perfil_usuario(usuario_id):
                return Resultado(False, "Usuário não encontrado.")
            self.db.atualizar_perfil_usuario(usuario_id, limpos, Sessao.nome())
        except ErroBanco as e:
            return self._falha_banco("Erro ao salvar o perfil", e)
        self.logger.info(f"Perfil do usuário {usuario_id} atualizado")
        return Resultado(True, "Dados biográficos salvos no livro de ata.", limpos)

    def salvar_foto(self, usuario_id, caminho) -> Resultado:
        """Grava (ou remove, com caminho None) a foto do crachá; apaga a antiga do disco."""
        erro = self._checar_imagem(caminho)
        if erro:
            return Resultado(False, erro)
        try:
            antigo = (self.db.buscar_perfil_usuario(usuario_id) or {}).get("foto")
            self.db.atualizar_perfil_usuario(usuario_id, {"foto": caminho}, Sessao.nome())
        except ErroBanco as e:
            return self._falha_banco("Erro ao salvar a foto", e)
        if antigo and antigo != caminho:
            self._descartar_imagem(antigo)
        return Resultado(True, "Foto atualizada." if caminho else "Foto removida.")

    # ---------- senha ----------
    def alterar_senha(self, usuario_id, atual, nova, confirmacao) -> Resultado:
        from .auth import DependenciaAusente, PasswordHasher
        try:
            registro = self.db._rodar("SELECT senha_hash FROM usuarios WHERE id = %s", (usuario_id,), fetch=True)
        except ErroBanco as e:
            return self._falha_banco("Erro ao verificar a senha", e)
        if not registro:
            return Resultado(False, "Usuário não encontrado.")
        if not registro[0]["senha_hash"]:
            return Resultado(False, "Esta conta entra pelo Google e não tem senha própria. "
                                    "Use \"Esqueci minha senha\" no login se quiser criar uma.")
        if not atual:
            return Resultado(False, "Informe a senha atual do terminal.")
        try:
            if not PasswordHasher.verificar(atual, registro[0]["senha_hash"]):
                return Resultado(False, "A senha atual está incorreta.")
            if len(nova or "") > SENHA_MAX:
                return Resultado(False, f"A nova senha pode ter no máximo {SENHA_MAX} caracteres.")
            pendencias = [texto for texto, ok in avaliar_senha(nova, atual, confirmacao) if not ok]
            if pendencias:
                return Resultado(False, "A nova senha não cumpre as regras: " + "; ".join(pendencias).lower() + ".")
            self.db.trocar_senha_usuario(usuario_id, PasswordHasher.gerar_hash(nova))
        except DependenciaAusente as e:
            return Resultado(False, str(e))
        except ErroBanco as e:
            return self._falha_banco("Erro ao trocar a senha", e)
        self.logger.info(f"Senha do usuário {usuario_id} alterada")
        evento_seguranca(self.db, self.logger, usuario_id, "Senha Atualizada",
                         "A senha mestre da sua conta foi alterada. Se não foi você, redefina-a imediatamente.")
        return Resultado(True, "Senha atualizada. As demais sessões devem entrar novamente.")

    # ---------- dois fatores ----------
    def desativar_dois_fatores(self, usuario_id) -> Resultado:
        try:
            self.db.desativar_dois_fatores(usuario_id)
        except Exception as erro:
            self.logger.error("Erro ao desativar o 2FA", erro)
            return Resultado(False, "Não foi possível desativar a verificação em duas etapas.")
        evento_seguranca(self.db, self.logger, usuario_id, "Verificação em Duas Etapas Desativada",
                         "A verificação por e-mail no login foi desligada na sua conta.")
        return Resultado(True, "Verificação em duas etapas desativada.")

    def avisar_dois_fatores_ativado(self, usuario_id):
        evento_seguranca(self.db, self.logger, usuario_id, "Verificação em Duas Etapas Ativada",
                         "A verificação por e-mail passou a ser exigida no login da sua conta.")

    # ---------- preferências ----------
    def preferencias(self, usuario_id) -> dict:
        """{chave: bool} com os padrões preenchidos."""
        try:
            guardadas = self.db.obter_preferencias(usuario_id)
        except ErroBanco as e:
            self._falha_banco("Erro ao carregar as preferências", e)
            guardadas = {}
        return {k: str(guardadas.get(k, v)) == "1" for k, v in PREFERENCIAS_PADRAO.items()}

    def salvar_preferencias(self, usuario_id, valores: dict) -> Resultado:
        desconhecidas = [k for k in valores if k not in PREFERENCIAS_PADRAO]
        if desconhecidas:
            return Resultado(False, "Preferência desconhecida: " + ", ".join(desconhecidas))
        textos = {k: "1" if valores[k] else "0" for k in valores}
        try:
            self.db.salvar_preferencias(usuario_id, textos)
        except ErroBanco as e:
            return self._falha_banco("Erro ao salvar as preferências", e)
        if Sessao.usuario_id() == usuario_id:
            Sessao.preferencias = {**Sessao.preferencias, **textos}
        return Resultado(True, "Preferências do operador preservadas.")
