# SpotUI (Android)

A native **Android (Kotlin + Jetpack Compose + Material 3)** music player rewritten from `Ashveil1/spotui`.

## Features

- **YouTube, ad-free by design**: Browse and watch YouTube without a Google account and without ads - the app simply never requests ad inventory, so there is nothing to skip or block.
- **Watch videos**: Full watch page with quality picker (up to 1080p), view count, upload date, like count, expandable description, comments, Up next with autoplay, and picture-in-picture.
- **Shorts**: Swipeable full-screen Shorts tab with in-feed playback and auto-advance.
- **Home feed**: Trending on YouTube shelf with load-more paging, plus a Following shelf with the latest from your followed channels.
- **Channels**: Tap a channel name to open its page - subscriber count, videos, and playlists (tap to import a playlist). Follow channels device-locally; no account needed.
- **Search**: Live results as you type, YouTube search suggestions, and recent searches.
- **Search & Instant Radio**: Search tracks on YouTube, view top results and matching library artists/playlists, and auto-build queue radio mixes.
- **Audio Playback & Effects**: Background foreground-service playback with `MediaSession` lockscreen/notification controls, playback speed (`0.75x`–`2.0x`), 4-band equalizer presets (`Off`, `Bass boost`, `Vocal`, `Treble boost`), loudness leveling, and sleep timer (presets, end-of-track, or custom minutes with 20s gentle fade-out).
- **Playlists & Library**: Manage `Liked Songs`, `Recently Played` (with repeat hiding and clear history), and custom playlists (pin, rename, duplicate, merge, dedupe, reorder, enhance with suggestions, Undo delete, and YouTube URL or JSON import/export via Android SAF).
- **Synced & Plain Lyrics**: Automatic LRCLIB synced `.lrc` and plain lyrics with auto-follow highlighting and tap-to-seek.
- **Listening Stats & Smart Shuffle**: Listening streak, 7-day bar chart, time-of-day breakdown, top artists/songs, `Artist spread` / `Discovery` / `Mood` shuffle modes, and `Private session`.
- **Themes & Adaptive UI**: Six selectable dark themes (`Spotify`, `Aurora`, `Sunset`, `Ocean`, `Rose`, `Amber`), `Reduced motion`, compact phone navigation bar + mini player, and wide tablet sidebar + desktop-style player bar.

## Honest notes

- **No account features**: Liking videos, posting comments, YouTube subscriptions, and YouTube history require a Google account and are not included. SpotUI's follows, likes, playlists and history are stored only on your device.
- **No offline mode**: Videos and audio stream on demand; nothing is downloaded for offline use.
- **Ad-free means what it says**: No ads are requested or shown. This is structural, not an ad blocker, and not a promise about any paid tier.
