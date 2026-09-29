import asyncio
import shutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    uvx_cmd = shutil.which("uvx")
    server_params = StdioServerParameters(command=uvx_cmd, args=["--with", "mcp==1.11.0", "awslabs.aws-api-mcp-server"])
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print([t.name for t in tools.tools])

asyncio.run(main())
