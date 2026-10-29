#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backup_config.py — instantáneas versionadas de la configuración y de los datos pequeños
irremplazables (item 27).

Copia a `/Volumes/research/metadatos/backups_config/<AAAAMMDD_HHMMSS>/` (misma estructura relativa):
  · config/*.yml y config/*.example         (keywords, scopus_queries, active_categories, plantillas)
  · metadatos/{doi_manual.xlsx, doi_registry.txt, pendientes_descarga.csv, validation_overrides.csv}
  · categorias/*/metadata/papers_metadata.jsonl   (el registro bibliográfico; ≈3 MB en total)
con un MANIFEST.json (sha256, tamaño). No crea instantánea si nada cambió respecto a la última, y
conserva solo las últimas `--keep` (12 por defecto).

El `config/.env` (todas las claves) NO se copia salvo con `--encrypt-env`, que lo cifra con
`openssl enc -aes-256-cbc -pbkdf2` pidiendo la passphrase por terminal (guárdala en un gestor
externo). Solo para uso interactivo: nunca lo lanza un job.
    Descifrar: openssl enc -d -aes-256-cbc -pbkdf2 -in env.enc -out .env

Uso:
    python3 scripts/backup_config.py              # instantánea (si hay cambios)
    python3 scripts/backup_config.py --list       # lista las instantáneas
    python3 scripts/backup_config.py --encrypt-env
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESEARCH = Path("/Volumes/research")
DEST_ROOT = RESEARCH / "metadatos" / "backups_config"
META_FILES = ["doi_manual.xlsx", "doi_registry.txt", "pendientes_descarga.csv", "validation_overrides.csv"]


def collect_sources(repo: Path = REPO, research: Path = RESEARCH) -> dict:
    """{ruta relativa en la instantánea: ruta origen} de lo que existe."""
    out = {}
    cfg = repo / "config"
    if cfg.is_dir():
        for p in sorted(list(cfg.glob("*.yml")) + list(cfg.glob("*.example"))):
            out[f"config/{p.name}"] = p
    for name in META_FILES:
        p = research / "metadatos" / name
        if p.is_file():
            out[f"metadatos/{name}"] = p
    cats = research / "categorias"
    if cats.is_dir():
        for p in sorted(cats.glob("*/metadata/papers_metadata.jsonl")):
            out[f"categorias/{p.parent.parent.name}/metadata/papers_metadata.jsonl"] = p
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def list_snapshots(dest_root: Path = DEST_ROOT) -> list:
    if not dest_root.is_dir():
        return []
    return sorted((d for d in dest_root.iterdir() if d.is_dir() and (d / "MANIFEST.json").exists()),
                  key=lambda d: d.name)


def snapshot(sources: dict | None = None, dest_root: Path = DEST_ROOT, keep: int = 12,
             now: datetime | None = None) -> Path | None:
    """Crea una instantánea si algo cambió desde la última. Devuelve su ruta o None."""
    sources = collect_sources() if sources is None else sources
    if not sources:
        return None
    hashes = {rel: sha256(p) for rel, p in sources.items()}
    snaps = list_snapshots(dest_root)
    if snaps:
        try:
            last = json.loads((snaps[-1] / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
            if {k: v["sha256"] for k, v in last.items()} == hashes:
                return None
        except Exception:
            pass
    ts = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    dest = dest_root / ts
    manifest = {"created": ts, "files": {}}
    for rel, src in sources.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        manifest["files"][rel] = {"sha256": hashes[rel], "bytes": target.stat().st_size}
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    for old in list_snapshots(dest_root)[:-keep] if keep > 0 else []:
        shutil.rmtree(old, ignore_errors=True)
    return dest


def encrypt_env(dest_root: Path = DEST_ROOT, repo: Path = REPO) -> Path:
    """Cifra config/.env con passphrase interactiva (openssl). Devuelve el fichero cifrado."""
    env = repo / "config" / ".env"
    if not env.is_file():
        raise SystemExit(f"No existe {env}")
    dest_root.mkdir(parents=True, exist_ok=True)
    out = dest_root / f"env_{datetime.now():%Y%m%d}.enc"
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "600000", "-salt",
                        "-in", str(env), "-out", str(out)])
    if r.returncode != 0:
        out.unlink(missing_ok=True)
        raise SystemExit("openssl falló (¿passphrase vacía o no coincide?)")
    out.chmod(0o600)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Instantáneas versionadas de la configuración (item 27)")
    ap.add_argument("--list", action="store_true", help="lista las instantáneas existentes")
    ap.add_argument("--keep", type=int, default=12, help="instantáneas a conservar (defecto 12)")
    ap.add_argument("--encrypt-env", action="store_true", help="cifra config/.env (pide passphrase)")
    args = ap.parse_args()
    if not RESEARCH.exists():
        print("NAS no montado: /Volumes/research")
        return 1
    if args.list:
        for d in list_snapshots():
            m = json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))
            print(f"{d.name}  {len(m['files'])} ficheros  {sum(v['bytes'] for v in m['files'].values()) / 1e6:.1f} MB")
        return 0
    if args.encrypt_env:
        print(f"Cifrado en {encrypt_env()} — guarda la passphrase en un gestor externo.")
        return 0
    d = snapshot(keep=args.keep)
    print(f"Instantánea creada: {d}" if d else "Sin cambios desde la última instantánea.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
