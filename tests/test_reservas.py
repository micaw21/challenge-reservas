"""Pruebas de reservas de laboratorio.

Ejecutar: python -m unittest discover -s tests -v
Sin dependencias externas; cada prueba usa su propia base SQLite temporal,
de modo que ninguna prueba contamina los datos de otra.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from reservas import Laboratorio, Rechazo, main

MIC = "MIC-01"
SOLICITANTE_A = "Solicitante A"
SOLICITANTE_B = "Solicitante B"
DIA_10_00 = "2026-11-03 10:00"
DIA_10_30 = "2026-11-03 10:30"
DIA_11_00 = "2026-11-03 11:00"
DIA_11_30 = "2026-11-03 11:30"
DIA_12_00 = "2026-11-03 12:00"


class BaseLaboratorio(unittest.TestCase):
    """Caso base: laboratorio con base temporal propia."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ruta_db = Path(tmp.name) / "reservas.db"
        self.lab = Laboratorio(self.ruta_db)
        self.addCleanup(self.lab.cerrar)

    def reservado(self, unidad: str, solicitante: str, inicio: str, fin: str) -> int:
        return self.lab.reservar(unidad, solicitante, inicio, fin)


class TestInventario(BaseLaboratorio):
    """R-01: el inventario precargado se lee sin administrarlo."""
    def test_inventario_precargado(self) -> None:
        unidades = [fila["unidad"] for fila in self.lab.unidades()]
        self.assertEqual(unidades, ["FUE-01", "MIC-01", "MIC-02", "MUL-01", "OSC-01"])

    def test_equipos_valen_lo_esperado(self) -> None:
        equipos = {fila["unidad"]: fila["equipo"] for fila in self.lab.unidades()}
        self.assertEqual(equipos["MIC-01"], "Microscopio digital")
        self.assertEqual(equipos["OSC-01"], "Osciloscopio")


class TestReservas(BaseLaboratorio):
    """R-03: reserva identificable con unidad, solicitante e intervalo."""
    def test_reserva_tiene_identificador_y_datos(self) -> None:
        id_reserva = self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        filas = self.lab.reservas()
        self.assertEqual(len(filas), 1)
        fila = filas[0]
        self.assertEqual(fila["id"], id_reserva)
        self.assertEqual(fila["unidad"], MIC)
        self.assertEqual(fila["solicitante"], SOLICITANTE_A)
        self.assertEqual(fila["inicio"], DIA_10_00)
        self.assertEqual(fila["fin"], DIA_11_00)
        self.assertEqual(fila["estado"], "ACTIVA")


class TestSuperposicion(BaseLaboratorio):
    """V-5/V-6: solo las reservas ACTIVAS bloquean su intervalo."""
    def test_superposicion_activa_rechazada(self) -> None:
        # Ejemplo del enunciado: MIC-01 reservado 10:00-11:00.
        self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        # 10:30-11:30 se rechaza.
        with self.assertRaises(Rechazo):
            self.reservado(MIC, SOLICITANTE_B, DIA_10_30, DIA_11_30)

    def test_superposicion_que_contiene_intervalo_rechazada(self) -> None:
        self.reservado(MIC, SOLICITANTE_B, DIA_10_30, DIA_11_30)
        with self.assertRaises(Rechazo):
            self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)

    def test_cancelada_no_bloquea_superposicion(self) -> None:
        id_reserva = self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        self.lab.cancelar(id_reserva)
        # La cancelada sigue bloqueando si la semántica fuera incorrecta.
        id_nueva = self.reservado(MIC, SOLICITANTE_B, DIA_10_30, DIA_11_30)
        self.assertGreater(id_nueva, id_reserva)


class TestLimitesConsecutivos(BaseLaboratorio):
    """V-7: tocar el límite (fin 11:00 / inicio 11:00) no es superposición."""
    def test_limites_consecutivos_permitidos(self) -> None:
        # Ejemplo del enunciado: 11:00-12:00 permitido con 10:00-11:00.
        self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        id_segunda = self.reservado(MIC, SOLICITANTE_B, DIA_11_00, DIA_12_00)
        self.assertGreater(id_segunda, 0)


class TestUnidadesDistintas(BaseLaboratorio):
    """V-8: unidades distintas no se bloquean entre sí."""
    def test_reservas_simultaneas_de_unidades_distintas(self) -> None:
        # Ejemplo del enunciado: MIC-02 puede reservarse en paralelo a MIC-01.
        id_uno = self.reservado("MIC-01", SOLICITANTE_A, DIA_10_00, DIA_11_00)
        id_dos = self.reservado("MIC-02", SOLICITANTE_B, DIA_10_00, DIA_11_00)
        self.assertGreater(id_dos, id_uno)


