package com.example.data.repository

import com.example.data.local.BlockedTrackEntity
import com.example.data.local.HistoryEntryEntity
import com.example.data.local.LikedTrackEntity
import com.example.data.local.LyricsCacheEntity
import com.example.data.local.PlayCountEntity
import com.example.data.local.PlaylistEntity
import com.example.data.local.PlaylistTrackEntity
import com.example.data.local.PreferencesRepository
import com.example.data.local.RecentSearchEntity
import com.example.data.local.SpotUiDatabase
import com.example.data.local.SpotUiPreferences
import com.example.data.model.EqPreset
import com.example.data.model.LyricsData
import com.example.data.model.PlayCount
import com.example.data.model.PlaybackSession
import com.example.data.model.Playlist
import com.example.data.model.ShuffleMode
import com.example.data.model.SimilarCache
import com.example.data.model.SortMode
import com.example.data.model.SpotTheme
import com.example.data.model.SyncedLine
import com.example.data.model.Track
import com.example.data.remote.YouTubeClient
import com.example.data.util.SpotUiTextUtils
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import org.json.JSONArray
import org.json.JSONObject

data class LibrarySnapshot(
    val liked: List<Track> = emptyList(),
    val playlists: List<Playlist> = emptyList(),
    val history: List<Track> = emptyList(),
    val playCounts: Map<String, PlayCount> = emptyMap(),
    val recentSearches: List<String> = emptyList(),
    val blockedIds: Set<String> = emptySet(),
    val lyricsCache: Map<String, LyricsData> = emptyMap(),
    val prefs: SpotUiPreferences = SpotUiPreferences()
)

