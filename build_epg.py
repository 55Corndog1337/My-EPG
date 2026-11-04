
"""Build an XMLTV guide and a PRIVATE, matching M3U playlist.

Source playlist is downloaded from the PLAYLIST_URL Actions secret.
Never publish playlist.m3u: streaming URLs may contain credentials.
"""

import csv
import gzip
import io
import os
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent

SOURCES = {
    "epg2": (
        "https://raw.githubusercontent.com/ferteque/"
        "Curated-M3U-Repository/main/epg2.xml.gz"
    ),
    "epg37": (
        "https://raw.githubusercontent.com/ferteque/"
        "Curated-M3U-Repository/main/epg37.xml.gz"
    ),
}

ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def download(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "My-EPG/2.0"}
    )

    with urllib.request.urlopen(request, timeout=240) as response:
        data = response.read(160 * 1024 * 1024 + 1)

    if len(data) > 160 * 1024 * 1024:
        raise ValueError("Download exceeds 160 MiB")

    if data.startswith(b"\x1f\x8b"):
        return gzip.decompress(data)

    return data


def normalize(value):
    return re.sub(
        r"[^a-z0-9]+",
        "",
        (value or "").casefold()
    )


def read_m3u(raw):
    lines = raw.decode(
        "utf-8-sig", "replace"
    ).splitlines()

    if not lines or not lines[0].startswith("#EXTM3U"):
        raise ValueError("Invalid M3U playlist")

    items = []
    pending = None

    for line in lines[1:]:
        if line.startswith("#EXTINF:"):
            pending = line

        elif (
            pending
            and line.strip()
            and not line.startswith("#")
        ):
            meta, _, name = pending.partition(",")
            attrs = dict(ATTR.findall(meta))

            items.append({
                "extinf": pending,
                "url": line,
                "name": name.strip(),
                "group": attrs.get("group-title", ""),
                "id": attrs.get("tvg-id", ""),
            })

            pending = None

    return lines[0], items


def main():
