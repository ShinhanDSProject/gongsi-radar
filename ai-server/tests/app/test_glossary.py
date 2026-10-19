"""용어 정의 초안(#14). mock이면 지어내지 않고, 투자 권유가 섞인 정의는 돌려주지 않는다."""
import pytest
from fastapi.testclient import TestClient

from app.api import glossary
from app.config import settings
from app.main import app
from app.safety import kill_switch

KEY = {"X-Internal-API-Key": settings.ai_server_api_key}


class FakeLLM:
    def __init__(self, text: str):
        self.text = text

    async def chat(self, messages, **kwargs):
        return self.text


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")

    def use(text: str):
        monkeypatch.setattr(glossary, "get_llm_client", lambda: FakeLLM(text))
    return use


def test_mock_provider_does_not_invent_a_definition(client):
    r = client.post("/ai/glossary/draft", json={"term": "PER"}, headers=KEY)
    assert r.status_code == 200
    assert r.json()["mock"] is True and "직접 작성" in r.json()["definition"]


def test_draft_parses_json_answer(client, llm):
    llm('```json\n{"definition": "주가를 주당순이익으로 나눈 값이다.", "usageNote": "시장 지표 화면에 나온다."}\n```')
    r = client.post("/ai/glossary/draft", json={"term": "PER", "aliases": ["주가수익비율"]}, headers=KEY)
    assert r.status_code == 200
    body = r.json()
    assert body["definition"].startswith("주가를") and body["usageNote"] and body["mock"] is False


def test_plain_text_answer_becomes_definition(client, llm):
    llm("주가를 주당순이익으로 나눈 값이다.")
    r = client.post("/ai/glossary/draft", json={"term": "PER"}, headers=KEY)
    assert r.json()["definition"] == "주가를 주당순이익으로 나눈 값이다." and r.json()["usageNote"] is None


def test_investment_advice_in_draft_is_blocked(client, llm):
    llm('{"definition": "지금이 매수 적기입니다.", "usageNote": ""}')
    r = client.post("/ai/glossary/draft", json={"term": "PER"}, headers=KEY)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "GUARDRAIL_BLOCKED"


def test_pii_in_input_is_blocked_before_llm(client, llm):
    llm("호출되면 안 된다")
    r = client.post("/ai/glossary/draft", json={"term": "PER", "context": "701010-1234567"}, headers=KEY)
    assert r.status_code == 422


def test_kill_switch_blocks_draft(client, monkeypatch):
    monkeypatch.setattr(kill_switch, "status", lambda **_: (True, "훈련"))
    r = client.post("/ai/glossary/draft", json={"term": "PER"}, headers=KEY)
    assert r.status_code == 503 and r.json()["detail"]["error"] == "KILL_SWITCH_ACTIVE"
