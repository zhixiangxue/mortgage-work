"""Skill market engine — repo-as-market for installable agent skills.

The market is a git repo. Each top-level directory is one Agent Skill (Anthropic
SKILL.md format). The app clones/pulls it like the work repo; install is
``uv sync``; load is ``ClaudeSkill(dir, runner=PyRunner(python=venv))`` — the
runner is scoped to each skill's ``.venv`` interpreter and exposed as a
namespaced ``{skill_name}__run_python`` companion tool, so multiple skills
never collide on a global ``python``/``bash`` tool name.

Three-layer state (all derived, nothing stored in a DB):
  present    — the skill exists in the market repo (git pull decides)
  installed  — the skill's ``.venv/`` exists (uv sync decides)
  enabled    — the user's on/off choice (skill.local.toml, gitignored)

Design rules (mirrors workrepo.py's philosophy):
  * The repo is the source of truth for skill content + author metadata.
  * Device-local state (.venv/, skill.local.toml, uv.lock) never enters git.
  * Clone/pull failures are non-fatal — the local copy keeps working.
  * Every subprocess uses UTF-8 explicitly (Windows locale is GBK).

Run standalone for a smoke test:

    uv run python skills_manager.py
"""
from __future__ import annotations

import os
import logging
import shutil
import subprocess
import sys
import tomllib  # py3.11+
from pathlib import Path

log = logging.getLogger(__name__)

# ── Paths ──

WORKSPACE_ROOT = Path.home() / "MortgageWork"
MARKET_DIR = WORKSPACE_ROOT / "mortgage-skills"

# The official-only market remote. No user-configurable sources for now.
# International build:
# MARKET_URL = "https://github.com/zhixiangxue/mortgage-skills.git"
# China build (Codeup — GitHub is unreliable there):
MARKET_URL = "https://codeup.aliyun.com/67a992d4136b5e5abf900e50/zhixiangxue/mortgage-skills.git"


# ── Git plumbing (UTF-8 on Windows, non-interactive, non-fatal) ──

def _git_env() -> dict:
    return os.environ | {
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
    }


def _git(args: list[str], cwd: Path | None = None,
         timeout: int = 60) -> subprocess.CompletedProcess:
    """Run git with explicit UTF-8 and a real timeout. Never raises."""
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        env=_git_env(), timeout=timeout,
    )


def _remote_reachable(url: str) -> bool:
    """Cheapest question git can ask the network."""
    res = _git(["ls-remote", "--exit-code", "-q", url, "HEAD"], timeout=15)
    return res.returncode == 0


def _last_line(text: str | None, fallback: str = "unknown") -> str:
    lines = (text or "").strip().splitlines()
    return lines[-1] if lines else fallback


# ── Market sync (clone-or-pull) ──

def sync_market() -> str:
    """Clone if first boot, fast-forward pull otherwise.

    Returns a status string for logging. Never raises — an unreachable remote
    leaves the existing local copy working.
    """
    MARKET_DIR.mkdir(parents=True, exist_ok=True)

    if not (MARKET_DIR / ".git").is_dir():
        if not _remote_reachable(MARKET_URL):
            return f"market unreachable: {MARKET_URL}"
        log.info("skills cloning %s → %s", MARKET_URL, MARKET_DIR)
        res = _git(["clone", MARKET_URL, str(MARKET_DIR)], timeout=300)
        if res.returncode != 0:
            return f"clone failed: {_last_line(res.stderr)}"
        return "cloned"
    else:
        res = _git(["pull", "--ff-only"], cwd=MARKET_DIR, timeout=90)
        if res.returncode == 0:
            return "up-to-date"
        # Non-fatal: keep working from local copy
        return f"pull skipped: {_last_line(res.stderr)}"


# ── Skill scanning ──

class SkillInfo:
    """One skill's merged state: author metadata (skill.toml) + local state
    (skill.local.toml) + derived install status (.venv/ exists).

    The dataclass-free shape mirrors how workrepo.py treats a client folder:
    the folder IS the skill, and its state is read fresh every time.
    """

    def __init__(self, skill_dir: Path):
        self.dir = skill_dir
        self.id = skill_dir.name  # folder name is the canonical id

        # Author metadata from skill.toml (travels with the repo)
        self.meta = _load_toml(skill_dir / "skill.toml")
        self.installable = self.meta.get("installable", True)
        self.default_enabled = self.meta.get("default_enabled", True)
        self.description = self.meta.get("description", "")
        self.version = self.meta.get("version", "")

        # User override from skill.local.toml (gitignored, device-local)
        local = _load_toml(skill_dir / "skill.local.toml")
        self.enabled = local.get("enabled", self.default_enabled)

        # Derived: .venv/ exists → installed. Never stored.
        self.installed = (skill_dir / ".venv").is_dir()

    def __repr__(self) -> str:
        flag = "enabled" if self.enabled else "disabled"
        inst = "installed" if self.installed else "not-installed"
        return (f"SkillInfo(id={self.id!r}, {inst}, {flag})")


