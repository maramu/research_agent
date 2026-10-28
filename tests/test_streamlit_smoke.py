# -*- coding: utf-8 -*-
"""Prueba de humo de las páginas de Streamlit (item 80).

Ejecuta cada página con `streamlit.testing.v1.AppTest` en un SUBPROCESO propio
(algunas páginas llaman a st.stop/sys.exit) y comprueba que renderiza sin
excepciones. La autenticación se salta rellenando `auth_PRIVATE_APP_PASSWORD` en
`session_state`, sin tocar código de producción. Las páginas solo LEEN: nadie
pulsa botones. Se necesita el corpus real (`/Volumes/research`); sin él se omite.
"""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PAGES = sorted((SCRIPTS / "streamlit_app" / "pages").glob("*.py"))
NAS = Path("/Volumes/research/categorias")

_RUNNER = """
import sys, os
sys.path.insert(0, '.'); sys.path.insert(0, 'streamlit_app')
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(sys.argv[1], default_timeout=180)
at.session_state['auth_PRIVATE_APP_PASSWORD'] = True
at.run()
exc = [e.value[:300] for e in at.exception]
print('SMOKE_EXC', exc)
sys.exit(1 if exc else 0)
"""


@pytest.mark.skipif(not NAS.exists(), reason="requiere el corpus real en /Volumes/research")
@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pagina_renderiza_sin_excepciones(page):
    pytest.importorskip("streamlit.testing.v1")
    r = subprocess.run([sys.executable, "-I", "-c", _RUNNER, str(page.relative_to(SCRIPTS))],
                       cwd=SCRIPTS, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"{page.name}: {r.stdout[-600:]} {r.stderr[-400:]}"
