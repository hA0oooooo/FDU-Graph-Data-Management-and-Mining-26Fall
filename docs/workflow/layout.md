##### 目录与职责

```text
src/
  baselines/             基线算法与作者实现适配
  radius/                自适应半径、索引与搜索
    hotspot.py           最终方法及前期热点实验入口
    demand_profile.py    正式实验编排
    hotspot.cpp          索引构建和查询
  run_baselines.py       基线统一运行入口
  run_stress.py          高内存补跑与复查
  report_baselines.py    构建及查询结果汇总
  rank_results.py        统一评测指标
dataset/
  raw/                   原始数据包
  prepared/              规范有向边表和编号映射
  frozen/                版本及哈希清单
  workloads/             冻结训练、验证及测试查询
docs/
  baselines/             基线机制与实测结果
  workflow/              数据、目录、运行和评测规范
  research/              方法设计、消融和正式实验分析
tests/                   独立正确性验证
cache/                   可重建依赖与编译缓存
output/                  本机实验数据与必要回执
```

源码、可复现的清单和冻结查询随 Git 维护。原始图与规范边表放在 dataset 的本地目录，编译缓存放 cache，实验结果放 output。机器路径及私有环境变量放 Git 忽略的 .env，本机开发计划和智能体说明也由 Git 忽略。公开命令均以仓库根目录为工作目录

##### 运行结果

```text
output/
  baselines/
    coverage.tsv         全部图、配置、指标和证据
    performance.tsv      统一资源正式对比
    methods/<method>/<graph>/
    ranking/
    pressure/           高内存构建及逐条查询回执
    historical/         初始结果汇总及容量证明
    runs/<run>/          原始实验回执与输入配置
  adaptive-radius/
    main/                同资源正式初试
    pilot/               预算探索
    ablation/            强统一半径消融
    hotspot/             中间点局部距离表、六图主对照与构建诊断
    demand-profile/      按需构建主实验、固定配置消融及新源点确认
  validation/           独立测试与兼容性验证
```

运行名使用数据集、算法机制或用途，不附日期、轮次或无实际含义的版本后缀。结果与其构建、查询配置同目录保存，不通过复制制造多份正式结果。各方法的构建、查询摘要和逐条答案在方法目录关联原始回执。临时编译文件使用 cache，完成后清理可重建的一次性验证文件

##### 复查入口

```sh
python3 src/report_baselines.py output/baselines/runs/standard-small output/baselines/runs/standard-extended --output output/baselines/performance.tsv
python3 src/rank_results.py output/baselines/performance.tsv --strict
python3 src/run_stress.py output/baselines/historical/performance.tsv --output output/baselines/pressure --review
python3 src/baseline_coverage.py
python3 tests/check_workloads.py
python3 tests/check_demand_profile.py
```

复查不重新建立已完成的索引。上述命令需要对应本地数据与回执。正式方法执行入口与新环境复现条件见 [方法说明](../research/hotspot-distance-index.md)，资源组按 [评测规范](evaluation.md) 比较
