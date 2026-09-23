# ASTRA CANON — SUPRA

SUPRA aplica el manifiesto local compatible con ASTRA_CANON v1. Se protegen contratos, no implementaciones concretas.

`CANON` es obligatorio. `CANON_WITH_LIMITATIONS` es obligatorio con límites explícitos. `RESEARCH_ONLY` no está promovido. `UNRESOLVED` conserva una pregunta abierta.

`implemented`, `wired`, `tested`, `scientifically supported` y `canon ready` son estados distintos. `code exists != scientifically validated`.

COMPLETED también es un estado explícitamente acreditado: requiere verificación de cobertura PASS o CONDITIONAL_PASS, una ejecución restringida vigente BOUND_PASS y un smoke de aislamiento Docker ligado a identidad vigente. Ese smoke acredita controles de aislamiento e identidad, no ejecuta el mecanismo/action plan/hypothesis del candidato. FAIL, NOT_EVALUATED o ausencia de cualquiera de los gates deja el workflow bloqueado. COMPLETED no equivale a ejecución semántica del candidato ni a validación científica.

CLAIM, TEST, OBSERVATION, EVIDENCE y RESULT permanecen separados. `RESTRICTED_EXECUTION_VERIFIED` significa únicamente que la ejecución restringida identificada pasó su propio protocolo; no demuestra que una hipótesis sea científicamente válida. Una ejecución debe enlazar candidate_id, mechanism/version, claim/hypothesis, protocol/test version, execution_id y observed result para acreditar evidencia experimental.

CODEOWNERS no impide cambios sin branch protection/ruleset.
