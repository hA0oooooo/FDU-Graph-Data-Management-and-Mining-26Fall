# FDU Graph Data Management and Mining

研究静态有向图上的精确 K-hop 可达性。当前实验统一在相同原图和冻结查询上运行历史基线

| 目录 | 内容 |
| --- | --- |
| `src/` | 代码、数据准备和实验入口 |
| `docs/` | 数据说明、基线配置、方法设计与实验分析 |
| `dataset/` | 数据清单和冻结查询，图文件在本机的 `raw/` 与 `prepared/` |
| `tests/` | 算法正确性与数据处理测试 |
| `cache/`、`output/` | 本机编译缓存与运行结果 |

在 baojian 的仓库根目录运行

```sh
python3 src/run_baselines.py wiki-Vote
python3 src/run_baselines.py all --jobs 4 --cpu-count 72
python3 src/run_baselines.py wiki-Vote --fixed-k 4
```

正式对比读取 `output/baselines/performance.tsv`，全部图与配置的指标及状态见 `output/baselines/coverage.tsv`，各方法的构建和查询回执位于 `output/baselines/methods/<方法>/<图>/`，排名数据位于 `output/baselines/ranking/`。高内存补跑单独保存在 `output/baselines/pressure/`，候选方法结果位于 `output/adaptive-radius/main/`。新运行默认写入 `output/baselines/runs/<图>-<查询集>[-kN]/`，多图选集使用 `selected`，可用 `--output` 指定固定用途目录。结果不记录运行日期，只保留可复查的测量值和配置。默认单线程串行、每项 48 GiB 地址空间预算；完整配置与对比数据入口见文档。[实验说明与复查](docs/baselines.md) · [数据版本](docs/datasets.md) · [方法设计](docs/adaptive-radius.md) · [评测与排名](docs/evaluation.md)
