# Challenge

> **Estado:** aplicación funcional y documentación parcialmente verificada (secciones 1–4 completas;
> algunas verificaciones humanas de los episodios quedan pendientes, ver 4.2).
> El repositorio debe explicar por sí solo **qué se construyó y cómo se comprobó**.

---

## 1. Especificación

### 1.1 Problema

La coordinación de un laboratorio registra pedidos en mensajes y una planilla. De forma recurrente ocurren dos fallas:

- se confirma la **misma unidad** para horarios superpuestos, y
- una **cancelación** sigue bloqueando el horario.

La coordinación necesita **consultar disponibilidad, reservar y cancelar sin perder el historial**.

### 1.2 Alcance

**Incluye:**

- Leer el inventario precargado y consultar disponibilidad por unidad e intervalo.
- Crear una reserva identificable con unidad, solicitante ficticio no vacío, inicio y fin (una unidad por reserva).
- Cancelar conservando el identificador y los datos, y liberar el intervalo.
- Persistir reservas y sus estados para recuperarlos al reiniciar la aplicación.

**Excluye:**

- Administrar o modificar el inventario (las unidades ya están definidas; cada ID identifica una unidad física distinta).
- Migrar o ingesta automática de los mensajes y la planilla existentes.
- Reservas con más de una unidad por reserva, usuarios/roles, ni interfaz web.

Inventario (ya definido):

| ID de unidad | Equipo |
|---|---|
| MIC-01 | Microscopio digital |
| MIC-02 | Microscopio digital |
| OSC-01 | Osciloscopio |
| MUL-01 | Multímetro |
| FUE-01 | Fuente de alimentación |

### 1.3 Requisitos verificables

| Req. | Descripción | Cómo se verifica |
|------|-------------|------------------|
| R-01 | El inventario precargado se lee sin administrarlo | `inventario` lista las 5 unidades; ver sección 2.7 |
| R-02 | Consulta de disponibilidad por unidad e intervalo, con las mismas reglas de reserva | `disponibilidad` responde LIBRE/OCUPADA; superposiciones y límites según reglas V-6…V-8 |
| R-03 | Reserva identificable: unidad, solicitante no vacío, inicio y fin | `reservar` devuelve id; `listar` muestra los datos |
| R-04 | Cancelación conserva identificador y datos, y libera el intervalo | tras `cancelar`, `listar` muestra CANCELADA y el intervalo vuelve a LIBRE |
| R-05 | Persistencia: reservas y estados sobreviven al reinicio | nueva ejecución muestra el historial (prueba `TestPersistencia`) |
| R-06 | Reglas de validación y conflicto (sección 1.4) aplicadas a reservar y consultar | pruebas `TestValidaciones`, `TestSuperposicion`, `TestCLI` |

### 1.4 Reglas

| Regla | Enunciado |
|-------|-----------|
| V-1 | Se rechaza cualquier operación sobre una **unidad desconocida** (no está en el inventario). |
| V-2 | El **solicitante** no puede ser vacío ni estar compuesto solo por espacios. |
| V-3 | Las **fechas y horas** deben ser válidas (formato `YYYY-MM-DD HH:MM`). |
| V-4 | El **inicio debe ser estrictamente anterior al fin**. |
| V-5 | Una reserva **activa** ocupa su intervalo; una **cancelada** no bloquea disponibilidad, pero se conserva con sus datos. |
| V-6 | Se rechaza la **superposición de reservas activas de la misma unidad**. |
| V-7 | Se **permiten límites consecutivos** (un intervalo que termina 11:00 no bloquea otro que empieza 11:00). |
| V-8 | Se permiten **reservas simultáneas de unidades distintas**. |
| V-9 | La **consulta de disponibilidad usa las mismas reglas** que la reserva (V-1…V-8). |

Ejemplo del enunciado: con MIC-01 reservado de 10:00 a 11:00, se rechaza 10:30–11:30 y se permite 11:00–12:00; MIC-02 puede reservarse de 10:00 a 11:00 aunque MIC-01 esté ocupado.

### 1.5 Supuestos

- Las fechas/horas son locales y sin zona horaria; formato de entrada `YYYY-MM-DD HH:MM`.
- Una reserva ocupa **una sola unidad** (suficiente según el enunciado).
- El inventario es estático: está definido y no crece ni se edita desde la aplicación.
- Los datos de mensajes/planilla actuales se cargan manualmente si se desea; no hay importación.
- Los solicitantes del historial son ficticios (no se usan datos reales de personas).

