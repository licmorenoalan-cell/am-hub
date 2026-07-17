from pathlib import Path
import os
import time
import base64
from PIL import Image
from datetime import date
import pandas as pd
import altair as alt
import streamlit as st
from sqlalchemy import create_engine, text as sql_text

# ============================================================
# Configuración general
# ============================================================

st.set_page_config(
    page_title="AM Hub | Portal de gestión digital",
    page_icon="AM",
    layout="wide",
)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"

CLIENTES_PATH = DATA_DIR / "clientes.csv"
CONTENIDOS_PATH = DATA_DIR / "contenidos.csv"
MATERIALES_PATH = DATA_DIR / "materiales.csv"
CAMPANIAS_PATH = DATA_DIR / "campanias.csv"
REPORTES_PATH = DATA_DIR / "reportes.csv"
TAREAS_PATH = DATA_DIR / "tareas.csv"
USUARIOS_PATH = DATA_DIR / "usuarios.csv"
ASIGNACIONES_EQUIPO_PATH = DATA_DIR / "asignaciones_equipo.csv"
OBJETIVOS_PATH = DATA_DIR / "objetivos.csv"
DOCUMENTOS_PATH = DATA_DIR / "documentos.csv"
INDICADORES_PATH = DATA_DIR / "indicadores.csv"
INDICADORES_MOVIMIENTOS_PATH = DATA_DIR / "indicadores_movimientos.csv"
CUENTA_CORRIENTE_PATH = DATA_DIR / "cuenta_corriente.csv"

# ============================================================
# Base de datos opcional PostgreSQL / Supabase
# ============================================================

POSTGRES_TABLE_MAP = {
    "clientes.csv": "clientes",
    "contenidos.csv": "contenidos",
    "materiales.csv": "materiales",
    "campanias.csv": "campanias",
    "reportes.csv": "reportes",
    "tareas.csv": "tareas",
    "usuarios.csv": "usuarios",
    "asignaciones_equipo.csv": "asignaciones_equipo",
    "objetivos.csv": "objetivos",
    "documentos.csv": "documentos",
    "indicadores.csv": "indicadores",
    "indicadores_movimientos.csv": "indicadores_movimientos",
    "cuenta_corriente.csv": "cuenta_corriente",
}

POSTGRES_KEY_MAP = {
    "clientes": "cliente",
    "usuarios": "username",
    "asignaciones_equipo": "id",
    "contenidos": "id",
    "materiales": "id",
    "campanias": "id",
    "reportes": "id",
    "tareas": "id",
    "objetivos": "id",
    "documentos": "id",
    "indicadores": "id",
    "indicadores_movimientos": "id",
    "cuenta_corriente": "id",
}

POSTGRES_CORE_TABLES = [
    "clientes",
    "usuarios",
    "asignaciones_equipo",
    "contenidos",
    "materiales",
    "campanias",
    "reportes",
    "tareas",
    "objetivos",
    "indicadores_movimientos",
    "cuenta_corriente",
]

_POSTGRES_ENGINE = None


def get_database_url():
    # Primero variable de entorno: no dispara errores visuales en Streamlit.
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    # Solo intentamos leer st.secrets si existe un archivo secrets.toml.
    posibles_secrets = [
        BASE_DIR / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]

    if not any(p.exists() for p in posibles_secrets):
        return ""

    try:
        return st.secrets.get("DATABASE_URL", "")
    except Exception:
        return ""


def normalizar_database_url(database_url: str) -> str:
    if not database_url:
        return ""

    # Supabase suele entregar postgresql://...
    # Para psycopg v3 usamos explícitamente postgresql+psycopg://...
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)

    return database_url


def usar_postgres():
    return bool(get_database_url())


def get_postgres_engine():
    global _POSTGRES_ENGINE

    if _POSTGRES_ENGINE is None:
        database_url = normalizar_database_url(get_database_url())

        if not database_url:
            raise ValueError("DATABASE_URL no está configurada.")

        _POSTGRES_ENGINE = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=2,
            max_overflow=3,
            connect_args={"connect_timeout": 10},
        )

    return _POSTGRES_ENGINE


def tabla_postgres_para_path(path):
    try:
        filename = Path(path).name
    except Exception:
        filename = str(path)

    return POSTGRES_TABLE_MAP.get(filename)


def normalizar_df_para_columnas(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()

    if columns is None:
        columns = []

    for col in columns:
        if col not in df.columns:
            df[col] = ""

    if columns:
        extras = [c for c in df.columns if c not in columns]
        return df[list(columns) + extras]

    return df


@st.cache_data(ttl=600, show_spinner=False)
def leer_postgres_core_cacheada() -> dict:
    inicio_perf = perf_start()
    engine = get_postgres_engine()
    data = {}

    with engine.connect() as conn:
        for tabla in POSTGRES_CORE_TABLES:
            try:
                data[tabla] = pd.read_sql(sql_text(f'SELECT * FROM "{tabla}"'), conn).fillna("")
            except Exception:
                data[tabla] = pd.DataFrame()

    try:
        total_filas = sum(len(df) for df in data.values())
    except Exception:
        total_filas = 0

    perf_log(f"CORE postgres tablas={len(data)} filas={total_filas}", inicio_perf)
    return data


def leer_postgres_core_tabla(tabla: str, columns: list[str]) -> pd.DataFrame:
    data = leer_postgres_core_cacheada()
    df = data.get(tabla, pd.DataFrame()).copy()
    return normalizar_df_para_columnas(df, columns)



@st.cache_data(ttl=600, show_spinner=False)
def leer_postgres_cacheada(tabla: str, columns_tuple: tuple) -> pd.DataFrame:
    columns = list(columns_tuple) if columns_tuple else []

    if tabla in POSTGRES_CORE_TABLES:
        return leer_postgres_core_tabla(tabla, columns)

    engine = get_postgres_engine()

    with engine.connect() as conn:
        df = pd.read_sql(sql_text(f'SELECT * FROM "{tabla}"'), conn)

    return normalizar_df_para_columnas(df, columns)


def leer_postgres(tabla: str, columns: list[str]) -> pd.DataFrame:
    inicio_perf = perf_start()
    try:
        columns_tuple = tuple(columns) if columns is not None else tuple()
        df = leer_postgres_cacheada(tabla, columns_tuple)
        perf_log(f"leer_postgres {tabla} filas={len(df)}", inicio_perf)
        return df
    except Exception:
        perf_log(f"leer_postgres ERROR {tabla}", inicio_perf)
        return pd.DataFrame(columns=columns)


@st.cache_data(ttl=600, show_spinner=False)
def leer_postgres_cliente_cacheada(tabla: str, columns_tuple: tuple, cliente: str) -> pd.DataFrame:
    columns = list(columns_tuple) if columns_tuple else []

    if tabla in POSTGRES_CORE_TABLES:
        df = leer_postgres_core_tabla(tabla, columns)

        if df.empty or "cliente" not in df.columns:
            return pd.DataFrame(columns=columns)

        return df[df["cliente"].astype(str) == str(cliente)].copy()

    engine = get_postgres_engine()

    with engine.connect() as conn:
        df = pd.read_sql(
            sql_text(f'SELECT * FROM "{tabla}" WHERE cliente = :cliente'),
            conn,
            params={"cliente": cliente},
        )

    return normalizar_df_para_columnas(df, columns)


def leer_postgres_cliente(tabla: str, columns: list[str], cliente: str) -> pd.DataFrame:
    if not cliente:
        return leer_postgres(tabla, columns)

    inicio_perf = perf_start()
    try:
        columns_tuple = tuple(columns) if columns is not None else tuple()
        df = leer_postgres_cliente_cacheada(tabla, columns_tuple, str(cliente))
        perf_log(f"leer_postgres_cliente {tabla} cliente={cliente} filas={len(df)}", inicio_perf)
        return df
    except Exception:
        perf_log(f"leer_postgres_cliente ERROR {tabla} cliente={cliente}", inicio_perf)
        return pd.DataFrame(columns=columns)


def _sql_cols(cols):
    return ", ".join([f'"{c}"' for c in cols])


def _normalizar_valor_postgres(value):
    if pd.isna(value):
        return ""
    return str(value)


def _filas_distintas(row_nueva, row_actual, columnas):
    for col in columnas:
        nuevo = _normalizar_valor_postgres(row_nueva.get(col, ""))
        actual = _normalizar_valor_postgres(row_actual.get(col, ""))
        if nuevo != actual:
            return True
    return False


def _limpiar_cache_postgres():
    for cache_func_name in [
        "leer_postgres_core_cacheada",
        "leer_postgres_cacheada",
        "leer_postgres_cliente_cacheada",
        "leer_postgres_preview_cacheada",
        "contar_postgres_cacheada",
    ]:
        try:
            globals()[cache_func_name].clear()
        except Exception:
            pass


def guardar_postgres(df: pd.DataFrame, tabla: str):
    engine = get_postgres_engine()

    clean = df.copy().fillna("")
    clean.columns = [str(c) for c in clean.columns]

    key_col = POSTGRES_KEY_MAP.get(tabla)

    if clean.empty:
        with engine.begin() as conn:
            try:
                conn.execute(sql_text(f'DELETE FROM "{tabla}"'))
            except Exception:
                pass
        _limpiar_cache_postgres()
        return

    # Si no tenemos clave confiable, hacemos reemplazo preservando estructura/índices:
    # DELETE + append, en vez de DROP/CREATE con if_exists="replace".
    if not key_col or key_col not in clean.columns:
        with engine.begin() as conn:
            try:
                conn.execute(sql_text(f'DELETE FROM "{tabla}"'))
                clean.to_sql(tabla, conn, if_exists="append", index=False, method="multi", chunksize=500)
            except Exception:
                clean.to_sql(tabla, engine, if_exists="replace", index=False, method="multi", chunksize=500)

        _limpiar_cache_postgres()
        return

    clean[key_col] = clean[key_col].astype(str).str.strip()
    clean = clean[clean[key_col] != ""].copy()
    clean = clean.drop_duplicates(subset=[key_col], keep="last")

    columnas = list(clean.columns)

    try:
        with engine.begin() as conn:
            try:
                actual = pd.read_sql(sql_text(f'SELECT * FROM "{tabla}"'), conn).fillna("")
            except Exception:
                # Tabla inexistente: crearla una sola vez.
                clean.to_sql(tabla, conn, if_exists="replace", index=False, method="multi", chunksize=500)
                _limpiar_cache_postgres()
                return

            if actual.empty or key_col not in actual.columns:
                try:
                    conn.execute(sql_text(f'DELETE FROM "{tabla}"'))
                    clean.to_sql(tabla, conn, if_exists="append", index=False, method="multi", chunksize=500)
                except Exception:
                    clean.to_sql(tabla, conn, if_exists="replace", index=False, method="multi", chunksize=500)

                _limpiar_cache_postgres()
                return

            actual = actual.copy().fillna("")
            actual.columns = [str(c) for c in actual.columns]
            actual[key_col] = actual[key_col].astype(str).str.strip()

            # Asegurar columnas nuevas si aparecieron en la app.
            for col in columnas:
                if col not in actual.columns:
                    try:
                        conn.execute(sql_text(f'ALTER TABLE "{tabla}" ADD COLUMN "{col}" TEXT'))
                        actual[col] = ""
                    except Exception:
                        actual[col] = ""

            actual_idx = actual.drop_duplicates(subset=[key_col], keep="last").set_index(key_col, drop=False)
            claves_nuevas = set(clean[key_col].astype(str).tolist())
            claves_actuales = set(actual_idx.index.astype(str).tolist())

            # Deletes: necesario para que baja de clientes/usuarios funcione sin reescribir todo.
            claves_a_borrar = claves_actuales - claves_nuevas
            for clave in claves_a_borrar:
                conn.execute(
                    sql_text(f'DELETE FROM "{tabla}" WHERE "{key_col}" = :key_value'),
                    {"key_value": clave},
                )

            insert_cols_sql = _sql_cols(columnas)
            insert_vals_sql = ", ".join([f":{c}" for c in columnas])
            insert_sql = sql_text(
                f'INSERT INTO "{tabla}" ({insert_cols_sql}) VALUES ({insert_vals_sql})'
            )

            update_cols = [c for c in columnas if c != key_col]
            update_set_sql = ", ".join([f'"{c}" = :{c}' for c in update_cols])
            update_sql = sql_text(
                f'UPDATE "{tabla}" SET {update_set_sql} WHERE "{key_col}" = :{key_col}'
            )

            inserts = 0
            updates = 0

            for _, row in clean.iterrows():
                params = {col: _normalizar_valor_postgres(row.get(col, "")) for col in columnas}
                clave = params[key_col]

                if clave not in claves_actuales:
                    conn.execute(insert_sql, params)
                    inserts += 1
                else:
                    row_actual = actual_idx.loc[clave]
                    if _filas_distintas(params, row_actual, columnas):
                        conn.execute(update_sql, params)
                        updates += 1

            # print útil en terminal local, no molesta en Streamlit Cloud.
            print(f"[Postgres smart save] {tabla}: inserts={inserts}, updates={updates}, deletes={len(claves_a_borrar)}")

    except Exception as e:
        # Fallback seguro: preserva funcionamiento aunque falle el smart-save.
        print(f"[Postgres smart save fallback] {tabla}: {e}")
        with engine.begin() as conn:
            try:
                conn.execute(sql_text(f'DELETE FROM "{tabla}"'))
                clean.to_sql(tabla, conn, if_exists="append", index=False, method="multi", chunksize=500)
            except Exception:
                clean.to_sql(tabla, engine, if_exists="replace", index=False, method="multi", chunksize=500)

    _limpiar_cache_postgres()


COLOR_NAVY = "#244777"
COLOR_BLUE = "#234579"
COLOR_TEAL = "#0788A6"
COLOR_TEAL_DARK = "#066478"
COLOR_BG = "#F6F8FB"
COLOR_CARD = "#FFFFFF"
COLOR_TEXT = "#172033"
COLOR_MUTED = "#667085"

USERS = {
    "alan": {
        "password": "alan_admin_2026",
        "role": "admin_general",
        "name": "Alan Moreno",
        "cliente": "",
    },
    "equipo": {
        "password": "equipo_am_2026",
        "role": "equipo",
        "name": "Equipo AM",
        "cliente": "",
    },
    "cliente_ritual": {
        "password": "ritual_2026",
        "role": "cliente",
        "name": "Ritual",
        "cliente": "Ritual Medicina Estética",
    },
    "cliente_ezca": {
        "password": "ezca_2026",
        "role": "cliente",
        "name": "EZCA",
        "cliente": "EZCA Premoldeados",
    },
}


def logo_sidebar_path():
    p = ASSETS_DIR / "isologo B.png"
    return p if p.exists() else None



def img_to_base64(path):
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode("utf-8")
    except Exception:
        return ""


# ============================================================
# Estilos
# ============================================================

st.markdown(
    f"""
    <style>
        .stApp {{
            background: {COLOR_BG};
        }}

        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {COLOR_NAVY} 0%, #14315B 100%);
        }}

        section[data-testid="stSidebar"] * {{
            color: white !important;
        }}

        .main-title {{
            font-size: 2.1rem;
            font-weight: 800;
            color: {COLOR_BLUE};
            margin-bottom: 0;
        }}

        .subtitle {{
            color: {COLOR_MUTED};
            font-size: 1rem;
            margin-top: -0.35rem;
            margin-bottom: 1.5rem;
        }}

        .am-card {{
            background: {COLOR_CARD};
            border: 1px solid #E5E7EB;
            border-radius: 18px;
            padding: 22px 24px;
            box-shadow: 0 8px 24px rgba(16, 24, 40, 0.04);
        }}

        .metric-card {{
            background: {COLOR_CARD};
            border: 1px solid #E5E7EB;
            border-radius: 18px;
            padding: 20px 22px;
            min-height: 130px;
            box-shadow: 0 8px 24px rgba(16, 24, 40, 0.04);
        }}

        .metric-label {{
            font-size: 0.9rem;
            color: {COLOR_MUTED};
            font-weight: 600;
        }}

        .metric-value {{
            font-size: 2.1rem;
            line-height: 1.1;
            color: {COLOR_TEXT};
            font-weight: 800;
        }}

        .metric-foot {{
            font-size: 0.85rem;
            color: {COLOR_TEAL};
            font-weight: 600;
        }}

        .status {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
        }}

        .status-pendiente {{
            background: #FFF4D6;
            color: #B7791F;
        }}

        .status-aprobado {{
            background: #DFF7E8;
            color: #177245;
        }}

        .status-revision {{
            background: #E0F2FE;
            color: #075985;
        }}

        .status-programado {{
            background: #EEF2FF;
            color: #3730A3;
        }}

        .status-publicado {{
            background: #E8F5E9;
            color: #1B5E20;
        }}

        .small-note {{
            font-size: 0.85rem;
            color: {COLOR_MUTED};
        }}

        div[data-testid="stMetric"] {{
            background: white;
            border: 1px solid #E5E7EB;
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 8px 24px rgba(16, 24, 40, 0.04);
        }}

        div.stButton > button {{
            border-radius: 12px;
            border: 1px solid {COLOR_TEAL};
            color: white;
            background: {COLOR_TEAL};
            font-weight: 700;
        }}

        div.stButton > button:hover {{
            background: {COLOR_TEAL_DARK};
            border: 1px solid {COLOR_TEAL_DARK};
            color: white;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Utilidades de datos
# ============================================================

def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)
    ASSETS_DIR.mkdir(exist_ok=True)


def perf_log(nombre, inicio):
    if os.getenv("PERF_DEBUG", "0") != "1":
        return

    try:
        duracion = time.perf_counter() - inicio
        print(f"[PERF] {nombre}: {duracion:.3f}s")
    except Exception:
        pass


def perf_start():
    try:
        return time.perf_counter()
    except Exception:
        return 0


def read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    ensure_data_dir()

    tabla = tabla_postgres_para_path(path)

    if usar_postgres() and tabla:
        return leer_postgres(tabla, columns)

    if not path.exists():
        return pd.DataFrame(columns=columns)

    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=columns)

    return normalizar_df_para_columnas(df, columns)


def read_csv_cliente(path: Path, columns: list[str], cliente: str) -> pd.DataFrame:
    ensure_data_dir()

    if not cliente:
        return read_csv(path, columns)

    tabla = tabla_postgres_para_path(path)

    if usar_postgres() and tabla:
        return leer_postgres_cliente(tabla, columns, cliente)

    df = read_csv(path, columns)

    if df.empty or "cliente" not in df.columns:
        return df

    return df[df["cliente"].astype(str) == str(cliente)].copy()


@st.cache_data(ttl=600, show_spinner=False)
def contar_postgres_cacheada(tabla: str) -> int:
    engine = get_postgres_engine()

    with engine.connect() as conn:
        result = conn.execute(sql_text(f'SELECT COUNT(*) FROM "{tabla}"')).scalar()

    try:
        return int(result or 0)
    except Exception:
        return 0


def contar_registros(path: Path, columns=None) -> int:
    tabla = tabla_postgres_para_path(path)

    if usar_postgres() and tabla:
        try:
            return contar_postgres_cacheada(tabla)
        except Exception:
            return 0

    try:
        df = read_csv(path, columns or [])
        return len(df)
    except Exception:
        return 0


@st.cache_data(ttl=600, show_spinner=False)
def leer_postgres_preview_cacheada(tabla: str, columns_tuple: tuple, limit: int, cliente: str = "") -> pd.DataFrame:
    columns = list(columns_tuple) if columns_tuple else []
    limit = int(limit or 80)

    if tabla in POSTGRES_CORE_TABLES:
        df = leer_postgres_core_tabla(tabla, columns)

        if cliente and "cliente" in df.columns:
            df = df[df["cliente"].astype(str) == str(cliente)].copy()

        return df.head(limit).copy()

    engine = get_postgres_engine()

    with engine.connect() as conn:
        if cliente:
            df = pd.read_sql(
                sql_text(f'SELECT * FROM "{tabla}" WHERE cliente = :cliente LIMIT :limit'),
                conn,
                params={"cliente": cliente, "limit": limit},
            )
        else:
            df = pd.read_sql(
                sql_text(f'SELECT * FROM "{tabla}" LIMIT :limit'),
                conn,
                params={"limit": limit},
            )

    return normalizar_df_para_columnas(df, columns)


def read_csv_preview(path: Path, columns: list[str], limit: int = 80, cliente: str = "") -> pd.DataFrame:
    inicio_perf = perf_start()
    tabla = tabla_postgres_para_path(path)

    if usar_postgres() and tabla:
        try:
            df = leer_postgres_preview_cacheada(tabla, tuple(columns or []), int(limit), str(cliente or ""))
            perf_log(f"preview {tabla} cliente={cliente or '-'} filas={len(df)}", inicio_perf)
            return df
        except Exception:
            perf_log(f"preview ERROR {tabla} cliente={cliente or '-'}", inicio_perf)
            return pd.DataFrame(columns=columns)

    df = read_csv_cliente(path, columns, cliente) if cliente else read_csv(path, columns)
    df = df.head(limit).copy()
    perf_log(f"preview CSV {Path(path).name} cliente={cliente or '-'} filas={len(df)}", inicio_perf)
    return df


def save_csv(df: pd.DataFrame, path: Path):
    ensure_data_dir()

    tabla = tabla_postgres_para_path(path)

    if usar_postgres() and tabla:
        guardar_postgres(df, tabla)
        return

    clean = df.copy().fillna("")
    clean.to_csv(path, index=False)


def seed_data():
    ensure_data_dir()

    if not CLIENTES_PATH.exists():
        clientes = pd.DataFrame([
            {
                "cliente": "Ritual Medicina Estética",
                "rubro": "Medicina estética",
                "estado": "Activo",
                "plan": "Gestión digital + pauta",
                "responsable_am": "Alan",
                "fecha_inicio": "2026-07-01",
                "notas": "Foco en cosmiatría, tratamientos, jornadas y contenido humano.",
            },
            {
                "cliente": "EZCA Premoldeados",
                "rubro": "Construcción / premoldeados",
                "estado": "Activo",
                "plan": "Contenido + branding",
                "responsable_am": "Alan",
                "fecha_inicio": "2026-07-01",
                "notas": "Foco en autoridad técnica, escaleras premoldeadas y humanización.",
            },
        ])
        save_csv(clientes, CLIENTES_PATH)

    if not CONTENIDOS_PATH.exists():
        contenidos = pd.DataFrame([
            {
                "id": "CON-001",
                "cliente": "Ritual Medicina Estética",
                "fecha": "2026-08-05",
                "canal": "Instagram",
                "formato": "Reel",
                "tema": "Beneficios de limpieza facial profunda",
                "objetivo": "Educar y generar consultas",
                "copy": "Una piel luminosa empieza con una limpieza profesional. En Ritual cuidamos tu piel con protocolos personalizados.",
                "link_canva": "https://www.canva.com/",
                "estado": "Pendiente de aprobación",
                "comentario_cliente": "",
            },
            {
                "id": "CON-002",
                "cliente": "Ritual Medicina Estética",
                "fecha": "2026-08-08",
                "canal": "Instagram",
                "formato": "Historia",
                "tema": "Turnos disponibles",
                "objetivo": "Conversión suave",
                "copy": "Esta semana abrimos nuevos turnos para tratamientos faciales. Escribinos y te asesoramos.",
                "link_canva": "https://www.canva.com/",
                "estado": "En diseño",
                "comentario_cliente": "",
            },
            {
                "id": "CON-003",
                "cliente": "EZCA Premoldeados",
                "fecha": "2026-08-06",
                "canal": "Instagram",
                "formato": "Carrusel",
                "tema": "¿Por qué elegir escaleras premoldeadas?",
                "objetivo": "Autoridad técnica",
                "copy": "Menos tiempo de obra, precisión dimensional y calidad constante.",
                "link_canva": "https://www.canva.com/",
                "estado": "Aprobado",
                "comentario_cliente": "",
            },
        ])
        save_csv(contenidos, CONTENIDOS_PATH)

    if not MATERIALES_PATH.exists():
        materiales = pd.DataFrame([
            {
                "id": "MAT-001",
                "cliente": "Ritual Medicina Estética",
                "solicitud": "Grabar video corto explicando qué es la cosmiatría",
                "responsable_cliente": "Leyla",
                "fecha_limite": "2026-08-04",
                "estado": "Solicitado",
                "observacion": "Formato vertical, 30 segundos, hablando a cámara.",
            },
            {
                "id": "MAT-002",
                "cliente": "EZCA Premoldeados",
                "solicitud": "Enviar fotos de obra y proceso de instalación",
                "responsable_cliente": "Equipo EZCA",
                "fecha_limite": "2026-08-07",
                "estado": "Pendiente",
                "observacion": "Ideal fotos horizontales y verticales.",
            },
        ])
        save_csv(materiales, MATERIALES_PATH)

    if not CAMPANIAS_PATH.exists():
        campanias = pd.DataFrame([
            {
                "id": "ADS-001",
                "cliente": "Ritual Medicina Estética",
                "campania": "Jornada estética agosto",
                "plataforma": "Meta Ads",
                "objetivo": "Mensajes",
                "presupuesto": 150000,
                "estado": "Activa",
                "leads": 28,
                "costo_por_lead": 5357,
                "observacion": "Campaña orientada a consultas por WhatsApp.",
            },
            {
                "id": "ADS-002",
                "cliente": "EZCA Premoldeados",
                "campania": "Reconocimiento de marca",
                "plataforma": "Meta Ads",
                "objetivo": "Alcance",
                "presupuesto": 80000,
                "estado": "Planificada",
                "leads": 0,
                "costo_por_lead": 0,
                "observacion": "Pendiente aprobación de creatividades.",
            },
        ])
        save_csv(campanias, CAMPANIAS_PATH)

    if not REPORTES_PATH.exists():
        reportes = pd.DataFrame([
            {
                "id": "REP-001",
                "cliente": "Ritual Medicina Estética",
                "mes": "Julio 2026",
                "alcance": 24800,
                "interacciones": 3200,
                "consultas": 76,
                "inversion": 150000,
                "estado": "Disponible",
                "que_funciono": "Contenido educativo y videos humanos tuvieron mejor respuesta.",
                "proximo_foco": "Reforzar jornadas, testimonios y llamados suaves a consulta.",
            },
            {
                "id": "REP-002",
                "cliente": "EZCA Premoldeados",
                "mes": "Julio 2026",
                "alcance": 9300,
                "interacciones": 840,
                "consultas": 11,
                "inversion": 0,
                "estado": "En armado",
                "que_funciono": "Contenido técnico e institucional.",
                "proximo_foco": "Mostrar obras, procesos y ventajas diferenciales.",
            },
        ])
        save_csv(reportes, REPORTES_PATH)

    if not TAREAS_PATH.exists():
        tareas = pd.DataFrame([
            {
                "id": "TAR-001",
                "cliente": "Ritual Medicina Estética",
                "tarea": "Diseñar carrusel de limpieza facial",
                "responsable_am": "Diseño",
                "prioridad": "Alta",
                "estado": "En diseño",
                "fecha_limite": "2026-08-03",
            },
            {
                "id": "TAR-002",
                "cliente": "EZCA Premoldeados",
                "tarea": "Armar calendario de contenidos de agosto",
                "responsable_am": "Alan",
                "prioridad": "Media",
                "estado": "Pendiente",
                "fecha_limite": "2026-08-05",
            },
        ])
        save_csv(tareas, TAREAS_PATH)


def load_clientes():
    return read_csv(
        CLIENTES_PATH,
        [
            "cliente",
            "rubro",
            "estado",
            "plan",
            "responsable_am",
            "fecha_inicio",
            "servicio_digital",
            "servicio_consultoria",
            "servicio_contabilidad",
            "notas",
        ],
    )


def load_contenidos(cliente=""):
    columns = [
        "id",
        "cliente",
        "fecha",
        "canal",
        "formato",
        "tema",
        "objetivo",
        "copy",
        "link_canva",
        "estado",
        "comentario_cliente",
    ]

    if cliente:
        return read_csv_cliente(CONTENIDOS_PATH, columns, cliente)

    return read_csv(CONTENIDOS_PATH, columns)


def columnas_materiales_completas():
    return [
        "id",
        "cliente",
        "solicitud",
        "responsable_cliente",
        "fecha_limite",
        "estado",
        "observacion",
        "formato_sugerido",
        "referencia",
        "link_entrega",
        "medio_envio",
        "comentario_cliente",
        "fecha_envio_cliente",
        "observacion_am",
        "fecha_carga",
        "creado_por",
        "fecha_actualizacion",
        "actualizado_por",
    ]


def load_materiales(cliente=""):
    columns = columnas_materiales_completas()

    if cliente:
        return read_csv_cliente(MATERIALES_PATH, columns, cliente)

    return read_csv(MATERIALES_PATH, columns)



def load_campanias(cliente=""):
    columns = [
        "id",
        "cliente",
        "campania",
        "plataforma",
        "objetivo",
        "presupuesto",
        "estado",
        "leads",
        "costo_por_lead",
        "observacion",
    ]

    if cliente:
        return read_csv_cliente(CAMPANIAS_PATH, columns, cliente)

    return read_csv(CAMPANIAS_PATH, columns)


def load_reportes(cliente=""):
    columns = [
        "id",
        "cliente",
        "mes",
        "alcance",
        "interacciones",
        "consultas",
        "inversion",
        "estado",
        "que_funciono",
        "proximo_foco",
        "pdf_nombre",
        "pdf_tipo",
        "pdf_base64",
        "fecha_carga",
        "cargado_por",
    ]

    if cliente:
        return read_csv_cliente(REPORTES_PATH, columns, cliente)

    return read_csv(REPORTES_PATH, columns)



def load_tareas(cliente=""):
    columns = [
        "id",
        "cliente",
        "tarea",
        "descripcion",
        "responsable_am",
        "prioridad",
        "estado",
        "fecha_limite",
        "comentarios",
        "fecha_carga",
        "creado_por",
        "fecha_actualizacion",
        "actualizado_por",
    ]

    if cliente:
        return read_csv_cliente(TAREAS_PATH, columns, cliente)

    return read_csv(TAREAS_PATH, columns)



def load_data():
    return (
        load_clientes(),
        load_contenidos(),
        load_materiales(),
        load_campanias(),
        load_reportes(),
        load_tareas(),
    )


def filter_cliente(df: pd.DataFrame, cliente: str) -> pd.DataFrame:
    if not cliente or df.empty or "cliente" not in df.columns:
        return df.copy()
    return df[df["cliente"].astype(str) == cliente].copy()


def money(x):
    try:
        return f"${float(x):,.0f}".replace(",", ".")
    except Exception:
        return "$0"


def status_badge(status: str):
    s = str(status)
    cls = "status-revision"
    if "Pendiente" in s or "Solicitado" in s:
        cls = "status-pendiente"
    elif "Aprobado" in s or "Disponible" in s:
        cls = "status-aprobado"
    elif "Programado" in s:
        cls = "status-programado"
    elif "Publicado" in s:
        cls = "status-publicado"
    elif "diseño" in s.lower() or "revisión" in s.lower() or "armado" in s.lower():
        cls = "status-revision"

    return f'<span class="status {cls}">{s}</span>'


# ============================================================
# Login
# ============================================================


def ensure_users_file():
    DATA_DIR.mkdir(exist_ok=True)

    if USUARIOS_PATH.exists():
        return

    rows = [
        {
            "username": "alan",
            "password": "alan_admin_2026",
            "role": "admin",
            "name": "Alan Moreno",
            "cliente": "",
            "activo": "Sí",
        },
        {
            "username": "equipo",
            "password": "equipo_am_2026",
            "role": "equipo",
            "name": "Equipo AM",
            "cliente": "",
            "activo": "Sí",
        },
        {
            "username": "cliente_ritual",
            "password": "ritual_2026",
            "role": "cliente",
            "name": "Ritual",
            "cliente": "Ritual Medicina Estética",
            "activo": "Sí",
        },
        {
            "username": "cliente_ezca",
            "password": "ezca_2026",
            "role": "cliente",
            "name": "EZCA",
            "cliente": "EZCA Premoldeados",
            "activo": "Sí",
        },
    ]

    pd.DataFrame(rows).to_csv(USUARIOS_PATH, index=False)


def load_users_df():
    ensure_users_file()

    required_cols = ["username", "password", "role", "name", "cliente", "activo"]
    df = read_csv(USUARIOS_PATH, required_cols).fillna("")

    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df["activo"] = df["activo"].replace({"": "Sí"})

    return df[required_cols]


def save_users_df(df):
    required_cols = ["username", "password", "role", "name", "cliente", "activo"]

    clean = df.copy().fillna("")

    for col in required_cols:
        if col not in clean.columns:
            clean[col] = ""

    clean = clean[required_cols]
    clean["username"] = clean["username"].astype(str).str.strip()
    clean["role"] = clean["role"].astype(str).str.strip()
    clean["activo"] = clean["activo"].astype(str).str.strip()

    clean = clean[clean["username"] != ""]
    clean = clean.drop_duplicates(subset=["username"], keep="last")

    save_csv(clean, USUARIOS_PATH)


def load_users():
    df = load_users_df()

    users = {}

    for _, row in df.iterrows():
        username = str(row.get("username", "")).strip()
        if not username:
            continue

        activo = str(row.get("activo", "Sí")).strip().lower()
        if activo not in ["sí", "si", "yes", "true", "1", "activo"]:
            continue

        users[username] = {
            "password": str(row.get("password", "")),
            "role": str(row.get("role", "")),
            "name": str(row.get("name", "")),
            "cliente": str(row.get("cliente", "")),
        }

    return users










def login():
    brand_path = ASSETS_DIR / "login_brand_lockup.png"

    st.markdown("<div style='height: 78px;'></div>", unsafe_allow_html=True)

    left_pad, brand_col, login_col, right_pad = st.columns([0.05, 0.42, 0.48, 0.05], gap="large")

    with brand_col:
        st.markdown("<div style='height: 36px;'></div>", unsafe_allow_html=True)

        if brand_path.exists():
            st.image(str(brand_path), width=430)
        else:
            st.markdown(
                """
                <div style="
                    font-size: 3.15rem;
                    font-weight: 900;
                    color: #244777;
                    letter-spacing: -0.055em;
                    line-height: 1;
                    margin-bottom: 16px;
                ">
                    AM Hub
                </div>
                <div style="
                    font-size: 1.05rem;
                    color: #667085;
                    line-height: 1.45;
                ">
                    Portal de gestión digital | AM Consultora
                </div>
                """,
                unsafe_allow_html=True,
            )

    with login_col:
        st.markdown(
            """
            <div style="
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 24px;
                padding: 28px 32px 8px 32px;
                box-shadow: 0 18px 45px rgba(16, 24, 40, 0.08);
            ">
                <div style="
                    font-size: 1.65rem;
                    font-weight: 850;
                    color: #172033;
                    margin-bottom: 6px;
                    letter-spacing: -0.035em;
                ">
                    Acceso
                </div>
                <div style="
                    font-size: 0.96rem;
                    color: #667085;
                    margin-bottom: 18px;
                ">
                    Ingresá con tu usuario para ver el portal correspondiente.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        username = st.text_input("Usuario", key="login_username")
        password = st.text_input("Contraseña", type="password", key="login_password")

        if st.button("Ingresar", key="login_button", use_container_width=True):
            users = load_users() if "load_users" in globals() else USERS

            username_clean = str(username).strip()
            password_clean = str(password).strip()

            user = users.get(username_clean)

            if user and str(user.get("password", "")).strip() == password_clean:
                st.session_state["logged_in"] = True
                st.session_state["auth"] = True
                st.session_state["username"] = username_clean
                st.session_state["role"] = str(user.get("role", "")).strip()
                st.session_state["name"] = str(user.get("name", "")).strip()
                st.session_state["cliente"] = str(user.get("cliente", "")).strip()
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos, o usuario inactivo.")



def logout_button():
    if st.sidebar.button("Cerrar sesión", use_container_width=True):
        for k in [
            "logged_in",
            "auth",
            "username",
            "role",
            "name",
            "cliente",
            "menu",
        ]:
            st.session_state.pop(k, None)

        st.rerun()



def preparar_logo_sidebar(ruta_logo):
    """
    Toma el logo, usa el color de la esquina superior izquierda como fondo,
    lo vuelve transparente y recorta márgenes sobrantes.
    """
    try:
        img = Image.open(ruta_logo).convert("RGBA")
        bg = img.getpixel((0, 0))  # color de fondo estimado

        datas = img.getdata()
        new_data = []

        for item in datas:
            # tolerancia para quitar el fondo aunque no sea exactamente igual
            if (
                abs(item[0] - bg[0]) < 20 and
                abs(item[1] - bg[1]) < 20 and
                abs(item[2] - bg[2]) < 20
            ):
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)

        img.putdata(new_data)

        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)

        return img
    except Exception:
        return None


