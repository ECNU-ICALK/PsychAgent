# Copyright 2025 Nanyang Technological University (NTU), Singapore
# and the verl-agent (GiGPO) team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -*- coding: utf-8 -*-
"""
Multi-client counseling training framework with a Manager:
- Ray-based parallel 'client agents' (GPT or mock).
- Counselor policy: trainable template (REINFORCE) or LLM baseline.
- Simple memory for dialog history.
- EnvironmentManagerBase-compatible CounselingEnvironmentManager to build counselor observations.
- Demos:
    1) trainer_demo(): classic rollout + REINFORCE over envs directly
    2) manager_demo(): use CounselingEnvironmentManager to drive the loop

Setup:
    pip install ray openai numpy pandas pillow
    export OPENAI_API_KEY=sk-...   # unless MOCK=1
Run:
    python counseling_with_manager.py

Environment variables:
    MOCK=1                  # use mock LLMs (no API needed)
    COUNSELOR=trainable     # or "llm"
    CLIENT_MODEL=gpt-4o-mini
    COUNSELOR_MODEL=gpt-4o-mini
"""

import os
import time
import json
import math
import random
import dataclasses
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional, Union

import numpy as np
import ray

# ===================== OpenAI / Mock Chat =====================
MOCK = os.environ.get("MOCK", "0") == "1"
try:
    from openai import OpenAI
    _HAS_OPENAI = (not MOCK)
except Exception:
    _HAS_OPENAI = False


class _BaseChat:
    def __init__(self, model: str, temperature: float, max_output_tokens: int):
        self.model = model
        self.temperature = float(temperature)
        self.max_output_tokens = int(max_output_tokens)

    def generate(self, messages: List[Dict[str, Any]], temperature: Optional[float] = None,
                 max_output_tokens: Optional[int] = None) -> str:
        raise NotImplementedError


class OpenAIChat(_BaseChat):
    """
    Minimal wrapper around OpenAI Responses API.
    """
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7, max_output_tokens: int = 400):
        super().__init__(model, temperature, max_output_tokens)
        if not _HAS_OPENAI:
            raise RuntimeError("OpenAI SDK unavailable or MOCK=1. Set MOCK=1 to use MockChat.")
        self.client = OpenAI()

    def generate(self, messages: List[Dict[str, Any]], temperature: Optional[float] = None,
                 max_output_tokens: Optional[int] = None) -> str:
        t = self.temperature if temperature is None else float(temperature)
        mot = self.max_output_tokens if max_output_tokens is None else int(max_output_tokens)
        resp = self.client.responses.create(
            model=self.model,
            input=messages,
            temperature=t,
            max_output_tokens=mot
        )
        return resp.output_text.strip()


class MockChat(_BaseChat):
    """
    Deterministic, API-free stand-in for both client and counselor LLMs.
    Produces short, plausible-looking text in Chinese based on the last input.
    """
    EMO = ["焦虑", "压力", "紧张", "难过", "无助", "害怕"]
    def __init__(self, model: str = "mock-model", temperature: float = 0.0, max_output_tokens: int = 200):
        super().__init__(model, temperature, max_output_tokens)
        self.rng = random.Random(1234)

    def _shorten(self, s: str, n: int = 80) -> str:
        s = s.strip().replace("\n", " ")
        return s if len(s) <= n else s[:n] + "..."

    def generate(self, messages: List[Dict[str, Any]], temperature: Optional[float] = None,
                 max_output_tokens: Optional[int] = None) -> str:
        # Get last user content
        user_texts = [m["content"] for m in messages if m.get("role") == "user"]
        last = user_texts[-1] if user_texts else ""
        # Heuristic response
        if "开场" in last or "开场陈述" in last:
            return "最近我总是感到有点焦虑，睡得不是很好，也不知道该怎么调整。"
        if "要求" in last and "当前来访者" in last:
            # counselor generation
            return "听起来这段时间对你并不容易。我在想，最让你困扰的部分是什么？"
        # client generation
        em = self.rng.choice(self.EMO)
        return f"嗯，我最近确实有{em}，尤其是在工作上，和同事沟通时会紧张。"

