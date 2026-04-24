"""
main.py
=======
Entry point – runs the full pipeline (Task-1 → Task-2 → Task-3) on a pair of PDFs.

Usage (from project root):
    python main.py <doc1.pdf> <doc2.pdf>

Example:
    python main.py cis-r1.pdf cis-r2.pdf

Pipeline:
    Task-1  PDF → LLM → YAML (one per document × prompt-type)
    Task-2  two YAMLs → name-diff TEXT + requirement-diff TEXT
    Task-3  diff TEXTs → Kubescape controls TEXT → CSV

All output files are written to ./output/
"""

import argparse
import shutil
import sys
from pathlib import Path

from task1.extractor import (
    validate_and_load_documents,
    construct_zero_shot_prompt,
    construct_few_shot_prompt,
    construct_chain_of_thought_prompt,
    extract_kdes_with_llm,
    collect_llm_outputs,
    load_gemma_pipeline,
    MODEL_NAME,
)
from task2.comparator import (
    load_yaml_files,
    compare_element_names,
    compare_elements_and_requirements,
)
from task3.executor import (
    load_task2_outputs,
    map_differences_to_controls,
    run_kubescape,
    generate_csv,
)

OUTPUT_DIR = "output"

# Prompt type used to produce the YAMLs that feed Task-2 / Task-3.
# few_shot gave the cleanest KDE output in our testing.
COMPARISON_PROMPT_TYPE = "few_shot"

PROMPT_BUILDERS = {
    "zero_shot":        construct_zero_shot_prompt,
    "few_shot":         construct_few_shot_prompt,
    "chain_of_thought": construct_chain_of_thought_prompt,
}


# ── Task 1 ────────────────────────────────────────────────────────────────
def run_task1(pdf1: str, pdf2: str) -> list[str]:
    """
    Run LLM-based KDE extraction on both PDFs across all three prompt types.
    Returns the list of YAML file stems that were written (e.g. "cis-r1").
    """
    pipe = load_gemma_pipeline()
    all_results: list[dict] = []

    fname1 = Path(pdf1).name
    fname2 = Path(pdf2).name
    print(f"\n{'='*60}\nTask-1: Processing {fname1}  vs  {fname2}\n{'='*60}")

    try:
        doc1, doc2 = validate_and_load_documents(pdf1, pdf2)
    except (FileNotFoundError, ValueError) as exc:
        print(f"  [ERROR] Could not load documents: {exc}")
        sys.exit(1)

    docs_to_process = [doc1]
    if doc1["path"] != doc2["path"]:
        docs_to_process.append(doc2)

    for doc in docs_to_process:
        for ptype, builder in PROMPT_BUILDERS.items():
            prompt = builder(doc["text"])
            kde_dict, raw = extract_kdes_with_llm(
                doc_info=doc,
                prompt=prompt,
                prompt_type=ptype,
                llm_pipe=pipe,
                output_dir=OUTPUT_DIR,
                prompt_builder=builder,
            )
            all_results.append({
                "llm_name":    MODEL_NAME,
                "doc_name":    doc["filename"],
                "prompt_type": ptype,
                "prompt":      prompt,
                "output":      raw,
            })
            print(f"  ✓ {doc['filename']} | {ptype} -> {len(kde_dict)} KDEs")

    out_txt = str(Path(OUTPUT_DIR) / "llm_outputs.txt")
    collect_llm_outputs(all_results, output_file=out_txt)
    print(f"Task-1 complete. LLM outputs -> {out_txt}")

    # Distinct document stems used downstream by Task-2
    return [doc["filename"] for doc in docs_to_process]


# ── Task 2 ────────────────────────────────────────────────────────────────
def run_task2(doc_stems: list[str]) -> tuple[str, str] | None:
    """
    Compare the YAMLs produced by Task-1 for the two documents using the
    configured COMPARISON_PROMPT_TYPE.

    If both PDFs were identical (only one stem), Task-2 is skipped.
    Returns (name_diffs_path, requirement_diffs_path) on success, else None.
    """
    print(f"\n{'='*60}\nTask-2: Comparing YAMLs ({COMPARISON_PROMPT_TYPE})\n{'='*60}")

    if len(doc_stems) < 2:
        print("  [SKIP] Both inputs are the same document — no comparison to run.")
        return None

    yaml1 = Path(OUTPUT_DIR) / f"{doc_stems[0]}-kdes-{COMPARISON_PROMPT_TYPE}.yaml"
    yaml2 = Path(OUTPUT_DIR) / f"{doc_stems[1]}-kdes-{COMPARISON_PROMPT_TYPE}.yaml"

    if not yaml1.exists() or not yaml2.exists():
        print(f"  [ERROR] Expected YAMLs missing: {yaml1.name}, {yaml2.name}")
        return None

    d1, d2, n1, n2 = load_yaml_files(str(yaml1), str(yaml2))

    name_diffs_path = str(Path(OUTPUT_DIR) / "name_differences.txt")
    req_diffs_path = str(Path(OUTPUT_DIR) / "requirement_differences.txt")

    compare_element_names(d1, d2, n1, n2, output_file=name_diffs_path)
    compare_elements_and_requirements(d1, d2, n1, n2, output_file=req_diffs_path)

    print(f"  ✓ Name diffs        -> {name_diffs_path}")
    print(f"  ✓ Requirement diffs -> {req_diffs_path}")
    return name_diffs_path, req_diffs_path


# ── Task 3 ────────────────────────────────────────────────────────────────
def run_task3(diff_paths: tuple[str, str], scan_target: str | None) -> None:
    """
    Map diffs to Kubescape controls, run Kubescape, write CSV.
    Skips the scan gracefully if the kubescape executable isn't on PATH.
    """
    print(f"\n{'='*60}\nTask-3: Kubescape scan\n{'='*60}")

    name_text, req_text = load_task2_outputs(*diff_paths)
    controls_file = str(Path(OUTPUT_DIR) / "kubescape_controls.txt")
    map_differences_to_controls(name_text, req_text, output_file=controls_file)
    print(f"  ✓ Controls mapping -> {controls_file}")

    if not scan_target:
        print("  [SKIP] No --scan-target provided — skipping Kubescape execution.")
        return

    if shutil.which("kubescape") is None:
        print("  [SKIP] 'kubescape' not found on PATH — skipping scan.")
        print("         Install from https://github.com/kubescape/kubescape")
        return

    try:
        df = run_kubescape(controls_file, scan_target)
        csv_path = str(Path(OUTPUT_DIR) / "kubescape_results.csv")
        generate_csv(df, output_file=csv_path)
        print(f"  ✓ Scan rows: {len(df)} -> {csv_path}")
    except Exception as exc:
        print(f"  [WARN] Kubescape scan failed: {exc}")


# ── CLI ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="COMP-5700 Project – full pipeline (Task-1 / 2 / 3)"
    )
    parser.add_argument("pdf1", help="Path to the first PDF file")
    parser.add_argument("pdf2", help="Path to the second PDF file")
    parser.add_argument(
        "--scan-target",
        default=None,
        help="Path (dir or zip) of Kubernetes YAMLs for Task-3 Kubescape scan. "
             "If omitted, Task-3 only writes the controls-mapping file.",
    )
    args = parser.parse_args()

    doc_stems = run_task1(args.pdf1, args.pdf2)
    diff_paths = run_task2(doc_stems)
    if diff_paths:
        run_task3(diff_paths, args.scan_target)

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
