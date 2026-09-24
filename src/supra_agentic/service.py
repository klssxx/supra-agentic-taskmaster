"""FastAPI backend for the provider-neutral SUPRA Agentic Taskmaster."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import secrets
from html import escape
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .dossier import export_full_html_dossier
from .mcp_handler import handle_mcp_jsonrpc_request
from .models import ProjectPosture
from .providers import ProviderError, get_provider, provider_names
from .runner import TaskmasterRunner, taskmaster_runner
from .state import ProjectAlreadyExistsError, state_manager, validate_project_id

logger = logging.getLogger("supra_agentic.service")


def _secure_sandbox_status(posture: ProjectPosture) -> str:
    latest = posture.secure_sandbox_results[-1] if posture.secure_sandbox_results else None
    if latest and latest.passed and latest.identity_bound and latest.isolation_verified:
        return "IDENTITY_BOUND_ISOLATION_PASS"
    if latest and latest.identity_bound and latest.isolation_verified:
        return "IDENTITY_BOUND_ISOLATION_FAIL"
    if latest:
        return "UNVERIFIED_ISOLATION"
    return "NOT_RUN"


def _secure_sandbox_scope(posture: ProjectPosture) -> str:
    latest = posture.secure_sandbox_results[-1] if posture.secure_sandbox_results else None
    return latest.execution_scope if latest else "NOT_RUN"


def _candidate_mechanism_executed_in_secure_sandbox(posture: ProjectPosture) -> bool:
    latest = posture.secure_sandbox_results[-1] if posture.secure_sandbox_results else None
    return bool(latest and latest.candidate_mechanism_executed)


def _markdown_text(value: Any) -> str:
    """Render untrusted values as single-line, inert Markdown text."""
    text = " ".join(str(value).splitlines())
    text = escape(text, quote=False).replace("`", "&#96;")
    for marker in ("\\", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", "!", "|", ">"):
        text = text.replace(marker, f"\\{marker}")
    return text


MAX_MCP_BODY_SIZE = 8 * 1024 * 1024


def _parse_cors_origins(raw: str | None) -> list[str]:
    """Parse explicit CORS origins; absent configuration remains closed."""
    if raw is None or not raw.strip():
        return []
    origins = [item.strip() for item in raw.split(",")]
    if any(not item for item in origins):
        raise RuntimeError("SUPRA_CORS_ORIGINS contains an empty origin")
    for origin in origins:
        if origin == "*":
            raise RuntimeError("SUPRA_CORS_ORIGINS must not contain wildcard origins")
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(f"Invalid CORS origin: {origin!r}")
    return origins


CORS_ORIGINS = _parse_cors_origins(os.getenv("SUPRA_CORS_ORIGINS"))
API_KEY = os.getenv("SUPRA_API_KEY", "").strip()


def _is_loopback_client(request: Request) -> bool:
    host = request.client.host if request.client is not None else ""
    if host == "testclient":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _supplied_api_key(request: Request) -> str:
    direct = request.headers.get("x-api-key", "").strip()
    if direct:
        return direct
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


app = FastAPI(
    title="SUPRA Agentic Taskmaster",
    version="1.0.0",
    description="Provider-neutral task decomposition, scoped strategy-coverage evaluation, restricted execution telemetry, and evidence generation.",
)

# Enable CORS - configurable, default restrictive (empty list = no CORS)
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )


@app.middleware("http")
async def enforce_api_auth(request: Request, call_next):
    """Require API-key authentication for non-loopback API clients."""
    if request.url.path.startswith("/api/v1/") and not _is_loopback_client(request):
        if not API_KEY:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "SUPRA_API_KEY is required for remote API access."},
            )
        supplied = _supplied_api_key(request)
        if not supplied or not secrets.compare_digest(supplied, API_KEY):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or missing API credentials."},
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)


STATIC_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class CribaDiscriminantProtocolRequest(BaseModel):
    """Discriminant protocol prepared by CRIBA; receipt is not execution evidence."""

    model_config = ConfigDict(extra="forbid")
    afirmacion_decisiva: str = Field(..., min_length=1, max_length=600)
    alternativa_explicativa: str = Field(..., min_length=1, max_length=1200)
    intervencion_prueba: str = Field(..., min_length=1, max_length=600)
    observable: str = Field(..., min_length=1, max_length=400)
    comparacion: str = Field("", max_length=800)
    metrica: str = Field("", max_length=400)
    resultado_favorable_mecanismo: str = Field(..., min_length=1, max_length=400)
    resultado_favorable_alternativa: str = Field(..., min_length=1, max_length=400)
    regla_decision: str = Field(..., min_length=1, max_length=400)
    condicion_fracaso: str = Field(..., min_length=1, max_length=400)
    coste_permisos: str = Field("", max_length=400)
    estado_prueba: Literal["NO_EJECUTADA"] = "NO_EJECUTADA"


class CribaDossierRequest(BaseModel):
    """Versioned CRIBA planning payload accepted by the project endpoint."""

    model_config = ConfigDict(extra="forbid")
    dossier_id: str = Field(..., min_length=1, max_length=128)
    candidate_id: str = Field(..., min_length=1, max_length=256)
    run_id: str = Field("", max_length=256)
    claim_id: str = Field(..., min_length=1, max_length=256)
    protocol_version: str = Field(..., pattern=r"^sha256:[0-9a-f]{64}$")
    mechanism_version: str = Field(..., pattern=r"^sha256:[0-9a-f]{64}$")
    problema: str = Field(..., min_length=1, max_length=400)
    bloqueo: str = Field("", max_length=1200)
    origen_bloqueo: str = Field("", max_length=120)
    hipotesis: str = Field(..., min_length=1, max_length=800)
    mecanismo: str = Field(..., min_length=1, max_length=2000)
    evidence_delivered: list[Any] = Field(default_factory=list)
    evidence_documented_as_used: list[Any] = Field(default_factory=list)
    evidencia_utilizada: list[Any] = Field(default_factory=list)
    prueba_discriminante: CribaDiscriminantProtocolRequest
    supuestos: list[Any] = Field(default_factory=list)
    estado: Literal["SUPRA_EJECUCION_PENDIENTE"]
    creado_at: str = Field("", max_length=80)


def _criba_dossier_receipt(dossier: CribaDossierRequest) -> dict[str, Any]:
    """Flatten only the discriminant planning facts SUPRA needs to preserve."""
    protocol = dossier.prueba_discriminante
    return {
        "receipt_scope": "PLANNED_DISCRIMINANT_PROTOCOL_ONLY",
        "execution_status": "NOT_EXECUTED",
        "scientific_status": "NOT_VALIDATED",
        "criba_dossier_id": dossier.dossier_id,
        "criba_candidate_id": dossier.candidate_id,
        "claim_id": dossier.claim_id,
        "mechanism_version": dossier.mechanism_version,
        "protocol_version": dossier.protocol_version,
        "alternativa_explicativa": protocol.alternativa_explicativa,
        "intervencion_prueba": protocol.intervencion_prueba,
        "observable": protocol.observable,
        "resultado_favorable_mecanismo": protocol.resultado_favorable_mecanismo,
        "resultado_favorable_alternativa": protocol.resultado_favorable_alternativa,
        "regla_decision": protocol.regla_decision,
        "condicion_fracaso": protocol.condicion_fracaso,
    }


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str = Field(
        ..., min_length=5, max_length=2000, description="The challenge or problem to solve."
    )
    domain: str = Field("general", max_length=100, description="Target problem domain.")
    project_id: str | None = Field(
        None,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
        description="Optional custom project ID using letters, digits, underscore, or hyphen.",
    )
    allow_disruptive: bool = Field(
        True, description="Whether to include disruptive divergent pathways."
    )
    provider: str | None = Field(
        None, max_length=64, description="Provider name, or SUPRA_PROVIDER when omitted."
    )
    model: str | None = Field(
        None, max_length=200, description="Provider model ID; auto-discovered when omitted."
    )
    use_model: bool = Field(
        False, description="Add optional model assistance without replacing deterministic gates."
    )
    criba_dossier: CribaDossierRequest | None = Field(
        None,
        description=(
            "Optional CRIBA planning dossier. SUPRA preserves a receipt but does not "
            "treat receipt as execution or scientific validation."
        ),
    )


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(..., min_length=1, max_length=12000)
    provider: str | None = Field(None, max_length=64)
    model: str | None = Field(None, max_length=200)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1, le=32768)


@app.get("/health", tags=["System"])
def healthcheck() -> dict[str, Any]:
    """Health probe with non-secret provider metadata."""
    return {
        "status": "healthy",
        "service": "supra-agentic-taskmaster",
        "version": "1.0.0",
        "provider": taskmaster_runner.provider_metadata(),
        "storage": {
            "mode": state_manager.storage_mode,
            "durability": (
                "instance-only"
                if state_manager.storage_mode == "INSTANCE_EPHEMERAL"
                else "depends-on-configured-filesystem"
                if state_manager.storage_mode == "CONFIGURED_FILESYSTEM"
                else "local-host"
            ),
        },
        "webmcp_enabled": True,
    }


@app.get("/api/v1/providers", tags=["Providers"])
def list_provider_options() -> dict[str, Any]:
    """List supported providers and safe local configuration metadata."""
    providers: list[dict[str, Any]] = []
    for name in provider_names():
        try:
            provider = get_provider(name)
            metadata = provider.metadata()
            metadata["alias"] = name != provider.name
            providers.append(metadata)
        except ValueError as exc:
            providers.append(
                {
                    "name": name,
                    "configured": False,
                    "error": "provider_configuration_invalid",
                    "error_type": type(exc).__name__,
                }
            )
    return {
        "status": "success",
        "active": os.getenv("SUPRA_PROVIDER", "hermes").strip().lower(),
        "providers": providers,
    }


@app.get("/", response_class=HTMLResponse, tags=["UI"])
def serve_ui() -> Response:
    """Serve the primary Web UI."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse(
            "<h1>SUPRA Agentic Taskmaster API Online</h1><p>Static UI building...</p>"
        )
    return FileResponse(str(index_file))


