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
python3 src/run_baselines.py all --jobs 4
python3 src/report_baselines.py output/baselines/20261126-full-ten output/baselines/20261126-extensions --output output/baselines/20261126-complete/performance.tsv
python3 src/run_baselines.py --review output/baselines/20261126-extensions
```

默认正式 `benchmark.tsv`，`--query-name test.tsv` 选择小型诊断输入。求解器单线程，默认没有墙钟上限，地址空间默认每项 48 GiB、完整 K-Reach 96 GiB。可按共享主机实际余量调整 `--memory-gib` 和 `--kreach-memory-gib`。重复实验指定独立 `--output`，中断后相同程序和配置可用 `--resume` 从已有回执恢复

`run.json` 保存源码指纹、编译器、图列表、配置和运行机器。各图与方法的 JSON/TSV 和日志全部在本地 output，`performance.tsv` 由回执生成并校验查询和图 SHA-256，记录完成状态、查询数及错答、构建秒数、首次批查询秒数、均值、索引有效负载和进程峰值 KiB。固定阈值每档分母仅包含该阈值请求；混合阈值独立构建一次。有效负载不含容器开销，峰值 RSS 含图和构建空间。未采集字段留空，失败配置的计时不参与比较

并行构建用于完整正确性验证和规模判断。精细论文延迟比较使用同一主机、绑定相同 CPU、串行、固定请求序列，并明确缓存条件和重复次数。当前整批均值无法推导 P95，需另行采集逐条延迟。自适应方案使用同一 `benchmark.tsv` 作为最终测试，与独立训练和验证分离，构建计入选根、探测、调参和建表全部环节

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

截至本次核验，共通过 185 项、2,622,161 次判定，错答为零；另记录原版 ESTI 的一个固定数组容量限制、K-Reach 两个实际内存分配失败及两个严格容量下界证书。Pokec 和 LiveJournal 的六项完整标签构建仍在运行，结果以本机合并回执为准

以 web-BerkStan 的 22,850 条正式查询为例，首次批查询耗时约为双向 BFS 0.070 s、gen-k-reach 0.258 s、VCRea+ 0.015 s。后两者构建分别约 10.3 s 与 61.5 s。Pokec 和 LiveJournal 的普通限深 BFS 批查询分别约 964 s 和 1,860 s，而双向 BFS 均约 0.56 s。两图的 gen-k-reach 构建分别约 459 s 与 902 s，批查询约 5.53 s 与 5.40 s。表明双向 BFS 是本查询分布下需要认真对比的在线基线，不能仅凭建表或命中标签推定最终收益

ESTI 的补测回执置于各运行目录的 esti-profile/，沿用原图、查询和作者程序，采集作者 index size 与 GNU time 峰值 RSS；返还原始首次实验回执与独立补测结果。其他指标口径与首次运行保持一致
