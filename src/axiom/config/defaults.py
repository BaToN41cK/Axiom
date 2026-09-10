"""Default configuration for Axiom."""

from __future__ import annotations

DEFAULT_PERMISSIONS: dict[str, str] = {
    "filesystem.read": "allow",
    "filesystem.write": "ask",
    "filesystem.delete": "ask",
    "filesystem.search": "allow",
    "terminal.execute": "ask",
    "terminal.process": "ask",
    "git.read": "allow",
    "git.write": "ask",
    "web.search": "allow",
    "web.fetch": "allow",
    "web.download": "ask",
    "agent.spawn": "ask",
    "workspace.outside": "deny",
}

DEFAULT_CONFIG: dict = {
    "model": {
        "provider": "openai_compatible",
        "model": "GPT-OSS-120B",
        "temperature": 0.2,
        "max_tokens": 8192,
        "timeout": 120.0,
    },
    "providers": {
        "openai_compatible": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "AXIOM_API_KEY",
            "headers": {},
        },
        "ollama": {"base_url": "http://localhost:11434"},
    },
    "router": {
        "enabled": True,
        "routes": {
            "FAST": ["Qwen3.6-27B", "GLM-4.5-Flash", "GPT-OSS-20B"],
            "CODING": ["GPT-OSS-120B", "GLM-5.3-Flash", "GPT-OSS-20B"],
            "REASONING": ["MiMo-V2.5", "GPT-OSS-120B", "GLM-5.3-Flash"],
            "REVIEW": ["GPT-OSS-120B", "GLM-5.3-Flash"],
            "ORCHESTRATOR": ["MiMo-V2.5", "GPT-OSS-120B"],
            "FALLBACK": [
                "GLM-5.3-Flash",
                "MiMo-V2.5",
                "Qwen3.8-Flash",
                "Qwen3.6-27B",
                "GPT-OSS-20B",
                "GLM-4.7-Flash",
                "GLM-4.6V-Flash",
                "GLM-4.5-Flash",
            ],
        },
    },
    "agents": {
        "build": {"mode": "BUILD", "max_iterations": 40},
        "plan": {"mode": "PLAN", "max_iterations": 20},
        "review": {"mode": "REVIEW", "max_iterations": 20},
        "auto": {"mode": "AUTO", "max_iterations": 60},
        "orchestrator": {"mode": "ORCHESTRATOR", "max_iterations": 60},
    },
    "orchestrator": {
        "max_agents": 4,
        "max_depth": 2,
        "agent_timeout": 600.0,
    },
    "context": {
        "max_tokens": 100000,
        "compact_threshold": 0.8,
        "keep_recent_messages": 8,
    },
    "verification": {
        "max_repair_cycles": 3,
    },
    "terminal": {
        "default_timeout": 60.0,
        "max_output_chars": 30000,
        "shell": None,  # None => auto (powershell on Windows)
    },
    "web": {
        "timeout": 30.0,
        "max_response_bytes": 5_000_000,
        "cache_ttl": 600,
        "allowed_schemes": ["http", "https"],
    },
    "sessions": {
        "max_sessions": 200,
    },
    "security": {
        "mode": "NORMAL",  # SAFE | NORMAL | AUTONOMOUS
        "blocked_commands": [
            "rm -rf /",
            "rd /s /q c:\\",
            "format",
            "diskpart",
            "shutdown",
            "del /f /s /q c:\\",
        ],
    },
    "permissions": dict(DEFAULT_PERMISSIONS),
    "ui": {
        "theme": "axiom-dark",
        "show_token_stats": True,
    },
}

# Security mode presets: mapping permission name -> state per mode.
SECURITY_MODE_PRESETS: dict[str, dict[str, str]] = {
    "SAFE": {
        "filesystem.read": "allow",
        "filesystem.write": "ask",
        "filesystem.delete": "ask",
        "terminal.execute": "ask",
        "terminal.process": "ask",
        "git.write": "ask",
        "web.fetch": "ask",
        "web.download": "ask",
        "agent.spawn": "ask",
        "workspace.outside": "deny",
    },
    "NORMAL": {
        "filesystem.read": "allow",
        "filesystem.write": "allow",
        "filesystem.delete": "ask",
        "terminal.execute": "ask",
        "terminal.process": "ask",
        "git.write": "ask",
        "web.fetch": "allow",
        "web.download": "ask",
        "agent.spawn": "ask",
        "workspace.outside": "deny",
    },
    "AUTONOMOUS": {
        "filesystem.read": "allow",
        "filesystem.write": "allow",
        "filesystem.delete": "allow",
        "terminal.execute": "allow",
        "terminal.process": "allow",
        "git.write": "allow",
        "web.fetch": "allow",
        "web.download": "allow",
        "agent.spawn": "allow",
        "workspace.outside": "deny",
    },
}
