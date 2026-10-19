#!/usr/bin/env bash
# Install into a project-local virtualenv, never into system Python.
set -euo pipefail
cd -- "$(dirname -- "$(readlink -f -- "$0")")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.9+ is required." >&2
    exit 1
fi
if ! command -v mpv >/dev/null 2>&1; then
    echo "mpv not found. Install it: sudo pacman -S mpv (Arch) or sudo apt install mpv (Debian/Ubuntu)." >&2
    exit 1
fi
if [ ! -x .venv/bin/python ]; then
    echo "Creating virtualenv..."
    python3 -m venv .venv || {
        echo "Could not create .venv. On Debian/Ubuntu install python3-venv, then retry." >&2
        exit 1
    }
fi
echo "Installing yt-dlp..."
.venv/bin/python -m pip install yt-dlp
.venv/bin/python -c 'import yt_dlp'
mkdir -p "$HOME/.local/bin"
ln -sf "$PWD/.venv/bin/yt-dlp" "$HOME/.local/bin/yt-dlp"
ln -sf "$PWD/spotui" "$HOME/.local/bin/spotui"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "$HOME/.local/bin is not in PATH. Add it to run spotui from anywhere." ;;
esac
echo "SpotUI ready. Run: spotui"
