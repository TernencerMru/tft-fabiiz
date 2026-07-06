"""EXPERIMENTAL: shop reading via screen capture + OCR.

Approach: grab the five shop-card name strips from your own screen (``mss``),
run Tesseract on each (``pytesseract``), and fuzzy-match the result against
the current set's champion names. Pure screen capture — no memory reading,
no injection, nothing Vanguard cares about — but inherently brittle: regions
depend on resolution/HUD scale, and skins/fonts hurt accuracy. That is why
this ships as an optional extra (``pip install .[ocr]``) with the lowest
source priority: a wrong OCR read must never override manual input.

Calibration workflow: take a screenshot of a real shop at your resolution,
measure the five name-strip rectangles, and put the fractions in
``SHOP_REGIONS`` (values are fractions of screen width/height so one
calibration survives most resolutions with the same aspect ratio).
"""
from __future__ import annotations

import difflib
from typing import Optional

from ..core.models import GameSnapshot, SetData

try:  # optional dependencies
    import mss  # type: ignore
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

# (left, top, width, height) as fractions of the full screen, one per slot.
# Placeholder values roughly for 16:9 default HUD — CALIBRATE for your setup.
SHOP_REGIONS: list[tuple[float, float, float, float]] = [
    (0.245 + i * 0.101, 0.945, 0.085, 0.030) for i in range(5)
]

MATCH_CUTOFF = 0.6


class OcrShopSource:
    name = "ocr_shop"
    priority = 1

    def __init__(self, set_data: SetData) -> None:
        if not _OCR_AVAILABLE:
            raise RuntimeError(
                "OCR extra no instalado: pip install 'tft-companion[ocr]' "
                "(y Tesseract en el sistema)."
            )
        self.set_data = set_data
        self._names = {c.name: c.id for c in set_data.champions.values()}

    def is_available(self) -> bool:
        return _OCR_AVAILABLE

    def poll(self) -> Optional[GameSnapshot]:
        shop = self._read_shop()
        if shop is None or not any(shop):
            return None
        return GameSnapshot(source=self.name, shop=shop)

    # ------------------------------------------------------------------
    def _read_shop(self) -> Optional[list[Optional[str]]]:
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                width, height = monitor["width"], monitor["height"]
                results: list[Optional[str]] = []
                for (fx, fy, fw, fh) in SHOP_REGIONS:
                    region = {
                        "left": monitor["left"] + int(fx * width),
                        "top": monitor["top"] + int(fy * height),
                        "width": int(fw * width),
                        "height": int(fh * height),
                    }
                    grab = sct.grab(region)
                    img = Image.frombytes("RGB", grab.size, grab.rgb)
                    text = pytesseract.image_to_string(img, config="--psm 7").strip()
                    results.append(self._match(text))
                return results
        except Exception:
            return None  # experimental source: fail silent, never crash the app

    def _match(self, text: str) -> Optional[str]:
        if not text:
            return None
        hits = difflib.get_close_matches(text, self._names.keys(), n=1, cutoff=MATCH_CUTOFF)
        return self._names[hits[0]] if hits else None
