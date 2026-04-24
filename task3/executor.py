"""
task3/executor.py
=================
Task-3 – Executor

Four public functions:
  1. load_task2_outputs         – read the two TEXT files produced by Task-2
  2. map_differences_to_controls – map textual differences to Kubescape control IDs,
                                    write a TEXT file ("NO DIFFERENCES FOUND" or list)
  3. run_kubescape              – run the Kubescape CLI on a target, return DataFrame
  4. generate_csv               – write the required 5-column CSV from the DataFrame
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Keyword → Kubescape control mapping ───────────────────────────────────
# Heuristic mapping of CIS-benchmark keywords to Kubescape control IDs.
# (Control IDs come from https://hub.armosec.io/docs/controls)
KEYWORD_TO_CONTROLS: dict[str, list[str]] = {
    "rbac":                 ["C-0088", "C-0035", "C-0015"],
    "role-based":           ["C-0088", "C-0035"],
    "cluster-admin":        ["C-0035"],
    "service account":      ["C-0034", "C-0053", "C-0020"],
    "logging":              ["C-0067"],
    "audit":                ["C-0067"],
    "encryption":           ["C-0066"],
    "etcd":                 ["C-0066"],
    "secret":               ["C-0012", "C-0015", "C-0066"],
    "credential":           ["C-0012"],
    "network policy":       ["C-0030"],
    "ingress":              ["C-0030"],
    "egress":               ["C-0030"],
    "hostnetwork":          ["C-0041"],
    "host network":         ["C-0041"],
    "hostpath":             ["C-0045", "C-0048"],
    "host path":            ["C-0045", "C-0048"],
    "hostpid":              ["C-0038"],
    "hostipc":              ["C-0038"],
    "privileged":           ["C-0057"],
    "privilege escalation": ["C-0016"],
    "non-root":             ["C-0013"],
    "run as root":          ["C-0013"],
    "capability":           ["C-0046", "C-0055"],
    "capabilities":         ["C-0046", "C-0055"],
    "readonly":             ["C-0017"],
    "read-only":            ["C-0017"],
    "image":                ["C-0001", "C-0075", "C-0078"],
    "registry":             ["C-0001", "C-0078"],
    "pull policy":          ["C-0075"],
    "latest tag":           ["C-0075"],
    "admission controller": ["C-0036", "C-0039"],
    "anonymous":            ["C-0069"],
    "kubelet":              ["C-0069", "C-0070"],
    "tls":                  ["C-0070"],
    "resource limit":       ["C-0009", "C-0050", "C-0004"],
    "memory limit":         ["C-0004"],
    "cpu limit":            ["C-0050"],
    "liveness":             ["C-0056"],
    "readiness":            ["C-0018"],
    "namespace":            ["C-0061"],
    "default namespace":    ["C-0061"],
    "psp":                  ["C-0068"],
    "pod security":         ["C-0068"],
    "api server":           ["C-0005"],
    "insecure port":        ["C-0005"],
    "docker socket":        ["C-0074"],
    "worker":               ["C-0069", "C-0070"],
    "controller manager":   ["C-0005"],
    "scheduler":            ["C-0005"],
}


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 1 – load_task2_outputs
# ══════════════════════════════════════════════════════════════════════════

def load_task2_outputs(
    name_diffs_path: str,
    requirement_diffs_path: str,
) -> tuple[str, str]:
    """
    Read the two TEXT files produced by Task-2.

    Args:
        name_diffs_path: Path to the Task-2 name-differences TEXT file.
        requirement_diffs_path: Path to the Task-2 requirement-differences TEXT file.

    Returns:
        (name_diffs_text, requirement_diffs_text)

    Raises:
        FileNotFoundError – if either path does not exist.
    """
    paths = [Path(name_diffs_path), Path(requirement_diffs_path)]
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Task-2 output not found: {p}")

    name_text = paths[0].read_text(encoding="utf-8")
    req_text = paths[1].read_text(encoding="utf-8")
    logger.info("Loaded Task-2 outputs: %s, %s", paths[0].name, paths[1].name)
    return name_text, req_text


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 2 – map_differences_to_controls
# ══════════════════════════════════════════════════════════════════════════

def map_differences_to_controls(
    name_diffs_text: str,
    requirement_diffs_text: str,
    output_file: str = "output/kubescape_controls.txt",
) -> str:
    """
    Determine whether the two TEXT files show any differences and, if so,
    map those differences to Kubescape control IDs using a keyword heuristic.

    Output TEXT file:
        * "NO DIFFERENCES FOUND"        – if both inputs report no differences, OR
        * one Kubescape control ID per line (e.g. ``C-0088``) – otherwise.

    Args:
        name_diffs_text: Content of the Task-2 name-diff file.
        requirement_diffs_text: Content of the Task-2 requirement-diff file.
        output_file: Path of the TEXT file to write.

    Returns:
        Absolute path of the written TEXT file.
    """
    has_name_diff = "NO DIFFERENCES IN REGARDS TO ELEMENT NAMES" not in name_diffs_text
    has_req_diff = "NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS" not in requirement_diffs_text

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    if not has_name_diff and not has_req_diff:
        Path(output_file).write_text("NO DIFFERENCES FOUND\n", encoding="utf-8")
        logger.info("No differences — wrote NO DIFFERENCES FOUND → %s", output_file)
        return str(Path(output_file).resolve())

    combined = f"{name_diffs_text}\n{requirement_diffs_text}".lower()

    matched: set[str] = set()
    for keyword, controls in KEYWORD_TO_CONTROLS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", combined):
            matched.update(controls)

    if not matched:
        # Differences exist but none mapped — fall back to a minimal default set
        matched.update(["C-0088", "C-0067", "C-0030"])

    ordered = sorted(matched)
    Path(output_file).write_text("\n".join(ordered) + "\n", encoding="utf-8")
    logger.info("Mapped %d Kubescape control(s) → %s", len(ordered), output_file)
    return str(Path(output_file).resolve())


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 3 – run_kubescape
# ══════════════════════════════════════════════════════════════════════════

def run_kubescape(
    controls_file: str,
    target_path: str,
    kubescape_bin: str = "kubescape",
) -> pd.DataFrame:
    """
    Execute the Kubescape CLI against ``target_path`` (a directory or zip of
    Kubernetes YAML files) using the controls listed in ``controls_file``.

    * If the file contains "NO DIFFERENCES FOUND", Kubescape is run with the
      full NSA framework (all available controls).
    * Otherwise, Kubescape is run only against the listed control IDs.

    Args:
        controls_file: Path to the TEXT file from ``map_differences_to_controls``.
        target_path: Path to the target (directory, zip, or glob) to scan.
        kubescape_bin: Name/path of the Kubescape executable.

    Returns:
        A pandas DataFrame with one row per (control, resource) pairing.
        Columns: ``FilePath``, ``Severity``, ``Control name``,
        ``Failed resources``, ``All Resources``, ``Compliance score``.

    Raises:
        FileNotFoundError – if ``controls_file`` or ``target_path`` does not exist.
        RuntimeError      – if Kubescape fails to run or returns no parsable JSON.
    """
    c_path = Path(controls_file)
    t_path = Path(target_path)
    if not c_path.exists():
        raise FileNotFoundError(f"Controls file not found: {c_path}")
    if not t_path.exists():
        raise FileNotFoundError(f"Target not found: {t_path}")

    content = c_path.read_text(encoding="utf-8").strip()
    run_all = content == "NO DIFFERENCES FOUND" or not content

    with tempfile.TemporaryDirectory() as td:
        out_json = Path(td) / "kubescape_result.json"

        if run_all:
            cmd = [
                kubescape_bin, "scan", "framework", "nsa",
                str(t_path), "--format", "json", "--output", str(out_json),
            ]
        else:
            control_ids = ",".join(
                line.strip() for line in content.splitlines() if line.strip()
            )
            cmd = [
                kubescape_bin, "scan", "control", control_ids,
                str(t_path), "--format", "json", "--output", str(out_json),
            ]

        logger.info("Running: %s", " ".join(cmd))
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Kubescape executable '{kubescape_bin}' not found on PATH."
            ) from exc

        def _diag() -> str:
            return (
                f"\n  exit code: {proc.returncode}"
                f"\n  stdout (last 2000 chars): {(proc.stdout or '')[-2000:]}"
                f"\n  stderr (last 2000 chars): {(proc.stderr or '')[-2000:]}"
            )

        # Some Kubescape versions write JSON to stdout instead of --output
        json_text = ""
        if out_json.exists():
            json_text = out_json.read_text(encoding="utf-8").strip()
        if not json_text and proc.stdout and proc.stdout.lstrip().startswith("{"):
            json_text = proc.stdout

        if not json_text:
            raise RuntimeError(
                "Kubescape did not produce JSON output." + _diag()
            )

        try:
            raw = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Cannot parse Kubescape JSON: {exc}" + _diag()
            ) from exc

    return _kubescape_json_to_dataframe(raw)


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 4 – generate_csv
# ══════════════════════════════════════════════════════════════════════════

def generate_csv(
    df: pd.DataFrame,
    output_file: str = "output/kubescape_results.csv",
) -> str:
    """
    Write the scan DataFrame to a CSV with the required five headers:
    ``FilePath``, ``Severity``, ``Control name``, ``Failed resources``,
    ``All Resources``, ``Compliance score``.

    Args:
        df: DataFrame returned by ``run_kubescape``.
        output_file: Path of the CSV file to write.

    Returns:
        Absolute path of the written CSV file.
    """
    required = [
        "FilePath", "Severity", "Control name",
        "Failed resources", "All Resources", "Compliance score",
    ]
    # Ensure every required column exists (fill missing with empty)
    for col in required:
        if col not in df.columns:
            df[col] = ""

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    df[required].to_csv(output_file, index=False, encoding="utf-8")
    logger.info("CSV written (%d rows) → %s", len(df), output_file)
    return str(Path(output_file).resolve())


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _kubescape_json_to_dataframe(raw: dict) -> pd.DataFrame:
    """
    Flatten a Kubescape JSON report into a pandas DataFrame.

    Kubescape's JSON schema varies slightly between versions; this helper
    tolerates both the newer "resources"/"results"/"summaryDetails" layout
    and the older "results" array layout.
    """
    rows: list[dict] = []

    # Build resource-id -> file path lookup (newer schema)
    resource_paths: dict[str, str] = {}
    for res in raw.get("resources", []) or []:
        rid = res.get("resourceID") or res.get("resourceId") or ""
        src = res.get("source", {}) or {}
        path = src.get("relativePath") or src.get("path") or ""
        if rid:
            resource_paths[rid] = path

    # Control metadata (severity, name, compliance score) from summaryDetails
    controls_meta: dict[str, dict] = {}
    summary = raw.get("summaryDetails", {}) or {}
    for cid, cdata in (summary.get("controls", {}) or {}).items():
        controls_meta[cid] = {
            "name": cdata.get("name", ""),
            "severity": _severity_label(cdata.get("scoreFactor")),
            "compliance": cdata.get("complianceScore", cdata.get("score", "")),
        }

    # Iterate per-resource results (newer schema)
    for result in raw.get("results", []) or []:
        rid = result.get("resourceID") or result.get("resourceId") or ""
        file_path = resource_paths.get(rid, rid)

        for ctrl in result.get("controls", []) or []:
            cid = ctrl.get("controlID") or ctrl.get("id") or ""
            meta = controls_meta.get(cid, {})
            failed = 1 if (ctrl.get("status", {}) or {}).get("status") == "failed" else 0
            rows.append({
                "FilePath": file_path,
                "Severity": meta.get("severity", ctrl.get("severity", "")),
                "Control name": meta.get("name", ctrl.get("name", cid)),
                "Failed resources": failed,
                "All Resources": 1,
                "Compliance score": meta.get("compliance", ""),
            })

    # Fallback: aggregate per-control if no per-resource results were produced
    if not rows and controls_meta:
        for cid, meta in controls_meta.items():
            cdata = summary.get("controls", {}).get(cid, {})
            rows.append({
                "FilePath": "",
                "Severity": meta.get("severity", ""),
                "Control name": meta.get("name", cid),
                "Failed resources": cdata.get("ResourceCounters", {}).get("failedResources", 0),
                "All Resources": (
                    cdata.get("ResourceCounters", {}).get("failedResources", 0)
                    + cdata.get("ResourceCounters", {}).get("passedResources", 0)
                    + cdata.get("ResourceCounters", {}).get("skippedResources", 0)
                ),
                "Compliance score": meta.get("compliance", ""),
            })

    return pd.DataFrame(rows)


def _severity_label(score_factor) -> str:
    """Map Kubescape's numeric scoreFactor to a severity label."""
    try:
        s = float(score_factor)
    except (TypeError, ValueError):
        return ""
    if s >= 9:
        return "Critical"
    if s >= 7:
        return "High"
    if s >= 4:
        return "Medium"
    if s > 0:
        return "Low"
    return ""


# ══════════════════════════════════════════════════════════════════════════
# Quick smoke-test: python -m task3.executor <name_txt> <req_txt> <target>
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        print("Usage: python -m task3.executor <name_diffs.txt> <req_diffs.txt> <target>")
        sys.exit(1)

    n_txt, r_txt, target = sys.argv[1], sys.argv[2], sys.argv[3]
    n, r = load_task2_outputs(n_txt, r_txt)
    ctrls = map_differences_to_controls(n, r)
    df = run_kubescape(ctrls, target)
    csv = generate_csv(df)

    print(f"\nControls file -> {ctrls}")
    print(f"CSV output    -> {csv}")
