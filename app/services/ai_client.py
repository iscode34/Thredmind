import httpx
from app.config import settings

PROVIDERS = [
    {
        "name": "deepseek",
        "model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
    },
    {
        "name": "google",
        "model": "gemini-2.0-flash",
        "env_key": "GOOGLE_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    },
    {
        "name": "nvidia",
        "model": "minimaxai/minimax-m2.7",
        "env_key": "NVIDIA_API_KEY",
        "base_url": "https://integrate.api.nvidia.com/v1",
    },
    {
        "name": "openrouter",
        "model": "google/gemini-2.0-flash-001:free",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
    },
]


def chat_completion(
    messages: list,
    system_prompt: str = None,
    max_tokens: int = 2000,
    temperature: float = 0.5,
) -> dict:
    if system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + messages

    errors = []
    for provider in PROVIDERS:
        api_key = getattr(settings, provider["env_key"], None)
        if not api_key:
            print(f"[AI] {provider['name']}: SKIP (no API key)")
            continue

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": provider["model"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            print(f"[AI] {provider['name']}: trying {provider['model']}...")
            response = httpx.post(
                f"{provider['base_url']}/chat/completions",
                headers=headers,
                json=body,
                timeout=90,
            )
            data = response.json()
            if "error" in data:
                err_msg = str(data["error"])
                print(f"[AI] {provider['name']}: FAIL ({response.status_code}) - {err_msg[:200]}")
                raise RuntimeError(err_msg)
            content = data["choices"][0]["message"]["content"]
            print(f"[AI] {provider['name']}: SUCCESS ({response.status_code})")
            return {
                "content": content,
                "model": provider["model"],
                "provider": provider["name"],
            }
        except Exception as e:
            err_str = str(e)[:200]
            print(f"[AI] {provider['name']}: ERROR - {err_str}")
            errors.append(f"{provider['name']}: {err_str}")
            continue

    raise RuntimeError(f"All AI providers failed: {'; '.join(errors)}")
