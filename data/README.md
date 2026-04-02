# `data/`

本目录适合准备评测输入、核对 `eval` 数据格式，或检查评测运行产物的读者；运行 `python -m src.eval` 前建议先看这里。

## 目录简介

`data/` 当前主要承载评测相关数据，不包含 `sample` / `rft` 的输入画像资产。

- `eval/`：供 `src.eval` 直接读取的原生评测 case 数据

`sample` / `rft` 的输入画像资产位于 [`../assets/profiles/`](../assets/profiles/)，由 `configs/datasets/*.yaml` 指定读取范围。

## 该目录在整个项目中的作用

在当前项目里，`data/` 的核心作用是为 `eval` 提供标准输入样例，并承接评测输出目录（运行时生成）。

- `eval` 可以直接消费 `data/eval` 的 case
- `eval` 也可以通过 [`../src/eval/io/input_adapter.py`](../src/eval/io/input_adapter.py) 适配 `sample` 产物后再评测

## 主要文件和子目录

### `eval/`

这是 `src.eval` 的原生输入目录。当前包含：

```text
eval/
  README.md
  bt/1.json
  cbt/1.json
  het/1.json
  pdt/1.json
  pmt/1.json
```

原生 `eval` case 采用评测侧结构，典型字段包括：

- `theoretical`
- `client_info`
- `global_plan`
- `sessions[].session_dialogue[]`

更精确的说明可直接参考 [`./eval/README.md`](./eval/README.md)。

## 与其他目录的关系

- 与 [`../configs/`](../configs/) 配合：`configs/runtime/eval_default.yaml` 决定 `eval` 的输入根目录与输出目录。
- 与 [`../assets/`](../assets/) 配合：`sample` / `rft` 的输入数据来自 `assets/profiles`，不在本目录。
- 与 [`../src/`](../src/) 配合：数据格式边界在 `input_adapter` 与各 dataclass schema 中定义。
- 与 [`../prompts/`](../prompts/) 配合：`eval` 会把对话与结构化字段拼入各方法提示词中。

## 阅读建议或使用入口

1. 想运行 `eval`：
   先看 [`./eval/README.md`](./eval/README.md)，再看 `eval/<modality>/1.json`。
2. 想评测 `sample` 产物：
   再看 [`../src/eval/io/input_adapter.py`](../src/eval/io/input_adapter.py)。
3. 想运行 `sample` / `rft`：
   直接看 [`../assets/profiles/`](../assets/profiles/) 与 [`../configs/datasets/`](../configs/datasets/)。

## 注意事项

- 当前仓库里的 `data/` 主要是评测输入样例与评测运行产物目录，而不是完整研究数据集。
- `eval` 默认输出根目录在 [`../configs/runtime/eval_default.yaml`](../configs/runtime/eval_default.yaml) 中配置为 `data/eval_outputs`，该目录通常属于运行时产物。
- 初始化技能库不在 `data/` 下，而是位于 [`../skills/sect`](../skills/sect)。

## 相关目录

- [根 README](../README.md)
- [`../configs/`](../configs/)
- [`../assets/`](../assets/)
- [`../prompts/`](../prompts/)
- [`../src/`](../src/)
