set -euo pipefail

cd "$INSTALL_DIR"

VENV_PATH="$BUILD_DIR/venv"
export UV_PROJECT_ENVIRONMENT="$VENV_PATH"

UV_BIN="${UV_INSTALL_DIR:-/usr/local}/uv"
if [ ! -x "$UV_BIN" ]; then
    UV_BIN="$(command -v uv)"
fi

"$UV_BIN" sync

PYTHON_DIR=$(ls "$VENV_PATH/lib/")
cp -r "$VENV_PATH/lib/$PYTHON_DIR/site-packages/"* .