# choose chat impl
ChatImpl = MockChat if (MOCK or not _HAS_OPENAI) else OpenAIChat


# ===================== Simple Memory =====================
class SimpleMemory:
    """
    Per-env time-series memory: each env has a list of step dicts
    {'text_obs': str, 'action': str} or custom keys.
    """
    def __init__(self):
        self._data = None
        self.keys = None
        self.batch_size = 0

    def __len__(self):
        return 0 if self._data is None else len(self._data)

    def __getitem__(self, idx):
        if self._data is None:
            raise RuntimeError("Call reset(batch_size) before indexing.")
        return self._data[idx]

    def reset(self, batch_size: int):
        self._data = [[] for _ in range(batch_size)]
        self.batch_size = batch_size
        self.keys = None

    def store(self, record: Dict[str, List[Any]]):
        if self.keys is None:
            self.keys = list(record.keys())
        else:
            assert set(self.keys) == set(record.keys()), "Schema mismatch in memory.store"

        for k, v in record.items():
            assert len(v) == self.batch_size, f"Length of {k} != batch_size"

        for env_idx in range(self.batch_size):
            self._data[env_idx].append({k: record[k][env_idx] for k in self.keys})

    def fetch_strings(self, history_length: int,
                      obs_key: str = "text_obs",
                      action_key: str = "action") -> Tuple[List[str], List[int]]:
        memory_contexts, valid_lengths = [], []
        for env_idx in range(self.batch_size):
            hl = max(0, int(history_length))
            recent = self._data[env_idx][-hl:] if hl > 0 else []
            valid_len = len(recent)
            start_idx = len(self._data[env_idx]) - valid_len
            lines = []
            for j, rec in enumerate(recent):
                step_num = start_idx + j + 1
                act = rec[action_key]
                obs = rec[obs_key]
                lines.append(f"[Observation {step_num}: '{obs}', Action {step_num}: '{act}']")
            memory_contexts.append("\n".join(lines))
            valid_lengths.append(valid_len)
        return memory_contexts, valid_lengths


# ===================== Prompt Templates =====================
CLIENT_SYSTEM_TEMPLATE = (
    "你是来访者，处于心理咨询的第一节会谈。"
    "背景：姓名：{name}；年龄：{age}；性别：{gender}；职业：{job}。"
    "主要困扰：{problem}。性格特征：{personality}。来访目标：{goals}。"
    "要求：只以第一人称、自然口语表达你的想法和感受；避免一次说太多；每次回复 1~4 句。"
)
CLIENT_INIT_USER = "请以第一人称给出开场陈述（1~3句），自然表达当前处境和感受。"

COUNSELOR_OBS_TEMPLATE = (
    "【任务】你是咨询师。下面是与来访者最近的对话历史（最多{hist_n}轮）：\n"
    "{history}\n"
    "【当前来访者】\n{current_client}\n"
    "【要求】用专业、简洁、共情的中文回应（1~4句），避免给建议式评判、避免一次问多个问题。"
)

# For Manager text building
COUNSELING_TEMPLATE_NO_HIS = (
    "【角色】你是心理咨询师。\n"
    "【来访者画像】姓名：{name}；年龄：{age}；性别：{gender}；职业：{job}\n"
    "【主要困扰】{problem}\n"
    "【目标】{goals}\n"
    "【当前来访者（开场）】\n{current_client}\n\n"
    "【要求】以共情、开放式提问为主，1~4句中文回复，避免评判/建议口吻。"
)
COUNSELING_TEMPLATE = (
    "【角色】你是心理咨询师。\n"
    "【来访者画像】姓名：{name}；年龄：{age}；性别：{gender}；职业：{job}\n"
    "【主要困扰】{problem}\n"
    "【目标】{goals}\n"
    "【对话历史（最近{history_length}轮）】\n"
    "{action_history}\n"
    "【统计】已完成轮数：{step_count}；即将进行：第{current_step}轮\n\n"
    "【当前来访者】\n{current_client}\n\n"
    "【要求】以共情、开放式提问为主，1~4句中文回复，避免评判/建议口吻。"
)


