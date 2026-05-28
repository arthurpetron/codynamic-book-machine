"""Deterministic authoring-agent workflows for canonical book projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from scripts.book.authoring import AuthoringLoop, EditProposal
from scripts.book.repository import BookRepository
from scripts.book.typesetting import CompileResult, LatexBuildService


AGENT_IDS = {
    "hypervisor": "hypervisor_agent",
    "section": "section_agent",
    "gardener": "gardener_agent",
    "diagram": "diagram_agent",
    "document_design": "document_design_agent",
}


@dataclass(frozen=True)
class SectionGraphNode:
    """One section in the contextual dependency/blocker graph."""

    section_id: str
    title: str
    parent_id: str | None
    dependencies: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    status: str = "ready"


class AgentCommitLog:
    """Append-only log of agent-authored checkpoints and proposal diffs."""

    def __init__(self, book_root: Path | str):
        self.path = Path(book_root) / "logs" / "agent_commit_log.jsonl"

    def record(
        self,
        agent_id: str,
        action: str,
        subject: str,
        rationale: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "checkpoint_id": f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "agent_id": agent_id,
            "action": action,
            "subject": subject,
            "rationale": rationale,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]


class AgentRuntimeRegistry:
    """Book-local runtime state for spawned authoring agents."""

    def __init__(self, repository: BookRepository):
        self.repository = repository
        self.path = repository.book_root / "logs" / "agent_runtime.json"
        self.loop = AuthoringLoop(repository.book_root)

    def spawn(self, agent_id: str, role: str, section_id: str | None = None) -> dict[str, Any]:
        state = self._load()
        record = state.setdefault(agent_id, {})
        record.update({
            "agent_id": agent_id,
            "role": role,
            "section_id": section_id,
            "status": "spawned",
            "spawned_at": record.get("spawned_at") or datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })
        self._save(state)
        self.loop.history.record_event(
            event_type="agent_spawned",
            agent_id=AGENT_IDS["hypervisor"],
            subject=agent_id,
            status="warn",
            rationale=f"Spawned {role} agent.",
            metadata=record,
        )
        return record

    def start(self, agent_id: str) -> dict[str, Any]:
        record = self._ensure(agent_id)
        record["status"] = "running"
        record["started_at"] = datetime.now().isoformat()
        record["updated_at"] = record["started_at"]
        self._write_record(agent_id, record)
        self.loop.history.record_event(
            event_type="agent_started",
            agent_id=AGENT_IDS["hypervisor"],
            subject=agent_id,
            status="warn",
            rationale=f"Started {agent_id}.",
            metadata=record,
        )
        return record

    def stop(self, agent_id: str, reason: str = "") -> dict[str, Any]:
        record = self._ensure(agent_id)
        record["status"] = "stopped"
        record["stopped_at"] = datetime.now().isoformat()
        record["updated_at"] = record["stopped_at"]
        if reason:
            record["stop_reason"] = reason
        self._write_record(agent_id, record)
        self.loop.history.record_event(
            event_type="agent_stopped",
            agent_id=AGENT_IDS["hypervisor"],
            subject=agent_id,
            status="warn",
            rationale=reason or f"Stopped {agent_id}.",
            metadata=record,
        )
        return record

    def list(self) -> dict[str, Any]:
        return self._load()

    def _ensure(self, agent_id: str) -> dict[str, Any]:
        state = self._load()
        if agent_id not in state:
            raise KeyError(f"Agent has not been spawned: {agent_id}")
        return state[agent_id]

    def _write_record(self, agent_id: str, record: dict[str, Any]) -> None:
        state = self._load()
        state[agent_id] = record
        self._save(state)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


class AuthoringAgentWorkflow:
    """Coordinate hypervisor, section, gardener, diagram, and design agents."""

    def __init__(
        self,
        book_root: Path | str,
        mode: str = "proposal",
        project_root: Path | str = Path("."),
    ):
        self.repository = BookRepository(Path(book_root))
        self.book_root = self.repository.book_root
        self.mode = mode
        self.project_root = Path(project_root)
        self.loop = AuthoringLoop(self.book_root, mode=mode)
        self.runtime = AgentRuntimeRegistry(self.repository)
        self.commit_log = AgentCommitLog(self.book_root)

    def dependency_graph(self) -> dict[str, Any]:
        """Build the hypervisor's contextual dependency and blocker graph."""
        service = self.repository.outline_service()
        raw_nodes = list(service._walk_raw(service.work.get("structure", [])))
        node_lookup = {node.get("id"): node for node, _, _ in raw_nodes}
        parent_lookup = {node.get("id"): parent_id for node, _, parent_id in raw_nodes}
        leaf_ids = [
            node["id"]
            for node, _, _ in raw_nodes
            if node.get("id") and not (node.get("content") or [])
        ]
        pending_targets = {
            proposal.target_path
            for proposal in self.loop.proposals.list(status="pending")
        }
        failed_subjects = {
            event["subject"]
            for event in self.loop.history.load()
            if event.get("status") in {"fail", "warn"}
            and event.get("event_type") in {"verification_check", "section_compile", "book_compile"}
        }
        media_blockers = {
            request["section_id"]
            for request in self.loop.media.load_requests()
            if request.get("status") == "pending"
        }

        graph_nodes = []
        edges = []
        for section_id in leaf_ids:
            node = node_lookup[section_id]
            dependencies = self._dependency_ids(node)
            blockers = []
            for dep_id in dependencies:
                edges.append({"from": dep_id, "to": section_id, "type": "structural"})
                if dep_id not in node_lookup:
                    blockers.append(f"Missing dependency: {dep_id}")
                elif dep_id in failed_subjects:
                    blockers.append(f"Dependency needs verification: {dep_id}")

            content = self.repository.load_section(section_id).strip()
            if not content:
                blockers.append("No section payload yet.")
            content_file = node.get("content_file") or f"content/sections/{section_id}.tex"
            if content_file in pending_targets:
                blockers.append("Pending proposal requires user review.")
            if section_id in media_blockers:
                blockers.append("Pending media request.")
            if section_id in failed_subjects:
                blockers.append("Recent verification warning or failure.")

            graph_nodes.append(SectionGraphNode(
                section_id=section_id,
                title=node.get("title", section_id),
                parent_id=parent_lookup.get(section_id),
                dependencies=dependencies,
                blockers=blockers,
                status="blocked" if blockers else "ready",
            ))

        payload = {
            "generated_at": datetime.now().isoformat(),
            "nodes": [asdict(node) for node in graph_nodes],
            "edges": edges,
            "ready": [node.section_id for node in graph_nodes if node.status == "ready"],
            "blocked": [node.section_id for node in graph_nodes if node.status == "blocked"],
        }
        self.commit_log.record(
            AGENT_IDS["hypervisor"],
            "dependency_graph",
            "book",
            "Built contextual dependency and blocker graph.",
            payload,
        )
        return payload

    def spawn_agents(self, section_ids: list[str] | None = None) -> dict[str, Any]:
        """Spawn the canonical long-lived agents and selected section agents."""
        section_ids = section_ids or self.dependency_graph()["ready"]
        records = {
            "hypervisor": self.runtime.spawn(AGENT_IDS["hypervisor"], "hypervisor"),
            "gardener": self.runtime.spawn(AGENT_IDS["gardener"], "gardener"),
            "diagram": self.runtime.spawn(AGENT_IDS["diagram"], "diagram"),
            "document_design": self.runtime.spawn(AGENT_IDS["document_design"], "document_design"),
        }
        for section_id in section_ids:
            agent_id = f"{AGENT_IDS['section']}__{section_id}"
            records[agent_id] = self.runtime.spawn(agent_id, "section", section_id=section_id)
        return records

    def start_agent(self, agent_id: str) -> dict[str, Any]:
        return self.runtime.start(agent_id)

    def stop_agent(self, agent_id: str, reason: str = "") -> dict[str, Any]:
        return self.runtime.stop(agent_id, reason=reason)

    def summarize_drift(self) -> dict[str, Any]:
        """Summarize global drift from verification history."""
        events = self.loop.history.load()
        relevant = [
            event for event in events
            if event.get("event_type") in {
                "verification_check",
                "section_compile",
                "book_compile",
                "document_design_review",
                "global_drift_check",
            }
        ]
        failures = [event for event in relevant if event.get("status") == "fail"]
        warnings = [event for event in relevant if event.get("status") == "warn"]
        status = "fail" if failures else "warn" if warnings else "pass"
        rationale = self._drift_rationale(failures, warnings, relevant)
        event = self.loop.record_hypervisor_drift(
            subject="book",
            status=status,
            rationale=rationale,
            metadata={
                "event_count": len(relevant),
                "failure_count": len(failures),
                "warning_count": len(warnings),
                "recent_subjects": [event["subject"] for event in relevant[-5:]],
            },
        )
        return {"status": status, "rationale": rationale, "event": event}

    def draft_section(self, section_id: str) -> EditProposal:
        """Have the section agent draft a TeX payload proposal for a section."""
        service = self.repository.outline_service()
        node = service.get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")
        graph = self.dependency_graph()
        graph_node = next((item for item in graph["nodes"] if item["section_id"] == section_id), {})
        content = self._section_tex(node, graph_node)
        target = Path("content") / "sections" / f"{section_id}.tex"
        proposal = self.loop.proposals.propose_file_edit(
            agent_id=f"{AGENT_IDS['section']}__{section_id}",
            target_path=target,
            proposed_content=content,
            rationale=f"Drafted TeX payload for {node.get('title', section_id)}.",
            metadata={
                "section_id": section_id,
                "kind": "section_tex_draft",
                "dependency_graph": graph_node,
                "content_file_update": str(target),
            },
            mode=self.mode,
        )
        self.commit_log.record(
            proposal.agent_id,
            "draft_section",
            section_id,
            proposal.rationale,
            {
                "proposal_id": proposal.proposal_id,
                "target_path": proposal.target_path,
                "diff": proposal.diff,
                "status": proposal.status,
            },
        )
        self.loop.history.record_event(
            event_type="section_drafted",
            agent_id=proposal.agent_id,
            subject=section_id,
            status="warn",
            rationale=proposal.rationale,
            metadata={"proposal_id": proposal.proposal_id, "target_path": proposal.target_path},
        )
        return proposal

    def run_gardener_checks(self, section_id: str) -> dict[str, Any]:
        """Run real section checks and append verification history."""
        node = self.repository.outline_service().get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")
        content = self.repository.load_section(section_id)
        known_ids = {item.id for item in self.repository.outline_service().tree()}
        dependencies = self._dependency_ids(node)
        missing_dependencies = [dep_id for dep_id in dependencies if dep_id not in known_ids]
        compile_result = LatexBuildService(self.book_root, project_root=self.project_root).compile_section(section_id)
        checks = {
            "intent": "pass" if (node.get("goal") or node.get("summary")) else "warn",
            "dependencies": "fail" if missing_dependencies else "pass",
            "claim_clarity": self._claim_clarity_status(content),
            "latex": "pass" if compile_result.status == "passed" else "fail",
        }
        rationale = self._gardener_rationale(checks, missing_dependencies, compile_result)
        event = self.loop.record_gardener_check(
            section_id=section_id,
            intent=checks["intent"],
            dependencies=checks["dependencies"],
            claim_clarity=checks["claim_clarity"],
            latex=checks["latex"],
            rationale=rationale,
        )
        event["metadata"].update({
            "compile": compile_result.as_dict(),
            "missing_dependencies": missing_dependencies,
        })
        self._rewrite_history_event(event)
        self.commit_log.record(
            AGENT_IDS["gardener"],
            "run_checks",
            section_id,
            rationale,
            {"event_id": event["event_id"], "checks": checks},
        )
        return event

    def fulfill_media_requests(self) -> list[dict[str, Any]]:
        """Have the single diagram agent fulfill pending media requests."""
        fulfilled = []
        for request in self.loop.media.load_requests():
            if request.get("status") != "pending":
                continue
            extension = self._media_extension(request.get("media_type", "tikz"))
            content = self._media_content(request, extension)
            result = self.loop.media.fulfill_request(
                request_id=request["request_id"],
                diagram_agent=AGENT_IDS["diagram"],
                content=content,
                extension=extension,
            )
            self.loop.history.record_event(
                event_type="media_fulfilled",
                agent_id=AGENT_IDS["diagram"],
                subject=request["section_id"],
                status="pass",
                rationale=f"Fulfilled media request {request['request_id']}.",
                metadata=result,
            )
            self.commit_log.record(
                AGENT_IDS["diagram"],
                "fulfill_media",
                request["section_id"],
                request.get("description", ""),
                {"request_id": request["request_id"], "path": result["path"]},
            )
            fulfilled.append(result)
        return fulfilled

    def review_document_design(self, compile_result: dict[str, Any] | CompileResult | None = None) -> dict[str, Any]:
        """Inspect compile results and propose class/style fixes when needed."""
        if isinstance(compile_result, CompileResult):
            result = compile_result.as_dict()
        elif compile_result is None:
            result = self._latest_compile_result()
        else:
            result = compile_result

        errors = result.get("errors") or []
        if result.get("status") == "passed" and not errors:
            event = self.loop.history.record_event(
                event_type="document_design_review",
                agent_id=AGENT_IDS["document_design"],
                subject="document",
                status="pass",
                rationale="Compiled PDF is available and no LaTeX errors were reported.",
                metadata={"compile": result},
            )
            return {"status": "pass", "event": event, "proposal": None}

        proposed = self._style_fix_content(result)
        proposal = self.loop.proposals.propose_file_edit(
            agent_id=AGENT_IDS["document_design"],
            target_path=Path("style") / "document_design_fixes.tex",
            proposed_content=proposed,
            rationale="Proposed class/style fixes after compile inspection.",
            metadata={"compile": result, "kind": "document_design_fix"},
            mode=self.mode,
        )
        event = self.loop.history.record_event(
            event_type="document_design_review",
            agent_id=AGENT_IDS["document_design"],
            subject="document",
            status="fail",
            rationale="Compile output needs document design or class/style attention.",
            metadata={"proposal_id": proposal.proposal_id, "compile": result},
        )
        self.commit_log.record(
            AGENT_IDS["document_design"],
            "review_compile",
            "document",
            "Proposed class/style fixes after compile inspection.",
            {"proposal_id": proposal.proposal_id, "errors": errors},
        )
        return {"status": "fail", "event": event, "proposal": proposal.__dict__}

    def _dependency_ids(self, node: dict[str, Any]) -> list[str]:
        ids = []
        for dep in node.get("dependencies", {}).get("structural", []) or []:
            dep_id = dep.get("section_id") or dep.get("id") or dep.get("target")
            if dep_id:
                ids.append(dep_id)
        for prereq in node.get("prerequisites", []) or []:
            if isinstance(prereq, str):
                ids.append(prereq)
            elif isinstance(prereq, dict):
                dep_id = prereq.get("section_id") or prereq.get("id")
                if dep_id:
                    ids.append(dep_id)
        return list(dict.fromkeys(ids))

    def _section_tex(self, node: dict[str, Any], graph_node: dict[str, Any]) -> str:
        title = node.get("title", "Untitled section")
        summary = node.get("summary") or "This section needs a focused draft."
        goal = node.get("goal") or "Clarify the section's intent for the reader."
        dependencies = graph_node.get("dependencies") or []
        dependency_text = ", ".join(dependencies) if dependencies else "none"
        return (
            f"% Agent draft for {node.get('id')}\n"
            f"% Dependencies: {dependency_text}\n\n"
            f"\\section{{{self._escape_tex(title)}}}\n\n"
            f"{self._escape_tex(summary)}\n\n"
            f"\\paragraph{{Intent.}}\n"
            f"{self._escape_tex(goal)}\n\n"
            "\\paragraph{Draft notes.}\n"
            "TODO: Replace this scaffold with the authored argument, examples, citations, "
            "and any requested diagrams after user review.\n"
        )

    def _claim_clarity_status(self, content: str) -> str:
        stripped = content.strip()
        if not stripped or "TODO" in stripped:
            return "warn"
        return "pass" if len(stripped.split()) >= 30 else "warn"

    def _gardener_rationale(
        self,
        checks: dict[str, str],
        missing_dependencies: list[str],
        compile_result: CompileResult,
    ) -> str:
        issues = []
        if checks["intent"] != "pass":
            issues.append("intent is underspecified")
        if missing_dependencies:
            issues.append(f"missing dependencies: {', '.join(missing_dependencies)}")
        if checks["claim_clarity"] != "pass":
            issues.append("claim clarity needs expansion")
        if checks["latex"] != "pass":
            issues.append("LaTeX compile failed")
        if not issues:
            return "Gardener checks passed for intent, dependencies, claims, and LaTeX."
        detail = "; ".join(issues)
        if compile_result.errors:
            detail += f"; first LaTeX error: {compile_result.errors[0]}"
        return detail

    def _media_extension(self, media_type: str) -> str:
        if media_type == "svg":
            return ".svg"
        if media_type in {"tikz", "diagram"}:
            return ".tikz"
        return ".txt"

    def _media_content(self, request: dict[str, Any], extension: str) -> str:
        description = request.get("description", "Requested media")
        if extension == ".svg":
            return (
                "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"640\" height=\"240\" viewBox=\"0 0 640 240\">\n"
                "  <rect width=\"640\" height=\"240\" fill=\"#f8faf8\"/>\n"
                "  <circle cx=\"180\" cy=\"120\" r=\"46\" fill=\"#0f766e\"/>\n"
                "  <circle cx=\"460\" cy=\"120\" r=\"46\" fill=\"#d9a441\"/>\n"
                "  <path d=\"M230 120h180\" stroke=\"#1f2a27\" stroke-width=\"6\" marker-end=\"url(#arrow)\"/>\n"
                "  <defs><marker id=\"arrow\" markerWidth=\"10\" markerHeight=\"10\" refX=\"8\" refY=\"3\" orient=\"auto\"><path d=\"M0,0 L0,6 L9,3 z\" fill=\"#1f2a27\"/></marker></defs>\n"
                f"  <text x=\"320\" y=\"210\" text-anchor=\"middle\" font-family=\"serif\" font-size=\"20\">{self._escape_xml(description)}</text>\n"
                "</svg>\n"
            )
        if extension == ".tikz":
            return (
                "\\begin{tikzpicture}[node distance=3cm,>=stealth]\n"
                "\\node[draw, rounded corners] (a) {Context};\n"
                "\\node[draw, rounded corners, right of=a] (b) {Section};\n"
                "\\draw[->] (a) -- node[above] {request} (b);\n"
                f"\\node[below=1cm of a, text width=8cm] {{{self._escape_tex(description)}}};\n"
                "\\end{tikzpicture}\n"
            )
        return f"{description}\n"

    def _latest_compile_result(self) -> dict[str, Any]:
        log_dir = self.book_root / "build" / "logs"
        logs = sorted(log_dir.glob("*.log")) if log_dir.exists() else []
        for path in reversed(logs):
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
        return {
            "status": "failed",
            "errors": ["No compile result was available for document design review."],
            "log_path": None,
            "pdf_path": None,
        }

    def _style_fix_content(self, result: dict[str, Any]) -> str:
        errors = result.get("errors") or ["No compile result was available."]
        lines = [
            "% Proposed by document_design_agent.",
            "% Review before including from the document preamble or class file.",
            "",
        ]
        error_blob = "\n".join(errors)
        if "Undefined control sequence" in error_blob:
            lines.append("% Undefined commands detected: add package imports or define missing macros here.")
        if "LaTeX Error: File" in error_blob or "not found" in error_blob:
            lines.append("% Missing class/package detected: verify TEXINPUTS and document style selection.")
        if "No LaTeX compiler" in error_blob:
            lines.append("% Install latexmk/xelatex or configure the app compiler path before retrying.")
        lines.append("% Latest errors:")
        lines.extend(f"% - {error}" for error in errors[:10])
        return "\n".join(lines) + "\n"

    def _drift_rationale(
        self,
        failures: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        relevant: list[dict[str, Any]],
    ) -> str:
        if failures:
            subjects = ", ".join(sorted({event["subject"] for event in failures})[:5])
            return f"Blocking drift remains in {subjects}."
        if warnings:
            subjects = ", ".join(sorted({event["subject"] for event in warnings})[:5])
            return f"Non-blocking drift or user review remains in {subjects}."
        if not relevant:
            return "No verification history exists yet."
        return "No current drift detected from verification history."

    def _rewrite_history_event(self, updated_event: dict[str, Any]) -> None:
        events = self.loop.history.load()
        for index, event in enumerate(events):
            if event["event_id"] == updated_event["event_id"]:
                events[index] = updated_event
                break
        self.loop.history.path.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in events)
        )

    def _escape_tex(self, value: str) -> str:
        replacements = {
            "\\": "\\textbackslash{}",
            "&": "\\&",
            "%": "\\%",
            "$": "\\$",
            "#": "\\#",
            "_": "\\_",
            "{": "\\{",
            "}": "\\}",
        }
        return "".join(replacements.get(char, char) for char in str(value))

    def _escape_xml(self, value: str) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
