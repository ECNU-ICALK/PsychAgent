from __future__ import annotations

import asyncio
import copy
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

try:
    from jinja2 import Template
except ImportError:  # pragma: no cover
    Template = None  # type: ignore[assignment]

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment]

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]

try:
    from src.shared.file_utils import resolve_path
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
    from shared.file_utils import resolve_path

from .backends.base import ModelBackend
from .core.schemas import RuntimeConfig
from .utils import extract_tag_content


STAGE_MAP: Dict[str, int] = {
    "问题概念化与目标设定": 1,
    "核心认知与行为干预": 2,
    "巩固与复发预防": 3,
}
DEFAULT_SECTS = ["cbt", "bt", "pdt", "het", "pmt"]


@dataclass
class LoadedSkillStage:
    meta: Dict[str, Dict[str, Any]]
    micro: Dict[str, Dict[str, Any]]
    leaf: Dict[str, Dict[str, Any]]


class SkillManager:
    def __init__(self, backend: ModelBackend, runtime_config: RuntimeConfig, logger: Optional[logging.Logger] = None):
        self._backend = backend
        self._runtime = runtime_config
        self._logger = logger or logging.getLogger(self.__class__.__name__)

        self.skill_lib: Dict[str, Dict[str, LoadedSkillStage]] = {}
        self._embedding_client: Any = None

        self._select_system_prompt = ""
        self._select_user_prompt = ""
        self._rewrite_system_prompt = ""
        self._rewrite_user_prompt = ""

    async def _ensure_embeddings_for_all(self, micro_lib: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], bool]:
        if not micro_lib:
            return micro_lib, False

        updated = False
        missing_merge_ids = []
        missing_retrieve_ids = []

        # 1. 扫描缺失情况并统一格式
        for sid, skill in micro_lib.items():
            # 确保已经是 list 格式，方便后续处理
            m_vec = self._vector_to_list(skill.get("embedding_to_merge"))
            r_vec = self._vector_to_list(skill.get("embedding_to_retrive"))
            
            if m_vec is None:
                missing_merge_ids.append(sid)
            else:
                skill["embedding_to_merge"] = m_vec # 统一存为 list

            if r_vec is None:
                missing_retrieve_ids.append(sid)
            else:
                skill["embedding_to_retrive"] = r_vec

        # 2. 补齐用于合并的向量 (Merge Embedding)
        if missing_merge_ids:
            self._logger.info(f"Backfilling {len(missing_merge_ids)} merge embeddings...")
            texts = [
                json.dumps(
                    {k: v for k, v in micro_lib[sid].items() 
                     if k in {"skill_id", "skill_name", "skill_description", "trigger", "when_to_use", "parent_ids"}},
                    ensure_ascii=False
                )
                for sid in missing_merge_ids
            ]
            embs = await self._embed_by_api(texts)
            for sid, emb in zip(missing_merge_ids, embs):
                micro_lib[sid]["embedding_to_merge"] = emb
            updated = True

        # 3. 补齐用于检索的向量 (Retrieve Embedding)
        if missing_retrieve_ids:
            self._logger.info(f"Backfilling {len(missing_retrieve_ids)} retrieve embeddings...")
            texts = [
                f"Trigger:{micro_lib[sid].get('trigger', '')}\nWhen_to_Use:{micro_lib[sid].get('when_to_use', '')}"
                for sid in missing_retrieve_ids
            ]
            embs = await self._embed_by_api(texts)
            for sid, emb in zip(missing_retrieve_ids, embs):
                micro_lib[sid]["embedding_to_retrive"] = emb
            updated = True

        return micro_lib, updated

    async def load_library(self) -> None:
        # Fail fast at startup: embedding key must be present before any run.
        self._require_embedding_api_key()
        self._load_prompts()

        sects = self._normalize_sects(self._runtime.psychagent_skill_sects)
        base_dir = resolve_path(self._runtime.psychagent_skill_base_dir)

        for sect in sects:
            sect_stages: Dict[str, LoadedSkillStage] = {}
            for stage_idx in (1, 2, 3):
                stage_key = f"stage{stage_idx}"
                stage_dir = base_dir / sect / stage_key
                meta = self._load_json_dict(stage_dir / "meta_skills.json")
                micro = self._load_micro_skills(stage_dir)
                leaf = self.get_leaf_nodes(meta)
                sect_stages[stage_key] = LoadedSkillStage(meta=meta, micro=micro, leaf=leaf)
            self.skill_lib[sect] = sect_stages

        self._logger.info("Skill library loaded, starting embedding check and backfill...")

        # 遍历所有领域 (sect) 和所有阶段 (stage)
        for sect, stages in self.skill_lib.items():
            for stage_key, loaded_stage in stages.items():
                # 检查 micro_skills 是否缺失 embedding
                # 注意：这里调用我们新定义的异步补齐方法
                updated_micro, is_updated = await self._ensure_embeddings_for_all(loaded_stage.micro)

                if is_updated:
                    self._logger.info(f"Updating embeddings for {sect} {stage_key}...")
                    loaded_stage.micro = updated_micro

                    save_dir = resolve_path(self._runtime.psychagent_skill_base_dir) / sect / stage_key
                    save_path = save_dir / "micro_skills.pt"

                    # 使用线程池保存，防止阻塞事件循环
                    if torch is not None:
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(
                            None, lambda: torch.save(loaded_stage.micro, str(save_path))
                        )
                        self._logger.info(f"Saved updated skills to {save_path}")

        self._logger.info("Skill library embedding check complete.")

    async def corse_filter(
        self,
        sect: str,
        session_goals: Any,
        stage: int | str,
        n: int = 20,
        model_kwgs: Optional[Dict[str, Any]] = None,
        saved: bool = False,
        rerank: bool = False,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Tuple[str, str]], Dict[str, Any]]:
        del saved, rerank
        stage_idx = self._resolve_stage(stage)
        stage_key = f"stage{stage_idx}"
        lib = self.skill_lib.get(sect, {})
        loaded_stage = lib.get(stage_key)
        if loaded_stage is None:
            raise ValueError(f"skill stage missing: sect={sect} stage={stage_key}")

        leaf_skills = loaded_stage.leaf
        if not leaf_skills:
            return [], [], [], {"messages": []}

        ids: List[Tuple[str, str]] = []
        select_system_prompt = self._select_system_prompt
        select_user_prompt = self._select_user_prompt
        response = ""

        try:
            if self._select_system_prompt and self._select_user_prompt:
                skill_to_filter = {
                    k: {ik: iv for ik, iv in v.items() if ik not in {"parent_ids", "embedding_to_merge", "embedding_to_retrive"}}
                    for k, v in leaf_skills.items()
                }
                select_system_prompt = self._render_template(self._select_system_prompt, number=n)
                select_user_prompt = self._render_template(
                    self._select_user_prompt,
                    session_goals=session_goals,
                    skills_library=skill_to_filter,
                )
                response = await self.llm_response(select_system_prompt, select_user_prompt, model_kwgs=model_kwgs)
                parsed = self._extract_json_object(response)
                raw_ids = parsed.get("skill_id", []) if isinstance(parsed, dict) else []
                ids = [(sect, str(sid)) for sid in raw_ids]
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._logger.warning("coarse_filter parse failed, fallback to default top skills: %s", exc)

        if not ids:
            fallback_ids = list(leaf_skills.keys())[:n]
            ids = [(sect, str(sid)) for sid in fallback_ids]

        meta_skills, meta_wo_embed = self.find_skill_by_id(stage_idx, ids)

        res = {
            "messages": [
                {"role": "system", "content": select_system_prompt},
                {"role": "user", "content": select_user_prompt},
                {"role": "assistant", "content": response},
            ]
        }
        return meta_skills, meta_wo_embed, ids, res

    async def retrive(
        self,
        sect: str,
        query: str,
        session_stage: int | str,
        session_goals: Any,
        diag_hist: List[Dict[str, str]],
        top_n: int = 20,
        top_k: int = 5,
        threshold: Optional[float] = None,
        candidate_skills: Optional[List[Dict[str, Any]]] = None,
        model_kwgs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        stage_idx = self._resolve_stage(session_stage)

        if candidate_skills is None:
            meta_skills, _, _, _ = await self.corse_filter(
                sect=sect,
                session_goals=session_goals,
                stage=stage_idx,
                n=top_n,
                model_kwgs=model_kwgs,
            )
            candidate_skills = []
            for skill in meta_skills:
                candidate_skills.extend(skill.get("micro_skills", []))

        if not candidate_skills:
            return [], {}

        rewritten_query, res_rewrite = await self.rewrite(
            sect=sect,
            query=query,
            stage=stage_idx,
            session_goals=session_goals,
            diag_hist=diag_hist,
            model_kwgs=model_kwgs,
        )
        query_text = extract_tag_content(rewritten_query, "response") or rewritten_query
        query_embedding = (await self._embed_by_api([query_text]))[0]

        await self._ensure_embeddings_for_candidates(candidate_skills)

        scored: List[Tuple[float, int]] = []
        for idx, skill in enumerate(candidate_skills):
            vec = self._vector_to_list(skill.get("embedding_to_retrive"))
            if not vec:
                continue
            score = self._cosine_similarity(query_embedding, vec)
            if threshold is not None and score < threshold:
                continue
            scored.append((score, idx))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[:top_k]

        retrieved: List[Dict[str, Any]] = []
        for score, idx in selected:
            skill = copy.deepcopy(candidate_skills[idx])
            skill["similarity"] = float(score)
            skill.pop("embedding_to_merge", None)
            skill.pop("embedding_to_retrive", None)
            retrieved.append(skill)

        return retrieved, res_rewrite

    async def rewrite(
        self,
        sect: str,
        query: str,
        stage: int | str,
        session_goals: Any,
        diag_hist: List[Dict[str, str]],
        model_kwgs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        del sect
        rewrite_system_prompt = self._rewrite_system_prompt
        rewrite_user_prompt = self._rewrite_user_prompt

        if not rewrite_user_prompt:
            return query, {"messages": []}

        rendered_user = self._render_template(
            rewrite_user_prompt,
            Session_Goals=session_goals,
            Dialogue_History=diag_hist if diag_hist else "暂无对话历史。",
            Current_Client_Query=query,
            stage=stage,
            Treatment_Structure="General",
        )
        response = await self.llm_response(rewrite_system_prompt, rendered_user, model_kwgs=model_kwgs)
        res = {
            "messages": [
                {"role": "system", "content": rewrite_system_prompt},
                {"role": "user", "content": rendered_user},
                {"role": "assistant", "content": response},
            ]
        }
        return response, res

    async def llm_response(
        self,
        template: str,
        input_text: str,
        model_kwgs: Optional[Dict[str, Any]] = None,
    ) -> str:
        del model_kwgs
        messages = [
            {"role": "system", "content": template},
            {"role": "user", "content": input_text},
        ]
        return await self._backend.chat_text(messages=messages)

    def find_skill_by_id(self, stage: int, skill_ids: Sequence[Tuple[str, str]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        result: List[Dict[str, Any]] = []
        result_wo_embed: List[Dict[str, Any]] = []
        stage_key = f"stage{stage}"

        for sect, meta_id in skill_ids:
            stage_data = self.skill_lib.get(sect, {}).get(stage_key)
            if stage_data is None:
                continue

            meta_skills = stage_data.meta
            micro_skills = stage_data.micro
            meta_item = meta_skills.get(meta_id)
            if not meta_item:
                continue

            parent_prefix = list(meta_item.get("parent_ids", []))
            children: List[Dict[str, Any]] = []
            for micro_item in micro_skills.values():
                micro_parent_ids = list(micro_item.get("parent_ids", []))
                if (
                    len(micro_parent_ids) == len(parent_prefix) + 1
                    and micro_parent_ids[:-1] == parent_prefix
                    and micro_parent_ids[-1] == str(micro_item.get("skill_id", ""))
                ):
                    children.append(micro_item)

            concat_meta = [str(meta_skills[aid].get("skill_name", "")) for aid in parent_prefix if aid in meta_skills]
            meta_str = "\n".join([x for x in concat_meta if x])

            children_wo_embed: List[Dict[str, Any]] = []
            for skill in children:
                children_wo_embed.append(
                    {k: v for k, v in skill.items() if k not in {"embedding_to_merge", "embedding_to_retrive"}}
                )

            result.append({"sect": sect, "meta_skill": meta_str, "micro_skills": children})
            result_wo_embed.append({"sect": sect, "meta_skill": meta_str, "micro_skills": children_wo_embed})

        return result, result_wo_embed

    def get_leaf_nodes(self, skills):
        """CPU Bound logic, fast enough to keep sync."""
        all_skill_ids = set(skills.keys())
        non_leaf_skill_ids = set()
        for skill_id, skill_data in skills.items():
            for other_skill_id, other_skill_data in skills.items():
                if skill_id == other_skill_id: continue
                if skill_id in other_skill_data.get("parent_ids", []):
                    non_leaf_skill_ids.add(skill_id)
                    break
        leaf_nodes = [
            (skill_id, skill_data) for skill_id, skill_data in skills.items()
            if skill_id not in non_leaf_skill_ids
        ]
        return dict(leaf_nodes)

    async def _ensure_embeddings_for_candidates(self, candidate_skills: List[Dict[str, Any]]) -> None:
        missing_retrieve: List[Dict[str, Any]] = []
        missing_merge: List[Dict[str, Any]] = []

        for skill in candidate_skills:
            if self._vector_to_list(skill.get("embedding_to_retrive")) is None:
                missing_retrieve.append(skill)
            if self._vector_to_list(skill.get("embedding_to_merge")) is None:
                missing_merge.append(skill)

        if missing_merge:
            merge_texts = [
                json.dumps(
                    {
                        k: v
                        for k, v in skill.items()
                        if k in {"skill_id", "skill_name", "skill_description", "trigger", "when_to_use", "parent_ids"}
                    },
                    ensure_ascii=False,
                )
                for skill in missing_merge
            ]
            merge_vecs = await self._embed_by_api(merge_texts)
            for skill, vec in zip(missing_merge, merge_vecs):
                skill["embedding_to_merge"] = vec

        if missing_retrieve:
            retrieve_texts = [
                f"Trigger:{skill.get('trigger', '')}\nWhen_to_Use:{skill.get('when_to_use', '')}"
                for skill in missing_retrieve
            ]
            retrieve_vecs = await self._embed_by_api(retrieve_texts)
            for skill, vec in zip(missing_retrieve, retrieve_vecs):
                skill["embedding_to_retrive"] = vec

    async def _embed_by_api(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if AsyncOpenAI is None:
            raise RuntimeError("openai package is required for embedding retrieval")

        client = self._build_embedding_client()
        embeddings: List[List[float]] = []
        batch_size = max(1, int(self._runtime.psychagent_embedding_batch_size))
        max_attempts = max(1, int(self._runtime.psychagent_embedding_max_retries))
        sleep_sec = float(self._runtime.psychagent_embedding_retry_sleep_sec)

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await client.embeddings.create(
                        input=batch,
                        model=self._runtime.psychagent_embedding_model,
                    )
                    embeddings.extend([list(item.embedding) for item in resp.data])
                    break
                except Exception as exc:
                    if attempt >= max_attempts:
                        raise RuntimeError(
                            f"embedding request failed after {max_attempts} attempts: {exc}"
                        ) from exc
                    backoff = sleep_sec * attempt
                    await asyncio.sleep(backoff)

        return embeddings

    def _build_embedding_client(self) -> Any:
        if self._embedding_client is not None:
            return self._embedding_client

        api_key = self._require_embedding_api_key()

        kwargs: Dict[str, Any] = {}
        if not self._runtime.psychagent_embedding_verify_ssl:
            if httpx is None:
                raise RuntimeError("httpx is required when psychagent_embedding_verify_ssl=false")
            kwargs["http_client"] = httpx.AsyncClient(verify=False)

        self._embedding_client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._runtime.psychagent_embedding_base_url,
            **kwargs,
        )
        return self._embedding_client

    def _require_embedding_api_key(self) -> str:
        env_name = str(self._runtime.psychagent_embedding_api_key_env).strip()
        if not env_name:
            raise RuntimeError("psychagent_embedding_api_key_env must be non-empty")

        api_key = os.environ.get(env_name, "").strip()
        if not api_key:
            raise RuntimeError(f"missing embedding api key env: {env_name}")
        return api_key

    def _load_prompts(self) -> None:
        select_dir = resolve_path(self._runtime.psychagent_skill_select_prompt_dir)
        rewrite_dir = resolve_path(self._runtime.psychagent_skill_rewrite_prompt_dir)

        self._select_system_prompt = (select_dir / "system.txt").read_text(encoding="utf-8")
        self._select_user_prompt = (select_dir / "user.txt").read_text(encoding="utf-8")
        self._rewrite_system_prompt = (rewrite_dir / "system.txt").read_text(encoding="utf-8")
        self._rewrite_user_prompt = (rewrite_dir / "user.txt").read_text(encoding="utf-8")

    def _normalize_sects(self, raw_sects: str | List[str]) -> List[str]:
        if isinstance(raw_sects, str):
            text = raw_sects.strip()
            if text.lower() == "all":
                return list(DEFAULT_SECTS)
            return [x.strip() for x in text.split(",") if x.strip()]

        sects = [str(x).strip() for x in raw_sects if str(x).strip()]
        if sects == ["all"]:
            return list(DEFAULT_SECTS)
        return sects or list(DEFAULT_SECTS)

    def _resolve_stage(self, stage: int | str) -> int:
        if isinstance(stage, int):
            return stage if stage in {1, 2, 3} else 1
        if isinstance(stage, str):
            stage = stage.strip()
            if stage.isdigit():
                parsed = int(stage)
                return parsed if parsed in {1, 2, 3} else 1
            return STAGE_MAP.get(stage, 1)
        return 1

    def _render_template(self, template_text: str, **kwargs: Any) -> str:
        if Template is None:
            return template_text
        return Template(template_text).render(**kwargs)

    @staticmethod
    def _load_json_dict(path: Path) -> Dict[str, Dict[str, Any]]:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}

    def _load_micro_skills(self, stage_dir: Path) -> Dict[str, Dict[str, Any]]:
        pt_path = stage_dir / "micro_skills.pt"
        json_path = stage_dir / "micro_skills.json"

        raw: Dict[str, Any] = {}
        if pt_path.exists() and torch is not None:
            loaded = torch.load(str(pt_path), weights_only=False)
            if isinstance(loaded, dict):
                raw = loaded
        elif json_path.exists():
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded

        cleaned: Dict[str, Dict[str, Any]] = {}
        for key, value in raw.items():
            if isinstance(value, dict):
                value = dict(value)
                if "skill_id" not in value:
                    value["skill_id"] = str(key)
                cleaned[str(key)] = value
        return cleaned

    @staticmethod
    def _extract_json_object(text: str) -> Dict[str, Any]:
        if not text:
            return {}

        inner = extract_tag_content(text, "response") or text
        inner = inner.strip()
        if inner.startswith("```"):
            inner = re.sub(r"^```(?:json)?", "", inner).strip()
            inner = re.sub(r"```$", "", inner).strip()

        try:
            parsed = json.loads(inner)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        match = re.search(r"\{.*\}", inner, re.S)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        return {}

    @staticmethod
    def _vector_to_list(value: Any) -> Optional[List[float]]:
        if value is None:
            return None

        if isinstance(value, list):
            try:
                return [float(x) for x in value]
            except Exception:
                return None

        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            try:
                listed = tolist()
                if isinstance(listed, list):
                    return [float(x) for x in listed]
            except Exception:
                return None

        return None

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return -1.0
        num = sum(a * b for a, b in zip(v1, v2))
        den1 = math.sqrt(sum(a * a for a in v1))
        den2 = math.sqrt(sum(b * b for b in v2))
        if den1 == 0 or den2 == 0:
            return -1.0
        return num / (den1 * den2)
