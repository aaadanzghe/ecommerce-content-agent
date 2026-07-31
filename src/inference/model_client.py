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
        # 简单的规则模拟
        if "标题" in user_message or "title" in user_message.lower():
            return "【品质之选】高性价比好物推荐"
        if "卖点" in user_message or "selling" in user_message.lower():
            return "1. 品质保障\n2. 性价比高\n3. 用户好评\n4. 售后无忧\n5. 快速发货"
        if "SEO" in user_message or "关键词" in user_message:
            return "高品质, 性价比, 热销, 正品, 快速发货"
        if "评分" in user_message or "score" in user_message.lower():
            return json.dumps({
                "accuracy": {"score": 4, "reason": "信息基本准确"},
                "attractiveness": {"score": 3, "reason": "吸引力一般"},
                "compliance": {"score": 5, "reason": "无违规内容"},
                "seo": {"score": 3, "reason": "关键词覆盖不足"},
                "overall_comment": "基本合格，SEO 需加强"
            }, ensure_ascii=False)
        return "这是一段模拟生成的电商文案。品质保证，值得信赖。"
