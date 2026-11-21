"""The gate: numbers a cut must pass before anyone is shown it.

measure(film)     mean shot length, share of static frames (frame diff), words per card (tesseract OCR, or a cards file), loudness
precheck(...)     the new cut against the previous cut: slower or more static fails; more words per card warns
cut_checks(...)   cut craft against library limits (data/cut-limits.json): bursts of tiny shots, cuts on every beat
Needs only ffmpeg/ffprobe and Python; OCR is optional.
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .util import probe

DATA = Path(__file__).resolve().parents[1] / "data"
SLOWER = 1.05        # the new mean shot may be at most 5% longer than the previous cut's
MORE_STATIC = 0.03   # the static share may be at most 0.03 above the previous cut's
MIN_CUTS = 8         # shot length is a hard stop only when both films show this many cuts (or a timeline): fewer means the detector is guessing
WORDS_WARN = 1.25
MF, W, H = 12, 80, 45  # motion is read at 12 fps on an 80x45 grey picture


def _run(cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True)


def scene_cuts(film, thr=0.3):
    """Scene changes by ffmpeg's scene score. It barely sees eased or animated transitions: pass a timeline when the real cuts are known."""
    e = _run(["ffmpeg", "-hide_banner", "-i", film, "-vf", f"select='gt(scene,{thr})',showinfo", "-an", "-f", "null", "-"]).stderr.decode(errors="replace")
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", e)]


def timeline_cuts(film, timeline_file):
    """{film file name or stem: [cut seconds]}: the director's own scene list. None when this film is not in the file."""
    if not timeline_file:
        return None
    j = json.loads(Path(timeline_file).read_text(encoding="utf-8"))
    film = Path(film)
    for k in (film.name, film.stem, str(film)):
        if k in j:
            return [float(x) for x in j[k]]
    return None


def motion(film, cuts, dur):
    """Mean |change| between neighbouring frames (0-255 grey levels) at 12 fps, cuts left out. static_share = share of steps under 0.35."""
    raw = _run(["ffmpeg", "-v", "error", "-i", film, "-an", "-vf", f"fps={MF},scale={W}:{H}:flags=area,format=gray", "-f", "rawvideo", "-"]).stdout
    n = len(raw) // (W * H)
    if n < 3:
        return {"motion_mean": None, "static_share": None}
    frames = [raw[i * W * H:(i + 1) * W * H] for i in range(n)]
    try:
        import numpy as np
        a = np.frombuffer(raw[:n * W * H], np.uint8).reshape(n, W * H).astype("float32")
        d = np.abs(np.diff(a, axis=0)).mean(1).tolist()
    except ImportError:
        d = [sum(abs(x - y) for x, y in zip(frames[i], frames[i + 1])) / (W * H) for i in range(n - 1)]
    at = {int(round(c * MF)) - 1 for c in cuts}
    keep = [x for k, x in enumerate(d) if k not in at and k + 1 not in at and x < 40] or d
    return {"motion_mean": round(sum(keep) / len(keep), 2), "static_share": round(sum(x < 0.35 for x in keep) / len(keep), 2)}


