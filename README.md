# SUPRA Agentic Taskmaster

Provider-neutral engine for decomposing complex objectives, generating strategy
candidates, evaluating scoped textual invariant coverage, running trusted
restricted checks, and issuing auditable technical dossiers.

## What it does

SUPRA combines a deterministic five-stage workflow with an optional model
boundary. The deterministic stages remain authoritative for state transitions,
safety gates, scoped coverage evaluation, trusted restricted execution, and the
SHA-256 payload-integrity ledger.

1. **RECEIVED** — capture the objective and initialize an isolated project.
2. **STRUCTURED** — separate invariants, mutable assumptions, and subtasks.
3. **STRATIFIED** — produce Conservative, Orthogonal, and Disruptive pathways.
4. **RESTRICTED_EXECUTION_VERIFIED** — the trusted internal check passed and is bound to the persisted selected candidate/protocol. This is in-process restricted execution, not a security sandbox or scientific validation.
5. **COMPLETED** — the workflow finished and exported the integrity-addressed dossier. Completion does not imply verification PASS or scientific validity.

The model is an interchangeable assistant, not a hidden requirement. The
application can execute the complete workflow offline and can optionally use
Hermes/Nous, Ollama, OpenAI, or any OpenAI-compatible local/cloud endpoint.

## Architecture

```text
Web UI / REST / WebMCP
          |
          v
Provider-neutral Taskmaster facade ---- optional model provider
          |
          v
Deterministic stage runner
  decompose -> synthesize -> coverage-check -> restricted-check -> checkpoint
          |
          v
Thread-safe state + JSON/Markdown/HTML dossier + SHA-256 ledger
```

The model boundary is deliberately narrow: SUPRA sends typed chat messages and
can receive text and tool-call envelopes through the OpenAI-compatible wire
contract. SUPRA does not launch provider subprocesses automatically and never
stores provider credentials in the repository.

## Providers

Provider selection uses `SUPRA_PROVIDER` unless a request supplies `provider`.

| Name | Default endpoint | Model configuration |
|---|---|---|
| `hermes` / `nous` | `http://127.0.0.1:8645/v1` | `SUPRA_HERMES_MODEL` or `SUPRA_MODEL` |
| `ollama` | `http://127.0.0.1:11434/v1` | `SUPRA_OLLAMA_MODEL` or `SUPRA_MODEL` |
| `openai` | `https://api.openai.com/v1` | `OPENAI_MODEL` or `SUPRA_MODEL` |
| `openai-compatible` / `custom` | `SUPRA_BASE_URL` | `SUPRA_MODEL` |

Examples:

```bash
# Full workflow stays offline by default.
uvicorn supra_agentic.service:app --host 127.0.0.1 --port 8080

# Use the Hermes/Nous proxy for a direct model request.
set SUPRA_PROVIDER=hermes
set SUPRA_HERMES_MODEL=auto
curl -X POST http://127.0.0.1:8080/api/v1/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"prompt\":\"Describe one falsifiable architecture hypothesis.\"}"

# Use Ollama instead.
set SUPRA_PROVIDER=ollama
set SUPRA_OLLAMA_MODEL=llama3.2

# Enable optional model assistance during a project run.
curl -X POST http://127.0.0.1:8080/api/v1/projects ^
  -H "Content-Type: application/json" ^
  -d "{\"objective\":\"Bound a local automation controller\",\"use_model\":true}"
```

For Hermes/Nous, start and authenticate the proxy outside SUPRA using the
Hermes CLI. SUPRA only connects to the local HTTP boundary; it does not copy,
inspect, or persist the proxy credentials. With Hermes installed, the
operator-managed sequence is:

```bash
hermes auth add nous
hermes proxy start --provider nous --host 127.0.0.1 --port 8645
```

The proxy supports Hermes' declared upstreams, while `openai-compatible` is
the separate preset for arbitrary endpoints configured with `SUPRA_BASE_URL`.

## Installation

Requirements: Python 3.11+ and Git.

```bash
python -m pip install -e .
uvicorn supra_agentic.service:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080`.

## API surface

- `GET /health` — service and non-secret active-provider metadata.
- `GET /api/v1/providers` — supported provider presets.
- `POST /api/v1/generate` — direct provider generation.
- `POST /api/v1/projects` — run the five-stage workflow.
- `GET /api/v1/projects` — list persisted projects.
- `GET /api/v1/projects/{project_id}` — retrieve full project telemetry.
- `GET /api/v1/examples/quick-run` — deterministic local example.
- `POST /api/v1/mcp` — JSON-RPC 2.0 tool boundary.
- `GET /api/v1/export/dossier/{project_id}` — Markdown dossier.
- `GET /api/v1/export/dossier/html/{project_id}` — HTML dossier.

## Tests

```bash
python -m pytest -q
```

The provider tests use an in-memory HTTP transport; they do not contact a
remote service or require credentials.

## Container

The included `Dockerfile` is a generic OCI-compatible image. It starts the
same Uvicorn application and does not assume a hosting vendor or provider.

## Security boundaries

- Credentials are read only from environment variables or the external local
  provider process.
- Error responses do not include provider response bodies or authorization
  headers.
- Restricted execution is in-process, accepts only the trusted internal contract,
  rejects imports/unbounded loop constructs, and is **not** an OS/process sandbox.
- A restricted PASS is scoped to that internal protocol; it is not proof of
  deployed-system safety or scientific validation.
- SHA-256 identifies serialized payload integrity relative to the hashed bytes;
  it is not evidence that the payload is true.

## License

Apache License 2.0. See [LICENSE](LICENSE).