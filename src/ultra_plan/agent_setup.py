from __future__ import annotations

from pathlib import Path

"""Pure functions that build agent-specific configuration from an ultra-plan bundle.

No subprocess or side effects — callers are responsible for writing the returned
data to disk.
"""


def build_claude_settings(bundle: dict) -> tuple[dict, list[str]]:
    """Build a Claude settings.json body from a bundle.

    Returns a ``(settings, skipped)`` tuple where ``settings`` is a dict with
    ``permissions`` and/or ``mcpServers`` keys populated from the bundle (only
    non-empty top-level keys are included), and ``skipped`` is the list of
    enabled MCP tool names that were omitted because their bundle entry lacks
    transport details (no ``command`` and no ``url``). Callers should surface
    the skipped list as a warning so users know which MCP tools will not be
    functional at execute time.
    """
    result: dict = {}
    skipped: list[str] = []

    # --- permissions ---
    permissions = bundle.get("permissions", {})
    if permissions:
        perm_block: dict = {}
        for key in ("allow", "deny", "ask"):
            values = permissions.get(key, [])
            if values:
                perm_block[key] = list(values)
        if perm_block:
            result["permissions"] = perm_block

    # --- mcpServers ---
    mcp_servers: dict = {}
    for tool in bundle.get("tools", []):
        if tool.get("enabled", True) is False:
            continue
        if tool.get("kind") != "mcp":
            continue
        name = tool.get("name", "")
        if not name:
            continue
        # Only emit when transport details are present in the bundle object.
        # The bundle schema does not require command/url, so we guard here.
        command = tool.get("command")
        url = tool.get("url")
        if command is None and url is None:
            # No transport details — skip; user must register via claude mcp add
            skipped.append(name)
            continue
        entry: dict = {}
        if command is not None:
            # command may be a string or list; Claude expects a list for args
            if isinstance(command, list):
                entry["command"] = command[0]
                if len(command) > 1:
                    entry["args"] = command[1:]
            else:
                entry["command"] = command
        if url is not None:
            entry["url"] = url
        if entry:
            mcp_servers[name] = entry

    if mcp_servers:
        result["mcpServers"] = mcp_servers

    return result, skipped


def build_opencode_config(bundle: dict) -> tuple[dict, list[str]]:
    """Build an opencode.json body from a bundle.

    Always includes ``$schema``. Other keys are only included when they
    carry meaningful content so the file stays minimal.

    Permission mapping logic
    ------------------------
    Bundle ``permissions.allow`` entries are inspected for patterns:
    - Exact ``"Write"`` → ``permission.write = "allow"``
    - Exact ``"Edit"`` → ``permission.edit = "allow"``
    - Starts with ``"Bash"`` → ``permission.bash = "allow"``

    Bundle ``permissions.deny`` entries with matching patterns override the
    value to ``"ask"`` (i.e. deny takes precedence over allow). A deny entry
    whose pattern was never in allow still produces a ``"ask"`` value — the
    intent is to be conservative when the user explicitly denied something.

    Returns a ``(config, skipped)`` tuple. ``skipped`` is the list of enabled
    MCP tool names whose bundle entry lacked transport (``command``/``url``)
    and were therefore omitted.
    """
    result: dict = {"$schema": "https://opencode.ai/config.json"}
    skipped: list[str] = []

    # --- permission ---
    permissions = bundle.get("permissions", {})
    allow_list: list[str] = permissions.get("allow", [])
    deny_list: list[str] = permissions.get("deny", [])

    perm_block: dict = {}

    def _matches_key(entry: str, key: str) -> bool:
        """Return True when *entry* pattern maps to the given broad key."""
        if key == "write":
            return entry == "Write"
        if key == "edit":
            return entry == "Edit"
        if key == "bash":
            return entry == "Bash" or entry.startswith("Bash(")
        return False

    # Build initial values from allow list
    for broad_key in ("write", "edit", "bash"):
        for allow_entry in allow_list:
            if _matches_key(allow_entry, broad_key):
                perm_block[broad_key] = "allow"
                break

    # Deny overrides: any matching deny entry forces "ask"
    for broad_key in ("write", "edit", "bash"):
        for deny_entry in deny_list:
            if _matches_key(deny_entry, broad_key):
                perm_block[broad_key] = "ask"
                break

    if perm_block:
        result["permission"] = perm_block

    # --- mcp ---
    mcp_block: dict = {}
    for tool in bundle.get("tools", []):
        if tool.get("enabled", True) is False:
            continue
        if tool.get("kind") != "mcp":
            continue
        name = tool.get("name", "")
        if not name:
            continue
        command = tool.get("command")
        url = tool.get("url")
        if command is None and url is None:
            # No transport details — skip
            skipped.append(name)
            continue
        entry: dict = {"enabled": True}
        if command is not None:
            entry["type"] = "local"
            # Normalise to list for opencode's command array
            entry["command"] = list(command) if isinstance(command, list) else [command]
        elif url is not None:
            entry["type"] = "remote"
            entry["url"] = url
        mcp_block[name] = entry

    if mcp_block:
        result["mcp"] = mcp_block

    return result, skipped


