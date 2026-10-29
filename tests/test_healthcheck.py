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


def test_cancel_active_steps_mata_el_subproceso_y_bloquea_pasos_nuevos(tmp_path, monkeypatch):
    """Item 54: el timeout del job semanal debe terminar de verdad los subprocesos."""
    import threading
    import time
    import pipeline
    (tmp_path / "lento.py").write_text("import time\nprint('inicio', flush=True)\ntime.sleep(60)\n")
    (tmp_path / "otro.py").write_text("print('no debería ejecutarse')\n")
    monkeypatch.setattr(pipeline, "SCRIPTS_DIR", tmp_path)
    pipeline.reset_cancel()
    res = {}
    t = threading.Thread(target=lambda: res.update(pipeline.run_step("lento.py", [], on_output=lambda l: None)))
    t0 = time.monotonic(); t.start()
    time.sleep(1.5)
    assert pipeline.cancel_active_steps(grace=5) == 1
    t.join(timeout=15)
    assert not t.is_alive() and time.monotonic() - t0 < 30
    assert res["returncode"] != 0
    # tras cancelar no se lanzan pasos nuevos
    nuevo = pipeline.run_step("otro.py", [])
    assert nuevo.get("cancelled") is True
    pipeline.reset_cancel()


def test_run_step_watchdog_mata_un_hijo_sin_salida(tmp_path, monkeypatch):
    """Item 56b: un subproceso colgado (sin imprimir nada) no puede bloquear el pipeline."""
    import time
    import pipeline
    (tmp_path / "colgado.py").write_text("print('hola', flush=True)\nimport time\ntime.sleep(120)\n")
    (tmp_path / "normal.py").write_text("print('ok')\n")
    monkeypatch.setattr(pipeline, "SCRIPTS_DIR", tmp_path)
    pipeline.reset_cancel()
    t0 = time.monotonic()
    res = pipeline.run_step("colgado.py", [], on_output=lambda l: None, idle_timeout=2)
    assert time.monotonic() - t0 < 30
    assert res.get("timed_out") is True and res["returncode"] != 0
    assert any("watchdog" in l for l in res["output"])
    ok = pipeline.run_step("normal.py", [], on_output=lambda l: None, idle_timeout=2)
    assert ok["returncode"] == 0 and not ok.get("timed_out")


def test_setup_pipeline_log_no_acumula_handlers(tmp_path, monkeypatch):
    """Item 56a: llamar N veces a _setup_pipeline_log no deja N FileHandlers."""
    import pipeline
    monkeypatch.setattr(pipeline, "SCRIPTS_DIR", tmp_path / "scripts")
    before = len(pipeline.log.handlers)
    for _ in range(5):
        pipeline._setup_pipeline_log("test_flujo")
    assert len(pipeline.log.handlers) == before + 1
    pipeline._PIPELINE_FILE_HANDLERS.pop("test_flujo").close()
    pipeline.log.handlers = pipeline.log.handlers[:before]


def test_run_books_encadena_process_y_embed(monkeypatch):
    import pipeline
    calls = []
    monkeypatch.setattr(pipeline, "check_nas", lambda: None)
    monkeypatch.setattr(pipeline, "run_step",
                        lambda script, args, **kw: calls.append((script, args)) or {"returncode": 0, "output": []})
    res = pipeline.run_books("mi_coleccion", pdf_dir="/tmp/pdfs")
    assert res["status"] == "ok" and [c[0] for c in calls] == ["books/process.py", "books/embed.py"]
    assert "--input-dir" in calls[0][1] and calls[1][1][:2] == ["--collection", "mi_coleccion"]
    calls.clear()
    monkeypatch.setattr(pipeline, "run_step",
                        lambda script, args, **kw: calls.append(script) or {"returncode": 1, "output": []})
    assert pipeline.run_books("x")["status"] == "error" and calls == ["books/process.py"]
