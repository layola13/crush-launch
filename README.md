# crush-launch

Launcher for [Charm Crush](https://github.com/charmbracelet/crush) that reads a `.env` file, generates a temporary `crush.json`, and runs the locally installed `crush` binary against an OpenAI-compatible endpoint.

**No secrets or private endpoints are hard-coded.** Configure everything via `.env` or environment variables.

---

## Architecture & Implementation Principles (实现原理)

`crush-launch` is a lightweight configuration wrapper around Crush. Crush already supports OpenAI-compatible providers natively, so this launcher does not translate protocols or proxy traffic. Instead, it bridges simple environment configuration into Crush's JSON provider format:

```
+-------------+                 +----------------------+                 +---------------+
|             |  env variables  |                      |  Chat/Provider  |               |
| .env / env  | --------------> | crush-launch Wrapper | --------------> | Upstream LLM  |
|             |                 | (Python subprocess)  |                 | (OpenAI/API)  |
+-------------+                 +----------------------+                 +---------------+
                                           |
                                           v
                                  temporary crush.json
```

### 1. Env Loading

* When you run `crush-launch`, it loads configuration from `.env` files and environment variables.
* Existing environment variables win over values from files.
* It supports project-local config, parent directory config, package config, and user-level config.

### 2. Temporary Crush Config Generation

The launcher writes a temporary `crush.json` and points Crush at its containing directory via `CRUSH_GLOBAL_CONFIG`:

* `providers.<id>.type` defaults to `openai-compat`.
* `providers.<id>.base_url` comes from `CRUSH_LAUNCH_BASE_URL`.
* `providers.<id>.api_key` comes from `CRUSH_LAUNCH_API_KEY`.
* `providers.<id>.models[0].id` comes from `CRUSH_LAUNCH_MODEL`.
* `models.large` and `models.small` are both set to the configured model.

### 3. Crush Subprocess Execution

The main thread runs the local `crush` binary as a subprocess and forwards all CLI arguments unchanged:

```bash
crush-launch --yolo
crush-launch run "reply with hello"
crush-launch --cwd /path/to/project
```

### 4. No Local Proxy

Unlike `grok-launch`, no local web server is started. Crush can call OpenAI-compatible and Anthropic-compatible providers directly from its own provider configuration.

---

## Quick start

### 1. Install (wrapper in ~/.local/bin + config template)

```bash
./install.sh
```

### 2. Edit user config

```bash
$EDITOR ~/.config/crush-launch/.env
```

### 3. Ensure PATH and run

```bash
export PATH="$HOME/.local/bin:$PATH"
crush-launch
crush-launch run "hello"
```

## Configuration

### Required

| Variable | Meaning |
|----------|---------|
| `CRUSH_LAUNCH_BASE_URL` | OpenAI-compatible base, e.g. `https://api.openai.com/v1` |
| `CRUSH_LAUNCH_MODEL` | Real model name sent by Crush, e.g. `gpt-4o` |
| `CRUSH_LAUNCH_API_KEY` | Bearer token |

### Optional

| Variable | Meaning |
|----------|---------|
| `CRUSH_LAUNCH_API_KEYS` | Comma-separated keys. The first key is used. |
| `CRUSH_LAUNCH_PROVIDER_ID` | Provider id written to `crush.json` (default `crush-launch`) |
| `CRUSH_LAUNCH_PROVIDER_NAME` | Provider display name (default `crush-launch`) |
| `CRUSH_LAUNCH_PROVIDER_TYPE` | Crush provider type (default `openai-compat`; use `openai` for direct OpenAI) |
| `CRUSH_LAUNCH_MODEL_NAME` | Display name for the model |
| `CRUSH_LAUNCH_CONTEXT_WINDOW` | Optional model context window metadata |
| `CRUSH_LAUNCH_MAX_TOKENS` | Optional default max output tokens |
| `CRUSH_LAUNCH_REASONING_EFFORT` | Default OpenAI reasoning effort (`low`, `medium`, `high`) |
| `CRUSH_LAUNCH_CAN_REASON` | Set `1` or `true` to mark model as reasoning-capable |
| `CRUSH_LAUNCH_SUPPORTS_IMAGES` | Set `1` or `true` to mark model as image-capable |
| `CRUSH_LAUNCH_EXTRA_HEADERS` | JSON object merged into provider `extra_headers` |
| `CRUSH_LAUNCH_ENV` | Explicit `.env` path |
| `CRUSH_LAUNCH_VERBOSE` | Enable launcher diagnostics (`1` or `true`) |
| `CRUSH_BIN` | Path to `crush` binary (default `crush`) |

### `.env` load priority

1. `CRUSH_LAUNCH_ENV`
2. `./.env` or `./.crush-launch.env` (cwd)
3. Parent directories (up to 6 levels)
4. Package directory `.env`
5. `~/.config/crush-launch/.env`
6. `~/.crush-launch.env`

## Usage (same flags as crush)

```bash
crush-launch
crush-launch --yolo
crush-launch run "reply with hello"
CRUSH_LAUNCH_VERBOSE=true crush-launch models
```
