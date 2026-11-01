import os
import subprocess
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TelasComTkFalso(unittest.TestCase):
    """Monta e exercita as telas novas (Previsão do Tempo, Clipping, Perfil) com um Tk de mentira.
    É uma SIMULAÇÃO: pega erros de lógica/nomes, não problemas visuais nem eventos reais."""

    def test_fluxos_das_telas(self):
        r = subprocess.run([sys.executable, os.path.join(RAIZ, "tests", "_rodar_telas.py")], cwd=RAIZ,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("telas: OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
