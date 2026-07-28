# E-commerce Copywriter LLM

> 从公开数据集选型 → 数据工程 → QLoRA 微调 → GRPO 对齐 → LLM-as-Judge 评估 → vLLM 部署的完整 LLM 微调管线

## 项目简介

本项目实现了一个电商商品文案智能生成系统，覆盖从原始数据到模型部署的完整机器学习管线。核心场景：输入商品信息（标题/属性），自动生成吸引人的商品描述文案。

### 核心特点

- **全真实数据**：19,885 条训练数据，来自阿里天池（212万条商品描述）和 AdvertiseGen（114K 条结构化文案），无模拟数据
- **9 品类均衡**：clothing / 3C数码 / 美妆 / 家居 / 食品 / 母婴 / 汽车 / 运动户外 / 其他，每品类 ~2000 条
- **双轨模型策略**：本地 Qwen3-14B（RTX 5070 Ti 12GB）快速迭代 + 云端 Qwen3.5-35B-A3B MoE（A100 40GB）出最终模型
- **完整评估体系**：LLM-as-Judge 四维评估（准确性/吸引力/合规性/SEO）+ ROUGE-L + 确定性指标
- **消融实验**：LoRA rank / 数据量 / 学习率 / LoRA target / 任务类型 / 训练方式 6 个变量

## 项目结构

```
ecommerce-copywriter-llm/
├── configs/
│   ├── train_config.yaml       # QLoRA SFT 训练配置 (12GB 显存)
│   └── grpo_config.yaml        # GRPO 对齐训练配置 (云端 A100)
├── data/
│   ├── dataset_info.json       # LLaMA Factory 数据集注册
│   ├── labeled/
│   │   ├── train.json          # 训练集 (15,908 条)
│   │   ├── val.json            # 验证集 (1,988 条)
│   │   └── test.json           # 测试集 (1,989 条)
│   ├── preprocess.py           # 数据预处理脚本
│   └── download_datasets.py    # 数据集下载脚本
├── eval/
│   └── judge.py                # LLM-as-Judge 四维评估 + 消融对比
├── inference/
│   └── vllm_serve.py           # vLLM 推理部署 (LoRA 热加载)
├── scripts/
│   ├── setup_env.ps1           # 一键环境安装
│   ├── download_model.py       # 模型下载
│   └── train_local.ps1         # 本地训练启动器
├── .gitignore
├── LICENSE
└── README.md
```

## 数据工程

### 数据来源

| 数据集 | 来源 | 原始规模 | 使用量 | 格式 |
|--------|------|---------|--------|------|
| AdvertiseGen | 清华 CoAI / ModelScope | 114K | 2,000 条 | content → summary |
| 天池商品描述 | 阿里天池 (dataset/9717) | 212 万 | 18,000 条 | title → description |

### 数据处理流程

```
原始数据 (223万条)
    │
    ├── 品类自动分类 (9品类关键词词典)
    ├── 同 title 去重 (保留最长描述)
    ├── 长度过滤 (≥30 字符)
    ├── 品类均衡采样 (每类 2000 条)
    ├── Alpaca 格式转换
    └── 训练/验证/测试集划分 (8:1:1)
    │
    ▼
最终数据集: 19,885 条 (9品类均衡)
```

### 品类分布

| 品类 | 数量 | 占比 |
|------|------|------|
| clothing | 3,907 | 19.6% |
| other | 2,000 | 10.1% |
| home | 1,999 | 10.1% |
| beauty | 1,999 | 10.1% |
| auto | 1,998 | 10.0% |
| food | 1,998 | 10.0% |
| sports_outdoor | 1,997 | 10.0% |
| 3c_digital | 1,995 | 10.0% |
| maternity_baby | 1,992 | 10.0% |

## 训练

### 硬件要求

| 轨道 | 模型 | 硬件 | 显存占用 |
|------|------|------|---------|
| 本地 | Qwen3-14B Dense | RTX 5070 Ti 12GB | ~10-11GB (QLoRA 4-bit) |
| 云端 | Qwen3.5-35B-A3B MoE | A100/H100 40GB+ | ~17.5GB (QLoRA 4-bit) |

### 快速开始

