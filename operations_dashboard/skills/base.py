"""定义通用 Skill 抽象，用于统一封装项目中的各类“能力”。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Skill(ABC):
    """所有具体技能的共同接口。

    设计要点：
    - 每个 Skill 都有稳定的 ``name``，用于在 Agent / MCP 中注册；
    - ``description`` 用于向 LLM 或调用者暴露用途说明；
    - ``invoke`` 统一为基于关键字参数的调用方式，便于直接映射到
      LangChain 工具、OpenAI tool / function calling、MCP tool 等。
    """

    name: str
    description: str

    @abstractmethod
    def invoke(self, **kwargs: Any) -> Any:  # pragma: no cover - 接口定义
        """执行技能主体逻辑。

        约定：
        - 入参全部通过 ``**kwargs`` 传递，具体字段由各个技能自行解析；
        - 返回值通常为 Dict 或 JSON 可序列化结构，方便跨进程传输。
        """

    def to_descriptor(self) -> Dict[str, Any]:
        """返回一个通用的元数据描述，可用于构建工具列表等场景。"""
        return {
            "name": self.name,
            "description": self.description,
        }

