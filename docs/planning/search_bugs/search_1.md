# Reporte de Bugs y Mejoras - Búsqueda 1

Tras analizar el código fuente del proyecto `meshassistant`, se han identificado varios problemas (bugs) y oportunidades de mejora en la arquitectura, manejo de errores y uso de la base de datos. A continuación se detallan los hallazgos y sus soluciones.

## 1. Bug Crítico: Terminación del Daemon (`main.py`)
**Problema:**
En `main.py`, la función principal `main()` llama a la función `loop()` envuelta en un bloque `try/except`. Si ocurre un error de conexión inicial con el puerto serie (`interface.connect()`) o surge alguna excepción global que se escape de las protecciones internas del bucle, la excepción es capturada en `main()`, se imprimen los errores, se ejecuta un `sleep(10)` y el script de Python finaliza de forma prematura. Esto rompe con la regla de tolerancia a fallos exigida en la documentación ("el bot debe seguir vivo pase lo que pase").

**Solución:**
En `main()`, se debe invocar a `loop()` dentro de un ciclo infinito (`while True:`). Si `loop()` falla por desconexión o excepción del dispositivo serie, el ciclo asegurará que tras una espera prudencial de reconexión, el daemon intentará restablecer el loop y la comunicación UART.
```python
def main():
    log_p("Iniciando receptor de mensajes...")
    try:
        ensure_database()
        while True:
            try:
                loop()
            except Exception as e:
                log_p(f"Reconexión tras caída del loop: {e}", level="WARN")
                sleep(10)
    except KeyboardInterrupt:
        # Fin controlado
        pass
```

## 2. Bug Crítico: Fugas de Descriptores de Archivo (Conexiones SQLite)
**Problema:**
En `Models/Database.py`, el método de ayuda `_connect()` devuelve una nueva conexión (`sqlite3.Connection`). Todos los métodos realizan sus consultas empleando el patrón contextual `with self._connect() as conn:`. En la librería `sqlite3` de Python, utilizar la conexión como un *context manager* solo maneja las transacciones (`commit` / `rollback`), pero **no cierra la conexión automáticamente** al salir del bloque. Como resultado, cada vez que se usa la BD, el daemon deja una conexión (y un *file descriptor*) abiertos. Eventualmente, en unas horas, el sistema operativo abortará el script lanzando errores de tipo `Too many open files`.

**Solución:**
Garantizar el cierre explícito de la conexión. Lo más recomendable y limpio en Python es usar `contextlib.closing` combinando el cierre de la conexión con el gestor de transacciones:
```python
from contextlib import closing

# Ejemplo en Database.py
def get_random_chiste(self, approved_only: bool = True):
    with closing(self._connect()) as conn:
        # conn cerrará al finalizar este bloque automáticamente
        with conn: # maneja commit o rollback de transacciones
            # lógica sql...
```

## 3. Mejora: Concurrencia SQLite (Locking por WAL)
**Problema:**
Aunque la BD SQLite está creada en modo `WAL` (`PRAGMA journal_mode=WAL`), este modo mejora la concurrencia pero no garantiza inmunidad frente a escrituras paralelas (por ejemplo, si el daemon en `main.py` y el script `cron_tasks.py` acceden de golpe). Si ocurre una colisión, SQLite usa un tiempo de espera que no está explícitamente protegido con un pragama anti-bloqueos en cada conexión de los Modelos.

**Solución:**
Añadir soporte explícito de retardo de bloqueos en `Database._connect()`.
```python
def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path, timeout=10.0) # subimos timeout
    conn.execute('PRAGMA busy_timeout = 10000') # pragama adicional de wait (10s)
    conn.row_factory = sqlite3.Row
    return conn
```

## 4. Mejora Lógica: Timeout Inefectivo en `traceroute`
**Problema:**
En el método `traceroute` en `Models/SerialInterface.py`, hay un mecanismo para capturar la salida textual con un `timeout = 10.0`. El bucle principal hace `while time.time() - start < timeout:`. Cuando detecta respuestas en el callback (`len(results) != last_len`), efectúa un `time.sleep(0.3)` adicional para "ampliar un poco la espera". No obstante, la variable `start` nunca se reinicia, ni se incrementa la variable `timeout`. Los `sleep()` adicionales no prolongan el tiempo global esperado, tan solo bloquean iteraciones. El método abortará a los 10 segundos ineludiblemente independientemente de los sleeps extra.

**Solución:**
Para prolongar efectivamente el tiempo cuando hay actividad (tráfico detectado), se debe desplazar `start`:
```python
if len(results) != last_len:
    last_len = len(results)
    start = time.time()  # Resetea el contador para esperar de nuevo 'timeout' ms
    time.sleep(0.3)
```

