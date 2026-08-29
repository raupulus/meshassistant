# 📋 Prompt para importar este directorio en otro proyecto

Este archivo existe para que, al copiar `docs/apis/` a otro repositorio, el prompt viaje con él.

**Cómo usarlo:** copia `docs/apis/` completo al otro proyecto y pega el bloque de abajo como primer
mensaje al agente de IA de ese proyecto.

---

```
He copiado a este proyecto el directorio `docs/apis/`, que contiene documentación técnica
VERIFICADA de APIs externas de terceros. Quiero integrar algunos endpoints de AEMET OpenData.

TAREA 1 — Registra el directorio en las instrucciones del proyecto.

Añade a AGENTS.md (o CLAUDE.md / .cursorrules, lo que use este proyecto) una sección con esto:

  ## Documentación de APIs externas (`docs/apis/`)

  - Contiene la documentación oficial DESTILADA Y VERIFICADA de APIs de terceros.
  - **Consúltala SOLO cuando la tarea toque una API externa.** Si no, no la leas: gasta
    contexto sin aportar nada.
  - Orden de lectura obligatorio al tocar una API externa:
    1. `docs/apis/<api>/README.md` — índice y normas
    2. `docs/apis/<api>/00-fundamentos.md` + `ERRATAS.md` + `LIMITACIONES.md`
    3. Solo el archivo del dominio concreto que necesites
  - **Nunca configures nada a partir de la especificación oficial de una API externa sin
    verificarlo con una petición real.** Está medido: en AEMET la especificación falla en el
    Content-Type, la codificación y la forma de los errores.
  - `docs/apis/<api>/src/` son las fuentes originales: NO se editan y NO se leen de rutina.
  - Cada archivo declara sus fuentes al principio, para saber qué volver a descargar al
    actualizar.
  - Al documentar CÓMO integramos la API en este proyecto (servicios, comandos, modelos,
    caché), hazlo en la carpeta de documentación propia del proyecto, NO en `docs/apis/`, y
    enlaza al archivo concreto de `docs/apis/` en vez de repetir el dato oficial.

TAREA 2 — Lee estos tres archivos antes de escribir una línea de código de AEMET:
`docs/apis/aemet/00-fundamentos.md`, `docs/apis/aemet/ERRATAS.md` y
`docs/apis/aemet/LIMITACIONES.md`. Son lectura previa, no de consulta.

CONTEXTO MÍNIMO PARA QUE NO TENGAS QUE DEDUCIRLO (todo verificado con peticiones reales):

1. Toda consulta son DOS peticiones. El endpoint devuelve un sobre
   {descripcion, estado, datos, metadatos}; los datos están en la URL `datos`, que NO lleva
   autenticación y es EFÍMERA (minutos). Se consume una vez y se persiste: nunca se guarda ni
   se referencia esa URL. Excepción: `balancehidrico` y `resumenclimatologico` devuelven el PDF
   directo, sin sobre.

2. La API responde en ISO-8859-15, salvo algunos productos que vienen en UTF-8 real. Hay que
   LEER EL CHARSET de la cabecera Content-Type y respetarlo: con los primeros, `json_decode`
   devuelve null en silencio; a los segundos, convertirlos los corrompe.

3. Un HTTP 200 no significa que haya datos. Puede traer `estado: 404` en el cuerpo, cuerpo
   vacío (si falta la api_key o el periodo no existe) o datos de años atrás. Hay que validar
   el estado del CUERPO y la FRESCURA del contenido (campo `elaborado`, o la fecha de la
   cabecera en los productos de texto).

4. La cuota se expone en la cabecera indocumentada `Remaining-request-endpoint`: 40 peticiones
   por PLANTILLA de endpoint (no por URL), menos en productos pesados, y ligada a la IP además
   de a la clave. El 429 no trae Retry-After y la recuperación tarda más de una hora. Hay que
   espaciar peticiones, rotar entre familias y hacer backoff a ciegas.

5. No todo es JSON: 22 de los 64 endpoints devuelven texto plano, y hay GIF, PNG, tar sin
   comprimir, gzip, ZIP, PDF y CSV. El Content-Type NO permite distinguir el tar del gzip: hay
   que comprobar el magic (1f8b = gzip; "ustar" en el offset 257 = tar plano).

6. La API Key es un JWT que CADUCA (~100 días). Va en `.env` como AEMET_API_KEY, en la cabecera
   `api_key` (nunca en la query string, que la filtra a los logs). Conviene guardar también la
   fecha de expiración para poder avisar antes de que caduque. Solicitar o renovar en
   https://opendata.aemet.es/centrodedescargas/altaUsuario

7. La web NUNCA llama a AEMET en la petición del usuario. Un proceso en segundo plano trae los
   datos y los persiste; la web lee de la base de datos.

TAREA 3 — Dime qué endpoints necesito según lo que quiero mostrar, citando el archivo de
`docs/apis/aemet/` donde está cada uno, y qué me falta por decidir. No escribas código todavía.
```

---

## Nota sobre la API Key

La clave **no viaja** en `docs/apis/`: está en el `.env` del proyecto de origen, que está
gitignorado. En el proyecto destino hay que poner una clave propia (o la misma) en su `.env`.

⚠️ Ojo con el límite: la cuota va ligada a la **IP** además de a la clave. Dos proyectos en el
mismo servidor **comparten cuota** por endpoint. Ver
[`aemet/LIMITACIONES.md`](aemet/LIMITACIONES.md#la-cuota-va-ligada-a-la-ip-no-solo-a-la-clave).
