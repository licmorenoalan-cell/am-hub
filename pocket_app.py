import hmac
import html
import os
import secrets
import base64
import uuid
from datetime import date
from pathlib import Path
import re

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from am_hub_i18n import LANGUAGES, normalize_language, translate


st.set_page_config(
    page_title="AM Pocket",
    page_icon="📥",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .block-container {
            max-width: 760px;
            padding-top: 1.1rem;
            padding-left: 0.9rem;
            padding-right: 0.9rem;
            padding-bottom: 4rem;
        }

        [data-testid="stHeader"] {
            height: 0;
        }

        [data-testid="stSidebar"] {
            display: none;
        }

        .pocket-title {
            font-size: 1.65rem;
            font-weight: 800;
            color: #244777;
            margin-bottom: 0;
        }

        .pocket-subtitle {
            color: #667085;
            margin-top: 0.15rem;
            margin-bottom: 1rem;
        }

        .task-meta {
            color: #667085;
            font-size: 0.88rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 14px;
        }

        .stButton button {
            min-height: 42px;
        }

        textarea {
            font-size: 16px !important;
        }

        input {
            font-size: 16px !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


BASE_DIR = Path(__file__).resolve().parent

ESTADOS = [
    "A priorizar",
    "Pendiente",
    "En curso",
    "En revisión",
    "Finalizada",
    "Pausada",
]

UNIDADES = [
    "AM Consultora",
    "Comunidad",
    "BRC Trading",
    "Universidad",
    "Personal",
]

COLORES_UNIDAD = {
    "AM Consultora": "🟦",
    "Comunidad": "🟩",
    "BRC Trading": "🟧",
    "Universidad": "🟪",
    "Personal": "🟨",
}


def pocket_language() -> str:
    return normalize_language(
        st.session_state.get(
            "pocket_language",
            st.query_params.get("lang", "es"),
        )
    )


def pocket_ui(texto: str) -> str:
    return translate(texto, pocket_language())


def get_secret(nombre: str, default: str = "") -> str:
    valor_env = os.getenv(nombre)

    if valor_env:
        return str(valor_env)

    try:
        return str(st.secrets.get(nombre, default))
    except Exception:
        return default


def normalizar_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    if url.startswith("postgres://"):
        return url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )

    return url


@st.cache_resource
def get_engine():
    url = normalizar_database_url(
        get_secret("DATABASE_URL")
    )

    if not url:
        raise RuntimeError(
            "DATABASE_URL no está configurada."
        )

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=1,
        max_overflow=2,
        connect_args={
            "connect_timeout": 10,
        },
    )


def acceso_autorizado() -> bool:
    token_configurado = get_secret(
        "POCKET_ACCESS_TOKEN"
    )

    if not token_configurado:
        st.error(
            "Falta configurar POCKET_ACCESS_TOKEN."
        )
        return False

    token_url = str(
        st.query_params.get("token", "")
    ).strip()

    if (
        token_url
        and hmac.compare_digest(
            token_url,
            token_configurado,
        )
    ):
        return True

    st.markdown(
        '<p class="pocket-title">AM Pocket</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="pocket-subtitle">'
        "Acceso personal al centro de tareas."
        "</p>",
        unsafe_allow_html=True,
    )

    token_ingresado = st.text_input(
        "Código de acceso",
        type="password",
    )

    if st.button(
        "Ingresar",
        type="primary",
        use_container_width=True,
    ):
        if hmac.compare_digest(
            token_ingresado.strip(),
            token_configurado,
        ):
            st.query_params["token"] = (
                token_configurado
            )
            st.rerun()
        else:
            st.error("Código incorrecto.")

    return False


@st.cache_resource
def asegurar_columnas():
    engine = get_engine()

    columnas = {
        "unidad": "text",
        "proyecto": "text",
        "cliente": "text",
        "tarea": "text",
        "descripcion": "text",
        "responsable_am": "text",
        "prioridad": "text",
        "estado": "text",
        "fecha_limite": "text",
        "checklist": "text",
        "avance": "integer",
        "recurrente": "text",
        "frecuencia": "text",
        "intervalo": "integer",
        "serie_id": "text",
        "ocurrencia": "integer",
        "comentarios": "text",
        "origen": "text",
        "id_externo": "text",
        "categoria": "text",
        "fecha_carga": "text",
        "creado_por": "text",
        "fecha_actualizacion": "text",
        "actualizado_por": "text",
        "archivos_habilitados": "text",
        "posicion_manual": "text",
    }

    with engine.begin() as conn:
        for columna, tipo in columnas.items():
            conn.execute(
                text(
                    f'ALTER TABLE "tareas" '
                    f'ADD COLUMN IF NOT EXISTS '
                    f'"{columna}" {tipo}'
                )
            )
        conn.execute(
            text(
                'CREATE TABLE IF NOT EXISTS "tarea_archivos" ('
                '"id" TEXT PRIMARY KEY, "tarea_id" TEXT NOT NULL, '
                '"nombre" TEXT NOT NULL, "tipo" TEXT, "tamano" BIGINT, '
                '"contenido_base64" TEXT NOT NULL, "fecha_carga" TEXT, '
                '"cargado_por" TEXT)'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE "objetivos" ADD COLUMN IF NOT EXISTS '
                '"responsable_tipo" TEXT'
            )
        )


@st.cache_data(
    ttl=20,
    show_spinner=False,
)
def cargar_tareas():
    engine = get_engine()

    consulta = text(
        """
        SELECT
            id,
            unidad,
            proyecto,
            cliente,
            tarea,
            descripcion,
            responsable_am,
            prioridad,
            estado,
            fecha_limite,
            checklist,
            avance,
            categoria,
            comentarios,
            recurrente,
            frecuencia,
            intervalo,
            fecha_carga,
            fecha_actualizacion
            , archivos_habilitados
            , posicion_manual
        FROM tareas
        ORDER BY
            CASE
                WHEN posicion_manual ~ '^[0-9]+$'
                THEN posicion_manual::integer
                ELSE NULL
            END ASC NULLS LAST,
            CASE prioridad
                WHEN 'Alta' THEN 1
                WHEN 'Media' THEN 2
                WHEN 'Baja' THEN 3
                ELSE 4
            END,
            NULLIF(fecha_limite, '') ASC NULLS LAST,
            fecha_carga DESC
        """
    )

    with engine.connect() as conn:
        return pd.read_sql(
            consulta,
            conn,
        ).fillna("")


@st.cache_data(ttl=20, show_spinner=False)
def cargar_plan_trabajo():
    """Carga solo los campos necesarios para la vista móvil del plan."""
    consulta = text(
        """
        SELECT
            id, cliente, mes, objetivo, descripcion,
            responsable_am, responsable_cliente, responsable_tipo, prioridad,
            estado, avance, checklist, fecha_limite,
            comentarios, fecha_actualizacion
        FROM objetivos
        ORDER BY
            CASE prioridad
                WHEN 'Alta' THEN 1
                WHEN 'Media' THEN 2
                WHEN 'Baja' THEN 3
                ELSE 4
            END,
            NULLIF(fecha_limite, '') ASC NULLS LAST,
            fecha_actualizacion DESC
        """
    )

    with get_engine().connect() as conn:
        return pd.read_sql(consulta, conn).fillna("")


@st.cache_data(ttl=20, show_spinner=False)
def cargar_cuenta_corriente_pocket():
    # El comprobante se excluye: puede ser pesado y no hace falta para listar.
    consulta = text(
        """
        SELECT id, cliente, mes, concepto, servicio, importe, estado,
               fecha_factura, fecha_pago, observacion, fecha_carga,
               cargado_por
        FROM cuenta_corriente
        ORDER BY mes DESC, fecha_factura DESC, id DESC
        """
    )
    with get_engine().connect() as conn:
        return pd.read_sql(consulta, conn).fillna("")


@st.cache_data(ttl=120, show_spinner=False)
def cargar_clientes_pocket():
    with get_engine().connect() as conn:
        filas = conn.execute(
            text(
                "SELECT cliente FROM clientes "
                "WHERE TRIM(COALESCE(cliente, '')) <> '' "
                "ORDER BY cliente"
            )
        ).scalars().all()
    return [str(cliente).strip() for cliente in filas if str(cliente).strip()]


