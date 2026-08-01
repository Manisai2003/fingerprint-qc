# Assignment 4 Report — Fingerprint Quality Assessment & Scoring Pipeline

*Fill in the bracketed values using your own results from
`outputs/test_results.csv` after running `test_quality.py` on your real
photos. This is a scaffold, not a finished report.*

## Q1. What threshold did you set for blur? How did you decide?

- Threshold used: `blur_reject = 10.0` (Laplacian variance) — this project's
  default, inherited from the assignment brief.
- Report your own calibration evidence: pull the `Blur Score` column from
  `outputs/test_results.csv` for your `good/` vs `blurry/` folders and state
  the actual ranges you observed, e.g. "[ ] to [ ] for sharp captures vs
  [ ] to [ ] for intentionally blurred ones." If your real numbers suggest
  10.0 is too strict or too lenient for your camera/lighting, say so and
  explain what you'd change it to — that's a better answer than just
  restating the default.

## Q2. Which metric was hardest to implement correctly? What went wrong first?

Candidates worth discussing, both genuinely tricky in this implementation:
- **ROI completeness**: plain Otsu thresholding doesn't know which
  intensity class is the finger vs. the background — see the "Design
  notes" section of `README.md` for the center-region heuristic used here,
  and speak to whether it held up on your real photos (does your camera
  setup keep the finger roughly centered?).
- **Ridge clarity**: unrestricted Gabor-filter variance picks up the
  finger/background boundary edge itself, not just ridge texture — the fix
  here was eroding the ROI mask before measuring. Worth checking your own
  `Ridge Score` numbers to see how much this mattered on your data.

Pick whichever genuinely gave you the most trouble once you had real
photos running through it, and describe what the wrong output looked like
before the fix.

## Q3. What is NFIQ2? Why is a score designed for contact scanners not reliable for phone camera images?

- **NFIQ2 (NIST Fingerprint Image Quality 2)**: the standard 0–100
  fingerprint image quality metric from NIST, built around and validated
  against flat-platen contact optical scanners (~500 DPI, controlled
  black/white ridge contrast, no perspective distortion).
- Why it doesn't transfer to phone captures — three angles to cover:
  1. **Acquisition physics gap**: NFIQ2's internal features assume the
     FTIR-scanner imaging model, not a handheld RGB camera at a variable
     angle/distance.
  2. **Perspective & scale variation**: phone captures have DPI that
     depends on distance-to-lens and non-linear warping from the finger's
     3D curvature — a contact scanner has neither.
  3. **Texture/color differences**: natural skin tone, ambient shadows, and
     specular highlights confuse features NFIQ2 was never trained to
     expect, often producing misleadingly low scores on perfectly usable
     contactless captures.

## Q4. Name 3 other quality problems you'd add checks for in a real deployment.

Three solid candidates (pick 3, or use your own if testing surfaced
something else):
1. **Pitch/yaw angle distortion** — a tilted finger warps ridge spacing
   even when otherwise sharp, well-lit, and centered.
2. **Multi-finger occlusion** — an adjacent finger entering the frame
   confuses segmentation (this project's ROI check, for instance, would
   likely treat both fingers as one connected blob).
3. **Distance/scale boundary check** — finger too far (insufficient
   effective resolution) or too close (outside minimum focal distance);
   neither is caught by any of the 5 metrics here, since a too-small or
   too-large-but-blurry finger can still pass ROI/blur individually.

## Q5. Rural agricultural worker with worn ridges — what should the system do differently?

- **Problem**: manual labor / environmental wear smooths friction ridges,
  causing legitimate users to consistently fail the ridge-clarity gate
  through no fault of their capture technique.
- Worth covering at least 2–3 of:
  1. **Adaptive thresholding per-user**: relax the ridge threshold based on
     an enrollment-time baseline rather than one fixed global cutoff.
  2. **Alternative-finger fallback**: prompt for a different digit that may
     be less worn.
  3. **Multi-frame fusion**: combine several frames into one
     higher-contrast composite before scoring, rather than judging off a
     single capture.
  4. **Multimodal fallback**: fall back to face/iris if fingerprint ridges
     are persistently unusable for that person.
