"""Dataset loader following PsychAgent case-file contract."""

from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.schemas import ClientCase, DatasetConfig

_PUBLIC_HARD_FIELDS: Dict[str, type] = {
    "static_traits": dict,
    "main_problem": str,
    "topic": str,
    "core_demands": str,
    "growth_experiences": list,
}

_MODALITY_HARD_FIELDS: Dict[str, Dict[str, type]] = {
    "bt": {
        "target_behavior": list,
    },
    "cbt": {
        "core_beliefs": list,
        "special_situations": list,
    },
    "het": {
        "existentialism_topic": list,
        "contact_model": list,
    },
    "pdt": {
        "core_conflict": dict,
        "object_relations": list,
        "behavioral_response_patterns": list,
    },
    "pmt": {
        "exception_events": list,
        "force_field": dict,
    },
}

_CBT_SPECIAL_REQUIRED_FIELDS = (
    "event",
    "conditional_assumptions",
    "compensatory_strategies",
    "automatic_thoughts",
    "cognitive_pattern",
)


class DatasetLoader:
    """Enumerate and parse case JSON files for baseline evaluation."""

    def __init__(self, config: DatasetConfig, *, logger: Optional[logging.Logger] = None) -> None:
        self._config = config
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def load_cases(self, *, seed: Optional[int] = None) -> List[ClientCase]:
        files_by_modality = self._enumerate_files_by_modality()
        rng = random.Random(seed)

        selected_files: List[Path] = []
        for modality in self._config.supported_modalities:
            modality_files = list(files_by_modality.get(modality, []))
            if self._config.case_selection_strategy == "random":
                rng.shuffle(modality_files)

            if self._config.max_cases_per_modality is not None:
                modality_files = modality_files[: self._config.max_cases_per_modality]

            selected_files.extend(modality_files)

        if self._config.case_selection_strategy == "sequential":
            selected_files = self._sort_files(selected_files)
        if self._config.max_cases is not None:
            selected_files = selected_files[: self._config.max_cases]

        return [self._load_case_file(path) for path in selected_files]

    def _enumerate_files_by_modality(self) -> Dict[str, List[Path]]:
        root = Path(self._config.root_data_path)
        files_by_modality: Dict[str, List[Path]] = defaultdict(list)

        for modality in self._config.supported_modalities:
            split_dir = root / modality / self._config.split
            if not split_dir.exists():
                self._logger.warning("dataset split directory not found: %s", split_dir)
                continue
            modality_files = list(split_dir.glob("*.json"))
            files_by_modality[modality] = self._sort_files(modality_files)

        return files_by_modality

    def _sort_files(self, files: List[Path]) -> List[Path]:
        is_desc = (self._config.filename_sort_policy == "stem_desc")

        def _stem_sort_key(path: Path) -> tuple[int, str | int]:
            stem = path.stem
            try:
                return (0, int(stem))
            except ValueError:
                return (1, stem)

        files = sorted(
            files, 
            key=lambda p: _stem_sort_key(p), 
            reverse=is_desc
        )
        return files

    def _load_case_file(self, path: Path) -> ClientCase:
        modality = path.parent.parent.name
        case_id = path.stem

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed json file: {path}") from exc

        if not isinstance(raw, dict):
            raise ValueError(f"case json must be object: {path}")

        basic_info = raw.get("basic_info", {})
        if not isinstance(basic_info, dict):
            basic_info = {}

        theory_root = raw.get("theory", {})
        if not isinstance(theory_root, dict):
            theory_root = {}
        theory_info = theory_root.get(modality, {})
        if not isinstance(theory_info, dict):
            theory_info = {}

        if modality not in theory_root:
            self._logger.warning(
                "missing modality-specific theory info for case=%s modality=%s file=%s",
                case_id,
                modality,
                path,
            )

        theory_info = _normalize_theory_info(theory_info, modality=modality, path=path)
        _validate_public_profile_fields(basic_info=basic_info, theory_info=theory_info, modality=modality, path=path)
        _validate_modality_profile_fields(theory_info=theory_info, modality=modality, path=path)

        return ClientCase(
            case_id=case_id,
            modality=modality,
            basic_info=basic_info,
            theory_info=theory_info,
        )