class TestCancelacion(BaseLaboratorio):
    """R-04: cancelar conserva id y datos y libera el intervalo."""
    def test_cancelar_conserva_registro_y_datos(self) -> None:
        id_reserva = self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        self.lab.cancelar(id_reserva)
        filas = self.lab.reservas()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["id"], id_reserva)
        self.assertEqual(filas[0]["estado"], "CANCELADA")
        self.assertEqual(filas[0]["solicitante"], SOLICITANTE_A)

    def test_cancelar_libera_intervalo(self) -> None:
        id_reserva = self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        self.lab.cancelar(id_reserva)
        id_nueva = self.reservado(MIC, SOLICITANTE_B, DIA_10_00, DIA_11_00)
        self.assertGreater(id_nueva, id_reserva)

    def test_doble_cancelacion_rechaza(self) -> None:
        id_reserva = self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        self.lab.cancelar(id_reserva)
        with self.assertRaises(Rechazo):
            self.lab.cancelar(id_reserva)

    def test_cancelar_reserva_inexistente_rechaza(self) -> None:
        with self.assertRaises(Rechazo):
            self.lab.cancelar(999)


class TestValidaciones(BaseLaboratorio):
    """V-1…V-4 y V-9: mismas validaciones para reservar y consultar."""
    def test_unidad_desconocida_rechaza(self) -> None:
        with self.assertRaises(Rechazo):
            self.reservado("XXX-99", SOLICITANTE_A, DIA_10_00, DIA_11_00)

    def test_solicitante_vacio_rechaza(self) -> None:
        with self.assertRaises(Rechazo):
            self.reservado(MIC, "", DIA_10_00, DIA_11_00)

    def test_solicitante_solo_espacios_rechaza(self) -> None:
        with self.assertRaises(Rechazo):
            self.reservado(MIC, "   ", DIA_10_00, DIA_11_00)

    def test_fecha_invalida_rechaza(self) -> None:
        with self.assertRaises(Rechazo):
            self.reservado(MIC, SOLICITANTE_A, "ayer", DIA_11_00)

    def test_inicio_igual_a_fin_rechaza(self) -> None:
        with self.assertRaises(Rechazo):
            self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_10_00)

    def test_inicio_posterior_a_fin_rechaza(self) -> None:
        with self.assertRaises(Rechazo):
            self.reservado(MIC, SOLICITANTE_A, DIA_11_00, DIA_10_00)

    def test_disponibilidad_aplica_mismas_validaciones(self) -> None:
        with self.assertRaises(Rechazo):
            self.lab.disponibilidad("XXX-99", DIA_10_00, DIA_11_00)
        with self.assertRaises(Rechazo):
            self.lab.disponibilidad(MIC, DIA_11_00, DIA_10_00)
        with self.assertRaises(Rechazo):
            self.lab.disponibilidad(MIC, "31-02-2026 10:00", DIA_11_00)


class TestDisponibilidad(BaseLaboratorio):
    """R-02: consulta de disponibilidad por unidad e intervalo."""
    def test_libre_si_no_hay_reservas(self) -> None:
        estado, choque = self.lab.disponibilidad(MIC, DIA_10_00, DIA_11_00)
        self.assertEqual(estado, "LIBRE")
        self.assertIsNone(choque)

    def test_ocupada_con_reserva_activa_solapada(self) -> None:
        id_reserva = self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        estado, choque = self.lab.disponibilidad(MIC, DIA_10_30, DIA_11_30)
        self.assertEqual(estado, "OCUPADA")
        self.assertEqual(choque["id"], id_reserva)

    def test_otra_unidad_libre_en_mismo_intervalo(self) -> None:
        self.reservado("MIC-01", SOLICITANTE_A, DIA_10_00, DIA_11_00)
        estado, _ = self.lab.disponibilidad("MIC-02", DIA_10_00, DIA_11_00)
        self.assertEqual(estado, "LIBRE")


class TestPersistencia(BaseLaboratorio):
    """R-05: reservas, estados e inventario sobreviven al reiniciar."""
    def test_reserva_persiste_al_reiniciar_aplicacion(self) -> None:
        self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        self.lab.cerrar()
        lab_reiniciado = Laboratorio(self.ruta_db)
        try:
            filas = lab_reiniciado.reservas()
            self.assertEqual(len(filas), 1)
            self.assertEqual(filas[0]["estado"], "ACTIVA")
        finally:
            lab_reiniciado.cerrar()

    def test_cancelacion_persiste_al_reiniciar_aplicacion(self) -> None:
        id_reserva = self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        self.lab.cancelar(id_reserva)
        self.lab.cerrar()
        lab_reiniciado = Laboratorio(self.ruta_db)
        try:
            fila = lab_reiniciado.reservas()[0]
            self.assertEqual(fila["estado"], "CANCELADA")
        finally:
            lab_reiniciado.cerrar()

    def test_inventario_no_riesembra_con_datos_presentes(self) -> None:
        # El inventario precargado no se duplica al reabrir la base.
        self.lab.cerrar()
        lab_reiniciado = Laboratorio(self.ruta_db)
        try:
            self.assertEqual(len(lab_reiniciado.unidades()), 5)
        finally:
            lab_reiniciado.cerrar()


