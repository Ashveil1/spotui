# Graph Report - spotui  (2026-10-19)

## Corpus Check
- Corpus is ~7,639 words - fits in a single context window. You may not need a graph.

## Summary
- 129 nodes · 294 edges · 9 communities (3 shown, 6 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 18 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Stdlib & Terminal APIs
- App State & Actions
- Drawing & Text Metrics
- Docs: Features & Data
- mpv Playback Bridge
- Truecolor Palette
- Init & Library Store
- Installer

## God Nodes (most connected - your core abstractions)
1. `App` - 30 edges
2. `UI` - 21 edges
3. `put()` - 19 edges
4. `fill()` - 15 edges
5. `run()` - 15 edges
6. `wcut()` - 13 edges
7. `Mpv` - 13 edges
8. `draw_art()` - 9 edges
9. `SpotUI` - 9 edges
10. `dlen()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `run()` --calls--> `Pal`  [EXTRACTED]
  spotui.py → spotui.py  _Bridges community 5 → community 0_
- `run()` --calls--> `App`  [EXTRACTED]
  spotui.py → spotui.py  _Bridges community 1 → community 0_
- `run()` --calls--> `UI`  [EXTRACTED]
  spotui.py → spotui.py  _Bridges community 2 → community 0_

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **YouTube Streaming Pipeline (SpotUI -> yt-dlp -> mpv)** — readme_spotui, readme_youtube, readme_yt_dlp, readme_mpv [EXTRACTED 1.00]
- **Persisted User State (library.json stores liked songs, playlists, recent searches)** — readme_spotui, readme_library_json, readme_liked_songs, readme_playlists, readme_recent_searches [EXTRACTED 1.00]
- **Player Control Surface (keys + mouse)** — readme_spotui, readme_keyboard_bindings, readme_mouse_controls [EXTRACTED 1.00]

## Communities (9 total, 6 thin omitted)

### Community 0 - "Stdlib & Terminal APIs"
Cohesion: 0.09
Nodes (11): clean_title(), eq_bars(), fmt_total(), handle_key(), handle_mouse(), main(), resolve_url(), run() (+3 more)

### Community 2 - "Drawing & Text Metrics"
Cohesion: 0.27
Nodes (9): box(), dlen(), draw_art(), dwidth(), fill(), fmt_t(), put(), UI (+1 more)

### Community 3 - "Docs: Features & Data"
Cohesion: 0.18
Nodes (12): Keyboard Bindings (vim-style music keys), library.json (persistent user store at ~/.config/spotui), Liked Songs, Mouse Controls (click rows, drag progress bar, scroll, click player controls), mpv (media player), NO_COLOR=1 Monochrome Mode, Playlists, Recent Searches (+4 more)

## Knowledge Gaps
- **7 isolated node(s):** `TUI Music Player Interface`, `Liked Songs`, `Playlists`, `Recent Searches`, `Keyboard Bindings (vim-style music keys)` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 35 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `App` connect `App State & Actions` to `Stdlib & Terminal APIs`, `Init & Library Store`?**
  _High betweenness centrality (0.266) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `run()` (e.g. with `main()` and `.next()`) actually correct?**
  _`run()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `TUI Music Player Interface`, `Liked Songs`, `Playlists` to the rest of the system?**
  _7 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Stdlib & Terminal APIs` be split into smaller, more focused modules?**
  _Cohesion score 0.0896551724137931 - nodes in this community are weakly interconnected._
- **Why does `Mpv` connect `mpv Playback Bridge` to `Stdlib & Terminal APIs`, `Init & Library Store`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Why does `run()` connect `Stdlib & Terminal APIs` to `App State & Actions`, `Drawing & Text Metrics`, `Truecolor Palette`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._