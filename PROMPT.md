# PROMPT.md — Key Data Element Extraction Prompts

This file documents every prompt used in **Task-1** of the project.  
All prompts target **Gemma-3-1b-it** (`google/gemma-3-1b-it`).  
The `{document_text}` placeholder is replaced at runtime with the first
`4 000` characters of the PDF's extracted text (truncated to fit the model's
context window).

---

## zero-shot

> No examples are provided. The model relies entirely on its pre-trained
> knowledge of security concepts and structured JSON output.

```
You are an expert security analyst.

Your task is to read the security requirements document below and
identify all Key Data Elements (KDEs). A Key Data Element is a
distinct security concept, asset, or control category mentioned in
the document (e.g., 'User Authentication', 'Access Control',
'Audit Logging').

For each KDE, list every specific requirement from the document that
belongs to that element.

Output ONLY valid JSON — no prose, no markdown fences — with this
exact structure:
{
  "element1": {
    "name": "<kde name>",
    "requirements": ["<req 1>", "<req 2>"]
  },
  "element2": {
    "name": "<kde name>",
    "requirements": ["<req 1>"]
  }
}

--- DOCUMENT START ---
{document_text}
--- DOCUMENT END ---

JSON:
```

---

## few-shot

> Two worked examples are provided so the model learns the exact
> input–output format before processing the real document.

```
You are an expert security analyst.

Your task is to read a security requirements document and identify
all Key Data Elements (KDEs), each paired with the requirements that
belong to it.

Study the two examples below, then process the real document.

=== EXAMPLE 1 ===
Document snippet:
  1.1 Ensure unique usernames are assigned to every user account.
  1.2 Disable or remove accounts that have been inactive for 90 days.
  1.3 Require multi-factor authentication for all privileged accounts.

Expected JSON output:
{"element1": {"name": "User Account Management", "requirements": [
  "Ensure unique usernames are assigned to every user account.",
  "Disable or remove accounts that have been inactive for 90 days.",
  "Require multi-factor authentication for all privileged accounts."]}}

=== EXAMPLE 2 ===
Document snippet:
  3.1 Enable audit logging for all authentication events.
  3.2 Retain audit logs for a minimum of 90 days.
  4.1 Encrypt all data at rest using AES-256 or stronger.
  4.2 Encrypt all data in transit using TLS 1.2 or higher.

Expected JSON output:
{"element1": {"name": "Audit Logging", "requirements": [
  "Enable audit logging for all authentication events.",
  "Retain audit logs for a minimum of 90 days."]},
 "element2": {"name": "Data Encryption", "requirements": [
  "Encrypt all data at rest using AES-256 or stronger.",
  "Encrypt all data in transit using TLS 1.2 or higher."]}}

=== NOW PROCESS THE REAL DOCUMENT ===
Output ONLY valid JSON — no prose, no markdown fences.

--- DOCUMENT START ---
{document_text}
--- DOCUMENT END ---

JSON:
```

---

## chain-of-thought

> The model is walked through four explicit reasoning steps before
> producing its final JSON answer, encouraging deeper analysis and
> reducing hallucination.

```
You are an expert security analyst.

Follow these reasoning steps carefully before writing your answer:

STEP 1 – Scan the document and list every distinct security topic,
control category, or asset type you encounter (e.g., 'passwords',
'network access', 'logging'). These are candidate Key Data Elements (KDEs).

STEP 2 – For each candidate KDE from Step 1, collect every sentence
or numbered clause in the document that belongs to that KDE.

STEP 3 – Give each KDE a clear, concise name that captures its
security theme (e.g., 'Password Policy', 'Network Access Control').

STEP 4 – Format your final answer as ONLY valid JSON — no prose,
no markdown fences — using this structure:
{
  "element1": {
    "name": "<kde name from Step 3>",
    "requirements": ["<clause from Step 2>", ...]
  },
  "element2": { ... }
}

--- DOCUMENT START ---
{document_text}
--- DOCUMENT END ---

Work through Steps 1-3 briefly, then output the JSON in Step 4:
```

---

### Notes

| Attribute | Value |
|---|---|
| Model | `google/gemma-3-1b-it` |
| Max new tokens | 1 024 |
| Document char limit fed to model | 4 000 per chunk |
| Output format | JSON (parsed → YAML) |
| Prompt builders | `construct_zero_shot_prompt`, `construct_few_shot_prompt`, `construct_chain_of_thought_prompt` in `task1/extractor.py` |

### Document Chunking

Documents longer than 4 000 characters are automatically split into
overlapping chunks (200-character overlap) so that the full document is
processed rather than truncated. Each chunk is sent to the LLM
independently using the same prompt template. The resulting KDE
dictionaries are merged by normalised element name and deduplicated by
requirement text before being saved as a single YAML file.

When `prompt_builder` is passed to `extract_kdes_with_llm`, chunking
is enabled automatically for any document exceeding the char limit.
Without `prompt_builder`, the function falls back to the original
single-prompt behaviour for backward compatibility.
