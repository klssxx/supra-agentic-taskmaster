# ASTRA COVERAGE MATRIX

Observed local gate: `uv run --locked pytest -q tests/astra_canon` → `6 passed`.

| ID | Contract | Code path(s) | Sentinel(s) | CI | Observed result |
|---|---|---|---|---|---|
| ASTRA-001 | ['hecho, hipótesis, pendiente, observación, evidencia y decisión permanecen distintos', 'una estructura completa no eleva certeza'] | `src/supra_agentic/dossier.py`<br>`src/supra_agentic/models.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-003 | ['las afirmaciones derivadas conservan source, transformation, version y scope cuando procede', 'la extracción no se presenta como observación experimental'] | `src/supra_agentic/dossier.py`<br>`src/supra_agentic/models.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-017 | ['planned test no equivale a executed test', 'generic restricted execution success no equivale a scientific validation'] | `src/supra_agentic/models.py`<br>`src/supra_agentic/state.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-018 | ['una prueba relaciona claim, rival explanation, intervention/test, observable, predictions y decision rule', 'una observación no discriminante es INCONCLUSIVE'] | `src/supra_agentic/dossier.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-019 | ['prior-art, judge y observed result permanecen separados hasta consumidor', 'combinar canales requiere semántica explícita'] | `src/supra_agentic/tools.py`<br>`src/supra_agentic/models.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-020 | ['INDETERMINATE, INVALID y NOT_EVALUATED no generan reward observado'] | `src/supra_agentic/dossier.py`<br>`src/supra_agentic/models.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-024 | ['seed y store hash no prometen reproducibilidad global si influyen clock, policy version, corpus, config, provider, ordering, code version o external state', 'se registran las dependencias reales conocidas del componente'] | `src/supra_agentic/dossier.py`<br>`src/supra_agentic/tools.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-026 | ['comparaciones contabilizan generation calls, retries, candidate opportunities, selection opportunities, evaluation calls y budget'] | `src/supra_agentic/models.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-028 | ['para claims fuertes se documentan blinding, positive controls, negative controls, disagreement y limits cuando aplican'] | `src/supra_agentic/dossier.py`<br>`src/supra_agentic/state.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-031 | ['nombres como Pareto, MAP-Elites, do-calculus o causal no acreditan implementación completa', 'las capacidades se describen por contrato real'] | `src/supra_agentic/tools.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-033 | ['una reparación no borra negative evidence, historical failures ni original protocols', 'un hash acredita integridad relativa a una referencia, no verdad'] | `src/supra_agentic/dossier.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |
| ASTRA-034 | ['cambiar un contrato requiere versioned decision, evidence y review', 'cambiar implementación conservando contrato está permitido'] | `src/supra_agentic/dossier.py` | `tests/astra_canon/test_astra_supra_contracts.py` | `ASTRA canon` required job | LOCAL PASS |

The local result is evidence for the working-tree snapshot at generation time; GitHub Actions remains NOT_RUN until the pushed commit is observed by GitHub.