```powershell
# 1. 安装环境
.\scripts\setup_env.ps1

# 2. 下载模型
python scripts\download_model.py --model qwen3-14b

# 3. 开始训练
.\scripts\train_local.ps1

# 4. 评估模型
python eval\judge.py --model models/qwen3-14b --lora output/ecommerce_qlora_sft

# 5. 启动推理服务
python inference\vllm_serve.py --model models/qwen3-14b --lora output/ecommerce_qlora_sft
```

### 训练配置

| 参数 | 值 | 说明 |
|------|-----|------|
| 微调方法 | QLoRA 4-bit | NF4 量化 + 双重量化 |
| LoRA rank | 64 | 消融实验范围: 8-64 |
| LoRA alpha | 128 | alpha = 2 × rank |
| LoRA target | all | 全层注入 |
| 学习率 | 2e-4 | 余弦退火 + 5% warmup |
| batch size | 4 × 4 | 有效 batch = 16 |
| epochs | 3 | - |
| 最大序列长度 | 1024 | - |

### 消融实验矩阵

| 变量 | 实验组 | 基线 |
|------|--------|------|
| LoRA rank | 8, 16, 32, 64 | 16 |
| 数据量 | 500, 1000, 2000, 5000 | 2000 |
| 学习率 | 1e-4, 2e-4, 5e-4, 1e-3 | 2e-4 |
| LoRA target | qv_only, qkvo, all | all |
| 任务类型 | 单任务, 多任务 | 多任务 |
| 训练方式 | SFT, SFT+GRPO | SFT+GRPO |

## 评估

### LLM-as-Judge 四维评估

| 维度 | 权重 | 评估内容 |
|------|------|---------|
| 准确性 (Accuracy) | 35% | 属性值、规格、品牌是否与原文一致 |
| 吸引力 (Attractiveness) | 30% | 语言流畅度、卖点突显、购买欲望 |
| 合规性 (Compliance) | 20% | 广告法违禁词、虚假宣传检测 |
| SEO覆盖 (SEO Coverage) | 15% | 关键词密度、标题结构、标签覆盖 |

### 确定性指标

- ROUGE-L (基于最长公共子序列)
- 长度比 (生成/参考)
- 2-gram 重复率 (检测模板化)
- 首尾完整性

## 部署

### vLLM 推理服务

```bash
# 本地 5070 Ti 12GB
python inference/vllm_serve.py \
    --model models/qwen3-14b \
    --lora output/ecommerce_qlora_sft \
    --gpu-memory 0.88 \
    --enforce-eager

# 云端 A100 40GB
python inference/vllm_serve.py \
    --model models/qwen3-moe \
    --lora output/ecommerce_grpo_aligned \
    --gpu-memory 0.92
```

### API 调用示例

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

response = client.completions.create(
    model="ecommerce-lora",
    prompt='''你是一名专业的电商文案撰写师。请根据以下商品信息，生成一段吸引人的商品描述文案。

{"category": "3c_digital", "title": "XX品牌 TWS Pro 真无线降噪耳机"}''',
    max_tokens=512,
    temperature=0.7,
    top_p=0.9
)
print(response.choices[0].text)
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 训练框架 | LLaMA-Factory |
| 微调方法 | QLoRA (bitsandbytes) + LoRA+ |
| 对齐训练 | GRPO (Group Relative Policy Optimization) |
| 评估 | LLM-as-Judge + ROUGE-L |
| 推理引擎 | vLLM |
| 基座模型 | Qwen3-14B / Qwen3.5-35B-A3B MoE |
| 数据处理 | Python + jieba |

## 数据集说明

原始数据集不包含在本仓库中（体积过大），可通过以下方式获取：

```powershell
# 方式1: 使用下载脚本
python data/download_datasets.py

# 方式2: 手动下载
# AdvertiseGen: https://modelscope.cn/datasets/lvjianjin/AdvertiseGen
# 天池商品描述: https://tianchi.aliyun.com/dataset/9717
```

下载后放入 `data/raw/` 目录，运行预处理：

```powershell
python data/preprocess.py
```

## License

MIT License - 详见 [LICENSE](LICENSE)

数据集遵循各自原始协议：
- AdvertiseGen: CC BY-NC 4.0
- 天池商品描述: CC BY-NC 4.0