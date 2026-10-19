# SpotUI 🎵

Spotify-style TUI music player for the terminal — streams from YouTube via mpv.

```
                                ╭──────────────────────────────────────────────────────╮
  ← →                           │ ⌕ What do you want to play?                          │              ?  a
                                ╰──────────────────────────────────────────────────────╯
  ◉ SpotUI
   ⌂  Home                        Good evening
   ⌕  Search                       ♥  Liked Songs      ♫  My Rock Mix
  Your Library             +
   ♥  Liked Songs
────────────────────────────────────────────────────────────────────────────────────────────
  ▚▒▚  Big City Nights    ♥         ⤨  ⏮  ▶  ⏭  ⟳                                   ≣
  ▞▞▞  Scorpions                    2:13 ━━━━━●━━━━━━━━ 4:52                      ◁)) ━●━━ 70
```

## Requirements

- Linux + Python 3.9+
- mpv ([mpv.io](https://mpv.io)) (`sudo pacman -S mpv` / `apt install mpv`)
- Internet access

**ตกแต่ง:** เทอร์มินัลที่รองรับการแก้พาเลต (ส่วนใหญ่ที่รันตรง เช่น kitty, alacritty, gnome-terminal)
จะได้สีเขียว Spotify เป๊ะ (`#1DB954`) และปกเพลย์ลิสต์เป็น gradient สีจริง รวม 16.7 ล้านสี —
ใน tmux และเทอร์มินัลที่ไม่รองรับจะใช้ 256 สี (นับยังดูดี) ·
กำหนด `NO_COLOR=1` เพื่อโหมดขาวดำ ล้วน

## Install

```bash
./install.sh     # creates .venv and installs yt-dlp
spotui           # run — from anywhere (installer links it into ~/.local/bin)
```

หรือรันจากโฟลเดอร์โดยตรงด้วย `./spotui` — launcher resolve ตำแหน่งตัวเองจาก symlink ด้วย

มีอนิเมชั่นเปิดแอป (equalizer + wordmark) — กดปุ่มใดก็ได้เพื่อข้าม; จอแคบจะข้ามให้เอง

## Keys

| Key | Action | Key | Action |
|---|---|---|---|
| `/` | search | `a` | add to queue |
| `j/k` ↑/↓ | move | `l` | like / unlike |
| `Enter` | play | `s` | shuffle |
| `Space` | play / pause | `r` | repeat off/all/one |
| `n` / `p` | next / prev | `v` | queue view |
| `R` | new "Made for you" picks | `P` | add to playlist |
| `←` / `→` | seek ±10s | `c` | create playlist |
| `+` / `-` | volume | `d` | delete from list |
| `Backspace` | back | `?` | help |
| `q` | quit | | |

Mouse works too: click anything (rows, tiles, sidebar items, playlists,
playlists rows, controls, toast — everything), drag the progress / volume
bars, and the wheel scrolls the list — or the sidebar when the cursor is
over it. `Ctrl+Z` suspends cleanly; the screen repaints on resume.

## Where is my data?

Liked songs, playlists, recent searches, your play history and the cached
"Made for you" shelf live in `~/.config/spotui/library.json`.

The home page shows three shelves: **Made for you** (tracks in the same style
as whatever you played or searched last — pulled from YouTube's "Mix" radio,
so it mixes the artist with similar ones; refreshed in the background and
cached, so it opens instantly and works offline), **Recently played** (the
songs you actually played, newest first) and **Songs you like**. Click any
card or row to play it, press `R` to roll new picks.

Play something from a search and SpotUI turns the queue into a **radio**:
same channel and same artist first, then similar artists, shuffled — so
`n` keeps the music going instead of walking down the result list. The
queue view (`v`) shows what is lined up.

## Notes

- RAM footprint (measured): TUI ~14 MiB idle / ~16 MiB while playing; mpv ~55–65 MiB. Searches never load yt-dlp into the app — they run in a short-lived helper process.
- Audio only (no video) — mpv plays the bestaudio stream resolved by yt-dlp.

## Development checks

Run the offline regression tests without mpv, network access or third-party Python packages:

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions runs these tests on Python 3.9, 3.11 and 3.13. The suite covers
mpv's IPC success replies, stale playback requests, queue navigation, playlist
creation, mouse hit boundaries, volume limits and Thai recommendation titles.
Live YouTube access and a working audio device still need a separate smoke test.

Saved libraries that cannot be parsed are left untouched rather than replaced
with an empty library. Back up `~/.config/spotui/library.json` before repairing
such a file. The app reports the read error at startup.

Long queues and the Add to playlist picker scroll to keep the selected row
visible. Track text is clipped by terminal-cell width so wide CJK titles do not
wrap into the next row.

While viewing a playlist, `e` renames it and `D` opens a delete confirmation.
Deletion only happens after `y`; `n` or Esc cancels. Removing a playlist does not
stop the current song or remove songs from Liked Songs.

Shuffle (`s`) preserves the current song and the already-played prefix, spaces
artists apart when the queue has enough variety, and defers recently played
songs within each artist's group. It never inserts or drops queue entries.
Turning shuffle off restores the original order, including queue edits. This is
an artist-spaced shuffle, not a uniformly random permutation; with one dominant
artist some adjacent repeats are unavoidable.

## Scope and service terms

SpotUI is an independent, experimental terminal player by Ash (Ashveil1). It
uses YouTube search and streams resolved by yt-dlp, played through mpv. It is
not affiliated with YouTube, Spotify or Apple and does not include their
subscriptions, licensed catalogs, DRM playback, lossless catalog access,
synchronized lyrics, offline-download rights or other paid-service entitlements.
SpotUI itself contains no advertising. It cannot promise that third-party
content or services will always be ad-free or available.

This project is intended for personal, non-commercial use with content you
have permission to access. That framing does not override platform terms or
copyright. [YouTube's Terms of Service](https://www.youtube.com/static?template=terms)
restrict automated access and use of content outside the ways the service
expressly permits. Using yt-dlp or direct streams can conflict with those terms,
and access can break or be restricted. Users are responsible for checking the
terms and rights that apply to their use. Use official clients when those are
required. This note is not legal advice.

`t` cycles a session sleep timer: 15 / 30 / 60 / 90 minutes / off. The countdown
appears at the bottom of the sidebar. At expiry SpotUI pauses playback and
cancels a pending track load; it does not close the app or shut down the computer.
The timer is not persisted across restarts. Seek and volume bars support dragging
on terminals that report mouse-motion events.

`f` opens Now Playing with larger cover art, playback status and the next song.
Click the small cover or title in the player bar to open it too. Its moving bars
are decorative animation, not measured audio levels. Set
`SPOTUI_REDUCED_MOTION=1` to skip the intro and keep visualizers still.

`A` queues the selected song to play next. In the queue view, `J` / `K` move the
selected upcoming song down / up. Non-finite numbers in a saved library are ignored.

## Session restore

The queue and position are saved in the library file and restored paused on the next launch. Press space to resume.

`F` (in Liked, playlists, history, queue) finds and jumps to the first song whose title or artist matches what you type; Enter keeps the selection.

`W` in the queue view saves the queue as a new playlist (duplicates removed).

`[` and `]` change playback speed (0.75x, 1x, 1.25x, 1.5x, 2x). Speed resets to 1x when SpotUI restarts.

`C` in the queue view clears the upcoming songs and keeps the current song and what already played.
