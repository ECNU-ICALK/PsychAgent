# `configs/`

这个目录适合想回答下面几个问题的读者：

- `sample`、`eval`、`rft` 各自需要哪几个配置文件
- 某个参数应该改在 `baseline`、`runtime`、`dataset` 还是 `rft-config`
- 想切换模型服务、控制数据规模、修改评测方法或 reward 端点时，应该从哪里下手

## 按工作流看需要哪些配置

```text
sample: baseline + runtime + dataset
eval: runtime
rft: baseline + runtime + dataset + rft runtime
```

如果你只想先跑起来，根目录 [`../README.md`](../README.md) 里的命令足够；如果你要改参数、换端点、缩小数据规模或排查配置边界，就从这里看。

## `sample` 需要什么

典型命令会同时读取三类配置：

- [`baselines/psychagent_sglang_local.yaml`](baselines/psychagent_sglang_local.yaml)
- [`runtime/psychagent_sglang_local.yaml`](runtime/psychagent_sglang_local.yaml)
- [`datasets/profiles_sample.yaml`](datasets/profiles_sample.yaml) 或其他 dataset YAML

三类配置分别负责：

- `baseline`
  控制咨询师模型端点和生成参数，例如 `backend`、`model`、`base_url`、`api_key_env`、`temperature`、`max_tokens`、`max_sessions`、`max_counselor_turns`、`end_token`。
- `runtime`
  控制运行行为，例如 `concurrency`、`resume`、`overwrite`、`save_dir`、`output_language`，以及 `client_*` 来访者模拟器参数、`psychagent_*` 会话与技能检索参数、`psychagent_embedding_*` embedding 参数。
- `dataset`
  控制读哪批 case，例如 `root_data_path`、`supported_modalities`、`split`、`max_cases`、`max_cases_per_modality`、`case_selection_strategy`、`filename_sort_policy`。

最常见的修改点是：

- 想换咨询师模型服务：改 `baselines/*.yaml`
- 想改输出语言、并发、续跑或来访者模拟器：改 `runtime/psychagent_sglang_local.yaml`
- 想缩小或切换 sample 数据集：改 `datasets/*.yaml`

## `eval` 需要什么

`eval` 只依赖运行配置，默认示例是：

- [`runtime/eval_default.yaml`](runtime/eval_default.yaml)

这一类配置主要负责：

- 输入输出路径：`data_root`、`output_root`
- 输入格式：`input_format`
- 评测端点：`api_key`、`api_base_url`、`api_model`
- 并发控制：`method_concurrency`、`file_concurrency`、`api_concurrency`、`api_rps`
- 运行行为：`resume`、`overwrite`、`case_limit`
- 方法选择：`supported_modalities`、`method_by_modality`

`eval` 还有一类常见情况是“YAML 给默认值，CLI 做临时覆盖”。最常见的 CLI 覆盖项有：

- `--input-format`
- `--data-root`
- `--output-root`
- `--modalities`

所以如果你只是临时想评测 `sample_outputs`，通常先不必改 YAML，直接改 CLI 就够了。

## `rft` 需要什么

`rft` 复用 `sample` 的三类配置，并额外增加一份 reward/rollout 配置：

- [`baselines/psychagent_sglang_local.yaml`](baselines/psychagent_sglang_local.yaml)
- [`runtime/psychagent_sglang_local.yaml`](runtime/psychagent_sglang_local.yaml)
- [`datasets/profiles_rft.yaml`](datasets/profiles_rft.yaml) 或其他 dataset YAML
- [`runtime/rft_default.yaml`](runtime/rft_default.yaml)

与 `sample` 相比，新增的 `rft runtime` 主要负责：

- rollout 规模：`rollout_n`、`rollout_concurrency`
- reward 并发：`reward_method_concurrency`、`reward_api_concurrency`、`reward_api_rps`
- reward 端点：`reward_api_key`、`reward_api_base_url`、`reward_api_model`
- 结果保留策略：`keep_all_rollout_transcripts`
- reward 方法映射：`method_by_modality`

如果你想把 reward evaluator 和主生成端点拆开，优先改 [`runtime/rft_default.yaml`](runtime/rft_default.yaml) 里的 `reward_api_*`。

## 当前目录里的示例文件各自适合什么场景

- [`baselines/psychagent_sglang_local.yaml`](baselines/psychagent_sglang_local.yaml)
  当前默认的咨询师模型连接配置。
- [`datasets/profiles_sample.yaml`](datasets/profiles_sample.yaml)
  基于内置画像资产的 `sample` 默认数据集。
- [`datasets/profiles_rft.yaml`](datasets/profiles_rft.yaml)
  基于内置画像资产的 `rft` 默认数据集。
- [`datasets/psycheval.yaml`](datasets/psycheval.yaml)
  五种 modality 的通用 `sample` 配置。
- [`datasets/psycheval_bt_cbt_het_pdt_pmt.yaml`](datasets/psycheval_bt_cbt_het_pdt_pmt.yaml)
  五种 modality、按 modality 限制样本量的配置。
- [`runtime/psychagent_sglang_local.yaml`](runtime/psychagent_sglang_local.yaml)
  `sample` 与 `rft` 共享的主 runtime 配置。
- [`runtime/eval_default.yaml`](runtime/eval_default.yaml)
  `eval` 默认运行配置。
- [`runtime/rft_default.yaml`](runtime/rft_default.yaml)
  `rft` 的 rollout 与 reward 配置。

## 路径和解析规则

- `datasets/*.yaml` 中的相对路径会按“相对于配置文件所在目录”解析，而不是相对于当前 shell 目录解析。
- `sample` 和 `rft` 的 dataset YAML 会先被 [`../src/sample/io/config_loader.py`](../src/sample/io/config_loader.py) 解析成 `DatasetConfig`，再交给 [`../src/sample/io/dataset_loader.py`](../src/sample/io/dataset_loader.py) 枚举和校验数据文件。
- `eval` 的 runtime YAML 会被 [`../src/eval/core/schemas.py`](../src/eval/core/schemas.py) 解析并校验。

## 推荐阅读顺序

1. 先看根目录 [`../README.md`](../README.md)，确认三个主入口命令。
2. 想跑 `sample` 时，看 `baselines/psychagent_sglang_local.yaml`、`runtime/psychagent_sglang_local.yaml`、`datasets/profiles_sample.yaml`。
3. 想跑 `eval` 时，看 `runtime/eval_default.yaml`。
4. 想跑 `rft` 时，再补看 `runtime/rft_default.yaml` 和 `datasets/profiles_rft.yaml`。
