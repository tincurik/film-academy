---
name: film-academy
description: Make a product, demo, launch or brand film from HTML scenes: Chromium films the page frame by frame, ffmpeg joins it, music is cut on bar lines to -14 LUFS, and a numeric gate (shot length, static frames, words per card, cut craft) plus verbatim owner notes decide when a cut is ready. Use when asked to "make a video", promo, trailer, explainer, demo film or social cut.
---

# Film academy

A way to make a film that is built, measured and corrected like code. You write the film as a web page, the renderer films it, the mixer lays sound on its beats, the gate refuses a cut that got slower or deader than the last one, and everything the owner says about the film is kept word for word and has to be answered before a cut passes.

All commands run from this skill's folder (`python film.py ...`). Needs ffmpeg, Python 3.9+, `pip install playwright && playwright install chromium`. `python film.py check` says what is missing. OCR (tesseract) is optional.

## Start here: describe the product, run two commands

When the owner describes a product and wants a film:

1. **Collect only what you cannot invent**: the name, the one promise (one sentence), 2-4 facts that are really true (proof rows), a real number if there is one, the one ask (a URL), and whether the product is a web page or a native/phone app (then ask for a screen recording, see below). Never invent a claim or a number: the film shows what it is given. Ask in one message; if they gave no length, 6-15 s is a social cut, 30-60 s a hero film.
2. `python film.py new "<name>" --promise "<promise>" --points "Label=value|Label=value" [--number "40%" --number-label "..."] [--slam "No setup."] [--action "One tap"] --url <url> [--music track.mp3 --drop-bar N] [--recording rec.mov]` writes `films/<slug>/film.json` and the page.
3. `python film.py make films/<slug>`: render, sound, gate; every make is a numbered build (`v1`, `v2`, ...) gated against the one before. `--master` for 1920x1080 at 60 fps.
4. **Look at it** (`python film.py sheet <film.mp4> films/<slug>/sheet.jpg`, then read the image; you cannot play video) and tell the owner where the mp4 is.
5. **Taste is theirs.** Round one is competent and generic. Ask them to watch it and say what is wrong; store every remark word for word that same turn (`film.py note "<their words>" --source "who, date" --store films/<slug>/film-notes.json`), change `film.json` or `film.html`, tick each note against the new build (`film.py tick N1 --film <mp4> --where 0:04 --store ...`), `make` again. The gate refuses a build with an unticked note, and a build that is slower or more static than the last.
6. **Say plainly** to the owner: the gate catches dead or worsening cuts but cannot judge taste; and the work spends their Claude tokens (a first film is tens of thousands, each correction round 10-30k; custom scenes cost more), so correct several things per round and read one contact sheet rather than many stills.

**A native or phone app** (not a web page): ask for one short screen recording (5-10 s, one task, notifications off, nothing personal on screen) and run `python film.py import-recording rec.mov films/<slug> --start 2 --seconds 6`. It becomes frames the page shows in a window, in place of the drawn card.

Read `playbook.md` before changing the page beyond `film.json` (structure and editing sections first, sound before choosing music). Music: the generated placeholder is the default; never ship a track in a repo, and a track the owner supplies needs a licence that lets them publish the film.

# The manual pipeline (what `make` does, step by step)

## The loop

