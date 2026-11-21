"""Placeholder audio, generated with ffmpeg alone: a 120 bpm track (a pad that changes chord every 2 bars, a kick on every beat, the last 2 bars louder as the
"drop") and three sound effects (impact, whoosh, click). Nothing is recorded or copied: this code makes the files, so there is no third-party licence and the
generated files are CC0. They keep a first film from being silent; replace the track with your own (`new --music`).
"""
import subprocess
from pathlib import Path

BPM = 120
BEAT = 60.0 / BPM
BAR = 4 * BEAT                       # 2.0 s


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *[str(a) for a in args]], check=True)


def sfx(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ff("-f", "lavfi", "-i", "sine=f=55:d=1.2:r=48000", "-af", "afade=t=out:st=0:d=1.2,volume=2.5", out / "impact.wav")
    ff("-f", "lavfi", "-i", "anoisesrc=d=0.7:c=pink:a=0.6:r=48000", "-af", "highpass=f=300,lowpass=f=5000,afade=t=in:d=0.35,afade=t=out:st=0.35:d=0.35", out / "whoosh.wav")
    ff("-f", "lavfi", "-i", "sine=f=1800:d=0.08:r=48000", "-af", "afade=t=out:st=0.01:d=0.07", out / "click.wav")


def track(out, bars):
    """out/track.wav, `bars` bars long (at least 2)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    chords = [(220.0, 277.2, 329.6), (196.0, 246.9, 293.7), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
    inputs, filt, labels, n = [], [], [], 0
    pads = -(-bars // 2)
    for i in range(pads):
        base = n
        for f in chords[i % len(chords)]:
            inputs += ["-f", "lavfi", "-t", f"{2 * BAR:.3f}", "-i", f"sine=f={f}:r=48000"]
            n += 1
        ms = int(i * 2 * BAR * 1000)
        vol = 0.28 if i >= pads - 1 else 0.2                    # the last pad is the lift
        filt.append(f"[{base}:a][{base + 1}:a][{base + 2}:a]amix=inputs=3:normalize=0,volume={vol},afade=t=in:d=0.05,"
                    f"afade=t=out:st={2 * BAR - 0.15:.2f}:d=0.15,adelay={ms}|{ms}[c{i}]")
        labels.append(f"[c{i}]")
    for b in range(bars * 4):
        inputs += ["-f", "lavfi", "-t", "0.35", "-i", "sine=f=55:r=48000"]
        ms = int(b * BEAT * 1000)
        filt.append(f"[{n}:a]afade=t=out:st=0:d=0.35,volume=0.9,adelay={ms}|{ms}[k{b}]")
        labels.append(f"[k{b}]")
        n += 1
    filt.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{bars * BAR:.3f}[o]")
    ff(*inputs, "-filter_complex", ";".join(filt), "-map", "[o]", out / "track.wav")
    return out / "track.wav"
