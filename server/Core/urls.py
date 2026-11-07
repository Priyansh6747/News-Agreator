from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}
TRACKING_PREFIXES = ("utm_",)


def domain_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(TRACKING_PREFIXES)


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    netloc = (parts.netloc or "").lower().removeprefix("www.")
    if not netloc:
        return url
    path = parts.path.rstrip("/") or "/"
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
         if not _is_tracking(key)]
    )
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def normalize_title(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", title.lower()))


def publisher_matches(url: str, domain: str) -> bool:
    host = domain_of(url)
    target = domain.lower().removeprefix("www.")
    if not host or not target:
        return False
    return host == target or host.endswith(f".{target}")