### 1.6 Criterios de aceptación

| Criterio | Se cumple si… |
|----------|----------------|
| CA-01 | Los comandos `inventario`, `disponibilidad`, `reservar`, `cancelar`, `listar` y `reset` funcionan según sección 2.6/2.7. |
| CA-02 | El ejemplo del enunciado (V-6/V-7/V-8 con MIC-01/MIC-02) se reproduce exactamente: rechaza 10:30–11:30, permite 11:00–12:00 y MIC-02 10:00–11:00. |
| CA-03 | Una cancelación conserva id y datos en `listar` y libera el intervalo para una nueva reserva. |
| CA-04 | Tras cerrar y reabrir la aplicación, reservas y estados se recuperan. |
| CA-05 | `python -m unittest discover -s tests` pasa sin errores (32 pruebas). |

---

## 2. Solución

### 2.1 Estructura

```
challenge/
├── reservas.py           # Aplicación: API y CLI (módulo único, sin dependencias)
├── tests/
│   └── test_reservas.py  # 32 pruebas (unittest, biblioteca estándar)
├── data/
│   └── reservas.db       # Base SQLite (se crea al primer arranque; no se versiona)
└── README.md
```

### 2.2 Decisiones técnicas

- **Python 3.11+ solo con biblioteca estándar** (`argparse`, `sqlite3`, `datetime`, `unittest`) — sin dependencias externas, para ejecución local reproducible. Elegido por el solicitante: "vamos con python + sqlite".
- **SQLite en un archivo local** (`data/reservas.db`): persistencia simple y recupera reservas/estados al reiniciar (R-05).
- **CLI con códigos de salida:** proceso termina con `0` cuando la operación se acepta y `1` cuando se rechaza (validación, unidad desconocida o superposición). Facilita verificación humana y automatización.
- **Validación y superposición en la capa de aplicación** (clase `Laboratorio`): las reglas V-1…V-9 viven en un solo lugar y se usan tanto en `reservar` como en `disponibilidad` (V-9). La superposición es **estricta** (`inicio < fin_ajena and inicio_ajena < fin`), por lo que los límites consecutivos se permiten (V-7).

### 2.3 Requisitos previos y versiones

- **Python **3.11 o superior** (verificado con 3.13.14): no requiere instalar ninguna otra herramienta (no hay dependencias externas).

### 2.4 Instalación

```bash
git clone <url-de-este-repositorio>
cd challenge
# Opcional: entorno virtual
python -m venv .venv            # Windows: .venv\Scripts\activate
```

No se requiere `pip install`: no hay dependencias externas.

### 2.5 Carga inicial y reinicio de datos

- **Carga inicial:** al primer arranque la base `data/reservas.db` se crea automáticamente y el inventario (5 unidades, sección 1.2) siembra la tabla `inventario`. No hay carga manual de datos: el inventario es precargado por diseño.
- **Reinicio de datos:** `python reservas.py reset` elimina las reservas y resiemba el inventario, dejando la aplicación en el estado inicial. Alternativa más rápida: borrar el archivo `data/reservas.db` (se recrea con el inventario en el siguiente arranque).

**Persistencia de datos:** archivo SQLite `data/reservas.db` dentro del proyecto (ignorado por git). Tablas: `inventario(unidad, equipo)` y `reservas(id, unidad, solicitante, inicio, fin, estado IN ('ACTIVA','CANCELADA'))`.

### 2.6 Comandos de aplicación y pruebas

```bash
python reservas.py inventario                        # R-01: lista el inventario
python reservas.py disponibilidad --unidad MIC-01 --desde "2026-11-03 10:00" --hasta "2026-11-03 11:00"   # R-02
python reservas.py reservar --unidad MIC-01 --solicitante "Solicitante A" --desde "2026-11-03 10:00" --hasta "2026-11-03 11:00"  # R-03
python reservas.py listar                            # R-04: historial completo (incluye canceladas)
python reservas.py listar --unidad MIC-01            # historial de una unidad
python reservas.py cancelar --id 1                   # R-04: cancela conservando id y datos
python reservas.py reset                             # reinicia datos y resiembra inventario
```

