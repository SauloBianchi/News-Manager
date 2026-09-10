"""
gui.py
Interface gráfica do NewsManager, construída com Tkinter.
Contém a janela de Login e a Janela Principal (com CRUD de notícias,
categorias, autores, e um gráfico com matplotlib).
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from database import DatabaseManager
from logger import Logger


class LoginWindow(tk.Tk):
    """Primeira janela da aplicação: autenticação do usuário."""

    def __init__(self, db: DatabaseManager, logger: Logger):
        super().__init__()
        self.db = db
        self.logger = logger

        self.title("NewsManager - Login")
        self.geometry("320x200")
        self.resizable(False, False)

        self._montar_layout()

    def _montar_layout(self):
        tk.Label(self, text="NewsManager", font=("Arial", 16, "bold")).pack(pady=10)

        tk.Label(self, text="Usuário").pack()
        self.entry_usuario = tk.Entry(self)
        self.entry_usuario.pack(pady=5)

        tk.Label(self, text="Senha").pack()
        self.entry_senha = tk.Entry(self, show="*")
        self.entry_senha.pack(pady=5)

        tk.Button(self, text="Entrar", command=self._autenticar).pack(pady=15)

    def _autenticar(self):
        usuario = self.entry_usuario.get().strip()
        senha = self.entry_senha.get().strip()

        if not usuario or not senha:
            messagebox.showwarning("Atenção", "Preencha usuário e senha.")
            return

        if not self.db.connection:
            if not self.db.conectar():
                messagebox.showerror("Erro", "Não foi possível conectar ao banco de dados.")
                return

        try:
            usuario_valido = self.db.validar_login(usuario, senha)
            if usuario_valido:
                self.logger.info(f"Login bem-sucedido: {usuario}")
                self.destroy()
                app = MainWindow(self.db, self.logger)
                app.mainloop()
            else:
                self.logger.warning(f"Tentativa de login inválida: {usuario}")
                messagebox.showerror("Erro", "Usuário ou senha inválidos.")
        except Exception as e:
            self.logger.error("Erro durante autenticação", e)
            messagebox.showerror("Erro", "Ocorreu um erro ao autenticar.")


class MainWindow(tk.Tk):
    """Janela principal: cadastro de notícias, categorias, autores e gráfico."""

    def __init__(self, db: DatabaseManager, logger: Logger):
        super().__init__()
        self.db = db
        self.logger = logger

        self.title("NewsManager - Sistema de Gerenciamento e Análise de Notícias")
        self.geometry("900x600")

        self._montar_layout()
        self._carregar_noticias()

    # ---------- Layout geral ----------
    def _montar_layout(self):
        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True)

        self.aba_noticias = ttk.Frame(abas)
        self.aba_grafico = ttk.Frame(abas)

        abas.add(self.aba_noticias, text="Notícias")
        abas.add(self.aba_grafico, text="Gráficos")

        self._montar_aba_noticias()
        self._montar_aba_grafico()

    # ---------- Aba de Notícias (CRUD) ----------
    def _montar_aba_noticias(self):
        frame_form = ttk.LabelFrame(self.aba_noticias, text="Nova / Editar Notícia")
        frame_form.pack(fill="x", padx=10, pady=10)

        tk.Label(frame_form, text="Título").grid(row=0, column=0, sticky="w")
        self.entry_titulo = tk.Entry(frame_form, width=50)
        self.entry_titulo.grid(row=0, column=1, padx=5, pady=3)

        tk.Label(frame_form, text="Categoria ID").grid(row=1, column=0, sticky="w")
        self.entry_categoria = tk.Entry(frame_form)
        self.entry_categoria.grid(row=1, column=1, sticky="w", padx=5, pady=3)

        tk.Label(frame_form, text="Autor ID").grid(row=2, column=0, sticky="w")
        self.entry_autor = tk.Entry(frame_form)
        self.entry_autor.grid(row=2, column=1, sticky="w", padx=5, pady=3)

        tk.Label(frame_form, text="Conteúdo").grid(row=3, column=0, sticky="nw")
        self.text_conteudo = tk.Text(frame_form, width=50, height=4)
        self.text_conteudo.grid(row=3, column=1, padx=5, pady=3)

        botoes = ttk.Frame(frame_form)
        botoes.grid(row=4, column=1, sticky="w", pady=5)
        ttk.Button(botoes, text="Adicionar", command=self._adicionar_noticia).pack(side="left", padx=3)
        ttk.Button(botoes, text="Atualizar", command=self._atualizar_noticia).pack(side="left", padx=3)
        ttk.Button(botoes, text="Excluir", command=self._excluir_noticia).pack(side="left", padx=3)

        colunas = ("id", "titulo", "categoria", "autor", "data_publicacao")
        self.tree = ttk.Treeview(self.aba_noticias, columns=colunas, show="headings")
        for col in colunas:
            self.tree.heading(col, text=col.capitalize())
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.bind("<<TreeviewSelect>>", self._selecionar_noticia)

    def _carregar_noticias(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for noticia in self.db.listar_noticias():
                self.tree.insert("", "end", values=(
                    noticia["id"], noticia["titulo"], noticia["categoria"],
                    noticia["autor"], noticia["data_publicacao"],
                ))
        except Exception as e:
            self.logger.error("Erro ao carregar notícias", e)

    def _adicionar_noticia(self):
        try:
            self.db.criar_noticia(
                self.entry_titulo.get(),
                self.text_conteudo.get("1.0", "end").strip(),
                int(self.entry_categoria.get()),
                int(self.entry_autor.get()),
                date.today(),
            )
            self._carregar_noticias()
            self.logger.info("Notícia adicionada.")
        except Exception as e:
            self.logger.error("Erro ao adicionar notícia", e)
            messagebox.showerror("Erro", "Não foi possível adicionar a notícia.")

    def _selecionar_noticia(self, event):
        selecionado = self.tree.focus()
        if selecionado:
            self._id_selecionado = self.tree.item(selecionado)["values"][0]

    def _atualizar_noticia(self):
        if not getattr(self, "_id_selecionado", None):
            messagebox.showwarning("Atenção", "Selecione uma notícia na lista.")
            return
        try:
            self.db.atualizar_noticia(
                self._id_selecionado,
                self.entry_titulo.get(),
                self.text_conteudo.get("1.0", "end").strip(),
                int(self.entry_categoria.get()),
                int(self.entry_autor.get()),
                date.today(),
            )
            self._carregar_noticias()
            self.logger.info(f"Notícia {self._id_selecionado} atualizada.")
        except Exception as e:
            self.logger.error("Erro ao atualizar notícia", e)
            messagebox.showerror("Erro", "Não foi possível atualizar a notícia.")

    def _excluir_noticia(self):
        if not getattr(self, "_id_selecionado", None):
            messagebox.showwarning("Atenção", "Selecione uma notícia na lista.")
            return
        try:
            self.db.excluir_noticia(self._id_selecionado)
            self._carregar_noticias()
            self.logger.info(f"Notícia {self._id_selecionado} excluída.")
        except Exception as e:
            self.logger.error("Erro ao excluir notícia", e)
            messagebox.showerror("Erro", "Não foi possível excluir a notícia.")

    # ---------- Aba de Gráficos ----------
    def _montar_aba_grafico(self):
        ttk.Button(
            self.aba_grafico, text="Atualizar gráfico", command=self._desenhar_grafico
        ).pack(pady=10)

        self.figura = Figure(figsize=(6, 4))
        self.canvas = FigureCanvasTkAgg(self.figura, master=self.aba_grafico)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self._desenhar_grafico()

    def _desenhar_grafico(self):
        try:
            dados = self.db.contar_noticias_por_categoria()
            self.figura.clear()
            ax = self.figura.add_subplot(111)

            categorias = [d["categoria"] for d in dados]
            totais = [d["total"] for d in dados]

            ax.bar(categorias, totais, color="#2b6cb0")
            ax.set_title("Notícias por Categoria")
            ax.set_ylabel("Quantidade")
            self.figura.autofmt_xdate(rotation=30)
            self.canvas.draw()
        except Exception as e:
            self.logger.error("Erro ao gerar gráfico", e)
