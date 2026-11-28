##### 对比任务与方法来源

在静态有向无权图 $G$ 上精确判断 $d_G(s,t)\le k$，不可达距离取 $+\infty$。所有主对照接受一般有向图，使用相同冻结原图与请求

| 方法 | 实现来源 | 对照作用 | 通过配置 |
| --- | --- | --- | ---: |
| 限深 BFS | 本项目 C++ 原图搜索 | 在线搜索、零索引预处理 | 15/15 |
| 双向限深 BFS | 本项目 C++ 原图双向搜索 | 在线搜索强基线 | 15/15 |
| K-Reach | Cheng 等，PVLDB 2012，算法 1–2 独立复现 | 完整顶点覆盖，三档距离编码，固定阈值 | 43/45 |
| Scalable K-Reach | Cheng 等，VLDB Journal 2014，算法 3–5 独立复现 | 两层部分覆盖、距离连接及残余搜索，固定阈值 | 45/45 |
| gen-k-reach | 同上，独立复现 | 两层索引支持变化阈值 | 15/15 |
| ESTI | Cai 与郑卫国，DASFAA 2021 Workshop，作者公开 C++ 源码 | 扩展生成树与拓扑过滤，可变阈值 | 15/15 |
| VCRea | Applied Sciences 2023，算法 1–5 独立复现 | 完整覆盖距离标签 | 15/15 |
| VCRea+ | 同上，独立复现 | 完整覆盖距离标签与度阈值增补 | 15/15 |
| Directed PLL | Akiba 等，SIGMOD 2013，§6 有向扩展独立实现 | 完整精确距离标签 | 15/15 |

固定阈值方法按 $k=2,4,6$ 各计一个配置，其余每图计一个。ESTI 的 LiveJournal1 使用仅扩容数组的作者程序版本，原版容量限制单独保存。K-Reach 的两个未通过配置为 LiveJournal1 四跳和六跳，已建立物理容量证明。其余逻辑配置共 193 项通过

