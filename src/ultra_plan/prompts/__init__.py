from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
SOURCES_DIR = PROMPTS_DIR / "sources"
KNOWN_SOURCES: tuple[str, ...] = ("github", "mcp", "anthropic", "web")
PRESETS: dict[str, tuple[str, ...]] = {
    "wide": KNOWN_SOURCES,
    "local-only": (),
}


def render_prompt(task: str, sources: list[str]) -> str:
    parts: list[str] = [(PROMPTS_DIR / "system.md").read_text()]
    for src in sources:
        if src not in KNOWN_SOURCES:
            raise ValueError(f"Unknown source: {src}")
        parts.append((SOURCES_DIR / f"{src}.md").read_text())
    parts.append(f"## Task\n\n{task}\n")
    return "\n\n".join(parts)


def resolve_sources(sources_flag: str | None, preset: str) -> list[str]:
    if sources_flag:
        items = [s.strip() for s in sources_flag.split(",") if s.strip()]
        for s in items:
            if s not in KNOWN_SOURCES:
                raise ValueError(f"Unknown source: {s}")
        return items
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}")
    return list(PRESETS[preset])
