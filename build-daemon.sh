
set -euo pipefail

SRC_FOLDER="wuzapi"
BINARY_FOLDER="dist"
BINARY_NAME="wuzapi-daemon"
GO_CACHE_FOLDER="go"

mkdir -p "$INSTALL_DIR/$SRC_FOLDER/$BINARY_FOLDER"
mkdir -p "$BUILD_DIR/$GO_CACHE_FOLDER"

export GOPATH="$BUILD_DIR/$GO_CACHE_FOLDER"
export CGO_ENABLED=1
export GOOS=linux
export GOARCH="$ARCH"
if [ "$ARCH" = "arm64" ]; then
    export CC=aarch64-linux-gnu-gcc
    export QEMU_LD_PREFIX=/usr/aarch64-linux-gnu
fi

cd "$INSTALL_DIR/$SRC_FOLDER"

go build -o "$INSTALL_DIR/$SRC_FOLDER/$BINARY_FOLDER/$BINARY_NAME" .
chmod +x "$INSTALL_DIR/$SRC_FOLDER/$BINARY_FOLDER/$BINARY_NAME"

cp "$INSTALL_DIR/$SRC_FOLDER/$BINARY_FOLDER/$BINARY_NAME" "$INSTALL_DIR/$BINARY_NAME"

rm -r "$INSTALL_DIR/$SRC_FOLDER"
