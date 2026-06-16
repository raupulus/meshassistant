# Documentación técnica de meshassistant

Documentación por módulo y funcionalidad. Cada documento es independiente y
describe una parte concreta del sistema. Para la visión funcional general consulta
el [`README.md`](../../README.md) y para las normas de desarrollo el
[`AGENTS.md`](../../AGENTS.md).

## Índice

| # | Documento | Contenido |
|---|---|---|
| 01 | [Arquitectura](01-arquitectura.md) | Procesos, flujo de datos y decisiones de diseño. |
| 02 | [Configuración](02-configuracion.md) | Variables de `env.py` y su efecto. |
| 03 | [Base de datos](03-base-de-datos.md) | Esquema SQLite completo, tablas e índices. |
| 04 | [Interfaz serial](04-interfaz-serial.md) | `SerialInterface`: conexión, eventos, envío, reconexión, traceroute. |
| 05 | [Nodos](05-nodos.md) | Modelo `Node` y su persistencia. |
| 06 | [Modelo Database](06-modelo-database.md) | API de acceso a datos (`Models/Database.py`). |
| 07 | [Comandos](07-comandos.md) | Sistema de comandos y cómo crear uno nuevo. |
| 08 | [Traceroute](08-traceroute.md) | Cola de traces, ejecución y enriquecimiento. |
| 09 | [AEMET](09-aemet.md) | Descarga, parseo CAP y publicación de alertas. |
| 10 | [Chistes](10-chistes.md) | Almacenamiento y sincronización con API externa. |
| 11 | [Cron](11-cron.md) | Tareas periódicas y *throttling*. |
| 12 | [API HTTP](12-api-http.md) | Cliente HTTP genérico con reintentos. |
| 13 | [Instalación y despliegue](13-instalacion-despliegue.md) | Hardware, venv, cron y systemd. |
| 14 | [Roadmap](14-roadmap.md) | Funcionalidades pendientes y placeholders. |

## Convenciones de la documentación

- Idioma: español.
- Las rutas y nombres de fichero se refieren a la raíz del repositorio.
- El estado de cada pieza se indica con: ✅ funcional · 🟡 parcial/placeholder · ⛔ no implementado.
