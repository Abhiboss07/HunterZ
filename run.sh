#!/bin/sh
# Launcher script for HunterZ
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/.venv/bin/python" -m hunterz.cli "$@"
