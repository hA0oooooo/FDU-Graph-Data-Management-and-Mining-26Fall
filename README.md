# FDU-Graph-Data-Management-and-Mining-26Fall

研究静态有向图上的精确 K-hop 可达性，比较查询时搜索、历史索引，以及按关键点和方向分配预处理半径的方案

[十图结果与比较](agent/round2-results.md) · [延迟图](results/round2/latency.svg) · [十图基线完成情况](results/round2/baseline-coverage.tsv) · [十图来源与版本](agent/catalogue.md) · [按查询阈值启用索引](agent/gate.md) · [项目导航](AGENTS.md)

##### 运行十图实验

从 Linux 仓库根目录运行。以下命令自动准备一张图，在同一份原图与真值上运行混合阈值、固定阈值、换源点复核、两个辅助索引和历史基线。结果放在 `results/local/`，数据文件保存在 `dataset/`。需要 Python 3.11 或更新版本、GCC、curl、GNU time 与常用 Linux 工具。首次运行需要获得冻结的公开数据，ESTI 从指定作者提交取得源码

```sh
python3 benchmark/radius/reproduce.py wiki-Vote --historical
```

将图名换成 `all` 逐一运行十图，省略 `--historical` 可单独研究半径策略。复测使用当前机器重新选择的半径；要检验已发布的冻结配置，用 `python3 benchmark/radius/confirm.py --graph wiki-Vote --build results/round2/wiki-Vote/build.tsv --balanced --output results/local/wiki-Vote-confirm.tsv`。历史参考实现与两档大图参数见 [Scalable K-Reach](agent/scalable.md) 与 [VCRea、定向 PLL](agent/cover-baselines.md)

##### 复核第一轮实验

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
