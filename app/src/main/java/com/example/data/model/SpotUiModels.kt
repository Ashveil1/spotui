package com.example.data.model

import androidx.compose.ui.graphics.Color

data class Track(
    val id: String,
    val title: String,
    val artist: String,
    val durSec: Int? = null,
    val url: String = "https://www.youtube.com/watch?v=$id",
    val channel: String = "",
    val addedDate: String? = null,
    val playedAtSec: Double? = null,
    val source: String? = null,
    val isAuto: Boolean = false,
    val isEnhanced: Boolean = false
) {
    val thumbnailUrl: String
        get() = "https://i.ytimg.com/vi/$id/mqdefault.jpg"
}

data class Playlist(
    val id: Long = 0,
    val name: String,
    val tracks: List<Track> = emptyList(),
    val pinned: Boolean = false,
    val enhanced: Boolean = false
)

data class SyncedLine(
    val timeSec: Double,
    val text: String
)

data class LyricsData(
    val trackId: String,
    val plainText: String? = null,
    val synced: List<SyncedLine> = emptyList(),
    val fetchedAtEpochSec: Long = 0L
) {
    val hasSynced: Boolean get() = synced.isNotEmpty()
    val hasAny: Boolean get() = !plainText.isNullOrBlank() || synced.isNotEmpty()
}

data class PlayCount(
    val trackId: String,
    val title: String,
    val artist: String,
    val count: Int
)

data class SimilarCache(
    val version: Int = 2,
    val seed: String = "",
    val kind: String = "artist",
    val videoId: String? = null,
    val items: List<Track> = emptyList(),
    val pool: List<Track> = emptyList(),
    val updatedAtSec: Double = 0.0
)

data class DailyMix(
    val index: Int,
    val name: String,
    val artist: String,
    val withArtists: List<String>,
    val tracks: List<Track>
)

data class NoticeItem(
    val message: String,
    val timestampMs: Long
)

data class PlaybackSession(
    val queue: List<Track> = emptyList(),
    val qpos: Int = 0,
    val positionSec: Double = 0.0,
    val playSource: String? = null
)

enum class SpotTheme(
    val displayName: String,
    val accent: Color,
    val background: Color,
    val hover: Color,
    val raised: Color,
    val avatar: Color
) {
    SPOTIFY(
        "Spotify",
        Color(29, 185, 84),
        Color(18, 18, 18),
        Color(31, 31, 31),
        Color(42, 42, 42),
        Color(83, 83, 83)
    ),
    AURORA(
        "Aurora",
        Color(167, 139, 250),
        Color(16, 14, 30),
        Color(30, 26, 52),
        Color(40, 35, 70),
        Color(90, 80, 140)
    ),
    SUNSET(
        "Sunset",
        Color(251, 146, 60),
        Color(24, 16, 14),
        Color(42, 28, 24),
        Color(58, 38, 32),
        Color(120, 80, 60)
    ),
    OCEAN(
        "Ocean",
        Color(56, 189, 248),
        Color(10, 20, 30),
        Color(20, 36, 52),
        Color(28, 50, 72),
        Color(60, 100, 130)
    ),
    ROSE(
        "Rose",
        Color(244, 114, 182),
        Color(26, 14, 22),
        Color(44, 26, 38),
        Color(60, 36, 52),
        Color(130, 70, 105)
    ),
    AMBER(
        "Amber",
        Color(250, 204, 21),
        Color(20, 18, 10),
        Color(38, 34, 18),
        Color(52, 46, 24),
        Color(110, 98, 50)
    );

    companion object {
        fun fromName(name: String?): SpotTheme =
            entries.firstOrNull { it.displayName.equals(name, ignoreCase = true) || it.name == name } ?: SPOTIFY
    }
}

enum class ShuffleMode(val key: String, val label: String, val badge: String) {
    SPREAD("spread", "Artist spread", ""),
    DISCOVERY("discovery", "Discovery (least played first)", "D"),
    MOOD("mood", "Your mood (most played first)", "M");

    companion object {
        fun fromKey(key: String?): ShuffleMode =
            entries.firstOrNull { it.key == key } ?: SPREAD
    }
}

enum class SortMode(val key: String, val label: String) {
    DEFAULT("default", "Default"),
    TITLE("title", "Title A-Z"),
    ARTIST("artist", "Artist A-Z"),
    ADDED("added", "Recently added"),
    DURATION("dur", "Longest first"),
    PLAYS("plays", "Most played first");

    companion object {
        fun fromKey(key: String?): SortMode =
            entries.firstOrNull { it.key == key } ?: DEFAULT
    }
}

enum class EqPreset(val key: String, val label: String) {
    OFF("off", "Off"),
    BASS("bass", "Bass boost"),
    VOCAL("vocal", "Vocal"),
    TREBLE("treble", "Treble boost");

    companion object {
        fun fromKey(key: String?): EqPreset =
            entries.firstOrNull { it.key == key } ?: OFF
    }
}

enum class RepeatMode(val label: String) {
    OFF("Repeat off"),
    ALL("Repeat all"),
    ONE("Repeat one")
}

enum class SearchFilter(val label: String) {
    ALL("All"),
    SONGS("Songs"),
    ARTISTS("Artists")
}

sealed interface NavDest {
    data object Home : NavDest
    data object Search : NavDest
    data object Library : NavDest
    data object Liked : NavDest
    data object History : NavDest
    data class PlaylistDest(val playlistId: Long) : NavDest
    data class Artist(val name: String) : NavDest
    data object Queue : NavDest
    data object NowPlaying : NavDest
    data object Stats : NavDest
    data object Similar : NavDest
    data class Video(val track: Track) : NavDest
}

data class StatsDay(val label: String, val plays: Int, val minutes: Int)
data class HourBucket(val label: String, val count: Int)
data class StatsSummaryData(
    val totalPlays: Int,
    val uniqueSongs: Int,
    val totalMinutesText: String,
    val playsThisWeek: Int,
    val firstPlayEpochSec: Double?,
    val streakDays: Int,
    val todayMinutes: Int,
    val weekDays: List<StatsDay>,
    val hourBuckets: List<HourBucket>,
    val biggestWeekday: Pair<String, Int>?,
    val weekTopArtist: Pair<String, Int>?,
    val onRepeat: List<Pair<Track, Int>>,
    val topArtists: List<Pair<String, Int>>,
    val topSongs: List<TopSongRow>
)

data class TopSongRow(
    val trackId: String,
    val title: String,
    val artist: String,
    val count: Int,
    val lastPlayedSec: Double?
)
