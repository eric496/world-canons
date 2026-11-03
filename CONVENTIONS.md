# Conventions

How this repo is organised and how to add to it. Everything in a section is generated from JSON, so the data files are the source of truth.

## Layout

```
<tradition>/                      e.g. western/
  periods.json                    shared eras for every section in the tradition
  tradition.json                  title + intro for the tradition README
  <subject>/                      e.g. western/art/
    data/subject.json             title, labels, intro, hero image
    data/creators.json            people
    data/works.json               their works
    data/movements.json           movements / schools / styles, each tied to an era
    data/image_urls.json          verified image URLs (written by scripts/wm.py)
    README.extra.md               optional extra text appended to the generated README
scripts/build.py                  builds all pages:  python3 scripts/build.py
scripts/wm.py                     the only way to talk to Wikipedia / Wikimedia Commons
```

Generated (never edit by hand): `<subject>/README.md`, `CREATORS.md`, `TIMELINE.md`, `GALLERY.md`, `creators/`, `movements/`, `data/works.csv`, and the tradition-level `README.md`, `PEOPLE.md`, `TIMELINE.md`, `periods/`.

A section can set `"generate_pages": false` in `subject.json` to keep hand-written pages (philosophy does this). It still provides `creators.json`, `works.json` and `movements.json`, and each creator then has a `"page"` path relative to the section folder, so the shared people index, timeline and era pages can link to it.

## Data format

**subject.json**
```json
{"title": "Music", "order": 5, "tagline": "One line for the tradition README",
 "hero_file": "Commons file name.jpg", "hero_caption": "What the hero picture shows",
 "labels": {"creator": "Composer", "creators": "Composers", "work": "Work", "works": "Works",
            "movement": "Era/School", "movements": "Eras & schools", "location": "Premiere / first published"},
 "intro": "Two or three sentences for the top of the section README."}
```

**movements.json** (in chronological order)
```json
{"id": "baroque-music", "name": "Baroque", "dates": "c. 1600–1750", "period": "seventeenth-century",
 "summary": "2–4 sentences.", "image_file": "optional Commons file", "image_caption": "optional"}
```
`period` must be an id from `<tradition>/periods.json`.

**creators.json**
```json
{"id": "bach", "name": "Johann Sebastian Bach", "born": "1685", "died": "1750", "sort": 1685,
 "birthplace": "Eisenach, Saxe-Eisenach", "deathplace": "Leipzig", "nationality": "German",
 "movements": ["baroque-music"],
 "bio": "One or two sentence summary.",
 "bio_full": ["Paragraph on life and career.", "Paragraph on style, ideas and legacy."],
 "portrait_file": "Commons file name.jpg", "portrait_caption": "Elias Gottlob Haussmann, portrait of Bach, 1746",
 "links": [{"name": "Scores on IMSLP", "url": "https://imslp.org/..."}]}
```
`sort` is a number (negative for BC) and is required when `born` is not a plain year. For BC people write `"born": "c. 480 BC"`.

**works.json**
```json
{"title": "Mass in B minor", "creator": "bach", "year": "1733–49", "sort": 1749, "type": "Choral mass",
 "location": "Where it is / first performed / first published",
 "note": "One-line summary.", "description": "A full paragraph introduction.",
 "image_file": "Commons file name", "image_caption": "e.g. Autograph score, first page of the Kyrie",
 "museum_name": "MoMA", "museum_url": "https://...", "links": [{"name": "...", "url": "..."}]}
```
Use `museum_name` and `museum_url` only for works still under copyright: the official page where the work can be seen.

### People ids are shared across sections

The same person must have the **same `id` in every section**, so that Michelangelo the artist, architect and poet is one person in `PEOPLE.md`. Use the plain surname slug when it is unambiguous (`goethe`, `newton`, `aquinas`), `firstname-surname` when it is not (`francis-bacon`, `roger-bacon`), and **reuse any id that already exists**: check `western/*/data/creators.json` first. Established ids include `leonardo`, `michelangelo`, `raphael`, `bernini`, `brunelleschi`, `giotto`, `durer`, `blake`, `rossetti`, `plato`, `aristotle`.

## Images

- **Wikimedia Commons only.** Use files hosted on Commons; a file that lives only on en.wikipedia is non-free and must not be used. `wm.py` reports this as `"commons": false`.
- **Portraits of people are artworks, never photographs.** Use a painted, drawn, engraved or sculpted portrait, coin or medal that is in the public domain. Do not use photographs of people, even old ones. A 20th-century person with no such portrait simply has no portrait.
- **Copyrighted works are not reproduced.** If the creator died less than about 70 years ago, or the work is otherwise still protected, give `museum_name`/`museum_url` instead of an image. Commons hosting is the test of freedom for everything else.
- **Pictures for non-visual subjects:** manuscript pages, autograph scores, first-edition title pages, early printed illustrations, premiere posters, instruments, buildings and places, paintings of the people or events. Say what the picture shows in `image_caption`.
- Workflow: find a file with `python3 -I scripts/wm.py lead "Wikipedia article title"` or `search "query"`, then record it with `python3 -I scripts/wm.py add western/<subject> "File name.jpg"`. Only files present in `image_urls.json` are displayed.

## Wikimedia rate limits

Wikimedia throttles our network address. `wm.py` shares one global throttle and cache across every process. **Never fetch Wikipedia or Commons any other way** (no curl, no parallel scripts). A 429 makes everyone pause for 45 seconds automatically. Batch work in a single loop rather than many separate commands.

## Writing

- The voice is plain, warm and accurate, for a curious general reader. No hype.
- `bio_full`: two paragraphs, first life and career, then style, ideas and legacy. `description`: one solid paragraph covering context, what it is or what happens, how it works or is made, why it matters, and later history.
- Flag genuine scholarly disputes ("debated", "traditionally attributed") rather than flattening them. Use "c." for uncertain dates.
- Quotations: only from texts long in the public domain, and under 15 words. Otherwise paraphrase.
- Do not invent facts, dates, locations or URLs. If unsure, leave it out.

## Checking your work

Run `python3 scripts/build.py --check`. It prints a warning for every unknown id, missing description or unregistered image. Aim for zero warnings in your section.

## Non-Western traditions

- **Names:** use the standard English romanization (pinyin for Chinese, Hepburn with macrons for Japanese, Revised Romanization for Korean, IAST for Sanskrit, and so on) in `name`. Put the original script in an optional `name_native` field, for example `"name_native": "李白"`. Movements can carry `name_native` too.
- **Dates and names:** give family name first where that is the convention (Li Bai, Katsushika Hokusai). Write dynasty and era names the standard way (Tang, Edo, Joseon).
- **People ids are global.** Someone who already exists in another tradition keeps the same id. For example, `avicenna` in Western science stays `avicenna` in the Islamic tradition.
