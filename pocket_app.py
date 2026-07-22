import hmac
import os
import secrets
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


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
]

COLORES_UNIDAD = {
    "AM Consultora": "🟦",
    "Comunidad": "🟩",
    "BRC Trading": "🟧",
}


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
        FROM tareas
        ORDER BY
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


def actualizar_detalle_tarea(
    tarea_id,
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


def texto_fecha(valor: str) -> str:
    fecha = pd.to_datetime(
        str(valor or "").strip(),
        errors="coerce",
    )

    if pd.isna(fecha):
        return "Sin fecha"

    hoy = date.today()
    fecha_tarea = fecha.date()
    texto = fecha.strftime("%d/%m")

    if fecha_tarea < hoy:
        return f"🔴 Vencida · {texto}"

    if fecha_tarea == hoy:
        return f"🟠 Hoy · {texto}"

    return f"📅 {texto}"


def texto_prioridad(valor: str) -> str:
    mapa = {
        "Alta": "🔴 Alta",
        "Media": "🟡 Media",
        "Baja": "🟢 Baja",
    }

    return mapa.get(
        str(valor or "Media"),
        "🟡 Media",
    )


if not acceso_autorizado():
    st.stop()


asegurar_columnas()

st.markdown(
    '<p class="pocket-title">AM Pocket</p>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="pocket-subtitle">'
    "Capturá y administrá pendientes desde el celular."
    "</p>",
    unsafe_allow_html=True,
)

pagina_pocket = st.radio(
    "Vista",
    [
        "📥 Capturar",
        "📋 Mi tablero",
    ],
    horizontal=True,
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
            "¿Qué tenés pendiente?",
            placeholder="Escribí o dictá un pendiente...",
            height=145,
            key="pocket_captura_confirmada",
        )

        una_por_linea = st.checkbox(
            "Crear una tarjeta por línea",
            value=False,
            key="pocket_una_por_linea_confirmada",
        )

        crear_tarea = st.form_submit_button(
            "Crear tarea",
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
        st.info("Todavía no hay tareas.")
        st.stop()

    unidades_disponibles = sorted(
        tareas["unidad"]
        .replace("", "AM Consultora")
        .astype(str)
        .str.strip()
        .replace("", "AM Consultora")
        .unique()
        .tolist()
    )

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
        "🔎 Filtros",
        expanded=True,
    ):
        f1, f2 = st.columns(2)

        with f1:
            estados_filtro = st.multiselect(
                "Estado",
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
                key="pocket_filtro_estado_multi",
            )

        with f2:
            unidades_filtro = st.multiselect(
                "Unidad",
                unidades_disponibles,
                default=[],
                key="pocket_filtro_unidad_multi",
            )

        f3, f4 = st.columns(2)

        with f3:
            clientes_filtro = st.multiselect(
                "Cliente",
                ["Sin cliente"]
                + clientes_disponibles,
                default=[],
                key="pocket_filtro_cliente_multi",
            )

        with f4:
            responsables_filtro = st.multiselect(
                "Responsable",
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
                "Prioridad",
                prioridades_disponibles,
                default=[],
                key="pocket_filtro_prioridad_multi",
            )

        with f6:
            categorias_filtro = st.multiselect(
                "Categoría",
                ["Sin categoría"]
                + categorias_disponibles,
                default=[],
                key="pocket_filtro_categoria_multi",
            )

        fechas_filtro = st.multiselect(
            "Fecha de vencimiento",
            [
                "Vencidas",
                "Vencen hoy",
                "Próximos 7 días",
                "Con fecha",
                "Sin fecha",
            ],
            default=[],
            key="pocket_filtro_fecha_multi",
        )

    vista = tareas.copy()

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
                    st.caption(
                        "Sin checklist cargado."
                    )

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

                cliente_editado = st.text_input(
                    "Cliente",
                    value=cliente,
                    key=(
                        f"pocket_cliente_"
                        f"{tarea_id}"
                    ),
                )

                comentario_nuevo = st.text_area(
                    "Comentario",
                    placeholder=(
                        "Agregar actualización..."
                    ),
                    height=80,
                    key=(
                        f"pocket_comentario_"
                        f"{tarea_id}"
                    ),
                )

                historial = str(
                    row.get("comentarios", "") or ""
                )

                if historial:
                    with st.expander(
                        "Historial"
                    ):
                        st.write(historial)

                if st.button(
                    "Guardar cambios",
                    type="primary",
                    use_container_width=True,
                    key=(
                        f"pocket_guardar_"
                        f"{tarea_id}"
                    ),
                ):
                    actualizar_detalle_tarea(
                        tarea_id=tarea_id,
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
