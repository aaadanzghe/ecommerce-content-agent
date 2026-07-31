# -*- coding: utf-8 -*-
"""
统一模型调用接口
支持四种后端：
  1. vLLM 本地服务 (OpenAI 兼容 API)
  2. HuggingFace Transformers (直接加载模型)
  3. 外部 API (OpenAI / DashScope / 其他)
  4. Mock (无 GPU 环境下的流程验证)

Agent 通过 ModelClient 统一调用，切换后端只需改配置。
"""

import json
import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class ModelConfig:
    """模型配置"""
    backend: str = "vllm"              # vllm / transformers / api / mock
    model_name: str = "ecommerce-copywriter"
    api_base: str = "http://localhost:8000/v1"
    api_key: str = "not-needed"
    # transformers 后端
    model_path: str = ""
    lora_path: str = ""
    # 生成参数
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024


def create_client(config: ModelConfig) -> "ModelClient":
    """工厂函数：根据 config.backend 创建对应客户端"""
    if config.backend == "mock":
        return MockModelClient(config)
    return ModelClient(config)


def get_mock_client() -> "MockModelClient":
    """获取 Mock 客户端（不需要 GPU/API，用于开发和测试）"""
    return MockModelClient(ModelConfig(backend="mock"))


class ModelClient:
    """
    统一模型调用客户端

    用法:
        client = create_client(ModelConfig(backend="vllm"))
        response = client.chat("你好", system_prompt="你是电商文案专家")
    """

    def __init__(self, config: ModelConfig):
        self.config = config
        self._client = None
        self._model = None
        self._tokenizer = None

    def _get_openai_client(self):
        """获取 OpenAI 兼容客户端（vLLM / 外部 API）"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.config.api_base,
                api_key=self.config.api_key,
            )
        return self._client

    def _get_transformers_model(self):
        """加载 HuggingFace 模型"""
        if self._model is None:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_path, trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self.config.model_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
            )

            if self.config.lora_path:
                self._model = PeftModel.from_pretrained(self._model, self.config.lora_path)

            self._model.eval()

        return self._model, self._tokenizer

    def chat(self, user_message: str, system_prompt: str = "") -> str:
        """对话式调用，返回生成的文本"""
        if self.config.backend in ("vllm", "api"):
            return self._chat_openai(user_message, system_prompt)
        elif self.config.backend == "transformers":
            return self._chat_transformers(user_message, system_prompt)
        else:
            raise ValueError(f"不支持的后端: {self.config.backend}")

    def chat_json(self, user_message: str, system_prompt: str = "") -> dict:
        """对话式调用，期望返回 JSON 并解析"""
        text = self.chat(user_message, system_prompt)
        return self._extract_json(text)

    def _chat_openai(self, user_message: str, system_prompt: str) -> str:
        """通过 OpenAI 兼容 API 调用"""
        client = self._get_openai_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=self.config.max_tokens,
        )

        return response.choices[0].message.content.strip()

    def _chat_transformers(self, user_message: str, system_prompt: str) -> str:
        """通过 HuggingFace Transformers 直接推理"""
        import torch

        model, tokenizer = self._get_transformers_model()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(text, return_tensors="pt").to(model.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=self.config.max_tokens,
                do_sample=True,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            )

        generated = outputs[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(generated, skip_special_tokens=True).strip()

    @staticmethod
    def _extract_json(text: str) -> dict:
        """从文本中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 块
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取 { ... }
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {}


