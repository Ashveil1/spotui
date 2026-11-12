#!/usr/bin/env python3
"""
SpotUI — a Spotify-style terminal player, powered by YouTube + mpv.

Layout mimics Spotify desktop: top bar with search pill, black sidebar,
#121212 main area, and a full now-playing bar. Light on RAM: curses + mpv.
"""

import base64
import curses
import json
import locale
import math
import os
import re
import signal
import shutil
import shlex
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
EXPORT_DIR = Path.home() / "spotui-exports"

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
IC_HIST = "↺"
IC_STATS = "▤"
IC_AUTO = "✦"
IC_PIN = "★"

# seconds before a sleep timer fires when the volume starts to fade
FADE_SECS = 20

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


def scroll_window(text, width, tick, hold=6):
    """A sliding window over a too-long title: hold at the start, scroll
    one cell per tick, hold at the end, then jump back to the start."""
    if width <= 0 or dlen(text) <= width:
        return text
    span = len(text) - width
    cycle = span + hold * 2
    t = tick % cycle
    if t < hold:
        off = 0
    elif t < hold + span:
        off = t - hold
    else:
        off = span
    # plain width-limited slice - no ellipsis, it would read as truncation
    out, used = "", 0
    for ch in text[off:]:
        dw = dwidth(ch)
        if used + dw > width:
            break
        out += ch
        used += dw
    return out


def fmt_t(sec):
    if sec is None:
        return "–:––"
    try:
        sec = int(sec)
    except (TypeError, ValueError, OverflowError):
        return "–:––"
    return f"{sec // 60}:{sec % 60:02d}"


def fmt_ago(ts):
    """'5m' / '2h' / '3d' / '2w' for an epoch timestamp; '' when invalid."""
    try:
        ts = float(ts or 0)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(ts) or ts <= 0:
        return ""
    d = time.time() - ts
    if d < 0:
        return ""
    if d < 3600:
        return f"{max(1, int(d // 60))}m"
    if d < 86400:
        return f"{int(d // 3600)}h"
    if d < 7 * 86400:
        return f"{int(d // 86400)}d"
    return f"{int(d // (7 * 86400))}w"


def fmt_added(v):
    """Date cell for a track: liked stores 'YYYY-MM-DD', history an epoch.

    Epochs render relative: Today / Yesterday / weekday within the last
    week, then the full date.
    """
    if v is None or isinstance(v, bool):
        return "—"
    if isinstance(v, (int, float)):
        if not math.isfinite(v) or v <= 0:
            return "—"
        try:
            lt = time.localtime(v)
            now = time.localtime()
            today0 = time.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                                  0, 0, 0, 0, 0, -1))
            d = int((v - today0) // 86400)
            if d == 0:
                return "Today"
            if d == -1:
                return "Yesterday"
            if -7 < d < -1:
                return time.strftime("%a", lt)
            return time.strftime("%Y-%m-%d", lt)
        except (OverflowError, OSError, ValueError):
            return "—"
    return str(v) if v else "—"


VIEW_HINTS = {
    "search": "Enter plays \u00b7 a queues \u00b7 Q queues all \u00b7 o opens artist \u00b7 Tab switches All/Songs/Artists",
    "liked": "Enter plays \u00b7 a queues \u00b7 l likes \u00b7 m sorts \u00b7 F finds \u00b7 o opens artist",
    "playlist": "Enter plays \u00b7 a queues \u00b7 m sorts \u00b7 J/K reorders \u00b7 e renames \u00b7 N duplicates \u00b7 B merges \u00b7 w pins \u00b7 h enhances \u00b7 L likes all \u00b7 V copies tracklist",
    "history": "Enter plays \u00b7 a queues \u00b7 m sorts \u00b7 F finds \u00b7 D hides repeats \u00b7 X clears",
    "artist": "Enter plays \u00b7 a queues \u00b7 F finds",
    "queue": "J/K or drag reorders \u00b7 C clears upcoming \u00b7 D drops autoplayed \u00b7 W saves as playlist",
    "playing": "Space pause \u00b7 l like \u00b7 v queue \u00b7 chips and Up Next are clickable",
    "stats": "Click a top artist to open it \u00b7 a top song plays \u00b7 Y copies summary \u00b7 Backspace back",
    "similar": "Enter plays \u00b7 a queues \u00b7 R finds new picks \u00b7 Backspace back",
}


def fmt_remaining(tracks):
    """'N min left' / 'N hr M min left' for the queue's unplayed tail."""
    tot = sum(t.get("dur") or 0 for t in tracks)
    if tot <= 0:
        return ""
    m = tot // 60
    if m >= 60:
        return f"{m // 60} hr {m % 60} min left"
    return f"{m} min left"


def fmt_listen(mins):
    """'45 min' / '2 hr 10 min' for a listening-time count."""
    if mins >= 60:
        return f"{mins // 60} hr {mins % 60} min"
    return f"{mins} min"


def fmt_ends(tracks, elapsed=0, now=None):
    """'ends 16:42' - the wall-clock time the given tracks run out."""
    tot = sum(t.get("dur") or 0 for t in tracks) - int(elapsed or 0)
    if tot <= 60:
        return ""
    lt = time.localtime((time.time() if now is None else now) + tot)
    return "ends " + time.strftime("%H:%M", lt)


def plays_for(tracks, plays):
    """Total local play count of a list of tracks (0 when never played)."""
    return sum(plays.get(str(t.get("id")), {}).get("n", 0)
               for t in tracks if isinstance(t, dict))


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
        self.plays = {}
        self.first_play = None
        self.shuffle_mode = "spread"
        self.autoplay = True
        self.time_left = False
        self.eq_preset = "off"
        self.sort_mode = "default"
        self.hist_dedupe = False
        self.zen = False
        self.theme = THEME_NAMES[0]
        self.blocked = []              # song ids hidden from suggestions
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
            if (not isinstance(t.get("dur"), (int, float)) or isinstance(t.get("dur"), bool)
                    or not math.isfinite(t["dur"]) or t["dur"] < 0):
                t["dur"] = None
            out.append(t)
        return out

    def _load(self):
        self.error = None
        self.session = {"queue": [], "pos": 0}
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
                entry = dict(name=pl["name"],
                             tracks=self._tracks(pl.get("tracks")))
                if pl.get("pinned"):
                    entry["pinned"] = True
                if pl.get("enhanced"):
                    entry["enhanced"] = True
                self.playlists.append(entry)
        sess = d.get("session") if isinstance(d.get("session"), dict) else {}
        self.session = {"queue": self._tracks(sess.get("queue"))[:500]}
        try:
            t = float(sess.get("t") or 0)
            if math.isfinite(t) and t > 0:
                self.session["t"] = t
        except (ValueError, TypeError):
            pass
        try:
            self.session["pos"] = int(sess.get("pos", 0))
        except (ValueError, TypeError):
            self.session["pos"] = 0
        self.recent = [q for q in d.get("recent", []) if isinstance(q, str)][:8] if isinstance(d.get("recent"), list) else []
        cache = d.get("similar")
        self.similar = dict(cache) if isinstance(cache, dict) else {}
        for key in ("items", "pool"):
            self.similar[key] = self._tracks(self.similar.get(key))
        try:
            self.last_search = float(d.get("last_search") or 0)
            if not math.isfinite(self.last_search):
                self.last_search = 0.0
        except (ValueError, TypeError):
            pass
        pl = d.get("plays")
        if isinstance(pl, dict):
            for k, v in list(pl.items())[:2000]:
                if (isinstance(k, str) and isinstance(v, dict)
                        and isinstance(v.get("title"), str)
                        and isinstance(v.get("n"), int) and not isinstance(v.get("n"), bool)
                        and v["n"] > 0):
                    self.plays[k] = dict(title=v["title"],
                                         artist=str(v.get("artist") or "Unknown"),
                                         n=v["n"])
        fp = d.get("first_play")
        if (isinstance(fp, (int, float)) and not isinstance(fp, bool)
                and math.isfinite(fp) and fp > 0):
            self.first_play = float(fp)
        if d.get("shuffle_mode") in SHUFFLE_MODES:
            self.shuffle_mode = d["shuffle_mode"]
        if isinstance(d.get("autoplay"), bool):
            self.autoplay = d["autoplay"]
        if isinstance(d.get("time_left"), bool):
            self.time_left = d["time_left"]
        if d.get("eq_preset") in EQ_PRESETS:
            self.eq_preset = d["eq_preset"]
        if d.get("sort_mode") in SORT_MODES:
            self.sort_mode = d["sort_mode"]
        if isinstance(d.get("hist_dedupe"), bool):
            self.hist_dedupe = d["hist_dedupe"]
        if isinstance(d.get("zen"), bool):
            self.zen = d["zen"]
        if isinstance(d.get("blocked"), list):
            self.blocked = [x for x in d["blocked"] if isinstance(x, str)]
        if d.get("theme") in THEMES:
            self.theme = d["theme"]
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
                        "session": self.session, "theme": self.theme,
                        "plays": self.plays, "first_play": self.first_play, "shuffle_mode": self.shuffle_mode, "autoplay": self.autoplay, "time_left": self.time_left, "eq_preset": self.eq_preset,
                        "sort_mode": self.sort_mode,
                        "hist_dedupe": self.hist_dedupe,
                        "zen": self.zen,
                        "blocked": self.blocked,
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
        self.sock_path = os.path.join(tempfile.gettempdir(),
                                      f"spotui-{os.getpid()}.mpv.sock")
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
                     # less silence between songs (mpv still opens each
                     # stream separately, so this is not a crossfade)
                     "--gapless-audio=yes",
                     "--osd-level=0", "--no-osc",       # no font/libass stack
                     # audio-only streams: small in-RAM cache keeps mpv light
                     "--demuxer-max-bytes=10MiB",
                     "--demuxer-max-back-bytes=2MiB",
                     "--cache-on-disk=no",
                     f"--input-ipc-server={self.sock_path}",
                     f"--volume={self.state['vol']}"]
                    + shlex.split(os.environ.get("SPOTUI_MPV_ARGS", "")),
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

    def set_speed(self, v):
        self.cmd(["set_property", "speed", float(v)])

    def set_eq(self, preset):
        self.cmd(["set_property", "af", EQ_FILTER.get(preset, "")])

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


SHUFFLE_MODES = ("spread", "discovery", "mood")
EQ_PRESETS = ("off", "bass", "vocal", "treble")
EQ_LABEL = {"off": "Off", "bass": "Bass boost", "vocal": "Vocal",
            "treble": "Treble boost"}
EQ_FILTER = {"bass": "bass=g=8",
             "vocal": "equalizer=f=2500:w=1500:g=5",
             "treble": "treble=g=6"}
SHUFFLE_LABEL = {"spread": "Artist spread", "discovery": "Discovery (least played first)",
                 "mood": "Your mood (most played first)"}


def smart_shuffle(tracks, previous_artist="", recent_ids=(), rng=None,
                  mode="spread", plays=None):
    """Artist-spaced shuffle, without adding or dropping queue entries.

    Choose the largest remaining artist bucket other than the last artist,
    with random tie-breaking. Randomize songs within buckets but defer recent
    plays. When only one artist remains, adjacent repeats are unavoidable.
    """
    import random
    rng = rng or random
    recent = set(recent_ids)
    buckets = {}
    for t in tracks:
        artist = unicodedata.normalize("NFKC", t.get("artist") or "").casefold().strip()
        buckets.setdefault(artist, []).append(t)
    plays = plays or {}
    count = lambda t: plays.get(str(t.get("id")), {}).get("n", 0)
    for group in buckets.values():
        rng.shuffle(group)
        if mode == "discovery":      # least played first
            group.sort(key=lambda t: (t.get("id") in recent, count(t)))
        elif mode == "mood":         # most played first
            group.sort(key=lambda t: (t.get("id") in recent, -count(t)))
        else:
            group.sort(key=lambda t: t.get("id") in recent)
    out = []
    previous = unicodedata.normalize("NFKC", previous_artist).casefold().strip()
    while buckets:
        choices = [a for a in buckets if a != previous] or list(buckets)
        if mode in ("discovery", "mood"):
            sign = 1 if mode == "discovery" else -1
            artist = min(choices, key=lambda a: sign * sum(count(t) for t in buckets[a])
                         / len(buckets[a]) + rng.random() * 0.5)
        else:
            largest = max(len(buckets[a]) for a in choices)
            artist = rng.choice([a for a in choices if len(buckets[a]) == largest])
        out.append(buckets[artist].pop(0))
        if not buckets[artist]:
            del buckets[artist]
        previous = artist
    return out


SORT_MODES = ("default", "title", "artist", "added", "dur")
SORT_LABEL = {"default": "Default", "title": "Title A-Z",
              "artist": "Artist A-Z", "added": "Recently added",
              "dur": "Longest first"}
SORTABLE_KINDS = ("liked", "playlist", "history")


def sort_tracks(tracks, mode):
    """A sorted copy for list views - the stored order never changes."""
    fold = lambda v: unicodedata.normalize("NFKC", v or "").casefold()
    if mode == "title":
        return sorted(tracks, key=lambda t: (fold(t.get("title")),
                                             fold(t.get("artist"))))
    if mode == "artist":
        return sorted(tracks, key=lambda t: (fold(t.get("artist")),
                                             fold(t.get("title"))))
    if mode == "added":
        return sorted(tracks, key=lambda t: t.get("added") or 0,
                      reverse=True)
    if mode == "dur":
        return sorted(tracks, key=lambda t: t.get("dur") or 0, reverse=True)
    return list(tracks)


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