原文为 [K-Reach 2012](https://vldb.org/pvldb/vol5/p1292_jamescheng_vldb2012.pdf)、[Scalable K-Reach 2014](https://www1.se.cuhk.edu.hk/~hcheng/paper/vldbj-cheng.pdf)、[ESTI 2021](https://doi.org/10.1007/978-3-030-73216-5_6)、[VCRea 2023](https://www.mdpi.com/2076-3417/13/6/3470)、[PLL 2013](https://arxiv.org/abs/1304.4661)。VCRea 直接用 Scalable K-Reach 与 ESTI 作者程序作为对照，2025 年 Computing Surveys 综述也专列 hop-constrained reachability 与 K-Reach。[综述](https://doi.org/10.1145/3776737)

ESTI 固定作者提交 `d893a28de9bf8f407ed24ebefc973f973be1e923`，校验下载包后编译，转换原图输入，增加逐条答案、批次计时和索引空间测量，保持扩展树构建与查询内核。LiveJournal 超出原版边数组容量时另建仅调整 maxm 的版本，保留两项状态。[作者仓库](https://github.com/YZ-Cai/ESTI)

K-Reach、Scalable K-Reach、VCRea 本次未取得作者程序，采用独立实现。PLL 作者公开程序读图时补双向边，因此按原论文有向双标签扩展独立实现。[PLL 作者仓库](https://github.com/iwiwi/pruned-landmark-labeling)

BFSI-B 与 MultiIndex 面向 DAG，用作 DAG 专项比较；普通可达性的 SCC 缩点会丢失原图跳数。WCF、Highway Cover 与 Landmark Hub Labeling 主要研究无向距离或路网。WKRI 研究权值区间和跳数联合约束，主体实验使用无向带权图。EVE 求解路径子图，标签约束可达性还要求路径标签满足相应约束。[WKRI](https://arxiv.org/abs/2403.13181) · [EVE](https://arxiv.org/abs/2304.12656)

##### 实现参数与正确性

- K-Reach 每个 $k=2,4,6$ 分别建立完整索引，排序稀疏行及两位密集行表示三种距离档位及不可达四态
- Scalable 主配置 $b=1000$ 与原文和 VCRea 的对照参数一致，第二层至多 128 根是工程实现的显式配置，若已经覆盖则提前停止。原文按可用内存继续选择第二层根，固定根数上限需在比较中注明。此前大图 $b=16$、第二层 4 根只作为低资源先验对照。[两层索引](scalable.md)
- VCRea+ 的接收端点度阈值 $d=1$，与论文主要对照一致。公开伪代码严格大于和等长去冗余存在歧义，本实现采用已知路径不长于当前 BFS 层的证据剪枝，亦保留严格条件与完整 BFS 变体用于小图复核。[覆盖标签及 PLL](cover-labels.md)

独立 Floyd–Warshall 和 BFS 核验覆盖边界、有环图、距离和方向。K-Reach 通过 69,120 条全点对判定，包含稀疏与两位密集编码。Scalable 自检 641 图共 582,786 条判定，包括跨层修正；VCRea、VCRea+、PLL 及其构建变体每种通过 7,650 条小图查询。ESTI 作者程序在 536 张图共通过 37,872 条判定。真实图仍按冻结请求逐条核验

##### 运行及统一复查

在仓库根目录，使用 Linux、Python 3.11 以上、GCC、curl、gzip、tar、GNU time

```sh
python3 src/run_baselines.py wiki-Vote
python3 src/run_baselines.py all --jobs 4 --cpu-count 72
python3 src/run_baselines.py wiki-Vote --fixed-k 4
python3 src/report_baselines.py output/baselines/runs/historical-core output/baselines/runs/historical-extra --output output/baselines/historical/performance.tsv
python3 src/run_baselines.py --review output/baselines/runs/historical-extra
```

默认正式 `benchmark.tsv`，`--query-name test.tsv` 选择小型诊断输入。均匀点对和分层难度分别使用 `--query-name benchmark-uniform.tsv` 与 `--query-name benchmark-stratified.tsv`，均能直接运行全套基线或半径方案。求解器单线程，默认没有墙钟上限，正式入口统一每项 48 GiB 地址空间上限，按图规模可通过 `--memory-gib 96` 或更高的预算配置所有方法。此前诊断运行给完整 K-Reach 96 GiB、其余方法 48 GiB，已完成配置的最大实测进程峰值 RSS 约 30.95 GiB，K-Reach 最大约 18.17 GiB，保留这些结果和实际执行上限。完整 K-Reach 的四个容量瓶颈均有超过 96 GiB 的严格下界证据。未来新实验保持同一图预算一致，`--kreach-memory-gib` 仅允许显式诊断。重复实验指定独立 `--output`，中断后相同程序和配置可用 `--resume` 从已有回执恢复

`run.json` 保存源码指纹、编译器、图列表、配置和运行机器。各图与方法的 JSON/TSV 和日志全部在本地 output，`performance.tsv` 由回执生成并校验查询和图 SHA-256，记录完成状态、查询数及错答、构建秒数、批查询秒数、首批时间、重复次数、平均延迟、原报告索引负载、实际辅助索引分配容量、就绪 RSS 和峰值 RSS（KiB）及相对回执路径。固定阈值每档分母仅包含该阈值请求；混合阈值独立构建一次。有效负载不含容器开销，峰值 RSS 含图和构建空间。未采集字段留空，失败配置的计时不参与比较

实验机器有 48 个物理核、96 个逻辑 CPU、503 GiB RAM。默认串行且绑定同一个可用逻辑 CPU（`--jobs 1 --cpu-count 1`）；并行验收可开放 72 个逻辑 CPU 并运行多个独立配置，每个求解器仍使用一个线程，运行元数据保存实际 CPU 亲和性与构建线程数，压力图多线程等价构建的结果单独标明，不混入单线程预处理比较。正式延迟比较使用串行、绑定相同 CPU、固定请求序列，预热一轮后重复完整批次五次取中位数。此前首次批查询保存用于初步分析，计时协议独立记录。[测量与排序标准](../workflow/evaluation.md)自适应方案使用同一 `benchmark.tsv` 作为最终测试，与独立训练和验证分离，构建计入选根、探测、调参和建表全部环节

##### 大图完整索引的容量

完整 K-Reach 的覆盖根数记 $r$。若根 $s$ 至少有 $L_s$ 个可达其他覆盖根，则当前行表示至少占 $\min(4L_s,\lceil r/4\rceil)$ 字节。用 32 个高入出度见证点分别做正反 BFS，依据真实路径组合建立 $L_s$ 的严格下界。对所有覆盖根求和得到当前稀疏/两位密集构造的负载下界，忽略容器及原图内存。[容量核验程序](../../src/baselines/kreach/capacity.cpp)

| 图 | $k=4$ 负载下界 GiB | $k=6$ 负载下界 GiB |
| --- | ---: | ---: |
| Pokec | 144.60 | 311.10 |
| LiveJournal1 | 586.23（最初下界 245.48） | 1793.37 |

两图 $k=4$ 均已在 96 GiB 地址空间下触发实际分配失败。$k=6$ 的下界严格超过该预算，保存已建前缀、取消信号及证据，记为 `capacity_proved`。这些下界针对当前确定的覆盖集和行编码。LiveJournal 的四跳、六跳下界均超过该服务器的 503 GiB RAM。Pokec 的四跳和六跳完整索引均有约 333.31 GiB 的负载上界，已在 384 GiB 预算下分别完成构建与查询验证。K-Reach 证据表及决策回执位于 `output/baselines/historical/kreach-capacity.tsv` 和原运行目录中的 `capacity_decisions.json`

进一步将目标覆盖集 $C$ 按距 512 个高入出度乘积见证点的最近正向距离划为互不重叠的子集 $P_i$。对于源点 $u$，设经见证点 $w$ 的可用剩余跳数为 $k-d(u,w)$，则每个子集可独立选择证实最多目标的见证点

$$
L_u=\max\left(0,\sum_i\max_{w:d(u,w)\le k}
\bigl|\{v\in P_i:d(w,v)\le k-d(u,w)\}\bigr|-1\right)
$$

各子集互斥，且每个计入目标都有原图路径证据，故 $L_u$ 是非自身可达覆盖根数的严格下界。对单行负载使用 $\min(4L_u,\lceil |C|/4\rceil)$，求和可得到整体负载下界。分区下界在 7,284 个小图核心行上与完整 BFS 距离核验一致，LiveJournal 四跳的实测证书为 629,454,501,006 bytes，超过物理内存与交换空间总计 583,554,162,688 bytes。原证据保留，新增证据及图、源码和二进制指纹存于 output/baselines/historical/kreach-partition-capacity.tsv

```sh
g++ -O3 -march=native -std=c++17 src/baselines/kreach/capacity.cpp -o cache/kreach-capacity
cache/kreach-capacity check
cache/kreach-capacity soc-LiveJournal1 4847571 dataset/prepared/soc-LiveJournal1.edges 4 512
```


##### 实验回执目录

- `output/baselines/runs/historical-core` 为原十图的扩大正式查询集
- `output/baselines/runs/historical-extra` 为新增五图，相同强基线配置，65 个配置已全部验证通过
- `output/baselines/historical/performance.tsv` 合并十五图，保留每条状态、指标与原始运行标识
- `output/validation/baselines/initial` 保存旧 2,849 条诊断查询和时间受限回执

##### 实测基线覆盖

本次 15 图使用 310,461 条唯一冻结查询。下表统计已完成并通过逐条判断的配置，固定阈值每图构建三次，通用阈值每图只构建一次

| 方法 | 已通过配置数 / 总数 |
| --- | ---: |
| BFS、双向 BFS | 各 15 / 15 |
| ESTI（含 LiveJournal 扩容版） | 15 / 15 |
| Scalable K-Reach / gen-k-reach | 45 / 45、15 / 15 |
| K-Reach | 41 / 45 |
| VCRea | 14 / 15 |
| VCRea+、Directed PLL | 各 13 / 15 |

原低预算与扩展组共通过 186 项、2,645,712 次判定，错答为零；另记录原版 ESTI 的一个固定数组容量限制、K-Reach 两个实际内存分配失败及两个严格容量下界证书。Pokec 和 LiveJournal 的六项完整标签构建曾因资源方案调整暂停，原回执保留；统一 48 GiB 后继续容量核验与补跑。LiveJournal 的 Directed PLL、VCRea+ 和 VCRea 已分别取得约 49.39 GiB、48.76 GiB、48.08 GiB 的必要编码下界，Pokec 的 PLL 和 VCRea+ 分别取得 48.02 GiB、48.13 GiB 的逐行分配容量下界。Pokec 的基础 VCRea 由八线程完整等价构建通过，实测构建 10,537.02 s，12,790,248,069 条标签，编码负载 26,173,860,885 bytes，峰值约 36.7 GiB，23,551 条查询零错答。该结果使用首次批次计时，单独保留，不参与单线程的严格排名。原低预算实验已全部形成完成或容量回执。上述容量证据针对当时的预算和编码布局，高内存补跑结果见下文

为候选方法对比，固定逻辑 CPU 46 和统一 48 GiB 复测六张代表图。runs/pilot 首批计时 78 项全部通过；runs/standard-small 统一预热及五次批次计时的 78 项、1,059,561 次判定也全部通过，均保存实际辅助索引大小。其余七张以同样的 CPU 46、48 GiB 和五轮协议补测，目录为 output/baselines/runs/standard-extended，91 项均通过。两批合并为 13 图、169 项配置、2,373,120 次判定，零错答；每项保留实际辅助索引空间和逐条答案。完整严格比较已生成于 output/baselines，主表 performance.tsv、分方法构建与查询回执和排名位于同一目录。候选试验与强消融见 [自适应半径](../research/adaptive-radius.md)

以 web-BerkStan 的 22,850 条正式查询为例，首次批查询耗时约为双向 BFS 0.070 s、gen-k-reach 0.258 s、VCRea+ 0.015 s。后两者构建分别约 10.3 s 与 61.5 s。Pokec 和 LiveJournal 的普通限深 BFS 批查询分别约 964 s 和 1,860 s，而双向 BFS 均约 0.56 s。两图的 gen-k-reach 构建分别约 459 s 与 902 s，批查询约 5.53 s 与 5.40 s。表明双向 BFS 是本查询分布下需要认真对比的在线基线，不能仅凭建表或命中标签推定最终收益

ESTI 的补测回执置于各运行目录的 esti-profile/，沿用原图、查询和作者程序，采集作者 index size 与 GNU time 峰值 RSS，保留原始首次实验回执与独立补测结果。其他指标口径与首次运行保持一致

##### 分方法存储与对比数据

新运行的目录以方法和图划分，固定阈值方法再按 k 划分，例如

```text
output/baselines/<run>/
  run.json
  performance.tsv
  methods/
    kreach/wiki-Vote/k4/build.json
    kreach/wiki-Vote/k4/query.json
    kreach/wiki-Vote/k4/answers.tsv
    gen-k-reach/wiki-Vote/build.json
    gen-k-reach/wiki-Vote/query.json
    vcrea/wiki-Vote/build.json
    vcrea/wiki-Vote/query.json
```

build.json 保存构建状态、完整索引构建时间、有效负载、已分配索引空间、驻留和峰值内存及资源预算；query.json 保存首批和中位批次时间、重复次数、平均延迟、查询数和错答数。新运行保留按冻结查询顺序的逐条布尔答案，固定阈值仅保留对应阈值子序列。索引在原生进程中构建并查询，构建报告记录其大小；当前算法没有索引持久化协议。已有正式回执也按相同结构导出，过去未保留逐条答案流的结果仍有逐条正确性统计与原始回执

全部十五张图的配置状态、构建与查询指标、索引和内存容量以及证据索引为 `output/baselines/coverage.tsv`，每项指向实际结果表、原始回执或容量证书，严格组与压力组不混合排名。补跑复查自动刷新此表，也可运行 `python3 src/baseline_coverage.py` 独立重建

正式汇总表直接位于 `output/baselines/performance.tsv`，方法级构建与查询数据位于同级 `methods/`，排名数据位于 `ranking/`。独立复测目录按数据集和实验用途命名，不使用日期或时间戳；构建时间、查询延迟及实验协议仍按原值保存

正式排名按 [评测标准](../workflow/evaluation.md) 执行，分别输出逐图各项指标和共同图排名。现有初步非支配数据仍保存在 output/baselines/historical/pareto/pareto.tsv。当前只生成数据

```sh
python3 src/report_baselines.py output/baselines/runs/standard-small output/baselines/runs/standard-extended --output output/baselines/performance.tsv
python3 src/rank_results.py output/baselines/performance.tsv --strict
```

13 张共同图的摊销加速及纯查询加速比几何平均如下，详细逐图时间、空间、吞吐及回收查询数见 ranking/metrics.tsv

| 方法 | 百万次查询摊销加速 | 十亿次查询摊销加速 | 纯查询加速 |
| --- | ---: | ---: | ---: |
| 双向 BFS | 1.000 | 1.000 | 1.000 |
| ESTI | 0.167 | 0.179 | 0.179 |
| VCRea+ | 0.153 | 1.706 | 1.883 |
| VCRea | 0.141 | 0.880 | 0.912 |
| K-Reach | 0.134 | 6.429 | 14.012 |
| Directed PLL | 0.133 | 1.489 | 1.641 |
| Scalable K-Reach | 0.116 | 0.279 | 0.281 |
| gen-k-reach | 0.069 | 0.138 | 0.139 |
| BFS | 0.030 | 0.030 | 0.030 |

在当前混合阈值负载和百万次查询规模下，双向 BFS 的总体时间最低；十亿次查询规模下，完整 K-Reach 的摊销优势明显。该结果适用于 13 张可完成全部方法的共同图，两张压力图的容量和运行指标另行记录。候选方法目前仅与相同协议的六张代表图直接比较

固定 k 比较使用 --fixed-k 2/4/6，所有算法收到同一阈值的冻结子查询。混合 k 的固定阈值方法各档索引构建时间、对应查询批次耗时和辅助索引大小相加，通用阈值方法构建一次。不同指标代表的空间范围与计时协议见评测标准

##### 高内存补跑

原预算下容量受限的配置保留原有证据和结果，另以串行方式提高内存至 256、384、448 GiB，最后可在物理容量允许时提高至 464 GiB。CPU 24–31 的构建预算为八线程，查询保持单线程。根据容量下界排除不足预算，完整 K-Reach 若已有负载上界则选择能覆盖该上界的初始预算，Pokec 四、六跳均从 384 GiB 起步。启动前等待共享主机留有对应预算及 32 GiB 可用内存余量。无墙钟限制

```sh
python3 src/run_stress.py output/baselines/historical/performance.tsv --output output/baselines/pressure --budgets 256 384 448 464 --cpu-set 24-31 --build-threads 8
python3 src/run_stress.py output/baselines/historical/performance.tsv --output output/baselines/pressure --review
```

完整标签的并行构建将每批根的记录按接收顶点分区，每个线程独立写入一个顶点区间，并在区间内保持根的递增次序。此实现通过 1,587 次完整逐字节索引比较以及 564 图标签计数核验。Pokec 的 PLL 前 4,096 根在八线程下进行单独的构建吞吐核验，顺序写入为 250.53 s，分区写入为 101.13 s，均生成 3,313,414,773 条标签和 6,627,346,373 字节编码；该前缀试验仅核验构建效率，不计入正式查询结果。email-EuAll 的完整 VCRea+ 两实现的编码、容量和逐条答案一致，分区写入在较小图上未加速。详细回执位于 output/validation/baselines/sharded-labels，已启动的完整构建使用启动时的源码指纹与原预算记录

多线程完整标签构建进一步使用混合实现，前 25% 根按位并行分区写入，其余根基于已建标签执行等价的标量剪枝。三种标签算法在 1,587 组小图及轮次切换检查中逐行比较了字节内容和分配容量。web-BerkStan 的 25%、50%、75%、100% 方案完整构建后均有相同标签数、编码量和行校验值

| 方法 | 全位并行构建 s | 前 25% 位并行构建 s |
| --- | ---: | ---: |
| VCRea | 126.37 | 73.17 |
| VCRea+ | 125.74 | 74.01 |
| Directed PLL | 158.00 | 95.66 |

八线程对比的完整记录在 output/validation/baselines/cover-hybrid/comparison.tsv，混合版本还在 Wiki-Vote 三方法的 59,118 条判定及 web-BerkStan 的 22,850 条 VCRea+ 判定上通过真值核验。后续多线程 packed 构建默认采用 25%，可通过 --packed-percent 100 选择完整位并行，回执保存实际 builder 和比例。已运行的压力配置沿用启动时的版本，实际构建器与位并行比例在每项的原始回执中记录

固定 K-Reach 并行构建使用与单线程相同的覆盖集和距离三档编码，每个线程持有独立 BFS 工作区并只写负责的索引行，按根编号的最终行完全一致。新版通过 69,120 次独立判定及逐行编码比较，Wiki-Vote 的真实冻结请求及完整压力入口也运行通过。Pokec 四跳前 512 根的吞吐核验为单线程 20.42 s、八线程 3.66 s，两者条目、扫描量、负载及行校验相同，见 output/validation/baselines/kreach-parallel。该前缀只衡量构建吞吐，完整构建仍以最终查询核验为准

output/baselines/pressure/run.json 保存补跑任务队列，`methods/<方法>/<图>/` 下按预算留存回执和逐条答案，`reviewed_performance.tsv` 保存实际复查结果，`output/baselines/coverage.tsv` 保存全部配置对应的证据

| 图 | 方法 | 预算 GiB | 构建 s | 辅助索引 GiB | 峰值 RSS GiB | 查询 µs | 通过数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pokec | PLL | 256 | 10076.23 | 未记录 | 63.48 | 40.548（首批） | 23551 |
| Pokec | VCRea+ | 256 | 6531.36 | 54.60 | 56.59 | 34.606 | 23551 |
| LiveJournal1 | PLL | 256 | 36542.83 | 159.49 | 175.88 | 35.583 | 23230 |
| LiveJournal1 | VCRea | 256 | 18555.17 | 84.20 | 92.29 | 76.827 | 23230 |
| LiveJournal1 | VCRea+ | 256 | 20056.34 | 126.38 | 137.23 | 40.661 | 23230 |
| Pokec | K-Reach k=4 | 384 | 3309.40 | 287.36 | 288.65 | 0.054 | 7933 |
| Pokec | K-Reach k=6 | 384 | 39055.43 | 314.05 | 303.29 | 0.043 | 7936 |

表中已通过的配置逐条答案均与冻结真值一致，错答为零；除标注首批外，查询时间为预热后五轮中位批次平均值。Pokec 的 PLL 原回执仅保存编码负载 46,092,602,219 bytes，不能当作实际分配空间。压力组使用八线程构建和更高内存预算，且固定阈值配置分档运行，因此不纳入普通 13 图的统一排名

LiveJournal 的 K-Reach 四跳和六跳的严格索引负载下界分别为 586.23 GiB、1793.37 GiB，超出实验机器的物理内存和交换空间总量；保留该表示的容量证明而不虚构耗时。Pokec 两档索引分别完成，但仅四、六跳的辅助索引空间之和已超过 384 GiB，不视为该预算下可同时驻留的混合阈值索引

##### 最终验收

十五张图的 196 条配置记录中，193 项已通过，共 2,778,373 次判定，错答为零；其余为两个已证物理容量不足的 K-Reach 配置和一个由扩容版本替代的原版 ESTI 配置。九个高内存补跑或容量核验项目均有终态，其中七项实际完成构建与查询，另外两项具备严格容量证据。正式 13 图的单线程统一协议排名保持独立，六图自适应初试及消融结果另见 [方法设计](../research/adaptive-radius.md)

原始图、索引构建及查询回执、全部结果表和逐条答案（正式组及压力补跑组）保存在实验机器本地，不将不同硬件资源组或不同计时协议的结果合并排名，也不生成图表。通过 coverage.tsv 可直接读取每个配置的构建时间、查询延迟、空间、实际资源和证据路径。最终核心算法回归测试回执保存在 output/validation/baselines/core-checks.tsv 和 core-cover-fixtures.json
