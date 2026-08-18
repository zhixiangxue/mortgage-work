"""Standalone inspection of the current settings file.

Run with:

    uv run python -m settings
"""
from .llm import read_models
from .memory import read_memory_config
from .store import SETTINGS_FILE


def main() -> None:
    view = read_models()
    print(f"settings file: {view['path']}"
          f"{'' if SETTINGS_FILE.exists() else ' (not created yet)'}")
    for p in view["providers"]:
        print(f"  {p['provider']:<12} {p['base_url'] or '(default url)':<40} "
              f"{p['key_hint'] or '(no key)':<14} {', '.join(p['models'])}")
    if not view["providers"]:
        print("  no providers configured")
    mem = read_memory_config()
    emb = mem["embedding"]
    print(f"memory: {'on' if mem['enabled'] else 'off'} · "
          f"{(emb['provider'] + '/' + emb['model']) if emb else 'no embedder'}"
          f"{'' if not emb or mem['ready'] else ' (provider unavailable)'}")


if __name__ == "__main__":
    main()
