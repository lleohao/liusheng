#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="$project_dir/.venv"
venv_python="$venv_dir/bin/python"

cd "$project_dir"

venv_error() {
    printf '%s\n' \
        "无法创建带 pip 的 Python 虚拟环境。" \
        "Ubuntu/Debian 请先运行：sudo apt install python3-venv" \
        "安装后重新执行 ./run.sh。" >&2
}

if [[ ! -x "$venv_python" ]]; then
    if ! python3 -m venv "$venv_dir"; then
        venv_error
        exit 1
    fi
fi

if ! "$venv_python" -m pip --version >/dev/null 2>&1; then
    printf '%s\n' "虚拟环境缺少 pip，正在尝试自动修复……" >&2
    if ! "$venv_python" -m ensurepip --upgrade; then
        venv_error
        exit 1
    fi
fi

if ! "$venv_python" -m pip --version >/dev/null 2>&1; then
    venv_error
    exit 1
fi

"$venv_python" -m pip install --quiet --disable-pip-version-check \
    -r "$project_dir/requirements.txt"
exec "$venv_python" "$project_dir/server.py" "$@"