class MockModelClient(ModelClient):
    """Mock 模型客户端 — 用于无 GPU 环境下的流程验证"""

    def chat(self, user_message: str, system_prompt: str = "") -> str:
        system = system_prompt.lower() if system_prompt else ""
        user = user_message.lower() if user_message else ""

        # 1. 商品理解 Agent (优先匹配，避免与其他重叠)
        if "商品分析专家" in system or "提炼卖点" in system:
            return json.dumps({
                "selling_points": ["主动降噪技术", "30小时超长续航", "IPX5防水防汗", "13mm大动圈音质", "蓝牙5.3低延迟"],
                "target_audience": "18-35岁都市白领、通勤族、运动爱好者",
                "use_scenes": ["通勤地铁", "健身房运动", "办公室专注"],
                "price_positioning": "mid"
            }, ensure_ascii=False)

        # 2. 文案生成 Agent
        if "文案撰写师" in system or "optimized_title" in user:
            return json.dumps({
                "optimized_title": "【主动降噪】TWS Pro真无线蓝牙耳机 30小时续航 IPX5防水",
                "selling_points": [
                    "ANC主动降噪，沉浸式聆听体验",
                    "30小时复合续航，一周一充无忧",
                    "IPX5级防水防汗，运动健身不受限",
                    "13mm生物振膜动圈，HiFi级音质表现",
                    "蓝牙5.3技术，游戏低延迟不断连"
                ],
                "description": "XX品牌 TWS Pro 真无线降噪耳机，采用全新ANC主动降噪技术，有效隔绝环境噪音。搭载13mm大动圈单元，三频均衡，低音浑厚有力。30小时超长续航，支持快充，充电10分钟听歌2小时。IPX5防水防汗设计，运动通勤两不误。蓝牙5.3芯片，延迟低至45ms，游戏影音同步更精准。人体工学入耳设计，久戴不痛，多尺寸耳塞适配不同耳型。",
                "social_copy": "通勤路上太吵？健身房里总被打断？这款TWS Pro降噪耳机真的拯救了我！ANC主动降噪一戴就静，30小时续航一周充一次就够了。IPX5防水运动出汗也不怕，音质完全超出这个价位的预期！#降噪耳机 #TWS #数码好物"
            }, ensure_ascii=False)

        # 3. SEO Agent
        if "seo 专家" in system or "搜索关键词" in system:
            return json.dumps({
                "seo_keywords": ["降噪耳机", "真无线蓝牙耳机", "TWS耳机", "主动降噪", "长续航耳机", "运动耳机", "蓝牙5.3"],
                "long_tail_keywords": ["降噪耳机 运动防水", "真无线耳机 30小时续航", "ANC耳机 低延迟"],
                "category_keywords": ["数码配件", "音频设备"]
            }, ensure_ascii=False)

        # 4. 重写 Rewrite Agent (必须在 Compliance 之前，因为 system prompt 包含"优化")
        if "文案优化专家" in system or "rewrite_reason" in user:
            return json.dumps({
                "optimized_title": "【ANC降噪】TWS Pro真无线耳机 30h续航 IPX5防水 游戏低延迟",
                "selling_points": [
                    "ANC主动降噪，-35dB深度降噪",
                    "30小时复合续航，Type-C快充",
                    "IPX5防水防汗，运动场景全覆盖",
                    "13mm生物振膜，Hi-Res高清音质",
                    "蓝牙5.3+45ms低延迟，电竞级体验"
                ],
                "description": "XX品牌 TWS Pro 真无线降噪耳机，搭载ANC主动降噪芯片，降噪深度达35dB。13mm生物振膜动圈单元，高频通透、中频人声饱满、低频下潜深。30小时复合续航，支持Type-C快充，充电10分钟畅听2小时。IPX5专业防水防汗，跑步健身全程陪伴。蓝牙5.3协议，游戏模式延迟仅45ms。附赠3组不同尺寸硅胶耳塞，佩戴稳固舒适。",
                "social_copy": "终于找到通勤+运动都能用的降噪耳机了！ANC一开整个世界都安静了，30小时续航我一周只充一次。健身房暴汗也不慌，IPX5防水不是盖的。打游戏延迟低到感受不到，这价格真的香！#降噪耳机推荐 #TWS #运动耳机",
                "rewrite_reason": "优化SEO关键词密度，增强卖点数据化表达，补充Type-C快充细节"
            }, ensure_ascii=False)

        # 5. 评分 Judge Agent
        if "质量评估专家" in system or "维度打分" in system:
            return json.dumps({
                "accuracy": {"score": 4, "reason": "产品属性准确，无虚构信息"},
                "attractiveness": {"score": 4, "reason": "卖点突出，描述有吸引力"},
                "compliance": {"score": 5, "reason": "无广告法违禁词"},
                "seo": {"score": 3, "reason": "关键词覆盖尚可，长尾词可加强"},
                "overall_comment": "整体质量良好，SEO维度有提升空间"
            }, ensure_ascii=False)

        # 6. 合规检查 Agent (放在最后，条件较宽泛)
        if "合规审核专家" in system or ("审核" in system and "优化" not in system):
            return json.dumps({
                "is_compliant": True,
                "violations": [],
                "risk_level": "low",
                "summary": "文案合规，无违规内容"
            }, ensure_ascii=False)

        # 默认文案
        return "这是一段模拟生成的电商文案。品质保证，值得信赖。"
