import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
MODEL_ID = os.getenv("LLM_MODEL_ID", "gpt-3.5-turbo")
# thinking 模式:enabled / adaptive / disabled,空字符串表示不传
THINKING_MODE = os.getenv("LLM_THINKING", "").strip()

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def extract_json(text: str) -> str:
    """
    从字符串中提取最长的合法 JSON 对象。

    Reasoning 模型(如 MiniMax-M3)的响应通常夹杂大量 thinking 块,
    其中可能含伪 JSON(Python 字面量、JSON 片段等)。简单的 find/rfind
    会被伪 JSON 误导。

    算法:遍历所有 `{` 起点,对每个起点用栈式配对找匹配的 `}`,
    然后用 json.loads 验证。返回所有合法候选中最长的那个。
    """
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


def chat(messages: list[dict], temperature: float = 0.7) -> str:
    """
    调用 LLM 并清洗响应,提取其中的 JSON 字符串。

    返回的是**纯 JSON 字符串**(不是 dict),由调用方负责解析成目标 schema。
    """
    kwargs = {
        "model": MODEL_ID,
        "messages": messages,
        "temperature": temperature,
    }
    if THINKING_MODE:
        # 把 thinking 模式塞进 extra_body(MiniMax / OpenAI 兼容扩展参数)
        kwargs["extra_body"] = {"thinking": {"type": THINKING_MODE}}

    response = client.chat.completions.create(**kwargs)
    raw_content = response.choices[0].message.content or ""
    return extract_json(raw_content)