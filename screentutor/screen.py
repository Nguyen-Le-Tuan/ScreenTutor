"""Screenshots for the tutor: grab the screen (Windows), encode it, and mark a point for checking by eye.

The image is sent as full-size PNG, the same encoding the grounding test
measured (grounding_test.datasets.prepare_image without resize).
"""

from __future__ import annotations

import base64
import io
import sys

from PIL import Image, ImageDraw


def _dpi_aware() -> None:
    """Physical pixels at 125% scaling, so a point on the screenshot is a point on the screen."""
    import ctypes

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


def grab() -> Image.Image:
    """The primary screen, as the user sees it."""
    if sys.platform != "win32":
        raise RuntimeError("Chụp màn hình trực tiếp chỉ chạy trên Windows; dùng --image trên máy khác.")
    from PIL import ImageGrab

    _dpi_aware()
    return ImageGrab.grab(all_screens=False).convert("RGB")


def load(path: str) -> Image.Image:
    with Image.open(path) as img:
        return img.convert("RGB")


def png_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def mark(img: Image.Image, point: tuple[int, int] | None, radius: int = 22) -> Image.Image:
    """A copy with a red ring and cross at the point; unchanged copy when there is no point."""
    out = img.copy()
    if point is None:
        return out
    x, y = point
    d = ImageDraw.Draw(out)
    d.ellipse((x - radius, y - radius, x + radius, y + radius), outline=(230, 0, 0), width=4)
    d.line((x - radius - 10, y, x - 6, y), fill=(230, 0, 0), width=3)
    d.line((x + 6, y, x + radius + 10, y), fill=(230, 0, 0), width=3)
    d.line((x, y - radius - 10, x, y - 6), fill=(230, 0, 0), width=3)
    d.line((x, y + 6, x, y + radius + 10), fill=(230, 0, 0), width=3)
    return out
