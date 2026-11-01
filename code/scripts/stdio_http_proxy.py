"""Expose inspected official stdio MCP servers through a local HTTP multiplexer.

This adapter does not implement benchmark tool bodies. It forwards calls to the
published server processes. A reset restarts those processes to clear memory.
Only bind to localhost. Config is generated from inspected deployment metadata.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness_adapt.description_overlay import apply_official_description_overlay, select_official_description_layers


class Multiplexer:
    def __init__(self, config):
        self.config = config
        self.stack = None
        self.sessions = {}
        self.tools = []
        self.routes = {}
        self.lock = asyncio.Lock()
        self.generation = 0
        self.control = asyncio.Queue()
        self.ready = None
        files = [Path(p) for p in config.get('official_evolution_files', [])]
        all_layers = [json.loads(p.read_text()) for p in files]
        self.layers, self.overlay_provenance = select_official_description_layers(all_layers, config.get('version', 'early'))
        self.overlay_provenance['raw_source_files'] = [
            {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
        self.overlay_audits = []

    async def owner(self):
        """Open and close AnyIO subprocess scopes in the same owner task."""
        try:
            await self.start()
            self.ready.set_result(True)
            while True:
                future = await self.control.get()
                if future is None:
                    break
                try:
                    await self.start()
                    future.set_result(True)
                except Exception as exc:
                    future.set_exception(exc)
        except BaseException as exc:
            if self.ready and not self.ready.done():
                self.ready.set_exception(exc)
            raise
        finally:
            await self.close()

    async def request_reset(self):
        future = asyncio.get_running_loop().create_future()
        await self.control.put(future)
        await future

    async def close(self):
        if self.stack:
            await self.stack.aclose()
        self.stack = None
        self.sessions, self.tools, self.routes = {}, [], {}
        self.overlay_audits = []

    async def start(self):
        await self.close()
        self.stack = AsyncExitStack()
        await self.stack.__aenter__()
        try:
            for name, entry in self.config['servers'].items():
                environment = dict(os.environ)
                environment.update(entry.get('env', {}))
                params = StdioServerParameters(command=entry['command'], args=entry['args'],
                                               cwd=entry['cwd'], env=environment)
                read, write = await self.stack.enter_async_context(stdio_client(params))
                session = await self.stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), timeout=45)
                self.sessions[name] = session
                page = await session.list_tools()
                tools = list(page.tools)
                while page.nextCursor:
                    page = await session.list_tools(cursor=page.nextCursor)
                    tools.extend(page.tools)
                for tool in tools:
                    native = tool.name
                    exposed = name + '_1mcp_' + native
                    if exposed in self.routes:
                        raise RuntimeError('Duplicate qualified tool identity')
                    data = tool.model_dump(exclude_none=True)
                    data, audit = apply_official_description_overlay(
                        data, entry.get('official_server_id', name), self.layers)
                    if audit['description_edit_count']:
                        self.overlay_audits.append(audit)
                    data['name'] = exposed
                    # Values must originate from the inspected official mutation
                    # metadata and be recorded in deployment provenance.
                    descriptions = entry.get('official_description_overrides', {})
                    if native in descriptions:
                        data['description'] = descriptions[native]
                    self.tools.append(types.Tool(**data))
                    self.routes[exposed] = (name, native)
            self.tools.sort(key=lambda t: t.name)
            self.generation += 1
        except BaseException:
            await self.close()
            raise

    async def call(self, name, arguments):
        if name not in self.routes:
            return types.CallToolResult(content=[types.TextContent(type='text', text='Unknown tool identity: ' + name)], isError=True)
        server, native = self.routes[name]
        return await self.sessions[server].call_tool(native, arguments=arguments)


def build_app(config):
    mux = Multiplexer(config)
    server = Server('mcpevol-inspected-stdio-proxy')

    @server.list_tools()
    async def list_tools():
        return mux.tools

    # Preserve native server validation. The proxy should not substitute a local
    # schema checker or rewrite arguments, including stale harness arguments.
    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        return await mux.call(name, arguments)

    manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)

    async def http(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    async def health(request):
        return JSONResponse({'status': 'ready', 'tools': len(mux.tools),
                             'servers': list(mux.sessions), 'generation': mux.generation})

    async def provenance(request):
        return JSONResponse({'overlay_provenance': mux.overlay_provenance,
                             'description_audits': mux.overlay_audits,
                             'server_entries': mux.config['servers']})

    async def reset(request):
        if request.client.host not in ('127.0.0.1', '::1'):
            return JSONResponse({'error': 'localhost only'}, status_code=403)
        async with mux.lock:
            await mux.request_reset()
        return JSONResponse({'status': 'reset', 'generation': mux.generation})

    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            mux.ready = asyncio.get_running_loop().create_future()
            owner = asyncio.create_task(mux.owner())
            await mux.ready
            try:
                yield
            finally:
                await mux.control.put(None)
                await owner

    return Starlette(routes=[Route('/health', health), Route('/provenance', provenance), Route('/reset', reset, methods=['POST']),
                             Mount('/mcp', app=http)], lifespan=lifespan)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    uvicorn.run(build_app(cfg), host='127.0.0.1', port=args.port, log_level='warning')
