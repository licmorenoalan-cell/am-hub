# Tablero independiente de Somos Compa

Desde octubre de 2026, el tablero se encuentra en https://somos-compa-tablero.lic-moreno-alan.chatgpt.site y fue retirado del menú y del enrutamiento de AMHub. Acceso con usuario SMPA; la clave se administra en el alojamiento independiente.

La base compartida fue copiada a D1. Las tablas fleet_sandbox y fleet_sandbox_history de AMHub se conservan como respaldo de la migración; no se eliminan ni se mezclan con la contabilidad. El cliente y su Plan de trabajo permanecen en AMHub.

El código histórico del componente queda disponible como referencia. El nuevo sitio conserva filtros, formularios, CSV, respaldo JSON y control de versiones.

---

## Referencia de la implementación anterior

# Somos Compa shared sandbox

Access: AMHub → Tablero gerencial. Enabled only for SMPA / KM146, administrators and team members assigned to that client. Data access is checked on the server. The existing portal authentication is reused.

The component preserves the standalone preview's branding. It receives a server snapshot and returns complete candidate snapshots. PostgreSQL tables `fleet_sandbox` and `fleet_sandbox_history` are isolated from accounting. Updates compare revision atomically; a stale update is rejected and can be downloaded from the browser. Request IDs make retries idempotent. Every accepted update retains a recoverable snapshot, actor and UTC timestamp. Revision zero is the checked-in synthetic seed.

Other sessions load changes through **Actualizar datos compartidos** or reopening the page. That button reloads the component, so save forms first. No background sync or external FleetOps/Cabify/GPS/bank connection is present. CSV import and manual entry are supported. JSON backups can be exported/restored. A restore/reset replaces the entire client's shared sandbox after confirmation, including other users' test data.

Rollback: remove the menu/router integration while retaining the database tables. For data recovery, export a historical payload and restore through the UI (creates a new revision); never delete the history. No existing accounting table is migrated.

Tests: `python -m unittest discover -s tests -v`; `python -m py_compile app.py am_hub_fleet.py`. Browser fixture verifies custom-component handshake, form save, server acknowledgement and persistence after reload.
