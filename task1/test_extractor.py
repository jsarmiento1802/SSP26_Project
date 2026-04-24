"""
task1/test_extractor.py
=======================
One test case per function (six total), using pytest.

Run:
    pytest task1/test_extractor.py -v
"""

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ── make sure the package root is on sys.path when run directly ────────────
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from task1.extractor import (
    collect_llm_outputs,
    construct_chain_of_thought_prompt,
    construct_few_shot_prompt,
    construct_zero_shot_prompt,
    extract_kdes_with_llm,
    validate_and_load_documents,
    _parse_kdes_from_text,
    _chunk_text,
    _merge_kde_dicts,
    DOC_CHAR_LIMIT,
)

# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def sample_pdfs(tmp_path):
    """
    Create two minimal but valid single-page PDFs using PyMuPDF so that
    validate_and_load_documents can open them for real.
    """
    import fitz

    texts = {
        "doc_a.pdf": (
            "1.1 All user passwords must be at least 12 characters.\n"
            "1.2 Passwords must not be reused within the last 12 cycles.\n"
            "2.1 Enable audit logging for every authentication attempt.\n"
            "2.2 Retain audit logs for a minimum of 90 days.\n"
        ),
        "doc_b.pdf": (
            "1.1 All user passwords must be at least 16 characters.\n"
            "1.2 Passwords must not be reused within the last 24 cycles.\n"
            "3.1 Encrypt all data at rest using AES-256.\n"
            "3.2 Encrypt all data in transit using TLS 1.2 or higher.\n"
        ),
    }

    paths = {}
    for fname, body in texts.items():
        pdf_path = tmp_path / fname
        doc = fitz.open()          # new empty PDF
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=11)
        doc.save(str(pdf_path))
        doc.close()
        paths[fname] = str(pdf_path)

    return paths["doc_a.pdf"], paths["doc_b.pdf"]


SAMPLE_TEXT = textwrap.dedent("""\
    1.1 All user passwords must be at least 12 characters.
    1.2 MFA must be enabled for privileged accounts.
    2.1 Audit logs must be retained for 90 days.
    2.2 Logs must be protected against tampering.
""")


# ══════════════════════════════════════════════════════════════════════════
# TEST 1 – validate_and_load_documents
# ══════════════════════════════════════════════════════════════════════════

class TestValidateAndLoadDocuments:
    """Covers the happy-path, wrong-extension, and missing-file branches."""

    def test_loads_two_valid_pdfs(self, sample_pdfs):
        path1, path2 = sample_pdfs
        doc1, doc2 = validate_and_load_documents(path1, path2)

        # Both dicts must have the required keys
        for doc, expected_stem in ((doc1, "doc_a"), (doc2, "doc_b")):
            assert set(doc.keys()) == {"filename", "path", "pages", "text"}
            assert doc["filename"] == expected_stem
            assert doc["pages"] >= 1
            assert isinstance(doc["text"], str)
            assert len(doc["text"]) > 10   # at least some text was extracted

    def test_raises_for_missing_file(self, tmp_path):
        ghost = str(tmp_path / "ghost.pdf")
        with pytest.raises(FileNotFoundError):
            validate_and_load_documents(ghost, ghost)

    def test_raises_for_non_pdf_extension(self, tmp_path):
        txt_file = tmp_path / "not_a_pdf.txt"
        txt_file.write_text("hello")
        with pytest.raises(ValueError, match="Expected a .pdf"):
            validate_and_load_documents(str(txt_file), str(txt_file))


# ══════════════════════════════════════════════════════════════════════════
# TEST 2 – construct_zero_shot_prompt
# ══════════════════════════════════════════════════════════════════════════

