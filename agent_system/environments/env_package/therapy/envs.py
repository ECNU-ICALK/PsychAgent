import dataclasses
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import ray

from agent_system.environments.env_package.therapy.patient.client import *
# from patient.client import *
from agent_system.environments.env_package.therapy.reward import *

from ...prompts.therapy import *


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
            self.client = OpenAIChat(model=self.client_model, temperature=self.temperature, max_output_tokens=400)

    def _build_system(self, p: ClientProfile) -> str:
        return CLIENT_SYSTEM_TEMPLATE.format(
            name=p.name, age=p.age, gender=p.gender, job=p.job,
            problem=p.problem, personality=p.personality, goals=p.goals
        )

    def _client_reply(self) -> str:
        msgs = self.history
        text = self.client.generate(msgs, temperature=self.temperature, max_output_tokens=400)
        return text

    # def reset(self, profile_dict: Dict[str, Any]):
        # self._ensure_client()
        # self.step_count = 0
        # self.profile = ClientProfile(**profile_dict)

        # sys_msg = {"role": "system", "content": self._build_system(self.profile)}
        # init_user = {"role": "user", "content": CLIENT_INIT_USER}
        
        # # print([sys_msg, init_user])
        
        # # sys.exit()
        
        # initial_client_text = self.client.generate([sys_msg, init_user], temperature=self.temperature, max_output_tokens=300)

        # self.history = [sys_msg, {"role": "assistant", "content": initial_client_text}]
        # info = {"profile": dataclasses.asdict(self.profile), "step_count": self.step_count}
        # return initial_client_text, info
    def reset(self, profile_dict: Dict[str, Any]):
        self._ensure_client()
        self.step_count = 0
        self.profile = ClientProfile(**profile_dict)

        sys_msg = {"role": "system", "content": self._build_system(self.profile)}
        # 过去这里会加 init_user 并生成 initial_client_text —— 删除
        self.history = [sys_msg]

        info = {"profile": dataclasses.asdict(self.profile), "step_count": self.step_count}
        # 返回空的 initial_client_text（或占位字符串）
        initial_client_text = ""  # 咨询师先说
        return initial_client_text, info
# python -m examples.dapo_trainer.main_dapo
    def step(self, counselor_utt: str):
        if self.profile is None:
            raise RuntimeError("Call reset() before step().")
        self.step_count += 1
        self.history.append({"role": "user", "content": counselor_utt})
        
        # print("self.history")
        
        # print("-"*60)
        # print(self.history)
        # sys.exit()
        
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
                 seed: int = 0,):
        self.env_num = int(env_num)
        self.group_n = int(group_n)
        self.num_processes = self.env_num * self.group_n
        self.max_interactions = int(max_interactions)
        self.client_model = client_model
        self.temperature = float(temperature)
        self.rng = np.random.default_rng(seed)

        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True)


        self.workers = [
            ClientWorker.remote(max_interactions=self.max_interactions,
                                client_model=self.client_model,
                                temperature=self.temperature)
            for _ in range(self.num_processes)
        ]

    def reset(self, profiles) -> Tuple[List[str], List[Dict[str, Any]]]:
        # idx = self.rng.choice(len(self.profiles), self.env_num, replace=False)
        # chosen = [self.profiles[i] for i in idx]
        batch_profiles = []
        for p in profiles:
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

def build_therapy_envs(max_interactions=50, seed=0, env_num=1, group_n=1, client_model="gpt-4o", temperature=0.5):

    envs = CounselingEnvs(
        seed=seed,
        env_num=env_num,
        group_n=group_n,
        max_interactions=max_interactions,
        client_model=client_model,
        temperature=temperature,
    )
    
    return envs