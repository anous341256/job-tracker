# Job Tracker Agent Handoff

**Generated:** 2026-08-19  
**Workspace:** `D:\New project`  
**Purpose:** give the next implementation agent an accurate starting point for the current, uncommitted “action center” version.

## 1. Read this first

1. The primary worktree is **dirty by design**. Do **not** use `git reset --hard`, `git checkout --`, branch switching in place, or broad cleanup commands.
2. All local project state must remain on **D:**. Do not install models, Docker data, Python environments, or other large assets on C:.
3. The application is a personal job-search tracker. All business queries must be scoped to the authenticated user. Preserve object-level authorization and CSRF protection.
4. Classic Outlook synchronization is **read only**. Do not add behavior that sends, deletes, moves, marks read, or otherwise changes Outlook mail without an explicit new user request.
5. AI output is advisory only. It must never create a formal calendar event, interview, To Do, company, application, or send email without explicit user approval.

## 2. Snapshot of the workspace

| Item | Current state |
| --- | --- |
| Main worktree | `D:\New project` |
| Base commit | `3627fa9` — `fix: verify portable Ollama startup` |
| Active branch | `agent/initial-job-tracker` |
| Uncommitted implementation | Large: 45 tracked files changed, 42 untracked files at the inventory time. This is the real current system; the base commit does not contain the action-center, Docker/Host Agent, or mail-assistant work. |
| Old UI worktree | `D:\job-tracker-old-ui` on branch `codex/old-ui-snapshot` |
| Old UI role | Isolated comparison version, available at `http://127.0.0.1:8001`; not the product baseline. |
| Current UI | `http://127.0.0.1:8000` |

Do not assume `git status` being dirty means the work is disposable. It contains the implementation that has been built during the current product iteration.

## 3. What is implemented in the current worktree

### Action center / business flow

- The home page is an **action center**, not a statistics dashboard.
- `Company` is the primary container. A card displays effective positions, upcoming calendar items, and incomplete To Do items.
- Company creation is a compound transaction: one company can be created with optional job positions, calendar events, and To Do items in one form.
- A job position exposes the five-stage Japanese job-search control:
  - no application;
  - researching (`preparing`);
  - applied / ES (`applied`, `screening`, `assessment`);
  - interviewing (`interviewing`);
  - ended (`offer`, `accepted`, `rejected`, `withdrawn`, `ghosted`, `closed`).
- Stage changes use the application service layer and record `ApplicationStatusLog`. Ended attempts remain historical; a new attempt creates a new `Application`.
- Companies can be pinned by `pinned_order`; non-pinned companies are automatically sorted by action urgency and priority.

Main implementation locations:

- `core/views.py`, `core/services.py`, `core/forms.py`, `core/models.py`
- `companies/views.py`, `companies/forms.py`, `companies/models.py`
- `applications/services.py`
- `templates/core/dashboard.html`, `templates/core/_company_action_card.html`, `templates/core/_job_pipeline_row.html`, `templates/core/_todo_mini_row.html`

### Calendar, tasks, and reminders

- `CalendarEvent` is the generic formal calendar record; it must belong to a company and may additionally reference a job, application, contact, or source email.
- `Interview` remains the specialized record for an interview associated with an application.
- `TodoItem` must belong to a company; it may reference a job, application, source email, and source link.
- The calendar aggregates formal calendar events, interviews, deadlines, follow-up items, and To Do layers.
- `GET /calendar/free-slots/` calculates weekday (Mon–Fri) availability from 10:00 to 19:00 in the user profile time zone. Only formal events and uncancelled interviews occupy time; intervals under 30 minutes are hidden.
- Notifications and reminders are generated/sent by Celery tasks. Calendar and reminder display are intentionally in the user’s profile time zone, defaulting to `Asia/Tokyo`.

Main implementation locations:

- `core/models.py`, `core/tasks.py`, `core/views.py`, `core/forms.py`
- `templates/core/calendar.html`, `templates/core/todos.html`

### Mailboxes and the Windows Host Agent

