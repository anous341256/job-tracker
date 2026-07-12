# AI Assistant

The first AI phase uses a provider-neutral service layer. Local Ollama is the default; each user may optionally save an individually encrypted OpenAI API key.

## Local runtime

All persistent local AI files are intentionally kept under `D:\New project\.local`:

- `.local/ollama` — standalone Ollama binaries
- `.local/ollama-models` — model weights
- `.local/ollama-home` — Ollama identity and configuration
- `.local/celery` — filesystem broker queues and processed messages

The project uses `qwen3:8b` as the default local model. Run `scripts/start-all.ps1` to start MySQL, Ollama, Celery worker, beat, and Django.

## OpenAI key encryption

Generate a dedicated Fernet key and add it to the ignored `.env` file:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```dotenv
AI_CREDENTIAL_ENCRYPTION_KEY=paste-generated-value-here
```

Never rotate this value while encrypted user API keys remain in the database. Delete the stored user keys first, rotate the encryption key, then ask users to enter their API keys again.

OpenAI requests use the Responses API with structured Pydantic output and `store=false`. The application stores model names, token counts, task status, and structured results, but not complete prompts or hidden reasoning.

## Safety boundaries

- AI output never changes business data without an explicit POST confirmation.
- Job descriptions and resumes are treated as untrusted input and cannot enable tools.
- Email addresses and phone numbers are redacted before cloud resume matching.
- Cloud resume matching is blocked until the user enables sensitive-cloud consent.
- `.doc` resumes must be converted to PDF or DOCX before analysis.
