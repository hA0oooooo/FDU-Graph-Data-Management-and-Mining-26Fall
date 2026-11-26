##### 对比任务与方法来源

在静态有向无权图 $G$ 上精确判断 $d_G(s,t)\le k$，不可达距离取 $+\infty$。所有主对照接受一般有向图，使用相同冻结原图与请求

| 方法 | 实现来源 | 对照作用 |
| --- | --- | --- |
| 限深 BFS、双向限深 BFS | 本项目 C++ 原图搜索 | 在线时间、零索引预处理 |
| K-Reach | Cheng 等，PVLDB 2012，算法 1–2 独立复现 | 完整顶点覆盖，三档距离编码，固定阈值 |
| Scalable K-Reach、gen-k-reach | Cheng 等，VLDB Journal 2014，算法 3–5 独立复现 | 两层部分覆盖、距离连接及残余搜索，固定与混合阈值 |
| ESTI | Cai 与郑卫国，DASFAA 2021 Workshop，作者公开 C++ 源码 | 扩展生成树与拓扑过滤，可变阈值 |
| VCRea、VCRea+ | Applied Sciences 2023，算法 1–5 独立复现 | 完整覆盖距离标签与度阈值增补 |
| Directed PLL | Akiba 等，SIGMOD 2013，§6 有向扩展独立实现 | 完整精确距离标签 |