@app.post(
    "/api/v1/projects",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
    tags=["Taskmaster"],
)
def create_and_run_project(req: CreateProjectRequest) -> dict[str, Any] | Response:
    """Execute the five-stage workflow with deterministic gates.

    Returns HTTP status for workflow execution. A 201 response means the
    workflow request completed; verification and scientific status are returned
    separately and must not be inferred from HTTP success.
    - 201 Created + {"status": "success"} only when completion gates pass
    - 201 Created + {"status": "blocked"} when verification/execution gates block completion
    - 500 Internal Server Error + {"status": "error"} on workflow failure
    """
    try:
        if req.project_id is not None:
            validate_project_id(req.project_id)
            if state_manager.get_project(req.project_id) is not None:
                raise HTTPException(status_code=409, detail="Project ID already exists.")
        runner = TaskmasterRunner(provider_name=req.provider, model_name=req.model)
        posture = runner.run_golden_path(
            objective=req.objective,
            project_id=req.project_id,
            domain=req.domain,
            allow_disruptive=req.allow_disruptive,
            use_model=req.use_model,
            criba_dossier_receipt=(
                _criba_dossier_receipt(req.criba_dossier)
                if req.criba_dossier is not None
                else None
            ),
        )

        # Workflow failure and strategy-coverage verdict are different
        # channels. A coverage FAIL is returned as verification state; it is not
        # converted into an execution/server failure.
        if posture.stage.value == "FAILED":
            return Response(
                content=json.dumps(
                    {
                        "status": "error",
                        "status_scope": "WORKFLOW_EXECUTION",
                        "project_id": posture.project_id,
                        "stage": posture.stage.value,
                        "error": posture.error_message or "Pipeline execution failed",
                        "verification": posture.verification.model_dump()
                        if posture.verification
                        else None,
                    }
                ),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                media_type="application/json",
            )

        final_output = posture.final_output or {}
        workflow_completed = posture.stage.value == "COMPLETED"
        return {
            "status": "success" if workflow_completed else "blocked",
            "status_scope": "WORKFLOW_EXECUTION_ONLY",
            "completion_status": "COMPLETED" if workflow_completed else "BLOCKED",
            "workflow_status": posture.stage.value,
            "verification_status": (
                posture.verification.verdict if posture.verification else "NOT_EVALUATED"
            ),
            "secure_sandbox_status": _secure_sandbox_status(posture),
            "secure_sandbox_execution_scope": _secure_sandbox_scope(posture),
            "candidate_mechanism_executed_in_secure_sandbox": (
                _candidate_mechanism_executed_in_secure_sandbox(posture)
            ),
            "verification_scope": (
                posture.verification.verification_scope
                if posture.verification
                else "TEXTUAL_STRATEGY_COVERAGE"
            ),
            "scientific_status": final_output.get("scientific_status", "NOT_VALIDATED"),
            "project_id": posture.project_id,
            "stage": posture.stage.value,
            "posture": posture.model_dump(),
        }
    except HTTPException:
        raise
    except ProjectAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Project ID already exists.") from exc
    except ValueError as exc:
        logger.warning("Invalid project request (%s)", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Invalid project request.") from exc
    except Exception as exc:
        logger.error("Project execution failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Project execution failed.") from exc


@app.post("/api/v1/generate", tags=["Providers"])
def generate_with_provider(req: GenerateRequest) -> dict[str, Any]:
    """Generate model output through the selected provider boundary."""
    try:
        runner = TaskmasterRunner(provider_name=req.provider, model_name=req.model)
        response = runner.generate(
            req.prompt,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except ProviderError as exc:
        logger.error("Provider generation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Provider request failed.") from exc
    except ValueError as exc:
        logger.error("Invalid provider request (%s)", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Invalid provider request.") from exc
    return {
        "status": "success",
        "provider": response.provider,
        "model": response.model,
        "text": response.text,
        "tool_calls": response.tool_calls,
    }


@app.get("/api/v1/projects", tags=["Taskmaster"])
def list_projects(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict[str, Any]:
    """List recent Taskmaster projects."""
    projects = state_manager.list_projects(limit=limit)
    return {
        "status": "success",
        "count": len(projects),
        "projects": [p.model_dump() for p in projects],
    }


@app.get("/api/v1/projects/{project_id}", tags=["Taskmaster"])
def get_project_posture(project_id: str) -> dict[str, Any]:
    """Retrieve full project telemetry and deliverable ledger."""
    try:
        validate_project_id(project_id)
        posture = state_manager.get_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project ID.") from exc
    if not posture:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return {
        "status": "success",
        "project_id": posture.project_id,
        "posture": posture.model_dump(),
    }


# Compat alias: the live Cloud Run deployment and all submission docs
# reference /api/v1/demo/quick-run. Keep it working alongside the new
# /api/v1/examples/quick-run route.
@app.get("/api/v1/demo/quick-run", tags=["Examples"], include_in_schema=False)
def demo_quick_run_alias() -> dict[str, Any]:
    """Backwards-compatible alias for the historical demo URL."""
    return example_quick_run()


@app.get("/api/v1/examples/quick-run", tags=["Examples"])
def example_quick_run() -> dict[str, Any]:
    """Run a deterministic example without contacting a model provider."""
    demo_objective = (
        "Design an autonomous secretless service mesh with real-time continuous "
        "invariant verification and automated counterfactual rollback."
    )
    posture = taskmaster_runner.run_golden_path(
        objective=demo_objective,
        project_id=None,
        domain="cloud_security",
        allow_disruptive=True,
    )
    completed = posture.stage.value == "COMPLETED"
    return {
        "status": "success" if completed else "blocked",
        "example": True,
        "completion_status": "COMPLETED" if completed else "BLOCKED",
        "workflow_status": posture.stage.value,
        "verification_status": (
            posture.verification.verdict if posture.verification else "NOT_EVALUATED"
        ),
        "secure_sandbox_status": _secure_sandbox_status(posture),
        "secure_sandbox_execution_scope": _secure_sandbox_scope(posture),
        "candidate_mechanism_executed_in_secure_sandbox": (
            _candidate_mechanism_executed_in_secure_sandbox(posture)
        ),
        "scientific_status": (
            (posture.final_output or {}).get("scientific_status", "NOT_VALIDATED")
        ),
        "project_id": posture.project_id,
        "stage": posture.stage.value,
        "deliverable": posture.final_output,
        "posture": posture.model_dump(),
    }


@app.post("/api/v1/mcp", tags=["WebMCP"])
async def mcp_jsonrpc_endpoint(request: Request) -> dict[str, Any]:
    """Native WebMCP JSON-RPC 2.0 Protocol Handler.

    Includes body size limit (8 MiB) and basic JSON-RPC argument validation.
    """
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header") from exc
        if declared_size < 0:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header")
        if declared_size > MAX_MCP_BODY_SIZE:
            raise HTTPException(status_code=413, detail="Request body too large (max 8 MiB)")

    body = await request.body()
    if len(body) > MAX_MCP_BODY_SIZE:
        raise HTTPException(status_code=413, detail="Request body too large (max 8 MiB)")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

    # Basic JSON-RPC 2.0 validation
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON-RPC payload must be an object")
    if payload.get("jsonrpc") != "2.0":
        raise HTTPException(status_code=400, detail="Only JSON-RPC 2.0 is supported")
    if "method" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'method' in JSON-RPC request")
    if "id" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'id' in JSON-RPC request")

    return handle_mcp_jsonrpc_request(payload)


@app.get("/api/v1/export/dossier/{project_id}", tags=["Export"])
def export_technical_dossier(project_id: str) -> dict[str, Any]:
    """Export a markdown technical dossier of the completed project."""
    try:
        validate_project_id(project_id)
        posture = state_manager.get_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project ID.") from exc
    if not posture:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    decomp = posture.decomposition
    cand = posture.selected_candidate
    ver = posture.verification
    out = posture.final_output
    confidence_text = f"{ver.confidence_score:.2f}" if ver else "N/A"
    verification_text = ver.verdict if ver else "NOT_EVALUATED"
    verification_scope = ver.verification_scope if ver else "TEXTUAL_STRATEGY_COVERAGE"
    h0_text = out.get("null_hypothesis_h0", "NOT_SPECIFIED") if out else "NOT_SPECIFIED"
    h0_status = out.get("h0_evaluation_status", "NOT_EVALUATED") if out else "NOT_EVALUATED"
    scientific_status = out.get("scientific_status", "NOT_VALIDATED") if out else "NOT_VALIDATED"

    md_lines = [
        f"# TECHNICAL DOSSIER: {_markdown_text(posture.objective)}",
        f"**Project ID:** `{_markdown_text(posture.project_id)}`  ",
        f"**Stage:** `{_markdown_text(posture.stage.value)}`  ",
        f"**Audit SHA-256:** `{_markdown_text(out.get('audit_sha256', 'N/A') if out else 'N/A')}`  ",
        "",
        "---",
        "",
        "## 1. Problem Decomposition & Invariants",
        f"- **Domain:** {_markdown_text(decomp.domain if decomp else 'N/A')}",
        f"- **Core Objective:** {_markdown_text(decomp.core_objective if decomp else 'N/A')}",
        "### System Invariants (Must Hold):",
    ]
    if decomp:
        for inv in decomp.invariants:
            md_lines.append(f"- [x] {_markdown_text(inv)}")
        md_lines.append("")
        md_lines.append("### Mutable Assumptions (Challenged):")
        for mut in decomp.mutable_assumptions:
            md_lines.append(f"- [ ] ~{_markdown_text(mut)}~")

    md_lines.extend(
        [
            "",
            "## 2. Selected Strategy Pathway",
            f"- **Pathway:** {_markdown_text(cand.pathway_name if cand else 'N/A')}",
            f"- **Paradigm:** `{_markdown_text(cand.paradigm_type if cand else 'N/A')}`",
            f"- **Hypothesis:** {_markdown_text(cand.hypothesis if cand else 'N/A')}",
            f"- **Feasibility:** {cand.feasibility_score if cand else 0.0:.2f} | **Divergence:** {cand.divergence_score if cand else 0.0:.2f}",
            "",
            "## 3. Strategy Coverage & Restricted Execution Telemetry",
            f"- **Coverage Verdict:** `{_markdown_text(verification_text)}` (Coverage fraction: {_markdown_text(confidence_text)})",
            f"- **Scope:** `{_markdown_text(verification_scope)}`",
            f"- **Rationale:** {_markdown_text(ver.rationale if ver else 'No coverage evaluation available.')}",
            "",
            "## 4. Empirical Falsification (H0)",
            f"- **Null Hypothesis:** `{_markdown_text(h0_text)}`",
            f"- **H0 Evaluation Status:** `{_markdown_text(h0_status)}`",
            f"- **Scientific Status:** `{_markdown_text(scientific_status)}`",
            "",
            "## 5. Checkpoints Timeline",
        ]
    )
    for chk in posture.checkpoints:
        md_lines.append(
            f"- **[{_markdown_text(chk.stage.value)}]** `{_markdown_text(chk.actor)}`: "
            f"{_markdown_text(chk.title)} — *{_markdown_text(chk.evidence_summary)}*"
        )

    return {
        "status": "success",
        "project_id": project_id,
        "markdown_dossier": "\n".join(md_lines),
    }


@app.get("/api/v1/export/dossier/html/{project_id}", response_class=HTMLResponse, tags=["Export"])
def export_html_dossier_route(project_id: str) -> HTMLResponse:
    """Export a self-contained HTML specification with embedded SVG architecture."""
    try:
        validate_project_id(project_id)
        posture = state_manager.get_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project ID.") from exc
    if not posture:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    html_content = export_full_html_dossier(posture)
    return HTMLResponse(html_content)
