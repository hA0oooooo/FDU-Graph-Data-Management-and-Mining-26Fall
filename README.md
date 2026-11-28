# FDU Graph Data Management and Mining

静态有向图上的精确 K-hop 可达性研究，包含传统索引、在线搜索基线及自适应预处理方法

| 目录 | 内容 |
| --- | --- |
| `src/` | 算法实现、数据处理和实验入口 |
| `dataset/` | 图数据清单、冻结查询及本地图文件 |
| `docs/` | 基线、评测规范、研究分析和使用说明 |
| `tests/` | 独立正确性测试 |

在仓库根目录运行

```sh
python3 src/run_baselines.py wiki-Vote
python3 src/run_baselines.py wiki-Vote --fixed-k 4
```

已在 15 张图上验证 193 项基线配置；其余两项 K-Reach 配置有物理容量证明。实验原件、结果与缓存保存在本机，不随 Git 发布

[目录与入口](docs/workflow/layout.md) · [数据集](docs/workflow/datasets.md) · [基线](docs/baselines/overview.md) · [评测标准](docs/workflow/evaluation.md) · [自适应预处理](docs/research/adaptive-radius.md) · [按需分层索引](docs/research/hotspot-distance-index.md)