def valor_si(valor):
    return str(valor).strip().lower() in ["sí", "si", "true", "1", "activo", "x"]


def servicios_activos_cliente(cliente_nombre):
    clientes_df = read_csv(
        CLIENTES_PATH,
        [
            "cliente",
            "servicio_digital",
            "servicio_consultoria",
            "servicio_contabilidad",
        ],
    )

    servicios = {
        "digital": False,
        "consultoria": False,
        "contabilidad": False,
    }

    if clientes_df is None or clientes_df.empty or "cliente" not in clientes_df.columns:
        return servicios

    fila = clientes_df[
        clientes_df["cliente"].astype(str).str.strip() == str(cliente_nombre).strip()
    ]

    if fila.empty:
        return servicios

    row = fila.iloc[0]

    servicios["digital"] = valor_si(row.get("servicio_digital", "No"))
    servicios["consultoria"] = valor_si(row.get("servicio_consultoria", "No"))
    servicios["contabilidad"] = valor_si(row.get("servicio_contabilidad", "No"))

    return servicios


def menu_cliente_por_servicios(cliente_nombre):
    servicios = servicios_activos_cliente(cliente_nombre)

    opciones = ["Inicio"]

    if servicios["digital"]:
        opciones += [
            "Calendario",
            "Aprobaciones",
            "Materiales",
            "Campañas",
            "Reportes",
        ]

    if servicios["consultoria"]:
        opciones += [
            "Objetivos",
            ]

    if servicios["contabilidad"]:
        opciones += [
            "Cash Flow",
            "Objetivos",
            ]

    limpio = []
    for opcion in opciones:
        if opcion not in limpio:
            limpio.append(opcion)

    return limpio


def usuarios_equipo_disponibles():
    usuarios_df = load_users_df()

    if usuarios_df is None or usuarios_df.empty or "role" not in usuarios_df.columns:
        return []

    equipos = usuarios_df[
        usuarios_df["role"].astype(str).isin(["equipo", "admin", "admin_general"])
    ].copy()

    if "activo" in equipos.columns:
        equipos = equipos[equipos["activo"].astype(str).str.lower().isin(["sí", "si", "true", "1", "activo"])]

    if "username" not in equipos.columns:
        return []

    return sorted(equipos["username"].dropna().astype(str).unique().tolist())


def cargar_asignaciones_equipo():
    return read_csv(
        ASIGNACIONES_EQUIPO_PATH,
        ["id", "username", "cliente", "activo"],
    )


def siguiente_id_asignacion(df):
    if df is None or df.empty or "id" not in df.columns:
        return 1

    ids = pd.to_numeric(df["id"], errors="coerce").fillna(0)
    return int(ids.max()) + 1


def clientes_visibles_para_usuario():
    role = st.session_state.get("role", "")
    username = st.session_state.get("username", "")

    clientes_df = read_csv(
        CLIENTES_PATH,
        [
            "cliente",
            "estado",
            "servicio_digital",
            "servicio_consultoria",
            "servicio_contabilidad",
        ],
    )

    if clientes_df is None or clientes_df.empty or "cliente" not in clientes_df.columns:
        return []

    if role in ["admin_general", "admin"]:
        return sorted(clientes_df["cliente"].dropna().astype(str).unique().tolist())

    if role == "cliente":
        cliente_actual = st.session_state.get("cliente", "")
        return [cliente_actual] if cliente_actual else []

    asignaciones = cargar_asignaciones_equipo()

    if asignaciones is None or asignaciones.empty:
        return []

    visibles = asignaciones[
        (asignaciones["username"].astype(str) == str(username))
        & (asignaciones["activo"].astype(str).str.lower().isin(["sí", "si", "true", "1", "activo"]))
    ]["cliente"].dropna().astype(str).unique().tolist()

    clientes_existentes = set(clientes_df["cliente"].dropna().astype(str).tolist())

    visibles = [c for c in visibles if c in clientes_existentes]

    return sorted(visibles)


def servicios_habilitados_para_equipo():
    role = st.session_state.get("role", "")

    if role in ["admin_general", "admin"]:
        return {
            "digital": True,
            "consultoria": True,
            "contabilidad": True,
        }

    clientes_visibles = clientes_visibles_para_usuario()

    clientes_df = read_csv(
        CLIENTES_PATH,
        [
            "cliente",
            "servicio_digital",
            "servicio_consultoria",
            "servicio_contabilidad",
        ],
    )

    servicios = {
        "digital": False,
        "consultoria": False,
        "contabilidad": False,
    }

    if clientes_df is None or clientes_df.empty or not clientes_visibles:
        return servicios

    base = clientes_df[clientes_df["cliente"].astype(str).isin(clientes_visibles)]

    if "servicio_digital" in base.columns:
        servicios["digital"] = base["servicio_digital"].apply(valor_si).any()

    if "servicio_consultoria" in base.columns:
        servicios["consultoria"] = base["servicio_consultoria"].apply(valor_si).any()

    if "servicio_contabilidad" in base.columns:
        servicios["contabilidad"] = base["servicio_contabilidad"].apply(valor_si).any()

    return servicios


def menu_equipo_por_permisos():
    servicios = servicios_habilitados_para_equipo()

    opciones = ["Dashboard AM"]

    if servicios.get("consultoria"):
        opciones += ["Objetivos"]

    if servicios.get("contabilidad"):
        opciones += ["Cash Flow", "Objetivos"]

    if servicios.get("digital"):
        opciones += ["Contenidos", "Materiales", "Campañas", "Reportes"]

    opciones += ["Tareas"]

    opciones = [op for op in opciones if op != "Cuenta corriente"]

    limpio = []
    for opcion in opciones:
        if opcion not in limpio:
            limpio.append(opcion)

    return limpio



def menu_por_servicios_cliente_para_equipo(cliente_nombre):
    servicios = servicios_activos_cliente(cliente_nombre)

    opciones = ["Portal cliente"]

    if servicios.get("digital"):
        opciones += ["Contenidos", "Materiales", "Campañas", "Reportes"]

    if servicios.get("consultoria"):
        opciones += ["Objetivos"]

    if servicios.get("contabilidad"):
        opciones += ["Cash Flow", "Objetivos"]

    opciones += ["Tareas"]

    opciones = [op for op in opciones if op != "Cuenta corriente"]

    limpio = []
    for opcion in opciones:
        if opcion not in limpio:
            limpio.append(opcion)

    return limpio


