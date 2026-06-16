from app.config import Settings
from app.llm.client import (
    OllamaLlmClient,
    OpenAICompatibleLlmClient,
    _openai_message_content,
    _parse_json_object_content,
    create_llm_client,
)


def test_create_llm_client_uses_openai_compatible_by_default() -> None:
    client = create_llm_client(Settings())

    assert isinstance(client, OpenAICompatibleLlmClient)


def test_create_llm_client_can_select_ollama() -> None:
    client = create_llm_client(Settings(llm_provider="ollama"))

    assert isinstance(client, OllamaLlmClient)


def test_openai_message_content_ignores_reasoning_content() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": '{"solved": true}',
                    "reasoning_content": "internal reasoning should be ignored",
                }
            }
        ]
    }

    assert _openai_message_content(response) == '{"solved": true}'


def test_parse_json_object_content_accepts_markdown_fence() -> None:
    content = """```json
{
  "key_facts": ["一", "二"]
}
```"""

    assert _parse_json_object_content(content) == {"key_facts": ["一", "二"]}


def test_parse_json_object_content_extracts_object_from_extra_text() -> None:
    content = '前言\n{"solved": false}\n補充說明'

    assert _parse_json_object_content(content) == {"solved": False}
