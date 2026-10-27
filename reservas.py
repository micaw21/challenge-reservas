"""Reservas de equipos de laboratorio.

Aplicación de consola para consultar disponibilidad, reservar y cancelar
unidades de un inventario precargado, con historial persistente en SQLite.

Sin dependencias externas: solo biblioteca estándar de Python (>= 3.11).

Códigos de proceso: 0 = operación aceptada; 1 = operación rechazada
(validación, unidad desconocida o superposición); 2 = uso incorrecto de la
línea de comandos.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

RUTA_DB = Path(__file__).resolve().parent / "data" / "reservas.db"

INVENTARIO_PRECARGADO: tuple[tuple[str, str], ...] = (
    ("MIC-01", "Microscopio digital"),
    ("MIC-02", "Microscopio digital"),
    ("OSC-01", "Osciloscopio"),
    ("MUL-01", "Multímetro"),
    ("FUE-01", "Fuente de alimentación"),
)

ESTADO_ACTIVA = "ACTIVA"
ESTADO_CANCELADA = "CANCELADA"

FORMATO_FECHA = "YYYY-MM-DD HH:MM"


class Rechazo(Exception):
    """Operación rechazada por validación o conflicto de negocio."""


def _texto_fecha(valor: str) -> str:
    return " ".join(valor.strip().split()).replace("T", " ")


def parse_fecha(valor: str) -> datetime:
    """Convierte 'YYYY-MM-DD HH:MM' (o ISO con T) en datetime ingenuo."""
    texto = _texto_fecha(valor)
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError as exc:
        raise Rechazo(
            f"fecha y hora inválidas: '{valor}' (se espera '{FORMATO_FECHA}')"
        ) from exc
    if momento.tzinfo is not None:
        raise Rechazo(
            f"fecha y hora inválidas: '{valor}' (no se admiten zonas horarias)"
        )
    return momento


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

    def _unidad(self, unidad: str) -> None:
        fila = self.conexion.execute(
            "SELECT 1 FROM inventario WHERE unidad = ?", (unidad.strip(),)
        ).fetchone()
        if fila is None:
            conocidas = ", ".join(e["unidad"] for e in self.unidades())
            raise Rechazo(f"unidad desconocida: '{unidad}' (conocidas: {conocidas})")
        return unidad.strip()

    def _solicitante(self, solicitante: str) -> str:
        limpio = solicitante.strip()
        if not limpio:
            raise Rechazo("solicitante vacío: la reserva necesita un solicitante")
        return limpio

    def _intervalo(self, inicio: str, fin: str) -> tuple[datetime, datetime]:
        desde = parse_fecha(inicio)
        hasta = parse_fecha(fin)
        if desde >= hasta:
            raise Rechazo(
                f"intervalo inválido: inicio '{_formato(desde)}' debe ser "
                f"estrictamente anterior a fin '{_formato(hasta)}'"
            )
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
        unidad = self._unidad(unidad)
        solicitante = self._solicitante(solicitante)
        desde, hasta = self._intervalo(inicio, fin)
        choque = self._activo_solapa(unidad, desde, hasta)
        if choque is not None:
            raise Rechazo(
                f"unidad {unidad} ya reservada por '{choque['solicitante']}'"
                f" de {choque['inicio']} a {choque['fin']}"
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
            f" id={fila['id']} [{fila['estado']}] {fila['unidad']}"
            f" {fila['inicio']} -> {fila['fin']} '{fila['solicitante']}'"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
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

    argumentos = parser.parse_args(argv)

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
            if estado == "LIBRE":
                print(
                    f"LIBRE: {argumentos.unidad} {_texto_fecha(argumentos.desde)} -> {_texto_fecha(argumentos.hasta)}"
                )
                return 0
            print(
                f"OCUPADA: {argumentos.unidad} {_texto_fecha(argumentos.desde)} -> {_texto_fecha(argumentos.hasta)}"
                f" (choca con reserva id={choque['id']} activa de"
                f" '{choque['solicitante']}' {choque['inicio']} -> {choque['fin']})"
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
                f" {fila['unidad']} {fila['inicio']} -> {fila['fin']}"
                f" '{fila['solicitante']}')."
            )
            return 0
    except Rechazo as error:
        print(f"ERROR: {error}")
        return 1
    finally:
        lab.cerrar()
    return 2  # comando no manejado


if __name__ == "__main__":
    raise SystemExit(main())
