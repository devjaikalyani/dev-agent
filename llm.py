# agent/llm.py — swap Cerebras → NVIDIA NIM
import config
from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """
    NVIDIA NIM via OpenAI-compatible API.
    Base URL: https://integrate.api.nvidia.com/v1
    Best coding model: qwen/qwen3-coder-480b-a35b-instruct
    """
    return ChatOpenAI(
        model=config.NVIDIA_MODEL,
        openai_api_key=config.NVIDIA_API_KEY,
        openai_api_base="https://integrate.api.nvidia.com/v1",
        temperature=temperature,
        max_tokens=config.MAX_TOKENS,
        streaming=False,
    )