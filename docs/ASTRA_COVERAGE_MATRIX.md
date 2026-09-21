# ASTRA COVERAGE MATRIX — SUPRA

This matrix separates **normative contract presence** from **runtime enforcement**.
The previous snapshot reported `6 passed` while mapping those tests to twelve
contracts. That was not sufficient evidence that twelve runtime invariants had
actually been falsified.

Current enforcement vocabulary:

- `ENFORCED`: behavioral/product-path sentinel exercises the material invariant.
- `PARTIAL`: meaningful enforcement exists, but material scope remains open.
- `LIMITATION_GUARD`: the code prevents an overclaim without implementing the
  stronger scientific capability.
- `DOCUMENTATION_ONLY`: governance requirement only.
- `NOT_APPLICABLE_RUNTIME`: no learning/action path exists in SUPRA for that contract.

## Execution evidence

The historical `6 passed` result belongs to the earlier ASTRA snapshot. New
behavioral sentinels and runtime repairs were added afterwards. The current branch
therefore remains **REMOTE CI NOT_RUN** until GitHub Actions executes this HEAD.

| ID | Current enforcement | Evidence / remaining limitation |
|---|---|---|
| ASTRA-001 | ENFORCED | UI, API, state and final payload separate workflow completion, coverage verdict, restricted execution and scientific status. Missing UI values no longer become PASS/95%/VERIFIED. |
| ASTRA-003 | PARTIAL | Final payload records telemetry provenance, transform and scope; universal claim-level provenance remains outside SUPRA. |
| ASTRA-006 | ENFORCED | Verification verdict vocabulary is closed; confidence is bounded and labelled `HEURISTIC_COVERAGE` / fraction of declared invariants, not probability of real success. |
| ASTRA-017 | ENFORCED | Restricted stage advances only for a passing execution whose identity is derived from the persisted selected candidate and executed protocol under the current execution-semantics version. Caller strings cannot create binding. Scientific validation is structurally rejected. |
| ASTRA-018 | LIMITATION_GUARD | SUPRA does not implement a full discriminant scientific protocol; final output declares `discriminant_protocol_status=NOT_ESTABLISHED`. |
| ASTRA-019 | ENFORCED | Workflow, textual coverage, restricted execution and scientific status are serialized as separate channels. |
| ASTRA-020 | NOT_APPLICABLE_RUNTIME | SUPRA does not turn verification verdicts into adaptive rewards; final output declares `learning_update_status=NOT_APPLICABLE`. |
| ASTRA-024 | PARTIAL | Final payload records known dependencies and explicitly sets `closure_complete=false` with unclosed code/runtime/provider/environment dependencies. |
| ASTRA-026 | PARTIAL | Candidate, selection, verification and restricted-execution opportunities are counted. Provider generation-call accounting remains explicitly non-authoritative and `budget_complete=false`. |
| ASTRA-027 | LIMITATION_GUARD | No independent confirmatory campaign is claimed; `independent_confirmation_status=NOT_ESTABLISHED`. |
| ASTRA-028 | LIMITATION_GUARD | Payload explicitly records blinding/positive controls/negative controls/disagreement as false and disallows strong scientific claims. |
| ASTRA-031 | ENFORCED | MCP/docs describe counterfactual use as inspired/scoped and explicitly deny a full Pearl causal-inference implementation; restricted execution is not called a security sandbox. |
| ASTRA-033 | ENFORCED | Failed restricted attempts remain in project history after later success. Persisted legacy/pre-versioned execution-derived stages are downgraded on load and cannot reactivate accreditation after restart. SHA-256 is labelled payload integrity, not truth. |
| ASTRA-034 | PARTIAL | Manifest, CI gate and CODEOWNERS exist. Server-side branch/ruleset enforcement is not verified here. |

## Master compatibility

The CRIBA master canon scopes **14** contracts to SUPRA:

`001, 003, 006, 017, 018, 019, 020, 024, 026, 027, 028, 031, 033, 034`.

All 14 are present in the SUPRA manifest. The previous omissions of
`ASTRA-006` and `ASTRA-027` are closed.

## Scientific state

- `D3_NOVELTY = UNRESOLVED`
- `D4_FUNCTIONAL_DIVERSITY = UNRESOLVED`
- `D6_ADAPTIVE_BENEFIT = STILL_UNRESOLVED`
- `SCIENTIFIC_ADVANTAGE_OF_CRIBA = NOT_ESTABLISHED`
- Anti-Goodhart runtime is not implemented by this branch.

A green CI run is evidence for the checks that actually executed. It is not a
blanket scientific validation of SUPRA or CRIBA.
