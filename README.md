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

### Arch Linux (works from fish, bash or zsh)

```
sudo pacman -S --needed git python mpv ffmpeg
git clone https://github.com/Ashveil1/spotui ~/spotui
cd ~/spotui
./install.sh
fish_add_path ~/.local/bin     # fish only, if the installer says it is not in PATH
spotui
```

ffmpeg is optional (cover art).

### Termux (Android, untested on a real phone)

```
pkg install python mpv ffmpeg git
git clone https://github.com/Ashveil1/spotui ~/spotui
cd ~/spotui && ./install.sh && ./spotui
```

SpotUI uses Termux's temp folder for mpv's control socket and detects Termux in the installer. I could not test audio on a real Android device.

Tips that make it nicer on a phone:

- **Silent audio?** Pass an output driver: `SPOTUI_MPV_ARGS="--ao=opensles" ./spotui`.
- **Keep playing with the screen off:** run `termux-wake-lock` first (and `termux-wake-unlock` when done), or Android may suspend the session.
- **Copy song links:** `pkg install termux-api` gives you `termux-clipboard-set`, which is the first clipboard tool `Y` tries, so copy-link works like on the desktop.
- **Small screens:** the layout squeezes by itself; `z` hides the sidebar for the full width, and `SPOTUI_REDUCED_MOTION=1 ./spotui` stops the animation if scrolling feels heavy.
- **Themes:** terminal palette themes need terminal support, so `T` may say it is unavailable and the app falls back to 256 colors.
- **Your files:** the library lives in `~/.config/spotui/` and playlist exports land in `~/spotui-exports/` - nothing leaves the phone.

## Keys

| Key | Action | Key | Action |
|---|---|---|---|
| `/` | search | `a` / `A` | add to queue / play next |
| `j/k` ↑/↓ | move | `l` | like / unlike |
| `g` / `G` | top / bottom of a list | | |
| `.` | jump to the playing song | |
| `Enter` | play | `s` | shuffle |
| `Space` | play / pause | `r` | repeat off/all/one |
| `n` / `p` | next / prev | `v` | queue view |
| `←` / `→` | seek ±10s | `P` | add to playlist (the picker filters as you type, shows song counts and a check on playlists that already have it) |
| `+` / `-` | volume | `M` | mute / unmute |
| `[` / `]` | speed down / up | `e` / `D` | rename / delete playlist |
| `F` | find in a list | `d` | delete from list |
| `m` | sort list (title/artist/date/duration) | | |
| `f` | Now Playing | `t` | sleep timer (presets, end of track, custom minutes) |
| `J` / `K` | reorder queue | `W` | save queue as playlist |
| `N` (playlist) | duplicate the playlist, tracks included | |
| `B` (playlist) | merge the playlist into another (skips songs already there) | |
| `w` (playlist) | pin / unpin the playlist to the top of the sidebar and home tiles | |
| `h` (playlist) | Enhance: weave suggested songs (✦) from your library into the playlist; toggle again to remove them | |
| `C` | clear upcoming queue | `X` | export playlist JSON |
| `Y` | copy song link to the clipboard (Termux, Wayland, X11, macOS, or OSC 52; shows the link when none work) | |
| `I` | song info card: plays, last played, liked, playlists it sits in, link | |
| `O` | open the song's link in the browser (termux-open-url / xdg-open / open / wslview) | |
| `Q` (search) | queue all search results (skips songs already queued) | |
| `D` | drop autoplayed songs (queue) / hide repeats (Recently Played) | `X` (Recently Played) | clear play history (asks first; playlists and likes stay) |
| `R` | Made for you (home) / new picks (inside) | `T` | theme picker with live preview |
| `i` or the sidebar | listening stats (plays, minutes, streaks, and how long you have listened) | `S` | shuffle mode |
| `y` | recently played | `1`-`3` | play a daily mix (home) |
| `o` | open artist | `u` | autoplay on/off |
| `b` | private session (plays and history stop counting until toggled off) | |
| `E` | equalizer preset | `z` | hide / show the sidebar (full-width view) |

| `?` | help | | |
| `Backspace` | back | `q` | quit |