def guardar_deuda_pocket(
    cliente, mes, concepto, servicio, importe, estado,
    fecha_factura, observacion,
):
    usuario = get_secret("POCKET_USERNAME", "alan")
    hoy = date.today().strftime("%Y-%m-%d")
    registro = {
        "id": f"CC-{uuid.uuid4().hex[:12].upper()}",
        "cliente": str(cliente).strip(),
        "mes": str(mes).strip(),
        "concepto": str(concepto).strip() or "Honorarios mensuales",
        "servicio": str(servicio).strip() or "General",
        "importe": float(importe),
        "estado": str(estado).strip(),
        "fecha_factura": fecha_factura.strftime("%Y-%m-%d"),
        "fecha_pago": hoy if estado == "Pagado" else "",
        "observacion": str(observacion).strip(),
        "fecha_carga": hoy,
        "cargado_por": usuario,
    }
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO cuenta_corriente
                    (id, cliente, mes, concepto, servicio, importe, estado,
                     fecha_factura, fecha_pago, observacion, fecha_carga,
                     cargado_por, comprobante_nombre, comprobante_tipo,
                     comprobante_base64)
                VALUES
                    (:id, :cliente, :mes, :concepto, :servicio, :importe,
                     :estado, :fecha_factura, :fecha_pago, :observacion,
                     :fecha_carga, :cargado_por, '', '', '')
                """
            ),
            registro,
        )
    cargar_cuenta_corriente_pocket.clear()


def registrar_pago_pocket(movimiento_id, fecha_pago, observacion):
    usuario = get_secret("POCKET_USERNAME", "alan")
    nota = str(observacion or "").strip()
    agregado = (
        f"{fecha_pago.strftime('%Y-%m-%d')} - Pago registrado por "
        f"{usuario}" + (f": {nota}" if nota else "")
    )
    with get_engine().begin() as conn:
        resultado = conn.execute(
            text(
                """
                UPDATE cuenta_corriente
                SET estado = 'Pagado', fecha_pago = :fecha_pago,
                    observacion = CASE
                        WHEN TRIM(COALESCE(observacion, '')) = '' THEN :nota
                        ELSE observacion || E'\n' || :nota
                    END
                WHERE id = :id
                """
            ),
            {
                "id": str(movimiento_id),
                "fecha_pago": fecha_pago.strftime("%Y-%m-%d"),
                "nota": agregado,
            },
        )
    cargar_cuenta_corriente_pocket.clear()
    return bool(resultado.rowcount)


@st.cache_data(ttl=120, show_spinner=False)
def cargar_adjuntos_pocket(tarea_id):
    with get_engine().connect() as conn:
        return pd.read_sql(
            text(
                'SELECT id, nombre, tipo, tamano, fecha_carga, cargado_por '
                'FROM tarea_archivos WHERE tarea_id = :tarea_id '
                'ORDER BY fecha_carga DESC'
            ),
            conn,
            params={"tarea_id": str(tarea_id)},
        ).fillna("")


def configurar_archivos_pocket(tarea_id, habilitar):
    with get_engine().begin() as conn:
        conn.execute(
            text(
                'UPDATE tareas SET archivos_habilitados = :valor '
                'WHERE id = :id'
            ),
            {
                "valor": "Sí" if habilitar else "No",
                "id": str(tarea_id),
            },
        )
    limpiar_cache()


def guardar_adjuntos_pocket(tarea_id, archivos):
    archivos = list(archivos or [])
    if not archivos:
        return 0
    if len(archivos) > 5:
        raise ValueError("Podés cargar hasta 5 archivos por vez.")

    existentes = cargar_adjuntos_pocket(tarea_id)
    if len(existentes) + len(archivos) > 20:
        raise ValueError("Cada tarjeta admite hasta 20 archivos.")

    usuario = get_secret("POCKET_USERNAME", "alan")
    registros = []
    for archivo in archivos:
        contenido = archivo.getvalue()
        if len(contenido) > 8 * 1024 * 1024:
            raise ValueError(f'"{archivo.name}" supera el límite de 8 MB.')
        registros.append({
            "id": f"ADJ-{uuid.uuid4().hex}",
            "tarea_id": str(tarea_id),
            "nombre": str(archivo.name),
            "tipo": str(archivo.type or "application/octet-stream"),
            "tamano": len(contenido),
            "contenido_base64": base64.b64encode(contenido).decode("ascii"),
            "fecha_carga": pd.Timestamp.now(
                tz="America/Argentina/Buenos_Aires"
            ).isoformat(),
            "cargado_por": usuario,
        })

    total_existente = pd.to_numeric(
        existentes.get("tamano", pd.Series(dtype="float64")),
        errors="coerce",
    ).fillna(0).sum()
    total_nuevo = sum(registro["tamano"] for registro in registros)
    if total_existente + total_nuevo > 40 * 1024 * 1024:
        raise ValueError(
            "Los adjuntos de la tarjeta no pueden superar 40 MB en total."
        )

    with get_engine().begin() as conn:
        conn.execute(
            text(
                'INSERT INTO tarea_archivos '
                '(id, tarea_id, nombre, tipo, tamano, contenido_base64, '
                'fecha_carga, cargado_por) VALUES '
                '(:id, :tarea_id, :nombre, :tipo, :tamano, '
                ':contenido_base64, :fecha_carga, :cargado_por)'
            ),
            registros,
        )
    cargar_adjuntos_pocket.clear()
    return len(registros)


def cargar_archivo_pocket(archivo_id, tarea_id):
    with get_engine().connect() as conn:
        fila = conn.execute(
            text(
                'SELECT nombre, tipo, contenido_base64 FROM tarea_archivos '
                'WHERE id = :archivo_id AND tarea_id = :tarea_id'
            ),
            {
                "archivo_id": str(archivo_id),
                "tarea_id": str(tarea_id),
            },
        ).mappings().first()
    return dict(fila) if fila else {}


def render_archivos_frente_pocket(frente_id):
    clave_abierto = f"pocket_archivos_frente_abierto_{frente_id}"
    if not st.session_state.get(clave_abierto, False):
        if st.button(
            "📎 Adjuntar / ver archivos",
            key=f"pocket_abrir_archivos_frente_{frente_id}",
            use_container_width=True,
        ):
            st.session_state[clave_abierto] = True
            st.rerun()
        return

    with st.container(border=True):
        st.markdown("**📎 Archivos adjuntos**")
        st.caption("Hasta 5 por vez y 8 MB por archivo.")
        nuevos = st.file_uploader(
            "Agregar archivos",
            accept_multiple_files=True,
            key=f"pocket_subir_archivos_frente_{frente_id}",
        )
        if st.button(
            "Subir archivos",
            key=f"pocket_guardar_archivos_frente_{frente_id}",
            disabled=not nuevos,
            use_container_width=True,
        ):
            try:
                cantidad = guardar_adjuntos_pocket(frente_id, nuevos)
                st.success(f"{cantidad} archivo(s) cargado(s).")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        adjuntos = cargar_adjuntos_pocket(frente_id)
        if adjuntos.empty:
            st.caption("Todavía no hay archivos adjuntos.")
        else:
            for _, adjunto in adjuntos.iterrows():
                archivo_id = str(adjunto.get("id", ""))
                nombre = str(adjunto.get("nombre", "archivo"))
                preparar = f"pocket_frente_archivo_preparado_{frente_id}"
                if st.button(
                    f"Preparar {nombre}",
                    key=f"pocket_preparar_frente_{archivo_id}",
                    use_container_width=True,
                ):
                    st.session_state[preparar] = archivo_id
                if st.session_state.get(preparar) == archivo_id:
                    archivo = cargar_archivo_pocket(archivo_id, frente_id)
                    contenido = str(archivo.get("contenido_base64", "") or "")
                    if contenido:
                        st.download_button(
                            f"Descargar {nombre}",
                            data=base64.b64decode(contenido),
                            file_name=str(archivo.get("nombre", nombre)),
                            mime=str(
                                archivo.get("tipo", "application/octet-stream")
                            ),
                            key=f"pocket_descargar_frente_{archivo_id}",
                            use_container_width=True,
                        )

        if st.button(
            "Cerrar archivos",
            key=f"pocket_cerrar_archivos_frente_{frente_id}",
            use_container_width=True,
        ):
            st.session_state[clave_abierto] = False
            st.rerun()


@st.cache_data(
    ttl=120,
    show_spinner=False,
)
def cargar_usuarios_equipo():
    engine = get_engine()

    consulta = text(
        """
        SELECT
            username,
            name
        FROM usuarios
        WHERE
            LOWER(TRIM(COALESCE(role, ''))) = 'equipo'
            AND LOWER(TRIM(COALESCE(activo, 'Sí'))) IN (
                'sí',
                'si',
                'yes',
                'true',
                '1',
                'activo'
            )
            AND TRIM(COALESCE(username, '')) <> ''
        ORDER BY
            COALESCE(
                NULLIF(TRIM(name), ''),
                username
            )
        """
    )

    with engine.connect() as conn:
        usuarios = pd.read_sql(
            consulta,
            conn,
        ).fillna("")

    resultado = []

    for _, row in usuarios.iterrows():
        username = str(
            row.get("username", "")
        ).strip()

        nombre = str(
            row.get("name", "")
        ).strip()

        if not username:
            continue

        resultado.append({
            "username": username,
            "nombre": nombre or username,
        })

    return resultado


def mapa_responsables_equipo():
    usuarios = cargar_usuarios_equipo()

    mapa = {
        "Sin asignar": "Sin asignar",
    }

    for usuario in usuarios:
        username = usuario["username"]
        nombre = usuario["nombre"]

        mapa[username] = nombre

    return mapa


def limpiar_cache():
    cargar_tareas.clear()
    cargar_plan_trabajo.clear()
    cargar_cuenta_corriente_pocket.clear()
    cargar_clientes_pocket.clear()
    cargar_adjuntos_pocket.clear()


def insertar_tareas(
    textos: list[str],
    una_por_linea: bool,
):
    engine = get_engine()
    hoy = date.today().strftime("%Y-%m-%d")
    usuario = get_secret(
        "POCKET_USERNAME",
        "alan",
    )

    registros = []

    for indice, contenido in enumerate(textos):
        contenido = str(contenido or "").strip()

        if not contenido:
            continue

        lineas = [
            linea.strip()
            for linea in contenido.splitlines()
            if linea.strip()
        ]

        if not lineas:
            continue

        titulo = (
            contenido
            if una_por_linea
            else lineas[0]
        )

        descripcion = (
            ""
            if una_por_linea or len(lineas) <= 1
            else contenido
        )

        identificador = (
            "TAR-POCKET-"
            + pd.Timestamp.now().strftime(
                "%Y%m%d%H%M%S%f"
            )
            + f"-{indice}"
        )

        registros.append({
            "id": identificador,
            "unidad": "AM Consultora",
            "proyecto": "AM Consultora",
            "cliente": "",
            "tarea": titulo[:250],
            "descripcion": descripcion,
            "responsable_am": "Sin asignar",
            "prioridad": "Media",
            "estado": "A priorizar",
            "fecha_limite": "",
            "checklist": "[]",
            "avance": 0,
            "recurrente": "No",
            "frecuencia": "",
            "intervalo": 1,
            "serie_id": "",
            "ocurrencia": 1,
            "comentarios": "",
            "origen": "AM Pocket",
            "id_externo": "",
            "categoria": "Bandeja de entrada",
            "fecha_carga": hoy,
            "creado_por": usuario,
            "fecha_actualizacion": hoy,
            "actualizado_por": usuario,
        })

    if not registros:
        return []

    consulta = text(
        """
        INSERT INTO tareas (
            id,
            unidad,
            proyecto,
            cliente,
            tarea,
            descripcion,
            responsable_am,
            prioridad,
            estado,
            fecha_limite,
            checklist,
            avance,
            recurrente,
            frecuencia,
            intervalo,
            serie_id,
            ocurrencia,
            comentarios,
            origen,
            id_externo,
            categoria,
            fecha_carga,
            creado_por,
            fecha_actualizacion,
            actualizado_por
        )
        VALUES (
            :id,
            :unidad,
            :proyecto,
            :cliente,
            :tarea,
            :descripcion,
            :responsable_am,
            :prioridad,
            :estado,
            :fecha_limite,
            :checklist,
            :avance,
            :recurrente,
            :frecuencia,
            :intervalo,
            :serie_id,
            :ocurrencia,
            :comentarios,
            :origen,
            :id_externo,
            :categoria,
            :fecha_carga,
            :creado_por,
            :fecha_actualizacion,
            :actualizado_por
        )
        RETURNING id
        """
    )

    ids_creados = []

    with engine.begin() as conn:
        for registro in registros:
            id_creado = conn.execute(
                consulta,
                registro,
            ).scalar_one()

            ids_creados.append(
                str(id_creado)
            )

    cargar_tareas.clear()

    return ids_creados

def actualizar_estado(
    tarea_id: str,
    nuevo_estado: str,
):
    engine = get_engine()
    hoy = date.today().strftime("%Y-%m-%d")
    usuario = get_secret(
        "POCKET_USERNAME",
        "alan",
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE tareas
                SET
                    estado = :estado,
                    fecha_actualizacion = :fecha,
                    actualizado_por = :usuario
                WHERE id = :id
                """
            ),
            {
                "estado": nuevo_estado,
                "fecha": hoy,
                "usuario": usuario,
                "id": tarea_id,
            },
        )

    limpiar_cache()