## 5. Mejora Arquitectónica: Duplicidad de Código (DRY en Comandos)
**Problema:**
Si revisamos los ficheros dentro de `Commands/` (`ping.py`, `chiste.py`, `weather.py`, etc.), vemos que **todos** repiten el bloque exacto para registrar un comando usando `Database().log_command()`. Esta repetición engorda cada fichero artificialmente y obliga a cualquier desarrollador futuro a acordarse de inyectar esa lógica engorrosa de imports locales dentro de los excepts.

**Solución:**
Mover la acción de `Database().log_command()` directamente al núcleo del sistema. Concretamente, en `SerialInterface.py` dentro de la función `on_receive_text`, luego de invocar `self.command_dict[command]["callback"](...)`. En ese punto ya se tiene acceso a la metadata del nodo que lo solicitó y al nombre del comando. Extraerlo hacia allí eliminaría entre 10 y 15 líneas repetitivas en cada uno de los comandos.

## 6. Bug de Lógica: Intervalo de Consulta a la API AEMET (`AEMET_PERIOD`)
**Problema:**
Existen dos lógicas vinculadas a los tiempos de AEMET: la **descarga de datos** desde la API (en `cron_tasks.py`) y la **publicación de avisos** en los canales de radio (en `main.py`).
Si bien la publicación sí respeta correctamente la frecuencia dictada por la variable de entorno `AEMET_PERIOD` (usando `aemet.period_to_minutes()`) y respeta fielmente la ventana horaria `AEMET_HOUR_MIN` y `AEMET_HOUR_MAX` para evitar molestar mientras la gente duerme, **la descarga desde la API no lo hace**.
En `cron_tasks.py` -> `check_aemet()`, el cooldown o retardo de consulta a la API está **marcado a fuego a 60 minutos** (`_should_run(db, task_name, 60)`). Esto significa que aunque se configure `AEMET_PERIOD="Three_hour"` o `"Day"`, el bot seguirá haciendo peticiones HTTP a la API de AEMET cada 60 minutos.

**Solución:**
En `cron_tasks.py`, se debe cargar dinámicamente el periodo configurado en minutos, usando el helper ya existente, para que la consulta a la API se alinee con las expectativas:
```python
def check_aemet() -> None:
    db = Database()
    task_name = 'aemet_fetch'
    
    # Extraer minutos desde la configuración general en lugar de hardcodear 60
    aemet = Aemet()
    period_min = aemet.period_to_minutes(aemet.period)
    
    # Ejecutar según la frecuencia configurada
    if not _should_run(db, task_name, period_min):
        log_p(f"[cron] check_aemet: omitido (cooldown {period_min}min)")
        return
```

## 7. Falsa Alarma y Mejora Menor: Tratamiento de Provincias (Cádiz)
**Observación sobre "Cádiz":**
Tras un análisis exhaustivo del flujo de normalización de cadenas, el sistema **sí soporta de manera robusta y a prueba de errores** cualquier variante que introduzca el usuario para la provincia de Cádiz (`"Cadiz"`, `"cádiz"`, `"CADIZ"`, `"Cádiz"`). 
1. El script cuenta con la función `_normalize()`, que elimina tildes y convierte el texto a mayúsculas puras, resultando siempre en `"CADIZ"`.
2. Para la primera técnica de descarga (el "archivo" `tar.gz`), buscará el patrón `"CADIZ"` en el XML normalizado, por lo que **atrapará cualquier alerta de la provincia y litoral gaditano correctamente**.
3. Para la segunda técnica (fallback al endpoint `ultimoelaborado`), el sistema tiene mapeado `"CADIZ"` al código INE oficial `"11"`. La consulta resultante a `/provincia/11` es el método infalible y estandarizado por la AEMET para provincias, haciendo innecesario adivinar o forzar cómo se escribe exactamente el nombre del área en el parámetro de la URL.

**Problema / Mejora para Comunidades Autónomas:**
Aunque Cádiz funcionará perfectamente por ser provincia, si un usuario pone el nombre de una Comunidad Autónoma (p.ej. `"Andalucia"`), el script fallará en el *fallback*, porque AEMET exige que las áreas se consulten en Title Case exacto y sin acento (`/area/Andalucia`). El código actual genera versiones que no encajan (`"ANDALUCIA"`, `"Andalucía"`) y, además, el sistema encola la llamada a área sólo dentro de un `else` excluyente si no halla el código numérico.

**Solución:**
Asegurar que en el bloque de fallback de `cron_tasks.py`, se añade una variante capitalizada sin tilde (`prov_norm.title()`) que satisface el formato de las áreas.
```python
# Asegurarse de que incluimos la variante "Cadiz" o "Andalucia" explícitamente:
area_unaccented_title = prov_norm.title() # -> "Cadiz" o "Andalucia"
for area_name in [prov_norm, prov_title, prov_raw, area_unaccented_title]:
    if area_name:
        endpoints.append(f"{base_filter}/area/{quote(area_name)}")
```
