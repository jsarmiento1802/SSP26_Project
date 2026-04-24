"""
task1/extractor.py
==================
Task-1 – Extractor

Six public functions:
  1. validate_and_load_documents   – open & validate two PDFs, return text dicts
  2. construct_zero_shot_prompt    – build a zero-shot prompt string
  3. construct_few_shot_prompt     – build a few-shot prompt string
  4. construct_chain_of_thought_prompt – build a CoT prompt string
  5. extract_kdes_with_llm         – run Gemma-3-1b-it, save YAML, return (dict, raw_str)
  6. collect_llm_outputs           – aggregate all runs into a single TEXT file
"""

from __future__ import annotations

import json
import logging
import os
import re
import yaml
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF  (pip install pymupdf)

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
MODEL_NAME   = "google/gemma-3-1b-it"
MAX_NEW_TOKENS = 1024
# Gemma-3-1B has a ~8 k-token context window; we cap the document snippet
# fed to the model so we leave room for the prompt template + output.
DOC_CHAR_LIMIT = 4000


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 1 – validate_and_load_documents
# ══════════════════════════════════════════════════════════════════════════

def validate_and_load_documents(path1: str, path2: str) -> tuple[dict, dict]:
    """
    Open and validate two PDF files, returning their full text in structured dicts.

    Each returned dict has the shape:
        {
            "filename": str,   # stem of the file (e.g. "cis-r1")
            "path":     str,   # resolved absolute path
            "pages":    int,   # page count
            "text":     str,   # full extracted plain text
        }

    Raises:
        FileNotFoundError – if a path does not exist.
        ValueError        – if a path is not a PDF or contains no text.
    """

    def _load_one(raw_path: str) -> dict:
        resolved = Path(raw_path).resolve()

        # ── existence check ────────────────────────────────────────────────
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {resolved}")

        # ── extension check ────────────────────────────────────────────────
        if resolved.suffix.lower() != ".pdf":
            raise ValueError(
                f"Expected a .pdf file, got '{resolved.suffix}': {resolved}"
            )

        # ── open with PyMuPDF ──────────────────────────────────────────────
        try:
            fz_doc = fitz.open(str(resolved))
        except Exception as exc:
            raise ValueError(
                f"Cannot open PDF '{resolved.name}': {exc}"
            ) from exc

        page_count = fz_doc.page_count
        text_parts: list[str] = []
        for page in fz_doc:
            text_parts.append(page.get_text("text"))
        fz_doc.close()

        full_text = "\n".join(text_parts).strip()
        if not full_text:
            raise ValueError(
                f"PDF '{resolved.name}' contains no extractable text "
                "(it may be a scanned image-only PDF)."
            )

        logger.info(
            "Loaded '%s' — %d pages, %d chars",
            resolved.name, page_count, len(full_text),
        )
        return {
            "filename": resolved.stem,
            "path":     str(resolved),
            "pages":    page_count,
            "text":     full_text,
        }

    doc1 = _load_one(path1)
    doc2 = _load_one(path2)
    return doc1, doc2


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 2 – construct_zero_shot_prompt
# ══════════════════════════════════════════════════════════════════════════

def construct_zero_shot_prompt(doc_text: str) -> str:
    """
    Build a zero-shot prompt that instructs the model to identify Key Data
    Elements (KDEs) directly, without any examples.

    Args:
        doc_text: The plain-text content of one security-requirements document.

    Returns:
        A fully-formed prompt string ready to be passed to the LLM.
    """
    snippet = doc_text[:DOC_CHAR_LIMIT]

    prompt = (
        "You are an expert security analyst.\n\n"
        "Your task is to read the security requirements document below and "
        "identify all Key Data Elements (KDEs). A Key Data Element is a "
        "distinct security concept, asset, or control category mentioned in "
        "the document (e.g., 'User Authentication', 'Access Control', "
        "'Audit Logging').\n\n"
        "For each KDE, list every specific requirement from the document that "
        "belongs to that element.\n\n"
        "Output ONLY valid JSON — no prose, no markdown fences — with this "
        "exact structure:\n"
        "{\n"
        '  "element1": {\n'
        '    "name": "<kde name>",\n'
        '    "requirements": ["<req 1>", "<req 2>"]\n'
        "  },\n"
        '  "element2": {\n'
        '    "name": "<kde name>",\n'
        '    "requirements": ["<req 1>"]\n'
        "  }\n"
        "}\n\n"
        "--- DOCUMENT START ---\n"
        f"{snippet}\n"
        "--- DOCUMENT END ---\n\n"
        "JSON:"
    )
    return prompt


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 3 – construct_few_shot_prompt
# ══════════════════════════════════════════════════════════════════════════

