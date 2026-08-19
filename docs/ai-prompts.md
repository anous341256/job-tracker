# AI prompt package

The production prompts live in `ai_assistant/prompts.py`. Both Ollama and OpenAI use the same system prompt, task instructions, input boundaries, and Pydantic output schemas.

## Version 2.0

The package contains three layers:

1. `SYSTEM_PROMPT` defines authority, prompt-injection resistance, evidence standards, and schema-only output.
2. `JD_EXTRACTION_INSTRUCTIONS` normalizes multilingual job descriptions without guessing missing facts.
3. `MATCHING_INSTRUCTIONS` requires resume-grounded evidence, a 100-point rubric, score caps, and internally consistent recommendations.

Every `AITask` stores `prompt_version`. Change `PROMPT_VERSION` whenever prompt behavior changes materially so results from different versions remain comparable.

## JD extraction behavior

- Treats the pasted job description as untrusted data, never as instructions.
- Separates required and preferred qualifications.
- Normalizes category, work mode, employment type, salary, currency, period, and deadline.
- Returns per-field confidence and an explicit list of unknown fields.
- Preserves the source language for descriptive text.
- Never follows links, creates companies, or writes data before user confirmation.

## Job matching behavior

- Candidate claims must be supported by the resume or profile.
- Missing resume evidence is reported as “not evidenced,” not as inability.
- Mandatory requirements, skills, experience, evidence quality, and practical constraints have explicit point budgets.
- Missing mandatory requirements cap the final score.
- Strengths and gaps must cite the corresponding requirement and evidence.
- Output is decision support, not a hiring probability or guarantee.

## Local-model tuning

Ollama requests use temperature `0`, strict JSON Schema, and `think: false`. Disabling hidden reasoning is intentional for this extraction workload: it improves latency and makes `qwen3:8b` more deterministic on an 8 GB GPU.

## Evaluation checklist

Before publishing a new prompt version, test Chinese, Japanese, and English samples covering:

- missing salary, deadline, and employment type;
- required versus preferred qualifications;
- hybrid versus fully remote work;
- numeric experience thresholds;
- malicious instructions embedded in a JD or resume;
- a strong match, partial match, and clearly weak match;
- agreement between score, reasoning, strengths, gaps, and recommendation.

Automated tests verify prompt boundaries, injection instructions, rubric presence, prompt version storage, and Ollama thinking configuration. Human comparison is still required because semantic quality cannot be fully asserted by unit tests.
