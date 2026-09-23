"""
logger.py
Responsável por registrar erros e eventos importantes da aplicação
no arquivo error.log.
"""

import logging
import os


class Logger:
    """Encapsula a configuração e uso do logging da aplicação."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        # Garante uma única instância de logger em toda a aplicação (Singleton)
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
        return cls._instance

    def __init__(self, log_file: str = os.path.join("logs", "error.log")):
        if getattr(self, "_configured", False):
            return

        self.log_file = log_file
        os.makedirs(os.path.dirname(self.log_file) or ".", exist_ok=True)
        self._configurar_logger()
        self._configured = True

    def _configurar_logger(self):
        logging.basicConfig(
            filename=self.log_file,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            encoding="utf-8",
        )
        self.logger = logging.getLogger("NewsManager")

    def info(self, mensagem: str):
        self.logger.info(mensagem)

    def warning(self, mensagem: str):
        self.logger.warning(mensagem)

    def error(self, mensagem: str, exc: Exception = None):
        if exc:
            self.logger.error(f"{mensagem} | Exceção: {exc}")
        else:
            self.logger.error(mensagem)


if __name__ == "__main__":
    log = Logger()
    log.info("Logger inicializado com sucesso.")
