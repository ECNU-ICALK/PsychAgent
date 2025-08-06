以下是上述代码的中文版本 `README.md`，适用于心理咨询 Agent 多轮对话模拟环境：

---

# 🧠 心理咨询环境：Client Agent 并行模拟框架

本项目基于 [Ray](https://docs.ray.io/) 实现了一个**并行多轮对话仿真环境**，用于训练和评估心理咨询师 Agent（如通过 RLHF 训练的语言模型）。系统通过模拟多个具备真实心理档案的来访者（Client Agent），与咨询师进行互动，实现**高效、多任务的对话学习框架**。

---

## 📁 项目结构

```text
agent_system/
│
├── environments/
│   └── env_package/
│       └── therapy/
│           ├── patient/
│           │   └── client.py          # 定义 ClientProfile 及可能的 mock 客户端
│           └── reward.py              # 包含基于规则的奖励函数
│
├── prompts/
│   └── therapy.py                     # 含 CLIENT_SYSTEM_TEMPLATE 和 CLIENT_INIT_USER 模板
│
├── examples/
│   └── dapo_trainer/
│       └── main_dapo.py               # RL 训练主入口
```

---

## ⚙️ 主要组件说明

### `ClientWorker`（基于 Ray 的远程 Actor）

* 表示一个**来访者客户端 Agent**，用于模拟一段心理咨询过程。
* 每个 Worker 对应一个来访者及其对话上下文。
* 功能包括：

  * 初始化来访者档案（`ClientProfile`）
  * 构建系统提示并调用 GPT 模型生成回复
  * 处理咨询师输入、计算回复与奖励

#### 主要方法

| 方法                    | 说明                            |
| --------------------- | ----------------------------- |
| `reset(profile_dict)` | 初始化来访者档案和初始上下文（GPT 作为 client） |
| `step(counselor_utt)` | 接收咨询师回复，生成来访者回应并计算奖励          |
| `close()`             | 释放资源（当前为空实现）                  |

---

### `CounselingEnvs`（并行环境管理器）

* 用于**批量管理多个来访者对话环境**，支持同时生成多个 episode。
* 主要用于强化学习训练中的并行交互。

#### 主要方法

| 方法                | 说明                           |
| ----------------- | ---------------------------- |
| `reset(profiles)` | 初始化多个来访者档案，并广播生成 N 个环境       |
| `step(actions)`   | 输入每个环境中的咨询师话语，统一调用 `step` 方法 |
| `close()`         | 关闭所有 Ray worker 实例并清理资源      |

---

### `build_therapy_envs(...)`

一个用于快速创建环境的构造函数，支持以下参数：

| 参数                 | 说明                            |
| ------------------ | ----------------------------- |
| `max_interactions` | 每个 episode 最多轮数（对话轮）          |
| `env_num`          | 并行环境数量（来访者数量）                 |
| `group_n`          | 每个来访者的复制数量（可用于 curriculum 学习） |
| `client_model`     | GPT 模型名称，如 `"gpt-4o-mini"`    |
| `temperature`      | 模型生成的采样温度（影响多样性）              |

---


---

## 🎯 奖励函数说明

在 `reward.py` 中定义了 `rule_based_reward(counselor_utt, client_reply)`


## 🚀 使用示例
python -m example.dapo_trainer.main_dapo