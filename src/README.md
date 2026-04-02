# `src/`

本目录适合想理解项目代码入口、模块边界和阅读顺序的读者；在准备二次开发、排查运行问题或扩展新方法之前建议先看这里。

## 目录简介

`src/` 是 `PsychAgent_v0402` 的代码主体。当前仓库把能力分成四个顶层模块：

- `sample/`：多 session 咨询对话生成
- `eval/`：量表与维度评测
- `rft/`：基于 rollout + reward 的 best-of-n 轨迹选择
- `shared/`：跨模块复用的路径、文件与 YAML 工具

根目录的 [`../README.md`](../README.md) 已给出高层介绍；本页重点说明“代码从哪里进、往哪里走”。

## 该目录在整个项目中的作用

整体执行关系可以简化为：

1. `sample` 从 `assets/profiles` 读取 case，生成 `course.json` 与 `session_*.json`
2. `eval` 直接评测标准 case，或适配 `sample` 产物后再评测
3. `rft` 复用 `sample` 做多条 rollout，再复用 `eval.reward` 计算 reward 选优
4. `shared` 为三者提供尽量保守的基础设施复用

因此，如果你想理解一个完整实验流，通常需要同时阅读 `sample`、`eval` 和 `rft` 三层，而不是只看单个脚本。

## 主要文件和子目录说明

### `sample/`

当前项目的生成主流程，入口是：

- `sample/__main__.py`
- `sample/main.py`

第一次阅读时最值得关注的文件是：

- `sample/main.py`
  负责命令行参数、配置加载和 runner 初始化。
- `sample/runner.py`
  核心执行流。负责并发跑 case、单 session 对话推进、summary/profile 更新、结果落盘、续跑恢复。
- `sample/io/dataset_loader.py`
  定义画像数据集的 case 发现与校验规则。
- `sample/io/store.py`
  定义运行结果的落盘结构，例如 `save_root/<baseline>/<modality>/<case_id>/session_*.json` 与 `course.json`。
- `sample/core/prompt_manager.py`
  读取 `prompts/public/` 与 `prompts/client/`。
- `sample/prompt_manager.py`
  读取 `prompts/psychagent/<modality>/...`。
- `sample/client/simulator.py`
  来访者模拟器。
- `sample/skill_manager.py`
  技能检索逻辑；只在开启技能库时真正参与流程。
- `sample/models.py`
  定义各 modality 的 summary/profile schema。

一个容易混淆但很重要的点是：`sample/core/prompt_manager.py` 和 `sample/prompt_manager.py` 负责的是两套不同 prompt 目录。

### `eval/`

评测入口是：

- `eval/__main__.py`
- `eval/main.py`

核心阅读路径建议是：

- `eval/main.py`
  负责 CLI 参数和运行配置合并。
- `eval/manager/evaluation_orchestrator.py`
  负责 case 发现、session 级编排、方法并发执行与结果汇总。
- `eval/io/input_adapter.py`
  定义 `eval_case` 与 `sample` 产物之间的适配逻辑。
- `eval/reward.py`
  提供给 `rft` 复用的程序化 reward 接口。
- `eval/methods/`
  评测方法注册表与具体实现。

`eval/methods/` 下的代码又大致分成三类：

- `client/`：如 `PANAS`、`SRS`、`BDI_II`
- `counselor/`：如 `MITI`、`CTRS`、`WAI`
- 根级方法：如 `rro.py`

这些方法普遍通过 `prompts/eval/` 加载评分提示词，并在 `core/base.py` 中复用 JSON 输出修复逻辑。

### `rft/`

入口是：

- `rft/__main__.py`
- `rft/main.py`

重点文件包括：

- `rft/main.py`
  负责加载 baseline、sample runtime、dataset 和 rft runtime。
- `rft/runner.py`
  继承自 `sample.runner.PsychAgentRunner`，在 session 级逻辑里插入 rollout 与 reward 选择。
- `rft/reward.py`
  负责 reward 聚合与分数计算。

如果你想知道 `rft` 与 `sample` 的边界，最直接的方法是对照 `sample/runner.py` 和 `rft/runner.py` 一起看。

### `shared/`

这是当前项目中真正稳定的共享层，规模很小，但边界很明确：

- `shared/file_utils.py`
  提供 `project_root()`、安全文件名和 JSON 写入工具。
- `shared/config_utils.py`
  提供 YAML 加载，且在没有 `PyYAML` 时保留一个轻量 fallback。

## 与其他目录的关系

- 与 [`../configs/`](../configs/) 配合：`main.py` 系列入口都会先读配置，再决定加载哪个模块。
- 与 [`../prompts/`](../prompts/) 配合：`sample`、`rft`、`eval` 都会直接按路径读取 prompt。
- 与 [`../data/`](../data/) 配合：`eval` 从 `eval` 或 `sample` 输出读取输入。
- 与 [`../assets/`](../assets/) 配合：`sample` / `rft` 从 `profiles` 读取输入。
- 与 [`../tests/`](../tests/) 配合：如果你想确认边界而不是只看实现，测试目录通常比 README 更接近“可执行规范”。

## 阅读建议或使用入口

推荐按照任务目的选择阅读路径：

1. 想运行生成流程：
   从 `sample/main.py` 看起，再进入 `sample/runner.py`。
2. 想理解评测流程：
   从 `eval/main.py` 看起，再进入 `eval/manager/evaluation_orchestrator.py` 和 `eval/io/input_adapter.py`。
3. 想理解 reward 训练数据生成：
   从 `rft/main.py` 看起，再对照 `rft/runner.py` 与 `eval/reward.py`。
4. 想理解数据与配置约束：
   结合 [`../data/`](../data/) 和 [`../configs/`](../configs/) 一起看。

## 注意事项

- 当前仓库中 `sample`、`eval`、`rft` 都支持 `python -m src.<module>` 方式运行，这些入口在各自的 `__main__.py` 中暴露。
- `eval/methods/*` 中多处使用了 Pydantic v2 风格的 `ConfigDict` 和 `model_validate()`；如果运行环境过旧，这一层可能先于业务逻辑报错。
- `rft` 并不是完全独立的新栈，而是显式复用 `sample` 与 `eval` 的一层组合代码。
- `shared/` 当前只承接基础设施复用；如果你在这里看到太多业务逻辑，通常说明模块边界正在变得模糊。

## 相关目录

- [根 README](../README.md)
- [`../configs/`](../configs/)
- [`../data/`](../data/)
- [`../prompts/`](../prompts/)
- [`../tests/`](../tests/)
