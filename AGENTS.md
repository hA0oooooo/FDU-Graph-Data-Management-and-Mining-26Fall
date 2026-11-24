##### 项目导航

| 要做的事 | 先读 | 代码或数据入口 |
| --- | --- | --- |
| 接续本轮研究、判断下一组实验 | [实验结论](agent/results.md)、[计划与比较条件](agent/plan.md) | [发现集结果](results/round1/)、[独立复核结果](results/confirmation/) |
| 准备相同图和查询 | [数据、方向和采样](agent/datasets.md) | [数据准备](dataset/prepare.py)、[数据清单](dataset/manifest.json)、[生成真值](benchmark/make_workloads.py) |
| 理解或更换半径分配策略 | [索引定义和正确性](agent/method.md) | [搜索和索引](src/khop.py)、[边界用例](tests/test_khop.py) |
| 增加历史方法或核对复现口径 | [已运行的方法及来源](agent/baselines.md) | [作者 ESTI 适配](baselines/esti/)、[固定阈值 K-Reach](baselines/kreach/) |
| 复查计时和空间 | [比较口径](agent/results.md) | [计时驱动](benchmark/run.py)、[冻结查询](benchmark/workloads/) |

工作从仓库根目录开始。原始数据在 `dataset/raw/`，有向边表在 `dataset/prepared/`，Git 保存来源、版本、校验值及生成命令。新一轮先固定对照、样本与成本口径，再跑实验；新测量使用单独输出路径，保留此前实际采集的数据

修改查询机制后先跑小图全点对检查，再逐条对比独立真值。一次里程碑通过关键验收后集中提交推送
