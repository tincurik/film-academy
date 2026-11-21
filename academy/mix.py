"""Sound for a film: music cut on bar lines, sound effects on their frames, loudness to -14 LUFS / -1 dBTP (two-pass loudnorm), then measured.

Everything is in a plan (json):
{
  "bpm": 120, "beats_per_bar": 4,
  "music": [ {"track_bar": 2, "film_bar": 0, "bars": 3},       # take 3 bars of the track starting at its bar 2, put them at film bar 0
             {"track_bar": 8, "film_bar": 3, "bars": 2} ],     # then jump to the track's bar 8 (its drop, its last chord) for film bars 3-4
  "track_offset_s": 0.0,                                        # where the track's bar 0 starts (seconds into the file)
  "hits": [ {"t": 2.0, "sfx": "impact", "db": -6} ],            # extra hits; <sfx dir>/<name>.wav; the page's own cues (film.cues.json) are added
  "fade_in_s": 0.6, "fade_out_s": 1.3
}
Cutting on bar lines means every jump lands on a downbeat, so the music never stumbles at a cut. With no --music the mix is the hits alone.
"""
import json
import re
import subprocess

from .util import duration
from pathlib import Path


def run(cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True)


def loudness(path):
    e = run(["ffmpeg", "-hide_banner", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr
    tail = e[e.rfind("Summary:"):]
    g = lambda k: float(re.search(k + r":\s+(-?[\d.]+)", tail).group(1))
    return {"lufs": g("I"), "lra": g("LRA"), "peak_dbfs": g("Peak")}




def mix(film, out, plan, music=None, sfx_dir=None, cues=None):
    film, out = str(film), Path(out)
    dur = duration(film)
    bar = plan.get("beats_per_bar", 4) * 60.0 / plan["bpm"]
    off = plan.get("track_offset_s", 0.0)
    ins, f, n = ["-i", film], [], 1
    mus = []
    if music and plan.get("music"):
        for seg in plan["music"]:
            ts, len_s = off + seg["track_bar"] * bar, seg["bars"] * bar
            ins += ["-ss", f"{ts:.3f}", "-t", f"{len_s + .08:.3f}", "-i", music]
            f.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo[m{n}]")
            mus.append(f"[m{n}]")
            n += 1
        fi, fo = plan.get("fade_in_s", 0.6), plan.get("fade_out_s", 1.3)
        chain = mus[0]
        for k, m in enumerate(mus[1:], 1):                       # joins sit on bar lines: a short crossfade hides the splice
            f.append(f"{chain}{m}acrossfade=d=0.08:c1=tri:c2=tri[x{k}]")
            chain = f"[x{k}]"
        f.append(f"{chain}afade=t=in:d={fi},afade=t=out:st={max(0, dur - fo):.2f}:d={fo}[mus]")
    hits = list(plan.get("hits", [])) + list(cues or [])
    labels = ["[mus]"] if mus else []
    for j, h in enumerate(hits):
        p = Path(sfx_dir or ".") / f"{h['sfx']}.wav"
        if not p.exists():
            raise SystemExit(f"sound effect not found: {p}")
        ins += ["-i", p]
        ms = int(h["t"] * 1000)
        f.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={h.get('db', -12)}dB,adelay={ms}|{ms}[h{j}]")
        labels.append(f"[h{j}]")
        n += 1
    if not labels:
        raise SystemExit("nothing to mix: give --music with a plan 'music' list, or hits / cues")
    f.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0[pre]")
    pre = out.with_suffix(".pre.wav")
    r = run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(f), "-map", "[pre]", "-t", f"{dur:.3f}", pre])
    assert r.returncode == 0, r.stderr
    m = json.loads(re.findall(r"\{[^{}]+\}", run(["ffmpeg", "-i", pre, "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"]).stderr)[-1])
    ln = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
    r = run(["ffmpeg", "-y", "-v", "error", "-i", film, "-i", pre, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", ln,
             "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out])
    assert r.returncode == 0, r.stderr
    pre.unlink()
    meas = loudness(str(out))
    out.with_suffix(".audio.json").write_text(json.dumps(meas))
    print(f"mixed {out} {meas}")
    return meas
