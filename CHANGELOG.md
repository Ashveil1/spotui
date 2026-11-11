# Changelog

SpotUI has no versioned releases yet; this log lists notable changes by the
day they landed on `main`.

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

All changes above are covered by the offline test suite
(`python3 -m unittest discover -s tests`), 126 tests at the time of writing.
