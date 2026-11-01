"""
rede.py
Camada única de acesso à internet do NewsManager (previsão do tempo e clipping).

Regras:
- Nenhuma tela chama a internet direto: os serviços usam `buscar()`, que sempre
  tem timeout, User-Agent identificável e limite de tamanho da resposta.
- Todo erro vira `ErroRede` com mensagem em português, pronta para exibir, já
  com a orientação para redes de faculdade/empresa (proxy, certificado).
- `buscar` pode ser substituída nos testes (injeção): os serviços recebem uma
  função com a mesma assinatura e nunca dependem da internet para serem testados.
- Este módulo NÃO mexe em widgets Tk nem no banco: é seguro chamá-lo de threads.
"""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

USER_AGENT = "NewsManager/1.0 (trabalho academico; leitor RSS e previsao do tempo; contato: veja README)"
TIMEOUT_PADRAO = 10          # segundos
TAMANHO_MAXIMO = 3_000_000   # bytes (feeds e JSON passam longe disso)

DICA_REDE = ("Se você está numa rede de faculdade ou empresa, configure o proxy "
             "(variáveis de ambiente HTTPS_PROXY e HTTP_PROXY) ou peça liberação do endereço ao suporte.")


class ErroRede(Exception):
    """Falha de rede com mensagem amigável. `codigo` guarda o status HTTP, se houver."""

    def __init__(self, mensagem, codigo=None):
        super().__init__(mensagem)
        self.codigo = codigo


@dataclass
class RespostaHttp:
    status: int
    conteudo: bytes = b""
    cabecalhos: dict = field(default_factory=dict)

    def cabecalho(self, nome, padrao=None):
        for chave, valor in self.cabecalhos.items():
            if chave.lower() == nome.lower():
                return valor
        return padrao

    @property
    def nao_modificado(self):
        return self.status == 304


def url_valida(url) -> bool:
    """Só http/https com endereço de servidor."""
    try:
        partes = urlsplit((url or "").strip())
    except ValueError:
        return False
    return partes.scheme in ("http", "https") and bool(partes.netloc)


def traduzir_erro(erro) -> ErroRede:
    """Converte exceções do `requests` (ou texto) em ErroRede compreensível."""
    nome = type(erro).__name__
    texto = str(erro).lower()
    if "ssl" in nome.lower() or "certificate" in texto or "ssl" in texto:
        return ErroRede("Falha de certificado/SSL ao acessar o servidor. Redes de faculdade ou empresa às vezes "
                        "interceptam conexões seguras: peça o certificado da rede ao suporte e aponte para ele na variável "
                        "REQUESTS_CA_BUNDLE. " + DICA_REDE)
    if "timeout" in nome.lower() or "timed out" in texto:
        return ErroRede("O servidor demorou demais para responder (tempo esgotado).")
    if "proxy" in nome.lower() or "proxy" in texto:
        return ErroRede("Falha no proxy da rede. " + DICA_REDE)
    if "connection" in nome.lower() or "name resolution" in texto or "getaddrinfo" in texto:
        return ErroRede("Sem conexão com a internet ou servidor inacessível. " + DICA_REDE)
    return ErroRede(f"Falha de rede ({nome}).")


def buscar(url, params=None, timeout=TIMEOUT_PADRAO, cabecalhos=None, max_bytes=TAMANHO_MAXIMO) -> RespostaHttp:
    """GET simples. Devolve RespostaHttp (inclusive 304/4xx/5xx: quem chama decide)
    ou lança ErroRede. Não segue para esquemas diferentes de http/https."""
    if not url_valida(url):
        raise ErroRede("Endereço inválido: use um link http:// ou https://.")
    try:
        import requests
    except ImportError as erro:
        raise ErroRede("A biblioteca 'requests' não está instalada (pip install requests).") from erro
    enviados = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    enviados.update(cabecalhos or {})
    try:
        with requests.get(url, params=params, headers=enviados, timeout=timeout, stream=True,
                          allow_redirects=True) as r:
            partes, total = [], 0
            for pedaco in r.iter_content(65536):
                total += len(pedaco)
                if total > max_bytes:
                    raise ErroRede("A resposta do servidor é grande demais e foi descartada.")
                partes.append(pedaco)
            return RespostaHttp(r.status_code, b"".join(partes), dict(r.headers))
    except ErroRede:
        raise
    except requests.exceptions.RequestException as erro:
        raise traduzir_erro(erro) from erro


def mensagem_http(status) -> str:
    """Texto em português para um status HTTP de erro."""
    if status == 404:
        return "Endereço não encontrado (404): o feed pode ter sido descontinuado."
    if status in (401, 403):
        return f"Acesso negado pelo servidor ({status})."
    if status == 429:
        return "Muitas requisições (429): tente de novo mais tarde."
    if status >= 500:
        return f"O servidor está com problemas ({status})."
    return f"Resposta inesperada do servidor ({status})."
