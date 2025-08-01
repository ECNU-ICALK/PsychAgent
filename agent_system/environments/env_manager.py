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

import os
from collections import defaultdict
from functools import partial
from typing import Any, Dict, List, Tuple, Union

import numpy as np
import torch

from agent_system.environments.base import EnvironmentManagerBase, to_numpy
from agent_system.environments.prompts import *
from agent_system.memory import SimpleMemory


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

    def reset(self, batch_profiles):
        text_obs, infos = self.envs.reset(batch_profiles)  # list[str] from clients (opening statement)
        self.profiles = [info['profile'] for info in infos]
        self.memory.reset(batch_size=len(text_obs))
        self.pre_client_obs = text_obs
        full_text_obs = self.build_text_obs(text_obs, init=True)
        
        for info in infos:
            info["has_client_opening"] = False  # 首轮没有 client 话术
            
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
            info['has_client_opening'] = True
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
                    # current_client=text_obs[i],
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


def make_envs(config):
    """
    Create enviroments 
    """ 
    # check if config.env.rollout.n is an integer
    if not isinstance(config.env.rollout.n, int):
        raise ValueError("config.env.rollout.n should be an integer")
    group_n = config.env.rollout.n if config.env.rollout.n > 0 else 1
    if "therapy" in config.env.env_name.lower():
        from agent_system.environments.env_package.therapy import (
            build_therapy_envs, identity_projection)
        _envs = build_therapy_envs(seed=config.env.seed, env_num=config.data.train_batch_size, group_n=group_n)
        _val_envs = build_therapy_envs(seed=config.env.seed + 1000, env_num=config.data.train_batch_size, group_n=1)
        
        projection_f = partial(identity_projection)
        envs = CounselingEnvironmentManager(_envs, projection_f, config)
        val_envs = CounselingEnvironmentManager(_val_envs, projection_f, config)
        return envs, val_envs
    else:
        print("Environment not supported")
        exit(1)
    