# ===================== Profiles =====================
@dataclass
class ClientProfile:
    name: str
    age: int
    gender: str
    job: str
    problem: str
    personality: str
    goals: str

def default_profiles() -> List[ClientProfile]:
    return [
        ClientProfile("小李", 27, "女", "产品经理", "长期加班导致焦虑与睡眠问题", "内向、追求完美、敏感", "缓解焦虑、改善睡眠"),
        ClientProfile("阿强", 34, "男", "销售", "与伴侣冲突频繁、情绪爆发", "外向、急躁、重面子", "改善沟通、稳定关系"),
        ClientProfile("欣欣", 19, "女", "大一学生", "社交恐惧与自我怀疑", "害羞、敏感、想太多", "提高社交自信"),
        ClientProfile("王伟", 41, "男", "工程师", "职业倦怠、动机下降", "务实、理性、压抑表达", "重新找回动力与意义感"),
        ClientProfile("婷婷", 29, "女", "自由职业者", "拖延严重、作息混乱", "有创造力、易分心", "形成稳定作息、提升执行"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
    ]


# ===================== Rewards =====================
EMPATHY_MARKERS = ["听起来", "我在想", "我理解", "我注意到", "听上去", "你似乎", "我能感受到"]
OPEN_QUESTION_MARKERS = ["是什么让你", "能不能多讲讲", "可以说说", "当时你", "这对你意味着什么", "最让你困扰的部分是什么"]
AVOID_MARKERS = ["你应该", "你必须", "我建议你", "很简单", "别想了", "其实这没什么"]

def rule_based_reward(counselor_utt: str, client_utt: str) -> float:
    cu = counselor_utt.strip()
    cl = client_utt.strip()
    r = 0.0
    r += sum(1 for m in EMPATHY_MARKERS if m in cu) * 1.0
    r += sum(1 for m in OPEN_QUESTION_MARKERS if m in cu) * 1.0
    r -= sum(1 for m in AVOID_MARKERS if m in cu) * 1.5
    sents = sum(1 for x in cl.replace("！", "。").replace("?", "。").split("。") if x.strip())
    if sents >= 2:
        r += 0.5
    if len(cu) > 180:
        r -= 0.5
    return float(r)


# ===================== Ray Client Worker & Envs =====================
@ray.remote(num_cpus=0.2)
class ClientWorker:
    """
    Each worker hosts one 'client agent' (GPT or mock) and simulates the env.
    reset(profile) -> initial client message & info
    step(counselor_utt) -> next client reply, reward, done, info
    """
    def __init__(self, max_interactions: int = 8,
                 client_model: str = "gpt-4o-mini",
                 temperature: float = 0.5):
        self.max_interactions = int(max_interactions)
        self.client_model = client_model
        self.temperature = float(temperature)

        self.client = None
        self.history: List[Dict[str, str]] = []  # messages (client system + alternates)
        self.step_count = 0
        self.profile: Optional[ClientProfile] = None

    def _ensure_client(self):
        if self.client is None:
            self.client = ChatImpl(model=self.client_model, temperature=self.temperature, max_output_tokens=400)

    def _build_system(self, p: ClientProfile) -> str:
        return CLIENT_SYSTEM_TEMPLATE.format(
            name=p.name, age=p.age, gender=p.gender, job=p.job,
            problem=p.problem, personality=p.personality, goals=p.goals
        )

    def _client_reply(self) -> str:
        msgs = self.history
        text = self.client.generate(msgs, temperature=self.temperature, max_output_tokens=400)
        return text

    def reset(self, profile_dict: Dict[str, Any]):
        self._ensure_client()
        self.step_count = 0
        self.profile = ClientProfile(**profile_dict)

        sys_msg = {"role": "system", "content": self._build_system(self.profile)}
        init_user = {"role": "user", "content": CLIENT_INIT_USER}
        initial_client_text = self.client.generate([sys_msg, init_user], temperature=self.temperature, max_output_tokens=300)

        self.history = [sys_msg, {"role": "assistant", "content": initial_client_text}]
        info = {"profile": dataclasses.asdict(self.profile), "step_count": self.step_count}
        return initial_client_text, info

    def step(self, counselor_utt: str):
        if self.profile is None:
            raise RuntimeError("Call reset() before step().")
        self.step_count += 1
        self.history.append({"role": "user", "content": counselor_utt})
        client_reply = self._client_reply()
        self.history.append({"role": "assistant", "content": client_reply})

        done = self.step_count >= self.max_interactions
        reward = rule_based_reward(counselor_utt, client_reply)
        info = {"profile": dataclasses.asdict(self.profile), "step_count": self.step_count,
                "won": float(reward >= 1.5)}  # heuristic 'won'
        return client_reply, float(reward), bool(done), info

    def close(self):
        pass


class CounselingEnvs:
    """
    Vectorized env manager producing batched (obs, reward, done, info)
    across n_processes workers.
    """
    def __init__(self,
                 env_num: int = 2,
                 group_n: int = 2,
                 max_interactions: int = 8,
                 client_model: str = "gpt-4o-mini",
                 temperature: float = 0.5,
                 seed: int = 0,
                 profiles: Optional[List[ClientProfile]] = None):
        self.env_num = int(env_num)
        self.group_n = int(group_n)
        self.num_processes = self.env_num * self.group_n
        self.max_interactions = int(max_interactions)
        self.client_model = client_model
        self.temperature = float(temperature)
        self.rng = np.random.default_rng(seed)

        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True)

        self.profiles = profiles or default_profiles()
        if self.env_num > len(self.profiles):
            raise ValueError(f"env_num({self.env_num}) > available profiles({len(self.profiles)}).")

        self.workers = [
            ClientWorker.remote(max_interactions=self.max_interactions,
                                client_model=self.client_model,
                                temperature=self.temperature)
            for _ in range(self.num_processes)
        ]

    def reset(self) -> Tuple[List[str], List[Dict[str, Any]]]:
        idx = self.rng.choice(len(self.profiles), self.env_num, replace=False)
        chosen = [self.profiles[i] for i in idx]
        batch_profiles = []
        for p in chosen:
            batch_profiles.extend([p] * self.group_n)

        futures = [w.reset.remote(dataclasses.asdict(batch_profiles[i])) for i, w in enumerate(self.workers)]
        results = ray.get(futures)
        obs_list, info_list = [], []
        for obs, info in results:
            obs_list.append(obs)
            info_list.append(info)
        return obs_list, info_list

    def step(self, actions: List[str]) -> Tuple[List[str], List[float], List[bool], List[Dict[str, Any]]]:
        assert len(actions) == self.num_processes, "actions length must equal number of workers"
        fut = [w.step.remote(actions[i]) for i, w in enumerate(self.workers)]
        results = ray.get(fut)
        obs, rew, done, info = [], [], [], []
        for o, r, d, inf in results:
            obs.append(o); rew.append(float(r)); done.append(bool(d)); info.append(inf)
        return obs, rew, done, info

    def close(self):
        ray.get([w.close.remote() for w in self.workers])
        for w in self.workers:
            try: ray.kill(w)
            except Exception: pass


