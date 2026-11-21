"""A film project in one folder, started with `film.py new` and built with `film.py make`.

films/<slug>/
  film.json        what the film says (name, promise, points, number, action, url, music ...): edit this, run make again
  film.html        the page (copied from academy/template.html): edit it for anything film.json cannot say
  plan.json        sound plan: bpm, which music file, where the drop is
  assets/          screen recordings turned into frames (`film.py import-recording`)
  builds/vN.mp4, vN-final.mp4   every make is a new numbered build; the gate compares each with the one before
  film-notes.json the owner's notes, verbatim (`film.py note`)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import gate as G
from . import mix as M
from . import notes as N
from . import placeholder_audio as PA
from . import render as R
from .util import duration

HERE = Path(__file__).resolve().parent
BAR_S = 2.0           # 120 bpm, 4 beats: one bar is 2 s; scene lengths in the template are whole or half bars


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "film"


def split_hook(promise):
    """The promise in two lines of about equal length (the first is set in the accent colour)."""
    w = promise.replace(".", "").split()
    if len(w) < 2:
        return [promise, ""]
    best = min(range(1, len(w)), key=lambda i: abs(len(" ".join(w[:i])) - len(" ".join(w[i:]))))
    tail = " ".join(w[best:])
    return [" ".join(w[:best]), tail + ("." if promise.rstrip().endswith(".") else "")]


def parse_points(text):
    out = []
    for item in [x.strip() for x in (text or "").split("|") if x.strip()]:
        k, _, v = item.partition("=")
        out.append([k.strip(), v.strip()])
    return out


def write_config(d):
    cfg = json.loads((d / "film.json").read_text(encoding="utf-8"))
    (d / "film.config.js").write_text("window.FILM = " + json.dumps(cfg, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    return cfg


def new(a):
    d = Path(a.dir or Path("films") / slug(a.name))
    if d.exists() and any(d.iterdir()):
        raise SystemExit(f"{d} already exists and is not empty: pick another --dir, or edit {d}/film.json and run `film.py make {d}`")
    d.mkdir(parents=True, exist_ok=True)
    cfg = {"name": a.name, "promise": a.promise, "hook": a.hook.split("|") if a.hook else split_hook(a.promise), "tagline": a.tagline or "",
           "points": parse_points(a.points), "slam": a.slam or "", "action": a.action or "", "url": a.url or "", "accent": a.accent, "recording": None}
    if a.number:
        v = re.match(r"\s*([\d.]+)\s*(.*)", a.number)
        cfg["number"] = {"value": float(v.group(1)), "suffix": v.group(2), "label": a.number_label or ""}
    (d / "film.json").write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.copy(HERE / "template.html", d / "film.html")
    (d / "plan.json").write_text(json.dumps({"bpm": 120, "beats_per_bar": 4, "music_file": a.music, "start_bar": 0, "drop_bar": a.drop_bar,
                                             "note": "music_file is your own track (leave null for the generated placeholder); with a track, give its bpm, "
                                                     "the bar where it starts and the bar of its drop/last chord (drop_bar): the film's last 2 bars play from there"}, indent=1))
    if a.recording:
        import_recording(a.recording, d, "app", seconds=a.rec_seconds)
    print(f"started {d}\n  say what the film says in {d}/film.json, then:  python film.py make {d}")
    return d


def import_recording(src, d, name="app", fps=30, start=0.0, seconds=6.0, width=1500):
    """A screen recording (any format ffmpeg reads) -> JPEG frames the page can show at any time. Chromium as shipped by Playwright cannot play H.264,
    and frames make every seek exact. Updates film.json to show it."""
    d = Path(d)
    out = d / "assets" / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(seconds), "-i", str(src), "-an",
                    "-vf", f"fps={fps},scale={2 * width}:-2:flags=lanczos", "-q:v", "3", str(out / "%05d.jpg")], check=True)
    n = len(list(out.glob("*.jpg")))
    if n == 0:
        raise SystemExit(f"no frames came out of {src} (start {start}s, {seconds}s): is the file shorter than the start?")
    cfg = json.loads((d / "film.json").read_text(encoding="utf-8"))
    cfg["recording"] = {"dir": f"assets/{name}", "fps": fps, "n": n, "bars": max(1, -(-int(n / fps * 100) // int(BAR_S * 100))), "width": width}
    (d / "film.json").write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{n} frames in {out} ({n / fps:.1f} s); film.json now shows it as the proof scene ({cfg['recording']['bars']} bars)")


def _merge(path, key, val):
    j = json.loads(path.read_text()) if path.exists() else {}
    j[key] = val
    path.write_text(json.dumps(j, indent=1))


def make(d, fps=30, size=(1280, 720), workers=2):
    """film.json -> render -> sound -> gate. Returns the gate's exit code (0 pass, 5 stop, 6 open notes)."""
    d = Path(d)
    cfg = write_config(d)
    (d / "builds").mkdir(exist_ok=True)
    nums = [int(m.group(1)) for p in (d / "builds").glob("v*.mp4") if (m := re.fullmatch(r"v(\d+)", p.stem))]
    v = max(nums, default=0) + 1
    pic = d / "builds" / f"v{v}.mp4"
    prev = d / "builds" / f"v{v - 1}-final.mp4"
    dur = R.render(d / "film.html", pic, fps, workers, size)
    plan = json.loads((d / "plan.json").read_text())
    bar = plan.get("beats_per_bar", 4) * 60.0 / plan["bpm"]
    bars = max(1, round(dur / bar))
    audio = d / "audio"
    if not (audio / "impact.wav").exists():
        PA.sfx(audio)
    own = Path(d / "sfx")
    sfx = own if own.exists() else audio
    mf = plan.get("music_file")
    if mf:
        drop = plan.get("drop_bar")
        segs = ([{"track_bar": plan.get("start_bar", 0), "film_bar": 0, "bars": bars - 2}, {"track_bar": drop, "film_bar": bars - 2, "bars": 2}]
                if drop is not None and bars >= 4 else [{"track_bar": plan.get("start_bar", 0), "film_bar": 0, "bars": bars}])
        track = mf
    else:
        track = audio / f"track{bars}.wav"
        if not track.exists():
            PA.track(audio, bars).replace(track)
        segs = [{"track_bar": 0, "film_bar": 0, "bars": bars}]
    final = d / "builds" / f"v{v}-final.mp4"
    cues = json.loads(pic.with_suffix(".cues.json").read_text()) if pic.with_suffix(".cues.json").exists() else []
    M.mix(pic, final, {**plan, "music": segs, "hits": []}, str(track), str(sfx), cues)
    _merge(d / "timeline.json", final.stem, json.loads(pic.with_suffix(".timeline.json").read_text()))
    _merge(d / "cards.json", final.stem, json.loads(pic.with_suffix(".cards.json").read_text()))
    cmd = [sys.executable, str(HERE.parent / "film.py"), "gate", "--film", str(final), "--cards", str(d / "cards.json"), "--timeline", str(d / "timeline.json"),
           "--bpm", str(plan["bpm"]), "--notes", str(d / N.DEFAULT)]
    if prev.exists():
        cmd += ["--against", str(prev)]
    rc = subprocess.run(cmd).returncode
    print(f"\nfilm: {final}   (build {v}{', gated against v' + str(v - 1) if prev.exists() else ', the first build: nothing to compare with yet'})")
    print(f"look at it: python film.py sheet {final} {d}/sheet.jpg   (one frame per second on one image)")
    print(f"say what is wrong in the owner's own words: python film.py note \"<their words>\" --source \"who, date\" --store {d}/{N.DEFAULT}")
    return rc
