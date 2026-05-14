# Sample Bundle for Testing Execute Feature

This is a sample bundle that demonstrates the structure and content of an ultra-plan bundle.

## Task

Create a simple Python CLI calculator

## How to Execute

From the repository root:

```bash
# Execute with Claude (interactive)
ultra-plan execute examples/sample-bundle/

# Execute with Claude (headless)
ultra-plan execute examples/sample-bundle/ --headless

# Execute with opencode
ultra-plan execute examples/sample-bundle/ --agent opencode

# Execute in a specific directory
ultra-plan execute examples/sample-bundle/ --cwd /tmp/calculator-project
```

## What This Bundle Contains

- **Task**: Create a simple Python CLI calculator
- **Expected Outcome**: A working calculator with tests and documentation
- **Skills**: python-skill from Anthropic
- **Tools**: Built-in tools (Bash, Write, Edit, Read)
- **Permissions**: Allow Python and pytest, deny dangerous operations
- **Plan**: 5-step implementation plan
- **Prompt Recommendations**: Best practices for Python development

## Try It

1. Navigate to the repository root
2. Run: `ultra-plan execute examples/sample-bundle/`
3. Watch the agent implement the calculator
4. Check the results in the working directory

## Modifying the Bundle

You can edit `bundle.json` to:
- Change the task
- Enable/disable tools
- Adjust permissions
- Modify the plan or prompt recommendations
- Add more tools (e.g., MCP servers)

Then re-execute to see different behavior.
