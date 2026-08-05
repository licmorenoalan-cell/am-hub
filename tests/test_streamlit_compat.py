import ast
from pathlib import Path
import unittest


class StreamlitCompatibilityTests(unittest.TestCase):
    def test_tipos_de_boton_compatibles_con_streamlit_instalado(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(app_path.read_text(encoding="utf-8"))
        tipos_permitidos = {"primary", "secondary"}
        incompatibles = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "button":
                continue

            for keyword in node.keywords:
                if keyword.arg != "type":
                    continue
                if not isinstance(keyword.value, ast.Constant):
                    continue
                if keyword.value.value not in tipos_permitidos:
                    incompatibles.append(
                        (node.lineno, keyword.value.value)
                    )

        self.assertEqual(incompatibles, [])


if __name__ == "__main__":
    unittest.main()
