# `prompts/`

本目录适合想理解模型输入、修改提示词或排查行为变化来源的读者；在调整咨询风格、评测标准或技能检索提示之前建议先看这里。

## 目录简介

`prompts/` 保存项目当前使用的提示词资产。这里既有 Jinja2 模板，也有直接拼接给模型的纯文本评分提示。它们分别被不同模块加载：

- `src/sample/core/prompt_manager.py`
- `src/sample/prompt_manager.py`
- `src/sample/skill_manager.py`
- `src/eval/utils.py`

这意味着提示词目录不是“附属文档”，而是运行逻辑的一部分。

## 该目录在整个项目中的作用

从功能上看，`prompts/` 可以分成三层：

- 生成层：驱动来访者模拟、咨询师对话、summary 与 profile 更新
- 技能层：在开启技能库时，为技能筛选与技能改写提供提示
- 评测层：为各量表或维度评分方法提供标准化评分提示

`sample` 和 `rft` 主要消费生成层与技能层，`eval` 主要消费评测层。

## 主要文件和子目录

### `public/`

供 `src/sample/core/prompt_manager.py` 使用的公共提示词：

- `counselor_system.jinja2`
- `session_opening.jinja2`
- `public_recap.jinja2`

这组模板定义的是“跨 modality 共享”的公共上下文，例如公开背景、历史摘要、作业回顾和开场语。

### `client/`

- `dialogue.jinja2`

这是来访者模拟器的核心输入模板，由 `ClientSimulator.generate_client_utterance()` 调用。模板里会拼入：

- `intake_profile`
- 历史摘要
- 上轮作业
- 咨询师最近一句话

如果你想调整来访者说话方式，优先从这里开始。

### `psychagent/`

这是 `sample` 与 `rft` 最直接相关的一组 modality 提示词。当前包含：

- `bt/`
- `cbt/`
- `het/`
- `pdt/`
- `pmt/`
- `skill/`

每个 modality 目录都遵循固定结构：

```text
<modality>/
  counsel/system.jinja2
  summary/system.jinja2
  summary/user.jinja2
  profile/system.jinja2
  profile/user.jinja2
```

这个结构不是约定俗成，而是 `src/sample/prompt_manager.py` 直接按路径硬编码读取的。如果你改目录名或文件名，运行会直接失败。

其中需要特别注意：

- `counsel/system.jinja2` 通常要求模型输出 `<think>` 与 `<response>` 两段
- `src/sample/runner.py` 在 `_chat_with_retry()` 中会提取 `<response>` 作为真实写入 transcript 的内容
- `skill/select_skill/` 和 `skill/rewrite/` 会由 `src/sample/skill_manager.py` 加载，并固定参与 coarse filter / turn-level retrieval 流程

### `eval/`

这是 `src.eval` 的评分提示词目录。大多数方法都采用：

```text
prompts/eval/<method_name>/<prompt_name>.txt
```

例如：

- `ctrs/collaboration.txt`
- `miti/empathy.txt`
- `psc/transference.txt`
- `tes/warmth.txt`

也有少数文件直接放在 `prompts/eval/` 根下，例如：

- `human_vs_llm_eval.txt`

这是因为 `src/eval/utils.py` 的 `load_prompt()` 同时支持“子目录模式”和“直接文件模式”。

## 与其他目录的关系

- 与 [`../src/`](../src/) 强耦合：目录结构和文件名会被代码直接引用。
- 与 [`../configs/`](../configs/) 配合：技能相关提示词路径可以通过 runtime 配置覆盖。
- 与 [`../data/`](../data/) 配合：数据文件提供 prompt 渲染时注入的 profile、history 和 dialogue 内容。

## 阅读建议或使用入口

如果你想快速建立整体认知，推荐按下面顺序阅读：

1. 先看 `public/counselor_system.jinja2` 和 `client/dialogue.jinja2`，理解公共对话约束。
2. 再看某一个 modality 的 `psychagent/<modality>/counsel/system.jinja2`、`summary/user.jinja2`、`profile/user.jinja2`，理解 `sample` / `rft` 如何组织一次 session。
3. 最后对照 [`../src/eval/methods/`](../src/eval/methods/) 查看 `eval/` 中的方法提示词。

## 注意事项

- 目录里既有 `.jinja2` 模板，也有 `.txt` 纯文本提示；不要把二者混为一类处理。
- `psychagent/<modality>/...` 的目录层级和文件名是 `src/sample/prompt_manager.py` 的输入契约，不建议随意调整。
- `eval` 提示词的组织方式以 `src/eval/utils.py::load_prompt()` 为准。并不是所有方法都必须在自己的子目录里有同名文件。
- 技能相关提示词虽然在仓库中存在，但当前示例 runtime 默认关闭技能库加载；如果没有外部技能资产，仅修改这些 prompt 不会让功能自动可用。

## 相关目录

- [根 README](../README.md)
- [`../configs/`](../configs/)
- [`../data/`](../data/)
- [`../src/`](../src/)