# ===================== Counselor Policies =====================
class CounselorPolicyBase:
    def act(self, full_obs_batch: List[str]) -> List[str]:
        raise NotImplementedError

    def learn(self, trajectories: List[Dict[str, Any]]):
        pass


class LLMCounselor(CounselorPolicyBase):
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.4, max_output_tokens: int = 300):
        self.chat = ChatImpl(model=model, temperature=temperature, max_output_tokens=max_output_tokens)

    def act(self, full_obs_batch: List[str]) -> List[str]:
        outputs = []
        for obs in full_obs_batch:
            msgs = [{"role": "user", "content": obs}]
            text = self.chat.generate(msgs, temperature=0.4, max_output_tokens=300)
            outputs.append(text)
        return outputs


class TrainableCounselor(CounselorPolicyBase):
    """
    Template selection with softmax over simple features (REINFORCE).
    """
    def __init__(self, templates: Optional[List[str]] = None, lr: float = 0.05, seed: int = 0):
        self.templates = templates or [
            "听起来你正经历着不容易的时刻。我在想，{last_client} 对你意味着什么？",
            "我能感受到这对你很重要。能不能多讲讲，当时你最强烈的感受是什么？",
            "我注意到你提到『{last_client}』。如果把它具体化一点，现在最想先聚焦哪一块？",
            "谢谢你分享这些。你似乎很在意{last_client}里的某个部分，我们可以一起把它梳理清楚吗？",
            "我理解你现在的心情。回看这件事，你最希望发生的改变是什么？"
        ]
        self.rng = random.Random(seed)
        self.lr = float(lr)
        self.dim = 5
        self.W = np.zeros((len(self.templates), self.dim), dtype=np.float32)
        self.baseline = 0.0
        self.emotion_kws = ["难过", "焦虑", "压力", "愤怒", "害怕", "紧张", "羞愧", "无助"]

    def _features(self, last_client: str) -> np.ndarray:
        s = last_client.strip()
        f = np.zeros(self.dim, dtype=np.float32)
        f[0] = 1.0
        f[1] = min(len(s) / 120.0, 2.0)
        f[2] = 1.0 if any(k in s for k in self.emotion_kws) else 0.0
        f[3] = 1.0 if ("?" in s or "？" in s) else 0.0
        f[4] = 0.0 if len(s) < 30 else (0.5 if len(s) < 120 else 1.0)
        return f

    def _policy(self, x: np.ndarray) -> np.ndarray:
        logits = self.W @ x
        logits = logits - logits.max()
        probs = np.exp(logits) / np.clip(np.exp(logits).sum(), 1e-8, None)
        return probs

    def _sample(self, probs: np.ndarray) -> int:
        return int(np.random.choice(len(probs), p=probs))

    def act(self, full_obs_batch: List[str]) -> List[str]:
        actions = []
        for obs in full_obs_batch:
            if "【当前来访者】" in obs:
                last_client = obs.split("【当前来访者】", 1)[1].strip()
            else:
                last_client = obs
            last_client = last_client[-300:]
            x = self._features(last_client)
            probs = self._policy(x)
            a = self._sample(probs)
            tpl = self.templates[a]
            action = tpl.replace("{last_client}", last_client[:80])
            actions.append(action)
        return actions

    def learn(self, trajectories: List[Dict[str, Any]]):
        if not trajectories: return
        mean_r = float(np.mean([t["reward"] for t in trajectories]))
        self.baseline = 0.9 * self.baseline + 0.1 * mean_r
        dW = np.zeros_like(self.W)
        for t in trajectories:
            x = self._features(t["last_client"])
            probs = self._policy(x)
            a = t["action_idx"]
            onehot = np.zeros_like(probs); onehot[a] = 1.0
            grad_logp = (onehot - probs)[:, None] @ x[None, :]
            advantage = t["reward"] - self.baseline
            dW += advantage * grad_logp
        self.W += self.lr * dW / max(1, len(trajectories))


