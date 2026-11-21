"""Render an HTML film frame by frame.

The page is the film. It must define:
    window.seek(t)       draw the page at time t seconds (a pure function of t: no timers, no CSS animations that run by themselves)
    window.duration()    length in seconds
  optional:
    window.ready         a promise (fonts, images loaded)
    window.timeline()    cut times in seconds (the scene list); window.cards() the text on each card: the gate uses them instead of guessing
    window.cues()        [{"t": 2.0, "sfx": "impact", "db": -6}, ...]: sounds that belong on a frame; the mixer reads them
    window.MISSING       [names] of assets the page could not load: any entry fails the render

N headless Chromium workers each film a slice of the frames, JPEG frames go to ffmpeg (libx264), the slices are joined without re-encoding.
"""
import base64
import json
import subprocess
import sys
import tempfile
from multiprocessing import Process
from pathlib import Path

LAUNCH = ["--mute-audio", "--allow-file-access-from-files", "--disable-dev-shm-usage", "--force-color-profile=srgb"]


def open_page(p, html, size):
    b = p.chromium.launch(headless=True, args=LAUNCH)
    pg = b.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
    pg.on("pageerror", lambda e: print("pageerror", e, file=sys.stderr, flush=True))
    pg.goto(Path(html).resolve().as_uri())
    pg.evaluate("window.ready || null")
    pg.evaluate("document.fonts.ready.then(() => 1)")
    return b, pg, pg.context.new_cdp_session(pg)


def _worker(html, a, z, out, fps, size, crf):
    from playwright.sync_api import sync_playwright
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-",
                           "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", str(crf), str(out)], stdin=subprocess.PIPE)
    with sync_playwright() as p:
        b, pg, cdp = open_page(p, html, size)
        for f in range(a, z):
            pg.evaluate("t => window.seek(t)", f / fps)
            r = cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 94})
            ff.stdin.write(base64.b64decode(r["data"]))
        missing = pg.evaluate("window.MISSING || []")
        b.close()
    ff.stdin.close()
    ff.wait()
    if missing:
        print(f"MISSING assets in {out.name}: {missing[:5]}", file=sys.stderr, flush=True)
        sys.exit(5)


def stills(html, out_dir, times, size=(1280, 720)):
    """PNG frames at the given times, for looking at (a model cannot play a video: look at stills)."""
    from playwright.sync_api import sync_playwright
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        b, pg, _ = open_page(p, html, size)
        for t in times:
            pg.evaluate("t => window.seek(t)", float(t))
            paths.append(out_dir / f"still_{float(t):06.2f}.png")
            pg.screenshot(path=str(paths[-1]))
        b.close()
    return paths


def render(html, out, fps=30, workers=2, size=(1280, 720), crf=18):
    """Film html -> out (mp4, picture only). Also writes <out>.cues.json when the page has window.cues()."""
    from playwright.sync_api import sync_playwright
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b, pg, _ = open_page(p, html, size)
        dur = pg.evaluate("window.duration()")
        cues = pg.evaluate("window.cues ? window.cues() : []")
        timeline = pg.evaluate("window.timeline ? window.timeline() : null")
        cards = pg.evaluate("window.cards ? window.cards() : null")
        b.close()
    n = round(dur * fps)
    cut = [round(n * i / workers) for i in range(workers + 1)]
    tmp = Path(tempfile.mkdtemp(prefix="film-"))
    parts = [tmp / f"part{i}.mp4" for i in range(workers)]
    ps = [Process(target=_worker, args=(str(html), cut[i], cut[i + 1], parts[i], fps, size, crf)) for i in range(workers)]
    [x.start() for x in ps]
    [x.join() for x in ps]
    if any(x.exitcode for x in ps):          # a crashed worker or a missing asset: no film at all, never a shorter one
        raise SystemExit(f"render failed: worker exit codes {[x.exitcode for x in ps]}")
    lst = tmp / "parts.txt"
    lst.write_text("".join(f"file '{q.as_posix()}'\n" for q in parts))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True)
    for q in parts:
        q.unlink()
    lst.unlink()
    tmp.rmdir()
    if cues:
        out.with_suffix(".cues.json").write_text(json.dumps(cues, indent=1))
    if timeline is not None:                      # the page's own scene list: the real cut times, and the text on each card (no OCR needed)
        out.with_suffix(".timeline.json").write_text(json.dumps(timeline))
    if cards is not None:
        out.with_suffix(".cards.json").write_text(json.dumps(cards))
    print(f"film {out} {dur:.2f} s, {n} frames at {fps} fps, {len(cues)} cues")
    return dur
