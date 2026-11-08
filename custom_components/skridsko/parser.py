"""Tolking av HTML fra tur.skridsko.net (kun standardbibliotek)."""
from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field

from .geo import map_links, rt90_from_page, rt90_to_wgs84
from .const import IMAGE_HOST, LEVEL_COLORS, NO_ACCESS, OBS_URL, SKATEABLE_LEVELS


class NotLoggedIn(Exception):
    """Siden svarte at vi ikke har tilgang."""


@dataclass
class Observation:
    id: str
    title: str
    status: str
    level: str
    isinfo: str
    comment: str
    reporter: str
    time: str
    url: str
    images: list[str] = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None

    @property
    def links(self) -> dict[str, str]:
        return map_links(self.lat, self.lon) if self.lat is not None else {}

    @property
    def name(self) -> str:
        return re.sub(r"\s*\[.*?\]\s*$", "", self.title)

    @property
    def region(self) -> str:
        m = re.search(r"\[(.*?)\]", self.title)
        return m.group(1) if m else ""

    @property
    def short_status(self) -> str:
        return self.status.split("|")[0].strip()

    @property
    def method(self) -> str:
        parts = self.status.split("|", 1)
        return parts[1].strip() if len(parts) > 1 else ""

    @property
    def color(self) -> str:
        return LEVEL_COLORS.get(self.level, "#757575")

    @property
    def skateable(self) -> bool:
        return self.level in SKATEABLE_LEVELS

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update(name=self.name, region=self.region, short_status=self.short_status,
                 method=self.method, color=self.color, skateable=self.skateable,
                 map_links=self.links)
        return d


def strip_tags(s: str) -> list[str]:
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h\d)>", "\n", s)
    # tagger kan ha «>» inni sitert attributt, f.eks. title="Helt islagt (> 95%)"
    s = re.sub(r"<(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in s.split("\n")]
    return [line for line in lines if line]


def is_logged_out(page: str) -> bool:
    return NO_ACCESS in page


def parse_list(page: str) -> list[str]:
    """Observasjons-ID-er i rekkefølgen de står i lista (nyeste først)."""
    ids: list[str] = []
    for m in re.finditer(r"isobservationer-v\.asp\?ID=(\d+)", page):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def parse_observation(page: str, obs_id: str) -> Observation:
    if is_logged_out(page):
        raise NotLoggedIn
    start = page.find('class="col-md-7 order-md-1"')
    end = page.find('id="fardrapportbilder"', start)
    if end < 0:
        end = page.find("Informasjonen i isobservasjonene", start)
    block = page[start:end] if start > 0 and end > 0 else page

    title_m = re.search(r"(?is)<h3>(.*?)</h3>", block)
    title = " ".join(strip_tags(title_m.group(1))) if title_m else f"Observasjon {obs_id}"
    level_m = re.search(r"akbarhet_(\d)", block)

    status = isinfo = time = reporter = ""
    comment: list[str] = []
    for row in re.findall(r"(?is)<tr[^>]*>(.*?)(?=<tr|</table>)", block):
        txt = " ".join(strip_tags(row))
        if "akbarhet_" in row and not status:
            status = txt
        elif txt.startswith("Isinfo:"):
            isinfo = txt.split(":", 1)[1].strip()
        elif "to_translate" in row:
            inner = re.sub(r"(?i)<br\s*/?>", "\n", row)
            text = "\n".join(strip_tags(inner))
            text = re.split(r"(?i)Automatisk oversettelse|Automatisk översättning|Automatic translation", text)[0]
            comment.append(text.strip())
        elif "minauppgifter" in row:
            reporter = txt
        elif txt.startswith("Tid:"):
            time = txt.split(":", 1)[1].strip()

    images: list[str] = []
    for img in re.findall(r"bildarkiv/normal/pic_\d+\.jpg", page):
        url = IMAGE_HOST + img
        if url not in images:
            images.append(url)

    lat = lon = None
    rt90 = rt90_from_page(page)
    if rt90:
        lat, lon = rt90_to_wgs84(*rt90)

    return Observation(
        lat=lat, lon=lon, id=obs_id, title=title, status=status, level=level_m.group(1) if level_m else "",
        isinfo=isinfo, comment="\n".join(c for c in comment if c), reporter=reporter,
        time=time, url=OBS_URL.format(id=obs_id), images=images,
    )


def ids_from_email(text: str) -> list[str]:
    ids: list[str] = []
    for m in re.finditer(r"isobservationer-v\.asp\?ID=(\d+)", text or ""):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    if not ids:  # lenken kan være kuttet bort – bruk «Nummer: 491401»
        ids = [m.group(1) for m in re.finditer(r"Nummer:\W*(\d{5,})", text or "")][:1]
    return ids
