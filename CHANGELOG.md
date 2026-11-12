# Changelog

SpotUI has no versioned releases yet; this log lists notable changes by the
day they landed on `main`.

## 2026-11-12

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
