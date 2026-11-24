# FDU-Graph-Data-Management-and-Mining-26Fall

研究静态有向图上的精确 K-hop 可达性，比较查询时搜索、历史索引，以及按关键点和方向分配预处理半径的方案

[实验结论与数据](agent/results.md) · [项目导航](AGENTS.md) · [数据与真值](agent/datasets.md) · [历史方法](agent/baselines.md)

##### 复核实验

在 Linux 仓库根目录执行，Python 使用标准库，历史方法使用 GCC。仓库内附冻结的查询和测量结果，实际图文件由准备脚本从 SNAP 获取

```sh
python3 dataset/prepare.py
python3 -m unittest discover -s tests
for graph in wiki-Vote p2p-Gnutella31; do
  python3 benchmark/run.py --graph "$graph" --output "results/local/$graph"
done
python3 baselines/esti/build.py
python3 baselines/esti/check.py --split confirmation wiki-Vote p2p-Gnutella31
python3 baselines/kreach/run.py
```

重建查询用 `python3 benchmark/make_workloads.py`，已发布的测量固定在单个 CPU 上，由 [实验计划](agent/plan.md) 说明参数和验收标准
