# -*- coding: utf-8 -*-
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "healthcheck_t", Path(__file__).resolve().parents[1] / "scripts" / "healthcheck.py")
hc = importlib.util.module_from_spec(_spec); sys.modules["healthcheck_t"] = hc
_spec.loader.exec_module(hc)


def _ok(url, timeout=8):
    if "11434" in url:
        return 401, ""
    if "11435" in url:
        return 200, '{"version":"0.30.7"}'
    if "8070" in url:
        return 200, "true"
    return 200, "ok"


def test_todo_bien(tmp_path):
    assert hc.run_checks(_ok, tmp_path) == []


def test_detecta_servicio_caido_y_datos_desmontados(tmp_path):
    def f(url, timeout=8):
        return (0, "") if "8501" in url else _ok(url)
    fails = hc.run_checks(f, tmp_path / "no_existe")
    assert any("8501" in x and "sin conexión" in x for x in fails)
    assert any("no está montado" in x for x in fails)


def test_caddy_sin_401_es_fallo(tmp_path):
    def f(url, timeout=8):
        return (200, "") if "11434" in url else _ok(url)
    assert any("Caddy" in x for x in hc.run_checks(f, tmp_path))
