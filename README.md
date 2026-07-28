# AM Hub

Portal de gestión para clientes y equipo AM, construido con Streamlit. La app
principal vive en `app.py`; `pocket_app.py` ofrece una interfaz móvil enfocada
en tareas. PostgreSQL es el almacenamiento recomendado y los CSV de `data/`
funcionan como modo local.

## Desarrollo local

Requiere Python 3.11.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/run_local.sh
```

La aplicación toma `DATABASE_URL` primero del entorno y luego de
`.streamlit/secrets.toml`. Sin esa configuración utiliza los CSV locales.

## Verificación

Antes de desplegar:

```bash
python -m py_compile app.py pocket_app.py am_hub_core.py scripts/*.py
python -m unittest discover -s tests -v
python -m pip check
```

## Persistencia

- Los CSV se escriben mediante reemplazo atómico para evitar archivos parciales.
- Las tablas PostgreSQL permitidas están declaradas en `POSTGRES_TABLE_MAP`.
- Los guardados PostgreSQL se ejecutan dentro de una transacción y propagan el
  error: no se intenta borrar o recrear una tabla como recuperación automática.
- Antes de migraciones o cambios masivos, generar un backup verificable de la
  base de datos. Los scripts de migración deben probarse primero con datos no
  productivos.

## Despliegue

`scripts/deploy_code.sh` valida sintaxis y pruebas antes de preparar el commit.
El script no incluye archivos de datos ni secretos en el commit.
