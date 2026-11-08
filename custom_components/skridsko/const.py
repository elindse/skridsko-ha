"""Konstanter for Skridsko-integrasjonen."""
from __future__ import annotations

DOMAIN = "skridsko"
PLATFORMS = ["binary_sensor", "sensor", "image", "button", "switch"]

BASE_URL = "https://tur.skridsko.net"
LIST_URL = BASE_URL + "/skridskonet/isobservationer/index.html?_kalender=1&_listlen=250&_intresseomrade=1"
OBS_URL = BASE_URL + "/skridskonet/isobservationer/isobservationer-v.asp?ID={id}"
IMAGE_HOST = "https://bild.skridsko.net/"
NO_ACCESS = "ikke tillatelse"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# config entry data
CONF_PHPSESSID = "phpsessid"
CONF_IMAP_ENTRY = "imap_entry"

# options
CONF_EMAIL_ENABLED = "email_enabled"
CONF_EMAIL_TO = "email_to"
CONF_EMAIL_SERVICE = "email_service"
CONF_SMTP_USER = "smtp_user"
CONF_SMTP_PASSWORD = "smtp_password"
BUILTIN_SMTP = "builtin"
CONF_PUSH_ENABLED = "push_enabled"
CONF_PUSH_SERVICES = "push_services"
CONF_PUSH_ONLY_SKATEABLE = "push_only_skateable"
CONF_MAX_IMAGES = "max_images"
CONF_USE_EMAIL = "use_email"
CONF_INCLUDE_MAP = "include_map"
CONF_KEEPALIVE_MIN = "keepalive_min"
CONF_KEEPALIVE_MAX = "keepalive_max"

DEFAULT_OPTIONS = {
    CONF_USE_EMAIL: False,
    CONF_IMAP_ENTRY: "",
    CONF_EMAIL_ENABLED: False,
    CONF_EMAIL_TO: "",
    CONF_EMAIL_SERVICE: "builtin",
    CONF_SMTP_USER: "",
    CONF_SMTP_PASSWORD: "",
    CONF_PUSH_ENABLED: False,
    CONF_PUSH_SERVICES: [],
    CONF_PUSH_ONLY_SKATEABLE: False,
    CONF_MAX_IMAGES: 4,
    CONF_INCLUDE_MAP: True,
    CONF_KEEPALIVE_MIN: 9,
    CONF_KEEPALIVE_MAX: 21,
}

# Åkbarhet-nivå fra siden (klassen akbarhet_N). 4 = uegnet og 6 = ukjent er
# bekreftet; 1–3 antas å være skøytbar is i synkende kvalitet.
SKATEABLE_LEVELS = {"1", "2", "3"}
LEVEL_COLORS = {
    "1": "#2e7d32",
    "2": "#7cb342",
    "3": "#f9a825",
    "4": "#c62828",
    "5": "#c62828",
    "6": "#757575",
}

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"
EVENT_OBSERVATION = f"{DOMAIN}_observation"
IMAGE_DIR = "skridsko"  # under /config/www
STORAGE_VERSION = 1
HISTORY_LEN = 10
JITTER_MAX_SECONDS = 40


def effective_options(entry) -> dict:
    """Innstillinger med standardverdier. Eldre oppsett (før 0.3) hadde IMAP-kontoen i data."""
    o = {**DEFAULT_OPTIONS, **entry.options}
    if CONF_USE_EMAIL not in entry.options and entry.data.get(CONF_IMAP_ENTRY):
        o[CONF_USE_EMAIL] = True
        o[CONF_IMAP_ENTRY] = entry.data[CONF_IMAP_ENTRY]
    return o
