import json
import os
import re

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
MODEL_ID = os.getenv("LLM_MODEL_ID", "gpt-3.5-turbo")
THINKING_MODE = os.getenv("LLM_THINKING", "").strip()

# Lazy init:不在 import 时构造客户端,避免 .env 缺 LLM_API_KEY 时整个进程崩。
# 延后到 chat() 第一次调用时再校验,这样 import 链路(reload / 评测脚本 / 单测)
# 都不会因为缺 key 而失败。
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """懒加载 LLM 客户端。第一次调用时校验 api_key,缺失则报错。"""
    global _client
    if _client is not None:
        return _client
    if not API_KEY:
        raise RuntimeError(
            "LLM_API_KEY 未配置。请在 backend/.env 里设置 "
            "LLM_API_KEY=your_key_here,然后重启服务。"
        )
    _client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _client


# Markdown 代码围栏:```json / ```JSON / ```(无语言标签)均可
_FENCE_RE = re.compile(r"```(?:json)?(.*?)```", re.DOTALL | re.IGNORECASE)


def _parse_object(s: str) -> dict | None:
    """把 s 解析成顶层为 object 的 JSON;失败或非 object 返回 None。"""
    try:
        value = json.loads(s)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def extract_json(text: str) -> str:
    """
    从 LLM 响应里提取 JSON 对象字符串(返回纯 JSON,由调用方解析成目标 schema)。

    模型形态不同,输出包装也不同,按成本从低到高逐层尝试:
    1. 整体直接是 JSON 对象 — 非 reasoning 模型最常见,一次 loads 即命中;
    2. Markdown 代码围栏 — 模型常把 JSON 包在 ```json 里,前后还夹解释性
       文字(非 reasoning 模型尤其常见),提取围栏内容解析;
    3. 栈式配对扫描 — reasoning 模型(如 MiniMax-M3)响应夹杂大量 thinking
       块,其中可能含伪 JSON(Python 字面量、JSON 片段)。遍历所有 `{` 起点,
       栈式配对找匹配的 `}`,json.loads 验证,返回最长合法对象,防伪 JSON 误导。

    都失败时原样返回文本,由调用方(Pydantic model_validate_json)兜底。
    """
    text = text.lstrip("﻿").strip()
    if not text:
        return text

    # 1. 整体就是纯 JSON 对象(没有前后缀、没有围栏)
    if _parse_object(text) is not None:
        return text

    # 2. 代码围栏提取(可多个围栏,取解析成功且最长的那个)
    valid = []
    for m in _FENCE_RE.finditer(text):
        content = m.group(1)
        if _parse_object(content) is not None:
            valid.append(content)
    if valid:
        return max(valid, key=len)

    # 3. 栈式配对扫描(兼容 thinking 块 + 伪 JSON)
    best = ""
    for start_pos in range(len(text)):
        if text[start_pos] != "{":
            continue

        depth = 0
        in_string = False
        escape = False
        for i in range(start_pos, len(text)):
            c = text[i]

            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue

            if in_string:
                if c == '"':
                    in_string = False
                continue

            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start_pos : i + 1]
                    try:
                        json.loads(candidate)
                        if len(candidate) > len(best):
                            best = candidate
                    except json.JSONDecodeError:
                        pass
                    break

    return best if best else text


async def chat(messages: list[dict], temperature: float = 0.7) -> str:
    """
    异步调 LLM 并清洗响应,提取其中的 JSON 字符串。

    返回的是**纯 JSON 字符串**(不是 dict),由调用方负责解析成目标 schema。
    """
    client = _get_client()

    kwargs = {
        "model": MODEL_ID,
        "messages": messages,
        "temperature": temperature,
    }
    if THINKING_MODE:
        kwargs["extra_body"] = {"thinking": {"type": THINKING_MODE}}

    response = await client.chat.completions.create(**kwargs)
    raw_content = response.choices[0].message.content or ""
    return extract_json(raw_content)