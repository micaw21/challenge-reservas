"""Pruebas de reservas de laboratorio.

Ejecutar: python -m unittest discover -s tests -v
Sin dependencias externas; cada prueba usa su propia base SQLite temporal,
de modo que ninguna prueba contamina los datos de otra.
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import reservas
from reservas import Laboratorio, Rechazo, _menu_interactivo, main

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


class TestMenuInteractivo(unittest.TestCase):
    """Bucle del menú: navegación, validación de opciones y salidas."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ruta_db = str(Path(tmp.name) / "menu.db")

    def _correr(self, respuestas: list[str]) -> int:
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        return codigo

    def test_salir_con_0_negativo_y_salir(self) -> None:
        for respuestas in (["0"], ["-1"], ["/salir"], ["-3"]):
            with self.subTest(respuestas=respuestas):
                self.assertEqual(self._correr(respuestas), 0)

    def test_opciones_fuera_de_navegacion_rechazadas(self) -> None:
        for respuestas in (["zzz", "", "0"], ["abc", "", "-2"], ["7", "", "/salir"]):
            with self.subTest(respuestas=respuestas):
                self.assertEqual(self._correr(respuestas), 0)

    def test_menu_muestra_opciones_numeradas(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=["0"]):
            _menu_interactivo(self.ruta_db)
        salida = buffer.getvalue()
        self.assertIn("1) Ver inventario", salida)
        self.assertIn("6) Reiniciar los datos", salida)
        self.assertIn("0) Salir", salida)
        # Menú friendly: sin datos técnicos ni anuncios del uso por consola.
        self.assertNotIn("Datos persistentes", salida)
        self.assertNotIn("Uso directo", salida)

    def test_opcion_invalida_muestra_mensaje_y_repite_menu(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=["zzz", "", "0"]):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        self.assertIn("Opción no válida: 'zzz'. Ingrese de nuevo.", salida)
        # El menú se vuelve a mostrar tras el mensaje.
        self.assertEqual(salida.count("RESERVAS DE EQUIPOS DE LABORATORIO"), 2)

    def test_reservar_y_listar_desde_menu(self) -> None:
        respuestas = [
            "4",
            MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00,
            "",        # pausa tras crear
            "2",       # listar: filtro vacío
            "", "",    # pausa tras listar, vuelve al menú
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        self.assertIn("Reserva creada con id=1", salida)
        self.assertIn(f"[ACTIVA] {MIC}", salida)
        # La ayuda de unidades aparece al reservar y al pedir el filtro de listar.
        self.assertGreaterEqual(salida.count("Unidades disponibles:"), 2)
        # La reserva quedó persistida en la base de ese menú.
        lab = Laboratorio(self.ruta_db)
        try:
            self.assertEqual(len(lab.reservas()), 1)
        finally:
            lab.cerrar()

    def test_listar_muestra_unidades_como_ayuda(self) -> None:
        respuestas = ["2", MIC, "", "0"]  # listar con filtro MIC-01
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        # La ayuda aparece después del encabezado de listar y antes de los datos.
        self.assertGreater(salida.index("Unidades disponibles:"), salida.index("--- LISTAR RESERVAS ---"))
        for texto in ("FUE-01", "MIC-01", "MIC-02", "MUL-01", "OSC-01", "Osciloscopio", "Multímetro"):
            self.assertIn(texto, salida)

    def test_prompts_instructivos(self) -> None:
        """Los pedidos de datos dicen qué ingresar y con qué ejemplo."""
        respuestas = [
            "3", MIC, "03-11-2026", "10:00", "11:00", "",  # disponibilidad por partes
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            _menu_interactivo(self.ruta_db)
        salida = buffer.getvalue()
        self.assertIn("Ingrese el ID de la unidad a consultar (ej.: MIC-01)", salida)
        self.assertIn("Ingrese la fecha a consultar (DD-MM-YYYY)", salida)
        self.assertIn("Ingrese la hora de inicio (HH:MM)", salida)
        self.assertIn("Ingrese la hora de fin (HH:MM)", salida)
        # La fecha y las horas se componen en el intervalo consultado.
        self.assertIn("LIBRE: MIC-01 03-11-2026 10:00 -> 03-11-2026 11:00", salida)

    def test_todas_las_salidas_usan_dd_mm_yyyy(self) -> None:
        """Listar y los mensajes muestran fechas en formato DD-MM-YYYY HH:MM."""
        respuestas = [
            "4", MIC, SOLICITANTE_A, "03-11-2026 10:00", "03-11-2026 11:00", "",  # crear
            "2", "", "",  # listar todas
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        # La reserva se creó con entrada DD-MM-YYYY...
        self.assertIn("Reserva creada con id=1", salida)
        # ... y el historial muestra la fecha en formato DD-MM-YYYY.
        self.assertIn(f"[ACTIVA] {MIC} 03-11-2026 10:00 -> 03-11-2026 11:00 '{SOLICITANTE_A}'", salida)
        self.assertNotIn("2026-11-03", salida)

    def test_listar_valida_unidad_antes_de_mostrar_datos(self) -> None:
        """Un filtro de unidad inválido se avisa y se vuelve a pedir."""
        respuestas = [
            "2",    # listar
            "s",    # filtro inválido (como en el reporte real)
            MIC,    # filtro válido recién entonces
            "",     # repetir-pregunta: volver al menú
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        self.assertIn("ERROR: unidad desconocida: 's'", salida)
        self.assertLess(
            salida.index("unidad desconocida: 's'"),
            salida.index("(sin reservas registradas)"),
        )
        self.assertEqual(salida.count("Ingrese un ID de unidad para filtrar"), 2)

    def test_reservar_valida_unidad_antes_de_pedir_solicitante(self) -> None:
        """La unidad a reservar se valida al pedirla, antes del solicitante."""
        respuestas = [
            "4",             # reservar
            "s",             # unidad inválida
            MIC,             # unidad válida recién entonces
            SOLICITANTE_A, "03-11-2026 10:00", "03-11-2026 11:00",
            "",              # repetir-pregunta: volver al menú
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        self.assertIn("ERROR: unidad desconocida: 's'", salida)
        self.assertLess(
            salida.index("unidad desconocida: 's'"),
            salida.index("Ingrese el solicitante"),
        )
        self.assertIn("Reserva creada con id=1", salida)

    def test_reservar_valida_campo_por_campo(self) -> None:
        """Solicitante vacío, fecha inválida y orden invertido se re-piden en el campo."""
        respuestas = [
            "4",                       # reservar
            MIC,                       # unidad válida
            "   ",                     # solicitante vacío -> re-pide (V-2)
            SOLICITANTE_A,             # solicitante válido
            "ayer",                    # fecha de inicio inválida -> re-pide
            "03-11-2026 10:00",        # inicio válido
            "03-11-2026 09:00",        # orden invertido -> re-piden fechas
            "03-11-2026 10:00", "03-11-2026 11:00",  # intervalo correcto
            "",                        # repetir-pregunta: volver al menú
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        self.assertIn("ERROR: solicitante vacío: la reserva necesita un solicitante", salida)
        self.assertIn("ERROR: fecha y hora inválidas: 'ayer' (se espera 'DD-MM-YYYY HH:MM')", salida)
        self.assertIn("ERROR: intervalo inválido: inicio '03-11-2026 10:00' debe ser", salida)
        # La unidad y el solicitante nunca se volvieron a pedir tras validar.
        self.assertEqual(salida.count("Ingrese el ID de la unidad a reservar"), 1)
        self.assertIn("Reserva creada con id=1", salida)

    def test_reservar_muestra_reservas_activas_del_equipo(self) -> None:
        """Antes de pedir horario muestra qué reservas activas tiene la unidad."""
        lab = Laboratorio(self.ruta_db)
        lab.reservar(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        lab.cerrar()
        respuestas = [
            "4", MIC,
            SOLICITANTE_B,
            "03-11-2026 12:00", "03-11-2026 13:00",  # horario libre
            "", "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        # La ayuda sale ANTES de pedir el solicitante/horario.
        self.assertGreater(salida.index("Ingrese el solicitante"), salida.index("Reservas activas de MIC-01"))
        self.assertIn(f"03-11-2026 10:00 -> 03-11-2026 11:00 '{SOLICITANTE_A}'", salida)
        self.assertIn("(ej.: MIC-01)", salida)

    def test_reservar_avisa_equipo_libre_en_cualquier_horario(self) -> None:
        """Una unidad sin reservas activas lo dice antes de pedir el horario."""
        respuestas = [
            "4", "MUL-01",
            SOLICITANTE_B,
            "03-11-2026 12:00", "03-11-2026 13:00",
            "", "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            _menu_interactivo(self.ruta_db)
        salida = buffer.getvalue()
        self.assertIn(
            "Reservas activas de MUL-01: ninguna (libre en cualquier horario).", salida
        )

    def test_reservar_avisa_solapamiento_apenas_se_completa_intervalo(self) -> None:
        """El choque (V-6) sale al toque: solo las fechas se vuelven a pedir."""
        lab = Laboratorio(self.ruta_db)
        lab.reservar(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        lab.cerrar()
        respuestas = [
            "4", MIC,
            "Solicitante B", "03-11-2026 10:30", "03-11-2026 11:15",  # choca
            "03-11-2026 12:00", "03-11-2026 13:00",  # solo fechas se re-piden
            "", "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        self.assertIn(
            "ERROR: unidad MIC-01 ya reservada por 'Solicitante A'"
            " de 03-11-2026 10:00 a 03-11-2026 11:00 (reserva id=1, activa)", salida
        )
        self.assertIn("Reserva creada con id=2", salida)
        # La unidad y el solicitante no se tipearon otra vez.
        self.assertEqual(salida.count("Ingrese el ID de la unidad a reservar"), 1)
        self.assertEqual(salida.count("Ingrese el solicitante"), 1)

    def test_cancelar_vuelve_a_pedir_id_con_dato_malo(self) -> None:
        """El id se valida al momento: no numérico o inexistente se re-piden."""
        lab = Laboratorio(self.ruta_db)
        lab.reservar(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        lab.cerrar()
        respuestas = [
            "5",      # cancelar
            "abc",    # no numérico
            "999",    # inexistente
            "1",      # válido
            "",       # repetir-pregunta: volver al menú
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        self.assertIn("ERROR: el id debe ser un número entero (sin signo).", salida)
        self.assertIn("ERROR: reserva inexistente: no hay reserva con id=999", salida)
        self.assertIn("Reserva id=1 cancelada", salida)
        self.assertIn(
            "(ej.: 1, Enter = volver al menú)", salida
        )

    def test_disponibilidad_valida_unidad_antes_de_pedir_fecha(self) -> None:
        """Un ID de unidad inválido se avisa y se vuelve a pedir ANTES de la fecha."""
        respuestas = [
            "3",           # opción disponibilidad
            "s",           # unidad inválida (como en el reporte real)
            "XXX-99",      # unidad inválida otra vez
            MIC,           # unidad válida recién entonces
            "03-11-2026", "10:00", "11:00",
            "",            # volver al menú
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        # Se avisa la unidad desconocida y se re-pide antes de pedir la fecha.
        self.assertIn("ERROR: unidad desconocida: 's'", salida)
        self.assertLess(
            salida.index("unidad desconocida: 's'"),
            salida.index("Ingrese la fecha a consultar (DD-MM-YYYY)"),
        )
        # La fecha nunca se pidió con la unidad inválida todavía en pie.
        self.assertIn("LIBRE: MIC-01 03-11-2026 10:00 -> 03-11-2026 11:00", salida)

    def test_disponibilidad_rechaza_hora_invalida(self) -> None:
        """La parte de hora inválida se avisa al pedirse y se re-pide el campo."""
        respuestas = [
            "3", MIC, "03-11-2026", "25:00",  # unidad y fecha bien, hora mal
            "10:00", "11:00",  # solo la hora se vuelve a pedir
            "",   # volver al menú tras el resultado
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        self.assertIn("ERROR: hora inválida: '25:00' (se espera 'HH:MM')", salida)
        self.assertIn("LIBRE: MIC-01 03-11-2026 10:00 -> 03-11-2026 11:00", salida)

    def test_disponibilidad_rechaza_fecha_invalida_y_dd_mm_ambiguo(self) -> None:
        """Una fecha fuera de DD-MM-YYYY e ISO se rechaza con el formato canónico."""
        respuestas = [
            "3", MIC, "ayer",  # fecha inválida
            "03-11-2026", "10:00", "11:00",  # solo la fecha se vuelve a pedir
            "",   # volver al menú tras el resultado
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        salida = buffer.getvalue()
        self.assertIn("ERROR: fecha inválida: 'ayer' (se espera 'DD-MM-YYYY')", salida)
        self.assertIn("LIBRE: MIC-01 03-11-2026 10:00 -> 03-11-2026 11:00", salida)

    def test_disponibilidad_repide_horas_si_el_orden_esta_invertido(self) -> None:
        """Con fin antes del inicio, el error sale al toque y solo se re-piden horas."""
        respuestas = [
            "3", MIC, "03-11-2026", "12:00", "10:00",  # orden invertido
            "10:00", "12:30",  # horas re-pedidas en orden correcto
            "",   # volver al menú
            "0",
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        salida = buffer.getvalue()
        self.assertIn("ERROR: intervalo inválido: inicio '03-11-2026 12:00'", salida)
        self.assertIn("LIBRE: MIC-01 03-11-2026 10:00 -> 03-11-2026 12:30", salida)

    def test_repetir_consulta_en_la_misma_opcion(self) -> None:
        """Tras el resultado, 's' repite la opción y Enter vuelve al menú."""
        respuestas = [
            "2",    # listar, filtro vacío (todas)
            "",     # sin datos: filtro vacío
            "s",    # repetir la consulta en la misma opción
            "",     # segunda pasada, filtro vacío
            "",     # volver al menú
            "0",    # salir
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        salida = buffer.getvalue()
        # La opción se ejecutó dos veces dentro del mismo bucle.
        self.assertEqual(salida.count("--- LISTAR RESERVAS ---"), 2)
        self.assertIn(
            "(s = sí, repetir aquí / Enter = volver al menú)", salida
        )

    def test_reset_desde_menu_reinicia(self) -> None:
        lab = Laboratorio(self.ruta_db)
        lab.reservar(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        lab.cerrar()
        respuestas = ["6", "s", "", "2", "", "", "0"]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        self.assertIn("Datos reiniciados", buffer.getvalue())

    def test_reset_cancelado_no_modifica(self) -> None:
        lab = Laboratorio(self.ruta_db)
        lab.reservar(MIC, SOLICITANTE_A, DIA_10_00, DIA_11_00)
        lab.cerrar()
        respuestas = ["6", "n", "", "0"]
        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("reservas.input", side_effect=respuestas):
            codigo = _menu_interactivo(self.ruta_db)
        self.assertEqual(codigo, 0)
        lab = Laboratorio(self.ruta_db)
        try:
            self.assertEqual(len(lab.reservas()), 1)
        finally:
            lab.cerrar()


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
