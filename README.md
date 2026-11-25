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
python3 src/run_baselines.py all --jobs 4
```

每次运行的日志、测量回执和 `coverage.tsv` 保存在本机的 `output/baselines/<运行目录>/`。[实验说明与复查](docs/baselines.md) · [数据版本](docs/datasets.md) · [方法设计](docs/adaptive-radius.md)
