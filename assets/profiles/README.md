# `assets/profiles/`

本目录保存不同流派的来访者画像资产，供 `src/sample` 与 `src/rft` 通过 dataset 配置复用。

目录结构遵循 `DatasetLoader` 约定：

```text
profiles/
  bt/sample/*.json
  bt/rft/*.json
  cbt/sample/*.json
  cbt/rft/*.json
  ...
```

说明：

- `sample/`：供 `src/sample` 使用的画像切分。
- `rft/`：供 `src/rft` 使用的画像切分。
- 当前只整理了 `sample` 与 `rft` 两个切分；历史 `dev` / `rl` 未并入 `v0402` 的正式资产目录。

推荐配套配置：

- [`../../configs/datasets/profiles_sample.yaml`](../../configs/datasets/profiles_sample.yaml)
- [`../../configs/datasets/profiles_rft.yaml`](../../configs/datasets/profiles_rft.yaml)
