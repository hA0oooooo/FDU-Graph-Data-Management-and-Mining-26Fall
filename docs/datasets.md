##### 数据集选择和结构

15 张图（13 个公开真实网络、2 张控制图）共 135,112,376 条有向边。所有查询直接定义在冻结的有向边表。平均出度为 $m/n$，非自环密度为 $(m-m_{loop})/[n(n-1)]$，最大 SCC、度分布、互惠边及源汇点均已实测。[完整结构统计](../dataset/graph_stats.tsv)

| 图 | $n$ | $m$ | 平均出度 | 最大 SCC 规模或占比 | 来源与用途 |
| --- | ---: | ---: | ---: | ---: | --- |
| ArXiv-sub | 6,000 | 66,707 | 11.12 | 1 个点 | 2012/2014 引文图 |
| GO-sub | 6,793 | 13,361 | 1.97 | 1 个点 | 2012/2014 本体图 |
| CiteSeer-sub | 10,720 | 44,258 | 4.13 | 1 个点 | 2012/2014 引文图 |
| Wiki-Vote | 7,115 | 103,689 | 14.57 | 18.27% | 投票网络 |
| p2p-Gnutella31 | 62,586 | 147,892 | 2.36 | 22.61% | 较低平均度 P2P |
| email-EuAll | 265,214 | 420,045 | 1.58 | 12.90% | 通信网络，大外围 |
| email-Eu-core | 1,005 | 25,571 | 25.44 | 79.90% | 通信核心，高平均度 |
| web-Google | 875,713 | 5,105,039 | 5.83 | 49.65% | 网页、EVE 2023 |
| web-BerkStan | 685,230 | 7,600,595 | 11.09 | 48.87% | VCRea/EVE 2023 |
| wiki-Talk | 2,394,385 | 5,021,410 | 2.10 | 4.67% | 讨论、EVE 2023 |
| cit-Patents | 3,774,768 | 16,518,948 | 4.38 | 1 个点 | 2014 大型引用图 |
| soc-Pokec | 1,632,803 | 30,622,564 | 18.75 | 79.90% | 大型强连通社交核心 |
| soc-LiveJournal1 | 4,847,571 | 68,993,773 | 14.23 | 78.98% | EVE 2023、规模压力 |
| ER-2048-sparse | 2,048 | 10,412 | 5.08 | 98.63% | 有向随机图，密度 0.248% |
| ER-2048-dense | 2,048 | 418,112 | 204.16 | 100% | 有向随机图，密度 9.973% |

规模覆盖 1,005 至 4,847,571 顶点，真实图包含 DAG、强连通核心和外围、低平均度及高平均度网络。真实图按全体有序点对比例仍属稀疏图。为隔离密度因素，新增两张相同顶点数、共享随机序列、各有向弧概率 0.0025 与 0.1 的 ER 图

##### 论文关联及版本

2012/2014 的小规模实验均含 ArXiv、CiteSeer、GO，采用 GRAIL 作者分发图，点边规模一致。2014 的 patent 与当前 SNAP 原件相差一条边，实验保留 SNAP 原始自环。三张 GRAIL 图的距离定义在分发 DAG 上。[2012](https://vldb.org/pvldb/vol5/p1292_jamescheng_vldb2012.pdf) · [2014](https://www1.se.cuhk.edu.hk/~hcheng/paper/vldbj-cheng.pdf)

VCRea 2023 使用 BerkStan 和变换后 WikiTalk，后者与原始 SNAP 版本规模不同。原文还使用 EX6、3dtube、bio 高平均度图，本次官方 Network Repository 下载超时或返回 403，SuiteSparse 的 3dtube 分发亦未取得。当前用 SNAP email-Eu-core 和两档 ER 图覆盖高平均度及密度差异。[VCRea 表 3](https://www.mdpi.com/2076-3417/13/6/3470)

EVE 2023 表 2 使用 BerkStan、Google、WikiTalk、LiveJournal1，并在实验设置引用 K-Reach 2012/2014 和 ESTI。WKRI 表 6 亦列 Email-EuAll、Google、WikiTalk、LiveJournal 与 Patents，其中多项规模明显不同。[EVE §6.1](https://arxiv.org/html/2304.12656) · [WKRI §5.2](https://arxiv.org/html/2403.13181v2)

真实来源为 [SNAP](https://snap.stanford.edu/data/) 与 [GRAIL 作者归档](https://github.com/zakimjz/grail/tree/c13a7364fbc185841fc6277cd295acf33a7188f0/Downloads)。具体来源、原包及规范图哈希见 [两图清单](../dataset/manifest.json)、[目录](../dataset/catalogue.json)、[逐图冻结](../dataset/frozen/)。O’Reach citeseer_sub 与 GRAIL 的点边规模、可达有序点对统计一致，字节身份未取得

##### 数据准备

```sh
python3 src/prepare.py
python3 src/freeze.py
python3 src/generate_synthetic.py ER-2048-sparse ER-2048-dense
python3 src/graph_stats.py
python3 src/prepare_benchmark.py wiki-Vote
python3 tests/check_workloads.py
```

原始压缩包位于本地 `dataset/raw/`，规范文件 `dataset/prepared/<图名>.edges` 与 ID 映射保留原方向、自环并合并重复有向边。原包、边表、编号映射均有 SHA-256，合成图按 [固定种子及概率](../dataset/synthetic.json) 校验。原件全部在 Git 忽略目录

##### 正式查询

`dataset/workloads/<图名>/` 中保留训练、验证、小型诊断及正式 `benchmark.tsv`。正式集共 310,461 条不同请求，每图 15,360 至 23,551 条，128 个源点，固定种子 26112026

- `benchmark-uniform.tsv` 使用 64 个均匀抽取的源点，对 $k=2,4,6$ 分别抽 64 个无重复目标，保留真实随机点对的类别偏斜
- `benchmark-stratified.tsv` 使用另一组 64 个有出边的源点，对 $d<k$、$d=k$、$d=k+1$、$k+1<d<\infty$、不可达分别抽最多 12 个目标，类别为空时保留缺失
- 合并后固定顺序洗牌。每个 $d$ 由完整单源 BFS 得到，$-1$ 代表不可达。正式源点与训练、验证、诊断及此前复核全部隔离，另用反向 BFS 对每图三类最多各 8 条做独立距离核验，共 344 条通过

每图 `benchmark.json` 固定图及查询哈希、每组源点数与分类统计。所有正式对照读取相同的合并文件，固定阈值各建一套索引，通用方法建一次服务全批；选参只使用相互独立的训练与验证集
