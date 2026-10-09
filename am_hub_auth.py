"""Sesiones persistentes firmadas para AM HUB."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json


def _b64_encode(contenido: bytes) -> str:
    return base64.urlsafe_b64encode(contenido).decode("ascii").rstrip("=")


def _b64_decode(contenido: str) -> bytes:
    relleno = "=" * (-len(contenido) % 4)
    return base64.urlsafe_b64decode((contenido + relleno).encode("ascii"))


def _password_version(password: str, secret: bytes) -> str:
    return hmac.new(
        secret, str(password).encode("utf-8"), hashlib.sha256,
    ).hexdigest()[:20]


def crear_token_sesion(
    username: str,
    password: str,
    secret: bytes,
    dias: int = 30,
    ahora: datetime | None = None,
) -> str:
    ahora = ahora or datetime.now(timezone.utc)
    payload = {
        "u": str(username),
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + timedelta(days=dias)).timestamp()),
        "pv": _password_version(password, secret),
    }
    cuerpo = _b64_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    firma = _b64_encode(
        hmac.new(secret, cuerpo.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{cuerpo}.{firma}"


def validar_token_sesion(
    token: str,
    users: dict,
    secret: bytes,
    ahora: datetime | None = None,
):
    """Devuelve ``(payload, usuario)`` si la sesión sigue siendo válida."""
    try:
        cuerpo, firma = str(token).split(".", 1)
        firma_esperada = _b64_encode(
            hmac.new(secret, cuerpo.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(firma, firma_esperada):
            return None

        payload = json.loads(_b64_decode(cuerpo).decode("utf-8"))
        ahora = ahora or datetime.now(timezone.utc)
        if int(payload.get("exp", 0)) <= int(ahora.timestamp()):
            return None

        user = users.get(str(payload.get("u", "")))
        if not user:
            return None
        if not hmac.compare_digest(
            str(payload.get("pv", "")),
            _password_version(user.get("password", ""), secret),
        ):
            return None
        return payload, user
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
