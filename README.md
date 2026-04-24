# COMP-5700 – Security Requirements Change Detector

## Team Members

| Name | University Email |
|------|-----------------|
| Joaquin Sarmiento | jzs0271@auburn.edu |

---

## LLM Used (Task-1)

**Model:** `google/gemma-3-1b-it`  
**Source:** [https://huggingface.co/google/gemma-3-1b-it](https://huggingface.co/google/gemma-3-1b-it)  
**Loaded via:** HuggingFace `transformers` library (local inference)

### Hardware Requirements
| Resource | Minimum |
|---|---|
| RAM (CPU mode) | 6 GB |
| VRAM (GPU mode) | 4 GB |
| Disk space | ~3 GB (model weights) |

> **Note:** You must accept the Gemma licence on HuggingFace and set the
> `HF_TOKEN` environment variable before running.

---

## Project Structure

```
project/
├── task1/
│   ├── extractor.py          # 6 functions – PDF loading, prompts, LLM, YAML, TEXT
│   └── test_extractor.py     # 6 test cases (one per function)
├── task2/
│   ├── comparator.py         # 3 functions – YAML diffing
│   └── test_comparator.py    # 3 test cases
├── task3/
│   ├── executor.py           # 4 functions – Kubescape execution, CSV output
│   └── test_executor.py      # 4 test cases
├── output/                   # Generated YAML, TEXT, CSV files
├── PROMPT.md                 # All prompts (zero-shot, few-shot, chain-of-thought)
├── main.py                   # Entry point – accepts a pair of PDFs
├── requirements.txt
└── README.md
```

---

## Quick Start

```bash
# 1 – create and activate virtual environment
python3 -m venv comp5700-venv
source comp5700-venv/bin/activate      # Windows: comp5700-venv\Scripts\activate

# 2 – install dependencies
pip install -r requirements.txt

# 3 – set HuggingFace token (required for gated Gemma model)
export HF_TOKEN=hf_your_token_here

# 4 – run the pipeline on a pair of PDFs
#    (also install kubescape for Task-3: https://github.com/kubescape/kubescape)
./run.sh cis-r1.pdf cis-r2.pdf ./project-yamls        # Linux / macOS / Git Bash
run.bat  cis-r1.pdf cis-r2.pdf project-yamls          # Windows cmd/PowerShell

# Or invoke Python directly:
python main.py cis-r1.pdf cis-r2.pdf --scan-target ./project-yamls

# 5 – run all tests
pytest task1/ task2/ task3/ -v
```

The third argument (Kubescape scan target) is optional. If omitted, Task-3
writes `output/kubescape_controls.txt` but skips the CSV scan.

### Outputs (written to `output/`)
- `*-kdes-{zero_shot,few_shot,chain_of_thought}.yaml` – Task-1 KDE extractions
- `llm_outputs.txt` – raw LLM input/output log
- `name_differences.txt`, `requirement_differences.txt` – Task-2 diffs
- `kubescape_controls.txt` – Task-3 control-ID mapping
- `kubescape_results.csv` – Task-3 Kubescape scan results (if `--scan-target` given)

---

## Input Files Required

The following CIS benchmark PDFs are used as input:
- `cis-r1.pdf`
- `cis-r2.pdf`
- `cis-r3.pdf`
- `cis-r4.pdf`

### Nine Input Combinations

```bash
python main.py cis-r1.pdf cis-r1.pdf   # Input-1
python main.py cis-r1.pdf cis-r2.pdf   # Input-2
python main.py cis-r1.pdf cis-r3.pdf   # Input-3
python main.py cis-r1.pdf cis-r4.pdf   # Input-4
python main.py cis-r2.pdf cis-r2.pdf   # Input-5
python main.py cis-r2.pdf cis-r3.pdf   # Input-6
python main.py cis-r2.pdf cis-r4.pdf   # Input-7
python main.py cis-r3.pdf cis-r3.pdf   # Input-8
python main.py cis-r3.pdf cis-r4.pdf   # Input-9
```