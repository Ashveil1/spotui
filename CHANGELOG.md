# Changelog

SpotUI has no versioned releases yet; this log lists notable changes by the
day they landed on `main`.

## 2026-11-12

- Right-click a playlist in the sidebar for a menu of everything you can do with it: play, rename, duplicate, pin, like all, copy tracklist, export JSON, delete.
- `V` now works in Liked Songs and Recently Played too, copying the visible list (with the current sort) as numbered shareable text.
- The right-click menu on queue rows offers queue actions: play now, move up next (works on already-played rows too, to hear a song again) and remove from queue.
- Right-click any song row for a context menu: play now, play next, add to queue, like/unlike, song info, copy link, hide from suggestions. `j`/`k` and `Enter` work in it too.
- `m` sort gains a Most played first order, using your local play counts.
- Import a playlist without leaving the app: type the exported `.json` path into the new-playlist box instead of a name. Also fixes a test that flaked when it ran across local midnight.
- `0`-`9` in the Now Playing view seeks to 0-90% of the song, like YouTube's number keys.
- `H` in a playlist removes duplicate songs, keeping the first copy of each; `U` restores them.
- `Z` shuffles your entire library (liked songs, history and every playlist, deduped, skipping hidden songs) into the queue with the current shuffle mode.
- Press `Y` in Stats to copy a shareable summary: plays, unique songs,
  listening time, top artist, top song, streak and this week's plays.
  Without a clipboard the toast previews the headline.

- Press `V` on a playlist to copy its tracklist as numbered text
  ("1. Title - Artist (2:24)") for sharing anywhere. Same clipboard
  chain as `Y` (Termux, Wayland, X11, macOS, OSC 52); without a
  clipboard the toast previews the first songs.

- Press `x` on a song to hide it from every suggestion surface: daily
  mixes, Enhance, Made for you and autoplay all skip it. The row gets a
  small x marker, the info card says "Suggested: no (hidden)", and `x`
  again brings it back. Saved in the library.

- Press `L` on a playlist to like every song in it at once. Songs
  already liked are skipped and the toast says how many were added.

- Press `U` to undo the last destructive delete: a playlist comes back
  at its old spot with every song, a removed song returns to its row.
  One level, like Spotify's undo toast.

- Press `O` to open the selected (or playing) song's link in the system
  browser - uses termux-open-url on Termux, then xdg-open/open/wslview.
  Works from the song info card too, and shows the link when no opener
  exists.

- `T` now opens a theme picker with live preview: j/k repaints the whole
  app in the highlighted theme, Enter keeps it, Esc reverts to the saved
  one (marked "saved" in the list).

- Press `I` on any song for its info card: length, your play count and
  last-played date, liked status, every playlist it sits in, and its
  link (Y copies it straight from the card).

- Press `b` for a private session: plays and history stop being recorded
  until you press `b` again. A "Private session" line sits at the bottom
  of the sidebar while it is on. Session-only, never saved.

- Press `h` on a playlist to Enhance it: suggestions from your library
  (same artists first, ranked by your plays) weave in every 2 songs with
  a ✦ marker. Press `h` again to drop them. Duplicating a playlist keeps
  only your own songs.

- Press `w` on a playlist to pin it: pinned playlists rise to the top of
  the sidebar and the home tiles with a ★, and the pin survives restarts.

- Press `B` on a playlist to merge all its songs into another playlist
  (or a new one) in one step. Songs already in the target are skipped,
  so merging is never destructive and the toast says how many moved.

