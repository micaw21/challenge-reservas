# Challenge

> **Estado:** documentación en construcción. Este README se actualiza a medida que avanza el trabajo.
> El repositorio debe explicar por sí solo **qué se construyó y cómo se comprobó**.

---

## 1. Especificación

### 1.1 Problema

TODO: descripción breve del problema a resolver.

### 1.2 Alcance

TODO: qué incluye y qué queda fuera del alcance.

### 1.3 Requisitos verificables

TODO: lista de requisitos con criterios de comprobación.

### 1.4 Reglas

TODO: reglas de negocio o de funcionamiento que la solución debe respetar.

### 1.5 Supuestos

TODO: supuestos tomados sobre la especificación.

### 1.6 Criterios de aceptación

TODO: lista de criterios que determinan si la entrega es aceptada.

---

## 2. Solución

### 2.1 Estructura

TODO: organización del código / carpetas principales.

### 2.2 Decisiones técnicas

TODO: lenguaje, framework, almacenamiento, y por qué.

### 2.3 Requisitos previos y versiones

TODO: runtime, gestor de paquetes y versiones mínimas (docker, node, python, etc.).

### 2.4 Instalación

TODO: pasos de instalación.

### 2.5 Carga inicial y reinicio de datos

TODO: cómo cargar datos iniciales y cómo resetear el estado.

**Persistencia de datos:** TODO — dónde se guardan los datos (archivo, base de datos, volumen, ruta).

### 2.6 Comandos de aplicación y pruebas

TODO: comandos para levantar la app, ejecutar pruebas, etc.

```bash
# TODO
```

### 2.7 Ejemplos de entrada y salida

TODO: ejemplos con **solicitantes ficticios** (sin datos reales de estudiantes).

**Entrada:**
```json
{ "TODO": "ejemplo de entrada ficticia" }
```

**Salida:**
```json
{ "TODO": "ejemplo de salida esperada" }
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
| 1. Creación del esqueleto del README + carga de datos del agente (esta sección) | v0.1 | `README.md` (secciones 1, 2, 3, 4 creadas; 3 completada con datos del agente) | commit `4472118` — `docs: esqueleto del README y datos del agente (seccion 3)` |

---

## 4. Registro de decisiones y delegación

### 4.1 Decisiones significativas

Registro de decisiones significativas, con motivo, alternativas evaluadas (cuando existía una disyuntiva) y consecuencias.

| # | Decisión | Motivo | Alternativas | Consecuencias |
|---|----------|--------|--------------|---------------|
| 1 | TODO | TODO | TODO | TODO |

### 4.2 Registro de episodios (delegación al agente)

Para cada episodio registrar: objetivo y requisito → contexto suministrado y extracto de instrucción →
acción o resultado del agente → decisión humana de aceptar/corregir/rechazar con motivo → enlace a
archivo, commit, prueba o resultado verificable.

Correcciones: registrar **solo si ocurrieron**; no inventar fallas.

#### Episodio 1 — TODO

- **Objetivo y requisito:** TODO
- **Contexto suministrado y extracto de instrucción:** TODO
- **Acción o resultado del agente:** TODO
- **Decisión humana (aceptar / corregir / rechazar) y motivo:** TODO
- **Evidencia (enlace a archivo, commit, prueba o resultado):** TODO
- **Correcciones (solo si ocurrieron):** TODO

---

## Notas de documentación

- No incluir secretos, tokens ni credenciales en este repositorio.
- No incluir conversaciones privadas completas: solo extractos breves de instrucciones.
- Usar **solicitantes ficticios**; ningún dato real de estudiantes.
- Criterio del README: el repositorio explica por sí solo qué se construyó y cómo se comprobó.
