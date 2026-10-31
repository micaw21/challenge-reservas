"""Reservas de equipos de laboratorio.

Aplicación de consola para consultar disponibilidad, reservar y cancelar
unidades de un inventario precargado, con historial persistente en SQLite.

Sin dependencias externas: solo biblioteca estándar de Python (>= 3.11).

Códigos de proceso (modo por comandos): 0 = aceptado; 1 = rechazado
(validación, unidad desconocida o superposición); 2 = uso incorrecto de la
línea de comandos. Al correr sin argumentos se abre un menú interactivo que
solo sale con 0, un número negativo o /salir.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Base local del proyecto; se puede apuntar a otra con --db (útil en pruebas).
RUTA_DB = Path(__file__).resolve().parent / "data" / "reservas.db"

# Inventario definido por negocio: se siembra, nunca se administra desde la app.
INVENTARIO_PRECARGADO: tuple[tuple[str, str], ...] = (
    ("MIC-01", "Microscopio digital"),
    ("MIC-02", "Microscopio digital"),
    ("OSC-01", "Osciloscopio"),
    ("MUL-01", "Multímetro"),
    ("FUE-01", "Fuente de alimentación"),
)

ESTADO_ACTIVA = "ACTIVA"
ESTADO_CANCELADA = "CANCELADA"

# Formato visible pedido por el solicitante; el ISO antiguo sigue aceptado.
FORMATO_FECHA = "DD-MM-YYYY HH:MM"
FORMATO_FECHA_ISO = "YYYY-MM-DD HH:MM"


class Rechazo(Exception):
    """Operación rechazada por validación o conflicto de negocio."""


def _texto_fecha(valor: str) -> str:
    """Normaliza espacios y acepta la separación ISO de la hora con 'T'."""
    return " ".join(valor.strip().split()).replace("T", " ")


def parse_fecha(valor: str) -> datetime:
    """Convierte 'DD-MM-YYYY HH:MM' (o el ISO 'YYYY-MM-DD HH:MM') en datetime.

    El formato visible/canónico es DD-MM-YYYY HH:MM; el ISO se mantiene como
    equivalente para compatibilidad con las consultas por comando.
    """
    texto = _texto_fecha(valor)
    try:
        momento = datetime.strptime(texto, "%d-%m-%Y %H:%M")
    except ValueError:
        try:
            momento = datetime.fromisoformat(texto)  # equivalente ISO
        except ValueError as exc:
            raise Rechazo(
                f"fecha y hora inválidas: '{valor}' (se espera '{FORMATO_FECHA}')"
            ) from exc
    if momento.tzinfo is not None:
        raise Rechazo(
            f"fecha y hora inválidas: '{valor}' (no se admiten zonas horarias)"
        )
    return momento


def _visible(momento: datetime) -> str:
    """Fecha visible en el formato canónico DD-MM-YYYY HH:MM."""
    return momento.strftime("%d-%m-%Y %H:%M")


def _mostrar(texto_iso: str) -> str:
    """Convierte una fecha guardada (ISO) al formato visible DD-MM-YYYY HH:MM."""
    momento = datetime.fromisoformat(str(texto_iso).replace("T", " "))
    return _visible(momento)


def _fecha_simple(valor: str) -> str:
    """Valida una fecha 'DD-MM-YYYY' sola (para pedidos por partes)."""
    for formato in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            datetime.strptime(valor, formato)
            return valor
        except (TypeError, ValueError):
            continue
    raise Rechazo(f"fecha inválida: '{valor}' (se espera 'DD-MM-YYYY')")


def _rechazo_intervalo(desde: datetime, hasta: datetime) -> Rechazo:
    """Error compartido: intervalo con inicio no estrictamente anterior al fin."""
    return Rechazo(
        f"intervalo inválido: inicio '{_visible(desde)}' debe ser "
        f"estrictamente anterior a fin '{_visible(hasta)}'"
    )


def _texto_requerido(valor: str) -> str:
    """Validador V-2: el solicitante no puede ser vacío ni solo espacios."""
    if not valor.strip():
        raise Rechazo("solicitante vacío: la reserva necesita un solicitante")
    return valor


def _pedir_parte(pedir, mensaje: str, validar) -> str:
    """Pide un dato y lo valida al momento; con error, avisa y re-pide solo ese campo."""
    while True:
        texto = _consultar(pedir, mensaje)
        try:
            validar(texto)
            return texto
        except Rechazo as error:
            print(f"\nERROR: {error}\n")


def _hora_simple(valor: str) -> str:
    """Valida una hora 'HH:MM' sola (para pedidos por partes)."""
    try:
        datetime.strptime(valor, "%H:%M")
    except (TypeError, ValueError) as exc:
        raise Rechazo(f"hora inválida: '{valor}' (se espera 'HH:MM')") from exc
    return valor


def _formato(momento: datetime) -> str:
    return momento.isoformat(sep=" ", timespec="minutes")


class Laboratorio:
    """Fachada sobre la base de datos de reservas."""

    def __init__(self, db: str | Path = RUTA_DB) -> None:
        self.ruta = Path(db)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.conexion = sqlite3.connect(self.ruta)
        self.conexion.row_factory = sqlite3.Row
        self._crear_tablas()

    def _crear_tablas(self) -> None:
        self.conexion.executescript(
            """
            CREATE TABLE IF NOT EXISTS inventario (
                unidad TEXT PRIMARY KEY,
                equipo TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reservas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unidad TEXT NOT NULL REFERENCES inventario(unidad),
                solicitante TEXT NOT NULL,
                inicio TEXT NOT NULL,
                fin TEXT NOT NULL,
                estado TEXT NOT NULL CHECK (estado IN ('ACTIVA', 'CANCELADA'))
            );
            """
        )
        # Solo siembra si la base es nueva: al reabrir, no duplica inventario.
        if self.conexion.execute("SELECT COUNT(*) FROM inventario").fetchone()[0] == 0:
            self.conexion.executemany(
                "INSERT INTO inventario (unidad, equipo) VALUES (?, ?)",
                INVENTARIO_PRECARGADO,
            )
        self.conexion.commit()

    def reset(self) -> None:
        """Reinicia los datos: borra todo y vuelve a sembrar el inventario."""
        self.conexion.executescript(
            "DROP TABLE IF EXISTS reservas; DROP TABLE IF EXISTS inventario;"
        )
        self.conexion.commit()
        self._crear_tablas()

    def cerrar(self) -> None:
        self.conexion.close()

    # ------------------------------------------------------------- consultas
    # (solo lectura: el inventario es precargado; no hay alta ni baja de unidades)

    def unidades(self) -> list[sqlite3.Row]:
        return self.conexion.execute(
            "SELECT unidad, equipo FROM inventario ORDER BY unidad"
        ).fetchall()

    def reservas(self, unidad: str | None = None) -> list[sqlite3.Row]:
        if unidad is None:
            return self.conexion.execute(
                "SELECT id, unidad, solicitante, inicio, fin, estado"
                " FROM reservas ORDER BY id"
            ).fetchall()
        return self.conexion.execute(
            "SELECT id, unidad, solicitante, inicio, fin, estado"
            " FROM reservas WHERE unidad = ? ORDER BY id",
            (unidad,),
        ).fetchall()

    # ------------------------------------------------------------- validación

    def _unidad(self, unidad: str) -> str:
        # V-1: rechazar unidades fuera del inventario precargado.
        fila = self.conexion.execute(
            "SELECT 1 FROM inventario WHERE unidad = ?", (unidad.strip(),)
        ).fetchone()
        if fila is None:
            conocidas = ", ".join(e["unidad"] for e in self.unidades())
            raise Rechazo(f"unidad desconocida: '{unidad}' (conocidas: {conocidas})")
        return unidad.strip()

    def validar_unidad(self, unidad: str) -> str:
        """Valida la unidad contra el inventario (V-1); Rechazo si no existe."""
        return self._unidad(unidad)

    def _solicitante(self, solicitante: str) -> str:
        limpio = solicitante.strip()
        if not limpio:
            raise Rechazo("solicitante vacío: la reserva necesita un solicitante")
        return limpio

    def _intervalo(self, inicio: str, fin: str) -> tuple[datetime, datetime]:
        desde = parse_fecha(inicio)
        hasta = parse_fecha(fin)
        if desde >= hasta:
            raise _rechazo_intervalo(desde, hasta)
        return desde, hasta

    def _activo_solapa(
        self, unidad: str, desde: datetime, hasta: datetime
    ) -> sqlite3.Row | None:
        filas = self.conexion.execute(
            "SELECT id, solicitante, inicio, fin FROM reservas"
            " WHERE unidad = ? AND estado = ?",
            (unidad, ESTADO_ACTIVA),
        ).fetchall()
        for fila in filas:
            otra_inicio = datetime.fromisoformat(fila["inicio"].replace("T", " "))
            otra_fin = datetime.fromisoformat(fila["fin"].replace("T", " "))
            # Superposición estricta: los límites consecutivos se permiten.
            if desde < otra_fin and otra_inicio < hasta:
                return fila
        return None

    # ------------------------------------------------------------- operaciones

    def reservar(
        self, unidad: str, solicitante: str, inicio: str, fin: str
    ) -> int:
        # V-1…V-6 en orden: unidad, solicitante, intervalo y superposición.
        unidad = self._unidad(unidad)
        solicitante = self._solicitante(solicitante)
        desde, hasta = self._intervalo(inicio, fin)
        choque = self._activo_solapa(unidad, desde, hasta)
        if choque is not None:
            raise Rechazo(
                f"unidad {unidad} ya reservada por '{choque['solicitante']}'"
                f" de {_mostrar(choque['inicio'])} a {_mostrar(choque['fin'])}"
                f" (reserva id={choque['id']}, activa)"
            )
        cursor = self.conexion.execute(
            "INSERT INTO reservas (unidad, solicitante, inicio, fin, estado)"
            " VALUES (?, ?, ?, ?, ?)",
            (unidad, solicitante, _formato(desde), _formato(hasta), ESTADO_ACTIVA),
        )
        self.conexion.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def cancelar(self, id_reserva: int) -> sqlite3.Row:
        # El historial no se borra: solo cambia el estado (V-5).
        fila = self.conexion.execute(
            "SELECT id, unidad, solicitante, inicio, fin, estado FROM reservas"
            " WHERE id = ?",
            (id_reserva,),
        ).fetchone()
        if fila is None:
            raise Rechazo(f"reserva inexistente: no hay reserva con id={id_reserva}")
        if fila["estado"] == ESTADO_CANCELADA:
            raise Rechazo(
                f"la reserva id={id_reserva} ya está cancelada"
            )
        self.conexion.execute(
            "UPDATE reservas SET estado = ? WHERE id = ?",
            (ESTADO_CANCELADA, id_reserva),
        )
        self.conexion.commit()
        return fila  # datos tal como quedaron, con estado cancelado

    def disponibilidad(
        self, unidad: str, inicio: str, fin: str
    ) -> tuple[str, sqlite3.Row | None]:
        """Devuelve ('LIBRE', None) o ('OCUPADA', reserva_activa_que_solapa)."""
        # V-9: consulta con exactamente las mismas reglas que la reserva.
        unidad = self._unidad(unidad)
        desde, hasta = self._intervalo(inicio, fin)
        choque = self._activo_solapa(unidad, desde, hasta)
        return (("LIBRE", None) if choque is None else ("OCUPADA", choque))


# --------------------------------------------------------------------- CLI


def _imprimir_unidades(lab: Laboratorio) -> int:
    for fila in lab.unidades():
        print(f"{fila['unidad']}\t{fila['equipo']}")
    return 0


def _imprimir_reservas(lab: Laboratorio, unidad: str | None) -> int:
    filas = lab.reservas(unidad)
    if not filas:
        print("(sin reservas registradas)")
        return 0
    for fila in filas:
        print(
            f"id={fila['id']} [{fila['estado']}] {fila['unidad']}"
            f" {_mostrar(fila['inicio'])} -> {_mostrar(fila['fin'])}"
            f" '{fila['solicitante']}'"
        )
    return 0


def _limpiar() -> None:
    """Limpia la pantalla de la consola (cls en Windows, clear en otro SO)."""
    os.system("cls" if os.name == "nt" else "clear")


def _consultar(pedir, mensaje: str) -> str:
    """Muestra el pedido de dato por stdout y devuelve la respuesta.

    Se imprime el prompt con `print` (no como argumento de `input`) para que
    el texto quede visible tanto en consola como en las pruebas capturadas.
    """
    print(mensaje, end="")
    return pedir("")


def _pausa(pedir) -> None:
    _consultar(pedir, "\n(Enter para volver al menú) ")


def _volver_o_repetir(pedir, accion: str) -> bool:
    """Tras el resultado: 's' repite la misma opción; Enter o 'n' vuelve al menú."""
    respuesta = _consultar(
        pedir,
        f"\n¿Desea {accion}?"
        " (s = sí, repetir aquí / Enter = volver al menú): ",
    ).strip().lower()
    return respuesta == "s"


def _es_salida(texto: str) -> bool:
    """La salida se acepta con 0, un número negativo o /salir."""
    t = texto.strip().lower()
    if t == "/salir" or t == "0":
        return True
    return len(t) > 1 and t.startswith("-") and t[1:].isdigit()


def _imprimir_menu() -> None:
    """Menú principal interactivo (opciones 1..6, salir con 0/-n//salir)."""
    print("=== RESERVAS DE EQUIPOS DE LABORATORIO ===")
    print()
    print("  1) Ver inventario")
    print("  2) Ver historial de reservas")
    print("  3) Consultar disponibilidad")
    print("  4) Crear una reserva")
    print("  5) Cancelar una reserva")
    print("  6) Reiniciar los datos (borra las reservas)")
    print()
    print("  0) Salir  (también: un número negativo o /salir)")


def _op_inventario(lab: Laboratorio, pedir) -> None:
    # Solo lectura del inventario: se muestra una vez y Enter vuelve al menú
    # (no tiene sentido preguntar por repetir una pantalla de solo datos).
    _limpiar()
    print("--- INVENTARIO PRECARGADO ---\n")
    print("Unidades definidas en la aplicación (no se administran desde aquí):\n")
    _imprimir_unidades(lab)
    _pausa(pedir)


def _ayuda_unidades(lab: Laboratorio) -> None:
    """Lista las unidades disponibles junto al prompt de unidad."""
    print("Unidades disponibles:")
    for fila in lab.unidades():
        print(f"  {fila['unidad']:<8} {fila['equipo']}")
    print()


def _op_listar(lab: Laboratorio, pedir) -> None:
    while True:
        _limpiar()
        print("--- LISTAR RESERVAS ---\n")
        _ayuda_unidades(lab)
        unidad = _pedir_unidad(
            lab,
            pedir,
            "Ingrese un ID de unidad para filtrar el historial"
            " (ej.: MIC-01, Enter = todas): ",
            permitir_vacio=True,
        )
        filas = lab.reservas(unidad or None)
        if not filas:
            print("(sin reservas registradas)")
        for fila in filas:
            print(
                f"id={fila['id']} [{fila['estado']}] {fila['unidad']}"
                f" {_mostrar(fila['inicio'])} -> {_mostrar(fila['fin'])}"
                f" '{fila['solicitante']}'"
            )
        if not _volver_o_repetir(pedir, "hacer otra consulta"):
            return


def _pedir_unidad(
    lab: Laboratorio, pedir, mensaje: str, permitir_vacio: bool = False
) -> str:
    """Pide el ID de unidad y lo valida al toque (V-1), antes de pedir más datos.

    Con una unidad desconocida muestra el error y vuelve a pedir la unidad;
    solo con una unidad válida se continúa. Si `permitir_vacio`, Enter devuelve
    "" (ej.: listar sin filtro).
    """
    while True:
        texto = _consultar(pedir, mensaje).strip()
        if permitir_vacio and not texto:
            return ""
        try:
            return lab.validar_unidad(texto)
        except Rechazo as error:
            print(f"\nERROR: {error}\n")


def _op_disponibilidad(lab: Laboratorio, pedir) -> None:
    while True:
        _limpiar()
        print("--- DISPONIBILIDAD ---\n")
        _ayuda_unidades(lab)
        unidad = _pedir_unidad(
            lab, pedir, "Ingrese el ID de la unidad a consultar (ej.: MIC-01): "
        )
        try:
            # Cada dato se valida al pedirse y solo ese campo se re-pide.
            fecha = _pedir_parte(
                pedir,
                "Ingrese la fecha a consultar (DD-MM-YYYY): ",
                _fecha_simple,
            ).strip()
            while True:
                hora_inicio = _pedir_parte(
                    pedir, "Ingrese la hora de inicio (HH:MM): ", _hora_simple
                ).strip()
                hora_fin = _pedir_parte(
                    pedir, "Ingrese la hora de fin (HH:MM): ", _hora_simple
                ).strip()
                desde = f"{fecha} {hora_inicio}"
                hasta = f"{fecha} {hora_fin}"
                if parse_fecha(desde) < parse_fecha(hasta):
                    break
                print(f"\nERROR: {_rechazo_intervalo(parse_fecha(desde), parse_fecha(hasta))}\n")
            estado, choque = lab.disponibilidad(unidad, desde, hasta)
        except Rechazo as error:
            print(f"\nERROR: {error}")
        else:
            if estado == "LIBRE":
                print(
                    f"\nLIBRE: {unidad}"
                    f" {_mostrar(parse_fecha(desde))} -> {_mostrar(parse_fecha(hasta))}"
                )
            else:
                print(
                    f"\nOCUPADA: choca con reserva id={choque['id']} activa de"
                    f" '{choque['solicitante']}'"
                    f" {_mostrar(choque['inicio'])} -> {_mostrar(choque['fin'])}"
                )
        if not _volver_o_repetir(pedir, "consultar otro intervalo"):
            return


def _ayuda_reservas(lab: Laboratorio, unidad: str) -> None:
    """Muestra las reservas activas de la unidad antes de pedir el horario.

    Así el solicitante ve de una si el equipo está ocupado y cuándo (V-6).
    """
    activas = [f for f in lab.reservas(unidad) if f["estado"] == ESTADO_ACTIVA]
    if not activas:
        print(f"Reservas activas de {unidad}: ninguna (libre en cualquier horario).\n")
        return
    print(f"Reservas activas de {unidad} (ese horario ya queda reservado):")
    for fila in activas:
        print(
            f"  id={fila['id']} {_mostrar(fila['inicio'])} -> {_mostrar(fila['fin'])}"
            f" '{fila['solicitante']}'"
        )
    print()


def _pedir_intervalo_reserva(lab: Laboratorio, pedir, unidad: str) -> tuple[str, str]:
    """Pide inicio y fin validados, con orden correcto y sin superposición (V-4/V-6).

    El choque con una reserva activa se detecta apenas el intervalo está
    completo: el error sale al toque y solo se re-piden las fechas (la unidad
    y el solicitante quedan en pie).
    """
    while True:
        inicio = _pedir_parte(
            pedir,
            "Ingrese fecha y hora de inicio (DD-MM-YYYY HH:MM): ",
            parse_fecha,
        ).strip()
        fin = _pedir_parte(
            pedir,
            "Ingrese fecha y hora de fin (DD-MM-YYYY HH:MM): ",
            parse_fecha,
        ).strip()
        desde_dt, hasta_dt = parse_fecha(inicio), parse_fecha(fin)
        if desde_dt >= hasta_dt:
            print(f"\nERROR: {_rechazo_intervalo(desde_dt, hasta_dt)}\n")
            continue
        # V-6 apenas se conoce el intervalo pedido: mensaje igual al de la API.
        estado, choque = lab.disponibilidad(unidad, inicio, fin)
        if estado == "OCUPADA":
            print(
                f"\nERROR: unidad {unidad} ya reservada por"
                f" '{choque['solicitante']}' de {_mostrar(choque['inicio'])}"
                f" a {_mostrar(choque['fin'])} (reserva id={choque['id']}, activa)\n"
            )
            continue
        return inicio, fin


def _op_reservar(lab: Laboratorio, pedir) -> None:
    while True:
        _limpiar()
        print("--- NUEVA RESERVA --- (fecha y hora 'DD-MM-YYYY HH:MM')\n")
        _ayuda_unidades(lab)
        unidad = _pedir_unidad(lab, pedir, "Ingrese el ID de la unidad a reservar (ej.: MIC-01): ")
        # Antes de pedir el horario: qué reservas activas tiene esta unidad.
        _ayuda_reservas(lab, unidad)
        solicitante = _pedir_parte(
            pedir,
            "Ingrese el solicitante (nombre de quien pide el equipo): ",
            _texto_requerido,
        ).strip()
        try:
            inicio, fin = _pedir_intervalo_reserva(lab, pedir, unidad)
            id_reserva = lab.reservar(unidad, solicitante, inicio, fin)
        except Rechazo as error:
            # A esta altura solo puede fallar algo externo síncrono; el choque
            # (V-6) ya se aviso al toque en _pedir_intervalo_reserva.
            print(f"\nERROR: {error}")
        else:
            print(f"\nReserva creada con id={id_reserva}.")
        if not _volver_o_repetir(pedir, "crear otra reserva"):
            return


def _op_cancelar(lab: Laboratorio, pedir) -> None:
    while True:
        _limpiar()
        print("--- CANCELAR RESERVA ---\n")
        # El id se valida al momento: con un dato malo se vuelve a pedir;
        # Enter deja la opción sin cancelar nada.
        while True:
            texto = _consultar(
                pedir,
                "Ingrese el número de id de la reserva a cancelar"
                " (ej.: 1, Enter = volver al menú): ",
            ).strip()
            if not texto:
                return
            # Validación del dato numérico ANTES de tocar la base de datos.
            if not texto.isdigit():
                print(
                    "\nERROR: el id debe ser un número entero (sin signo).\n"
                )
                continue
            try:
                fila = lab.cancelar(int(texto))
                break
            except Rechazo as error:
                print(f"\nERROR: {error}\n")
        print(
            f"\nReserva id={fila['id']} cancelada (registro conservado:"
            f" {fila['unidad']} {_mostrar(fila['inicio'])} ->"
            f" {_mostrar(fila['fin'])} '{fila['solicitante']}')."
        )
        if not _volver_o_repetir(pedir, "cancelar otra reserva"):
            return


def _op_reset(lab: Laboratorio, pedir) -> None:
    _limpiar()
    print("--- REINICIAR DATOS ---\n")
    respuesta = _consultar(pedir, "¿Seguro que desea reiniciar? (s/N): ").strip().lower()
    if respuesta == "s":
        lab.reset()
        print("\nDatos reiniciados: inventario resiembado y reservas eliminadas.")
    else:
        print("\nOperación cancelada: no se modificó nada.")
    _pausa(pedir)


def _menu_interactivo(db: str | Path = RUTA_DB, entrada=None) -> int:
    """Bucle del menú: se repite hasta elegir 0, un negativo o /salir."""
    pedir = entrada if entrada is not None else input
    lab = Laboratorio(db)
    try:
        while True:
            _limpiar()
            _imprimir_menu()
            eleccion = pedir("Elija una opción (0-6): ").strip()
            if _es_salida(eleccion):
                return 0
            match eleccion:
                case "1":
                    _op_inventario(lab, pedir)
                case "2":
                    _op_listar(lab, pedir)
                case "3":
                    _op_disponibilidad(lab, pedir)
                case "4":
                    _op_reservar(lab, pedir)
                case "5":
                    _op_cancelar(lab, pedir)
                case "6":
                    _op_reset(lab, pedir)
                case _:
                    # Cualquier valor fuera de la navegación se rechaza y
                    # vuelve a mostrar el menú.
                    print(f"\nOpción no válida: '{eleccion}'. Ingrese de nuevo.")
                    _pausa(pedir)
    except (EOFError, KeyboardInterrupt):
        # Cerrar ordenadamente con Ctrl+D / Ctrl+C.
        return 0
    finally:
        lab.cerrar()


def main(argv: list[str] | None = None) -> int:
    # Sin argumentos: menú interactivo; con argumentos: uso directo por comandos.
    argumentos_externos = sys.argv[1:] if argv is None else argv
    if not argumentos_externos:
        return _menu_interactivo()

    parser = argparse.ArgumentParser(
        prog="reservas",
        description=(
            "Consultar disponibilidad, reservar y cancelar unidades de"
            " un inventario de laboratorio (persistencia local en SQLite)."
        ),
    )
    parser.add_argument("--db", default=str(RUTA_DB), help="ruta de la base SQLite")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("inventario", help="lista el inventario precargado")

    sub.add_parser("listar", help="lista reservas registradas (historial)")
    listar = sub.choices["listar"]
    listar.add_argument("--unidad", help="filtro por unidad")

    consulta = sub.add_parser("disponibilidad", help="consulta si un intervalo está libre")
    consulta.add_argument("--unidad", required=True)
    consulta.add_argument("--desde", required=True)
    consulta.add_argument("--hasta", required=True)

    alta = sub.add_parser("reservar", help="crea una reserva activa")
    alta.add_argument("--unidad", required=True)
    alta.add_argument("--solicitante", required=True)
    alta.add_argument("--desde", required=True)
    alta.add_argument("--hasta", required=True)

    baja = sub.add_parser("cancelar", help="cancela una reserva conservando el registro")
    baja.add_argument("--id", type=int, required=True)

    sub.add_parser("reset", help="reinicia los datos y resiembra el inventario")

    argumentos = parser.parse_args(argumentos_externos)

    if argumentos.comando == "reset":
        lab = Laboratorio(argumentos.db)
        lab.reset()
        lab.cerrar()
        print("Datos reiniciados: inventario resiembado y reservas eliminadas.")
        return 0

    lab = Laboratorio(argumentos.db)
    try:
        if argumentos.comando == "inventario":
            return _imprimir_unidades(lab)
        if argumentos.comando == "listar":
            return _imprimir_reservas(lab, argumentos.unidad)
        if argumentos.comando == "disponibilidad":
            estado, choque = lab.disponibilidad(
                argumentos.unidad, argumentos.desde, argumentos.hasta
            )
            desde_mostrado = _mostrar(parse_fecha(argumentos.desde))
            hasta_mostrado = _mostrar(parse_fecha(argumentos.hasta))
            if estado == "LIBRE":
                print(
                    f"LIBRE: {argumentos.unidad} {desde_mostrado} -> {hasta_mostrado}"
                )
                return 0
            # Ocupada se reporta con código 1 para verificar sin parsear texto.
            print(
                f"OCUPADA: {argumentos.unidad} {desde_mostrado} -> {hasta_mostrado}"
                f" (choca con reserva id={choque['id']} activa de"
                f" '{choque['solicitante']}'"
                f" {_mostrar(choque['inicio'])} -> {_mostrar(choque['fin'])})"
            )
            return 1
        if argumentos.comando == "reservar":
            id_reserva = lab.reservar(
                argumentos.unidad,
                argumentos.solicitante,
                argumentos.desde,
                argumentos.hasta,
            )
            print(f"Reserva creada con id={id_reserva}.")
            return 0
        if argumentos.comando == "cancelar":
            fila = lab.cancelar(argumentos.id)
            print(
                f"Reserva id={fila['id']} cancelada (registro conservado:"
                f" {fila['unidad']} {_mostrar(fila['inicio'])} ->"
                f" {_mostrar(fila['fin'])} '{fila['solicitante']}')."
            )
            return 0
    except Rechazo as error:
        # Cualquier rechazo de negocio comparte código de salida 1.
        print(f"ERROR: {error}")
        return 1
    finally:
        # Cerrar siempre: evita dejar la base SQLite bloqueada en Windows.
        lab.cerrar()
    return 2  # comando no manejado


if __name__ == "__main__":
    raise SystemExit(main())