1. **Brief, in one pass.** Kind (promo, explainer, social cut), the one promise the film makes (one sentence), length, where it plays, and what you are allowed to show (only material the owner may publish; no data you cannot name the right to use). If the owner gave no length, 30-60 s for a hero film, 15 s for social. Do not ask how the film should be made; that is your job.
2. **References before pixels.** Get 2+ films in the same space (watch them, download only what you may keep for private study) and run `python film.py measure ref1.mp4 ref2.mp4`. Their mean shot length, static share and words per card are your yardstick. Read `playbook.md`: the structure and editing groups before writing, the sound group before mixing. Never copy a reference; take its numbers and its techniques.
3. **Write the film as one HTML page** (start from `academy/template.html`, which `film.py new` copies into the project; it also defines `window.timeline()` and `window.cards()` so the gate knows the real cuts and card text). The contract: `window.seek(t)` draws the page at time `t` as a pure function of `t` (no timers, no autoplaying CSS animation), `window.duration()` returns seconds, `window.cues()` returns `[{t, sfx, db}]` for sounds that belong on a frame, `window.ready` is a promise for fonts and images, `window.MISSING` lists assets that failed to load (any entry fails the render). Put scene starts on the bar grid of the music (`bar = beats_per_bar * 60 / bpm`). Open on the payoff (frame 0 is a picture), one promise, a key moment late, the brand early and again on the end card.
4. **Look before you render.** A model cannot play video: `python film.py stills film.html out/stills 0,2.5,5` and read the PNGs; `python film.py sheet film.mp4 sheet.jpg` after a render gives one frame per second on one image. Fix what you see.
5. **Render.** `python film.py render film.html out/film.mp4 --fps 30 --size 1280x720 --workers 2` (use `--fps 60 --size 1920x1080` for the master). N Chromium workers each film a slice; a crashed worker or a missing asset fails the whole render, never a shorter film. The page's cues are written to `out/film.cues.json`.
6. **Sound.** `python film.py mix out/film.mp4 out/final.mp4 --plan plan.json --music track.mp3 --sfx sfx_dir --cues out/film.cues.json`. The plan lists music segments by bar (`track_bar` -> `film_bar`, `bars`) so every jump lands on a downbeat; the last chord rings under the end card. Loudness goes to -14 LUFS, true peak -1 dBTP (two-pass loudnorm) and is measured after. **Music: bring your own, with a licence that lets you publish the film** (never ship a track in a repo); sound effects as `<name>.wav`. No voice by default; a flat synthetic voice is worse than none.
7. **Long films in parts.** Give each part its own page and render, so several people or agents can work in parallel, then `python film.py join p1.mp4 p2.mp4 p3.mp4 --out film.mp4 --dissolve 0.5` (each part's `.cues.json` moves onto the whole film's clock) and mix once over the whole.
8. **Gate.** `python film.py gate --film out/final.mp4 --against previous.mp4 --refs ref1.mp4 ref2.mp4 --timeline times.json --bpm 120`. It stops (exit 5) when the cut is slower than the previous one, more static, or has a burst of tiny shots / cuts on every beat; it warns on words per card and loudness. ffmpeg's scene score barely sees eased transitions, so give the real cut times in `times.json` (`{"final": [2.0, 4.0, ...]}`, keyed by file stem). Fix the film, render, gate again. A film that never beats the previous cut is not finished.
9. **Notes bind every cut.** Whenever the owner says anything about the film, store it that same turn, verbatim: `python film.py note "<their exact words>" --source "who, date" [--means "your reading"]`. Before a gate, tick each note against the exact file with where it is answered: `python film.py tick N1 --film out/final.mp4 --where 0:04` (a timestamp or `shot 7`). `film.py gate` refuses (exit 6) while any note has no tick for that file's hash; a re-render or a music swap is a new file and needs new ticks. `python film.py notes --film out/final.mp4` lists what is open. Their words are never edited; your reading goes in `--means`.
10. **Deliver the finished film.** The owner sees the final cut (full-resolution master, stills for the poster), not animatics, storyboards or half-built versions; if they asked to see a draft, that is their call, not a default.

## Rules that held up

- The owner's taste outranks any score: the gate catches regressions and dead cuts, it does not pick the better film. When the owner says what is good or bad about a film, add it to the playbook for the next one.
- Never rebuild a part of the pipeline a measure already covers: measure first (`film.py measure`), then change.
- Corrections go into this folder (the playbook, the page template, the plan), not into a prompt that is lost after the session.
- No reference film, clip or licensed track goes into a repo: only numbers.

## Files

| File | What |
|---|---|
| `film.py` | the command line: new, make, import-recording, check, render, stills, join, mix, measure, gate, sheet, note, tick, notes |
| `academy/project.py`, `academy/template.html` | `new`/`make`: the film project, the config-driven page |
| `academy/render.py` | frame-by-frame Chromium renderer (parallel slices, ffmpeg) |
| `academy/mix.py` | bar-line music cut, hits on cues, two-pass loudnorm to -14 LUFS |
| `academy/join.py` | parts joined with dissolves, cues merged |
| `academy/gate.py` | the measures and checks |
| `academy/notes.py` | verbatim notes, ticks tied to a file hash |
| `playbook.md` | 43 sourced techniques and the gate's numbers |
| `data/` | reference numbers (18 published films) and cut-craft limits (205 films), numbers only |
| `example/` | a 10 s original film (`bash example/build.sh`): `new` then `make` on an invented product |