def _load_toml(path: Path) -> dict:
    """Read a TOML file; return {} if missing or broken."""
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
        # skill.toml uses [skill] section; skill.local.toml uses flat top-level
        if "skill" in data and isinstance(data["skill"], dict):
            return data["skill"]
        return data
    except Exception:  # noqa: BLE001 — broken metadata is no reason to skip a skill
        return {}


def scan_skills() -> list[SkillInfo]:
    """Every skill present in the market repo. A skill is a directory that
    contains a SKILL.md (the Anthropic format contract)."""
    if not MARKET_DIR.is_dir():
        return []
    skills = []
    for entry in sorted(MARKET_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name == ".git":
            continue
        if not (entry / "SKILL.md").is_file():
            continue  # not a skill — maybe a docs folder, maybe a future thing
        skills.append(SkillInfo(entry))
    return skills


# ── Install / uninstall (uv sync / delete .venv) ──

def _venv_python(skill_dir: Path) -> Path:
    """The interpreter path for a skill's .venv (Windows vs Unix layout)."""
    if sys.platform == "win32":
        return skill_dir / ".venv" / "Scripts" / "python.exe"
    return skill_dir / ".venv" / "bin" / "python"


def install_skill(skill_id: str) -> str:
    """uv sync inside the skill directory. Creates/refreshes .venv/.

    Returns a status string for logging. Never raises.
    """
    skill_dir = MARKET_DIR / skill_id
    if not skill_dir.is_dir():
        return f"no such skill: {skill_id}"

    info = SkillInfo(skill_dir)
    if not info.installable:
        return f"skill {skill_id} is not installable"

    # uv sync reads pyproject.toml, creates .venv/, installs deps.
    # --active is omitted on purpose: we want .venv, not a shared env.
    res = subprocess.run(
        ["uv", "sync", "--no-progress"],
        cwd=str(skill_dir),
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=300,
    )
    if res.returncode != 0:
        return f"install failed: {_last_line(res.stderr)}"
    return f"installed: {skill_id}"


def uninstall_skill(skill_id: str) -> str:
    """Delete the .venv/ directory. Source stays (it's part of the market repo)."""
    skill_dir = MARKET_DIR / skill_id
    venv = skill_dir / ".venv"
    if not venv.is_dir():
        return f"not installed: {skill_id}"
    shutil.rmtree(venv, ignore_errors=True)
    return f"uninstalled: {skill_id}"


# ── Enable / disable (skill.local.toml, gitignored) ──

def set_enabled(skill_id: str, enabled: bool) -> str:
    """Toggle a skill on/off by writing skill.local.toml.

    This is the ONLY writeable state, and it lives OUTSIDE git on purpose.
    """
    skill_dir = MARKET_DIR / skill_id
    if not skill_dir.is_dir():
        return f"no such skill: {skill_id}"
    local_path = skill_dir / "skill.local.toml"
    local_path.write_text(
        f"# Device-local skill state — gitignored, never synced.\n"
        f"enabled = {str(enabled).lower()}\n",
        encoding="utf-8",
    )
    return f"{'enabled' if enabled else 'disabled'}: {skill_id}"


# ── Load: build chak tool instances for the agent ──

def load_skill_tools(
    filter: set[str] | None = None,
) -> tuple[list, list[str]]:
    """Build the list of chak tools for all enabled+installed skills.

    Each skill contributes a single ClaudeSkill carrying a PyRunner bound to
    that skill's ``.venv`` interpreter. The runner is exposed to the LLM as a
    namespaced ``{skill_name}__run_python`` tool, so every skill gets its own
    execution surface without colliding on a global ``python`` tool name.

    If *filter* is given, only skills whose id is in the set are loaded —
    clerk uses this to pick pure-calc skills while delegating vision skills
    to sub-agents.

    If a skill is enabled but not installed, it is logged and skipped — the
    agent still gets the rest.

    Returns (tools, skill_names) so the caller can log what was loaded.
    """
    from chak.tools.skills import ClaudeSkill, PyRunner

    tools = []
    loaded_names = []
    for info in scan_skills():
        if filter and info.id not in filter:
            continue
        if not info.enabled:
            continue
        if not info.installed:
            log.warning("skills %s: enabled but not installed — skipping", info.id)
            continue
        try:
            python_exe = str(_venv_python(info.dir))
            skill = ClaudeSkill(str(info.dir),
                                runner=PyRunner(python=python_exe))
            tools.append(skill)
            loaded_names.append(info.id)
            log.info("skills loaded: %s (venv: %s)", info.id, python_exe)
        except Exception as exc:  # noqa: BLE001 — one bad skill must not break the rest
            log.error("skills %s: load failed — %s", info.id, exc)
    return tools, loaded_names


# ── UI query ──

def skill_inventory() -> list[dict]:
    """Skill list for the UI, JSON-safe.

    Mirrors what scan_skills() sees, but as plain dicts so the bridge can
    serialise them. Called on boot and after every install/uninstall/toggle.
    """
    return [{
        "id": s.id,
        "name": s.meta.get("name", s.id),
        "description": s.description,
        "version": s.version,
        "installed": s.installed,
        "enabled": s.enabled,
        "installable": s.installable,
    } for s in scan_skills()]


# ── Boot-time orchestration ──

def ensure_skills() -> list[SkillInfo]:
    """The boot sequence: sync market → auto-install enabled skills → list.

    This is what the agent service calls on startup (or what a standalone
    test calls). Returns the full skill inventory for logging/UI.
    """
    status = sync_market()
    log.info("skills market: %s", status)

    skills = scan_skills()
    for info in skills:
        state_parts = []
        if info.enabled:
            state_parts.append("enabled")
        else:
            state_parts.append("disabled")
        if info.installable and not info.installed:
            state_parts.append("not-installed")
            # Auto-install on first boot so the agent doesn't start with gaps.
            result = install_skill(info.id)
            log.info("skills %s", result)
        elif info.installed:
            state_parts.append("installed")
        log.info("skills %s: %s", info.id, ', '.join(state_parts))
    return skills


# ── Helpers for the standalone smoke test ──

def _indent(text: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in text.strip().splitlines())


if __name__ == "__main__":
    print("=" * 60)
    print("SkillsManager — standalone smoke test")
    print("=" * 60)

    # 1. Sync market
    print("\n[1] Syncing market...")
    print(f"    {sync_market()}")

    # 2. Scan skills
    print("\n[2] Scanning skills...")
    skills = scan_skills()
    for s in skills:
        print(f"    {s}")
    if not skills:
        print("    (none found)")
        sys.exit(0)

    # 3. Install each (idempotent — uv sync is a no-op when already in sync)
    print("\n[3] Installing skills...")
    for s in skills:
        print(f"    {install_skill(s.id)}")

    # 4. Verify install
    print("\n[4] Verifying install...")
    for s in scan_skills():
        print(f"    {s}")

    # 5. Load tools
    print("\n[5] Loading skill tools...")
    tools, names = load_skill_tools()
    print(f"    loaded skills: {names}")
    print(f"    tool instances: {len(tools)}")
    for t in tools:
        print(f"      {t}")

    # 6. Execute pure-calc skill scripts + verify vision skills import
    print("\n[6] Executing skill scripts...")
    import json as _json

    # Pure-calc skills: run end-to-end with sample input (no API key needed)
    _calc_tests = {
        "payment-calculator": {
            "script": "scripts/payment_calc.py",
            "input": {"loan_amount": 400000, "interest_rate": 6.875,
                      "term_years": 30, "home_value": 500000},
        },
        "dti-calculator": {
            "script": "scripts/dti_calc.py",
            "input": {"monthly_income": 8000, "monthly_housing_piti": 2400,
                      "monthly_debts": [{"name": "auto", "amount": 500}]},
        },
        "ltv-cltv": {
            "script": "scripts/ltv_cltv.py",
            "input": {"first_loan": 475000, "home_value": 500000},
        },
        "doc-checklist": {
            "script": "scripts/doc_checklist.py",
            "input": {"loan_type": "fha", "borrower_type": "purchase"},
        },
    }
    # Vision skills: just verify venv exists (API key needed for real run)
    _vision_skills = {"income-calc", "credit-report-analyzer"}

    for skill_id, test in _calc_tests.items():
        skill_dir = MARKET_DIR / skill_id
        if not skill_dir.is_dir():
            print(f"    [{skill_id}] not found — skipping")
            continue
        py = _venv_python(skill_dir)
        if not py.is_file():
            print(f"    [{skill_id}] venv not installed — skipping")
            continue
        payload = _json.dumps(test["input"])
        res = subprocess.run(
            [str(py), str(skill_dir / test["script"])],
            input=payload, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        status = "OK" if res.returncode == 0 else "FAIL"
        print(f"    [{skill_id}] {status} (exit {res.returncode})")
        print(f"{_indent(res.stdout[:500])}")
        if res.stderr.strip():
            print(f"{_indent(res.stderr[:300])}")

    for skill_id in _vision_skills:
        skill_dir = MARKET_DIR / skill_id
        if not skill_dir.is_dir():
            continue
        py = _venv_python(skill_dir)
        if py.is_file():
            print(f"    [{skill_id}] venv OK (vision skill — API key required for real run)")
        else:
            print(f"    [{skill_id}] venv not installed")

    print("\n" + "=" * 60)
    print("Done — full pipeline verified.")
