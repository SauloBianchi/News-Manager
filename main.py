"""
main.py
Ponto de entrada do NewsManager.
Inicializa o logger, o gerenciador de banco de dados e abre a
janela de login.
"""

from app.logger import Logger
from app.database import DatabaseManager
from app.gui import LoginWindow


def main():
    logger = Logger()
    logger.info("Aplicação NewsManager iniciada.")

    # Ajuste host/user/password/database conforme o seu ambiente MySQL
    db = DatabaseManager(
        host="localhost",
        user="root",
        password="",
        database="newsmanager",
    )

    login = LoginWindow(db, logger)
    login.mainloop()

    db.desconectar()
    logger.info("Aplicação NewsManager encerrada.")


if __name__ == "__main__":
    main()
