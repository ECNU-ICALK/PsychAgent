"""Core evaluation orchestration for PsychAgent ``eval`` workflows."""

from __future__ import annotations

import asyncio
import json
import re
import traceback
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..core import (
    ConfigValidationError,
    EvalRuntimeConfig,
    EvaluationSummary,
    GPT5ChatClient,
    MethodExecution,
    SessionRunResult,
)
from ..core.base import EvaluationMethod
from ..io.input_adapter import adapt_eval_case_file
from ..methods import METHOD_REGISTRY

try:
    from src.shared.file_utils import load_json_if_exists, safe_filename, write_json_atomic
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
    from shared.file_utils import load_json_if_exists, safe_filename, write_json_atomic

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", flags=re.S | re.IGNORECASE)
_CASE_ID_RE = re.compile(r"case-(\d+)_rep\d+")


@dataclass(frozen=True)
class _CaseDescriptor:
    path: Path
    name: str
    modality: Optional[str]


class EvaluationOrchestrator:
    """Coordinate eval cases, sessions and method execution."""

    def __init__(self, config: EvalRuntimeConfig) -> None:
        self.config = config.validated()
        self._client = GPT5ChatClient(
            api_key=self.config.api_key,
            base_url=self.config.api_base_url,
            model=self.config.api_model,
            max_concurrency=self.config.api_concurrency,
            rps=self.config.api_rps,
            rps_period=self.config.api_rps_period,
        )
        self._file_locks: dict[Path, asyncio.Lock] = {}
        self._data_root = Path(self.config.data_root).expanduser().resolve()
        self._output_root = Path(self.config.output_root).expanduser().resolve()

    @property
    def data_root(self) -> Path:
        return self._data_root

    @property
    def output_root(self) -> Path:
        return self._output_root

    async def close(self) -> None:
        await self._client.aclose()

    async def run(self) -> EvaluationSummary:
        """Run the whole evaluation pipeline and return a compact summary."""
        case_list = list(self.discover_cases())
        if not case_list:
            raise RuntimeError(f"No eval case found under data_root={self._data_root}")

        case_tasks: list[asyncio.Task[List[SessionRunResult]]] = []
        file_semaphore = asyncio.Semaphore(max(1, self.config.file_concurrency))

        async def _run_one_case(case: _CaseDescriptor) -> List[SessionRunResult]:
            async with file_semaphore:
                return await self._evaluate_case(case)

        for case in case_list:
            case_tasks.append(asyncio.create_task(_run_one_case(case), name=f"case:{case.name}"))

        results: list[SessionRunResult] = []
        for task in asyncio.as_completed(case_tasks):
            case_result = await task
            results.extend(case_result)

        summary = EvaluationSummary(
            total_files=len(case_list),
            completed=len([r for r in results if r.status == "completed"]),
            failed=len([r for r in results if r.status != "completed"]),
            results=[r.__dict__ for r in results],
        )

        await self._safe_write_json(self.output_root / "evaluation_summary.json", summary.__dict__)
        return summary

    def discover_cases(self) -> List[_CaseDescriptor]:
        """Find and normalize all case files under data_root."""
        if not self._data_root.exists():
            raise RuntimeError(f"data_root does not exist: {self._data_root}")
        if not self._data_root.is_dir() and self._data_root.suffix.lower() != ".json":
            raise RuntimeError(f"data_root must be a directory or .json file: {self._data_root}")

        selected_modalities = self._normalize_str_list(self.config.modalities)
        supported_modalities = self._normalize_str_list(self.config.supported_modalities)
        known_modalities = list(dict.fromkeys([*selected_modalities, *supported_modalities]))
        target_modalities = [m for m in selected_modalities if m] or [m for m in supported_modalities if m]

        selected_files = self._normalize_str_list(self.config.selected_files)

        if self._data_root.is_file():
            case = self._descriptor_for_single_file(
                self._data_root,
                known_modalities=known_modalities,
                target_modalities=target_modalities,
                supported_modalities=supported_modalities,
            )
            return self._filter_and_limit_cases([case], selected_files)

        descriptors: list[_CaseDescriptor] = []
        if target_modalities:
            for modality in target_modalities:
                modality_root = self._data_root / modality
                if modality_root.is_dir():
                    descriptors.extend(self._collect_cases_from_directory(modality_root, modality, known_modalities))

        if not descriptors:
            descriptors.extend(self._collect_cases_from_directory(self._data_root, None, known_modalities))

        if not descriptors:
            return []

        unique = {c.path: c for c in descriptors}.values()
        sorted_cases = sorted(unique, key=lambda c: self._case_sort_key(c))
        return self._filter_and_limit_cases(list(sorted_cases), selected_files)

    async def _evaluate_case(self, case: _CaseDescriptor) -> List[SessionRunResult]:
        adapted_case = adapt_eval_case_file(case.path, input_format=self.config.input_format)
        case_name = adapted_case.case_name or case.name
        case_data = adapted_case.payload
        sessions = case_data.get("sessions")
        if not isinstance(sessions, list):
            raise RuntimeError(f"{case.path}: invalid sessions format")

        profile = case_data.get("client_info", {})
        if not isinstance(profile, dict):
            profile = {}
        profile = self._normalize_profile(profile)
        global_plan = case_data.get("global_plan")
        normalized_modality = str(case_data.get("theoretical") or "").strip().lower()
        case_modality = normalized_modality or case.modality
        normalized_case = _CaseDescriptor(path=case.path, name=case_name, modality=case_modality)

        case_id = self._get_case_identifier(case_data, normalized_case)
        output_root = self._case_output_root(normalized_case)

        case_results: list[SessionRunResult] = []
        for index, session in enumerate(sessions):
            if not isinstance(session, dict):
                continue
            session_number = _safe_session_number(session.get("session_number"), index + 1)
            session_dialogue = self._extract_dialogue(session.get("session_dialogue"))
            if not session_dialogue:
                continue

            formatted_dialogue = self._format_dialogue(session_dialogue)
            scale_dir = output_root / "scale_results" / f"{case.name}_session{session_number}"
            summary_path = output_root / f"{case.name}_session{session_number}.json"

            if self.config.resume and summary_path.exists():
                summary_record = load_json_if_exists(summary_path)
                if summary_record and summary_record.get("status") == "completed":
                    case_results.append(self._replay_session_result(case, summary_record, case_id))
                    continue

            method_names = self._resolve_method_names(normalized_case.modality)
            try:
                evaluation_results, method_status, method_errors, missing = await self._evaluate_session_with_methods(
                    normalized_case,
                    case_id,
                    session_number,
                    formatted_dialogue,
                    profile,
                    global_plan,
                    scale_dir,
                    method_names,
                )
                status = "completed" if not missing else "incomplete"
                summary = SessionRunResult(
                    case_name=normalized_case.name,
                    case_number=case_id,
                    case_path=str(case.path),
                    session_number=session_number,
                    session_file=f"session_{session_number}",
                    status=status,
                    evaluation_results=evaluation_results,
                    method_status=method_status,
                    method_errors=method_errors,
                    missing_methods=missing,
                    scale_results_dir=str(scale_dir),
                    completed_at=self._iso_now() if status == "completed" else None,
                    model_name=self.config.api_model,
                    thread_id=self._current_task_name(),
                )
                if status == "completed":
                    await self._safe_write_json(summary_path, summary.__dict__)
                elif self.config.overwrite:
                    await self._safe_write_json(summary_path, summary.__dict__)

                case_results.append(summary)
            except Exception as exc:  # noqa: BLE001
                failed = SessionRunResult(
                    case_name=normalized_case.name,
                    case_number=case_id,
                    case_path=str(case.path),
                    session_number=session_number,
                    session_file=f"session_{session_number}",
                    status="failed",
                    evaluation_results={},
                    method_status={},
                    method_errors={
                        "exception": {
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        }
                    },
                    missing_methods=method_names,
                    scale_results_dir=str(scale_dir),
                    model_name=self.config.api_model,
                    thread_id=self._current_task_name(),
                )
                await self._safe_write_json(summary_path, failed.__dict__)
                case_results.append(failed)

        return case_results

    async def _evaluate_session_with_methods(
        self,
        case: _CaseDescriptor,
        case_id: str,
        session_number: int,
        dialogue: str,
        profile: Dict[str, Any],
        global_plan: Any,
        scale_dir: Path,
        method_names: List[str],
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, Dict[str, Any]], List[str]]:
        """Evaluate one session with selected methods."""
        if not method_names:
            return {}, {}, {}, []

        method_instances = self._instantiate_methods(method_names)

        skip_methods: Set[str] = set()
        if self.config.resume:
            skip_methods = self._load_completed_methods(scale_dir)

        methods_to_run = [m for m in method_instances if m.get_name() not in skip_methods]

        results_by_name: Dict[str, MethodExecution] = {}
        method_eval: Dict[str, Dict[str, Any]] = {}
        method_status: Dict[str, str] = {}
        method_errors: Dict[str, Dict[str, Any]] = {}
        missing: List[str] = []

        if self.config.output_root:
            scale_dir.mkdir(parents=True, exist_ok=True)

        semaphore = asyncio.Semaphore(max(1, self.config.method_concurrency))

        async def _run_one(method: EvaluationMethod) -> MethodExecution:
            async with semaphore:
                method_name = method.get_name()
                start_at = self._iso_now()
                raw_outputs: list[str] = []

                class _LoggedChatClient:
                    def __init__(self, base: GPT5ChatClient, outputs: list[str]) -> None:
                        self._base = base
                        self._outputs = outputs
                        self.model = getattr(base, "model", "")

                    async def chat_text(self, *args: Any, **kwargs: Any) -> str:
                        output = await self._base.chat_text(*args, **kwargs)
                        self._outputs.append(output)
                        return output

                    def __getattr__(self, item: str) -> Any:
                        return getattr(self._base, item)

                try:
                    method_profile = self._build_method_profile(profile, global_plan, method_name)
                    output_client = _LoggedChatClient(self._client, raw_outputs)
                    scores = await method.evaluate(output_client, dialogue, method_profile)
                    if not isinstance(scores, dict):
                        raise TypeError(f"{method_name}.evaluate() returned non-dict: {type(scores)!r}")
                    return MethodExecution(
                        method_name=method_name,
                        status="completed",
                        scores=scores,
                        raw_model_outputs=raw_outputs,
                        started_at=start_at,
                        finished_at=self._iso_now(),
                        thread_name=self._current_task_name(),
                        model_name=self.config.api_model,
                    )
                except Exception as exc:  # noqa: BLE001
                    return MethodExecution(
                        method_name=method_name,
                        status="failed",
                        scores={},
                        error=str(exc),
                        traceback=traceback.format_exc(),
                        raw_model_outputs=raw_outputs,
                        started_at=start_at,
                        finished_at=self._iso_now(),
                        thread_name=self._current_task_name(),
                        model_name=self.config.api_model,
                    )

        tasks = [asyncio.create_task(_run_one(m)) for m in methods_to_run]
        for task in asyncio.as_completed(tasks):
            record = await task
            method_path = scale_dir / f"{safe_filename(record.method_name)}.json"
            if self.config.output_root:
                await self._safe_write_json(method_path, record.__dict__)
            results_by_name[record.method_name] = record

        for name in method_names:
            method_record = results_by_name.get(name)
            if name in skip_methods:
                method_status[name] = "completed"
                continue

            if method_record is None:
                method_status[name] = "skipped"
                missing.append(name)
                continue

            method_status[name] = method_record.status
            if method_record.status == "completed":
                for dimension, value in (method_record.scores or {}).items():
                    if isinstance(value, dict):
                        continue
                    method_eval.setdefault(dimension, {})[name] = value
            else:
                method_errors[name] = {
                    "error": method_record.error,
                    "traceback": method_record.traceback,
                }
                missing.append(name)

        return method_eval, method_status, method_errors, missing

    def _aggregate_scale_results(
        self,
        scale_dir: Path,
        method_names: List[str],
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, Dict[str, Any]], List[str]]:
        evaluation_results: Dict[str, Dict[str, Any]] = {}
        method_status: Dict[str, str] = {}
        method_errors: Dict[str, Dict[str, Any]] = {}
        missing: List[str] = []

        for method_name in method_names:
            path = scale_dir / f"{safe_filename(method_name)}.json"
            data = load_json_if_exists(path)
            if not data:
                method_status[method_name] = "missing"
                missing.append(method_name)
                continue

            status = str(data.get("status") or "unknown")
            method_status[method_name] = status
            if status != "completed":
                method_errors[method_name] = {
                    "error": data.get("error"),
                    "traceback": data.get("traceback"),
                }
                missing.append(method_name)
                continue

            scores = data.get("scores")
            if not isinstance(scores, dict):
                method_status[method_name] = "failed"
                method_errors[method_name] = {"error": "invalid scores payload"}
                missing.append(method_name)
                continue

            for key, value in scores.items():
                if isinstance(value, dict):
                    continue
                evaluation_results.setdefault(key, {})[method_name] = value

        return evaluation_results, method_status, method_errors, missing

    def _load_completed_methods(self, scale_dir: Path) -> Set[str]:
        if not self.config.resume or not scale_dir.exists():
            return set()
        completed: Set[str] = set()
        for method_name in METHOD_REGISTRY:
            data = load_json_if_exists(scale_dir / f"{safe_filename(method_name)}.json")
            if data and data.get("status") == "completed":
                completed.add(str(data.get("method_name") or method_name))
        return completed

    def _resolve_method_names(self, modality: Optional[str]) -> List[str]:
        if self.config.method_names:
            return list(dict.fromkeys(self.config.method_names))

        method_by_modality = self.config.method_by_modality or {}
        if modality:
            configured = method_by_modality.get(modality)
            if configured:
                return list(dict.fromkeys(configured))

        return list(METHOD_REGISTRY.keys())

    def _instantiate_methods(self, method_names: List[str]) -> List[EvaluationMethod]:
        registry = _build_method_by_effective_name()
        methods: list[EvaluationMethod] = []
        for name in method_names:
            cls = registry.get(name)
            if cls is None:
                available = ", ".join(sorted(registry.keys()))
                raise ConfigValidationError(f"Unknown eval method {name!r}, available: {available}")
            methods.append(cls())
        return methods

    def _build_method_profile(self, profile: Dict[str, Any], global_plan: Any, method_name: str) -> Optional[Dict[str, Any]]:
        if method_name in {
            "PersonaConsistency",
            "OverallGoalConsistency",
            "ProcessDetailConsistency",
            "TreatmentOutcomeConsistency",
        }:
            return {"global_plan": global_plan}
        return profile

    def _normalize_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(profile)
        if "growth_experience" in normalized and "growth_experiences" not in normalized:
            normalized["growth_experiences"] = normalized["growth_experience"]
        if "growth_experiences" in normalized and not normalized.get("growth_experiences"):
            normalized["growth_experiences"] = []
        return normalized

    def _extract_dialogue(self, turn_list: Any) -> List[Dict[str, Any]]:
        if not isinstance(turn_list, list):
            return []
        dialogue: list[Dict[str, Any]] = []
        for turn in turn_list:
            if not isinstance(turn, dict):
                continue
            role = str(turn.get("role", "")).strip().lower()
            if role == "system":
                continue
            content = turn.get("text")
            if content is None:
                content = turn.get("content")
            if content is None:
                message = turn.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
            if not content:
                continue
            text = str(content).strip()
            if not text:
                continue
            dialogue.append({"role": role, "text": text})
        return dialogue

    def _format_dialogue(self, session_dialogue: List[Dict[str, Any]]) -> str:
        lines: list[str] = []
        for turn in session_dialogue:
            role = str(turn.get("role", "")).strip().lower()
            content = _strip_think(str(turn.get("text", "")))
            if role in {"assistant", "counselor", "therapist"}:
                lines.append(f"counselor: {content}")
            elif role in {"client", "user", "human"}:
                lines.append(f"client: {content}")
        return "\n".join(lines).replace("</end>", "").strip()

    def _case_output_root(self, case: _CaseDescriptor) -> Path:
        root = self.output_root
        return root / (case.modality or "all") / case.name

    def _case_sort_key(self, case: _CaseDescriptor) -> tuple[str, object]:
        try:
            return (case.modality or "", int(case.name))
        except ValueError:
            return (case.modality or "", case.name)

    def _replay_session_result(self, case: _CaseDescriptor, record: Dict[str, Any], case_id: str) -> SessionRunResult:
        return SessionRunResult(
            case_name=case.name,
            case_number=case_id,
            case_path=str(case.path),
            session_number=int(record.get("session_number", 1)),
            session_file=record.get("session_file", "session_1"),
            status="completed",
            evaluation_results=record.get("evaluation_results", {}),
            method_status=record.get("method_status", {}),
            method_errors=record.get("method_errors", {}),
            missing_methods=record.get("missing_methods", []),
            scale_results_dir=record.get("scale_results_dir"),
            completed_at=record.get("completed_at"),
            model_name=record.get("model_name"),
            thread_id=record.get("thread_id"),
        )

    def _collect_cases_from_directory(
        self,
        root: Path,
        default_modality: Optional[str],
        known_modalities: List[str],
    ) -> List[_CaseDescriptor]:
        descriptors: list[_CaseDescriptor] = []
        sample_course_dirs: Set[Path] = set()
        if self.config.input_format in {"auto", "sample"}:
            for course_path in root.rglob("course.json"):
                if course_path.is_file():
                    sample_course_dirs.add(course_path.parent)

        for path in sorted(root.rglob("*.json")):
            if not path.is_file():
                continue
            # Avoid recursively treating eval outputs as new input cases when output_root
            # is configured under data_root.
            try:
                path.relative_to(self.output_root)
                continue
            except ValueError:
                pass
            if path == self.output_root:
                continue

            if self.config.input_format == "eval_case":
                if path.name == "course.json" or path.stem.startswith("session_"):
                    continue
            elif self.config.input_format in {"auto", "sample"}:
                if path.stem.startswith("session_") and path.parent in sample_course_dirs:
                    # course.json is the canonical sample case descriptor for this case dir.
                    continue
                if self.config.input_format == "sample" and not (
                    path.name == "course.json" or path.stem.startswith("session_")
                ):
                    continue

            if path.name == "course.json" or path.stem.startswith("session_"):
                case_name = path.parent.name
            else:
                case_name = path.stem
            modality = default_modality
            if modality is None:
                try:
                    relative = path.relative_to(root)
                    modality = _infer_modality_from_parts(relative.parts, known_modalities)
                except ValueError:
                    modality = None
            descriptors.append(_CaseDescriptor(path=path, name=case_name, modality=modality))
        return descriptors

    def _descriptor_for_single_file(
        self,
        path: Path,
        *,
        known_modalities: List[str],
        target_modalities: List[str],
        supported_modalities: List[str],
    ) -> _CaseDescriptor:
        if path.name == "course.json" or path.stem.startswith("session_"):
            case_name = path.parent.name
        else:
            case_name = path.stem

        modality = _infer_modality_from_path(path.parent.name, target_modalities, supported_modalities)
        if modality is None:
            modality = _infer_modality_from_parts(path.parts, known_modalities)
        return _CaseDescriptor(path=path, name=case_name, modality=modality)

    @staticmethod
    def _get_case_identifier(case_data: Dict[str, Any], case: _CaseDescriptor) -> str:
        client_info = case_data.get("client_info", {})
        if isinstance(client_info, dict):
            raw_id = client_info.get("client_id") or client_info.get("clientId")
            if isinstance(raw_id, (str, int)) and str(raw_id).strip():
                return str(raw_id).strip()

        match = _CASE_ID_RE.match(case.name)
        if match:
            return match.group(1)
        return case.name

    def _load_case_json(self, path: Path) -> Dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"failed to load eval case json {path}: {exc}") from exc

    def _filter_and_limit_cases(self, cases: List[_CaseDescriptor], selected_files: Optional[List[str]]) -> List[_CaseDescriptor]:
        if selected_files:
            normalized = {item if item.endswith(".json") else f"{item}.json" for item in selected_files}
            cases = [case for case in cases if case.path.name in normalized]

        if self.config.case_limit is not None:
            return cases[: int(self.config.case_limit)]
        return cases

    async def _safe_write_json(self, path: Path, data: Dict[str, Any]) -> None:
        lock = self._file_locks.get(path)
        if lock is None:
            lock = asyncio.Lock()
            self._file_locks[path] = lock
        async with lock:
            write_json_atomic(path, data)

    @staticmethod
    def _normalize_str_list(value: Optional[List[str]]) -> List[str]:
        if value is None:
            return []
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out

    @staticmethod
    def _current_task_name() -> str:
        task = asyncio.current_task()
        return task.get_name() if task else "main"

    @staticmethod
    def _iso_now() -> str:
        return datetime.now().isoformat(timespec="seconds")


def _infer_modality_from_path(candidate: str, target_modalities: List[str], supported_modalities: List[str]) -> Optional[str]:
    if candidate and (candidate in target_modalities or candidate in supported_modalities):
        return candidate
    return None


def _infer_modality_from_parts(parts: Any, known_modalities: List[str]) -> Optional[str]:
    normalized_known = {str(item).strip().lower() for item in known_modalities if str(item).strip()}
    if not normalized_known:
        return None
    for item in parts:
        text = str(item).strip().lower()
        if text in normalized_known:
            return text
    return None


def _safe_session_number(raw_value: Any, default_index: int) -> int:
    try:
        idx = int(raw_value)
        if idx > 0:
            return idx
    except Exception:
        pass
    return default_index


def _strip_think(text: str) -> str:
    cleaned = _THINK_TAG_RE.sub("", text)
    return cleaned.replace("  ", " ").strip()


def _build_method_by_effective_name() -> Dict[str, Any]:
    by_name: Dict[str, Any] = {}
    for cls in METHOD_REGISTRY.values():
        by_name[cls.__name__] = cls
        try:
            effective_name = cls().get_name()
            by_name.setdefault(effective_name, cls)
        except Exception:
            # fallback to class name only
            continue
    return by_name
