# FDU Graph Data Management and Mining

静态有向图上的精确 K-hop 可达性研究，包含九类基线与按需分层距离索引。根据搜索中的剩余跳数，分别为关键点的入向、出向确定预处理深度，并在原图上保证精确查询

| 目录 | 内容 |
| --- | --- |
| `src/` | 算法实现、数据处理和实验入口 |
| `dataset/` | 图数据清单及冻结查询 |
| `docs/` | 基线、评测规范、研究分析和使用说明 |
| `tests/` | 独立正确性测试与实验复查 |

在 Linux 的仓库根目录运行。需要 Python 3.11 以上、GCC、GNU time、prlimit 和数据准备工具

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 src/run_baselines.py wiki-Vote
python3 tests/check_demand_profile.py
```

已在 15 张图上验证 193 项基线配置，其余两项 K-Reach 配置有容量证明。正式方法完成七图对照、构建消融和新源点确认。复查命令读取实验机器已有的本地回执，新环境的准备与运行入口见下方说明。原始图、编译缓存及实验输出保留本地

[最终方法与结果](docs/research/hotspot-distance-index.md) · [目录与运行入口](docs/workflow/layout.md) · [数据集](docs/workflow/datasets.md) · [九类基线](docs/baselines/overview.md) · [评测标准](docs/workflow/evaluation.md) · [前期方法](docs/research/adaptive-radius.md)
