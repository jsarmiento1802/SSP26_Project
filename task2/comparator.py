"""
task2/comparator.py
===================
Task-2 – Comparator

Three public functions:
  1. load_yaml_files              – load two Task-1 YAML files, return (dict1, dict2, name1, name2)
  2. compare_element_names        – identify differences in KDE names, write TEXT file
  3. compare_elements_and_requirements – identify differences in names AND requirements,
                                         write TEXT file with tuple-formatted output
"""

from __future__ import annotations

import logging
import yaml
from pathlib import Path
from typing import Any

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 1 – load_yaml_files
# ══════════════════════════════════════════════════════════════════════════

def load_yaml_files(path1: str, path2: str) -> tuple[dict, dict, str, str]:
    """
    Load two Task-1 YAML files and return their parsed content along with
    the original filenames.

    Args:
        path1: Path to the first YAML file produced by Task-1.
        path2: Path to the second YAML file produced by Task-1.

    Returns:
        (kde_dict_1, kde_dict_2, filename_1, filename_2) where each kde_dict
        is a ``{element_key: {name, requirements}}`` mapping and each filename
        is the basename of the respective file.

    Raises:
        FileNotFoundError – if either path does not exist.
        ValueError        – if a file is not a valid YAML or has wrong shape.
    """
    def _load_one(raw_path: str) -> tuple[dict, str]:
        resolved = Path(raw_path).resolve()

        if not resolved.exists():
            raise FileNotFoundError(f"YAML file not found: {resolved}")

        if resolved.suffix.lower() not in (".yaml", ".yml"):
            raise ValueError(
                f"Expected a .yaml/.yml file, got '{resolved.suffix}': {resolved}"
            )

        try:
            with open(resolved, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ValueError(f"Cannot parse YAML '{resolved.name}': {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(
                f"YAML '{resolved.name}' does not contain a top-level mapping."
            )

        logger.info("Loaded '%s' — %d elements", resolved.name, len(data))
        return data, resolved.name

    d1, n1 = _load_one(path1)
    d2, n2 = _load_one(path2)
    return d1, d2, n1, n2


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 2 – compare_element_names
# ══════════════════════════════════════════════════════════════════════════

def compare_element_names(
    kde_dict_1: dict,
    kde_dict_2: dict,
    filename_1: str,
    filename_2: str,
    output_file: str = "output/name_differences.txt",
) -> str:
    """
    Identify KDE names that differ between two YAML files and write the
    result to a TEXT file.

    A name is considered "different" if it is present in one file but not
    the other (case-insensitive, whitespace-trimmed comparison).

    Output TEXT file format:
        <kde name>   (one per line, names that are different)
    If both files have identical name sets, writes:
        NO DIFFERENCES IN REGARDS TO ELEMENT NAMES

    Args:
        kde_dict_1: First Task-1 KDE dict.
        kde_dict_2: Second Task-1 KDE dict.
        filename_1: Basename of the first YAML file (for the report header).
        filename_2: Basename of the second YAML file (for the report header).
        output_file: Path of the TEXT file to write.

    Returns:
        Absolute path of the written TEXT file as a string.
    """
    names_1 = _extract_names(kde_dict_1)
    names_2 = _extract_names(kde_dict_2)

    # Differences = symmetric difference (case-insensitive)
    norm_to_orig_1 = {n.lower().strip(): n for n in names_1}
    norm_to_orig_2 = {n.lower().strip(): n for n in names_2}
    norm_set_1 = set(norm_to_orig_1.keys())
    norm_set_2 = set(norm_to_orig_2.keys())

    only_in_1 = sorted(norm_set_1 - norm_set_2)
    only_in_2 = sorted(norm_set_2 - norm_set_1)

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if not only_in_1 and not only_in_2:
        lines.append("NO DIFFERENCES IN REGARDS TO ELEMENT NAMES")
    else:
        lines.append(f"Comparing: {filename_1}  vs  {filename_2}")
        lines.append("=" * 60)
        if only_in_1:
            lines.append(f"\nKDE names present in {filename_1} but ABSENT in {filename_2}:")
            for norm in only_in_1:
                lines.append(f"  - {norm_to_orig_1[norm]}")
        if only_in_2:
            lines.append(f"\nKDE names present in {filename_2} but ABSENT in {filename_1}:")
            for norm in only_in_2:
                lines.append(f"  - {norm_to_orig_2[norm]}")

    text = "\n".join(lines) + "\n"
    with open(output_file, "w", encoding="utf-8") as fh:
        fh.write(text)

    logger.info("Name comparison written → %s", output_file)
    return str(Path(output_file).resolve())


# ══════════════════════════════════════════════════════════════════════════
# FUNCTION 3 – compare_elements_and_requirements
# ══════════════════════════════════════════════════════════════════════════

def compare_elements_and_requirements(
    kde_dict_1: dict,
    kde_dict_2: dict,
    filename_1: str,
    filename_2: str,
    output_file: str = "output/requirement_differences.txt",
) -> str:
    """
    Identify differences between two YAML files with respect to (i) names of
    KDEs and (ii) requirements within each KDE.  Write the result to a TEXT
    file as comma-separated tuples.

    Output line format:
        NAME,ABSENT-IN-<filename>,PRESENT-IN-<filename>,NA
            → the KDE is present in one file but absent in the other.

        NAME,ABSENT-IN-<filename>,PRESENT-IN-<filename>,REQ
            → the KDE exists in both files, but the requirement "REQ" is
              present in one and absent in the other.

    If both files have identical names AND requirements, writes:
        NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS

    Args:
        kde_dict_1: First Task-1 KDE dict.
        kde_dict_2: Second Task-1 KDE dict.
        filename_1: Basename of the first YAML file.
        filename_2: Basename of the second YAML file.
        output_file: Path of the TEXT file to write.

    Returns:
        Absolute path of the written TEXT file as a string.
    """
    # Build normalized-name -> (original_name, set(normalized_reqs), dict(norm_req -> orig_req))
    map_1 = _build_name_to_reqs_map(kde_dict_1)
    map_2 = _build_name_to_reqs_map(kde_dict_2)

    norm_names_1 = set(map_1.keys())
    norm_names_2 = set(map_2.keys())

    tuples: list[str] = []

    # Case A – KDE name present in one file but not the other
    for norm in sorted(norm_names_1 - norm_names_2):
        name = map_1[norm]["name"]
        tuples.append(f"{name},ABSENT-IN-{filename_2},PRESENT-IN-{filename_1},NA")

    for norm in sorted(norm_names_2 - norm_names_1):
        name = map_2[norm]["name"]
        tuples.append(f"{name},ABSENT-IN-{filename_1},PRESENT-IN-{filename_2},NA")

    # Case B – same KDE name in both files, compare requirements
    for norm in sorted(norm_names_1 & norm_names_2):
        name = map_1[norm]["name"]  # use the name from file 1
        reqs_1 = map_1[norm]["norm_reqs"]
        reqs_2 = map_2[norm]["norm_reqs"]

        # Requirements only in file 1 (absent from file 2)
        for norm_req in sorted(reqs_1 - reqs_2):
            orig_req = map_1[norm]["req_text"][norm_req]
            tuples.append(
                f"{name},ABSENT-IN-{filename_2},PRESENT-IN-{filename_1},{orig_req}"
            )

        # Requirements only in file 2 (absent from file 1)
        for norm_req in sorted(reqs_2 - reqs_1):
            orig_req = map_2[norm]["req_text"][norm_req]
            tuples.append(
                f"{name},ABSENT-IN-{filename_1},PRESENT-IN-{filename_2},{orig_req}"
            )

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as fh:
        if not tuples:
            fh.write("NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS\n")
        else:
            fh.write("\n".join(tuples) + "\n")

    logger.info("Requirement comparison written → %s", output_file)
    return str(Path(output_file).resolve())


# ══════════════════════════════════════════════════════════════════════════
# HELPERS  (not part of the public API)
# ══════════════════════════════════════════════════════════════════════════

def _extract_names(kde_dict: dict) -> list[str]:
    """Return the ``name`` field of every element in a Task-1 KDE dict."""
    names: list[str] = []
    for _key, elem in kde_dict.items():
        if isinstance(elem, dict) and "name" in elem:
            names.append(str(elem["name"]))
    return names


def _build_name_to_reqs_map(kde_dict: dict) -> dict:
    """
    Build a mapping from normalized KDE name → info dict.

    Each info dict contains:
        - ``name``      : original (first-seen) KDE name
        - ``norm_reqs`` : set of normalized (lowered/stripped) requirement strings
        - ``req_text``  : dict(norm_req -> first-seen original requirement text)

    If two elements share the same normalized name, their requirements are
    merged (useful when a Task-1 YAML contains duplicate-named elements).
    """
    result: dict[str, dict] = {}
    for _key, elem in kde_dict.items():
        if not isinstance(elem, dict):
            continue
        name = str(elem.get("name", "")).strip()
        if not name:
            continue
        norm_name = name.lower()
        reqs = elem.get("requirements", []) or []
        if not isinstance(reqs, list):
            reqs = [str(reqs)]

        if norm_name not in result:
            result[norm_name] = {
                "name": name,
                "norm_reqs": set(),
                "req_text": {},
            }

        for req in reqs:
            req_str = str(req).strip()
            if not req_str:
                continue
            norm_req = req_str.lower()
            result[norm_name]["norm_reqs"].add(norm_req)
            # Keep the first-seen original wording
            result[norm_name]["req_text"].setdefault(norm_req, req_str)

    return result


# ══════════════════════════════════════════════════════════════════════════
# Quick smoke-test (run directly: python comparator.py yaml1 yaml2)
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python comparator.py <yaml1> <yaml2>")
        sys.exit(1)

    d1, d2, n1, n2 = load_yaml_files(sys.argv[1], sys.argv[2])

    name_report = compare_element_names(d1, d2, n1, n2)
    req_report = compare_elements_and_requirements(d1, d2, n1, n2)

    print(f"\nName differences  -> {name_report}")
    print(f"Requirement diffs -> {req_report}")
