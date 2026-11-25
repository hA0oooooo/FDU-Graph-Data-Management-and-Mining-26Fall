##### 任务与对照

在静态有向无权图上判断 $d_G(s,t)\le k$。全套基线读取同一份原始有向图与同一批冻结查询，按完整单源 BFS 给出的距离逐条核对。查询分别包含限跳可达、存在路径但超过阈值、完全不可达三类。所有时间均为单个求解器的单线程测量

| 方法 | 运行配置 |
| --- | --- |
| 单向限深 BFS、双向限深 BFS | 原图搜索，读取同一批混合阈值，记录查询耗时和扫描边数 |
| K-Reach 2012 | 用顶点覆盖建立核心间距离档位，每个 $k=2,4,6$ 独立建表。每档 120 秒、6 GiB |
| Scalable K-Reach、gen-k-reach | 两层核心加残余搜索，分别比较三个固定阈值与一个通用索引。每档 150 秒、4 GiB。[参数和机制](baselines/scalable.md) |
| ESTI | 固定作者提交，增加答案输出，保留原算法。每图 100 秒、6 GiB。LiveJournal 超过原静态数组容量，额外记录仅扩大边数组后的运行 |
| VCRea、VCRea+、有向 PLL | 复现两跳距离标签，前两法用去冗余条件。每图每法 180 秒、4 GiB。[构建条件和机制](baselines/cover-labels.md) |

2012 年 K-Reach 只对固定阈值建立覆盖索引。其 $h$-hop cover 参数定义的是覆盖路径长度。[K-Reach 原文](https://www.microsoft.com/en-us/research/wp-content/uploads/2012/08/vldb2012.pdf)

ESTI 来自固定提交 `d893a28`。查询标签依据扩展 BFS 树的真实节点与虚拟副本。首次运行会校验作者源码包的 SHA-256，编译产物进入 `cache/esti/`。[ESTI 作者源码](https://github.com/YZ-Cai/ESTI/tree/d893a28de9bf8f407ed24ebefc973f973be1e923)

##### 运行与复查

在 baojian 的仓库根目录执行。依赖 Linux、Python 3.11 或以上、GCC、curl、gzip、tar 和 GNU time

```sh
python3 src/run_baselines.py wiki-Vote
python3 src/run_baselines.py all --jobs 4
python3 src/run_baselines.py --review output/baselines/<运行目录>
```

可传多个图名，`--jobs` 控制并行的图数。每个图内的基线依次运行，并行只用于整套回归验收。要比较短查询的耗时，使用默认的单图串行运行，并在相同机器和线程条件下采集

入口会校验边表和测试查询的哈希，缺少边表时准备对应数据。每次运行生成独立日期目录，可用 `--output` 指定新目录。目录内的 `run.json` 记录机器、输入图名、代码提交和编译器，`<图名>/run.log` 保留运行日志。各个 JSON 回执保存方法计量，`coverage.tsv` 汇总每个图与配置的状态、应核对和实际核对的查询数及错答数

只有建表完成且答对全部预期查询的项目标为 `verified`。达到时限和地址空间上限的配置保留真实状态，汇总中不填入已核对数。复查入口从本机已有回执重新验证输入身份、完成配置和核对数量，无需重新建表
