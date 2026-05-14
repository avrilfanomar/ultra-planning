from __future__ import annotations

"""Pure functions that build agent-specific configuration from an ultra-plan bundle.

No subprocess or side effects — callers are responsible for writing the returned
data to disk.
"""


def build_claude_settings(bundle: dict) -> dict:
    """Build a Claude settings.json body from a bundle.

    Returns a dict with ``permissions`` and/or ``mcpServers`` keys populated
    from the bundle. Only non-empty top-level keys are included.

    MCP entries are emitted only when the tool object carries a usable
    ``command`` or ``url`` field. When neither is present we skip the entry
    and rely on the user having registered the server via ``claude mcp add``.
    """
    result: dict = {}

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

    return result


def build_opencode_config(bundle: dict) -> dict:
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
    """
    result: dict = {"$schema": "https://opencode.ai/config.json"}

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
        for entry in allow_list:
            if _matches_key(entry, broad_key):
                perm_block[broad_key] = "allow"
                break

    # Deny overrides: any matching deny entry forces "ask"
    for broad_key in ("write", "edit", "bash"):
        for entry in deny_list:
            if _matches_key(entry, broad_key):
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

    return result


def build_skills_context(bundle: dict) -> str:
    """Return a markdown block listing each enabled skill.

    Returns an empty string when no skills are present or all are disabled.
    Otherwise returns a ``# Skills`` section with one bullet per skill.
    """
    skills = bundle.get("skills", [])
    enabled = [s for s in skills if s.get("enabled", True) is not False]
    if not enabled:
        return ""

    lines = ["# Skills\n"]
    for skill in enabled:
        name = skill.get("name", "")
        source_url = skill.get("source_url", "")
        rationale = skill.get("rationale", "")
        lines.append(f"- **{name}** ({source_url}): {rationale}")
    return "\n".join(lines)
