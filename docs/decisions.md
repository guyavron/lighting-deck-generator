# Design decisions

The project keeps a running decision log (73 entries so far, in Hebrew, internal to the studio). Comments in the code cite its numbers, like `D-033`. These are the 12 that shaped the tool most. Each one says what was **measured**, what was **chosen**, and what was **rejected**, and why.

The numbers come from the studio's real material: 4 CAD drawings, 5 past decks and 5 Photoshop files. None of that material is in this repository.

| # | Decision | In one line |
|---|---|---|
| [D-001](#d-001--python) | Python | The only mature DXF library is in Python |
| [D-002](#d-002--d-016--separate-objects-not-one-flattened-image) | Separate objects | Every plan, photo and title can be moved in PowerPoint |
| [D-003](#d-003--the-glow-is-measured-from-the-studios-photoshop-files) | Glow from Photoshop | 229 glow effects, one formula |
| [D-004](#d-004--the-acceptance-test-is-the-studio-not-a-number) | Acceptance test | The studio's eye, not a metric |
| [D-006](#d-006--knowledge-in-yaml-and-csv-not-in-code) | Knowledge tables | YAML/CSV survive a rewrite of the code |
| [D-010](#d-010--photos-on-the-right-plan-width-varies) | Layout | Plan from 4%, photos to 96% |
| [D-012](#d-012--three-time-sinks-and-the-glow-is-the-smallest) | Where the hours go | Dressing slides and searching, not the glow |
| [D-017](#d-017--the-designer-marks-the-areas) | Areas | Drawn by a person, suggested by code |
| [D-020](#d-020--arrange-in-the-preview-not-in-powerpoint) | Arranging | In the preview, before export |
| [D-036](#d-036--saved-work-is-never-lost) | Saving | Four ways to lose a deck, all closed |
| [D-048](#d-048--a-soft-photo-filter-that-follows-what-is-lit) | Photo filter | Soft, so half the bank isn't hidden |
| [D-070](#d-070--what-you-cut-is-what-you-see) | Framing | The window is the rectangle that was cut |

---

## D-001 · Python
- **Chosen:** Python with `ezdxf`, Pillow and `python-pptx`.
- **Rejected:** Node/TypeScript. `ezdxf` is the only mature DXF library, and Node has nothing equivalent.

## D-002 / D-016 · Separate objects, not one flattened image
- **Measured:** in the reference decks only **45–76% of the content slides** are one flattened image. The rest were already assembled in PowerPoint.
- **Chosen:** the plan (with its glow), every photo, the title and the title rule are separate PowerPoint objects.
- **Why it's safe:** the slide background and the plan background are both pure black, so the assembled slide looks pixel-identical to a flattened one. Checked by eye.
- **Rejected:** copying the flattened structure. It exists because Photoshop forces it, not because it is better, and the designer wanted to resize things at the end.

## D-003 · The glow is measured from the studio's Photoshop files
- **Measured:** the Photoshop files were mapped before any rendering code was written. **229 glow effects** were extracted: every one is an *Outer Glow* with *Screen* blending, spread 0 and noise 0.
- **Chosen:** the renderer reproduces that effect, with `sigma = (size − expansion) × 0.39` and the glow layer doubled. The parameters are fixed **per project** by default. Since D-051 a designer can change colour, size and strength for one slide, but only within a list of allowed values (`knowledge/glow.yaml`).
- **Rejected:** a blurred brush that "looks about right". The taxonomy, room names and layer structure were already documented in the PSDs, and an hour of mapping replaced reverse-engineering by eye.

## D-004 · The acceptance test is the studio, not a number
- **Chosen:** a blind comparison by the head of the studio. The numeric match is only a regression check.
- **Rejected:** "glow within ±15% of the measured sigma" as the success criterion. Sigma was measured against hand-made Photoshop work, not against a standard, so checking against our own measurement would be circular.

## D-006 · Knowledge in YAML and CSV, not in code
- **Chosen:** `knowledge/*.yaml|csv` is the source of truth: lighting layers, block codes → categories, glow, slide layout, photo tags.
- **Rejected:** SQLite as the main store.
- **Why:** the code is written with AI and will be rewritten. What survives a rewrite are the decision tables, and YAML/CSV can be read and diffed in git. If a mapping table appears inside a `.py` file, that is a bug.

## D-010 · Photos on the right, plan width varies
- **Measured** on three decks: the plan always **starts at 4%** of the slide width, and the photos always **end at 96%**, on the same right edge as the title. The plan's width changes with the building: 332 px for a narrow building, 1,212 px for a wide flat.
- **Chosen:** the plan width is derived from the content's aspect ratio.
- **Rejected:** a fixed column. Forcing a wide plan into a narrow column produced a 489×132 strip.

## D-012 · Three time sinks, and the glow is the smallest
- **Measured** on 5 decks: 245 content slides (49 per deck), 345 large photos (69 per deck), 205 glow marks (41 per deck). Only 14% of the named products repeat between decks.
- **Estimated** (assumptions, not timings): dressing slides ~48% of the time, searching for products and photos ~40%, the glow ~12%.
- **Chosen:** the unit of output is a **whole deck**, not a slide, and the photo bank is shared by the whole team.
- **Lesson:** the glow was built first because it was the biggest *risk*: if it couldn't be reproduced, the project was dead. But it was never the biggest *cost*, and the order of work shouldn't be mistaken for the order of value.

## D-017 · The designer marks the areas
- **Chosen:** one local, right-to-left screen. The designer drags a rectangle on the plan for each room and names it.
- **Kept as a suggestion only:** automatic area detection. How a floor is divided changes from project to project, so the code can't decide it.
- **Why local:** CAD drawings of 56 MB and more don't leave the office.

## D-020 · Arrange in the preview, not in PowerPoint
- **Reverses** part of D-016, which said fine-tuning would happen in PowerPoint.
- **Why:** the preview exists so a designer can approve a slide *before* export. If approving means "then fix 49 slides by hand", the preview only shows the bad news earlier. Correction rounds are about a quarter of the work.
- **Chosen:** drag and resize the plan, each photo and the title in the preview; rotate the plan in 90° steps; edit the title in place. Changes are saved with the project and go into the export. **The aspect ratio is always locked**: a stretched plan is exactly the bug the preview was built to prevent.

## D-036 · Saved work is never lost
- **Found** in a usability test on a 111-slide project, four ways to lose a deck: a file damaged by a power cut opened as an empty project and was overwritten on the first rename; a crashed server failed to save silently; an old browser window deleted a slide added in another window; a change followed by closing the tab within half a second was lost.
- **Chosen:** atomic writes (temp file → swap), a version history (at most one entry every 10 minutes, never deleted), a revision number (a save from an older version is rejected with `409`), a file that can't be read is never overwritten, and every change is written to the browser first and retried until the server confirms.
- **Checked** in the browser, all four cases, including restoring a damaged 110-slide project from its history.

## D-048 · A soft photo filter that follows what is lit
- **Asked by the studio:** "the process is long and hard. Narrow the photos by the fixture type that is lit."
- **Measured first:** 216 of 417 photos had no install type. A hard filter on "recessed ceiling" would have left 34.
- **Chosen:** the install-type filter is *soft*. A photo tagged with a **different** type is hidden; an untagged photo is shown below a line ("not tagged yet, may fit"). The chips switch on by themselves from what is lit and can be switched off. Once the designer touches a chip, the drawing stops changing the filter on that slide. Only unambiguous categories map to a type; "spots" and "system" don't.
- **Result:** 232 photos instead of 417 (34 + 198 below the line).
- **Rejected:** a hard filter (hides half the bank) and ranking only (shortens nothing).

## D-070 · What you cut is what you see
- **Problem** (raised by me after using it): a slide was framed by the fixtures inside the area. Fixtures sit 50–100 cm from the walls, so every slide lost its outer walls, and the designer couldn't move the frame.
- **Chosen:** the window is exactly the rectangle that was cut, as it already was for sub-areas (D-026). Everything outside it is black. Step 3 warns when a fixture crosses the edge and is cut.
- **Reverses** an earlier choice (D-057) to frame by fixtures. Why now: a rectangle that is too wide shows up at once in the preview, so it isn't a silent error; it unifies the rule with sub-areas; and no deck had gone to a client yet.
