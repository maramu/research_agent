# -*- coding: utf-8 -*-
"""Tests de utils.crossref._pick_year (mensajes Crossref sintéticos, offline).

Política de año canónico: published-print → published-online → issued →
published. `issued` es el mínimo de fechas Crossref (online temprano) y
published-online puede ser digitalización tardía (caso Wise), por eso print
va primero.
"""
from utils.crossref import _pick_year


def _msg(**dates):
    """{'published-print': 1990, ...} → mensaje Crossref sintético."""
    return {key.replace("_", "-"): {"date-parts": [[year]]}
            for key, year in dates.items() if year is not None}


def test_pick_year_print_normal():
    """print=1990, online ausente, issued=1990 → 1990."""
    assert _pick_year(_msg(published_print=1990, issued=1990)) == 1990


def test_pick_year_wise_digitalizacion_tardia():
    """El raro Wise: print=1978, online=2004, issued=1978 → 1978 (NO online)."""
    msg = _msg(published_print=1978, published_online=2004, issued=1978)
    assert _pick_year(msg) == 1978


def test_pick_year_cae_a_online():
    """Sin print: online=2020, issued=2019 → 2020 (online antes que issued)."""
    assert _pick_year(_msg(published_online=2020, issued=2019)) == 2020


def test_pick_year_solo_issued():
    assert _pick_year(_msg(issued=2015)) == 2015


def test_pick_year_cae_a_published():
    """Solo la clave genérica `published` → la usa como último recurso."""
    assert _pick_year(_msg(published=2018)) == 2018


def test_pick_year_sin_fechas():
    assert _pick_year({}) is None
    assert _pick_year({"published-print": {"date-parts": [[None]]}}) is None
