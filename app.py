from pathlib import Path
import base64
from PIL import Image
from datetime import date
import pandas as pd
import streamlit as st

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
        "role": "admin",
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
    candidatos = [
        logo_sidebar_path(),
        ASSETS_DIR / "isologo B.jpg",
        ASSETS_DIR / "isologo B.jpeg",
        ASSETS_DIR / "isologo B.webp",
        ASSETS_DIR / "isologo B",
        ASSETS_DIR / "Isologo B.png",
        ASSETS_DIR / "Isologo B.jpg",
        ASSETS_DIR / "Isologo B.jpeg",
        ASSETS_DIR / "Isologo B.webp",
        ASSETS_DIR / "Isologo B",
    ]
    for p in candidatos:
        if p.exists():
            return p
    return None



def logo_login_path():
    p = ASSETS_DIR / "isologo A.png"
    return p if p.exists() else None


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


def read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    ensure_data_dir()
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=columns)

    for c in columns:
        if c not in df.columns:
            df[c] = ""
    return df[columns]


def save_csv(df: pd.DataFrame, path: Path):
    ensure_data_dir()
    df.to_csv(path, index=False)


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


def load_data():
    clientes = read_csv(
        CLIENTES_PATH,
        ["cliente", "rubro", "estado", "plan", "responsable_am", "fecha_inicio", "notas"],
    )
    contenidos = read_csv(
        CONTENIDOS_PATH,
        ["id", "cliente", "fecha", "canal", "formato", "tema", "objetivo", "copy", "link_canva", "estado", "comentario_cliente"],
    )
    materiales = read_csv(
        MATERIALES_PATH,
        ["id", "cliente", "solicitud", "responsable_cliente", "fecha_limite", "estado", "observacion"],
    )
    campanias = read_csv(
        CAMPANIAS_PATH,
        ["id", "cliente", "campania", "plataforma", "objetivo", "presupuesto", "estado", "leads", "costo_por_lead", "observacion"],
    )
    reportes = read_csv(
        REPORTES_PATH,
        ["id", "cliente", "mes", "alcance", "interacciones", "consultas", "inversion", "estado", "que_funciono", "proximo_foco"],
    )
    tareas = read_csv(
        TAREAS_PATH,
        ["id", "cliente", "tarea", "responsable_am", "prioridad", "estado", "fecha_limite"],
    )
    return clientes, contenidos, materiales, campanias, reportes, tareas


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

