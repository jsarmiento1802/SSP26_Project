"""
task2/test_comparator.py
========================
One test case per function (three total), using pytest.

Run:
    pytest task2/test_comparator.py -v
"""

import sys
from pathlib import Path

import pytest
import yaml

# ── make sure the package root is on sys.path when run directly ────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from task2.comparator import (
    load_yaml_files,
    compare_element_names,
    compare_elements_and_requirements,
)


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def sample_yamls(tmp_path):
    """Write two small YAML files with overlapping and differing content."""
    data1 = {
        "element1": {
            "name": "Password Policy",
            "requirements": [
                "Passwords must be 12+ characters.",
                "Enforce MFA for privileged accounts.",
            ],
        },
        "element2": {
            "name": "Audit Logging",
            "requirements": ["Retain logs for 90 days."],
        },
    }
    data2 = {
        "element1": {
            "name": "Password Policy",
            "requirements": [
                "Passwords must be 12+ characters.",
                "Rotate passwords every 90 days.",   # different req
            ],
        },
        "element2": {
            "name": "Data Encryption",                # totally different KDE
            "requirements": ["Encrypt at rest with AES-256."],
        },
    }
    p1 = tmp_path / "doc_a-kdes-zero_shot.yaml"
    p2 = tmp_path / "doc_b-kdes-zero_shot.yaml"
    p1.write_text(yaml.safe_dump(data1), encoding="utf-8")
    p2.write_text(yaml.safe_dump(data2), encoding="utf-8")
    return str(p1), str(p2)


@pytest.fixture()
def identical_yamls(tmp_path):
    """Two YAML files with the exact same content."""
    data = {
        "element1": {
            "name": "Password Policy",
            "requirements": ["Passwords must be 12+ characters."],
        },
    }
    p1 = tmp_path / "doc_a-kdes-zero_shot.yaml"
    p2 = tmp_path / "doc_b-kdes-zero_shot.yaml"
    p1.write_text(yaml.safe_dump(data), encoding="utf-8")
    p2.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(p1), str(p2)


# ══════════════════════════════════════════════════════════════════════════
# TEST 1 – load_yaml_files
# ══════════════════════════════════════════════════════════════════════════

class TestLoadYamlFiles:
    """Covers the happy-path, missing-file, and wrong-extension branches."""

    def test_loads_two_valid_yamls(self, sample_yamls):
        p1, p2 = sample_yamls
        d1, d2, n1, n2 = load_yaml_files(p1, p2)

        assert isinstance(d1, dict) and isinstance(d2, dict)
        assert "element1" in d1 and "element1" in d2
        assert d1["element1"]["name"] == "Password Policy"
        assert d2["element2"]["name"] == "Data Encryption"
        assert n1.endswith("doc_a-kdes-zero_shot.yaml")
        assert n2.endswith("doc_b-kdes-zero_shot.yaml")

    def test_raises_for_missing_file(self, tmp_path):
        ghost = str(tmp_path / "ghost.yaml")
        with pytest.raises(FileNotFoundError):
            load_yaml_files(ghost, ghost)

    def test_raises_for_wrong_extension(self, tmp_path):
        txt = tmp_path / "not_a_yaml.txt"
        txt.write_text("hello")
        with pytest.raises(ValueError, match="Expected a .yaml"):
            load_yaml_files(str(txt), str(txt))


# ══════════════════════════════════════════════════════════════════════════
# TEST 2 – compare_element_names
# ══════════════════════════════════════════════════════════════════════════

class TestCompareElementNames:
    """Verifies name comparison writes the right content to a TEXT file."""

    def test_detects_name_differences(self, sample_yamls, tmp_path):
        p1, p2 = sample_yamls
        d1, d2, n1, n2 = load_yaml_files(p1, p2)

        out_file = tmp_path / "name_diffs.txt"
        returned = compare_element_names(d1, d2, n1, n2, output_file=str(out_file))

        assert Path(returned).exists()
        content = out_file.read_text(encoding="utf-8")

        # "Audit Logging" only in file 1; "Data Encryption" only in file 2
        assert "Audit Logging" in content
        assert "Data Encryption" in content
        # "Password Policy" is shared and should NOT appear as a difference
        assert "Password Policy" not in content
        # File names should show in the header
        assert n1 in content and n2 in content

    def test_reports_no_differences_when_identical(self, identical_yamls, tmp_path):
        p1, p2 = identical_yamls
        d1, d2, n1, n2 = load_yaml_files(p1, p2)

        out_file = tmp_path / "name_diffs.txt"
        compare_element_names(d1, d2, n1, n2, output_file=str(out_file))

        content = out_file.read_text(encoding="utf-8")
        assert "NO DIFFERENCES IN REGARDS TO ELEMENT NAMES" in content


# ══════════════════════════════════════════════════════════════════════════
# TEST 3 – compare_elements_and_requirements
# ══════════════════════════════════════════════════════════════════════════

class TestCompareElementsAndRequirements:
    """Verifies the tuple-formatted TEXT output for name+requirement diffs."""

    def test_detects_name_and_requirement_differences(self, sample_yamls, tmp_path):
        p1, p2 = sample_yamls
        d1, d2, n1, n2 = load_yaml_files(p1, p2)

        out_file = tmp_path / "req_diffs.txt"
        compare_elements_and_requirements(d1, d2, n1, n2, output_file=str(out_file))

        content = out_file.read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.strip()]

        # Audit Logging is only in file 1 → NA tuple
        audit_lines = [l for l in lines if l.startswith("Audit Logging,")]
        assert len(audit_lines) == 1
        assert audit_lines[0].endswith(",NA")
        assert f"ABSENT-IN-{n2}" in audit_lines[0]
        assert f"PRESENT-IN-{n1}" in audit_lines[0]

        # Data Encryption only in file 2 → NA tuple
        enc_lines = [l for l in lines if l.startswith("Data Encryption,")]
        assert len(enc_lines) == 1
        assert enc_lines[0].endswith(",NA")
        assert f"ABSENT-IN-{n1}" in enc_lines[0]

        # Password Policy is in both files, but has a differing req
        pw_lines = [l for l in lines if l.startswith("Password Policy,")]
        assert len(pw_lines) == 2  # one req each direction
        # File 1 has "Enforce MFA…", file 2 has "Rotate passwords…"
        assert any("Enforce MFA" in l and f"PRESENT-IN-{n1}" in l for l in pw_lines)
        assert any("Rotate passwords" in l and f"PRESENT-IN-{n2}" in l for l in pw_lines)

    def test_reports_no_differences_when_identical(self, identical_yamls, tmp_path):
        p1, p2 = identical_yamls
        d1, d2, n1, n2 = load_yaml_files(p1, p2)

        out_file = tmp_path / "req_diffs.txt"
        compare_elements_and_requirements(d1, d2, n1, n2, output_file=str(out_file))

        content = out_file.read_text(encoding="utf-8")
        assert "NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS" in content
