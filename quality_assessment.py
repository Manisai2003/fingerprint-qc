"""
quality_assessment.py
----------------------
Core logic for the contactless fingerprint capture Quality Control (QC)
gate. Five independent metrics (blur, brightness, glare, ROI completeness,
ridge clarity) are each computed, then combined into:
  1. hard pass/fail flags per metric (used to build the guidance message)
  2. a single 0-100 composite score (weighted, normalized blend)

`quality_gate()` is the single entry point downstream code should call.

All thresholds/weights have sensible defaults but can be overridden per-call
(this is what lets quality_app.py's sidebar sliders actually change
behavior instead of just being decorative).
"""

from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Defaults. Two kinds of numbers appear below for blur/roi/ridge:
#   *_reject       -- below this, the capture hard-fails on that metric
#   *_full_credit  -- at/above this, that metric contributes its FULL weight
#                      to the composite score (values between reject and
#                      full_credit get partial credit, scaled linearly)
# This means a capture can clear the hard-fail bar but still pull the
# composite score down for being marginal -- which is the point of having
# both a composite score AND per-metric pass/fail flags.
# ---------------------------------------------------------------------------
DEFAULT_THRESHOLDS = {
    "blur_reject": 10.0,
    "blur_full_credit": 50.0,
    "brightness_min": 50.0,
    "brightness_max": 210.0,
    "glare_reject": 0.05,
    "roi_reject": 0.15,
    "roi_full_credit": 0.30,
    "ridge_reject": 15.0,
    "ridge_full_credit": 30.0,
}

DEFAULT_WEIGHTS = {
    "blur": 0.25,
    "brightness": 0.15,
    "glare": 0.15,
    "roi": 0.20,
    "ridge": 0.25,
}

PASS_SCORE_THRESHOLD = 60.0


def _load_bgr(image_path_or_array):
    if isinstance(image_path_or_array, (str, Path)):
        img = cv2.imread(str(image_path_or_array))
        if img is None:
            raise ValueError(f"Could not read image at '{image_path_or_array}' "
                              f"(bad path, unsupported format, or corrupt file).")
        return img
    if isinstance(image_path_or_array, np.ndarray):
        return image_path_or_array
    raise TypeError(f"Expected a file path or a BGR numpy array, got {type(image_path_or_array)}")


# ---------------------------------------------------------------------------
# Metric 1: Blur
# ---------------------------------------------------------------------------
def check_blur(image_bgr: np.ndarray, threshold: float = 10.0) -> dict:
    """Laplacian-variance blur detection.

    The Laplacian is a 2nd-derivative edge operator -- it responds strongly
    wherever intensity changes sharply (real edges/ridges) and weakly over
    smooth regions. A sharp photo has lots of well-defined edges, so its
    Laplacian response has high VARIANCE across the image. A blurry photo's
    edges are smeared out, so the Laplacian response stays close to flat
    everywhere -> low variance.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return {
        "blur_score": round(blur_score, 2),
        "is_blurry": blur_score < threshold,
    }


# ---------------------------------------------------------------------------
# Metric 2: Brightness
# ---------------------------------------------------------------------------
def check_brightness(image_bgr: np.ndarray, min_thresh: float = 50.0, max_thresh: float = 210.0) -> dict:
    """Mean grayscale intensity -- flags underexposed / overexposed frames."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    return {
        "brightness": round(brightness, 2),
        "too_dark": brightness < min_thresh,
        "too_bright": brightness > max_thresh,
    }


# ---------------------------------------------------------------------------
# Metric 3: Glare
# ---------------------------------------------------------------------------
def check_glare(image_bgr: np.ndarray, max_glare_ratio: float = 0.05) -> dict:
    """Fraction of near-saturated pixels (>240/255) -- specular highlight glare."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    glare_pixels = int(np.sum(gray > 240))
    total_pixels = gray.size
    glare_fraction = float(glare_pixels / total_pixels)
    return {
        "glare_fraction": round(glare_fraction, 4),
        "has_glare": glare_fraction > max_glare_ratio,
    }


# ---------------------------------------------------------------------------
# Metric 4: ROI (finger) completeness
# ---------------------------------------------------------------------------
def check_roi_completeness(image_bgr: np.ndarray, min_roi_ratio: float = 0.15) -> dict:
    """Estimates what fraction of the frame the finger occupies.

    Plain Otsu thresholding splits the image into two intensity classes but
    has no idea which class is "finger" and which is "background" -- on a
    dark background it's the bright class, on a light background it's the
    reverse, and either way it's a coin flip. We resolve that ambiguity with
    a cheap, reasonable assumption for a camera-guided capture UI: the
    finger should be roughly centered, so whichever class dominates the
    center of the frame is treated as foreground. A light morphological
    open+close pass then cleans up small speckle noise from the threshold.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    h, w = thresh.shape
    cy0, cy1 = int(h * 0.25), int(h * 0.75)
    cx0, cx1 = int(w * 0.25), int(w * 0.75)
    center_white_fraction = np.mean(thresh[cy0:cy1, cx0:cx1] > 0)
    if center_white_fraction < 0.5:
        thresh = cv2.bitwise_not(thresh)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    roi_fraction = float(np.sum(mask > 0) / mask.size)

    return {
        "roi_fraction": round(roi_fraction, 4),
        "roi_complete": roi_fraction >= min_roi_ratio,
        "mask": mask,  # not JSON-serializable -- consumers should pop() this before logging/saving
    }