def construct_few_shot_prompt(doc_text: str) -> str:
    """
    Build a few-shot prompt with two worked examples so the model understands
    exactly the expected input–output mapping before seeing the real document.

    Args:
        doc_text: The plain-text content of one security-requirements document.

    Returns:
        A fully-formed prompt string ready to be passed to the LLM.
    """
    snippet = doc_text[:DOC_CHAR_LIMIT]

    prompt = (
        "You are an expert security analyst.\n\n"
        "Your task is to read a security requirements document and identify "
        "all Key Data Elements (KDEs), each paired with the requirements that "
        "belong to it.\n\n"
        "Study the two examples below, then process the real document.\n\n"
        "=== EXAMPLE 1 ===\n"
        "Document snippet:\n"
        "  1.1 Ensure unique usernames are assigned to every user account.\n"
        "  1.2 Disable or remove accounts that have been inactive for 90 days.\n"
        "  1.3 Require multi-factor authentication for all privileged accounts.\n"
        "\n"
        "Expected JSON output:\n"
        '{"element1": {"name": "User Account Management", "requirements": [\n'
        '  "Ensure unique usernames are assigned to every user account.",\n'
        '  "Disable or remove accounts that have been inactive for 90 days.",\n'
        '  "Require multi-factor authentication for all privileged accounts."]}}\n'
        "\n"
        "=== EXAMPLE 2 ===\n"
        "Document snippet:\n"
        "  3.1 Enable audit logging for all authentication events.\n"
        "  3.2 Retain audit logs for a minimum of 90 days.\n"
        "  4.1 Encrypt all data at rest using AES-256 or stronger.\n"
        "  4.2 Encrypt all data in transit using TLS 1.2 or higher.\n"
        "\n"
        "Expected JSON output:\n"
        '{"element1": {"name": "Audit Logging", "requirements": [\n'
        '  "Enable audit logging for all authentication events.",\n'
        '  "Retain audit logs for a minimum of 90 days."]},\n'
        ' "element2": {"name": "Data Encryption", "requirements": [\n'
        '  "Encrypt all data at rest using AES-256 or stronger.",\n'
        '  "Encrypt all data in transit using TLS 1.2 or higher."]}}\n'
        "\n"
        "=== NOW PROCESS THE REAL DOCUMENT ===\n"
        "Output ONLY valid JSON — no prose, no markdown fences.\n\n"
        "--- DOCUMENT START ---\n"
        f"{snippet}\n"
        "--- DOCUMENT END ---\n\n"
        "JSON:"
    )
    return prompt


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 4 – construct_chain_of_thought_prompt
# ══════════════════════════════════════════════════════════════════════════

def construct_chain_of_thought_prompt(doc_text: str) -> str:
    """
    Build a chain-of-thought prompt that walks the model through explicit
    reasoning steps before producing the final structured output.

    Args:
        doc_text: The plain-text content of one security-requirements document.

    Returns:
        A fully-formed prompt string ready to be passed to the LLM.
    """
    snippet = doc_text[:DOC_CHAR_LIMIT]

    prompt = (
        "You are an expert security analyst.\n\n"
        "Follow these reasoning steps carefully before writing your answer:\n\n"
        "STEP 1 – Scan the document and list every distinct security topic, "
        "control category, or asset type you encounter (e.g., 'passwords', "
        "'network access', 'logging'). These are candidate Key Data Elements (KDEs).\n\n"
        "STEP 2 – For each candidate KDE from Step 1, collect every sentence "
        "or numbered clause in the document that belongs to that KDE.\n\n"
        "STEP 3 – Give each KDE a clear, concise name that captures its "
        "security theme (e.g., 'Password Policy', 'Network Access Control').\n\n"
        "STEP 4 – Format your final answer as ONLY valid JSON — no prose, "
        "no markdown fences — using this structure:\n"
        "{\n"
        '  "element1": {\n'
        '    "name": "<kde name from Step 3>",\n'
        '    "requirements": ["<clause from Step 2>", ...]\n'
        "  },\n"
        '  "element2": { ... }\n'
        "}\n\n"
        "--- DOCUMENT START ---\n"
        f"{snippet}\n"
        "--- DOCUMENT END ---\n\n"
        "Work through Steps 1-3 briefly, then output the JSON in Step 4:\n"
    )
    return prompt


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 5 – extract_kdes_with_llm
# ══════════════════════════════════════════════════════════════════════════

