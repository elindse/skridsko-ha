"""Koordinater og kartbilde.

Skridsko oppgir vannets posisjon i RT90 2.5 gon V (svensk rikssystem). Vi regner om til
WGS84 med Lantmäteriets parametre for direkte omregning, og til UTM33 for Norgeskart.
"""
from __future__ import annotations

import io
import math
import re

KARTVERKET_TILE = "https://cache.kartverket.no/v1/wmts/1.0.0/topo/default/webmercator/{z}/{y}/{x}.png"
OSM_TILE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

# GRS80
_A = 6378137.0
_F = 1 / 298.257222101


def rt90_from_page(page: str) -> tuple[int, int] | None:
    m = re.search(r"vatten=(\d{7})(?:\||%7C)(\d{7})", page)
    return (int(m.group(1)), int(m.group(2))) if m else None


def rt90_to_wgs84(x: float, y: float) -> tuple[float, float]:
    lon0 = 15 + 48 / 60 + 22.624306 / 3600
    k0, fn, fe = 1.00000561024, -667.711, 1500064.274
    e2 = _F * (2 - _F)
    n = _F / (2 - _F)
    ah = _A / (1 + n) * (1 + n * n / 4 + n ** 4 / 64)
    d1 = n / 2 - 2 * n * n / 3 + 37 * n ** 3 / 96 - n ** 4 / 360
    d2 = n * n / 48 + n ** 3 / 15 - 437 * n ** 4 / 1440
    d3 = 17 * n ** 3 / 480 - 37 * n ** 4 / 840
    d4 = 4397 * n ** 4 / 161280
    a_ = e2 + e2 ** 2 + e2 ** 3 + e2 ** 4
    b_ = -(7 * e2 ** 2 + 17 * e2 ** 3 + 30 * e2 ** 4) / 6
    c_ = (224 * e2 ** 3 + 889 * e2 ** 4) / 120
    d_ = -(4279 * e2 ** 4) / 1260
    xi = (x - fn) / (k0 * ah)
    eta = (y - fe) / (k0 * ah)
    xp = xi - sum(d * math.sin(2 * k * xi) * math.cosh(2 * k * eta) for k, d in enumerate((d1, d2, d3, d4), 1))
    ep = eta - sum(d * math.cos(2 * k * xi) * math.sinh(2 * k * eta) for k, d in enumerate((d1, d2, d3, d4), 1))
    phis = math.asin(math.sin(xp) / math.cosh(ep))
    dl = math.atan(math.sinh(ep) / math.cos(xp))
    s = math.sin(phis)
    lat = phis + s * math.cos(phis) * (a_ + b_ * s * s + c_ * s ** 4 + d_ * s ** 6)
    return round(math.degrees(lat), 6), round(lon0 + math.degrees(dl), 6)


def wgs84_to_utm33(lat: float, lon: float) -> tuple[int, int]:
    n = _F / (2 - _F)
    a_ = _A / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    b = (n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16, 13 * n ** 2 / 48 - 3 * n ** 3 / 5, 61 * n ** 3 / 240)
    e = math.sqrt(_F * (2 - _F))
    p, lam = math.radians(lat), math.radians(lon - 15)
    t = math.sinh(math.atanh(math.sin(p)) - e * math.atanh(e * math.sin(p)))
    xi = math.atan(t / math.cos(lam))
    eta = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    north = 0.9996 * a_ * (xi + sum(c * math.sin(2 * k * xi) * math.cosh(2 * k * eta) for k, c in enumerate(b, 1)))
    east = 500000 + 0.9996 * a_ * (eta + sum(c * math.cos(2 * k * xi) * math.sinh(2 * k * eta) for k, c in enumerate(b, 1)))
    return round(north), round(east)


def map_links(lat: float, lon: float) -> dict[str, str]:
    n, e = wgs84_to_utm33(lat, lon)
    return {
        "norgeskart": f"https://norgeskart.no/#!?project=norgeskart&zoom=12&lat={n}&lon={e}&markerLat={n}&markerLon={e}",
        "google": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
    }


def _tile_xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def tiles_needed(lat: float, lon: float, z: int, w: int, h: int) -> tuple[list[tuple[int, int]], tuple[int, int]]:
    """Fliser som dekker et w×h-utsnitt sentrert på punktet, og utsnittets øvre venstre piksel."""
    fx, fy = _tile_xy(lat, lon, z)
    px, py = fx * 256, fy * 256
    left, top = int(px - w / 2), int(py - h / 2)
    tiles = [(tx, ty) for ty in range(top // 256, (top + h) // 256 + 1)
             for tx in range(left // 256, (left + w) // 256 + 1)]
    return tiles, (left, top)


def compose_map(tiles: dict[tuple[int, int], bytes], origin: tuple[int, int], w: int, h: int,
                attribution: str) -> bytes:
    """Setter sammen fliser til ett JPEG-bilde med markør i midten. Krever Pillow."""
    from PIL import Image, ImageDraw

    left, top = origin
    canvas = Image.new("RGB", (w, h), (235, 235, 235))
    for (tx, ty), data in tiles.items():
        try:
            tile = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            continue
        canvas.paste(tile, (tx * 256 - left, ty * 256 - top))
    d = ImageDraw.Draw(canvas)
    cx, cy = w // 2, h // 2
    # dråpeformet markør
    d.ellipse((cx - 11, cy - 34, cx + 11, cy - 12), fill=(198, 40, 40), outline=(255, 255, 255), width=2)
    d.polygon([(cx - 9, cy - 19), (cx + 9, cy - 19), (cx, cy)], fill=(198, 40, 40))
    d.ellipse((cx - 4, cy - 27, cx + 4, cy - 19), fill=(255, 255, 255))
    # kildemerking
    tw = int(d.textlength(attribution)) + 10
    d.rectangle((w - tw, h - 16, w, h), fill=(255, 255, 255))
    d.text((w - tw + 5, h - 14), attribution, fill=(60, 60, 60))
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=82)
    return out.getvalue()