def sidebar():
    logo_path = ASSETS_DIR / "isologo_sidebar_limpio.png"
    if not logo_path.exists():
        logo_path = ASSETS_DIR / "isologo B.png"

    st.sidebar.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)

    if logo_path.exists():
        st.sidebar.image(str(logo_path), width=112)
    else:
        st.sidebar.markdown("## AM Consultora")

    st.sidebar.markdown(
        """
        <div style="margin-top: 10px; margin-bottom: 24px;">
            <div style="font-size: 1.35rem; font-weight: 800; color: white;">
                AM Hub
            </div>
            <div style="font-size: 0.9rem; color: rgba(255,255,255,0.78); margin-top: 2px;">
                Portal de gestión digital
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    role = st.session_state.get("role")

    if role == "cliente":
        cliente_actual = st.session_state.get("cliente", "")
        opciones_cliente = menu_cliente_por_servicios(cliente_actual)

        # Cuenta corriente debe estar disponible para todos los usuarios cliente,
        # actuales y nuevos, independientemente de los servicios contratados.
        if "Cuenta corriente" not in opciones_cliente:
            opciones_cliente = ["Inicio", "Cuenta corriente"] + [
                op for op in opciones_cliente if op not in ["Inicio", "Cuenta corriente", "Documentos"]
            ]
        else:
            opciones_cliente = [op for op in opciones_cliente if op != "Documentos"]

        destino_menu_cliente = st.session_state.pop("menu_cliente_destino", None)

        if destino_menu_cliente in opciones_cliente:
            st.session_state["menu_cliente_v2"] = destino_menu_cliente

        menu = st.sidebar.radio(
            "Menú",
            opciones_cliente,
            key="menu_cliente_v2",
        )
    elif role in ["admin_general", "admin"]:
        menu = st.sidebar.radio(
            "Menú",
            [
                "Dashboard AM",
                "Edición rápida",
                "Usuarios",
                "Onboarding",
                "Clientes",
                "Objetivos",
                        "Cash Flow",
                "Cuenta corriente",
                "Contenidos",
                "Materiales",
                "Campañas",
                "Reportes",
                "Tareas",
                "Vista cliente",
            ],
            key="menu_admin",
        )
    else:
        clientes_asignados = clientes_visibles_para_usuario()

        if not clientes_asignados:
            st.sidebar.warning("No tenés clientes asignados.")
            menu = "Sin clientes asignados"
        else:
            cliente_equipo = st.sidebar.selectbox(
                "Cliente asignado",
                clientes_asignados,
                key="cliente_equipo_activo",
            )

            st.session_state["cliente_equipo_visible"] = cliente_equipo

            st.sidebar.markdown(
                f"""
                <div style="
                    margin-top: 12px;
                    margin-bottom: 14px;
                    padding: 12px 14px;
                    border-radius: 14px;
                    background: rgba(255,255,255,0.10);
                    border: 1px solid rgba(255,255,255,0.18);
                ">
                    <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: .08em; color: rgba(255,255,255,0.72);">
                        Cliente activo
                    </div>
                    <div style="font-size: 1.02rem; font-weight: 800; color: white; margin-top: 3px; line-height: 1.2;">
                        {cliente_equipo}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            menu = st.sidebar.radio(
                "Portal del cliente",
                menu_por_servicios_cliente_para_equipo(cliente_equipo),
                key="menu_equipo_cliente",
            )

    st.sidebar.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    st.sidebar.markdown("---")

    st.sidebar.markdown(
        f"""
        <div style="font-size: 0.9rem; line-height: 1.6;">
            <strong>Usuario:</strong> {st.session_state.get('name')}<br>
            <strong>Rol:</strong> {role}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    logout_button()

    return menu

# ============================================================
# Vista interna
# ============================================================


def header(title, subtitle=""):
    st.markdown(
        f"""
        <div style="margin-bottom: 26px;">
            <h1 style="
                margin: 0 0 6px 0;
                color: #244777;
                font-size: 2.25rem;
                font-weight: 850;
                letter-spacing: -0.035em;
            ">
                {title}
            </h1>
            <p style="
                margin: 0;
                color: #667085;
                font-size: 1rem;
                line-height: 1.45;
            ">
                {subtitle}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )




def kpi_card(label, value, foot=""):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-foot">{foot}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_inicio_cliente(cliente, contenidos, materiales, campanias, reportes):
    header("AM Hub", f"Portal de gestión digital | {cliente}")

    contenidos_c = filter_cliente(contenidos, cliente)
    materiales_c = filter_cliente(materiales, cliente)
    campanias_c = filter_cliente(campanias, cliente)
    reportes_c = filter_cliente(reportes, cliente)

    pendientes_aprobacion = contenidos_c[
        contenidos_c["estado"].astype(str).str.contains(
            "Pendiente|revisión|aprobación|Correcciones",
            case=False,
            na=False,
        )
    ].copy() if not contenidos_c.empty else contenidos_c.copy()

    materiales_pend = materiales_c[
        ~materiales_c["estado"].astype(str).str.contains(
            "Recibido|Publicado|Usado",
            case=False,
            na=False,
        )
    ].copy() if not materiales_c.empty else materiales_c.copy()

    camp_act = campanias_c[
        campanias_c["estado"].astype(str).str.contains(
            "Activa",
            case=False,
            na=False,
        )
    ].copy() if not campanias_c.empty else campanias_c.copy()

    rep_disp = reportes_c[
        reportes_c["estado"].astype(str).str.contains(
            "Disponible",
            case=False,
            na=False,
        )
    ].copy() if not reportes_c.empty else reportes_c.copy()

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #244777 0%, #0788A6 100%);
            border-radius: 24px;
            padding: 28px 32px;
            margin-bottom: 28px;
            color: white;
            box-shadow: 0 18px 45px rgba(36, 71, 119, 0.18);
        ">
            <div style="font-size: 0.95rem; opacity: 0.82; margin-bottom: 6px;">
                Resumen de gestión
            </div>
            <div style="font-size: 2rem; font-weight: 850; letter-spacing: -0.035em; margin-bottom: 8px;">
                {cliente}
            </div>        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        kpi_card("Contenidos del mes", len(contenidos_c), "Calendario vigente")
    with c2:
        kpi_card("Pendientes de aprobación", len(pendientes_aprobacion), "Requieren revisión")
    with c3:
        kpi_card("Campañas activas", len(camp_act), "Pauta en curso")
    with c4:
        kpi_card("Reportes disponibles", len(rep_disp), "Últimos informes")

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    col_left, col_right = st.columns([0.58, 0.42], gap="large")

    with col_left:
        st.markdown("### Calendario próximo")

        if contenidos_c.empty:
            st.info("Todavía no hay contenidos cargados.")
        else:
            cols = ["fecha", "canal", "formato", "tema", "estado"]
            cols = [c for c in cols if c in contenidos_c.columns]
            st.dataframe(contenidos_c[cols].head(8), use_container_width=True, hide_index=True)

        st.markdown("### Pendientes de aprobación")

        if pendientes_aprobacion.empty:
            st.success("No hay contenidos pendientes de aprobación.")
        else:
            for _, row in pendientes_aprobacion.head(4).iterrows():
                with st.container(border=True):
                    st.write(f"**{row.get('formato', '')} — {row.get('tema', '')}**")
                    st.caption(
                        f"{row.get('fecha', '')} | {row.get('canal', '')} | Objetivo: {row.get('objetivo', '')}"
                    )
                    st.markdown(status_badge(row.get("estado", "")), unsafe_allow_html=True)

                    if str(row.get("copy", "")).strip():
                        st.markdown("**Copy propuesto**")
                        st.write(row.get("copy", ""))

                    if str(row.get("link_canva", "")).strip():
                        st.link_button("Ver diseño en Canva", row.get("link_canva", ""))

    with col_right:
        st.markdown("### Materiales pendientes")

        if materiales_pend.empty:
            st.success("No hay materiales pendientes.")
        else:
            for _, row in materiales_pend.head(5).iterrows():
                with st.container(border=True):
                    st.write(f"**{row.get('solicitud', '')}**")
                    st.caption(
                        f"Responsable: {row.get('responsable_cliente', '')} | Límite: {row.get('fecha_limite', '')}"
                    )
                    st.markdown(status_badge(row.get("estado", "")), unsafe_allow_html=True)

        st.markdown("### Campañas activas")

        if campanias_c.empty:
            st.info("No hay campañas cargadas.")
        else:
            for _, row in campanias_c.head(4).iterrows():
                with st.container(border=True):
                    st.write(f"**{row.get('campania', '')}**")
                    st.caption(f"{row.get('plataforma', '')} | Objetivo: {row.get('objetivo', '')}")

                    ca, cb = st.columns(2)
                    ca.metric("Presupuesto", money(row.get("presupuesto", 0)))
                    cb.metric("Consultas", row.get("leads", 0))

                    st.markdown(status_badge(row.get("estado", "")), unsafe_allow_html=True)

        st.markdown("### Último reporte")

        if rep_disp.empty:
            st.info("Todavía no hay reportes disponibles.")
        else:
            row = rep_disp.iloc[-1]
            with st.container(border=True):
                st.write(f"**{row.get('mes', '')}**")

                ca, cb = st.columns(2)
                ca.metric("Alcance", f"{int(float(row.get('alcance', 0))):,}".replace(",", "."))
                cb.metric("Consultas", int(float(row.get("consultas", 0))))

                st.markdown("**Qué funcionó**")
                st.write(row.get("que_funciono", ""))

                st.markdown("**Próximo foco**")
                st.write(row.get("proximo_foco", ""))





def render_contenidos_equipo(cliente):
    header("Contenidos", f"Planificación digital | {cliente}")

    contenidos_all = read_csv(
        CONTENIDOS_PATH,
        [
            "id",
            "cliente",
            "fecha",
            "canal",
            "formato",
            "tema",
            "objetivo",
            "copy",
            "link_canva",
            "estado",
            "comentario_cliente",
        ],
    )

    def next_contenido_id(df):
        if df is None or df.empty or "id" not in df.columns:
            return "CON-001"

        nums = []

        for value in df["id"].dropna().astype(str).tolist():
            value = value.strip()

            if value.upper().startswith("CON-"):
                try:
                    nums.append(int(value.split("-")[-1]))
                except Exception:
                    pass
            else:
                try:
                    nums.append(int(value))
                except Exception:
                    pass

        siguiente = max(nums) + 1 if nums else 1
        return f"CON-{siguiente:03d}"

    if contenidos_all is None:
        contenidos_all = pd.DataFrame(columns=[
            "id",
            "cliente",
            "fecha",
            "canal",
            "formato",
            "tema",
            "objetivo",
            "copy",
            "link_canva",
            "estado",
            "comentario_cliente",
        ])

    for col in [
        "id",
        "cliente",
        "fecha",
        "canal",
        "formato",
        "tema",
        "objetivo",
        "copy",
        "link_canva",
        "estado",
        "comentario_cliente",
    ]:
        if col not in contenidos_all.columns:
            contenidos_all[col] = ""

    df = filter_cliente(contenidos_all, cliente)

    # --------------------------------------------------------
    # Alta de contenido
    # --------------------------------------------------------
    st.markdown("### Nuevo contenido")

    with st.form(f"form_contenido_equipo_{cliente}"):
        c1, c2, c3 = st.columns(3)

        with c1:
            st.text_input("Cliente", value=cliente, disabled=True)
            fecha = st.date_input("Fecha propuesta")

        with c2:
            canal = st.selectbox(
                "Canal",
                ["Instagram", "Facebook", "LinkedIn", "TikTok", "YouTube", "Email", "Web", "Otro"],
            )
            formato = st.selectbox(
                "Formato",
                ["Post", "Carrusel", "Reel", "Historia", "Video", "Newsletter", "Landing", "Otro"],
            )

        with c3:
            estado = st.selectbox(
                "Estado",
                [
                    "En diseño",
                    "Pendiente de aprobación",
                    "Correcciones",
                    "Aprobado",
                    "Programado",
                    "Publicado",
                ],
                index=1,
            )
            link_canva = st.text_input("Link Canva / diseño")

        tema = st.text_input("Tema")
        objetivo = st.text_input("Objetivo")
        copy_text = st.text_area("Copy propuesto")

        guardar = st.form_submit_button("Guardar contenido", use_container_width=True)

        if guardar:
            if not tema.strip():
                st.error("El tema es obligatorio.")
            else:
                nuevo = {
                    "id": next_contenido_id(contenidos_all),
                    "cliente": cliente,
                    "fecha": fecha.strftime("%Y-%m-%d"),
                    "canal": canal,
                    "formato": formato,
                    "tema": tema.strip(),
                    "objetivo": objetivo,
                    "copy": copy_text,
                    "link_canva": link_canva,
                    "estado": estado,
                    "comentario_cliente": "",
                }

                actualizado = pd.concat(
                    [contenidos_all, pd.DataFrame([nuevo])],
                    ignore_index=True,
                )

                save_csv(actualizado, CONTENIDOS_PATH)
                st.success("Contenido cargado correctamente.")
                st.rerun()

    # --------------------------------------------------------
    # Resumen
    # --------------------------------------------------------
    df = filter_cliente(read_csv(
        CONTENIDOS_PATH,
        [
            "id",
            "cliente",
            "fecha",
            "canal",
            "formato",
            "tema",
            "objetivo",
            "copy",
            "link_canva",
            "estado",
            "comentario_cliente",
        ],
    ), cliente)

    if df.empty:
        st.info("Todavía no hay contenidos cargados para este cliente.")
        return

    df = df.copy()

    pendientes = df["estado"].astype(str).str.contains(
        "Pendiente|revisión|aprobación|Correcciones|En diseño",
        case=False,
        na=False,
    ).sum()

    aprobados = df["estado"].astype(str).str.contains(
        "Aprobado|Programado|Publicado",
        case=False,
        na=False,
    ).sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total contenidos", len(df))
    c2.metric("Pendientes / revisión", int(pendientes))
    c3.metric("Aprobados / programados", int(aprobados))

    # --------------------------------------------------------
    # Filtros
    # --------------------------------------------------------
    st.markdown("### Calendario de contenidos")

    f1, f2, f3 = st.columns(3)

    with f1:
        estados = ["Todos"] + sorted(df["estado"].dropna().astype(str).unique().tolist())
        filtro_estado = st.selectbox("Estado", estados, key=f"cont_equipo_estado_{cliente}")

    with f2:
        formatos = ["Todos"] + sorted(df["formato"].dropna().astype(str).unique().tolist())
        filtro_formato = st.selectbox("Formato", formatos, key=f"cont_equipo_formato_{cliente}")

    with f3:
        canales = ["Todos"] + sorted(df["canal"].dropna().astype(str).unique().tolist())
        filtro_canal = st.selectbox("Canal", canales, key=f"cont_equipo_canal_{cliente}")

    vista = df.copy()

    if filtro_estado != "Todos":
        vista = vista[vista["estado"].astype(str) == filtro_estado]

    if filtro_formato != "Todos":
        vista = vista[vista["formato"].astype(str) == filtro_formato]

    if filtro_canal != "Todos":
        vista = vista[vista["canal"].astype(str) == filtro_canal]

    if "fecha" in vista.columns:
        vista = vista.sort_values("fecha")

    cols = ["fecha", "canal", "formato", "tema", "objetivo", "estado", "comentario_cliente"]
    cols = [c for c in cols if c in vista.columns]

    st.dataframe(
        vista[cols],
        use_container_width=True,
        hide_index=True,
    )

    # --------------------------------------------------------
    # Tarjetas pendientes
    # --------------------------------------------------------
    st.markdown("### Pendientes de aprobación / revisión")

    pendientes_df = vista[
        vista["estado"].astype(str).str.contains(
            "Pendiente|revisión|aprobación|Correcciones|En diseño",
            case=False,
            na=False,
        )
    ].copy()

    if pendientes_df.empty:
        st.success("No hay contenidos pendientes.")
    else:
        for _, row in pendientes_df.head(8).iterrows():
            with st.container(border=True):
                st.markdown(f"**{row.get('formato', '')} — {row.get('tema', '')}**")
                st.caption(f"{row.get('fecha', '')} | {row.get('canal', '')} | Estado: {row.get('estado', '')}")

                if str(row.get("objetivo", "")).strip():
                    st.write(row.get("objetivo", ""))

                if str(row.get("comentario_cliente", "")).strip():
                    st.markdown("**Comentario cliente:**")
                    st.write(row.get("comentario_cliente", ""))

                link = str(row.get("link_canva", "")).strip()
                if link:
                    st.link_button("Abrir diseño", link)

    # --------------------------------------------------------
    # Edición segura
    # --------------------------------------------------------
    with st.expander("Edición segura de contenidos del cliente"):
        st.caption(
            "Esta edición actualiza solo las filas de este cliente dentro del archivo completo, "
            "sin pisar contenidos de otros clientes."
        )

        editable_cols = [
            "id",
            "fecha",
            "canal",
            "formato",
            "tema",
            "objetivo",
            "copy",
            "link_canva",
            "estado",
            "comentario_cliente",
        ]

        editable_cols = [c for c in editable_cols if c in df.columns]

        edited = st.data_editor(
            df[editable_cols],
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            key=f"editor_contenidos_equipo_{cliente}",
            column_config={
                "id": st.column_config.TextColumn("ID", disabled=True),
                "estado": st.column_config.SelectboxColumn(
                    "Estado",
                    options=[
                        "En diseño",
                        "Pendiente de aprobación",
                        "Correcciones",
                        "Aprobado",
                        "Programado",
                        "Publicado",
                    ],
                ),
            },
        )

        if st.button("Guardar cambios de contenidos", use_container_width=True, key=f"guardar_contenidos_equipo_{cliente}"):
            full = read_csv(
                CONTENIDOS_PATH,
                [
                    "id",
                    "cliente",
                    "fecha",
                    "canal",
                    "formato",
                    "tema",
                    "objetivo",
                    "copy",
                    "link_canva",
                    "estado",
                    "comentario_cliente",
                ],
            )

            for _, row in edited.iterrows():
                row_id = str(row.get("id", ""))

                if not row_id:
                    continue

                mask = full["id"].astype(str) == row_id

                for col in editable_cols:
                    if col == "id":
                        continue

                    full.loc[mask, col] = row.get(col, "")

            save_csv(full, CONTENIDOS_PATH)
            st.success("Contenidos actualizados correctamente.")
            st.rerun()



def render_calendario(cliente, contenidos):
    header("Calendario de contenidos", f"Planificación mensual | {cliente}")

    df = filter_cliente(contenidos, cliente)

    if df.empty:
        st.info("No hay contenidos cargados para este cliente.")
        return

    df = df.copy()

    for col in ["fecha", "canal", "formato", "tema", "objetivo", "copy", "link_canva", "estado", "comentario_cliente"]:
        if col not in df.columns:
            df[col] = ""

    df["fecha"] = df["fecha"].astype(str)
    df["mes"] = df["fecha"].str.slice(0, 7)

    meses = sorted(df["mes"].dropna().astype(str).unique().tolist())
    estados = ["Todos"] + sorted(df["estado"].dropna().astype(str).unique().tolist())
    formatos = ["Todos"] + sorted(df["formato"].dropna().astype(str).unique().tolist())

    st.markdown("### Filtros")

    f1, f2, f3 = st.columns(3)

    with f1:
        mes_sel = st.selectbox(
            "Mes",
            ["Todos"] + meses,
            index=0,
            key=f"cal_mes_{cliente}",
        )

    with f2:
        estado_sel = st.selectbox(
            "Estado",
            estados,
            key=f"cal_estado_cliente_{cliente}",
        )

    with f3:
        formato_sel = st.selectbox(
            "Formato",
            formatos,
            key=f"cal_formato_cliente_{cliente}",
        )

    vista = df.copy()

    if mes_sel != "Todos":
        vista = vista[vista["mes"] == mes_sel]

    if estado_sel != "Todos":
        vista = vista[vista["estado"].astype(str) == estado_sel]

    if formato_sel != "Todos":
        vista = vista[vista["formato"].astype(str) == formato_sel]

    if vista.empty:
        st.info("No hay contenidos para los filtros seleccionados.")
        return

    pendientes = vista["estado"].astype(str).str.contains(
        "Pendiente|revisión|aprobación|Correcciones|En diseño",
        case=False,
        na=False,
    ).sum()

    aprobados = vista["estado"].astype(str).str.contains(
        "Aprobado|Programado|Publicado",
        case=False,
        na=False,
    ).sum()

    publicados = vista["estado"].astype(str).str.contains(
        "Publicado",
        case=False,
        na=False,
    ).sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", len(vista))
    c2.metric("Pendientes", int(pendientes))
    c3.metric("Aprobados / programados", int(aprobados))
    c4.metric("Publicados", int(publicados))

    if "fecha" in vista.columns:
        vista = vista.sort_values("fecha")

    st.markdown("### Calendario")

    cols = ["fecha", "canal", "formato", "tema", "objetivo", "estado"]
    cols = [c for c in cols if c in vista.columns]

    st.dataframe(
        vista[cols],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Detalle de piezas")

    for _, row in vista.iterrows():
        estado = str(row.get("estado", ""))

        with st.container(border=True):
            top1, top2 = st.columns([0.72, 0.28])

            with top1:
                st.markdown(f"**{row.get('formato', '')} — {row.get('tema', '')}**")
                st.caption(f"{row.get('fecha', '')} | {row.get('canal', '')}")

            with top2:
                st.markdown(status_badge(estado), unsafe_allow_html=True)

            objetivo = str(row.get("objetivo", "")).strip()
            if objetivo:
                st.markdown("**Objetivo**")
                st.write(objetivo)

            copy_text = str(row.get("copy", "")).strip()
            if copy_text:
                with st.expander("Ver copy"):
                    st.write(copy_text)

            comentario = str(row.get("comentario_cliente", "")).strip()
            if comentario:
                with st.expander("Comentario / correcciones"):
                    st.write(comentario)

            link_canva = str(row.get("link_canva", "")).strip()
            if link_canva:
                st.link_button("Ver diseño", link_canva)


def render_aprobaciones(cliente, contenidos):
    header("Aprobaciones", f"Revisión de contenidos y copies | {cliente}")

    df = filter_cliente(contenidos, cliente)

    if df.empty:
        st.info("No hay contenidos cargados para aprobar.")
        return

    df = df.copy()

    for col in ["id", "fecha", "canal", "formato", "tema", "objetivo", "copy", "link_canva", "estado", "comentario_cliente"]:
        if col not in df.columns:
            df[col] = ""

    pendientes = df[
        df["estado"].astype(str).str.contains(
            "Pendiente|revisión|aprobación|Correcciones|En diseño",
            case=False,
            na=False,
        )
    ].copy()

    aprobados = df[
        df["estado"].astype(str).str.contains(
            "Aprobado|Programado|Publicado",
            case=False,
            na=False,
        )
    ].copy()

    c1, c2, c3 = st.columns(3)
    c1.metric("Para revisar", len(pendientes))
    c2.metric("Aprobados / programados", len(aprobados))
    c3.metric("Total contenidos", len(df))

    st.markdown("### Contenidos que requieren acción")

    if pendientes.empty:
        st.success("No hay contenidos pendientes de revisión.")
    else:
        contenidos_all = contenidos.copy()

        for _, row in pendientes.sort_values("fecha").iterrows():
            row_id = row.get("id", "")
            estado_actual = str(row.get("estado", ""))

            with st.container(border=True):
                top_left, top_right = st.columns([0.72, 0.28])

                with top_left:
                    st.markdown(f"**{row.get('formato', '')} — {row.get('tema', '')}**")
                    st.caption(
                        f"{row.get('fecha', '')} | {row.get('canal', '')} | Objetivo: {row.get('objetivo', '')}"
                    )

                with top_right:
                    st.markdown(status_badge(estado_actual), unsafe_allow_html=True)

                copy_text = str(row.get("copy", "")).strip()
                if copy_text:
                    st.markdown("**Copy propuesto**")
                    st.write(copy_text)

                link_canva = str(row.get("link_canva", "")).strip()
                if link_canva:
                    st.link_button("Abrir diseño", link_canva)

                comentario = st.text_area(
                    "Comentario / correcciones",
                    value=str(row.get("comentario_cliente", "")),
                    key=f"comentario_cliente_{row_id}",
                    placeholder="Escribí cambios o comentarios para el equipo AM...",
                )

                action_left, action_right = st.columns(2)

                with action_left:
                    if st.button("Aprobar", key=f"aprobar_{row_id}", use_container_width=True):
                        contenidos_all.loc[contenidos_all["id"] == row_id, "estado"] = "Aprobado"
                        contenidos_all.loc[contenidos_all["id"] == row_id, "comentario_cliente"] = comentario
                        save_csv(contenidos_all, CONTENIDOS_PATH)
                        st.success("Contenido aprobado.")
                        st.rerun()

                with action_right:
                    if st.button("Pedir cambios", key=f"corregir_{row_id}", use_container_width=True):
                        if not comentario.strip():
                            st.error("Para pedir cambios, agregá un comentario.")
                        else:
                            contenidos_all.loc[contenidos_all["id"] == row_id, "estado"] = "Correcciones"
                            contenidos_all.loc[contenidos_all["id"] == row_id, "comentario_cliente"] = comentario
                            save_csv(contenidos_all, CONTENIDOS_PATH)
                            st.success("Pedido de cambios enviado.")
                            st.rerun()

    st.markdown("### Ya aprobados / programados")

    if aprobados.empty:
        st.info("Todavía no hay contenidos aprobados.")
    else:
        cols = ["fecha", "canal", "formato", "tema", "estado"]
        cols = [c for c in cols if c in aprobados.columns]

        st.dataframe(
            aprobados.sort_values("fecha")[cols],
            use_container_width=True,
            hide_index=True,
        )


def render_materiales(cliente, materiales=None):
    header(
        "Pedidos de material",
        f"Solicitudes de grabación y entrega de contenidos | {cliente}",
    )

    columnas = columnas_materiales_completas()

    if materiales is None:
        df_all = load_materiales()
    else:
        df_all = materiales.copy()

    if df_all is None or df_all.empty:
        st.info("No hay pedidos de material cargados.")
        return

    df_all = df_all.copy().fillna("")

    for col in columnas:
        if col not in df_all.columns:
            df_all[col] = ""

    df_all = df_all[columnas].fillna("")

    df = df_all[
        df_all["cliente"].astype(str) == str(cliente)
    ].copy()

    if df.empty:
        st.info("No hay pedidos de material para este cliente.")
        return

    estados_finales = [
        "Aprobado",
        "Publicado",
        "Cancelado",
    ]

    pendientes = df[
        ~df["estado"].astype(str).isin(estados_finales)
    ].copy()

    cerrados = df[
        df["estado"].astype(str).isin(estados_finales)
    ].copy()

    enviados = df[
        df["estado"].astype(str).isin(
            [
                "Enviado por cliente",
                "En revisión",
                "Requiere cambios",
                "Aprobado",
                "Publicado",
            ]
        )
    ].copy()

    k1, k2, k3 = st.columns(3)
    k1.metric("Pedidos totales", len(df))
    k2.metric("Pendientes", len(pendientes))
    k3.metric("Entregados", len(enviados))

    st.markdown("### Pedidos activos")

    if pendientes.empty:
        st.success("No tenés pedidos de material pendientes.")
    else:
        st.caption(
            "Revisá las indicaciones, grabá el material y compartí el link "
            "cuando esté listo. También podés dejar comentarios o avisar si "
            "necesitás una aclaración."
        )

        pendientes = pendientes.sort_values(
            "fecha_limite",
            ascending=True,
        )

        for idx, row in pendientes.iterrows():
            material_id = str(row.get("id", idx))
            solicitud = str(
                row.get("solicitud", "") or "Material solicitado"
            )
            estado = str(
                row.get("estado", "") or "Solicitado"
            )
            fecha_limite = str(
                row.get("fecha_limite", "") or ""
            )
            responsable = str(
                row.get("responsable_cliente", "") or ""
            )
            indicaciones = str(
                row.get("observacion", "") or ""
            )
            formato = str(
                row.get("formato_sugerido", "") or ""
            )
            referencia = str(
                row.get("referencia", "") or ""
            )
            observacion_am = str(
                row.get("observacion_am", "") or ""
            )

            with st.container(border=True):
                encabezado_1, encabezado_2 = st.columns([3, 1])

                with encabezado_1:
                    st.markdown(f"### {solicitud}")

                    if responsable:
                        st.caption(
                            f"Responsable sugerido: {responsable}"
                        )

                with encabezado_2:
                    if estado == "Requiere cambios":
                        st.warning(estado)
                    elif estado in [
                        "Enviado por cliente",
                        "En revisión",
                    ]:
                        st.info(estado)
                    else:
                        st.caption(f"Estado: {estado}")

                if fecha_limite:
                    st.caption(f"Fecha límite: {fecha_limite}")

                if indicaciones:
                    st.markdown("**Indicaciones de AM Consultora**")
                    st.write(indicaciones)

                if formato:
                    st.markdown("**Formato sugerido**")
                    st.write(formato)

                if referencia:
                    st.markdown("**Referencia o ejemplo**")
                    st.write(referencia)

                    if referencia.startswith(("http://", "https://")):
                        st.link_button(
                            "Abrir referencia",
                            referencia,
                            use_container_width=True,
                        )

                if observacion_am:
                    st.markdown("**Última devolución de AM**")
                    st.warning(observacion_am)

                st.divider()
                st.markdown("#### Entrega del material")

                medio_actual = str(
                    row.get("medio_envio", "") or "Link cargado acá"
                )

                opciones_medio = [
                    "Link cargado acá",
                    "Drive",
                    "WeTransfer",
                    "Dropbox",
                    "Canva",
                    "WhatsApp",
                    "Mail",
                    "Otro",
                ]

                if medio_actual not in opciones_medio:
                    opciones_medio.append(medio_actual)

                medio = st.selectbox(
                    "Medio de entrega",
                    opciones_medio,
                    index=opciones_medio.index(medio_actual),
                    key=f"medio_material_cliente_{material_id}",
                )

                link_entrega = st.text_input(
                    "Link del video o archivo",
                    value=str(
                        row.get("link_entrega", "") or ""
                    ),
                    placeholder=(
                        "Pegá un enlace de Drive, WeTransfer, "
                        "Dropbox, Canva, etc."
                    ),
                    key=f"link_material_cliente_{material_id}",
                )

                comentario = st.text_area(
                    "Comentario para AM Consultora",
                    value=str(
                        row.get("comentario_cliente", "") or ""
                    ),
                    placeholder=(
                        "Ejemplo: falta una toma, lo grabé en dos partes, "
                        "necesito confirmar una indicación..."
                    ),
                    height=100,
                    key=f"comentario_material_cliente_{material_id}",
                )

                b1, b2 = st.columns(2)

                with b1:
                    if st.button(
                        "Guardar avance",
                        key=f"guardar_avance_material_{material_id}",
                        use_container_width=True,
                    ):
                        materiales_full = load_materiales()
                        mask = (
                            materiales_full["id"].astype(str)
                            == material_id
                        )

                        if not mask.any():
                            st.error("No se encontró el pedido.")
                        else:
                            materiales_full.loc[
                                mask, "medio_envio"
                            ] = medio
                            materiales_full.loc[
                                mask, "link_entrega"
                            ] = link_entrega.strip()
                            materiales_full.loc[
                                mask, "comentario_cliente"
                            ] = comentario.strip()

                            if estado == "Solicitado":
                                materiales_full.loc[
                                    mask, "estado"
                                ] = "En preparación"

                            materiales_full.loc[
                                mask, "fecha_actualizacion"
                            ] = date.today().strftime("%Y-%m-%d")
                            materiales_full.loc[
                                mask, "actualizado_por"
                            ] = st.session_state.get(
                                "name",
                                st.session_state.get(
                                    "username",
                                    "Cliente",
                                ),
                            )

                            save_csv(
                                materiales_full,
                                MATERIALES_PATH,
                            )
                            st.success("Avance guardado.")
                            st.rerun()

                with b2:
                    puede_entregar = bool(
                        link_entrega.strip()
                        or comentario.strip()
                        or medio in ["WhatsApp", "Mail"]
                    )

                    if st.button(
                        "Marcar como entregado",
                        key=f"entregar_material_{material_id}",
                        use_container_width=True,
                        disabled=not puede_entregar,
                    ):
                        materiales_full = load_materiales()
                        mask = (
                            materiales_full["id"].astype(str)
                            == material_id
                        )

                        if not mask.any():
                            st.error("No se encontró el pedido.")
                        else:
                            materiales_full.loc[
                                mask, "estado"
                            ] = "Enviado por cliente"
                            materiales_full.loc[
                                mask, "medio_envio"
                            ] = medio
                            materiales_full.loc[
                                mask, "link_entrega"
                            ] = link_entrega.strip()
                            materiales_full.loc[
                                mask, "comentario_cliente"
                            ] = comentario.strip()
                            materiales_full.loc[
                                mask, "fecha_envio_cliente"
                            ] = date.today().strftime("%Y-%m-%d")
                            materiales_full.loc[
                                mask, "fecha_actualizacion"
                            ] = date.today().strftime("%Y-%m-%d")
                            materiales_full.loc[
                                mask, "actualizado_por"
                            ] = st.session_state.get(
                                "name",
                                st.session_state.get(
                                    "username",
                                    "Cliente",
                                ),
                            )

                            save_csv(
                                materiales_full,
                                MATERIALES_PATH,
                            )
                            st.success(
                                "Material entregado para revisión."
                            )
                            st.rerun()

    st.markdown("### Historial de pedidos")

    if cerrados.empty:
        st.caption("Todavía no hay pedidos cerrados.")
    else:
        columnas_historial = [
            "solicitud",
            "fecha_limite",
            "estado",
            "medio_envio",
            "link_entrega",
            "fecha_envio_cliente",
        ]

        st.dataframe(
            cerrados[columnas_historial],
            use_container_width=True,
            hide_index=True,
        )



def render_campanias(cliente, campanias):
    header("Campañas publicitarias", f"Seguimiento de pauta | {cliente}")

    df = filter_cliente(campanias, cliente)

    if df.empty:
        st.info("No hay campañas cargadas.")
        return

    presupuesto = pd.to_numeric(df["presupuesto"], errors="coerce").fillna(0).sum()
    leads = pd.to_numeric(df["leads"], errors="coerce").fillna(0).sum()
    activas = df["estado"].astype(str).str.contains("Activa", case=False, na=False).sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Presupuesto", money(presupuesto))
    c2.metric("Consultas / leads", int(leads))
    c3.metric("Campañas activas", int(activas))

    st.markdown("### Campañas")

    for _, row in df.iterrows():
        with st.container(border=True):
            st.write(f"**{row.get('campania', '')}**")
            st.caption(f"{row.get('plataforma', '')} | Objetivo: {row.get('objetivo', '')}")
            st.markdown(status_badge(row.get("estado", "")), unsafe_allow_html=True)

            ca, cb, cc = st.columns(3)
            ca.metric("Presupuesto", money(row.get("presupuesto", 0)))
            cb.metric("Consultas", row.get("leads", 0))
            cc.metric("Costo por lead", money(row.get("costo_por_lead", 0)))

            if str(row.get("observacion", "")).strip():
                st.write(row.get("observacion", ""))



def render_reportes(cliente, reportes=None):
    import base64

    header("Reportería", f"Resultados mensuales y documentos | {cliente}")

    if reportes is None:
        df = load_reportes(cliente)
    else:
        df = filter_cliente(reportes, cliente)

    if df is None or df.empty:
        st.info("No hay reportes cargados.")
        return

    df = df.copy().fillna("")

    columnas = [
        "id",
        "cliente",
        "mes",
        "alcance",
        "interacciones",
        "consultas",
        "inversion",
        "estado",
        "que_funciono",
        "proximo_foco",
        "pdf_nombre",
        "pdf_tipo",
        "pdf_base64",
        "fecha_carga",
        "cargado_por",
    ]

    for col in columnas:
        if col not in df.columns:
            df[col] = ""

    opciones = []

    for idx, row in df.iterrows():
        mes = str(row.get("mes", "") or "Sin período")
        estado = str(row.get("estado", "") or "")
        etiqueta = f"{mes} · {estado}" if estado else mes
        opciones.append((idx, etiqueta))

    indice_sel = st.selectbox(
        "Seleccionar reporte",
        options=[item[0] for item in opciones],
        format_func=lambda valor: dict(opciones).get(valor, str(valor)),
        key=f"reporte_cliente_selector_{cliente}",
    )

    row = df.loc[indice_sel]

    mes = str(row.get("mes", "") or "Sin período")
    estado = str(row.get("estado", "") or "Sin estado")

    with st.container(border=True):
        c1, c2 = st.columns([3, 1])

        with c1:
            st.caption("REPORTE SELECCIONADO")
            st.markdown(f"## {mes}")

        with c2:
            st.info(estado)

    def numero_entero(valor):
        try:
            return int(float(valor or 0))
        except Exception:
            return 0

    def numero_decimal(valor):
        try:
            return float(valor or 0)
        except Exception:
            return 0.0

    alcance = numero_entero(row.get("alcance", 0))
    interacciones = numero_entero(row.get("interacciones", 0))
    consultas = numero_entero(row.get("consultas", 0))
    inversion = numero_decimal(row.get("inversion", 0))

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Alcance", f"{alcance:,}".replace(",", "."))
    k2.metric("Interacciones", f"{interacciones:,}".replace(",", "."))
    k3.metric("Consultas", consultas)
    k4.metric("Inversión", money(inversion))

    col_izq, col_der = st.columns([1, 1])

    with col_izq:
        st.markdown("### Lectura estratégica")

        with st.container(border=True):
            st.markdown("**Qué funcionó**")
            st.write(row.get("que_funciono", "") or "Sin información cargada.")

            st.markdown("**Próximo foco**")
            st.write(row.get("proximo_foco", "") or "Sin información cargada.")

    with col_der:
        st.markdown("### Documento del reporte")

        pdf_nombre = str(row.get("pdf_nombre", "") or "")
        pdf_tipo = str(row.get("pdf_tipo", "") or "application/pdf")
        pdf_base64 = str(row.get("pdf_base64", "") or "")

        if pdf_nombre and pdf_base64:
            try:
                pdf_bytes = base64.b64decode(pdf_base64)

                with st.container(border=True):
                    st.markdown(f"**{pdf_nombre}**")

                    fecha_carga = str(row.get("fecha_carga", "") or "")
                    if fecha_carga:
                        st.caption(f"Cargado el {fecha_carga}")

                    st.download_button(
                        "Descargar PDF",
                        data=pdf_bytes,
                        file_name=pdf_nombre,
                        mime=pdf_tipo,
                        use_container_width=True,
                        key=f"descargar_reporte_{row.get('id', indice_sel)}",
                    )

            except Exception:
                st.error("El archivo PDF guardado no pudo ser leído.")
        else:
            st.info("Este reporte no tiene un PDF adjunto.")

    st.markdown("### Historial")

    columnas_historial = [
        "mes",
        "alcance",
        "interacciones",
        "consultas",
        "inversion",
        "estado",
        "pdf_nombre",
    ]

    columnas_historial = [
        col for col in columnas_historial if col in df.columns
    ]

    st.dataframe(
        df[columnas_historial],
        use_container_width=True,
        hide_index=True,
    )



def render_gestion_clientes():
    header("Clientes", "Gestión, edición y baja de clientes existentes.")

    clientes_df = read_csv(
        CLIENTES_PATH,
        [
            "cliente",
            "rubro",
            "estado",
            "plan",
            "responsable_am",
            "fecha_inicio",
            "servicio_digital",
            "servicio_consultoria",
            "servicio_contabilidad",
            "notas",
        ],
    )

    if clientes_df is None or clientes_df.empty:
        st.info("No hay clientes cargados.")
        return

    for col in [
        "cliente",
        "rubro",
        "estado",
        "plan",
        "responsable_am",
        "fecha_inicio",
        "servicio_digital",
        "servicio_consultoria",
        "servicio_contabilidad",
        "notas",
    ]:
        if col not in clientes_df.columns:
            clientes_df[col] = ""

    st.markdown("### Resumen")

    activos = clientes_df["estado"].astype(str).str.contains("Activo", case=False, na=False).sum() if "estado" in clientes_df.columns else 0
    prospectos = clientes_df["estado"].astype(str).str.contains("Prospecto", case=False, na=False).sum() if "estado" in clientes_df.columns else 0
    pausados = clientes_df["estado"].astype(str).str.contains("Pausado", case=False, na=False).sum() if "estado" in clientes_df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total clientes", len(clientes_df))
    c2.metric("Activos", int(activos))
    c3.metric("Prospectos", int(prospectos))
    c4.metric("Pausados", int(pausados))

    st.markdown("### Editar clientes")

    st.caption(
        "El alta principal se hace desde Onboarding. Acá podés corregir datos, cambiar servicios, pausar o eliminar clientes."
    )

    # Normalizar tipos para que Streamlit permita editar columnas de texto sin errores.
    columnas_texto = [
        "cliente",
        "rubro",
        "estado",
        "plan",
        "responsable_am",
        "fecha_inicio",
        "servicio_digital",
        "servicio_consultoria",
        "servicio_contabilidad",
        "notas",
    ]

    for col in columnas_texto:
        if col in clientes_df.columns:
            clientes_df[col] = clientes_df[col].fillna("").astype(str)

    edited = st.data_editor(
        clientes_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "cliente": st.column_config.TextColumn("Cliente", required=True),
            "rubro": st.column_config.TextColumn("Rubro"),
            "estado": st.column_config.SelectboxColumn(
                "Estado",
                options=["Activo", "Prospecto", "Pausado", "Finalizado"],
                required=True,
            ),
            "plan": st.column_config.TextColumn("Plan / acuerdo"),
            "responsable_am": st.column_config.TextColumn("Responsable AM"),
            "fecha_inicio": st.column_config.TextColumn("Fecha inicio"),
            "servicio_digital": st.column_config.SelectboxColumn(
                "Ecosistema digital",
                options=["Sí", "No"],
                required=True,
            ),
            "servicio_consultoria": st.column_config.SelectboxColumn(
                "Consultoría",
                options=["Sí", "No"],
                required=True,
            ),
            "servicio_contabilidad": st.column_config.SelectboxColumn(
                "Cash Flow / gestión",
                options=["Sí", "No"],
                required=True,
            ),
            "notas": st.column_config.TextColumn("Notas"),
        },
        key="gestion_clientes_editor",
    )

    if st.button("Guardar cambios de clientes", use_container_width=True):
        save_csv(edited, CLIENTES_PATH)
        st.success("Clientes actualizados.")
        st.rerun()

    st.markdown("### Eliminar cliente")

    clientes_lista = sorted(clientes_df["cliente"].dropna().astype(str).unique().tolist())

    with st.form("form_eliminar_cliente"):
        cliente_eliminar = st.selectbox("Cliente a eliminar", clientes_lista)
        modo_baja = st.radio(
            "Tipo de baja",
            [
                "Solo eliminar de Clientes",
                "Eliminar cliente y datos vinculados",
            ],
            help="La segunda opción elimina también contenidos, materiales, campañas, reportes, objetivos, cash flow, asignaciones y usuarios cliente vinculados.",
        )

        confirmar = st.checkbox(f"Confirmo eliminar: {cliente_eliminar}")

        eliminar = st.form_submit_button("Eliminar cliente", use_container_width=True)

        if eliminar:
            if not confirmar:
                st.error("Marcá la confirmación antes de eliminar.")
                return

            cliente_eliminar = str(cliente_eliminar)

            clientes_nuevo = clientes_df[
                clientes_df["cliente"].astype(str) != cliente_eliminar
            ].copy()

            save_csv(clientes_nuevo, CLIENTES_PATH)

            if modo_baja == "Eliminar cliente y datos vinculados":
                archivos_cliente = [
                    CONTENIDOS_PATH,
                    MATERIALES_PATH,
                    CAMPANIAS_PATH,
                    REPORTES_PATH,
                    OBJETIVOS_PATH,
                    DOCUMENTOS_PATH,
                    INDICADORES_PATH,
                ]

                if "INDICADORES_MOVIMIENTOS_PATH" in globals():
                    archivos_cliente.append(INDICADORES_MOVIMIENTOS_PATH)

                if "ASIGNACIONES_EQUIPO_PATH" in globals():
                    archivos_cliente.append(ASIGNACIONES_EQUIPO_PATH)

                for archivo in archivos_cliente:
                    try:
                        df_archivo = pd.read_csv(archivo)

                        if "cliente" in df_archivo.columns:
                            df_archivo = df_archivo[
                                df_archivo["cliente"].astype(str) != cliente_eliminar
                            ].copy()
                            df_archivo.to_csv(archivo, index=False)
                    except Exception:
                        pass

                try:
                    usuarios_df = load_users_df()
                    if "cliente" in usuarios_df.columns:
                        usuarios_df = usuarios_df[
                            usuarios_df["cliente"].astype(str) != cliente_eliminar
                        ].copy()
                        save_users_df(usuarios_df)
                except Exception:
                    pass

            st.success("Cliente eliminado correctamente.")
            st.rerun()



def render_onboarding_cliente():
    header("Onboarding", "Alta integral de cliente, servicios contratados y usuario de acceso.")

    role = st.session_state.get("role", "")

    if role not in ["admin_general", "admin"]:
        st.error("No tenés permisos para acceder al onboarding.")
        return

    clientes_df = read_csv(
        CLIENTES_PATH,
        [
            "cliente",
            "rubro",
            "estado",
            "plan",
            "responsable_am",
            "fecha_inicio",
            "servicio_digital",
            "servicio_consultoria",
            "servicio_contabilidad",
            "notas",
        ],
    )

    usuarios_df = read_csv(
        USUARIOS_PATH,
        ["username", "password", "role", "name", "cliente", "activo"],
    )

    for col in ["servicio_digital", "servicio_consultoria", "servicio_contabilidad"]:
        if col not in clientes_df.columns:
            clientes_df[col] = "No"

    st.markdown("### Nuevo cliente")

    with st.form("form_onboarding_cliente"):
        st.markdown("#### Datos del cliente")

        c1, c2, c3 = st.columns(3)

        with c1:
            cliente = st.text_input("Nombre del cliente / marca")
            rubro = st.text_input("Rubro")

        with c2:
            estado = st.selectbox("Estado", ["Activo", "Prospecto", "Pausado", "Finalizado"], index=0)
            plan = st.text_input("Plan / acuerdo comercial")

        with c3:
            responsable_am = st.text_input("Responsable AM", value=st.session_state.get("name", "AM Consultora"))
            fecha_inicio = st.date_input("Fecha de inicio")

        st.markdown("#### Servicios contratados")

        s1, s2, s3 = st.columns(3)

        with s1:
            servicio_digital = st.checkbox("Ecosistema digital")

        with s2:
            servicio_consultoria = st.checkbox("Consultoría")

        with s3:
            servicio_contabilidad = st.checkbox("Contabilidad / gestión")

        notas = st.text_area("Notas internas")

        st.markdown("#### Equipo AM asignado")

        equipos_disponibles = usuarios_equipo_disponibles()
        equipo_asignado = st.multiselect(
            "Asignar este cliente a usuarios internos",
            equipos_disponibles,
            default=[st.session_state.get("username", "")] if st.session_state.get("username", "") in equipos_disponibles else [],
        )

        st.markdown("#### Acceso del cliente")

        crear_usuario = st.checkbox("Crear usuario de acceso para este cliente", value=True)

        u1, u2, u3 = st.columns(3)

        with u1:
            username = st.text_input(
                "Usuario",
                placeholder="Ejemplo: cliente_cooperativa",
                disabled=not crear_usuario,
            )

        with u2:
            password = st.text_input(
                "Contraseña inicial",
                placeholder="Ejemplo: cooperativa_2026",
                disabled=not crear_usuario,
            )

        with u3:
            name = st.text_input(
                "Nombre visible",
                placeholder="Ejemplo: Cooperativa Villa Adelina",
                disabled=not crear_usuario,
            )

        submitted = st.form_submit_button("Crear cliente y acceso", use_container_width=True)

        if submitted:
            cliente_limpio = cliente.strip()

            if not cliente_limpio:
                st.error("El nombre del cliente es obligatorio.")
                return

            if not servicio_digital and not servicio_consultoria and not servicio_contabilidad:
                st.error("Seleccioná al menos un servicio contratado.")
                return

            if "cliente" in clientes_df.columns:
                existe_cliente = clientes_df["cliente"].astype(str).str.strip().str.lower().eq(cliente_limpio.lower()).any()
            else:
                existe_cliente = False

            if existe_cliente:
                st.error("Ya existe un cliente con ese nombre. Revisá el menú Clientes o usá otro nombre.")
                return

            if crear_usuario:
                if not username.strip():
                    st.error("El usuario es obligatorio si vas a crear el acceso.")
                    return

                if not password.strip():
                    st.error("La contraseña es obligatoria si vas a crear el acceso.")
                    return

                usuario_limpio = username.strip()

                existe_usuario = usuarios_df["username"].astype(str).str.strip().str.lower().eq(usuario_limpio.lower()).any()

                if existe_usuario:
                    st.error("Ya existe un usuario con ese nombre. Elegí otro usuario.")
                    return

            nuevo_cliente = {
                "cliente": cliente_limpio,
                "rubro": rubro,
                "estado": estado,
                "plan": plan,
                "responsable_am": responsable_am,
                "fecha_inicio": fecha_inicio.strftime("%Y-%m-%d"),
                "servicio_digital": "Sí" if servicio_digital else "No",
                "servicio_consultoria": "Sí" if servicio_consultoria else "No",
                "servicio_contabilidad": "Sí" if servicio_contabilidad else "No",
                "notas": notas,
            }

            clientes_actualizado = pd.concat(
                [clientes_df, pd.DataFrame([nuevo_cliente])],
                ignore_index=True,
            )

            save_csv(clientes_actualizado, CLIENTES_PATH)

            if crear_usuario:
                nuevo_usuario = {
                    "username": username.strip(),
                    "password": password.strip(),
                    "role": "cliente",
                    "name": name.strip() if name.strip() else cliente_limpio,
                    "cliente": cliente_limpio,
                    "activo": "Sí",
                }

                usuarios_actualizado = pd.concat(
                    [usuarios_df, pd.DataFrame([nuevo_usuario])],
                    ignore_index=True,
                )

                save_csv(usuarios_actualizado, USUARIOS_PATH)

            asignaciones_df = cargar_asignaciones_equipo()
            nuevas_asignaciones = []
            next_id = siguiente_id_asignacion(asignaciones_df)

            for usuario_equipo in equipo_asignado:
                nuevas_asignaciones.append({
                    "id": next_id,
                    "username": usuario_equipo,
                    "cliente": cliente_limpio,
                    "activo": "Sí",
                })
                next_id += 1

            if nuevas_asignaciones:
                asignaciones_actualizado = pd.concat(
                    [asignaciones_df, pd.DataFrame(nuevas_asignaciones)],
                    ignore_index=True,
                )
                save_csv(asignaciones_actualizado, ASIGNACIONES_EQUIPO_PATH)

            st.success("Cliente creado correctamente, acceso vinculado y equipo asignado.")
            st.rerun()

    st.markdown("### Últimos clientes cargados")

    if clientes_df is None or clientes_df.empty:
        st.info("Todavía no hay clientes cargados.")
    else:
        columnas = [
            "cliente",
            "estado",
            "plan",
            "responsable_am",
            "servicio_digital",
            "servicio_consultoria",
            "servicio_contabilidad",
        ]
        columnas = [c for c in columnas if c in clientes_df.columns]

        st.dataframe(
            clientes_df[columnas].tail(10),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("### Usuarios cliente activos")

    if usuarios_df is None or usuarios_df.empty:
        st.info("Todavía no hay usuarios cargados.")
    else:
        vista_usuarios = usuarios_df.copy()

        if "role" in vista_usuarios.columns:
            vista_usuarios = vista_usuarios[vista_usuarios["role"].astype(str) == "cliente"]

        columnas_u = ["username", "name", "cliente", "activo"]
        columnas_u = [c for c in columnas_u if c in vista_usuarios.columns]

        st.dataframe(
            vista_usuarios[columnas_u].tail(10),
            use_container_width=True,
            hide_index=True,
        )



def render_usuarios(clientes):
    header("Usuarios", "Alta, edición y permisos de acceso al portal")

    df = load_users_df()

    st.markdown(
        """
        <div style="
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 22px;
            padding: 22px 26px;
            margin-bottom: 22px;
            box-shadow: 0 12px 30px rgba(16, 24, 40, 0.05);
        ">
            <div style="font-size:1.2rem; font-weight:850; color:#172033; margin-bottom:6px;">
                Gestión de accesos
            </div>
            <div style="font-size:0.95rem; color:#667085; line-height:1.45;">
                Creá usuarios para clientes y asistentes. Los usuarios cliente ven solo su portal; los asistentes pueden cargar y gestionar información interna.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Usuarios activos", len(df[df["activo"].astype(str).str.lower().isin(["sí", "si", "activo", "true", "1"])]))
    c2.metric("Clientes", len(df[df["role"] == "cliente"]))
    c3.metric("Equipo AM", len(df[df["role"].isin(["admin_general", "admin", "equipo"])]))

    st.markdown("### Crear nuevo usuario")

    clientes_lista = [""]
    if clientes is not None and not clientes.empty and "cliente" in clientes.columns:
        clientes_lista += sorted(clientes["cliente"].dropna().astype(str).unique().tolist())

    with st.form("crear_usuario_form"):
        col1, col2, col3 = st.columns(3)

        with col1:
            username = st.text_input("Usuario")
            name = st.text_input("Nombre visible")

        with col2:
            password = st.text_input("Contraseña")
            role = st.selectbox("Rol", ["cliente", "equipo", "admin", "admin_general"])

        with col3:
            cliente = st.selectbox("Cliente asociado solo si el rol es cliente", clientes_lista)
            activo = st.selectbox("Activo", ["Sí", "No"])

        st.markdown("#### Permisos para equipo interno")
        st.info("Los permisos del equipo se calculan según los clientes asignados. La asignación se gestiona más abajo.")
        permiso_todos = False
        permiso_digital = False
        permiso_consultoria = False
        permiso_contabilidad = False

        crear = st.form_submit_button("Crear usuario")

        if crear:
            username = username.strip()

            if not username:
                st.error("El usuario no puede estar vacío.")
            elif username in df["username"].astype(str).tolist():
                st.error("Ya existe un usuario con ese nombre.")
            elif role == "cliente" and not cliente:
                st.error("Los usuarios cliente deben tener un cliente asociado.")
            else:
                nuevo = pd.DataFrame([
                    {
                        "username": username,
                        "password": password,
                        "role": role,
                        "name": name,
                        "cliente": cliente,
                        "activo": activo,
                        "permiso_todos": "Sí" if permiso_todos else "No",
                        "permiso_digital": "Sí" if permiso_digital else "No",
                        "permiso_consultoria": "Sí" if permiso_consultoria else "No",
                        "permiso_contabilidad": "Sí" if permiso_contabilidad else "No",
                    }
                ])

                df = pd.concat([df, nuevo], ignore_index=True)
                save_users_df(df)
                st.success("Usuario creado correctamente.")
                st.rerun()

    st.markdown("### Baja rápida de usuarios")

    usuarios_eliminables = []
    if df is not None and not df.empty and "username" in df.columns:
        usuarios_eliminables = sorted(df["username"].dropna().astype(str).unique().tolist())

    with st.form("form_baja_usuario"):
        usuario_baja = st.selectbox("Usuario", usuarios_eliminables)
        accion_usuario = st.radio(
            "Acción",
            ["Desactivar usuario", "Eliminar usuario definitivamente"],
        )
        confirmar_usuario = st.checkbox(f"Confirmo la acción sobre el usuario: {usuario_baja}")

        ejecutar_baja = st.form_submit_button("Aplicar acción sobre usuario", use_container_width=True)

        if ejecutar_baja:
            if not confirmar_usuario:
                st.error("Marcá la confirmación antes de aplicar la acción.")
            elif usuario_baja == st.session_state.get("username", "") and accion_usuario == "Eliminar usuario definitivamente":
                st.error("No podés eliminar tu propio usuario desde esta pantalla.")
            else:
                df_actualizado = df.copy()

                if accion_usuario == "Desactivar usuario":
                    df_actualizado.loc[
                        df_actualizado["username"].astype(str) == str(usuario_baja),
                        "activo"
                    ] = "No"
                else:
                    df_actualizado = df_actualizado[
                        df_actualizado["username"].astype(str) != str(usuario_baja)
                    ].copy()

                    if "ASIGNACIONES_EQUIPO_PATH" in globals():
                        try:
                            asignaciones = cargar_asignaciones_equipo()
                            asignaciones = asignaciones[
                                asignaciones["username"].astype(str) != str(usuario_baja)
                            ].copy()
                            save_csv(asignaciones, ASIGNACIONES_EQUIPO_PATH)
                        except Exception:
                            pass

                save_users_df(df_actualizado)
                st.success("Usuario actualizado correctamente.")
                st.rerun()


    st.markdown("### Editar usuarios existentes")

    st.caption("Para desactivar un usuario, cambiá Activo a No. Evitá borrar tu propio usuario admin.")

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "username": st.column_config.TextColumn("Usuario", required=True),
            "password": st.column_config.TextColumn("Contraseña"),
            "role": st.column_config.SelectboxColumn("Rol", options=["admin_general", "admin", "equipo", "cliente"], required=True),
            "name": st.column_config.TextColumn("Nombre visible"),
            "cliente": st.column_config.SelectboxColumn("Cliente asociado solo para rol cliente", options=clientes_lista),
            "activo": st.column_config.SelectboxColumn("Activo", options=["Sí", "No"], required=True),
            "permiso_todos": st.column_config.SelectboxColumn("Todos los servicios", options=["Sí", "No"], required=True),
            "permiso_digital": st.column_config.SelectboxColumn("Ecosistema digital", options=["Sí", "No"], required=True),
            "permiso_consultoria": st.column_config.SelectboxColumn("Consultoría", options=["Sí", "No"], required=True),
            "permiso_contabilidad": st.column_config.SelectboxColumn("Contabilidad / gestión", options=["Sí", "No"], required=True),
        },
        key="usuarios_editor",
    )

    if st.button("Guardar cambios de usuarios"):
        save_users_df(edited)
        st.success("Usuarios actualizados.")
        st.rerun()

    st.markdown("### Asignaciones de equipo por cliente")

    asignaciones_df = cargar_asignaciones_equipo()

    equipos_lista = usuarios_equipo_disponibles()

    clientes_activos = clientes.copy()
    if clientes_activos is not None and not clientes_activos.empty and "estado" in clientes_activos.columns:
        clientes_activos = clientes_activos[clientes_activos["estado"].astype(str).isin(["Activo", "Prospecto"])]

    clientes_asignables = []
    if clientes_activos is not None and not clientes_activos.empty and "cliente" in clientes_activos.columns:
        clientes_asignables = sorted(clientes_activos["cliente"].dropna().astype(str).unique().tolist())

    with st.form("form_asignar_clientes_equipo"):
        a1, a2 = st.columns(2)

        with a1:
            usuario_equipo = st.selectbox("Usuario interno", equipos_lista)

        with a2:
            clientes_seleccionados = st.multiselect("Clientes asignados", clientes_asignables)

        guardar_asignacion = st.form_submit_button("Guardar asignaciones", use_container_width=True)

        if guardar_asignacion:
            if not usuario_equipo:
                st.error("Seleccioná un usuario interno.")
            else:
                base = asignaciones_df.copy()

                # Desactivar asignaciones previas de ese usuario.
                if not base.empty:
                    base.loc[base["username"].astype(str) == str(usuario_equipo), "activo"] = "No"

                next_id = siguiente_id_asignacion(base)
                nuevas = []

                existentes = set(
                    zip(
                        base["username"].astype(str),
                        base["cliente"].astype(str),
                    )
                ) if not base.empty else set()

                for cliente_sel in clientes_seleccionados:
                    par = (usuario_equipo, cliente_sel)

                    if par in existentes:
                        base.loc[
                            (base["username"].astype(str) == str(usuario_equipo))
                            & (base["cliente"].astype(str) == str(cliente_sel)),
                            "activo"
                        ] = "Sí"
                    else:
                        nuevas.append({
                            "id": next_id,
                            "username": usuario_equipo,
                            "cliente": cliente_sel,
                            "activo": "Sí",
                        })
                        next_id += 1

                if nuevas:
                    base = pd.concat([base, pd.DataFrame(nuevas)], ignore_index=True)

                save_csv(base, ASIGNACIONES_EQUIPO_PATH)
                st.success("Asignaciones actualizadas.")
                st.rerun()

    if asignaciones_df is None or asignaciones_df.empty:
        st.info("Todavía no hay asignaciones de equipo.")
    else:
        st.dataframe(
            asignaciones_df.sort_values(["username", "cliente"]),
            use_container_width=True,
            hide_index=True,
        )






def render_edicion_rapida(clientes, contenidos, materiales, campanias, reportes, tareas):
    header("Edición rápida", "Panel general para modificar datos operativos del portal.")

    role = st.session_state.get("role", "")

    if role not in ["admin_general", "admin"]:
        st.error("No tenés permisos para acceder a edición rápida.")
        return

    st.warning(
        "Este panel permite editar datos en tabla. Usalo para correcciones rápidas, altas masivas o ajustes operativos."
    )

    tabs = st.tabs([
        "Usuarios",
        "Clientes",
        "Contenidos",
        "Materiales",
        "Campañas",
        "Reportes",
        "Tareas",
    ])

    with tabs[0]:
        st.markdown("### Usuarios")
        usuarios_df = load_users_df()

        clientes_lista = [""]
        if clientes is not None and not clientes.empty and "cliente" in clientes.columns:
            clientes_lista += sorted(clientes["cliente"].dropna().astype(str).unique().tolist())

        edited = st.data_editor(
            usuarios_df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "username": st.column_config.TextColumn("Usuario", required=True),
                "password": st.column_config.TextColumn("Contraseña"),
                "role": st.column_config.SelectboxColumn(
                    "Rol",
                    options=["admin_general", "admin", "equipo", "cliente"],
                    required=True,
                ),
                "name": st.column_config.TextColumn("Nombre visible"),
                "cliente": st.column_config.SelectboxColumn("Cliente asociado", options=clientes_lista),
                "activo": st.column_config.SelectboxColumn("Activo", options=["Sí", "No"], required=True),
            },
            key="editor_rapido_usuarios",
        )

        if st.button("Guardar usuarios", use_container_width=True, key="guardar_rapido_usuarios"):
            save_users_df(edited)
            st.success("Usuarios guardados.")
            st.rerun()

    with tabs[1]:
        st.markdown("### Clientes")
        edited = st.data_editor(
            clientes,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="editor_rapido_clientes",
        )

        if st.button("Guardar clientes", use_container_width=True, key="guardar_rapido_clientes"):
            save_csv(edited, CLIENTES_PATH)
            st.success("Clientes guardados.")
            st.rerun()

    with tabs[2]:
        st.markdown("### Contenidos")
        edited = st.data_editor(
            contenidos,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="editor_rapido_contenidos",
        )

        if st.button("Guardar contenidos", use_container_width=True, key="guardar_rapido_contenidos"):
            save_csv(edited, CONTENIDOS_PATH)
            st.success("Contenidos guardados.")
            st.rerun()

    with tabs[3]:
        st.markdown("### Materiales")
        edited = st.data_editor(
            materiales,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="editor_rapido_materiales",
        )

        if st.button("Guardar materiales", use_container_width=True, key="guardar_rapido_materiales"):
            save_csv(edited, MATERIALES_PATH)
            st.success("Materiales guardados.")
            st.rerun()

    with tabs[4]:
        st.markdown("### Campañas")
        edited = st.data_editor(
            campanias,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="editor_rapido_campanias",
        )

        if st.button("Guardar campañas", use_container_width=True, key="guardar_rapido_campanias"):
            save_csv(edited, CAMPANIAS_PATH)
            st.success("Campañas guardadas.")
            st.rerun()

    with tabs[5]:
        st.markdown("### Reportes")
        edited = st.data_editor(
            reportes,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="editor_rapido_reportes",
        )

        if st.button("Guardar reportes", use_container_width=True, key="guardar_rapido_reportes"):
            save_csv(edited, REPORTES_PATH)
            st.success("Reportes guardados.")
            st.rerun()

    with tabs[6]:
        st.markdown("### Tareas")
        edited = st.data_editor(
            tareas,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="editor_rapido_tareas",
        )

        if st.button("Guardar tareas", use_container_width=True, key="guardar_rapido_tareas"):
            save_csv(edited, TAREAS_PATH)
            st.success("Tareas guardadas.")
            st.rerun()



def cargar_objetivos(cliente=""):
    columns = [
        "id", "cliente", "servicio", "mes", "objetivo", "descripcion",
        "responsable_am", "responsable_cliente", "prioridad", "estado",
        "avance", "proxima_accion", "fecha_limite", "comentarios"
    ]

    if cliente:
        return read_csv_cliente(OBJETIVOS_PATH, columns, cliente)

    return read_csv(OBJETIVOS_PATH, columns)


def cargar_documentos():
    return read_csv(
        DOCUMENTOS_PATH,
        [
            "id", "cliente", "servicio", "categoria", "nombre", "link",
            "estado", "fecha", "observacion"
        ],
    )


def cargar_indicadores():
    return read_csv(
        INDICADORES_PATH,
        [
            "id", "cliente", "mes", "facturacion", "gastos", "inversiones",
            "resultado_estimado", "objetivo_facturacion", "objetivo_gastos",
            "objetivos_mes", "observacion_am", "observacion_cliente", "estado"
        ],
    )


def puede_ver_cuenta_corriente():
    role = st.session_state.get("role", "")
    username = st.session_state.get("username", "")

    # El cliente ve únicamente su propia cuenta corriente.
    if role == "cliente":
        return True

    # Alan / admin general puede ver y gestionar cuenta corriente.
    if role == "admin_general":
        return True

    # Fallback por si Alan quedó logueado con role admin.
    if username == "alan":
        return True

    return False



def render_resumen_cuenta_corriente_inicio(cliente):
    if not puede_ver_cuenta_corriente():
        return

    columnas = [
        "id",
        "cliente",
        "mes",
        "concepto",
        "servicio",
        "importe",
        "estado",
        "fecha_factura",
        "fecha_pago",
        "observacion",
        "comprobante_nombre",
        "comprobante_tipo",
        "comprobante_base64",
        "fecha_carga",
        "cargado_por",
    ]

    cuenta = read_csv_cliente(CUENTA_CORRIENTE_PATH, columnas, cliente)

    def formato_pesos(valor):
        try:
            return f"$ {float(valor):,.0f}".replace(",", ".")
        except Exception:
            return "$ 0"

    if cuenta is None or cuenta.empty:
        saldo_adeudado = 0
        movimientos_pendientes = 0
        resumen_servicios = pd.DataFrame(columns=["servicio", "importe"])
    else:
        cuenta = cuenta.copy().fillna("")

        if "servicio" not in cuenta.columns:
            cuenta["servicio"] = "General"

        cuenta["servicio"] = cuenta["servicio"].replace("", "General")
        cuenta["importe"] = pd.to_numeric(cuenta["importe"], errors="coerce").fillna(0)

        estados_sin_deuda = ["Pagado", "Bonificado"]
        pendientes = cuenta[
            ~cuenta["estado"].astype(str).isin(estados_sin_deuda)
        ].copy()

        saldo_adeudado = pendientes["importe"].sum()
        movimientos_pendientes = len(pendientes)

        if pendientes.empty:
            resumen_servicios = pd.DataFrame(columns=["servicio", "importe"])
        else:
            resumen_servicios = (
                pendientes
                .groupby("servicio", dropna=False)["importe"]
                .sum()
                .reset_index()
                .sort_values("importe", ascending=False)
            )

    if saldo_adeudado > 0:
        estado_label = "Pendiente de pago"
        boton_label = "Registrar pago"
        detalle = f"{movimientos_pendientes} movimiento(s) pendiente(s)"
    else:
        estado_label = "Al día"
        boton_label = "Ver cuenta corriente"
        detalle = "Sin saldo adeudado"

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2.1, 1.4, 2.3, 1.5])

        with c1:
            st.caption("CUENTA CORRIENTE")
            st.markdown("**Saldo adeudado**")

        with c2:
            st.markdown(f"### {formato_pesos(saldo_adeudado)}")
            st.caption(detalle)

        with c3:
            if not resumen_servicios.empty:
                servicios_txt = []
                for _, row in resumen_servicios.iterrows():
                    servicio = str(row.get("servicio", "") or "General")
                    importe_servicio = formato_pesos(row.get("importe", 0))
                    servicios_txt.append(f"{servicio}: {importe_servicio}")
                st.caption("Detalle por servicio")
                st.write(" · ".join(servicios_txt))
            else:
                st.caption("Detalle por servicio")
                st.write("Sin deuda por servicio")

        with c4:
            if saldo_adeudado > 0:
                st.warning(estado_label)
            else:
                st.success(estado_label)

            if st.button(boton_label, use_container_width=True, key=f"btn_registrar_pago_inicio_{cliente}"):
                st.session_state["menu_cliente_destino"] = "Cuenta corriente"
                st.rerun()



def render_inicio_cliente_ejecutivo(cliente):
    header("Inicio", f"Panel ejecutivo | {cliente}")

    # ------------------------------------------------------------
    # Cuenta corriente: solo cliente/admin, no equipo.
    # ------------------------------------------------------------
    render_resumen_cuenta_corriente_inicio(cliente)

    servicios = servicios_activos_cliente(cliente)

    # ------------------------------------------------------------
    # Servicios activos.
    # ------------------------------------------------------------
    servicios_visibles = []

    if servicios.get("digital"):
        servicios_visibles.append("Ecosistema digital")

    if servicios.get("consultoria"):
        servicios_visibles.append("Consultoría")

    if servicios.get("contabilidad"):
        servicios_visibles.append("Contabilidad / gestión")

    if servicios_visibles:
        st.markdown("### Servicios activos")
        cols_servicios = st.columns(len(servicios_visibles))

        for idx, servicio in enumerate(servicios_visibles):
            with cols_servicios[idx]:
                with st.container(border=True):
                    st.caption("Servicio contratado")
                    st.markdown(f"**{servicio}**")

    # ------------------------------------------------------------
    # Carga de datos del cliente.
    # ------------------------------------------------------------
    columnas_objetivos = [
        "id",
        "cliente",
        "mes",
        "objetivo",
        "descripcion",
        "responsable",
        "prioridad",
        "estado",
        "avance",
        "checklist",
        "fecha_limite",
        "comentarios",
        "fecha_carga",
        "creado_por",
        "fecha_actualizacion",
        "actualizado_por",
    ]

    columnas_contenidos = [
        "id",
        "cliente",
        "mes",
        "tipo",
        "titulo",
        "copy",
        "fecha",
        "estado",
        "observaciones",
    ]

    columnas_materiales = [
        "id",
        "cliente",
        "titulo",
        "descripcion",
        "link",
        "estado",
        "fecha_carga",
        "observaciones",
    ]

    objetivos = read_csv_cliente(OBJETIVOS_PATH, columnas_objetivos, cliente)
    contenidos = read_csv_cliente(CONTENIDOS_PATH, columnas_contenidos, cliente)
    materiales = read_csv_cliente(MATERIALES_PATH, columnas_materiales, cliente)

    if objetivos is None or objetivos.empty:
        objetivos = pd.DataFrame(columns=columnas_objetivos)
    else:
        objetivos = objetivos.copy().fillna("")

    if contenidos is None or contenidos.empty:
        contenidos = pd.DataFrame(columns=columnas_contenidos)
    else:
        contenidos = contenidos.copy().fillna("")

    if materiales is None or materiales.empty:
        materiales = pd.DataFrame(columns=columnas_materiales)
    else:
        materiales = materiales.copy().fillna("")

    for col in columnas_objetivos:
        if col not in objetivos.columns:
            objetivos[col] = ""

    for col in columnas_contenidos:
        if col not in contenidos.columns:
            contenidos[col] = ""

    for col in columnas_materiales:
        if col not in materiales.columns:
            materiales[col] = ""

    objetivos = objetivos[columnas_objetivos].fillna("")
    contenidos = contenidos[columnas_contenidos].fillna("")
    materiales = materiales[columnas_materiales].fillna("")

    objetivos["avance"] = pd.to_numeric(objetivos["avance"], errors="coerce").fillna(0)
    objetivos["estado"] = objetivos["estado"].astype(str).replace("", "Pendiente")

    objetivos_activos = objetivos[
        ~objetivos["estado"].astype(str).isin(["Finalizado", "Finalizada"])
    ].copy()

    avance_promedio = 0
    if not objetivos.empty:
        avance_promedio = int(objetivos["avance"].mean())

    aprobaciones_pendientes = 0
    if not contenidos.empty and "estado" in contenidos.columns:
        aprobaciones_pendientes = len(
            contenidos[
                contenidos["estado"].astype(str).str.lower().isin(
                    ["pendiente", "pendiente de aprobación", "en revisión", "a aprobar"]
                )
            ]
        )

    materiales_pendientes = 0
    if not materiales.empty and "estado" in materiales.columns:
        materiales_pendientes = len(
            materiales[
                materiales["estado"].astype(str).str.lower().isin(
                    ["pendiente", "solicitado", "faltante", "a enviar"]
                )
            ]
        )

    # ------------------------------------------------------------
    # Resumen operativo.
    # ------------------------------------------------------------
    st.markdown("### Resumen operativo")

    k1, k2, k3, k4 = st.columns(4)

    with k1:
        with st.container(border=True):
            st.caption("Objetivos activos")
            st.markdown(f"## {len(objetivos_activos)}")

    with k2:
        with st.container(border=True):
            st.caption("Avance promedio")
            st.markdown(f"## {avance_promedio}%")

    with k3:
        with st.container(border=True):
            st.caption("Aprobaciones pendientes")
            st.markdown(f"## {aprobaciones_pendientes}")

    with k4:
        with st.container(border=True):
            st.caption("Materiales pendientes")
            st.markdown(f"## {materiales_pendientes}")

    # ------------------------------------------------------------
    # Próximas acciones + pendientes digitales.
    # ------------------------------------------------------------
    col_acciones, col_digital = st.columns([1.2, 1])

    with col_acciones:
        st.markdown("### Próximas acciones")

        if objetivos_activos.empty:
            st.info("No hay próximas acciones cargadas.")
        else:
            proximos = objetivos_activos.copy()

            if "fecha_limite" in proximos.columns:
                proximos = proximos.sort_values("fecha_limite", ascending=True)

            proximos = proximos.head(3)

            for _, row in proximos.iterrows():
                objetivo_txt = str(row.get("objetivo", "") or "Sin objetivo")
                descripcion_txt = str(row.get("descripcion", "") or "")
                estado_txt = str(row.get("estado", "") or "Pendiente")
                prioridad_txt = str(row.get("prioridad", "") or "Media")
                fecha_limite_txt = str(row.get("fecha_limite", "") or "")
                avance_val = int(float(row.get("avance", 0) or 0))

                with st.container(border=True):
                    st.markdown(f"**{objetivo_txt}**")

                    if descripcion_txt:
                        st.write(descripcion_txt)

                    st.caption(f"Estado: {estado_txt} · Prioridad: {prioridad_txt} · Límite: {fecha_limite_txt}")
                    st.progress(avance_val / 100)
                    st.caption(f"Avance: {avance_val}%")

    with col_digital:
        st.markdown("### Pendientes digitales")

        pendientes = []

        if aprobaciones_pendientes > 0:
            pendientes.append(f"{aprobaciones_pendientes} aprobación(es) pendiente(s).")

        if materiales_pendientes > 0:
            pendientes.append(f"{materiales_pendientes} material(es) pendiente(s).")

        if pendientes:
            for item in pendientes:
                st.warning(item)
        else:
            st.success("No hay pendientes digitales críticos.")



def parsear_checklist_objetivo(valor):
    import json

    if valor is None:
        return []

    if isinstance(valor, list):
        return valor

    texto = str(valor).strip()

    if not texto:
        return []

    try:
        data = json.loads(texto)
        if isinstance(data, list):
            normalizado = []
            for item in data:
                if isinstance(item, dict):
                    normalizado.append({
                        "texto": str(item.get("texto", "")).strip(),
                        "hecho": bool(item.get("hecho", False)),
                    })
                else:
                    normalizado.append({
                        "texto": str(item).strip(),
                        "hecho": False,
                    })
            return [i for i in normalizado if i.get("texto")]
    except Exception:
        pass

    items = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue

        hecho = False

        if linea.lower().startswith(("[x]", "x ", "✅", "☑")):
            hecho = True
            linea = linea.replace("[x]", "", 1).replace("✅", "", 1).replace("☑", "", 1).strip()
        elif linea.lower().startswith(("[ ]", "- [ ]", "☐")):
            linea = linea.replace("[ ]", "", 1).replace("- [ ]", "", 1).replace("☐", "", 1).strip()
        elif linea.startswith("-"):
            linea = linea[1:].strip()

        if linea:
            items.append({"texto": linea, "hecho": hecho})

    return items


def serializar_checklist_objetivo(items):
    import json

    normalizado = []

    for item in items or []:
        if isinstance(item, dict):
            texto = str(item.get("texto", "")).strip()
            hecho = bool(item.get("hecho", False))
        else:
            texto = str(item).strip()
            hecho = False

        if texto:
            normalizado.append({"texto": texto, "hecho": hecho})

    return json.dumps(normalizado, ensure_ascii=False)


def avance_desde_checklist_objetivo(items, avance_manual=0):
    items = items or []

    if not items:
        try:
            return int(float(avance_manual or 0))
        except Exception:
            return 0

    total = len(items)
    hechos = sum(1 for item in items if bool(item.get("hecho", False)))

    if total == 0:
        return 0

    return int(round((hechos / total) * 100))


def checklist_desde_textarea_objetivo(texto):
    items = []

    for linea in str(texto or "").splitlines():
        linea = linea.strip()
        if not linea:
            continue

        if linea.startswith("-"):
            linea = linea[1:].strip()

        if linea:
            items.append({"texto": linea, "hecho": False})

    return items



def render_objetivos(cliente="", modo="cliente"):
    role = st.session_state.get("role", "")
    username = st.session_state.get("username", "")
    nombre_usuario = st.session_state.get("name", username)

    if modo == "admin":
        header("Objetivos", "Plan de trabajo y seguimiento por cliente.")
    else:
        header("Objetivos", f"Plan de trabajo | {cliente}")

    columnas = [
        "id",
        "cliente",
        "mes",
        "objetivo",
        "descripcion",
        "responsable",
        "prioridad",
        "estado",
        "avance",
        "checklist",
        "fecha_limite",
        "comentarios",
        "fecha_carga",
        "creado_por",
        "fecha_actualizacion",
        "actualizado_por",
    ]

    if cliente:
        objetivos = read_csv_cliente(OBJETIVOS_PATH, columnas, cliente)
    else:
        objetivos = read_csv(OBJETIVOS_PATH, columnas)

    if objetivos is None or objetivos.empty:
        objetivos = pd.DataFrame(columns=columnas)

    objetivos = objetivos.copy().fillna("")

    for col in columnas:
        if col not in objetivos.columns:
            objetivos[col] = ""

    objetivos = objetivos[columnas].fillna("")

    objetivos["cliente"] = objetivos["cliente"].astype(str).str.strip()
    objetivos["objetivo"] = objetivos["objetivo"].astype(str).str.strip()
    objetivos["estado"] = objetivos["estado"].astype(str).str.strip().replace("", "Pendiente")
    objetivos["prioridad"] = objetivos["prioridad"].astype(str).str.strip().replace("", "Media")
    objetivos["responsable"] = objetivos["responsable"].astype(str).str.strip().replace("", "AM Consultora")
    objetivos["avance"] = pd.to_numeric(objetivos["avance"], errors="coerce").fillna(0).clip(0, 100)

    estados = ["Pendiente", "En curso", "En revisión", "Finalizado", "Pausado"]
    prioridades = ["Alta", "Media", "Baja"]

    # ------------------------------------------------------------
    # Alta de objetivo: admin general o equipo.
    # El equipo solo puede crear objetivos para clientes asignados.
    # ------------------------------------------------------------
    puede_crear_objetivos = modo == "admin" or role in ["admin_general", "admin", "equipo"]

    if puede_crear_objetivos:
        if role == "equipo":
            if cliente:
                clientes_opciones = [cliente]
            else:
                clientes_opciones = clientes_visibles_para_usuario()
        else:
            clientes_df = load_clientes()

            if clientes_df is None or clientes_df.empty or "cliente" not in clientes_df.columns:
                clientes_opciones = []
            else:
                clientes_opciones = sorted(clientes_df["cliente"].dropna().astype(str).unique().tolist())

        with st.expander("Crear nuevo objetivo", expanded=False):
            if not clientes_opciones:
                st.info("No hay clientes cargados.")
            else:
                with st.form("form_nuevo_objetivo"):
                    c1, c2 = st.columns([2, 1])

                    with c1:
                        if role == "equipo" and cliente:
                            cliente_sel = cliente
                            st.text_input("Cliente", value=cliente_sel, disabled=True)
                        else:
                            cliente_sel = st.selectbox("Cliente", clientes_opciones)

                        objetivo_txt = st.text_input("Objetivo", placeholder="Ejemplo: análisis de régimen PADIC")
                        descripcion = st.text_area("Descripción", placeholder="Detalle del objetivo, alcance o entregable esperado.")
                        checklist_txt = st.text_area(
                            "Checklist / workflow",
                            placeholder="Un paso por línea. Ejemplo:\nRelevar información inicial\nAnalizar normativa\nPreparar informe\nRevisar con cliente",
                            height=140,
                        )

                    with c2:
                        mes_ref = st.text_input("Mes", value=date.today().strftime("%Y-%m"))
                        responsable = st.text_input("Responsable", value="AM Consultora")
                        prioridad = st.selectbox("Prioridad", prioridades, index=1)
                        estado = st.selectbox("Estado inicial", estados)
                        fecha_limite = st.date_input("Fecha límite", value=date.today())

                    crear = st.form_submit_button("Crear objetivo", use_container_width=True)

                    if crear:
                        if not objetivo_txt.strip():
                            st.error("El objetivo no puede estar vacío.")
                        else:
                            checklist_items = checklist_desde_textarea_objetivo(checklist_txt)
                            avance_auto = avance_desde_checklist_objetivo(checklist_items, 0)

                            nuevo = {
                                "id": f"OBJ-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}",
                                "cliente": cliente_sel,
                                "mes": mes_ref.strip(),
                                "objetivo": objetivo_txt.strip(),
                                "descripcion": descripcion.strip(),
                                "responsable": responsable.strip() or "AM Consultora",
                                "prioridad": prioridad,
                                "estado": estado,
                                "avance": avance_auto,
                                "checklist": serializar_checklist_objetivo(checklist_items),
                                "fecha_limite": fecha_limite.strftime("%Y-%m-%d"),
                                "comentarios": "",
                                "fecha_carga": date.today().strftime("%Y-%m-%d"),
                                "creado_por": nombre_usuario,
                                "fecha_actualizacion": date.today().strftime("%Y-%m-%d"),
                                "actualizado_por": nombre_usuario,
                            }

                            objetivos_full = read_csv(OBJETIVOS_PATH, columnas)
                            if objetivos_full is None or objetivos_full.empty:
                                objetivos_full = pd.DataFrame(columns=columnas)

                            for col in columnas:
                                if col not in objetivos_full.columns:
                                    objetivos_full[col] = ""

                            actualizado = pd.concat(
                                [objetivos_full[columnas], pd.DataFrame([nuevo])],
                                ignore_index=True,
                            )
                            save_csv(actualizado, OBJETIVOS_PATH)
                            st.success("Objetivo creado correctamente.")
                            st.rerun()

    # ------------------------------------------------------------
    # Filtros.
    # ------------------------------------------------------------
    objetivos_vista = objetivos.copy()

    if cliente:
        objetivos_vista = objetivos_vista[
            objetivos_vista["cliente"].astype(str) == str(cliente)
        ].copy()

    f1, f2, f3 = st.columns([1.4, 1.2, 1])

    with f1:
        if modo == "admin":
            clientes_lista = sorted(objetivos_vista["cliente"].dropna().astype(str).unique().tolist())
            cliente_filtro = st.selectbox(
                "Cliente",
                ["Todos"] + clientes_lista,
                key=f"objetivos_cliente_filtro_{modo}_{cliente or 'admin'}",
            )

            if cliente_filtro != "Todos":
                objetivos_vista = objetivos_vista[
                    objetivos_vista["cliente"].astype(str) == cliente_filtro
                ].copy()
        else:
            st.caption(f"Cliente: {cliente}")

    with f2:
        estado_filtro = st.selectbox(
            "Estado",
            ["Todos"] + estados,
            key=f"objetivos_estado_filtro_{modo}_{cliente or 'admin'}",
        )

    with f3:
        prioridad_filtro = st.selectbox(
            "Prioridad",
            ["Todas"] + prioridades,
            key=f"objetivos_prioridad_filtro_{modo}_{cliente or 'admin'}",
        )

    if estado_filtro != "Todos":
        objetivos_vista = objetivos_vista[
            objetivos_vista["estado"].astype(str) == estado_filtro
        ].copy()

    if prioridad_filtro != "Todas":
        objetivos_vista = objetivos_vista[
            objetivos_vista["prioridad"].astype(str) == prioridad_filtro
        ].copy()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Objetivos visibles", len(objetivos_vista))
    k2.metric("Pendientes", len(objetivos_vista[objetivos_vista["estado"] == "Pendiente"]))
    k3.metric("En curso", len(objetivos_vista[objetivos_vista["estado"] == "En curso"]))
    k4.metric("Finalizados", len(objetivos_vista[objetivos_vista["estado"] == "Finalizado"]))

    st.markdown("### Tablero de objetivos")

    if objetivos_vista.empty:
        st.info("No hay objetivos cargados para los filtros seleccionados.")
        return

    cols = st.columns(len(estados))

    puede_editar = modo == "admin" or role in ["admin_general", "admin", "cliente", "equipo"]

    for idx, estado in enumerate(estados):
        subset = objetivos_vista[objetivos_vista["estado"].astype(str) == estado].copy()

        with cols[idx]:
            st.markdown(f"#### {estado}")
            st.caption(f"{len(subset)} objetivo(s)")

            if subset.empty:
                st.caption("Sin tarjetas.")
                continue

            for _, row in subset.iterrows():
                objetivo_id = str(row.get("id", ""))
                cliente_txt = str(row.get("cliente", ""))
                objetivo_txt = str(row.get("objetivo", "Sin objetivo"))
                descripcion_txt = str(row.get("descripcion", ""))
                responsable_txt = str(row.get("responsable", "AM Consultora"))
                prioridad_txt = str(row.get("prioridad", "Media"))
                fecha_limite_txt = str(row.get("fecha_limite", ""))
                comentarios_txt = str(row.get("comentarios", ""))

                checklist_items = parsear_checklist_objetivo(row.get("checklist", ""))
                avance_val = avance_desde_checklist_objetivo(checklist_items, row.get("avance", 0))

                with st.container(border=True):
                    if modo == "admin":
                        st.caption(cliente_txt)

                    st.markdown(f"**{objetivo_txt}**")

                    if descripcion_txt:
                        st.write(descripcion_txt)

                    st.caption(f"Responsable: {responsable_txt}")
                    st.caption(f"Prioridad: {prioridad_txt} · Límite: {fecha_limite_txt}")

                    st.progress(avance_val / 100)
                    st.caption(f"Avance: {avance_val}%")

                    if checklist_items:
                        st.markdown("**Checklist**")

                        checklist_actualizado = []
                        for i, item in enumerate(checklist_items):
                            texto_item = str(item.get("texto", ""))
                            hecho_item = bool(item.get("hecho", False))

                            if puede_editar:
                                hecho_nuevo = st.checkbox(
                                    texto_item,
                                    value=hecho_item,
                                    key=f"check_objetivo_{objetivo_id}_{i}",
                                )
                            else:
                                hecho_nuevo = st.checkbox(
                                    texto_item,
                                    value=hecho_item,
                                    key=f"check_objetivo_cliente_{objetivo_id}_{i}",
                                    disabled=True,
                                )

                            checklist_actualizado.append({
                                "texto": texto_item,
                                "hecho": hecho_nuevo,
                            })
                    else:
                        checklist_actualizado = []
                        st.caption("Sin checklist cargado.")

                    if comentarios_txt:
                        with st.expander("Historial"):
                            st.write(comentarios_txt)

                    if puede_editar:
                        with st.expander("Actualizar objetivo"):
                            nuevo_estado = st.selectbox(
                                "Estado",
                                estados,
                                index=estados.index(estado) if estado in estados else 0,
                                key=f"estado_objetivo_{objetivo_id}",
                            )

                            nuevo_checklist_txt = st.text_area(
                                "Agregar nuevos ítems al checklist",
                                value="",
                                placeholder="Un ítem por línea",
                                key=f"nuevo_checklist_objetivo_{objetivo_id}",
                                height=90,
                            )

                            nuevo_comentario = st.text_area(
                                "Comentario / actualización",
                                value="",
                                placeholder="Agregar una actualización breve...",
                                key=f"comentario_objetivo_{objetivo_id}",
                                height=90,
                            )

                            if st.button(
                                "Guardar actualización",
                                key=f"guardar_objetivo_{objetivo_id}",
                                use_container_width=True,
                            ):
                                objetivos_full = read_csv(OBJETIVOS_PATH, columnas)
                                if objetivos_full is None or objetivos_full.empty:
                                    objetivos_full = pd.DataFrame(columns=columnas)

                                for col in columnas:
                                    if col not in objetivos_full.columns:
                                        objetivos_full[col] = ""

                                objetivos_full = objetivos_full[columnas].fillna("")
                                mask = objetivos_full["id"].astype(str) == objetivo_id

                                if not mask.any():
                                    st.error("No se encontró el objetivo.")
                                else:
                                    nuevos_items = checklist_desde_textarea_objetivo(nuevo_checklist_txt)
                                    checklist_final = checklist_actualizado + nuevos_items
                                    avance_final = avance_desde_checklist_objetivo(checklist_final, avance_val)

                                    objetivos_full.loc[mask, "estado"] = nuevo_estado
                                    objetivos_full.loc[mask, "avance"] = avance_final
                                    objetivos_full.loc[mask, "checklist"] = serializar_checklist_objetivo(checklist_final)
                                    objetivos_full.loc[mask, "fecha_actualizacion"] = date.today().strftime("%Y-%m-%d")
                                    objetivos_full.loc[mask, "actualizado_por"] = nombre_usuario

                                    if nuevo_comentario.strip():
                                        anterior = str(objetivos_full.loc[mask, "comentarios"].iloc[0] or "")
                                        agregado = f"{date.today().strftime('%Y-%m-%d')} - {nombre_usuario}: {nuevo_comentario.strip()}"
                                        objetivos_full.loc[mask, "comentarios"] = (anterior + "\n" + agregado).strip()

                                    save_csv(objetivos_full, OBJETIVOS_PATH)
                                    st.success("Objetivo actualizado.")
                                    st.rerun()



def render_documentos(cliente="", modo="cliente"):
    columns = [
        "id",
        "cliente",
        "servicio",
        "categoria",
        "nombre",
        "link",
        "estado",
        "fecha",
        "observacion",
    ]

    if modo == "cliente":
        header(f"Documentación y links útiles | {cliente}")
        documentos = read_csv_cliente(DOCUMENTOS_PATH, columns, cliente)
        df = documentos.copy()
    else:
        header("Repositorio general de documentación")
        documentos = read_csv(DOCUMENTOS_PATH, columns)
        df = documentos.copy()

    if df is None or df.empty:
        st.info("No hay documentos cargados.")
    else:
        columnas = [
            "cliente", "servicio", "categoria", "nombre",
            "link", "estado", "fecha", "observacion"
        ]
        columnas = [c for c in columnas if c in df.columns]
        st.dataframe(df[columnas], use_container_width=True, hide_index=True)

    if modo != "cliente":
        st.markdown("### Edición rápida de documentos")
        edited = st.data_editor(
            documentos,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="editor_documentos_admin",
        )

        if st.button("Guardar documentos", use_container_width=True, key="guardar_documentos_admin"):
            save_csv(edited, DOCUMENTOS_PATH)
            st.success("Documentos guardados.")
            st.rerun()



def render_indicadores(cliente="", modo="cliente"):
    columnas_movimientos = [
        "id",
        "cliente",
        "mes",
        "tipo",
        "categoria",
        "importe",
        "observacion",
        "fecha_carga",
        "cargado_por",
    ]

    if modo == "cliente" and cliente:
        movimientos = read_csv_cliente(
            INDICADORES_MOVIMIENTOS_PATH,
            columnas_movimientos,
            cliente,
        )
    else:
        movimientos = read_csv(
            INDICADORES_MOVIMIENTOS_PATH,
            columnas_movimientos,
        )

    def next_prefixed_id(df, prefix):
        if df is None or df.empty or "id" not in df.columns:
            return f"{prefix}-001"

        nums = []
        for value in df["id"].dropna().astype(str).tolist():
            value = value.strip()
            if value.upper().startswith(prefix.upper() + "-"):
                try:
                    nums.append(int(value.split("-")[-1]))
                except Exception:
                    pass

        siguiente = max(nums) + 1 if nums else 1
        return f"{prefix}-{siguiente:03d}"

    def formato_pesos(valor):
        try:
            return f"$ {float(valor):,.0f}".replace(",", ".")
        except Exception:
            return "$ 0"

    def mes_label(fecha):
        try:
            return fecha.strftime("%Y-%m")
        except Exception:
            return date.today().strftime("%Y-%m")

    def cargar_movimientos_para_guardar():
        return read_csv(
            INDICADORES_MOVIMIENTOS_PATH,
            columnas_movimientos,
        )

    def categorias_previas(df, cliente_actual, tipo_actual):
        if df is None or df.empty:
            return []

        base = df.copy()

        if "cliente" in base.columns and cliente_actual:
            base = base[base["cliente"].astype(str) == str(cliente_actual)]

        if "tipo" in base.columns:
            base = base[base["tipo"].astype(str) == str(tipo_actual)]

        if "categoria" not in base.columns or base.empty:
            return []

        cats = base["categoria"].dropna().astype(str).str.strip()
        cats = cats[cats != ""].unique().tolist()
        return sorted(cats)

    if modo == "cliente":
        header("Cash Flow", f"Carga mensual y tablero de gestión | {cliente}")
        cliente_fijo = cliente
    else:
        header("Cash Flow", "Carga mensual y tablero de gestión por cliente")
        cliente_fijo = ""

    clientes_lista = clientes_visibles_para_usuario()

    # --------------------------------------------------------
    # Carga de movimientos
    # --------------------------------------------------------
    st.markdown("### Cargar ingreso o gasto")

    if modo != "cliente" and not clientes_lista:
        st.warning("Primero cargá clientes en el menú Clientes.")
    else:
        with st.form(f"form_movimiento_indicador_{modo}_{cliente_fijo}"):
            c1, c2, c3 = st.columns(3)

            with c1:
                if modo == "cliente":
                    cliente_mov = cliente_fijo
                    st.text_input("Cliente", value=cliente_mov, disabled=True)
                else:
                    cliente_mov = st.selectbox("Cliente", clientes_lista)

                fecha_mes = st.date_input("Mes y año", value=date.today())
                mes = mes_label(fecha_mes)

            with c2:
                tipo = st.selectbox("Tipo", ["Ingreso", "Gasto"])

                cats = categorias_previas(movimientos, cliente_mov if modo == "cliente" else "", tipo)
                opciones_categoria = ["Nueva categoría"] + cats

                categoria_opcion = st.selectbox("Categoría", opciones_categoria)

                if categoria_opcion == "Nueva categoría":
                    categoria = st.text_input("Nombre de nueva categoría")
                else:
                    categoria = categoria_opcion

            with c3:
                importe = st.number_input("Importe", min_value=0.0, step=10000.0)
                st.metric("Importe a cargar", formato_pesos(importe))

            observacion = st.text_area("Observación")

            guardar = st.form_submit_button("Guardar movimiento", use_container_width=True)

            if guardar:
                if not cliente_mov:
                    st.error("No se pudo identificar el cliente.")
                elif not categoria or not str(categoria).strip():
                    st.error("La categoría es obligatoria.")
                elif importe <= 0:
                    st.error("El importe debe ser mayor a cero.")
                else:
                    movimientos_guardado = cargar_movimientos_para_guardar()

                    nuevo = {
                        "id": next_prefixed_id(movimientos_guardado, "MOV"),
                        "cliente": cliente_mov,
                        "mes": mes,
                        "tipo": tipo,
                        "categoria": str(categoria).strip(),
                        "importe": importe,
                        "observacion": observacion,
                        "fecha_carga": date.today().strftime("%Y-%m-%d"),
                        "cargado_por": st.session_state.get("username", ""),
                    }

                    actualizado = pd.concat([movimientos_guardado, pd.DataFrame([nuevo])], ignore_index=True)
                    save_csv(actualizado, INDICADORES_MOVIMIENTOS_PATH)
                    st.success("Movimiento cargado correctamente.")
                    st.rerun()

    # --------------------------------------------------------
    # Carga rápida mensual por varias categorías
    # --------------------------------------------------------
    st.markdown("### Carga rápida mensual")

    if modo != "cliente" and not clientes_lista:
        st.warning("Primero cargá clientes en el menú Clientes.")
    else:
        with st.expander("Cargar varias categorías del mismo mes", expanded=False):
            with st.form(f"form_carga_rapida_indicadores_{modo}_{cliente_fijo}"):
                r1, r2 = st.columns(2)

                with r1:
                    if modo == "cliente":
                        cliente_rapido = cliente_fijo
                        st.text_input("Cliente", value=cliente_rapido, disabled=True, key=f"cliente_rapido_{modo}_{cliente_fijo}")
                    else:
                        cliente_rapido = st.selectbox("Cliente", clientes_lista, key="cliente_rapido_admin")

                with r2:
                    fecha_mes_rapido = st.date_input("Mes y año", value=date.today(), key=f"fecha_rapida_{modo}_{cliente_fijo}")
                    mes_rapido = mes_label(fecha_mes_rapido)

                st.markdown("#### Ingresos")

                ingresos_previos = categorias_previas(movimientos, cliente_rapido, "Ingreso")
                ingresos_base = ingresos_previos[:5] if ingresos_previos else ["Ventas", "Honorarios", "Cuotas", "Otros"]

                ingresos_data = []
                for i in range(6):
                    c1, c2, c3 = st.columns([2, 1, 2])

                    categoria_default = ingresos_base[i] if i < len(ingresos_base) else ""

                    with c1:
                        cat = st.text_input(
                            f"Categoría ingreso {i + 1}",
                            value=categoria_default,
                            key=f"ing_cat_{modo}_{cliente_fijo}_{i}",
                        )

                    with c2:
                        imp = st.number_input(
                            f"Importe ingreso {i + 1}",
                            min_value=0.0,
                            step=10000.0,
                            key=f"ing_imp_{modo}_{cliente_fijo}_{i}",
                        )

                    with c3:
                        obs = st.text_input(
                            f"Observación ingreso {i + 1}",
                            key=f"ing_obs_{modo}_{cliente_fijo}_{i}",
                        )

                    ingresos_data.append((cat, imp, obs))

                st.markdown("#### Gastos")

                gastos_previos = categorias_previas(movimientos, cliente_rapido, "Gasto")
                gastos_base = gastos_previos[:7] if gastos_previos else ["Sueldos", "Alquiler", "Servicios", "Publicidad", "Honorarios", "Impuestos", "Otros"]

                gastos_data = []
                for i in range(8):
                    c1, c2, c3 = st.columns([2, 1, 2])

                    categoria_default = gastos_base[i] if i < len(gastos_base) else ""

                    with c1:
                        cat = st.text_input(
                            f"Categoría gasto {i + 1}",
                            value=categoria_default,
                            key=f"gas_cat_{modo}_{cliente_fijo}_{i}",
                        )

                    with c2:
                        imp = st.number_input(
                            f"Importe gasto {i + 1}",
                            min_value=0.0,
                            step=10000.0,
                            key=f"gas_imp_{modo}_{cliente_fijo}_{i}",
                        )

                    with c3:
                        obs = st.text_input(
                            f"Observación gasto {i + 1}",
                            key=f"gas_obs_{modo}_{cliente_fijo}_{i}",
                        )

                    gastos_data.append((cat, imp, obs))

                guardar_rapido = st.form_submit_button("Guardar carga rápida mensual", use_container_width=True)

                if guardar_rapido:
                    nuevos = []
                    movimientos_guardado = cargar_movimientos_para_guardar()

                    for cat, imp, obs in ingresos_data:
                        if str(cat).strip() and imp > 0:
                            nuevos.append({
                                "id": next_prefixed_id(pd.concat([movimientos_guardado, pd.DataFrame(nuevos)], ignore_index=True), "MOV"),
                                "cliente": cliente_rapido,
                                "mes": mes_rapido,
                                "tipo": "Ingreso",
                                "categoria": str(cat).strip(),
                                "importe": imp,
                                "observacion": obs,
                                "fecha_carga": date.today().strftime("%Y-%m-%d"),
                                "cargado_por": st.session_state.get("username", ""),
                            })

                    for cat, imp, obs in gastos_data:
                        if str(cat).strip() and imp > 0:
                            nuevos.append({
                                "id": next_prefixed_id(pd.concat([movimientos_guardado, pd.DataFrame(nuevos)], ignore_index=True), "MOV"),
                                "cliente": cliente_rapido,
                                "mes": mes_rapido,
                                "tipo": "Gasto",
                                "categoria": str(cat).strip(),
                                "importe": imp,
                                "observacion": obs,
                                "fecha_carga": date.today().strftime("%Y-%m-%d"),
                                "cargado_por": st.session_state.get("username", ""),
                            })

                    if not nuevos:
                        st.error("No cargaste ningún importe mayor a cero.")
                    else:
                        actualizado = pd.concat([movimientos_guardado, pd.DataFrame(nuevos)], ignore_index=True)
                        save_csv(actualizado, INDICADORES_MOVIMIENTOS_PATH)
                        st.success(f"Se cargaron {len(nuevos)} movimiento(s) correctamente.")
                        st.rerun()


    # --------------------------------------------------------
    # Filtrado para tablero
    # --------------------------------------------------------
    if movimientos is None or movimientos.empty:
        st.info("Todavía no hay ingresos ni gastos cargados.")
        return

    vista = movimientos.copy()

    if modo == "cliente":
        vista = vista[vista["cliente"].astype(str) == str(cliente)]
    else:
        clientes_permitidos = clientes_visibles_para_usuario()

        if st.session_state.get("role") == "equipo":
            vista = vista[vista["cliente"].astype(str).isin(clientes_permitidos)]

        clientes_disponibles = ["Todos"] + sorted(vista["cliente"].dropna().astype(str).unique().tolist()) if "cliente" in vista.columns else ["Todos"]
        filtro_cliente = st.selectbox("Filtrar cliente", clientes_disponibles, key="indicadores_mov_filtro_cliente_admin")

        if filtro_cliente != "Todos":
            vista = vista[vista["cliente"].astype(str) == filtro_cliente]

    if vista.empty:
        st.info("No hay movimientos cargados para este cliente.")
        return

    vista["importe"] = pd.to_numeric(vista["importe"], errors="coerce").fillna(0)
    vista["mes"] = vista["mes"].astype(str)

    meses_disponibles = sorted(vista["mes"].dropna().astype(str).unique().tolist())

    st.markdown("### Filtros del tablero")

    f1, f2, f3 = st.columns(3)

    with f1:
        mes_desde = st.selectbox("Mes desde", meses_disponibles, index=0)

    with f2:
        mes_hasta = st.selectbox("Mes hasta", meses_disponibles, index=len(meses_disponibles) - 1)

    with f3:
        anios_disponibles = sorted({m[:4] for m in meses_disponibles if len(m) >= 4})
        modo_vista = st.selectbox("Vista rápida", ["Rango seleccionado", "Año completo"])

    if modo_vista == "Año completo":
        anio = st.selectbox("Año", anios_disponibles, key="indicadores_anio")
        vista_filtrada = vista[vista["mes"].str.startswith(anio)]
    else:
        desde = min(mes_desde, mes_hasta)
        hasta = max(mes_desde, mes_hasta)
        vista_filtrada = vista[(vista["mes"] >= desde) & (vista["mes"] <= hasta)]

    if vista_filtrada.empty:
        st.info("No hay movimientos para el período seleccionado.")
        return

    # --------------------------------------------------------
    # Sumatorias
    # --------------------------------------------------------
    ingresos_total = vista_filtrada.loc[vista_filtrada["tipo"] == "Ingreso", "importe"].sum()
    gastos_total = vista_filtrada.loc[vista_filtrada["tipo"] == "Gasto", "importe"].sum()
    resultado_total = ingresos_total - gastos_total

    st.markdown("### Tablero de control")

    k1, k2, k3 = st.columns(3)
    k1.metric("Ingresos", formato_pesos(ingresos_total))
    k2.metric("Gastos", formato_pesos(gastos_total))
    k3.metric("Resultado", formato_pesos(resultado_total))

    if ingresos_total > 0:
        margen = resultado_total / ingresos_total * 100
        st.progress(max(0, min(int(margen), 100)))
        st.caption(f"Margen estimado sobre ingresos: {margen:.1f}%")

    # --------------------------------------------------------
    # Agrupaciones
    # --------------------------------------------------------
    mensual = (
        vista_filtrada
        .groupby(["mes", "tipo"], as_index=False)["importe"]
        .sum()
    )

    mensual_pivot = (
        mensual
        .pivot(index="mes", columns="tipo", values="importe")
        .fillna(0)
        .reset_index()
    )

    if "Ingreso" not in mensual_pivot.columns:
        mensual_pivot["Ingreso"] = 0

    if "Gasto" not in mensual_pivot.columns:
        mensual_pivot["Gasto"] = 0

    mensual_pivot["Resultado"] = mensual_pivot["Ingreso"] - mensual_pivot["Gasto"]

    por_categoria = (
        vista_filtrada
        .groupby(["tipo", "categoria"], as_index=False)["importe"]
        .sum()
        .sort_values("importe", ascending=False)
    )

    # --------------------------------------------------------
    # Gráficos
    # --------------------------------------------------------
    st.markdown("### Gráficos")

    g1, g2 = st.columns(2)

    with g1:
        st.markdown("#### Ingresos vs gastos por mes")

        chart_mensual = (
            alt.Chart(mensual)
            .mark_bar()
            .encode(
                x=alt.X("mes:N", title="Mes"),
                y=alt.Y("importe:Q", title="Importe"),
                color=alt.Color("tipo:N", title="Tipo"),
                tooltip=["mes:N", "tipo:N", alt.Tooltip("importe:Q", format=",.0f")],
            )
            .properties(height=320)
        )

        st.altair_chart(chart_mensual, use_container_width=True)

    with g2:
        st.markdown("#### Resultado mensual")

        chart_resultado = (
            alt.Chart(mensual_pivot)
            .mark_line(point=True)
            .encode(
                x=alt.X("mes:N", title="Mes"),
                y=alt.Y("Resultado:Q", title="Resultado"),
                tooltip=["mes:N", alt.Tooltip("Resultado:Q", format=",.0f")],
            )
            .properties(height=320)
        )

        st.altair_chart(chart_resultado, use_container_width=True)

    g3, g4 = st.columns(2)

    with g3:
        st.markdown("#### Ingresos por categoría")

        ingresos_cat = por_categoria[por_categoria["tipo"] == "Ingreso"]

        if ingresos_cat.empty:
            st.info("No hay ingresos cargados en el período.")
        else:
            chart_ingresos = (
                alt.Chart(ingresos_cat)
                .mark_bar()
                .encode(
                    x=alt.X("importe:Q", title="Importe"),
                    y=alt.Y("categoria:N", title="Categoría", sort="-x"),
                    tooltip=["categoria:N", alt.Tooltip("importe:Q", format=",.0f")],
                )
                .properties(height=320)
            )

            st.altair_chart(chart_ingresos, use_container_width=True)

    with g4:
        st.markdown("#### Gastos por categoría")

        gastos_cat = por_categoria[por_categoria["tipo"] == "Gasto"]

        if gastos_cat.empty:
            st.info("No hay gastos cargados en el período.")
        else:
            chart_gastos = (
                alt.Chart(gastos_cat)
                .mark_bar()
                .encode(
                    x=alt.X("importe:Q", title="Importe"),
                    y=alt.Y("categoria:N", title="Categoría", sort="-x"),
                    tooltip=["categoria:N", alt.Tooltip("importe:Q", format=",.0f")],
                )
                .properties(height=320)
            )

            st.altair_chart(chart_gastos, use_container_width=True)

    # --------------------------------------------------------
    # Detalle
    # --------------------------------------------------------
    st.markdown("### Detalle del período")

    columnas = [
        "cliente",
        "mes",
        "tipo",
        "categoria",
        "importe",
        "observacion",
        "fecha_carga",
        "cargado_por",
    ]

    columnas = [c for c in columnas if c in vista_filtrada.columns]

    st.dataframe(
        vista_filtrada[columnas].sort_values(["mes", "tipo", "categoria"]),
        use_container_width=True,
        hide_index=True,
    )

    if modo != "cliente":
        with st.expander("Edición avanzada en tabla"):
            edited = st.data_editor(
                movimientos,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="editor_indicadores_movimientos_admin",
            )

            if st.button("Guardar edición avanzada de movimientos", use_container_width=True, key="guardar_indicadores_movimientos_admin"):
                save_csv(edited, INDICADORES_MOVIMIENTOS_PATH)
                st.success("Movimientos guardados.")
                st.rerun()


def columnas_por_path(path):
    filename = Path(path).name

    mapa = {
        "contenidos.csv": [
            "id", "cliente", "fecha", "canal", "formato", "tema", "objetivo",
            "copy", "link_canva", "estado", "comentario_cliente",
        ],
        "materiales.csv": [
            "id",
            "cliente",
            "solicitud",
            "responsable_cliente",
            "fecha_limite",
            "estado",
            "observacion",
            "formato_sugerido",
            "referencia",
            "link_entrega",
            "medio_envio",
            "comentario_cliente",
            "fecha_envio_cliente",
            "observacion_am",
            "fecha_carga",
            "creado_por",
            "fecha_actualizacion",
            "actualizado_por",
        ],
        "campanias.csv": [
            "id", "cliente", "campania", "plataforma", "objetivo", "presupuesto",
            "estado", "leads", "costo_por_lead", "observacion",
        ],
        "reportes.csv": [
            "id", "cliente", "mes", "alcance", "interacciones", "consultas",
            "inversion", "estado", "que_funciono", "proximo_foco",
            "pdf_nombre", "pdf_tipo", "pdf_base64", "fecha_carga",
            "cargado_por",
        ],
        "tareas.csv": [
            "id",
            "cliente",
            "tarea",
            "descripcion",
            "responsable_am",
            "prioridad",
            "estado",
            "fecha_limite",
            "checklist",
            "avance",
            "recurrente",
            "frecuencia",
            "intervalo",
            "serie_id",
            "ocurrencia",
            "comentarios",
            "fecha_carga",
            "creado_por",
            "fecha_actualizacion",
            "actualizado_por",
        ],
        "indicadores_movimientos.csv": [
            "id", "cliente", "mes", "tipo", "categoria", "importe",
            "observacion", "fecha_carga", "cargado_por",
        ],
        "cuenta_corriente.csv": [
            "id", "cliente", "mes", "concepto", "importe", "estado",
            "fecha_factura", "fecha_pago", "observacion", "comprobante_nombre",
            "comprobante_tipo", "comprobante_base64", "fecha_carga",
            "cargado_por",
        ],
    }

    return mapa.get(filename, [])



def cargar_cuenta_corriente(cliente=""):
    columns = [
        "id",
        "cliente",
        "mes",
        "concepto",
        "servicio",
        "importe",
        "estado",
        "fecha_factura",
        "fecha_pago",
        "observacion",
        "comprobante_nombre",
        "comprobante_tipo",
        "comprobante_base64",
        "fecha_carga",
        "cargado_por",
    ]

    if cliente:
        return read_csv_cliente(CUENTA_CORRIENTE_PATH, columns, cliente)

    return read_csv(CUENTA_CORRIENTE_PATH, columns)


def opciones_servicio_cliente(cliente_nombre):
    servicios = servicios_activos_cliente(cliente_nombre)
    opciones = []

    if servicios.get("digital"):
        opciones.append("Ecosistema digital")

    if servicios.get("consultoria"):
        opciones.append("Consultoría")

    if servicios.get("contabilidad"):
        opciones.append("Contabilidad / Gestión")

    if not opciones:
        opciones.append("General")

    return opciones



def render_cuenta_corriente_admin():
    if st.session_state.get("role") != "admin_general":
        header("Cuenta corriente", "Acceso restringido")
        st.error("Este módulo solo está disponible para el administrador general.")
        return

    header("Cuenta corriente", "Honorarios, facturación, pagos y deuda por cliente")

    columnas = [
        "id",
        "cliente",
        "mes",
        "concepto",
        "servicio",
        "importe",
        "estado",
        "fecha_factura",
        "fecha_pago",
        "observacion",
        "comprobante_nombre",
        "comprobante_tipo",
        "comprobante_base64",
        "fecha_carga",
        "cargado_por",
    ]

    cuenta = cargar_cuenta_corriente()
    clientes_df = load_clientes()

    clientes_lista = []
    if clientes_df is not None and not clientes_df.empty and "cliente" in clientes_df.columns:
        clientes_lista = sorted(
            clientes_df["cliente"]
            .dropna()
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
            .tolist()
        )

    def next_prefixed_id(df, prefix):
        if df is None or df.empty or "id" not in df.columns:
            return f"{prefix}-001"

        nums = []
        for value in df["id"].dropna().astype(str).tolist():
            value = value.strip()
            if value.upper().startswith(prefix.upper() + "-"):
                try:
                    nums.append(int(value.split("-")[-1]))
                except Exception:
                    pass

        siguiente = max(nums) + 1 if nums else 1
        return f"{prefix}-{siguiente:03d}"

    def mes_label(fecha):
        try:
            return fecha.strftime("%Y-%m")
        except Exception:
            return date.today().strftime("%Y-%m")

    def formato_pesos(valor):
        try:
            return f"$ {float(valor):,.0f}".replace(",", ".")
        except Exception:
            return "$ 0"

    estados_pago = [
        "Pendiente de facturar",
        "Facturado",
        "Pagado",
        "No pagado",
        "Vencido",
        "Bonificado",
    ]

    # --------------------------------------------------------
    # Alta rápida
    # --------------------------------------------------------
    with st.expander("Cargar honorario mensual", expanded=True):
        if not clientes_lista:
            st.warning("Primero cargá clientes.")
        else:
            with st.form("form_cuenta_corriente_alta"):
                c1, c2, c3 = st.columns(3)

                with c1:
                    cliente_sel = st.selectbox("Cliente", clientes_lista)
                    fecha_mes = st.date_input("Mes", value=date.today())
                    mes = mes_label(fecha_mes)

                with c2:
                    concepto = st.text_input("Concepto", value="Honorarios mensuales")
                    importe = st.number_input("Importe", min_value=0.0, step=10000.0)

                with c3:
                    estado = st.selectbox("Estado", estados_pago, index=0)
                    fecha_factura = st.date_input("Fecha factura / emisión", value=date.today())

                observacion = st.text_area("Observación")

                guardar = st.form_submit_button("Guardar movimiento de cuenta corriente", use_container_width=True)

                if guardar:
                    if not cliente_sel:
                        st.error("Seleccioná un cliente.")
                    elif importe <= 0:
                        st.error("El importe debe ser mayor a cero.")
                    else:
                        cuenta_full = cargar_cuenta_corriente()

                        nuevo = {
                            "id": next_prefixed_id(cuenta_full, "CC"),
                            "cliente": cliente_sel,
                            "mes": mes,
                            "concepto": concepto.strip() or "Honorarios mensuales",
                            "servicio": servicio_sel,
                            "importe": importe,
                            "estado": estado,
                            "fecha_factura": fecha_factura.strftime("%Y-%m-%d"),
                            "fecha_pago": date.today().strftime("%Y-%m-%d") if estado == "Pagado" else "",
                            "observacion": observacion,
                            "comprobante_nombre": "",
                            "comprobante_tipo": "",
                            "comprobante_base64": "",
                            "fecha_carga": date.today().strftime("%Y-%m-%d"),
                            "cargado_por": st.session_state.get("username", ""),
                        }

                        actualizado = pd.concat([cuenta_full, pd.DataFrame([nuevo])], ignore_index=True)
                        save_csv(actualizado, CUENTA_CORRIENTE_PATH)
                        st.success("Movimiento cargado correctamente.")
                        st.rerun()

    # --------------------------------------------------------
    # Resumen
    # --------------------------------------------------------
    if cuenta is None or cuenta.empty:
        st.info("Todavía no hay movimientos de cuenta corriente cargados.")
        return

    cuenta = cuenta.copy().fillna("")
    if "servicio" not in cuenta.columns:
        cuenta["servicio"] = "General"
    cuenta["servicio"] = cuenta["servicio"].replace("", "General")
    cuenta["importe"] = pd.to_numeric(cuenta["importe"], errors="coerce").fillna(0)
    cuenta["mes"] = cuenta["mes"].astype(str)

    st.markdown("### Resumen")

    f1, f2, f3 = st.columns(3)

    clientes_filtro = ["Todos"]
    if "cliente" in cuenta.columns:
        clientes_filtro += sorted(cuenta["cliente"].dropna().astype(str).unique().tolist())

    with f1:
        filtro_cliente = st.selectbox("Cliente", clientes_filtro, key="cc_filtro_cliente")

    with f2:
        estados_filtro = ["Todos"] + estados_pago
        filtro_estado = st.selectbox("Estado", estados_filtro, key="cc_filtro_estado")

    with f3:
        meses = sorted(cuenta["mes"].dropna().astype(str).unique().tolist())
        filtro_mes = st.selectbox("Mes", ["Todos"] + meses, key="cc_filtro_mes")

    vista = cuenta.copy()

    if filtro_cliente != "Todos":
        vista = vista[vista["cliente"].astype(str) == filtro_cliente]

    if filtro_estado != "Todos":
        vista = vista[vista["estado"].astype(str) == filtro_estado]

    if filtro_mes != "Todos":
        vista = vista[vista["mes"].astype(str) == filtro_mes]

    if vista.empty:
        st.info("No hay movimientos para los filtros seleccionados.")
        return

    estados_sin_deuda = ["Pagado", "Bonificado"]
    deuda = vista[~vista["estado"].astype(str).isin(estados_sin_deuda)]["importe"].sum()
    pagado = vista[vista["estado"].astype(str) == "Pagado"]["importe"].sum()
    total = vista["importe"].sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total cargado", formato_pesos(total))
    k2.metric("Pagado", formato_pesos(pagado))
    k3.metric("Deuda / pendiente", formato_pesos(deuda))
    k4.metric("Movimientos", len(vista))

    st.markdown("### Detalle de cuenta corriente")

    columnas_vista = [
        "cliente",
        "mes",
        "concepto",
        "servicio",
        "importe",
        "estado",
        "fecha_factura",
        "fecha_pago",
        "observacion",
    ]
    columnas_vista = [c for c in columnas_vista if c in vista.columns]

    st.dataframe(vista[columnas_vista], use_container_width=True, hide_index=True)

    with st.expander("Edición avanzada"):
        st.warning("Solo admin general. Acá podés modificar estados, importes, fechas u observaciones.")

        edited = st.data_editor(
            cuenta,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="editor_cuenta_corriente_admin",
        )

        if st.button("Guardar edición de cuenta corriente", use_container_width=True, key="guardar_cuenta_corriente_admin"):
            save_csv(edited, CUENTA_CORRIENTE_PATH)
            st.success("Cuenta corriente actualizada.")
            st.rerun()



def render_cuenta_corriente_cliente(cliente):
    if not puede_ver_cuenta_corriente():
        st.warning("No tenés permisos para ver cuenta corriente.")
        return

    header("Cuenta corriente", f"Estado de honorarios y pagos | {cliente}")

    columnas = [
        "id",
        "cliente",
        "mes",
        "concepto",
        "servicio",
        "importe",
        "estado",
        "fecha_factura",
        "fecha_pago",
        "observacion",
        "comprobante_nombre",
        "comprobante_tipo",
        "comprobante_base64",
        "fecha_carga",
        "cargado_por",
    ]

    cuenta = read_csv_cliente(CUENTA_CORRIENTE_PATH, columnas, cliente)

    if cuenta is None or cuenta.empty:
        st.info("Todavía no hay movimientos de cuenta corriente cargados.")
        return

    cuenta = cuenta.copy().fillna("")
    if "servicio" not in cuenta.columns:
        cuenta["servicio"] = "General"
    cuenta["servicio"] = cuenta["servicio"].replace("", "General")
    cuenta["importe"] = pd.to_numeric(cuenta["importe"], errors="coerce").fillna(0)
    cuenta["mes"] = cuenta["mes"].astype(str)

    estados_sin_deuda = ["Pagado", "Bonificado"]
    deuda = cuenta[~cuenta["estado"].astype(str).isin(estados_sin_deuda)]["importe"].sum()
    pagado = cuenta[cuenta["estado"].astype(str) == "Pagado"]["importe"].sum()
    total = cuenta["importe"].sum()

    def formato_pesos(valor):
        try:
            return f"$ {float(valor):,.0f}".replace(",", ".")
        except Exception:
            return "$ 0"

    k1, k2, k3 = st.columns(3)
    k1.metric("Total cargado", formato_pesos(total))
    k2.metric("Pagado", formato_pesos(pagado))
    k3.metric("Pendiente / deuda", formato_pesos(deuda))

    st.markdown("### Detalle")

    columnas_vista = [
        "mes",
        "concepto",
        "servicio",
        "importe",
        "estado",
        "fecha_factura",
        "fecha_pago",
        "observacion",
    ]
    columnas_vista = [c for c in columnas_vista if c in cuenta.columns]

    st.dataframe(cuenta[columnas_vista], use_container_width=True, hide_index=True)

    pendientes = cuenta[
        ~cuenta["estado"].astype(str).isin(["Pagado", "Bonificado"])
    ].copy()

    if pendientes.empty:
        st.success("No hay honorarios pendientes de pago.")
        return

    st.markdown("### Informar pago")

    opciones = []
    mapa = {}

    for _, row in pendientes.iterrows():
        servicio_txt = str(row.get("servicio", "") or "General")
        etiqueta = f"{row.get('id', '')} · {row.get('mes', '')} · {servicio_txt} · {row.get('concepto', '')} · {formato_pesos(row.get('importe', 0))}"
        opciones.append(etiqueta)
        mapa[etiqueta] = row.get("id", "")

    with st.form(f"form_informar_pago_{cliente}"):
        seleccion = st.selectbox("Movimiento a informar como pagado", opciones)
        observacion_pago = st.text_area(
            "Observación / detalle del comprobante",
            placeholder="Ejemplo: Transferencia realizada el día..., banco..., número de operación..."
        )
        archivo = st.file_uploader(
            "Adjuntar comprobante",
            type=["pdf", "png", "jpg", "jpeg", "webp"],
            key=f"comprobante_pago_{cliente}",
        )

        confirmar = st.form_submit_button("Marcar como pagado", use_container_width=True)

        if confirmar:
            mov_id = mapa.get(seleccion)

            if not mov_id:
                st.error("No se pudo identificar el movimiento.")
            elif not observacion_pago.strip() and archivo is None:
                st.error("Agregá una observación o adjuntá un comprobante.")
            else:
                cuenta_full = cargar_cuenta_corriente()
                mask = cuenta_full["id"].astype(str) == str(mov_id)

                if not mask.any():
                    st.error("No se encontró el movimiento en la base.")
                else:
                    cuenta_full.loc[mask, "estado"] = "Pagado"
                    cuenta_full.loc[mask, "fecha_pago"] = date.today().strftime("%Y-%m-%d")

                    obs_anterior = cuenta_full.loc[mask, "observacion"].astype(str).fillna("")
                    nuevo_texto = observacion_pago.strip()

                    if nuevo_texto:
                        cuenta_full.loc[mask, "observacion"] = (
                            obs_anterior
                            + "\n"
                            + date.today().strftime("%Y-%m-%d")
                            + " - Cliente informó pago: "
                            + nuevo_texto
                        )

                    if archivo is not None:
                        contenido = archivo.read()
                        cuenta_full.loc[mask, "comprobante_nombre"] = archivo.name
                        cuenta_full.loc[mask, "comprobante_tipo"] = archivo.type or ""
                        cuenta_full.loc[mask, "comprobante_base64"] = base64.b64encode(contenido).decode("utf-8")

                    save_csv(cuenta_full, CUENTA_CORRIENTE_PATH)
                    st.success("Pago informado correctamente.")
                    st.rerun()

    with st.expander("Comprobantes cargados"):
        con_comprobante = cuenta[
            cuenta.get("comprobante_base64", "").astype(str).str.strip() != ""
        ].copy() if "comprobante_base64" in cuenta.columns else pd.DataFrame()

        if con_comprobante.empty:
            st.info("No hay comprobantes adjuntos.")
        else:
            for _, row in con_comprobante.iterrows():
                nombre = row.get("comprobante_nombre", "comprobante")
                tipo = row.get("comprobante_tipo", "application/octet-stream")
                data_b64 = row.get("comprobante_base64", "")

                try:
                    data = base64.b64decode(data_b64)
                    st.download_button(
                        label=f"Descargar {nombre} · {row.get('mes', '')}",
                        data=data,
                        file_name=nombre,
                        mime=tipo,
                        key=f"download_cc_{row.get('id', '')}",
                    )
                except Exception:
                    st.caption(f"No se pudo preparar el comprobante de {row.get('mes', '')}.")



def render_admin_dashboard_ligero():
    header("Dashboard AM", "Resumen operativo liviano")

    clientes = load_clientes()

    total_clientes = len(clientes) if clientes is not None else 0
    clientes_activos = 0

    if clientes is not None and not clientes.empty and "estado" in clientes.columns:
        clientes_activos = len(
            clientes[
                clientes["estado"].astype(str).str.lower().str.contains("activo", na=False)
            ]
        )

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Clientes", total_clientes)

    with c2:
        st.metric("Clientes activos", clientes_activos)

    with c3:
        st.metric("Modo", "liviano")

    st.markdown("### Clientes recientes")

    if clientes is None or clientes.empty:
        st.info("No hay clientes cargados.")
    else:
        columnas = [
            "cliente",
            "rubro",
            "estado",
            "plan",
            "responsable_am",
            "fecha_inicio",
        ]
        columnas = [c for c in columnas if c in clientes.columns]
        st.dataframe(clientes[columnas].tail(20), use_container_width=True, hide_index=True)

    with st.expander("Ver conteos operativos"):
        st.caption("Estos conteos consultan Supabase. Quedan bajo expander para que el dashboard inicial cargue más rápido.")

        k1, k2, k3 = st.columns(3)
        k1.metric("Contenidos", contar_registros(CONTENIDOS_PATH, ["id"]))
        k2.metric("Materiales", contar_registros(MATERIALES_PATH, ["id"]))
        k3.metric("Campañas", contar_registros(CAMPANIAS_PATH, ["id"]))

        k4, k5, k6 = st.columns(3)
        k4.metric("Reportes", contar_registros(REPORTES_PATH, ["id"]))
        k5.metric("Tareas", contar_registros(TAREAS_PATH, ["id"]))
        k6.metric("Cash Flow", contar_registros(INDICADORES_MOVIMIENTOS_PATH, ["id"]))

    st.info("Para editar información, usá Clientes, Usuarios o Edición rápida. El dashboard evita cargas pesadas al entrar.")



def render_edicion_rapida_ligera():
    header("Edición rápida", "Elegí un módulo para cargar solo esa tabla")

    modulos = {
        "Clientes": {
            "path": CLIENTES_PATH,
            "loader": load_clientes,
        },
        "Contenidos": {
            "path": CONTENIDOS_PATH,
            "loader": load_contenidos,
        },
        "Materiales": {
            "path": MATERIALES_PATH,
            "loader": load_materiales,
        },
        "Campañas": {
            "path": CAMPANIAS_PATH,
            "loader": load_campanias,
        },
        "Reportes": {
            "path": REPORTES_PATH,
            "loader": load_reportes,
        },
        "Tareas": {
            "path": TAREAS_PATH,
            "loader": load_tareas,
        },
        "Cash Flow": {
            "path": INDICADORES_MOVIMIENTOS_PATH,
            "loader": lambda: read_csv(
                INDICADORES_MOVIMIENTOS_PATH,
                [
                    "id",
                    "cliente",
                    "mes",
                    "tipo",
                    "categoria",
                    "importe",
                    "observacion",
                    "fecha_carga",
                    "cargado_por",
                ],
            ),
        },
    }

    modulo = st.selectbox("Módulo", list(modulos.keys()), key="edicion_rapida_modulo_ligero")

    config = modulos[modulo]
    render_crud_table(modulo, config["path"])



def render_admin_dashboard(clientes, contenidos, materiales, campanias, reportes, tareas):
    header("Dashboard AM", "Vista interna de gestión de clientes, contenidos y campañas.")

    c1, c2, c3, c4 = st.columns(4)

    pendientes = contenidos["estado"].astype(str).str.contains("Pendiente|revisión|aprobación|Correcciones", case=False, na=False).sum() if not contenidos.empty else 0
    materiales_pend = materiales["estado"].astype(str).str.contains("Pendiente|Solicitado", case=False, na=False).sum() if not materiales.empty else 0
    camp_act = campanias["estado"].astype(str).str.contains("Activa", case=False, na=False).sum() if not campanias.empty else 0

    c1.metric("Clientes activos", len(clientes[clientes["estado"].astype(str) == "Activo"]) if not clientes.empty else 0)
    c2.metric("Contenidos pendientes", int(pendientes))
    c3.metric("Materiales pendientes", int(materiales_pend))
    c4.metric("Campañas activas", int(camp_act))

    st.markdown("### Próximos contenidos")
    if contenidos.empty:
        st.info("No hay contenidos.")
    else:
        vista_contenidos = contenidos[["cliente", "fecha", "formato", "tema", "estado"]].copy()
        if "fecha" in vista_contenidos.columns:
            vista_contenidos = vista_contenidos.sort_values("fecha").head(20)
        st.dataframe(vista_contenidos, use_container_width=True, hide_index=True)

    st.markdown("### Tareas internas")
    if tareas.empty:
        st.info("No hay tareas.")
    else:
        st.dataframe(tareas, use_container_width=True, hide_index=True)




def columnas_reportes_completas():
    return [
        "id",
        "cliente",
        "mes",
        "alcance",
        "interacciones",
        "consultas",
        "inversion",
        "estado",
        "que_funciono",
        "proximo_foco",
        "pdf_nombre",
        "pdf_tipo",
        "pdf_base64",
        "fecha_carga",
        "cargado_por",
    ]


def render_reportes_gestion(cliente_fijo="", modo="admin"):
    import base64

    role = st.session_state.get("role", "")
    username = st.session_state.get("username", "")
    nombre_usuario = st.session_state.get("name", username)

    if modo == "equipo":
        header(
            "Reportes",
            f"Carga y seguimiento de reportes | {cliente_fijo}",
        )
    else:
        header(
            "Reportes",
            "Carga y administración de reportes por cliente.",
        )

    columnas = columnas_reportes_completas()
    reportes_full = read_csv(REPORTES_PATH, columnas)

    if reportes_full is None or reportes_full.empty:
        reportes_full = pd.DataFrame(columns=columnas)

    reportes_full = reportes_full.copy().fillna("")

    for col in columnas:
        if col not in reportes_full.columns:
            reportes_full[col] = ""

    reportes_full = reportes_full[columnas]

    clientes_df = load_clientes()

    if clientes_df is None or clientes_df.empty:
        clientes_opciones = []
    else:
        clientes_opciones = sorted(
            clientes_df["cliente"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

    if modo == "equipo":
        clientes_permitidos = clientes_visibles_para_usuario()

        if cliente_fijo:
            if cliente_fijo not in clientes_permitidos:
                st.error("No tenés permisos sobre este cliente.")
                return

            clientes_opciones = [cliente_fijo]
        else:
            clientes_opciones = clientes_permitidos

    if not clientes_opciones:
        st.info("No hay clientes disponibles.")
        return

    with st.expander("Cargar nuevo reporte", expanded=True):
        with st.form(
            f"form_nuevo_reporte_{modo}_{cliente_fijo or 'general'}"
        ):
            c1, c2 = st.columns([1.2, 1])

            with c1:
                if modo == "equipo" and cliente_fijo:
                    cliente_sel = cliente_fijo
                    st.text_input(
                        "Cliente",
                        value=cliente_sel,
                        disabled=True,
                    )
                else:
                    cliente_sel = st.selectbox(
                        "Cliente",
                        clientes_opciones,
                    )

                mes = st.text_input(
                    "Período",
                    value=date.today().strftime("%Y-%m"),
                    placeholder="2026-07",
                )

                estado = st.selectbox(
                    "Estado",
                    [
                        "Borrador",
                        "En revisión",
                        "Publicado",
                        "Archivado",
                    ],
                    index=2,
                )

                que_funciono = st.text_area(
                    "Qué funcionó",
                    height=110,
                )

                proximo_foco = st.text_area(
                    "Próximo foco",
                    height=110,
                )

            with c2:
                alcance = st.number_input(
                    "Alcance",
                    min_value=0,
                    step=1,
                )

                interacciones = st.number_input(
                    "Interacciones",
                    min_value=0,
                    step=1,
                )

                consultas = st.number_input(
                    "Consultas",
                    min_value=0,
                    step=1,
                )

                inversion = st.number_input(
                    "Inversión",
                    min_value=0.0,
                    step=1000.0,
                )

                pdf = st.file_uploader(
                    "Reporte PDF",
                    type=["pdf"],
                    help="Tamaño máximo: 5 MB.",
                    key=f"pdf_nuevo_reporte_{modo}_{cliente_fijo}",
                )

            guardar = st.form_submit_button(
                "Guardar reporte",
                use_container_width=True,
            )

            if guardar:
                if not mes.strip():
                    st.error("Indicá el período del reporte.")
                elif pdf is not None and pdf.size > 5 * 1024 * 1024:
                    st.error("El PDF supera el límite de 5 MB.")
                else:
                    pdf_nombre = ""
                    pdf_tipo = ""
                    pdf_base64 = ""

                    if pdf is not None:
                        pdf_bytes = pdf.getvalue()
                        pdf_nombre = pdf.name
                        pdf_tipo = pdf.type or "application/pdf"
                        pdf_base64 = base64.b64encode(
                            pdf_bytes
                        ).decode("utf-8")

                    nuevo = {
                        "id": (
                            "REP-"
                            + pd.Timestamp.now().strftime(
                                "%Y%m%d%H%M%S%f"
                            )
                        ),
                        "cliente": cliente_sel,
                        "mes": mes.strip(),
                        "alcance": int(alcance),
                        "interacciones": int(interacciones),
                        "consultas": int(consultas),
                        "inversion": float(inversion),
                        "estado": estado,
                        "que_funciono": que_funciono.strip(),
                        "proximo_foco": proximo_foco.strip(),
                        "pdf_nombre": pdf_nombre,
                        "pdf_tipo": pdf_tipo,
                        "pdf_base64": pdf_base64,
                        "fecha_carga": date.today().strftime("%Y-%m-%d"),
                        "cargado_por": nombre_usuario,
                    }

                    actualizado = pd.concat(
                        [
                            reportes_full,
                            pd.DataFrame([nuevo]),
                        ],
                        ignore_index=True,
                    )

                    save_csv(actualizado, REPORTES_PATH)
                    st.success("Reporte guardado.")
                    st.rerun()

    if modo == "equipo":
        vista = reportes_full[
            reportes_full["cliente"]
            .astype(str)
            .isin(clientes_opciones)
        ].copy()
    else:
        vista = reportes_full.copy()

    st.markdown("### Reportes cargados")

    if vista.empty:
        st.info("Todavía no hay reportes cargados.")
        return

    filtro_cliente = st.selectbox(
        "Filtrar por cliente",
        (
            clientes_opciones
            if len(clientes_opciones) == 1
            else ["Todos"] + clientes_opciones
        ),
        key=f"filtro_reportes_gestion_{modo}_{cliente_fijo}",
    )

    if filtro_cliente != "Todos":
        vista = vista[
            vista["cliente"].astype(str) == filtro_cliente
        ].copy()

    columnas_editor = [
        "id",
        "cliente",
        "mes",
        "alcance",
        "interacciones",
        "consultas",
        "inversion",
        "estado",
        "que_funciono",
        "proximo_foco",
        "pdf_nombre",
        "fecha_carga",
        "cargado_por",
    ]

    edited = st.data_editor(
        vista[columnas_editor],
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=[
            "id",
            "cliente",
            "pdf_nombre",
            "fecha_carga",
            "cargado_por",
        ],
        key=f"editor_reportes_gestion_{modo}_{cliente_fijo}",
    )

    if st.button(
        "Guardar modificaciones",
        use_container_width=True,
        key=f"guardar_reportes_gestion_{modo}_{cliente_fijo}",
    ):
        base = reportes_full.copy()

        for _, fila in edited.iterrows():
            reporte_id = str(fila.get("id", ""))
            mask = base["id"].astype(str) == reporte_id

            if not mask.any():
                continue

            for col in [
                "mes",
                "alcance",
                "interacciones",
                "consultas",
                "inversion",
                "estado",
                "que_funciono",
                "proximo_foco",
            ]:
                base.loc[mask, col] = fila.get(col, "")

        save_csv(base, REPORTES_PATH)
        st.success("Reportes actualizados.")
        st.rerun()

    st.markdown("### Reemplazar PDF")

    ids_vista = vista["id"].astype(str).tolist()

    reporte_id_sel = st.selectbox(
        "Reporte",
        ids_vista,
        format_func=lambda reporte_id: (
            f"{vista[vista['id'].astype(str) == reporte_id].iloc[0].get('cliente', '')}"
            f" · {vista[vista['id'].astype(str) == reporte_id].iloc[0].get('mes', '')}"
        ),
        key=f"reporte_pdf_selector_{modo}_{cliente_fijo}",
    )

    nuevo_pdf = st.file_uploader(
        "Seleccionar nuevo PDF",
        type=["pdf"],
        key=f"reemplazar_pdf_{modo}_{cliente_fijo}_{reporte_id_sel}",
    )

    if st.button(
        "Guardar PDF",
        use_container_width=True,
        key=f"guardar_pdf_{modo}_{cliente_fijo}",
    ):
        if nuevo_pdf is None:
            st.error("Seleccioná un archivo PDF.")
        elif nuevo_pdf.size > 5 * 1024 * 1024:
            st.error("El PDF supera el límite de 5 MB.")
        else:
            base = reportes_full.copy()
            mask = base["id"].astype(str) == reporte_id_sel

            if not mask.any():
                st.error("No se encontró el reporte.")
            else:
                base.loc[mask, "pdf_nombre"] = nuevo_pdf.name
                base.loc[mask, "pdf_tipo"] = (
                    nuevo_pdf.type or "application/pdf"
                )
                base.loc[mask, "pdf_base64"] = (
                    base64.b64encode(
                        nuevo_pdf.getvalue()
                    ).decode("utf-8")
                )
                base.loc[mask, "fecha_carga"] = (
                    date.today().strftime("%Y-%m-%d")
                )
                base.loc[mask, "cargado_por"] = nombre_usuario

                save_csv(base, REPORTES_PATH)
                st.success("PDF actualizado.")
                st.rerun()



def render_materiales_gestion(cliente_fijo="", modo="admin"):
    role = st.session_state.get("role", "")
    username = st.session_state.get("username", "")
    nombre_usuario = st.session_state.get("name", username)

    if modo == "equipo":
        header(
            "Pedidos de material",
            f"Gestión de solicitudes | {cliente_fijo}",
        )
    else:
        header(
            "Pedidos de material",
            "Creación, seguimiento y revisión de entregas.",
        )

    columnas = columnas_materiales_completas()
    materiales_full = load_materiales()

    if materiales_full is None or materiales_full.empty:
        materiales_full = pd.DataFrame(columns=columnas)

    materiales_full = materiales_full.copy().fillna("")

    for col in columnas:
        if col not in materiales_full.columns:
            materiales_full[col] = ""

    materiales_full = materiales_full[columnas].fillna("")

    if modo == "equipo":
        clientes_permitidos = clientes_visibles_para_usuario()

        if cliente_fijo:
            if cliente_fijo not in clientes_permitidos:
                st.error("No tenés permisos sobre este cliente.")
                return

            clientes_opciones = [cliente_fijo]
        else:
            clientes_opciones = clientes_permitidos
    else:
        clientes_df = load_clientes()

        if (
            clientes_df is None
            or clientes_df.empty
            or "cliente" not in clientes_df.columns
        ):
            clientes_opciones = []
        else:
            clientes_opciones = sorted(
                clientes_df["cliente"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

    if not clientes_opciones:
        st.info("No hay clientes disponibles.")
        return

    estados = [
        "Solicitado",
        "En preparación",
        "Enviado por cliente",
        "En revisión",
        "Requiere cambios",
        "Aprobado",
        "Publicado",
        "Cancelado",
    ]

    with st.expander(
        "Crear nuevo pedido de material",
        expanded=True,
    ):
        with st.form(
            f"nuevo_material_{modo}_{cliente_fijo or 'general'}"
        ):
            c1, c2 = st.columns([1.5, 1])

            with c1:
                if modo == "equipo" and cliente_fijo:
                    cliente_sel = cliente_fijo
                    st.text_input(
                        "Cliente",
                        value=cliente_sel,
                        disabled=True,
                    )
                else:
                    cliente_sel = st.selectbox(
                        "Cliente",
                        clientes_opciones,
                    )

                solicitud = st.text_input(
                    "Pedido de grabación",
                    placeholder=(
                        "Ejemplo: video explicando entrenamiento híbrido"
                    ),
                )

                indicaciones = st.text_area(
                    "Indicaciones para grabar",
                    placeholder=(
                        "Explicá qué debe decir, cómo grabarlo, "
                        "qué planos realizar y cualquier detalle necesario."
                    ),
                    height=150,
                )

                referencia = st.text_input(
                    "Link de referencia",
                    placeholder=(
                        "Instagram, TikTok, Drive, Canva u otro ejemplo"
                    ),
                )

            with c2:
                responsable_cliente = st.text_input(
                    "Responsable del cliente",
                    placeholder="Ejemplo: Leyla, Mishel, equipo comercial",
                )

                formato_sugerido = st.text_area(
                    "Formato sugerido",
                    placeholder=(
                        "Ejemplo: vertical 9:16, buena luz, "
                        "sin música, versión corta y larga"
                    ),
                    height=100,
                )

                fecha_limite = st.date_input(
                    "Fecha límite",
                    value=date.today(),
                )

                estado_inicial = st.selectbox(
                    "Estado inicial",
                    estados,
                    index=0,
                )

            crear = st.form_submit_button(
                "Crear pedido",
                use_container_width=True,
            )

            if crear:
                if not solicitud.strip():
                    st.error(
                        "El pedido de grabación no puede estar vacío."
                    )
                else:
                    nuevo = {
                        "id": (
                            "MAT-"
                            + pd.Timestamp.now().strftime(
                                "%Y%m%d%H%M%S%f"
                            )
                        ),
                        "cliente": cliente_sel,
                        "solicitud": solicitud.strip(),
                        "responsable_cliente": (
                            responsable_cliente.strip()
                        ),
                        "fecha_limite": (
                            fecha_limite.strftime("%Y-%m-%d")
                        ),
                        "estado": estado_inicial,
                        "observacion": indicaciones.strip(),
                        "formato_sugerido": (
                            formato_sugerido.strip()
                        ),
                        "referencia": referencia.strip(),
                        "link_entrega": "",
                        "medio_envio": "",
                        "comentario_cliente": "",
                        "fecha_envio_cliente": "",
                        "observacion_am": "",
                        "fecha_carga": (
                            date.today().strftime("%Y-%m-%d")
                        ),
                        "creado_por": nombre_usuario,
                        "fecha_actualizacion": (
                            date.today().strftime("%Y-%m-%d")
                        ),
                        "actualizado_por": nombre_usuario,
                    }

                    actualizado = pd.concat(
                        [
                            materiales_full,
                            pd.DataFrame([nuevo]),
                        ],
                        ignore_index=True,
                    )

                    save_csv(
                        actualizado,
                        MATERIALES_PATH,
                    )
                    st.success("Pedido creado.")
                    st.rerun()

    if modo == "equipo":
        vista = materiales_full[
            materiales_full["cliente"]
            .astype(str)
            .isin(clientes_opciones)
        ].copy()
    else:
        vista = materiales_full.copy()

    st.markdown("### Seguimiento de pedidos")

    filtro_1, filtro_2 = st.columns(2)

    with filtro_1:
        opciones_filtro_cliente = (
            clientes_opciones
            if len(clientes_opciones) == 1
            else ["Todos"] + clientes_opciones
        )

        cliente_filtro = st.selectbox(
            "Cliente",
            opciones_filtro_cliente,
            key=f"filtro_material_cliente_{modo}_{cliente_fijo}",
        )

    with filtro_2:
        estado_filtro = st.selectbox(
            "Estado",
            ["Todos"] + estados,
            key=f"filtro_material_estado_{modo}_{cliente_fijo}",
        )

    if cliente_filtro != "Todos":
        vista = vista[
            vista["cliente"].astype(str) == cliente_filtro
        ].copy()

    if estado_filtro != "Todos":
        vista = vista[
            vista["estado"].astype(str) == estado_filtro
        ].copy()

    if vista.empty:
        st.info("No hay pedidos para los filtros seleccionados.")
        return

    vista = vista.sort_values(
        ["fecha_limite", "fecha_carga"],
        ascending=[True, False],
    )

    for idx, row in vista.iterrows():
        material_id = str(row.get("id", idx))
        solicitud = str(
            row.get("solicitud", "") or "Material solicitado"
        )
        cliente_txt = str(row.get("cliente", ""))
        estado_actual = str(
            row.get("estado", "") or "Solicitado"
        )
        link_entrega = str(
            row.get("link_entrega", "") or ""
        )
        comentario_cliente = str(
            row.get("comentario_cliente", "") or ""
        )
        medio_envio = str(
            row.get("medio_envio", "") or ""
        )
        fecha_envio = str(
            row.get("fecha_envio_cliente", "") or ""
        )

        with st.container(border=True):
            c_titulo, c_estado = st.columns([3, 1])

            with c_titulo:
                st.markdown(f"### {solicitud}")
                st.caption(
                    f"{cliente_txt} · límite "
                    f"{row.get('fecha_limite', '')}"
                )

            with c_estado:
                if estado_actual == "Requiere cambios":
                    st.warning(estado_actual)
                elif estado_actual in [
                    "Enviado por cliente",
                    "En revisión",
                ]:
                    st.info(estado_actual)
                elif estado_actual in [
                    "Aprobado",
                    "Publicado",
                ]:
                    st.success(estado_actual)
                else:
                    st.caption(estado_actual)

            if row.get("observacion", ""):
                st.markdown("**Indicaciones enviadas**")
                st.write(row.get("observacion", ""))

            if row.get("formato_sugerido", ""):
                st.markdown("**Formato sugerido**")
                st.write(row.get("formato_sugerido", ""))

            if comentario_cliente:
                st.markdown("**Comentario del cliente**")
                st.write(comentario_cliente)

            if medio_envio:
                st.caption(
                    f"Medio de entrega: {medio_envio}"
                    + (
                        f" · Fecha: {fecha_envio}"
                        if fecha_envio
                        else ""
                    )
                )

            if link_entrega:
                st.link_button(
                    "Abrir material entregado",
                    link_entrega,
                    use_container_width=True,
                )

            with st.expander("Revisar y actualizar pedido"):
                nuevo_estado = st.selectbox(
                    "Estado",
                    estados,
                    index=(
                        estados.index(estado_actual)
                        if estado_actual in estados
                        else 0
                    ),
                    key=f"estado_material_am_{material_id}",
                )

                nuevas_indicaciones = st.text_area(
                    "Indicaciones originales",
                    value=str(
                        row.get("observacion", "") or ""
                    ),
                    height=120,
                    key=f"indicaciones_material_am_{material_id}",
                )

                nuevo_formato = st.text_area(
                    "Formato sugerido",
                    value=str(
                        row.get("formato_sugerido", "") or ""
                    ),
                    height=80,
                    key=f"formato_material_am_{material_id}",
                )

                devolucion_am = st.text_area(
                    "Devolución para el cliente",
                    value=str(
                        row.get("observacion_am", "") or ""
                    ),
                    placeholder=(
                        "Ejemplo: volver a grabar con mejor luz, "
                        "sumar una toma, corregir el audio..."
                    ),
                    height=100,
                    key=f"devolucion_material_am_{material_id}",
                )

                if st.button(
                    "Guardar actualización",
                    use_container_width=True,
                    key=f"guardar_material_am_{material_id}",
                ):
                    materiales_actualizados = load_materiales()
                    mask = (
                        materiales_actualizados["id"].astype(str)
                        == material_id
                    )

                    if not mask.any():
                        st.error("No se encontró el pedido.")
                    else:
                        materiales_actualizados.loc[
                            mask, "estado"
                        ] = nuevo_estado
                        materiales_actualizados.loc[
                            mask, "observacion"
                        ] = nuevas_indicaciones.strip()
                        materiales_actualizados.loc[
                            mask, "formato_sugerido"
                        ] = nuevo_formato.strip()
                        materiales_actualizados.loc[
                            mask, "observacion_am"
                        ] = devolucion_am.strip()
                        materiales_actualizados.loc[
                            mask, "fecha_actualizacion"
                        ] = date.today().strftime("%Y-%m-%d")
                        materiales_actualizados.loc[
                            mask, "actualizado_por"
                        ] = nombre_usuario

                        save_csv(
                            materiales_actualizados,
                            MATERIALES_PATH,
                        )
                        st.success("Pedido actualizado.")
                        st.rerun()



def render_crud_table_cliente_seguro(title, path, columns, cliente):
    render_crud_table(title, path, df=None, cliente_preview=cliente)



def render_crud_table(title, path, df=None, cliente_preview=""):
    header(title, "Vista rápida y edición avanzada")

    columns = columnas_por_path(path)
    if df is None:
        df_preview = read_csv_preview(path, columns, limit=80, cliente=cliente_preview)
    else:
        df_preview = df.copy().fillna("").head(80)

    total_aprox = contar_registros(path, columns)

    c1, c2, c3 = st.columns(3)
    c1.metric("Registros totales", total_aprox)
    c2.metric("Vista previa", len(df_preview))
    c3.metric("Modo", "rápido")

    if df_preview is None or df_preview.empty:
        st.info("No hay registros cargados.")
    else:
        vista = df_preview.copy()

        if "cliente" in vista.columns and not cliente_preview:
            clientes = ["Todos"] + sorted(vista["cliente"].dropna().astype(str).unique().tolist())
            filtro_cliente = st.selectbox("Cliente", clientes, key=f"filtro_crud_cliente_{title}")
            if filtro_cliente != "Todos":
                vista = vista[vista["cliente"].astype(str) == filtro_cliente]

        if "estado" in vista.columns:
            estados = ["Todos"] + sorted(vista["estado"].dropna().astype(str).unique().tolist())
            filtro_estado = st.selectbox("Estado", estados, key=f"filtro_crud_estado_{title}")
            if filtro_estado != "Todos":
                vista = vista[vista["estado"].astype(str) == filtro_estado]

        st.caption("Vista rápida. Para modificar datos, activá la edición avanzada.")
        st.dataframe(vista, use_container_width=True, hide_index=True)

    activar_edicion = st.toggle(
        f"Activar edición avanzada de {title}",
        value=False,
        key=f"toggle_edicion_{title}_{cliente_preview}",
    )

    if activar_edicion:
        st.warning("Ahora sí se carga la tabla completa para edición.")

        full = read_csv_cliente(path, columns, cliente_preview) if cliente_preview else read_csv(path, columns)

        edited = st.data_editor(
            full,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"editor_{title}_{cliente_preview}",
        )

        if st.button(f"Guardar {title}", use_container_width=True, key=f"guardar_{title}_{cliente_preview}"):
            if cliente_preview and "cliente" in edited.columns:
                edited = edited.copy().fillna("")
                edited["cliente"] = cliente_preview

                full_all = read_csv(path, columns)

                if "id" in full_all.columns and "id" in edited.columns:
                    ids_editados = edited["id"].astype(str).tolist()
                    restante = full_all[~full_all["id"].astype(str).isin(ids_editados)].copy()
                    nuevo = pd.concat([restante, edited], ignore_index=True)
                else:
                    restante = full_all[full_all["cliente"].astype(str) != str(cliente_preview)].copy()
                    nuevo = pd.concat([restante, edited], ignore_index=True)

                save_csv(nuevo, path)
            else:
                save_csv(edited, path)

            st.success("Cambios guardados.")
            st.rerun()



def render_vista_cliente_admin(clientes, contenidos, materiales, campanias, reportes):
    header("Vista cliente", "Previsualización del portal según cliente.")

    if clientes.empty:
        st.info("No hay clientes.")
        return

    cliente = st.selectbox("Cliente", clientes["cliente"].astype(str).tolist())

    render_inicio_cliente(cliente, contenidos, materiales, campanias, reportes)


# ============================================================
# Main
# ============================================================

def banner_cliente_equipo():
    if st.session_state.get("role") != "equipo":
        return

    cliente = st.session_state.get("cliente_equipo_visible") or st.session_state.get("cliente_equipo_activo", "")

    if not cliente:
        return

    st.markdown(
        f"""
        <div style="
            margin: 0 0 18px 0;
            padding: 14px 18px;
            border-radius: 16px;
            background: linear-gradient(135deg, rgba(28,73,128,0.10), rgba(28,73,128,0.04));
            border: 1px solid rgba(28,73,128,0.18);
        ">
            <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: .08em; color: #31506f; font-weight: 700;">
                Cliente activo
            </div>
            <div style="font-size: 1.35rem; font-weight: 850; color: #17324d; margin-top: 2px;">
                {cliente}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def banner_cliente_global():
    role = st.session_state.get("role", "")

    if role == "cliente":
        cliente = st.session_state.get("cliente", "")
        etiqueta = "Portal cliente"
    elif role == "equipo":
        cliente = st.session_state.get("cliente_equipo_visible") or st.session_state.get("cliente_equipo_activo", "")
        etiqueta = "Cliente activo"
    else:
        return

    if not cliente:
        return

    st.markdown(
        f"""
        <div style="
            margin: 0 0 24px 0;
            padding: 28px 32px;
            border-radius: 24px;
            background: linear-gradient(135deg, #244A7C 0%, #3B94A8 100%);
            box-shadow: 0 10px 28px rgba(23, 50, 77, 0.12);
        ">
            <div style="
                font-size: 0.82rem;
                text-transform: uppercase;
                letter-spacing: .08em;
                color: rgba(255,255,255,0.82);
                font-weight: 750;
                margin-bottom: 10px;
            ">
                {etiqueta}
            </div>
            <div style="
                font-size: 1.85rem;
                line-height: 1.15;
                font-weight: 900;
                color: #FFFFFF;
            ">
                {cliente}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )



def columnas_tareas_internas():
    return [
        "id",
        "cliente",
        "tarea",
        "descripcion",
        "responsable_am",
        "prioridad",
        "estado",
        "fecha_limite",
        "checklist",
        "avance",
        "recurrente",
        "frecuencia",
        "intervalo",
        "serie_id",
        "ocurrencia",
        "comentarios",
        "fecha_carga",
        "creado_por",
        "fecha_actualizacion",
        "actualizado_por",
    ]


def parsear_checklist_tarea(valor):
    import json

    if valor is None:
        return []

    if isinstance(valor, list):
        data = valor
    else:
        texto = str(valor).strip()

        if not texto:
            return []

        try:
            data = json.loads(texto)
        except Exception:
            data = []

            for linea in texto.splitlines():
                linea = linea.strip()

                if not linea:
                    continue

                hecho = False

                if linea.lower().startswith(("[x]", "✅", "☑")):
                    hecho = True
                    linea = (
                        linea.replace("[x]", "", 1)
                        .replace("✅", "", 1)
                        .replace("☑", "", 1)
                        .strip()
                    )
                elif linea.startswith("-"):
                    linea = linea[1:].strip()

                if linea:
                    data.append({
                        "texto": linea,
                        "hecho": hecho,
                    })

    resultado = []

    for item in data:
        if isinstance(item, dict):
            texto_item = str(item.get("texto", "")).strip()
            hecho_item = bool(item.get("hecho", False))
        else:
            texto_item = str(item).strip()
            hecho_item = False

        if texto_item:
            resultado.append({
                "texto": texto_item,
                "hecho": hecho_item,
            })

    return resultado


def serializar_checklist_tarea(items):
    import json

    normalizado = []

    for item in items or []:
        texto_item = str(item.get("texto", "")).strip()
        hecho_item = bool(item.get("hecho", False))

        if texto_item:
            normalizado.append({
                "texto": texto_item,
                "hecho": hecho_item,
            })

    return json.dumps(
        normalizado,
        ensure_ascii=False,
    )


def checklist_tarea_desde_texto(texto):
    items = []

    for linea in str(texto or "").splitlines():
        linea = linea.strip()

        if not linea:
            continue

        if linea.startswith("-"):
            linea = linea[1:].strip()

        if linea:
            items.append({
                "texto": linea,
                "hecho": False,
            })

    return items


def avance_checklist_tarea(items):
    items = items or []

    if not items:
        return 0

    completados = sum(
        1
        for item in items
        if bool(item.get("hecho", False))
    )

    return int(round(
        completados / len(items) * 100
    ))


def siguiente_fecha_tarea(fecha_actual, frecuencia, intervalo=1):
    try:
        fecha = pd.Timestamp(fecha_actual)
    except Exception:
        fecha = pd.Timestamp(date.today())

    try:
        intervalo = max(1, int(float(intervalo or 1)))
    except Exception:
        intervalo = 1

    if frecuencia == "Diaria":
        siguiente = fecha + pd.DateOffset(days=intervalo)
    elif frecuencia == "Semanal":
        siguiente = fecha + pd.DateOffset(weeks=intervalo)
    elif frecuencia == "Mensual":
        siguiente = fecha + pd.DateOffset(months=intervalo)
    else:
        siguiente = fecha

    return siguiente.strftime("%Y-%m-%d")


def cargar_tareas_internas(cliente=""):
    columnas = columnas_tareas_internas()

    if cliente:
        return read_csv_cliente(
            TAREAS_PATH,
            columnas,
            cliente,
        )

    return read_csv(
        TAREAS_PATH,
        columnas,
    )


def normalizar_tareas_internas(df):
    columnas = columnas_tareas_internas()

    if df is None or df.empty:
        return pd.DataFrame(columns=columnas)

    df = df.copy()

    for col in columnas:
        if col not in df.columns:
            df[col] = ""

    df = df[columnas].fillna("")

    df["cliente"] = (
        df["cliente"]
        .astype(str)
        .str.strip()
    )

    df["tarea"] = (
        df["tarea"]
        .astype(str)
        .str.strip()
    )

    df["responsable_am"] = (
        df["responsable_am"]
        .astype(str)
        .str.strip()
        .replace("", "Sin asignar")
    )

    df["prioridad"] = (
        df["prioridad"]
        .astype(str)
        .str.strip()
        .replace("", "Media")
    )

    df["estado"] = (
        df["estado"]
        .astype(str)
        .str.strip()
        .replace("", "Pendiente")
    )

    df["recurrente"] = (
        df["recurrente"]
        .astype(str)
        .str.strip()
        .replace("", "No")
    )

    df["frecuencia"] = (
        df["frecuencia"]
        .astype(str)
        .str.strip()
    )

    df["intervalo"] = pd.to_numeric(
        df["intervalo"],
        errors="coerce",
    ).fillna(1).astype(int)

    df["ocurrencia"] = pd.to_numeric(
        df["ocurrencia"],
        errors="coerce",
    ).fillna(1).astype(int)

    df["avance"] = pd.to_numeric(
        df["avance"],
        errors="coerce",
    ).fillna(0).clip(0, 100).astype(int)

    return df


def render_tareas_internas(cliente_fijo="", modo="admin"):
    role = st.session_state.get("role", "")
    username = st.session_state.get("username", "")
    nombre_usuario = st.session_state.get(
        "name",
        username,
    )

    header(
        "Tareas internas",
        "Tablero operativo por cliente, responsable y workflow.",
    )

    estados_kanban = [
        "Pendiente",
        "En curso",
        "En revisión",
        "Finalizada",
        "Pausada",
    ]

    prioridades = [
        "Alta",
        "Media",
        "Baja",
    ]

    frecuencias = [
        "Diaria",
        "Semanal",
        "Mensual",
    ]

    usuarios_equipo = usuarios_equipo_disponibles()
    responsables = ["Sin asignar"] + usuarios_equipo

    if modo == "equipo":
        clientes_opciones = (
            [cliente_fijo]
            if cliente_fijo
            else clientes_visibles_para_usuario()
        )
    else:
        clientes_df = load_clientes()

        if (
            clientes_df is None
            or clientes_df.empty
            or "cliente" not in clientes_df.columns
        ):
            clientes_opciones = []
        else:
            clientes_opciones = sorted(
                clientes_df["cliente"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

    if not clientes_opciones:
        st.info(
            "No hay clientes disponibles para cargar tareas."
        )
        return

    tareas_full = normalizar_tareas_internas(
        cargar_tareas_internas()
    )

    if modo == "equipo":
        clientes_permitidos = set(clientes_opciones)

        tareas_vista_base = tareas_full[
            tareas_full["cliente"]
            .astype(str)
            .isin(clientes_permitidos)
        ].copy()
    else:
        tareas_vista_base = tareas_full.copy()

    # ========================================================
    # Alta de tarea
    # ========================================================

    with st.expander(
        "Crear nueva tarea interna",
        expanded=(modo == "admin"),
    ):
        with st.form(
            f"form_nueva_tarea_interna_{modo}_{cliente_fijo or 'admin'}"
        ):
            col_1, col_2 = st.columns([1.5, 1])

            with col_1:
                if modo == "equipo" and cliente_fijo:
                    cliente_sel = cliente_fijo

                    st.text_input(
                        "Cliente",
                        value=cliente_sel,
                        disabled=True,
                    )
                else:
                    cliente_sel = st.selectbox(
                        "Cliente",
                        clientes_opciones,
                        key=f"tarea_cliente_{modo}",
                    )

                tarea_txt = st.text_input(
                    "Tarea",
                    placeholder="Ejemplo: preparar reporte mensual",
                )

                descripcion = st.text_area(
                    "Descripción / detalle operativo",
                    placeholder=(
                        "Indicaciones, links, contexto y "
                        "entregables esperados."
                    ),
                    height=120,
                )

                checklist_txt = st.text_area(
                    "Checklist / workflow",
                    placeholder=(
                        "Un paso por línea. Ejemplo:\n"
                        "Relevar información\n"
                        "Preparar borrador\n"
                        "Revisar internamente\n"
                        "Enviar al cliente"
                    ),
                    height=140,
                )

            with col_2:
                responsable_sel = st.selectbox(
                    "Responsable",
                    responsables,
                    key=f"tarea_responsable_{modo}",
                )

                prioridad_sel = st.selectbox(
                    "Prioridad",
                    prioridades,
                    index=1,
                    key=f"tarea_prioridad_{modo}",
                )

                fecha_limite = st.date_input(
                    "Fecha límite",
                    value=date.today(),
                )

                estado_sel = st.selectbox(
                    "Estado inicial",
                    estados_kanban,
                    key=f"tarea_estado_inicial_{modo}",
                )

                es_recurrente = st.checkbox(
                    "Tarea recurrente",
                    value=False,
                )

                if es_recurrente:
                    frecuencia_sel = st.selectbox(
                        "Frecuencia",
                        frecuencias,
                    )

                    intervalo_sel = st.number_input(
                        "Repetir cada",
                        min_value=1,
                        max_value=24,
                        value=1,
                        step=1,
                        help=(
                            "Ejemplo: cada 1 semana o "
                            "cada 3 meses."
                        ),
                    )
                else:
                    frecuencia_sel = ""
                    intervalo_sel = 1

            crear = st.form_submit_button(
                "Crear tarea",
                use_container_width=True,
            )

            if crear:
                if not tarea_txt.strip():
                    st.error(
                        "La tarea no puede estar vacía."
                    )
                else:
                    ahora_id = pd.Timestamp.now().strftime(
                        "%Y%m%d%H%M%S%f"
                    )

                    tarea_id = f"TAR-{ahora_id}"

                    checklist_items = (
                        checklist_tarea_desde_texto(
                            checklist_txt
                        )
                    )

                    nueva = {
                        "id": tarea_id,
                        "cliente": cliente_sel,
                        "tarea": tarea_txt.strip(),
                        "descripcion": descripcion.strip(),
                        "responsable_am": responsable_sel,
                        "prioridad": prioridad_sel,
                        "estado": estado_sel,
                        "fecha_limite": (
                            fecha_limite.strftime("%Y-%m-%d")
                        ),
                        "checklist": (
                            serializar_checklist_tarea(
                                checklist_items
                            )
                        ),
                        "avance": (
                            avance_checklist_tarea(
                                checklist_items
                            )
                        ),
                        "recurrente": (
                            "Sí"
                            if es_recurrente
                            else "No"
                        ),
                        "frecuencia": frecuencia_sel,
                        "intervalo": int(intervalo_sel),
                        "serie_id": (
                            f"SER-{ahora_id}"
                            if es_recurrente
                            else ""
                        ),
                        "ocurrencia": 1,
                        "comentarios": "",
                        "fecha_carga": (
                            date.today().strftime("%Y-%m-%d")
                        ),
                        "creado_por": nombre_usuario,
                        "fecha_actualizacion": (
                            date.today().strftime("%Y-%m-%d")
                        ),
                        "actualizado_por": nombre_usuario,
                    }

                    actualizado = pd.concat(
                        [
                            tareas_full,
                            pd.DataFrame([nueva]),
                        ],
                        ignore_index=True,
                    )

                    save_csv(
                        actualizado,
                        TAREAS_PATH,
                    )

                    st.success(
                        "Tarea creada correctamente."
                    )
                    st.rerun()

    # ========================================================
    # Filtros
    # ========================================================

    st.markdown("### Tablero Kanban")

    f1, f2, f3, f4 = st.columns(
        [2, 1.5, 1, 1]
    )

    with f1:
        if modo == "equipo" and cliente_fijo:
            cliente_filtro = cliente_fijo
            st.caption(
                f"Cliente activo: {cliente_filtro}"
            )
        else:
            cliente_filtro = st.selectbox(
                "Filtrar por cliente",
                ["Todos"] + clientes_opciones,
                key=f"filtro_cliente_tareas_{modo}",
            )

    with f2:
        responsables_disponibles = sorted(
            tareas_vista_base["responsable_am"]
            .dropna()
            .astype(str)
            .replace("", "Sin asignar")
            .unique()
            .tolist()
        )

        responsable_filtro = st.selectbox(
            "Responsable",
            ["Todos"] + responsables_disponibles,
            key=f"filtro_responsable_tareas_{modo}",
        )

    with f3:
        prioridad_filtro = st.selectbox(
            "Prioridad",
            ["Todas"] + prioridades,
            key=f"filtro_prioridad_tareas_{modo}",
        )

    with f4:
        recurrencia_filtro = st.selectbox(
            "Recurrencia",
            ["Todas", "Recurrentes", "No recurrentes"],
            key=f"filtro_recurrencia_tareas_{modo}",
        )

    tareas_vista = tareas_vista_base.copy()

    if cliente_filtro != "Todos":
        tareas_vista = tareas_vista[
            tareas_vista["cliente"].astype(str)
            == str(cliente_filtro)
        ].copy()

    if responsable_filtro != "Todos":
        tareas_vista = tareas_vista[
            tareas_vista["responsable_am"].astype(str)
            == str(responsable_filtro)
        ].copy()

    if prioridad_filtro != "Todas":
        tareas_vista = tareas_vista[
            tareas_vista["prioridad"].astype(str)
            == str(prioridad_filtro)
        ].copy()

    if recurrencia_filtro == "Recurrentes":
        tareas_vista = tareas_vista[
            tareas_vista["recurrente"] == "Sí"
        ].copy()
    elif recurrencia_filtro == "No recurrentes":
        tareas_vista = tareas_vista[
            tareas_vista["recurrente"] != "Sí"
        ].copy()

    k1, k2, k3, k4 = st.columns(4)

    k1.metric(
        "Tareas visibles",
        len(tareas_vista),
    )

    k2.metric(
        "Pendientes",
        len(
            tareas_vista[
                tareas_vista["estado"] == "Pendiente"
            ]
        ),
    )

    k3.metric(
        "En curso",
        len(
            tareas_vista[
                tareas_vista["estado"] == "En curso"
            ]
        ),
    )

    k4.metric(
        "Recurrentes",
        len(
            tareas_vista[
                tareas_vista["recurrente"] == "Sí"
            ]
        ),
    )

    if tareas_vista.empty:
        st.info(
            "No hay tareas para los filtros seleccionados."
        )
        return

    # ========================================================
    # Kanban
    # ========================================================

    columnas_kanban = st.columns(
        len(estados_kanban)
    )

    for idx_estado, estado in enumerate(
        estados_kanban
    ):
        subset = tareas_vista[
            tareas_vista["estado"].astype(str)
            == estado
        ].copy()

        with columnas_kanban[idx_estado]:
            st.markdown(f"#### {estado}")
            st.caption(f"{len(subset)} tarea(s)")

            if subset.empty:
                st.caption("Sin tareas.")
                continue

            for _, row in subset.iterrows():
                tarea_id = str(row.get("id", ""))
                tarea_titulo = str(
                    row.get("tarea", "Sin título")
                )
                cliente_txt = str(
                    row.get("cliente", "")
                )
                responsable_txt = str(
                    row.get(
                        "responsable_am",
                        "Sin asignar",
                    )
                )
                prioridad_txt = str(
                    row.get("prioridad", "Media")
                )
                fecha_txt = str(
                    row.get("fecha_limite", "")
                )
                descripcion_txt = str(
                    row.get("descripcion", "")
                )
                comentarios_txt = str(
                    row.get("comentarios", "")
                )
                recurrente_txt = str(
                    row.get("recurrente", "No")
                )
                frecuencia_txt = str(
                    row.get("frecuencia", "")
                )
                intervalo_val = int(
                    row.get("intervalo", 1) or 1
                )
                serie_id = str(
                    row.get("serie_id", "")
                )
                ocurrencia_val = int(
                    row.get("ocurrencia", 1) or 1
                )

                checklist_items = (
                    parsear_checklist_tarea(
                        row.get("checklist", "")
                    )
                )

                avance_val = avance_checklist_tarea(
                    checklist_items
                )

                with st.container(border=True):
                    st.markdown(
                        f"**{tarea_titulo}**"
                    )
                    st.caption(cliente_txt)
                    st.caption(
                        f"Responsable: {responsable_txt}"
                    )
                    st.caption(
                        f"Prioridad: {prioridad_txt} "
                        f"· Límite: {fecha_txt}"
                    )

                    if recurrente_txt == "Sí":
                        st.info(
                            f"Recurrente: cada "
                            f"{intervalo_val} "
                            f"{frecuencia_txt.lower()}"
                            + (
                                f" · Ocurrencia {ocurrencia_val}"
                                if ocurrencia_val
                                else ""
                            )
                        )

                    if descripcion_txt:
                        st.write(descripcion_txt)

                    st.progress(
                        avance_val / 100
                    )
                    st.caption(
                        f"Avance: {avance_val}%"
                    )

                    if checklist_items:
                        st.markdown("**Checklist**")

                        checklist_actualizado = []

                        for i, item in enumerate(
                            checklist_items
                        ):
                            marcado = st.checkbox(
                                str(item.get("texto", "")),
                                value=bool(
                                    item.get("hecho", False)
                                ),
                                key=(
                                    f"check_tarea_"
                                    f"{tarea_id}_{i}"
                                ),
                            )

                            checklist_actualizado.append({
                                "texto": str(
                                    item.get("texto", "")
                                ),
                                "hecho": marcado,
                            })
                    else:
                        checklist_actualizado = []
                        st.caption(
                            "Sin checklist cargado."
                        )

                    if comentarios_txt:
                        with st.expander("Historial"):
                            st.write(comentarios_txt)

                    with st.expander(
                        "Actualizar tarea"
                    ):
                        nuevo_estado = st.selectbox(
                            "Estado",
                            estados_kanban,
                            index=(
                                estados_kanban.index(estado)
                                if estado in estados_kanban
                                else 0
                            ),
                            key=f"estado_tarea_{tarea_id}",
                        )

                        nuevos_items_txt = st.text_area(
                            "Agregar ítems al checklist",
                            value="",
                            placeholder="Un ítem por línea",
                            height=80,
                            key=(
                                f"nuevo_checklist_tarea_"
                                f"{tarea_id}"
                            ),
                        )

                        nuevo_comentario = st.text_area(
                            "Comentario / avance",
                            value="",
                            placeholder=(
                                "Agregar actualización breve..."
                            ),
                            key=(
                                f"comentario_tarea_"
                                f"{tarea_id}"
                            ),
                            height=90,
                        )

                        if st.button(
                            "Guardar avance",
                            key=(
                                f"guardar_tarea_"
                                f"{tarea_id}"
                            ),
                            use_container_width=True,
                        ):
                            tareas_actualizadas = (
                                normalizar_tareas_internas(
                                    cargar_tareas_internas()
                                )
                            )

                            mask = (
                                tareas_actualizadas["id"]
                                .astype(str)
                                == tarea_id
                            )

                            if not mask.any():
                                st.error(
                                    "No se encontró la tarea."
                                )
                            else:
                                estado_anterior = str(
                                    tareas_actualizadas
                                    .loc[mask, "estado"]
                                    .iloc[0]
                                )

                                nuevos_items = (
                                    checklist_tarea_desde_texto(
                                        nuevos_items_txt
                                    )
                                )

                                checklist_final = (
                                    checklist_actualizado
                                    + nuevos_items
                                )

                                avance_final = (
                                    avance_checklist_tarea(
                                        checklist_final
                                    )
                                )

                                tareas_actualizadas.loc[
                                    mask, "estado"
                                ] = nuevo_estado

                                tareas_actualizadas.loc[
                                    mask, "checklist"
                                ] = (
                                    serializar_checklist_tarea(
                                        checklist_final
                                    )
                                )

                                tareas_actualizadas.loc[
                                    mask, "avance"
                                ] = avance_final

                                tareas_actualizadas.loc[
                                    mask,
                                    "fecha_actualizacion",
                                ] = date.today().strftime(
                                    "%Y-%m-%d"
                                )

                                tareas_actualizadas.loc[
                                    mask,
                                    "actualizado_por",
                                ] = nombre_usuario

                                if nuevo_comentario.strip():
                                    anterior = str(
                                        tareas_actualizadas
                                        .loc[
                                            mask,
                                            "comentarios",
                                        ]
                                        .iloc[0]
                                        or ""
                                    )

                                    agregado = (
                                        f"{date.today().strftime('%Y-%m-%d')}"
                                        f" - {nombre_usuario}: "
                                        f"{nuevo_comentario.strip()}"
                                    )

                                    tareas_actualizadas.loc[
                                        mask,
                                        "comentarios",
                                    ] = (
                                        anterior
                                        + "\n"
                                        + agregado
                                    ).strip()

                                # --------------------------------
                                # Generar próxima ocurrencia
                                # solo al finalizar por primera vez
                                # --------------------------------

                                debe_generar = (
                                    recurrente_txt == "Sí"
                                    and nuevo_estado == "Finalizada"
                                    and estado_anterior != "Finalizada"
                                )

                                if debe_generar:
                                    proxima_ocurrencia = (
                                        ocurrencia_val + 1
                                    )

                                    ya_existe = False

                                    if serie_id:
                                        ya_existe = (
                                            (
                                                tareas_actualizadas[
                                                    "serie_id"
                                                ].astype(str)
                                                == serie_id
                                            )
                                            & (
                                                tareas_actualizadas[
                                                    "ocurrencia"
                                                ].astype(int)
                                                == proxima_ocurrencia
                                            )
                                        ).any()

                                    if not ya_existe:
                                        checklist_reiniciado = [
                                            {
                                                "texto": str(
                                                    item.get(
                                                        "texto",
                                                        "",
                                                    )
                                                ),
                                                "hecho": False,
                                            }
                                            for item
                                            in checklist_final
                                            if str(
                                                item.get(
                                                    "texto",
                                                    "",
                                                )
                                            ).strip()
                                        ]

                                        siguiente_fecha = (
                                            siguiente_fecha_tarea(
                                                fecha_txt,
                                                frecuencia_txt,
                                                intervalo_val,
                                            )
                                        )

                                        nueva_id = (
                                            "TAR-"
                                            + pd.Timestamp.now()
                                            .strftime(
                                                "%Y%m%d%H%M%S%f"
                                            )
                                        )

                                        nueva_ocurrencia = {
                                            "id": nueva_id,
                                            "cliente": cliente_txt,
                                            "tarea": tarea_titulo,
                                            "descripcion": (
                                                descripcion_txt
                                            ),
                                            "responsable_am": (
                                                responsable_txt
                                            ),
                                            "prioridad": (
                                                prioridad_txt
                                            ),
                                            "estado": "Pendiente",
                                            "fecha_limite": (
                                                siguiente_fecha
                                            ),
                                            "checklist": (
                                                serializar_checklist_tarea(
                                                    checklist_reiniciado
                                                )
                                            ),
                                            "avance": 0,
                                            "recurrente": "Sí",
                                            "frecuencia": (
                                                frecuencia_txt
                                            ),
                                            "intervalo": (
                                                intervalo_val
                                            ),
                                            "serie_id": serie_id,
                                            "ocurrencia": (
                                                proxima_ocurrencia
                                            ),
                                            "comentarios": "",
                                            "fecha_carga": (
                                                date.today()
                                                .strftime(
                                                    "%Y-%m-%d"
                                                )
                                            ),
                                            "creado_por": (
                                                "Generación automática"
                                            ),
                                            "fecha_actualizacion": (
                                                date.today()
                                                .strftime(
                                                    "%Y-%m-%d"
                                                )
                                            ),
                                            "actualizado_por": (
                                                nombre_usuario
                                            ),
                                        }

                                        tareas_actualizadas = (
                                            pd.concat(
                                                [
                                                    tareas_actualizadas,
                                                    pd.DataFrame(
                                                        [
                                                            nueva_ocurrencia
                                                        ]
                                                    ),
                                                ],
                                                ignore_index=True,
                                            )
                                        )

                                save_csv(
                                    tareas_actualizadas,
                                    TAREAS_PATH,
                                )

                                if debe_generar:
                                    st.success(
                                        "Tarea actualizada y próxima "
                                        "ocurrencia generada."
                                    )
                                else:
                                    st.success(
                                        "Tarea actualizada."
                                    )

                                st.rerun()



def main():
    ensure_data_dir()
    seed_data()

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if "auth" not in st.session_state:
        st.session_state["auth"] = False

    if not st.session_state.get("logged_in", False) and not st.session_state.get("auth", False):
        login()
        return

    menu = sidebar()
    banner_cliente_global()
    inicio_menu_perf = perf_start()
    if os.getenv("PERF_DEBUG", "0") == "1":
        print(f"[PERF] MENU START role={st.session_state.get('role')} menu={menu}")

    if menu == "Documentos":
        st.warning("El módulo Documentos fue desactivado del MVP.")
        role_tmp = st.session_state.get("role", "")
        menu = "Dashboard AM" if role_tmp in ["admin", "admin_general"] else "Inicio"

    role = st.session_state.get("role")
    cliente_user = st.session_state.get("cliente")

    if role == "cliente":
        cliente = cliente_user

        if menu == "Inicio":
            render_inicio_cliente_ejecutivo(cliente)
        elif menu == "Cuenta corriente":
            render_cuenta_corriente_cliente(cliente)
        elif menu == "Calendario":
            render_calendario(cliente, load_contenidos(cliente))
        elif menu == "Aprobaciones":
            render_aprobaciones(cliente, load_contenidos(cliente))
        elif menu == "Materiales":
            render_materiales(cliente, load_materiales(cliente))
        elif menu == "Campañas":
            render_campanias(cliente, load_campanias(cliente))
        elif menu == "Reportes":
            render_reportes(cliente, load_reportes(cliente))
        elif menu == "Objetivos":
            render_objetivos(cliente, modo="cliente")
        elif menu == "Cash Flow":
            render_indicadores(cliente, modo="cliente")

    else:
        role_actual = st.session_state.get("role", "")

        if role_actual == "equipo":
            cliente_equipo = st.session_state.get("cliente_equipo_activo", "")

            if menu == "Sin clientes asignados":
                header("Sin clientes asignados", "Pedile a un administrador que te asigne clientes desde Usuarios.")
                st.info("Todavía no tenés clientes asignados para operar.")
            elif menu == "Portal cliente":
                render_inicio_cliente_ejecutivo(cliente_equipo)
            elif menu == "Objetivos":
                render_objetivos(cliente_equipo, modo="cliente")
            elif menu == "Cash Flow":
                render_indicadores(cliente_equipo, modo="cliente")
            elif menu == "Contenidos":
                render_contenidos_equipo(cliente_equipo)
            elif menu == "Materiales":
                render_materiales_gestion(
                    cliente_fijo=cliente_equipo,
                    modo="equipo",
                )
            elif menu == "Campañas":
                render_crud_table_cliente_seguro(
                    "Campañas",
                    CAMPANIAS_PATH,
                    [
                        "id",
                        "cliente",
                        "campania",
                        "plataforma",
                        "objetivo",
                        "presupuesto",
                        "estado",
                        "leads",
                        "costo_por_lead",
                        "observacion",
                    ],
                    cliente_equipo,
                )
            elif menu == "Reportes":
                render_reportes_gestion(
                    cliente_fijo=cliente_equipo,
                    modo="equipo",
                )
            elif menu == "Tareas":
                render_tareas_internas(cliente_fijo=cliente_equipo, modo="equipo")

        else:
            if menu == "Dashboard AM":
                render_admin_dashboard_ligero()
            elif menu == "Edición rápida":
                render_edicion_rapida_ligera()
            elif menu == "Usuarios":
                render_usuarios(load_clientes())
            elif menu == "Onboarding":
                render_onboarding_cliente()
            elif menu == "Clientes":
                render_gestion_clientes()
            elif menu == "Objetivos":
                render_objetivos("", modo="admin")
            elif menu == "Cash Flow":
                render_indicadores("", modo="admin")
            elif menu == "Cuenta corriente":
                render_cuenta_corriente_admin()
            elif menu == "Contenidos":
                render_crud_table("Contenidos", CONTENIDOS_PATH)
            elif menu == "Materiales":
                render_materiales_gestion(modo="admin")
            elif menu == "Campañas":
                render_crud_table("Campañas", CAMPANIAS_PATH)
            elif menu == "Reportes":
                render_reportes_gestion(modo="admin")
            elif menu == "Tareas":
                render_tareas_internas(modo="admin")
            elif menu == "Vista cliente":
                clientes, contenidos, materiales, campanias, reportes, _ = load_data()
                render_vista_cliente_admin(clientes, contenidos, materiales, campanias, reportes)


if __name__ == "__main__":
    main()
