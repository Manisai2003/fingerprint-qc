# Contactless Fingerprint Quality Assessment & Scoring Pipeline

An image Quality Control (QC) gate for a contactless phone-camera
fingerprint capture pipeline. Scores a capture on 5 metrics (blur,
brightness, glare, ROI/finger completeness, ridge clarity), combines them
into a single 0–100 composite score, and returns actionable guidance
("Too dark — turn on flash") when a capture should be retaken.

## How the pieces fit together

```
quality_assessment.py   <- the 5 metrics + composite score + quality_gate()
        |
        +--> quality_app.py     (Streamlit dashboard, live threshold sliders)
        +--> test_quality.py    (batch-tests test_dataset/, verifies each
        |                        defect category is flagged correctly)
        |
test_dataset/{good,blurry,dark,glare}/   <- your 20 real phone photos (you provide these)
outputs/                                  <- test_results.csv lands here
screenshots/                              <- your 4 required UI screenshots go here
```

Both `quality_app.py` and `test_quality.py` import from `quality_assessment.py`
— there's exactly one implementation of each metric in the whole project.

## 1. Install dependencies

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
(If activation is blocked, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once first — see the Assignment 3 project notes if you hit this again.)

**macOS/Linux:**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Collect your 20 test images (you need to do this yourself)

Take these with your phone camera, transfer them to your computer, and
drop them into the matching folder:

| Folder | Count | How to capture it |
|---|---|---|
| `test_dataset/good/` | 5 | Well-lit, focused, finger centered and filling the frame |
| `test_dataset/blurry/` | 5 | Move your hand or phone slightly during capture |
| `test_dataset/dark/` | 5 | Dim room / cover the flash / turn away from light |
| `test_dataset/glare/` | 5 | Point a flashlight or lamp directly at your finger |

I validated the whole pipeline (all 3 scripts) end-to-end against synthetic
placeholder images built to mimic each of these four conditions — 20/20
were correctly flagged — but those were geometric stand-ins, not real
fingerprint photos, so they aren't included in this delivery. The logic is
solid; your real photos are what actually need to go in these folders.

## 3. Run the batch test

```bash
python test_quality.py
```
Prints a results table and a "Correctly flagged: X/20" summary, and saves
the full breakdown to `outputs/test_results.csv`. If something in your
`dark/` or `blurry/` folder isn't getting flagged, that's a genuine signal
to either retake the photo more decisively or revisit your threshold —
either is a legitimate finding for report Q1/Q2.

## 4. Run the Streamlit dashboard

```bash
streamlit run quality_app.py
```
Opens in your browser automatically (usually `http://localhost:8501`).
Upload an image, watch the composite score and 5 pass/fail badges update,
and try dragging the sidebar sliders to see how moving a threshold changes
the verdict in real time.

### Taking your 4 required screenshots

The assignment wants one screenshot per defect type (`good`, `blurry`,
`dark`, `glare`) showing the UI with the correct ❌/✅ flag. With the app
running: upload one image from each `test_dataset/` subfolder, screenshot
the result, and save into `screenshots/` (e.g. `screenshots/blurry.png`).
This has to happen on your machine since it needs your real photos and a
real browser window — I can't generate these for you.

## Design notes worth knowing for the code-walkthrough call

- **ROI foreground/background ambiguity**: plain Otsu thresholding splits
  the image into two intensity classes but has no idea which one is the
  finger — on a dark background the finger is the bright class, on a light
  background it's the reverse. `check_roi_completeness` resolves this by
  assuming the finger is roughly centered (reasonable for a camera-guided
  capture UI) and picking whichever class dominates the center of the
  frame, then cleans up speckle noise with a morphological open+close pass.
  This was, unsurprisingly, the fiddliest metric to get right — a good,
  honest answer for report Q2.
- **Ridge clarity is restricted to an eroded ROI mask**, not the whole
  image. Without this, the sharp edge where the finger meets the
  background is itself high-frequency content that a Gabor filter responds
  to strongly — which has nothing to do with actual ridge texture and can
  make a blurry finger with a crisp background look artificially clear. The
  mask is eroded by ~15px before use so the segmentation boundary itself
  (not just background clutter) is excluded from the measurement.
- **Two-tier thresholds (`*_reject` / `*_full_credit`)**: blur, ROI, and
  ridge each have a hard-fail floor AND a separate "full marks" ceiling, so
  a capture can clear the hard-fail bar but still cost you composite-score
  points for being marginal — worth being able to explain why a 62/100
  "FAIL" and a 15/100 "FAIL" aren't the same kind of bad.
- **Why brightness and glare don't use `_full_credit`**: brightness is
  scored by closeness to an ideal midpoint (128) rather than "more is
  better", and glare is scored by *distance below* its own reject fraction
  — both already produce a natural 0–1 range without needing a second
  calibration point.

## Report questions (`report.pdf`)

See `report_template.md` for a scaffold with guidance per question — fill
it in using your real `outputs/test_results.csv` numbers, not placeholders.
# fingerprint-qc
# fingerprint-qc
