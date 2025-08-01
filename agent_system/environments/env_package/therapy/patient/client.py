
import argparse
import json
import logging
import os
from dataclasses import dataclass
from time import sleep
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import ray
import requests
from dotenv import load_dotenv
from openai import OpenAI


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
    
    res = [
        ClientProfile("小李", 27, "女", "产品经理", "长期加班导致焦虑与睡眠问题", "内向、追求完美、敏感", "缓解焦虑、改善睡眠"),
        ClientProfile("阿强", 34, "男", "销售", "与伴侣冲突频繁、情绪爆发", "外向、急躁、重面子", "改善沟通、稳定关系"),
        ClientProfile("欣欣", 19, "女", "大一学生", "社交恐惧与自我怀疑", "害羞、敏感、想太多", "提高社交自信"),
        ClientProfile("王伟", 41, "男", "工程师", "职业倦怠、动机下降", "务实、理性、压抑表达", "重新找回动力与意义感"),
        ClientProfile("婷婷", 29, "女", "自由职业者", "拖延严重、作息混乱", "有创造力、易分心", "形成稳定作息、提升执行"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
    ]
    
    
    return res
    
def default_val_profiles() -> List[ClientProfile]:
    
    res = [
        ClientProfile("小李", 27, "女", "产品经理", "长期加班导致焦虑与睡眠问题", "内向、追求完美、敏感", "缓解焦虑、改善睡眠"),
        ClientProfile("阿强", 34, "男", "销售", "与伴侣冲突频繁、情绪爆发", "外向、急躁、重面子", "改善沟通、稳定关系"),
        ClientProfile("欣欣", 19, "女", "大一学生", "社交恐惧与自我怀疑", "害羞、敏感、想太多", "提高社交自信"),
        ClientProfile("王伟", 41, "男", "工程师", "职业倦怠、动机下降", "务实、理性、压抑表达", "重新找回动力与意义感"),
        ClientProfile("婷婷", 29, "女", "自由职业者", "拖延严重、作息混乱", "有创造力、易分心", "形成稳定作息、提升执行"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
        ClientProfile("陈晨", 31, "男", "设计师", "自我价值感低、否定自己", "完美主义、敏感", "增强自我接纳"),
    ]
    
    return res
    
class _BaseChat:
    def __init__(self, model: str, temperature: float, max_output_tokens: int):
        self.model = model
        self.temperature = float(temperature)
        self.max_output_tokens = int(max_output_tokens)

    def generate(self, messages: List[Dict[str, Any]], temperature: Optional[float] = None,
                 max_output_tokens: Optional[int] = None) -> str:
        raise NotImplementedError


class Xmindai():
    def __init__(self,params=None):
        self.params = params
        self.tools = []  # 工具在定义角色时传递，所以初始化设置为空
        self.api_key='7d88e6a14f3b40e4863ca8cf586bbed7'

    def check_model(self,used_model):
        if used_model=='gpt-3.5-0125':
            return 'xchatgptv3'
        elif used_model=='gpt-4o':
            return 'xchat4o'

    def get_message(self, messages_list,used_model='gpt-4o'):  # 如果需要修改供应商和chatgpt的设置，请在这里修改
        headers = {
            'api-key':self.api_key,
            'tppBizNo':"D6AD5316-F6CF-4E93-B7BF-05756E11465C"
        }
        '''
        deploymentName
        gpt-3.5-turbo	xchatgpt
        gpt-4	xchat4
        gpt-4-32k	xchat432
        gpt-3.5-turbo-16k	xchatgpt16
        gpt-3.5-turbo-1106	xchatgptv2
        gpt-4-turbo	xchat4t
        gpt-4-turbo-vision	xchat4v
        gpt-3.5-turbo-0125	xchatgptv3
        gpt-4o	xchat4o
        text-embedding-ada-002	xembedding
        '''
        apiVersion='2024-05-01-preview'
        chat_url=f'https://aoai-apis.xmindai.cn/openai/deployments/{self.check_model(used_model)}/chat/completions?api-version={apiVersion}'
        # 设置GPT的参数
        '''
            model: 模型类别（0：gpt-3.5-turbo，1：gpt-4，2：gpt-4-32k，3：gpt-3.5-turbo-16k），尽量用0，节省。token容易超出，就用3
            temperature:
                要使用的采样温度，介于 0 和 2 之间。 较高的值（如 0.8）将使输出更随机，而较小的值（如 0.2）将使输出更集中，更具确定性。 
                我们通常建议更改此设置或 top_p，但不能同时更改两者。
            top_p:
                温度采样的替代方法，称为核采样，其中模型考虑具有 top_p 概率质量的令牌的结果。 所以 0.1 意味着只考虑包含前 10% 概率质量的令牌。 
                我们通常建议更改此设置或温度，但不要同时更改这两者。
            n:  每个提示生成多少完成次数。
            presence_penalty: 在-2.0和2.0之间的数字。正值根据它们在文本中出现的情况对新令牌进行惩罚，从而增加模型谈论新主题的可能性
            frequency_penalty: 在-2.0和2.0之间的数字。正值会根据文本中现有词频惩罚新令牌，从而降低模型重复相同行的可能性。
        '''
        param2gpt = {
            "messages": [],  # gpt交互的消息列表
            "temperature": 1 if 'temperature' not in self.params.keys() else self.params['temperature'],
            "top_p": 1 if 'top_p' not in self.params.keys() else self.params['top_p'],
            "n": 1 if 'n' not in self.params.keys() else self.params['n'],
            "stream": False if 'stream' not in self.params.keys() else self.params['stream'],
            "max_tokens": None if 'max_tokens' not in self.params.keys() else self.params['max_tokens'],
            "presence_penalty": 0 if 'presence_penalty' not in self.params.keys() else self.params['presence_penalty'],
            "frequency_penalty": 0 if 'frequency_penalty' not in self.params.keys() else self.params['frequency_penalty'],
            # # "function_call": "auto" if 'function_call' not in self.params.keys() else self.params['function_call'],
            # # "functions": self.tools
            #"tool": self.tools,
            #"tool_choice": "auto" if 'tool_choice' not in self.params.keys() else self.params['tool_choice']
        }

        # 设置GPT的参数
        data = param2gpt
        data['messages'] = messages_list  # 更新messages
        print(messages_list)
        requests.packages.urllib3.disable_warnings()

        time = 0
        while time < 10:
            time += 1
            try:
                # 发送 POST 请求
                response = requests.post(chat_url, headers=headers, json=data, verify=False)

                # 检查响应状态码
                if response.status_code == 200:
                    # 解析并打印响应内容
                    result = response.json()
                    print(result)
                    return result
                else:
                    # 处理非 200 状态码
                    try:
                        error_message = response.json()["error"]["message"]
                        if "Rate limit reached for gpt-4o in organization" in error_message:
                            print(error_message)
                            sleep(5)
                        elif "Remote end closed connection without response" in error_message:
                            print(error_message)
                            sleep(5)
                        else:
                            print(f"Error: {response.status_code}, {error_message}")
                    except (ValueError, KeyError, TypeError):
                        # 如果响应体不是有效的 JSON 或不包含 'error' 键
                        print(
                            f"Error: Unable to parse error message from response. Status code: {response.status_code}")

                        # 可以在这里添加重试逻辑，但请注意避免无限循环
                    # 这里只是简单地打印错误并继续执行后续代码

            except requests.exceptions.RequestException as e:
                # 处理网络请求异常（如连接错误）
                print(f"Request failed: {e}")
                sleep(30)
        return {"extra": messages_list}



class OpenAIChat(_BaseChat):
    """
    Minimal wrapper around OpenAI Responses API.
    """
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7, max_output_tokens: int = 400):
        super().__init__(model, temperature, max_output_tokens)
        # if not _HAS_OPENAI:
        #     raise RuntimeError("OpenAI SDK unavailable or MOCK=1. Set MOCK=1 to use MockChat.")
        self.client = Xmindai(params={"temperature": 0})

    def generate(self, messages: List[Dict[str, Any]], temperature: Optional[float] = None,
                 max_output_tokens: Optional[int] = None) -> str:
        # t = self.temperature if temperature is None else float(temperature)
        # mot = self.max_output_tokens if max_output_tokens is None else int(max_output_tokens)
        # resp = self.client.responses.create(
        #     model=self.model,
        #     input=messages,
        #     temperature=t,
        #     max_output_tokens=mot
        # )
        question =  "\n".join([msg["content"] for msg in messages])
        
        
        
        round_user = {"role": "user", "content": [{"type": "text", "text": question}]}
        messages =  [round_user]
        # print(messages)
        response = self.client.get_message(messages, 'gpt-4o')
        
        resp = response["choices"][0]["message"]["content"].strip().strip("```json").strip("```").strip()
            
        return resp.output_text.strip()

