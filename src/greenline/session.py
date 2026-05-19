"""Shared session and QR-code helpers."""

import base64
import os
from dataclasses import dataclass

from ut_components.config import get_cache_path

QR_IMAGE_PATH = os.path.join(get_cache_path(), "qr.png")


@dataclass
class SessionStatusResponse:
    logged_in: bool
    qr_image_path: str


def write_qr_image(qr_image_base64: str) -> str:
    if not qr_image_base64:
        return ""

    os.makedirs(os.path.dirname(QR_IMAGE_PATH), exist_ok=True)
    with open(QR_IMAGE_PATH, "wb") as file_handle:
        file_handle.write(base64.b64decode(qr_image_base64))
    return "file://" + QR_IMAGE_PATH


def build_session_status_response(logged_in: bool, qr_image_base64: str) -> SessionStatusResponse:
    qr_image_path = ""
    if not logged_in and qr_image_base64:
        qr_image_path = write_qr_image(qr_image_base64)
    return SessionStatusResponse(logged_in=logged_in, qr_image_path=qr_image_path)
