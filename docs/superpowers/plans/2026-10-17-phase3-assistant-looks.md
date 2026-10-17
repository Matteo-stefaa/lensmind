# Phase 3 — Assistant that looks: Implementation Plan

> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a shot, the assistant sees a reduced copy, exposure statistics and the
shooting data, and proposes corrections through the phase 2 approval flow.

**Spec:** `docs/superpowers/specs/2026-10-17-phase3-assistant-looks-design.md`

**Note:** tasks 1–5 were implemented before the spec was written. Each is checked
against the spec rather than redone; mismatches become new steps.

## Global Constraints

- `api → assistant → camera`; `assistant/` never imports `storage.py` or FastAPI.
- Pillow is imported in `assistant/vision.py` only (within `assistant/`).
- Full-resolution files never leave the Pi.
- No model call or hardware in tests: `FakeProvider`, `MockCamera`, `tmp_path` stores.
- Strings for the model in English; user strings it/en in `web/js/i18n.js`.
- `.venv/bin/ruff check . && .venv/bin/ruff format .` clean, line length 100.
- Commits: imperative sentence, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A stale shot judged as if it showed the new settings → `taken_after_last_applied_proposal`
   (Task 2, `test_evaluate_tells_whether_the_shot_follows_the_applied_proposal`).
2. RAW-only quality → tool error that points to a JPEG quality, no crash (Task 2).
3. Requests growing with every evaluation → image pruning (Task 2,
   `test_only_the_newest_images_stay_in_the_history`).
4. Evaluation while a capture is being written → atomic save (Task 6).

---

## File map

| File | Responsibility |
|---|---|
| `src/lensmind/assistant/vision.py` (create) | `PhotoSource`, `latest_shot`, `view_shot`, stats, EXIF |
| `src/lensmind/assistant/tools.py` (modify) | `evaluate_shot` schema |
| `src/lensmind/assistant/loop.py` (modify) | `_evaluate`, `applied_at`, `clock`, `photos`, `_prune_images` |
| `src/lensmind/assistant/prompts.py` (modify) | evaluation rules in the system prompt |
| `src/lensmind/api/app.py` (modify) | pass the store to `Assistant` |
| `src/lensmind/camera/mock.py`, `mock_image.py` (modify) | EXIF in mock JPEGs |
| `src/lensmind/storage.py` (modify) | atomic writes |
| `web/js/assistant.js`, `app.js`, `i18n.js`, `style.css` (modify) | evaluation offer |
| `tests/test_vision.py` (create), `test_assistant_loop.py`, `test_api_assistant.py`, `test_assistant_tools.py`, `test_storage.py` (modify) | |
| `CLAUDE.md`, `docs/cameras/nikon-d3500.md` (modify) | status, hardware checklist |

---

### Task 1: vision module — done, checked

- [x] `view_shot`: draft decode, EXIF transpose, thumbnail 1024, JPEG q80
- [x] `histogram_stats` keys as in spec §2
- [x] `shooting_data` keys as in spec §2, non-finite values skipped
- [x] `latest_shot` over the `PhotoSource` protocol
- [x] `tests/test_vision.py`

### Task 2: `evaluate_shot` in the loop — done, checked

- [x] Tool schema in `TOOLS` (between `ask_user` and `finish`)
- [x] `_evaluate` result: JSON text + image block; four error cases of spec §3
- [x] `applied_at` set on `applied` and `partial`
- [x] `_prune_images` keeps `MAX_IMAGES = 2`
- [x] Loop tests listed in spec §7

### Task 3: prompt and wiring — done, checked

- [x] System prompt rules of spec §3
- [x] `create_app` passes `photos=store`
- [x] API test through `/api/capture`

### Task 4: mock EXIF — done, checked

- [x] `render(..., exif=None)`; `MockCamera._exif()` with the fields of spec §5

### Task 5: web offer — check against spec §6

- [x] Offer after capture, one at a time, removed by typing and by "New conversation"
- [x] Tap while busy leaves the card in place
- [x] Strings it/en

### Task 6: atomic writes in the photo store (spec §4)

- [x] Write the failing test in `tests/test_storage.py`: after `save`, the directory holds
  no hidden temporary files, and a file written through `save` is complete. Run it.
- [x] In `PhotoStore.save`, write each file to `root / f".{name}.part"` and `replace()`
  it onto `root / name`.
- [x] Run `pytest tests/test_storage.py tests/test_vision.py`, then the full suite.

### Task 7: test robustness

- [x] `test_latest_shot_picks_the_jpeg_of_the_newest_shot` relies on two saves in the
  same second having different mtimes: set mtimes explicitly with `os.utime`.

### Task 8: finish

- [x] `ruff check . && ruff format .`, full `pytest`
- [ ] Commit spec + plan, then the implementation
- [ ] Push branch `feat/phase3-evaluate-shot`, open PR
- [ ] Manual test on the Pi (spec "Done when" 4) after merge and deploy; record results
  in `docs/cameras/nikon-d3500.md`. Deploy needs SSH access to the Pi.