**Correr sin comando** (`python reservas.py`) muestra un menú con todos los comandos y un ejemplo, y sale con código 0:

```
$ python reservas.py
Reservas de equipos de laboratorio

Uso: python .\reservas.py <comando> [opciones]
Datos persistentes: data/reservas.db

Comandos disponibles:
  inventario       lista el inventario precargado
  listar           historial de reservas (activas y canceladas)
                   opcional: --unidad MIC-01
  disponibilidad   consulta si un intervalo esta libre (LIBRE / OCUPADA)
                   requiere: --unidad MIC-01 --desde ... --hasta ...
  reservar         crea una reserva activa
                   requiere: --unidad --solicitante --desde --hasta
  cancelar         cancela conservando el registro (requiere --id N)
  reset            reinicia los datos y resiembra el inventario

Fechas y horas en formato 'YYYY-MM-DD HH:MM'. Ejemplo:
  python .\reservas.py reservar --unidad MIC-01 --solicitante "Solicitante A"
                 --desde "2026-11-03 10:00" --hasta "2026-11-03 11:00"

Códigos de proceso: 0 = aceptado, 1 = rechazado.
```

Todas admiten `--db <ruta>` para opcionalmente usar otra base (útil en pruebas).

**Pruebas:**

```bash
python -m unittest discover -s tests
```

32 pruebas en verde = estado aceptado (CA-05). Códigos de proceso: `0` aceptado, `1` rechazado.

### 2.7 Ejemplos de entrada y salida

(*Solicitantes ficticios; sin datos reales de estudiantes.*)

**Secuencia del ejemplo del enunciado (CA-02):** MIC-01 es reservado de 10:00 a 11:00 por Solicitante A:

```
$ python reservas.py reservar --unidad MIC-01 --solicitante "Solicitante A" --desde "2026-11-03 10:00" --hasta "2026-11-03 11:00"
Reserva creada con id=1.
```

Consultar 10:30→11:30 sobre MIC-01 se rechaza porque choca (V-6):

```
$ python reservas.py disponibilidad --unidad MIC-01 --desde "2026-11-03 10:30" --hasta "2026-11-03 11:30"
OCUPADA: MIC-01 2026-11-03 10:30 -> 2026-11-03 11:30 (choca con reserva id=1 activa de 'Solicitante A' 2026-11-03 10:00 -> 2026-11-03 11:00)
# código de proceso: 1
```

Reservar ese intervalo igualmente se rechaza:

```
$ python reservas.py reservar --unidad MIC-01 --solicitante "Solicitante B" --desde "2026-11-03 10:30" --hasta "2026-11-03 11:30"
ERROR: unidad MIC-01 ya reservada por 'Solicitante A' de 2026-11-03 10:00 a 2026-11-03 11:00 (reserva id=1, activa)
# código de proceso: 1
```

Con límite consecutivo **11:00→12:00** se permite (V-7):

```
$ python reservas.py reservar --unidad MIC-01 --solicitante "Solicitante B" --desde "2026-11-03 11:00" --hasta "2026-11-03 12:00"
Reserva creada con id=2.
```

Otra unidad distinta puede reservarse en el mismo intervalo (V-8):

```
$ python reservas.py reservar --unidad MIC-02 --solicitante "Solicitante C" --desde "2026-11-03 10:00" --hasta "2026-11-03 11:00"
Reserva creada con id=3.
```

Cancelar conserva el registro y libera el intervalo (V-5):

```
$ python reservas.py cancelar --id 1
Reserva id=1 cancelada (registro conservado: MIC-01 2026-11-03 10:00 -> 2026-11-03 11:00 'Solicitante A').
```

**Estado final visible con `listar`:**

```
id=1 [CANCELADA] MIC-01 2026-11-03 10:00 -> 2026-11-03 11:00 'Solicitante A'
id=2 [ACTIVA] MIC-01 2026-11-03 11:00 -> 2026-11-03 12:00 'Solicitante B'
id=3 [ACTIVA] MIC-02 2026-11-03 10:00 -> 2026-11-03 11:00 'Solicitante C'
```

**Casos de rechazo por validación (V-1…V-4):**