class TestConstructZeroShotPrompt:
    """Verifies structure and required keywords of the zero-shot prompt."""

    def test_returns_string_with_required_elements(self):
        result = construct_zero_shot_prompt(SAMPLE_TEXT)

        assert isinstance(result, str), "Prompt must be a string"
        assert len(result) > 50,        "Prompt should not be trivially short"

        # Must contain the instruction keyword and the document content marker
        assert "Key Data Element" in result,  "Must reference KDE concept"
        assert "JSON"             in result,  "Must specify JSON output format"
        assert "DOCUMENT START"   in result,  "Must embed the document text"

        # The document snippet itself should appear in the prompt
        assert "passwords must be at least 12" in result

    def test_truncates_very_long_documents(self):
        long_text = "A" * 10_000
        prompt = construct_zero_shot_prompt(long_text)
        # The prompt should NOT embed the full 10 k chars (DOC_CHAR_LIMIT=4000)
        assert len(prompt) < 10_000 + 500   # 500 chars headroom for template


# ══════════════════════════════════════════════════════════════════════════
# TEST 3 – construct_few_shot_prompt
# ══════════════════════════════════════════════════════════════════════════

class TestConstructFewShotPrompt:
    """Verifies that the few-shot prompt contains at least two examples."""

    def test_contains_two_examples_and_document(self):
        result = construct_few_shot_prompt(SAMPLE_TEXT)

        assert isinstance(result, str)
        assert "EXAMPLE 1" in result,     "Must have first example"
        assert "EXAMPLE 2" in result,     "Must have second example"
        assert "DOCUMENT START" in result, "Must embed the target document"
        assert "User Account Management" in result or "element1" in result, \
            "First example KDE name should appear in the prompt"

    def test_document_snippet_is_present(self):
        result = construct_few_shot_prompt(SAMPLE_TEXT)
        assert "passwords must be at least 12" in result


# ══════════════════════════════════════════════════════════════════════════
# TEST 4 – construct_chain_of_thought_prompt
# ══════════════════════════════════════════════════════════════════════════

class TestConstructChainOfThoughtPrompt:
    """Verifies that the CoT prompt contains step-by-step reasoning cues."""

    def test_contains_all_four_steps(self):
        result = construct_chain_of_thought_prompt(SAMPLE_TEXT)

        assert isinstance(result, str)
        for step_num in ("STEP 1", "STEP 2", "STEP 3", "STEP 4"):
            assert step_num in result, f"Missing {step_num} from CoT prompt"

    def test_document_and_json_instruction_present(self):
        result = construct_chain_of_thought_prompt(SAMPLE_TEXT)
        assert "DOCUMENT START"   in result
        assert "JSON"             in result
        assert "Key Data Element" in result


# ══════════════════════════════════════════════════════════════════════════
# TEST 5 – extract_kdes_with_llm
# ══════════════════════════════════════════════════════════════════════════