def build_skills_context(
    bundle: dict,
    bundle_dir: Path | None = None,
) -> tuple[str, list[str]]:
    """Return a markdown block inlining each enabled skill's content.

    For every enabled skill, attempt to read ``bundle_dir/skills/<name>/SKILL.md``
    (plus any sibling ``*.md`` files in the same directory) and inline the
    content under a ``## <name>`` subsection so the executing agent receives
    the skill body as already-loaded context — no runtime ``Skill()`` calls or
    fetch decisions required.

    When ``bundle_dir`` is ``None`` or a skill's content cannot be resolved on
    disk, the skill falls back to a single bullet line listing its name, URL,
    and rationale, and its name is appended to the returned ``missing`` list
    so callers can surface a warning.

    Returns a ``(context, missing)`` tuple. ``context`` is the empty string
    when no skills are enabled.
    """
    skills = bundle.get("skills", [])
    enabled = [s for s in skills if s.get("enabled", True) is not False]
    missing: list[str] = []
    if not enabled:
        return "", missing

    skills_root: Path | None = None
    if bundle_dir is not None:
        skills_root = Path(bundle_dir) / "skills"

    lines = [
        "# Skills (loaded statically)\n",
        "The following skill content has been inlined into your context. "
        "Treat it as already loaded — do not invoke the Skill tool to fetch "
        "these, and do not skip them based on relevance heuristics.\n",
    ]

    for skill in enabled:
        name = skill.get("name", "")
        source_url = skill.get("source_url", "")
        rationale = skill.get("rationale", "")

        skill_dir = skills_root / name if skills_root is not None else None
        md_files: list[Path] = []
        if skill_dir is not None and skill_dir.is_dir():
            primary = skill_dir / "SKILL.md"
            if primary.is_file():
                md_files.append(primary)
            for extra in sorted(skill_dir.glob("*.md")):
                if extra.name == "SKILL.md":
                    continue
                md_files.append(extra)

        if md_files:
            lines.append(f"## {name}")
            lines.append(f"_Source: {source_url}_")
            if rationale:
                lines.append(f"_Rationale: {rationale}_")
            for md in md_files:
                try:
                    body = md.read_text()
                except OSError:
                    missing.append(name)
                    continue
                lines.append(f"\n<!-- {md.name} -->")
                lines.append(body.rstrip())
            lines.append("")
        else:
            missing.append(name)
            lines.append(
                f"- **{name}** ({source_url}): {rationale} "
                f"_(skill content not found at skills/{name}/SKILL.md — agent "
                f"will not have the skill body available)_"
            )

    return "\n".join(lines), missing
