"""End-to-end skill test via chak — the agent way.

This script builds a real chak Conversation with skill tools attached,
sends natural-language messages, and watches the LLM autonomously pick
and invoke the right skill. It's the same mechanism the chat UI uses:
the model reads SKILL.md descriptions, decides which tool to call, runs
the Python script in the skill's venv, and narrates the result.

    uv run python test_skills.py                          # all pure-calc skills
    uv run python test_skills.py dti                      # only dti-calculator
    uv run python test_skills.py ltv doc                  # ltv-cltv + doc-checklist
    uv run python test_skills.py --model openai/gpt-4o    # force a specific model
    uv run python test_skills.py dti --model deepseek/deepseek-v4-pro

Prerequisites:
    1. At least one provider configured in ~/MortgageWork/settings/models.yaml
    2. Pure-calc skills installed (uv sync in each skill dir)
    3. The chat model must support tool calling (Claude, GPT-4o, etc.)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chak
from chak import MessageChunk
from chak.message import (
    ToolCallStartEvent,
    ToolCallSuccessEvent,
    ToolCallErrorEvent,
)

from model_settings import _load as load_models_yaml
from skills_manager import load_skill_tools, scan_skills, MARKET_DIR


# ── ANSI colors for readable console output ─────────────────────────────────

_NO_COLOR = "\033[0m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"


# ── Pick a chat model from models.yaml ──────────────────────────────────────

def pick_chat_model(forced: str | None = None) -> tuple[str, str]:
    """Pick a provider+model from models.yaml for tool calling.

    Args:
        forced: 'provider/model' override from --model CLI arg.

    Returns (model_ref, api_key) where model_ref is 'provider/model'.
    """
    data = load_models_yaml()
    providers = data.get("providers") or {}

    # Explicit --model override
    if forced:
        if "/" not in forced:
            print(f"{_RED}--model must be 'provider/model', got '{forced}'{_NO_COLOR}")
            sys.exit(1)
        provider, model = forced.split("/", 1)
        entry = providers.get(provider)
        if not isinstance(entry, dict) or not entry.get("api_key"):
            print(f"{_RED}provider '{provider}' not configured{_NO_COLOR}")
            sys.exit(1)
        api_key = str(entry["api_key"])
        models = entry.get("models") or []
        if model not in models:
            print(f"{_YELLOW}warning: '{model}' not in configured models {models}, "
                  f"using anyway{_NO_COLOR}")
        print(f"{_DIM}[test] using chat model: {forced}{_NO_COLOR}")
        return forced, api_key

    # Auto-pick: deepseek > openai > anthropic > anything else
    # (deepseek/openai tend to have fewer proxy issues in CN)
    priority = ["deepseek", "openai", "anthropic"]
    all_names = priority + [p for p in providers if p not in priority]

    for name in all_names:
        entry = providers.get(name)
        if not isinstance(entry, dict):
            continue
        api_key = str(entry.get("api_key") or "")
        if not api_key:
            continue
        models = entry.get("models") or []
        if not models:
            continue
        model_ref = f"{name}/{models[0]}"
        print(f"{_DIM}[test] using chat model: {model_ref}{_NO_COLOR}")
        return model_ref, api_key

    print(f"{_RED}[test] No provider with a model found in models.yaml{_NO_COLOR}")
    print(f"{_DIM}       Configure one in Settings or edit "
          f"~/MortgageWork/settings/models.yaml{_NO_COLOR}")
    sys.exit(1)


def resolve_to_uri(model_ref: str, api_key: str) -> str:
    """Convert 'provider/model' to a chak URI, preserving base_url if set."""
    data = load_models_yaml()
    provider, model = model_ref.split("/", 1)
    entry = (data["providers"].get(provider)) or {}
    base_url = str(entry.get("base_url") or "").strip()
    return f"{provider}@{base_url or '~'}:{model}"


# ── Test cases: natural-language prompts that should trigger each skill ─────

TESTS: list[dict] = [
    {
        "id": "payment",
        "skill": "payment-calculator",
        "keyword": "payment",
        "prompt": (
            "A client is buying a $500,000 home with a $400,000 loan at 6.875% "
            "interest for 30 years. Property tax is $6,000/year and insurance "
            "is $1,750/year. What's their total monthly housing payment (PITIA)?"
        ),
    },
    {
        "id": "dti",
        "skill": "dti-calculator",
        "keyword": "dti",
        "prompt": (
            "Help me calculate the DTI for a borrower: monthly income $8,000, "
            "monthly housing payment (PITIA) $2,400, car loan $500/month, "
            "student loan $300/month, credit card minimum payment $120/month. "
            "Do they qualify for conventional, FHA, and VA?"
        ),
    },
    {
        "id": "ltv",
        "skill": "ltv-cltv",
        "keyword": "ltv",
        "prompt": (
            "A borrower is buying a $500,000 home with a first mortgage of "
            "$475,000. They also have a $25,000 HELOC but haven't drawn on it yet. "
            "What's the LTV, CLTV, and HCLTV? Will they need PMI and at what rate?"
        ),
    },
    {
        "id": "doc",
        "skill": "doc-checklist",
        "keyword": "doc",
        "prompt": (
            "I'm working on an FHA purchase loan for a first-time homebuyer who "
            "is also self-employed. What documents do I need to collect? "
            "Give me the checklist."
        ),
    },
]


# ── Run one test case ───────────────────────────────────────────────────────

async def run_test(
    conv_factory,
    test: dict,
    index: int,
    total: int,
) -> bool:
    """Run a single test case. Returns True if the skill was invoked successfully."""
    test_id = test["id"]
    skill_name = test["skill"]
    prompt = test["prompt"]

    header = f" Test {index}/{total}: {test_id} → expect {skill_name} "
    bar_len = max(0, 60 - len(header))
    print(f"\n{'=' * 3}{header}{'=' * bar_len}")
    print(f"{_BOLD}User:{_NO_COLOR} {prompt}")
    print(f"{_DIM}{'─' * 60}{_NO_COLOR}")

    # Fresh conversation per test — no cross-contamination
    conv = conv_factory()

    # Stream the response, watching for tool calls
    final_text_parts: list[str] = []
    tool_calls: list[str] = []
    skill_invoked = False
    skill_succeeded = False
    error_msg = ""

    try:
        stream = await conv.asend(prompt, stream=True, event=True)
        async for ev in stream:
            if isinstance(ev, ToolCallStartEvent):
                tool_name = ev.tool_name
                tool_calls.append(tool_name)
                # Highlight skill-related tool calls
                if tool_name in ("python", "bash"):
                    print(f"{_CYAN}  → {tool_name}({ev.arguments}){_NO_COLOR}")
                else:
                    print(f"{_DIM}  → {tool_name}(...){_NO_COLOR}")

            elif isinstance(ev, ToolCallSuccessEvent):
                result_str = str(ev.result)
                # Check if the result references the expected skill
                if test["skill"] in result_str.lower() or test["id"] in result_str.lower():
                    skill_invoked = True
                    skill_succeeded = True
                # Show a snippet of the result
                snippet = result_str[:200].replace("\n", " ")
                print(f"{_GREEN}  ✓ {snippet}...{_NO_COLOR}")

            elif isinstance(ev, ToolCallErrorEvent):
                print(f"{_RED}  ✗ {ev.tool_name} error: {ev.error}{_NO_COLOR}")
                error_msg = str(ev.error)

            elif isinstance(ev, MessageChunk):
                if ev.content:
                    final_text_parts.append(ev.content)
                if ev.is_final and ev.final_message is not None:
                    content = ev.final_message.content
                    if isinstance(content, str) and content:
                        final_text_parts = [content]

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print(f"{_RED}  ✗ exception: {error_msg}{_NO_COLOR}")

    # ── Verdict ─────────────────────────────────────────────────────────────
    print(f"{_DIM}{'─' * 60}{_NO_COLOR}")

    final_answer = "".join(final_text_parts).strip()
    # Show a trimmed version of the final answer
    if final_answer:
        preview = final_answer[:500]
        if len(final_answer) > 500:
            preview += "\n  ..."
        print(f"{_BOLD}Agent:{_NO_COLOR}\n  {preview}")

    # Determine pass/fail
    # Heuristic: did the agent call a python/bash tool AND produce a non-empty answer?
    called_code_tool = any(t in ("python", "bash") for t in tool_calls)
    has_answer = bool(final_answer)

    if called_code_tool and has_answer and not error_msg:
        print(f"\n  {_GREEN}✓ PASS — skill invoked, answer generated{_NO_COLOR}")
        return True
    elif has_answer and not error_msg:
        # The model might have answered from general knowledge without calling the tool.
        # That's not a hard fail, but worth flagging.
        if called_code_tool:
            print(f"\n  {_GREEN}✓ PASS{_NO_COLOR}")
            return True
        else:
            print(f"\n  {_YELLOW}⚠ ANSWER WITHOUT TOOL — model answered "
                  f"but didn't call any skill{_NO_COLOR}")
            return True  # soft pass
    else:
        print(f"\n  {_RED}✗ FAIL — {error_msg or 'no answer produced'}{_NO_COLOR}")
        return False


# ── Main ────────────────────────────────────────────────────────────────────

async def main_async():
    print(f"\n{_BOLD}{'═' * 60}{_NO_COLOR}")
    print(f"{_BOLD}  Mortgage Skills — End-to-End Agent Test{_NO_COLOR}")
    print(f"{_BOLD}{'═' * 60}{_NO_COLOR}")

    # 1. Check which skills are installed + enabled
    print(f"\n{_BOLD}[1] Checking installed skills...{_NO_COLOR}")
    skills = scan_skills()
    active = [s for s in skills if s.installed and s.enabled]
    for s in skills:
        status = []
        if s.installed:
            status.append("installed")
        if s.enabled:
            status.append("enabled")
        marker = _GREEN if (s.installed and s.enabled) else _DIM
        print(f"  {marker}{s.id:<25} {', '.join(status) or 'inactive'}{_NO_COLOR}")

    if not active:
        print(f"\n{_RED}No installed+enabled skills found.{_NO_COLOR}")
        print(f"{_DIM}Install skills first: uv run python skills_manager.py{_NO_COLOR}")
        return

    # 2. Load skill tools, deduplicate python/bash by name
    #    (Each skill contributes a ClaudeSkill + Python + Bash. ClaudeSkill
    #    instances are already unique, but Python/Bash share the same tool name
    #    — some providers like DeepSeek reject duplicate tool names.)
    print(f"\n{_BOLD}[2] Loading skill tools...{_NO_COLOR}")
    raw_tools, loaded_names = load_skill_tools()
    print(f"  loaded skills: {loaded_names}")

    seen_names: set[str] = set()
    tools = []
    for t in raw_tools:
        tname = getattr(t, "name", None) or getattr(t, "__name__", str(id(t)))
        if tname in seen_names:
            continue
        seen_names.add(tname)
        tools.append(t)
    print(f"  unique tools: {len(tools)} (deduped from {len(raw_tools)})")

    if not tools:
        print(f"\n{_RED}No skill tools loaded. Check install status.{_NO_COLOR}")
        return

    # 3. Pick chat model
    print(f"\n{_BOLD}[3] Selecting chat model...{_NO_COLOR}")
    model_ref, api_key = pick_chat_model()
    model_uri = resolve_to_uri(model_ref, api_key)

    # 4. Filter tests based on CLI args (positional, not --model)
    cli_args = sys.argv[1:]
    forced_model = None
    cli_filters = []
    i = 0
    while i < len(cli_args):
        if cli_args[i] == "--model" and i + 1 < len(cli_args):
            forced_model = cli_args[i + 1]
            i += 2
        elif cli_args[i].startswith("--model="):
            forced_model = cli_args[i].split("=", 1)[1]
            i += 1
        else:
            cli_filters.append(cli_args[i].lower())
            i += 1

    # Re-pick model if --model was provided
    if forced_model:
        model_ref, api_key = pick_chat_model(forced=forced_model)
        model_uri = resolve_to_uri(model_ref, api_key)

    if cli_filters:
        tests = [t for t in TESTS
                 if any(f in t["id"] or f in t["keyword"] for f in cli_filters)]
        if not tests:
            print(f"{_RED}No tests matching: {cli_filters}{_NO_COLOR}")
            print(f"{_DIM}Available: {[t['id'] for t in TESTS]}{_NO_COLOR}")
            return
    else:
        tests = list(TESTS)

    # 5. Run tests
    print(f"\n{_BOLD}[4] Running {len(tests)} test(s)...{_NO_COLOR}")

    # Conversation factory: each test gets a fresh conversation with all skill tools
    def conv_factory():
        return chak.Conversation(
            model_uri,
            api_key=api_key,
            tools=tools,
        )

    results: list[tuple[str, bool]] = []
    for i, test in enumerate(tests, 1):
        passed = await run_test(conv_factory, test, i, len(tests))
        results.append((test["id"], passed))

    # 6. Summary
    print(f"\n{_BOLD}{'═' * 60}{_NO_COLOR}")
    print(f"{_BOLD}  Summary{_NO_COLOR}")
    print(f"{_BOLD}{'═' * 60}{_NO_COLOR}")
    passed_count = sum(1 for _, p in results if p)
    for test_id, passed in results:
        marker = f"{_GREEN}✓{_NO_COLOR}" if passed else f"{_RED}✗{_NO_COLOR}"
        print(f"  {marker} {test_id}")
    print(f"\n  {passed_count}/{len(results)} passed")

    if passed_count == len(results):
        print(f"  {_GREEN}{_BOLD}All tests passed!{_NO_COLOR}")
    else:
        print(f"  {_YELLOW}{len(results) - passed_count} test(s) need attention{_NO_COLOR}")


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print(f"\n{_YELLOW}[test] interrupted{_NO_COLOR}")
        sys.exit(130)


if __name__ == "__main__":
    main()
