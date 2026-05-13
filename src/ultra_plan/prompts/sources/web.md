## Source: web

General web fallback for items the other sources miss:

- Run a WebSearch with the task plus terms like `library`, `cli`, `docs`, `tutorial`.
- Use WebFetch on the top results to confirm they exist and are maintained.
- Use this source for niche libraries, vendor docs, and SaaS API references.
- Set `kind` = `lib` or `cli` as appropriate; never use `mcp` here (that belongs to the mcp source).