Search is live: results appear as you type (after a short pause), and the result list header counts them —
`Enter` keeps them and saves the query to recent searches, `Esc` just
closes the bar. Filter chips under the bar narrow results to songs or
artists (click them, or press `Tab` while typing). Matching artists from your library show as chips above the
results; click one to open its artist page. Playlists whose name
matches show as chips too, with their song counts. Recent searches show when the
bar is empty; click the × on one to remove it, and your six most
recently played songs sit below as a Jump back in list (click to play). When the query is an
artist's name, the top-result card shows the artist (click to open their
page, or use its play button); otherwise it shows the top song. A query
with no results offers your recent searches below the message.

Mouse works too: click anything (rows, tiles, sidebar items, playlists,
playlists rows, controls, toast — everything), drag the progress / volume
bars, click a column header to sort by it (click the active column again to
restore the original order), and the wheel scrolls the list — or the
sidebar when the cursor is over it. `Ctrl+Z` suspends cleanly; the screen
repaints on resume.

## Where is my data?

Liked songs, playlists, recent searches, your play history and the cached
"Made for you" shelf live in `~/.config/spotui/library.json`.

The home greeting shows your listening streak when you have played something on consecutive days.

Home's shortcut tiles name each playlist with its size underneath ("8 songs · 25 min").

The home page shows four shelves: **On repeat** (cover cards for the songs
you played most over the last 7 days, with weekly play counts), **Made for you** (tracks in the same style
as whatever you played or searched last — pulled from YouTube's "Mix" radio,
so it mixes the artist with similar ones; refreshed in the background and
cached, so it opens instantly and works offline), **Recently played** (the
songs you actually played, newest first, with how long ago each one was) and **Songs you like**. Click any
card or row to play it, press `R` to roll new picks.

Play something from a search and SpotUI turns the queue into a **radio**:
same channel and same artist first, then similar artists, shuffled — so
`n` keeps the music going instead of walking down the result list. The
queue view (`v`) shows what is lined up and where the queue started ("From Late Night Drive"), and any song that did not come from the queue's own origin - one you added by hand with `a` / `A`, for example - is tagged with where it came from ("· Added").

## Notes

- RAM footprint (measured): TUI ~14 MiB idle / ~16 MiB while playing; mpv ~55–65 MiB. Searches never load yt-dlp into the app — they run in a short-lived helper process.
- Audio only (no video) — mpv plays the bestaudio stream resolved by yt-dlp. mpv's gapless-audio is on, which removes most of the silence between songs; streams are still opened one by one, so it is not a true crossfade.

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

`t` cycles a session sleep timer: 15 / 30 / 60 / 90 minutes / end of track /
off. Timed countdowns appear at the bottom of the sidebar; end of track lets
the current song finish and then pauses. Over the last 20 seconds the
volume fades toward zero before the pause, and returns to your normal
level afterwards - your stored volume never changes. At expiry SpotUI pauses playback and
cancels a pending track load; it does not close the app or shut down the computer.
The timer is not persisted across restarts. Seek and volume bars support dragging
on terminals that report mouse-motion events, and clicking the speaker glyph mutes
(click again to restore).

`f` opens Now Playing with larger cover art, playback status and the next song.
Click the small cover or title in the player bar to open it too. Its moving bars
are decorative animation, not measured audio levels. Set
`SPOTUI_REDUCED_MOTION=1` to skip the intro and keep visualizers still.

`A` queues the selected song to play next. In the queue view, `J` / `K` move the
selected upcoming song down / up, or drag a row with the mouse - the song
follows the cursor and lands where you drop it; the Now Playing song stays
put. Non-finite numbers in a saved library are ignored.

## Session restore

The queue and position are saved in the library file and restored on the next launch. The Home screen shows a **Continue listening** card with where you stopped ("left off at 1:14") - click it to resume the song at that exact position.

