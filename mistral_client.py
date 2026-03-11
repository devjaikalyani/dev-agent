"""
mistral_client.py — Mistral AI client for DevAgent.
"""
from __future__ import annotations
import json
import os
import time
from typing import Optional
from openai import OpenAI  # Actually using Mistral SDK, but keeping for compatibility
from mistralai import Mistral
import config

_client: Optional[Mistral] = None


def get_client() -> Mistral:
    """Get Mistral AI client."""
    global _client
    if _client is None:
        api_key = os.environ.get("MISTRAL_API_KEY") or config.MISTRAL_API_KEY
        if not api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY not set.\n"
                "Get your key at: https://console.mistral.ai/"
            )
        _client = Mistral(api_key=api_key)
    return _client


def call_with_retry(func, max_retries=5, base_delay=2):
    """Call a function with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            # Check if it's a rate limit error (429)
            if "429" in str(e) or "rate limit" in str(e).lower():
                if attempt == max_retries - 1:
                    raise  # Re-raise on last attempt
                
                # Exponential backoff
                wait_time = base_delay * (2 ** attempt)
                print(f"  [yellow]Rate limit hit, waiting {wait_time}s (attempt {attempt+1}/{max_retries})...[/yellow]")
                time.sleep(wait_time)
            else:
                # Not a rate limit, re-raise immediately
                raise
    raise RuntimeError("Max retries exceeded")


def chat(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    system: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.0,
    json_mode: bool = False,
) -> tuple[object, int]:
    """
    Unified chat completion with optional tools.
    Returns (message_object, tokens_used).
    """
    client = get_client()
    
    # Prepare messages
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)
    
    # Get model from config
    model = config.MISTRAL_MODEL
    
    # Prepare kwargs
    kwargs = {
        "model": model,
        "messages": full_messages,
        "max_tokens": max_tokens or config.MAX_TOKENS,
        "temperature": temperature,
    }
    
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    
    # Make the API call with retry
    def make_request():
        return client.chat.complete(**kwargs)
    
    try:
        response = call_with_retry(make_request)
        message = response.choices[0].message
        tokens = response.usage.total_tokens if response.usage else 0
        return message, tokens
    except Exception as e:
        print(f"  [red]Mistral API error after retries: {e}[/red]")
        raise


# For backward compatibility with existing code
def call_llm(
    messages: list[dict],
    system: str | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
    json_mode: bool = False,
) -> tuple[str, int]:
    """Simple text completion (no tools)."""
    msg, tokens = chat(messages, tools=None, system=system, 
                       max_tokens=max_tokens, temperature=temperature, json_mode=json_mode)
    return msg.content or "", tokens


def call_llm_with_tools(
    messages: list[dict],
    tools: list[dict],
    system: str | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
) -> tuple[object, int]:
    """Tool-calling completion."""
    return chat(messages, tools=tools, system=system, 
                max_tokens=max_tokens, temperature=temperature)