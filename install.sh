#!/usr/bin/env bash
# SpotUI installer — creates an isolated venv and installs yt-dlp.
set -e
cd "$(dirname "$0")"

if ! command -v mpv >/dev/null 2>&1; then
    echo "mpv not found. Install it first:  sudo pacman -S mpv"
    exit 1
fi

if [ ! -d .venv ]; then
    echo "Creating virtualenv…"
    python3 -m venv .venv 2>/dev/null || {
        echo "venv failed, falling back to --user install"
        pip3 install --user --break-system-packages -q yt-dlp
        mkdir -p .venv/bin
        printf '#!/usr/bin/env python3\nimport yt_dlp.yt_dlp as y\ny.main()\n' > .venv/bin/yt-dlp 2>/dev/null || true
        chmod +x .venv/bin/yt-dlp 2>/dev/null || true
        echo "Done (user install)."
        exit 0
    }
fi

echo "Installing yt-dlp…"
.venv/bin/pip install -q --upgrade pip >/dev/null 2>&1 || true
.venv/bin/pip install -q yt-dlp

mkdir -p "$HOME/.local/bin"
ln -sf "$PWD/.venv/bin/yt-dlp" "$HOME/.local/bin/yt-dlp" 2>/dev/null || true
ln -sf "$PWD/spotui" "$HOME/.local/bin/spotui"

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "⚠  $HOME/.local/bin not in PATH — add it to use 'spotui' from anywhere" ;;
esac

echo "✔ SpotUI ready. Run it from anywhere with:  spotui"