def _normalize_theory_info(theory_info: Dict[str, Any], *, modality: str, path: Path) -> Dict[str, Any]:
    normalized = dict(theory_info)
    if modality == "cbt":
        raw_situations = normalized.get("special_situations", [])
        if isinstance(raw_situations, list):
            fixed_items: List[Dict[str, Any]] = []
            for idx, item in enumerate(raw_situations):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"{path}: cbt.special_situations[{idx}] must be object, got {type(item)!r}"
                    )
                fixed = dict(item)
                for field_name in _CBT_SPECIAL_REQUIRED_FIELDS:
                    value = fixed.get(field_name)
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(
                            f"{path}: cbt.special_situations[{idx}].{field_name} must be non-empty string"
                        )
                progress = fixed.get("progress")
                if not isinstance(progress, str) or not progress.strip():
                    fixed["progress"] = "待解决"
                analysis = fixed.get("analysis")
                if not isinstance(analysis, list):
                    fixed["analysis"] = []
                else:
                    fixed["analysis"] = [str(entry) for entry in analysis if str(entry).strip()]
                fixed_items.append(fixed)
            normalized["special_situations"] = fixed_items
    return normalized


def _validate_public_profile_fields(
    *,
    basic_info: Dict[str, Any],
    theory_info: Dict[str, Any],
    modality: str,
    path: Path,
) -> None:
    merged = dict(basic_info)
    merged.update(theory_info)
    for field_name, expected_type in _PUBLIC_HARD_FIELDS.items():
        value = merged.get(field_name)
        if not isinstance(value, expected_type):
            raise ValueError(
                f"{path}: {modality} public field {field_name!r} must be {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        if expected_type is str and not value.strip():
            raise ValueError(f"{path}: {modality} public field {field_name!r} must be non-empty string")


def _validate_modality_profile_fields(*, theory_info: Dict[str, Any], modality: str, path: Path) -> None:
    required = _MODALITY_HARD_FIELDS.get(modality)
    if not required:
        return

    for field_name, expected_type in required.items():
        value = theory_info.get(field_name)
        if not isinstance(value, expected_type):
            raise ValueError(
                f"{path}: theory[{modality!r}].{field_name} must be {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )

    if modality == "bt":
        _validate_bt_target_behavior(theory_info["target_behavior"], path=path)
    elif modality == "cbt":
        _validate_cbt_profile(theory_info, path=path)
    elif modality == "het":
        _validate_het_profile(theory_info, path=path)
    elif modality == "pdt":
        _validate_pdt_profile(theory_info, path=path)
    elif modality == "pmt":
        _validate_pmt_profile(theory_info, path=path)


def _validate_bt_target_behavior(items: List[Any], *, path: Path) -> None:
    required = ("behavior", "antecedent", "core_reason", "function", "consequence")
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: bt.target_behavior[{idx}] must be object, got {type(item)!r}")
        for key in required:
            if key not in item:
                raise ValueError(f"{path}: bt.target_behavior[{idx}] missing required field {key!r}")
        _ensure_non_empty_string(item["behavior"], path=path, field=f"bt.target_behavior[{idx}].behavior")
        _ensure_string_list(item["antecedent"], path=path, field=f"bt.target_behavior[{idx}].antecedent")
        _ensure_non_empty_string(item["core_reason"], path=path, field=f"bt.target_behavior[{idx}].core_reason")
        _ensure_non_empty_string(item["function"], path=path, field=f"bt.target_behavior[{idx}].function")
        _ensure_non_empty_string(item["consequence"], path=path, field=f"bt.target_behavior[{idx}].consequence")


def _validate_cbt_profile(theory_info: Dict[str, Any], *, path: Path) -> None:
    _ensure_string_list(theory_info["core_beliefs"], path=path, field="cbt.core_beliefs")
    for idx, item in enumerate(theory_info["special_situations"]):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: cbt.special_situations[{idx}] must be object, got {type(item)!r}")
        for key in _CBT_SPECIAL_REQUIRED_FIELDS:
            if key not in item:
                raise ValueError(f"{path}: cbt.special_situations[{idx}] missing required field {key!r}")
            _ensure_non_empty_string(item[key], path=path, field=f"cbt.special_situations[{idx}].{key}")


def _validate_het_profile(theory_info: Dict[str, Any], *, path: Path) -> None:
    for idx, item in enumerate(theory_info["existentialism_topic"]):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: het.existentialism_topic[{idx}] must be object, got {type(item)!r}")
        for key in ("theme", "manifestations", "outcomes"):
            if key not in item:
                raise ValueError(f"{path}: het.existentialism_topic[{idx}] missing required field {key!r}")
        _ensure_non_empty_string(item["theme"], path=path, field=f"het.existentialism_topic[{idx}].theme")
        _ensure_string_list(
            item["manifestations"],
            path=path,
            field=f"het.existentialism_topic[{idx}].manifestations",
        )
        _ensure_string_list(item["outcomes"], path=path, field=f"het.existentialism_topic[{idx}].outcomes")

    for idx, item in enumerate(theory_info["contact_model"]):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: het.contact_model[{idx}] must be object, got {type(item)!r}")
        for key in ("mode", "definition", "manifestations"):
            if key not in item:
                raise ValueError(f"{path}: het.contact_model[{idx}] missing required field {key!r}")
        _ensure_non_empty_string(item["mode"], path=path, field=f"het.contact_model[{idx}].mode")
        _ensure_non_empty_string(item["definition"], path=path, field=f"het.contact_model[{idx}].definition")
        _ensure_string_list(item["manifestations"], path=path, field=f"het.contact_model[{idx}].manifestations")


def _validate_pdt_profile(theory_info: Dict[str, Any], *, path: Path) -> None:
    core_conflict = theory_info["core_conflict"]
    if not isinstance(core_conflict, dict):
        raise ValueError(f"{path}: pdt.core_conflict must be object, got {type(core_conflict)!r}")
    for key in ("wish", "fear", "defense_goal"):
        if key not in core_conflict:
            raise ValueError(f"{path}: pdt.core_conflict missing required field {key!r}")
    _ensure_non_empty_string(core_conflict["wish"], path=path, field="pdt.core_conflict.wish")
    _ensure_non_empty_string(core_conflict["fear"], path=path, field="pdt.core_conflict.fear")
    _ensure_string_list(core_conflict["defense_goal"], path=path, field="pdt.core_conflict.defense_goal")

    for idx, item in enumerate(theory_info["object_relations"]):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: pdt.object_relations[{idx}] must be object, got {type(item)!r}")
        for key in ("self_representation", "object_representation", "linking_affect"):
            if key not in item:
                raise ValueError(f"{path}: pdt.object_relations[{idx}] missing required field {key!r}")
            _ensure_non_empty_string(item[key], path=path, field=f"pdt.object_relations[{idx}].{key}")

    for idx, item in enumerate(theory_info["behavioral_response_patterns"]):
        if not isinstance(item, dict):
            raise ValueError(
                f"{path}: pdt.behavioral_response_patterns[{idx}] must be object, got {type(item)!r}"
            )
        for key in (
            "trigger_condition",
            "interpretation",
            "defense_mechanism",
            "response_instruction",
        ):
            if key not in item:
                raise ValueError(
                    f"{path}: pdt.behavioral_response_patterns[{idx}] missing required field {key!r}"
                )
            _ensure_non_empty_string(item[key], path=path, field=f"pdt.behavioral_response_patterns[{idx}].{key}")


def _validate_pmt_profile(theory_info: Dict[str, Any], *, path: Path) -> None:
    for idx, item in enumerate(theory_info["exception_events"]):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: pmt.exception_events[{idx}] must be object, got {type(item)!r}")
        for key in ("target_problem", "unique_outcome", "reason"):
            if key not in item:
                raise ValueError(f"{path}: pmt.exception_events[{idx}] missing required field {key!r}")
            _ensure_non_empty_string(item[key], path=path, field=f"pmt.exception_events[{idx}].{key}")

    force_field = theory_info["force_field"]
    if not isinstance(force_field, dict):
        raise ValueError(f"{path}: pmt.force_field must be object, got {type(force_field)!r}")
    for key in ("positive_force", "negative_force"):
        if key not in force_field:
            raise ValueError(f"{path}: pmt.force_field missing required field {key!r}")
        _ensure_string_list(force_field[key], path=path, field=f"pmt.force_field.{key}")


def _ensure_non_empty_string(value: Any, *, path: Path, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {field} must be non-empty string")


def _ensure_string_list(value: Any, *, path: Path, field: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{path}: {field} must be list[str], got {type(value)!r}")
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{path}: {field}[{idx}] must be non-empty string")