# ===================== Classic Trainer (envs directly) =====================
class Trainer:
    def __init__(self, envs: CounselingEnvs, counselor: Union[LLMCounselor, TrainableCounselor],
                 history_length: int = 4):
        self.envs = envs
        self.counselor = counselor
        self.history_length = int(history_length)
        self.memory = SimpleMemory()

    def _build_observations(self, client_obs_batch: List[str]) -> List[str]:
        post = []
        mem_strings, _ = self.memory.fetch_strings(self.history_length, obs_key="client", action_key="counselor")
        for i in range(len(client_obs_batch)):
            hist = mem_strings[i] if mem_strings[i] else "(无历史)"
            obs = COUNSELOR_OBS_TEMPLATE.format(hist_n=self.history_length, history=hist, current_client=client_obs_batch[i])
            post.append(obs)
        return post

    def rollout(self, max_steps: int = 8) -> Dict[str, Any]:
        client_first, infos = self.envs.reset()
        self.memory.reset(batch_size=len(client_first))
        full_obs = self._build_observations(client_first)

        all_rewards = []
        episode_trajectories: List[Dict[str, Any]] = []

        for step in range(max_steps):
            actions = self.counselor.act(full_obs)
            next_client, rewards, dones, step_infos = self.envs.step(actions)
            self.memory.store({"client": next_client, "counselor": actions})
            all_rewards.append(rewards)

            if isinstance(self.counselor, TrainableCounselor):
                for i in range(len(actions)):
                    last_client = full_obs[i].split("【当前来访者】", 1)[1].strip() if "【当前来访者】" in full_obs[i] else full_obs[i]
                    chosen_idx = 0
                    for idx, tpl in enumerate(self.counselor.templates):
                        if actions[i].startswith(tpl.split("{last_client}")[0][:8]):
                            chosen_idx = idx; break
                    episode_trajectories.append({"last_client": last_client, "action_idx": chosen_idx, "reward": float(rewards[i])})

            full_obs = self._build_observations(next_client)
            if all(dones): break

        if isinstance(self.counselor, TrainableCounselor):
            self.counselor.learn(episode_trajectories)

        avg_return = float(np.mean(np.sum(np.array(all_rewards), axis=0))) if all_rewards else 0.0
        return {"avg_return": avg_return, "steps": step + 1}

    def close(self):
        self.envs.close()


