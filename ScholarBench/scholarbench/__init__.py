"""ScholarBench — 面向学术研究与创作工作流的端到端评测基准。

设计目标：
1. 系统无关：被测系统统一抽象为 SUT.generate(task) -> Answer
2. 客观优先：能规则计算的指标绝不交给模型
3. 可复现：数据集可从公开元数据重建，带版本号与快照哈希

版本：scholarbench-v0.1
"""
__version__ = "0.1.0"
DATASET_VERSION = "v0.1"
