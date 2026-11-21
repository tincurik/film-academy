# film-academy

A Claude Code skill for making product, demo and launch films the way a build system makes software. The film is a web page; a headless Chromium films it frame by frame; ffmpeg joins it; the music is cut on bar lines and normalised to -14 LUFS; a gate refuses a cut that got slower or deader than the last one. What you say about the film is stored word for word and has to be answered before a cut passes.

![example film](docs/example.gif)

*The 10 s example (`example/`): an invented product, original scenes, generated audio. Built by one command in about 10 seconds on a laptop CPU.*

## The start: one command

```bash
git clone https://github.com/tincurik/film-academy ~/.claude/skills/film-academy
cd ~/.claude/skills/film-academy
pip install -r requirements.txt && playwright install chromium       # plus ffmpeg from your package manager
python film.py new "Acme" --promise "Plan your week in one tap." --url "acme.example"
python film.py make films/acme                                       # -> films/acme/builds/v1-final.mp4
```

`python film.py check` tells you what is missing. Nothing else is needed: no GPU, no cloud, no account.

## From "describe your product" to a finished film

You can run the commands yourself, but the intended way is to **tell Claude Code about your product** and let it drive: "make a 15 s launch film for Acme, a calendar app that plans your week. The site is acme.example." The skill tells Claude to do the following, and you can do each step by hand.

| Step | What happens | Your part |
|---|---|---|
| 1. Describe | Name, the **one promise** (a sentence), the proof you really have (2-4 facts, a real number if you have one), the one ask (a URL). | Give real facts. The film will show what you give it, so do not give claims you cannot back. |
| 2. Start | `film.py new "<name>" --promise "..." --points "Label=value\|Label=value" --number "40%" --url ...` writes `films/<slug>/film.json` and the page. | None. |
| 3. Build | `film.py make films/<slug>` renders the page, mixes the sound, runs the gate. Every make is a numbered build (`v1`, `v2`, ...); each is gated against the one before. | Wait about as long as the film is long. |
| 4. Look | `film.py sheet <film> sheet.jpg` puts one frame per second on one image. Claude looks at it (it cannot play video); you watch the mp4. | **Watch the film.** |
| 5. Say what is wrong | `film.py note "the middle drags" --source "me, today"`. Your exact words are kept. | **This is the step that makes the film good.** |
| 6. Fix and rebuild | Claude changes `film.json` or `film.html`, ticks each note with where it is answered (`film.py tick N1 --film <mp4> --where 0:04`), runs `make` again. The gate stops a build that is slower or more static than the last, or that leaves a note unanswered. | Repeat 4-6 until you would post it. |
| 7. Master | `film.py make films/<slug> --master` renders 1920x1080 at 60 fps. | None. |

`film.json` is the one file a first film needs: name, promise, hook, tagline, proof rows, a slam line, a number, a press, the URL, an accent colour, your music. Anything it cannot say, you change in `film.html` (each scene type is one short function).

## Be clear about what you get

**Taste comes from you.** The gate measures things a machine can measure: shot length, how much of the film sits still, words per card, bursts of tiny shots, loudness, whether every note was answered. It catches a film that got worse and a film that is dead. It cannot tell you a film is good, and the first build will be competent and generic. What makes it yours is you watching it and writing down, in your own words, what is wrong; those notes bind every later build. The playbook (`playbook.md`, 43 techniques with sources) gives the agent craft to work from; your notes give it your taste.

**Token use is real.** Rendering is free local CPU, but the agent that drives this is a Claude session, and it spends tokens reading the skill (about 3k) and the playbook (about 9k, read at the steps that need it), writing the config, looking at stills and sheets (each image costs on the order of a thousand tokens or more), and reading build output. Rough estimates from this kind of work, not measurements: a first film from `film.json` is tens of thousands of tokens; each correction round is 10-30k; a film with custom scenes and several rounds can reach hundreds of thousands. To keep it lean: start with `new` and the config rather than hand-written pages, correct several things per round, and look at a sheet rather than many stills.

## Using your own screen recordings (native apps, phone apps)

Real product frames are the strongest proof a product film can show (playbook technique 11, "Real product frames as proof"), and for an app that is not a web page they are the only way to show it. Record, then import:

1. **Record** one short task (5-10 s), one take, at the screen's native size, cursor visible, notifications off, nothing personal on screen. macOS: Shift-Cmd-5. Windows: Win+Alt+R (Game Bar) or OBS. Linux: OBS, or `ffmpeg -f x11grab`. iPhone: Control Centre screen recording. Android: `adb shell screenrecord /sdcard/rec.mp4`.
2. **Import**: `python film.py import-recording rec.mov films/acme --start 2 --seconds 6` (or `new ... --recording rec.mov`). Any format ffmpeg reads works. The clip becomes numbered JPEG frames under `assets/app/`, and `film.json` shows it as the proof scene, in a window frame, in place of the drawn card. Frames are used instead of playing the file because Playwright's Chromium cannot decode H.264, and because frame-by-frame seeking is then exact.
3. `film.py make films/acme` as before. The recording runs at real speed (`speed` in `film.json` changes it); its length sets the scene's length in whole bars.

Only record what you may publish. Frames of your own app are yours; third-party content on screen is not.

## What is in it

| Piece | What it does |
|---|---|
| `film.py new / make` | The one-command start and the numbered, gated build. |
| `film.py render / stills` | Your HTML page defines `window.seek(t)`; N Chromium workers film slices; ffmpeg encodes; slices join without re-encoding. A missing asset or crashed worker fails the render. |
| `film.py mix` | Cuts a track you supply on bar lines (`plan.json`), puts sound effects on the page's own cues, two-pass loudnorm to -14 LUFS / -1 dBTP, measures the result. |
| `film.py join` | Parts rendered separately (so several people or agents build in parallel) joined with dissolves; cues move onto the whole clock. |
| `film.py gate / measure` | Mean shot length, share of static frames, words per card (cards from the page, tesseract, or a cards file) against the previous cut and reference films you supply; cut-craft limits (bursts, cuts on every beat). Exit 5 on a stop, 6 on an unanswered note. |
| `film.py note / tick / notes` | Your words, verbatim, tied to the exact film file by hash. |
| `playbook.md` | 43 sourced techniques from editors, motion designers, studios and ad research, plus the gate's numbers. |

## Licences and what is not here

- Code: MIT (`LICENSE`).
- **Placeholder audio is generated** by `academy/placeholder_audio.py` (sine pads, a kick, noise sweeps): no third-party sound, and the generated files are CC0. A first film is not silent, but it is placeholder music: pass `--music your-track.mp3 --drop-bar N` to `new` (or edit `plan.json`).
- **No music is shipped.** Bring a track you may publish: a licence that allows redistributing the film. "Free to use in videos" is often not the same as "free to redistribute the file". Put your own sound effects as `impact.wav`, `whoosh.wav`, `click.wav` in `films/<slug>/sfx/`.
- No reference films or clips are included, only measured numbers (`data/`). The playbook quotes short passages from public pages, each with its link.
- Fonts: the page uses the system's sans-serif; no font files are bundled.

## Tests

```bash
python -m unittest discover -s tests
```
