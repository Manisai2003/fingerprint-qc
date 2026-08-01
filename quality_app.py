"""
quality_app.py
---------------
Streamlit dashboard for the fingerprint capture QC gate:
  - drag-and-drop image upload
  - composite score, shown big, green/red
  - PASS/FAIL badge per individual metric
  - guidance banner
  - sidebar sliders so every threshold is live-adjustable (not hardcoded)

Run with:
    streamlit run quality_app.py
"""

import cv2
import numpy as np
import streamlit as st
from PIL import Image

from quality_assessment import quality_gate, DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, PASS_SCORE_THRESHOLD

st.set_page_config(page_title="Fingerprint QC Gate", page_icon="📱", layout="wide")
st.title("📱 Contactless Fingerprint Quality Control System")
st.caption("Upload a capture to see the 5-metric quality gate evaluate it in real time.")

# --------------------------------------------------------------------------
# Sidebar: live threshold tuning
# --------------------------------------------------------------------------
st.sidebar.header("QC Threshold Settings")
st.sidebar.caption("Adjust and the result below updates immediately.")

blur_reject = st.sidebar.slider("Blur reject threshold (Laplacian var)", 1.0, 100.0, DEFAULT_THRESHOLDS["blur_reject"])
brightness_min = st.sidebar.slider("Min brightness (too dark below)", 0, 120, int(DEFAULT_THRESHOLDS["brightness_min"]))
brightness_max = st.sidebar.slider("Max brightness (too bright above)", 150, 255, int(DEFAULT_THRESHOLDS["brightness_max"]))
glare_reject = st.sidebar.slider("Max glare fraction", 0.01, 0.30, DEFAULT_THRESHOLDS["glare_reject"], step=0.01)
roi_reject = st.sidebar.slider("Min ROI (finger area) fraction", 0.02, 0.50, DEFAULT_THRESHOLDS["roi_reject"], step=0.01)
ridge_reject = st.sidebar.slider("Ridge clarity reject threshold", 1.0, 60.0, DEFAULT_THRESHOLDS["ridge_reject"])

with st.sidebar.expander("Composite score weights"):
    w_blur = st.slider("Weight: blur", 0.0, 1.0, DEFAULT_WEIGHTS["blur"])
    w_bright = st.slider("Weight: brightness", 0.0, 1.0, DEFAULT_WEIGHTS["brightness"])
    w_glare = st.slider("Weight: glare", 0.0, 1.0, DEFAULT_WEIGHTS["glare"])
    w_roi = st.slider("Weight: ROI", 0.0, 1.0, DEFAULT_WEIGHTS["roi"])
    w_ridge = st.slider("Weight: ridge", 0.0, 1.0, DEFAULT_WEIGHTS["ridge"])
    weight_sum = w_blur + w_bright + w_glare + w_roi + w_ridge
    if abs(weight_sum - 1.0) > 1e-6:
        st.caption(f"⚠️ Weights sum to {weight_sum:.2f}, not 1.0 — scores are still computed, "
                   f"just not on a clean 0-100 scale until these are rebalanced.")

thresholds = {
    "blur_reject": blur_reject,
    "blur_full_credit": DEFAULT_THRESHOLDS["blur_full_credit"],
    "brightness_min": brightness_min,
    "brightness_max": brightness_max,
    "glare_reject": glare_reject,
    "roi_reject": roi_reject,
    "roi_full_credit": DEFAULT_THRESHOLDS["roi_full_credit"],
    "ridge_reject": ridge_reject,
    "ridge_full_credit": DEFAULT_THRESHOLDS["ridge_full_credit"],
}
weights = {"blur": w_blur, "brightness": w_bright, "glare": w_glare, "roi": w_roi, "ridge": w_ridge}

# --------------------------------------------------------------------------
# Main panel
# --------------------------------------------------------------------------
uploaded_file = st.file_uploader("Upload a fingerprint capture", type=["jpg", "jpeg", "png", "bmp"])

if uploaded_file is not None:
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    image_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

    if image_bgr is None:
        st.error("Could not decode that file as an image. Try a different file.")
    else:
        res = quality_gate(image_bgr, thresholds=thresholds, weights=weights)

        col1, col2 = st.columns([1, 1])

        with col1:
            st.image(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB), caption="Uploaded Image", use_container_width=True)

        with col2:
            score = res["composite_score"]
            if res["passed"]:
                st.success(f"### Composite Score: {score} / 100 — PASSED")
            else:
                st.error(f"### Composite Score: {score} / 100 — REJECTED")

            st.info(f"**Guidance:** {res['guidance']}")

            st.markdown("#### Quality Checks Breakdown")

            def badge(ok):
                return "✅ PASS" if ok else "❌ FAIL"

            st.write(f"**Blur:** {badge(not res['blur']['is_blurry'])} "
                     f"(Laplacian var: {res['blur']['blur_score']}, reject below {blur_reject:.1f})")
            st.write(f"**Brightness:** {badge(not (res['brightness']['too_dark'] or res['brightness']['too_bright']))} "
                     f"(mean: {res['brightness']['brightness']}, valid range {brightness_min}–{brightness_max})")
            st.write(f"**Glare:** {badge(not res['glare']['has_glare'])} "
                     f"(fraction: {res['glare']['glare_fraction']}, reject above {glare_reject:.2f})")
            st.write(f"**ROI Completeness:** {badge(res['roi']['roi_complete'])} "
                     f"(fraction: {res['roi']['roi_fraction']}, reject below {roi_reject:.2f})")
            st.write(f"**Ridge Clarity:** {badge(res['ridge']['ridges_clear'])} "
                     f"(score: {res['ridge']['ridge_score']}, reject below {ridge_reject:.1f})")

        with st.expander("Raw result dict (for debugging)"):
            st.json(res)
else:
    st.info("⬆️ Upload an image to see the quality gate evaluate it. "
            "Try adjusting the sidebar thresholds and re-uploading to see how the decision changes.")