# ===================== Manager Base & Counseling Manager =====================
try:
    import torch
except Exception:
    torch = None

def to_numpy(data):
    if torch is not None and isinstance(data, torch.Tensor):
        data = data.detach().cpu().numpy()
    elif isinstance(data, np.ndarray):
        pass
    elif isinstance(data, (int, float, bool, tuple, list)):
        data = np.array(data)
    else:
        raise ValueError(f"Unsupported type: {type(data)})")
    return data


class EnvironmentManagerBase:
    def __init__(self, envs, projection_f, config):
        """
        envs: vectorized env with reset()/step()/close()
        projection_f: function(List[str]) -> (actions: List[Any], valids: List[bool])
        config: with at least config.env.history_length, config.env.env_name
        """
        self.envs = envs
        self.projection_f = projection_f
        self.config = config

    def reset(self) -> Dict[str, Any]:
        obs, infos = self.envs.reset()
        return {'text': None, 'image': obs, 'anchor': None}, infos
    
    def step(self, text_actions: List[str]):
        actions, valids = self.projection_f(text_actions)
        next_obs, rewards, dones, infos = self.envs.step(actions)
        next_observations = {'text': None, 'image': next_obs, 'anchor': None}
        for i, info in enumerate(infos):
            info['is_action_valid'] = to_numpy(valids[i])
        rewards = to_numpy(rewards); dones = to_numpy(dones)
        return next_observations, rewards, dones, infos

    def build_text_obs(self,) -> List[str]:
        pass

    def close(self) -> None:
        self.envs.close()

    def success_evaluator(self, *args, **kwargs) -> Dict[str, np.ndarray]:
        from collections import defaultdict
        total_infos = kwargs['total_infos']
        total_batch_list = kwargs['total_batch_list']
        batch_size = len(total_batch_list)
        success = defaultdict(list)
        for bs in range(batch_size):
            self._process_batch(bs, total_batch_list, total_infos, success)
        assert len(success['success_rate']) == batch_size
        return {key: np.array(value) for key, value in success.items()}
    
    def _process_batch(self, batch_idx, total_batch_list, total_infos, success):
        for i in reversed(range(len(total_batch_list[batch_idx]))):
            batch_item = total_batch_list[batch_idx][i]
            if batch_item['active_masks']:
                info = total_infos[batch_idx][i]
                won_value = float(info.get('won', 0.0))
                success['success_rate'].append(won_value)
                return

