"""PreToolUse guard for the "绝对禁止" list in AGENTS.md.

Reads the hook payload on stdin. Exit 2 blocks the tool call and the stderr
text is shown to the model; exit 0 lets it through.
"""

import json
import re
import sys
from pathlib import PurePath

# A whole token that names a .env file, e.g. ".env", "backend/.env", ".env.local".
ENV_TOKEN = re.compile(r"""(?:^|[\s/\\'"=:(])(\.env(?:\.[\w-]+)*)(?![\w.-])""")

DESTRUCTIVE_DOCKER = [
    (re.compile(r"\bdown\b[^|;&]*\s(-v|--volumes)\b"), "docker compose down -v"),
    (re.compile(r"\bdocker\s+(system|volume|container|image|network|builder)\s+prune\b"), "docker ... prune"),
    (re.compile(r"\bdocker\s+volume\s+rm\b"), "docker volume rm"),
]
DELETE_ARTIFACTS = re.compile(r"\b(rm|rmdir|del|Remove-Item)\b[^|;&]*\bartifacts\b", re.IGNORECASE)
CONTAINER_OP = re.compile(
    r"\bdocker\s+(?:container\s+)?(?:stop|rm|kill|restart|start|pause|unpause|update|exec)\b([^|;&]*)"
)
# Flags of those subcommands that take a separate value ("-u root", "--time 5").
FLAGS_WITH_VALUE = {"-u", "--user", "-w", "--workdir", "-e", "--env", "--env-file", "-t", "--time", "-s", "--signal"}


def first_container(args: str) -> str | None:
    tokens = args.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-"):
            return token.strip("'\"")
        index += 2 if token in FLAGS_WITH_VALUE else 1
    return None


def is_secret_env(name: str) -> bool:
    return name.startswith(".env") and not name.endswith(".example")


def check_path(path: str | None) -> str | None:
    if path and is_secret_env(PurePath(path.replace("\\", "/")).name):
        return f"AGENTS.md 禁止读取或改写 .env（{path}）。需要配置说明时读 .env.example，只写键名。"
    return None


def check_command(command: str) -> str | None:
    for match in ENV_TOKEN.finditer(command):
        if is_secret_env(match.group(1)):
            return "AGENTS.md 禁止打印或操作 .env。需要配置说明时读 .env.example，只写键名，值写 ***。"
    for pattern, label in DESTRUCTIVE_DOCKER:
        if pattern.search(command):
            return f"AGENTS.md 绝对禁止 {label}：会删除数据卷或其他项目的资源。"
    if DELETE_ARTIFACTS.search(command):
        return "AGENTS.md 绝对禁止删除 artifacts/。"
    for match in CONTAINER_OP.finditer(command):
        name = first_container(match.group(1))
        if name and not name.startswith("agent-"):
            return f"AGENTS.md 禁止操作名称不以 agent- 开头的容器（{name}）。请用 agent- 开头的容器名。"
    return None


def main() -> int:
    # The project path contains Chinese characters; the Windows console code
    # page would mis-decode the UTF-8 payload and garble the reason text.
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    sys.stderr.reconfigure(encoding="utf-8")
    tool = payload.get("tool_name", "")
    data = payload.get("tool_input") or {}
    if tool in {"Read", "Edit", "Write", "NotebookEdit"}:
        reason = check_path(data.get("file_path") or data.get("notebook_path"))
    elif tool == "Grep":
        reason = check_path(data.get("path"))
    elif tool in {"Bash", "PowerShell"}:
        reason = check_command(data.get("command", ""))
    else:
        reason = None
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
