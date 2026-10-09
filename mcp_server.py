"""Match Analyst as an MCP server (src/mcp_server/server.py): the card corpus for any MCP host.

    python mcp_server.py               # stdio: what Claude Desktop, Claude Code, VS Code, Cursor and the MCP Inspector launch
    MCP_HTTP=1 python mcp_server.py    # Streamable HTTP, stateless: http://localhost:8000/mcp

Hosts launch it with absolute paths: the python of the project's virtual environment and this
file (see the README, "Use it from Claude Desktop and other MCP hosts"). search_cards needs Qdrant
running and OPENAI_API_KEY in .env; list_cards, read_card and the card:// resources need nothing.
"""

from src.mcp_server.server import main

if __name__ == "__main__":
    main()