```
$ python reservas.py reservar --unidad XXX-99 --solicitante "Solicitante X" --desde "2026-11-03 09:00" --hasta "2026-11-03 10:00"
ERROR: unidad desconocida: 'XXX-99' (conocidas: FUE-01, MIC-01, MIC-02, MUL-01, OSC-01)

$ python reservas.py reservar --unidad MIC-01 --solicitante "   " --desde "2026-11-03 09:00" --hasta "2026-11-03 10:00"
ERROR: solicitante vacío: la reserva necesita un solicitante

$ python reservas.py reservar --unidad MIC-01 --solicitante "Solicitante X" --desde "ayer" --hasta "2026-11-03 10:00"
ERROR: fecha y hora inválidas: 'ayer' (se espera 'YYYY-MM-DD HH:MM')
```

---

## 3. Preparación del agente

### 3.1 Entorno y modelo

- **Modelo:** GLM-5.3 Flash (`glm-5.3-flash-free`), entrenado por Z.ai.
- **Harness:** OpenCode (agente de código CLI), con gestión del proyecto/sesiones mediante **Orca**.
- **Entorno de ejecución:** Windows (`win32`) con PowerShell; repositorio git local en `C:\Users\mics\orca\projects\challenge` (proyecto gestionado por Orca). Fecha de inicio del trabajo: octubre de 2026.

### 3.2 Instrucciones

