# Changelog

SpotUI has no versioned releases yet; this log lists notable changes by the
day they landed on `main`.

## 2026-11-12

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