def login():
    logo_path = ASSETS_DIR / "isologo_login_limpio.png"
    if not logo_path.exists():
        logo_path = ASSETS_DIR / "isologo A.png"

    logo_b64 = img_to_base64(logo_path) if logo_path.exists() else ""

    st.markdown("<div style='height: 76px;'></div>", unsafe_allow_html=True)

    left_pad, brand_col, login_col, right_pad = st.columns([0.05, 0.42, 0.48, 0.05], gap="large")

    with brand_col:
        if logo_b64:
            st.markdown(
                f"""
                <div style="
                    display: flex;
                    align-items: center;
                    gap: 28px;
                    margin-top: 42px;
                    margin-left: 4px;
                ">
                    <div style="
                        color: #244777;
                        font-size: 3.15rem;
                        line-height: 1;
                        font-weight: 850;
                        letter-spacing: -0.045em;
                        white-space: nowrap;
                    ">
                        AM Hub
                    </div>
                    <img src="data:image/png;base64,{logo_b64}" style="
                        width: 150px;
                        height: auto;
                        display: block;
                    " />
                </div>

                <div style="
                    margin-top: 28px;
                    margin-left: 4px;
                    color: #667085;
                    font-size: 1.45rem;
                    line-height: 1.35;
                    font-weight: 500;
                    letter-spacing: -0.02em;
                    white-space: nowrap;
                ">
                    Portal de gestión digital | AM Consultora
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div style="
                    margin-top: 42px;
                    color: #244777;
                    font-size: 3.15rem;
                    line-height: 1;
                    font-weight: 850;
                    letter-spacing: -0.045em;
                ">
                    AM Hub
                </div>
                <div style="
                    margin-top: 28px;
                    color: #667085;
                    font-size: 1.45rem;
                    line-height: 1.35;
                    font-weight: 500;
                    letter-spacing: -0.02em;
                    white-space: nowrap;
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
                border-radius: 18px;
                padding: 30px 34px 22px 34px;
                box-shadow: 0 16px 40px rgba(16, 24, 40, 0.07);
                margin-top: 18px;
            ">
                <h2 style="
                    margin: 0 0 12px 0;
                    color: #172033;
                    font-size: 1.45rem;
                    line-height: 1.15;
                    font-weight: 850;
                ">
                    Acceso clientes
                </h2>
                <p style="
                    margin: 0;
                    color: #667085;
                    font-size: 0.88rem;
                    line-height: 1.4;
                ">
                    Ingresá con tu usuario para ver el portal correspondiente.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Ingresar")

        if submit:
            user = USERS.get(username)
            if user and user["password"] == password:
                st.session_state["auth"] = True
                st.session_state["username"] = username
                st.session_state["role"] = user["role"]
                st.session_state["name"] = user["name"]
                st.session_state["cliente"] = user["cliente"]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")

def logout_button():
    if st.sidebar.button("Cerrar sesión"):
        for k in ["auth", "username", "role", "name", "cliente"]:
            st.session_state.pop(k, None)
        st.rerun()


# ============================================================
# Sidebar
# ============================================================



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

def sidebar():
    logo_path = logo_sidebar_path()

    if logo_path is not None:
        st.sidebar.image(str(logo_path), width=190)
    else:
        st.sidebar.markdown("## AM Consultora")

    st.sidebar.markdown("### AM Hub")
    st.sidebar.caption("Portal de gestión digital")

    role = st.session_state.get("role")
    if role == "cliente":
        menu = st.sidebar.radio(
            "Menú",
            [
                "Inicio",
                "Calendario",
                "Aprobaciones",
                "Materiales",
                "Campañas",
                "Reportes",
            ],
        )
    else:
        menu = st.sidebar.radio(
            "Menú",
            [
                "Dashboard AM",
                "Clientes",
                "Contenidos",
                "Materiales",
                "Campañas",
                "Reportes",
                "Tareas",
                "Vista cliente",
            ],
        )

    st.sidebar.divider()
    st.sidebar.write(f"**Usuario:** {st.session_state.get('name')}")
    st.sidebar.write(f"**Rol:** {role}")
    logout_button()

    return menu

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


def header(title, subtitle=""):
    st.markdown(f'<div class="main-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="subtitle">{subtitle}</div>', unsafe_allow_html=True)


def render_inicio_cliente(cliente, contenidos, materiales, campanias, reportes):
    header("AM Hub", f"Portal de gestión digital | {cliente}")

    contenidos_c = filter_cliente(contenidos, cliente)
    materiales_c = filter_cliente(materiales, cliente)
    campanias_c = filter_cliente(campanias, cliente)
    reportes_c = filter_cliente(reportes, cliente)

    pendientes_aprobacion = contenidos_c[contenidos_c["estado"].astype(str).str.contains("Pendiente|revisión|aprobación", case=False, na=False)]
    materiales_pend = materiales_c[~materiales_c["estado"].astype(str).str.contains("Recibido|Publicado|Usado", case=False, na=False)]
    camp_act = campanias_c[campanias_c["estado"].astype(str).str.contains("Activa", case=False, na=False)]
    rep_disp = reportes_c[reportes_c["estado"].astype(str).str.contains("Disponible", case=False, na=False)]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Contenidos del mes", len(contenidos_c), "Calendario vigente")
    with c2:
        kpi_card("Pendientes de aprobación", len(pendientes_aprobacion), "Requieren revisión")
    with c3:
        kpi_card("Campañas activas", len(camp_act), "Pauta en curso")
    with c4:
        kpi_card("Reportes disponibles", len(rep_disp), "Últimos informes")

    st.markdown("### Calendario de contenidos")
    if contenidos_c.empty:
        st.info("Todavía no hay contenidos cargados.")
    else:
        vista = contenidos_c[["fecha", "canal", "formato", "tema", "estado"]].copy()
        st.dataframe(vista, use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Pendientes de aprobación")
        if pendientes_aprobacion.empty:
            st.success("No hay contenidos pendientes de aprobación.")
        else:
            for _, row in pendientes_aprobacion.head(5).iterrows():
                with st.container(border=True):
                    st.write(f"**{row['formato']} — {row['tema']}**")
                    st.caption(f"Fecha sugerida: {row['fecha']} | Canal: {row['canal']}")
                    st.markdown(status_badge(row["estado"]), unsafe_allow_html=True)

    with col2:
        st.markdown("### Materiales pendientes")
        if materiales_pend.empty:
            st.success("No hay materiales pendientes.")
        else:
            for _, row in materiales_pend.head(5).iterrows():
                with st.container(border=True):
                    st.write(f"**{row['solicitud']}**")
                    st.caption(f"Responsable: {row['responsable_cliente']} | Límite: {row['fecha_limite']}")
                    st.markdown(status_badge(row["estado"]), unsafe_allow_html=True)


def render_calendario(cliente, contenidos):
    header("Calendario de contenidos", "Revisión de piezas, copies y fechas sugeridas.")

    df = filter_cliente(contenidos, cliente)

    if df.empty:
        st.info("No hay contenidos cargados.")
        return

    filtros = st.columns(3)
    with filtros[0]:
        estado = st.selectbox("Estado", ["Todos"] + sorted(df["estado"].dropna().astype(str).unique().tolist()))
    with filtros[1]:
        formato = st.selectbox("Formato", ["Todos"] + sorted(df["formato"].dropna().astype(str).unique().tolist()))
    with filtros[2]:
        canal = st.selectbox("Canal", ["Todos"] + sorted(df["canal"].dropna().astype(str).unique().tolist()))

    vista = df.copy()

    if estado != "Todos":
        vista = vista[vista["estado"].astype(str) == estado]
    if formato != "Todos":
        vista = vista[vista["formato"].astype(str) == formato]
    if canal != "Todos":
        vista = vista[vista["canal"].astype(str) == canal]

    st.dataframe(
        vista[["id", "fecha", "canal", "formato", "tema", "objetivo", "estado"]],
        use_container_width=True,
        hide_index=True,
    )


def render_aprobaciones(cliente, contenidos):
    header("Aprobaciones", "Revisá contenidos, copies y links de diseño.")

    df = filter_cliente(contenidos, cliente)
    pendientes = df[df["estado"].astype(str).str.contains("Pendiente|revisión|aprobación", case=False, na=False)].copy()

    if pendientes.empty:
        st.success("No hay contenidos pendientes de aprobación.")
        return

    contenidos_all = contenidos.copy()

    for _, row in pendientes.iterrows():
        with st.container(border=True):
            st.markdown(f"### {row['formato']} — {row['tema']}")
            st.caption(f"{row['fecha']} | {row['canal']} | Objetivo: {row['objetivo']}")
            st.markdown(status_badge(row["estado"]), unsafe_allow_html=True)

            st.markdown("**Copy propuesto**")
            st.write(row["copy"])

            if str(row["link_canva"]).strip():
                st.link_button("Ver diseño en Canva", row["link_canva"])

            comentario = st.text_area(
                "Comentario / correcciones",
                value=str(row.get("comentario_cliente", "")),
                key=f"comentario_{row['id']}",
            )

            c1, c2 = st.columns(2)

            with c1:
                if st.button("Aprobar contenido", key=f"aprobar_{row['id']}"):
                    contenidos_all.loc[contenidos_all["id"] == row["id"], "estado"] = "Aprobado"
                    contenidos_all.loc[contenidos_all["id"] == row["id"], "comentario_cliente"] = comentario
                    save_csv(contenidos_all, CONTENIDOS_PATH)
                    st.success("Contenido aprobado.")
                    st.rerun()

            with c2:
                if st.button("Solicitar correcciones", key=f"corregir_{row['id']}"):
                    contenidos_all.loc[contenidos_all["id"] == row["id"], "estado"] = "Correcciones"
                    contenidos_all.loc[contenidos_all["id"] == row["id"], "comentario_cliente"] = comentario
                    save_csv(contenidos_all, CONTENIDOS_PATH)
                    st.warning("Correcciones registradas.")
                    st.rerun()


def render_materiales(cliente, materiales):
    header("Materiales pendientes", "Solicitudes de fotos, videos, grabaciones o información.")

    df = filter_cliente(materiales, cliente)

    if df.empty:
        st.info("No hay materiales solicitados.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)


def render_campanias(cliente, campanias):
    header("Campañas publicitarias", "Seguimiento simple de pauta y resultados.")

    df = filter_cliente(campanias, cliente)

    if df.empty:
        st.info("No hay campañas cargadas.")
        return

    c1, c2, c3 = st.columns(3)

    presupuesto = pd.to_numeric(df["presupuesto"], errors="coerce").fillna(0).sum()
    leads = pd.to_numeric(df["leads"], errors="coerce").fillna(0).sum()
    activas = df["estado"].astype(str).str.contains("Activa", case=False, na=False).sum()

    c1.metric("Presupuesto", money(presupuesto))
    c2.metric("Leads / consultas", int(leads))
    c3.metric("Campañas activas", int(activas))

    st.dataframe(df, use_container_width=True, hide_index=True)


def render_reportes(cliente, reportes):
    header("Reportería", "Resultados mensuales con lectura estratégica.")

    df = filter_cliente(reportes, cliente)

    if df.empty:
        st.info("No hay reportes cargados.")
        return

    reporte = st.selectbox("Reporte", df["mes"].astype(str).tolist())
    row = df[df["mes"].astype(str) == reporte].iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alcance", f"{int(float(row['alcance'])):,}".replace(",", "."))
    c2.metric("Interacciones", f"{int(float(row['interacciones'])):,}".replace(",", "."))
    c3.metric("Consultas", int(float(row["consultas"])))
    c4.metric("Inversión", money(row["inversion"]))

    st.markdown("### Qué funcionó")
    st.write(row["que_funciono"])

    st.markdown("### Próximo foco")
    st.write(row["proximo_foco"])


# ============================================================
# Vista interna
# ============================================================

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
        st.dataframe(contenidos[["cliente", "fecha", "formato", "tema", "estado"]], use_container_width=True, hide_index=True)

    st.markdown("### Tareas internas")
    if tareas.empty:
        st.info("No hay tareas.")
    else:
        st.dataframe(tareas, use_container_width=True, hide_index=True)


def render_crud_table(title, path, df):
    header(title)

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### Carga rápida")
    with st.expander("Agregar registro"):
        nuevo = {}
        for col in df.columns:
            nuevo[col] = st.text_input(col, key=f"{title}_{col}")

        if st.button(f"Agregar a {title}"):
            df2 = pd.concat([df, pd.DataFrame([nuevo])], ignore_index=True)
            save_csv(df2, path)
            st.success("Registro agregado.")
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

def main():
    ensure_data_dir()
    seed_data()

    if "auth" not in st.session_state:
        st.session_state["auth"] = False

    if not st.session_state["auth"]:
        login()
        return

    clientes, contenidos, materiales, campanias, reportes, tareas = load_data()
    menu = sidebar()

    role = st.session_state.get("role")
    cliente_user = st.session_state.get("cliente")

    if role == "cliente":
        cliente = cliente_user

        if menu == "Inicio":
            render_inicio_cliente(cliente, contenidos, materiales, campanias, reportes)
        elif menu == "Calendario":
            render_calendario(cliente, contenidos)
        elif menu == "Aprobaciones":
            render_aprobaciones(cliente, contenidos)
        elif menu == "Materiales":
            render_materiales(cliente, materiales)
        elif menu == "Campañas":
            render_campanias(cliente, campanias)
        elif menu == "Reportes":
            render_reportes(cliente, reportes)

    else:
        if menu == "Dashboard AM":
            render_admin_dashboard(clientes, contenidos, materiales, campanias, reportes, tareas)
        elif menu == "Clientes":
            render_crud_table("Clientes", CLIENTES_PATH, clientes)
        elif menu == "Contenidos":
            render_crud_table("Contenidos", CONTENIDOS_PATH, contenidos)
        elif menu == "Materiales":
            render_crud_table("Materiales", MATERIALES_PATH, materiales)
        elif menu == "Campañas":
            render_crud_table("Campañas", CAMPANIAS_PATH, campanias)
        elif menu == "Reportes":
            render_crud_table("Reportes", REPORTES_PATH, reportes)
        elif menu == "Tareas":
            render_crud_table("Tareas", TAREAS_PATH, tareas)
        elif menu == "Vista cliente":
            render_vista_cliente_admin(clientes, contenidos, materiales, campanias, reportes)


if __name__ == "__main__":
    main()