def eliminar_tarea(tarea_id: str) -> bool:
    engine = get_engine()

    with engine.begin() as conn:
        resultado = conn.execute(
            text(
                """
                DELETE FROM tareas
                WHERE id = :id
                """
            ),
            {
                "id": str(tarea_id),
            },
        )

    limpiar_cache()

    return bool(resultado.rowcount)


def parsear_checklist(valor):
    import json

    if valor is None:
        return []

    if isinstance(valor, list):
        return valor

    texto_valor = str(valor).strip()

    if not texto_valor:
        return []

    try:
        datos = json.loads(texto_valor)
    except Exception:
        return []

    if not isinstance(datos, list):
        return []

    resultado = []

    for item in datos:
        if isinstance(item, dict):
            texto_item = str(
                item.get("texto", "")
            ).strip()

            if texto_item:
                resultado.append({
                    "texto": texto_item,
                    "hecho": bool(
                        item.get("hecho", False)
                    ),
                })

    return resultado


def serializar_checklist(items):
    import json

    return json.dumps(
        items,
        ensure_ascii=False,
    )


def agregar_item_checklist_pocket(tarea_id, texto_item):
    texto_limpio = str(texto_item or "").strip()
    if not texto_limpio:
        raise ValueError("Escribí el nombre del ítem.")

    usuario = get_secret("POCKET_USERNAME", "alan")
    hoy = date.today().strftime("%Y-%m-%d")
    with get_engine().begin() as conn:
        fila = conn.execute(
            text(
                'SELECT checklist FROM tareas WHERE id = :id FOR UPDATE'
            ),
            {"id": str(tarea_id)},
        ).mappings().first()
        if fila is None:
            raise ValueError("No se encontró la tarea.")
        items = parsear_checklist(fila.get("checklist", ""))
        items.append({"texto": texto_limpio, "hecho": False})
        completos = sum(1 for item in items if item.get("hecho"))
        avance = int(round(completos * 100 / len(items))) if items else 0
        conn.execute(
            text(
                'UPDATE tareas SET checklist = :checklist, '
                'avance = :avance, fecha_actualizacion = :fecha, '
                'actualizado_por = :usuario WHERE id = :id'
            ),
            {
                "checklist": serializar_checklist(items),
                "avance": avance,
                "fecha": hoy,
                "usuario": usuario,
                "id": str(tarea_id),
            },
        )
    limpiar_cache()


def actualizar_detalle_tarea(
    tarea_id,
    unidad,
    proyecto,
    estado,
    responsable,
    prioridad,
    fecha_limite,
    cliente,
    checklist,
    comentario,
):
    engine = get_engine()
    hoy = date.today().strftime("%Y-%m-%d")
    usuario = get_secret(
        "POCKET_USERNAME",
        "alan",
    )

    completos = sum(
        1
        for item in checklist
        if item.get("hecho")
    )

    total = len(checklist)

    avance = (
        int(round(completos * 100 / total))
        if total
        else 0
    )

    with engine.begin() as conn:
        actual = conn.execute(
            text(
                """
                SELECT comentarios
                FROM tareas
                WHERE id = :id
                """
            ),
            {"id": tarea_id},
        ).scalar()

        historial = str(actual or "").strip()

        if comentario.strip():
            agregado = (
                f"{hoy} - {usuario}: "
                f"{comentario.strip()}"
            )

            historial = (
                historial
                + "\n"
                + agregado
            ).strip()

        conn.execute(
            text(
                """
                UPDATE tareas
                SET
                    unidad = :unidad,
                    proyecto = :proyecto,
                    estado = :estado,
                    responsable_am = :responsable,
                    prioridad = :prioridad,
                    fecha_limite = :fecha_limite,
                    cliente = :cliente,
                    checklist = :checklist,
                    avance = :avance,
                    comentarios = :comentarios,
                    fecha_actualizacion = :fecha_actualizacion,
                    actualizado_por = :actualizado_por
                WHERE id = :id
                """
            ),
            {
                "unidad": unidad,
                "proyecto": proyecto,
                "estado": estado,
                "responsable": responsable,
                "prioridad": prioridad,
                "fecha_limite": fecha_limite,
                "cliente": cliente,
                "checklist": serializar_checklist(
                    checklist
                ),
                "avance": avance,
                "comentarios": historial,
                "fecha_actualizacion": hoy,
                "actualizado_por": usuario,
                "id": tarea_id,
            },
        )

    limpiar_cache()


def actualizar_frente_pocket(
    frente_id,
    cliente,
    mes,
    objetivo,
    descripcion,
    responsable_am,
    responsable_cliente,
    responsable_tipo,
    prioridad,
    estado,
    fecha_limite,
    checklist,
    comentario,
):
    usuario = get_secret("POCKET_USERNAME", "alan")
    hoy = date.today().strftime("%Y-%m-%d")
    items = [
        {
            "texto": str(item.get("texto", "")).strip(),
            "hecho": bool(item.get("hecho", False)),
        }
        for item in checklist
        if str(item.get("texto", "")).strip()
    ]
    completos = sum(1 for item in items if item["hecho"])
    avance = int(round(completos * 100 / len(items))) if items else 0

    with get_engine().begin() as conn:
        fila = conn.execute(
            text(
                "SELECT comentarios FROM objetivos "
                "WHERE id = :id FOR UPDATE"
            ),
            {"id": str(frente_id)},
        ).mappings().first()
        if fila is None:
            raise ValueError("No se encontró el frente de trabajo.")

        historial = str(fila.get("comentarios", "") or "").strip()
        comentario = str(comentario or "").strip()
        if comentario:
            agregado = f"{hoy} - {usuario}: {comentario}"
            historial = (historial + "\n" + agregado).strip()

        conn.execute(
            text(
                """
                UPDATE objetivos
                SET cliente = :cliente, mes = :mes, objetivo = :objetivo,
                    descripcion = :descripcion, responsable = :responsable_am,
                    responsable_am = :responsable_am,
                    responsable_cliente = :responsable_cliente,
                    responsable_tipo = :responsable_tipo,
                    prioridad = :prioridad, estado = :estado,
                    fecha_limite = :fecha_limite, checklist = :checklist,
                    avance = :avance, comentarios = :comentarios,
                    fecha_actualizacion = :fecha_actualizacion,
                    actualizado_por = :actualizado_por
                WHERE id = :id
                """
            ),
            {
                "cliente": str(cliente).strip(),
                "mes": str(mes).strip(),
                "objetivo": str(objetivo).strip(),
                "descripcion": str(descripcion).strip(),
                "responsable_am": str(responsable_am).strip(),
                "responsable_cliente": str(responsable_cliente).strip(),
                "responsable_tipo": str(responsable_tipo).strip(),
                "prioridad": str(prioridad).strip(),
                "estado": str(estado).strip(),
                "fecha_limite": str(fecha_limite).strip(),
                "checklist": serializar_checklist(items),
                "avance": avance,
                "comentarios": historial,
                "fecha_actualizacion": hoy,
                "actualizado_por": usuario,
                "id": str(frente_id),
            },
        )

    cargar_plan_trabajo.clear()


def eliminar_frente_pocket(frente_id):
    with get_engine().begin() as conn:
        resultado = conn.execute(
            text("DELETE FROM objetivos WHERE id = :id"),
            {"id": str(frente_id)},
        )
    cargar_plan_trabajo.clear()
    if resultado.rowcount:
        with get_engine().begin() as conn:
            conn.execute(
                text("DELETE FROM tarea_archivos WHERE tarea_id = :id"),
                {"id": str(frente_id)},
            )
        cargar_adjuntos_pocket.clear()
    return bool(resultado.rowcount)


def texto_fecha(valor: str) -> str:
    fecha = pd.to_datetime(
        str(valor or "").strip(),
        errors="coerce",
    )

    if pd.isna(fecha):
        return pocket_ui("Sin fecha")

    hoy = date.today()
    fecha_tarea = fecha.date()
    texto = fecha.strftime("%d/%m")

    if fecha_tarea < hoy:
        return f"🔴 {'Overdue' if pocket_language() == 'en' else 'Vencida'} · {texto}"

    if fecha_tarea == hoy:
        return f"🟠 {'Today' if pocket_language() == 'en' else 'Hoy'} · {texto}"

    return f"📅 {texto}"