def loud(film):
    e = _run(["ffmpeg", "-hide_banner", "-i", film, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr.decode(errors="replace")
    tail = e[e.rfind("Summary:"):]
    g = lambda k: (lambda m: float(m.group(1)) if m else None)(re.search(k + r":\s+(-?[\d.]+)", tail))
    return {"lufs": g("I"), "lra": g("LRA"), "peak_dbfs": g("Peak")}


def card_words(film, cuts, dur, cards_file=None):
    """(mean words per card, how). From a cards file {film name or stem: [card texts]}, else tesseract on the middle frame of each shot, else (None, why)."""
    film = Path(film)
    if cards_file:
        j = json.loads(Path(cards_file).read_text(encoding="utf-8"))
        for k in (film.name, film.stem, str(film)):
            if k in j:
                cards = j[k]
                return (sum(len(str(c).split()) for c in cards) / len(cards) if cards else None), "cards file"
    if not shutil.which("tesseract"):
        return None, "no cards file and tesseract is not installed (optional: apt install tesseract-ocr)"
    bounds = [0.0] + list(cuts) + [dur]
    mids = [(a + b) / 2 for a, b in zip(bounds[:-1], bounds[1:]) if b - a > 0.2][:36]
    words = []
    with tempfile.TemporaryDirectory() as td:
        for i, t in enumerate(mids):
            png = Path(td) / f"{i}.png"
            _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", film, "-frames:v", "1", png])
            txt = _run(["tesseract", png, "stdout", "--psm", "11"]).stdout.decode(errors="replace")
            words.append(len([w for w in re.findall(r"[A-Za-z0-9$€£%][\w'’.,%-]*", txt) if len(w) > 1 or w.isalnum()]))
    return (sum(words) / len(words) if words else None), "tesseract OCR, one frame per shot"


def measure(film, cards=None, timeline=None):
    film = Path(film)
    if not film.exists():
        raise SystemExit(f"film not found: {film}")
    dur, w, h, fps = probe(film)
    tl = timeline_cuts(film, timeline)
    cuts = [x for x in tl if 0 < x < dur] if tl is not None else scene_cuts(film)
    m = motion(film, cuts, dur)
    wpc, how = card_words(film, cuts, dur, cards)
    r = {"file": str(film), "name": film.stem, "seconds": round(dur, 2), "size": f"{w}x{h}", "cuts": len(cuts), "cut_times": [round(x, 2) for x in cuts],
         "cuts_how": "timeline" if tl is not None else "scene detector", "mean_shot_s": round(dur / (len(cuts) + 1), 2), "static_share": m["static_share"],
         "motion_mean": m["motion_mean"], "words_per_card": None if wpc is None else round(wpc, 1), "words_how": how}
    r.update(loud(film))
    return r


def precheck(new, prev):
    """(fails, warns) of the new cut against the previous one. A number that could not be measured is a failure, not a pass."""
    fails, warns = [], []
    if new["mean_shot_s"] > prev["mean_shot_s"] * SLOWER:
        msg = f"slower: mean shot {new['mean_shot_s']} s against {prev['mean_shot_s']} s in the previous cut (limit {prev['mean_shot_s'] * SLOWER:.2f} s)"
        if min(new["cuts"], prev["cuts"]) >= MIN_CUTS or new["cuts_how"] == prev["cuts_how"] == "timeline":
            fails.append(msg)
        else:
            warns.append(msg + f" (only {new['cuts']} and {prev['cuts']} cuts detected, under {MIN_CUTS}: not trusted as a stop; pass --timeline with the real cut times)")
    if new["static_share"] is None or prev["static_share"] is None:
        fails.append("static share could not be measured (film too short or unreadable)")
    elif new["static_share"] > prev["static_share"] + MORE_STATIC:
        fails.append(f"more static: {new['static_share']:.0%} of frames hold still against {prev['static_share']:.0%} in the previous cut")
    nw, pw = new.get("words_per_card"), prev.get("words_per_card")
    if nw is not None and pw is not None and nw > pw * WORDS_WARN:
        warns.append(f"more words per card: {nw} against {pw} in the previous cut")
    return fails, warns


def vs_refs(new, refs):
    """Warnings only: a reference is a yardstick, not a pass mark."""
    warns = []
    if refs:
        slowest = max(r["mean_shot_s"] for r in refs)
        if new["mean_shot_s"] > slowest:
            warns.append(f"slower than every reference (mean shot {new['mean_shot_s']} s, slowest reference {slowest} s)")
        if new["static_share"] is not None and refs and new["static_share"] > max(r["static_share"] or 0 for r in refs) + MORE_STATIC:
            warns.append(f"more static than every reference ({new['static_share']:.0%})")
        wp = [r["words_per_card"] for r in refs if r["words_per_card"] is not None]
        if wp and new["words_per_card"] is not None and new["words_per_card"] > max(wp) * WORDS_WARN:
            warns.append(f"more words per card ({new['words_per_card']}) than any reference ({max(wp)})")
    if new.get("lufs") is not None and abs(new["lufs"] + 14) > 1.5:
        warns.append(f"loudness {new['lufs']} LUFS: platforms normalise to about -14; run the mixer")
    return warns


def cut_checks(m, bpm=None):
    """Cut craft against data/cut-limits.json. Returns (fails, warns). Skipped (said) under min_cuts cuts."""
    lim = json.loads((DATA / "cut-limits.json").read_text(encoding="utf-8"))
    if m["cuts"] < lim["min_cuts"]:
        return [], [f"cut craft not checked: {m['cuts']} cuts, the limits need {lim['min_cuts']}+ (a short film: nothing to check)"]
    t = [0.0] + m["cut_times"] + [m["seconds"]]
    shots = [b - a for a, b in zip(t[:-1], t[1:])]
    fails, warns = [], []
    run = best = 0
    for s in shots:
        run = run + 1 if s < lim["no_burst"]["under_s"] else 0
        best = max(best, run)
    if best > lim["no_burst"]["max_run"]:
        fails.append(f"a burst of {best} shots in a row under {lim['no_burst']['under_s']} s: {lim['no_burst']['why']}")
    share = sum(s < lim["hold_floor"]["under_s"] for s in shots) / len(shots)
    if share > lim["hold_floor"]["max_share"]:
        warns.append(f"{share:.0%} of shots under {lim['hold_floor']['under_s']} s: {lim['hold_floor']['why']}")
    if bpm:
        beat, tol = 60.0 / bpm, lim["cut_every_beat"]["tolerance_s"]
        gaps = [b - a for a, b in zip(m["cut_times"][:-1], m["cut_times"][1:])]
        run = best = 0
        for g in gaps:
            run = run + 1 if abs(g - beat) <= tol else 0
            best = max(best, run)
        if best + 1 > lim["cut_every_beat"]["max_run"]:
            fails.append(f"{best + 1} cuts in a row one beat apart: {lim['cut_every_beat']['why']}")
    return fails, warns


def table(rows):
    head = ["film", "seconds", "cuts", "mean shot s", "static share", "words/card", "LUFS", "peak dBFS"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in [r.get("label", r["name"]), r["seconds"], r["cuts"], r["mean_shot_s"],
                     "n/a" if r["static_share"] is None else f"{r['static_share']:.0%}", "n/a" if r["words_per_card"] is None else r["words_per_card"],
                     r.get("lufs"), r.get("peak_dbfs")]) + " |")
    return "\n".join(lines)
