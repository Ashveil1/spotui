#!/usr/bin/env python3
"""
SpotUI — a Spotify-style terminal player, powered by YouTube + mpv.

Layout mimics Spotify desktop: top bar with search pill, black sidebar,
#121212 main area, and a full now-playing bar. Light on RAM: curses + mpv.
"""

import curses
import json
import locale
import os
import re
import signal
import shutil
import socket
import subprocess
import sys
import threading
import tempfile
import time
import unicodedata
import queue
from collections import OrderedDict
from pathlib import Path

import importlib.util

# existence probe only — the module (~25 MB) is never loaded into this process
HAVE_YTDL = importlib.util.find_spec("yt_dlp") is not None


def _yt_sub(args, timeout=75):
    """Run yt-dlp in a short-lived subprocess; returns (json|None, err).

    Keeps the TUI process free of yt_dlp's ~25 MB footprint: the helper
    process pays the import cost and dies right after.
    """
    cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings"] + args
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except Exception:
        return None, RuntimeError("yt-dlp failed to start (missing venv?)")
    if r.returncode == 0:
        try:
            return json.loads(r.stdout.decode("utf-8", "replace")), None
        except Exception:
            return None, None
    tail = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
    msg = tail[-1][:120] if tail else f"yt-dlp exit {r.returncode}"
    return None, RuntimeError(msg)

CFG = Path.home() / ".config" / "spotui"
STORE = CFG / "library.json"

# ---------------------------------------------------------------- glyphs ---
IC_LOGO = "◉"
IC_HOME = "⌂"
IC_SEARCH = "⌕"
IC_LIB = "≡"
IC_HEART = "♥"
IC_HEARTO = "♡"
IC_SHUF = "⇄"
IC_PREV = "◄"
IC_NEXT = "►"
IC_PLAY = "▶"
IC_PAUSE = "‖"
IC_REP = "⟳"
IC_QUEUE = "≣"
IC_NOTE = "♫"
IC_SPK = "◁"
IC_PLUS = "+"

SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
EQ_FRAMES = ["▁▄▂▆", "▄▂▆▁", "▂▆▁▄", "▆▁▄▂"]
PLACEHOLDER = "What do you want to play?"


# ------------------------------------------------------------- text utils ---
def dwidth(ch):
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def dlen(s):
    return sum(dwidth(c) for c in s)


def wcut(s, w):
    """Truncate to display width w; ellipsize Spotify-style when cut."""
    if w <= 0:
        return ""
    out, used, full = "", 0, True
    for ch in s:
        dw = dwidth(ch)
        if used + dw > w:
            full = False
            break
        out += ch
        used += dw
    if not full:
        ew = dwidth("…")
        while out and used + ew > w:
            used -= dwidth(out[-1])
            out = out[:-1]
        out = out + "…" if out else "…"
    return out


def fmt_t(sec):
    if sec is None:
        return "–:––"
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return "–:––"
    return f"{sec // 60}:{sec % 60:02d}"


def fmt_total(tracks):
    n = len(tracks)
    tot = sum(t.get("dur") or 0 for t in tracks)
    if tot <= 0:
        return f"{n} songs"
    m = tot // 60
    if m >= 60:
        return f"{n} songs, about {m // 60} hr {m % 60} min"
    return f"{n} songs, about {m} min"


JUNK_WORDS = re.compile(
    r"official|video|audio|lyric|visuali[sz]er|\bhq\b|\bhd\b|4k|\bmv\b|fmv"
    r"|color\s*coded|performance|karaoke|instrumental|remaster|full\s+album"
    r"|sub\s*esp|hardstyle|nightcore|explicit",
    re.I,
)


def _strip_junk_paren(s):
    out, i, changed = [], 0, False
    while i < len(s):
        c = s[i]
        if c in "([":
            depth, j = 1, i + 1
            while j < len(s) and depth:
                c2 = s[j]
                depth += (c2 in "([" ) - (c2 in ")]")
                j += 1
            inner = s[i + 1:j - 1]
            if depth == 0 and len(inner) <= 40 and JUNK_WORDS.search(inner):
                i = j
                changed = True
                continue
            out.append(s[i:j])
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out), changed


def clean_title(s):
    s = re.sub(r"【[^】]*】", " ", s or "")
    for _ in range(4):
        s2, ch = _strip_junk_paren(s)
        if not ch:
            break
        s = s2
    s = re.sub(r"\s*[-–—]\s*(official\s+)?(music\s+)?(video|audio|lyrics?)\s*$",
               "", s, flags=re.I)
    s = re.sub(r"\s+(HQ|HD|4K)\s+(Audio|Video|Lyrics|MV)\s*$", "", s,
               flags=re.I)
    s = re.sub(r"\s{2,}", " ", s).strip(" -–—|")
    return s or "Unknown title"


_SPLIT_RE = re.compile(r"\s+[-–—]\s+")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _pretty_artist(up):
    """'NirvanaVEVO' → 'Nirvana', 'QueenOfficialMusicVideo' → 'Queen'."""
    up = (up or "").strip()
    up = re.sub(r"^official\s+", "", up, flags=re.I)
    up = re.sub(r"\s*[-–—]?\s*(official)?\s*(music\s*)?(video|vevo|topic|"
                r"records|tv)\s*$", "", up, flags=re.I).strip()
    m = re.match(r"^(.+?)VEVO$", up, flags=re.I)
    if m:
        up = m.group(1)
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", up).strip()
    return name or up