- **Instrucción base del harness:** reglas de OpenCode (uso de herramientas, estilo de respuesta, gestión de código). No se conserva transcripción completa solo extractos relevantes.
- **Instrucciones del solicitante (por episodio):** se entregan en cada episodio como mensaje del usuario; el extracto relevante queda registrado en la [sección 4.2](#42-registro-de-episodios-delegación-al-agente).

### 3.3 Contexto

- Consulta inicial del solicitante: especificación breve + estructura exigida del README (ver [sección 1](#1-especificación)).
- Repositorio inicialmente vacío (solo commit inicial de git). No se suministraron archivos adicionales de código ni datos.
- La memoria de trabajo viva es este README, actualizado en cada episodio.

### 3.4 Permisos

- Lectura/escritura de archivos del proyecto (`read`, `write`, `edit`) y búsqueda (`glob`, `grep`).
- Ejecución de comandos en PowerShell (shell local del proyecto).
- Búsqueda y descarga web (`websearch`, `webfetch`) para consultas de documentación.
- Subagentes de apoyo (búsqueda/exploración del codebase) y herramienta de preguntas al solicitante.
- Sin acceso por defecto a GUI (solo mediante skill `computer-use` si la tarea lo exige; no utilizada hasta ahora).

### 3.5 Adaptación y retención del progreso

- **README como memoria de trabajo:** tras cada episodio se actualiza este README con lo producido; el contexto entre sesiones se reconstruye leyendo el documento y el historial git.
- **Commits:** los cambios se registran como commits para poder vincular evidencia a la versión entregada.
- **Sesiones Orca:** el trabajo se realiza en la sesión/proyecto del worktree de Orca, lo que permite retomar el hilo sin repetir contexto.

### 3.6 Evidencia de uso real

Vincular la evidencia con la **versión entregada**. No adjuntar transcripciones completas; solo extractos y enlaces.

| Episodio | Versión | Evidencia | Enlace |
|----------|---------|-----------|--------|
| 1. Esqueleto del README + datos del agente (sección 3) | v0.1 | `README.md` (secciones creadas; 3 completada con datos del agente) | commit `4472118` — `docs: esqueleto del README y datos del agente (seccion 3)` |
| 2. Especificación del challenge (sección 1) + stack definido (2.2) | v0.2 | `README.md` secciones 1 y 2 | commit `cf0637c` — `docs: especificacion (seccion 1), solucion (seccion 2) y registro de episodios (seccion 4)` |
| 3. Implementación Python+SQLite, 32 pruebas y demo CLI (secciones 2.6/2.7) | v0.2 | `reservas.py`, `tests/test_reservas.py`, suite `unittest` en verde | commit `79e2fb0` — `feat: app de reservas (Python+stdlib/SQLite) con CLI y 32 pruebas` |
| 3b. Comentarios legibles + fix de anotación y espacio en `listar` | v0.2 | suite sigue en verde tras el refactor | commit `4d4af71` — `refactor: comentarios y docstrings vinculados a requisitos; fix typo anotacion _unidad y espacio en listar` |
| 4. Menú de comandos al correr sin argumentos (solicitud del aplicante sobre la salida real del error) | v0.3 | `reservas.py` (`_imprimir_menu`), sección 2.6, suite en 33 pruebas | commit `c59fd75` — `feat: menu de comandos al correr sin argumentos (sale 0, ver 2.6)` |

---

## 4. Registro de decisiones y delegación

### 4.1 Decisiones significativas

Registro de decisiones significativas, con motivo, alternativas evaluadas (cuando existía una disyuntiva) y consecuencias.

| # | Decisión | Motivo | Alternativas | Consecuencias |
|---|----------|--------|--------------|---------------|
| D-01 | Stack Python 3.11+ (solo stdlib) + SQLite en archivo local | Elección del solicitante ("vamos con python + sqlite"); ejecución local pequeña y verificable sin dependencias | Node/JSON, Go, Docker+Postgres (descartadas: más piezas que verificar y mantener) | Instalación es "clonar y ejecutar"; límites: una sola instancia escribiendo a la vez (suficiente para el caso local) |
| D-02 | CLI con códigos de proceso (0 aceptado / 1 rechazado) | Hace verificable el rechazo de una operación (superposición, validación) sin parsear texto | Salida JSON (más pesada para inspección humana) | Las pruebas verifican comportamiento vía API y CLI; la consulta de disponibilidad ocupada sale con `1` |
| D-03 | Pruebas con `unittest` (stdlib) en vez de pytest | Cero dependencias: la verificación también corre con Python de fábrica | pytest (más ergonómico pero agregó dependencia) | Suite de 32 pruebas en `tests/test_reservas.py`; el enunciado de pytest no es necesario |
| D-04 | Superposición estricta implementada en Python (clase `Laboratorio`), no en SQL | Reglas V-1…V-9 en un solo lugar reutilizadas por `reservar` y `disponibilidad` (V-9); fáciles de testear | Query SQL con BETWEEN / paquete dedicado de calendarios | Riesgo de divergencia si mañana se consultara directamente por SQL; hoy no existe ese caso |
| D-05 | Formato de fecha estricto `YYYY-MM-DD HH:MM` sin zonas horarias | Simplicidad y determinismo del caso local; evita ambigüedades de zonas | ISO con segundos / fechas con zona horaria (innecesarias) | Entradas con segundos u horas de zona se rechazan con mensaje claro |
| D-06 | Salida ASCII en la CLI (p. ej. `->` en lugar de `→`) | Corregir bug real: la consola Windows (cp1252) no codifica flecha Unicode y `print` abortaba | Reconfigurar stdout a UTF-8 (depende de terminal) | Mensajes cortos y robustos en cualquier consola; se registró como corrección en el episodio 3 |
| D-07 | `python reservas.py` sin argumentos muestra un menú de comandos (y sale 0) | El solicitante reportó que correr la app sin comando mostraba un error seco de argparse; el menú hace la app autoexplicativa para uso local | Dejar el error de argparse (código 2, más rígido); menú interactivo de selección (más código, no pedido) | La app corre con menú sin argumentos; los usos incorrectos con argumentos parcialmente dados siguen con error 2 de argparse |

### 4.2 Registro de episodios (delegación al agente)

Para cada episodio registrar: objetivo y requisito → contexto suministrado y extracto de instrucción →
acción o resultado del agente → decisión humana de aceptar/corregir/rechazar con motivo → enlace a
archivo, commit, prueba o resultado verificable.

Correcciones: registrar **solo si ocurrieron**; no inventar fallas.

#### Episodio 1 — Preparación de la documentación (README)

- **Objetivo y requisito:** crear el README organizado en cuatro secciones (especificación, solución, preparación del agente, registro de decisiones/delegación) con plantillas y criterios de la solicita.
- **Contexto suministrado y extracto de instrucción:** *"requiero crear un readme organizado en cuatro secciones… por ahora solo crealo con esto y vamos a ir rellenando con lo necesario. siempre actualizá el readme"*.
- **Acción o resultado del agente:** creó `README.md` con las 4 secciones y plantillas `TODO`, con las notas de documentación (sin secretos, solicitantes ficticios, sin transcripciones).
- **Decisión humana y motivo:** **aceptar** — el solicitante continuó el trabajo y pidió rellenar los datos del agente con los reales del agente.
- **Evidencia:** commit `4472118` (README con datos del agente en la sección 3); commit `2a89bce` registra el hash de esa evidencia.
- **Correcciones:** no ocurrieron.

#### Episodio 2 — Registro de la especificación

- **Objetivo y requisito:** cargar en el README la especificación del challenge (problema, alcance, reglas mínimas y ejemplo MIC-01) según el enunciado dado por el solicitante.
- **Contexto suministrado y extracto de instrucción:** *"Construir una solución local pequeña y verificable… coordinación de un laboratorio… consultar disponibilidad, reservar y cancelar sin perder el historial… vamos con python + sqlite"* más la tabla de inventario (5 unidades) suministrada como imagen.
- **Acción o resultado del agente:** completó la sección 1 del README (problema, alcance in/out, R-01…R-06, reglas V-1…V-9 con el ejemplo del enunciado, supuestos, CA-01…CA-05) y dejó definida la sección 2.2 con el stack elegido.
- **Decisión humana:** pendiente de verificación.
- **Evidencia:** `README.md` sección 1, commit `cf0637c`.
- **Correcciones:** ninguna (aún no verificada).

#### Episodio 3 — Implementación y verificación (cuarta entrega del episodio en un único ciclo delegado)

- **Objetivo y requisito:** construir la solución Python + SQLite local con reglas V-1…V-9 y persistencia (R-01…R-06), con pruebas automatizadas.
- **Contexto suministrado y extracto de instrucción:** el episodio 2 de especificación (*"vamos con python + sqlite"*).
- **Acción o resultado del agente:** escribió `reservas.py` (API `Laboratorio` + CLI de 6 comandos con códigos de proceso) y `tests/test_reservas.py` (32 pruebas de unittest) que cubren inventario precargado, superposición estricta, límites consecutivos, unidades distintas, cancelación conservando datos, persistencia al reiniciar, reset y validaciones. Demostración CLI end‑to‑end de la secuencia del ejemplo de MIC‑01 (ver sección 2.7) con los códigos de proceso correctos. Datos persistidos en `data/reservas.db` (no versionado); base reiniciada con `reset` al final para dejar datos limpios.
- **Decisión humana:** pendiente de verificación.
- **Evidencia:** commit `79e2fb0` — `feat: app de reservas (Python+stdlib/SQLite) con CLI y 32 pruebas`; salida de `python -m unittest discover -s tests` → `Ran 32 tests … OK`; transcript del ejemplo completo capturado en la sección 2.7.
- **Correcciones (ocurrieron):** (a) la CLI abortaba con `UnicodeEncodeError` en consola cp1252 por usar el carácter `→` en los mensajes: se corrigió usando flecha ASCII `->` (D-06). (b) La rama `reset` del CLI dejaba una conexión SQLite abierta (bloqueo al limpiar temporales en Windows): se corrigió cerrando explícitamente la conexión. Ambas correcciones quedaron en el mismo commit `79e2fb0` de la entrega.

#### Episodio 4 — Menú de comandos al correr sin argumentos

- **Objetivo y requisito:** hacer que `python .\reservas.py` sin comando muestre un menú de lo que se puede hacer, en lugar del error en seco de argparse (reporte del solicitante con su salida real).
- **Contexto suministrado y extracto de instrucción:** *"al correr reservas.py agrega un menú de qué se puede hacer"* junto a la salida del error: `reservas: error: the following arguments are required: comando`.
- **Acción o resultado del agente:** agregó `_imprimir_menu()` con los 6 comandos, sus opciones requeridas, la ruta de datos y un ejemplo de uso; `main` ahora muestra el menú y sale con código 0 cuando no hay argumentos (con argumentos incorrectos sigue el error 2 de argparse). Prueba nueva `test_menu_sin_comando_sale_con_0`; suite en 33 pruebas en verde. Se actualizó la sección 2.6 con la salida real del menú.
- **Decisión humana:** pendiente de verificación.
- **Evidencia:** commit de esta entrega (`feat: menu de comandos…`); salida del menú documentada en 2.6; suite `Ran 33 tests … OK`.
- **Correcciones:** no ocurrieron (funcionó de primera).

---

## Notas de documentación

- No incluir secretos, tokens ni credenciales en este repositorio.
- No incluir conversaciones privadas completas: solo extractos breves de instrucciones.
- Usar **solicitantes ficticios**; ningún dato real de estudiantes.
- Criterio del README: el repositorio explica por sí solo qué se construyó y cómo se comprobó.
