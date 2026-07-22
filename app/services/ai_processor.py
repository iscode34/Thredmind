import json
from app.services.ai_client import chat_completion

SYSTEM_PROMPT = """You are an AI knowledge processor. Given a text, output a JSON object with the following structure:
{
  "summary": "A concise 200-300 word summary of the content.",
  "entities": {
    "people": ["list of people mentioned"],
    "topics": ["list of topics or concepts discussed"],
    "organizations": ["list of organizations mentioned"],
    "dates": ["list of dates or time periods mentioned"]
  },
  "keywords": ["5-10 relevant keywords or tags"]
}

Only return valid JSON. No markdown, no code blocks, no explanation."""


def process_content(text: str) -> dict:
    if not text.strip():
        raise ValueError("No text content to process")
    text = text[:12000]
    result = chat_completion(
        messages=[{"role": "user", "content": text}],
        system_prompt=SYSTEM_PROMPT,
        max_tokens=1500,
        temperature=0.3,
    )
    return _parse_ai_response(result["content"])


def _parse_ai_response(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])
    return json.loads(content)