原文为 [K-Reach 2012](https://vldb.org/pvldb/vol5/p1292_jamescheng_vldb2012.pdf)、[Scalable K-Reach 2014](https://www1.se.cuhk.edu.hk/~hcheng/paper/vldbj-cheng.pdf)、[ESTI 2021](https://doi.org/10.1007/978-3-030-73216-5_6)、[VCRea 2023](https://www.mdpi.com/2076-3417/13/6/3470)、[PLL 2013](https://arxiv.org/abs/1304.4661)。VCRea 直接用 Scalable K-Reach 与 ESTI 作者程序作为对照，2025 年 Computing Surveys 综述也专列 hop-constrained reachability 与 K-Reach。[综述](https://doi.org/10.1145/3776737)

ESTI 固定作者提交 `d893a28de9bf8f407ed24ebefc973f973be1e923`，校验下载包后编译，仅增加每条答案输出，转换原图输入和新增测量字段。LiveJournal 超出原版边数组容量时另建仅调整 maxm 的版本，保留两项状态。[作者仓库](https://github.com/YZ-Cai/ESTI)

K-Reach、Scalable K-Reach、VCRea 本次未取得作者程序，采用独立实现。PLL 作者公开程序读图时补双向边，因此按原论文有向双标签扩展独立实现。[PLL 作者仓库](https://github.com/iwiwi/pruned-landmark-labeling)

BFSI-B 与 MultiIndex 面向 DAG，用作 DAG 专项比较；普通可达性的 SCC 缩点会丢失原图跳数。WCF、Highway Cover 与 Landmark Hub Labeling 主要研究无向距离或路网。WKRI 研究权值区间和跳数联合约束，主体实验使用无向带权图。EVE 求解路径子图，标签约束可达性还要求路径标签满足相应约束。[WKRI](https://arxiv.org/abs/2403.13181) · [EVE](https://arxiv.org/abs/2304.12656)

##### 实现参数与正确性

- K-Reach 每个 $k=2,4,6$ 分别建立完整索引，排序稀疏行及两位密集行表示三种距离档位及不可达四态
- Scalable 主配置 $b=1000$ 与原文和 VCRea 的对照参数一致，第二层至多 128 根是工程实现的显式配置，若已经覆盖则提前停止。原文按可用内存继续选择第二层根，固定根数上限需在比较中注明。此前大图 $b=16$、第二层 4 根只作为低资源先验对照。[两层索引](baselines/scalable.md)
- VCRea+ 的接收端点度阈值 $d=1$，与论文主要对照一致。公开伪代码严格大于和等长去冗余存在歧义，本实现采用已知路径不长于当前 BFS 层的证据剪枝，亦保留严格条件与完整 BFS 变体用于小图复核。[覆盖标签及 PLL](baselines/cover-labels.md)

独立 Floyd–Warshall 和 BFS 核验覆盖边界、有环图、距离和方向。K-Reach 通过 69,120 条全点对判定，包含稀疏与两位密集编码。Scalable 自检 641 图共 582,786 条判定，包括跨层修正；VCRea、VCRea+、PLL 及其构建变体每种通过 7,650 条小图查询。ESTI 作者程序在 536 张图共通过 37,872 条判定。真实图仍按冻结请求逐条核验

##### 运行及统一复查

在 baojian 仓库根目录，使用 Linux、Python 3.11 以上、GCC、curl、gzip、tar、GNU time

```sh
python3 src/run_baselines.py wiki-Vote
python3 src/run_baselines.py all --jobs 4 --cpu-count 72
python3 src/run_baselines.py wiki-Vote --fixed-k 4
python3 src/report_baselines.py output/baselines/20261126-full-ten output/baselines/20261126-extensions --output output/baselines/20261126-complete/performance.tsv
python3 src/run_baselines.py --review output/baselines/20261126-extensions
```

默认正式 `benchmark.tsv`，`--query-name test.tsv` 选择小型诊断输入。均匀点对和分层难度分别使用 `--query-name benchmark-uniform.tsv` 与 `--query-name benchmark-stratified.tsv`，均能直接运行全套基线或半径方案。求解器单线程，默认没有墙钟上限，正式入口统一每项 48 GiB 地址空间上限，按图规模可通过 `--memory-gib 96` 或更高的预算配置所有方法。此前诊断运行给完整 K-Reach 96 GiB、其余方法 48 GiB，已完成配置的最大实测进程峰值 RSS 约 30.95 GiB，K-Reach 最大约 18.17 GiB，保留这些结果和实际执行上限。完整 K-Reach 的四个容量瓶颈均有超过 96 GiB 的严格下界证据。未来新实验保持同一图预算一致，`--kreach-memory-gib` 仅允许显式诊断。重复实验指定独立 `--output`，中断后相同程序和配置可用 `--resume` 从已有回执恢复

`run.json` 保存源码指纹、编译器、图列表、配置和运行机器。各图与方法的 JSON/TSV 和日志全部在本地 output，`performance.tsv` 由回执生成并校验查询和图 SHA-256，记录完成状态、查询数及错答、构建秒数、首次批查询秒数、均值、索引有效负载和进程峰值 KiB及相对回执路径。固定阈值每档分母仅包含该阈值请求；混合阈值独立构建一次。有效负载不含容器开销，峰值 RSS 含图和构建空间。未采集字段留空，失败配置的计时不参与比较

baojian（xsuper）有 48 个物理核、96 个逻辑 CPU、503 GiB RAM。默认串行且绑定同一个可用逻辑 CPU（`--jobs 1 --cpu-count 1`）；并行验收可开放 72 个逻辑 CPU 并运行多个独立配置，每个求解器仍使用一个线程，运行元数据保存实际 CPU 亲和性。精细论文延迟比较使用串行、绑定相同 CPU、固定请求序列，并明确缓存条件和重复次数。当前整批均值无法推导 P95，需另行采集逐条延迟。自适应方案使用同一 `benchmark.tsv` 作为最终测试，与独立训练和验证分离，构建计入选根、探测、调参和建表全部环节

##### 大图完整索引的容量

完整 K-Reach 的覆盖根数记 $r$。若根 $s$ 至少有 $L_s$ 个可达其他覆盖根，则当前行表示至少占 $\min(4L_s,\lceil r/4\rceil)$ 字节。用 32 个高入出度见证点分别做正反 BFS，依据真实路径组合建立 $L_s$ 的严格下界。对所有覆盖根求和得到当前稀疏/两位密集构造的负载下界，忽略容器及原图内存。[容量核验程序](../src/baselines/kreach/capacity.cpp)

| 图 | $k=4$ 负载下界 GiB | $k=6$ 负载下界 GiB |
| --- | ---: | ---: |
| Pokec | 144.60 | 311.10 |
| LiveJournal1 | 245.48 | 1793.37 |

两图 $k=4$ 均已在 96 GiB 地址空间下触发实际分配失败。$k=6$ 的下界严格超过该预算，保存已建前缀、取消信号及证据，记为 `capacity_proved`。这些下界针对当前确定的覆盖集和行编码。LiveJournal 的六跳下界也超过该服务器的 503 GiB RAM。其他方法仍按实际完成或资源失败记录。证据表及决策回执位于 `output/baselines/20261126-complete/kreach-capacity.tsv` 和原运行目录中的 `capacity_decisions.json`

##### 实验回执目录

- `output/baselines/20261126-full-ten` 为原十图的扩大正式查询集
- `output/baselines/20261126-extensions` 为新增五图，相同强基线配置，65 个配置已全部验证通过
- `output/baselines/20261126-complete/performance.tsv` 合并十五图，保留每条状态、指标与原始运行标识
- `output/baselines/20261125-1d5db5d` 保存旧 2,849 条诊断查询和时间受限回执

##### 实测基线覆盖

本次 15 图使用 310,461 条唯一冻结查询。下表统计已完成并通过逐条判断的配置，固定阈值每图构建三次，通用阈值每图只构建一次

| 方法 | 已通过配置数 / 总数 |
| --- | ---: |
| BFS、双向 BFS | 各 15 / 15 |
| ESTI（含 LiveJournal 扩容版） | 15 / 15 |
| Scalable K-Reach / gen-k-reach | 45 / 45、15 / 15 |
| K-Reach | 41 / 45 |
| VCRea、VCRea+、Directed PLL | 各 13 / 15 |

截至本次核验，共通过 185 项、2,622,161 次判定，错答为零；另记录原版 ESTI 的一个固定数组容量限制、K-Reach 两个实际内存分配失败及两个严格容量下界证书。Pokec 和 LiveJournal 的六项完整标签构建曾因资源方案调整暂停，原回执保留；统一 48 GiB 后继续容量核验与补跑。LiveJournal 的 Directed PLL 和 VCRea+ 已分别取得约 49.39 GiB、48.76 GiB 的必要编码下界，其余四项仍在构建和核验，最新状态以本机合并回执为准

为初步候选方法对比，另外在固定逻辑 CPU 46 和统一 48 GiB 的条件下复测六张代表图，78 个配置全部通过，数据位于 output/baselines/20261126-pilot-matched，候选试验与强消融见 [自适应半径](adaptive-radius.md)

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

build.json 保存构建状态、完整索引构建时间、有效负载、进程峰值及资源预算，query.json 保存批次时间、平均延迟、查询数和错答数。新运行保留按冻结查询顺序的逐条布尔答案，固定阈值仅保留对应阈值子序列。索引在原生进程中构建并查询，构建报告记录其大小；当前算法没有索引持久化协议。已有正式回执也按相同结构导出，过去未保留逐条答案流的结果仍有逐条正确性统计与原始回执

```sh
python3 src/plot_pareto.py output/baselines/<run>/performance.tsv --table-only
```

横轴为索引构建总秒数，包含选点、选参及索引建立；纵轴为冻结查询的平均延迟（微秒）。零索引方法的横轴取 0，使用对称对数轴显示。对每张原图和同一查询集，只将完成且零错答的配置纳入比较。某方法在两个指标上均不差于另一方法且至少一项更优时，后者被支配，在 pareto.tsv 中标记为非支配配置

固定 k 比较使用 `--fixed-k 2/4/6`，所有算法收到同一阈值的冻结子查询。混合 k 比较中，固定阈值方法各档索引构建时间和对应查询时间相加，通用阈值方法构建一次；固定索引的有效负载相加，单进程峰值取最大值，后者不能代表多档索引同时常驻的峰值。若负载和已经超过统一预算，则混合配置不参与前沿。构建失败、容量不可行及待完成配置保留在 pareto.tsv，只有具有实际性能的配置进入非支配计算

候选方法输出相同字段的 performance.tsv 后可将两份表同时传给对比数据入口，核对图和查询哈希，`--strict` 再检查执行资源一致。现有 15 图的初始非支配数据位于 output/baselines/20261126-complete/pareto/pareto.tsv，输入为已验收的同图同查询回执。当前非支配点共 46 个，双向 BFS 在 14 张图进入前沿，完整 K-Reach 在具有全部三档可用索引的 13 张图进入前沿。这批数据用于方法探索和规模判断；候选方法确定后，将双方在同一资源配置和固定 CPU 条件下重测关键图的延迟
