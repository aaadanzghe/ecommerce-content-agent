# -*- coding: utf-8 -*-
"""
Agent 基类
所有 Agent 继承 BaseAgent，统一接口：
  - run(product: ProductProfile) -> dict
  - 使用共享的 ModelClient
"""

from src.schemas import ProductProfile
from src.inference.model_client import ModelClient


class BaseAgent:
    """Agent 基类"""

    name: str = "base"
    description: str = ""

    def __init__(self, model_client: ModelClient):
        self.model = model_client

    def run(self, product: ProductProfile, **kwargs) -> dict:
        """执行 Agent 逻辑，子类必须实现"""
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name}>"
