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
