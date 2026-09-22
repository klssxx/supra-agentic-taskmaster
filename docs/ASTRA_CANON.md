# ASTRA CANON — SUPRA

SUPRA aplica el manifiesto local compatible con ASTRA_CANON v1. Se protegen contratos, no implementaciones concretas.

`CANON` es obligatorio. `CANON_WITH_LIMITATIONS` es obligatorio con límites explícitos. `RESEARCH_ONLY` no está promovido. `UNRESOLVED` conserva una pregunta abierta.

`implemented`, `wired`, `tested`, `scientifically supported` y `canon ready` son estados distintos. `code exists != scientifically validated`.

COMPLETED también es un estado explícitamente acreditado: requiere verificación de cobertura PASS o CONDITIONAL_PASS y una ejecución restringida vigente BOUND_PASS. FAIL, NOT_EVALUATED, ausencia de verificación o ausencia de ejecución ligada dejan el workflow bloqueado en la etapa previa. COMPLETED no equivale a validación científica.

CLAIM, TEST, OBSERVATION, EVIDENCE y RESULT permanecen separados. `RESTRICTED_EXECUTION_VERIFIED` significa únicamente que la ejecución restringida identificada pasó su propio protocolo; no demuestra que una hipótesis sea científicamente válida. Una ejecución debe enlazar candidate_id, mechanism/version, claim/hypothesis, protocol/test version, execution_id y observed result para acreditar evidencia experimental.

CODEOWNERS no impide cambios sin branch protection/ruleset.
