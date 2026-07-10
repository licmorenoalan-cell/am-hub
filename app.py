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
USUARIOS_PATH = DATA_DIR / "usuarios.csv"

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

    df = pd.read_csv(USUARIOS_PATH, dtype=str).fillna("")

    required_cols = ["username", "password", "role", "name", "cliente", "activo"]
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

    clean.to_csv(USUARIOS_PATH, index=False)


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
            key="menu_cliente",
        )
    else:
        menu = st.sidebar.radio(
            "Menú",
            [
                "Dashboard AM",
                "Usuarios",
                "Clientes",
                "Contenidos",
                "Materiales",
                "Campañas",
                "Reportes",
                "Tareas",
                "Vista cliente",
            ],
            key="menu_admin",
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





def render_calendario(cliente, contenidos):
    header("Calendario de contenidos", f"Planificación mensual | {cliente}")

    df = filter_cliente(contenidos, cliente)

    if df.empty:
        st.info("No hay contenidos cargados para este cliente.")
        return

    df = df.copy()

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
            <div style="font-size:1.25rem; font-weight:850; color:#172033; margin-bottom:6px;">
                Vista de planificación
            </div>
            <div style="font-size:0.95rem; color:#667085; line-height:1.45;">
                Acá podés consultar los contenidos planificados, sus objetivos y el estado de cada pieza.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    total = len(df)
    pendientes = df["estado"].astype(str).str.contains("Pendiente|revisión|aprobación|Correcciones|En diseño", case=False, na=False).sum()
    aprobados = df["estado"].astype(str).str.contains("Aprobado|Programado|Publicado", case=False, na=False).sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Contenidos planificados", total)
    c2.metric("Pendientes / revisión", int(pendientes))
    c3.metric("Aprobados / programados", int(aprobados))

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    f1, f2, f3 = st.columns(3)

    with f1:
        estados = ["Todos"] + sorted(df["estado"].dropna().astype(str).unique().tolist())
        estado = st.selectbox("Estado", estados, key="cal_estado_cliente")

    with f2:
        formatos = ["Todos"] + sorted(df["formato"].dropna().astype(str).unique().tolist())
        formato = st.selectbox("Formato", formatos, key="cal_formato_cliente")

    with f3:
        canales = ["Todos"] + sorted(df["canal"].dropna().astype(str).unique().tolist())
        canal = st.selectbox("Canal", canales, key="cal_canal_cliente")

    vista = df.copy()

    if estado != "Todos":
        vista = vista[vista["estado"].astype(str) == estado]
    if formato != "Todos":
        vista = vista[vista["formato"].astype(str) == formato]
    if canal != "Todos":
        vista = vista[vista["canal"].astype(str) == canal]

    st.markdown("### Calendario")

    cols = ["fecha", "canal", "formato", "tema", "objetivo", "estado"]
    cols = [c for c in cols if c in vista.columns]

    st.dataframe(
        vista[cols],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Detalle de piezas")

    for _, row in vista.head(10).iterrows():
        with st.container(border=True):
            top_left, top_right = st.columns([0.76, 0.24])

            with top_left:
                st.markdown(
                    f"""
                    <div style="font-size:1.05rem; font-weight:800; color:#172033;">
                        {row.get('formato', '')} — {row.get('tema', '')}
                    </div>
                    <div style="font-size:0.88rem; color:#667085; margin-top:3px;">
                        {row.get('fecha', '')} | {row.get('canal', '')}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with top_right:
                st.markdown(status_badge(row.get("estado", "")), unsafe_allow_html=True)

            objetivo = str(row.get("objetivo", "")).strip()
            if objetivo:
                st.markdown("**Objetivo**")
                st.write(objetivo)

            copy_text = str(row.get("copy", "")).strip()
            if copy_text:
                with st.expander("Ver copy"):
                    st.write(copy_text)

            link_canva = str(row.get("link_canva", "")).strip()
            if link_canva:
                st.link_button("Ver diseño en Canva", link_canva)

def render_aprobaciones(cliente, contenidos):
    header("Aprobaciones", f"Revisión de contenidos y copies | {cliente}")

    df = filter_cliente(contenidos, cliente)

    if df.empty:
        st.info("No hay contenidos cargados para aprobar.")
        return

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
    c1.metric("Pendientes", len(pendientes))
    c2.metric("Aprobados / programados", len(aprobados))
    c3.metric("Total contenidos", len(df))

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    if pendientes.empty:
        st.success("No hay contenidos pendientes de revisión.")
        return

    st.markdown("### Contenidos para revisar")

    contenidos_all = contenidos.copy()

    for _, row in pendientes.iterrows():
        estado_actual = str(row.get("estado", ""))

        with st.container(border=True):
            top_left, top_right = st.columns([0.76, 0.24])

            with top_left:
                st.markdown(
                    f"""
                    <div style="font-size:1.1rem; font-weight:800; color:#172033; margin-bottom:4px;">
                        {row.get('formato', '')} — {row.get('tema', '')}
                    </div>
                    <div style="font-size:0.88rem; color:#667085; margin-bottom:10px;">
                        {row.get('fecha', '')} | {row.get('canal', '')} | Objetivo: {row.get('objetivo', '')}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with top_right:
                st.markdown(status_badge(estado_actual), unsafe_allow_html=True)

            copy_text = str(row.get("copy", "")).strip()
            if copy_text:
                st.markdown("**Copy propuesto**")
                st.write(copy_text)

            link_canva = str(row.get("link_canva", "")).strip()
            if link_canva:
                st.link_button("Abrir diseño en Canva", link_canva)

            comentario = st.text_area(
                "Comentario / correcciones",
                value=str(row.get("comentario_cliente", "")),
                key=f"comentario_cliente_{row.get('id', '')}",
                placeholder="Escribí cambios o comentarios para el equipo AM...",
            )

            action_left, action_right, _ = st.columns([0.28, 0.32, 0.40])

            with action_left:
                if st.button("Aprobar", key=f"aprobar_{row.get('id', '')}"):
                    contenidos_all.loc[contenidos_all["id"] == row.get("id"), "estado"] = "Aprobado"
                    contenidos_all.loc[contenidos_all["id"] == row.get("id"), "comentario_cliente"] = comentario
                    save_csv(contenidos_all, CONTENIDOS_PATH)
                    st.success("Contenido aprobado.")
                    st.rerun()

            with action_right:
                if st.button("Pedir cambios", key=f"corregir_{row.get('id', '')}"):
                    contenidos_all.loc[contenidos_all["id"] == row.get("id"), "estado"] = "Correcciones"
                    contenidos_all.loc[contenidos_all["id"] == row.get("id"), "comentario_cliente"] = comentario
                    save_csv(contenidos_all, CONTENIDOS_PATH)
                    st.warning("Correcciones registradas.")
                    st.rerun()

    st.markdown("### Historial reciente")

    cols = ["fecha", "canal", "formato", "tema", "estado"]
    cols = [c for c in cols if c in df.columns]

    st.dataframe(df[cols].tail(8), use_container_width=True, hide_index=True)

def render_materiales(cliente, materiales):
    header("Materiales pendientes", f"Solicitudes de material | {cliente}")

    df = filter_cliente(materiales, cliente)

    if df.empty:
        st.info("No hay materiales solicitados.")
        return

    pendientes = df[
        ~df["estado"].astype(str).str.contains("Recibido|Publicado|Usado", case=False, na=False)
    ].copy()

    c1, c2 = st.columns(2)
    c1.metric("Solicitudes totales", len(df))
    c2.metric("Pendientes", len(pendientes))

    st.markdown("### Solicitudes")

    for _, row in df.iterrows():
        with st.container(border=True):
            st.write(f"**{row.get('solicitud', '')}**")
            st.caption(f"Responsable: {row.get('responsable_cliente', '')} | Fecha límite: {row.get('fecha_limite', '')}")
            st.markdown(status_badge(row.get("estado", "")), unsafe_allow_html=True)

            if str(row.get("observacion", "")).strip():
                st.write(row.get("observacion", ""))


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



def render_reportes(cliente, reportes):
    header("Reportería", f"Resultados mensuales y lectura estratégica | {cliente}")

    df = filter_cliente(reportes, cliente)

    if df.empty:
        st.info("No hay reportes cargados.")
        return

    reporte = st.selectbox(
        "Seleccionar reporte",
        df["mes"].astype(str).tolist(),
        key="reporte_cliente_mes",
    )

    row = df[df["mes"].astype(str) == reporte].iloc[0]

    st.markdown(
        f"""
        <div style="
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 22px;
            padding: 24px 28px;
            margin-bottom: 22px;
            box-shadow: 0 12px 30px rgba(16, 24, 40, 0.05);
        ">
            <div style="font-size:0.9rem; color:#667085; margin-bottom:6px;">
                Reporte seleccionado
            </div>
            <div style="font-size:1.75rem; font-weight:850; color:#244777; letter-spacing:-0.035em;">
                {row.get('mes', '')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Alcance", f"{int(float(row.get('alcance', 0))):,}".replace(",", "."))
    c2.metric("Interacciones", f"{int(float(row.get('interacciones', 0))):,}".replace(",", "."))
    c3.metric("Consultas", int(float(row.get("consultas", 0))))
    c4.metric("Inversión", money(row.get("inversion", 0)))

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

    col_left, col_right = st.columns([0.52, 0.48], gap="large")

    with col_left:
        st.markdown("### Lectura estratégica")

        with st.container(border=True):
            st.markdown("**Qué funcionó**")
            st.write(row.get("que_funciono", ""))

            st.markdown("**Próximo foco**")
            st.write(row.get("proximo_foco", ""))

            st.markdown("**Estado del reporte**")
            st.markdown(status_badge(row.get("estado", "")), unsafe_allow_html=True)

    with col_right:
        st.markdown("### Resumen ejecutivo")

        alcance = int(float(row.get("alcance", 0)))
        interacciones = int(float(row.get("interacciones", 0)))
        consultas = int(float(row.get("consultas", 0)))
        inversion = float(row.get("inversion", 0) or 0)

        costo_consulta = inversion / consultas if consultas else 0

        with st.container(border=True):
            st.write(f"Durante **{row.get('mes', '')}**, la gestión alcanzó aproximadamente **{alcance:,} personas**.".replace(",", "."))
            st.write(f"Se registraron **{interacciones:,} interacciones** y **{consultas} consultas**.".replace(",", "."))
            if inversion > 0:
                st.write(f"La inversión publicitaria fue de **{money(inversion)}**, con un costo estimado por consulta de **{money(costo_consulta)}**.")
            else:
                st.write("No se registró inversión publicitaria para este período.")

    st.markdown("### Historial de reportes")

    cols = ["mes", "alcance", "interacciones", "consultas", "inversion", "estado"]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)


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
    c3.metric("Equipo AM", len(df[df["role"].isin(["admin", "equipo"])]))

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
            role = st.selectbox("Rol", ["cliente", "equipo", "admin"])

        with col3:
            cliente = st.selectbox("Cliente asociado", clientes_lista)
            activo = st.selectbox("Activo", ["Sí", "No"])

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
                    }
                ])

                df = pd.concat([df, nuevo], ignore_index=True)
                save_users_df(df)
                st.success("Usuario creado correctamente.")
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
            "role": st.column_config.SelectboxColumn("Rol", options=["admin", "equipo", "cliente"], required=True),
            "name": st.column_config.TextColumn("Nombre visible"),
            "cliente": st.column_config.SelectboxColumn("Cliente asociado", options=clientes_lista),
            "activo": st.column_config.SelectboxColumn("Activo", options=["Sí", "No"], required=True),
        },
        key="usuarios_editor",
    )

    if st.button("Guardar cambios de usuarios"):
        save_users_df(edited)
        st.success("Usuarios actualizados.")
        st.rerun()




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
    header(title, "Carga y gestión de información del portal")

    df = df.copy()

    clientes_df = read_csv(
        CLIENTES_PATH,
        ["cliente", "rubro", "estado", "plan", "responsable_am", "fecha_inicio", "notas"],
    )

    clientes_lista = []
    if clientes_df is not None and not clientes_df.empty and "cliente" in clientes_df.columns:
        clientes_lista = sorted(clientes_df["cliente"].dropna().astype(str).unique().tolist())

    archivo = Path(path).name

    def next_id(dataframe):
        if dataframe is None or dataframe.empty or "id" not in dataframe.columns:
            return 1
        ids = pd.to_numeric(dataframe["id"], errors="coerce").fillna(0)
        return int(ids.max()) + 1

    def append_and_save(nuevo):
        nonlocal df
        nuevo_df = pd.DataFrame([nuevo])
        df = pd.concat([df, nuevo_df], ignore_index=True)
        save_csv(df, path)
        st.success("Registro cargado correctamente.")
        st.rerun()

    st.markdown(
        """
        <div style="
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 20px;
            padding: 20px 24px;
            margin-bottom: 22px;
            box-shadow: 0 10px 24px rgba(16, 24, 40, 0.04);
        ">
            <div style="font-size:1.1rem; font-weight:850; color:#172033; margin-bottom:5px;">
                Carga de información
            </div>
            <div style="font-size:0.94rem; color:#667085; line-height:1.45;">
                Usá los formularios para cargar datos de forma ordenada. Cuando corresponde, el cliente se selecciona desde el desplegable para que la información aparezca en su portal.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------
    # CLIENTES
    # ------------------------------------------------------------
    if archivo == "clientes.csv":
        st.markdown("### Nuevo cliente")

        with st.form("form_clientes"):
            col1, col2, col3 = st.columns(3)

            with col1:
                cliente = st.text_input("Nombre del cliente")
                rubro = st.text_input("Rubro")

            with col2:
                estado = st.selectbox("Estado", ["Activo", "Pausado", "Finalizado", "Prospecto"])
                plan = st.text_input("Plan / servicio")

            with col3:
                responsable_am = st.text_input("Responsable AM")
                fecha_inicio = st.date_input("Fecha de inicio")

            notas = st.text_area("Notas internas")

            submitted = st.form_submit_button("Guardar cliente", use_container_width=True)

            if submitted:
                if not cliente.strip():
                    st.error("El nombre del cliente es obligatorio.")
                else:
                    nuevo = {
                        "cliente": cliente.strip(),
                        "rubro": rubro,
                        "estado": estado,
                        "plan": plan,
                        "responsable_am": responsable_am,
                        "fecha_inicio": fecha_inicio.strftime("%Y-%m-%d"),
                        "notas": notas,
                    }
                    append_and_save(nuevo)

    # ------------------------------------------------------------
    # CONTENIDOS
    # ------------------------------------------------------------
    elif archivo == "contenidos.csv":
        st.markdown("### Nuevo contenido para aprobación")

        if not clientes_lista:
            st.warning("Primero cargá clientes en el menú Clientes.")
        else:
            with st.form("form_contenidos"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    cliente = st.selectbox("Cliente", clientes_lista)
                    fecha = st.date_input("Fecha de publicación / propuesta")

                with col2:
                    canal = st.selectbox("Canal", ["Instagram", "Facebook", "LinkedIn", "TikTok", "YouTube", "Email", "Web", "Otro"])
                    formato = st.selectbox("Formato", ["Post", "Carrusel", "Reel", "Historia", "Video", "Newsletter", "Landing", "Otro"])

                with col3:
                    estado = st.selectbox("Estado", ["Pendiente de aprobación", "En diseño", "Correcciones", "Aprobado", "Programado", "Publicado"])
                    link_canva = st.text_input("Link Canva")

                tema = st.text_input("Tema")
                objetivo = st.text_input("Objetivo")
                copy_text = st.text_area("Copy propuesto")

                submitted = st.form_submit_button("Guardar contenido", use_container_width=True)

                if submitted:
                    if not tema.strip():
                        st.error("El tema es obligatorio.")
                    else:
                        nuevo = {
                            "id": next_id(df),
                            "cliente": cliente,
                            "fecha": fecha.strftime("%Y-%m-%d"),
                            "canal": canal,
                            "formato": formato,
                            "tema": tema,
                            "objetivo": objetivo,
                            "copy": copy_text,
                            "link_canva": link_canva,
                            "estado": estado,
                            "comentario_cliente": "",
                        }
                        append_and_save(nuevo)

    # ------------------------------------------------------------
    # MATERIALES
    # ------------------------------------------------------------
    elif archivo == "materiales.csv":
        st.markdown("### Nuevo material solicitado")

        if not clientes_lista:
            st.warning("Primero cargá clientes en el menú Clientes.")
        else:
            with st.form("form_materiales"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    cliente = st.selectbox("Cliente", clientes_lista)
                    solicitud = st.text_input("Solicitud")

                with col2:
                    responsable_cliente = st.text_input("Responsable del cliente")
                    fecha_limite = st.date_input("Fecha límite")

                with col3:
                    estado = st.selectbox("Estado", ["Solicitado", "Pendiente", "Recibido", "Usado", "Cancelado"])

                observacion = st.text_area("Indicaciones / observaciones")

                submitted = st.form_submit_button("Guardar solicitud", use_container_width=True)

                if submitted:
                    if not solicitud.strip():
                        st.error("La solicitud es obligatoria.")
                    else:
                        nuevo = {
                            "id": next_id(df),
                            "cliente": cliente,
                            "solicitud": solicitud,
                            "responsable_cliente": responsable_cliente,
                            "fecha_limite": fecha_limite.strftime("%Y-%m-%d"),
                            "estado": estado,
                            "observacion": observacion,
                        }
                        append_and_save(nuevo)

    # ------------------------------------------------------------
    # CAMPAÑAS
    # ------------------------------------------------------------
    elif archivo == "campanias.csv":
        st.markdown("### Nueva campaña")

        if not clientes_lista:
            st.warning("Primero cargá clientes en el menú Clientes.")
        else:
            with st.form("form_campanias"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    cliente = st.selectbox("Cliente", clientes_lista)
                    campania = st.text_input("Nombre de campaña")

                with col2:
                    plataforma = st.selectbox("Plataforma", ["Meta Ads", "Google Ads", "LinkedIn Ads", "TikTok Ads", "Orgánico", "Otro"])
                    objetivo = st.text_input("Objetivo")

                with col3:
                    presupuesto = st.number_input("Presupuesto", min_value=0.0, step=1000.0)
                    estado = st.selectbox("Estado", ["Activa", "Pausada", "Finalizada", "Borrador"])

                col4, col5 = st.columns(2)
                with col4:
                    leads = st.number_input("Consultas / leads", min_value=0, step=1)
                with col5:
                    costo_por_lead = st.number_input("Costo por lead", min_value=0.0, step=100.0)

                observacion = st.text_area("Observaciones")

                submitted = st.form_submit_button("Guardar campaña", use_container_width=True)

                if submitted:
                    if not campania.strip():
                        st.error("El nombre de la campaña es obligatorio.")
                    else:
                        nuevo = {
                            "id": next_id(df),
                            "cliente": cliente,
                            "campania": campania,
                            "plataforma": plataforma,
                            "objetivo": objetivo,
                            "presupuesto": presupuesto,
                            "estado": estado,
                            "leads": leads,
                            "costo_por_lead": costo_por_lead,
                            "observacion": observacion,
                        }
                        append_and_save(nuevo)

    # ------------------------------------------------------------
    # REPORTES
    # ------------------------------------------------------------
    elif archivo == "reportes.csv":
        st.markdown("### Nuevo reporte mensual")

        if not clientes_lista:
            st.warning("Primero cargá clientes en el menú Clientes.")
        else:
            with st.form("form_reportes"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    cliente = st.selectbox("Cliente", clientes_lista)
                    mes = st.text_input("Mes", placeholder="Ej: Julio 2026")

                with col2:
                    alcance = st.number_input("Alcance", min_value=0, step=100)
                    interacciones = st.number_input("Interacciones", min_value=0, step=50)

                with col3:
                    consultas = st.number_input("Consultas", min_value=0, step=1)
                    inversion = st.number_input("Inversión publicitaria", min_value=0.0, step=1000.0)

                estado = st.selectbox("Estado", ["Disponible", "Borrador", "En revisión"])
                que_funciono = st.text_area("Qué funcionó")
                proximo_foco = st.text_area("Próximo foco")

                submitted = st.form_submit_button("Guardar reporte", use_container_width=True)

                if submitted:
                    if not mes.strip():
                        st.error("El mes del reporte es obligatorio.")
                    else:
                        nuevo = {
                            "id": next_id(df),
                            "cliente": cliente,
                            "mes": mes,
                            "alcance": alcance,
                            "interacciones": interacciones,
                            "consultas": consultas,
                            "inversion": inversion,
                            "estado": estado,
                            "que_funciono": que_funciono,
                            "proximo_foco": proximo_foco,
                        }
                        append_and_save(nuevo)

    # ------------------------------------------------------------
    # TAREAS
    # ------------------------------------------------------------
    elif archivo == "tareas.csv":
        st.markdown("### Nueva tarea interna")

        if not clientes_lista:
            st.warning("Primero cargá clientes en el menú Clientes.")
        else:
            with st.form("form_tareas"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    cliente = st.selectbox("Cliente", clientes_lista)
                    tarea = st.text_input("Tarea")

                with col2:
                    responsable_am = st.text_input("Responsable AM")
                    fecha_limite = st.date_input("Fecha límite")

                with col3:
                    prioridad = st.selectbox("Prioridad", ["Alta", "Media", "Baja"])
                    estado = st.selectbox("Estado", ["Pendiente", "En curso", "Finalizado", "Pausado"])

                submitted = st.form_submit_button("Guardar tarea", use_container_width=True)

                if submitted:
                    if not tarea.strip():
                        st.error("La tarea es obligatoria.")
                    else:
                        nuevo = {
                            "id": next_id(df),
                            "cliente": cliente,
                            "tarea": tarea,
                            "responsable_am": responsable_am,
                            "prioridad": prioridad,
                            "estado": estado,
                            "fecha_limite": fecha_limite.strftime("%Y-%m-%d"),
                        }
                        append_and_save(nuevo)

    else:
        st.warning("No hay formulario específico para esta sección.")

    st.markdown("---")
    st.markdown("### Últimos registros")

    if df.empty:
        st.info("Todavía no hay registros cargados.")
    else:
        st.dataframe(df.tail(10), use_container_width=True, hide_index=True)

    with st.expander("Edición avanzada en tabla"):
        st.caption("Usá esta vista solo para correcciones puntuales o edición masiva.")
        edited = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"editor_avanzado_{title}",
        )

        if st.button(f"Guardar edición avanzada en {title}", use_container_width=True):
            save_csv(edited, path)
            st.success(f"{title} actualizado correctamente.")
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

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if "auth" not in st.session_state:
        st.session_state["auth"] = False

    if not st.session_state.get("logged_in", False) and not st.session_state.get("auth", False):
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
        elif menu == "Usuarios":
            render_usuarios(clientes)
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
