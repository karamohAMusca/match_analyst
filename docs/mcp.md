# Use it from Claude Desktop and other MCP hosts


`mcp_server.py` gives the knowledge base to any MCP host: Claude Desktop, Claude Code, VS Code +
Copilot (Agent mode), Cursor, the MCP Inspector, or Python code with `mcp.Client`. The host's own
model reads the cards; the app's agent is not involved, so the measured results (see
[evaluation](evaluation.md)) do not change. It is built with the reference MCP SDK (`mcp` ≥ 2, spec 2026-07-28, stateless):
datapizza-ai 0.1.0 has no MCP server, and its MCP client speaks only the older protocol.

| Primitive | Name | What it does | Needs |
|---|---|---|---|
| tool | `search_cards(query, categories)` | the agent's hybrid search: up to 5 cards, each headed by its `[document_id]` | Qdrant; the key for a new query |
| tool | `read_card(document_id)` | one whole card | nothing |
| tool | `list_cards(category)` | the catalogue: id, title, category and date of each card | nothing |
| resource | `card://{document_id}` | one card by URI; the 31 cards are listed | nothing |
| prompt | `prepare_match(team, opponent)` | the recipe: search game situations and real matches, cite every sentence, "Non lo so" when the cards do not cover it | nothing |

The tools are read-only (they declare it to the host) and look cards up by id, never by path.
Catalogue and cards are read from `corpus/`, the same text the agent reads, so they work with
nothing running. `search_cards` needs Qdrant (`docker compose up -d`) and reads the key from the
project's `.env`: no key goes into a host's configuration. A server started before Qdrant works as
soon as Qdrant is up. The log goes to `logs/match_analyst.log`, and with Phoenix running every
search is also a trace.

A host starts the server itself, with absolute paths. Below, `<PYTHON>` is the Python of the
environment where `requirements.txt` is installed (with the setup of
[Getting started](../README.md#quick-start): `<PROJECT>\.venv\Scripts\python.exe` on Windows,
`<PROJECT>/.venv/bin/python` on macOS and Linux) and `<PROJECT>` is the absolute path of this folder.

- **Claude Desktop**: Settings → Developer → Edit Config, add the server to
  `claude_desktop_config.json`, then restart Claude Desktop. In JSON, Windows paths take double
  backslashes (`C:\\Users\\...`) or forward slashes.
  ```json
  {
    "mcpServers": {
      "match-analyst": {
        "command": "<PYTHON>",
        "args": ["<PROJECT>/mcp_server.py"]
      }
    }
  }
  ```
- **Claude Code**: `claude mcp add match-analyst -- <PYTHON> <PROJECT>/mcp_server.py`
- **VS Code + Copilot**: in `.vscode/mcp.json`,
  `{"servers": {"match-analyst": {"type": "stdio", "command": "<PYTHON>", "args": ["<PROJECT>/mcp_server.py"]}}}`,
  then Copilot Chat in Agent mode. **Cursor**: `.cursor/mcp.json` with the same block as Claude Desktop.
- **MCP Inspector** (needs Node.js), to try the tools by hand:
  `npx @modelcontextprotocol/inspector <PYTHON> <PROJECT>/mcp_server.py`
- **Over HTTP** (Streamable HTTP, stateless): `MCP_HTTP=1 python mcp_server.py` (PowerShell:
  `$env:MCP_HTTP=1; python mcp_server.py`), then connect to `http://localhost:8000/mcp`.