def extract_kdes_with_llm(
    doc_info: dict,
    prompt: str,
    prompt_type: str,
    llm_pipe,
    output_dir: str = "output",
    prompt_builder=None,
) -> tuple[dict, str]:
    """
    Send *prompt* to the Gemma-3-1b-it pipeline, parse the response into the
    required nested KDE dict, and save it as a YAML file.

    When *prompt_builder* is provided and the document text exceeds
    ``DOC_CHAR_LIMIT``, the text is split into overlapping chunks and
    each chunk is processed independently.  The resulting KDE dicts are
    merged and deduplicated before saving.

    Args:
        doc_info:       Dict returned by validate_and_load_documents for one doc.
        prompt:         A fully-formed prompt string (from one of the builders).
        prompt_type:    One of "zero_shot" | "few_shot" | "chain_of_thought".
        llm_pipe:       A HuggingFace transformers ``pipeline`` object.
        output_dir:     Directory where YAML files are written.
        prompt_builder: Optional callable(text) -> str.  When supplied, enables
                        automatic chunking for documents longer than DOC_CHAR_LIMIT.

    Returns:
        (kde_dict, raw_output) where:
            kde_dict   – nested dict  {element1: {name: ..., requirements: [...]}, ...}
            raw_output – the raw text string returned by the LLM
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    chunks = _chunk_text(doc_info["text"])
    use_chunking = len(chunks) > 1 and prompt_builder is not None

    if use_chunking:
        logger.info(
            "Document '%s' split into %d chunks for %s.",
            doc_info["filename"], len(chunks), prompt_type,
        )

    # ── call the LLM (once per chunk) ──────────────────────────────────────
    chunk_kde_dicts: list[dict] = []
    raw_parts: list[str] = []

    prompts_to_run = (
        [prompt_builder(c) for c in chunks] if use_chunking else [prompt]
    )

    for chunk_idx, cur_prompt in enumerate(prompts_to_run, start=1):
        if use_chunking:
            logger.info(
                "  chunk %d/%d (%s | %s | doc=%s) ...",
                chunk_idx, len(prompts_to_run),
                MODEL_NAME, prompt_type, doc_info["filename"],
            )
        else:
            logger.info(
                "Running LLM (%s | %s | doc=%s) ...",
                MODEL_NAME, prompt_type, doc_info["filename"],
            )

        messages = [{"role": "user", "content": cur_prompt}]
        response = llm_pipe(messages, max_new_tokens=MAX_NEW_TOKENS)

        raw_output: str = response[0]["generated_text"]
        if isinstance(raw_output, list):
            for turn in reversed(raw_output):
                if isinstance(turn, dict) and turn.get("role") == "assistant":
                    raw_output = turn.get("content", "")
                    break
        raw_output = str(raw_output)

        chunk_kde_dicts.append(_parse_kdes_from_text(raw_output))
        raw_parts.append(raw_output)

    # ── merge results across chunks ────────────────────────────────────────
    kde_dict = _merge_kde_dicts(chunk_kde_dicts) if use_chunking else chunk_kde_dicts[0]
    combined_raw = ("\n\n--- CHUNK BOUNDARY ---\n\n".join(raw_parts)
                    if use_chunking else raw_parts[0])

    # ── save YAML ──────────────────────────────────────────────────────────
    yaml_name = f"{doc_info['filename']}-kdes-{prompt_type}.yaml"
    yaml_path = Path(output_dir) / yaml_name
    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.dump(kde_dict, fh, default_flow_style=False, allow_unicode=True)
    logger.info("Saved YAML → %s", yaml_path)

    return kde_dict, combined_raw


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 6 – collect_llm_outputs
# ══════════════════════════════════════════════════════════════════════════

def collect_llm_outputs(
    results: list[dict],
    output_file: str = "output/llm_outputs.txt",
) -> str:
    """
    Aggregate every LLM run into a single, human-readable TEXT file.

    Args:
        results: A list of dicts, each containing:
            {
                "llm_name":   str,   # e.g. "google/gemma-3-1b-it"
                "prompt":     str,   # the exact prompt sent to the model
                "prompt_type":str,   # "zero_shot" | "few_shot" | "chain_of_thought"
                "output":     str,   # raw LLM output
                "doc_name":   str,   # document filename stem
            }
        output_file: Path (including filename) where the TEXT file is written.

    Returns:
        The absolute path of the written file as a string.
    """
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    sep = "=" * 72

    lines: list[str] = [
        sep,
        "LLM OUTPUTS REPORT",
        f"Total runs: {len(results)}",
        sep,
        "",
    ]

    for i, entry in enumerate(results, start=1):
        lines += [
            f"--- Run {i} ---",
            f"*LLM Name*",
            entry.get("llm_name", MODEL_NAME),
            "",
            f"*Document*",
            entry.get("doc_name", "N/A"),
            "",
            f"*Prompt Type*",
            entry.get("prompt_type", "N/A"),
            "",
            f"*Prompt Used*",
            entry.get("prompt", ""),
            "",
            f"*LLM Output*",
            entry.get("output", ""),
            "",
            sep,
            "",
        ]

    text_body = "\n".join(lines)
    with open(output_file, "w", encoding="utf-8") as fh:
        fh.write(text_body)
    logger.info("Saved LLM outputs → %s", output_file)
    return str(Path(output_file).resolve())


# ══════════════════════════════════════════════════════════════════════════
# HELPERS  (not part of the public API)
# ══════════════════════════════════════════════════════════════════════════

def load_gemma_pipeline():
    """
    Load the Gemma-3-1b-it model and return a HuggingFace text-generation
    pipeline.

    Requirements:
        • A HuggingFace account with the Gemma-3 licence accepted.
        • The environment variable HF_TOKEN set to your access token.
        • ≥ 6 GB RAM (CPU) or ≥ 4 GB VRAM (GPU).

    Returns:
        A ``transformers.pipeline`` object.
    """
    import torch
    from transformers import pipeline as hf_pipeline

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        logger.warning(
            "HF_TOKEN is not set. You may hit an authentication error for the "
            "gated Gemma model. Export HF_TOKEN=<your token> and retry."
        )

    device_map = "auto" if torch.cuda.is_available() else "cpu"
    dtype      = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    logger.info("Loading %s on device_map=%s …", MODEL_NAME, device_map)
    pipe = hf_pipeline(
        "text-generation",
        model=MODEL_NAME,
        torch_dtype=dtype,
        device_map=device_map,
        token=hf_token,
    )
    logger.info("Model loaded.")
    return pipe


def _chunk_text(
    text: str,
    chunk_size: int = DOC_CHAR_LIMIT,
    overlap: int = 200,
) -> list[str]:
    """
    Split *text* into chunks of at most *chunk_size* characters with
    *overlap* characters repeated between consecutive chunks so that
    requirements spanning a boundary are captured in at least one chunk.

    Splits prefer paragraph breaks (``\\n\\n``), then line breaks
    (``\\n``), then sentence endings (``. ``).  Falls back to a hard
    cut when no natural boundary is found.

    Returns a list with at least one element.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Last chunk – just take the rest
        if end >= len(text):
            chunks.append(text[start:])
            break

        # Try to find a natural split point within the last 400 chars
        window = text[end - 400 : end]
        split_offset = -1
        for sep in ("\n\n", "\n", ". "):
            pos = window.rfind(sep)
            if pos != -1:
                split_offset = (end - 400) + pos + len(sep)
                break

        if split_offset <= start:
            split_offset = end  # hard cut

        chunks.append(text[start:split_offset])
        start = max(split_offset - overlap, start + 1)

    return chunks


