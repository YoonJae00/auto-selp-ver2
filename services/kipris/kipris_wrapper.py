from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import os

app = FastAPI()

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict

# This will be injected into the container where mcp_kipris is installed.
@app.post("/tools/call")
async def call_tool(request: ToolCallRequest):
    try:
        from mcp_kipris.server import get_tool_handler
    except ImportError:
        # Fallback to the kipris path
        import mcp_kipris.kipris.tools
        from mcp_kipris.server import get_tool_handler

    tool_handler = get_tool_handler(request.name)
    if not tool_handler:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    try:
        try:
            result = await tool_handler.run_tool_async(request.arguments)
        except (AttributeError, NotImplementedError):
            result = tool_handler.run_tool(request.arguments)
        
        # result is a list of TextContent / ImageContent / EmbeddedResource
        # Convert to the format expected by KiprisClient
        def content_to_dict(c):
            if hasattr(c, "text"): return {"type": "text", "text": c.text}
            if hasattr(c, "url"): return {"type": "image", "url": c.url}
            return {"type": "unknown"}
            
        return {"content": [content_to_dict(c) for c in result]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
