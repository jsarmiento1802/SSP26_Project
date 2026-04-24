"""
main.py
=======
Entry point – runs Task-1 KDE extraction on a pair of PDF files.

Usage (from project root):
    python main.py <doc1.pdf> <doc2.pdf>

Example:
    python main.py cis-r1.pdf cis-r2.pdf

All output files are written to ./output/
"""

import argparse
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

OUTPUT_DIR = "output"

PROMPT_BUILDERS = {
    "zero_shot":        construct_zero_shot_prompt,
    "few_shot":         construct_few_shot_prompt,
    "chain_of_thought": construct_chain_of_thought_prompt,
}


def run_task1(pdf1: str, pdf2: str) -> None:
    """Process a single pair of PDFs through all three prompt strategies."""
    pipe = load_gemma_pipeline()
    all_results = []

    fname1 = Path(pdf1).name
    fname2 = Path(pdf2).name

    print(f"\n{'='*60}")
    print(f"Processing: {fname1}  vs  {fname2}")
    print(f"{'='*60}")

    try:
        doc1, doc2 = validate_and_load_documents(pdf1, pdf2)
    except (FileNotFoundError, ValueError) as exc:
        print(f"  [ERROR] Could not load documents: {exc}")
        sys.exit(1)

    # Determine unique docs to avoid processing the same file twice
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
            all_results.append(
                {
                    "llm_name":    MODEL_NAME,
                    "doc_name":    doc["filename"],
                    "prompt_type": ptype,
                    "prompt":      prompt,
                    "output":      raw,
                }
            )
            print(f"  ✓ {doc['filename']} | {ptype} → {len(kde_dict)} KDEs found")

    out_txt = str(Path(OUTPUT_DIR) / "llm_outputs.txt")
    collect_llm_outputs(all_results, output_file=out_txt)
    print(f"\nDone. LLM outputs written to: {out_txt}")


def main():
    parser = argparse.ArgumentParser(
        description="COMP-5700 Project – Task-1 KDE Extractor"
    )
    parser.add_argument(
        "pdf1",
        help="Path to the first PDF file",
    )
    parser.add_argument(
        "pdf2",
        help="Path to the second PDF file",
    )
    args = parser.parse_args()

    run_task1(args.pdf1, args.pdf2)


if __name__ == "__main__":
    main()