THEMES = {
    # name: accent, background, hover, raised (pill), avatar  (0-255 RGB)
    "Spotify":  ((29, 185, 84),  (18, 18, 18),  (31, 31, 31),  (42, 42, 42),  (83, 83, 83)),
    "Aurora":   ((167, 139, 250), (16, 14, 30),  (30, 26, 52),  (40, 35, 70),  (90, 80, 140)),
    "Sunset":   ((251, 146, 60),  (24, 16, 14),  (42, 28, 24),  (58, 38, 32),  (120, 80, 60)),
    "Ocean":    ((56, 189, 248),  (10, 20, 30),  (20, 36, 52),  (28, 50, 72),  (60, 100, 130)),
    "Rose":     ((244, 114, 182), (26, 14, 22),  (44, 26, 38),  (60, 36, 52),  (130, 70, 105)),
    "Amber":    ((250, 204, 21),  (20, 18, 10),  (38, 34, 18),  (52, 46, 24),  (110, 98, 50)),
}
THEME_NAMES = list(THEMES)
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
        self.theme = THEME_NAMES[0]
        self.orig = {}
        self._truecolor()

    def can_theme(self):
        try:
            return (not self.mono) and self.n >= 256 and curses.can_change_color()
        except curses.error:
            return False

    def apply_theme(self, name):
        """Re-skin by redefining palette slots; False without palette support."""
        if name not in THEMES or not self.can_theme():
            return False
        self.theme = name
        self._truecolor()
        return True

    def _truecolor(self):
        """Theme palette: redefine terminal color slots (0-1000 RGB)."""
        if self.mono:
            return
        acc, bg, hov, pill, av = THEMES[self.theme]
        k = lambda c: tuple(v * 1000 // 255 for v in c)
        shade = lambda f: tuple(int(v * f) for v in acc)
        slots = {
            41: k(acc), 40: k(acc),
            34: k(shade(.76)), 28: k(shade(.5)), 22: k(shade(.28)),
            233: k(bg), 235: k(hov),
            236: k(tuple((a + b) // 2 for a, b in zip(hov, pill))),
            237: k(pill), 238: k(av),
            244: k((140, 140, 140)),  # faint text
            250: k((179, 179, 179)),  # #b3b3b3 dim text
        }
        for fi, shades in enumerate(FAMS):
            for k, rgb in enumerate(shades):
                slots[ART_SLOTS + fi * 4 + k] = tuple(
                    v * 1000 // 255 for v in rgb)
        try:
            if not curses.can_change_color():
                return
            for slot, rgb in slots.items():
                if slot not in self.orig:
                    self.orig[slot] = curses.color_content(slot)
                curses.init_color(slot, *rgb)
        except curses.error:
            pass

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


def lib_fresh(store):
    """True for a brand-new library: nothing liked, played, or saved yet."""
    return (not store.liked and not store.history and not store.plays
            and not any(p.get("tracks") for p in store.playlists))


def daily_mixes(store, n=3):
    """Mixes built only from songs already in the library, grouped by artist.

    Ranks artists by play count plus how many of their songs you saved; each
    mix is that artist's songs plus songs by artists you also listen to.
    """
    pool, seen = [], set(getattr(store, "blocked", None) or [])
    for src in (store.liked, store.history, store.similar.get("items", []),
                *[p["tracks"] for p in store.playlists]):
        for t in src:
            if t.get("id") not in seen and t.get("title"):
                seen.add(t["id"])
                pool.append(t)
    by_artist = {}
    for t in pool:
        a = unicodedata.normalize("NFKC", t.get("artist") or "").casefold().strip()
        if a:
            by_artist.setdefault(a, []).append(t)
    def score(a):
        played = sum(p["n"] for p in store.plays.values()
                     if unicodedata.normalize("NFKC", p["artist"]).casefold().strip() == a)
        return played * 2 + len(by_artist[a])
    ranked = [a for a in sorted(by_artist, key=lambda a: (-score(a), a))
              if len(by_artist[a]) >= 2][:n]
    others = [a for a in sorted(by_artist, key=lambda a: (-score(a), a))]
    mixes = []
    for i, a in enumerate(ranked):
        tracks = list(by_artist[a])
        extra = [x for x in others if x != a and x not in ranked[:i]][:3]
        for x in extra:
            tracks += by_artist[x][:3]
        mixes.append(dict(name=f"Daily Mix {i + 1}", artist=by_artist[a][0]["artist"],
                          with_=[by_artist[x][0]["artist"] for x in extra[:2]],
                          tracks=tracks))
    return mixes


def stats_minutes(store):
    """Rough listening time: play counts x duration, songs we know the
    length of. Songs without a known duration are skipped, so this is a
    floor - shown as 'about'."""
    dur = {}
    pools = [store.liked, store.history] + [pl["tracks"]
                                            for pl in store.playlists]
    for tracks in pools:
        for t in tracks:
            if t.get("id") and t.get("dur"):
                dur.setdefault(t["id"], t["dur"])
    sec = sum(p["n"] * dur.get(k, 0) for k, p in store.plays.items())
    if sec < 60:
        return ""
    m = sec // 60
    return f"{m // 60} hr {m % 60} min" if m >= 60 else f"{m} min"


def stats_week(store):
    """Plays in the last 7 days, from the (capped) history list."""
    try:
        cutoff = time.time() - 7 * 86400
        return sum(1 for h in store.history
                   if isinstance(h, dict)
                   and math.isfinite(float(h.get("added") or 0))
                   and float(h.get("added") or 0) >= cutoff)
    except (TypeError, ValueError):
        return 0


def stats_streak(store):
    """Consecutive days with at least one play, ending today or yesterday.

    Counted from the (capped) history list. A streak only counts when the
    most recent play is from today or yesterday; an older last play means
    the streak is already broken. Returns the number of days.
    """
    lt = time.localtime()
    today0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                          0, 0, 0, 0, 0, -1))
    days = set()
    for h in store.history:
        if not isinstance(h, dict):
            continue
        try:
            ts = float(h.get("added") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ts):
            continue
        days.add(int((ts - today0) // 86400))
    start = 0 if 0 in days else (-1 if -1 in days else None)
    if start is None:
        return 0
    n, d = 0, start
    while d in days:
        n, d = n + 1, d - 1
    return n


def stats_last_played(store):
    """Video id -> most recent play epoch, from the (capped) history list.

    Entries with missing ids or non-finite timestamps are ignored.
    """
    out = {}
    for h in store.history:
        if not isinstance(h, dict) or not h.get("id"):
            continue
        try:
            ts = float(h.get("added") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ts):
            continue
        if ts > out.get(h["id"], 0):
            out[h["id"]] = ts
    return out

def stats_weekday(store):
    """(name, plays) of the busiest local weekday over the history list.

    All-time, counted from the (capped) history list, not the 7-day window.
    Entries with missing or non-finite timestamps are ignored. Returns None
    when history is thin (< 10 plays) or two weekdays tie for the top, so
    the caption never overclaims.
    """
    counts = [0] * 7
    total = 0
    for h in store.history:
        if not isinstance(h, dict):
            continue
        try:
            ts = float(h.get("added") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ts):
            continue
        counts[time.localtime(ts).tm_wday] += 1
        total += 1
    if total < 10:
        return None
    order = sorted(range(7), key=lambda d: counts[d], reverse=True)
    if counts[order[0]] == 0 or counts[order[0]] == counts[order[1]]:
        return None
    names = ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays",
             "Saturdays", "Sundays")
    return names[order[0]], counts[order[0]]

def stats_days(store):
    """Plays per local day for the last 7 days, oldest first, today last.

    Counted from the (capped) history list, like stats_week(). Entries with
    missing or non-finite timestamps are ignored; future timestamps and
    anything older than 6 days fall outside the window.
    """
    lt = time.localtime()
    today0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                          0, 0, 0, 0, 0, -1))
    counts = [0] * 7
    for h in store.history:
        if not isinstance(h, dict):
            continue
        try:
            ts = float(h.get("added") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ts):
            continue
        idx = int((ts - today0) // 86400)
        if -6 <= idx <= 0:
            counts[6 + idx] += 1
    labels = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    return [(labels[time.localtime(today0 - (6 - i) * 86400).tm_wday],
             counts[i]) for i in range(7)]


def stats_day_minutes(store):
    """Listening minutes per local day for the last 7 days, oldest first.

    Same window and sources as stats_days(), but each history entry counts
    its track duration instead of one play. Entries without a known
    duration are skipped, so these are approximate - like stats_minutes().
    """
    lt = time.localtime()
    today0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                          0, 0, 0, 0, 0, -1))
    sec = [0] * 7
    for h in store.history:
        if not isinstance(h, dict):
            continue
        try:
            ts = float(h.get("added") or 0)
            d = float(h.get("dur") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ts) or not math.isfinite(d) or d <= 0:
            continue
        idx = int((ts - today0) // 86400)
        if -6 <= idx <= 0:
            sec[6 + idx] += d
    return [int(s // 60) for s in sec]


def stats_on_repeat(store, top=5):
    """Songs played 2+ times in the last 7 days, most repeats first.

    Counted from the (capped) history list, like stats_week(). Returns
    [(track, n)] with the history entry as the track. Entries with
    missing/invalid timestamps or no id are ignored.
    """
    cutoff = time.time() - 7 * 86400
    counts, meta = {}, {}
    for h in store.history:
        if not isinstance(h, dict):
            continue
        try:
            ts = float(h.get("added") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ts) or ts < cutoff:
            continue
        tid = h.get("id")
        if not tid:
            continue
        counts[tid] = counts.get(tid, 0) + 1
        meta.setdefault(tid, h)
    rows = [(tid, n) for tid, n in counts.items() if n >= 2]
    rows.sort(key=lambda kv: (-kv[1], str(meta[kv[0]].get("title") or "")))
    return [(meta[tid], n) for tid, n in rows[:top]]


def stats_week_top(store):
    """(artist, plays) most played in the last 7 days, or ("", 0).

    Counted from the (capped) history list, like stats_week(). Ties go
    to the artist played most recently.
    """
    cutoff = time.time() - 7 * 86400
    counts, last = {}, {}
    for h in store.history:
        if not isinstance(h, dict):
            continue
        try:
            ts = float(h.get("added") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ts) or ts < cutoff:
            continue
        a = (h.get("artist") or "").strip()
        if not a:
            continue
        counts[a] = counts.get(a, 0) + 1
        last[a] = max(last.get(a, 0), ts)
    if not counts:
        return "", 0
    best = max(counts, key=lambda a: (counts[a], last[a]))
    return best, counts[best]


def stats_hours(store):
    """Plays per time-of-day bucket, counted from the (capped) history list.

    Buckets in local time: Morning 5-12, Afternoon 12-17, Evening 17-22,
    Night 22-5. Entries with missing or non-finite timestamps are ignored.
    Returns [("Morning", n), ("Afternoon", n), ("Evening", n), ("Night", n)].
    """
    buckets = [0, 0, 0, 0]
    for h in store.history:
        if not isinstance(h, dict):
            continue
        try:
            ts = float(h.get("added") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ts) or ts <= 0:
            continue
        hr = time.localtime(ts).tm_hour
        buckets[0 if 5 <= hr < 12 else 1 if 12 <= hr < 17
                else 2 if 17 <= hr < 22 else 3] += 1
    return list(zip(("Morning", "Afternoon", "Evening", "Night"), buckets))


def stats_summary(plays, top=6):
    """(total plays, unique songs, top artists, top songs) from play counts."""
    total = sum(p["n"] for p in plays.values())
    artists = {}
    for p in plays.values():
        artists[p["artist"]] = artists.get(p["artist"], 0) + p["n"]
    ta = sorted(artists.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    ts = sorted(((p["title"], p["artist"], p["n"], vid)
                 for vid, p in plays.items()),
                key=lambda r: (-r[2], r[0]))[:top]
    return total, len(plays), ta, ts


# ------------------------------------------------------------------- app ---
class App:
    def __init__(self):
        self.store = Store()
        self.mpv = Mpv()
        self.mpv.state["vol"] = self.store.volume
        self.mpv.set_eq(self.store.eq_preset)
        self.pal = None
        self.lock = threading.RLock()
        self.stack = [("home", None)]
        self.sel = {}
        self.off = {}
        self.query = ""
        self.live_q = ""             # query the live results already show
        self._edit_t = 0.0           # last search-bar keystroke
        self.results = []
        self.searching = False
        self.search_token = 0
        self._artist_remote = {}
        self._artist_busy = set()
        self.find_buf = ""
        self.mode = "normal"          # normal | search | name | pick | find
        self.name_buf = ""
        self.rename_index = None
        self.delete_index = None
        self.pick_rows = []
        self.pick_idx = 0
        self.pick_pending = None      # track waiting to be added
        self.pick_merge = None        # playlist index being merged, or None
        self.pick_title = "Add to playlist"
        self.pick_filter = ""         # type-to-filter inside the picker
        self.toast = ("", 0.0)
        self.queue = []
        self.queue_revision = 0
        self.qpos = -1
        self.orig_queue = None
        self.current = None
        self.pending_seek = None       # (load_token, seconds) to seek to
        self._resume_t = 0.0           # saved position from the session
        self.play_source = None        # where the current queue was started
        self.restore_session()
        self.loading = False
        self.load_token = 0
        self._last_row = None
        self._last_row_t = 0.0
        self.shuffle = False
        self.repeat = 0               # 0 off, 1 all, 2 one
        self.reduced_motion = bool(os.environ.get("SPOTUI_REDUCED_MOTION"))
        self.frame = 0
        self.rects = []
        self.soff = 0                 # sidebar scroll offset
        self.sw_bounds = None         # (SW, y0, y1) for wheel-over-sidebar
        self.liked_ids = {t["id"] for t in self.store.liked}
        self.blocked_ids = set(self.store.blocked)
        self._sim_busy = False
        self._sim_at = 0.0
        self._radio_busy = False
        self._auto_busy = False
        self.quit = False
        self.show_help = False
        self.help_page = 0
        self.help_pages = 1
        self.sleep_deadline = None
        self.sleep_eot = False
        self._fading = False           # sleep fade is ramping mpv's volume
        self.private = False           # private session: nothing is recorded
        self.info_track = None         # song shown in the info modal
        self.theme_orig = None         # theme to revert to (picker)
        self.theme_idx = 0             # highlighted theme in the picker
        self._trash = None             # last deleted playlist/song (undo)
        self._fade_level = None        # last level sent (1/sec throttle)
        self._muted_from = None      # volume before muting, None = not muted
        self.speed = 1.0
        self.sleep_minutes = 0
        self.sleep_buf = ""          # custom-minutes modal input
        self._sleep_cycle_at = None  # cycle position while the modal is up
        self.search_filter = "all"   # search filter chips: all/songs/artists
        self.drag_rect = None
        self.drag_row = None           # [view key, index] being row-dragged
        self.last_store_error = None
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
            if kind == "artist":
                self._maybe_artist_remote(arg)

    def _maybe_artist_remote(self, name):
        """Artist not in the library: fetch their YouTube songs in the
        background so the artist page is never a dead end."""
        if not name or not HAVE_YTDL or self.artist_tracks(name):
            return
        if name in self._artist_remote or name in self._artist_busy:
            return
        self._artist_busy.add(name)
        threading.Thread(target=self._artist_remote_worker, args=(name,),
                         daemon=True).start()

    def _artist_remote_worker(self, name):
        try:
            res = [t for t in (ytdl_search(name) or []) if _real_song(t)]
            mine = [t for t in res
                    if self._norm_artist(t.get("artist"))
                    == self._norm_artist(name)]
            if mine:
                res = mine
            res = res[:25]
        except Exception:
            res = []
        with self.lock:
            self._artist_remote[name] = res
            self._artist_busy.discard(name)

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
            return sort_tracks(self.store.liked, self.store.sort_mode)
        if kind == "playlist":
            try:
                pl = self.store.playlists[int(arg)]
            except Exception:
                return []
            return sort_tracks(pl["tracks"], self.store.sort_mode)
        if kind == "queue":
            return self.queue
        if kind == "history":
            hist = self.store.history
            if self.store.hist_dedupe:
                seen, ded = set(), []
                for t in hist:
                    tid = t.get("id")
                    if tid is not None:
                        if tid in seen:
                            continue
                        seen.add(tid)
                    ded.append(t)
                hist = ded
            return sort_tracks(hist, self.store.sort_mode)
        if kind == "artist":
            lib = self.artist_tracks(arg or "")
            return lib or self._artist_remote.get(arg or "", [])
        if kind == "similar":
            items = (self.store.similar or {}).get("items") or []
            return [t for t in items
                    if t.get("id") not in self.blocked_ids]
        return []

    def find_jump(self):
        q = self.find_buf.casefold().strip()
        tracks = self.view_tracks()
        if not q:
            self.toast_now("Find: type to jump, Enter to stay")
            return
        for i, t in enumerate(tracks):
            if q in f"{t.get('title', '')} {t.get('artist', '')}".casefold():
                self.sel[self.key()] = i
                self.toast_now(f"Find: {self.find_buf}")
                return
        self.toast_now(f"Find: {self.find_buf} (no match)")

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
    def play(self, tracks, pos, source=None):
        if not tracks or not 0 <= pos < len(tracks):
            return
        self.queue_revision += 1
        self.orig_queue = None
        self.play_source = source
        self.queue = [dict(t) for t in tracks]
        if source:
            for t in self.queue:
                t["src"] = source
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
            previous = head[-1].get("artist", "") if head else ""
            recent = [t.get("id") for t in self.store.history[:10]]
            self.queue = head + smart_shuffle(tail, previous, recent, mode=self.store.shuffle_mode,
                                              plays=self.store.plays)
        elif self.orig_queue:
            cur = self.current
            self.queue = [dict(t) for t in self.orig_queue]
            if cur:
                for i, t in enumerate(self.queue):
                    if t["id"] == cur["id"]:
                        self.qpos = i
                        break
            self.orig_queue = None

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
        self._maybe_autoplay()

    def _note_history(self, t):
        """Remember what was actually played (newest first, capped)."""
        if self.private:
            return
        try:
            rec = {k: t.get(k) for k in ("id", "title", "artist", "dur", "url")}
            rec["added"] = time.time()
            if self.store.first_play is None:
                self.store.first_play = rec["added"]
            h = [x for x in self.store.history
                 if isinstance(x, dict) and x.get("id") != rec.get("id")]
            h.insert(0, rec)
            self.store.history = h[:30]
            pid = str(rec.get("id"))
            p = self.store.plays.get(pid) or dict(
                title=str(rec.get("title") or ""), artist=str(rec.get("artist") or "Unknown"), n=0)
            p["n"] += 1
            self.store.plays[pid] = p
            # milestones: every 25 plays of one song, every 500 overall
            if p["n"] % 25 == 0:
                self.toast_now(
                    f"{rec.get('title') or '?'} - {p['n']} plays!")
            else:
                total = sum(x["n"] for x in self.store.plays.values())
                if total % 500 == 0:
                    self.toast_now(f"{total} plays on SpotUI!")
            if len(self.store.plays) > 2000:
                for k in sorted(self.store.plays, key=lambda k: self.store.plays[k]["n"])[:200]:
                    del self.store.plays[k]
            self.snapshot_session()
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
                self.orig_queue = None
                if self.shuffle:
                    self._apply_shuffle(True)
                self.toast_now("Radio on — more from "
                               f"{track.get('artist') or 'this artist'}")
            self._radio_busy = False

    # --------------------------------------------------------- autoplay --
    def toggle_autoplay(self):
        self.store.autoplay = not self.store.autoplay
        self.store.save()
        self.toast_now("Autoplay " + ("on — the music continues after the queue"
                       if self.store.autoplay else "off"))

    def _maybe_autoplay(self):
        """Prefetch similar songs when the last queued song starts, so the
        music keeps going instead of stopping at the end of the queue."""
        if not self.store.autoplay or self._auto_busy or self._radio_busy:
            return
        if not self.current or self.qpos < len(self.queue) - 1:
            return
        self._auto_busy = True
        threading.Thread(target=self._autoplay_worker,
                         args=(dict(self.current), self.queue_revision,
                               self.load_token), daemon=True).start()

    def _autoplay_worker(self, track, revision, token):
        import random
        items = []
        try:
            items = _ytdl_playlist(_radio_url(track["id"]), n=60)
        except Exception:
            items = []
        items = [t for t in items
                 if t.get("id") != track.get("id") and _real_song(t)]
        random.shuffle(items)
        picks, per_artist = [], {}
        for t in items:
            a = (t.get("artist") or "").lower()
            if per_artist.get(a, 0) >= 2:
                continue
            per_artist[a] = per_artist.get(a, 0) + 1
            picks.append(t)
            if len(picks) >= 25:
                break
        advance = False
        with self.lock:
            try:
                if not (picks and not self.quit
                        and revision == self.queue_revision
                        and token == self.load_token and self.current
                        and self.current.get("id") == track.get("id")):
                    return
                have = {t.get("id") for t in self.queue}
                picks = [t for t in picks if t.get("id") not in have
                         and t.get("id") not in self.blocked_ids]
                if not picks:
                    return
                for t in picks:   # tag so the UI can mark autoplayed songs
                    t["auto"] = True
                was_end = self.qpos == len(self.queue) - 1
                self.queue.extend(picks)
                if self.shuffle:
                    self.orig_queue = None
                    self._apply_shuffle(True)
                self.toast_now("Autoplay — more from "
                               f"{track.get('artist') or 'this artist'}")
                # the song may already have ended while we fetched
                advance = was_end and self.mpv.state["idle"]
            finally:
                self._auto_busy = False
        if advance:
            self.next(auto=True)

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
                ps = self.pending_seek
                if ps and ps[0] == token:
                    self.pending_seek = None
                    self.mpv.seek_abs(ps[1])
                self._note_history(track)
        except Exception as e:
            with self.lock:
                if token != self.load_token or self.quit:
                    return
                self.loading = False
                self.toast_now(f"Couldn't play — {e}")

    def _source_for_vk(self, vk):
        """Human label for where a played list came from (now-playing line)."""
        kind, _, arg = vk.partition(":")
        if kind == "search":
            q = self.query.strip()
            return f'Search "{q}"' if q else "Search"
        if kind == "similar":
            return "Made for you"
        if kind == "history":
            return "Recently Played"
        if kind == "liked":
            return "Liked Songs"
        if kind == "artist":
            return arg or "Artist"
        if kind == "playlist":
            try:
                return self.store.playlists[int(arg)]["name"]
            except (ValueError, IndexError, TypeError):
                return "Playlist"
        return None

    def play_row(self, vk, idx):
        if vk.split(":", 1)[0] == "queue":
            if 0 <= idx < len(self.queue):
                self.qpos = idx
                self._play_current()
            return
        tracks = self.view_tracks(vk)
        if 0 <= idx < len(tracks):
            self.play(tracks, idx, source=self._source_for_vk(vk))
            # a search pick keeps the music going with the same artist /
            # channel instead of walking down the result list
            if vk.split(":")[0] in ("search", "similar", "history", "artist"):
                self._start_radio(tracks[idx])

    def snapshot_session(self):
        keep = ("id", "title", "artist", "dur", "url")
        if self.current and not self.mpv.state["idle"]:
            try:
                pos_s = max(0.0, float(self.mpv.state["pos"]))
            except (TypeError, ValueError):
                pos_s = 0.0
        else:
            # nothing playing: keep the previous resume point
            try:
                pos_s = float((self.store.session or {}).get("t") or 0)
                if not math.isfinite(pos_s) or pos_s < 0:
                    pos_s = 0.0
            except (TypeError, ValueError):
                pos_s = 0.0
        self.store.session = {
            "queue": [{k: t.get(k) for k in keep} for t in self.queue[:500]],
            "pos": self.qpos,
            "t": round(pos_s, 1)}

    def restore_session(self):
        q = self.store.session.get("queue") or []
        pos = self.store.session.get("pos", 0)
        if q and 0 <= pos < len(q) and not self.queue:
            self.queue = [dict(t) for t in q]
            self.qpos = pos
        try:
            t = float(self.store.session.get("t") or 0)
            self._resume_t = t if math.isfinite(t) and t >= 0 else 0.0
        except (TypeError, ValueError, AttributeError):
            self._resume_t = 0.0
            self.queue_revision += 1

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

    def play_mix(self, i):
        mixes = daily_mixes(self.store)
        if not 0 <= i < len(mixes):
            return
        m = mixes[i]
        recent = [t.get("id") for t in self.store.history[:10]]
        tracks = smart_shuffle(m["tracks"], "", recent)
        self.play(tracks, 0, source=m["name"])
        self.toast_now(f"{m['name']}: {len(tracks)} songs - "
                       f"{m['artist']} and more")

    def cycle_shuffle_mode(self):
        i = SHUFFLE_MODES.index(self.store.shuffle_mode)
        self.store.shuffle_mode = SHUFFLE_MODES[(i + 1) % len(SHUFFLE_MODES)]
        self.store.save()
        self.shuffle = True
        self._apply_shuffle(False)       # restore original order, then reshuffle
        self._apply_shuffle(True)
        self.toast_now("Shuffle: " + SHUFFLE_LABEL[self.store.shuffle_mode])

    def toggle_zen(self):
        self.store.zen = not self.store.zen
        self.store.save()
        self.toast_now("Sidebar hidden - z brings it back"
                       if self.store.zen else "Sidebar shown")

    def toggle_hist_dedupe(self):
        self.store.hist_dedupe = not self.store.hist_dedupe
        self.store.save()
        if self.store.hist_dedupe:
            self.toast_now("Recently Played: repeats hidden")
        else:
            self.toast_now("Recently Played: repeats shown")

    def cycle_sort(self):
        i = SORT_MODES.index(self.store.sort_mode)
        self.set_sort(SORT_MODES[(i + 1) % len(SORT_MODES)], cycle=True)

    def set_sort(self, mode, cycle=False):
        if mode not in SORT_MODES:
            return
        # clicking the active column again restores the original order
        if not cycle and self.store.sort_mode == mode:
            mode = "default"
        self.store.sort_mode = mode
        self.store.save()
        self.toast_now("Sort: " + SORT_LABEL[mode])

    def cycle_repeat(self):
        self.repeat = (self.repeat + 1) % 3
        if self.repeat == 2:
            self.mpv.cmd(["set_property", "loop-file", "inf"])
        else:
            self.mpv.cmd(["set_property", "loop-file", "no"])
        names = ["Repeat off", "Repeat all", "Repeat one"]
        self.toast_now(names[self.repeat])

    def seek(self, delta):
        """Arrow-key seek with position feedback, like Spotify's overlay."""
        self.mpv.seek_rel(delta)
        st = self.mpv.state
        try:
            pos = float(st.get("pos") or 0.0) + delta
            dur = float(st.get("dur") or 0.0)
        except (TypeError, ValueError):
            pos, dur = 0.0, 0.0
        target = max(0.0, pos)
        if dur:
            target = min(target, dur)
        sign = "+" if delta > 0 else "-"
        self.toast_now(f"{sign}{abs(delta)}s - {fmt_t(target)}")

    def vol(self, d=None, absolute=None):
        v = self.mpv.state["vol"]
        if absolute is not None:
            v = absolute
        else:
            v += (d or 0)
        self.mpv.set_vol(v)
        self._muted_from = None      # any volume change unmutes
        self._fading = False         # and takes over from a sleep fade
        self._fade_level = None
        self.store.volume = self.mpv.state["vol"]
        self.store.save()
        self.toast_now(f"Volume {self.mpv.state['vol']}")

    def chip_action(self, tag):
        """Click on a Now Playing state chip: same effect as its key."""
        if tag == "speed":
            self.speed = 1.0
            self.mpv.set_speed(1.0)
            self.toast_now("Speed 1x")
            return
        {"playpause": self.toggle, "shuffle": self.toggle_shuffle,
         "repeat": self.cycle_repeat, "eq": self.cycle_eq,
         "autoplay": self.toggle_autoplay,
         "sleep": self.cycle_sleep}[tag]()

    def toggle_mute(self):
        """Speaker click: drop to 0 remembering the level, click to restore."""
        if self._muted_from is not None:
            v, self._muted_from = self._muted_from, None
            self.vol(absolute=v)
        elif self.mpv.state["vol"] > 0:
            self._muted_from = self.mpv.state["vol"]
            self.mpv.set_vol(0)
            self.store.volume = 0
            self.store.save()
            self.toast_now("Muted")
        else:
            self.toast_now("Volume 0")

    # ------------------------------------------------------------ library --
    def cycle_theme(self):
        i = THEME_NAMES.index(self.store.theme) if self.store.theme in THEMES else 0
        name = THEME_NAMES[(i + 1) % len(THEME_NAMES)]
        if self.pal is None or not self.pal.apply_theme(name):
            self.toast_now("Themes need a terminal with palette support (not NO_COLOR)")
            return
        self.store.theme = name
        self.store.save()
        self.toast_now(f"Theme: {name}")

    def open_theme_picker(self):
        """Theme picker with live preview: moving applies instantly."""
        if self.pal is None or not self.pal.can_theme():
            self.toast_now("Themes need a terminal with palette "
                           "support (not NO_COLOR)")
            return
        self.theme_orig = self.store.theme
        self.theme_idx = (THEME_NAMES.index(self.store.theme)
                          if self.store.theme in THEMES else 0)
        self.mode = "theme"

    def theme_move(self, d):
        self.theme_idx = (self.theme_idx + d) % len(THEME_NAMES)
        name = THEME_NAMES[self.theme_idx]
        if not self.pal.apply_theme(name):
            self.pal.apply_theme(self.theme_orig)
            self.store.theme = self.theme_orig
            self.mode = "normal"
            self.toast_now("Themes need a terminal with palette "
                           "support (not NO_COLOR)")
            return
        self.store.theme = name   # live preview; saved only on Enter

    def theme_apply(self):
        name = THEME_NAMES[self.theme_idx]
        self.store.theme = name
        self.store.save()
        self.mode = "normal"
        self.toast_now(f"Theme: {name}")

    def theme_cancel(self):
        self.pal.apply_theme(self.theme_orig)
        self.store.theme = self.theme_orig
        self.mode = "normal"

    def cycle_sleep(self):
        options = [0, 15, 30, 60, 90, "eot", "custom"]
        cur = self._sleep_cycle_at or \
            ("eot" if self.sleep_eot else self.sleep_minutes)
        self._sleep_cycle_at = None
        try:
            i = options.index(cur)
        except ValueError:
            i = 0      # a custom value is armed: cycle from off
        nxt = options[(i + 1) % len(options)]
        if nxt == "custom":
            self.mode = "sleep"
            self.sleep_buf = ""
            # remember where the cycle stopped, so the next t moves on to
            # off even if the user cancels the prompt
            self._sleep_cycle_at = "custom"
            return
        self.sleep_eot = nxt == "eot"
        self.sleep_minutes = 0 if self.sleep_eot else nxt
        self.sleep_deadline = (time.monotonic() + self.sleep_minutes * 60
                               if self.sleep_minutes else None)
        if self.sleep_eot:
            self.toast_now("Sleep timer: end of track")
        elif self.sleep_minutes:
            self.toast_now(f"Sleep timer: {self.sleep_minutes} min")
        else:
            self.toast_now("Sleep timer off")

    def set_sleep_custom(self):
        """Arm the sleep timer from the typed-in minutes (sleep modal)."""
        try:
            mins = int(self.sleep_buf or "0")
        except ValueError:
            mins = 0
        self.sleep_buf = ""
        self.mode = "normal"
        if not 1 <= mins <= 1440:
            self.toast_now("Sleep timer unchanged")
            return
        self.sleep_eot = False
        self.sleep_minutes = mins
        self.sleep_deadline = time.monotonic() + mins * 60
        self.toast_now(f"Sleep timer: {mins} min")

    def _track_ended(self):
        """Natural track end: advance, unless the end-of-track sleep timer
        is armed - then pause here instead and disarm it."""
        if self.sleep_eot:
            self.sleep_eot = False
            self.load_token += 1
            self.loading = False
            self.mpv.cmd(["set_property", "pause", True])
            self.mpv.state["pause"] = True
            self._fade_restore()
            self.toast_now("Sleep timer - playback paused")
        else:
            self.next(auto=True)

    def _fade_restore(self):
        if self._fading:
            self._fading = False
            self._fade_level = None
            self.mpv.cmd(["set_property", "volume",
                          self.mpv.state["vol"]])

    def _sleep_fade(self):
        """Fade mpv's volume toward zero over the last FADE_SECS of an
        armed sleep timer. Only mpv's runtime volume changes - the
        user's stored volume stays, so the next play starts at the
        usual level."""
        rem = None
        if self.sleep_deadline is not None:
            rem = self.sleep_deadline - time.monotonic()
        elif self.sleep_eot:
            st = self.mpv.state
            if not st["idle"] and st["dur"] > 0:
                rem = st["dur"] - st["pos"]
        if rem is not None and 0 < rem <= FADE_SECS:
            level = max(0, int(round(self.mpv.state["vol"]
                                     * rem / FADE_SECS)))
            if level != self._fade_level:
                self._fade_level = level
                self.mpv.cmd(["set_property", "volume", level])
            self._fading = True
        else:
            self._fade_restore()

    def tick(self):
        self._sleep_fade()
        self._tick_live_search()
        if self.store.error and self.store.error != self.last_store_error:
            self.toast_now(self.store.error)
        self.last_store_error = self.store.error
        if self.sleep_deadline is not None and time.monotonic() >= self.sleep_deadline:
            self.sleep_deadline = None
            self.sleep_minutes = 0
            self.load_token += 1
            self.loading = False
            self.mpv.on_end.clear()
            self.mpv.cmd(["set_property", "pause", True])
            self.mpv.state["pause"] = True
            self._fade_restore()
            self.toast_now("Sleep timer - playback paused")

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

    def like_all(self, pi):
        """Like every song of playlist pi at once."""
        if not 0 <= pi < len(self.store.playlists):
            return
        pl = self.store.playlists[pi]
        if not pl["tracks"]:
            self.toast_now("This playlist is empty")
            return
        today = time.strftime("%Y-%m-%d")
        fresh = [t for t in pl["tracks"] if t["id"] not in self.liked_ids]
        if not fresh:
            self.toast_now(f"Every song in {pl['name']} is already liked")
            return
        for t in reversed(fresh):
            self.store.liked.insert(0, dict(t, added=today))
            self.liked_ids.add(t["id"])
        self.store.save()
        self.toast_now(f"Liked {len(fresh)} song"
                       f"{'s' if len(fresh) != 1 else ''} "
                       f"from {pl['name']}")

    def toggle_block(self, t):
        """Hide a song from every suggestion surface (mixes, Enhance,
        Made for you, autoplay) - or bring it back."""
        if not t:
            return
        tid = str(t.get("id") or "")
        title = t.get("title") or "Song"
        if tid in self.blocked_ids:
            self.blocked_ids.discard(tid)
            self.store.blocked = [x for x in self.store.blocked if x != tid]
            self.toast_now(f"{title} is back in suggestions")
        else:
            self.blocked_ids.add(tid)
            self.store.blocked.append(tid)
            self.toast_now(f"Won't suggest {title} again (x to undo)")
        self.store.save()

    def add_queue(self, t):
        if not t:
            return
        if not self.current:
            self.play([t], 0)
            return
        self.queue_revision += 1
        self.queue.append(dict(t, src="Added"))
        if self.shuffle and self.orig_queue:
            self.orig_queue.append(dict(t, src="Added"))
        self.toast_now(f"Added to queue: {t['title'][:30]}")

    def queue_all(self, tracks):
        """Append a whole list to the queue, skipping songs already in it.

        Starts playing instead when nothing is playing, like add_queue."""
        have = {q.get("id") for q in self.queue}
        fresh = [t for t in tracks if t.get("id") not in have]
        if not fresh:
            self.toast_now("Every result is already in the queue")
            return 0
        if not self.current:
            self.play(fresh, 0)
            return len(fresh)
        self.queue_revision += 1
        self.queue.extend(dict(t, src="Added") for t in fresh)
        if self.shuffle and self.orig_queue is not None:
            self.orig_queue.extend(dict(t, src="Added") for t in fresh)
        self.toast_now(f"Added {len(fresh)} song"
                       f"{'s' if len(fresh) != 1 else ''} to the queue")
        return len(fresh)

    def play_next(self, t):
        if not t:
            return
        if not self.current:
            self.play([t], 0)
            return
        self.queue_revision += 1
        self.queue.insert(self.qpos + 1, dict(t, src="Added"))
        if self.shuffle and self.orig_queue is not None:
            self.orig_queue.append(dict(t, src="Added"))
        self.toast_now(f"Plays next: {t['title'][:30]}")

    def move_queue(self, idx, d):
        j = idx + d
        if not (self.qpos < idx < len(self.queue) and self.qpos < j < len(self.queue)):
            return False
        self.queue_revision += 1
        self.queue[idx], self.queue[j] = self.queue[j], self.queue[idx]
        self.sel["queue:"] = j
        return True

    def move_in_playlist(self, pi, idx, d):
        try:
            tracks = self.store.playlists[pi]["tracks"]
        except (IndexError, KeyError, TypeError):
            return False
        j = idx + d
        if not (0 <= idx < len(tracks) and 0 <= j < len(tracks)):
            return False
        tracks[idx], tracks[j] = tracks[j], tracks[idx]
        self.store.save()
        self.sel[self.key()] = j
        return True

    def copy_link(self, t):
        """Copy a song's YouTube link to the system clipboard.

        Tries the usual clipboard tools first (Termux, Wayland, X11,
        macOS), then an OSC 52 escape written straight to the terminal.
        Always returns the URL; when no clipboard worked the toast shows
        the link itself so it can still be copied by hand.
        """
        url = (t or {}).get("url")
        if not url and t and t.get("id"):
            url = f"https://www.youtube.com/watch?v={t['id']}"
        if not url:
            self.toast_now("No link for this song")
            return None
        if self.copy_text(url, "Link"):
            return url
        self.toast_now(f"Link: {url}")
        return url

    def copy_text(self, text, what="Text"):
        """Copy text to the system clipboard (Termux, Wayland, X11, macOS,
        OSC 52 fallback). True when a clipboard took it."""
        for cmd in (["termux-clipboard-set"], ["wl-copy"],
                    ["xclip", "-selection", "clipboard"],
                    ["xsel", "--clipboard", "--input"], ["pbcopy"]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, input=text.encode(), timeout=3,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, check=True)
                    self.toast_now(f"{what} copied to clipboard")
                    return True
                except (OSError, subprocess.SubprocessError):
                    continue
        try:
            with open("/dev/tty", "wb") as tty:
                tty.write(b"\x1b]52;c;" + base64.b64encode(text.encode())
                          + b"\a")
                tty.flush()
            self.toast_now(f"{what} copied to clipboard")
            return True
        except OSError:
            pass
        return False

    def copy_tracklist(self, pi):
        """Copy a playlist's tracklist as shareable numbered text."""
        if not 0 <= pi < len(self.store.playlists):
            return None
        pl = self.store.playlists[pi]
        if not pl["tracks"]:
            self.toast_now("This playlist is empty")
            return None
        lines = [pl["name"]]
        for i, t in enumerate(pl["tracks"], 1):
            line = (f"{i}. {t.get('title') or '?'} - "
                    f"{t.get('artist') or 'Unknown'}")
            if t.get("dur"):
                line += f" ({fmt_t(t['dur'])})"
            lines.append(line)
        text = "\n".join(lines)
        if self.copy_text(text, "Tracklist"):
            return text
        preview = " \u00b7 ".join(
            f"{t.get('title') or '?'}" for t in pl["tracks"][:3])
        self.toast_now(f"Tracklist: {preview} \u2026")
        return text

    def stats_share_text(self):
        """Wrapped-style stats summary as shareable text."""
        total, uniq, ta, ts = stats_summary(self.store.plays)
        lines = ["My SpotUI stats"]
        lines.append(f"{total} plays \u00b7 {uniq} different songs")
        mins = stats_minutes(self.store)
        if mins:
            lines.append(f"About {mins} listened")
        if ta:
            lines.append(f"Top artist: {ta[0][0]} ({ta[0][1]} plays)")
        if ts:
            lines.append(f"Top song: {ts[0][0]} - {ts[0][1]} "
                         f"({ts[0][2]} plays)")
        streak = stats_streak(self.store)
        if streak:
            lines.append(f"{streak}-day streak")
        week = stats_week(self.store)
        if week:
            lines.append(f"{week} plays this week")
        return "\n".join(lines)

    def share_stats(self):
        """Copy the stats summary; falls back to showing it in a toast."""
        text = self.stats_share_text()
        if self.copy_text(text, "Stats"):
            return text
        top = text.split("\n")[1] if "\n" in text else text
        self.toast_now("Stats: " + top)
        return text

    def library_tracks(self):
        """Every song in the library (liked, history, playlists), deduped."""
        seen, out = set(), []
        sources = [self.store.liked, self.store.history]
        sources += [pl["tracks"] for pl in self.store.playlists]
        for src in sources:
            for t in src:
                tid = t.get("id")
                if tid and tid not in seen:
                    seen.add(tid)
                    out.append(t)
        return out

    def shuffle_library(self):
        """Z: shuffle the whole library into the queue."""
        pool = [t for t in self.library_tracks()
                if t.get("id") not in self.blocked_ids]
        if not pool:
            self.toast_now("Your library is empty - like or add some songs first")
            return
        tracks = smart_shuffle(pool, mode=self.store.shuffle_mode,
                               plays=self.store.plays)
        self.play(tracks, 0, "Library shuffle")
        self.toast_now(f"Shuffling your library - {len(tracks)} songs")

    def export_playlist(self, pi):
        if not 0 <= pi < len(self.store.playlists):
            return None
        pl = self.store.playlists[pi]
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in pl["name"]).strip() or "playlist"
        path = EXPORT_DIR / f"{safe}.json"
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.part")
            tmp.write_text(json.dumps({"name": pl["name"], "tracks": pl["tracks"]},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(path)
        except OSError as e:
            self.toast_now(f"Export failed: {e}")
            return None
        self.toast_now(f"Exported to {path}")
        return path

    def clear_upcoming(self):
        if self.qpos + 1 >= len(self.queue):
            self.toast_now("Nothing upcoming to clear")
            return
        n = len(self.queue) - self.qpos - 1
        self.queue_revision += 1
        del self.queue[self.qpos + 1:]
        if self.orig_queue is not None:
            ids = {t.get("id") for t in self.queue}
            self.orig_queue = [t for t in self.orig_queue if t.get("id") in ids]
        self.sel["queue:"] = max(0, min(self.sel.get("queue:", 0), len(self.queue) - 1))
        self.toast_now(f"Cleared {n} upcoming songs")

    def drop_autoplayed(self):
        """Remove autoplay-added songs from the queue (never the playing one)."""
        marked = [i for i, t in enumerate(self.queue)
                  if t.get("auto") and i != self.qpos]
        if not marked:
            self.toast_now("No autoplayed songs to drop")
            return
        self.queue_revision += 1
        drop = set(marked)
        self.queue = [t for i, t in enumerate(self.queue) if i not in drop]
        if self.orig_queue is not None:
            ids = {t.get("id") for t in self.queue}
            self.orig_queue = [t for t in self.orig_queue
                               if t.get("id") in ids]
        self.qpos -= sum(1 for i in marked if i < self.qpos)
        self.qpos = max(0, min(self.qpos, len(self.queue) - 1))
        self.sel["queue:"] = max(0, min(self.sel.get("queue:", 0),
                                        len(self.queue) - 1))
        self.toast_now(f"Dropped {len(marked)} autoplayed songs")

    def save_queue_as_playlist(self):
        keep = ("id", "title", "artist", "dur", "url")
        seen, tracks = set(), []
        for t in self.queue:
            if t.get("id") in seen:
                continue
            seen.add(t.get("id"))
            tracks.append({k: t.get(k) for k in keep})
        if not tracks:
            self.toast_now("Queue is empty")
            return
        name = time.strftime("Queue %b %d %H:%M")
        self.store.playlists.append({"name": name, "tracks": tracks})
        self.store.save()
        self.toast_now(f"Saved {len(tracks)} songs as {name}")

    SPEEDS = (0.75, 1.0, 1.25, 1.5, 2.0)

    def change_speed(self, d):
        i = self.SPEEDS.index(self.speed) if self.speed in self.SPEEDS else 1
        i = max(0, min(len(self.SPEEDS) - 1, i + d))
        self.speed = self.SPEEDS[i]
        self.mpv.set_speed(self.speed)
        self.toast_now(f"Speed {self.speed:g}x")

    def cycle_eq(self):
        i = EQ_PRESETS.index(self.store.eq_preset)
        self.store.eq_preset = EQ_PRESETS[(i + 1) % len(EQ_PRESETS)]
        self.mpv.set_eq(self.store.eq_preset)
        self.store.save()
        p = self.store.eq_preset
        self.toast_now("Equalizer: " + ("off" if p == "off" else EQ_LABEL[p]))

    def create_playlist(self, name):
        name = name.strip() or "New Playlist"
        self.store.playlists.append({"name": name, "tracks": []})
        self.store.save()
        self.push("playlist", len(self.store.playlists) - 1)
        self.toast_now(f"Created playlist: {name}")

    def duplicate_playlist(self, pi):
        """Copy a playlist, tracks included, as '<name> (copy)'."""
        if not 0 <= pi < len(self.store.playlists):
            return
        pl = self.store.playlists[pi]
        base = pl["name"] + " (copy)"
        name, n = base, 2
        names = {p["name"] for p in self.store.playlists}
        while name in names:
            name = f"{base} {n}"
            n += 1
        self.store.playlists.append(
            {"name": name,
             "tracks": [dict(t) for t in pl["tracks"]
                        if not t.get("enhanced")]})
        self.store.save()
        self.push("playlist", len(self.store.playlists) - 1)
        self.toast_now(f"Duplicated as: {name}")

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

    def clear_history(self):
        self.store.history = []
        self.store.plays = {}
        self.store.save()
        self.toast_now("Play history cleared - playlists and liked songs kept")

    def delete_playlist(self, pi):
        if not 0 <= pi < len(self.store.playlists):
            return
        name = self.store.playlists[pi]["name"]
        self._trash = ("playlist", pi, dict(self.store.playlists[pi]))
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

    def undo_delete(self):
        """Restore the last deleted playlist or playlist song (one level)."""
        trash, self._trash = self._trash, None
        if not trash:
            self.toast_now("Nothing to restore")
            return
        if trash[0] == "playlist":
            _, pi, pl = trash
            pi = max(0, min(pi, len(self.store.playlists)))
            self.store.playlists.insert(pi, pl)
            self.store.save()
            self.toast_now(f"Restored playlist: {pl['name']}")
        else:
            _, pi, idx, t = trash
            if not 0 <= pi < len(self.store.playlists):
                self.toast_now("That playlist is gone")
                return
            tracks = self.store.playlists[pi]["tracks"]
            tracks.insert(max(0, min(idx, len(tracks))), t)
            self.store.save()
            self.toast_now(f"Restored {t.get('title') or 'song'}")

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
            t = tracks[idx]
            pl = self.store.playlists[arg]["tracks"]
            for i, item in enumerate(pl):
                if item is t:
                    self._trash = ("track", arg, i, item)
                    del pl[i]
                    break
            else:
                return
            s = self.sel_row()
            if s >= len(tracks) - 1:
                self.sel[self.key()] = max(0, len(tracks) - 2)
            self.store.save()
        elif kind == "liked":
            self.like(tracks[idx])
        elif kind == "queue":
            self.queue_revision += 1
            removed = self.queue[idx]
            if self.orig_queue is not None:
                for oi, item in enumerate(self.orig_queue):
                    if item == removed:
                        del self.orig_queue[oi]
                        break
            del self.queue[idx]
            if idx < self.qpos:
                self.qpos -= 1
            elif idx == self.qpos:
                # deleted the playing row: mpv keeps playing it, so step
                # the pointer back so auto-advance lands on the next song
                self.qpos -= 1

    def open_pick(self, t):
        self.pick_pending = t
        self.pick_merge = None
        self.pick_title = "Add to playlist"
        self.pick_rows = [{"name": "+ New playlist", "new": True}] + [
            {"name": p["name"], "new": False, "n": len(p["tracks"]),
             "has": any(x["id"] == t["id"] for x in p["tracks"]), "pi": j}
            for j, p in enumerate(self.store.playlists)]
        self.pick_idx = 0
        self.pick_filter = ""
        self.mode = "pick"

    def open_pick_merge(self, pi):
        """Picker that merges the whole of playlist pi into another one."""
        if not 0 <= pi < len(self.store.playlists):
            return
        if not self.store.playlists[pi]["tracks"]:
            self.toast_now("This playlist is empty")
            return
        self.pick_pending = None
        self.pick_merge = pi
        self.pick_title = f"Merge \u201c{self.store.playlists[pi]['name']}\u201d into"
        self.pick_rows = [{"name": "+ New playlist", "new": True}] + [
            {"name": p["name"], "new": False, "n": len(p["tracks"]),
             "has": False, "pi": j}
            for j, p in enumerate(self.store.playlists) if j != pi]
        self.pick_idx = 0
        self.pick_filter = ""
        self.mode = "pick"

    def merge_playlist(self, src, dst):
        """Append every song of playlist src into dst, skipping dupes."""
        if not (0 <= src < len(self.store.playlists)
                and 0 <= dst < len(self.store.playlists)):
            return 0
        a, b = self.store.playlists[src], self.store.playlists[dst]
        have = {x["id"] for x in b["tracks"]}
        fresh = [t for t in a["tracks"] if t["id"] not in have]
        today = time.strftime("%Y-%m-%d")
        b["tracks"].extend(dict(t, added=t.get("added") or today)
                           for t in fresh)
        self.store.save()
        if not fresh:
            self.toast_now(f"{b['name']} already has every song")
        else:
            self.toast_now(f"Merged {len(fresh)} song"
                           f"{'s' if len(fresh) != 1 else ''} "
                           f"into {b['name']}")
        return len(fresh)

    def pinned_order(self):
        """Playlist indexes, pinned ones first, stable within each group."""
        pls = self.store.playlists
        return ([i for i, p in enumerate(pls) if p.get("pinned")]
                + [i for i, p in enumerate(pls) if not p.get("pinned")])

    def toggle_pin(self, pi):
        """Pin/unpin a playlist to the top of the sidebar and home tiles."""
        if not 0 <= pi < len(self.store.playlists):
            return
        pl = self.store.playlists[pi]
        pl["pinned"] = not pl.get("pinned")
        self.store.save()
        self.toast_now(("Pinned " if pl["pinned"] else "Unpinned ")
                       + pl["name"])

    def enhance_candidates(self, pl):
        """Library songs not in pl, same-artist first, ranked by plays."""
        seen = {t["id"] for t in pl["tracks"]} | self.blocked_ids
        artists = {self._norm_artist(t.get("artist"))
                   for t in pl["tracks"]}
        pool = []

        def scan(tracks):
            for t in tracks:
                if t["id"] in seen:
                    continue
                seen.add(t["id"])
                pool.append(t)

        scan(self.store.liked)
        scan(self.store.history)
        for other in self.store.playlists:
            if other is not pl:
                scan(other["tracks"])

        def rank(t):
            same = self._norm_artist(t.get("artist")) in artists
            n = (self.store.plays.get(t["id"]) or {}).get("n", 0)
            title = unicodedata.normalize(
                "NFKC", t.get("title") or "").casefold()
            return (0 if same else 1, -n, title)

        return sorted(pool, key=rank)

    def toggle_enhance(self, pi):
        """Spotify-style Enhance: weave library suggestions (every 2 songs,
        capped at 30) into a playlist; toggle again to drop them."""
        if not 0 <= pi < len(self.store.playlists):
            return
        pl = self.store.playlists[pi]
        if pl.get("enhanced"):
            n = sum(1 for t in pl["tracks"] if t.get("enhanced"))
            pl["tracks"] = [t for t in pl["tracks"]
                            if not t.get("enhanced")]
            pl["enhanced"] = False
            self.store.save()
            self.toast_now(f"Enhance off · removed {n} suggestion"
                           f"{'s' if n != 1 else ''}")
            return
        own = [t for t in pl["tracks"] if not t.get("enhanced")]
        if not own:
            self.toast_now("Add some songs first")
            return
        want = min(30, max(1, len(own) // 2))
        picks = self.enhance_candidates(pl)[:want]
        if not picks:
            self.toast_now("No suggestions yet - like or play more songs")
            return
        today = time.strftime("%Y-%m-%d")
        added = 0
        merged = []
        for i, t in enumerate(own):
            merged.append(t)
            if (i + 1) % 2 == 0 and added < len(picks):
                p = dict(picks[added], enhanced=True, added=today)
                merged.append(p)
                added += 1
        while added < len(picks):
            merged.append(dict(picks[added], enhanced=True, added=today))
            added += 1
        pl["tracks"] = merged
        pl["enhanced"] = True
        self.store.save()
        self.toast_now(f"Enhanced {pl['name']} · {added} suggestion"
                       f"{'s' if added != 1 else ''}")

    def toggle_private(self):
        """Private session (like Spotify's): plays and history stop being
        recorded until toggled off. Session-only, never saved."""
        self.private = not self.private
        self.toast_now("Private session on \u00b7 plays won't count"
                       if self.private else
                       "Private session off \u00b7 listening counts again")

    def open_info(self, t):
        """Song-info modal: every local fact about one track."""
        if not t:
            self.toast_now("Nothing to show")
            return
        self.info_track = dict(t)
        self.mode = "info"

    def info_rows(self):
        """(label, value) facts about the info-track, all local data."""
        t = self.info_track or {}
        tid = str(t.get("id") or "")
        rows = [("Title", t.get("title") or "?"),
                ("Channel", t.get("artist") or "Unknown")]
        if t.get("dur"):
            rows.append(("Length", fmt_t(t["dur"])))
        p = self.store.plays.get(tid) or {}
        n = p.get("n", 0)
        plays = f"{n} play{'s' if n != 1 else ''}"
        last = next((h.get("added") for h in self.store.history
                     if isinstance(h, dict)
                     and str(h.get("id")) == tid), None)
        try:
            if last:
                plays += (" \u00b7 last "
                          + time.strftime("%d %b",
                                          time.localtime(float(last))))
        except (TypeError, ValueError, OverflowError):
            pass
        rows.append(("Plays", plays))
        rows.append(("Liked", "yes" if tid in self.liked_ids else "no"))
        rows.append(("Suggested", "no (hidden)" if tid in self.blocked_ids
                     else "yes"))
        in_pls = [pl["name"] for pl in self.store.playlists
                  if any(str(x.get("id")) == tid for x in pl["tracks"])]
        rows.append(("In playlists", ", ".join(in_pls) if in_pls else "-"))
        if t.get("added"):
            rows.append(("Added", fmt_added(t.get("added"))))
        if t.get("url"):
            rows.append(("Link", t["url"]))
        return rows

    def open_in_browser(self, t):
        """Open the song's link in the system browser (Termux-friendly)."""
        url = (t or {}).get("url") or ""
        if not url.startswith("http"):
            self.toast_now("No link for this song")
            return False
        opener = (shutil.which("termux-open-url") or shutil.which("xdg-open")
                  or shutil.which("open") or shutil.which("wslview"))
        if not opener:
            self.toast_now("No browser opener found - link: " + url)
            return False
        try:
            subprocess.Popen([opener, url], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            self.toast_now("Could not open the browser - link: " + url)
            return False
        self.toast_now(f"Opening {t.get('title') or 'song'} in browser")
        return True

    def pick_view(self):
        """Picker rows as filtered by pick_filter ("+ New" always stays)."""
        if not self.pick_filter:
            return self.pick_rows
        f = self.pick_filter.casefold()
        return self.pick_rows[:1] + [
            r for r in self.pick_rows[1:] if f in r["name"].casefold()]

    def remove_recent(self, q):
        """Forget one recent search (the \u00d7 on its pill)."""
        if q in self.store.recent:
            self.store.recent.remove(q)
            self.store.save()
            self.toast_now(f"Removed search: {q}")

    def _record_search(self, q):
        """Remember a submitted search and reseed the made-for-you shelf."""
        q = q.strip()
        if not q:
            return
        if q in self.store.recent:
            self.store.recent.remove(q)
        self.store.recent.insert(0, q)
        self.store.recent = self.store.recent[:8]
        self.store.last_search = time.time()
        self.store.save()
        self.refresh_similar()

    def do_search(self, q, record=True):
        q = q.strip()
        if not q or not HAVE_YTDL:
            if not HAVE_YTDL:
                self.toast_now("yt-dlp missing — run ./install.sh")
            return
        self.push("search")
        self.live_q = q
        self.search_token += 1
        token = self.search_token
        self.searching = True
        threading.Thread(target=self._search_worker,
                         args=(q, token), daemon=True).start()
        if record:
            self._record_search(q)

    def submit_search(self):
        """Enter in the search bar: keep the live results, record the query."""
        self.mode = "normal"
        q = self.query.strip()
        if not q:
            return
        if q != self.live_q:
            self.do_search(q)
        else:
            self._record_search(q)

    LIVE_DEBOUNCE = 0.6

    def _tick_live_search(self):
        """Search-as-you-type: fire once the query is idle for a moment.

        Live searches never touch recent searches or the similar shelf —
        only a submitted (Enter) search does.
        """
        if self.mode != "search" or self.stack[-1][0] != "search":
            return
        q = self.query.strip()
        if not q:
            self.live_q = ""
            return
        if q == self.live_q:
            return
        if time.time() - getattr(self, "_edit_t", 0.0) < self.LIVE_DEBOUNCE:
            return
        self.do_search(q, record=False)

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

    def resume_session_or_play(self):
        """Continue listening: resume the saved session where it stopped.

        Only when nothing is playing and the saved session's current song
        is the most recent history entry - otherwise play that entry fresh.
        """
        hist = self.store.history
        if self.current or not hist:
            if hist:
                self.play_row("history:", 0)
            return
        q = self.queue
        if q and 0 <= self.qpos < len(q) \
                and q[self.qpos].get("id") == hist[0].get("id"):
            t = self._resume_t
            self._play_current()
            if t > 5:
                self.pending_seek = (self.load_token, t)
            return
        self.play_row("history:", 0)

    def track_under(self):
        tracks = self.view_tracks()
        idx = self.sel_row()
        return tracks[idx] if 0 <= idx < len(tracks) else None

    def jump_to_current(self):
        """'.' key: select the playing song in the current list.

        In the queue the playing row sits in its own Now playing box, so
        the jump lands on the next-up row instead."""
        if not self.current:
            self.toast_now("Nothing is playing")
            return
        kind, _ = self.stack[-1]
        if kind == "queue":
            nxt = min(self.qpos + 1, max(0, len(self.queue) - 1))
            if self.qpos + 1 >= len(self.queue):
                self.toast_now("Already at the last queued song")
                return
            self.sel["queue:"] = nxt
            return
        tracks = self.view_tracks()
        cid = self.current.get("id")
        for i, t in enumerate(tracks):
            if t.get("id") == cid:
                self.sel[self.key()] = i
                return
        self.toast_now("The playing song is not in this list")

    def open_source(self, src):
        """Open the library page a play source came from, when it has one."""
        if src == "Liked Songs":
            self.push("liked")
            return True
        if src == "Recently Played":
            self.push("history")
            return True
        if src == "Made for you":
            self.push("similar")
            return True
        for i, pl in enumerate(self.store.playlists):
            if pl.get("name") == src:
                self.push("playlist", i)
                return True
        if src and self.artist_tracks(src):
            self.push("artist", src)
            return True
        self.toast_now("No page for this source")
        return False

    def play_tile(self, kind, pidx):
        """Green play button on a home tile: play Liked Songs or a playlist."""
        if kind == "liked":
            tracks, src = self.store.liked, "Liked Songs"
        elif 0 <= (pidx if pidx is not None else -1) < len(self.store.playlists):
            pl = self.store.playlists[pidx]
            tracks, src = pl["tracks"], pl["name"]
        else:
            return False
        if not tracks:
            self.toast_now("Nothing to play here yet")
            return False
        self.play(tracks, 0, source=src)
        return True

    @staticmethod
    def _norm_artist(name):
        return unicodedata.normalize("NFKC", name or "").casefold().strip()

    def artist_plays(self, name):
        """Total local play count for one artist (0 when never played)."""
        norm = self._norm_artist(name)
        return sum(p["n"] for p in self.store.plays.values()
                   if self._norm_artist(p.get("artist")) == norm)

    def artist_minutes(self, name):
        """Rough listening time for one artist: play counts x duration for
        songs we know the length of (a floor, like stats_minutes())."""
        dur = {}
        pools = [self.store.liked, self.store.history] + \
            [pl["tracks"] for pl in self.store.playlists]
        for tracks in pools:
            for t in tracks:
                if t.get("id") and t.get("dur"):
                    dur.setdefault(t["id"], t["dur"])
        norm = self._norm_artist(name)
        sec = sum(p["n"] * dur.get(k, 0)
                  for k, p in self.store.plays.items()
                  if self._norm_artist(p.get("artist")) == norm)
        if sec < 60:
            return ""
        m = int(sec // 60)
        return f"{m // 60} hr {m % 60} min" if m >= 60 else f"{m} min"

    def artist_tracks(self, name):
        """Every song by this artist across the library, deduped, liked first."""
        norm = self._norm_artist(name)
        seen, out = set(), []
        sources = [self.store.liked, self.store.history, self.queue]
        sources += [pl["tracks"] for pl in self.store.playlists]
        for src in sources:
            for t in src:
                if self._norm_artist(t.get("artist")) == norm \
                        and t["id"] not in seen:
                    seen.add(t["id"])
                    out.append(t)
        return out

    def search_playlists(self, q, limit=4):
        """Library playlists whose name contains the query, in order."""
        nq = q.casefold().strip()
        if not nq:
            return []
        out = []
        for i, p in enumerate(self.store.playlists):
            if nq in p["name"].casefold():
                out.append((i, p))
                if len(out) >= limit:
                    break
        return out

    def search_artists(self, q, limit=5):
        """Artists matching a query: library first, then the result list."""
        norm = self._norm_artist(q)
        if not norm:
            return []
        seen, out = set(), []

        def scan(tracks):
            for t in tracks:
                a = (t.get("artist") or "").strip()
                na = self._norm_artist(a)
                if a and na not in seen and norm in na:
                    seen.add(na)
                    out.append(a)

        scan(self.store.liked)
        scan(self.store.history)
        for pl in self.store.playlists:
            scan(pl["tracks"])
        scan(self.results)
        return out[:limit]


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
    if app.reduced_motion:
        return EQ_FRAMES[0]
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

        px = max(SW + 2, (W - min(56, W - SW - 14)) // 2)
        pw = min(56, W - px - 12)
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
            put(self.scr, y0 + 1, px + 4, wcut(PLACEHOLDER, pw - 6), pal["pilldim"])
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

        sleeping = app.sleep_deadline is not None or app.sleep_eot
        if app.sleep_deadline is not None:
            remaining = max(0, int(app.sleep_deadline - time.monotonic()))
            put(scr, y1 - 2, 2, f"Sleep {fmt_t(remaining)}", pal["sgreen"])
        elif app.sleep_eot:
            put(scr, y1 - 2, 2, "Sleep: end of track", pal["sgreen"])
        if app.private:
            put(scr, y1 - (3 if sleeping else 2), 2, "\u25cb Private session",
                pal["sgreen"])
        kind, _ = app.stack[-1]
        navs = [("home", IC_HOME, "Home"), ("search", IC_SEARCH, "Search"),
                ("stats", IC_STATS, "Stats")]
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

        put(scr, y0 + 6, 2, "─" * (SW - 4), pal["sfaint"])
        y = y0 + 7
        put(scr, y, 2, "Your Library", pal["sdim"], curses.A_BOLD)
        put(scr, y, SW - 3, IC_PLUS, pal["sdim"], curses.A_BOLD)
        self.hit(SW - 4, y, 2, 1, "create")

        items = [("liked", IC_HEART, "Liked Songs"),
                 ("history", IC_HIST, "Recently Played")]
        for i in app.pinned_order():
            pl = app.store.playlists[i]
            items.append(("playlist",
                          IC_PIN if pl.get("pinned") else IC_NOTE,
                          pl["name"], i))
        top, bot = y0 + 9, y1 - (
            1 + sleeping + app.private)
        vis = max(1, bot - top)
        app.soff_max = max(0, len(items) - vis)
        app.soff = max(0, min(app.soff, app.soff_max))
        for row, i in enumerate(range(app.soff, len(items))):
            y = top + row
            if y >= bot:
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
            if k == "liked":
                n = len(app.store.liked)
            elif k == "history":
                n = len(app.store.history)
            else:
                n = len(app.store.playlists[item[3]]["tracks"])
            cnt = str(n) if n else ""
            playing_here = (app.play_source == label and app.current
                            and not app.mpv.state["idle"])
            name = wcut(label, SW - 10 - len(cnt))
            put(scr, y, 6, name,
                pal["sgreen"] if playing_here and not active else txp,
                curses.A_BOLD if playing_here else 0)
            if playing_here:
                bx = 6 + dlen(name) + 1
                if bx + 3 <= SW - 3 - len(cnt):
                    put(scr, y, bx, eq_bars(app)[:3],
                        pal["pgreen"] if active else pal["sgreen"])
            if cnt:
                put(scr, y, SW - 3 - len(cnt), cnt, pal["sfaint"])
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
        if self.app.reduced_motion:
            return
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
        elif kind in ("liked", "playlist", "history"):
            self.v_collection(y0, y1, x0, W, kind, arg)
        elif kind == "artist":
            self.v_artist(y0, y1, x0, W)
        elif kind == "queue":
            self.v_queue(y0, y1, x0, W)
        elif kind == "playing":
            self.v_playing(y0, y1, x0, W)
        elif kind == "stats":
            self.v_stats(y0, y1, x0, W)
        elif kind == "similar":
            self.v_similar(y0, y1, x0, W)
        self._reveal(y0, y1, x0, W)

    REVEAL_FRAMES = 6

    def _reveal(self, y0, y1, x0, W):
        """Top-down reveal when the main view changes (skipped for reduced motion)."""
        app = self.app
        top = app.stack[-1]
        if top != getattr(self, "_seen_view", None):
            first = getattr(self, "_seen_view", None) is None
            self._seen_view = top
            self._view_t = -999 if first else app.frame
        n = app.frame - getattr(self, "_view_t", -999)
        if app.reduced_motion or not 0 <= n < self.REVEAL_FRAMES:
            return
        shown = (n + 1) * (y1 - y0) // self.REVEAL_FRAMES
        for y in range(y0 + shown, y1):
            fill(self.scr, y, x0, W - x0, self.pal["text"])

    def v_stats(self, y0, y1, x0, W):
        app, pal, scr = self.app, self.pal, self.scr
        put(scr, y0 + 1, x0 + 2, "Your listening", pal["text"], curses.A_BOLD)
        total, uniq, ta, ts = stats_summary(app.store.plays)
        if not total:
            put(scr, y0 + 3, x0 + 2, "Play some songs and your top artists and "
                "songs will show up here.", pal["faint"])
            return
        head = f"{total} plays  \u00b7  {uniq} songs"
        mins = stats_minutes(app.store)
        if mins:
            head += f"  \u00b7  ~{mins}"
        week = stats_week(app.store)
        if week:
            head += f"  \u00b7  {week} this week"
        if app.store.first_play:
            since = time.strftime("%d %b %Y",
                                  time.localtime(app.store.first_play))
            extra = f"  \u00b7  since {since}"
            if dlen(head) + dlen(extra) <= W - x0 - 21:
                head += extra
        put(scr, y0 + 1, x0 + 19, head, pal["faint"])
        inner = W - x0 - 4
        half = inner >= 80
        colw = (inner - 4) // 2 if half else inner
        by = y0 + 3
        days = stats_days(app.store)
        week_n = sum(n for _, n in days)
        day_min = stats_day_minutes(app.store)
        week_min = sum(day_min)
        if week_n and by + 8 <= y1 - 1:
            put(scr, by, x0 + 2, "LAST 7 DAYS", pal["dim"], curses.A_BOLD)
            cap = f"{week_n} plays"
            if week_min:
                cap += f"  \u00b7  ~{week_min} min"
            put(scr, by + 1, x0 + 2, cap, pal["faint"])
            bh, top_n = 3, max(n for _, n in days)
            for i, (lab, n) in enumerate(days):
                x = x0 + 3 + i * 4
                filled = round(n / top_n * bh) if top_n else 0
                col = pal["green"] if i == 6 else pal["sdim"]
                for r in range(bh - filled, bh):
                    put(scr, by + 2 + r, x, "\u2588", col)
                put(scr, by + 2 + bh, x, lab, pal["faint"])
                m = day_min[i]
                if m:
                    mtxt = f"{m}m" if m < 100 else f"{m // 60}h"
                    put(scr, by + 3 + bh, x, mtxt, pal["faint"])
            # time-of-day mini chart beside the daily one, when wide enough
            hours = stats_hours(app.store)
            htot = sum(n for _, n in hours)
            hx = x0 + 36
            if htot and inner >= 80:
                put(scr, by, hx, "TIME OF DAY", pal["dim"], curses.A_BOLD)
                streak = stats_streak(app.store)
                if streak >= 2:
                    put(scr, by, hx + 13, f"{streak}-day streak",
                        pal["faint"])
                htop = max(n for _, n in hours)
                hbw = 12
                for i, (lab, n) in enumerate(hours):
                    hy = by + 2 + i
                    put(scr, hy, hx, lab.ljust(9), pal["faint"])
                    filled = round(n / htop * hbw) if htop else 0
                    if filled:
                        put(scr, hy, hx + 10, "\u2588" * filled,
                            pal["green"] if n == htop else pal["sdim"])
                    put(scr, hy, hx + 10 + hbw + 1, str(n), pal["faint"])
            big = stats_weekday(app.store)
            if big:
                put(scr, by + 7, x0 + 2,
                    f"{big[0]} are your biggest listening day",
                    pal["faint"])
            wtop, wtop_n = stats_week_top(app.store)
            if wtop and by + 8 <= y1 - 3:
                put(scr, by + 8, x0 + 2,
                    f"Top this week: {wtop} ({wtop_n} plays)",
                    pal["faint"])
                by += 1
            by += 8
            rep = stats_on_repeat(app.store)
            if rep and by + 2 <= y1 - 3:
                put(scr, by, x0 + 2, "ON REPEAT THIS WEEK", pal["dim"],
                    curses.A_BOLD)
                cx = x0 + 2
                for t, n in rep:
                    label = f"{t.get('title', '?')} \u00d7{n}"
                    w = dlen(label) + 4
                    if cx + w > W - 4:
                        break
                    fill(scr, by + 1, cx, w, pal["pill"])
                    put(scr, by + 1, cx + 2, label, pal["pilldim"])
                    self.hit(cx, by + 1, w, 1, "playtrack",
                             (t, "On repeat"))
                    cx += w + 1
                by += 3
        # rows are (label, subtitle-or-None, count, click action-or-None)
        def block(y, x, w, title, rows):
            put(scr, y, x, title, pal["dim"], curses.A_BOLD)
            if not rows:
                return
            top = max(r[2] for r in rows)
            label_w = max(10, min(24, w // 2))
            bar_w = max(4, w - label_w - 6)
            for i, (label, sub, n, act) in enumerate(rows):
                yy = y + 2 + i * 2
                if yy >= y1 - 3:   # keep the hint line and a blank row clear
                    break
                put(scr, yy, x, f"{i + 1}", pal["faint"])
                put(scr, yy, x + 3, wcut(label, label_w - 3), pal["text"])
                filled = max(1, round(n / top * bar_w))
                put(scr, yy, x + label_w, "█" * filled, pal["green"])
                put(scr, yy, x + label_w + filled + 1, str(n), pal["faint"])
                if sub:
                    # the row below a bar is free: subtitles may run the
                    # full block width
                    put(scr, yy + 1, x + 3, wcut(sub, w - 6), pal["faint"])
                if act:
                    self.hit(x, yy, w, 2 if sub else 1, act[0], act[1])
        last = stats_last_played(app.store)
        song_rows = [(t, (a + "  \u00b7  " + fmt_added(last[vid]))
                      if vid in last else a, n, ("playtrack",
                                {"id": vid, "title": t, "artist": a,
                                 "url": f"https://www.youtube.com/watch?v={vid}",
                                 "dur": None}))
                     for t, a, n, vid in ts]
        block(by, x0 + 2, colw, "TOP ARTISTS",
              [(a, None, n, ("artist", a)) for a, n in ta])
        if half:
            block(by, x0 + 2 + colw + 4, colw, "TOP SONGS", song_rows)
        else:
            gap = by + 2 + min(len(ta), 6) * 2 + 1
            if gap + 4 < y1:
                block(gap, x0 + 2, colw, "TOP SONGS",
                      song_rows[:max(1, (y1 - gap - 3) // 2)])
        self.hint(y1 - 2, x0, "stats")

    def v_playing(self, y0, y1, x0, W):
        app, pal, scr = self.app, self.pal, self.scr
        track = app.current
        width, height = W - x0 - 4, y1 - y0 - 2
        put(scr, y0 + 1, x0 + 2, "N O W   P L A Y I N G", pal["green"], curses.A_BOLD)
        if not track:
            put(scr, y0 + 3, x0 + 2, "Search for a song with / to begin", pal["dim"])
            return
        if app.queue:
            pos = f"{app.qpos + 1} of {len(app.queue)}"
            put(scr, y0 + 1, x0 + 2 + width - dlen(pos), pos, pal["faint"])
        wide = width >= 56
        aw = min(36, max(8, width * 2 // 5)) if wide else min(30, max(8, width // 3))
        ah = max(3, min(aw // 2 + 1, height - (4 if wide else 12)))
        ax = x0 + 2 if wide else x0 + 2 + max(0, (width - aw) // 2)
        ay = y0 + 3
        draw_art(scr, ay, ax, aw, ah, track["id"], pal, icon=IC_NOTE,
                 art=app.cover_for(track["id"], aw, ah))
        tx = ax + aw + 4 if wide else x0 + 2
        ty = ay if wide else ay + ah + 1
        tw = max(8, W - tx - 3)
        ttl = track["title"]
        if dlen(ttl) > tw - 4 and not app.reduced_motion:
            ttl = scroll_window(ttl, tw - 4, app.frame // 2)
        else:
            ttl = wcut(ttl, tw - 4)
        put(scr, ty, tx, ttl, pal["text"], curses.A_BOLD)
        put(scr, ty + 1, tx, wcut(track["artist"], tw), pal["dim"],
            curses.A_UNDERLINE)
        self.hit(tx, ty + 1, min(dlen(track["artist"]), tw), 1,
                 "artist", track["artist"])
        src = "Autoplay" if track.get("auto") else app.play_source
        line = ("From " + src) if src else ""
        n_plays = (app.store.plays.get(track["id"]) or {}).get("n", 0)
        if n_plays:
            line += ("  \u00b7  " if line else "") + f"{n_plays} plays"
        if line:
            put(scr, ty + 2, tx, wcut(line, tw), pal["faint"])
            # the source name opens its library page, like the artist link
            known = src in ("Liked Songs", "Recently Played", "Made for you") \
                or any(pl["name"] == src for pl in app.store.playlists)
            if src and dlen(src) + 5 <= tw:
                if known:
                    put(scr, ty + 2, tx + 5, wcut(src, tw - 5), pal["faint"],
                        curses.A_UNDERLINE)
                self.hit(tx + 5, ty + 2, min(dlen(src), tw - 5), 1,
                         "opensrc", src)
        liked_now = track["id"] in app.liked_ids
        put(scr, ty, tx + tw - 2, IC_HEART if liked_now else IC_HEARTO,
            pal["green"] if liked_now else pal["sdim"], curses.A_BOLD)
        self.hit(tx + tw - 3, ty, 3, 1, "likesong", track)
        state = "Connecting..." if app.loading else ("Paused" if app.mpv.state["pause"] else
                 "Stopped" if app.mpv.state["idle"] else "Playing")
        # chips: state, shuffle mode, repeat, speed
        chips = [(state, "playpause")]
        if app.shuffle:
            chips.append(("Shuffle " + SHUFFLE_LABEL[app.store.shuffle_mode].split(" ")[0], "shuffle"))
        if app.repeat:
            chips.append(("Repeat one" if app.repeat == 2 else "Repeat all", "repeat"))
        if app.speed != 1.0:
            chips.append((f"{app.speed:g}x", "speed"))
        if app.store.eq_preset != "off":
            chips.append(("EQ " + EQ_LABEL[app.store.eq_preset], "eq"))
        if app.store.autoplay:
            chips.append(("Autoplay", "autoplay"))
        if app.sleep_deadline is not None:
            left = max(0, int(app.sleep_deadline - time.monotonic()))
            chips.append((f"Sleep {fmt_t(left)}", "sleep"))
        elif app.sleep_eot:
            chips.append(("Sleep: end of track", "sleep"))
        cx, cy = tx, ty + 3
        for label, tag in chips:
            w = dlen(label) + 2
            if cx + w > tx + tw:
                break
            if cy < y1 - 1:
                fill(scr, cy, cx, w, pal["pill"])
                put(scr, cy, cx + 1, label, pal["pgreen"], curses.A_BOLD)
                self.hit(cx, cy, w, 1, "chip", tag)
            cx += w + 1
        # large progress bar (click or drag to seek)
        st = app.mpv.state
        by = cy + 2
        if by < y1 - 1 and tw >= 20:
            el, du = fmt_t(st.get("pos")), fmt_t(st.get("dur")) if st.get("dur") else "-:--"
            bx0 = tx + dlen(el) + 1
            bw = max(6, tw - dlen(el) - dlen(du) - 2)
            put(scr, by, tx, el, pal["dim"])
            frac = (st["pos"] / st["dur"]) if st.get("dur") else 0.0
            frac = max(0.0, min(1.0, frac))
            knob = int(round(frac * (bw - 1)))
            for i in range(bw):
                if i < knob:
                    put(scr, by, bx0 + i, "━", pal["green"])
                elif i == knob:
                    put(scr, by, bx0 + i, "●", pal["green"], curses.A_BOLD)
                else:
                    put(scr, by, bx0 + i, "─", pal["faint"])
            put(scr, by, bx0 + bw + 1, du, pal["dim"])
            self.hit(bx0, by, bw, 1, "seek", (bx0, bw))
        ey = by + 2
        # narrow: the bars are decorative - drop them when the up-next row
        # would not fit below them
        bars = wide or ey + 3 < y1 - 2
        if bars and ey + 1 < y1 - 1:
            n = min(24, tw)
            for i in range(n):
                v = self.BARS_PAT[(i + app.frame // 2) % len(self.BARS_PAT)]
                ch = "▁" if state != "Playing" or app.reduced_motion else "▁▂▃▄▅▆▇█"[v]
                put(scr, ey, tx + i, ch, pal["green"])
            put(scr, ey + 1, tx, "visual animation, not audio levels", pal["faint"])
        # wide: fill the right column with the artist's other top songs
        if wide:
            my = ey + 3
            more = [t for t in app.artist_tracks(track["artist"])
                    if t["id"] != track["id"]]
            more.sort(key=lambda t: (
                -(app.store.plays.get(t["id"]) or {}).get("n", 0),
                t["title"]))
            if more and my + 2 < y1 - 2:
                put(scr, my, tx, f"MORE FROM {track['artist'].upper()}",
                    pal["dim"], curses.A_BOLD)
                for i, t in enumerate(more):
                    ry = my + 2 + i
                    if ry >= y1 - 2:
                        break
                    put(scr, ry, tx, f"{i + 1}", pal["faint"])
                    put(scr, ry, tx + 3, wcut(t["title"], tw - 14),
                        pal["text"])
                    np_ = (app.store.plays.get(t["id"]) or {}).get("n", 0)
                    if np_:
                        ptxt = f"{np_} plays"
                        put(scr, ry, tx + tw - dlen(ptxt), ptxt,
                            pal["faint"])
                    self.hit(tx, ry, tw, 1, "playtrack",
                             (t, track["artist"]))
        # up next
        uy = ay + ah + 1 if wide else ((ey + 3) if bars else (by + 2))
        if wide and uy + 2 < y1 - 2:
            put(scr, uy, x0 + 2, "UP NEXT", pal["faint"], curses.A_BOLD)
            for j in range(3):
                qi = app.qpos + 1 + j
                if qi >= len(app.queue) or uy + 1 + j >= y1 - 2:
                    break
                nxt = app.queue[qi]
                put(scr, uy + 1 + j, x0 + 2, f"{j + 1}", pal["faint"])
                ntw = max(8, width // 2 - 8)
                put(scr, uy + 1 + j, x0 + 5, wcut(nxt["title"], ntw), pal["text"])
                if nxt.get("auto") and dlen(nxt["title"]) + 2 < ntw:
                    put(scr, uy + 1 + j,
                        x0 + 5 + dlen(nxt["title"]) + 1, IC_AUTO, pal["accent"])
                put(scr, uy + 1 + j, x0 + 5 + width // 2 - 2, wcut(nxt["artist"], max(8, width // 2 - 6)), pal["dim"])
                rx = x0 + 2 + width
                if nxt.get("dur"):
                    dtxt = fmt_t(nxt["dur"])
                    put(scr, uy + 1 + j, rx - dlen(dtxt),
                        dtxt, pal["faint"])
                    rx -= dlen(dtxt) + 1
                if nxt["id"] in app.liked_ids and rx - 1 > x0 + 5 + width // 2:
                    put(scr, uy + 1 + j, rx - 1, IC_HEART, pal["green"])
                self.hit(x0 + 2, uy + 1 + j, width - 2, 1, "qjump", qi)
        elif not wide and uy < y1 - 2 and app.qpos + 1 < len(app.queue):
            nxt = app.queue[app.qpos + 1]
            put(scr, uy, x0 + 2, "Next", pal["faint"], curses.A_BOLD)
            put(scr, uy, x0 + 8, wcut(f"{nxt['title']} - {nxt['artist']}",
                                      width - 8), pal["dim"])
            self.hit(x0 + 2, uy, width - 2, 1, "qjump", app.qpos + 1)
        if y1 - y0 >= 18:
            self.hint(y1 - 2, x0, "playing")

    def v_home(self, y0, y1, x0, W):
        app, pal = self.app, self.pal
        scr = self.scr
        h = time.localtime().tm_hour
        greet = "Good morning" if h < 12 else \
            "Good afternoon" if h < 18 else "Good evening"
        put(scr, y0 + 1, x0 + 2, greet, pal["text"], curses.A_BOLD)
        dtxt = time.strftime("%a %d %b", time.localtime())
        put(scr, y0 + 1, x0 + 4 + dlen(greet), dtxt, pal["faint"])
        streak = stats_streak(app.store)
        gx = x0 + 4 + dlen(greet) + dlen(dtxt) + 2
        if streak >= 2:
            stxt = f"\u00b7 {streak}-day streak"
            put(scr, y0 + 1, gx, stxt, pal["green"])
            gx += dlen(stxt) + 2
        today_min = stats_day_minutes(app.store)[-1]
        if today_min and gx + 14 <= W - 2:
            put(scr, y0 + 1, gx, f"\u00b7 {fmt_listen(today_min)} today",
                pal["faint"])
        fill(scr, y0 + 2, x0 + 2, 6, pal["accent"])   # accent underline

        y = y0 + 4
        if y1 - y0 >= 27 and app.store.history:
            y = self._home_hero(app, pal, scr, y, y1, x0, W)
        y = self._home_tiles(app, pal, scr, y, y1, x0, W)
        if lib_fresh(app.store):
            y = self._home_welcome(app, pal, scr, y, y1, x0, W)
        else:
            y = self._home_mixes(app, pal, scr, y, y1, x0, W)
            y = self._home_similar(app, pal, scr, y, y1, x0, W)
            y = self._home_heavy(app, pal, scr, y, y1, x0, W)
            y = self._home_history(app, pal, scr, y, y1, x0, W)
            y = self._home_liked(app, pal, scr, y, y1, x0, W)
        y = self._home_recent(app, pal, scr, y, y1, x0, W)
        put(scr, y1 - 2, x0 + 2,
            "Type / to search \u00b7 Enter opens \u00b7 R: Made for you \u00b7 ? for shortcuts",
            pal["faint"])

    def _home_hero(self, app, pal, scr, y0, y1, x0, W):
        """'Continue listening' banner: big cover, title, one-click play."""
        t = app.store.history[0]
        aw, ah = 16, 5
        bw = W - x0 - 4
        for j in range(ah):
            fill(scr, y0 + j, x0 + 2, bw, pal["pill"])
        draw_art(scr, y0, x0 + 2, aw, ah, t["id"], pal, icon=IC_NOTE,
                 art=app.cover_for(t["id"], aw, ah))
        tx = x0 + 2 + aw + 3
        tw = max(8, bw - aw - 14)
        put(scr, y0 + 1, tx, "CONTINUE LISTENING", pal["pgreen"], curses.A_BOLD)
        put(scr, y0 + 2, tx, wcut(t["title"], tw), pal["pill"], curses.A_BOLD)
        sub = t["artist"]
        q = app.queue
        if (not app.current and q and 0 <= app.qpos < len(q)
                and q[app.qpos].get("id") == t.get("id")
                and app._resume_t > 5):
            sub += f"  \u00b7  left off at {fmt_t(app._resume_t)}"
        n_plays = (app.store.plays.get(t["id"]) or {}).get("n", 0)
        if n_plays:
            sub += f"  \u00b7  {n_plays} plays"
        put(scr, y0 + 3, tx, wcut(sub, tw), pal["pilldim"])
        bx = x0 + 2 + bw - 9
        put(scr, y0 + 2, bx, f"  {IC_PLAY}  ", pal["btn"], curses.A_BOLD)
        self.hit(x0 + 2, y0, bw, ah, "resume", None)
        return y0 + ah + 1

    def _home_tiles(self, app, pal, scr, y0, y1, x0, W):
        """Shortcut tiles: Liked Songs + your playlists."""
        tiles = [("liked", IC_HEART, "Liked Songs", "liked", None,
                  app.store.liked)]
        for i in app.pinned_order():
            pl = app.store.playlists[i]
            tiles.append(("pl",
                          IC_PIN if pl.get("pinned") else IC_NOTE,
                          pl["name"], "playlist", i, pl["tracks"]))
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
            tracks = t[5]
            if tracks:
                n_tr = len(tracks)
                sub = f"{n_tr} song" + ("s" if n_tr != 1 else "")
                mins = int(sum(x.get("dur") or 0 for x in tracks) // 60)
                cand = f"{sub} \u00b7 {mins} min"
                if mins and dlen(cand) <= tw - 7:
                    sub = cand
                put(scr, y + 2, x + 5, wcut(sub, tw - 7),
                    pal["pilldim"] if i == sel_i else pal["faint"])
            if i == sel_i:
                put(scr, y + 1, x + tw - 3, f" {IC_PLAY} ", pal["btn"],
                    curses.A_BOLD)
            self.hit(x, y, tw, th, "tile", (t[3], t[4]))
            if i == sel_i:
                self.hit(x + tw - 3, y + 1, 3, 1, "tileplay", (t[3], t[4]))
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
        return y0 + 2 + n

    def _home_welcome(self, app, pal, scr, y0, y1, x0, W):
        """First-run panel: three steps to a full home screen."""
        if y0 + 7 >= y1 - 1:
            return y0
        bw = W - x0 - 4
        for j in range(7):
            fill(scr, y0 + j, x0 + 2, bw, pal["pill"])
        put(scr, y0 + 1, x0 + 4, "Welcome to SpotUI", pal["pgreen"],
            curses.A_BOLD)
        put(scr, y0 + 1, x0 + 24, "your library is empty - for now",
            pal["pilldim"])
        steps = [
            "Press  /  and search for a song or artist",
            "Enter plays · a queues · l likes · P saves to a playlist",
            "This screen fills up with your mixes and picks as you listen",
        ]
        for i, txt in enumerate(steps):
            put(scr, y0 + 3 + i, x0 + 4, f"{i + 1}.", pal["pgreen"],
                curses.A_BOLD)
            put(scr, y0 + 3 + i, x0 + 8, wcut(txt, bw - 10), pal["pill"])
        return y0 + 8

    def _home_mixes(self, app, pal, scr, y0, y1, x0, W):
        mixes = daily_mixes(app.store)
        if not mixes or y0 + 6 >= y1 - 1:
            return y0
        put(scr, y0, x0 + 2, "Your mixes", pal["text"], curses.A_BOLD)
        put(scr, y0, x0 + 14, "· press 1-3 to play", pal["faint"])
        cw = 26
        per = max(1, (W - x0 - 4) // cw)
        for i, m in enumerate(mixes[:per]):
            x = x0 + 2 + i * cw
            draw_art(scr, y0 + 1, x, 8, 3, m["artist"], pal, icon=str(i + 1))
            put(scr, y0 + 1, x + 10, wcut(m["name"], cw - 12), pal["text"], curses.A_BOLD)
            put(scr, y0 + 2, x + 10, wcut(m["artist"], cw - 12), pal["dim"])
            if m["with_"]:
                put(scr, y0 + 3, x + 10, wcut("+ " + ", ".join(m["with_"]), cw - 12), pal["faint"])
            self.hit(x, y0 + 1, cw - 1, 3, "mix", i)
        return y0 + 5

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
        full = y0 + 5 < y1 - 2         # covers + title + artist all fit
        if not full and not y0 + 4 < y1 - 2:
            # tight space: compact rows instead of cover cards
            w = W - x0 - 4
            title_w = max(12, int(w * 0.62))
            n = 0
            for i, t in enumerate(items):
                y = y0 + 1 + i
                if y >= y1 - 2 or i >= 3:
                    break
                self.homerow(y, x0 + 2, w, t, i, title_w, vk="similar:")
                n += 1
            return y0 + 2 + n
        cw = 20
        per = max(1, (W - x0 - 4) // cw)
        for i, t in enumerate(items[:per]):
            x = x0 + 2 + i * cw
            draw_art(scr, y0 + 1, x, 8, 3, t["id"], pal,
                     art=app.cover_for(t["id"], 8, 3))
            put(scr, y0 + 4, x, wcut(t["title"], cw - 2), pal["text"])
            if full:
                put(scr, y0 + 5, x, wcut(t["artist"], cw - 2), pal["dim"])
            self.hit(x, y0 + 1, cw - 1, 5 if full else 4,
                     "row", ("similar:", i, True))
        return y0 + (7 if full else 6)

    def _home_heavy(self, app, pal, scr, y0, y1, x0, W):
        """'On repeat' - the songs you played most this week."""
        rep = stats_on_repeat(app.store, top=6)
        if not rep or y0 + 2 >= y1 - 1:
            return y0
        put(scr, y0, x0 + 2, "On repeat", pal["text"], curses.A_BOLD)
        put(scr, y0, x0 + 13, "\u00b7 most played this week", pal["faint"])
        put(scr, y0, W - 13, "Open Stats \u2192", pal["green"])
        self.hit(W - 14, y0, 15, 1, "nav", "stats")
        cw = 20
        per = max(1, (W - x0 - 4) // cw)
        full = y0 + 5 < y1 - 2
        for i, (t, cnt) in enumerate(rep[:per]):
            x = x0 + 2 + i * cw
            draw_art(scr, y0 + 1, x, 8, 3, t["id"], pal,
                     art=app.cover_for(t["id"], 8, 3))
            put(scr, y0 + 4, x, wcut(t["title"], cw - 2), pal["text"])
            if full:
                cap = f"{t['artist']} \u00b7 {cnt} plays"
                put(scr, y0 + 5, x, wcut(cap, cw - 2), pal["dim"])
            self.hit(x, y0 + 1, cw - 1, 5 if full else 4,
                     "playtrack", (t, "On repeat"))
        return y0 + (7 if full else 6)

    def _home_history(self, app, pal, scr, y0, y1, x0, W):
        """'Recently played' — the real play history (mouse = play)."""
        hist = app.store.history
        if not hist or y0 + 1 >= y1 - 1:
            return y0
        put(scr, y0, x0 + 2, "Recently played", pal["text"], curses.A_BOLD)
        put(scr, y0, W - 21, "Open Recently Played \u2192", pal["green"])
        self.hit(W - 22, y0, 24, 1, "tile", ("history", None))
        w = W - x0 - 4
        title_w = max(12, int(w * 0.62))
        n = 0
        for i, t in enumerate(hist):
            y = y0 + 1 + i
            if y >= y1 - 2 or i >= 4:
                break
            self.homerow(y, x0 + 2, w, t, i, title_w, vk="history:")
            n += 1
        return y0 + 2 + n

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
        aw = max(2, x0 + w - 9 - ax)
        acut = wcut(t["artist"], aw)
        put(scr, y, ax, acut, pal["dim"])
        if vk == "history:":
            rel = fmt_ago(t.get("added"))
            rx = ax + dlen(acut) + 2
            if rel and rx + dlen(rel) <= x0 + w - 9:
                put(scr, y, rx, "\u00b7 " + rel, pal["faint"])
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
            w = dlen(q) + 5
            if x + w > W - 4:
                x = x0 + 2
                y += 2
            if y >= y1 - 2:
                break
            fill(scr, y, x, w, pal["pill"])
            put(scr, y, x + 2, q, pal["pilldim"])
            put(scr, y, x + w - 2, "\u00d7", pal["faint"])
            self.hit(x, y, w - 2, 1, "recent", q)
            self.hit(x + w - 2, y, 2, 1, "delrecent", q)
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
            last = self._recent_chips(scr, y0 + 3, x0 + 2, W)
            if not app.store.recent:
                put(scr, y0 + 3, x0 + 2, f"Type in the search bar above — press / "
                                    "to start", pal["faint"])
                return
            y = last + 2
            if app.store.history and y + 2 < y1 - 2:
                put(scr, y, x0 + 2, "Jump back in", pal["text"],
                    curses.A_BOLD)
                w = W - x0 - 4
                for i, t in enumerate(app.store.history[:6]):
                    yy = y + 2 + i
                    if yy >= y1 - 2:
                        break
                    put(scr, yy, x0 + 2, f"{i + 1}", pal["faint"])
                    put(scr, yy, x0 + 5, wcut(t["title"], w // 2 - 8),
                        pal["text"])
                    put(scr, yy, x0 + 4 + w // 2,
                        wcut(t["artist"], w // 2 - 8), pal["dim"])
                    if t.get("dur"):
                        dtxt = fmt_t(t["dur"])
                        put(scr, yy, x0 + 2 + w - dlen(dtxt), dtxt,
                            pal["faint"])
                    self.hit(x0 + 2, yy, w, 1, "playtrack",
                             (t, "Jump back in"))
            return

        # filter chips: All / Songs / Artists (mouse, like Spotify's)
        fx = x0 + 2
        for fname in ("All", "Songs", "Artists"):
            fsel = app.search_filter == fname.lower()
            fch = dlen(fname) + 2
            if fsel:
                fill(scr, y0 + 1, fx, fch, pal["pill"])
                put(scr, y0 + 1, fx + 1, fname, pal["text"], curses.A_BOLD)
            else:
                put(scr, y0 + 1, fx + 1, fname, pal["dim"])
            self.hit(fx, y0 + 1, fch, 1, "sfilter", fname.lower())
            fx += fch + 1
        y0 += 2

        if app.search_filter == "artists":
            rows_a = app.search_artists(app.query, limit=20)
            put(scr, y0 + 1, x0 + 2, "Artists", pal["text"], curses.A_BOLD)
            if not rows_a:
                put(scr, y0 + 3, x0 + 2,
                    f"No artists matching \u201c{wcut(app.query, mw - 30)}\u201d",
                    pal["dim"])
                return
            for i, a in enumerate(rows_a):
                ay = y0 + 2 + i
                if ay >= y1 - 2:
                    break
                put(scr, ay, x0 + 2, f"{i + 1}", pal["faint"])
                put(scr, ay, x0 + 6, wcut(a, mw - 20), pal["text"])
                n_songs = len(app.artist_tracks(a))
                n_plays = app.artist_plays(a)
                detail = (f"{n_songs} songs \u00b7 {n_plays} plays"
                          if n_songs and n_plays else
                          f"{n_songs} songs" if n_songs else "Artist")
                put(scr, ay, x0 + 8 + min(dlen(a), mw - 20), detail,
                    pal["faint"])
                self.hit(x0 + 2, ay, mw - 4, 1, "artist", a)
            return

        artists = app.search_artists(app.query) if app.search_filter == "all" else []
        if artists:
            put(scr, y0 + 1, x0 + 2, "Artists", pal["text"], curses.A_BOLD)
            x = x0 + 10
            for a in artists:
                w = dlen(a) + 4
                if x + w > W - 4:
                    break
                fill(scr, y0 + 1, x, w, pal["pill"])
                put(scr, y0 + 1, x + 2, a, pal["pilldim"])
                self.hit(x, y0 + 1, w, 1, "artist", a)
                x += w + 1
            y0 += 2

        pls = app.search_playlists(app.query) if app.search_filter == "all" \
            else []
        if pls:
            put(scr, y0 + 1, x0 + 2, "Playlists", pal["text"], curses.A_BOLD)
            x = x0 + 12
            for pidx, p in pls:
                label = f"{p['name']} \u00b7 {len(p['tracks'])}"
                w = dlen(label) + 4
                if x + w > W - 4:
                    break
                fill(scr, y0 + 1, x, w, pal["pill"])
                put(scr, y0 + 1, x + 2, label, pal["pilldim"])
                self.hit(x, y0 + 1, w, 1, "libitem", ("playlist", pidx))
                x += w + 1
            y0 += 2

        tracks = app.results
        if not tracks:
            put(scr, y0 + 1, x0 + 2,
                f"No results found for “{wcut(app.query, mw - 30)}”",
                pal["dim"])
            put(scr, y0 + 2, x0 + 2,
                "Check spelling, or try fewer / different words",
                pal["faint"])
            if app.store.recent:
                put(scr, y0 + 4, x0 + 2, "Recent searches", pal["text"],
                    curses.A_BOLD)
                self._recent_chips(scr, y0 + 6, x0 + 2, W)
            return

        top = tracks[0]
        # Strong artist match (exact or prefix): the top-result card becomes
        # the artist, like Spotify's Top result, and the side list keeps
        # every song.
        top_artist = None
        if artists:
            na, nq = app._norm_artist(artists[0]), app._norm_artist(app.query)
            if nq and na.startswith(nq):
                top_artist = artists[0]
        cw = min(34, mw - 4)
        ch = 9
        # card only when width fits a side list AND rows remain below it
        card = ((W - (x0 + cw + 6) - 2) >= 40
                and (y1 - y0) - (ch + 3) >= 5)
        if card:
            box(scr, y0 + 1, x0 + 2, cw, ch, pal["faint"], pal["text"])
            if top_artist:
                draw_art(scr, y0 + 2, x0 + 4, cw - 4, 3, top_artist, pal,
                         icon=IC_NOTE)
                put(scr, y0 + 5, x0 + 4, wcut(top_artist, cw - 6),
                    pal["text"], curses.A_BOLD)
                n_songs = len(app.artist_tracks(top_artist))
                n_plays = app.artist_plays(top_artist)
                detail = (f"{n_songs} songs · {n_plays} plays"
                          if n_songs and n_plays else
                          f"{n_songs} songs" if n_songs else "")
                sub = "Artist" + (f" • {detail}" if detail else "")
                put(scr, y0 + 6, x0 + 4, wcut(sub, cw - 6), pal["dim"])
                self.hit(x0 + 2, y0 + 1, cw, ch, "artist", top_artist)
                fy = y0 + 7
                atracks = app.artist_tracks(top_artist) or tracks
                put(scr, fy, x0 + cw - 6, f" {IC_PLAY} ", pal["btn"],
                    curses.A_BOLD)
                self.hit(x0 + cw - 7, fy, 3, 1, "playall",
                         ("search:", atracks))
            else:
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
            start = 0 if top_artist else 1
            for i in range(start, min(start + 5, len(tracks))):
                t = tracks[i]
                y = ly0 + (i - start) * 2
                if y + 2 > y0 + ch:
                    break
                self.row(ly0 + (i - start) * 2, lx0, lw, t, i,
                         "search:", i, compact=True)
            fy0 = y0 + ch + 1
        else:
            # short/narrow terminal: skip the card, list uses the full width
            fy0 = y0 + 1

        put(scr, fy0, x0 + 2, "All", pal["text"], curses.A_BOLD)
        if tracks:
            put(scr, fy0, x0 + 6, f"{len(tracks)} songs", pal["faint"])
            qall = "Queue all →"
            qx = x0 + 8 + dlen(f"{len(tracks)} songs")
            if qx + dlen(qall) <= W - 4:
                put(scr, fy0, qx, qall, pal["green"])
                self.hit(qx, fy0, dlen(qall), 1, "queueall", None)
        self.list_header(fy0 + 1, x0 + 2, mw - 4, show_date=False)
        self.track_list(fy0 + 2, y1 - 2, x0 + 2, mw - 4, tracks, "search:",
                        show_date=False)
        self.hint(y1 - 2, x0, "search")

    def _recent_chips(self, scr, y, x0, W):
        """Recent-search pills with click-to-search and ×-to-remove.

        Returns the row of the last chip line, so callers can stack more
        content below."""
        app, pal = self.app, self.pal
        x = x0
        for q in app.store.recent:
            w = dlen(q) + 5
            if x + w > W - 4:
                x = x0
                y += 2
            fill(scr, y, x, w, pal["pill"])
            put(scr, y, x + 2, q, pal["pilldim"])
            put(scr, y, x + w - 2, "\u00d7", pal["faint"])
            self.hit(x, y, w - 2, 1, "recent", q)
            self.hit(x + w - 2, y, 2, 1, "delrecent", q)
            x += w + 1
        return y

    def v_collection(self, y0, y1, x0, W, kind, arg):
        app, pal = self.app, self.pal
        scr = self.scr
        if kind == "liked":
            pl = {"name": "Liked Songs", "tracks": app.store.liked}
        elif kind == "history":
            pl = {"name": "Recently Played", "tracks": app.store.history}
        else:
            try:
                pl = app.store.playlists[arg]
            except IndexError:
                return
        eyebrow = "HISTORY" if kind == "history" else "PLAYLIST"
        vk = app.key()
        tracks = app.view_tracks(vk)

        cy = y0 + 1
        # header gradient band in the collection's own colour family
        fi = art_fam(pl["name"])
        band = ["g{0}1", "g{0}1", "g{0}2", "g{0}3"]
        for j, name in enumerate(band):
            fill(scr, cy + j, x0, W - x0, pal[name.format(fi)])
        icon = {"liked": IC_HEART, "history": IC_HIST}.get(kind, IC_NOTE)
        if kind == "playlist" and len(tracks) >= 4:
            # Spotify-style 2x2 mosaic of the first four covers
            for qi, t in enumerate(tracks[:4]):
                draw_art(scr, cy + (qi // 2) * 2, x0 + 2 + (qi % 2) * 5,
                         5, 2, t["id"], pal,
                         art=app.cover_for(t["id"], 5, 2))
        else:
            draw_art(scr, cy, x0 + 2, 10, 4, pl["name"], pal,
                     icon=icon,
                     art=app.cover_for(tracks[0]["id"] if tracks else None, 10, 4))
        hx = x0 + 15
        put(scr, cy, hx, eyebrow, pal[f"g{fi}1"], curses.A_BOLD)
        put(scr, cy + 1, hx, wcut(pl["name"].upper(), W - hx - 4),
            pal[f"g{fi}1"], curses.A_BOLD)
        sub = fmt_total(tracks)
        nplays = plays_for(tracks, app.store.plays)
        if nplays:
            sub += f" \u00b7 {nplays} plays"
        if kind == "history" and app.store.hist_dedupe:
            sub += " \u00b7 repeats hidden"
        if kind == "playlist" and pl.get("enhanced"):
            sub += " \u00b7 Enhanced"
        if kind in ("liked", "playlist"):
            ym = time.strftime("%Y-%m")
            new = sum(1 for t in tracks
                      if str(t.get("added") or "").startswith(ym))
            if new:
                sub += f" \u00b7 {new} new this month"
        put(scr, cy + 2, hx, sub, pal[f"g{fi}d"])

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
        self.list_header(ly, x0 + 2, W - x0 - 4, show_date=True, kind=kind)
        self.track_list(ly + 1, y1 - 2, x0 + 2, W - x0 - 4, tracks, vk,
                        show_date=True)
        self.hint(y1 - 2, x0, kind)
        if not tracks and kind == "history":
            put(scr, ly + 2, x0 + 5,
                "Songs you play will show up here.", pal["faint"])

    def v_artist(self, y0, y1, x0, W):
        app, pal = self.app, self.pal
        scr = self.scr
        _, name = app.stack[-1]
        name = name or ""
        tracks = app.view_tracks()
        vk = app.key()
        cy = y0 + 1
        fi = art_fam(name)
        band = ["g{0}1", "g{0}1", "g{0}2", "g{0}3"]
        for j, nm in enumerate(band):
            fill(scr, cy + j, x0, W - x0, pal[nm.format(fi)])
        draw_art(scr, cy, x0 + 2, 10, 4, name, pal, icon=IC_NOTE,
                 art=app.cover_for(tracks[0]["id"] if tracks else None, 10, 4))
        hx = x0 + 15
        put(scr, cy, hx, "ARTIST", pal[f"g{fi}1"], curses.A_BOLD)
        put(scr, cy + 1, hx, wcut(name.upper() or "UNKNOWN", W - hx - 4),
            pal[f"g{fi}1"], curses.A_BOLD)
        if tracks:
            sub = (fmt_total(tracks) + " in your library"
                   if app.artist_tracks(name) else
                   fmt_total(tracks) + " - from YouTube")
            nplays = app.artist_plays(name)
            if nplays:
                sub += f" \u00b7 {nplays} plays"
            amins = app.artist_minutes(name)
            if amins:
                sub += f" \u00b7 ~{amins} listened"
        elif name in app._artist_busy:
            sub = "Searching YouTube..."
        else:
            sub = "Nothing in your library yet"
        put(scr, cy + 2, hx, sub, pal[f"g{fi}d"])
        by = cy + 4
        put(scr, by, x0 + 3, f" {IC_PLAY} ", pal["btn"], curses.A_BOLD)
        self.hit(x0 + 2, by - 1 if by else by, 5, 2, "playall", (vk, tracks))
        put(scr, by, x0 + 9, IC_SHUF,
            pal["green"] if app.shuffle else pal["dim"], curses.A_BOLD)
        self.hit(x0 + 8, by - 1, 3, 2, "shuffle")
        ly = by + 2
        # Spotify-style Popular: the artist's most played songs, from local
        # play counts, above the full list (only when tall enough to keep
        # several full-list rows visible).
        pop = sorted((t for t in tracks
                      if (app.store.plays.get(t["id"]) or {}).get("n")),
                     key=lambda t: (-app.store.plays[t["id"]]["n"],
                                    t["title"]))[:5]
        if pop and y1 - ly >= 14:
            put(scr, ly, x0 + 2, "POPULAR", pal["dim"], curses.A_BOLD)
            pw = W - x0 - 4
            for i, t in enumerate(pop):
                py = ly + 1 + i
                playing = (app.current and app.current["id"] == t["id"]
                           and not app.mpv.state["idle"])
                if playing:
                    put(scr, py, x0 + 2, eq_bars(app)[:3], pal["green"],
                        curses.A_BOLD)
                else:
                    put(scr, py, x0 + 2, f"{i + 1}", pal["faint"])
                put(scr, py, x0 + 5, wcut(t["title"], pw - 20),
                    pal["green"] if playing else pal["text"],
                    curses.A_BOLD if playing else 0)
                pn = f"{app.store.plays[t['id']]['n']} plays"
                put(scr, py, x0 + 2 + pw - dlen(pn), pn, pal["faint"])
                self.hit(x0 + 2, py, pw, 1, "playat", (vk, pop, i))
            ly += len(pop) + 2
        # other artists from your own play counts, as clickable chips
        # (local data only - no recommendation graph behind it)
        if y1 - ly >= 16:
            norm = app._norm_artist(name)
            others = {}
            for p in app.store.plays.values():
                a = (p.get("artist") or "").strip()
                if a and app._norm_artist(a) != norm:
                    others[a] = others.get(a, 0) + p["n"]
            others = sorted(others.items(), key=lambda kv: (-kv[1], kv[0]))
            if others:
                put(scr, ly, x0 + 2, "MORE ARTISTS YOU PLAY", pal["dim"],
                    curses.A_BOLD)
                cx = x0 + 2
                for a, _ in others:
                    w = dlen(a) + 4
                    if cx + w > W - 4:
                        break
                    fill(scr, ly + 1, cx, w, pal["pill"])
                    put(scr, ly + 1, cx + 2, a, pal["pilldim"])
                    self.hit(cx, ly + 1, w, 1, "artist", a)
                    cx += w + 1
                ly += 3
        self.list_header(ly, x0 + 2, W - x0 - 4, show_date=True)
        self.track_list(ly + 1, y1, x0 + 2, W - x0 - 4, tracks, vk,
                        show_date=True)
        if not tracks:
            if name in app._artist_busy:
                put(scr, ly + 2, x0 + 5,
                    SPIN[(app.frame // 3) % len(SPIN)] + " Searching YouTube...",
                    pal["dim"])
            else:
                put(scr, ly + 2, x0 + 5,
                    f"No YouTube results for {wcut(name, 30)} either",
                    pal["faint"])

    def v_similar(self, y0, y1, x0, W):
        """Made for you as a full list - the keyboard way into the picks."""
        app, pal, scr = self.app, self.pal, self.scr
        cache = app.store.similar or {}
        items = cache.get("items") or []
        seed = cache.get("seed") or ""
        skind = cache.get("kind") or "artist"
        put(scr, y0 + 1, x0 + 2, "Made for you", pal["text"], curses.A_BOLD)
        if seed:
            label = (f"in the style of {seed}" if skind == "artist"
                     else f"after \u201c{seed}\u201d")
            put(scr, y0 + 1, x0 + 16, wcut(label, W - x0 - 18), pal["faint"])
        if not items:
            put(scr, y0 + 3, x0 + 2,
                "No picks yet - play something, or press R to look now",
                pal["dim"])
            self.hint(y1 - 2, x0, "similar")
            return
        ly = y0 + 3
        self.list_header(ly, x0 + 2, W - x0 - 4, show_date=False)
        self.track_list(ly + 1, y1 - 2, x0 + 2, W - x0 - 4, items,
                        "similar:", show_date=False)
        self.hint(y1 - 2, x0, "similar")

    def v_queue(self, y0, y1, x0, W):
        app, pal = self.app, self.pal
        scr = self.scr
        put(scr, y0 + 1, x0 + 2, "Queue", pal["text"], curses.A_BOLD)
        if app.queue:
            label = f"{len(app.queue)} songs"
            left = fmt_remaining(app.queue[max(0, app.qpos):])
            if left:
                label += f", {left}"
                ends = fmt_ends(app.queue[max(0, app.qpos):],
                                app.mpv.state.get("pos") or 0)
                if ends:
                    label += f" · {ends}"
            put(scr, y0 + 1, x0 + 9, label, pal["faint"])
            if app.play_source:
                flabel = f"  \u00b7  From {app.play_source}"
                put(scr, y0 + 1, x0 + 9 + dlen(label), flabel,
                    pal["faint"])
                label += flabel
            auto_tail = [t for t in app.queue[max(0, app.qpos):]
                         if t.get("auto")]
            n_auto = len(auto_tail)
            if n_auto:
                legend = f"  ·  {IC_AUTO} {n_auto} autoplayed"
                arem = fmt_remaining(auto_tail)
                if arem:
                    legend += f" ({arem[:-5]})"   # strip " left"
                lx = x0 + 9 + dlen(label)
                put(scr, y0 + 1, lx, legend, pal["faint"])
                self.hit(lx, y0 + 1, dlen(legend), 1, "dropauto")
        y = y0 + 3
        if app.current:
            put(scr, y, x0 + 2, "Now playing", pal["dim"], curses.A_BOLD)
            self.row(y + 1, x0 + 2, W - x0 - 4, app.current, 0,
                     "queue:", app.qpos, show_date=False, current=True)
            st = app.mpv.state
            if not st["idle"] and st["dur"] > 0 and W - x0 - 6 >= 10:
                bw = W - x0 - 6
                fill_n = int(bw * min(1.0, max(0.0, st["pos"] / st["dur"])))
                put(scr, y + 2, x0 + 3, "\u2501" * fill_n, pal["green"])
                put(scr, y + 2, x0 + 3 + fill_n, "\u2500" * (bw - fill_n),
                    pal["dim"])
                self.hit(x0 + 3, y + 2, bw, 1, "seek", (x0 + 3, bw))
            y += 3
        put(scr, y, x0 + 2, "Next up", pal["dim"], curses.A_BOLD)
        first = max(0, app.qpos + 1)
        if first >= len(app.queue):
            put(scr, y + 1, x0 + 5, "Queue is empty - press a on a song "
                "to add it", pal["faint"])
            return
        # Reuse list scrolling but retain original queue indices for input.
        visible = max(0, y1 - y - 3)   # one row spare for the hint line
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
        self.hint(y1 - 2, x0, "queue")

    # --------------------------------------------------------- list bits --
    def list_header(self, y, x0, w, show_date, kind=None):
        """Column captions that share col_widths() with the rows below.

        In sortable views the active column gets an arrow and every column
        is clickable (click the active one again to restore the list order).
        """
        pal = self.pal
        num_w, title_w, chan_w, date_w, dur_w, heart_w = \
            self.col_widths(w, show_date)
        tx = x0 + num_w
        cx = tx + title_w + 2
        mode = self.app.store.sort_mode
        sortable = kind in SORTABLE_KINDS

        def cap(text, col):
            return text + " \u25b2" if sortable and mode == col else text

        put(self.scr, y, tx, cap("TITLE", "title"), pal["faint"],
            curses.A_BOLD)
        if chan_w:
            put(self.scr, y, cx, cap("CHANNEL", "artist"), pal["faint"],
                curses.A_BOLD)
        if show_date and date_w:
            put(self.scr, y, cx + chan_w + 2, cap("DATE ADDED", "added"),
                pal["faint"], curses.A_BOLD)
        put(self.scr, y, x0 + w - dur_w, cap("\u23f1", "dur"), pal["faint"],
            curses.A_BOLD)
        if sortable:
            self.hit(tx, y, title_w, 1, "sort", "title")
            if chan_w:
                self.hit(cx, y, chan_w, 1, "sort", "artist")
            if show_date and date_w:
                self.hit(cx + chan_w + 2, y, date_w, 1, "sort", "added")
            self.hit(x0 + w - dur_w, y, dur_w, 1, "sort", "dur")

    def col_widths(self, w, show_date):
        num_w, dur_w, heart_w = 4, 7, 2
        date_w = 12 if show_date and w >= 66 else 0
        fixed = num_w + dur_w + heart_w + date_w + 6
        available = max(0, w - fixed)
        title_w = max(8, int(available * 0.60))
        chan_w = max(0, available - title_w)
        if chan_w < 8:
            title_w = max(8, available)
            chan_w = 0
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
        cx_safe = x0 + num_w + title_w + 2   # artist column start

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
        if t.get("auto") or t.get("enhanced"):
            ax = tx + min(dlen(t["title"]), title_w) + 1
            if ax < cx_safe - 1:
                put(scr, y, ax, IC_AUTO, cp(pal["accent"]))
        elif t["id"] in app.blocked_ids:
            ax = tx + min(dlen(t["title"]), title_w) + 1
            if ax < cx_safe - 1:
                put(scr, y, ax, "\u00d7", cp(pal["faint"]))

        cx = tx + title_w + 2
        if chan_w:
            put(scr, y, cx, wcut(t["artist"], chan_w), cp(pal["dim"]))
            ptxt = ""
            if (vk.startswith("search:")
                    or (vk.startswith("history") and app.store.hist_dedupe)):
                # songs you played before carry their local play count
                np_ = (app.store.plays.get(t["id"]) or {}).get("n", 0)
                ptxt = f" \u00b7 {np_} plays" if np_ else ""
            elif vk.startswith("queue") and not t.get("auto"):
                # queue rows note where a song came from when it differs
                # from the queue's own origin (manual adds, other lists)
                src_ = (t.get("src") or "").strip()
                if src_ and src_ != (app.play_source or ""):
                    ptxt = f" \u00b7 {src_}"
            ax = cx + min(dlen(t["artist"]), chan_w)
            if ptxt:
                room = cx + chan_w - ax
                if vk.startswith("queue"):
                    # queue rows have no date column: the free space up to
                    # the duration column may hold the tag
                    room = max(room, x0 + w - dur_w - 2 - ax)
                if 4 <= room < dlen(ptxt):
                    ptxt = wcut(ptxt, room)
                if dlen(ptxt) <= room:
                    put(scr, y, ax, ptxt, cp(pal["faint"]))

        if show_date and date_w:
            dx = cx + chan_w + 2
            put(scr, y, dx, wcut(fmt_added(t.get("added")), date_w),
                pal["faint"])

        lx = x0 + w - dur_w - heart_w - 2
        liked = t["id"] in app.liked_ids
        if liked or selected:
            put(scr, y, lx, IC_HEART if liked else IC_HEARTO,
                pal["green"] if liked else cp(pal["dim"]))
        put(scr, y, x0 + w - dur_w, fmt_t(t.get("dur")).rjust(dur_w - 1),
            cp(pal["dim"]))

        self.hit(x0, y, w, 1, "row", (vk, real_idx, False))
        if chan_w and t.get("artist"):
            self.hit(cx, y, chan_w, 1, "artist", t["artist"])

    def hint(self, y, x0, kind):
        """Context key hints on a view's bottom row."""
        text = VIEW_HINTS.get(kind)
        if text:
            put(self.scr, y, x0 + 2, text, self.pal["faint"])

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
        tw = 30 if W >= 104 else (20 if W >= 86 else 12)
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
            # the elapsed time starts at bx-5 == 7+tw; keep a 1-col gap so
            # a long artist name never touches it on narrow terminals
            put(scr, y0 + 1, 7, wcut(cur["artist"], max(4, tw - 1)),
                pal["bsdim"])
            liked = cur["id"] in app.liked_ids
            put(scr, y0, hx, IC_HEART if liked else IC_HEARTO,
                pal["bsgreen"] if liked else pal["bsdim"], curses.A_BOLD)
            self.hit(2, y0, 3, 2, "playing")
            self.hit(7, y0, tw, 2, "playing")
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
        # reserve room for a speed badge after the duration when needed
        bw = max(4, min(132, spx - bx - (13 if app.speed != 1.0 else 6)))
        cx = max(hx + 4, (W - 22) // 2)     # transport cluster centered
        if cx + 22 > rz:
            cx = max(hx + 4, rz - 22)
        x = cx
        put(scr, y0, x, IC_SHUF,
            pal["bsgreen"] if app.shuffle else pal["bsdim"], curses.A_BOLD)
        if app.shuffle and app.store.shuffle_mode != "spread":
            put(scr, y0, x + 1, app.store.shuffle_mode[0].upper(),
                pal["bsgreen"], curses.A_BOLD)
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
        if app.store.time_left and dur:
            rem = "-" + fmt_t(max(0.0, dur - pos))
            put(scr, y0 + 1, bx - 5 - max(0, len(rem) - 5), rem, pal["bsdim"])
        else:
            put(scr, y0 + 1, bx - 5, fmt_t(pos).rjust(4), pal["bsdim"])
        self.hit(bx - 6, y0 + 1, 6, 1, "toggletime")
        for i in range(bw):
            if abs(i - frac * bw) < 0.5:
                ch, p = "●", pal["bsgreen"]
            else:
                ch = "─"
                p = pal["bsdim"] if i <= frac * bw else pal["bbar"]
            put(scr, y0 + 1, bx + i, ch, p,
                curses.A_BOLD if ch == "●" else 0)
        put(scr, y0 + 1, bx + bw + 1, fmt_t(dur), pal["bsdim"])
        if app.speed != 1.0:
            sptxt = f"{app.speed:g}x"
            sx = bx + bw + 7      # past the duration text (4 cells + gap)
            if sx + len(sptxt) <= spx:
                put(scr, y0 + 1, sx, sptxt, pal["bsgreen"],
                    curses.A_BOLD)
        self.hit(bx, y0 + 1, bw, 1, "seek", (bx, bw))

        # --- right: queue + volume (squeezed on narrow terminals)
        put(scr, y0, qw, IC_QUEUE, pal["bsdim"], curses.A_BOLD)
        self.hit(qw - 1, y0, 3, 1, "queue")
        put(scr, y0 + 1, vx - 4,
            IC_SPK + ("\u00d7" if app._muted_from is not None else "))"),
            pal["bsdim"])
        self.hit(vx - 4, y0 + 1, 3, 1, "mute")
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
        pal = self.pal
        rows = [
            ("/", "focus search"), ("j/k or ↑/↓", "move"),
            ("g / G", "top / bottom of a list"),
            ("1-3", "home: play a daily mix"),
            ("z", "hide / show the sidebar"),
            ("Enter", "play selection"), ("Space", "play / pause"),
            ("n / p", "next / prev"), ("← / →", "seek ±10s"),
            ("+ / -", "volume"), ("M", "mute / unmute"), ("a", "add to queue"), ("A", "play next"), ("J / K", "reorder queue / playlist"), ("W", "save queue as playlist"), ("C", "clear upcoming queue"), ("D", "queue: drop autoplayed / history: hide repeats"), ("X", "playlist: export JSON"), ("Y", "copy song link / stats summary"), ("I", "song info"), ("O", "open song in browser"), ("x", "hide song from suggestions"), ("Q", "search: queue all results"), (".", "jump to the playing song"), ("N", "playlist: duplicate"), ("B", "playlist: merge into another"), ("w", "playlist: pin to the top"), ("h", "playlist: enhance with suggestions"), ("L", "playlist: like every song"), ("V", "playlist: copy tracklist"), ("[ / ]", "speed down / up"), ("T", "theme picker (live preview)"), ("i", "listening stats"), ("S", "shuffle mode"), ("u", "autoplay"), ("b", "private session"), ("U", "undo delete"), ("Z", "shuffle whole library"), ("E", "equalizer"), ("y", "recently played"), ("o", "open artist"),
            ("F", "find in a list"), ("m", "sort list"), ("l", "like / unlike"), ("s", "shuffle"),
            ("r", "repeat"), ("R", "new picks"),
            ("v", "queue view"), ("f", "now playing"), ("t", "sleep timer: presets, end of track, custom"),
            ("c", "create playlist"), ("P", "add to playlist"),
            ("d", "delete from list"), ("e / D", "playlist: rename / delete"),
            ("Backspace", "back"),
            ("?", "this help"), ("q", "quit"),
        ]
        w = min(100, W - 4)
        columns = 2 if w >= 90 else 1
        capacity = max(1, min(12, self.scr.getmaxyx()[0] - 7))
        page_size = capacity * columns
        self.app.help_pages = max(1, (len(rows) + page_size - 1) // page_size)
        self.app.help_page = min(self.app.help_page, self.app.help_pages - 1)
        rows = rows[self.app.help_page * page_size:(self.app.help_page + 1) * page_size]
        h = min(capacity, (len(rows) + columns - 1) // columns) + 5
        y = max(1, (self.scr.getmaxyx()[0] - h) // 2)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        put(self.scr, y + 1, x + 2, "Keyboard shortcuts", pal["side"], curses.A_BOLD)
        colw = (w - 4) // columns
        for i, (key, description) in enumerate(rows):
            ci, ri = divmod(i, capacity)
            xx, yy = x + 2 + ci * colw, y + 3 + ri
            put(self.scr, yy, xx, wcut(key, 10), pal["sgreen"], curses.A_BOLD)
            put(self.scr, yy, xx + 12, wcut(description, colw - 13), pal["sdim"])
        footer = f"Page {self.app.help_page + 1}/{self.app.help_pages}  j/k: page  Esc: close"
        put(self.scr, y + h - 2, x + 2, wcut(footer, w - 4), pal["sfaint"])
        self.hit(x, y, w, h, "helpclose")

    def theme_modal(self, W):
        app, pal = self.app, self.pal
        w = 36
        h = len(THEME_NAMES) + 5
        H = self.scr.getmaxyx()[0]
        y = max(1, (H - h) // 2)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        put(self.scr, y + 1, x + 2, "Theme", pal["side"], curses.A_BOLD)
        for i, name in enumerate(THEME_NAMES):
            ry = y + 3 + i
            sel = i == app.theme_idx
            if sel:
                fill(self.scr, ry, x + 1, w - 2, pal["pill"])
            put(self.scr, ry, x + 3, name,
                pal["pill"] if sel else pal["side"],
                curses.A_BOLD if sel else 0)
            if name == app.theme_orig:
                put(self.scr, ry, x + w - 9, "saved",
                    pal["pilldim"] if sel else pal["sfaint"])
        put(self.scr, y + h - 2, x + 2,
            "j/k: preview \u00b7 Enter: keep \u00b7 Esc: revert",
            pal["sfaint"])

    def info_modal(self, W):
        app, pal = self.app, self.pal
        rows = app.info_rows()
        w = 56
        h = len(rows) + 5
        H = self.scr.getmaxyx()[0]
        y = max(1, (H - h) // 2)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        put(self.scr, y + 1, x + 2, "Song info", pal["side"], curses.A_BOLD)
        lw = max(dlen(label) for label, _ in rows)
        for i, (label, value) in enumerate(rows):
            put(self.scr, y + 3 + i, x + 2, label, pal["sfaint"])
            put(self.scr, y + 3 + i, x + 4 + lw,
                wcut(str(value), w - lw - 7), pal["side"])
        put(self.scr, y + h - 2, x + 2,
            "Y: copy link \u00b7 O: open in browser \u00b7 Esc: close",
            pal["sfaint"])

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

    def sleep_modal(self, y0, W):
        app, pal = self.app, self.pal
        w, h = 44, 7
        y = max(2, y0 - 8)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        put(self.scr, y + 1, x + 2, "Sleep timer - custom", pal["side"],
            curses.A_BOLD)
        fill(self.scr, y + 3, x + 2, w - 4, pal["pill"])
        buf = app.sleep_buf or ""
        put(self.scr, y + 3, x + 3, wcut(buf + " min" if buf else "minutes",
                                         w - 8),
            pal["pill"] if buf else pal["pilldim"],
            curses.A_BOLD if buf else 0)
        put(self.scr, y + h - 2, x + 2, "Enter: start \u00b7 Esc: cancel",
            pal["sfaint"])

    def pick_modal(self, y0, W):
        app, pal = self.app, self.pal
        view = app.pick_view()
        w = 44
        h = min(len(view) + 5, 15)
        y = max(1, (self.scr.getmaxyx()[0] - h) // 2)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        put(self.scr, y + 1, x + 2, wcut(app.pick_title, w - 4), pal["side"],
            curses.A_BOLD)
        if app.pick_filter:
            put(self.scr, y + 2, x + 2,
                wcut("filter: " + app.pick_filter + "\u258c", w - 4),
                pal["green"])
        else:
            put(self.scr, y + 2, x + 2, "type to filter", pal["sfaint"])
        count = max(1, h - 5)
        start = max(0, min(app.pick_idx - count + 1,
                           len(view) - count))
        for i in range(start, min(start + count, len(view))):
            r = view[i]
            yy = y + 4 + i - start
            sel = i == app.pick_idx
            if sel:
                fill(self.scr, yy, x + 2, w - 4, pal["hover"])
            suffix = ""
            if not r.get("new") and r.get("n") is not None:
                suffix = str(r["n"])
                if r.get("has"):
                    suffix = "\u2713 " + suffix
            name_w = w - 8 - (dlen(suffix) + 2 if suffix else 0)
            put(self.scr, yy, x + 4, wcut(r["name"], name_w),
                pal["hover"] if sel else pal["sdim"],
                curses.A_BOLD if sel else 0)
            if suffix:
                put(self.scr, yy, x + w - 3 - dlen(suffix), suffix,
                    pal["hover"] if sel
                    else (pal["green"] if r.get("has") else pal["sfaint"]))
            self.hit(x, yy, w, 1, "pickrow", i)
        if app.pick_filter and len(view) == 1:
            put(self.scr, y + 4, x + 4, "no playlists match", pal["sfaint"])

    def clearhist_modal(self, W):
        app, pal = self.app, self.pal
        w, h = min(62, W - 4), 9
        y = max(1, (self.scr.getmaxyx()[0] - h) // 2)
        x = (W - w) // 2
        box(self.scr, y, x, w, h, pal["dim"], pal["side"])
        put(self.scr, y + 1, x + 2, "Clear play history?", pal["side"],
            curses.A_BOLD)
        put(self.scr, y + 3, x + 2,
            "Recently Played, play counts and stats reset.", pal["sdim"])
        put(self.scr, y + 4, x + 2,
            "Playlists and Liked Songs stay.", pal["sdim"])
        put(self.scr, y + 6, x + 2, "y: clear history   n / Esc: cancel",
            pal["sfaint"])

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
        SW = 0 if app.store.zen else max(24, min(32, W // 4))
        y1 = H - 3
        app.sw_bounds = (SW, 3, y1)
        self.topbar(0, W, SW)
        if SW:
            self.sidebar(3, y1, SW)
        self.main(3, y1, SW, W)
        self.playerbar(H - 3, W)
        if app.show_help:
            self.help(3, W)
        if app.mode == "name":
            self.name_modal(y1, W)
        if app.mode == "sleep":
            self.sleep_modal(y1, W)
        if app.mode == "pick":
            self.pick_modal(y1, W)
        if app.mode == "info":
            self.info_modal(W)
        if app.mode == "theme":
            self.theme_modal(W)
        if app.mode == "confirm_delete":
            self.delete_modal(W)
        if app.mode == "confirm_clearhist":
            self.clearhist_modal(W)
        if not app.show_help and app.mode not in ("name", "pick", "confirm_delete", "confirm_clearhist", "sleep", "info",
                          "theme"):
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
            if k == "\t":
                order = ("all", "songs", "artists")
                app.search_filter = order[
                    (order.index(app.search_filter) + 1) % len(order)]
                app.toast_now("Search filter: " + app.search_filter)
                return
            if k in ("\n", "\r"):
                app.submit_search()
                return
            if k == "\x1b":
                app.mode = "normal"
                return
            if k in ("\x7f", "\b"):
                app.query = app.query[:-1]
                app._edit_t = time.time()
                return
            if k >= " " and unicodedata.category(k)[0] != "C":
                app.query += k
                app._edit_t = time.time()
                return
        else:
            if k in (curses.KEY_BACKSPACE, 127, 8, 263):
                app.query = app.query[:-1]
                app._edit_t = time.time()
            elif k == curses.KEY_ENTER or k == 10 or k == 13:
                app.submit_search()
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

    if app.mode == "confirm_clearhist":
        if k in ("y", "Y"):
            app.clear_history()
            app.mode = "normal"
        elif k in ("n", "N", "q", "\x1b", 27):
            app.mode = "normal"
        return

    if app.mode == "find":
        if k in ("\n", "\r", curses.KEY_ENTER, 10, 13, "\x1b", 27):
            app.find_buf = ""
            app.mode = "normal"
        elif k in ("\x7f", "\b", curses.KEY_BACKSPACE, 127, 8, 263):
            app.find_buf = app.find_buf[:-1]
            app.find_jump()
        elif isinstance(k, str) and k >= " " and unicodedata.category(k)[0] != "C":
            app.find_buf += k
            app.find_jump()
        return

    if app.mode == "sleep":
        if k in ("\n", "\r", curses.KEY_ENTER, 10, 13):
            app.set_sleep_custom()
        elif k in ("\x1b", 27):
            app.sleep_buf = ""
            app.mode = "normal"
        elif k in ("\x7f", "\b", curses.KEY_BACKSPACE, 127, 8, 263):
            app.sleep_buf = app.sleep_buf[:-1]
        elif isinstance(k, str) and k.isdigit() and len(app.sleep_buf) < 4:
            app.sleep_buf += k
        return

    if app.mode == "name":
        if k in ("\n", "\r", curses.KEY_ENTER, 10, 13):
            if app.rename_index is not None:
                app.rename_playlist(app.rename_index, app.name_buf)
            else:
                app.create_playlist(app.name_buf)
                if app.pick_merge is not None:
                    app.merge_playlist(app.pick_merge,
                                       len(app.store.playlists) - 1)
                    app.pick_merge = None
                elif app.pick_pending:
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

    if app.mode == "theme":
        if k in (curses.KEY_UP, "k"):
            app.theme_move(-1)
        elif k in (curses.KEY_DOWN, "j"):
            app.theme_move(1)
        elif k in ("\n", "\r", curses.KEY_ENTER, 10, 13):
            app.theme_apply()
        elif k in ("\x1b", 27, "q"):
            app.theme_cancel()
        return

    if app.mode == "info":
        if k in ("\x1b", 27, "q", "I", "\n", "\r", curses.KEY_ENTER,
                 10, 13):
            app.mode = "normal"
            app.info_track = None
        elif k == "Y":
            app.copy_link(app.info_track)
        elif k == "O":
            app.open_in_browser(app.info_track)
        return

    if app.mode == "pick":
        view = app.pick_view()
        n = len(view)
        filtering = bool(app.pick_filter)
        if k == curses.KEY_UP or (k == "k" and not filtering):
            app.pick_idx = max(0, app.pick_idx - 1)
        elif k == curses.KEY_DOWN or (k == "j" and not filtering):
            app.pick_idx = min(n - 1, app.pick_idx + 1)
        elif k in ("\n", "\r", curses.KEY_ENTER, 10, 13):
            if not view:
                return
            r = view[app.pick_idx]
            app.mode = "normal"
            if r["new"]:
                app.mode = "name"
                app.name_buf = ""
            elif app.pick_merge is not None:
                app.merge_playlist(app.pick_merge, r["pi"])
                app.pick_merge = None
            else:
                app.add_to_playlist(r.get("pi", app.pick_rows.index(r) - 1),
                                    app.pick_pending)
                app.pick_pending = None
        elif k == "\x1b" or k == 27:
            if filtering:
                app.pick_filter = ""
                app.pick_idx = 0
            else:
                app.mode = "normal"
                app.pick_pending = None
                app.pick_merge = None
        elif k == "q" and not filtering:
            app.mode = "normal"
            app.pick_pending = None
            app.pick_merge = None
        elif k in ("\x7f", "\b", curses.KEY_BACKSPACE, 127, 8, 263):
            app.pick_filter = app.pick_filter[:-1]
            app.pick_idx = 0
        elif (isinstance(k, str) and k >= " "
              and unicodedata.category(k)[0] != "C"):
            app.pick_filter += k
            app.pick_idx = 0
        return

    # normal mode
    if app.show_help:
        if k in ("j", curses.KEY_DOWN, curses.KEY_NPAGE):
            app.help_page = min(app.help_pages - 1, app.help_page + 1)
        elif k in ("k", curses.KEY_UP, curses.KEY_PPAGE):
            app.help_page = max(0, app.help_page - 1)
        elif k == "\x1b" or k == 27 or k == "?" or k == "q":
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
        elif k == "F" and kind in ("liked", "playlist", "history", "queue",
                                   "similar", "artist"):
            app.find_buf = ""
            app.mode = "find"
            app.toast_now("Find: type to jump, Enter to stay")
        elif k == " ":
            app.toggle()
        elif k == ".":
            app.jump_to_current()
        elif k == "g":
            app.sel[vk] = 0
        elif k == "G":
            if kind == "home":
                app.sel[vk] = len(app.store.playlists)   # last tile
            else:
                app.sel[vk] = max(0, len(app.view_tracks()) - 1)
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
            elif kind == "artist" and not app.view_tracks(vk):
                app.mode = "search"
                app.query = arg or ""
                app.do_search(app.query)
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
        elif k == "A":
            app.play_next(app.track_under() or app.current)
        elif k == "C" and kind == "queue":
            app.clear_upcoming()
        elif k == "D" and kind == "queue":
            app.drop_autoplayed()
        elif k == "D" and kind == "history":
            app.toggle_hist_dedupe()
        elif k == "W" and kind == "queue":
            app.save_queue_as_playlist()
        elif k in ("J", "K") and kind == "queue":
            app.move_queue(app.sel_row(), 1 if k == "J" else -1)
        elif k in ("J", "K") and kind == "playlist":
            if app.store.sort_mode != "default":
                app.toast_now("Turn sorting off (m) to reorder songs")
            else:
                app.move_in_playlist(arg, app.sel_row(), 1 if k == "J" else -1)
        elif k == "Y" and kind == "stats":
            app.share_stats()
        elif k == "Y":
            app.copy_link(app.track_under() or app.current)
        elif k == "I":
            app.open_info(app.track_under() or app.current)
        elif k == "O":
            app.open_in_browser(app.track_under() or app.current)
        elif k == "x":
            app.toggle_block(app.track_under() or app.current)
        elif k == "Q" and kind == "search":
            app.queue_all(list(app.results))
        elif k == "a":
            app.add_queue(app.track_under() or app.current)
        elif k == "l":
            app.like(app.track_under() or app.current)
        elif k == "m" and kind in SORTABLE_KINDS:
            app.cycle_sort()
        elif k == "s":
            app.toggle_shuffle()
        elif k == "S":
            app.cycle_shuffle_mode()
        elif k in ("1", "2", "3") and kind == "home":
            app.play_mix(int(k) - 1)
        elif k == "i":
            app.push("stats")
        elif k == "o":
            t = app.track_under() or app.current
            if t and (t.get("artist") or "").strip():
                app.push("artist", t["artist"].strip())
            else:
                app.toast_now("No artist for this song")
        elif k == "z":
            app.toggle_zen()
        elif k == "y":
            app.push("history")
        elif k == "t":
            app.cycle_sleep()
        elif k == "T":
            app.open_theme_picker()
        elif k == "R":
            if kind == "home":
                app.push("similar")
            else:
                app.refresh_similar(force=True)
                app.toast_now("Finding new picks…")
        elif k == "r":
            app.cycle_repeat()
        elif k == "u":
            app.toggle_autoplay()
        elif k == "b":
            app.toggle_private()
        elif k == "U":
            app.undo_delete()
        elif k == "Z":
            app.shuffle_library()
        elif k == "E":
            app.cycle_eq()
        elif k == "f":
            if kind == "playing":
                app.back()
            else:
                app.push("playing")
        elif k == "v":
            app.push("queue")
        elif k == "N" and kind == "playlist":
            app.duplicate_playlist(arg)
        elif k == "B" and kind == "playlist":
            app.open_pick_merge(arg)
        elif k == "w" and kind == "playlist":
            app.toggle_pin(arg)
        elif k == "h" and kind == "playlist":
            app.toggle_enhance(arg)
        elif k == "L" and kind == "playlist":
            app.like_all(arg)
        elif k == "V" and kind == "playlist":
            app.copy_tracklist(arg)
        elif k == "e" and kind == "playlist":
            app.rename_index = arg
            app.name_buf = app.store.playlists[arg]["name"]
            app.mode = "name"
        elif k == "X" and kind == "playlist":
            app.export_playlist(arg)
        elif k == "X" and kind == "history":
            app.mode = "confirm_clearhist"
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
        elif k == "M":
            app.toggle_mute()
        elif k in ("[", "]"):
            app.change_speed(1 if k == "]" else -1)
        elif k == "\x7f" or k == "\b":
            app.back()
        return

    # special keys (int)
    if k == curses.KEY_DOWN:
        app.move_sel(1, len(app.view_tracks()))
    elif k == curses.KEY_UP:
        app.move_sel(-1, len(app.view_tracks()))
    elif k == curses.KEY_RIGHT:
        app.seek(10)
    elif k == curses.KEY_LEFT:
        app.seek(-10)
    elif k in (curses.KEY_ENTER, 10, 13):
        if kind == "home":
            handle_key(app, "\n")
        elif kind == "artist" and not app.view_tracks(vk):
            app.mode = "search"
            app.query = arg or ""
            app.do_search(app.query)
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
    if os.environ.get("SPOTUI_DEBUG"):
        open("/tmp/spotui-debug.log", "a").write(
            f"mouse x={mx} y={my} bstate={bstate:#x}\n")
    modal = app.show_help or app.mode in ("name", "pick", "confirm_delete", "confirm_clearhist")
    if modal:
        app.drag_rect = None
        app.drag_row = None
        if bstate & (curses.BUTTON4_PRESSED | getattr(curses, "BUTTON5_PRESSED", 0)):
            if app.mode == "pick":
                step = -1 if bstate & curses.BUTTON4_PRESSED else 1
                app.pick_idx = max(0, min(len(app.pick_rows) - 1, app.pick_idx + step))
            return
    if app.drag_row is not None and bstate & (curses.REPORT_MOUSE_POSITION | curses.BUTTON1_RELEASED):
        if bstate & curses.REPORT_MOUSE_POSITION:
            vk0 = app.drag_row[0]
            for r in app.rects:
                if r["act"] == "row" and r["arg"][0] == vk0 and \
                        r["x0"] <= mx < r["x1"] and r["y0"] <= my < r["y1"]:
                    target = r["arg"][1]
                    while app.drag_row[1] != target:
                        d = 1 if target > app.drag_row[1] else -1
                        if vk0 == "queue:":
                            ok = app.move_queue(app.drag_row[1], d)
                        else:
                            ok = app.move_in_playlist(
                                int(vk0.split(":", 1)[1]), app.drag_row[1], d)
                        if not ok:
                            break
                        app.drag_row[1] += d
                    break
        if bstate & curses.BUTTON1_RELEASED:
            app.drag_row = None
        return
    if app.drag_rect is not None and bstate & (curses.REPORT_MOUSE_POSITION | curses.BUTTON1_RELEASED):
        r = app.drag_rect
        start, width = r["arg"]
        fraction = min(1.0, max(0.0, (mx - start) / max(1, width - 1)))
        if r["act"] == "vol":
            app.vol(absolute=round(fraction * 100))
        elif app.mpv.state["dur"]:
            app.mpv.seek_abs(fraction * app.mpv.state["dur"])
        if bstate & curses.BUTTON1_RELEASED:
            app.drag_rect = None
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
    blocked = app.show_help or app.mode in ("name", "pick", "confirm_delete", "confirm_clearhist")
    allowed = {"helpclose"} if app.show_help else ({"pickrow"} if app.mode == "pick" else set())
    for r in reversed(app.rects):
        if not (r["x0"] <= mx < r["x1"] and r["y0"] <= my < r["y1"]):
            continue
        act, arg = r["act"], r["arg"]
        if act in ("seek", "vol") and not blocked and bstate & curses.BUTTON1_PRESSED:
            app.drag_rect = r
        if act == "row" and not blocked and bstate & curses.BUTTON1_PRESSED:
            if arg[0] == "queue:" and arg[1] > app.qpos:
                app.drag_row = ["queue:", arg[1]]
            elif arg[0].split(":")[0] == "playlist" \
                    and app.store.sort_mode == "default":
                app.drag_row = [arg[0], arg[1]]
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
        elif act == "artist":
            app.push("artist", arg)
        elif act == "create":
            app.mode = "name"
            app.name_buf = ""
        elif act == "tile":
            app.push(arg[0], arg[1])
        elif act == "tileplay":
            app.play_tile(arg[0], arg[1])
        elif act == "mix":
            app.play_mix(arg)
        elif act == "toggletime":
            app.store.time_left = not app.store.time_left
            app.store.save()
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
                app.play(tracks, 0, source=app._source_for_vk(vk2))
        elif act == "playat":
            vk2, tracks, pos = arg
            if tracks:
                app.play(tracks, pos, source=app._source_for_vk(vk2))
        elif act == "playtrack":
            if isinstance(arg, tuple):
                app.play([arg[0]], 0, source=arg[1])
            else:
                app.play([arg], 0, source="Listening stats")
        elif act == "dropauto":
            app.drop_autoplayed()
        elif act == "delrecent":
            app.remove_recent(arg)
        elif act == "sfilter":
            app.search_filter = arg
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
        elif act == "queueall":
            app.queue_all(list(app.results))
        elif act == "opensrc":
            app.open_source(arg)
        elif act == "playing":
            app.push("playing")
        elif act == "queue":
            app.push("queue")
        elif act == "resume":
            if not blocked:
                app.resume_session_or_play()
        elif act == "qjump":
            # click an UP NEXT row in Now Playing to jump straight to it
            if not blocked and 0 <= arg < len(app.queue) and arg != app.qpos:
                app.qpos = arg
                app._play_current()
        elif act == "sort":
            app.set_sort(arg)
        elif act == "seek":
            bx, bw = arg
            frac = min(1.0, max(0.0, (mx - bx) / max(1, bw - 1)))
            if app.mpv.state["dur"]:
                app.mpv.seek_abs(frac * app.mpv.state["dur"])
        elif act == "vol":
            vx, vw = arg
            frac = min(1.0, max(0.0, (mx - vx) / max(1, vw - 1)))
            app.vol(absolute=round(frac * 100))
        elif act == "mute":
            app.toggle_mute()
        elif act == "chip":
            app.chip_action(arg)
        elif act == "pickrow":
            app.pick_idx = arg
            handle_key(app, "\n")
        return

def mouse_tracking(on):
    """Ask the terminal for button-motion events (1002) in SGR format (1006).

    ncurses on xterm-256color only enables click tracking (1000), so
    seek/volume drags get no motion events at all without this. 1003
    (any-motion) is avoided on purpose: some ncurses builds wedge on
    SGR motion-no-button events.
    """
    try:
        sys.stdout.write("\x1b[?1002h\x1b[?1006h" if on
                         else "\x1b[?1002l\x1b[?1006l")
        sys.stdout.flush()
    except Exception:
        pass


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
            | curses.BUTTON4_PRESSED | getattr(curses, "BUTTON5_PRESSED", 0)
            | curses.REPORT_MOUSE_POSITION)
    except curses.error:
        pass
    mouse_tracking(True)

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
            mouse_tracking(True)
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
    app.pal.apply_theme(app.store.theme)
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
            with app.lock:
                app.tick()
                if app.mpv.on_end.is_set():
                    app.mpv.on_end.clear()
                    app._track_ended()
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
                    with app.lock:
                        handle_mouse(app)
                except Exception:
                    pass
                continue
            try:
                if os.environ.get("SPOTUI_DEBUG"):
                    open("/tmp/spotui-debug.log", "a").write(
                        f"key={k!r} mode={app.mode}\n")
                with app.lock:
                    handle_key(app, k)
            except Exception:
                pass
    finally:
        app.quit = True
        app.load_token += 1
        mouse_tracking(False)
        try:
            app.pal.restore()
        except Exception:
            pass
        app.snapshot_session()
        app.store.save()
        app.mpv.stop()


def import_playlist(path):
    """Import a playlist JSON written by X. Returns (ok, message)."""
    store = Store()
    if store._corrupt:
        return False, store.error
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return False, f"Could not read {path}: {e}"
    if not isinstance(d, dict) or not isinstance(d.get("name"), str):
        return False, "Not a SpotUI playlist file"
    tracks = Store._tracks(d.get("tracks"))
    store.playlists.append({"name": d["name"], "tracks": tracks})
    if not store.save():
        return False, store.error
    return True, f"Imported {d['name']} ({len(tracks)} songs)"


def main():
    locale.setlocale(locale.LC_ALL, "")
    if len(sys.argv) == 3 and sys.argv[1] == "--import":
        ok, msg = import_playlist(sys.argv[2])
        print(msg, file=sys.stdout if ok else sys.stderr)
        sys.exit(0 if ok else 1)
    if not sys.stdout.isatty():
        print("SpotUI needs a terminal.", file=sys.stderr)
        sys.exit(1)
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
