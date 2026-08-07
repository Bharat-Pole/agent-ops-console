"""Freshness + memory fixes for the live runtime and generated projects.

Covers the web_searcher failure class: (1) every turn was a cold start (fresh
MemorySaver per call), (2) the model had no idea what today's date is, so it
overrode fresh tool results with its stale prior.
"""
import json
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent_forge import generate
from agent_forge.runtime import run_agent, _sys_prompt
from agent_forge.loader import load_agent

FIX = Path(__file__).parent / "fixtures"


class FakeChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    def bind_tools(self, tools, **kwargs):
        return self


def test_conversation_memory_across_calls():
    # Two separate run_agent calls, same agent + thread → the second call must
    # see the first call's history (regression: fresh MemorySaver per call).
    rec = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    first = run_agent(rec, "my name is Bharat", thread_id="mem-test", model=FakeChatModel())
    second = run_agent(rec, "what is my name?", thread_id="mem-test", model=FakeChatModel())
    assert second["trace"]["messages"] > first["trace"]["messages"]
    # a different thread on the same agent starts clean (thread isolation)
    other = run_agent(rec, "hello", thread_id="mem-test-other", model=FakeChatModel())
    assert other["trace"]["messages"] == first["trace"]["messages"]


def test_runtime_system_prompt_carries_todays_date():
    ir = load_agent(json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8")))
    sp = _sys_prompt(ir)
    assert "Today's date is" in sp
    assert "tool results are the ground truth" in sp


def test_generated_prompts_compute_date_at_run_time():
    res = generate(str(FIX / "hr_policy_bot.json"))
    prompts = res.files[f"src/{res.agent.pkg}/prompts.py"]
    # date is COMPUTED at run time, never baked as a literal at generation time
    assert "_TODAY = datetime.now()" in prompts.replace('.strftime("%A, %B %d, %Y")', "")
    assert "Today's date is {_TODAY}" in prompts
    compile(prompts, "prompts.py", "exec")  # generated module is valid python
    # determinism: identical input → byte-identical output (date not baked)
    res2 = generate(str(FIX / "hr_policy_bot.json"))
    assert res.files == res2.files and res.zip_bytes() == res2.zip_bytes()


def test_honesty_clause_present_when_tools_bound():
    rec = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    rec["config"]["tooling"]["bound_tools"]["value"] = ["tools://web_searcher@v1"]
    ir = load_agent(rec)
    assert "TOOL HONESTY" in ir.prompt.system_prompt
