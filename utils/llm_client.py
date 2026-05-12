"""
AutoTestDesign - LLM 客户端封装（DEEPSEEK 适配）
将原来的 Claude/Anthropic 调用替换为对 Deepseek REST API 的通用封装。
配置由环境变量提供（参考 .env）：
  - DEEPSEEK_API_KEY
  - DEEPSEEK_MODEL
  - DEEPSEEK_API_URL
"""

import os
import re
import json
from typing import Any, Dict, Optional, List
import requests


class DeepseekClient:
    """简单的 Deepseek REST API 客户端封装（最小实现）"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 base_url: Optional[str] = None, temperature: float = 0.1, max_tokens: int = 8000,
                 request_timeout: Optional[int] = None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        # 从 .env 读取 DEEPSEEK_API_URL，格式为 https://api.deepseek.com/v1，需要补全 /chat/completions 端点
        api_base = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
        # 移除末尾的 /chat 或 /completions，确保一致性
        api_base = api_base.rstrip("/").rstrip("/completions").rstrip("/chat")
        self.base_url = base_url or f"{api_base}/chat/completions"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.request_timeout = request_timeout or int(os.environ.get("DEEPSEEK_REQUEST_TIMEOUT", "90"))

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _normalize_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        normalized = []
        for m in messages:
            if isinstance(m, dict):
                role = m.get("role", "user")
                content = m.get("content", "")
            else:
                # fallback: try to access attributes
                role = getattr(m, "role", None) or ("system" if "System" in m.__class__.__name__ else "user")
                content = getattr(m, "content", str(m))
            normalized.append({"role": role, "content": content})
        return normalized

    def invoke(self, messages: List[Any]) -> Dict[str, Any]:
        """调用 Deepseek REST API，返回原始解析的 JSON 响应（不对内容做深度处理）。"""
        msgs = self._normalize_messages(messages)
        payload = {
            "model": self.model,
            "messages": msgs,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        resp = requests.post(self.base_url, headers=self._build_headers(), json=payload, timeout=self.request_timeout)
        resp.raise_for_status()
        return resp.json()

def get_llm(temperature: float = 0.1) -> DeepseekClient:
    """返回 Deepseek 客户端实例"""
    return DeepseekClient(temperature=temperature)


def _extract_content_from_response(resp_json: Dict[str, Any]) -> str:
    """根据常见响应格式提取文本内容（兼容多种 API 形式）"""
    # 常见： {choices:[{message:{content:...}}]} 或 {choices:[{text:...}]} 或 {output: '...'}
    if not isinstance(resp_json, dict):
        return str(resp_json)

    if "choices" in resp_json and isinstance(resp_json["choices"], list) and resp_json["choices"]:
        first = resp_json["choices"][0]
        if isinstance(first, dict):
            if "message" in first and isinstance(first["message"], dict) and "content" in first["message"]:
                return first["message"]["content"]
            if "text" in first:
                return first.get("text", "")

    if "output" in resp_json:
        return resp_json.get("output", "")
    if "result" in resp_json:
        return resp_json.get("result", "")
    if "data" in resp_json and isinstance(resp_json["data"], dict):
        # 某些 API 嵌套在 data 下
        return json.dumps(resp_json["data"], ensure_ascii=False)

    # 最后兜底：把整个响应序列化为字符串
    return json.dumps(resp_json, ensure_ascii=False)


def call_llm_json(
    llm: DeepseekClient,
    system_prompt: str,
    user_prompt: str,
    retry: int = 2
) -> Any:
    """
    调用 LLM 并解析 JSON 输出（期望 LLM 返回 JSON 字符串），支持重试与修正提示。
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for attempt in range(retry + 1):
        resp = llm.invoke(messages)
        content = _extract_content_from_response(resp)

        # 提取代码块中的 JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            content = json_match.group(1)

        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            if attempt == retry:
                # 让模型只返回纯 JSON
                fix_messages = messages + [{"role": "user", "content": f"你的输出无法解析为 JSON，错误: {e}. 请只返回纯 JSON，不要包含任何解释或 Markdown。"}]
                fix_resp = llm.invoke(fix_messages)
                fixed_content = _extract_content_from_response(fix_resp).strip()
                # 再次尝试解析
                return json.loads(fixed_content)
            # 否则继续重试一次


def call_llm_text(
    llm: DeepseekClient,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """调用 LLM 返回纯文本"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    resp = llm.invoke(messages)
    return _extract_content_from_response(resp)


# 全局共享 LLM 实例（节省初始化开销）
_llm_instance: Optional[DeepseekClient] = None


def get_shared_llm() -> DeepseekClient:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = get_llm()
    return _llm_instance
