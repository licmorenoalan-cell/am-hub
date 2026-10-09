import unittest
from datetime import datetime, timedelta, timezone

from am_hub_auth import crear_token_sesion, validar_token_sesion


class AuthSessionTests(unittest.TestCase):
    def setUp(self):
        self.secret = b"una-clave-de-prueba-estable"
        self.ahora = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
        self.users = {
            "alan": {"password": "clave-segura", "role": "admin"},
        }

    def token(self):
        return crear_token_sesion(
            "alan", "clave-segura", self.secret, dias=30, ahora=self.ahora,
        )

    def test_sesion_valida_durante_treinta_dias(self):
        resultado = validar_token_sesion(
            self.token(),
            self.users,
            self.secret,
            ahora=self.ahora + timedelta(days=29),
        )
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado[0]["u"], "alan")

    def test_sesion_expirada_es_rechazada(self):
        resultado = validar_token_sesion(
            self.token(),
            self.users,
            self.secret,
            ahora=self.ahora + timedelta(days=30),
        )
        self.assertIsNone(resultado)

    def test_token_adulterado_es_rechazado(self):
        token = self.token()
        adulterado = token[:-1] + ("A" if token[-1] != "A" else "B")
        self.assertIsNone(
            validar_token_sesion(adulterado, self.users, self.secret)
        )

    def test_cambio_de_clave_revoca_la_sesion(self):
        users = {"alan": {"password": "otra-clave", "role": "admin"}}
        self.assertIsNone(
            validar_token_sesion(self.token(), users, self.secret)
        )

    def test_usuario_desactivado_o_eliminado_no_restaurara_sesion(self):
        self.assertIsNone(
            validar_token_sesion(self.token(), {}, self.secret)
        )


if __name__ == "__main__":
    unittest.main()