class TestReset(BaseLaboratorio):
    """Reinicio: vuelven al estado inicial (inventario sembrado, sin reservas)."""
    def test_reset_deja_solo_inventario(self) -> None:
        self.reservado(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        self.lab.reset()
        self.assertEqual(self.lab.reservas(), [])
        self.assertEqual(len(self.lab.unidades()), 5)


class TestCLI(unittest.TestCase):
    """Verificación de la interfaz de comandos: textos y códigos de salida."""

    def _ruta(self) -> tuple[Path, tempfile.TemporaryDirectory]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name) / "cli.db", tmp

    def _salida(self, *args: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            codigo = main(list(args))
        return codigo, buffer.getvalue().strip()

    def test_flujo_reservar_listar_cancelar(self) -> None:
        db, _ = self._ruta()
        codigo, salida = self._salida(
            "--db", str(db), "reservar", "--unidad", MIC,
            "--solicitante", SOLICITANTE_A, "--desde", DIA_10_00, "--hasta", DIA_11_00,
        )
        self.assertEqual(codigo, 0)
        self.assertIn("id=1", salida)
        codigo, salida = self._salida("--db", str(db), "listar")
        self.assertEqual(codigo, 0)
        self.assertIn("[ACTIVA]", salida)

    def test_rechazo_superposicion_sale_con_1(self) -> None:
        db, _ = self._ruta()
        self._salida(
            "--db", str(db), "reservar", "--unidad", MIC,
            "--solicitante", SOLICITANTE_A, "--desde", DIA_10_00, "--hasta", DIA_11_00,
        )
        codigo, salida = self._salida(
            "--db", str(db), "reservar", "--unidad", MIC,
            "--solicitante", SOLICITANTE_B, "--desde", DIA_10_30, "--hasta", DIA_11_30,
        )
        self.assertEqual(codigo, 1)
        self.assertTrue(salida.startswith("ERROR:"))

    def test_disponibilidad_libre_y_ocupada(self) -> None:
        db, _ = self._ruta()
        self._salida(
            "--db", str(db), "reservar", "--unidad", MIC,
            "--solicitante", SOLICITANTE_A, "--desde", DIA_10_00, "--hasta", DIA_11_00,
        )
        codigo, _ = self._salida(
            "--db", str(db), "disponibilidad", "--unidad", MIC,
            "--desde", DIA_10_30, "--hasta", DIA_11_30,
        )
        self.assertEqual(codigo, 1)  # ocupada
        codigo, _ = self._salida(
            "--db", str(db), "disponibilidad", "--unidad", "MIC-02",
            "--desde", DIA_10_30, "--hasta", DIA_11_30,
        )
        self.assertEqual(codigo, 0)  # libre

    def test_cancelar_libera_para_reservar(self) -> None:
        db, _ = self._ruta()
        self._salida(
            "--db", str(db), "reservar", "--unidad", MIC,
            "--solicitante", SOLICITANTE_A, "--desde", DIA_10_00, "--hasta", DIA_11_00,
        )
        self._salida("--db", str(db), "cancelar", "--id", "1")
        codigo, salida = self._salida(
            "--db", str(db), "reservar", "--unidad", MIC,
            "--solicitante", SOLICITANTE_B, "--desde", DIA_10_00, "--hasta", DIA_11_00,
        )
        self.assertEqual(codigo, 0)

    def test_reset_deja_historial_vacio(self) -> None:
        db, _ = self._ruta()
        self._salida(
            "--db", str(db), "reservar", "--unidad", MIC,
            "--solicitante", SOLICITANTE_A, "--desde", DIA_10_00, "--hasta", DIA_11_00,
        )
        codigo, _ = self._salida("--db", str(db), "reset")
        self.assertEqual(codigo, 0)
        codigo, salida = self._salida("--db", str(db), "listar")
        self.assertEqual(codigo, 0)
        self.assertEqual(salida, "(sin reservas registradas)")

    def test_ruta_db_por_defecto_vive_en_proyecto(self) -> None:
        from reservas import RUTA_DB

        self.assertEqual(RUTA_DB.name, "reservas.db")


if __name__ == "__main__":
    unittest.main()
