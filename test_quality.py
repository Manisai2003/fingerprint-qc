"""
test_quality.py
-----------------
Batch-runs quality_gate() over every image in test_dataset/{good,blurry,
dark,glare}/ and builds a summary table, so you can verify at a glance that
each defect category is actually being flagged as the RIGHT defect (not
just flagged as *something*).

Usage:
    python test_quality.py
    python test_quality.py --dataset_dir test_dataset --out outputs/test_results.csv
"""

import argparse
import glob
import os
from pathlib import Path

import pandas as pd

from quality_assessment import quality_gate

# What each test_dataset/<folder> is expected to trigger. Used only to
# print a convenience "match?" column -- a real deployment wouldn't have
# these labels, but for verifying your implementation against images you
# captured on purpose, it's exactly the check you want.
EXPECTED_FLAG_BY_CATEGORY = {
    "good": lambda res: res["passed"],
    "blurry": lambda res: res["blur"]["is_blurry"],
    "dark": lambda res: res["brightness"]["too_dark"],
    "bright": lambda res: res["brightness"]["too_bright"],
    "glare": lambda res: res["glare"]["has_glare"],
}


def run_batch_tests(dataset_dir="test_dataset", out_csv="outputs/test_results.csv"):
    records = []
    image_paths = sorted(glob.glob(os.path.join(dataset_dir, "*", "*.*")))

    if not image_paths:
        print(f"No images found under '{dataset_dir}/<category>/'. "
              f"Add your 20 test photos first (see README).")
        return None

    for path in image_paths:
        category = os.path.basename(os.path.dirname(path))
        filename = os.path.basename(path)

        try:
            res = quality_gate(path)
        except Exception as e:
            print(f"[ERROR] {path}: {e}")
            continue

        check_fn = EXPECTED_FLAG_BY_CATEGORY.get(category)
        matched = check_fn(res) if check_fn else None

        records.append({
            "File": filename,
            "Category": category,
            "Passed": res["passed"],
            "Composite Score": res["composite_score"],
            "Blur Score": res["blur"]["blur_score"],
            "Is Blurry": res["blur"]["is_blurry"],
            "Brightness": res["brightness"]["brightness"],
            "Too Dark": res["brightness"]["too_dark"],
            "Too Bright": res["brightness"]["too_bright"],
            "Glare Fraction": res["glare"]["glare_fraction"],
            "Has Glare": res["glare"]["has_glare"],
            "ROI Fraction": res["roi"]["roi_fraction"],
            "Ridge Score": res["ridge"]["ridge_score"],
            "Guidance": res["guidance"],
            "Matches Expected Category": matched,
        })

    df = pd.DataFrame(records)

    print("\n================ QUALITY CONTROL BATCH EVALUATION ================\n")
    display_cols = ["File", "Category", "Passed", "Composite Score", "Guidance", "Matches Expected Category"]
    print(df[display_cols].to_string(index=False))

    if "Matches Expected Category" in df.columns and df["Matches Expected Category"].notna().any():
        known = df[df["Matches Expected Category"].notna()]
        n_correct = int(known["Matches Expected Category"].sum())
        n_total = len(known)
        print(f"\nCorrectly flagged: {n_correct}/{n_total} "
              f"({100 * n_correct / n_total:.0f}%)")
        mismatches = known[~known["Matches Expected Category"]]
        if len(mismatches) > 0:
            print("\nMismatches (worth a closer look / threshold tuning):")
            print(mismatches[["File", "Category", "Guidance"]].to_string(index=False))

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    print(f"\nFull results saved to {out_csv}")
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch-test quality_gate() against test_dataset/")
    parser.add_argument("--dataset_dir", default="test_dataset")
    parser.add_argument("--out", default="outputs/test_results.csv")
    args = parser.parse_args()
    run_batch_tests(args.dataset_dir, args.out)
