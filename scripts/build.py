#!/usr/bin/env python3
"""Generate every Markdown page in this repo from the JSON data.

    python3 scripts/build.py            # build everything
    python3 scripts/build.py --check    # validate data only, print warnings

Layout:  <tradition>/<subject>/data/{subject,creators,works,movements,image_urls}.json
         <tradition>/periods.json
See CONVENTIONS.md for the data format. Only the Python standard library is needed.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
CHECK_ONLY = "--check" in sys.argv
WARN = []


def warn(msg):
    WARN.append(msg)


def load(path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise SystemExit(f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, text):
    if CHECK_ONLY:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def century_label(year):
    if year < 0:
        return f"{ordinal((-year - 1) // 100 + 1)} century BC"
    return f"{ordinal(year // 100 + 1)} century"


def born_year(c):
    if "sort" in c:
        return c["sort"]
    m = re.search(r"\d{3,4}", c.get("born", ""))
    y = int(m.group()) if m else 0
    return -y if "BC" in c.get("born", "") else y


def anchor(text):
    text = re.sub(r"[^\w\- ]", "", text.lower())
    return text.replace(" ", "-")


def rel(from_dir, to_path):
    """Relative link from a directory to a file, both relative to ROOT."""
    import os
    return os.path.relpath(ROOT / to_path, ROOT / from_dir).replace(os.sep, "/")


# ---------------------------------------------------------------- subjects ---
class Subject:
    def __init__(self, path):
        self.path = path                                   # e.g. western/art (relative)
        d = ROOT / path / "data"
        self.meta = load(d / "subject.json")
        self.creators = load(d / "creators.json", [])
        self.works = sorted(load(d / "works.json", []), key=lambda w: w.get("sort", 0))
        self.movements = load(d / "movements.json", [])
        self.images = load(d / "image_urls.json", {})
        self.slug = path.split("/")[-1]
        self.title = self.meta["title"]
        self.L = {"creator": "Creator", "creators": "Creators", "work": "Work", "works": "Works",
                  "movement": "Movement", "movements": "Movements", "location": "Where",
                  **self.meta.get("labels", {})}
        self.generate = self.meta.get("generate_pages", True)
        self.by_id = {c["id"]: c for c in self.creators}
        self.mov_by_id = {m["id"]: m for m in self.movements}
        self.works_by = defaultdict(list)
        for w in self.works:
            self.works_by[w["creator"]].append(w)
        self.validate()

    def validate(self):
        seen = set()
        for c in self.creators:
            if c["id"] in seen:
                warn(f"{self.path}: duplicate creator id {c['id']}")
            seen.add(c["id"])
            for m in c.get("movements", []):
                if m not in self.mov_by_id:
                    warn(f"{self.path}: {c['id']} has unknown movement '{m}'")
            if c.get("portrait_file") and c["portrait_file"] not in self.images:
                warn(f"{self.path}: portrait for {c['id']} not in image_urls.json")
            if not c.get("bio_full"):
                warn(f"{self.path}: {c['id']} has no bio_full")
        for w in self.works:
            if w["creator"] not in self.by_id:
                warn(f"{self.path}: work '{w['title']}' has unknown creator '{w['creator']}'")
            if w.get("image_file") and w["image_file"] not in self.images:
                warn(f"{self.path}: image for '{w['title']}' not in image_urls.json")
            if not w.get("description"):
                warn(f"{self.path}: '{w['title']}' has no description")

    # --- helpers
    def img(self, file, size):
        u = self.images.get(file, {})
        return u.get(str(size)) or u.get("1280")

    def commons_page(self, file):
        return "https://commons.wikimedia.org/wiki/File:" + quote(file.replace(" ", "_"))

    def creator_page(self, cid):
        c = self.by_id[cid]
        if not self.generate:
            return f"{self.path}/{c['page']}" if c.get("page") else f"{self.path}/README.md"
        return f"{self.path}/creators/{cid}.md"

    def portrait_thumb(self, c, from_dir, width=60):
        f = c.get("portrait_file")
        if not f or f not in self.images:
            return ""
        return f'<img src="{self.img(f, 330)}" width="{width}" alt="{c["name"]}">'

    def work_thumb(self, w):
        if w.get("image_file") and w["image_file"] in self.images:
            return (f'<a href="{self.commons_page(w["image_file"])}"><img src="{self.img(w["image_file"], 330)}" '
                    f'width="140" alt="{w["title"]}"></a>')
        if w.get("museum_url"):
            return f"[View ↗]({w['museum_url']})"
        return "—"

    def first_movement(self, c):
        return c.get("movements", [None])[0]

    # --- pages
    def build_pages(self):
        L, P = self.L, self.path
        # creators
        for c in self.creators:
            here = f"{P}/creators"
            movs = ", ".join(f"[{self.mov_by_id[m]['name']}](../movements/{m}.md)"
                             for m in c.get("movements", []) if m in self.mov_by_id)
            out = [f"# {c['name']}", ""]
            if c.get("name_native"):
                out += [f"*{c['name_native']}*", ""]
            pf = c.get("portrait_file")
            if pf and pf in self.images:
                cap = c.get("portrait_caption", "Portrait")
                out += [f'<a href="{self.commons_page(pf)}"><img align="right" width="240" '
                        f'src="{self.img(pf, 330)}" alt="{c["name"]}" title="{cap}"></a>', ""]
            life = f"{c.get('born', '?')} – {c.get('died', '')}".rstrip(" –")
            out += [f"**{life}** · {c.get('nationality', '')}  "]
            if c.get("birthplace") or c.get("deathplace"):
                out += [f"Born: {c.get('birthplace', '?')} · Died: {c.get('deathplace', '?')}  "]
            if movs:
                out += [f"{L['movements']}: {movs}  "]
            also = PEOPLE_SUBJECTS.get(c["id"], [])
            others = [s for s in also if s.path != P]
            if others:
                out += ["Also in: " + ", ".join(f"[{s.title}]({rel(here, s.creator_page(c['id']))})" for s in others) + "  "]
            out += [""]
            if c.get("bio"):
                out += [f"> {c['bio']}", ""]
            if pf and pf in self.images:
                out += [f"<sub>Portrait: {c.get('portrait_caption', '')} · [Wikimedia Commons]({self.commons_page(pf)})</sub>", ""]
            if c.get("links"):
                out += ["**Links:** " + " · ".join(f"[{l['name']}]({l['url']})" for l in c["links"]), ""]
            out += ["## Biography", ""]
            for para in c.get("bio_full", [c.get("bio", "")]):
                out += [para, ""]
            ws = self.works_by.get(c["id"], [])
            if ws:
                out += [f"## Key {L['works'].lower()}", ""]
                if len(ws) > 1:
                    out += [f"- [{w['title']}](#{anchor(w['title'] + ' (' + w['year'] + ')')}) ({w['year']})" for w in ws] + [""]
                for w in ws:
                    out += [f"### {w['title']} ({w['year']})", ""]
                    if w.get("image_file") and w["image_file"] in self.images:
                        cap = (w["image_caption"] + " ") if w.get("image_caption") else ""
                        out += [f'[![{w["title"]}]({self.img(w["image_file"], 1280)})]({self.commons_page(w["image_file"])})', "",
                                f"<sub>{cap}Image: Wikimedia Commons. [Full resolution, credit and licence]({self.commons_page(w['image_file'])}).</sub>", ""]
                    elif w.get("museum_url"):
                        out += [f"> 🖼️ **[View it at {w['museum_name']} →]({w['museum_url']})**  ",
                                "> <sub>Still under copyright, so it is not reproduced here.</sub>", ""]
                    out += [f"- **Date:** {w['year']}", f"- **Type:** {w.get('type', '')}"]
                    if w.get("location"):
                        out += [f"- **{L['location']}:** {w['location']}"]
                    q = quote(f"{w['title']} {c['name']}")
                    out += [f"- **Read more:** [Wikipedia](https://en.wikipedia.org/w/index.php?search={q})"]
                    if w.get("links"):
                        out += ["- **Links:** " + " · ".join(f"[{l['name']}]({l['url']})" for l in w["links"])]
                    out += [""]
                    out += [w.get("description") or w.get("note", ""), ""]
            out += ["---", f"[← All {L['creators'].lower()}](../CREATORS.md) · [{self.title}](../README.md) · [{TRAD_TITLE}](../../README.md)"]
            write(ROOT / here / f"{c['id']}.md", "\n".join(out))
        # movements
        for i, m in enumerate(self.movements):
            here = f"{P}/movements"
            members = sorted([c for c in self.creators if m["id"] in c.get("movements", [])], key=born_year)
            ids = {c["id"] for c in members if self.first_movement(c) == m["id"]}
            ws = [w for w in self.works if w["creator"] in ids]
            out = [f"# {m['name']}" + (f" ({m['name_native']})" if m.get("name_native") else ""), "", f"*{m.get('dates', '')}*", ""]
            if m.get("period") in PERIODS:
                out += [f"Era: [{PERIODS[m['period']]['name']}](../../periods/{m['period']}.md)", ""]
            out += [m.get("summary", ""), ""]
            if m.get("image_file") and m["image_file"] in self.images:
                out += [f'<img src="{self.img(m["image_file"], 1280)}" width="100%" alt="{m["name"]}">', "",
                        f"<sub>{m.get('image_caption', '')} · [Wikimedia Commons]({self.commons_page(m['image_file'])})</sub>", ""]
            out += [f"## {L['creators']}", ""]
            for c in members:
                t = self.portrait_thumb(c, here, 40)
                out += [f"- {t} [{c['name']}](../creators/{c['id']}.md) ({c.get('born', '')} – {c.get('died', '')})"]
            if ws:
                out += ["", f"## Key {L['works'].lower()}", "", f"| Image | Year | {L['work']} | {L['creator']} | {L['location']} |", "|---|---|---|---|---|"]
                for w in ws:
                    out += [f"| {self.work_thumb(w)} | {w['year']} | **{w['title']}** | [{self.by_id[w['creator']]['name']}](../creators/{w['creator']}.md) | {w.get('location', '')} |"]
            nav = []
            if i > 0:
                nav.append(f"[← {self.movements[i-1]['name']}]({self.movements[i-1]['id']}.md)")
            nav.append(f"[{self.title}](../README.md)")
            if i < len(self.movements) - 1:
                nav.append(f"[{self.movements[i+1]['name']} →]({self.movements[i+1]['id']}.md)")
            out += ["", "---", " · ".join(nav)]
            write(ROOT / here / f"{m['id']}.md", "\n".join(out))
        # creator index
        out = [f"# {L['creators']}", "", "Ordered by date of birth.", "",
               f"| | {L['creator'].split('/')[0]} | Life | {L['movements']} | {L['works']} |", "|---|---|---|---|---|"]
        for c in sorted(self.creators, key=born_year):
            movs = ", ".join(f"[{self.mov_by_id[m]['name']}](movements/{m}.md)" for m in c.get("movements", []) if m in self.mov_by_id)
            out += [f"| {self.portrait_thumb(c, P, 50)} | [{c['name']}](creators/{c['id']}.md) | {c.get('born', '')} – {c.get('died', '')} | {movs} | {len(self.works_by.get(c['id'], []))} |"]
        write(ROOT / P / "CREATORS.md", "\n".join(out))
        # timeline
        out = [f"# Timeline of {L['works'].lower()}", "", f"Every {L['work'].lower()} in this section in chronological order.", ""]
        cur = None
        for w in self.works:
            lab = century_label(w.get("sort", 0))
            if lab != cur:
                cur = lab
                out += ["", f"## {lab}", "", f"| Image | Year | {L['work']} | {L['creator']} |", "|---|---|---|---|"]
            out += [f"| {self.work_thumb(w)} | {w['year']} | **{w['title']}** | [{self.by_id[w['creator']]['name']}](creators/{w['creator']}.md) |"]
        write(ROOT / P / "TIMELINE.md", "\n".join(out))
        # gallery (images only)
        pics = [w for w in self.works if w.get("image_file") and w["image_file"] in self.images]
        if pics:
            out = [f"# {self.title}: gallery", "", f"{len(pics)} images, oldest first. Click a picture for the full-resolution original.", ""]
            for i in range(0, len(pics), 3):
                row = pics[i:i + 3]
                out += ["| " + " | ".join(self.work_thumb(w) for w in row) + " |",
                        "|" + "---|" * len(row),
                        "| " + " | ".join(f"**{w['title']}**<br>{self.by_id[w['creator']]['name']}, {w['year']}" for w in row) + " |", ""]
            write(ROOT / P / "GALLERY.md", "\n".join(out))
        self.build_readme()
        self.build_csv()

    def build_readme(self):
        L, P = self.L, self.path
        hero = self.meta.get("hero_file")
        n_img = sum(1 for w in self.works if w.get("image_file") in self.images)
        n_por = sum(1 for c in self.creators if c.get("portrait_file") in self.images)
        out = [f"# {self.title}", ""]
        if hero and hero in self.images:
            out += [f'<img src="{self.img(hero, 1280)}" width="100%" alt="{self.title}">', "",
                    f"<sub>{self.meta.get('hero_caption', '')} · [Wikimedia Commons]({self.commons_page(hero)})</sub>", ""]
        out += [self.meta.get("intro", ""), "",
                f"**{len(self.creators)} {L['creators'].lower()}** · **{len(self.works)} {L['works'].lower()}** "
                f"({n_img} with images) · **{len(self.movements)} {L['movements'].lower()}** · {n_por} portraits", "",
                "## Browse", "",
                f"| | |", "|---|---|",
                f"| [**{L['movements']}**](#{anchor(L['movements'])}) | Each {L['movement'].lower()} in order, with its people and key {L['works'].lower()} |",
                f"| [**{L['creators']}**](CREATORS.md) | Everyone, by date of birth, with a page each |",
                f"| [**Timeline**](TIMELINE.md) | Every {L['work'].lower()} in chronological order |"]
        if (ROOT / P / "GALLERY.md").exists() or any(w.get("image_file") in self.images for w in self.works):
            out += [f"| [**Gallery**](GALLERY.md) | All the pictures on one page |"]
        out += [f"| [`data/`](data/) | The same information as JSON and CSV |", "", f"## {L['movements']}", ""]
        for i, m in enumerate(self.movements, 1):
            out += [f"{i}. [{m['name']}](movements/{m['id']}.md) · {m.get('dates', '')}"]
        extra = ROOT / P / "README.extra.md"
        if extra.exists():
            out += ["", extra.read_text(encoding="utf-8").strip()]
        out += ["", "---", f"[← {TRAD_TITLE}](../README.md) · [All people](../PEOPLE.md) · [Timeline](../TIMELINE.md)"]
        write(ROOT / P / "README.md", "\n".join(out))

    def build_csv(self):
        if CHECK_ONLY:
            return
        with open(ROOT / self.path / "data" / "works.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["year", "title", "creator", "type", "location", "description", "image"])
            for w in self.works:
                wr.writerow([w["year"], w["title"], self.by_id.get(w["creator"], {}).get("name", w["creator"]),
                             w.get("type", ""), w.get("location", ""), w.get("description", ""),
                             self.commons_page(w["image_file"]) if w.get("image_file") else ""])


# --------------------------------------------------------------- tradition ---
def build_tradition(tdir, subjects):
    global PERIODS, TRAD_TITLE
    TRAD_TITLE = load(ROOT / tdir / "tradition.json", {"title": tdir.title()})["title"]
    periods = load(ROOT / tdir / "periods.json", [])
    PERIODS = {p["id"]: p for p in periods}
    for s in subjects:
        for m in s.movements:
            if m.get("period") and m["period"] not in PERIODS:
                warn(f"{s.path}: movement {m['id']} has unknown period {m['period']}")
    if CHECK_ONLY:
        return
    for s in subjects:
        if s.generate:
            s.build_pages()
    # people index
    people = {}
    for s in subjects:
        for c in s.creators:
            people.setdefault(c["id"], []).append((s, c))
    out = [f"# People of {TRAD_TITLE.replace('The ', 'the ')}", "",
           f"Everyone in every section, {len(people)} people in all, ordered by date of birth. "
           "People who appear in more than one section are listed once.", "",
           "| | Name | Life | Sections |", "|---|---|---|---|"]
    for pid, entries in sorted(people.items(), key=lambda kv: born_year(kv[1][0][1])):
        s0, c0 = next(((s, c) for s, c in entries if c.get("portrait_file") in s.images), entries[0])
        links = ", ".join(f"[{s.title}]({rel(tdir, s.creator_page(pid))})" for s, c in entries)
        out += [f"| {s0.portrait_thumb(c0, tdir, 50)} | **{c0['name']}** | {c0.get('born', '')} – {c0.get('died', '')} | {links} |"]
    write(ROOT / tdir / "PEOPLE.md", "\n".join(out))
    # combined timeline
    allw = sorted([(w, s) for s in subjects for w in s.works], key=lambda x: x[0].get("sort", 0))
    out = [f"# Timeline: {TRAD_TITLE}", "", "Every work in every section, in one chronology.", ""]
    cur = None
    for w, s in allw:
        lab = century_label(w.get("sort", 0))
        if lab != cur:
            cur = lab
            out += ["", f"## {lab}", "", "| Image | Year | Work | By | Section |", "|---|---|---|---|---|"]
        c = s.by_id.get(w["creator"], {"name": w["creator"]})
        out += [f"| {s.work_thumb(w)} | {w['year']} | **{w['title']}** | [{c['name']}]({rel(tdir, s.creator_page(w['creator']))}) | {s.title} |"]
    write(ROOT / tdir / "TIMELINE.md", "\n".join(out))
    # period pages
    for i, p in enumerate(periods):
        here = f"{tdir}/periods"
        out = [f"# {p['name']}", "", f"*{p['dates']}*", "", p["summary"], ""]
        for s in subjects:
            movs = [m for m in s.movements if m.get("period") == p["id"]]
            ws = [w for w in s.works if p["start"] <= w.get("sort", 0) < p["end"]]
            if not movs and not ws:
                continue
            out += [f"## {s.title}", ""]
            if movs and s.generate:
                out += ["**" + s.L["movements"] + ":** " + " · ".join(f"[{m['name']}]({rel(here, s.path + '/movements/' + m['id'] + '.md')})" for m in movs), ""]
            elif movs:
                out += ["**" + s.L["movements"] + ":** " + " · ".join(m["name"] for m in movs), ""]
            for w in ws[:40]:
                c = s.by_id.get(w["creator"], {"name": w["creator"]})
                out += [f"- {w['year']} · **{w['title']}**, [{c['name']}]({rel(here, s.creator_page(w['creator']))})"]
            out += [""]
        nav = []
        if i > 0:
            nav.append(f"[← {periods[i-1]['name']}]({periods[i-1]['id']}.md)")
        nav.append(f"[{TRAD_TITLE}](../README.md)")
        if i < len(periods) - 1:
            nav.append(f"[{periods[i+1]['name']} →]({periods[i+1]['id']}.md)")
        out += ["---", " · ".join(nav)]
        write(ROOT / here / f"{p['id']}.md", "\n".join(out))
    # tradition README
    meta = load(ROOT / tdir / "tradition.json", {"title": tdir.title(), "intro": ""})
    out = [f"# {meta['title']}", "", meta.get("intro", ""), "", "## Sections", "",
           "| | Section | People | Works | Images |", "|---|---|---|---|---|"]
    for s in subjects:
        hero = s.meta.get("hero_file")
        th = f'<img src="{s.img(hero, 330)}" width="120">' if hero in s.images else ""
        n_img = sum(1 for w in s.works if w.get("image_file") in s.images) + sum(1 for c in s.creators if c.get("portrait_file") in s.images)
        out += [f"| {th} | [**{s.title}**]({s.slug}/README.md)<br>{s.meta.get('tagline', '')} | {len(s.creators)} | {len(s.works)} | {n_img} |"]
    out += ["", "## Eras", "", "The same eras are used in every section, so you can see what was happening across the arts and ideas at once.", ""]
    for p in periods:
        out += [f"- [**{p['name']}**](periods/{p['id']}.md) · {p['dates']}"]
    out += ["", "## Across sections", "", f"- [**People**](PEOPLE.md): all {len(people)} people, with links to every section they appear in",
            "- [**Timeline**](TIMELINE.md): every work from every section in one chronology", "", "---", "[← World canons](../README.md)"]
    write(ROOT / tdir / "README.md", "\n".join(out))
    return {"people": len(people), "works": len(allw),
            "images": sum(1 for w, s in allw if w.get("image_file") in s.images)}


PERIODS = {}
TRAD_TITLE = ""
PEOPLE_SUBJECTS = defaultdict(list)


def main():
    traditions = sorted(p.parent.name for p in ROOT.glob("*/periods.json"))
    stats = {}
    for t in traditions:
        subjects = [Subject(f"{t}/{p.parent.parent.name}") for p in sorted((ROOT / t).glob("*/data/subject.json"))]
        subjects.sort(key=lambda s: s.meta.get("order", 99))
        PEOPLE_SUBJECTS.clear()
        for s in subjects:
            for c in s.creators:
                PEOPLE_SUBJECTS[c["id"]].append(s)
        stats[t] = build_tradition(t, subjects)
    for w in WARN:
        print("warning:", w)
    print(f"Built {', '.join(f'{t}: {v}' for t, v in stats.items())}. {len(WARN)} warnings.")


if __name__ == "__main__":
    main()