def _merge_kde_dicts(kde_dicts: list[dict]) -> dict:
    """
    Merge KDE dicts from multiple chunks into a single dict, deduplicating
    elements by normalised name and requirements by exact (lowered) match.

    Returns a dict keyed ``element1``, ``element2``, … with merged results.
    """
    if len(kde_dicts) == 1:
        return kde_dicts[0]

    merged: dict[str, dict] = {}  # norm_name -> {name, requirements, seen_reqs}

    for kde_dict in kde_dicts:
        for _key, elem in kde_dict.items():
            name = elem.get("name", "")
            norm = name.lower().strip()
            reqs = elem.get("requirements", [])

            if norm in merged:
                entry = merged[norm]
                for r in reqs:
                    if r.lower().strip() not in entry["seen_reqs"]:
                        entry["requirements"].append(r)
                        entry["seen_reqs"].add(r.lower().strip())
            else:
                seen = {r.lower().strip() for r in reqs}
                merged[norm] = {
                    "name": name,
                    "requirements": list(reqs),
                    "seen_reqs": seen,
                }

    # Build final dict with element1, element2, … keys
    result: dict = {}
    for idx, (_norm, entry) in enumerate(merged.items(), start=1):
        result[f"element{idx}"] = {
            "name": entry["name"],
            "requirements": entry["requirements"],
        }
    return result