class SpotUiRepository(
    private val db: SpotUiDatabase,
    private val prefsRepo: PreferencesRepository,
    private val yt: YouTubeClient
) {
    private val likedDao = db.likedDao()
    private val playlistDao = db.playlistDao()
    private val historyDao = db.historyDao()
    private val playCountDao = db.playCountDao()
    private val recentDao = db.recentSearchDao()
    private val blockedDao = db.blockedDao()
    private val lyricsDao = db.lyricsDao()

    private val playlistsFlow: Flow<List<Playlist>> = combine(
        playlistDao.observePlaylists(),
        playlistDao.observeAllPlaylistTracks()
    ) { pls, tracks ->
        val byPl = tracks.groupBy { it.playlistId }
        pls.map { pe ->
            Playlist(
                id = pe.id,
                name = pe.name,
                pinned = pe.pinned,
                enhanced = pe.enhanced,
                tracks = (byPl[pe.id] ?: emptyList()).map { te ->
                    Track(
                        id = te.trackId,
                        title = te.title,
                        artist = te.artist,
                        durSec = te.durSec,
                        url = te.url,
                        channel = te.channel,
                        addedDate = te.addedDate,
                        isEnhanced = te.isEnhanced
                    )
                }
            )
        }
    }

    val libraryFlow: Flow<LibrarySnapshot> = combine(
        likedDao.observeAll().map { list ->
            list.map {
                Track(
                    id = it.id,
                    title = it.title,
                    artist = it.artist,
                    durSec = it.durSec,
                    url = it.url,
                    channel = it.channel,
                    addedDate = it.addedDate
                )
            }
        },
        playlistsFlow,
        historyDao.observeRecent().map { list ->
            list.map {
                Track(
                    id = it.id,
                    title = it.title,
                    artist = it.artist,
                    durSec = it.durSec,
                    url = it.url,
                    channel = it.channel,
                    playedAtSec = it.playedAtSec
                )
            }
        },
        playCountDao.observeAll().map { list ->
            list.associate { it.trackId to PlayCount(it.trackId, it.title, it.artist, it.count) }
        },
        recentDao.observeAll().map { list -> list.map { it.query } },
        blockedDao.observeAll().map { list -> list.map { it.trackId }.toSet() },
        lyricsDao.observeAll().map { list ->
            list.associate { e ->
                e.trackId to LyricsData(
                    trackId = e.trackId,
                    plainText = e.plainText,
                    synced = decodeSynced(e.syncedJson),
                    fetchedAtEpochSec = e.fetchedAtEpochSec
                )
            }
        },
        prefsRepo.preferences
    ) { arr ->
        @Suppress("UNCHECKED_CAST")
        LibrarySnapshot(
            liked = arr[0] as List<Track>,
            playlists = arr[1] as List<Playlist>,
            history = arr[2] as List<Track>,
            playCounts = arr[3] as Map<String, PlayCount>,
            recentSearches = arr[4] as List<String>,
            blockedIds = arr[5] as Set<String>,
            lyricsCache = arr[6] as Map<String, LyricsData>,
            prefs = arr[7] as SpotUiPreferences
        )
    }

    suspend fun searchYouTube(query: String): Result<List<Track>> = yt.search(query)
    suspend fun fetchRadioMix(videoId: String, limit: Int = 60): Result<List<Track>> = yt.fetchRadioMix(videoId, limit)
    suspend fun fetchYouTubePlaylist(url: String): Result<Pair<String?, List<Track>>> = yt.fetchPlaylist(url)
    suspend fun resolveStreamUrl(videoId: String): Result<String> = yt.resolveAudioStreamUrl(videoId)
    suspend fun resolveVideoStream(videoId: String): Result<YouTubeClient.VideoStream> = yt.resolveVideoStream(videoId)
    suspend fun fetchHomeFeed(): Result<List<Track>> = yt.fetchHomeFeed()
    suspend fun fetchRelated(videoId: String): Result<List<Track>> = yt.fetchRelated(videoId)
    suspend fun fetchComments(videoId: String): Result<List<YouTubeClient.YtComment>> = yt.fetchComments(videoId)

    suspend fun toggleLike(track: Track, currentlyLiked: Boolean) {
        if (currentlyLiked) {
            likedDao.deleteById(track.id)
        } else {
            likedDao.upsert(
                LikedTrackEntity(
                    id = track.id,
                    title = track.title,
                    artist = track.artist,
                    durSec = track.durSec,
                    url = track.url,
                    channel = track.channel,
                    addedDate = SpotUiTextUtils.todayDateStr(),
                    sortOrder = System.currentTimeMillis()
                )
            )
        }
    }

    suspend fun likeAll(tracks: List<Track>, existingLikedIds: Set<String>): Int {
        val fresh = tracks.filter { it.id !in existingLikedIds }
        if (fresh.isEmpty()) return 0
        val today = SpotUiTextUtils.todayDateStr()
        val baseOrder = System.currentTimeMillis()
        likedDao.upsertAll(
            fresh.reversed().mapIndexed { idx, t ->
                LikedTrackEntity(
                    id = t.id,
                    title = t.title,
                    artist = t.artist,
                    durSec = t.durSec,
                    url = t.url,
                    channel = t.channel,
                    addedDate = today,
                    sortOrder = baseOrder + idx
                )
            }
        )
        return fresh.size
    }

    suspend fun recordPlay(track: Track): Pair<Int, Int> {
        val nowSec = System.currentTimeMillis() / 1000.0
        prefsRepo.setFirstPlayIfUnset(nowSec)
        historyDao.upsert(
            HistoryEntryEntity(
                id = track.id,
                title = track.title,
                artist = track.artist,
                durSec = track.durSec,
                url = track.url,
                channel = track.channel,
                playedAtSec = nowSec
            )
        )
        historyDao.trimTo30()
        val prev = playCountDao.getById(track.id)
        val newCount = (prev?.count ?: 0) + 1
        playCountDao.upsert(
            PlayCountEntity(
                trackId = track.id,
                title = track.title,
                artist = track.artist,
                count = newCount
            )
        )
        return newCount to 0
    }

    suspend fun clearHistory() {
        historyDao.clearAll()
        playCountDao.clearAll()
        prefsRepo.clearFirstPlay()
    }

    suspend fun recordRecentSearch(query: String) {
        val q = query.trim()
        if (q.isEmpty()) return
        recentDao.upsert(RecentSearchEntity(q, System.currentTimeMillis()))
        recentDao.trimTo8()
        prefsRepo.setLastSearch(System.currentTimeMillis() / 1000.0)
    }

    suspend fun removeRecentSearch(query: String) = recentDao.delete(query)

    suspend fun toggleBlock(trackId: String, currentlyBlocked: Boolean) {
        if (currentlyBlocked) blockedDao.unblock(trackId)
        else blockedDao.block(BlockedTrackEntity(trackId))
    }

    suspend fun createPlaylist(name: String, tracks: List<Track> = emptyList(), pinned: Boolean = false, enhanced: Boolean = false): Long {
        val cleanName = name.trim().ifEmpty { "New Playlist" }
        val id = playlistDao.insertPlaylist(
            PlaylistEntity(name = cleanName, pinned = pinned, enhanced = enhanced, sortOrder = System.currentTimeMillis())
        )
        if (tracks.isNotEmpty()) {
            replacePlaylistTracks(id, tracks)
        }
        return id
    }

    suspend fun renamePlaylist(playlist: Playlist, newName: String) {
        val clean = newName.trim()
        if (clean.isEmpty()) return
        playlistDao.updatePlaylistName(playlist.id, clean)
    }

    suspend fun setPlaylistPinned(playlist: Playlist, pinned: Boolean) {
        playlistDao.updatePlaylistPinned(playlist.id, pinned)
    }

    suspend fun setPlaylistEnhanced(playlist: Playlist, enhanced: Boolean, tracks: List<Track>) {
        playlistDao.updatePlaylistEnhanced(playlist.id, enhanced)
        replacePlaylistTracks(playlist.id, tracks)
    }

    suspend fun deletePlaylist(playlistId: Long) = playlistDao.deletePlaylist(playlistId)

    suspend fun replacePlaylistTracks(playlistId: Long, tracks: List<Track>) {
        val entities = tracks.mapIndexed { idx, t ->
            PlaylistTrackEntity(
                playlistId = playlistId,
                trackId = t.id,
                title = t.title,
                artist = t.artist,
                durSec = t.durSec,
                url = t.url,
                channel = t.channel,
                addedDate = t.addedDate ?: SpotUiTextUtils.todayDateStr(),
                isEnhanced = t.isEnhanced,
                position = idx
            )
        }
        playlistDao.replacePlaylistTracks(playlistId, entities)
    }

    suspend fun getOrFetchLyrics(track: Track): LyricsData {
        val cached = lyricsDao.get(track.id)
        if (cached != null) {
            return LyricsData(
                trackId = track.id,
                plainText = cached.plainText,
                synced = decodeSynced(cached.syncedJson),
                fetchedAtEpochSec = cached.fetchedAtEpochSec
            )
        }
        val cleanTitle = SpotUiTextUtils.cleanTitle(track.title)
        val artist = track.artist.trim()
        val nowSec = System.currentTimeMillis() / 1000L
        if (cleanTitle == "Unknown title" || artist.isEmpty()) {
            lyricsDao.upsert(LyricsCacheEntity(track.id, null, null, nowSec))
            return LyricsData(trackId = track.id, fetchedAtEpochSec = nowSec)
        }
        val fetched = yt.fetchLyrics(cleanTitle, artist)
        val entity = LyricsCacheEntity(
            trackId = track.id,
            plainText = fetched?.plainText,
            syncedJson = encodeSynced(fetched?.synced ?: emptyList()),
            fetchedAtEpochSec = nowSec
        )
        lyricsDao.upsert(entity)
        lyricsDao.trimTo400()
        return fetched?.copy(trackId = track.id, fetchedAtEpochSec = nowSec)
            ?: LyricsData(trackId = track.id, fetchedAtEpochSec = nowSec)
    }

    fun exportPlaylistJson(playlist: Playlist): String = JSONObject().apply {
        put("name", playlist.name)
        put("tracks", JSONArray().apply {
            playlist.tracks.forEach { put(PreferencesRepository.trackToJson(it)) }
        })
    }.toString(2)

    fun parsePlaylistJson(raw: String): Pair<String, List<Track>>? = runCatching {
        val obj = JSONObject(raw)
        val name = obj.optString("name", "").trim().takeIf { it.isNotEmpty() } ?: return null
        val arr = obj.optJSONArray("tracks") ?: JSONArray()
        val tracks = mutableListOf<Track>()
        for (i in 0 until arr.length()) {
            val item = arr.optJSONObject(i) ?: continue
            PreferencesRepository.trackFromJson(item)?.let(tracks::add)
        }
        name to tracks
    }.getOrNull()

    suspend fun setTheme(theme: SpotTheme) = prefsRepo.setTheme(theme)
    suspend fun setVolume(vol: Int) = prefsRepo.setVolume(vol)
    suspend fun setShuffleMode(mode: ShuffleMode) = prefsRepo.setShuffleMode(mode)
    suspend fun setSortMode(mode: SortMode) = prefsRepo.setSortMode(mode)
    suspend fun setAutoplay(on: Boolean) = prefsRepo.setAutoplay(on)
    suspend fun setTimeLeft(on: Boolean) = prefsRepo.setTimeLeft(on)
    suspend fun setEqPreset(preset: EqPreset) = prefsRepo.setEqPreset(preset)
    suspend fun setVolumeLeveling(on: Boolean) = prefsRepo.setVolumeLeveling(on)
    suspend fun setHistDedupe(on: Boolean) = prefsRepo.setHistDedupe(on)
    suspend fun setZenMode(on: Boolean) = prefsRepo.setZenMode(on)
    suspend fun setReducedMotion(on: Boolean) = prefsRepo.setReducedMotion(on)
    suspend fun setSimilarCache(cache: SimilarCache) = prefsRepo.setSimilarCache(cache)
    suspend fun setSession(session: PlaybackSession) = prefsRepo.setSession(session)

    private fun encodeSynced(lines: List<SyncedLine>): String? {
        if (lines.isEmpty()) return null
        return JSONArray().apply {
            lines.forEach { l ->
                put(JSONArray().put(l.timeSec).put(l.text))
            }
        }.toString()
    }

    private fun decodeSynced(raw: String?): List<SyncedLine> {
        if (raw.isNullOrBlank()) return emptyList()
        return runCatching {
            val arr = JSONArray(raw)
            (0 until arr.length()).mapNotNull { idx ->
                val pair = arr.optJSONArray(idx) ?: return@mapNotNull null
                val t = pair.optDouble(0, Double.NaN)
                val line = pair.optString(1, "")
                if (t.isFinite()) SyncedLine(t, line) else null
            }
        }.getOrDefault(emptyList())
    }
}