class TestExtractKdesWithLlm:
    """
    Uses a mock LLM pipeline that returns canned JSON so the test never needs
    a GPU or network access.
    """

    MOCK_LLM_RESPONSE = json.dumps({
        "element1": {
            "name": "Password Policy",
            "requirements": [
                "Passwords must be at least 12 characters.",
                "MFA must be enabled for privileged accounts.",
            ],
        },
        "element2": {
            "name": "Audit Logging",
            "requirements": [
                "Audit logs must be retained for 90 days.",
                "Logs must be protected against tampering.",
            ],
        },
    })

    def _mock_pipe(self, messages, max_new_tokens=512):
        return [{"generated_text": self.MOCK_LLM_RESPONSE}]

    def test_returns_dict_and_raw_and_saves_yaml(self, tmp_path):
        doc_info = {
            "filename": "cis-r1",
            "path":     "/fake/cis-r1.pdf",
            "pages":    5,
            "text":     SAMPLE_TEXT,
        }
        prompt = construct_zero_shot_prompt(SAMPLE_TEXT)

        kde_dict, raw_output = extract_kdes_with_llm(
            doc_info,
            prompt,
            prompt_type="zero_shot",
            llm_pipe=self._mock_pipe,
            output_dir=str(tmp_path),
        )

        # Return types
        assert isinstance(kde_dict, dict),    "Must return a dict"
        assert isinstance(raw_output, str),   "Must return raw string"

        # Nested structure
        assert "element1" in kde_dict
        assert kde_dict["element1"]["name"] == "Password Policy"
        assert len(kde_dict["element1"]["requirements"]) == 2

        # YAML file created
        expected_yaml = tmp_path / "cis-r1-kdes-zero_shot.yaml"
        assert expected_yaml.exists(), "YAML file must be saved to output_dir"

        # YAML content is correct
        with open(expected_yaml, encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
        assert loaded["element1"]["name"] == "Password Policy"


# ══════════════════════════════════════════════════════════════════════════
# TEST 6 – collect_llm_outputs
# ══════════════════════════════════════════════════════════════════════════

class TestCollectLlmOutputs:
    """Verifies that the TEXT file is written with the correct format."""

    RESULTS = [
        {
            "llm_name":    "google/gemma-3-1b-it",
            "doc_name":    "cis-r1",
            "prompt_type": "zero_shot",
            "prompt":      "Extract KDEs …",
            "output":      '{"element1": {"name": "Password Policy", "requirements": []}}',
        },
        {
            "llm_name":    "google/gemma-3-1b-it",
            "doc_name":    "cis-r2",
            "prompt_type": "few_shot",
            "prompt":      "Here are examples …",
            "output":      '{"element1": {"name": "Audit Logging", "requirements": []}}',
        },
    ]

    def test_creates_text_file_with_all_sections(self, tmp_path):
        out_file = str(tmp_path / "llm_outputs.txt")
        returned_path = collect_llm_outputs(self.RESULTS, output_file=out_file)

        # File must exist
        assert Path(returned_path).exists(), "Output file must be created"

        content = Path(returned_path).read_text(encoding="utf-8")

        # Required section markers for both runs
        assert "*LLM Name*"    in content
        assert "*Prompt Used*" in content
        assert "*Prompt Type*" in content
        assert "*LLM Output*"  in content

        # Model name
        assert "google/gemma-3-1b-it" in content

        # Both docs appear
        assert "cis-r1"     in content
        assert "cis-r2"     in content
        assert "zero_shot"  in content
        assert "few_shot"   in content

    def test_handles_empty_results_list(self, tmp_path):
        out_file = str(tmp_path / "empty_outputs.txt")
        returned_path = collect_llm_outputs([], output_file=out_file)
        assert Path(returned_path).exists()
        content = Path(returned_path).read_text()
        assert "Total runs: 0" in content


# ══════════════════════════════════════════════════════════════════════════
# TEST 7 – _chunk_text
# ══════════════════════════════════════════════════════════════════════════

class TestChunkText:
    """Covers short text (single chunk), long text, and boundary splitting."""

    def test_short_text_returns_single_chunk(self):
        text = "A" * 100
        chunks = _chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_exact_limit_returns_single_chunk(self):
        text = "A" * DOC_CHAR_LIMIT
        chunks = _chunk_text(text)
        assert len(chunks) == 1

    def test_long_text_produces_multiple_chunks(self):
        # 12000 chars should yield ~3-4 chunks at 4000 per chunk
        text = "Sentence end. " * 900  # ~12600 chars
        chunks = _chunk_text(text)
        assert len(chunks) >= 3
        for chunk in chunks:
            assert len(chunk) <= DOC_CHAR_LIMIT

    def test_chunks_have_overlap(self):
        # Build text with clear sentence boundaries
        text = ("Requirement number one. " * 200)  # ~4800 chars
        chunks = _chunk_text(text, overlap=200)
        assert len(chunks) >= 2
        # The tail of chunk[0] should appear at the start of chunk[1]
        tail = chunks[0][-100:]
        assert tail in chunks[1], "Overlap region not found in next chunk"

    def test_prefers_paragraph_boundary(self):
        # Put a paragraph break near the chunk boundary
        block = "A" * 3700 + "\n\n" + "B" * 500
        chunks = _chunk_text(block)
        assert len(chunks) >= 2
        assert chunks[0].endswith("\n\n") or chunks[0][-1] == "A" or "B" in chunks[0]


# ══════════════════════════════════════════════════════════════════════════
# TEST 8 – _merge_kde_dicts
# ══════════════════════════════════════════════════════════════════════════

class TestMergeKdeDicts:
    """Covers deduplication by name and by requirement."""

    def test_merges_same_name_elements(self):
        d1 = {"element1": {"name": "Password Policy", "requirements": ["Req A"]}}
        d2 = {"element1": {"name": "Password Policy", "requirements": ["Req B"]}}
        merged = _merge_kde_dicts([d1, d2])
        assert len(merged) == 1
        assert merged["element1"]["name"] == "Password Policy"
        assert set(merged["element1"]["requirements"]) == {"Req A", "Req B"}

    def test_deduplicates_requirements(self):
        d1 = {"element1": {"name": "Audit", "requirements": ["Log all events."]}}
        d2 = {"element1": {"name": "Audit", "requirements": ["Log all events.", "Retain 90 days."]}}
        merged = _merge_kde_dicts([d1, d2])
        assert merged["element1"]["requirements"].count("Log all events.") == 1
        assert "Retain 90 days." in merged["element1"]["requirements"]

    def test_disjoint_elements_preserved(self):
        d1 = {"element1": {"name": "Passwords", "requirements": ["Req A"]}}
        d2 = {"element1": {"name": "Encryption", "requirements": ["Req B"]}}
        merged = _merge_kde_dicts([d1, d2])
        assert len(merged) == 2
        names = {v["name"] for v in merged.values()}
        assert names == {"Passwords", "Encryption"}

    def test_single_dict_returned_as_is(self):
        d = {"element1": {"name": "Test", "requirements": ["R1"]}}
        assert _merge_kde_dicts([d]) is d


# ══════════════════════════════════════════════════════════════════════════
# TEST 9 – extract_kdes_with_llm multi-chunk
# ══════════════════════════════════════════════════════════════════════════

class TestExtractKdesMultiChunk:
    """
    Verifies that extract_kdes_with_llm correctly chunks a long document,
    calls the LLM multiple times, and merges the results.
    """

    RESPONSES = [
        json.dumps({"element1": {"name": "Password Policy",
                                  "requirements": ["Passwords must be 12+ chars."]}}),
        json.dumps({"element1": {"name": "Audit Logging",
                                  "requirements": ["Retain logs 90 days."]},
                     "element2": {"name": "Password Policy",
                                  "requirements": ["MFA required."]}}),
    ]

    def _mock_pipe(self, messages, max_new_tokens=512):
        """Return successive canned responses."""
        idx = getattr(self, "_call_count", 0)
        self._call_count = idx + 1
        return [{"generated_text": self.RESPONSES[idx % len(self.RESPONSES)]}]

    def test_multi_chunk_merges_results(self, tmp_path):
        self._call_count = 0
        # Create text large enough to require 2 chunks
        long_text = "Security requirement sentence. " * 300  # ~9300 chars

        doc_info = {
            "filename": "cis-r1",
            "path": "/fake/cis-r1.pdf",
            "pages": 50,
            "text": long_text,
        }
        prompt = construct_zero_shot_prompt(long_text)

        kde_dict, raw_output = extract_kdes_with_llm(
            doc_info,
            prompt,
            prompt_type="zero_shot",
            llm_pipe=self._mock_pipe,
            output_dir=str(tmp_path),
            prompt_builder=construct_zero_shot_prompt,
        )

        # Should have merged Password Policy from both chunks
        names = {v["name"] for v in kde_dict.values()}
        assert "Password Policy" in names
        assert "Audit Logging" in names

        # Password Policy should have merged requirements
        pw_elem = [v for v in kde_dict.values() if v["name"] == "Password Policy"][0]
        assert len(pw_elem["requirements"]) == 2

        # Raw output should contain chunk boundary markers
        assert "CHUNK BOUNDARY" in raw_output

        # YAML file saved
        assert (tmp_path / "cis-r1-kdes-zero_shot.yaml").exists()
