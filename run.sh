#!/bin/sh
# uv があれば使い、なければ .venv に PyMuPDF を入れて nencho.py を実行する
set -e
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project --python '>=3.11' --with pymupdf python nencho.py "$@"
fi
PY=""
for p in python3.13 python3.12 python3.11 python3; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    PY="$p"; break
  fi
done
if [ -z "$PY" ]; then
  echo "エラー: Python 3.11 以上が見つかりません。https://www.python.org/downloads/ からインストールするか、uv を入れてください。" >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "初回セットアップ中（.venv を作成して PyMuPDF をインストールします）..."
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet pymupdf
fi
exec .venv/bin/python nencho.py "$@"
