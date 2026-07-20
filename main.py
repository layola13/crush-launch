#!/usr/bin/env python3
# Copyright (c) 2026 crush-launch contributors
# For learning and research only; any other use is at your own risk.
"""crush-launch: env-driven launcher for Charm Crush.

Creates a temporary Crush config from .env / environment variables and then
executes the locally installed `crush` binary. Secrets are not hard-coded.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent

_REQUIRED_KEYS = (
    "CRUSH_LAUNCH_BASE_URL",
    "CRUSH_LAUNCH_MODEL",
)

_LOADED_ENV_FILES: list[Path] = []


def _parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if not key:
                continue
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            out[key] = val
    except OSError:
        pass
    return out


def _candidate_env_paths() -> list[Path]:
    paths: list[Path] = []
    explicit = os.environ.get("CRUSH_LAUNCH_ENV")
    if explicit:
        paths.append(Path(explicit).expanduser())

    cwd = Path.cwd()
    paths.append(cwd / ".env")
    paths.append(cwd / ".crush-launch.env")

    parent = cwd.parent
    for _ in range(6):
        if parent == parent.parent:
            break
        paths.append(parent / ".env")
        paths.append(parent / ".crush-launch.env")
        parent = parent.parent

    paths.append(_HERE / ".env")

    xdg = Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser()
    paths.append(xdg / "crush-launch" / ".env")
    paths.append(Path("~/.crush-launch.env").expanduser())

    seen: set[Path] = set()
    uniq: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            uniq.append(resolved)
    return uniq


def load_dotenv_files() -> list[Path]:
    loaded: list[Path] = []
    claimed = set(os.environ.keys())

    for path in _candidate_env_paths():
        if not path.is_file():
            continue
        data = _parse_dotenv(path)
        if not data:
            continue
        for key, value in data.items():
            if key in claimed:
                continue
            os.environ[key] = value
            claimed.add(key)
        loaded.append(path)
    return loaded


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _optional_int(name: str) -> int | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        print(f"warning: {name} must be an integer", file=sys.stderr)
        return None
    return value if value > 0 else None


def load_config() -> dict[str, str]:
    global _LOADED_ENV_FILES
    _LOADED_ENV_FILES = load_dotenv_files()

    missing = [key for key in _REQUIRED_KEYS if not (os.environ.get(key) or "").strip()]
    keys = os.environ.get("CRUSH_LAUNCH_API_KEYS") or os.environ.get("CRUSH_LAUNCH_API_KEY") or ""
    api_keys = [key.strip() for key in keys.split(",") if key.strip()]
    placeholder_keys = {"your-api-key-here", "key1", "key2", "key3", "sk-fake123456789abcdef..."}
    api_keys = [key for key in api_keys if key not in placeholder_keys]
    if not api_keys:
        missing.append("CRUSH_LAUNCH_API_KEY (or CRUSH_LAUNCH_API_KEYS)")

    if missing:
        example = _HERE / ".env.example"
        xdg = Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser()
        user_env = xdg / "crush-launch" / ".env"
        print("error: missing required configuration:", ", ".join(missing), file=sys.stderr)
        print(file=sys.stderr)
        print("Set them in a .env file or environment variables.", file=sys.stderr)
        print("  project:  ./.env   (copy from .env.example)", file=sys.stderr)
        print(f"  user:     {user_env}", file=sys.stderr)
        print(f"  template: {example}", file=sys.stderr)
        if _LOADED_ENV_FILES:
            print(file=sys.stderr)
            print("loaded env files (still missing keys):", file=sys.stderr)
            for path in _LOADED_ENV_FILES:
                print(f"  - {path}", file=sys.stderr)
        sys.exit(2)

    return {
        "base_url": os.environ["CRUSH_LAUNCH_BASE_URL"].strip().rstrip("/"),
        "model": os.environ["CRUSH_LAUNCH_MODEL"].strip(),
        "api_key": api_keys[0],
        "bin": (os.environ.get("CRUSH_BIN") or "crush").strip(),
        "provider": (os.environ.get("CRUSH_LAUNCH_PROVIDER_ID") or "crush-launch").strip(),
        "provider_name": (os.environ.get("CRUSH_LAUNCH_PROVIDER_NAME") or "crush-launch").strip(),
        "provider_type": (os.environ.get("CRUSH_LAUNCH_PROVIDER_TYPE") or "openai-compat").strip(),
    }


def build_crush_config(cfg: dict[str, str]) -> dict[str, Any]:
    provider = cfg["provider"]
    model = cfg["model"]
    max_tokens = _optional_int("CRUSH_LAUNCH_MAX_TOKENS")
    context_window = _optional_int("CRUSH_LAUNCH_CONTEXT_WINDOW")

    model_config: dict[str, Any] = {
        "id": model,
        "name": os.environ.get("CRUSH_LAUNCH_MODEL_NAME") or model,
    }
    if max_tokens:
        model_config["default_max_tokens"] = max_tokens
    if context_window:
        model_config["context_window"] = context_window
    if _truthy("CRUSH_LAUNCH_CAN_REASON"):
        model_config["can_reason"] = True
    if _truthy("CRUSH_LAUNCH_SUPPORTS_IMAGES"):
        model_config["supports_images"] = True

    selected_model: dict[str, Any] = {"provider": provider, "model": model}
    if max_tokens:
        selected_model["max_tokens"] = max_tokens
    reasoning = (os.environ.get("CRUSH_LAUNCH_REASONING_EFFORT") or "").strip().lower()
    if reasoning:
        selected_model["reasoning_effort"] = reasoning

    config: dict[str, Any] = {
        "$schema": "https://charm.land/crush.json",
        "providers": {
            provider: {
                "id": provider,
                "name": cfg["provider_name"],
                "type": cfg["provider_type"],
                "base_url": cfg["base_url"],
                "api_key": cfg["api_key"],
                "discover_models": False,
                "models": [model_config],
            }
        },
        "models": {
            "large": selected_model,
            "small": selected_model,
        },
        "options": {
            "disable_default_providers": True,
            "disable_provider_auto_update": True,
        },
    }

    if _truthy("CRUSH_LAUNCH_VERBOSE"):
        config["options"]["debug"] = True

    extra_headers_raw = (os.environ.get("CRUSH_LAUNCH_EXTRA_HEADERS") or "").strip()
    if extra_headers_raw:
        try:
            headers = json.loads(extra_headers_raw)
            if isinstance(headers, dict):
                config["providers"][provider]["extra_headers"] = headers
            else:
                print("warning: CRUSH_LAUNCH_EXTRA_HEADERS must be a JSON object", file=sys.stderr)
        except json.JSONDecodeError as exc:
            print(f"warning: invalid CRUSH_LAUNCH_EXTRA_HEADERS JSON: {exc}", file=sys.stderr)

    return config


def _passthrough_without_config(args: list[str]) -> bool:
    if not args:
        return False
    first = args[0]
    if first in ("-h", "--help", "-v", "--version", "help", "completion", "dirs"):
        return True
    return len(args) > 1 and args[1] in ("-h", "--help")


def _crush_bin_from_env() -> str:
    return (os.environ.get("CRUSH_BIN") or "crush").strip()


def _run_crush(crush_bin: str, args: list[str], env: dict[str, str]) -> None:
    if not shutil.which(crush_bin):
        print(f"error: cannot find crush binary ({crush_bin})", file=sys.stderr)
        sys.exit(127)
    try:
        res = subprocess.run([crush_bin, *args], env=env)
        sys.exit(res.returncode)
    except KeyboardInterrupt:
        sys.exit(130)


def main() -> None:
    args = sys.argv[1:]
    if _passthrough_without_config(args):
        _run_crush(_crush_bin_from_env(), args, os.environ.copy())

    cfg = load_config()
    crush_bin = cfg["bin"]
    env = os.environ.copy()

    with tempfile.TemporaryDirectory(prefix="crush-launch-") as temp_dir:
        config_path = Path(temp_dir) / "crush.json"
        config_path.write_text(json.dumps(build_crush_config(cfg), indent=2), encoding="utf-8")
        env["CRUSH_GLOBAL_CONFIG"] = temp_dir

        if _truthy("CRUSH_LAUNCH_VERBOSE"):
            env_note = ", ".join(str(path) for path in _LOADED_ENV_FILES) if _LOADED_ENV_FILES else "(none)"
            print(
                f"[crush-launch] config={config_path} upstream={cfg['base_url']} "
                f"provider={cfg['provider']} model={cfg['model']}\n"
                f"[crush-launch] env files: {env_note}",
                file=sys.stderr,
            )

        _run_crush(crush_bin, args, env)


if __name__ == "__main__":
    main()