# ---------------------------------------------------------------------------
# Metric 5: Ridge clarity
# ---------------------------------------------------------------------------
def check_ridge_clarity(image_bgr: np.ndarray, threshold: float = 15.0, roi_mask: np.ndarray = None) -> dict:
    """Gabor-filter response variance -- measures how much ridge-like
    periodic texture is present.

    A Gabor kernel is a sinusoid windowed by a Gaussian; tuned to a
    ridge-like spatial frequency/orientation, it responds strongly to
    repeating ridge-valley patterns and weakly to smooth or random texture.
    If `roi_mask` is provided (from check_roi_completeness), the variance is
    computed ONLY over finger pixels -- otherwise background clutter (e.g. a
    textured tabletop) can dominate the statistic and produce a misleadingly
    high score even when the finger itself is smeared/out of focus.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getGaborKernel((21, 21), sigma=5.0, theta=np.pi / 4, lambd=10.0, gamma=0.5, psi=0)
    filtered = cv2.filter2D(gray, cv2.CV_64F, kernel)

    if roi_mask is not None and np.sum(roi_mask > 0) > 0:
        values = filtered[roi_mask > 0]
    else:
        values = filtered.ravel()

    ridge_score = float(np.var(values) / 100.0)
    return {
        "ridge_score": round(ridge_score, 2),
        "ridges_clear": ridge_score >= threshold,
    }


# ---------------------------------------------------------------------------
# Composite score + master gate
# ---------------------------------------------------------------------------
def _normalize(value, reject_point, full_credit_point):
    """Linearly maps value -> [0, 1]: 0 at/below reject_point, 1 at/above
    full_credit_point, linear in between. Used for metrics where MORE is
    better (blur, roi, ridge)."""
    if full_credit_point <= reject_point:
        raise ValueError("full_credit_point must be greater than reject_point")
    return float(np.clip((value - reject_point) / (full_credit_point - reject_point), 0.0, 1.0))


def quality_gate(image_path_or_array, thresholds: dict = None, weights: dict = None) -> dict:
    """Master Quality Control Pipeline. Runs all 5 metrics, computes the
    composite score, decides pass/fail, and resolves a single guidance
    message (first failing check wins, in a fixed priority order).

    Args:
        image_path_or_array: file path (str/Path) or a BGR numpy array
            (e.g. from cv2.imread or an uploaded file already decoded).
        thresholds: optional dict overriding any keys in DEFAULT_THRESHOLDS
            (partial overrides are fine -- unspecified keys keep defaults).
        weights: optional dict overriding any keys in DEFAULT_WEIGHTS.

    Returns a dict; see README for the exact shape.
    """
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    img = _load_bgr(image_path_or_array)

    blur_res = check_blur(img, threshold=t["blur_reject"])
    bright_res = check_brightness(img, min_thresh=t["brightness_min"], max_thresh=t["brightness_max"])
    glare_res = check_glare(img, max_glare_ratio=t["glare_reject"])
    roi_res = check_roi_completeness(img, min_roi_ratio=t["roi_reject"])

    # Erode the ROI mask before measuring ridge clarity so the high-contrast
    # finger/background BOUNDARY itself (a segmentation artifact, not
    # fingerprint texture) doesn't dominate the Gabor-response variance.
    erosion_kernel = np.ones((15, 15), np.uint8)
    eroded_mask = cv2.erode(roi_res["mask"], erosion_kernel)
    ridge_res = check_ridge_clarity(img, threshold=t["ridge_reject"], roi_mask=eroded_mask)

    n_blur = _normalize(blur_res["blur_score"], t["blur_reject"], t["blur_full_credit"])
    n_bright = max(0.0, 1.0 - abs(bright_res["brightness"] - 128.0) / 128.0)
    n_glare = max(0.0, 1.0 - (glare_res["glare_fraction"] / t["glare_reject"]))
    n_roi = _normalize(roi_res["roi_fraction"], t["roi_reject"], t["roi_full_credit"])
    n_ridge = _normalize(ridge_res["ridge_score"], t["ridge_reject"], t["ridge_full_credit"])

    composite = 100.0 * (
        w["blur"] * n_blur
        + w["brightness"] * n_bright
        + w["glare"] * n_glare
        + w["roi"] * n_roi
        + w["ridge"] * n_ridge
    )
    composite_score = round(composite, 1)

    has_hard_failure = (
        blur_res["is_blurry"]
        or bright_res["too_dark"] or bright_res["too_bright"]
        or glare_res["has_glare"]
        or not roi_res["roi_complete"]
        or not ridge_res["ridges_clear"]
    )
    passed = (composite_score >= PASS_SCORE_THRESHOLD) and (not has_hard_failure)

    # Priority order matches the assignment's guidance matrix: report the
    # first actionable problem rather than overwhelming the user with all
    # of them at once.
    if blur_res["is_blurry"]:
        guidance = "Too blurry — hold your hand steady and re-focus."
    elif bright_res["too_dark"]:
        guidance = "Too dark — move to a brighter spot or turn on flash."
    elif bright_res["too_bright"]:
        guidance = "Too bright — reduce direct light source exposure."
    elif glare_res["has_glare"]:
        guidance = "Glare detected — tilt finger slightly to eliminate reflections."
    elif not roi_res["roi_complete"]:
        guidance = "Finger incomplete — position your fingertip within the camera guide."
    elif not ridge_res["ridges_clear"]:
        guidance = "Low ridge contrast — clean lens or re-position finger."
    else:
        guidance = "Good capture — ready for processing."

    roi_res_public = {k: v for k, v in roi_res.items() if k != "mask"}  # drop non-serializable mask

    return {
        "passed": passed,
        "composite_score": composite_score,
        "blur": blur_res,
        "brightness": bright_res,
        "glare": glare_res,
        "roi": roi_res_public,
        "ridge": ridge_res,
        "guidance": guidance,
    }