- The home greeting shows today's listening time next to the streak
  ("Good evening Thu 12 Nov · 5-day streak · 26 min today") (#143)

- The green play glyph on the selected home tile is a real button now:
  it plays Liked Songs or the playlist (clicking the rest of the tile
  still opens it) (#142)

- The sleep timer learned custom minutes: keep pressing t past
  "end of track" and a prompt takes any value from 1 to 1440 (#141)

- Press N in a playlist to duplicate it, tracks included, as
  "<name> (copy)" (numbered when that name is taken) (#140)

- The "From Late Night Drive" line in Now Playing is clickable: it opens
  the playlist, Liked Songs, Recently Played, Made for you, or the
  artist page the song is playing from (#139)

- Press . to jump the selection to the playing song in any list; in the
  queue it lands on the next-up row (#138)

- The Termux section grew into a real guide: OpenSL ES audio flag,
  termux-wake-lock for screen-off playback, termux-api for the copy-link
  key, small-screen tips, and where the data lives (#137)

- Search results can be queued in one go: the "Queue all →" link in the
  All header (or pressing Q) appends every result, skipping songs that
  are already in the queue (#136)

- The queue header shows the wall-clock time the music runs out
  ("12 songs, 35 min left · ends 17:03"), minus what's already played
  of the current song (#135)

- Long song titles in Now Playing now scroll marquee-style (hold, slide,
  hold, restart) instead of being cut off; SPOTUI_REDUCED_MOTION keeps
  the old static cut (#134)

- First run now shows a welcome panel on home with the three steps to a
  full library (search, play/queue/like, shelves fill up) instead of a
  nearly blank screen (#133)

- Press Y to copy the selected (or playing) song's YouTube link - via
  termux-clipboard-set / wl-copy / xclip / xsel / pbcopy when present,
  an OSC 52 escape otherwise, and the toast shows the link as a
  fallback (#132)

- The On repeat shelf on home links to the stats view ("Open Stats →"),
  like Recently played links to its full view (#131)

- The state chips in Now Playing (Playing/Paused, Shuffle, Repeat, speed,
  EQ, Autoplay, Sleep) are clickable: same effect as their keys, and the
  speed chip resets to 1x (#130)

- "Made for you" is now a full view, not just a home shelf: `R` on home
  opens it as a playable list (Enter plays, `a` queues), and `R` inside it
  rolls new picks like before (#129)

- `Tab` in the search bar cycles the All / Songs / Artists filter chips,
  which were mouse-only before (#128)

- `M` mutes and unmutes from the keyboard (the speaker icon was the only
  way before); the level is remembered and restored (#127)

- The stats header remembers your first-ever play and shows it
  ("· since 13 Oct 2026") when it fits (#126)

- Clear your play history: `X` in Recently Played asks for confirmation,
  then resets Recently Played, play counts and stats. Playlists and Liked
  Songs are kept (#125)

- The home greeting shows your listening streak ("· 5-day streak") when
  you have played something on consecutive days (#124)

- Home gains an "On repeat" shelf: cover cards for the songs you played
  most over the last 7 days, each captioned with its weekly play count;
  click a card to play it (#123)

- The sidebar has a Stats entry (with its own icon) under Home and Search,
  so the listening-stats view is discoverable and clickable, not just `i` (#122)

- Search now surfaces your own playlists too: matching playlists appear as
  clickable chips (with song counts) next to the artist chips (#121)

- The add-to-playlist picker (`P`) now filters as you type; Esc clears the
  filter, Enter adds, "+ New playlist" always stays (#120)

- Zen mode: `z` hides the sidebar so the main view takes the full terminal
  width; press `z` again to bring it back. Remembered across restarts (#119)

## 2026-11-11

New views and navigation:
- Recently Played view (`y` or the sidebar), the real play history (#33)
- Artist view (`o` or clicking the artist column): everything by that artist
  in your library, one Enter away from a YouTube search for more (#36)
- `g` / `G` jump to the top / bottom of any list (#50)

Search:
- Live results as you type (short pause, no Enter needed); Enter saves the
  search, Esc closes (#34)
- Matching artists from your library appear as clickable chips above the
  results (#37)

Queues and playlists:
- Queue header shows how much listening time is left (#38)
- Reorder upcoming queue songs with `J`/`K` or by dragging the row (#43)
- Reorder playlist songs with `J`/`K` or by dragging the row (#45, #46)
- Save the queue as a playlist (`W`) and clear upcoming (`C`) were already
  there; they keep working with all of the above

Lists:
- Sort Liked / playlists / Recently Played with `m` (default, title, artist,
  recently added, longest first - saved) or by clicking a column header;
  the active column gets an arrow, click it again to restore (#41)
- Every view shows its own key hints at the bottom (#39)

Playback and mouse:
- Drag the seek bar and volume slider (terminals with SGR mouse support) (#40)
- Click an Up Next row in Now Playing to jump straight to it (#47)
- Sidebar shows song counts next to each library item (#48)

Stats:
- Listening time estimate in the stats view (`i`): plays x known song
  lengths, shown as "about" (#49)

Fixes and hardening:
- Non-finite numbers in a hand-edited library file can no longer crash the
  time/date formatting (#35)
- Test suite: fixed a race that made search tests flaky in CI (#40)

Later the same day:

Playback:
- Autoplay: when the last queued song starts, similar songs are fetched and
  appended so the music keeps going (`u` toggles, on by default) (#54)
- Arrow-key seeks and volume changes show feedback toasts with the landing
  position / new level (#55)
- Click the playerbar time to count down instead of up; remembered across
  restarts (#58)
- Equalizer presets on `E` (off, bass boost, vocal, treble boost) through
  mpv audio filters, with a chip in Now Playing (#59)

Looks:
- Playlist headers show a 2x2 mosaic of the first four covers (#56)
- Now Playing has a clickable heart next to the title, and narrow terminals
  get a "Next: ..." row (#57)
- Resume where you left off: the session saves the playback position and
  Home's Continue listening card resumes the song at that second (#53)
- Narrow-terminal fixes for the playerbar and home shelves (#52)

And later still:

Stats (`i`):
- "N this week" in the header, and a per-day activity chart for the last
  7 days (#62, #63)
- Top artists and songs are clickable: open the artist, play the song (#64)

Autoplay and the queue:
- Songs autoplay added show a ✦ next to their title in the queue and in
  Now Playing's Up Next; an "Autoplay" chip shows in Now Playing while
  it's on (#65)
- `D` in the queue view (or clicking the ✦ legend) drops only the songs
  autoplay added (#67)
- The queue's Now playing row has a progress line; clicking or dragging
  it seeks (#68)

Now Playing:
- "From <playlist / search / artist>" line under the artist; songs
  autoplay picked say "From Autoplay" (#66)

All changes above are covered by the offline test suite
(`python3 -m unittest discover -s tests`), 169 tests at the time of writing.
