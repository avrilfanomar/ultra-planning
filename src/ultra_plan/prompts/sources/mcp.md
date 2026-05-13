## Source: mcp

Query MCP registries for servers relevant to the task:

- Fetch `https://github.com/modelcontextprotocol/servers` README for the official server list.
- Check community catalogs: `https://mcp.so`, `https://glama.ai/mcp`.
- For each matching server, record install command (typically `npx -y @modelcontextprotocol/server-<name>` or vendor-specific) and required auth (env vars, OAuth, etc.).
- Set `kind` = `mcp`.