def _parse_kdes_from_text(raw: str) -> dict:
    """
    Best-effort extraction of a KDE nested dict from raw LLM text.

    Strategy:
        1. Try to find a JSON object in the text and parse it directly.
        2. If that fails, use regex to pull out element names and requirements.
        3. If all else fails, return a single element containing the raw text
           so that no data is silently lost.
    """
    # ── Strategy 1: locate first '{…}' block and parse as JSON ────────────
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        candidate = json_match.group(0)
        try:
            parsed = json.loads(candidate)
            # Validate expected shape
            if isinstance(parsed, dict) and parsed:
                # Normalise keys to element1, element2, … if they aren't already
                normalised: dict = {}
                for idx, (k, v) in enumerate(parsed.items(), start=1):
                    key = k if k.startswith("element") else f"element{idx}"
                    if isinstance(v, dict):
                        normalised[key] = {
                            "name":         str(v.get("name", k)),
                            "requirements": list(v.get("requirements", [])),
                        }
                    else:
                        normalised[key] = {"name": str(k), "requirements": [str(v)]}
                return normalised
        except json.JSONDecodeError:
            pass

    # ── Strategy 2: regex heuristic ────────────────────────────────────────
    # Look for patterns like  "name": "...", "requirements": ["...", "..."]
    elements: dict = {}
    name_re = re.compile(r'"name"\s*:\s*"([^"]+)"')
    reqs_re = re.compile(r'"requirements"\s*:\s*\[([^\]]*)\]', re.DOTALL)

    names = name_re.findall(raw)
    reqs_blocks = reqs_re.findall(raw)

    for idx, name in enumerate(names, start=1):
        reqs: list[str] = []
        if idx - 1 < len(reqs_blocks):
            block = reqs_blocks[idx - 1]
            reqs = [
                r.strip().strip('"').strip("'")
                for r in re.split(r',\s*(?=")', block)
                if r.strip().strip('"').strip("'")
            ]
        elements[f"element{idx}"] = {"name": name, "requirements": reqs}

    if elements:
        return elements

    # ── Strategy 3: fallback – store raw text so nothing is lost ───────────
    logger.warning("Could not parse structured JSON from LLM output; storing raw text.")
    return {
        "element1": {
            "name": "UNPARSED_LLM_OUTPUT",
            "requirements": [raw.strip()],
        }
    }


# ══════════════════════════════════════════════════════════════════════════
# Quick smoke-test (run directly: python extractor.py path1.pdf path2.pdf)
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python extractor.py <doc1.pdf> <doc2.pdf>")
        sys.exit(1)

    doc1, doc2 = validate_and_load_documents(sys.argv[1], sys.argv[2])
    pipe = load_gemma_pipeline()

    prompt_builders = {
        "zero_shot":          construct_zero_shot_prompt,
        "few_shot":           construct_few_shot_prompt,
        "chain_of_thought":   construct_chain_of_thought_prompt,
    }

    all_results: list[dict] = []

    for doc in (doc1, doc2):
        for ptype, builder in prompt_builders.items():
            prompt = builder(doc["text"])
            kde_dict, raw = extract_kdes_with_llm(doc, prompt, ptype, pipe,
                                                    prompt_builder=builder)
            all_results.append(
                {
                    "llm_name":   MODEL_NAME,
                    "doc_name":   doc["filename"],
                    "prompt_type": ptype,
                    "prompt":     prompt,
                    "output":     raw,
                }
            )

    out_path = collect_llm_outputs(all_results)
    print(f"\nAll outputs written to: {out_path}")
