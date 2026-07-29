"""本地模拟 Model Gateway - 不调用真实 AI 模型，直接返回模拟结果

用途：
1. 开发和测试阶段使用，不需要 API Key
2. 后续替换为真实的 OpenAI Gateway 时，调用方式完全一致
"""

import logging
import json
import re
import time
from app.core.gateway.base import ModelGateway, ModelCallRecord
from app.services.model_governance import record_model_call, reserve_model_call

logger = logging.getLogger(__name__)


class LocalModelGateway(ModelGateway):
    """本地模拟网关 - 假装调用了 AI 模型，实际上返回固定文本"""

    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        json_mode: bool = False,
    ) -> str:
        """模拟 AI 对话"""
        start = time.perf_counter()
        governance_scope = reserve_model_call(
            provider="local",
            model_name="local-simulator",
            estimated_prompt_tokens=self.count_tokens(prompt),
        )

        # 模拟模型处理的耗时
        time.sleep(0.5)

        if json_mode:
            chunk_ids = re.findall(r'chunk_id="(\d+)"', prompt)
            if not chunk_ids:
                raise ValueError("Local JSON simulation requires an evidence chunk_id")
            response = json.dumps(
                {
                    "answer": "本地测试替身：请使用 DeepSeek 获得真实分析结果。",
                    "citations": [{"chunk_id": int(chunk_ids[0])}],
                },
                ensure_ascii=False,
            )
        else:
            # 模拟生成回答
            response = f"针对问题「{prompt}」的分析结果：\n"
            response += "1. 根据现有数据，该指标呈现下降趋势\n"
            response += "2. 主要原因是市场竞争加剧和成本上升\n"
            response += "3. 建议优化产品结构和控制运营成本\n"

        # 模拟 Token 计算（实际按字数估算）
        prompt_tokens = len(prompt) * 2
        completion_tokens = len(response) * 2

        duration = (time.perf_counter() - start) * 1000

        # 记录这次调用
        record = ModelCallRecord(
            model_name="local-simulator",
            prompt=prompt,
            response=response,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=round(duration, 2),
        )
        logger.info(
            "Model call completed",
            extra={
                "model": record.model_name,
                "prompt_tokens": record.prompt_tokens,
                "completion_tokens": record.completion_tokens,
                "duration_ms": record.duration_ms,
            },
        )
        record_model_call(
            governance_scope,
            provider="local",
            model_name="local-simulator",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration,
            result_category="success",
        )

        return response

    def count_tokens(self, text: str) -> int:
        """估算 Token 数量（按字符数估算）"""
        return len(text) * 2
