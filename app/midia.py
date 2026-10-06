"""
midia.py
Armazenamento e exibição das imagens do NewsManager: fotografia de capa das
matérias e foto dos jornalistas.

Como funciona:
- O usuário escolhe um arquivo no computador; `GerenciadorMidia.importar()`
  confere se é mesmo uma imagem, reduz para no máximo 1600 px no maior lado,
  remove metadados (EXIF) e grava uma cópia na pasta `midia/` do projeto com
  um nome aleatório. No banco fica só o caminho relativo (ex.:
  "noticias/3f9a....jpg"), então mover o projeto de pasta não quebra nada.
- Para mostrar na tela, `carregar_tk()` devolve uma imagem já recortada no
  tamanho pedido (modo "cobrir", igual ao object-fit: cover do layout) e
  guarda em cache.

Depende do Pillow (`pip install pillow`). Sem ele o sistema continua
funcionando, apenas sem imagens: `disponivel()` devolve False e as telas
mostram o marcador colorido de sempre.
"""

import os
import uuid
from pathlib import Path

try:  # Pillow é opcional para o resto do sistema
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:  # pragma: no cover - depende do ambiente
    Image = ImageOps = UnidentifiedImageError = None

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
PASTA_MIDIA = RAIZ_PROJETO / "midia"

EXTENSOES_ACEITAS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
TIPOS_ARQUIVO_DIALOGO = [
    ("Imagens", "*.png *.jpg *.jpeg *.webp *.gif *.bmp"),
    ("Todos os arquivos", "*.*"),
]
TAMANHO_MAX_ARQUIVO = 10 * 1024 * 1024   # 10 MB
LADO_MAX_PX = 1600
PASTAS = ("noticias", "autores")


class ErroMidia(Exception):
    """Falha ao importar/ler uma imagem. A mensagem já pode ser mostrada ao usuário."""


def _raiz_tk() -> int:
    """Identifica a janela raiz do Tk em uso. Cada tk.Tk() é um interpretador
    separado: uma imagem criada na janela antiga não existe na nova (após
    Sair e entrar de novo), então o cache precisa ser por janela."""
    try:
        import tkinter
        return id(getattr(tkinter, "_default_root", None))
    except ImportError:   # pragma: no cover
        return 0


def disponivel() -> bool:
    """True se o Pillow está instalado."""
    return Image is not None


class GerenciadorMidia:
    def __init__(self, base=None):
        self.base = Path(base) if base else PASTA_MIDIA
        self._cache = {}

    # ---------- caminhos ----------
    def caminho_absoluto(self, relativo):
        """Caminho completo do arquivo, ou None se o caminho for vazio ou tentar
        sair da pasta de mídia (ex.: '../../senha.txt')."""
        if not relativo or not isinstance(relativo, str):
            return None
        alvo = (self.base / relativo).resolve()
        try:
            alvo.relative_to(self.base.resolve())
        except ValueError:
            return None
        return alvo

    def existe(self, relativo) -> bool:
        alvo = self.caminho_absoluto(relativo)
        return bool(alvo and alvo.is_file())

    # ---------- importar / remover ----------
    def importar(self, origem, pasta="noticias") -> str:
        """Valida e copia a imagem para a pasta de mídia. Devolve o caminho
        relativo. Lança ErroMidia com mensagem amigável se algo estiver errado."""
        if not disponivel():
            raise ErroMidia("Para usar imagens, instale o Pillow: pip install pillow")
        if pasta not in PASTAS:
            raise ErroMidia("Destino de imagem inválido.")
        origem = Path(origem)
        if origem.suffix.lower() not in EXTENSOES_ACEITAS:
            raise ErroMidia("Formato não suportado. Use PNG, JPG, WEBP, GIF ou BMP.")
        try:
            tamanho = origem.stat().st_size
        except OSError:
            raise ErroMidia("Não foi possível abrir o arquivo escolhido.") from None
        if tamanho > TAMANHO_MAX_ARQUIVO:
            raise ErroMidia("A imagem tem mais de 10 MB. Escolha um arquivo menor.")

        try:
            with Image.open(origem) as bruta:
                bruta.load()
                imagem = ImageOps.exif_transpose(bruta)   # respeita a rotação da câmera
                imagem.thumbnail((LADO_MAX_PX, LADO_MAX_PX))
                tem_transparencia = imagem.mode in ("RGBA", "LA", "P") and (
                    imagem.mode != "P" or "transparency" in imagem.info)
                extensao = ".png" if tem_transparencia else ".jpg"
                imagem = imagem.convert("RGBA" if tem_transparencia else "RGB")

                destino_dir = self.base / pasta
                destino_dir.mkdir(parents=True, exist_ok=True)
                nome = f"{uuid.uuid4().hex}{extensao}"
                if extensao == ".png":
                    imagem.save(destino_dir / nome, "PNG", optimize=True)
                else:
                    imagem.save(destino_dir / nome, "JPEG", quality=88, optimize=True)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise ErroMidia("O arquivo escolhido não é uma imagem válida.") from None
        return f"{pasta}/{nome}"

    def remover(self, relativo) -> bool:
        """Apaga o arquivo (se existir e estiver dentro da pasta de mídia)."""
        alvo = self.caminho_absoluto(relativo)
        if not alvo or not alvo.is_file():
            return False
        try:
            alvo.unlink()
        except OSError:
            return False
        self._cache = {k: v for k, v in self._cache.items() if k[0] != relativo}
        return True

    # ---------- exibição ----------
    def preparar(self, relativo, largura, altura, modo="cobrir"):
        """Imagem PIL no tamanho pedido, ou None se não for possível ler.
        modo='cobrir': preenche a área e corta o excesso (como nos cartões);
        modo='caber': mantém a imagem inteira dentro da área."""
        if not disponivel():
            return None
        alvo = self.caminho_absoluto(relativo)
        if not alvo or not alvo.is_file():
            return None
        try:
            with Image.open(alvo) as imagem:
                imagem = imagem.convert("RGB")
                if modo == "caber":
                    imagem.thumbnail((largura, altura))
                    return imagem.copy()
                return ImageOps.fit(imagem, (largura, altura), method=Image.LANCZOS)
        except (UnidentifiedImageError, OSError, ValueError):
            return None

    def _chave_cache(self, relativo, largura, altura, modo):
        alvo = self.caminho_absoluto(relativo)
        return (relativo, largura, altura, modo,
                alvo.stat().st_mtime_ns if alvo and alvo.is_file() else 0, _raiz_tk())

    def limpar_cache(self):
        """Descarta as imagens já preparadas (ex.: ao encerrar a sessão)."""
        self._cache.clear()

    def carregar_tk(self, relativo, largura, altura, modo="cobrir"):
        """PhotoImage do Tkinter pronta para usar em um Label (ou None).
        Guarde a referência no widget (label.image = foto) para o Tk não
        descartá-la."""
        if not relativo:
            return None
        chave = self._chave_cache(relativo, largura, altura, modo)
        if chave in self._cache:
            return self._cache[chave]
        imagem = self.preparar(relativo, largura, altura, modo)
        if imagem is None:
            return None
        try:
            from PIL import ImageTk
            foto = ImageTk.PhotoImage(imagem)
        except Exception:  # sem Tk/ImageTk (ex.: testes) ou erro do Tk
            return None
        self._cache[chave] = foto
        return foto


# Instância única usada pelo sistema todo
midia = GerenciadorMidia()
