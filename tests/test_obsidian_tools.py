# -*- coding: utf-8 -*-
"""Tests de _validar_ruta_escritura (tools/obsidian.py) — única garantía a
nivel de código de que las tools de escritura no pueden salir de 00_Inbox/."""

import pytest

from tools.obsidian import (
    VAULT_WRITE_ROOT,
    _sanitizar_nombre,
    _validar_ruta_escritura,
    anexar_a_nota_inbox,
    crear_nota_inbox,
)


class TestValidarRutaEscrituraValida:
    @pytest.mark.parametrize(
        "ruta,esperado",
        [
            ("00_Inbox/nota.md", "00_Inbox/nota.md"),
            ("00_Inbox/sub/x.md", "00_Inbox/sub/x.md"),
            ("  00_Inbox/con_espacios.md  ", "00_Inbox/con_espacios.md"),
        ],
    )
    def test_rutas_validas(self, ruta, esperado):
        assert _validar_ruta_escritura(ruta) == esperado


class TestValidarRutaEscrituraRechazada:
    @pytest.mark.parametrize(
        "ruta",
        [
            "../20_Trabajo/x.md",
            "/etc/passwd",
            "00_Inbox/../20_Trabajo/x.md",
            "20_Trabajo/x.md",
            "00_Inbox/x.txt",
            "",
            "   ",
            "00_Inbox",
            "00_Inbox/",
            "00_Inbox_evil/x.md",
            "00_InboxOtra/x.md",
            "../../etc/passwd",
        ],
    )
    def test_rutas_rechazadas(self, ruta):
        with pytest.raises(PermissionError):
            _validar_ruta_escritura(ruta)

    def test_mensaje_incluye_write_root(self):
        with pytest.raises(PermissionError, match=VAULT_WRITE_ROOT.replace("/", r"\/")):
            _validar_ruta_escritura("20_Trabajo/x.md")


class TestSanitizarNombre:
    @pytest.mark.parametrize(
        "nombre,esperado",
        [
            ("prueba-agente", "prueba-agente"),
            ("con espacios", "con_espacios"),
            ("con/barras", "con_barras"),
            ("con:dos|puntos?*", "con_dos_puntos"),
            ("  espacios_extra  ", "espacios_extra"),
        ],
    )
    def test_sanitiza(self, nombre, esperado):
        assert _sanitizar_nombre(nombre) == esperado


class TestToolsEscrituraAdversarial:
    """crear_nota_inbox y anexar_a_nota_inbox deben lanzar PermissionError
    ANTES de hacer ninguna llamada de red — así el test es válido tanto con
    Obsidian abierto como cerrado."""

    def test_crear_nota_inbox_con_ruta_en_nombre(self):
        with pytest.raises(PermissionError):
            crear_nota_inbox("../20_Trabajo/hack", "contenido")

    def test_crear_nota_inbox_con_barra(self):
        with pytest.raises(PermissionError):
            crear_nota_inbox("sub/hack", "contenido")

    def test_anexar_a_nota_inbox_fuera_de_inbox(self):
        with pytest.raises(PermissionError):
            anexar_a_nota_inbox("20_Trabajo/x.md", "contenido")
