"""Run a batch of prompts through the configured SUPRA provider."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from supra_agentic.agent import create_taskmaster_agent


PROMPT = """Actúa como un Motor de Innovación Combinatoria y Falsación Causal. Tu objetivo es generar propuestas de arquitectura, mejora o producto estrictamente ortogonales a las convenciones actuales.

REGLAS DE GENERACIÓN:
1. ANTICONSENSO: Descarta asociaciones lógicas obvias y evoluciones lineales.
2. ADYACENTE POSIBLE (0.45 <= Dh <= 0.85): Cruza dos dominios poco conectados cuya unión sea viable.
3. ESTRUCTURA VS CONTENIDO: Cambia el mecanismo, arquitectura o flujo de control; no solo los datos o la estética.
4. CONDICIÓN DE MUERTE: Toda propuesta debe ser falsable con una métrica o experimento.

FORMATO DE SALIDA:
- [CÓDIGO DE INNOVACIÓN]
- [VECTORES CRUZADOS]
- [LA TESIS]
- [EL MECANISMO ESTRUCTURAL]
- [HIPÓTESIS NULA (H0) Y FALSACIÓN]
- [VERIFICACIÓN MVP]
"""


async def generate_one(agent, index: int, semaphore: asyncio.Semaphore) -> dict[str, object]:
    async with semaphore:
        try:
            response = await asyncio.to_thread(agent.run, PROMPT)
            return {
                "index": index,
                "status": "success",
                "provider": response.provider,
                "model": response.model,
                "content": response.text,
                "tool_calls": response.tool_calls,
            }
        except Exception as exc:
            return {"index": index, "status": "error", "error": str(exc)}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("data/provider_runs.json"))
    args = parser.parse_args()
    if args.runs < 1 or args.concurrency < 1:
        raise SystemExit("--runs and --concurrency must be positive")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    agent = create_taskmaster_agent()
    semaphore = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(
        *(generate_one(agent, index, semaphore) for index in range(1, args.runs + 1))
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Saved %s provider runs to %s", len(results), args.output)


if __name__ == "__main__":
    asyncio.run(main())