def texto_prioridad(valor: str) -> str:
    mapa = {
        "Alta": "🔴 " + pocket_ui("Alta"),
        "Media": "🟡 " + pocket_ui("Media"),
        "Baja": "🟢 " + pocket_ui("Baja"),
    }

    return mapa.get(
        str(valor or "Media"),
        "🟡 Media",
    )


if not acceso_autorizado():
    st.stop()


idioma_inicial = pocket_language()
if "pocket_language" not in st.session_state:
    st.session_state["pocket_language"] = idioma_inicial

idioma_elegido = st.selectbox(
    "Language / Idioma",
    list(LANGUAGES.keys()),
    format_func=lambda value: LANGUAGES[value],
    key="pocket_language",
)

if idioma_elegido != normalize_language(st.query_params.get("lang", "es")):
    st.query_params["lang"] = idioma_elegido


asegurar_columnas()

st.markdown(
    '<p class="pocket-title">AM Pocket</p>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<p class="pocket-subtitle">{pocket_ui("Capturá y administrá pendientes desde el celular.")}</p>',
    unsafe_allow_html=True,
)

pagina_pocket = st.selectbox(
    pocket_ui("Vista"),
    [
        "📥 Capturar",
        "📋 Mi tablero",
        "🤝 Plan de trabajo",
        "💳 Cuenta corriente",
    ],
    format_func=pocket_ui,
    label_visibility="collapsed",
    key="pocket_pagina",
)

if pagina_pocket == "📥 Capturar":
    mensaje_exito = st.session_state.pop(
        "pocket_mensaje_exito",
        "",
    )

    if mensaje_exito:
        st.success(
            mensaje_exito,
            icon="✅",
        )

    with st.form(
        "pocket_form_captura_confirmada",
        clear_on_submit=True,
        border=False,
    ):
        pendiente = st.text_area(
            pocket_ui("¿Qué tenés pendiente?"),
            placeholder="Type or dictate a task..." if pocket_language() == "en" else "Escribí o dictá un pendiente...",
            height=145,
            key="pocket_captura_confirmada",
        )

        una_por_linea = st.checkbox(
            pocket_ui("Crear una tarjeta por línea"),
            value=False,
            key="pocket_una_por_linea_confirmada",
        )

        crear_tarea = st.form_submit_button(
            pocket_ui("Crear tarea"),
            type="primary",
            use_container_width=True,
        )

    if crear_tarea:
        contenido = str(
            pendiente or ""
        ).strip()

        if not contenido:
            st.warning(
                "Escribí un pendiente antes de crear la tarea."
            )
        else:
            if una_por_linea:
                textos = [
                    linea.strip()
                    for linea in contenido.splitlines()
                    if linea.strip()
                ]
            else:
                textos = [contenido]

            try:
                with st.spinner(
                    "Creando tarea..."
                ):
                    ids_creados = insertar_tareas(
                        textos,
                        una_por_linea,
                    )

                cantidad = len(ids_creados)

                if cantidad == 0:
                    st.error(
                        "La base no confirmó la creación de la tarea."
                    )
                else:
                    st.session_state[
                        "pocket_mensaje_exito"
                    ] = (
                        "TAREA CREADA · "
                        "Quedó guardada en A priorizar."
                        if cantidad == 1
                        else (
                            f"{cantidad} TAREAS CREADAS · "
                            "Quedaron guardadas en A priorizar."
                        )
                    )

                    cargar_tareas.clear()
                    st.rerun()

            except Exception as exc:
                st.error(
                    "No se pudo crear la tarea."
                )
                st.exception(exc)


