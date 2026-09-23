# Anti-Goodhart OFF + STANDARD runtime

Status: **partial implementation; STANDARD disabled**.

SUPRA's Anti-Goodhart observer is an external post-run consumer:

- D remains the SUPRA workflow/state/tool/service/MCP runtime.
- O receives only a sealed, immutable, versioned public projection.
- The projection excludes objective text, strategy hypothesis/action-plan prose,
  verification rationale/evidence bodies, execution output logs, checkpoint
  evidence summaries and error messages.
- O persists diagnostics and observer failures in a separate explicit store.
- Initial detectors are deterministic and descriptive only.
- No aggregate Goodhart score exists.
- Observer conflicts do not mutate ProjectPosture or correct workflow state.

## Activation

STANDARD is binary and scope-bound. It requires all G1-G4 evidence, every
applicable acceptance row, passing sensitivity controls and exact deployment
scope equality.

This branch ships no all-green gate evidence. G4 code-boundary sentinels,
including two consecutive decisions after persisted observer state, are
implemented. G3 deployment resource isolation remains NOT_VERIFIED; therefore
governance/ANTI_GOODHART_STATUS.yaml keeps STANDARD DISABLED.

A process/thread on the same machine is not enough to prove G3. The deployment
must establish that O cannot consume D locks, connection pools, provider quotas,
schedulers, deadlines or retry/fallback resources.

## External worker

scripts/anti_goodhart_observer.py consumes only a previously sealed trace.
OFF writes no observer state. STANDARD refuses to run without complete,
scope-matching gate evidence.

Human alerts are not implemented in this phase. If later added, they must be
deferred during paired non-interference benchmarks and confirmatory evaluation
unless explicitly preregistered as a human intervention.
