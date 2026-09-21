# SUPRA Architecture

## Boundaries

SUPRA is split into four explicit boundaries:

1. **Transport** — FastAPI REST, the Web UI, and the JSON-RPC tool endpoint.
2. **Provider facade** — a small typed contract for Hermes/Nous, Ollama,
   OpenAI, and arbitrary OpenAI-compatible endpoints.
3. **Deterministic coordinator** — five stateful stages with safety gates,
   textual strategy-coverage evaluation, and trusted in-process restricted execution.
4. **Evidence** — thread-safe project persistence plus JSON, Markdown, and HTML
   dossier exports with a SHA-256 integrity value.

## Provider contract

`src/supra_agentic/providers/base.py` defines the stable interface. The HTTP
adapter sends only typed messages and optional tool schemas to
`/chat/completions`, discovers `/models` when the model is `auto`, and converts
the response into a provider-neutral `ProviderResponse`.

Hermes is a local boundary by default. Its proxy owns authentication and
upstream routing; SUPRA never embeds or persists those credentials. A provider
failure is reported as an unavailable model boundary and does not corrupt the
deterministic project state.

## State flow

```text
RECEIVED -> STRUCTURED -> STRATIFIED -> RESTRICTED_EXECUTION_VERIFIED -> COMPLETED
```

Each transition writes a checkpoint containing the actor, evidence summary, and
timestamp. `record_checkpoint` serializes the final deliverable in sorted JSON
before computing an integrity digest. That SHA-256 identifies those serialized
bytes; it is not a truth, verification, or scientific-validity certificate.

## Safety model

- The default project path does not contact a model.
- Model assistance is opt-in per request (`use_model`) or through
  `SUPRA_USE_MODEL=true`.
- Model output is advisory and recorded separately from deterministic evidence.
- Provider HTTP errors exclude response bodies and authorization headers.
- `verify_solution` is a deterministic textual coverage heuristic. Its PASS
  means supported invariant keywords are covered by the selected strategy text;
  it is not deployed-system certification.
- `restricted_python_executor` is an in-process trusted internal check, not a
  security sandbox. It cannot claim process isolation or scientific validation.
- The restricted stage advances only when a passing execution is bound to the
  persisted selected candidate and the actually executed protocol.
- `COMPLETED` denotes workflow completion only; verification and scientific
  status remain separate fields.

## Extension points

To add a backend, implement `AgentProvider.generate`, `name`, and `metadata`,
then register a factory in `providers/__init__.py`. No coordinator or state
machine changes are required for a new OpenAI-compatible endpoint.