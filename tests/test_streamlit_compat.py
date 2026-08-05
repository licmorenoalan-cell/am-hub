import ast
from pathlib import Path
import unittest


class StreamlitCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.app_path = Path(__file__).resolve().parents[1] / "app.py"

    def test_tipos_de_boton_compatibles_con_streamlit_instalado(self):
        tree = ast.parse(self.app_path.read_text(encoding="utf-8"))
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

    def test_checklist_editable_usa_una_sola_grilla(self):
        source = self.app_path.read_text(encoding="utf-8")
        checklist = source.index('st.markdown("**Checklist**")')
        inicio = source.index("texto_item = str(", checklist)
        fin = source.index("checklist_actualizado.append", inicio)

        self.assertEqual(source[inicio:fin].count("st.columns("), 1)


if __name__ == "__main__":
    unittest.main()
