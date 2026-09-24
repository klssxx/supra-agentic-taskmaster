"""Native Model Context Protocol (MCP) JSON-RPC 2.0 Handler for SUPRA Agentic Taskmaster.

Exposes standard MCP tools, resources, and prompts over HTTP JSON-RPC 2.0:
  - Tools: supra_decompose, supra_synthesize, supra_verify,
    supra_restricted_execution, supra_secure_sandbox, supra_quick_run
  - Resources: supra://schema/invariants, supra://state/active-projects
  - Prompts: prompt_taskmaster_challenge, prompt_falsification_audit
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from .runner import taskmaster_runner
from .state import state_manager, validate_project_id
from .tools import (
    MAX_FUZZ_ITERATIONS,
    decompose_objective,
    restricted_python_executor,
    secure_sandbox_executor,
    synthesize_strategy,
    verify_solution,
)

logger = logging.getLogger("supra_agentic.mcp_handler")

MCP_TOOLS_MANIFEST = [
    {
        "name": "supra_quick_run",
        "description": (
            "Execute the gated Taskmaster workflow; completion is reported only "
            "when verification, restricted preflight, and the identity-bound "
            "Docker isolation-smoke gate pass."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "The challenge or problem to solve.",
                },
                "domain": {"type": "string", "default": "general"},
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
    },
    {
        "name": "supra_decompose",
        "description": "Deconstruct an objective into core system invariants and mutable assumptions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "objective": {"type": "string"},
                "domain": {"type": "string", "default": "general"},
            },
            "required": ["project_id", "objective"],
            "additionalProperties": False,
        },
    },
    {
        "name": "supra_synthesize",
        "description": "Synthesize multi-paradigm strategy candidates (Conservative, Orthogonal, Disruptive).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "pathways_count": {"type": "integer", "default": 3},
                "allow_disruptive": {"type": "boolean", "default": True},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "supra_verify",
        "description": "Evaluate supported textual invariant-coverage checks for the persisted selected strategy; this is not scientific validation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "supra_restricted_execution",
        "description": (
            "Run SUPRA's fixed trusted internal Python check. "
            "This is in-process restricted execution, not a security sandbox; "
            "remote Python source is not accepted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "fuzz_iterations": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": MAX_FUZZ_ITERATIONS,
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "supra_secure_sandbox",
        "description": (
            "Run SUPRA's fixed identity-bound isolation smoke in the configured "
            "fail-closed Docker sandbox. It does not execute the selected candidate "
            "mechanism/action plan/hypothesis, and no remote source code is accepted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        },
    },
]

_TOOL_ALLOWED_FIELDS: dict[str, set[str]] = {
    "supra_quick_run": {"objective", "domain"},
    "supra_decompose": {"project_id", "objective", "domain"},
    "supra_synthesize": {"project_id", "pathways_count", "allow_disruptive"},
    "supra_verify": {"project_id"},
    "supra_restricted_execution": {"project_id", "fuzz_iterations"},
    "supra_secure_sandbox": {"project_id"},
}
_TOOL_REQUIRED_FIELDS: dict[str, set[str]] = {
    "supra_quick_run": {"objective"},
    "supra_decompose": {"project_id", "objective"},
    "supra_synthesize": {"project_id"},
    "supra_verify": {"project_id"},
    "supra_restricted_execution": {"project_id"},
    "supra_secure_sandbox": {"project_id"},
}


def _validate_tool_arguments(tool_name: str, args: Mapping[str, Any]) -> str | None:
    """Return a stable invalid-params message before dispatching a public tool."""
    allowed = _TOOL_ALLOWED_FIELDS.get(tool_name)
    if allowed is None:
        return None

    unexpected = sorted(str(key) for key in args if key not in allowed)
    if unexpected:
        return f"Invalid params: unsupported fields {unexpected}"

    missing = sorted(field for field in _TOOL_REQUIRED_FIELDS[tool_name] if field not in args)
    if missing:
        return f"Invalid params: missing required fields {missing}"

    for field in ("objective", "domain"):
        if field not in args:
            continue
        value = args[field]
        if not isinstance(value, str) or (field == "objective" and not value.strip()):
            qualifier = "non-empty " if field == "objective" else ""
            return f"Invalid params: {field} must be a {qualifier}string"

    if "project_id" in args:
        try:
            validate_project_id(args["project_id"])
        except (TypeError, ValueError):
            return "Invalid params: project_id has an invalid format"

    if "pathways_count" in args:
        pathways_count = args["pathways_count"]
        if (
            isinstance(pathways_count, bool)
            or not isinstance(pathways_count, int)
            or not 1 <= pathways_count <= 100
        ):
            return "Invalid params: pathways_count must be an integer between 1 and 100"

    if "allow_disruptive" in args and not isinstance(args["allow_disruptive"], bool):
        return "Invalid params: allow_disruptive must be a boolean"

    if "fuzz_iterations" in args:
        iterations = args["fuzz_iterations"]
        if (
            isinstance(iterations, bool)
            or not isinstance(iterations, int)
            or not 1 <= iterations <= MAX_FUZZ_ITERATIONS
        ):
            return (
                "Invalid params: fuzz_iterations must be an integer "
                f"between 1 and {MAX_FUZZ_ITERATIONS}"
            )
    return None


MCP_RESOURCES_MANIFEST = [
    {
        "uri": "supra://schema/invariants",
        "name": "Taskmaster System Invariants Schema",
        "mimeType": "application/json",
        "description": "Standard system invariant definitions and boundaries.",
    },
    {
        "uri": "supra://state/active-projects",
        "name": "Active Taskmaster Projects State",
        "mimeType": "application/json",
        "description": "In-memory snapshot of current project lifecycles.",
    },
]

MCP_PROMPTS_MANIFEST = [
    {
        "name": "prompt_taskmaster_challenge",
        "description": "Deconstruct an engineering challenge into formal invariants and orthogonal pathways.",
        "arguments": [
            {"name": "objective", "description": "Target engineering challenge", "required": True},
        ],
    },
    {
        "name": "prompt_falsification_audit",
        "description": "Review a project with scoped invariant-coverage and counterfactual-inspired prompts; no full Pearl causal-inference implementation is claimed.",
        "arguments": [
            {"name": "project_id", "description": "Project ID to audit", "required": True},
        ],
    },
]


def handle_mcp_jsonrpc_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Process an MCP JSON-RPC 2.0 request and return a compliant response."""
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    if not isinstance(method, str):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32600, "message": "Invalid Request: 'method' must be a string"},
        }
    if not isinstance(params, Mapping):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32602,
                "message": "Invalid params: params must be an object",
            },
        }

    try:
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "supra-agentic-taskmaster", "version": "1.0.0"},
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": MCP_TOOLS_MANIFEST},
            }

        if method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": MCP_RESOURCES_MANIFEST},
            }

        if method == "resources/read":
            uri = params.get("uri")
            if uri == "supra://schema/invariants":
                content = json.dumps(
                    {
                        "invariants": [
                            "System integrity",
                            "Memory boundary containment",
                            "Explicit trust-boundary checks",
                        ]
                    },
                    indent=2,
                )
            elif uri == "supra://state/active-projects":
                projects = [p.model_dump() for p in state_manager.list_projects(limit=10)]
                content = json.dumps(
                    {"active_count": len(projects), "projects": projects}, indent=2
                )
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Invalid params: unknown resource URI"},
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [{"uri": uri, "mimeType": "application/json", "text": content}]
                },
            }

        if method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"prompts": MCP_PROMPTS_MANIFEST},
            }

        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            if not isinstance(tool_name, str):
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params: tool name must be a string",
                    },
                }
            if not isinstance(args, Mapping):
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params: arguments must be an object",
                    },
                }
            invalid_arguments = _validate_tool_arguments(tool_name, args)
            if invalid_arguments is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": invalid_arguments},
                }

            if tool_name == "supra_quick_run":
                posture = taskmaster_runner.run_golden_path(
                    objective=args["objective"],
                    domain=args.get("domain", "general"),
                )
                res = {
                    "status": "success" if posture.stage.value == "COMPLETED" else "blocked",
                    "completion_status": (
                        "COMPLETED" if posture.stage.value == "COMPLETED" else "BLOCKED"
                    ),
                    "workflow_status": posture.stage.value,
                    "verification_status": (
                        posture.verification.verdict
                        if posture.verification is not None
                        else "NOT_EVALUATED"
                    ),
                    "secure_sandbox_status": (
                        "IDENTITY_BOUND_ISOLATION_PASS"
                        if posture.secure_sandbox_results
                        and posture.secure_sandbox_results[-1].passed
                        and posture.secure_sandbox_results[-1].identity_bound
                        and posture.secure_sandbox_results[-1].isolation_verified
                        else "IDENTITY_BOUND_ISOLATION_FAIL"
                        if posture.secure_sandbox_results
                        and posture.secure_sandbox_results[-1].identity_bound
                        and posture.secure_sandbox_results[-1].isolation_verified
                        else "UNVERIFIED_ISOLATION"
                        if posture.secure_sandbox_results
                        else "NOT_RUN"
                    ),
                    "secure_sandbox_execution_scope": (
                        posture.secure_sandbox_results[-1].execution_scope
                        if posture.secure_sandbox_results
                        else "NOT_RUN"
                    ),
                    "candidate_mechanism_executed_in_secure_sandbox": bool(
                        posture.secure_sandbox_results
                        and posture.secure_sandbox_results[-1].candidate_mechanism_executed
                    ),
                    "posture": posture.model_dump(),
                }
            elif tool_name == "supra_decompose":
                res = decompose_objective(
                    args["project_id"], args["objective"], args.get("domain", "general")
                )
            elif tool_name == "supra_synthesize":
                res = synthesize_strategy(
                    args["project_id"],
                    args.get("pathways_count", 3),
                    args.get("allow_disruptive", True),
                )
            elif tool_name == "supra_verify":
                res = verify_solution(args["project_id"])
            elif tool_name == "supra_restricted_execution":
                iterations = args.get("fuzz_iterations", 5)
                assert isinstance(iterations, int) and not isinstance(iterations, bool)
                res = restricted_python_executor(args["project_id"], fuzz_iterations=iterations)
            elif tool_name == "supra_secure_sandbox":
                res = secure_sandbox_executor(args["project_id"])
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": "Method not found: unknown tool"},
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}
                    ],
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": "Method not found"},
        }

    except KeyError:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": "Invalid params: missing required field"},
        }
    except Exception as exc:
        logger.error("Unhandled MCP error (%s)", type(exc).__name__)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32603, "message": "Internal server error"},
        }
