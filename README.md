# Operations Dashboard MCP

Model Context Protocol (MCP) server and LangGraph agent for Amazon operations analytics. The project exposes unified resources and tool interfaces, supports MCP clients, and can also be exercised locally for debugging.

## Environment Setup

1. Install Python 3.10 or newer.
2. Create and activate a virtual environment:
   `ash
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   `
3. If you previously installed older versions of LangChain packages, upgrade them to ensure GPT-5 compatibility:
   `ash
   python -m pip install --upgrade langchain langchain-openai
   `
4. Optional environment variables:

| Variable | Description |
| --- | --- |
| OPENAI_API_KEY | Required to generate insights via OpenAI; without it only placeholder text is returned. |
| AMAZON_ACCESS_KEY / AMAZON_SECRET_KEY / AMAZON_ASSOCIATE_TAG / AMAZON_MARKETPLACE | Amazon PAAPI credentials required by the mazon_bestseller_search tool. |

## Running the MCP Server

`ash
# stdio transport (default)
python -m operations_dashboard.mcp_server

# Streamable HTTP transport (for MCP Inspector, etc.)
python -m operations_dashboard.mcp_server streamable-http --host 127.0.0.1 --port 8000
`

Optional environment variables:

- USE_MCP_BRIDGE: set to 1/true/yes to make the LangGraph agent call tools via MCP.
- MCP_BRIDGE_COMMAND / MCP_BRIDGE_ARGS / MCP_BRIDGE_ENV: customize how the MCP child process is launched and which environment variables are passed to it.

## Self-check & Debugging Scripts

- python operations_dashboard/test.py – sequentially verifies stdio transport, tool invocations, the LangGraph agent loop, and a temporary HTTP listener. If you only care about stdio/tools, comment out the HTTP section near the end of the script.
- python operations_dashboard/call_insights_tool.py – minimal script that calls both etch_dashboard_data and generate_dashboard_insights via MCP and prints the structured responses.
- python operations_dashboard/verify_openai_key.py – validates whether OPENAI_API_KEY works (a proxy may be required on restricted networks).

## LangGraph Agent

- gent.py builds a LangGraph-based operations consultant agent. It can run locally or forward calls through the MCP bridge.
- The bridge launches python -m operations_dashboard.mcp_server by default; adjust MCP_BRIDGE_COMMAND, MCP_BRIDGE_ARGS, or MCP_BRIDGE_ENV if you need a different command or environment.
- When USE_MCP_BRIDGE is disabled, the agent directly invokes the local service implementations.

## Project Layout

`
operations_dashboard/
├── agent.py
├── call_insights_tool.py
├── config.py
├── mcp_bridge.py
├── mcp_server.py
├── services.py
├── test.py
├── verify_openai_key.py
├── data_sources/
├── metrics/
├── reporting/
├── storage/
└── utils/
`

## Troubleshooting

1. **generate_dashboard_insights reports missing OPENAI_API_KEY** – check the variable in the current terminal (echo  on PowerShell or python -c "import os; print(os.getenv('OPENAI_API_KEY'))"). If you use the MCP bridge, ensure MCP_BRIDGE_ENV also carries the key.
2. **generate_dashboard_insights raises “unhandled errors in a TaskGroup”** – upgrade LangChain packages: python -m pip install --upgrade langchain langchain-openai. Older versions do not fully support the GPT-5 API and surface this aggregated error inside MCP.
3. **mazon_bestseller_search warns about missing credentials** – provide Amazon PAAPI credentials or ignore the warning when the tool is not needed.
4. **HTTP connectivity check times out** – ensure uvicorn is installed, the port is free, and retry with another port (for example --port 8765).

## Version Notes

- Starting in December 2024, running GPT-5 models requires langchain>=0.3.12 and langchain-openai>=0.3.3. Older versions surface the TaskGroup aggregate error shown above.

[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logoColor=ffffff)](https://zread.ai/gaochao0609/E-commerce-Assistant-agent)
