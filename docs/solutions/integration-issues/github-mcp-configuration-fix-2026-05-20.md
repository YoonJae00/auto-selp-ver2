---
title: Fixing GitHub MCP OAuth and Config Parsing Errors
date: 2026-05-20
category: docs/solutions/integration-issues/
module: mcp-integration
problem_type: integration_issue
component: tooling
symptoms:
  - "Unexpected end of JSON input error for ~/.gemini/config/mcp_config.json"
  - "OAuth setup failed for github: OAuth client ID required warning"
root_cause: config_error
resolution_type: config_change
severity: medium
tags:
  - github-mcp
  - mcp-config
  - oauth-setup
  - token-auth
---

# Fixing GitHub MCP OAuth and Config Parsing Errors

## Problem
The GitHub MCP (Model Context Protocol) integration was failing to initialize correctly due to a corrupted 0-byte configuration file (`mcp_config.json`) and missing authentication credentials, causing the system to fallback to an invalid OAuth flow.

## Symptoms
- System log throws parsing error: `Failed to load JSON config file /home/yoonjae/.gemini/config/mcp_config.json: unexpected end of JSON input`
- Warning in CLI log: `OAuth setup failed for github: OAuth client ID required: server does not support dynamic client registration`

## What Didn't Work
- Reading `/home/yoonjae/.gemini/config/mcp_config.json` directly initially failed because it was completely empty (0 bytes), making it invalid JSON.
- Relying on automated environment variable extraction without custom headers in the plugin definition failed because the remote HTTP MCP server (`https://api.githubcopilot.com/mcp/`) requires a Bearer REDACTED in the `Authorization` header, and defaults to standard OAuth registration when missing.

## Solution
1. **Fix `mcp_config.json` Empty File Error**: Populated `/home/yoonjae/.gemini/config/mcp_config.json` with a valid empty JSON object (`{}`) to resolve the JSON parsing error in the CLI discovery:
   ```json
   {}
   ```
2. **Configure HTTP Authentication for GitHub MCP**: Added the correct authentication details with a `Bearer` token to `/home/yoonjae/.gemini/settings.json` under `mcpServers` using the valid personal access token from `GITHUB_MCP_PAT`:
   ```json
   "github": {
     "httpUrl": "https://api.githubcopilot.com/mcp/",
     "headers": {
       "Authorization": "Bearer REDACTED",
       "Accept": "application/json, text/event-stream"
     }
   }
   ```
3. **Synchronize Plugin Config**: Updated `/home/yoonjae/.gemini/antigravity-cli/plugins/github/mcp_config.json` to include the identical authentication header.

## Why This Works
Populating `/home/yoonjae/.gemini/config/mcp_config.json` with `{}` satisfies the JSON parser's requirement of a valid JSON object. Explicitly defining the `github` MCP server with standard `Authorization` and `Accept` headers in both user `settings.json` and the plugin's `mcp_config.json` tells the MCP client to use the `Bearer` token instead of triggering the default OAuth flow, successfully connecting to the GitHub Copilot remote MCP.

## Prevention
- Never leave configuration files completely empty (0 bytes); write at least `{}`.
- When utilizing remote HTTP MCP servers, ensure that the headers configuration explicitly contains the `Authorization` header rather than leaving them empty, which prevents the client from trying unauthorized OAuth flows.
