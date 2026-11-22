#!/bin/bash
# dist/myds.app をビルドする
set -euo pipefail

cd "$(dirname "$0")/.."

# ビルド専用の仮想環境（開発用 .venv とは分ける。成果物はどちらにも依存しない）
VENV=.build-venv
PYTHON=${PYTHON:-python3}

if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r requirements.txt -r requirements-build.txt

rm -rf build dist/myds dist/myds.app
"$VENV/bin/pyinstaller" --clean --noconfirm myds.spec

# PyInstallerの一時ディレクトリを削除し、.app だけを残す
rm -rf dist/myds

# 証明書名を指定した場合は署名し直す（再ビルド後もカメラ許可が維持される）
if [ -n "${MYDS_SIGN_IDENTITY:-}" ]; then
  codesign --force --deep --sign "$MYDS_SIGN_IDENTITY" dist/myds.app
fi

echo "ビルド完了: $(pwd)/dist/myds.app"
