"""Join parts rendered separately (the way a team or a long film is built: each part its own page and render) into one film.

Parts are joined with a short dissolve (video xfade, audio acrossfade). Each part's cues (<part>.cues.json from the renderer) are moved to
the whole film's clock and written to <out>.cues.json, so the sound is mixed once over the whole.  Parts must share size and fps.
"""
import json
import subprocess
from pathlib import Path

from .util import duration as _probe




def join(parts, out, dissolve=0.5):
    parts = [Path(p) for p in parts]
    durs = [_probe(p) for p in parts]
    ins = [x for p in parts for x in ("-i", str(p))]
    f, starts, t = [], [0.0], 0.0
    chain = "[0:v]"
    for i in range(1, len(parts)):
        t += durs[i - 1] - dissolve                         # part i starts `dissolve` before part i-1 ends
        starts.append(t)
        f.append(f"{chain}[{i}:v]xfade=transition=fade:duration={dissolve}:offset={t:.3f}[v{i}]")
        chain = f"[v{i}]"
    cmd = ["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(f) if f else "null", "-map", chain if f else "0:v",
           "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", str(out)]
    if not f:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(parts[0]), "-c", "copy", str(out)]
    subprocess.run(cmd, check=True)
    cues = []
    for p, s in zip(parts, starts):
        c = p.with_suffix(".cues.json")
        if c.exists():
            cues += [{**h, "t": round(h["t"] + s, 3)} for h in json.loads(c.read_text())]
    if cues:
        Path(out).with_suffix(".cues.json").write_text(json.dumps(sorted(cues, key=lambda h: h["t"]), indent=1))
    print(f"joined {len(parts)} parts -> {out} ({_probe(out):.2f} s; seams at {[round(s, 2) for s in starts[1:]]})")
