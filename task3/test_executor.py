"""
task3/test_executor.py
======================
One test case per function (four total), using pytest.

Run:
    pytest task3/test_executor.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from task3.executor import (
    load_task2_outputs,
    map_differences_to_controls,
    run_kubescape,
    generate_csv,
)


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def task2_files_with_diffs(tmp_path):
    name_file = tmp_path / "name_diffs.txt"
    req_file = tmp_path / "req_diffs.txt"
    name_file.write_text(
        "Comparing: a.yaml  vs  b.yaml\n"
        "============================================================\n"
        "KDE names present in a.yaml but ABSENT in b.yaml:\n"
        "  - Logging\n",
        encoding="utf-8",
    )
    req_file.write_text(
        "Audit Logging,ABSENT-IN-b.yaml,PRESENT-IN-a.yaml,"
        "Enable RBAC on the cluster.\n"
        "Password Policy,ABSENT-IN-a.yaml,PRESENT-IN-b.yaml,"
        "Encrypt secrets at rest with etcd encryption.\n",
        encoding="utf-8",
    )
    return str(name_file), str(req_file)


@pytest.fixture()
def task2_files_no_diffs(tmp_path):
    name_file = tmp_path / "name_diffs.txt"
    req_file = tmp_path / "req_diffs.txt"
    name_file.write_text("NO DIFFERENCES IN REGARDS TO ELEMENT NAMES\n", encoding="utf-8")
    req_file.write_text("NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS\n", encoding="utf-8")
    return str(name_file), str(req_file)


# ══════════════════════════════════════════════════════════════════════════
# TEST 1 – load_task2_outputs
# ══════════════════════════════════════════════════════════════════════════

class TestLoadTask2Outputs:
    def test_loads_both_files(self, task2_files_with_diffs):
        n_path, r_path = task2_files_with_diffs
        name_text, req_text = load_task2_outputs(n_path, r_path)

        assert "Logging" in name_text
        assert "Encrypt secrets" in req_text

    def test_raises_for_missing_file(self, tmp_path):
        ghost = str(tmp_path / "ghost.txt")
        with pytest.raises(FileNotFoundError):
            load_task2_outputs(ghost, ghost)


# ══════════════════════════════════════════════════════════════════════════
# TEST 2 – map_differences_to_controls
# ══════════════════════════════════════════════════════════════════════════

class TestMapDifferencesToControls:
    def test_maps_keywords_to_controls(self, task2_files_with_diffs, tmp_path):
        n_path, r_path = task2_files_with_diffs
        name_text, req_text = load_task2_outputs(n_path, r_path)

        out = tmp_path / "controls.txt"
        map_differences_to_controls(name_text, req_text, output_file=str(out))

        content = out.read_text(encoding="utf-8")
        # "Logging" + "rbac" + "encryption"/"etcd"/"secret" should all map
        assert "C-0067" in content  # audit/logging
        assert "C-0088" in content  # rbac
        assert "C-0066" in content  # encryption / etcd
        assert "NO DIFFERENCES FOUND" not in content

    def test_reports_no_differences(self, task2_files_no_diffs, tmp_path):
        n_path, r_path = task2_files_no_diffs
        name_text, req_text = load_task2_outputs(n_path, r_path)

        out = tmp_path / "controls.txt"
        map_differences_to_controls(name_text, req_text, output_file=str(out))

        assert out.read_text(encoding="utf-8").strip() == "NO DIFFERENCES FOUND"


# ══════════════════════════════════════════════════════════════════════════
# TEST 3 – run_kubescape (subprocess mocked)
# ══════════════════════════════════════════════════════════════════════════

class TestRunKubescape:
    def test_parses_kubescape_json(self, tmp_path):
        controls_file = tmp_path / "controls.txt"
        controls_file.write_text("C-0067\nC-0088\n", encoding="utf-8")

        target = tmp_path / "yamls"
        target.mkdir()
        (target / "dummy.yaml").write_text("kind: Pod\n", encoding="utf-8")

        fake_json = {
            "resources": [
                {"resourceID": "r1",
                 "source": {"relativePath": "yamls/dummy.yaml"}},
            ],
            "results": [
                {"resourceID": "r1",
                 "controls": [
                     {"controlID": "C-0067",
                      "status": {"status": "failed"}},
                 ]},
            ],
            "summaryDetails": {
                "controls": {
                    "C-0067": {"name": "Audit logs enabled",
                               "scoreFactor": 7,
                               "complianceScore": 0.0},
                },
            },
        }

        def fake_run(cmd, check=False, capture_output=True, text=True):
            # Kubescape writes output via --output <path>
            out_idx = cmd.index("--output") + 1
            Path(cmd[out_idx]).write_text(json.dumps(fake_json), encoding="utf-8")

            class R: returncode = 0; stdout = ""; stderr = ""
            return R()

        with patch("task3.executor.subprocess.run", side_effect=fake_run):
            df = run_kubescape(str(controls_file), str(target))

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]["Control name"] == "Audit logs enabled"
        assert df.iloc[0]["Severity"] == "High"
        assert df.iloc[0]["Failed resources"] == 1
        assert df.iloc[0]["FilePath"] == "yamls/dummy.yaml"


# ══════════════════════════════════════════════════════════════════════════
# TEST 4 – generate_csv
# ══════════════════════════════════════════════════════════════════════════

class TestGenerateCsv:
    def test_writes_required_headers(self, tmp_path):
        df = pd.DataFrame([
            {"FilePath": "a.yaml", "Severity": "High",
             "Control name": "RBAC enabled", "Failed resources": 1,
             "All Resources": 3, "Compliance score": 66.7},
            {"FilePath": "b.yaml", "Severity": "Medium",
             "Control name": "Audit logs enabled", "Failed resources": 0,
             "All Resources": 3, "Compliance score": 100.0},
        ])

        out = tmp_path / "results.csv"
        generate_csv(df, output_file=str(out))

        assert out.exists()
        header = out.read_text(encoding="utf-8").splitlines()[0]
        for col in ["FilePath", "Severity", "Control name",
                    "Failed resources", "All Resources", "Compliance score"]:
            assert col in header

        reloaded = pd.read_csv(out)
        assert len(reloaded) == 2
        assert reloaded.iloc[0]["Control name"] == "RBAC enabled"
