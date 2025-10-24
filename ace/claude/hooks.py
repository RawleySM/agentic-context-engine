"""Hook helpers that bridge Claude agent events to ACE explainability."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..delta import DeltaBatch

HookCallback = Callable[[str, Dict[str, Any]], None]


@dataclass
class HookMatcher:
    """Simple hook matcher compatible with Claude Agent SDK patterns."""

    event: str
    callback: HookCallback
    description: Optional[str] = None

    def matches(self, event: str) -> bool:
        return self.event == event

    def __call__(self, event: str, payload: Dict[str, Any]) -> None:
        if self.matches(event):
            self.callback(event, payload)


_LOGGER = logging.getLogger("ace.claude.hooks")


def build_explainability_hooks(
    *,
    evolution_tracker: Optional[object] = None,
    attribution_analyzer: Optional[object] = None,
    interaction_tracer: Optional[object] = None,
) -> List[HookMatcher]:
    """Return hook matchers that route Claude events into ACE analyzers."""

    hooks: List[HookMatcher] = []

    if evolution_tracker is not None:

        def _record_curator_delta(event: str, payload: Dict[str, Any]) -> None:
            if payload.get("agent") != "ace-curator":
                return
            delta = payload.get("delta")
            if delta is None:
                raw = payload.get("result")
                if isinstance(raw, dict):
                    try:
                        delta = DeltaBatch.from_json(raw)
                    except Exception:  # pragma: no cover - defensive parse guard
                        _LOGGER.debug("Unable to parse curator delta from hook payload.")
                        return
            if not isinstance(delta, DeltaBatch):
                return
            try:
                evolution_tracker.record_delta(  # type: ignore[attr-defined]
                    delta,
                    int(payload.get("epoch") or 0),
                    int(payload.get("step") or 0),
                    context=str(payload.get("context") or event),
                )
            except Exception:  # pragma: no cover - analytics are best-effort
                _LOGGER.exception("Failed to record curator delta via hook.")

        hooks.append(
            HookMatcher(
                event="post_tool_use",
                callback=_record_curator_delta,
                description="Record ACE curator delta batches",
            )
        )

    if attribution_analyzer is not None:

        def _record_generator_usage(event: str, payload: Dict[str, Any]) -> None:
            if payload.get("agent") != "ace-generator":
                return
            generator_output = payload.get("generator_output")
            if generator_output is None:
                return
            sample = payload.get("sample")
            metrics = payload.get("environment_metrics") or {}
            bullet_metadata = payload.get("bullet_metadata")
            bullet_ids = list(getattr(generator_output, "bullet_ids", []))
            if not bullet_ids:
                return
            sample_id = "unknown"
            if hasattr(sample, "metadata") and isinstance(sample.metadata, dict):
                sample_id = str(sample.metadata.get("sample_id") or sample_id)
            if sample_id == "unknown" and hasattr(sample, "question"):
                sample_id = str(sample.question)
            try:
                attribution_analyzer.record_bullet_usage(  # type: ignore[attr-defined]
                    bullet_ids,
                    metrics,
                    sample_id,
                    int(payload.get("epoch") or 0),
                    int(payload.get("step") or 0),
                    bullet_metadata=bullet_metadata,
                )
            except Exception:  # pragma: no cover - attribution is best-effort
                _LOGGER.exception("Failed to record bullet usage via hook.")

        hooks.append(
            HookMatcher(
                event="environment_feedback",
                callback=_record_generator_usage,
                description="Capture generator bullet usage after feedback",
            )
        )

    if interaction_tracer is not None:

        def _trace_interaction(event: str, payload: Dict[str, Any]) -> None:
            if event != "post_tool_use":
                return
            sample = payload.get("sample")
            agent = payload.get("agent")
            if agent not in {"ace-generator", "ace-reflector", "ace-curator"}:
                return
            try:
                interaction_tracer.log_event(  # type: ignore[attr-defined]
                    agent=agent,
                    event=event,
                    payload=payload,
                )
            except AttributeError:
                # Older tracer implementations might not expose log_event; ignore silently.
                _LOGGER.debug("Interaction tracer does not support log_event; skipping.")
            except Exception:  # pragma: no cover - tracing is optional best-effort
                _LOGGER.exception("Failed to forward hook payload to interaction tracer.")

        hooks.append(
            HookMatcher(
                event="post_tool_use",
                callback=_trace_interaction,
                description="Log ACE role traffic to the interaction tracer",
            )
        )

    if not hooks:

        def _log_fallback(event: str, payload: Dict[str, Any]) -> None:
            _LOGGER.debug("Claude hook emitted event=%s payload=%s", event, payload)

        hooks.append(HookMatcher(event="post_tool_use", callback=_log_fallback))

    return hooks


__all__ = ["HookMatcher", "build_explainability_hooks", "HookCallback"]
