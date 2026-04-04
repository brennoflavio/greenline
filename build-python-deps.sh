set -euo pipefail

cd "$INSTALL_DIR"

VENV_PATH="$BUILD_DIR/venv"
export UV_PROJECT_ENVIRONMENT="$VENV_PATH"

/usr/local/uv sync

PYTHON_DIR=$(ls "$VENV_PATH/lib/")
cp -r "$VENV_PATH/lib/$PYTHON_DIR/site-packages/"* .
