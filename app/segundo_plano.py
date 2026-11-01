"""
segundo_plano.py
Executa trabalho demorado (rede) fora da thread da interface e devolve o
resultado a ela com `after()`, usando uma fila — o Tkinter nunca é tocado pela
thread de trabalho.

Regras de uso:
- `funcao` roda na thread de trabalho: pode usar rede, NUNCA widgets Tk nem o
  banco de dados (a conexão MySQL é única e não é segura entre threads).
- `ao_concluir(ok, valor)` roda na thread principal: aí sim se mexe em widgets e
  no banco. Se `ok` for False, `valor` é a exceção.
"""

import queue
import threading

INTERVALO_VERIFICACAO_MS = 80


def executar_async(widget, funcao, ao_concluir):
    fila = queue.Queue()

    def trabalho():
        try:
            fila.put((True, funcao()))
        except Exception as erro:   # devolvida à interface, que decide o que mostrar
            fila.put((False, erro))

    def verificar():
        try:
            ok, valor = fila.get_nowait()
        except queue.Empty:
            try:
                widget.after(INTERVALO_VERIFICACAO_MS, verificar)
            except Exception:       # janela fechada
                pass
            return
        try:
            ao_concluir(ok, valor)
        except Exception as erro:   # janela fechada no meio: não derruba nada
            if type(erro).__name__ != "TclError":
                raise

    threading.Thread(target=trabalho, daemon=True).start()
    widget.after(INTERVALO_VERIFICACAO_MS, verificar)


def executar_sincrono(widget, funcao, ao_concluir):
    """Mesma interface, sem thread: usada nos testes."""
    try:
        resultado = (True, funcao())
    except Exception as erro:
        resultado = (False, erro)
    ao_concluir(*resultado)