When the last queued song starts, **autoplay** quietly lines up similar songs so the music never just stops (`u` toggles it, on by default). Songs autoplay added are marked with a ✦ in the queue and in Now Playing's Up Next, so you can tell them from your own picks; `D` in the queue view drops just those, and the queue header counts how many upcoming songs came from autoplay and how long they run ("✦ 3 autoplayed (9 min)"). Now Playing also shows where the queue started from ("From Late Night Drive") and how many times you have played the song, the artist name under the title opens the artist page, and an active sleep timer appears as a countdown chip. Those state chips are clickable: same effect as their keys, and the speed chip resets to 1x. On wide terminals its right column ends with a **More from <artist>** list - the artist's other songs in your library, ranked by your plays, one click or Enter away from playing. The queue view has a seekable progress line under the Now playing row. `E` cycles equalizer presets (off, bass boost, vocal, treble boost) through mpv's audio filters. Clicking the elapsed time in the playerbar switches it to a countdown. Playlist headers show a 2x2 mosaic of the first four covers. The Up Next rows show each song's duration, the home hero counts your plays of the song, and the sidebar marks the playlist that's playing with animated bars.

`F` (in Liked, playlists, history, queue) finds and jumps to the first song whose title or artist matches what you type; Enter keeps the selection.

`W` in the queue view saves the queue as a new playlist (duplicates removed).

`[` and `]` change playback speed (0.75x, 1x, 1.25x, 1.5x, 2x). A non-1x speed shows as a badge next to the playerbar time and as a chip in Now Playing. Speed resets to 1x when SpotUI restarts. Now Playing's Up Next rows mark songs you have liked with a heart.

`C` in the queue view clears the upcoming songs and keeps the current song and what already played. The header of the queue view shows how many songs are lined up and about how long is left.

In Recently Played, `D` collapses repeat plays of the same song into its most recent row, which then carries your total play count; the header notes "repeats hidden" and the choice is saved. `m` in Liked Songs, a playlist or Recently Played cycles the sort order: default, title A-Z, artist A-Z, recently added, longest first. The choice is saved and applies to all three views. Sorting only changes how the list is shown - the stored order never changes, and playing, liking or deleting always acts on the row you see. Dates in these lists render relative: Today, Yesterday, the weekday within the last week, then the full date.

`X` in a playlist exports it as JSON to `~/spotui-exports/`. Import one with `python3 spotui.py --import file.json` while SpotUI is closed.

`T` cycles color themes (Spotify, Aurora, Sunset, Ocean, Rose, Amber). Themes redefine terminal palette slots, so they need a terminal that allows it (most do; tmux and `NO_COLOR` do not). The choice is saved.

Play milestones pop a toast: every 25 plays of one song, and every 500 plays overall.

`i` opens listening stats: your most played artists and songs, counted from what you play in SpotUI (stored locally in the library file). The header shows how much you played this week, with a per-day activity chart (plays, with about how many minutes each day ran underneath) and a time-of-day breakdown (morning / afternoon / evening / night) beside it, plus your current listening streak (consecutive days with a play), and, once there's enough history, a caption naming your biggest listening day. Songs you played twice or more this week appear as clickable **On repeat this week** chips under the chart. Click a top artist to open its page, or a top song to play it; top songs also note when you last played them. An artist page's header adds about how long you have listened to them ("~2 hr 4 min listened", from play counts x song lengths, so it is a floor). Artist pages open with a Popular section - that artist's five most-played songs, with animated bars on the one that's playing, one click or Enter away from playing - and link to your other most-played artists. Artist rows in search show their total plays, and song rows show your own play count on the right. The Liked Songs, playlist, and Recently Played headers end with the total play count of their songs, and Liked and playlist headers also count how many songs you added this month ("3 new this month").

`S` cycles shuffle modes and turns shuffle on: **Artist spread** (default), **Discovery** (songs you have played least first) and **Your mood** (your most played songs and artists first). Discovery and mood use the play counts SpotUI keeps locally, so they get better as you listen. All modes keep artists apart when the queue allows it and never add or drop songs. The mode is shown as a D or M next to the shuffle button.

Views reveal top-down when you switch (about half a second). Set `SPOTUI_REDUCED_MOTION=1` to turn this and the other animations off.

**Your mixes** on the home screen are built from songs already in your library (liked, history, playlists, Made for you), grouped around the artists you play most. Press `1`, `2` or `3` on the home screen, or click one, to play it shuffled (the toast names its size). Nothing is fetched for them.