if pagina_pocket == "📋 Mi tablero":
    tareas = cargar_tareas()

    if tareas.empty:
        st.info(pocket_ui("Todavía no hay tareas."))
        st.stop()

    unidades_existentes = (
        tareas["unidad"]
        .replace("", "AM Consultora")
        .astype(str)
        .str.strip()
        .replace("", "AM Consultora")
        .unique()
        .tolist()
    )
    unidades_disponibles = []
    for unidad_disponible in UNIDADES + sorted(unidades_existentes):
        if (
            unidad_disponible
            and unidad_disponible not in unidades_disponibles
        ):
            unidades_disponibles.append(unidad_disponible)

    proyectos_disponibles = sorted([
        valor
        for valor in (
            tareas["proyecto"]
            .fillna("")
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )
        if valor and valor != "Sin proyecto"
    ])

    clientes_disponibles = sorted([
        valor
        for valor in (
            tareas["cliente"]
            .fillna("")
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )
        if valor
    ])

    responsables_mapa = mapa_responsables_equipo()

    responsables_asignados = [
        valor
        for valor in (
            tareas["responsable_am"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", "Sin asignar")
            .unique()
            .tolist()
        )
        if valor
    ]

    for responsable_existente in responsables_asignados:
        if responsable_existente not in responsables_mapa:
            responsables_mapa[
                responsable_existente
            ] = responsable_existente

    responsables_disponibles = list(
        responsables_mapa.keys()
    )

    prioridades_disponibles = [
        prioridad
        for prioridad in [
            "Alta",
            "Media",
            "Baja",
        ]
        if prioridad in (
            tareas["prioridad"]
            .fillna("")
            .astype(str)
            .unique()
            .tolist()
        )
    ]

    categorias_disponibles = sorted([
        valor
        for valor in (
            tareas["categoria"]
            .fillna("")
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )
        if valor
    ])

    with st.expander(
        "🔎 " + pocket_ui("Filtros"),
        expanded=True,
    ):
        busqueda_tareas = st.text_input(
            pocket_ui("Buscar tarjetas"),
            placeholder=(
                "Tarea, cliente, responsable, categoría..."
            ),
            key="pocket_busqueda_tareas",
        )

        f1, f2 = st.columns(2)

        with f1:
            estados_filtro = st.multiselect(
                pocket_ui("Estado"),
                [
                    "Activas",
                    "A priorizar",
                    "Pendiente",
                    "En curso",
                    "En revisión",
                    "Pausada",
                    "Finalizada",
                ],
                default=["Activas"],
                format_func=pocket_ui,
                key="pocket_filtro_estado_multi",
            )

        with f2:
            unidades_filtro = st.multiselect(
                pocket_ui("Unidad"),
                unidades_disponibles,
                default=[],
                key="pocket_filtro_unidad_multi",
            )

        f3, f4 = st.columns(2)

        with f3:
            clientes_filtro = st.multiselect(
                pocket_ui("Cliente"),
                ["Sin cliente"]
                + clientes_disponibles,
                default=[],
                format_func=pocket_ui,
                key="pocket_filtro_cliente_multi",
            )

        with f4:
            responsables_filtro = st.multiselect(
                pocket_ui("Responsable"),
                responsables_disponibles,
                default=[],
                format_func=lambda valor: (
                    responsables_mapa.get(
                        valor,
                        valor,
                    )
                ),
                key="pocket_filtro_responsable_multi",
            )

        f5, f6 = st.columns(2)

        with f5:
            prioridades_filtro = st.multiselect(
                pocket_ui("Prioridad"),
                prioridades_disponibles,
                default=[],
                format_func=pocket_ui,
                key="pocket_filtro_prioridad_multi",
            )

        with f6:
            categorias_filtro = st.multiselect(
                pocket_ui("Categoría"),
                ["Sin categoría"]
                + categorias_disponibles,
                default=[],
                format_func=pocket_ui,
                key="pocket_filtro_categoria_multi",
            )

        fechas_filtro = st.multiselect(
            pocket_ui("Fecha de vencimiento"),
            [
                "Vencidas",
                "Vencen hoy",
                "Próximos 7 días",
                "Con fecha",
                "Sin fecha",
            ],
            default=[],
            format_func=pocket_ui,
            key="pocket_filtro_fecha_multi",
        )

    vista = tareas.copy()

    if str(busqueda_tareas or "").strip():
        palabras = [
            palabra.strip().casefold()
            for palabra in str(busqueda_tareas).split()
            if palabra.strip()
        ]

        columnas_busqueda = [
            columna
            for columna in [
                "tarea",
                "descripcion",
                "cliente",
                "unidad",
                "proyecto",
                "responsable_am",
                "prioridad",
                "estado",
                "categoria",
                "comentarios",
                "origen",
            ]
            if columna in vista.columns
        ]

        texto_completo = pd.Series(
            "",
            index=vista.index,
            dtype="object",
        )

        for columna in columnas_busqueda:
            texto_completo = (
                texto_completo
                + " "
                + vista[columna]
                .fillna("")
                .astype(str)
                .str.casefold()
            )

        mascara_busqueda = pd.Series(
            True,
            index=vista.index,
        )

        for palabra in palabras:
            mascara_busqueda &= texto_completo.str.contains(
                palabra,
                regex=False,
                na=False,
            )

        vista = vista[
            mascara_busqueda
        ].copy()

    # --------------------------------------------------------
    # Búsqueda libre por palabras clave
    # --------------------------------------------------------

    palabras_busqueda = [
        palabra.strip()
        for palabra in str(
            busqueda_tareas or ""
        ).split()
        if palabra.strip()
    ]

    if palabras_busqueda:
        columnas_busqueda = [
            columna
            for columna in [
                "tarea",
                "descripcion",
                "cliente",
                "unidad",
                "proyecto",
                "responsable_am",
                "prioridad",
                "estado",
                "categoria",
                "comentarios",
                "origen",
            ]
            if columna in vista.columns
        ]

        texto_busqueda = pd.Series(
            "",
            index=vista.index,
            dtype="object",
        )

        for columna in columnas_busqueda:
            texto_busqueda = (
                texto_busqueda
                + " "
                + vista[columna]
                .fillna("")
                .astype(str)
            )

        mascara_busqueda = pd.Series(
            True,
            index=vista.index,
        )

        for palabra in palabras_busqueda:
            mascara_busqueda &= (
                texto_busqueda.str.contains(
                    re.escape(palabra),
                    case=False,
                    na=False,
                    regex=True,
                )
            )

        vista = vista[
            mascara_busqueda
        ].copy()

    # --------------------------------------------------------
    # Estado
    # --------------------------------------------------------

    if estados_filtro:
        estado_serie = (
            vista["estado"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        mascara_estado = pd.Series(
            False,
            index=vista.index,
        )

        if "Activas" in estados_filtro:
            mascara_estado |= estado_serie.ne(
                "Finalizada"
            )

        estados_concretos = [
            valor
            for valor in estados_filtro
            if valor != "Activas"
        ]

        if estados_concretos:
            mascara_estado |= estado_serie.isin(
                estados_concretos
            )

        vista = vista[
            mascara_estado
        ].copy()

    # --------------------------------------------------------
    # Unidad
    # --------------------------------------------------------

    if unidades_filtro:
        vista = vista[
            vista["unidad"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", "AM Consultora")
            .isin(unidades_filtro)
        ].copy()

    # --------------------------------------------------------
    # Cliente
    # --------------------------------------------------------

    if clientes_filtro:
        cliente_serie = (
            vista["cliente"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        mascara_cliente = pd.Series(
            False,
            index=vista.index,
        )

        if "Sin cliente" in clientes_filtro:
            mascara_cliente |= cliente_serie.eq("")

        clientes_concretos = [
            valor
            for valor in clientes_filtro
            if valor != "Sin cliente"
        ]

        if clientes_concretos:
            mascara_cliente |= cliente_serie.isin(
                clientes_concretos
            )

        vista = vista[
            mascara_cliente
        ].copy()

    # --------------------------------------------------------
    # Responsable
    # --------------------------------------------------------

    if responsables_filtro:
        vista = vista[
            vista["responsable_am"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", "Sin asignar")
            .isin(responsables_filtro)
        ].copy()

    # --------------------------------------------------------
    # Prioridad
    # --------------------------------------------------------

    if prioridades_filtro:
        vista = vista[
            vista["prioridad"]
            .fillna("")
            .astype(str)
            .str.strip()
            .isin(prioridades_filtro)
        ].copy()

    # --------------------------------------------------------
    # Categoría
    # --------------------------------------------------------

    if categorias_filtro:
        categoria_serie = (
            vista["categoria"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        mascara_categoria = pd.Series(
            False,
            index=vista.index,
        )

        if "Sin categoría" in categorias_filtro:
            mascara_categoria |= (
                categoria_serie == ""
            )

        categorias_concretas = [
            valor
            for valor in categorias_filtro
            if valor != "Sin categoría"
        ]

        if categorias_concretas:
            mascara_categoria |= (
                categoria_serie.isin(
                    categorias_concretas
                )
            )

        vista = vista[
            mascara_categoria
        ].copy()

    # --------------------------------------------------------
    # Fecha de vencimiento
    # --------------------------------------------------------

    if fechas_filtro:
        fechas_serie = pd.to_datetime(
            vista["fecha_limite"],
            errors="coerce",
        )

        estado_serie = (
            vista["estado"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        hoy_timestamp = pd.Timestamp(
            date.today()
        )

        limite = (
            hoy_timestamp
            + pd.Timedelta(days=7)
        )

        mascara_fecha = pd.Series(
            False,
            index=vista.index,
        )

        if "Vencidas" in fechas_filtro:
            mascara_fecha |= (
                fechas_serie.notna()
                & (fechas_serie < hoy_timestamp)
                & estado_serie.ne("Finalizada")
            )

        if "Vencen hoy" in fechas_filtro:
            mascara_fecha |= (
                fechas_serie.notna()
                & (fechas_serie == hoy_timestamp)
                & estado_serie.ne("Finalizada")
            )

        if "Próximos 7 días" in fechas_filtro:
            mascara_fecha |= (
                fechas_serie.notna()
                & (fechas_serie >= hoy_timestamp)
                & (fechas_serie <= limite)
                & estado_serie.ne("Finalizada")
            )

        if "Con fecha" in fechas_filtro:
            mascara_fecha |= fechas_serie.notna()

        if "Sin fecha" in fechas_filtro:
            mascara_fecha |= fechas_serie.isna()

        vista = vista[
            mascara_fecha
        ].copy()

    st.caption(
        f"{len(vista)} tarea(s)"
    )

    if vista.empty:
        st.info(
            "No hay tareas para estos filtros."
        )

    for _, row in vista.iterrows():
        tarea_id = str(row.get("id", ""))
        titulo = str(
            row.get("tarea", "Sin título")
        )
        unidad = str(
            row.get(
                "unidad",
                "AM Consultora",
            )
            or "AM Consultora"
        )
        proyecto = str(
            row.get("proyecto", "") or ""
        ).strip()
        cliente = str(
            row.get("cliente", "") or ""
        )
        estado = str(
            row.get("estado", "Pendiente")
        )
        prioridad = str(
            row.get("prioridad", "Media")
        )
        responsable = str(
            row.get(
                "responsable_am",
                "Sin asignar",
            )
            or "Sin asignar"
        )
        categoria = str(
            row.get("categoria", "") or ""
        )
        archivos_habilitados = (
            str(row.get("archivos_habilitados", "")).strip() == "Sí"
        )

        with st.container(border=True):
            etiqueta_unidad = (
                f"{COLORES_UNIDAD.get(unidad, '⬜')} "
                f"{unidad}"
            )

            if cliente:
                etiqueta_unidad += (
                    f" · {cliente}"
                )

            st.caption(etiqueta_unidad)

            titulo_col, check_col = st.columns(
                [6, 1],
                vertical_alignment="center",
            )

            with titulo_col:
                st.markdown(f"**{titulo}**")

            with check_col:
                if estado != "Finalizada":
                    if st.button(
                        "✓",
                        key=f"pocket_fin_{tarea_id}",
                        help="Finalizar",
                        use_container_width=True,
                    ):
                        actualizar_estado(
                            tarea_id,
                            "Finalizada",
                        )
                        st.rerun()

            st.caption(
                f"{texto_prioridad(prioridad)}"
                f" · {texto_fecha(row.get('fecha_limite', ''))}"
            )

            detalle = f"👤 {responsable}"

            if categoria:
                detalle += f" · {categoria}"

            st.caption(detalle)

            nuevo_estado = st.selectbox(
                "Mover a",
                ESTADOS,
                index=(
                    ESTADOS.index(estado)
                    if estado in ESTADOS
                    else 0
                ),
                key=f"pocket_estado_{tarea_id}",
                label_visibility="collapsed",
            )

            if nuevo_estado != estado:
                actualizar_estado(
                    tarea_id,
                    nuevo_estado,
                )
                st.rerun()

            detalle_abierto = (
                st.session_state.get(
                    "pocket_tarea_abierta",
                    "",
                )
                == tarea_id
            )

            texto_boton = (
                "Cerrar"
                if detalle_abierto
                else "Abrir"
            )

            if st.button(
                texto_boton,
                key=f"pocket_abrir_{tarea_id}",
                use_container_width=True,
            ):
                st.session_state[
                    "pocket_tarea_abierta"
                ] = (
                    ""
                    if detalle_abierto
                    else tarea_id
                )

                detalle_abierto = (
                    st.session_state.get(
                        "pocket_tarea_abierta",
                        "",
                    )
                    == tarea_id
                )

            if detalle_abierto:
                st.divider()

                descripcion = str(
                    row.get("descripcion", "") or ""
                )

                if descripcion:
                    with st.expander("Descripción", expanded=False):
                        st.write(descripcion)

                checklist_items = parsear_checklist(
                    row.get("checklist", "")
                )

                checklist_actualizado = []

                if checklist_items:
                    st.markdown("**Checklist**")

                    for indice, item in enumerate(
                        checklist_items
                    ):
                        marcado = st.checkbox(
                            str(
                                item.get(
                                    "texto",
                                    "",
                                )
                            ),
                            value=bool(
                                item.get(
                                    "hecho",
                                    False,
                                )
                            ),
                            key=(
                                f"pocket_check_"
                                f"{tarea_id}_{indice}"
                            ),
                        )

                        checklist_actualizado.append({
                            "texto": str(
                                item.get(
                                    "texto",
                                    "",
                                )
                            ),
                            "hecho": marcado,
                        })
                else:
                    checklist_actualizado = []
                    st.caption("Sin checklist cargado.")

                mensaje_item_pocket = st.session_state.pop(
                    "pocket_mensaje_item",
                    "",
                )
                error_item_pocket = st.session_state.pop(
                    "pocket_error_item",
                    "",
                )
                if mensaje_item_pocket:
                    st.success(mensaje_item_pocket)
                if error_item_pocket:
                    st.error(error_item_pocket)

                clave_mostrar_item = f"pocket_mostrar_item_{tarea_id}"
                clave_item = f"pocket_nuevo_item_{tarea_id}"
                if st.session_state.get(clave_mostrar_item, False):
                    def guardar_item_pocket(
                        tarea_id_actual=tarea_id,
                        clave_item_actual=clave_item,
                        clave_mostrar_actual=clave_mostrar_item,
                    ):
                        try:
                            agregar_item_checklist_pocket(
                                tarea_id_actual,
                                st.session_state.get(clave_item_actual, ""),
                            )
                            st.session_state[clave_item_actual] = ""
                            st.session_state[clave_mostrar_actual] = False
                            st.session_state[
                                "pocket_mensaje_item"
                            ] = "Ítem agregado."
                        except Exception as exc:
                            st.session_state[
                                "pocket_error_item"
                            ] = str(exc)

                    st.text_input(
                        "Nuevo ítem",
                        placeholder="Escribí y presioná Enter",
                        key=clave_item,
                        on_change=guardar_item_pocket,
                        label_visibility="collapsed",
                    )
                elif st.button(
                    "+ Agregar ítem",
                    key=f"pocket_abrir_item_{tarea_id}",
                    use_container_width=True,
                ):
                    st.session_state[clave_mostrar_item] = True
                    st.rerun()

                responsables_tarjeta_mapa = (
                    mapa_responsables_equipo()
                )

                if (
                    responsable
                    and responsable
                    not in responsables_tarjeta_mapa
                ):
                    responsables_tarjeta_mapa[
                        responsable
                    ] = responsable

                responsables_opciones = list(
                    responsables_tarjeta_mapa.keys()
                )

                responsable_actual = (
                    responsable
                    if responsable
                    in responsables_opciones
                    else "Sin asignar"
                )

                responsable_editado = st.selectbox(
                    "Responsable",
                    responsables_opciones,
                    index=responsables_opciones.index(
                        responsable_actual
                    ),
                    format_func=lambda valor: (
                        responsables_tarjeta_mapa.get(
                            valor,
                            valor,
                        )
                    ),
                    key=(
                        f"pocket_responsable_"
                        f"{tarea_id}"
                    ),
                )

                unidades_tarjeta = list(unidades_disponibles)
                if unidad not in unidades_tarjeta:
                    unidades_tarjeta.append(unidad)

                opcion_nueva_unidad = "Agregar nueva unidad"
                unidades_tarjeta.append(opcion_nueva_unidad)

                unidad_seleccionada = st.selectbox(
                    "Unidad",
                    unidades_tarjeta,
                    index=unidades_tarjeta.index(unidad),
                    key=f"pocket_unidad_{tarea_id}",
                )

                if unidad_seleccionada == opcion_nueva_unidad:
                    unidad_editada = st.text_input(
                        "Nombre de la nueva unidad",
                        key=f"pocket_nueva_unidad_{tarea_id}",
                    ).strip()
                else:
                    unidad_editada = unidad_seleccionada

                proyectos_tarjeta = list(proyectos_disponibles)
                if proyecto and proyecto not in proyectos_tarjeta:
                    proyectos_tarjeta.append(proyecto)
                opcion_nuevo_proyecto = "Agregar nuevo proyecto"
                proyectos_tarjeta.append(opcion_nuevo_proyecto)

                proyecto_seleccionado = st.selectbox(
                    "Proyecto",
                    proyectos_tarjeta,
                    index=(
                        proyectos_tarjeta.index(proyecto)
                        if proyecto in proyectos_tarjeta
                        else 0
                    ),
                    key=f"pocket_proyecto_{tarea_id}",
                )
                if proyecto_seleccionado == opcion_nuevo_proyecto:
                    proyecto_editado = st.text_input(
                        "Nombre del nuevo proyecto",
                        key=f"pocket_nuevo_proyecto_{tarea_id}",
                    ).strip()
                else:
                    proyecto_editado = proyecto_seleccionado

                prioridad_editada = st.selectbox(
                    "Prioridad",
                    [
                        "Alta",
                        "Media",
                        "Baja",
                    ],
                    index=(
                        [
                            "Alta",
                            "Media",
                            "Baja",
                        ].index(prioridad)
                        if prioridad in [
                            "Alta",
                            "Media",
                            "Baja",
                        ]
                        else 1
                    ),
                    key=(
                        f"pocket_prioridad_"
                        f"{tarea_id}"
                    ),
                )

                fecha_actual = pd.to_datetime(
                    row.get("fecha_limite", ""),
                    errors="coerce",
                )

                fecha_editada = st.date_input(
                    "Fecha límite",
                    value=(
                        fecha_actual.date()
                        if not pd.isna(
                            fecha_actual
                        )
                        else date.today()
                    ),
                    key=(
                        f"pocket_fecha_"
                        f"{tarea_id}"
                    ),
                )

                if unidad_editada == "AM Consultora":
                    cliente_editado = st.text_input(
                        "Cliente",
                        value=cliente,
                        key=(
                            f"pocket_cliente_"
                            f"{tarea_id}"
                        ),
                    )
                else:
                    cliente_editado = ""
                    st.caption(
                        "Esta unidad no requiere un cliente asociado."
                    )

                historial = str(
                    row.get("comentarios", "") or ""
                )

                cantidad_actualizaciones = len([
                    linea
                    for linea in historial.splitlines()
                    if linea.strip()
                ])
                titulo_actualizaciones = "📝 Actualizaciones"
                if cantidad_actualizaciones:
                    titulo_actualizaciones += f" ({cantidad_actualizaciones})"

                with st.expander(
                    titulo_actualizaciones,
                    expanded=False,
                ):
                    if historial:
                        st.caption("Más recientes primero")
                        for actualizacion in reversed([
                            linea.strip()
                            for linea in historial.splitlines()
                            if linea.strip()
                        ]):
                            st.markdown(f"- {actualizacion}")
                        st.divider()
                    comentario_nuevo = st.text_area(
                        "Nueva actualización",
                        placeholder="Escribir actualización...",
                        height=70,
                        key=f"pocket_comentario_{tarea_id}",
                    )

                if not archivos_habilitados:
                    if st.button(
                        "📎 Habilitar archivos",
                        key=f"pocket_habilitar_archivos_{tarea_id}",
                        use_container_width=True,
                    ):
                        configurar_archivos_pocket(tarea_id, True)
                        st.rerun()
                else:
                    with st.expander("📎 Archivos adjuntos", expanded=False):
                        if st.button(
                            "Ocultar sección de archivos",
                            key=f"pocket_ocultar_archivos_{tarea_id}",
                            use_container_width=True,
                            help="Oculta la sección sin borrar los archivos.",
                        ):
                            configurar_archivos_pocket(tarea_id, False)
                            st.rerun()

                        archivos_nuevos = st.file_uploader(
                            "Agregar archivos",
                            accept_multiple_files=True,
                            key=f"pocket_adjuntos_{tarea_id}",
                        )
                        if st.button(
                            "Subir archivos",
                            key=f"pocket_subir_adjuntos_{tarea_id}",
                            use_container_width=True,
                            disabled=not archivos_nuevos,
                        ):
                            try:
                                cantidad = guardar_adjuntos_pocket(
                                    tarea_id,
                                    archivos_nuevos,
                                )
                                st.success(f"{cantidad} archivo(s) cargado(s).")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))

                        adjuntos = cargar_adjuntos_pocket(tarea_id)
                        if adjuntos.empty:
                            st.caption("Todavía no hay archivos adjuntos.")
                        else:
                            for _, adjunto in adjuntos.iterrows():
                                archivo_id = str(adjunto.get("id", ""))
                                nombre_archivo = str(
                                    adjunto.get("nombre", "archivo")
                                )
                                preparar_key = (
                                    f"pocket_adjunto_preparado_{tarea_id}"
                                )
                                if st.button(
                                    f"Preparar · {nombre_archivo}",
                                    key=f"pocket_preparar_{archivo_id}",
                                    use_container_width=True,
                                ):
                                    st.session_state[preparar_key] = archivo_id

                                if (
                                    st.session_state.get(preparar_key)
                                    == archivo_id
                                ):
                                    archivo = cargar_archivo_pocket(
                                        archivo_id,
                                        tarea_id,
                                    )
                                    st.download_button(
                                        f"Descargar · {nombre_archivo}",
                                        data=base64.b64decode(
                                            str(
                                                archivo.get(
                                                    "contenido_base64",
                                                    "",
                                                )
                                            )
                                        ),
                                        file_name=str(
                                            archivo.get(
                                                "nombre",
                                                nombre_archivo,
                                            )
                                        ),
                                        mime=str(
                                            archivo.get(
                                                "tipo",
                                                "application/octet-stream",
                                            )
                                        ),
                                        key=f"pocket_descargar_{archivo_id}",
                                        use_container_width=True,
                                    )

                if st.button(
                    "Guardar cambios",
                    type="primary",
                    use_container_width=True,
                    key=(
                        f"pocket_guardar_"
                        f"{tarea_id}"
                    ),
                ):
                    if not unidad_editada.strip():
                        st.error("Ingresá el nombre de la unidad.")
                        st.stop()

                    if not proyecto_editado.strip():
                        st.error("Ingresá el nombre del proyecto.")
                        st.stop()

                    actualizar_detalle_tarea(
                        tarea_id=tarea_id,
                        unidad=unidad_editada,
                        proyecto=proyecto_editado,
                        estado=nuevo_estado,
                        responsable=responsable_editado,
                        prioridad=prioridad_editada,
                        fecha_limite=(
                            fecha_editada.strftime(
                                "%Y-%m-%d"
                            )
                        ),
                        cliente=cliente_editado.strip(),
                        checklist=checklist_actualizado,
                        comentario=comentario_nuevo,
                    )

                    st.session_state[
                        "pocket_tarea_abierta"
                    ] = ""

                    st.success(
                        "Tarea actualizada."
                    )
                    st.rerun()

                st.divider()
                confirmar_eliminacion = st.checkbox(
                    "Confirmo eliminar esta tarjeta",
                    key=(
                        f"pocket_confirmar_eliminar_"
                        f"{tarea_id}"
                    ),
                )

                if st.button(
                    "Eliminar tarea",
                    key=(
                        f"pocket_eliminar_"
                        f"{tarea_id}"
                    ),
                    use_container_width=True,
                    disabled=(
                        not confirmar_eliminacion
                    ),
                ):
                    if eliminar_tarea(tarea_id):
                        st.session_state[
                            "pocket_tarea_abierta"
                        ] = ""
                        st.success(
                            "Tarea eliminada."
                        )
                        st.rerun()
                    else:
                        st.error(
                            "No se encontró la tarea."
                        )


if pagina_pocket == "🤝 Plan de trabajo":
    st.markdown("### " + pocket_ui("Plan de trabajo"))
    st.caption(
        "Seguimiento de frentes y compromisos con clientes."
    )

    plan = cargar_plan_trabajo()

    if plan.empty:
        st.info("No hay frentes de trabajo cargados.")
        st.stop()

    for columna, valor_default in {
        "cliente": "",
        "objetivo": "",
        "descripcion": "",
        "responsable_am": "",
        "responsable_cliente": "",
        "responsable_tipo": "AM Consultora",
        "prioridad": "Media",
        "estado": "Pendiente",
        "avance": 0,
        "checklist": "",
        "fecha_limite": "",
        "comentarios": "",
        "mes": "",
    }.items():
        if columna not in plan.columns:
            plan[columna] = valor_default

    plan["estado"] = (
        plan["estado"].astype(str).str.strip().replace("", "Pendiente")
    )
    plan["prioridad"] = (
        plan["prioridad"].astype(str).str.strip().replace("", "Media")
    )

    clientes_plan = sorted(
        valor for valor in plan["cliente"].astype(str).str.strip().unique()
        if valor
    )
    estados_plan = [
        "Pendiente", "En curso", "En revisión", "Pausado", "Finalizado"
    ]
    prioridades_plan = ["Alta", "Media", "Baja"]

    with st.expander("🔎 " + pocket_ui("Filtros"), expanded=False):
        buscar_plan = st.text_input(
            "Buscar",
            placeholder="Frente, cliente o responsable...",
            key="pocket_plan_buscar",
        )
        clientes_plan_filtro = st.multiselect(
            "Cliente",
            clientes_plan,
            key="pocket_plan_clientes",
        )
        estados_plan_filtro = st.multiselect(
            "Estado",
            estados_plan,
            default=["Pendiente", "En curso", "En revisión", "Pausado"],
            key="pocket_plan_estados",
        )
        prioridades_plan_filtro = st.multiselect(
            "Prioridad",
            prioridades_plan,
            key="pocket_plan_prioridades",
        )

    plan_vista = plan.copy()

    if clientes_plan_filtro:
        plan_vista = plan_vista[
            plan_vista["cliente"].astype(str).isin(clientes_plan_filtro)
        ].copy()

    # Una selección vacía también representa la vista normal: no muestra
    # finalizados hasta que el usuario los elige expresamente.
    if estados_plan_filtro:
        plan_vista = plan_vista[
            plan_vista["estado"].astype(str).isin(estados_plan_filtro)
        ].copy()
    else:
        plan_vista = plan_vista[
            plan_vista["estado"].astype(str).ne("Finalizado")
        ].copy()

    if prioridades_plan_filtro:
        plan_vista = plan_vista[
            plan_vista["prioridad"].astype(str).isin(prioridades_plan_filtro)
        ].copy()

    if str(buscar_plan or "").strip():
        palabras = [
            palabra.casefold()
            for palabra in str(buscar_plan).split()
            if palabra.strip()
        ]
        texto_plan = pd.Series("", index=plan_vista.index, dtype="object")
        for columna in [
            "objetivo", "descripcion", "cliente", "responsable_am",
            "responsable_cliente", "comentarios", "mes",
        ]:
            texto_plan = (
                texto_plan + " "
                + plan_vista[columna].fillna("").astype(str).str.casefold()
            )
        mascara_plan = pd.Series(True, index=plan_vista.index)
        for palabra in palabras:
            mascara_plan &= texto_plan.str.contains(
                palabra, regex=False, na=False
            )
        plan_vista = plan_vista[mascara_plan].copy()

    total_plan = len(plan_vista)
    en_marcha = int(
        plan_vista["estado"].isin(["En curso", "En revisión"]).sum()
    )
    fechas_plan = pd.to_datetime(
        plan_vista["fecha_limite"].replace("", pd.NA), errors="coerce"
    )
    vencidos_plan = int(
        (
            fechas_plan.notna()
            & (fechas_plan < pd.Timestamp(date.today()))
            & plan_vista["estado"].ne("Finalizado")
        ).sum()
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Visibles", total_plan)
    m2.metric("En marcha", en_marcha)
    m3.metric("Vencidos", vencidos_plan)

    if plan_vista.empty:
        st.info("No hay frentes para los filtros seleccionados.")
        st.stop()

    clientes_edicion_plan = sorted(
        set(clientes_plan + cargar_clientes_pocket()) - {""}
    )

    for _, frente in plan_vista.iterrows():
        frente_id = str(frente.get("id", ""))
        titulo = str(frente.get("objetivo", "") or "Frente sin título").strip()
        cliente_frente = str(frente.get("cliente", "") or "Sin cliente").strip()
        estado_frente = str(frente.get("estado", "Pendiente"))
        prioridad_frente = str(frente.get("prioridad", "Media"))
        responsable_tipo_frente = str(
            frente.get("responsable_tipo", "AM Consultora")
            or "AM Consultora"
        ).strip()
        if responsable_tipo_frente not in ["AM Consultora", "Cliente"]:
            responsable_tipo_frente = "AM Consultora"
        avance_numero = pd.to_numeric(
            frente.get("avance", 0), errors="coerce"
        )
        avance_frente = 0 if pd.isna(avance_numero) else int(avance_numero)
        avance_frente = max(0, min(100, avance_frente))

        with st.container(border=True):
            etiqueta_frente = (
                cliente_frente
                if responsable_tipo_frente == "Cliente"
                else "AM Consultora"
            )
            color_frente = (
                "#15803D"
                if responsable_tipo_frente == "Cliente"
                else "#1D4ED8"
            )
            st.markdown(
                '<div style="display:flex;align-items:center;gap:8px;'
                'flex-wrap:wrap">'
                f'<strong>{html.escape(titulo)}</strong>'
                '<span style="padding:2px 8px;border-radius:999px;'
                f'background:{color_frente};color:white;font-size:0.72rem;'
                f'font-weight:700">{html.escape(etiqueta_frente)}</span></div>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"{cliente_frente} · {estado_frente} · "
                f"{texto_prioridad(prioridad_frente)} · "
                f"{texto_fecha(frente.get('fecha_limite', ''))}"
            )
            st.progress(avance_frente, text=f"{avance_frente}%")

            with st.expander("Ver y editar", expanded=False):
                descripcion_frente = str(frente.get("descripcion", "")).strip()
                if descripcion_frente:
                    st.markdown(descripcion_frente)

                responsable_am = str(frente.get("responsable_am", "")).strip()
                responsable_cliente = str(
                    frente.get("responsable_cliente", "")
                ).strip()
                if responsable_am:
                    st.caption(f"Responsable AM: {responsable_am}")
                if responsable_cliente:
                    st.caption(f"Responsable cliente: {responsable_cliente}")

                checklist_frente = parsear_checklist(
                    frente.get("checklist", "")
                )
                if checklist_frente:
                    st.markdown("**Checklist**")
                    for item in checklist_frente:
                        marca = "✅" if item.get("hecho", False) else "⬜"
                        st.write(f"{marca} {item.get('texto', '')}")

                comentarios_frente = str(frente.get("comentarios", "")).strip()
                if comentarios_frente:
                    st.markdown("**Actualizaciones**")
                    for comentario in comentarios_frente.splitlines():
                        if comentario.strip():
                            st.caption(comentario.strip())

                with st.form(f"pocket_plan_form_{frente_id}"):
                    objetivo_editado = st.text_input(
                        "Frente de trabajo",
                        value=titulo,
                        key=f"pocket_plan_objetivo_{frente_id}",
                    )
                    descripcion_editada = st.text_area(
                        "Descripción",
                        value=descripcion_frente,
                        key=f"pocket_plan_descripcion_{frente_id}",
                    )

                    indice_cliente = (
                        clientes_edicion_plan.index(cliente_frente)
                        if cliente_frente in clientes_edicion_plan else 0
                    )
                    cliente_editado = st.selectbox(
                        "Cliente",
                        clientes_edicion_plan,
                        index=indice_cliente,
                        key=f"pocket_plan_cliente_{frente_id}",
                    )
                    mes_editado = st.text_input(
                        "Mes",
                        value=str(frente.get("mes", "")).strip(),
                        placeholder="AAAA-MM",
                        key=f"pocket_plan_mes_{frente_id}",
                    )

                    e1, e2 = st.columns(2)
                    with e1:
                        estado_actual = (
                            estado_frente if estado_frente in estados_plan
                            else "Pendiente"
                        )
                        estado_editado = st.selectbox(
                            "Estado",
                            estados_plan,
                            index=estados_plan.index(estado_actual),
                            key=f"pocket_plan_estado_{frente_id}",
                        )
                    with e2:
                        prioridad_actual = (
                            prioridad_frente if prioridad_frente in prioridades_plan
                            else "Media"
                        )
                        prioridad_editada = st.selectbox(
                            "Prioridad",
                            prioridades_plan,
                            index=prioridades_plan.index(prioridad_actual),
                            key=f"pocket_plan_prioridad_{frente_id}",
                        )

                    responsable_am_editado = st.text_input(
                        "Responsable AM",
                        value=responsable_am,
                        key=f"pocket_plan_resp_am_{frente_id}",
                    )
                    responsable_cliente_editado = st.text_input(
                        "Responsable cliente",
                        value=responsable_cliente,
                        key=f"pocket_plan_resp_cliente_{frente_id}",
                    )
                    responsable_tipo_editado = st.selectbox(
                        "Responsabilidad principal",
                        ["AM Consultora", "Cliente"],
                        index=(
                            1 if responsable_tipo_frente == "Cliente" else 0
                        ),
                        key=f"pocket_plan_resp_tipo_{frente_id}",
                    )

                    fecha_actual_plan = pd.to_datetime(
                        frente.get("fecha_limite", ""), errors="coerce"
                    )
                    sin_fecha_plan = st.checkbox(
                        "Sin fecha de vencimiento",
                        value=pd.isna(fecha_actual_plan),
                        key=f"pocket_plan_sin_fecha_{frente_id}",
                    )
                    fecha_editada_plan = st.date_input(
                        "Fecha de vencimiento",
                        value=(
                            date.today() if pd.isna(fecha_actual_plan)
                            else fecha_actual_plan.date()
                        ),
                        disabled=sin_fecha_plan,
                        key=f"pocket_plan_fecha_{frente_id}",
                    )

                    st.markdown("**Checklist**")
                    checklist_editado = []
                    for indice_item, item in enumerate(checklist_frente):
                        texto_item_editado = st.text_input(
                            f"Ítem {indice_item + 1}",
                            value=str(item.get("texto", "")),
                            key=(
                                f"pocket_plan_item_texto_{frente_id}_"
                                f"{indice_item}"
                            ),
                        )
                        ci1, ci2 = st.columns(2)
                        with ci1:
                            hecho_item = st.checkbox(
                                "Completado",
                                value=bool(item.get("hecho", False)),
                                key=(
                                    f"pocket_plan_item_hecho_{frente_id}_"
                                    f"{indice_item}"
                                ),
                            )
                        with ci2:
                            eliminar_item = st.checkbox(
                                "Eliminar",
                                value=False,
                                key=(
                                    f"pocket_plan_item_borrar_{frente_id}_"
                                    f"{indice_item}"
                                ),
                            )
                        if texto_item_editado.strip() and not eliminar_item:
                            checklist_editado.append({
                                "texto": texto_item_editado.strip(),
                                "hecho": hecho_item,
                            })

                    nuevo_item_plan = st.text_input(
                        "+ Agregar ítem",
                        placeholder="Nuevo paso...",
                        key=f"pocket_plan_item_nuevo_{frente_id}",
                    )
                    nueva_actualizacion = st.text_area(
                        "Nueva actualización",
                        placeholder="Escribí el avance o comentario...",
                        key=f"pocket_plan_comentario_{frente_id}",
                    )
                    guardar_frente = st.form_submit_button(
                        "Guardar cambios",
                        type="primary",
                        use_container_width=True,
                    )

                if guardar_frente:
                    if not objetivo_editado.strip():
                        st.error("El frente de trabajo no puede estar vacío.")
                    else:
                        if nuevo_item_plan.strip():
                            checklist_editado.append({
                                "texto": nuevo_item_plan.strip(),
                                "hecho": False,
                            })
                        actualizar_frente_pocket(
                            frente_id=frente_id,
                            cliente=cliente_editado,
                            mes=mes_editado,
                            objetivo=objetivo_editado,
                            descripcion=descripcion_editada,
                            responsable_am=responsable_am_editado,
                            responsable_cliente=responsable_cliente_editado,
                            responsable_tipo=responsable_tipo_editado,
                            prioridad=prioridad_editada,
                            estado=estado_editado,
                            fecha_limite=(
                                "" if sin_fecha_plan
                                else fecha_editada_plan.strftime("%Y-%m-%d")
                            ),
                            checklist=checklist_editado,
                            comentario=nueva_actualizacion,
                        )
                        st.success("Frente actualizado.")
                        st.rerun()

                render_archivos_frente_pocket(frente_id)

                st.divider()
                confirmar_borrado_frente = st.checkbox(
                    "Confirmo eliminar este frente",
                    key=f"pocket_plan_confirmar_borrar_{frente_id}",
                )
                if st.button(
                    "Eliminar frente",
                    disabled=not confirmar_borrado_frente,
                    use_container_width=True,
                    key=f"pocket_plan_borrar_{frente_id}",
                ):
                    if eliminar_frente_pocket(frente_id):
                        st.success("Frente eliminado.")
                        st.rerun()
                    else:
                        st.error("No se encontró el frente.")


if pagina_pocket == "💳 Cuenta corriente":
    st.markdown("### Cuenta corriente")
    st.caption("Pagos, deuda y movimientos por cliente.")

    cuenta_pocket = cargar_cuenta_corriente_pocket()
    clientes_base = cargar_clientes_pocket()
    clientes_con_cuenta = (
        cuenta_pocket.get("cliente", pd.Series(dtype="object"))
        .fillna("").astype(str).str.strip().tolist()
    )
    clientes_cuenta = sorted(set(clientes_base + clientes_con_cuenta) - {""})

    if not clientes_cuenta:
        st.info("No hay clientes cargados.")
        st.stop()

    cliente_cuenta = st.selectbox(
        "Cliente",
        clientes_cuenta,
        key="pocket_cc_cliente",
    )

    detalle_cuenta = cuenta_pocket[
        cuenta_pocket["cliente"].astype(str).eq(cliente_cuenta)
    ].copy()
    detalle_cuenta["importe"] = pd.to_numeric(
        detalle_cuenta.get("importe", 0), errors="coerce"
    ).fillna(0)

    def pesos_pocket(valor):
        return f"$ {float(valor):,.0f}".replace(",", ".")

    estados_sin_deuda = ["Pagado", "Bonificado"]
    total_cuenta = float(detalle_cuenta["importe"].sum())
    cobrado_cuenta = float(
        detalle_cuenta.loc[
            detalle_cuenta["estado"].astype(str).eq("Pagado"), "importe"
        ].sum()
    )
    deuda_cuenta = float(
        detalle_cuenta.loc[
            ~detalle_cuenta["estado"].astype(str).isin(estados_sin_deuda),
            "importe",
        ].sum()
    )

    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Total", pesos_pocket(total_cuenta))
    cc2.metric("Cobrado", pesos_pocket(cobrado_cuenta))
    cc3.metric("Deuda", pesos_pocket(deuda_cuenta))

    with st.expander("➕ Cargar movimiento", expanded=False):
        tab_deuda, tab_pago = st.tabs(["Nueva deuda", "Registrar pago"])

        with tab_deuda:
            with st.form("pocket_cc_nueva_deuda", clear_on_submit=True):
                fecha_mes_deuda = st.date_input(
                    "Período",
                    value=date.today(),
                    key="pocket_cc_mes_deuda",
                )
                concepto_deuda = st.text_input(
                    "Concepto",
                    value="Honorarios mensuales",
                    key="pocket_cc_concepto_deuda",
                )
                servicio_deuda = st.selectbox(
                    "Servicio",
                    [
                        "General", "Ecosistema digital", "Consultoría",
                        "Contabilidad / Gestión",
                    ],
                    key="pocket_cc_servicio_deuda",
                )
                importe_deuda = st.number_input(
                    "Importe",
                    min_value=0.0,
                    step=10000.0,
                    key="pocket_cc_importe_deuda",
                )
                estado_deuda = st.selectbox(
                    "Estado",
                    [
                        "Pendiente de facturar", "Facturado", "No pagado",
                        "Vencido",
                    ],
                    key="pocket_cc_estado_deuda",
                )
                fecha_factura_deuda = st.date_input(
                    "Fecha de emisión",
                    value=date.today(),
                    key="pocket_cc_fecha_deuda",
                )
                observacion_deuda = st.text_area(
                    "Observación",
                    key="pocket_cc_obs_deuda",
                )
                crear_deuda = st.form_submit_button(
                    "Guardar deuda",
                    type="primary",
                    use_container_width=True,
                )

            if crear_deuda:
                if importe_deuda <= 0:
                    st.error("El importe debe ser mayor a cero.")
                else:
                    guardar_deuda_pocket(
                        cliente=cliente_cuenta,
                        mes=fecha_mes_deuda.strftime("%Y-%m"),
                        concepto=concepto_deuda,
                        servicio=servicio_deuda,
                        importe=importe_deuda,
                        estado=estado_deuda,
                        fecha_factura=fecha_factura_deuda,
                        observacion=observacion_deuda,
                    )
                    st.success("Deuda cargada.")
                    st.rerun()

        with tab_pago:
            pendientes_pago = detalle_cuenta[
                ~detalle_cuenta["estado"].astype(str).isin(estados_sin_deuda)
            ].copy()

            if pendientes_pago.empty:
                st.info("Este cliente no tiene deudas pendientes.")
            else:
                opciones_pago = {}
                for _, movimiento in pendientes_pago.iterrows():
                    etiqueta_pago = (
                        f"{movimiento.get('mes', '')} · "
                        f"{movimiento.get('concepto', '')} · "
                        f"{pesos_pocket(movimiento.get('importe', 0))}"
                    )
                    # El id evita perder movimientos con etiquetas iguales.
                    opciones_pago[
                        f"{etiqueta_pago} · {movimiento.get('id', '')}"
                    ] = str(movimiento.get("id", ""))

                with st.form("pocket_cc_registrar_pago", clear_on_submit=True):
                    pago_seleccionado = st.selectbox(
                        "Deuda a cancelar",
                        list(opciones_pago.keys()),
                        key="pocket_cc_pago_movimiento",
                    )
                    fecha_pago_pocket = st.date_input(
                        "Fecha del pago",
                        value=date.today(),
                        key="pocket_cc_fecha_pago",
                    )
                    observacion_pago_pocket = st.text_area(
                        "Observación",
                        placeholder="Transferencia, banco o referencia...",
                        key="pocket_cc_obs_pago",
                    )
                    guardar_pago = st.form_submit_button(
                        "Registrar pago",
                        type="primary",
                        use_container_width=True,
                    )

                if guardar_pago:
                    movimiento_id = opciones_pago.get(pago_seleccionado, "")
                    if registrar_pago_pocket(
                        movimiento_id,
                        fecha_pago_pocket,
                        observacion_pago_pocket,
                    ):
                        st.success("Pago registrado.")
                        st.rerun()
                    else:
                        st.error("No se encontró el movimiento.")

    st.markdown("#### Detalle")

    if detalle_cuenta.empty:
        st.info("Este cliente todavía no tiene movimientos.")
    else:
        estados_detalle = sorted(
            valor for valor in detalle_cuenta["estado"].astype(str).unique()
            if valor
        )
        filtro_estado_cuenta = st.multiselect(
            "Filtrar estado",
            estados_detalle,
            key="pocket_cc_filtro_estado",
        )
        if filtro_estado_cuenta:
            detalle_cuenta = detalle_cuenta[
                detalle_cuenta["estado"].astype(str).isin(filtro_estado_cuenta)
            ].copy()

        for _, movimiento in detalle_cuenta.iterrows():
            with st.container(border=True):
                st.markdown(
                    f"**{movimiento.get('concepto', '') or 'Movimiento'}**"
                )
                st.caption(
                    f"{movimiento.get('mes', '')} · "
                    f"{movimiento.get('estado', '')} · "
                    f"{movimiento.get('servicio', '') or 'General'}"
                )
                st.markdown(f"### {pesos_pocket(movimiento.get('importe', 0))}")
                fecha_pago_mov = str(movimiento.get("fecha_pago", "")).strip()
                if fecha_pago_mov:
                    st.caption(f"Pagado: {fecha_pago_mov}")
                observacion_mov = str(movimiento.get("observacion", "")).strip()
                if observacion_mov:
                    with st.expander("Ver observación"):
                        st.write(observacion_mov)
