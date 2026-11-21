"""Notes: what the person who owns the film said about it, stored verbatim, and ticked before a cut passes the gate.

A note is the person's own words (never paraphrased: `means` holds your reading). It binds every later film of the project. Before a gate, each note is
ticked against that exact film file (its sha256) with where it is answered: a timestamp ("0:04", "4.5 s") or "shot 3". A re-render or a music swap
changes the file, so the ticks are made again. `unticked()` is what the gate refuses on.
"""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

WHERE = re.compile(r"(\d+:\d{2}|\d+(?:\.\d+)?\s*s\b|\bt\s*=\s*\d|\bshot\s*#?\d+|\bframe\s*\d+)", re.I)
DEFAULT = "film-notes.json"


def _load(store):
    p = Path(store)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"notes": []}


def _save(store, d):
    Path(store).write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def add(store, words, source, means=""):
    d = _load(store)
    nid = f"N{len(d['notes']) + 1}"
    d["notes"].append({"id": nid, "words": words, "source": source, "means": means, "at": dt.datetime.now().isoformat(timespec="seconds"), "ticks": {}})
    _save(store, d)
    return nid


def tick(store, nid, film, where):
    if not WHERE.search(where or ""):
        raise SystemExit(f"--where must point into the film: a time like 0:42 or 4.5 s, or 'shot 7' (got {where!r})")
    d = _load(store)
    n = next((x for x in d["notes"] if x["id"].lower() == nid.lower()), None)
    if n is None:
        raise SystemExit(f"no note {nid}")
    if not Path(film).exists():
        raise SystemExit(f"film not found: {film}")
    n["ticks"][file_hash(film)] = {"film": Path(film).name, "where": where, "at": dt.datetime.now().isoformat(timespec="seconds")}
    _save(store, d)


def unticked(store, film):
    h = file_hash(film)
    return [n for n in _load(store)["notes"] if h not in n["ticks"]]


def listing(store, film=None):
    d = _load(store)["notes"]
    h = file_hash(film) if film else None
    lines = []
    for n in d:
        state = "" if h is None else ("  [ticked: " + n["ticks"][h]["where"] + "]" if h in n["ticks"] else "  [OPEN for this film]")
        lines.append(f'{n["id"]} ({n["source"]}): "{n["words"]}"{state}' + (f'\n     reading: {n["means"]}' if n["means"] else ""))
    return "\n".join(lines) or "no notes yet"
