##### 首轮历史方法与比较目的

本页记录两图先导实验。十图版本的运行口径、资源上限与逐图状态见[本轮结果](round2-results.md)与[比较矩阵](../results/round2/baseline-matrix.tsv)

| 方法 | 建什么索引、如何回答 | 本仓库的比较用途 |
| --- | --- | --- |
| 限深 BFS、双向限深 BFS | 单向只搜索源点出边，双向使用源点出边和目标入边。两者都在原始有向边集上执行 | 无索引成本对照。独立真值由工作负载生成器的完整单源 BFS 提供，可区分超出 $k$ 与完全不可达 |
| K-Reach 2012 | 对固定 $k$，以顶点覆盖保证两端至多各走一步就进入核心。在核心间保留满足 $k-2$、$k-1$、$k$ 的距离档位，按查询端点是否位于覆盖集选择阈值 | 论文算法自行实现，固定 $k$ 的查询应与相应索引配对。论文的 $h$-hop cover 指覆盖长度为 $h$ 的路径，与本项目的距离球半径定义不同 [原论文](https://www.microsoft.com/en-us/research/wp-content/uploads/2012/08/vldb2012.pdf) |
| Scalable K-Reach 2014 | 预算内选择两层核心，索引分别处理经过这些核心的路径，余下查询在残余图搜索。第 5.6 节讨论预算自适应，第 6.8 节验证同一索引处理变化的 $k$ | 可比较建索引与残余搜索之间的取舍。首轮仅做机制分析，次轮已完成[固定与通用两档的独立实现](scalable.md)；公开的 dynamic-k-reach 属于第三方工作 [作者全文](https://www1.se.cuhk.edu.hk/~hcheng/paper/vldbj-cheng.pdf) |
| ESTI 2021 | 在原图上建扩展 BFS 树，重复到达同一顶点时记录虚拟副本。拓扑坐标与层数差排除部分查询，祖先区间与层数提供路径证据，其余按剩余跳数继续展开 | 固定作者 C++ 源码，构建一次即可处理混合 $k$。逐条比对流程及结果见下文 [论文](https://doi.org/10.1007/978-3-030-73216-5_6) |
| VCRea / VCRea+ 2023 | 在顶点覆盖集内建立距离标签，通过端点邻居接入；增强版本为高出度源点、高入度终点增补相应方向的标签 | 后续可比较完整距离标签与截断距离球的空间、查询代价。全文说明对比用的 ESTI 与 kReach 代码由相应作者提供，首轮未取得 VCRea 作者实现，次轮用[严格构建与去冗余构建](cover-baselines.md)分别验证 [原论文](https://www.mdpi.com/2076-3417/13/6/3470) |

##### 运行 ESTI

在仓库根目录执行，准备数据与公共测试查询的命令见仓库导航

```sh
python3 baselines/esti/build.py
python3 baselines/esti/check.py wiki-Vote p2p-Gnutella31
python3 baselines/esti/check.py wiki-Vote p2p-Gnutella31 --split confirmation
```

构建入口获取固定提交，校验压缩包 SHA-256 后使用 GCC 的 C++11、`-O3 -m64` 编译。上游为 MIT 许可。若运行机无法访问 GitHub，可在联网机器下载同一[归档](https://codeload.github.com/YZ-Cai/ESTI/tar.gz/d893a28de9bf8f407ed24ebefc973f973be1e923)，放入 `baselines/esti/_build/upstream.tar.gz` 后执行同一命令 [固定版本与许可](https://github.com/YZ-Cai/ESTI/tree/d893a28de9bf8f407ed24ebefc973f973be1e923)

上游主程序仅显示总用时。构建脚本在主程序中保留每次 `ESTI_query` 的返回值，计时结束后统一写出，原有构树和查询函数直接来自固定源码。适配器依据顶点表和有向边表生成上游所需的出邻接表，以 `cyc` 模式运行，查询输入中的标准答案字段统一填占位值。Python 按原序逐项核对返回值与独立真值 $0\le d\le k$。两张小图穷举全部有序点对及 $k=0,\ldots,|V|$，覆盖孤立顶点、环、源汇不对称和自动翻转图的分支；两张实图默认读取各自的 `benchmark/workloads/<graph>/test.tsv`，用 `--split confirmation` 单独核验独立复核查询

[首批验收](../baselines/esti/verification.json)与[独立复核](../baselines/esti/confirmation.json)分别给出逐图错答数、三类真值计数、输入哈希与实测成本。构建毫秒数从上游读图后开始；查询毫秒数为单批循环并含逐条保存一个字节，排除读查询与写结果。进程墙钟另含图和查询文件读取、索引与退出；峰值 RSS 使用 Linux GNU time，包含上游固定数组及工作区；逻辑索引字节数是上游 `get_index_size()` 的字段估算。一次 C++ 批量查询与 Python 逐条计时有语言与测量差异，不能由此拆出算法本身的加速比