- Current mailbox product path is classic Windows Outlook COM, not Microsoft Graph OAuth.
- Docker cannot use Outlook COM or loopback-only Ollama directly. Django creates `HostAgentCommand` records; the Windows agent claims commands and posts the bounded result back.
- Commands cover Outlook connection/sync and local Ollama inference. Health is represented by `HostAgentHeartbeat`.
- Host Agent source is `scripts/host_agent.py`; receiver/authentication is `core/host_agent.py`; Outlook import and idempotent storage handling is `mailboxes/host_agent.py` plus `mailboxes/services.py`.
- The data copy is deduplicated by `EmailAccount + provider_message_id` (classic Outlook EntryID in the current local provider).
- Local MySQL mail deletion only deletes the Job Tracker copy. `DeletedEmailMarker` saves a hash to prevent immediate re-import for 45 days.
- Retention policy protects linked mail, removes unlinked mail after 180 days, and keeps up to 1,000 unlinked mails per mailbox.
- Manual linking, company quick-linking, search, pagination, attachment selection/import, and local message reading are implemented.

Historical audit note: a prior reconciliation found 372 Inbox messages in the latest 30-day window already present in the local copy. This is historical evidence, not a guarantee that the current sync has no timezone/pagination issue; re-verify before claiming mail sync is fixed.

### AI assistant

- Default provider: local Ollama model `qwen3:8b`.
- Optional provider: OpenAI Responses API; each user supplies a personal API key. The key is Fernet-encrypted using `AI_CREDENTIAL_ENCRYPTION_KEY`; cloud resume/mail use needs explicit sensitive-data consent.
- Implemented AI tasks: JD parsing, resume/job matching, email schedule extraction, and one-email assistant chat.
- Email assistant workflow: `EmailAssistantThread` + visible `EmailAssistantMessage` conversation + versioned `EmailScheduleCandidate` and `EmailTodoCandidate`.
- Assistant output uses structured schemas. Candidates may be edited, approved, rejected, or superseded. Approval creates exactly one formal `Interview`, `CalendarEvent`, or `TodoItem` through the service layer.
- Long email text is bounded before prompting; prompts and hidden model reasoning are not intended to be persistently stored.
- In Docker mode local Ollama calls are routed through the Host Agent. OpenAI tasks execute directly in the worker.

Main implementation locations:

- `ai_assistant/models.py`, `services.py`, `tasks.py`, `providers.py`, `schemas.py`, `prompts.py`
- `ai_assistant/assistant_views.py`, `ai_assistant/views.py`, `ai_assistant/urls.py`
- `templates/ai_assistant/mail_assistant.html` and `_mail_assistant_*.html`

## 4. Architecture and runtime

```text
Browser
  -> Django web container (port 8000)
       -> MySQL 8.4 (business source of truth)
       -> Redis + Celery worker/beat
       -> Docker media/static volumes
       -> authenticated Host Agent command endpoints

Windows Host Agent (same signed-in desktop session)
  -> classic Outlook COM (read-only)
  -> local Ollama at 127.0.0.1:11434
  -> outbound authenticated requests to Django
```

### Docker services currently running at inventory time

| Service | State | Notes |
| --- | --- | --- |
| `web` | running | New application, port 8000 |
| `mysql` | healthy | Host port 3307 -> container 3306 |
| `redis` | running | Host port 6379 |
| `worker` / `beat` | running | Async work and schedules |
| `legacy-web` | running | Local-only `127.0.0.1:8001`, isolated old UI comparison |

`docker-compose.yml` is currently an **untracked** but required file. It defines the main stack and the legacy comparison service. `Dockerfile`, `.dockerignore`, `.env.docker.example`, and Docker helper scripts are also new files that must be considered together if/when committing.

### Startup commands

```powershell
# Docker stack
cd "D:\New project"
powershell -ExecutionPolicy Bypass -File .\scripts\docker-up.ps1

# Windows-only integration helper for Docker mode
powershell -ExecutionPolicy Bypass -File .\scripts\start-host-agent.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-ollama.ps1

# Stop containers (does not remove volumes)
powershell -ExecutionPolicy Bypass -File .\scripts\docker-down.ps1
```

Do not use `docker compose down -v` unless the user explicitly approves deleting Docker-managed MySQL, Redis, media, and static data.

## 5. Important data and migration facts

- Custom user model: `accounts.User`; `AUTH_USER_MODEL` is already configured.
- Default application time zone: `Asia/Tokyo`; profile can override it.
- Current new migrations that must travel with this worktree:
  - `companies/migrations/0004_company_pinned_order.py`
  - `core/migrations/0002_todoitem.py` through `0006_todoitem_source_email_source_url.py`
  - `ai_assistant/migrations/0002_emailschedulecandidate_and_more.py` through `0005_email_todo_candidate.py`
