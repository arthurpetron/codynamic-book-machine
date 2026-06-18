"""Desktop app state projection for the Electron UI."""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

import yaml

from scripts.api import get_provider_with_fallback
from scripts.book.authoring import AuthoringLoop, VerificationHistory
from scripts.book.repository import BookRepository
from scripts.book.typesetting import DesignSettingsService, DocumentStyleRegistry, LatexBuildService


class BookAppState:
    """Project canonical book data into a compact UI state payload."""

    def __init__(self, book_root: Path | str, data_root: Path | str = Path("data")):
        self.book_root = Path(book_root).resolve()
        self.data_root = Path(data_root).resolve()
        self.repository = BookRepository(self.book_root)

    def snapshot(self, selected_id: str | None = None) -> dict[str, Any]:
        book = self.repository.load_book()
        work = book["work"]
        outline = self._outline(work.get("structure", []))
        selected = self._valid_selected_id(selected_id, outline)
        return {
            "bookRoot": str(self.book_root),
            "book": {
                "id": work.get("id"),
                "title": work.get("title"),
                "summary": work.get("summary", ""),
            },
            "outline": outline,
            "selectedId": selected,
            "selectedSection": self.section_payload(selected) if selected else None,
            "design": DesignSettingsService(self.repository).get(),
            "styles": [style.__dict__ for style in DocumentStyleRegistry(Path(".")).list_styles()],
            "messages": self._messages(),
            "agentStatus": self._agent_status(),
            "artifacts": [artifact.__dict__ for artifact in self.repository.artifacts.discover()],
            "proposals": [proposal.__dict__ for proposal in self.repository.proposals.list()],
            "references": self._references(work),
            "knowledgeGraph": self.repository.knowledge_graph().analyze().as_dict(),
            "compile": self._latest_compile(),
            "verification": self._verification_events(),
        }

    def section_payload(self, section_id: str) -> dict[str, Any]:
        node = self.repository.outline_service().get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")
        content = self._unwrap_latex_payload(self.repository.load_latex_section(section_id))
        if not content.strip():
            content = self._fallback_section_content(node)
        return {
            "id": section_id,
            "title": node.get("title", section_id),
            "number": node.get("number", ""),
            "type": node.get("type", "section"),
            "source": content,
            "summary": node.get("summary", ""),
            "contentFile": node.get("content_file"),
            "latexFile": f"tex/section_payloads/{section_id}.tex",
            "score": self._score_for(section_id),
            "tone": self._tone_for(section_id),
            "agent": self._agent_label(section_id),
        }

    def save_section(self, section_id: str, content: str) -> dict[str, Any]:
        path = self.repository.save_latex_section(section_id, content)
        AuthoringLoop(self.book_root).history.record_event(
            event_type="section_saved",
            agent_id="desktop_app",
            subject=section_id,
            status="pass",
            rationale=f"Section saved to {path.relative_to(self.book_root)}",
        )
        return self.section_payload(section_id)

    def start_section_agent(self, section_id: str, task_context: dict[str, Any] | None = None) -> dict[str, Any]:
        from scripts.book.agent_workflow import AGENT_IDS, AuthoringAgentWorkflow

        node = self.repository.outline_service().get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")
        workflow = AuthoringAgentWorkflow(self.book_root, project_root=Path("."))
        workflow.supervise_agents(section_ids=[section_id], queue_work=False)
        agent_id = f"{AGENT_IDS['section']}__{section_id}"
        task = workflow.queue_agent_task(
            agent_id,
            "plan_section_work",
            {
                "section_id": section_id,
                "trigger": "manual_start_agent_button",
                "instruction": (
                    "Review the full document, this section, and the outline. "
                    "Send yourself a structured action plan message so the plan enters your task queue."
                ),
                **(task_context or {}),
            },
            priority=5,
        )
        result = workflow.run_agent_task(agent_id)
        event = AuthoringLoop(self.book_root).history.record_event(
            event_type="section_agent_planned",
            agent_id=agent_id,
            subject=section_id,
            status="pass",
            rationale="Section agent reviewed context and sent itself an action plan.",
            metadata={
                "task": result.get("task"),
                "result": result.get("result"),
            },
        )
        return {
            "event": event,
            "section": self.section_payload(section_id),
            "planning_task": task,
            "planning_result": result,
        }

    def _run_section_latex_pass(self, section_id: str, task_context: dict[str, Any] | None = None) -> dict[str, Any]:
        book = self.repository.load_book()
        node = self.repository.outline_service().get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")

        source_markdown = self.repository.load_section(section_id)
        existing_latex = self.repository.load_latex_section(section_id)
        sibling_context = self._sibling_context(book["work"].get("structure", []), section_id)
        prompt = self._section_agent_prompt(book, node, source_markdown, existing_latex, sibling_context, task_context or {})
        provider = get_provider_with_fallback(["openai", "anthropic"])
        response = provider.simple_prompt(
            prompt,
            system_prompt=self._section_agent_system_prompt(),
            temperature=0.2,
            max_tokens=4000,
        )
        agent_output = self._extract_section_agent_response(response.content)
        latex = agent_output["latex"]
        path = self.repository.save_latex_section(section_id, latex)
        event = AuthoringLoop(self.book_root).history.record_event(
            event_type="section_agent_started",
            agent_id=f"section_agent__{section_id}",
            subject=section_id,
            status="pass",
            rationale=f"Generated initial LaTeX draft at {path.relative_to(self.book_root)}.",
            metadata={
                "model": response.model,
                "provider": response.provider,
                "completeness_percent": agent_output["completeness_percent"],
                "completeness_rationale": agent_output.get("completeness_rationale", ""),
            },
        )
        return {
            "event": event,
            "section": self.section_payload(section_id),
            "output_path": str(path),
        }

    def run_hypervisor_once(
        self,
        exclude_section_ids: list[str] | None = None,
        include_section_ids: list[str] | None = None,
        phase: str = "draft",
    ) -> dict[str, Any]:
        """Select the next section needing work and run one section-agent pass."""
        urgent = self._run_urgent_hypervisor_task()
        if urgent:
            return urgent
        heartbeat = self._run_gardener_heartbeat_task()
        excluded = set(exclude_section_ids or [])
        included = set(include_section_ids or [])
        book = self.repository.load_book()
        candidates = [
            candidate
            for candidate in self._section_candidates(book["work"].get("structure", []))
            if candidate["id"] not in excluded
            and (not included or candidate["id"] in included)
        ]
        if not candidates:
            event = AuthoringLoop(self.book_root).history.record_event(
                event_type="hypervisor_idle",
                agent_id="hypervisor_agent",
                subject="book",
                status="pass",
                rationale="No remaining sections are available for this hypervisor run.",
                metadata={
                    "phase": phase,
                    "excluded_section_ids": sorted(excluded),
                    "include_section_ids": sorted(included),
                },
            )
            return {
                "event": event,
                "targetSectionId": None,
                "sectionAgent": None,
                "complete": True,
                "phase": phase,
                "gardenerHeartbeat": heartbeat,
            }

        unscored = [candidate for candidate in candidates if candidate["score"] is None]
        target = unscored[0] if unscored else min(candidates, key=lambda candidate: candidate["score"] or 0)
        result = (
            self._run_revision_cycle_via_task_queue(target["id"])
            if phase == "revision"
            else self._run_draft_cycle_via_task_queue(target["id"])
        )
        section_agent_metadata = (result.get("event") or {}).get("metadata") or {}
        event = AuthoringLoop(self.book_root).history.record_event(
            event_type="hypervisor_section_agent_dispatched",
            agent_id="hypervisor_agent",
            subject=target["id"],
            status="pass",
            rationale=f"Hypervisor selected {target['id']} for the next {phase} section-agent pass.",
            metadata={
                "phase": phase,
                "selection_reason": "unscored" if unscored else "lowest_score",
                "completeness_percent": section_agent_metadata.get("completeness_percent"),
                "completeness_rationale": section_agent_metadata.get("completeness_rationale", ""),
            },
        )
        return {
            "event": event,
            "targetSectionId": target["id"],
            "sectionAgent": result,
            "phase": phase,
            "gardenerHeartbeat": heartbeat,
        }

    def _run_urgent_hypervisor_task(self) -> dict[str, Any] | None:
        from scripts.book.agent_workflow import AGENT_IDS, AuthoringAgentWorkflow

        workflow = AuthoringAgentWorkflow(self.book_root, project_root=Path("."))
        workflow.supervise_agents(section_ids=[], queue_work=False)
        runtime = workflow.runtime.list().get(AGENT_IDS["hypervisor"], {})
        pending = [
            task for task in runtime.get("task_queue", [])
            if task.get("status") == "pending"
        ]
        if not pending:
            return None
        pending.sort(key=lambda item: (item.get("priority", 50), item.get("added_at", "")))
        task = pending[0]
        message = (task.get("context") or {}).get("message") or {}
        if task.get("priority", 50) > 0 or not str(message.get("subject", "")).startswith("LaTeX compile failed:"):
            return None
        result = workflow.run_agent_task(AGENT_IDS["hypervisor"])
        urgent_result = result.get("result") or {}
        queued_repairs = urgent_result.get("queued_repairs") or []
        executed_repairs = []
        for repair_task in queued_repairs:
            repair_agent_id = repair_task.get("agent_id")
            if not repair_agent_id:
                repair_section_id = (repair_task.get("context") or {}).get("section_id")
                repair_agent_id = f"{AGENT_IDS['section']}__{repair_section_id}" if repair_section_id else ""
            if not repair_agent_id:
                continue
            latest_task = self._runtime_task_by_id(workflow, repair_agent_id, repair_task.get("task_id"))
            if not latest_task:
                continue
            if latest_task.get("status") != "pending":
                continue
            executed_repairs.append(
                self._run_existing_workflow_task(
                    workflow,
                    repair_agent_id,
                    latest_task,
                    execute_latex=True,
                )
            )
        retry = self._retry_compile_after_urgent_repair(message, executed_repairs)
        event = AuthoringLoop(self.book_root).history.record_event(
            event_type="hypervisor_urgent_compile_failure_processed",
            agent_id=AGENT_IDS["hypervisor"],
            subject="book",
            status="warn",
            rationale="Processed top-priority LaTeX compile failure before normal hypervisor work.",
            metadata={
                "task": result.get("task"),
                "result": result.get("result"),
                "executed_repairs": executed_repairs,
                "retry_compile": retry,
            },
        )
        return {
            "event": event,
            "targetSectionId": None,
            "sectionAgent": executed_repairs[0] if executed_repairs else None,
            "complete": bool(retry and retry.get("status") == "passed"),
            "phase": "compile_repair",
            "urgent": result,
            "executedRepairs": executed_repairs,
            "retryCompile": retry,
        }

    def _runtime_task_by_id(
        self,
        workflow: Any,
        agent_id: str,
        task_id: str | None,
    ) -> dict[str, Any] | None:
        if not task_id:
            return None
        for task in workflow.runtime.list().get(agent_id, {}).get("task_queue", []):
            if task.get("task_id") == task_id:
                return task
        return None

    def _retry_compile_after_urgent_repair(
        self,
        message: dict[str, Any],
        executed_repairs: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not executed_repairs:
            return None
        try:
            payload = yaml.safe_load(message.get("body") or "") or {}
        except yaml.YAMLError:
            payload = {}
        scope = payload.get("scope") or str(message.get("subject") or "").split(":", 1)[-1].strip()
        target_ids = payload.get("responsible_section_ids") or payload.get("target_section_ids") or []
        builder = LatexBuildService(self.book_root)
        if scope == "section" and len(target_ids) == 1:
            return builder.compile_section(target_ids[0]).as_dict()
        if scope == "book":
            return builder.compile_book().as_dict()
        return None

    def review_document_for_revision_subset(self, limit: int = 5) -> dict[str, Any]:
        """Read the assembled document and choose sections for a second revision pass."""
        document_tex = LatexBuildService(self.book_root).assembler.assemble_book()
        book = self.repository.load_book()
        candidates = self._section_candidates(book["work"].get("structure", []))
        scored = [candidate for candidate in candidates if candidate["score"] is not None]
        needs_revision = [
            candidate
            for candidate in scored
            if (candidate["score"] or 0) < 85
        ]
        ranked = sorted(needs_revision or scored, key=lambda candidate: candidate["score"] or 0)
        selected = ranked[:max(0, limit)]
        average_score = (
            sum(candidate["score"] or 0 for candidate in scored) / len(scored)
            if scored
            else None
        )
        event = AuthoringLoop(self.book_root).history.record_event(
            event_type="hypervisor_document_reviewed",
            agent_id="hypervisor_agent",
            subject="book",
            status="warn" if selected else "pass",
            rationale=(
                f"Selected {len(selected)} section(s) for coordinate/propose/revise follow-up."
                if selected
                else "No section agents need a follow-up revision pass."
            ),
            metadata={
                "document_chars": len(document_tex),
                "average_completeness_percent": average_score,
                "selected_section_ids": [candidate["id"] for candidate in selected],
                "selection_rule": "scores below 85, otherwise lowest-scored sections",
            },
        )
        return {
            "event": event,
            "selectedSectionIds": [candidate["id"] for candidate in selected],
            "documentChars": len(document_tex),
            "averageCompletenessPercent": average_score,
        }

    def compile_section(self, section_id: str) -> dict[str, Any]:
        result = LatexBuildService(self.book_root).compile_section(section_id)
        AuthoringLoop(self.book_root).history.record_event(
            event_type="section_compile",
            agent_id="desktop_app",
            subject=section_id,
            status="pass" if result.status == "passed" else "fail",
            rationale="Selected section compile requested from UI.",
            metadata=result.as_dict(),
        )
        if result.status != "passed":
            return self._run_section_compile_repair_loop(section_id, result.as_dict())
        return result.as_dict()

    def _run_section_compile_repair_loop(
        self,
        section_id: str,
        initial_result: dict[str, Any],
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        attempts = []
        current_result = initial_result
        for attempt in range(1, max_attempts + 1):
            current_result = self._compile_result_with_responsible_sections(current_result, [section_id])
            self._route_compile_failure_to_hypervisor(
                current_result,
                [section_id],
                "section",
                queue_repairs=False,
            )
            urgent = None
            urgent_error = ""
            try:
                urgent = self._run_urgent_hypervisor_task()
            except Exception as exc:
                urgent_error = str(exc)
            repair = (urgent or {}).get("sectionAgent")
            retry = (urgent or {}).get("retryCompile")
            if not retry:
                try:
                    repair = self._run_compile_fix_section_agent(section_id, current_result, attempt, max_attempts)
                except Exception as exc:
                    repair = {
                        "section_id": section_id,
                        "action_id": "fix_latex_compile_error",
                        "status": "failed",
                        "error": str(exc),
                    }
                retry = LatexBuildService(self.book_root).compile_section(section_id).as_dict()
            retry = self._compile_result_with_responsible_sections(retry, [section_id])
            if urgent_error:
                retry.setdefault("errors", [])
                retry["errors"] = list(dict.fromkeys([*retry["errors"], f"Repair dispatch failed: {urgent_error}"]))
            AuthoringLoop(self.book_root).history.record_event(
                event_type="section_compile_repair_attempt",
                agent_id="desktop_app",
                subject=section_id,
                status="pass" if retry.get("status") == "passed" else "fail",
                rationale=f"Compile repair attempt {attempt} of {max_attempts}.",
                metadata={
                    "compile": retry,
                    "repair_task_id": (repair.get("task") or {}).get("task_id"),
                    "hypervisor_urgent_task_id": ((urgent or {}).get("urgent") or {}).get("task", {}).get("task_id"),
                },
            )
            attempts.append({
                "attempt": attempt,
                "repair": repair,
                "hypervisor": self._urgent_compile_repair_summary(urgent),
                "error": urgent_error or (repair.get("error") if isinstance(repair, dict) else ""),
                "compile": self._compile_attempt_snapshot(retry),
            })
            current_result = retry
            if retry.get("status") == "passed":
                retry["repair_loop"] = {
                    "status": "passed",
                    "attempts": attempts,
                }
                return retry
        current_result["repair_loop"] = {
            "status": "failed",
            "attempts": attempts,
        }
        return current_result

    def compile_book(self) -> dict[str, Any]:
        result = LatexBuildService(self.book_root).compile_book()
        AuthoringLoop(self.book_root).history.record_event(
            event_type="book_compile",
            agent_id="desktop_app",
            subject="book",
            status="pass" if result.status == "passed" else "fail",
            rationale="Full book compile requested from UI.",
            metadata=result.as_dict(),
        )
        if result.status != "passed":
            return self._run_book_compile_repair_loop(result.as_dict())
        return result.as_dict()

    def _run_book_compile_repair_loop(
        self,
        initial_result: dict[str, Any],
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        attempts = []
        current_result = initial_result
        for attempt in range(1, max_attempts + 1):
            target_ids = self._compile_repair_targets(current_result)
            current_result = self._compile_result_with_responsible_sections(current_result, target_ids)
            if not target_ids:
                break
            self._route_compile_failure_to_hypervisor(
                current_result,
                target_ids,
                "book",
                queue_repairs=False,
            )
            urgent = None
            urgent_error = ""
            try:
                urgent = self._run_urgent_hypervisor_task()
            except Exception as exc:
                urgent_error = str(exc)
            repairs = (urgent or {}).get("executedRepairs") or []
            retry = (urgent or {}).get("retryCompile")
            if not retry:
                repairs = []
                for section_id in target_ids:
                    try:
                        repairs.append(self._run_compile_fix_section_agent(section_id, current_result, attempt, max_attempts))
                    except Exception as exc:
                        repairs.append({
                            "section_id": section_id,
                            "action_id": "fix_latex_compile_error",
                            "status": "failed",
                            "error": str(exc),
                        })
                retry = LatexBuildService(self.book_root).compile_book().as_dict()
            retry = self._compile_result_with_responsible_sections(retry, target_ids)
            if urgent_error:
                retry.setdefault("errors", [])
                retry["errors"] = list(dict.fromkeys([*retry["errors"], f"Repair dispatch failed: {urgent_error}"]))
            AuthoringLoop(self.book_root).history.record_event(
                event_type="book_compile_repair_attempt",
                agent_id="desktop_app",
                subject="book",
                status="pass" if retry.get("status") == "passed" else "fail",
                rationale=f"Direct compile repair attempt {attempt} of {max_attempts}.",
                metadata={
                    "compile": retry,
                    "target_section_ids": target_ids,
                    "repair_task_ids": [(repair.get("task") or {}).get("task_id") for repair in repairs],
                    "hypervisor_urgent_task_id": ((urgent or {}).get("urgent") or {}).get("task", {}).get("task_id"),
                },
            )
            attempts.append({
                "attempt": attempt,
                "target_section_ids": target_ids,
                "repairs": repairs,
                "hypervisor": self._urgent_compile_repair_summary(urgent),
                "error": urgent_error,
                "compile": self._compile_attempt_snapshot(retry),
            })
            current_result = retry
            if retry.get("status") == "passed":
                retry["repair_loop"] = {"status": "passed", "attempts": attempts}
                return retry
        current_result["repair_loop"] = {"status": "failed", "attempts": attempts}
        return current_result

    def _compile_attempt_snapshot(self, compile_result: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in dict(compile_result or {}).items()
            if key != "repair_loop"
        }

    def _compile_repair_targets(self, compile_result: dict[str, Any]) -> list[str]:
        responsible_ids = compile_result.get("responsible_section_ids") or []
        if responsible_ids:
            return list(dict.fromkeys(responsible_ids))
        return []

    def _compile_result_with_responsible_sections(
        self,
        compile_result: dict[str, Any],
        fallback_section_ids: list[str],
    ) -> dict[str, Any]:
        result = dict(compile_result or {})
        ids = list(dict.fromkeys(result.get("responsible_section_ids") or fallback_section_ids or []))
        if ids:
            titles = result.get("responsible_section_titles") or []
            if len(titles) < len(ids):
                title_map = {
                    section_id: (self.repository.outline_service().get_node(section_id) or {}).get("title", section_id)
                    for section_id in ids
                }
                titles = [title_map.get(section_id, section_id) for section_id in ids]
            result["responsible_section_ids"] = ids
            result["responsible_section_titles"] = titles
            if result.get("status") == "failed" and not result.get("diagnostic_summary"):
                first_error = (result.get("errors") or ["See the compile log for details."])[0]
                result["diagnostic_summary"] = f"Compile failed in {', '.join(titles)}: {first_error}"
        return result

    def _urgent_compile_repair_summary(self, urgent: dict[str, Any] | None) -> dict[str, Any] | None:
        if not urgent:
            return None
        urgent_task = (urgent.get("urgent") or {}).get("task") or {}
        retry = urgent.get("retryCompile") or {}
        return {
            "phase": urgent.get("phase"),
            "complete": urgent.get("complete"),
            "task_id": urgent_task.get("task_id"),
            "executed_repair_count": len(urgent.get("executedRepairs") or []),
            "retry_status": retry.get("status"),
            "responsible_section_ids": retry.get("responsible_section_ids") or [],
            "responsible_section_titles": retry.get("responsible_section_titles") or [],
        }

    def _run_compile_fix_section_agent(
        self,
        section_id: str,
        compile_result: dict[str, Any],
        attempt: int,
        max_attempts: int,
    ) -> dict[str, Any]:
        node = self.repository.outline_service().get_node(section_id) or {}
        context = {
            "section_id": section_id,
            "title": node.get("title", section_id),
            "phase": "compile_repair",
            "attempt": attempt,
            "max_attempts": max_attempts,
            "diagnostic_summary": compile_result.get("diagnostic_summary", ""),
            "errors": compile_result.get("errors") or [],
            "log_path": compile_result.get("log_path"),
            "tex_path": compile_result.get("tex_path"),
            "responsible_section_ids": compile_result.get("responsible_section_ids") or [section_id],
            "responsible_section_titles": compile_result.get("responsible_section_titles") or [node.get("title", section_id)],
            "instruction": (
                "Direct compile repair: fix only the concrete LaTeX compiler error in this section. "
                "Do not route through Hypervisor and do not perform a general rewrite."
            ),
        }
        return self._run_section_agent_task(
            section_id,
            "fix_latex_compile_error",
            context,
            execute_latex=True,
            priority=0,
        )

    def _activate_hypervisor_for_compile_error(
        self,
        compile_result: dict[str, Any],
        section_ids: list[str],
        scope: str,
    ) -> None:
        from scripts.book.agent_workflow import AGENT_IDS, AuthoringAgentWorkflow

        workflow = AuthoringAgentWorkflow(self.book_root, project_root=Path("."))
        workflow.supervise_agents(section_ids=section_ids, queue_work=False)
        try:
            workflow.runtime.start(AGENT_IDS["hypervisor"])
        except KeyError:
            return
        AuthoringLoop(self.book_root).history.record_event(
            event_type="hypervisor_compile_error_notified",
            agent_id="desktop_app",
            subject="book",
            status="warn",
            rationale="Hypervisor runtime was activated for compile-error visibility; section repair runs directly.",
            metadata={
                "scope": scope,
                "target_section_ids": section_ids,
                "compile": compile_result,
            },
        )

    def _route_compile_failure_to_hypervisor(
        self,
        compile_result: dict[str, Any],
        section_ids: list[str],
        scope: str,
        queue_repairs: bool = True,
    ) -> None:
        from scripts.book.agent_workflow import AGENT_IDS, AuthoringAgentWorkflow

        target_section_ids = list(dict.fromkeys(section_ids))
        workflow = AuthoringAgentWorkflow(self.book_root, project_root=Path("."))
        workflow.supervise_agents(section_ids=target_section_ids, queue_work=False)
        message = {
            "from": "desktop_app",
            "to": AGENT_IDS["hypervisor"],
            "reply_to": "desktop_app",
            "subject": f"LaTeX compile failed: {scope}",
            "body": yaml.safe_dump({
                "scope": scope,
                "target_section_ids": target_section_ids,
                "status": compile_result.get("status"),
                "errors": compile_result.get("errors") or [],
                "diagnostic_summary": compile_result.get("diagnostic_summary", ""),
                "responsible_section_ids": compile_result.get("responsible_section_ids") or target_section_ids,
                "responsible_section_titles": compile_result.get("responsible_section_titles") or [],
                "log_path": compile_result.get("log_path"),
                "tex_path": compile_result.get("tex_path"),
                "instructions": (
                    "Route concrete LaTeX repair tasks to the section agent(s). "
                    "Each section agent should preserve useful prose and only fix the syntax causing the compile failure."
                ),
            }, sort_keys=False, allow_unicode=True),
        }
        workflow.message_router.publish(message)
        if not queue_repairs:
            return
        feedback = yaml.safe_dump({
            "source": "hypervisor_agent",
            "reason": "LaTeX compile failed.",
            "scope": scope,
            "errors": compile_result.get("errors") or [],
            "diagnostic_summary": compile_result.get("diagnostic_summary", ""),
            "responsible_section_ids": compile_result.get("responsible_section_ids") or target_section_ids,
            "responsible_section_titles": compile_result.get("responsible_section_titles") or [],
            "log_path": compile_result.get("log_path"),
            "tex_path": compile_result.get("tex_path"),
            "instructions": "Fix the LaTeX error(s) causing compilation to fail. Preserve useful content and make the smallest valid repair.",
        }, sort_keys=False, allow_unicode=True)
        for section_id in target_section_ids:
            workflow.queue_agent_task(
                f"{AGENT_IDS['section']}__{section_id}",
                "fix_latex_compile_error",
                {
                    "section_id": section_id,
                    "phase": "compile_repair",
                    "feedback": feedback,
                    "diagnostic_summary": compile_result.get("diagnostic_summary", ""),
                    "errors": compile_result.get("errors") or [],
                    "log_path": compile_result.get("log_path"),
                    "tex_path": compile_result.get("tex_path"),
                },
                priority=0,
            )

    def update_design_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        settings = DesignSettingsService(self.repository).update(updates)
        AuthoringLoop(self.book_root).history.record_event(
            event_type="design_settings_updated",
            agent_id="desktop_app",
            subject="book",
            status="pass",
            rationale="Updated document design settings from the desktop UI.",
            metadata={"updates": updates},
        )
        return settings

    def request_review(self, subject: str = "book") -> dict[str, Any]:
        from scripts.book.agent_workflow import AuthoringAgentWorkflow

        workflow = AuthoringAgentWorkflow(self.book_root)
        graph = workflow.dependency_graph()
        gardener_event = None
        if subject != "book":
            gardener_event = workflow.run_gardener_checks(subject)
        drift = workflow.summarize_drift()
        event = AuthoringLoop(self.book_root).history.record_event(
            event_type="review_requested",
            agent_id="desktop_app",
            subject=subject,
            status="warn",
            rationale="User requested full review across outline, drafts, dependencies, and compile state.",
            metadata={
                "dependency_graph": graph,
                "gardener_event_id": gardener_event["event_id"] if gardener_event else None,
                "drift_event_id": drift["event"]["event_id"],
            },
        )
        return {
            **event,
            "event": event,
            "dependencyGraph": graph,
            "gardener": gardener_event,
            "drift": drift,
        }

    def create_section(self, title: str, parent_id: str | None = None) -> dict[str, Any]:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Section title is required")

        book = self.repository.load_book()
        structure = book["work"].setdefault("structure", [])
        if not structure:
            structure.append({
                "id": "chapter_1",
                "type": "chapter",
                "number": 1,
                "title": "Chapter 1",
                "content": [],
            })

        parent = self._find_node(structure, parent_id) if parent_id else structure[0]
        if parent is None:
            raise KeyError(f"Unknown parent id: {parent_id}")

        parent.setdefault("content", [])
        existing_ids = self._all_node_ids(structure)
        section_id = self._unique_id(clean_title, existing_ids)
        parent_number = str(parent.get("number") or "")
        child_number = len(parent["content"]) + 1
        number = f"{parent_number}.{child_number}" if parent_number else str(child_number)

        section = {
            "id": section_id,
            "type": "section",
            "number": number,
            "title": clean_title,
            "summary": "",
            "goal": "",
            "prerequisites": [],
            "dependencies": {"structural": [], "narrative": ""},
            "key_concepts": [],
            "citations": [],
            "content_file": f"content/sections/{section_id}.md",
        }
        parent["content"].append(section)
        self.repository.save_book(book)
        self.repository.save_section(section_id, self._fallback_section_content(section))
        AuthoringLoop(self.book_root).history.record_event(
            event_type="section_created",
            agent_id="desktop_app",
            subject=section_id,
            status="warn",
            rationale=f"Created section '{clean_title}' from the desktop outline.",
        )
        return self.section_payload(section_id)

    def create_chapter(self, title: str) -> dict[str, Any]:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Chapter title is required")

        book = self.repository.load_book()
        structure = book["work"].setdefault("structure", [])
        existing_ids = self._all_node_ids(structure)
        chapter_id = self._unique_id(clean_title, existing_ids)
        chapter = {
            "id": chapter_id,
            "type": "chapter",
            "number": len(structure) + 1,
            "title": clean_title,
            "content": [],
        }
        structure.append(chapter)
        self.repository.save_book(book)
        AuthoringLoop(self.book_root).history.record_event(
            event_type="chapter_created",
            agent_id="desktop_app",
            subject=chapter_id,
            status="warn",
            rationale=f"Created chapter '{clean_title}' from the desktop outline.",
        )
        return chapter

    def update_outline_node(self, node_id: str, title: str) -> dict[str, Any]:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Outline title is required")

        book = self.repository.load_book()
        node = self._find_node(book["work"].get("structure", []), node_id)
        if not node:
            raise KeyError(f"Unknown outline node id: {node_id}")
        node["title"] = clean_title
        self.repository.save_book(book)
        AuthoringLoop(self.book_root).history.record_event(
            event_type="outline_updated",
            agent_id="desktop_app",
            subject=node_id,
            status="warn",
            rationale=f"Renamed outline node to '{clean_title}'.",
        )
        return node

    def accept_proposal(self, proposal_id: str, note: str = "") -> dict[str, Any]:
        proposal = self.repository.proposals.accept(proposal_id, reviewer="desktop_app", note=note)
        return proposal.__dict__

    def reject_proposal(self, proposal_id: str, note: str = "") -> dict[str, Any]:
        proposal = self.repository.proposals.reject(proposal_id, reviewer="desktop_app", note=note)
        return proposal.__dict__

    def revise_proposal(self, proposal_id: str, proposed_content: str, note: str = "") -> dict[str, Any]:
        proposal = self.repository.proposals.revise(
            proposal_id,
            proposed_content=proposed_content,
            reviewer="desktop_app",
            note=note or "Revised from desktop proposal review.",
        )
        return proposal.__dict__

    def _outline(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chapters = []
        for index, node in enumerate(nodes, 1):
            leaves = self._leaf_items(node)
            chapters.append({
                "id": node.get("id"),
                "chapter": str(node.get("number") or f"Chapter {index}"),
                "title": node.get("title", "Untitled"),
                "expanded": True,
                "items": leaves,
            })
        return chapters

    def _fallback_section_content(self, node: dict[str, Any]) -> str:
        section_id = node.get("id")
        if section_id:
            source = self.repository.load_section(section_id)
            if source.strip():
                return source
        title = node.get("title", node.get("id", "Untitled"))
        summary = node.get("summary") or node.get("goal") or "Draft this section."
        return f"\\section{{{title}}}\n\n{summary}\n"

    def _section_agent_system_prompt(self) -> str:
        definition_path = Path("scripts/agents/agent_definitions/section_agent.yaml")
        try:
            definition = yaml.safe_load(definition_path.read_text()) or {}
            role = definition.get("role", "")
            prompt_header = str(definition.get("prompt_header") or "").strip()
            tasks = "\n".join(f"- {task}" for task in definition.get("tasks", []))
        except Exception:
            role = "Composes LaTeX content for a specific document section."
            prompt_header = ""
            tasks = "- Draft valid LaTeX for the selected section"
        return (
            "You are section_agent, an agent in the Codynamic Book Machine system.\n"
            f"Role: {role}\n\n"
            f"Prompt Header:\n{prompt_header or '(No prompt header declared.)'}\n\n"
            f"Responsibilities:\n{tasks}\n\n"
            "You can see the full book outline for context, but you are performing one single pass for the selected section only. "
            "Return a valid JSON object only, with keys latex_body, completeness_percent, and completeness_rationale. "
            "latex_body must contain valid LaTeX body content only: no documentclass, preamble, begin/end document, markdown fences, or commentary. "
            "completeness_percent must be an integer from 0 to 100 estimating how complete the generated draft is for this section's outline intent and source material."
        )

    def _run_draft_cycle_via_task_queue(self, section_id: str) -> dict[str, Any]:
        result = self._run_introspective_section_cycle(section_id, phase="draft")
        result["gardener"] = self._run_gardener_task(section_id)
        return result

    def _run_revision_cycle_via_task_queue(self, section_id: str) -> dict[str, Any]:
        result = self._run_introspective_section_cycle(section_id, phase="revision")
        result["gardener"] = self._run_gardener_task(section_id)
        return result

    def _run_introspective_section_cycle(self, section_id: str, phase: str) -> dict[str, Any]:
        from scripts.book.agent_workflow import AGENT_IDS, AuthoringAgentWorkflow

        planning = self.start_section_agent(section_id, task_context={
            "trigger": f"hypervisor_{phase}_cycle",
            "requested_phase": phase,
        })
        workflow = AuthoringAgentWorkflow(self.book_root, project_root=Path("."))
        workflow.supervise_agents(section_ids=[section_id], queue_work=False)
        agent_id = f"{AGENT_IDS['section']}__{section_id}"
        completed_tasks = []
        diagram_results = []
        latex_result = None
        visual_result = None
        for _ in range(12):
            task = workflow.runtime.next_task(agent_id)
            if not task:
                break
            action_id = task.get("action_id")
            if action_id in {"draft_initial_section", "revise_section_from_feedback", "fix_latex_compile_error"}:
                task_result = self._run_existing_workflow_task(workflow, agent_id, task, execute_latex=True)
                latex_result = task_result.get("result") or latex_result
            else:
                task_result = workflow.run_agent_task(agent_id)
            completed_tasks.append(task_result)
            if action_id == "propose_section_visuals":
                visual_result = task_result
                diagram_count = int((task_result.get("result") or {}).get("diagram_count") or 0)
                for _diagram_index in range(diagram_count):
                    diagram = workflow.run_agent_task(AGENT_IDS["diagram"])
                    if diagram.get("task"):
                        diagram_results.append(diagram)
                break
        event = (latex_result or {}).get("event") or planning.get("event")
        result = {
            "event": event,
            "section": self.section_payload(section_id),
            "planning": planning,
            "completedTasks": completed_tasks,
            "diagram_results": diagram_results,
            "diagram_result": diagram_results[0] if diagram_results else None,
        }
        if (latex_result or {}).get("output_path"):
            result["output_path"] = latex_result["output_path"]
        if visual_result:
            result["visual"] = {
                "proposal_result": visual_result,
                "diagram_results": diagram_results,
                "diagram_result": diagram_results[0] if diagram_results else None,
            }
        return result

    def _run_existing_workflow_task(
        self,
        workflow: Any,
        agent_id: str,
        task: dict[str, Any],
        execute_latex: bool,
    ) -> dict[str, Any]:
        workflow.runtime.mark_task(agent_id, task["task_id"], "running")
        if execute_latex:
            section_id = (task.get("context") or {}).get("section_id") or agent_id.split("__", 1)[1]
            result = self._run_section_latex_pass(
                section_id,
                task_context={"action_id": task.get("action_id"), **(task.get("context") or {})},
            )
        else:
            result = {
                "section_id": (task.get("context") or {}).get("section_id"),
                "action_id": task.get("action_id"),
                "status": "complete",
                "context": task.get("context") or {},
            }
        completed = workflow.runtime.mark_task(agent_id, task["task_id"], "complete", result=result)
        workflow._publish_task_completion(agent_id, task, result)
        completed_summary = {key: value for key, value in completed.items() if key != "result"}
        return {**result, "task": completed_summary, "result": result}

    def _run_pending_section_visual_task(self, section_id: str) -> dict[str, Any] | None:
        node = self.repository.outline_service().get_node(section_id) or {}
        if self._is_front_matter_node(section_id, node):
            return None
        from scripts.book.agent_workflow import AGENT_IDS, AuthoringAgentWorkflow

        workflow = AuthoringAgentWorkflow(self.book_root, project_root=Path("."))
        workflow.supervise_agents(section_ids=[section_id], queue_work=False)
        agent_id = f"{AGENT_IDS['section']}__{section_id}"
        proposal_task = self._pending_section_visual_task(workflow, agent_id, section_id)
        if not proposal_task:
            if not self._section_should_propose_visual(section_id):
                return None
            node = self.repository.outline_service().get_node(section_id) or {}
            proposal_task = workflow.queue_agent_task(
                agent_id,
                "propose_section_visuals",
                {
                    "section_id": section_id,
                    "phase": "post_section_pass_visual_decision",
                    "max_diagrams": 2,
                    "description": self._section_visual_description(section_id, node),
                    "media_type": "tikz",
                    "priority": 4,
                },
                priority=4,
            )
        proposal_result = workflow.run_agent_task(agent_id)
        diagram_results = []
        diagram_count = int((proposal_result.get("result") or {}).get("diagram_count") or 0)
        for _index in range(diagram_count):
            diagram = workflow.run_agent_task(AGENT_IDS["diagram"])
            if diagram.get("task"):
                diagram_results.append(diagram)
        return {
            "section_id": section_id,
            "proposal_task": proposal_task,
            "proposal_result": proposal_result,
            "diagram_results": diagram_results,
            "diagram_result": diagram_results[0] if diagram_results else None,
        }

    def _pending_section_visual_task(
        self,
        workflow: Any,
        agent_id: str,
        section_id: str,
    ) -> dict[str, Any] | None:
        for task in workflow.runtime.list().get(agent_id, {}).get("task_queue", []):
            if task.get("status") != "pending":
                continue
            if task.get("action_id") != "propose_section_visuals":
                continue
            if (task.get("context") or {}).get("section_id") == section_id:
                return task
        return None

    def _section_should_propose_visual(self, section_id: str) -> bool:
        node = self.repository.outline_service().get_node(section_id) or {}
        if self._is_front_matter_node(section_id, node):
            return False
        existing_latex = self.repository.load_latex_section(section_id)
        if "media/diagrams/" in existing_latex or "\\includegraphics" in existing_latex or "\\input{media/diagrams/" in existing_latex:
            return False
        loop = AuthoringLoop(self.book_root)
        if any(request.get("section_id") == section_id for request in loop.media.load_requests()):
            return False
        source = self.repository.load_section(section_id)
        text = " ".join(str(value or "") for value in [
            node.get("title"),
            node.get("summary"),
            node.get("goal"),
            source,
        ]).lower()
        visual_terms = [
            "diagram",
            "figure",
            "schema",
            "architecture",
            "workflow",
            "message flow",
            "lifecycle",
            "runtime",
            "graph",
            "coordination",
            "pipeline",
            "queue",
        ]
        return any(term in text for term in visual_terms)

    def _is_front_matter_node(self, section_id: str, node: dict[str, Any]) -> bool:
        matter = str(node.get("matter") or node.get("section_matter") or "").lower()
        if matter in {"main", "main_matter", "back", "back_matter", "appendix", "appendices"}:
            return False
        if matter in {"front", "front_matter"}:
            return True
        front_ids = self._front_matter_ids()
        if section_id in front_ids or node.get("id") in front_ids:
            return True
        content_file = str(node.get("content_file") or "").lower()
        if "/front_matter/" in content_file or content_file.startswith("front_matter/"):
            return True
        title = str(node.get("title") or section_id).strip().lower().replace("-", "_").replace(" ", "_")
        conventional_front = {
            "abstract",
            "title_page",
            "table_of_contents",
            "toc",
            "dedication",
            "epigraph",
            "foreword",
            "preface",
            "acknowledgements",
            "acknowledgments",
        }
        return section_id in conventional_front or title in conventional_front

    def _front_matter_ids(self) -> set[str]:
        front = self.repository.outline_service().work.get("front_matter") or {}
        ids: set[str] = set()
        if isinstance(front, list):
            for item in front:
                if isinstance(item, str):
                    ids.add(item)
                elif isinstance(item, dict):
                    ids.update(str(value) for key, value in item.items() if key in {"id", "section_id"} and value)
        elif isinstance(front, dict):
            for key, value in front.items():
                ids.add(str(key))
                if isinstance(value, dict):
                    ids.update(str(value[item_key]) for item_key in {"id", "section_id"} if value.get(item_key))
        return ids

    def _section_visual_description(self, section_id: str, node: dict[str, Any]) -> str:
        title = node.get("title", section_id)
        summary = node.get("summary") or node.get("goal") or self.repository.load_section(section_id)[:240]
        return (
            f"Create a concise TikZ diagram for section '{title}'. "
            f"Show the main structure, workflow, or relationship described here: {summary}"
        )

    def _run_gardener_task(self, section_id: str) -> dict[str, Any]:
        from scripts.book.agent_workflow import AGENT_IDS, AuthoringAgentWorkflow

        workflow = AuthoringAgentWorkflow(self.book_root, project_root=Path("."))
        workflow.supervise_agents(section_ids=[section_id], queue_work=False)
        task = workflow.queue_agent_task(
            AGENT_IDS["gardener"],
            "run_section_checks",
            {"section_id": section_id, **self._section_coherence_context(section_id)},
            priority=30,
        )
        return workflow.run_agent_task(AGENT_IDS["gardener"]) | {"queued_task": task}

    def _run_gardener_heartbeat_task(self) -> dict[str, Any]:
        from scripts.book.agent_workflow import AGENT_IDS, AuthoringAgentWorkflow

        workflow = AuthoringAgentWorkflow(self.book_root, project_root=Path("."))
        workflow.supervise_agents(section_ids=[], queue_work=False)
        task = workflow.queue_agent_task(
            AGENT_IDS["gardener"],
            "run_maintenance_cycle",
            {"trigger": "hypervisor_pass"},
            priority=60,
        )
        return workflow.run_agent_task(AGENT_IDS["gardener"]) | {"queued_task": task}

    def _section_coherence_context(self, section_id: str) -> dict[str, Any]:
        latest = self._latest_verification_for(section_id) or {}
        metadata = latest.get("metadata") or {}
        score = metadata.get("completeness_percent")
        rationale = metadata.get("completeness_rationale", "")
        if score is None:
            score = self._score_for(section_id)
        return {
            "section_agent_coherence_percent": score,
            "section_agent_coherence_rationale": rationale,
        }

    def _run_section_agent_task(
        self,
        section_id: str,
        action_id: str,
        context: dict[str, Any],
        execute_latex: bool,
        priority: int = 20,
    ) -> dict[str, Any]:
        from scripts.book.agent_workflow import AGENT_IDS, AuthoringAgentWorkflow

        workflow = AuthoringAgentWorkflow(self.book_root, project_root=Path("."))
        workflow.supervise_agents(section_ids=[section_id], queue_work=False)
        agent_id = f"{AGENT_IDS['section']}__{section_id}"
        task = workflow.queue_agent_task(agent_id, action_id, context=context, priority=priority)
        workflow.runtime.mark_task(agent_id, task["task_id"], "running")
        if execute_latex:
            result = self._run_section_latex_pass(section_id, task_context={"action_id": action_id, **context})
        else:
            result = {
                "section_id": section_id,
                "action_id": action_id,
                "status": "complete",
                "context": context,
            }
        completed = workflow.runtime.mark_task(agent_id, task["task_id"], "complete", result=result)
        workflow._publish_task_completion(agent_id, task, result)
        completed_summary = {key: value for key, value in completed.items() if key != "result"}
        return {**result, "task": completed_summary}

    def _section_agent_prompt(
        self,
        book: dict[str, Any],
        node: dict[str, Any],
        source_markdown: str,
        existing_latex: str,
        sibling_context: list[dict[str, Any]],
        task_context: dict[str, Any],
    ) -> str:
        outline_context = yaml.safe_dump(book["work"], sort_keys=False, allow_unicode=True)
        section_context = yaml.safe_dump(node, sort_keys=False, allow_unicode=True)
        sibling_yaml = yaml.safe_dump(sibling_context, sort_keys=False, allow_unicode=True)
        existing_block = existing_latex.strip() or "(No existing LaTeX draft was found.)"
        action_id = str(task_context.get("action_id", ""))
        if action_id == "fix_latex_compile_error":
            task_mode = (
                "DIRECT LATEX COMPILE REPAIR. The compiler has identified this section as responsible for the current failure. "
                "Use fix_latex_compile_error only. Read diagnostic_summary, errors, log_path, tex_path, and the current LaTeX. "
                "Return the smallest body-level LaTeX change that fixes the named compiler error. Do not perform a general rewrite, "
                "do not add preamble/package requirements, and do not change unaffected prose. If the failure is caused by booktabs "
                "commands such as \\toprule, \\midrule, or \\bottomrule, replace those commands locally with \\hline."
            )
        else:
            task_mode = (
                "This section already has LaTeX content. Use coordinate_with_sibling_sections to compare the section against "
                "nearby sections, use propose_section_improvements to identify a concrete improvement plan, then use "
                "revise_section_from_feedback with that proposal as the feedback. Return the revised single-pass result."
                if existing_latex.strip()
                else
                "This section has no existing LaTeX draft. Use draft_initial_section, while still checking sibling context for fit."
            )
        return f"""
Generate or revise the LaTeX draft for this section.

Selected section:
{section_context}

Imported source material for this section:
{source_markdown or "(No imported source text was found. Use the section title, summary, and full outline context.)"}

Existing LaTeX content for this section:
{existing_block}

Sibling section context:
{sibling_yaml}

Hypervisor task context:
{yaml.safe_dump(task_context, sort_keys=False, allow_unicode=True)}

Full book outline context:
{outline_context}

Task mode:
{task_mode}

Requirements:
- Return JSON only: {{"latex_body": "...", "completeness_percent": 0-100, "completeness_rationale": "..."}}.
- latex_body must use LaTeX, not Markdown.
- latex_body must not include \\section, \\subsection, or other heading commands unless they are structurally necessary inside this section.
- When existing LaTeX is present, preserve usable material and revise it instead of discarding it.
- Preserve factual content from the imported source.
- Expand terse bullets into concise prose when useful, but do not invent unsupported claims.
- Use valid LaTeX escapes for &, %, $, #, _, {{, and }}.
- Keep citations as textual placeholders if source citations are not registered.
- completeness_percent should reflect source coverage, specificity, citation readiness, and whether the draft is publishable without further section-agent work.
""".strip()

    def _extract_section_agent_response(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        fenced = re.search(r"```(?:json|latex|tex)?\s*(.*?)```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1).strip()
        try:
            payload = json.loads(cleaned)
        except Exception:
            payload = {
                "latex_body": cleaned,
                "completeness_percent": 50,
                "completeness_rationale": "Agent returned LaTeX without a structured completeness estimate.",
            }
        latex = str(payload.get("latex_body") or payload.get("latex") or "").strip() or cleaned
        try:
            completeness = int(payload.get("completeness_percent", 50))
        except (TypeError, ValueError):
            completeness = 50
        return {
            "latex": latex.rstrip() + "\n",
            "completeness_percent": max(0, min(100, completeness)),
            "completeness_rationale": str(payload.get("completeness_rationale") or ""),
        }

    def _unwrap_latex_payload(self, content: str) -> str:
        stripped = content.strip()
        fenced = re.search(r"```(?:json|latex|tex)?\s*(.*?)```", stripped, re.DOTALL)
        if fenced:
            stripped = fenced.group(1).strip()
        if not stripped.startswith("{"):
            return content
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            legacy_match = re.match(r'^\{\s*"latex_body"\s*:\s*"(.*)"\s*,\s*"completeness_percent"\s*:', stripped, re.DOTALL)
            if legacy_match:
                return self._decode_legacy_latex_body(legacy_match.group(1))
            return content
        if isinstance(payload, dict) and payload.get("latex_body"):
            return str(payload["latex_body"]).rstrip() + "\n"
        return content

    def _decode_legacy_latex_body(self, value: str) -> str:
        return (
            value
            .replace("\\n", "\n")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
            .rstrip()
            + "\n"
        )

    def _leaf_items(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        children = node.get("content") or []
        if not children:
            section_id = node["id"]
            return [{
                "id": section_id,
                "number": str(node.get("number") or ""),
                "title": node.get("title", section_id),
                "score": self._score_for(section_id),
                "tone": self._tone_for(section_id),
                "agent": self._agent_label(section_id),
            }]
        items = []
        for child in children:
            items.extend(self._leaf_items(child))
        return items

    def _section_candidates(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = []
        for node in nodes:
            children = node.get("content") or []
            if children:
                candidates.extend(self._section_candidates(children))
            elif node.get("id"):
                candidates.append({
                    "id": node["id"],
                    "title": node.get("title", node["id"]),
                    "score": self._score_for(node["id"]),
                })
        return candidates

    def _sibling_context(self, nodes: list[dict[str, Any]], section_id: str) -> list[dict[str, Any]]:
        parent_children = self._parent_children_for(nodes, section_id) or []
        siblings = []
        for child in parent_children:
            if not child.get("id"):
                continue
            siblings.append({
                "id": child["id"],
                "title": child.get("title", child["id"]),
                "summary": child.get("summary", ""),
                "goal": child.get("goal", ""),
                "is_selected": child["id"] == section_id,
                "has_latex": bool(self.repository.load_latex_section(child["id"]).strip()) if not (child.get("content") or []) else None,
            })
        return siblings

    def _parent_children_for(self, nodes: list[dict[str, Any]], section_id: str) -> list[dict[str, Any]] | None:
        for node in nodes:
            children = node.get("content") or []
            if any(child.get("id") == section_id for child in children):
                return children
            match = self._parent_children_for(children, section_id)
            if match is not None:
                return match
        return None

    def _first_leaf_id(self, outline: list[dict[str, Any]]) -> str | None:
        for chapter in outline:
            if chapter.get("items"):
                return chapter["items"][0]["id"]
        return None

    def _valid_selected_id(self, selected_id: str | None, outline: list[dict[str, Any]]) -> str | None:
        valid_ids = {
            item["id"]
            for chapter in outline
            for item in chapter.get("items", [])
        }
        if selected_id in valid_ids:
            return selected_id
        return self._first_leaf_id(outline)

    def _references(self, work: dict[str, Any]) -> list[dict[str, Any]]:
        citations = work.get("citations", {}).get("entries", [])
        if citations:
            return citations
        references = work.get("references") or work.get("bibliography") or []
        if isinstance(references, list):
            return references
        if isinstance(references, dict):
            entries = references.get("entries", references)
            if isinstance(entries, dict):
                return [{"id": key, **(value if isinstance(value, dict) else {"title": str(value)})} for key, value in entries.items()]
            if isinstance(entries, list):
                return entries
        return []

    def _find_node(self, nodes: list[dict[str, Any]], node_id: str | None) -> dict[str, Any] | None:
        if not node_id:
            return None
        for node in nodes:
            if node.get("id") == node_id:
                return node
            match = self._find_node(node.get("content") or [], node_id)
            if match:
                return match
        return None

    def _all_node_ids(self, nodes: list[dict[str, Any]]) -> set[str]:
        node_ids = set()
        for node in nodes:
            if node.get("id"):
                node_ids.add(node["id"])
            node_ids.update(self._all_node_ids(node.get("content") or []))
        return node_ids

    def _unique_id(self, title: str, existing_ids: set[str]) -> str:
        base = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "section"
        candidate = base
        suffix = 2
        while candidate in existing_ids:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    def _score_for(self, section_id: str) -> int | None:
        completeness = self._latest_completeness_for(section_id)
        if completeness is not None:
            return completeness
        latest = self._latest_verification_for(section_id)
        if not latest:
            return None
        return {"pass": 80, "warn": 50, "fail": 20}.get(latest.get("status"))

    def _latest_completeness_for(self, section_id: str) -> int | None:
        for event in reversed(VerificationHistory(self.book_root).load()):
            if event.get("subject") != section_id:
                continue
            metadata = event.get("metadata") or {}
            if "completeness_percent" not in metadata:
                continue
            try:
                return int(metadata["completeness_percent"])
            except (TypeError, ValueError):
                continue
        return None

    def _tone_for(self, section_id: str) -> str:
        latest = self._latest_verification_for(section_id)
        if not latest:
            return "idle"
        return {"pass": "good", "warn": "warn", "fail": "warn"}.get(latest.get("status"), "idle")

    def _agent_label(self, section_id: str) -> str:
        latest = self._latest_verification_for(section_id)
        if latest:
            return latest.get("agent_id", "agent")
        return "Queued"

    def _latest_verification_for(self, section_id: str) -> dict[str, Any] | None:
        for event in reversed(VerificationHistory(self.book_root).load()):
            if event.get("subject") == section_id:
                return event
        return None

    def _messages(self) -> list[str]:
        chat_path = self.book_root / "logs" / "message_log" / "chat.log"
        if chat_path.exists():
            lines = [line for line in chat_path.read_text().splitlines() if line.strip()]
            if lines:
                return [self._truncate_display_line(line) for line in lines[-40:]]
        return ["desktop_app --> book: Loaded canonical book state."]

    def _truncate_display_line(self, line: str, max_chars: int = 600) -> str:
        if len(line) <= max_chars:
            return line
        return f"{line[:max_chars].rstrip()} ... [truncated {len(line) - max_chars} chars]"

    def _verification_events(self) -> list[dict[str, Any]]:
        events = VerificationHistory(self.book_root).load()[-20:]
        return [self._verification_event_summary(event) for event in events]

    def _verification_event_summary(self, event: dict[str, Any]) -> dict[str, Any]:
        metadata = event.get("metadata") or {}
        summary_metadata = {
            key: metadata[key]
            for key in (
                "completeness_percent",
                "completeness_rationale",
                "selected_section_ids",
                "target_section_ids",
                "repair_task_id",
                "repair_task_ids",
                "hypervisor_urgent_task_id",
            )
            if key in metadata
        }
        compile_result = metadata.get("compile")
        if isinstance(compile_result, dict):
            summary_metadata["compile"] = {
                "status": compile_result.get("status"),
                "errors": (compile_result.get("errors") or [])[:3],
                "diagnostic_summary": compile_result.get("diagnostic_summary"),
                "responsible_section_ids": compile_result.get("responsible_section_ids") or [],
                "responsible_section_titles": compile_result.get("responsible_section_titles") or [],
                "log_path": compile_result.get("log_path"),
            }
        return {
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "agent_id": event.get("agent_id"),
            "subject": event.get("subject"),
            "status": event.get("status"),
            "rationale": event.get("rationale"),
            "created_at": event.get("created_at"),
            "metadata": summary_metadata,
        }

    def _agent_status(self) -> dict[str, Any]:
        runtime = self._agent_runtime_state()
        pending_counts = {
            agent_id: len([
                task for task in record.get("task_queue", [])
                if task.get("status") in {"pending", "running"}
            ])
            for agent_id, record in runtime.items()
        }
        active_agents = [
            {
                "agent_id": agent_id,
                "role": record.get("role", "agent"),
                "section_id": record.get("section_id"),
                "status": record.get("status", "unknown"),
                "task_queue_length": pending_counts.get(agent_id, 0),
            }
            for agent_id, record in sorted(runtime.items())
            if record.get("status") == "running" or pending_counts.get(agent_id, 0)
        ]
        legacy_agents = list((self.data_root / "agent_state").glob("*")) if (self.data_root / "agent_state").exists() else []
        pending_proposals = len(self.repository.proposals.list(status="pending"))
        book = self.repository.load_book()
        outline = self._outline(book["work"].get("structure", []))
        section_scores = [
            score
            for chapter in outline
            for item in chapter.get("items", [])
            for score in [item.get("score")]
            if isinstance(score, (int, float))
        ]
        confidence = round(sum(section_scores) / len(section_scores)) if section_scores else 0
        working_agents = [
            agent for agent in active_agents
            if agent["task_queue_length"] > 0
        ]
        hypervisor_confidence = max(0, min(100, 100 - (pending_proposals * 10)))
        return {
            "active": len(working_agents) if runtime else len(legacy_agents),
            "total": max(len(runtime) if runtime else len(legacy_agents), 1),
            "confidence": confidence,
            "hypervisorConfidence": hypervisor_confidence,
            "pendingProposals": pending_proposals,
            "activeAgents": active_agents,
        }

    def _agent_runtime_state(self) -> dict[str, Any]:
        path = self.book_root / "logs" / "agent_runtime.json"
        if not path.exists():
            return {}
        import json

        return json.loads(path.read_text())

    def _latest_compile(self) -> dict[str, Any] | None:
        logs = sorted((self.book_root / "build" / "logs").glob("*.log"))
        if not logs:
            return None
        import json

        return json.loads(logs[-1].read_text())
