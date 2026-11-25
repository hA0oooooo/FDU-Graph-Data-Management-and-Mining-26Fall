##### 数据版本

十张图均已下载、按原方向整理，并重新读取文件核对哈希。各图合计 134,578,213 条边，原始压缩包共 537,784,454 字节，规范边表共 1,939,093,244 字节。所有方法读取同一份按源点、终点编号升序排列的有向边表。前两张图沿用[两张小图的清单](../dataset/manifest.json)，新增八张图的[分发地址](../dataset/catalogue.json)和[逐图校验记录](../dataset/frozen/)与原始数据分开保存

| 图 | 顶点 | 边 | 文件来源与版本 |
| --- | ---: | ---: | --- |
| Wiki-Vote | 7,115 | 103,689 | [SNAP 投票网络](https://snap.stanford.edu/data/wiki-Vote.html)，投票者指向候选人 |
| CiteSeer-sub | 10,720 | 44,258 | [GRAIL 作者 sigmod09 归档](https://github.com/zakimjz/grail/tree/c13a7364fbc185841fc6277cd295acf33a7188f0/Downloads)的引文 DAG，成员为 citeseer_sub_10720.gra |
| p2p-Gnutella31 | 62,586 | 147,892 | [SNAP Gnutella](https://snap.stanford.edu/data/p2p-Gnutella31.html)，2002 年 8 月 31 日有向快照 |
| email-EuAll | 265,214 | 420,045 | [SNAP 邮件网络](https://snap.stanford.edu/data/email-EuAll.html)，发件人指向收件人，保留 1,089 条自环 |
| web-Google | 875,713 | 5,105,039 | [SNAP Google 网页图](https://snap.stanford.edu/data/web-Google.html)，边为有向超链接 |
| web-BerkStan | 685,230 | 7,600,595 | [SNAP BerkStan 网页图](https://snap.stanford.edu/data/web-BerkStan.html)，同规模的论文图不保证边表字节相同 |
| wiki-Talk | 2,394,385 | 5,021,410 | [SNAP Wikipedia 讨论网络](https://snap.stanford.edu/data/wiki-Talk.html)，编辑者指向被编辑讨论页的用户。VCRea 的变换版本只有 2,281,879 点、2,311,570 边 |
| cit-Patents | 3,774,768 | 16,518,948 | [SNAP 美国专利引用](https://snap.stanford.edu/data/cit-Patents.html)，引用方指向被引专利，文件含一条自环，边数较 K-Reach 2014 表中多一条；这两项是否对应同一条记录尚未核实 |
| soc-Pokec | 1,632,803 | 30,622,564 | [SNAP Pokec](https://snap.stanford.edu/data/soc-Pokec.html)，只取有向关系边表 |
| soc-LiveJournal1 | 4,847,571 | 68,993,773 | [SNAP LiveJournal](https://snap.stanford.edu/data/soc-LiveJournal1.html)，单向好友声明，保留文件中的 518,382 条自环 |

[O’Reach 实例表](https://oreach.taa.univie.ac.at/)注明小型稠密组来自 GRAIL，列出 citeseer_sub 的上述规模。该页的 tar.xz 下载在本轮返回 HTTP 404，因此实验固定上游作者明确命名的原图，公开包的 Git blob 为 `08aaf9b00a2bc7f52ee63988d02a381b0714b896`。对上游原图做拓扑排序覆盖全部 10,720 个顶点，再按逆拓扑序合并后继的可达集合，得到不同端点的可达有序点对 421,995 个，占全部 $n(n-1)$ 的 0.3672469934%，与 O’Reach 公布的 0.367247% 一致。尚未核实 O’Reach 的重新编号、查询文件或其边表与这份上游图的逐项一致性，项目自己生成 K-hop 查询。实验中的距离定义在这张分发 DAG 上

##### 准备与校验

仓库根目录中运行以下命令。新增图的 Python 入口使用标准库，Linux 需要 g++、curl、tar 和 gzip

```sh
python3 src/prepare.py
python3 src/freeze.py
python3 -m unittest discover -s tests
```

可以在 `freeze.py` 后列出图名，例如 `python3 src/freeze.py CiteSeer-sub email-EuAll`。服务器不能访问发布站时，可先在联网机器按清单下载原压缩包，再以 URL 对应的文件名放到 `dataset/raw/`。脚本以 SHA-256 复核已冻结的原包，重新生成边表后还会核对其哈希与顶点映射

SNAP 的文本文件以边端点给出顶点，将出现的原始整数编号升序重编号到 $0,\ldots,|V|-1$。GRAIL 用文件头给出全体顶点数，每个顶点有一行出邻居，包括空邻接行。顶点对按原方向去重，保留自环，未将强连通分量缩成顶点。输出文件 `dataset/prepared/<图名>.nodes.tsv` 的两列是新编号与原编号；`.edges` 无表头，每行为源点和目的点，两者用制表符分隔

每个新增图的 JSON 实测记录包括原始行数、规范边数、自环与重边数、孤立点数、原件及边表字节数，以及原件、边表和编号映射的 SHA-256。程序完成全部计数和哈希校验后才发布边表，生成期间的中间文件在同文件系统的临时目录


##### 查询和真值

`dataset/workloads/<图名>/test.tsv` 是各基线共用的冻结输入，共 2,849 条查询。每行依次给出源点、终点、阈值 $k$ 和不设深度限制的原图最短距离 $d$，不可达记为 $-1$。判定条件为 $0\le d\le k$。$k$ 固定档分别用 $2,4,6$，通用方法用同一索引回答混合阈值。每个图目录的 `manifest.json` 记录查询、边表哈希和样本计数

训练、验证和测试按源点分开，`holdouts/` 和 `gate-holdouts/` 保留供以后研究使用的独立查询。`prior-sources.txt` 只记录生成冻结查询时排除的源点编号