- Treat `docs/data-model.md` as the design baseline. Update it before new model decisions.
- The application database is `job_tracker`. The old UI comparison database is separate: `job_tracker_legacy`.
- Do not copy MySQL data directories between machines or try to make two writable MySQL primaries. Use a backup/export or a deliberately designed synchronization strategy.

## 6. Verification done during this handoff

| Check | Result |
| --- | --- |
| Host-source `manage.py check` | Passed: no issues |
| Host-source `makemigrations --check --dry-run` | No model changes detected; emitted a MySQL access warning because the host process could not authenticate to the Docker database at that moment |
| Docker `web` `manage.py check` | Passed: no issues |
| Docker service status | Main web, MySQL, Redis, worker, beat, and legacy-web were running; MySQL healthy |
| System manual | `docs/system-manual.html` was added and HTML-parsed successfully |

No complete `manage.py test --keepdb` regression run was performed in this handoff turn. Do not state a full regression result without running it in the intended database context.

## 7. Current risks and known gaps

1. **Mailbox sync is not a completed reliability story.** Existing risks include received-time/time-zone handling, finite Inbox/30-day scanning behavior, pagination/retry behavior, and Host Agent process lifecycle. Diagnose each issue with logs and stored timestamps; do not guess.
2. **Local AI availability depends on the desktop.** When Ollama or the Host Agent is offline, local AI tasks correctly wait but the recovery/retry user experience needs continued validation.
3. **Host Agent authentication is static Bearer-token based.** It is acceptable for the current same-machine development scope but is not a final remote-agent security design. Future remote use should move to device keys, signed requests, timestamps, and nonces.
4. **Docker configuration is development-oriented.** It uses Django’s development server and exposes MySQL/Redis on host ports. Do not expose the present Compose setup directly to the internet.
5. **Graph real-time mail architecture is only a proposed next step.** Microsoft Graph OAuth, subscriptions/webhooks, delta synchronization, renewal, and missed-event recovery are not implemented in this code path.
6. **The repo needs an intentional commit/review pass.** Changes are broad, span models/templates/Docker/scripts, and currently exist as a working tree delta. Do not push them piecemeal without reviewing migrations, ignored files, and secrets.

## 8. First actions for the next agent

1. Read `docs/system-manual.html`, `docs/data-model.md`, and this file.
2. Run `git status --short`; preserve all pre-existing changes.
3. Confirm the requested area and inspect the relevant app before editing. Avoid broad rewrites.
4. For ordinary web/database work, prefer Docker verification:

   ```powershell
   docker compose exec web python manage.py check
   docker compose exec web python manage.py migrate --check
   ```

5. For Outlook/Ollama issues, inspect separately:
   - Docker web/worker/beat logs;
   - Host Agent log/status under `D:\New project\.local\host-agent\`;
   - local Ollama health at `127.0.0.1:11434`;
   - stored email timestamps in MySQL.
6. Before committing, inspect `git diff`, `git ls-files --others --exclude-standard`, migration consistency, and ensure `.env`, `.local`, media, tokens, mailbox bodies, and database files are not staged.

## 9. Reference documents and entry points

| Path | Why it matters |
| --- | --- |
| `README.md` | User-facing project overview and startup instructions |
| `docs/system-manual.html` | Current system-level explanation and architecture |
| `docs/data-model.md` | Domain and action-center data design |
| `docs/ai-assistant.md` | AI provider, privacy, local runtime rules |
| `docs/ai-prompts.md` | Prompt design documentation |
| `config/settings.py` | Environment, security, database, Celery, Host Agent settings |
| `docker-compose.yml` | Actual local Docker topology |
| `scripts/start-all.ps1` | Non-Docker local stack entry point |
| `scripts/start-host-agent.ps1` | Windows integration helper entry point |

## 10. User collaboration preferences

- Work in small, verified increments; explain what changed, why, what was verified, and the next step.
- Keep large artifacts and new installations on D:, never casually consume C:.
- Do not make destructive cleanup, data-reset, remote-network, or external-account changes without clear user authorization.
- Prefer practical implementation over abstract explanation, but distinguish implemented facts from plans and recommendations.
- The user cares about the Japanese job-search experience: compact, calm, action-oriented UI; avoid reverting to a database-like dashboard full of charts.