def _format_history_line(step_number: int, counselor: str, client: str) -> str:
    return (
        f"Counselor {step_number}:\n{counselor}\n\n"
        f"Client {step_number}:\n{client}\n"
    )

class CounselingEnvironmentManager(EnvironmentManagerBase):
    """
    Manager that builds text observations for counselor:
    - Maintains SimpleMemory of (counselor, client) per env
    - Renders recent N turns + current client message using templates
    """
    def __init__(self, envs, projection_f, config):
        self.memory = SimpleMemory()
        super().__init__(envs, projection_f, config)
        self.profiles = None
        self.pre_client_obs = None

    def reset(self):
        text_obs, infos = self.envs.reset()  # list[str] from clients (opening statement)
        self.profiles = [info['profile'] for info in infos]
        self.memory.reset(batch_size=len(text_obs))
        self.pre_client_obs = text_obs
        full_text_obs = self.build_text_obs(text_obs, init=True)
        return {'text': full_text_obs, 'image': None, 'anchor': text_obs}, infos

    def step(self, text_actions: List[str]):
        # projection: identity by default
        actions, valids = self.projection_f(text_actions)
        text_obs, rewards, dones, infos = self.envs.step(actions)
        self.memory.store({'client': text_obs, 'counselor': actions})
        self.pre_client_obs = text_obs
        full_text_obs = self.build_text_obs(text_obs, init=False)
        for i, info in enumerate(infos):
            info['is_action_valid'] = to_numpy(True)
        next_observations = {'text': full_text_obs, 'image': None, 'anchor': text_obs}
        rewards = to_numpy(rewards); dones = to_numpy(dones)
        return next_observations, rewards, dones, infos

    def build_text_obs(self, text_obs: List[str], init: bool = False) -> List[str]:
        postprocess_text_obs = []
        B = len(text_obs)
        if init and self.profiles is not None:
            for i in range(B):
                p = self.profiles[i]
                obs = COUNSELING_TEMPLATE_NO_HIS.format(
                    name=p.get('name', ''),
                    age=p.get('age', ''),
                    gender=p.get('gender', ''),
                    job=p.get('job', ''),
                    problem=p.get('problem', ''),
                    goals=p.get('goals', ''),
                    current_client=text_obs[i],
                )
                postprocess_text_obs.append(obs)
            return postprocess_text_obs

        for i in range(B):
            hl = max(0, int(self.config.env.history_length))
            recent = self.memory[i][-hl:] if hl > 0 else []
            valid_history_length = len(recent)
            start_index = len(self.memory[i]) - valid_history_length
            action_history = ""
            for j, record in enumerate(recent):
                step_number = start_index + j + 1
                counselor = record["counselor"]
                client = record["client"]
                action_history += _format_history_line(step_number, counselor, client)
            if len(action_history) > 10000:
                action_history = "... " + action_history[-10000:]

            p = self.profiles[i]
            obs = COUNSELING_TEMPLATE.format(
                name=p.get('name', ''),
                age=p.get('age', ''),
                gender=p.get('gender', ''),
                job=p.get('job', ''),
                problem=p.get('problem', ''),
                goals=p.get('goals', ''),
                step_count=len(self.memory[i]),
                history_length=valid_history_length,
                action_history=action_history.strip(),
                current_step=len(self.memory[i]) + 1,
                current_client=text_obs[i],
            )
            postprocess_text_obs.append(obs)
        return postprocess_text_obs


