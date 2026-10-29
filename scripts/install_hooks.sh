#!/usr/bin/env bash
# Activa los hooks versionados de .githooks/ en este clon (item 39).
set -e
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
echo "Hooks activados: core.hooksPath = $(git config core.hooksPath)"