def split_artist(title, uploader):
    """Return (artist, title). 'X - Topic' channels mean title is 'A - Song'."""
    up = (uploader or "").strip()
    if up.endswith(" - Topic"):
        parts = _SPLIT_RE.split(title, 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return up[:-8].strip(), title
    art = _pretty_artist(up)
    parts = _SPLIT_RE.split(title, 1)
    if len(parts) == 2:
        a, t = parts[0].strip(), parts[1].strip()
        na, nart = _norm(a), _norm(art)
        if art and nart and (na == nart or nart.startswith(na)):
            return (a or art), t
    return art or "Unknown artist", title


def _ytdl_playlist(url, n=40, timeout=30):
    """List a playlist (e.g. YouTube's auto 'Mix' radio) as track dicts."""
    info, err = _yt_sub(["--flat-playlist", "--socket-timeout", "15",
                         "-J", url], timeout=timeout)
    if info is None:
        raise err or RuntimeError("no playlist")
    out = []
    for e in (info or {}).get("entries") or []:
        if not e or not e.get("id"):
            continue
        raw = e.get("title") or e["id"]
        up = e.get("uploader") or e.get("channel") or ""
        artist, title = split_artist(clean_title(raw), up)
        out.append({
            "id": e["id"], "title": title, "artist": artist,
            "dur": e.get("duration"),
            "url": f"https://www.youtube.com/watch?v={e['id']}",
            "ch": e.get("uploader") or e.get("channel") or "",
            "added": None,
        })
    return out[:n]


def _radio_url(vid):
    """YouTube's auto-generated 'Mix' radio for a video = same-style picks."""
    return f"https://www.youtube.com/watch?v={vid}&list=RDAMVM{vid}"


# ----------------------------------------------------------------- store ---
class Store:
    def __init__(self):
        self.liked = []
        self.playlists = []
        self.recent = []
        self.history = []            # tracks actually played, newest first
        self.similar = {}            # cached "made for you" shelf
        self.last_search = 0.0       # when the last search happened
        self.volume = 70
        self._load()

    @staticmethod
    def _tracks(value):
        if not isinstance(value, list):
            return []
        out = []
        for t in value:
            if not isinstance(t, dict) or not isinstance(t.get("id"), str):
                continue
            if not re.fullmatch(r"[A-Za-z0-9_-]+", t["id"]):
                continue
            t = dict(t)
            for key, default in (("title", "Unknown title"),
                                 ("artist", "Unknown artist")):
                if not isinstance(t.get(key), str):
                    t[key] = default
            t["url"] = f"https://www.youtube.com/watch?v={t['id']}"
            if not isinstance(t.get("dur"), (int, float)):
                t["dur"] = None
            out.append(t)
        return out

    def _load(self):
        self.error = None
        self._save_lock = threading.Lock()
        self._corrupt = False
        try:
            d = json.loads(STORE.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                raise ValueError("library root must be an object")
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            self.error = f"Library could not be read: {e}"
            self._corrupt = True
            return
        self.liked = self._tracks(d.get("liked"))
        self.history = self._tracks(d.get("history"))[:30]
        self.playlists = []
        for pl in d.get("playlists", []) if isinstance(d.get("playlists"), list) else []:
            if isinstance(pl, dict) and isinstance(pl.get("name"), str):
                self.playlists.append(dict(name=pl["name"], tracks=self._tracks(pl.get("tracks"))))
        self.recent = [q for q in d.get("recent", []) if isinstance(q, str)][:8] if isinstance(d.get("recent"), list) else []
        cache = d.get("similar")
        self.similar = dict(cache) if isinstance(cache, dict) else {}
        for key in ("items", "pool"):
            self.similar[key] = self._tracks(self.similar.get(key))
        try:
            self.last_search = float(d.get("last_search") or 0)
        except (ValueError, TypeError):
            pass
        try:
            self.volume = max(0, min(100, int(d.get("volume", 70))))
        except (ValueError, TypeError):
            pass

    def save(self):
        # A private unique temp file prevents two background saves from
        # replacing each other's temp files. Never destroy an unreadable library.
        with self._save_lock:
            if self._corrupt:
                return False
            tmp = None
            try:
                CFG.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                                 dir=CFG, delete=False) as f:
                    tmp = Path(f.name)
                    json.dump({
                        "liked": self.liked, "playlists": self.playlists,
                        "recent": self.recent, "history": self.history,
                        "similar": self.similar, "last_search": self.last_search,
                        "volume": self.volume,
                    }, f, ensure_ascii=False, indent=1)
                    f.flush()
                    os.fsync(f.fileno())
                tmp.replace(STORE)
                self.error = None
                return True
            except (OSError, ValueError, TypeError) as e:
                self.error = f"Library could not be saved: {e}"
                return False
            finally:
                if tmp is not None:
                    tmp.unlink(missing_ok=True)


# ------------------------------------------------------------------- mpv ---
class Mpv:
    def __init__(self):
        self.sock_path = f"/tmp/spotui-{os.getpid()}.mpv.sock"
        self.proc = None
        self.state = {"idle": True, "pause": False, "pos": 0.0,
                      "dur": 0.0, "vol": 70}
        self.slock = threading.Lock()
        self.vlock = threading.Lock()
        self.last_load = 0.0
        self.was_idle = True
        self.running = True
        self.on_end = threading.Event()
        self._rid = 0

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def ensure(self):
        with self.slock:
            if not self.running:
                return False
            if self.alive():
                return True
            try:
                self.proc = subprocess.Popen(
                    ["mpv", "--no-video", "--no-terminal", "--audio-display=no",
                     "--idle=yes", "--keep-open=no", "--really-quiet",
                     "--osd-level=0", "--no-osc",       # no font/libass stack
                     # audio-only streams: small in-RAM cache keeps mpv light
                     "--demuxer-max-bytes=10MiB",
                     "--demuxer-max-back-bytes=2MiB",
                     "--cache-on-disk=no",
                     f"--input-ipc-server={self.sock_path}",
                     f"--volume={self.state['vol']}"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
            except Exception:
                return False
            for _ in range(40):
                if self.alive():
                    try:
                        s = socket.socket(socket.AF_UNIX)
                        s.settimeout(0.3)
                        s.connect(self.sock_path)
                        s.close()
                        return True
                    except OSError:
                        time.sleep(0.1)
                else:
                    return False
            return self.alive()

    def cmd(self, arr, *, status=False):
        if not self.alive():
            return None
        with self.slock:
            self._rid += 1
            rid = self._rid
            try:
                s = socket.socket(socket.AF_UNIX)
                s.settimeout(0.8)
                s.connect(self.sock_path)
                s.sendall((json.dumps(
                    {"command": arr, "request_id": rid}) + "\n").encode())
                buf = b""
                deadline = time.time() + 1.2
                while time.time() < deadline:
                    try:
                        chunk = s.recv(8192)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    lines = buf.split(b"\n")
                    buf = lines[-1]
                    for line in lines[:-1]:
                        try:
                            d = json.loads(line)
                        except Exception:
                            continue
                        if d.get("request_id") == rid:
                            s.close()
                            return (d.get("error") == "success") if status else (
                                d.get("data") if d.get("error") == "success" else None)
                s.close()
            except Exception:
                return None
        return None

    def load(self, url):
        if not self.ensure():
            return False
        self.last_load = time.time()
        self.was_idle = False
        ok = self.cmd(["loadfile", url, "replace"], status=True)
        self.cmd(["set_property", "pause", False])
        return bool(ok)

    def toggle(self):
        cur = self.cmd(["get_property", "pause"])
        if cur is None:
            return
        self.cmd(["set_property", "pause", not cur])

    def set_vol(self, v):
        v = max(0, min(100, int(v)))
        self.state["vol"] = v
        self.cmd(["set_property", "volume", v])

    def seek_abs(self, t):
        self.cmd(["set_property", "time-pos", max(0.0, float(t))])

    def seek_rel(self, d):
        self.cmd(["seek", d])

    def watch(self):
        while self.running:
            time.sleep(0.4)
            if not self.alive():
                continue
            idle = self.cmd(["get_property", "idle-active"])
            pause = self.cmd(["get_property", "pause"])
            pos = self.cmd(["get_property", "time-pos"])
            dur = self.cmd(["get_property", "duration"])
            with self.vlock:
                if idle is not None:
                    self.state["idle"] = bool(idle)
                if pause is not None:
                    self.state["pause"] = bool(pause)
                if pos is not None:
                    self.state["pos"] = float(pos)
                if dur is not None:
                    self.state["dur"] = float(dur)
            if idle is True and not self.was_idle and \
                    time.time() - self.last_load > 2.0:
                self.on_end.set()
            self.was_idle = bool(idle) if idle is not None else self.was_idle

    def stop(self):
        self.running = False
        try:
            if self.alive():
                self.cmd(["quit"])
                try:
                    self.proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        self.proc.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            try:
                os.unlink(self.sock_path)
            except FileNotFoundError:
                pass


# -------------------------------------------------------------- yt-dlp -----
def ytdl_search(q, n=25):
    info, err = _yt_sub(["--flat-playlist", "--socket-timeout", "15",
                         "-J", f"ytsearch{n}:{q}"])
    if info is None:
        # propagate so the calling thread can toast the reason
        raise err or RuntimeError("No results from yt-dlp")
    out = []
    for e in (info or {}).get("entries") or []:
        if not e or not e.get("id"):
            continue
        raw_title = e.get("title") or e["id"]
        up = e.get("uploader") or e.get("channel") or ""
        artist, title = split_artist(clean_title(raw_title), up)
        out.append({
            "id": e["id"], "title": title, "artist": artist,
            "dur": e.get("duration"),
            "url": f"https://www.youtube.com/watch?v={e['id']}",
            "ch": up,
            "added": None,
        })
    return out


def resolve_url(url):
    info, err = _yt_sub(["--no-playlist", "--socket-timeout", "15",
                         "-f", "bestaudio/best", "-J", url])
    if info is None and err:
        raise err
    return (info or {}).get("url") or None


# long uploads and "top hits / mix" videos are not songs — keep the shelf
# to real tracks only
_MIX_WORDS = ("playlist", "mix", "top hits", "best of", "full album",
              "greatest hits", "non stop", "nonstop", "compilation",
              "collection", "all songs", "videos")


def _real_song(t):
    dur = t.get("dur") or 0
    if dur and dur > 600:
        return False
    title = (t.get("title") or "").lower()
    return not any(w in title for w in _MIX_WORDS)


# -------------------------------------------------------------- colors ---
# per-song cover palettes — 8 families × 4 shades (bright → dark)
# the family is derived from a hash of the seed, like Spotify's
# generated card art: every playlist/song gets its own colour family
FAMS = [
    [(29, 185, 84), (18, 138, 63), (12, 92, 42), (7, 53, 28)],      # green
    [(155, 89, 182), (108, 52, 131), (74, 35, 90), (40, 17, 58)],   # purple
    [(230, 126, 34), (185, 119, 14), (142, 91, 8), (93, 63, 8)],    # orange
    [(52, 152, 219), (40, 116, 166), (26, 82, 118), (18, 48, 89)],  # blue
    [(231, 76, 60), (176, 58, 46), (123, 45, 38), (78, 27, 23)],    # red
    [(26, 188, 156), (20, 143, 119), (14, 102, 85), (9, 74, 56)],   # teal
    [(240, 98, 146), (190, 63, 105), (140, 44, 77), (92, 26, 47)],  # magenta
    [(93, 109, 222), (65, 77, 157), (47, 56, 113), (28, 33, 70)],   # indigo
]

ART_SLOTS = 50                    # 8 fams × 4 shades: slots 50–81


def art_fam(seed):
    import hashlib
    return hashlib.md5(str(seed).encode()).digest()[0] % len(FAMS)


def _nearest256(rgb):
    r, g, b = rgb
    best, bi = 1 << 30, 234
    for i in range(16, 232):
        q = i - 16
        cr = (q // 36) * 51
        cg = ((q % 36) // 6) * 51
        cb = (q % 6) * 51
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < best:
            best, bi = d, i
    for i in range(232, 256):
        v = 8 + (i - 232) * 10
        d = (r - v) ** 2 + (g - v) ** 2 + (b - v) ** 2
        if d < best:
            best, bi = d, i
    return bi


class Pal:
    """Logical color pairs; 256-color when available, 8-color fallback."""
    def __init__(self, scr):
        self.pairs = {}
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        n = curses.tigetnum("colors") or 8
        self.n = n
        self.mono = bool(os.environ.get("NO_COLOR"))
        if self.mono:
            spec = {}
        elif n >= 256:
            spec = {
                "text": (231, 233), "dim": (250, 233), "faint": (244, 233),
                "green": (41, 233), "side": (231, 16), "sdim": (250, 16),
                "sgreen": (41, 16), "sfaint": (244, 16),
                "hover": (231, 235), "hdim": (250, 235), "hgreen": (41, 235),
                "pill": (231, 237), "pilldim": (250, 237),
                "btn": (16, 41), "av": (231, 238),
                "bar": (244, 16), "toast": (231, 235),
                "pgreen": (41, 237), "accent": (41, 41),
                "bside": (231, 234), "bsdim": (250, 234),
                "bsgreen": (41, 234), "bbar": (239, 234),
                "g1": (16, 22), "g2": (16, 28), "g3": (16, 34), "g4": (16, 40),
                "cg1": (231, 22), "cg2": (231, 28), "cg3": (231, 34),
                "cg4": (231, 40), "g1d": (250, 22),
                "fade": (236, 236), "sbtrack": (244, 236),
                "sbthumb": (231, 244),
            }
        else:
            W, B, G, K = (curses.COLOR_WHITE, curses.COLOR_BLACK,
                          curses.COLOR_GREEN, 8)
            spec = {
                "text": (W, B), "dim": (W, B), "faint": (W, B),
                "green": (G, B), "side": (W, K), "sdim": (W, K),
                "sgreen": (G, K), "sfaint": (W, K),
                "hover": (B, W), "hdim": (B, W), "hgreen": (B, W),
                "pill": (W, B), "pilldim": (W, B),
                "btn": (B, G), "av": (W, B),
                "bar": (W, K), "toast": (B, W),
                "pgreen": (G, K), "accent": (G, G),
                "bside": (W, K), "bsdim": (W, K),
                "bsgreen": (G, K), "bbar": (W, K),
                "g1": (B, G), "g2": (B, G), "g3": (B, G), "g4": (B, G),
                "cg1": (B, G), "cg2": (B, G), "cg3": (B, G), "cg4": (B, G),
                "g1d": (B, G),
                "fade": (W, K), "sbtrack": (W, K), "sbthumb": (W, K),
            }
        i = 1
        for name, (fg, bg) in spec.items():
            try:
                curses.init_pair(i, fg, bg)
                self.pairs[name] = i
            except curses.error:
                self.pairs[name] = 0
            i += 1
        # per-song gradient families (FAMS): 8 palettes × 4 shades.
        # truecolor redefines slots 50–81; plain 256-color picks the
        # nearest cube index; 8-color and mono reuse the green pair.
        if self.mono or n < 256:
            gp = self.pairs.get("g1", 0)
            gd = self.pairs.get("g1d", 0)
            for fi in range(len(FAMS)):
                for k in range(4):
                    self.pairs[f"g{fi}{k}"] = gp
                self.pairs[f"g{fi}d"] = gd
        else:
            cc = False
            try:
                cc = curses.can_change_color()
            except curses.error:
                pass
            for fi in range(len(FAMS)):
                for k in range(4):
                    bg = (ART_SLOTS + fi * 4 + k) if cc else \
                        _nearest256(FAMS[fi][k])
                    try:
                        curses.init_pair(i, 231, bg)
                        self.pairs[f"g{fi}{k}"] = i
                    except curses.error:
                        self.pairs[f"g{fi}{k}"] = 0
                    i += 1
                bg2 = (ART_SLOTS + fi * 4 + 2) if cc else \
                    _nearest256(FAMS[fi][2])
                try:
                    curses.init_pair(i, 250, bg2)
                    self.pairs[f"g{fi}d"] = i
                except curses.error:
                    self.pairs[f"g{fi}d"] = 0
                i += 1
        if self.mono:
            # no-color.org: grayscale; bg-fill tokens become reverse video
            self.pairs.update({"hover": -1, "pill": -1, "btn": -1,
                               "toast": -1, "fade": 0, "sbtrack": 0,
                               "sbthumb": -1, "bside": -1, "bsdim": -1,
                               "bsgreen": -1, "bbar": -1, "pgreen": -1,
                               "accent": -1})
        # per-pixel cover pair cache (see cellpair); numbering continues
        # from the logical pairs above, capped under COLOR_PAIRS
        self.cpairs = {}
        self.cp_order = OrderedDict()
        self.cpnext = i
        try:
            self.cpmax = max(i + 16, curses.COLOR_PAIRS - 32)
        except Exception:
            self.cpmax = i + 16
        self._truecolor()

    def _truecolor(self):
        """Exact Spotify palette: redefine terminal color slots (0-1000 RGB)."""
        self.orig = {}
        if self.mono:
            return
        slots = {
            41: (114, 725, 329),   # 41: #1DB954 Spotify green
            40: (114, 725, 329),   # same, for gradient top
            34: (71, 541, 247),    # #128a3f
            28: (47, 361, 165),    # #0c5c2a
            22: (27, 208, 110),    # #07351c
            233: (71, 71, 71),     # #121212 main bg
            235: (122, 122, 122),  # #1f1f1f hover
            236: (142, 142, 142),  # #242424
            237: (162, 162, 162),  # #2a2a2a pill
            238: (83, 83, 83),     # #535353 avatar
            244: (106, 106, 106),  # #6a6a6a faint text
            250: (179, 179, 179),  # #b3b3b3 dim text
        }
        for fi, shades in enumerate(FAMS):
            for k, rgb in enumerate(shades):
                slots[ART_SLOTS + fi * 4 + k] = tuple(
                    v * 1000 // 255 for v in rgb)
        try:
            if not curses.can_change_color():
                return
            for slot, rgb in slots.items():
                self.orig[slot] = curses.color_content(slot)
                curses.init_color(slot, *rgb)
        except curses.error:
            self.orig = {}

    def restore(self):
        for slot, rgb in getattr(self, "orig", {}).items():
            try:
                curses.init_color(slot, *rgb)
            except curses.error:
                pass

    def __getitem__(self, name):
        return self.pairs.get(name, 0)

    # --- per-pixel cover pairs (real thumbnails rendered as half-blocks) ---

    def has_pair_headroom(self):
        return (not self.mono and self.n >= 256
                and self.cpnext < self.cpmax)

    def cellpair(self, fg256, bg256):
        """Numbered pair for a (fg, bg) 256-color combo with LRU reuse."""
        key = (fg256, bg256)
        p = self.cpairs.get(key)
        if p is not None:
            self.cp_order.move_to_end(key)
            return p
        if self.cpnext >= self.cpmax:          # recycle the oldest pair slot
            if not self.cp_order:
                return 0
            old_key = next(iter(self.cp_order))
            old = self.cpairs.pop(old_key)
            try:
                curses.init_pair(old, fg256, bg256)
                self.cpairs[key] = old
                self.cp_order[key] = old
            except curses.error:
                pass
            return self.cpairs.get(key, 0)
        try:
            curses.init_pair(self.cpnext, fg256, bg256)
            self.cpairs[key] = self.cpnext
            self.cp_order[key] = self.cpnext
            self.cpnext += 1
            return self.cpnext - 1
        except curses.error:
            return 0


# ------------------------------------------------------------------- app ---
class App:
    def __init__(self):
        self.store = Store()
        self.mpv = Mpv()
        self.mpv.state["vol"] = self.store.volume
        self.pal = None
        self.lock = threading.RLock()
        self.stack = [("home", None)]
        self.sel = {}
        self.off = {}
        self.query = ""
        self.results = []
        self.searching = False
        self.search_token = 0
        self.mode = "normal"          # normal | search | name | pick
        self.name_buf = ""
        self.rename_index = None
        self.delete_index = None
        self.pick_rows = []
        self.pick_idx = 0
        self.pick_pending = None      # track waiting to be added
        self.toast = ("", 0.0)
        self.queue = []
        self.queue_revision = 0
        self.qpos = -1
        self.orig_queue = None
        self.current = None
        self.loading = False
        self.load_token = 0
        self._last_row = None
        self._last_row_t = 0.0
        self.shuffle = False
        self.repeat = 0               # 0 off, 1 all, 2 one
        self.frame = 0
        self.rects = []
        self.soff = 0                 # sidebar scroll offset
        self.sw_bounds = None         # (SW, y0, y1) for wheel-over-sidebar
        self.liked_ids = {t["id"] for t in self.store.liked}
        self._sim_busy = False
        self._sim_at = 0.0
        self._radio_busy = False
        self.quit = False
        self.show_help = False
        self.user = (os.environ.get("USER") or "u")[:1]
        # --- real cover art piping (thumbnails as half-block pixels) ---
        self.cover_ok = shutil.which("ffmpeg") is not None
        self.cover_frames = {}     # (uid, w, h) -> (indices, pw, ph)
        self.cover_wait = set()    # queued (uid, w, h) keys
        self.cover_fail = set()    # uids that failed download/decode
        self.cover_dir = os.path.expanduser("~/.cache/spotui/covers")
        self.coverq = queue.Queue()
        threading.Thread(target=self._cover_worker, daemon=True).start()

    # ---------------------------------------------------------- helpers ---
    def toast_now(self, msg):
        self.toast = (msg, time.time() + 2.6)

    def key(self):
        k, a = self.stack[-1]
        # canonical selection key; None arg becomes "" so every view
        # (search/queue/home) shares the exact key the rows are drawn with
        return f"{k}:{'' if a is None else a}"

    def push(self, kind, arg=None):
        top = self.stack[-1]
        if top != (kind, arg):
            self.stack.append((kind, arg))
            self.sel.setdefault(f"{kind}:{'' if arg is None else arg}", 0)

    def back(self):
        if os.environ.get("SPOTUI_DEBUG"):
            open("/tmp/spotui-debug.log", "a").write(
                f"back stack={self.stack}\n")
        if len(self.stack) > 1:
            self.stack.pop()

    def view_tracks(self, vk=None):
        vk = vk or self.key()
        kind, arg = (vk.split(":", 1) + [None])[:2]
        if kind == "search":
            return self.results
        if kind == "liked":
            return self.store.liked
        if kind == "playlist":
            try:
                return self.store.playlists[int(arg)]["tracks"]
            except Exception:
                return []
        if kind == "queue":
            return self.queue
        if kind == "history":
            return self.store.history
        if kind == "similar":
            return (self.store.similar or {}).get("items") or []
        return []

    def sel_row(self):
        return self.sel.get(self.key(), 0)

    def move_sel(self, d, n):
        if self.stack[-1][0] == "home":
            n = 1 + len(self.store.playlists)
        if n <= 0:
            return
        k = self.key()
        s = max(0, min(n - 1, self.sel.get(k, 0) + d))
        self.sel[k] = s

    # ------------------------------------------------------------ covers ---
    def cover_for(self, uid, w, h):
        """Decode-on-demand thumbnail as (palette indices, pw, ph).

        Returns None while loading or when covers are unavailable —
        callers fall back to the generated gradient art.
        """
        if not uid or not self.cover_ok:
            return None
        if not self.pal or not self.pal.has_pair_headroom():
            return None
        frame = self.cover_frames.get((uid, w, h))
        if frame:
            return frame
        if uid in self.cover_fail or (uid, w, h) in self.cover_wait:
            return None
        self.cover_wait.add((uid, w, h))
        self.coverq.put((uid, w, h))
        if len(self.cover_frames) > 64:       # fifo trim of decoded frames
            self.cover_frames.pop(next(iter(self.cover_frames)))
        return None

    def _cover_jpg(self, uid):
        path = os.path.join(self.cover_dir, uid + ".jpg")
        if os.path.exists(path):
            return path
        try:
            # ffmpeg fetches the HTTP thumbnail itself — keeps urllib's
            # ~12 MB (ssl, http.client, email) out of the TUI process.
            tmp = path + ".part.jpg"
            r = subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-y",
                 "-i", f"https://i.ytimg.com/vi/{uid}/mqdefault.jpg",
                 "-frames:v", "1", tmp],
                timeout=15, capture_output=True)
            if r.returncode != 0 or not os.path.exists(tmp) \
                    or os.path.getsize(tmp) < 500:
                raise ValueError("thumbnail fetch failed")
            os.replace(tmp, path)
            return path
        except Exception:
            self.cover_fail.add(uid)
            return None

    def _decode_cover(self, jpg, w, h):
        """ffmpeg → center-cropped RGB → 256-palette indices.

        Pixel grid is w × 2h: one pixel per cell horizontally, two vertically
        (rendered as the ▀ fg/bg pairs)."""
        pw, ph = w, h * 2
        try:
            r = subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", jpg,
                 "-vf",
                 f"scale={pw}:{ph}:force_original_aspect_ratio=increase,"
                 f"crop={pw}:{ph}",
                 "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
                 "pipe:1"], capture_output=True, timeout=10)
        except Exception:
            return None
        buf = r.stdout
        if len(buf) != pw * ph * 3:
            return None
        idx = bytearray(pw * ph)
        for i in range(pw * ph):
            idx[i] = _nearest256(
                (buf[i * 3], buf[i * 3 + 1], buf[i * 3 + 2]))
        return bytes(idx), pw, ph

    def _cover_worker(self):
        try:
            os.makedirs(self.cover_dir, exist_ok=True)
        except Exception:
            self.cover_ok = False             # unwritable $HOME → no covers
            return
        while True:
            uid, w, h = self.coverq.get()
            try:
                if (uid, w, h) in self.cover_frames \
                        or uid in self.cover_fail:
                    continue
                jpg = self._cover_jpg(uid)
                if not jpg:
                    continue
                frame = self._decode_cover(jpg, w, h)
                if frame:
                    self.cover_frames[(uid, w, h)] = frame
                else:
                    self.cover_fail.add(uid)
            except Exception:
                self.cover_fail.add(uid)

    # ------------------------------------------------------------- play ---
    def play(self, tracks, pos):
        if not tracks or not 0 <= pos < len(tracks):
            return
        self.queue_revision += 1
        self.orig_queue = None
        self.queue = [dict(t) for t in tracks]
        self.qpos = pos
        if self.shuffle:
            self._apply_shuffle(True)
        self._play_current()

    def _apply_shuffle(self, on):
        self.queue_revision += 1
        if on:
            self.orig_queue = [dict(t) for t in self.queue]
            head = self.queue[:self.qpos + 1]
            tail = self.queue[self.qpos + 1:]
            import random
            random.shuffle(tail)
            self.queue = head + tail
        elif self.orig_queue:
            cur = self.current
            self.queue = [dict(t) for t in self.orig_queue]
            if cur:
                for i, t in enumerate(self.queue):
                    if t["id"] == cur["id"]:
                        self.qpos = i
                        break

    def _play_current(self):
        if not 0 <= self.qpos < len(self.queue):
            return
        self.load_token += 1
        token = self.load_token
        self.mpv.on_end.clear()
        t = self.queue[self.qpos]
        self.current = t
        self.loading = True
        threading.Thread(target=self._resolve_load, args=(t, token),
                         daemon=True).start()

    def _note_history(self, t):
        """Remember what was actually played (newest first, capped)."""
        try:
            rec = {k: t.get(k) for k in ("id", "title", "artist", "dur", "url")}
            rec["added"] = time.time()
            h = [x for x in self.store.history
                 if isinstance(x, dict) and x.get("id") != rec.get("id")]
            h.insert(0, rec)
            self.store.history = h[:30]
            self.store.save()
        except Exception:
            pass
        self.refresh_similar()

    # ------------------------------------------------------- radio queue --
    def _start_radio(self, track):
        """Queue up same-artist / same-channel tracks after this one."""
        vid = track.get("id")
        if not vid or self._radio_busy:
            return
        self._radio_busy = True
        threading.Thread(target=self._radio_worker, args=(dict(track), self.queue_revision, self.load_token),
                         daemon=True).start()

    def _radio_worker(self, track, revision=None, token=None):
        revision = self.queue_revision if revision is None else revision
        token = self.load_token if token is None else token
        import random
        items = []
        try:
            items = _ytdl_playlist(_radio_url(track["id"]), n=60)
        except Exception:
            items = []
        ch = track.get("ch") or ""
        items = [t for t in items
                 if t.get("id") != track.get("id") and _real_song(t)]
        random.shuffle(items)
        # same channel first (Topic/VEVO = the artist's own uploads)
        picks, per_artist = [], {}
        for t in items:
            a = (t.get("artist") or "").lower()
            if per_artist.get(a, 0) >= 2:
                continue
            per_artist[a] = per_artist.get(a, 0) + 1
            picks.append(t)
            if len(picks) >= 30:
                break
        picks.sort(key=lambda t: 0 if (t.get("ch") or "") == ch else 1)
        with self.lock:
            # only swap the queue if the user is still on this track
            if (picks and not self.quit and revision == self.queue_revision
                    and token == self.load_token and self.current
                    and self.current.get("id") == track.get("id")):
                self.queue = [track] + picks
                self.qpos = 0
                self.toast_now("Radio on — more from "
                               f"{track.get('artist') or 'this artist'}")
            self._radio_busy = False

    # ------------------------------------------------- made-for-you shelf --
    def _similar_seed(self):
        """(seed, is_artist, video_id) the 'same vibe' shelf is built from."""
        hist = self.store.history
        newest_play = 0.0
        if hist and isinstance(hist[0], dict):
            newest_play = float(hist[0].get("added") or 0)
        # a search that happened after the last play wins the shelf
        if float(self.store.last_search or 0) > newest_play:
            for q in self.store.recent[:3]:
                if q and len(q) > 2:
                    return q, False, None
        for t in hist[:6]:
            a = (t.get("artist") or "").strip()
            if a:
                return a, True, t.get("id")
        for t in self.store.liked[:6]:
            a = (t.get("artist") or "").strip()
            if a:
                return a, True, t.get("id")
        for q in self.store.recent[:3]:
            if q and len(q) > 2:
                return q, False, None
        return "", False, None

    def refresh_similar(self, force=False):
        """Kick off a background search for same-vibe tracks (never blocks)."""
        seed, is_artist, vid = self._similar_seed()
        if not seed:
            return
        cache = self.store.similar or {}
        stale = cache.get("v") != 2          # old caches get rebuilt
        if not force and not stale and cache.get("seed") == seed \
                and cache.get("items"):
            return
        now = time.time()
        if self._sim_busy:
            return
        if not force and now - self._sim_at < 120:
            return
        self._sim_busy = True
        self._sim_at = now
        # instant re-roll: reshuffle the pool we already fetched
        pool = cache.get("pool") or []
        if force and pool and cache.get("seed") == seed:
            picks = self._pick_similar(pool)
            with self.lock:
                self.store.similar = dict(cache, items=picks, ts=time.time())
                self.store.save()
            self._sim_busy = False
            return
        q = f"{seed} songs" if is_artist else seed
        kind = "artist" if is_artist else "query"
        threading.Thread(target=self._similar_worker,
                         args=(seed, q, kind, vid), daemon=True).start()

    def _similar_worker(self, seed, q, kind="artist", vid=None):
        # 1) fast lane: plain search → the shelf shows within a few seconds
        try:
            items = ytdl_search(q, n=14)
        except Exception:
            items = []
        if vid is None and items:
            vid = items[0].get("id")
        pool = [t for t in items if _real_song(t)]
        picks = self._pick_similar(pool)
        if picks:
            with self.lock:
                self.store.similar = {"v": 2, "seed": seed, "items": picks,
                                      "kind": kind, "vid": vid,
                                      "pool": pool, "ts": time.time()}
                self.store.save()
        # 2) upgrade: YouTube's auto "Mix" radio = the artist AND similar
        #    artists — slower, but the picks get properly varied
        if vid:
            try:
                radio = _ytdl_playlist(_radio_url(vid), n=90)
            except Exception:
                radio = []
            pool = [t for t in radio if _real_song(t)][:90]
            picks = self._pick_similar(pool)
            if picks:
                with self.lock:
                    self.store.similar = {"v": 2, "seed": seed,
                                          "items": picks, "kind": kind,
                                          "vid": vid, "pool": pool,
                                          "ts": time.time()}
                    self.store.save()
        with self.lock:
            self._sim_busy = False

    def _pick_similar(self, items):
        """Different songs, different artists, random order."""
        import random
        seen = {t.get("id") for t in self.store.history}
        seen |= {t.get("id") for t in self.store.liked}
        items = [t for t in items
                 if t.get("id") not in seen and _real_song(t)]
        # one entry per song title — the shelf must not repeat one song
        uniq, seen_titles = [], set()
        for t in items:
            k = "".join(c for c in unicodedata.normalize(
                "NFKC", t.get("title") or "").casefold() if c.isalnum())
            if not k or k in seen_titles:
                continue
            seen_titles.add(k)
            uniq.append(t)
        random.shuffle(uniq)
        # at most two songs per artist, so the shelf stays varied
        picks, per_artist = [], {}
        for t in uniq:
            a = (t.get("artist") or "").lower()
            if per_artist.get(a, 0) >= 2:
                continue
            per_artist[a] = per_artist.get(a, 0) + 1
            picks.append(t)
            if len(picks) >= 6:
                break
        return picks

    def _resolve_load(self, track, token=None):
        token = self.load_token if token is None else token
        try:
            if not HAVE_YTDL:
                raise RuntimeError("yt-dlp not installed — run install.sh")
            url = resolve_url(track["url"])
            if not url:
                raise RuntimeError("no stream found")
            with self.lock:
                if token != self.load_token or self.quit:
                    return
                if not self.mpv.load(url):
                    raise RuntimeError("mpv failed to start")
                self.loading = False
                self._note_history(track)
        except Exception as e:
            with self.lock:
                if token != self.load_token or self.quit:
                    return
                self.loading = False
                self.toast_now(f"Couldn't play — {e}")

    def play_row(self, vk, idx):
        if vk.split(":", 1)[0] == "queue":
            if 0 <= idx < len(self.queue):
                self.qpos = idx
                self._play_current()
            return
        tracks = self.view_tracks(vk)
        if 0 <= idx < len(tracks):
            self.play(tracks, idx)
            # a search pick keeps the music going with the same artist /
            # channel instead of walking down the result list
            if vk.split(":")[0] in ("search", "similar", "history"):
                self._start_radio(tracks[idx])

    def toggle(self):
        if self.current:
            self.mpv.toggle()
        elif self.queue:
            self._play_current()

    def next(self, auto=False):
        if auto and self.repeat == 2 and self.current:
            self._play_current()
            return
        if self.qpos + 1 < len(self.queue):
            self.qpos += 1
            self._play_current()
        elif auto and self.repeat == 1 and self.queue:
            self.qpos = 0
            self._play_current()

    def prev(self):
        if self.mpv.state["pos"] > 2.5:
            self.mpv.seek_abs(0)
        elif self.qpos > 0:
            self.qpos -= 1
            self._play_current()

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self._apply_shuffle(self.shuffle)
        self.toast_now(f"Shuffle {'on' if self.shuffle else 'off'}")

    def cycle_repeat(self):
        self.repeat = (self.repeat + 1) % 3
        if self.repeat == 2:
            self.mpv.cmd(["set_property", "loop-file", "inf"])
        else:
            self.mpv.cmd(["set_property", "loop-file", "no"])
        names = ["Repeat off", "Repeat all", "Repeat one"]
        self.toast_now(names[self.repeat])

    def vol(self, d=None, absolute=None):
        v = self.mpv.state["vol"]
        if absolute is not None:
            v = absolute
        else:
            v += (d or 0)
        self.mpv.set_vol(v)
        self.store.volume = self.mpv.state["vol"]
        self.store.save()

    # ------------------------------------------------------------ library --
    def like(self, t):
        if not t:
            return
        if t["id"] in self.liked_ids:
            self.liked_ids.discard(t["id"])
            self.store.liked = [x for x in self.store.liked
                                if x["id"] != t["id"]]
            self.toast_now("Removed from Liked Songs")
        else:
            self.liked_ids.add(t["id"])
            self.store.liked.insert(0, dict(t, added=time.strftime("%Y-%m-%d")))
            self.toast_now("Added to Liked Songs")
        self.store.save()

    def add_queue(self, t):
        if not t:
            return
        if not self.current:
            self.play([t], 0)
            return
        self.queue_revision += 1
        self.queue.append(dict(t))
        if self.shuffle and self.orig_queue:
            self.orig_queue.append(dict(t))
        self.toast_now(f"Added to queue: {t['title'][:30]}")

    def create_playlist(self, name):
        name = name.strip() or "New Playlist"
        self.store.playlists.append({"name": name, "tracks": []})
        self.store.save()
        self.push("playlist", len(self.store.playlists) - 1)
        self.toast_now(f"Created playlist: {name}")

    def rename_playlist(self, pi, name):
        if not 0 <= pi < len(self.store.playlists):
            return
        name = name.strip()
        if not name:
            self.toast_now("Playlist name cannot be empty")
            return
        self.store.playlists[pi]["name"] = name
        self.store.save()
        self.toast_now(f"Renamed playlist: {name}")

    def delete_playlist(self, pi):
        if not 0 <= pi < len(self.store.playlists):
            return
        name = self.store.playlists[pi]["name"]
        del self.store.playlists[pi]
        # Playlist view keys use indices; remove deleted views and reindex
        # every saved selection and back-stack entry after that index.
        self.stack = [(kind, arg - 1 if kind == "playlist" and arg > pi else arg)
                      for kind, arg in self.stack
                      if not (kind == "playlist" and arg == pi)] or [("home", None)]
        for state in (self.sel, self.off):
            updated = {}
            for key, value in state.items():
                if key.startswith("playlist:"):
                    idx = int(key.split(":", 1)[1])
                    if idx == pi:
                        continue
                    key = f"playlist:{idx - 1 if idx > pi else idx}"
                updated[key] = value
            state.clear()
            state.update(updated)
        self.store.save()
        self.toast_now(f"Deleted playlist: {name}")

    def add_to_playlist(self, pi, t):
        try:
            pl = self.store.playlists[pi]
        except IndexError:
            return
        if any(x["id"] == t["id"] for x in pl["tracks"]):
            self.toast_now("Already in playlist")
            return
        pl["tracks"].append(dict(t, added=time.strftime("%Y-%m-%d")))
        self.store.save()
        self.toast_now(f"Added to {pl['name']}")

    def delete_selected(self):
        kind, arg = self.stack[-1]
        idx = self.sel_row()
        tracks = self.view_tracks()
        if not (0 <= idx < len(tracks)):
            return
        if kind == "playlist":
            del self.store.playlists[arg]["tracks"][idx]
            s = self.sel_row()
            if s >= len(tracks) - 1:
                self.sel[self.key()] = max(0, len(tracks) - 2)
            self.store.save()
        elif kind == "liked":
            self.like(tracks[idx])
        elif kind == "queue":
            self.queue_revision += 1
            del self.queue[idx]
            if idx < self.qpos:
                self.qpos -= 1
            elif idx == self.qpos:
                # deleted the playing row: mpv keeps playing it, so step
                # the pointer back so auto-advance lands on the next song
                self.qpos -= 1

    def open_pick(self, t):
        self.pick_pending = t
        self.pick_rows = [{"name": "+ New playlist", "new": True}] + [
            {"name": p["name"], "new": False} for p in self.store.playlists]
        self.pick_idx = 0
        self.mode = "pick"

    def do_search(self, q):
        q = q.strip()
        if not q or not HAVE_YTDL:
            if not HAVE_YTDL:
                self.toast_now("yt-dlp missing — run ./install.sh")
            return
        self.push("search")
        self.search_token += 1
        token = self.search_token
        self.searching = True
        threading.Thread(target=self._search_worker,
                         args=(q, token), daemon=True).start()
        if q in self.store.recent:
            self.store.recent.remove(q)
        self.store.recent.insert(0, q)
        self.store.recent = self.store.recent[:8]
        self.store.last_search = time.time()
        self.store.save()
        self.refresh_similar()

    def _search_worker(self, q, token):
        try:
            res = ytdl_search(q)
        except Exception as e:
            res = []
            self.toast_now(f"Search failed — {e}")
        with self.lock:
            if token != self.search_token:
                return
            self.results = res
            self.searching = False
            self.sel["search:"] = 0
            self.off["search:"] = 0

    def track_under(self):
        tracks = self.view_tracks()
        idx = self.sel_row()
        return tracks[idx] if 0 <= idx < len(tracks) else None


# ---------------------------------------------------------------- drawing --
def put(scr, y, x, s, pair, attr=0):
    H, W = scr.getmaxyx()
    if y < 0 or y >= H or x >= W or x < 0:
        return
    if pair == -1:  # NO_COLOR mode — selection signaled by reverse video
        pair = 0
        attr |= curses.A_REVERSE
    # Never write the last column: a write there arms curses' pending
    # wrap, and the NEXT write then silently lands one row lower (the
    # whole background shifts down a row = black boxes over the text).
    text, used = [], 0
    for ch in str(s):
        if unicodedata.category(ch).startswith("C"):
            continue
        width = dwidth(ch)
        if used + width > W - 1 - x:
            break
        text.append(ch)
        used += width
    if not text:
        return
    try:
        scr.addstr(y, x, "".join(text), curses.color_pair(pair) | attr)
    except curses.error:
        pass


def fill(scr, y, x, w, pair):
    put(scr, y, x, " " * w, pair)


def box(scr, y, x, w, h, pair, bg=None):
    for j in range(h):
        fill(scr, y + j, x, w, bg if bg else 0)
    put(scr, y, x, "╭" + "─" * (w - 2) + "╮", pair)
    for j in range(1, h - 1):
        put(scr, y + j, x, "│", pair)
        put(scr, y + j, x + w - 1, "│", pair)
    put(scr, y + h - 1, x, "╰" + "─" * (w - 2) + "╯", pair)


AGLY = "▚▞▟▛▜▓▒░▞▙▚▟"


def draw_art(scr, y, x, w, h, seed, pal, icon=None, art=None):
    """Cover art: real thumbnail pixels (half-block cells) when `art` is
    supplied, otherwise the generated per-song gradient (Spotify style)."""
    if art and not pal.mono and pal.has_pair_headroom():
        idx, pw, ph = art
        for cy in range(ph // 2):
            yy = y + cy
            if yy >= 0:                      # defensive vs tiny screens
                for cx in range(pw):
                    top = idx[cy * 2 * pw + cx]
                    bot = idx[(cy * 2 + 1) * pw + cx]
                    put(scr, yy, x + cx, "▀",
                        pal.cellpair(top, bot))
        return
    fi = art_fam(seed)
    shades = [f"g{fi}{k}" for k in range(4)]
    for j in range(h):
        fill(scr, y + j, x, w, pal[shades[min(3, j * 4 // max(1, h))]])
    if icon and h >= 3 and w >= 3:
        name = shades[min(3, (h // 2) * 4 // max(1, h))]
        put(scr, y + h // 2, x + max(0, w // 2 - dlen(icon) // 2), icon,
            pal[name], curses.A_BOLD)


def eq_bars(app):
    return EQ_FRAMES[(app.frame // 4) % len(EQ_FRAMES)]


# ------------------------------------------------------------------ app ui --
class UI:
    def __init__(self, app, scr):
        self.app = app
        self.scr = scr
        self.pal = app.pal

    def hit(self, x0, y0, w, h, act, arg=None):
        self.app.rects.append(
            {"x0": x0, "y0": y0, "x1": x0 + w, "y1": y0 + h,
             "act": act, "arg": arg})

    # ------------------------------------------------------------ topbar --
    def topbar(self, y0, W, SW):
        app, pal = self.app, self.pal
        for j in range(3):
            fill(self.scr, y0 + j, 0, W, pal["side"])
        put(self.scr, y0 + 1, 2, "←", pal["sdim"])
        self.hit(2, y0 + 1, 1, 1, "back")

        pw = min(max(28, W - 34), 56)
        px = max(SW + 2, (W - pw) // 2)
        focused = app.mode == "search"
        border = pal["green"] if focused else pal["pilldim"]
        put(self.scr, y0, px, "╭" + "─" * (pw - 2) + "╮", border)
        put(self.scr, y0 + 2, px, "╰" + "─" * (pw - 2) + "╯", border)
        for j in (1,):
            fill(self.scr, y0 + j, px + 1, pw - 2, pal["pill"])
            put(self.scr, y0 + j, px, "│", border)
            put(self.scr, y0 + j, px + pw - 1, "│", border)
        q = app.query
        if q:
            put(self.scr, y0 + 1, px + 2, IC_SEARCH, pal["pill"])
            put(self.scr, y0 + 1, px + 4, wcut(q, pw - 6), pal["pill"],
                curses.A_BOLD)
        else:
            put(self.scr, y0 + 1, px + 2, IC_SEARCH, pal["pilldim"])
            put(self.scr, y0 + 1, px + 4, PLACEHOLDER, pal["pilldim"])
        self.hit(px, y0, pw, 3, "focus_search")
        app.search_xy = (px + 4 + min(dlen(q), pw - 7), y0 + 1)

        put(self.scr, y0 + 1, W - 9, "?", pal["sdim"])
        self.hit(W - 9, y0 + 1, 1, 1, "help")
        put(self.scr, y0 + 1, W - 6, f" {app.user} ", pal["av"], curses.A_BOLD)
        self.hit(W - 6, y0 + 1, 3, 1, "noop")

    # ----------------------------------------------------------- sidebar --
    def sidebar(self, y0, y1, SW):
        app, pal = self.app, self.pal
        scr = self.scr
        for y in range(y0, y1):
            fill(scr, y, 0, SW, pal["side"])
        put(scr, y0 + 1, 2, IC_LOGO, pal["sgreen"], curses.A_BOLD)
        put(scr, y0 + 1, 4, "SpotUI", pal["side"], curses.A_BOLD)

        kind, _ = app.stack[-1]
        navs = [("home", IC_HOME, "Home"), ("search", IC_SEARCH, "Search")]
        for i, (k, ic, label) in enumerate(navs):
            y = y0 + 3 + i
            active = kind == k
            if active:
                fill(scr, y, 1, SW - 2, pal["pill"])
            put(scr, y, 3, ic, pal["pill"] if active else pal["sdim"],
                curses.A_BOLD if active else 0)
            put(scr, y, 6, label,
                pal["pill"] if active else pal["sdim"],
                curses.A_BOLD if active else 0)
            self.hit(1, y, SW - 2, 1, "nav", k)

        put(scr, y0 + 5, 2, "─" * (SW - 4), pal["sfaint"])
        y = y0 + 6
        put(scr, y, 2, "Your Library", pal["sdim"], curses.A_BOLD)
        put(scr, y, SW - 3, IC_PLUS, pal["sdim"], curses.A_BOLD)
        self.hit(SW - 4, y, 2, 1, "create")

        items = [("liked", IC_HEART, "Liked Songs")]
        for i, pl in enumerate(app.store.playlists):
            items.append(("playlist", IC_NOTE, pl["name"], i))
        top, bot = y0 + 8, y1 - 1
        vis = max(1, bot - top)
        app.soff_max = max(0, len(items) - vis)
        app.soff = max(0, min(app.soff, app.soff_max))
        for row, i in enumerate(range(app.soff, len(items))):
            y = top + row
            if y >= y1 - 1:
                break
            item = items[i]
            k, ic, label = item[0], item[1], item[2]
            active = (kind, app.stack[-1][1]) == (k, item[3] if len(item) > 3 else None)
            if active:
                fill(scr, y, 1, SW - 2, pal["pill"])
                icp = pal["pgreen"] if k == "liked" else pal["pilldim"]
                txp = pal["pill"]
            else:
                icp = pal["sgreen"] if k == "liked" else pal["sdim"]
                txp = pal["sdim"]
            put(scr, y, 3, ic, icp)
            name = wcut(label, SW - 10)
            put(scr, y, 6, name, txp)
            arg = item[3] if len(item) > 3 else None
            self.hit(1, y, SW - 2, 1, "libitem", (k, arg))
        # overflow indicators when items run off-screen
        if app.soff > 0:
            put(scr, top - 1, SW - 5, "▴", pal["sdim"])
        if app.soff < app.soff_max:
            put(scr, y1 - 1, SW - 5, "▾", pal["sdim"])

    # -------------------------------------------------------------- main --
    BARS_PAT = (1, 3, 2, 5, 4, 7, 5, 3, 6, 4, 2, 5, 3, 1, 4, 6, 3, 2, 4, 7,
                5, 2, 3, 1)

    def splash(self, scr):
        """Opening animation: sweeping equalizer bars + wordmark reveal.
        Any key skips it; tiny screens skip it automatically."""
        pal = self.pal
        H, W = scr.getmaxyx()
        if H < 16 or W < 72:
            return
        scr.nodelay(True)
        word = "◉  S  P  O  T  U  I"
        tag = "your music, in the terminal"
        cy0 = H // 2 - 4
        skip = False
        try:
            for step in range(12):
                if step:
                    try:
                        if scr.get_wch() is not None:
                            skip = True
                            break
                    except curses.error:
                        pass
                    time.sleep(0.11)
                for y in range(H - 1):
                    fill(scr, y, 0, W, pal["side"])
                if step >= 5:
                    put(scr, cy0, max(2, (W - dlen(word)) // 2), word,
                        pal["side"], curses.A_BOLD)
                    if step >= 9:
                        put(scr, cy0 + 2, max(2, (W - dlen(tag)) // 2), tag,
                            pal["sdim"])
                # equalizer bars sweeping right, growing with time
                amp = max(1, min(step - 1, 7))
                base = min(cy0 + 11, H - 3)
                n = min(48, W - 24)
                bx = max(6, (W - n) // 2)
                cap = max(1, base - cy0 - 4)
                for i in range(n):
                    hgt = (self.BARS_PAT[(i + step * 2) % len(self.BARS_PAT)]
                           * amp // 7 + 1)
                    for r in range(min(hgt, cap)):
                        fill(scr, base - r, bx + i, 1, pal["btn"])
            if not skip:
                time.sleep(0.3)         # hold the finished frame briefly
        finally:
            scr.nodelay(False)
            scr.timeout(90)

    def main(self, y0, y1, x0, W):
        kind, arg = self.app.stack[-1]
        for y in range(y0, y1):
            fill(self.scr, y, x0, W - x0, self.pal["text"])
        if kind == "home":
            self.v_home(y0, y1, x0, W)
        elif kind == "search":
            self.v_search(y0, y1, x0, W)
        elif kind in ("liked", "playlist"):
            self.v_collection(y0, y1, x0, W, kind, arg)
        elif kind == "queue":
            self.v_queue(y0, y1, x0, W)

    def v_home(self, y0, y1, x0, W):
        app, pal = self.app, self.pal
        scr = self.scr
        h = time.localtime().tm_hour
        greet = "Good morning" if h < 12 else \
            "Good afternoon" if h < 18 else "Good evening"
        put(scr, y0 + 1, x0 + 2, greet, pal["text"], curses.A_BOLD)
        put(scr, y0 + 1, x0 + 4 + dlen(greet),
            time.strftime("%a %d %b", time.localtime()), pal["faint"])
        fill(scr, y0 + 2, x0 + 2, 6, pal["accent"])   # accent underline

        y = self._home_tiles(app, pal, scr, y0 + 4, y1, x0, W)
        y = self._home_similar(app, pal, scr, y, y1, x0, W)
        y = self._home_history(app, pal, scr, y, y1, x0, W)
        y = self._home_liked(app, pal, scr, y, y1, x0, W)
        y = self._home_recent(app, pal, scr, y, y1, x0, W)
        put(scr, y1 - 2, x0 + 2,
            "Type / to search · Enter opens · ? for shortcuts",
            pal["faint"])

    def _home_tiles(self, app, pal, scr, y0, y1, x0, W):
        """Shortcut tiles: Liked Songs + your playlists."""
        tiles = [("liked", IC_HEART, "Liked Songs", "liked", None)]
        for i, pl in enumerate(app.store.playlists):
            tiles.append(("pl", IC_NOTE, pl["name"], "playlist", i))
        tw = min(26, (W - x0 - 4) // 2)
        th = 3
        per_row = max(1, (W - x0 - 2) // (tw + 1))
        sel_i = app.sel.get("home:", 0)
        last = y0
        for i, t in enumerate(tiles):
            row, col = divmod(i, per_row)
            x = x0 + 2 + col * (tw + 1)
            y = y0 + row * (th + 1)
            if y + th >= y1:
                break
            last = y + th
            if i == sel_i:
                for j in range(th):
                    fill(scr, y + j, x + 3, tw - 3, pal["pill"])
            draw_art(scr, y, x, 3, th, t[2], pal,
                     icon=(IC_HEART if t[0] == "liked" else IC_NOTE))
            put(scr, y + 1, x + 5, wcut(t[2], tw - 9),
                pal["pill"] if i == sel_i else pal["dim"], curses.A_BOLD)
            if i == sel_i:
                put(scr, y + 1, x + tw - 3, f" {IC_PLAY} ", pal["btn"],
                    curses.A_BOLD)
            self.hit(x, y, tw, th, "tile", (t[3], t[4]))
        if sel_i >= len(tiles):
            app.sel["home:"] = 0
        return last + 1

    def _home_liked(self, app, pal, scr, y0, y1, x0, W):
        """'Songs you like' — a live peek into the Liked list (mouse plays)."""
        likes = app.store.liked
        if not likes or y0 + 1 >= y1 - 1:
            return y0
        put(scr, y0, x0 + 2, "Songs you like", pal["text"], curses.A_BOLD)
        put(scr, y0, W - 17, "Open Liked Songs →", pal["green"])
        self.hit(W - 18, y0, 20, 1, "tile", ("liked", None))
        w = W - x0 - 4
        title_w = max(12, int(w * 0.62))
        n = 0
        for i, t in enumerate(likes):
            y = y0 + 1 + i
            if y >= y1 - 2 or i >= 5:
                break
            self.homerow(y, x0 + 2, w, t, i, title_w)
            n += 1
        return y0 + 1 + n

    def _home_similar(self, app, pal, scr, y0, y1, x0, W):
        """'Made for you' — same-vibe picks, cached, refreshed in background."""
        cache = app.store.similar or {}
        items = cache.get("items") or []
        seed = cache.get("seed") or ""
        kind = cache.get("kind") or "artist"
        if y0 + 2 >= y1 - 1:
            return y0
        put(scr, y0, x0 + 2, "Made for you", pal["text"], curses.A_BOLD)
        if seed:
            label = (f"· {wcut(seed, 18)}" if kind == "artist"
                     else f"· after “{wcut(seed, 16)}”")
            put(scr, y0, x0 + 16, label, pal["faint"])
        if not items:
            msg = (f"Looking for songs in the style of {wcut(seed, 20)}…"
                   if seed else
                   "Play something — we'll bring songs in the same style")
            put(scr, y0 + 1, x0 + 2, msg, pal["dim"])
            return y0 + 3
        cw = 20
        per = max(1, (W - x0 - 4) // cw)
        for i, t in enumerate(items[:per]):
            x = x0 + 2 + i * cw
            draw_art(scr, y0 + 1, x, 8, 3, t["id"], pal,
                     art=app.cover_for(t["id"], 8, 3))
            put(scr, y0 + 4, x, wcut(t["title"], cw - 2), pal["text"])
            put(scr, y0 + 5, x, wcut(t["artist"], cw - 2), pal["dim"])
            self.hit(x, y0 + 1, cw - 1, 5, "row", ("similar:", i, True))
        return y0 + 6

    def _home_history(self, app, pal, scr, y0, y1, x0, W):
        """'Recently played' — the real play history (mouse = play)."""
        hist = app.store.history
        if not hist or y0 + 1 >= y1 - 1:
            return y0
        put(scr, y0, x0 + 2, "Recently played", pal["text"], curses.A_BOLD)
        w = W - x0 - 4
        title_w = max(12, int(w * 0.62))
        n = 0
        for i, t in enumerate(hist):
            y = y0 + 1 + i
            if y >= y1 - 2 or i >= 5:
                break
            self.homerow(y, x0 + 2, w, t, i, title_w, vk="history:")
            n += 1
        return y0 + 1 + n

    def homerow(self, y, x0, w, t, idx, title_w, vk="liked:"):
        """Compact real-data line on home; mouse = play, hover = Spotify row."""
        app, pal = self.app, self.pal
        scr = self.scr
        play = (app.current and app.current["id"] == t["id"]
                and not app.mpv.state["idle"])
        put(scr, y, x0, eq_bars(app) if play else f"{idx + 1}",
            pal["green"] if play else pal["faint"],
            curses.A_BOLD if play else 0)
        put(scr, y, x0 + 4, wcut(t["title"], title_w),
            pal["green"] if play else pal["text"],
            curses.A_BOLD if play else 0)
        ax = x0 + 4 + title_w + 2
        put(scr, y, ax, wcut(t["artist"], max(2, x0 + w - 9 - ax)),
            pal["dim"])
        if t["id"] in app.liked_ids:
            put(scr, y, x0 + w - 8, IC_HEART, pal["green"], curses.A_BOLD)
        put(scr, y, x0 + w - 6, fmt_t(t.get("dur")).rjust(5), pal["dim"])
        self.hit(x0, y, w, 1, "row", (vk, idx, False))

    def _home_recent(self, app, pal, scr, y0, y1, x0, W):
        """Recent searches as pills, like the search view."""
        recs = app.store.recent
        if not recs or y0 + 1 >= y1 - 1:
            return y0
        put(scr, y0, x0 + 2, "Recent searches", pal["text"], curses.A_BOLD)
        x = x0 + 2
        y = y0 + 2
        for q in recs:
            w = dlen(q) + 4
            if x + w > W - 4:
                x = x0 + 2
                y += 2
            if y >= y1 - 2:
                break
            fill(scr, y, x, w, pal["pill"])
            put(scr, y, x + 2, q, pal["pilldim"])
            self.hit(x, y, w, 1, "recent", q)
            x += w + 1
        return y + 1

    def v_search(self, y0, y1, x0, W):
        app, pal = self.app, self.pal
        scr = self.scr
        mw = W - x0
        if app.searching:
            put(scr, y0 + 1, x0 + 2,
                SPIN[(app.frame // 3) % len(SPIN)] + " Searching…",
                pal["dim"])
            return
        if not app.query:
            put(scr, y0 + 1, x0 + 2, "Recent searches", pal["text"],
                curses.A_BOLD)
            y = y0 + 3
            x = x0 + 2
            for q in app.store.recent:
                w = dlen(q) + 4
                if x + w > W - 4:
                    x = x0 + 2
                    y += 2
                fill(scr, y, x, w, pal["pill"])
                put(scr, y, x + 2, q, pal["pilldim"])
                self.hit(x, y, w, 1, "recent", q)
                x += w + 1
            if not app.store.recent:
                put(scr, y, x0 + 2, f"Type in the search bar above — press / "
                                    "to start", pal["faint"])
            return

        tracks = app.results
        if not tracks:
            put(scr, y0 + 1, x0 + 2,
                f"No results found for “{wcut(app.query, mw - 30)}”",
                pal["dim"])
            put(scr, y0 + 2, x0 + 2,
                "Check spelling, or try fewer / different words",
                pal["faint"])
            return

        top = tracks[0]
        cw = min(34, mw - 4)
        ch = 9
        # card only when width fits a side list AND rows remain below it
        card = ((W - (x0 + cw + 6) - 2) >= 40
                and (y1 - y0) - (ch + 3) >= 5)
        if card:
            box(scr, y0 + 1, x0 + 2, cw, ch, pal["faint"], pal["text"])
            draw_art(scr, y0 + 2, x0 + 4, cw - 4, 3, top["id"], pal,
                     icon=IC_NOTE,
                     art=app.cover_for(top["id"], cw - 4, 3))
            put(scr, y0 + 5, x0 + 4, wcut(top["title"], cw - 6), pal["text"],
                curses.A_BOLD)
            put(scr, y0 + 6, x0 + 4, wcut(f"Song • {top['artist']}", cw - 6),
                pal["dim"])
            self.hit(x0 + 2, y0 + 1, cw, ch, "row", ("search:", 0, True))
            # footer: like · duration · add to queue · play, all clickable
            fy = y0 + 7
            l0 = top["id"] in app.liked_ids
            put(scr, fy, x0 + 4, IC_HEART if l0 else IC_HEARTO,
                pal["green"] if l0 else pal["sdim"], curses.A_BOLD)
            self.hit(x0 + 3, fy, 2, 1, "likesong", top)
            put(scr, fy, x0 + 8, fmt_t(top.get("dur")), pal["faint"])
            put(scr, fy, x0 + cw - 13, IC_PLUS, pal["sdim"], curses.A_BOLD)
            self.hit(x0 + cw - 14, fy, 2, 1, "addq", top)
            put(scr, fy, x0 + cw - 6, f" {IC_PLAY} ", pal["btn"],
                curses.A_BOLD)
            self.hit(x0 + cw - 7, fy, 3, 1, "row", ("search:", 0, True))

            ly0 = y0 + 1
            lx0 = x0 + cw + 4
            lw = W - lx0 - 2
            put(scr, ly0, lx0 + 2, "Songs", pal["text"], curses.A_BOLD)
            ly0 += 1
            for i in range(1, min(6, len(tracks))):
                t = tracks[i]
                y = ly0 + (i - 1) * 2
                if y + 2 > y0 + ch:
                    break
                self.row(ly0 + (i - 1) * 2, lx0, lw, t, i,
                         "search:", i, compact=True)
            fy0 = y0 + ch + 1
        else:
            # short/narrow terminal: skip the card, list uses the full width
            fy0 = y0 + 1

        put(scr, fy0, x0 + 2, "All", pal["text"], curses.A_BOLD)
        self.list_header(fy0 + 1, x0 + 2, mw - 4, show_date=False)
        self.track_list(fy0 + 2, y1, x0 + 2, mw - 4, tracks, "search:",
                        show_date=False)

    def v_collection(self, y0, y1, x0, W, kind, arg):
        app, pal = self.app, self.pal
        scr = self.scr
        if kind == "liked":
            pl = {"name": "Liked Songs", "tracks": app.store.liked}
        else:
            try:
                pl = app.store.playlists[arg]
            except IndexError:
                return
        eyebrow = "PLAYLIST"
        tracks = pl["tracks"]
        vk = app.key()

        cy = y0 + 1
        # header gradient band in the collection's own colour family
        fi = art_fam(pl["name"])
        band = ["g{0}1", "g{0}1", "g{0}2", "g{0}3"]
        for j, name in enumerate(band):
            fill(scr, cy + j, x0, W - x0, pal[name.format(fi)])
        draw_art(scr, cy, x0 + 2, 10, 4, pl["name"], pal,
                 icon=(IC_HEART if kind == "liked" else IC_NOTE),
                 art=app.cover_for(tracks[0]["id"] if tracks else None, 10, 4))
        hx = x0 + 15
        put(scr, cy, hx, eyebrow, pal[f"g{fi}1"], curses.A_BOLD)
        put(scr, cy + 1, hx, wcut(pl["name"].upper(), W - hx - 4),
            pal[f"g{fi}1"], curses.A_BOLD)
        put(scr, cy + 2, hx, fmt_total(tracks), pal[f"g{fi}d"])

        by = cy + 4
        put(scr, by, x0 + 3, f" {IC_PLAY} ", pal["btn"], curses.A_BOLD)
        self.hit(x0 + 2, by - 1 if by else by, 5, 2, "playall", (vk, tracks))
        put(scr, by, x0 + 9, IC_SHUF,
            pal["green"] if app.shuffle else pal["dim"], curses.A_BOLD)
        self.hit(x0 + 8, by - 1, 3, 2, "shuffle")
        rp = IC_REP + ("¹" if app.repeat == 2 else "")
        put(scr, by, x0 + 13, rp,
            pal["green"] if app.repeat else pal["dim"], curses.A_BOLD)
        self.hit(x0 + 12, by - 1, 3, 2, "repeat")

        ly = by + 2
        self.list_header(ly, x0 + 2, W - x0 - 4, show_date=True)
        self.track_list(ly + 1, y1, x0 + 2, W - x0 - 4, tracks, vk,
                        show_date=True)

    def v_queue(self, y0, y1, x0, W):
        app, pal = self.app, self.pal
        scr = self.scr
        put(scr, y0 + 1, x0 + 2, "Queue", pal["text"], curses.A_BOLD)
        if app.queue:
            put(scr, y0 + 1, x0 + 9,
                f"{len(app.queue)} songs", pal["faint"])
        y = y0 + 3
        if app.current:
            put(scr, y, x0 + 2, "Now playing", pal["dim"], curses.A_BOLD)
            self.row(y + 1, x0 + 2, W - x0 - 4, app.current, 0,
                     "queue:", app.qpos, show_date=False, current=True)
            y += 3
        put(scr, y, x0 + 2, "Next up", pal["dim"], curses.A_BOLD)
        first = max(0, app.qpos + 1)
        if first >= len(app.queue):
            put(scr, y + 1, x0 + 5, "Queue is empty - press a on a song "
                "to add it", pal["faint"])
            return
        # Reuse list scrolling but retain original queue indices for input.
        visible = max(0, y1 - y - 2)
        selected = app.sel.get("queue:", first)
        offset = max(first, app.off.get("queue:", first))
        if selected >= first:
            if selected < offset:
                offset = selected
            elif selected >= offset + visible:
                offset = selected - visible + 1
        offset = max(first, min(offset, max(first, len(app.queue) - visible)))
        app.off["queue:"] = offset
        for j, qi in enumerate(range(offset, min(offset + visible, len(app.queue)))):
            self.row(y + 1 + j, x0 + 2, W - x0 - 4, app.queue[qi], qi,
                     "queue:", qi, show_date=False)

    # --------------------------------------------------------- list bits --
    def list_header(self, y, x0, w, show_date):
        """Column captions that share col_widths() with the rows below."""
        pal = self.pal
        num_w, title_w, chan_w, date_w, dur_w, heart_w = \
            self.col_widths(w, show_date)
        tx = x0 + num_w
        cx = tx + title_w + 2
        put(self.scr, y, tx, "TITLE", pal["faint"], curses.A_BOLD)
        put(self.scr, y, cx, "CHANNEL", pal["faint"], curses.A_BOLD)
        if show_date and date_w:
            put(self.scr, y, cx + chan_w + 2, "DATE ADDED", pal["faint"],
                curses.A_BOLD)
        put(self.scr, y, x0 + w - dur_w, "⏱", pal["faint"], curses.A_BOLD)

    def col_widths(self, w, show_date):
        num_w, dur_w, heart_w = 4, 7, 2
        date_w = 12 if show_date else 0
        fixed = num_w + dur_w + heart_w + date_w + 6
        title_w = max(10, int((w - fixed) * 0.55))
        chan_w = max(8, w - fixed - title_w)
        return num_w, title_w, chan_w, date_w, dur_w, heart_w

    def row(self, y, x0, w, t, idx, vk, real_idx, show_date=False,
            compact=False, current=False):
        app, pal = self.app, self.pal
        scr = self.scr
        selidx = app.sel.get(vk, 0)
        selected = (real_idx == selidx and not current)
        playing = (app.current and app.current["id"] == t["id"]
                   and not app.mpv.state["idle"])
        num_w, title_w, chan_w, date_w, dur_w, heart_w = \
            self.col_widths(w, show_date)
        if compact:
            num_w = 3
            date_w = 0

        base = {"text": pal["hover"], "dim": pal["hdim"],
                "green": pal["hgreen"], "faint": pal["hdim"]}
        cp = (lambda n: base.get(n, n)) if selected else (lambda n: n)

        if selected:
            fill(scr, y, x0, w, pal["hover"])

        # number / play / eq — all right-aligned on the same column edge
        if playing:
            put(scr, y, x0 + num_w - 4, eq_bars(app)[:3], pal["green"],
                curses.A_BOLD)
        elif selected:
            put(scr, y, x0 + num_w - 2, IC_PLAY, pal["green"], curses.A_BOLD)
        else:
            put(scr, y, x0 + num_w - 3,
                str(idx + 1).rjust(2) if not compact else "·",
                pal["faint"] if not compact else pal["dim"])

        tx = x0 + num_w
        put(scr, y, tx, wcut(t["title"], title_w),
            pal["green"] if playing else cp(pal["text"]),
            curses.A_BOLD if (playing or selected) else 0)

        cx = tx + title_w + 2
        put(scr, y, cx, wcut(t["artist"], chan_w), cp(pal["dim"]))

        if show_date and date_w:
            dx = cx + chan_w + 2
            put(scr, y, dx, wcut(t.get("added") or "—", date_w), pal["faint"])

        lx = x0 + w - dur_w - heart_w - 2
        liked = t["id"] in app.liked_ids
        if liked or selected:
            put(scr, y, lx, IC_HEART if liked else IC_HEARTO,
                pal["green"] if liked else cp(pal["dim"]))
        put(scr, y, x0 + w - dur_w, fmt_t(t.get("dur")).rjust(dur_w - 1),
            cp(pal["dim"]))

        self.hit(x0, y, w, 1, "row", (vk, real_idx, False))

    def track_list(self, y0, y1, x0, w, tracks, vk, show_date):
        app, pal = self.app, self.pal
        scr = self.scr
        n = y1 - y0
        if n <= 0:
            return
        if not tracks:
            if vk.startswith("liked:"):
                msg = "Songs you like will appear here — press l while playing"
            elif vk.startswith("queue"):
                msg = "Queue is empty — press a on a song to add it"
            else:
                msg = "Empty — search a song with /, then press a to add it"
            cy = y0 + max(0, (n - 1) // 2)
            if n >= 2:
                put(scr, cy - 1, x0 + w // 2 - 1, IC_NOTE, pal["faint"])
            put(scr, cy, x0 + max(2, (w - dlen(msg)) // 2), msg, pal["faint"])
            return
        s = app.sel.get(vk, 0)
        s = max(0, min(s, len(tracks) - 1))
        app.sel[vk] = s
        off = app.off.get(vk, 0)
        off = max(0, min(off, max(0, len(tracks) - n)))
        if s < off:
            off = s
        if s >= off + n:
            off = s - n + 1
        app.off[vk] = off
        overflow = len(tracks) > n
        eff_w = w - 2 if overflow else w
        for i in range(off, min(off + n, len(tracks))):
            self.row(y0 + (i - off), x0, eff_w, tracks[i], i, vk, i,
                     show_date=show_date)
        if overflow:                    # thin scrollbar, Spotify-style
            thumb = max(1, n * n // len(tracks))
            pos = off * (n - thumb) // max(1, len(tracks) - n)
            for yy in range(y0, y0 + n):
                fill(scr, yy, x0 + eff_w, 1, pal["sbtrack"])
            for yy in range(y0 + pos, y0 + pos + thumb):
                fill(scr, yy, x0 + eff_w, 1, pal["sbthumb"])

    # ------------------------------------------------------------ player --
    def playerbar(self, y0, W):
        app, pal = self.app, self.pal
        scr = self.scr
        fill(scr, y0 - 1, 0, W, pal["fade"])  # 1px separator, Spotify-style
        for j in range(3):
            fill(scr, y0 + j, 0, W, pal["bside"])

        cur = app.current
        # left block shrinks on narrow terminals
        tw = 30 if W >= 104 else (24 if W >= 80 else 20)
        hx = 7 + tw + 1            # heart column
        if cur:
            draw_art(scr, y0, 2, 3, 2, cur["id"], pal)
            if (not app.mpv.state["idle"] and not app.mpv.state["pause"]
                    and not app.loading):
                # tiny equalizer riding the cover art, like Spotify's ember
                fi = art_fam(cur["id"])
                put(scr, y0 + 1, 2, eq_bars(app)[:3], pal[f"g{fi}1"],
                    curses.A_BOLD)
            put(scr, y0, 7, wcut(cur["title"], tw), pal["bside"], curses.A_BOLD)
            put(scr, y0 + 1, 7, wcut(cur["artist"], tw), pal["bsdim"])
            liked = cur["id"] in app.liked_ids
            put(scr, y0, hx, IC_HEART if liked else IC_HEARTO,
                pal["bsgreen"] if liked else pal["bsdim"], curses.A_BOLD)
            self.hit(hx - 1, y0, 2, 2, "heart")

        # geometry: right block reserves its columns first so the
        # full-length seekbar can exactly fill the middle (Spotify)
        narrow = W < 86
        rz = W - 18 if narrow else W - 24   # first column the right block owns
        qw = W - 18 if narrow else W - 22
        vw = 6 if narrow else 10
        vx = (W - 11) if narrow else (W - 20)
        spx = vx - 4                        # speaker glyph column
        bx = hx + 4                         # seekbar starts after the heart
        bw = max(16, min(132, spx - bx - 6))
        cx = max(hx + 4, (W - 22) // 2)     # transport cluster centered
        if cx + 22 > rz:
            cx = max(hx + 4, rz - 22)
        x = cx
        put(scr, y0, x, IC_SHUF,
            pal["bsgreen"] if app.shuffle else pal["bsdim"], curses.A_BOLD)
        self.hit(x, y0, 1, 1, "shuffle")
        x += 3
        put(scr, y0, x, IC_PREV, pal["bside"], curses.A_BOLD)
        self.hit(x - 1, y0, 3, 1, "prev")
        x += 4
        glyph = IC_PAUSE if (cur and not app.mpv.state["idle"]
                             and not app.mpv.state["pause"]) else IC_PLAY
        if app.loading:
            glyph = SPIN[(app.frame // 3) % len(SPIN)]
        put(scr, y0, x, f" {glyph} ", pal["btn"], curses.A_BOLD)
        self.hit(x - 1, y0, 5, 1, "toggle")
        x += 6
        put(scr, y0, x, IC_NEXT, pal["bside"], curses.A_BOLD)
        self.hit(x - 1, y0, 3, 1, "next")
        x += 4
        rp = IC_REP + ("¹" if app.repeat == 2 else "")
        put(scr, y0, x, rp,
            pal["bsgreen"] if app.repeat else pal["bsdim"], curses.A_BOLD)
        self.hit(x, y0, 2, 1, "repeat")

        # --- center: progress
        st = app.mpv.state
        dur = st["dur"] or (cur or {}).get("dur") or 0
        pos = min(st["pos"], dur) if dur else st["pos"]
        frac = (pos / dur) if dur else 0.0
        put(scr, y0 + 1, bx - 5, fmt_t(pos).rjust(4), pal["bsdim"])
        for i in range(bw):
            if abs(i - frac * bw) < 0.5:
                ch, p = "●", pal["bsgreen"]
            else:
                ch = "─"
                p = pal["bsdim"] if i <= frac * bw else pal["bbar"]
            put(scr, y0 + 1, bx + i, ch, p,
                curses.A_BOLD if ch == "●" else 0)
        put(scr, y0 + 1, bx + bw + 1, fmt_t(dur), pal["bsdim"])
        self.hit(bx, y0 + 1, bw, 1, "seek", (bx, bw))

        # --- right: queue + volume (squeezed on narrow terminals)
        put(scr, y0, qw, IC_QUEUE, pal["bsdim"], curses.A_BOLD)
        self.hit(qw - 1, y0, 3, 1, "queue")
        put(scr, y0 + 1, vx - 4, IC_SPK + "))", pal["bsdim"])
        for i in range(vw):
            if abs(i - app.mpv.state["vol"] / 100 * (vw - 1)) < 0.5:
                ch, p = "●", pal["bsgreen"]
            else:
                ch = "─"
                p = pal["bsdim"] \
                    if i <= app.mpv.state["vol"] / 100 * vw else pal["bbar"]
            put(scr, y0 + 1, vx + i, ch, p)
        put(scr, y0 + 1, vx + vw + 1, str(app.mpv.state["vol"]).rjust(3),
            pal["bsdim"])
        self.hit(vx, y0 + 1, vw, 1, "vol", (vx, vw))

    # ---------------------------------------------------------- overlays --
    def toast(self, y0, W):
        app, pal = self.app, self.pal
        msg, until = app.toast
        if time.time() >= until or not msg:
            return
        s = f" ✓ {msg} "
        x = max(0, W - dlen(s) - 2)
        fill(self.scr, y0, x, dlen(s) + 1, pal["toast"])
        put(self.scr, y0, x, wcut(s, W - x - 1), pal["toast"])

    def help(self, y0, W):
        app, pal = self.app, self.pal
        rows = [
            ("/", "focus search"), ("j/k or ↑/↓", "move"),
            ("Enter", "play selection"), ("Space", "play / pause"),
            ("n / p", "next / prev"), ("← / →", "seek ±10s"),
            ("+ / -", "volume"), ("a", "add to queue"),
            ("l", "like / unlike"), ("s", "shuffle"),
            ("r", "repeat"), ("R", "new picks"),
            ("v", "queue view"),
            ("c", "create playlist"), ("P", "add to playlist"),
            ("d", "delete from list"), ("e / D", "rename / delete playlist"),
            ("Backspace", "back"),
            ("?", "this help"), ("q", "quit"),
        ]
        w = min(70, W - 6)
        two = w >= 62
        per_col = (len(rows) + 1) // 2 if two else len(rows)
        h = per_col + 5
        y = max(3, y0 - h // 2 - 2)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        put(self.scr, y + 1, x + 2, "Keyboard shortcuts", pal["side"],
            curses.A_BOLD)
        cols = [rows[:per_col], rows[per_col:]] if two else [rows]
        colw = (w - 4) // len(cols)
        for ci, col in enumerate(cols):
            xx = x + 2 + ci * colw
            for i, (k, d) in enumerate(col):
                yy = y + 3 + i
                put(self.scr, yy, xx, wcut(k, 10).ljust(11), pal["sgreen"],
                    curses.A_BOLD)
                put(self.scr, yy, xx + 11, wcut(d, colw - 13), pal["sdim"])
        put(self.scr, y + h - 2, x + 2, "Esc or ? to close", pal["sfaint"])
        self.hit(x, y, w, h, "helpclose")

    def name_modal(self, y0, W):
        app, pal = self.app, self.pal
        w, h = 50, 7
        y = max(2, y0 - 8)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        label = "Rename playlist" if app.rename_index is not None else "Create playlist"
        put(self.scr, y + 1, x + 2, label, pal["side"],
            curses.A_BOLD)
        fill(self.scr, y + 3, x + 2, w - 4, pal["pill"])
        put(self.scr, y + 3, x + 3, wcut(app.name_buf, w - 8), pal["pill"],
            curses.A_BOLD)
        app.name_xy = (x + 3 + min(dlen(app.name_buf), w - 9), y + 3)
        put(self.scr, y + h - 2, x + 2, "Enter: save · Esc: cancel",
            pal["sfaint"])

    def pick_modal(self, y0, W):
        app, pal = self.app, self.pal
        w = 44
        h = min(len(app.pick_rows) + 4, 14)
        y = max(1, (self.scr.getmaxyx()[0] - h) // 2)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        put(self.scr, y + 1, x + 2, "Add to playlist", pal["side"],
            curses.A_BOLD)
        count = max(1, h - 4)
        start = max(0, min(app.pick_idx - count + 1,
                           len(app.pick_rows) - count))
        for i in range(start, min(start + count, len(app.pick_rows))):
            r = app.pick_rows[i]
            yy = y + 3 + i - start
            if i == app.pick_idx:
                fill(self.scr, yy, x + 2, w - 4, pal["hover"])
            put(self.scr, yy, x + 4, wcut(r["name"], w - 8),
                pal["hover"] if i == app.pick_idx else pal["sdim"],
                curses.A_BOLD if i == app.pick_idx else 0)
            self.hit(x, yy, w, 1, "pickrow", i)

    def delete_modal(self, W):
        app, pal = self.app, self.pal
        w, h = min(56, W - 4), 7
        y = max(1, (self.scr.getmaxyx()[0] - h) // 2)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        name = app.store.playlists[app.delete_index]["name"]
        put(self.scr, y + 1, x + 2, "Delete playlist?", pal["side"], curses.A_BOLD)
        put(self.scr, y + 3, x + 2, wcut(name, w - 4), pal["sdim"])
        put(self.scr, y + 5, x + 2, "y: delete playlist   n / Esc: cancel", pal["sfaint"])

    # -------------------------------------------------------------- draw --
    def draw(self):
        app = self.app
        scr = self.scr
        pal = self.pal
        H, W = scr.getmaxyx()
        app.rects = []
        scr.erase()
        if H < 16 or W < 72:
            put(scr, H // 2, 2, "Terminal too small — SpotUI needs ≥ 72×16",
                0)
            scr.noutrefresh()
            curses.doupdate()
            return
        # solid #121212 canvas first — no transparent gaps showing the
        # terminal's own background as patchwork boxes around text
        for y in range(H):
            fill(scr, y, 0, W, pal["text"])
        SW = max(24, min(32, W // 4))
        y1 = H - 3
        app.sw_bounds = (SW, 3, y1)
        self.topbar(0, W, SW)
        self.sidebar(3, y1, SW)
        self.main(3, y1, SW, W)
        self.playerbar(H - 3, W)
        if app.show_help:
            self.help(3, W)
        if app.mode == "name":
            self.name_modal(y1, W)
        if app.mode == "pick":
            self.pick_modal(y1, W)
        if app.mode == "confirm_delete":
            self.delete_modal(W)
        self.toast(y1 - 1, W)
        # cursor for text input
        if app.mode == "search" and hasattr(app, "search_xy"):
            try:
                scr.move(app.search_xy[1], app.search_xy[0])
                curses.curs_set(1)
            except curses.error:
                pass
        else:
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            if app.mode == "name" and hasattr(app, "name_xy"):
                try:
                    scr.move(app.name_xy[1], app.name_xy[0])
                    curses.curs_set(1)
                except curses.error:
                    pass
        scr.noutrefresh()
        curses.doupdate()


# ------------------------------------------------------------------ input --
def handle_key(app, k):
    if k is None:
        return
    if app.mode == "search":
        if isinstance(k, str):
            if k in ("\n", "\r"):
                app.mode = "normal"
                app.do_search(app.query)
                return
            if k == "\x1b":
                app.mode = "normal"
                return
            if k in ("\x7f", "\b"):
                app.query = app.query[:-1]
                return
            if k >= " " and unicodedata.category(k)[0] != "C":
                app.query += k
                return
        else:
            if k in (curses.KEY_BACKSPACE, 127, 8, 263):
                app.query = app.query[:-1]
            elif k == curses.KEY_ENTER or k == 10 or k == 13:
                app.mode = "normal"
                app.do_search(app.query)
            elif k == 27:
                app.mode = "normal"
        return

    if app.mode == "confirm_delete":
        if k in ("y", "Y"):
            app.delete_playlist(app.delete_index)
            app.delete_index = None
            app.mode = "normal"
        elif k in ("n", "N", "q", "\x1b", 27):
            app.delete_index = None
            app.mode = "normal"
        return

    if app.mode == "name":
        if k in ("\n", "\r", curses.KEY_ENTER, 10, 13):
            if app.rename_index is not None:
                app.rename_playlist(app.rename_index, app.name_buf)
            else:
                app.create_playlist(app.name_buf)
                if app.pick_pending:
                    app.add_to_playlist(len(app.store.playlists) - 1,
                                        app.pick_pending)
            app.pick_pending = None
            app.rename_index = None
            app.name_buf = ""
            app.mode = "normal"
        elif k in ("\x1b", 27):
            app.name_buf = ""
            app.pick_pending = None
            app.rename_index = None
            app.mode = "normal"
        elif k in ("\x7f", "\b", curses.KEY_BACKSPACE, 127, 8, 263):
            app.name_buf = app.name_buf[:-1]
        elif isinstance(k, str) and k >= " " and unicodedata.category(k)[0] != "C":
            app.name_buf += k
        return

    if app.mode == "pick":
        n = len(app.pick_rows)
        if k == curses.KEY_UP or k == "k":
            app.pick_idx = max(0, app.pick_idx - 1)
        elif k == curses.KEY_DOWN or k == "j":
            app.pick_idx = min(n - 1, app.pick_idx + 1)
        elif k in ("\n", "\r", curses.KEY_ENTER, 10, 13):
            r = app.pick_rows[app.pick_idx]
            app.mode = "normal"
            if r["new"]:
                app.mode = "name"
                app.name_buf = ""
            else:
                app.add_to_playlist(app.pick_idx - 1, app.pick_pending)
                app.pick_pending = None
        elif k == "\x1b" or k == 27 or k == "q":
            app.mode = "normal"
            app.pick_pending = None
        return

    # normal mode
    if app.show_help:
        if k == "\x1b" or k == 27 or k == "?" or k == "q":
            app.show_help = False
            if k == "q":
                app.quit = True
        return

    kind, arg = app.stack[-1]
    vk = app.key()

    if isinstance(k, str):
        if k == "q":
            app.quit = True
        elif k == "/":
            app.push("search")
            app.mode = "search"
        elif k == "?":
            app.show_help = True
        elif k == " ":
            app.toggle()
        elif k == "j":
            app.move_sel(1, len(app.view_tracks()))
        elif k == "k":
            app.move_sel(-1, len(app.view_tracks()))
        elif k in ("\n", "\r"):
            if kind == "home":
                idx = app.sel.get("home:", 0)
                if os.environ.get("SPOTUI_DEBUG"):
                    open("/tmp/spotui-debug.log", "a").write(
                        f"home-enter idx={idx} sel={dict(app.sel)}\n")
                tiles = [("liked", "liked", None)] + [
                    ("playlist", "playlist", i)
                    for i in range(len(app.store.playlists))]
                if 0 <= idx < len(tiles):
                    app.push(tiles[idx][1], tiles[idx][2])
            elif kind == "search":
                if app.results:
                    app.play_row("search:", app.sel_row())
            else:
                app.play_row(vk, app.sel_row())
        elif k == "n":
            app.next()
        elif k == "p":
            app.prev()
        elif k == "P":
            t = app.track_under() or app.current
            if t:
                app.open_pick(t)
            else:
                app.toast_now("Nothing selected — play or pick a song first")
        elif k == "a":
            app.add_queue(app.track_under() or app.current)
        elif k == "l":
            app.like(app.track_under() or app.current)
        elif k == "s":
            app.toggle_shuffle()
        elif k == "R":
            app.refresh_similar(force=True)
            app.toast_now("Finding new picks…")
        elif k == "r":
            app.cycle_repeat()
        elif k == "v":
            app.push("queue")
        elif k == "e" and kind == "playlist":
            app.rename_index = arg
            app.name_buf = app.store.playlists[arg]["name"]
            app.mode = "name"
        elif k == "D" and kind == "playlist":
            app.delete_index = arg
            app.mode = "confirm_delete"
        elif k == "c":
            app.rename_index = None
            app.mode = "name"
            app.name_buf = ""
        elif k == "d":
            app.delete_selected()
        elif k == "+" or k == "=":
            app.vol(+5)
        elif k == "-":
            app.vol(-5)
        elif k == "\x7f" or k == "\b":
            app.back()
        return

    # special keys (int)
    if k == curses.KEY_DOWN:
        app.move_sel(1, len(app.view_tracks()))
    elif k == curses.KEY_UP:
        app.move_sel(-1, len(app.view_tracks()))
    elif k == curses.KEY_RIGHT:
        app.mpv.seek_rel(10)
    elif k == curses.KEY_LEFT:
        app.mpv.seek_rel(-10)
    elif k in (curses.KEY_ENTER, 10, 13):
        if kind == "home":
            handle_key(app, "\n")
        else:
            app.play_row(vk, app.sel_row())
    elif k in (curses.KEY_BACKSPACE, 127, 8, 263):
        app.back()
    elif k == curses.KEY_NPAGE:
        app.move_sel(8, len(app.view_tracks()))
    elif k == curses.KEY_PPAGE:
        app.move_sel(-8, len(app.view_tracks()))
    elif k == curses.KEY_HOME:
        k2 = app.key()
        app.sel[k2] = 0
    elif k == curses.KEY_END:
        k2 = app.key()
        app.sel[k2] = max(0, len(app.view_tracks()) - 1)


def handle_mouse(app):
    try:
        _, mx, my, _, bstate = curses.getmouse()
    except curses.error:
        return
    if bstate & curses.BUTTON4_PRESSED:
        if app.sw_bounds and mx < app.sw_bounds[0]:
            app.soff = max(0, min(getattr(app, "soff_max", 0),
                                  app.soff - 2))
        else:
            app.move_sel(-3, len(app.view_tracks()))
        return
    if bstate & getattr(curses, "BUTTON5_PRESSED", 0):
        if app.sw_bounds and mx < app.sw_bounds[0]:
            app.soff = max(0, min(getattr(app, "soff_max", 0),
                                  app.soff + 2))
        else:
            app.move_sel(3, len(app.view_tracks()))
        return
    if not (bstate & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED
                      | curses.BUTTON1_DOUBLE_CLICKED | curses.BUTTON1_TRIPLE_CLICKED)):
        return
    dbl = bool(bstate & (curses.BUTTON1_DOUBLE_CLICKED
                         | curses.BUTTON1_TRIPLE_CLICKED))
    # while a modal is open, only the modal's own controls respond
    blocked = app.show_help or app.mode in ("name", "pick", "confirm_delete")
    allowed = {"helpclose"} if app.show_help else ({"pickrow"} if app.mode == "pick" else set())
    for r in reversed(app.rects):
        if not (r["x0"] <= mx < r["x1"] and r["y0"] <= my < r["y1"]):
            continue
        act, arg = r["act"], r["arg"]
        if blocked and act not in allowed:
            return
        if act == "noop":
            return
        if act == "back":
            app.back()
        elif act == "help":
            app.show_help = True
        elif act == "helpclose":
            app.show_help = False
        elif act == "focus_search":
            app.mode = "search"
        elif act == "nav":
            app.push(arg)
        elif act == "libitem":
            app.push(arg[0], arg[1])
        elif act == "create":
            app.mode = "name"
            app.name_buf = ""
        elif act == "tile":
            app.push(arg[0], arg[1])
        elif act == "recent":
            app.query = arg
            app.mode = "search"
            app.do_search(arg)
        elif act == "row":
            vk, idx, force = arg
            app.sel[vk] = idx
            if force or dbl:
                app.play_row(vk, idx)
            else:
                # second click on same row within 0.6s plays (Spotify-ish)
                if app._last_row == (vk, idx) and \
                        time.time() - app._last_row_t < 0.6:
                    app.play_row(vk, idx)
                    app._last_row = None
                else:
                    app._last_row = (vk, idx)
                    app._last_row_t = time.time()
        elif act == "playall":
            vk2, tracks = arg
            if tracks:
                app.play(tracks, 0)
        elif act == "shuffle":
            app.toggle_shuffle()
        elif act == "repeat":
            app.cycle_repeat()
        elif act == "toggle":
            app.toggle()
        elif act == "prev":
            app.prev()
        elif act == "next":
            app.next()
        elif act == "heart":
            app.like(app.current)
        elif act == "likesong":
            app.like(arg)
        elif act == "addq":
            app.add_queue(arg)
        elif act == "queue":
            app.push("queue")
        elif act == "seek":
            bx, bw = arg
            frac = min(1.0, max(0.0, (mx - bx) / max(1, bw - 1)))
            if app.mpv.state["dur"]:
                app.mpv.seek_abs(frac * app.mpv.state["dur"])
        elif act == "vol":
            vx, vw = arg
            frac = min(1.0, max(0.0, (mx - vx) / max(1, vw - 1)))
            app.vol(absolute=round(frac * 100))
        elif act == "pickrow":
            app.pick_idx = arg
            handle_key(app, "\n")
        return

# ------------------------------------------------------------------ main ---
def run(scr):
    scr.keypad(True)
    curses.noecho()
    curses.cbreak()
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    scr.timeout(90)
    try:
        curses.mousemask(
            curses.BUTTON1_PRESSED | curses.BUTTON1_RELEASED
            | curses.BUTTON1_CLICKED | curses.BUTTON1_DOUBLE_CLICKED
            | curses.BUTTON4_PRESSED | getattr(curses, "BUTTON5_PRESSED", 0))
    except curses.error:
        pass

    def _resume(signum, frame):
        # Ctrl+Z → Ctrl+V resume: re-enter program mode and force repaint
        try:
            curses.reset_prog_mode()
            curses.noecho()
            curses.cbreak()
            scr.keypad(True)
            scr.timeout(90)
            scr.clearok(True)
            scr.refresh()
        except Exception:
            pass

    def _suspend(signum, frame):
        try:
            curses.endwin()
        except Exception:
            pass
        signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTSTP)

    signal.signal(signal.SIGTSTP, _suspend)
    signal.signal(signal.SIGCONT, _resume)

    app = App()
    app.pal = Pal(scr)
    app._last_row = None
    app._last_row_t = 0.0
    ui = UI(app, scr)
    threading.Thread(target=app.mpv.watch, daemon=True).start()

    try:
        ui.splash(scr)          # opening animation (any key skips)
    except Exception:
        pass

    if not HAVE_YTDL:
        app.toast_now("yt-dlp missing — run ./install.sh first")
    if app.store.error:
        app.toast_now(app.store.error)
    app.refresh_similar()

    try:
        while not app.quit:
            app.frame += 1
            if app.mpv.on_end.is_set():
                app.mpv.on_end.clear()
                app.next(auto=True)
            try:
                ui.draw()
            except curses.error:
                pass
            try:
                k = scr.get_wch()
            except curses.error:
                continue
            if k == curses.KEY_RESIZE:
                continue
            if k == curses.KEY_MOUSE:
                try:
                    handle_mouse(app)
                except Exception:
                    pass
                continue
            try:
                if os.environ.get("SPOTUI_DEBUG"):
                    open("/tmp/spotui-debug.log", "a").write(
                        f"key={k!r} mode={app.mode}\n")
                handle_key(app, k)
            except Exception:
                pass
    finally:
        app.quit = True
        app.load_token += 1
        try:
            app.pal.restore()
        except Exception:
            pass
        app.store.save()
        app.mpv.stop()


def main():
    locale.setlocale(locale.LC_ALL, "")
    if not sys.stdout.isatty():
        print("SpotUI needs a terminal.", file=sys.stderr)
        sys.exit(1)
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