# ===================== Config, projection, builders =====================
@dataclass
class EnvConfig:
    env_name: str = "counseling"
    history_length: int = 4

@dataclass
class Config:
    env: EnvConfig = EnvConfig()

def identity_projection(text_actions: List[str]) -> Tuple[List[str], List[bool]]:
    return text_actions, [True] * len(text_actions)

def build_counseling_manager(
    env_num=2,
    group_n=2,
    horizon=6,
    client_model="gpt-4o-mini",
    temperature=0.5,
    history_length=4,
    seed=42,
):
    envs = CounselingEnvs(
        env_num=env_num,
        group_n=group_n,
        max_interactions=horizon,
        client_model=client_model,
        temperature=temperature,
        seed=seed
    )
    cfg = Config(env=EnvConfig(env_name="counseling", history_length=history_length))
    mgr = CounselingEnvironmentManager(envs=envs, projection_f=identity_projection, config=cfg)
    return mgr


# ===================== Demos / Entry =====================
def trainer_demo():
    envs = CounselingEnvs(env_num=2, group_n=2, max_interactions=6,
                          client_model=os.environ.get("CLIENT_MODEL", "gpt-4o-mini"),
                          temperature=0.5, seed=42)
    counselor_mode = os.environ.get("COUNSELOR", "trainable")
    if counselor_mode == "llm":
        counselor = LLMCounselor(model=os.environ.get("COUNSELOR_MODEL", "gpt-4o-mini"))
    else:
        counselor = TrainableCounselor(lr=0.08, seed=123)
    trainer = Trainer(envs, counselor, history_length=4)
    for ep in range(3):
        stats = trainer.rollout(max_steps=6)
        print(f"[Trainer Epoch {ep+1}] avg_return={stats['avg_return']:.3f} steps={stats['steps']} mode={counselor_mode}")
    trainer.close()
    ray.shutdown()


def manager_demo():
    mode = os.environ.get("COUNSELOR", "trainable")
    if mode == "llm":
        counselor = LLMCounselor(model=os.environ.get("COUNSELOR_MODEL", "gpt-4o-mini"))
    else:
        counselor = TrainableCounselor(lr=0.08, seed=123)

    horizon = 6
    mgr = build_counseling_manager(env_num=2, group_n=2, horizon=horizon, history_length=4)

    observations, infos = mgr.reset()
    full_text = observations['text']      # List[str]
    all_rewards = []
    trajectories = []

    for t in range(horizon):
        actions = counselor.act(full_text)
        next_observations, rewards, dones, step_infos = mgr.step(actions)
        all_rewards.append(rewards)

        if isinstance(counselor, TrainableCounselor):
            last_clients = next_observations['anchor']
            for i in range(len(actions)):
                chosen_idx = 0
                for idx, tpl in enumerate(counselor.templates):
                    if actions[i].startswith(tpl.split("{last_client}")[0][:8]):
                        chosen_idx = idx; break
                trajectories.append({"last_client": last_clients[i], "action_idx": chosen_idx, "reward": float(rewards[i])})

        full_text = next_observations['text']
        if all(dones):
            break

    if isinstance(counselor, TrainableCounselor):
        counselor.learn(trajectories)

    avg_return = float(np.mean(np.sum(np.array(all_rewards), axis=0))) if all_rewards else 0.0
    print(f"[Manager Demo] avg_return={avg_return:.3f} steps={t+1} mode={mode}")

    mgr.close()
    ray.shutdown()


if __name__ == "__main__":
    # demo = os.environ.get("DEMO", "manager")  # "manager" or "trainer"
    # if demo == "trainer":
    #     trainer_demo()
    # else:
    manager_demo()
