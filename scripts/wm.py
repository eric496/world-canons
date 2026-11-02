#!/usr/bin/env python3
"""Polite Wikimedia helper shared by everyone building this repo.

Wikimedia rate-limits our shared network address hard, so every request goes
through one global throttle (a lock file shared by all processes) and a shared
on-disk cache. Never call Wikipedia/Commons any other way.

Usage (CLI):
  python3 -I scripts/wm.py lead  "Mona Lisa"                 # lead image of an en.wikipedia article
  python3 -I scripts/wm.py search "Degas Dance Class Orsay"   # Commons file titles for a query
  python3 -I scripts/wm.py resolve "File name.jpg"            # verify a Commons file + get thumb URLs
  python3 -I scripts/wm.py add western/art "File name.jpg"    # resolve and store in <subject>/data/image_urls.json

Output is JSON. `lead` returns {"file", "commons": bool, "page", "disambiguation", "url_1280", "url_330"}.
Only use files where "commons" is true (en.wikipedia-only files are non-free).
"""
import fcntl
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "WorldCanonsRepo/1.0 (https://github.com/eric496/world-canons; utwysgo@gmail.com)"
STATE = Path("/tmp/wm-throttle")          # shared across all processes
CACHE = Path("/tmp/wm-cache")
MIN_INTERVAL = 1.6                         # seconds between any two Wikimedia requests
COOLDOWN_429 = 45                          # global pause after a 429
STATE.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_noredir = urllib.request.build_opener(_NoRedirect)


def _throttle():
    lock = open(STATE / "lock", "a+")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        f = STATE / "next"
        now = time.time()
        nxt = float(f.read_text()) if f.exists() else 0
        if nxt > now:
            time.sleep(nxt - now)
        f.write_text(str(time.time() + MIN_INTERVAL))
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _cooldown():
    (STATE / "next").write_text(str(time.time() + COOLDOWN_429))


def _cached(key):
    p = CACHE / hashlib.sha1(key.encode()).hexdigest()
    return json.loads(p.read_text()) if p.exists() else None


def _store(key, value):
    (CACHE / hashlib.sha1(key.encode()).hexdigest()).write_text(json.dumps(value))


def _get(url, follow=True, tries=5):
    """Return (status, final_url_or_location, body_text). Retries on 429/5xx."""
    for attempt in range(tries):
        _throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            opener = urllib.request.urlopen if follow else _noredir.open
            with opener(req, timeout=40) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307) and not follow:
                return e.code, e.headers.get("Location"), ""
            if e.code == 429 or e.code >= 500:
                _cooldown()
                continue
            return e.code, url, ""
        except Exception:
            time.sleep(5 * (attempt + 1))
    return 0, url, ""


def thumb_urls(file_name, og_width=None):
    """Build upload.wikimedia.org thumbnail URLs from a Commons file name."""
    name = file_name.replace(" ", "_")
    h = hashlib.md5(name.encode()).hexdigest()
    q = urllib.parse.quote(name)
    base = f"https://upload.wikimedia.org/wikipedia/commons/thumb/{h[0]}/{h[:2]}/{q}"
    orig = f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[:2]}/{q}"
    ext = ".png" if name.lower().endswith((".svg", ".tif", ".tiff")) else ""
    big = 1280 if not og_width or og_width >= 1280 else None
    return {
        "1280": f"{base}/1280px-{q}{ext}" if big else (orig if not ext else f"{base}/{og_width}px-{q}{ext}"),
        "330": f"{base}/330px-{q}{ext}" if (not og_width or og_width >= 330) else orig,
    }


def _file_from_upload_url(src):
    p = urllib.parse.urlparse(src).path
    if "/wikipedia/commons/" not in p:
        return None
    parts = p.split("/")
    name = parts[parts.index("thumb") + 3] if "thumb" in parts else parts[-1]
    return urllib.parse.unquote(name).replace("_", " ")


def lead(title):
    """Lead (og:image) picture of an English Wikipedia article."""
    key = "lead:" + title
    if (c := _cached(key)) is not None:
        return c
    url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="")
    status, final, body = _get(url)
    out = {"title": title, "status": status}
    if status == 200:
        m = re.search(r'<meta property="og:image" content="([^"]+)"', body)
        w = re.search(r'<meta property="og:image:width" content="(\d+)"', body)
        t = re.search(r"<title>(.*?) - Wikipedia</title>", body)
        out["page"] = html.unescape(t.group(1)) if t else final
        out["disambiguation"] = "(disambiguation)" in out["page"] or 'id="disambigbox"' in body
        if m:
            src = html.unescape(m.group(1))
            f = _file_from_upload_url(src)
            out["commons"] = bool(f)
            out["src"] = src
            if f:
                out["file"] = f
                loc = src.split("?")[0].replace("https://thumb.wikimedia.org/", "https://upload.wikimedia.org/")
                if "/thumb/" in loc:
                    out["url_1280"] = loc
                    out["url_330"] = re.sub(r"/\d+px-", "/330px-", loc)
                else:
                    out["url_1280"] = out["url_330"] = loc
    if status in (200, 404):
        _store(key, out)
    return out


def search(query, limit=12):
    """Commons media search; returns a list of file names."""
    key = "search:" + query
    if (c := _cached(key)) is not None:
        return c
    url = ("https://commons.wikimedia.org/w/index.php?title=Special:MediaSearch&type=image&search="
           + urllib.parse.quote(query))
    status, _, body = _get(url)
    files = []
    for m in re.finditer(r'title="File:([^"]+)"', body):
        f = html.unescape(m.group(1))
        if f not in files:
            files.append(f)
    if status == 200:
        _store(key, files[:limit])
    return files[:limit]


def resolve(file_name):
    """Check that a Commons file exists; return its thumbnail URLs."""
    key = "resolve:" + file_name
    if (c := _cached(key)) is not None:
        return c
    url = ("https://commons.wikimedia.org/w/index.php?title=Special:Redirect/file/"
           + urllib.parse.quote(file_name.replace(" ", "_")) + "&width=1280")
    status, loc, _ = _get(url, follow=False)
    out = {"file": file_name, "exists": status in (301, 302, 303, 307)}
    if out["exists"]:
        loc = loc.split("?")[0].replace("https://thumb.wikimedia.org/", "https://upload.wikimedia.org/")
        if "/thumb/" in loc:
            out["1280"] = loc
            out["330"] = re.sub(r"/\d+px-", "/330px-", loc)
        else:  # original is smaller than 1280 px
            out["1280"] = out["330"] = loc
        _store(key, out)
    return out


def add(subject_dir, file_name, urls=None):
    """Record a verified file's URLs in <subject>/data/image_urls.json (locked write).
    Pass urls={"1280":..,"330":..} from a lead() result to save a request."""
    urls = urls or resolve(file_name)
    if not urls.get("1280"):
        raise SystemExit(f"not found on Commons: {file_name}")
    path = ROOT / subject_dir / "data" / "image_urls.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else {}
        data[file_name] = {"1280": urls["1280"], "330": urls["330"]}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True))
    return data[file_name]


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    if cmd == "lead":
        print(json.dumps(lead(args[0]), ensure_ascii=False, indent=1))
    elif cmd == "search":
        print(json.dumps(search(args[0]), ensure_ascii=False, indent=1))
    elif cmd == "resolve":
        print(json.dumps(resolve(args[0]), ensure_ascii=False, indent=1))
    elif cmd == "add":
        print(json.dumps(add(args[0], args[1]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
