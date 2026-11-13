package com.example.ui.viewmodel

import android.app.Application
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.SpotUiApplication
import com.example.data.local.SpotUiPreferences
import com.example.data.model.DailyMix
import com.example.data.model.EqPreset
import com.example.data.model.LyricsData
import com.example.data.model.NavDest
import com.example.data.remote.YouTubeClient
import com.example.data.model.NoticeItem
import com.example.data.model.PlayCount
import com.example.data.model.PlaybackSession
import com.example.data.model.Playlist
import com.example.data.model.RepeatMode
import com.example.data.model.SearchFilter
import com.example.data.model.ShuffleMode
import com.example.data.model.SimilarCache
import com.example.data.model.SortMode
import com.example.data.model.SpotTheme
import com.example.data.model.StatsSummaryData
import com.example.data.model.Track
import com.example.data.repository.LibrarySnapshot
import com.example.data.repository.SpotUiRepository
import com.example.data.util.SpotUiTextUtils
import com.example.player.AudioPlayerState
import com.example.player.PlaybackService
import com.example.player.SpotUiAudioPlayer
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

sealed interface TrashItem {
    data class DeletedPlaylist(val playlist: Playlist) : TrashItem
    data class DeletedTrack(val playlistId: Long, val index: Int, val track: Track) : TrashItem
    data class DedupedTracks(val playlistId: Long, val dropped: List<Pair<Int, Track>>) : TrashItem
}

sealed interface ActiveModal {
    data class SongMenu(val track: Track, val sourceLabel: String? = null, val queueIndex: Int? = null, val playlistContext: Pair<Playlist, Int>? = null) : ActiveModal
    data class CollectionMenu(val kind: String, val playlist: Playlist? = null) : ActiveModal
    data object PlaybackMenu : ActiveModal
    data class AddToPlaylistPicker(val track: Track) : ActiveModal
    data class MergePlaylistPicker(val sourcePlaylist: Playlist) : ActiveModal
    data class CreateOrImportPlaylist(val pendingTrack: Track? = null, val mergeFrom: Playlist? = null) : ActiveModal
    data class RenamePlaylist(val playlist: Playlist) : ActiveModal
    data class ConfirmDeletePlaylist(val playlist: Playlist) : ActiveModal
    data object ConfirmClearHistory : ActiveModal
    data class SongInfo(val track: Track) : ActiveModal
    data class LyricsSheet(val track: Track) : ActiveModal
    data object ThemePicker : ActiveModal
    data object SleepTimerSheet : ActiveModal
    data object RecentNotices : ActiveModal
    data object HelpDialog : ActiveModal
}

data class SpotUiState(
    val library: LibrarySnapshot = LibrarySnapshot(),
    val backStack: List<NavDest> = listOf(NavDest.Home),
    val searchQuery: String = "",
    val searchFilter: SearchFilter = SearchFilter.ALL,
    val searchResults: List<Track> = emptyList(),
    val isSearching: Boolean = false,
    val artistRemoteTracks: Map<String, List<Track>> = emptyMap(),
    val artistBusy: Set<String> = emptySet(),
    val queue: List<Track> = emptyList(),
    val qpos: Int = -1,
    val currentTrack: Track? = null,
    val playSource: String? = null,
    val shuffle: Boolean = false,
    val repeat: RepeatMode = RepeatMode.OFF,
    val privateSession: Boolean = false,
    val playerState: AudioPlayerState = AudioPlayerState(),
    val sleepMinutes: Int = 0,
    val sleepEot: Boolean = false,
    val sleepRemainingSec: Int? = null,
    val toastMessage: String? = null,
    val notices: List<NoticeItem> = emptyList(),
    val findQuery: String = "",
    val findActive: Boolean = false,
    val activeModal: ActiveModal? = null,
    val previewTheme: SpotTheme? = null,
    val showSplash: Boolean = true,
    val isMuted: Boolean = false,
    val hasUndo: Boolean = false,
    val activeLyricsLoading: Boolean = false,
    val homeFeed: List<Track> = emptyList(),
    val homeFeedLoading: Boolean = false,
    val homeFeedError: String? = null,
    val homeFeedContinuation: String? = null,
    val homeFeedMoreLoading: Boolean = false
) {
    val currentDest: NavDest get() = backStack.lastOrNull() ?: NavDest.Home
    val effectiveTheme: SpotTheme get() = previewTheme ?: library.prefs.theme
    val likedIds: Set<String> get() = library.liked.map { it.id }.toSet()
    val blockedIds: Set<String> get() = library.blockedIds
    val prefs: SpotUiPreferences get() = library.prefs
    val isLibFresh: Boolean
        get() = library.liked.isEmpty() && library.history.isEmpty() &&
            library.playCounts.isEmpty() && library.playlists.all { it.tracks.isEmpty() }

    val dailyMixes: List<DailyMix>
        get() = SpotUiTextUtils.dailyMixes(
            liked = library.liked,
            history = library.history,
            similarItems = library.prefs.similarCache.items,
            playlists = library.playlists,
            plays = library.playCounts,
            blockedIds = blockedIds
        )

    val stats: StatsSummaryData
        get() = SpotUiTextUtils.computeStats(
            liked = library.liked,
            history = library.history,
            playlists = library.playlists,
            plays = library.playCounts,
            firstPlayEpochSec = prefs.firstPlayEpochSec
        )
}

class SpotUiViewModel(application: Application) : AndroidViewModel(application) {

    private val repo: SpotUiRepository = (application as SpotUiApplication).repository
    private val _uiState = MutableStateFlow(SpotUiState())
    val uiState: StateFlow<SpotUiState> = _uiState.asStateFlow()

    val audioPlayer = SpotUiAudioPlayer(
        context = application,
        onTrackCompleted = { handleTrackEnded() },
        onPlaybackError = { err ->
            loadToken++
            audioPlayerStateSync()
            toastNow("Couldn't play \u2014 $err")
        }
    )

    private var playbackService: PlaybackService? = null
    private var origQueue: List<Track>? = null
    private var loadToken: Long = 0L
    private var searchJob: Job? = null
    private var liveSearchJob: Job? = null
    private var toastJob: Job? = null
    private var sleepJob: Job? = null
    private var sleepDeadlineMs: Long? = null
    private var mutedFromVol: Int? = null
    private var trash: TrashItem? = null
    private var radioBusy = false
    private var autoBusy = false
    private var simBusy = false
    private var lastSimAtSec = 0.0
    private var sessionRestored = false
    private var pendingSeekAfterLoad: Pair<Long, Double>? = null
    private val lyricsInFlight = mutableSetOf<String>()

    init {
        viewModelScope.launch {
            repo.libraryFlow.collect { snapshot ->
                _uiState.update { state ->
                    state.copy(library = snapshot)
                }
                audioPlayer.setVolume(snapshot.prefs.volume)
                audioPlayer.setEqPreset(snapshot.prefs.eqPreset)
                audioPlayer.setVolumeLeveling(snapshot.prefs.volumeLeveling)

                if (!sessionRestored) {
                    sessionRestored = true
                    val sess = snapshot.prefs.session
                    if (sess.queue.isNotEmpty() && sess.qpos in sess.queue.indices) {
                        _uiState.update {
                            it.copy(
                                queue = sess.queue,
                                qpos = sess.qpos,
                                playSource = sess.playSource
                            )
                        }
                    }
                    refreshSimilar(force = false)
                    maybeLoadHomeFeed()
                }
            }
        }

        viewModelScope.launch {
            audioPlayer.state.collect { pState ->
                _uiState.update { it.copy(playerState = pState) }
                val cur = _uiState.value.currentTrack
                if (cur != null) {
                    playbackService?.updatePlaybackNotification(
                        track = cur,
                        playing = !pState.isPaused && !pState.isIdle && !pState.isLoading,
                        posSec = pState.positionSec,
                        durSec = pState.durationSec
                    )
                }
            }
        }

        startSleepMonitor()
    }

    fun attachPlaybackService(service: PlaybackService?) {
        playbackService = service
        service?.onActionToggle = { togglePlayPause() }
        service?.onActionNext = { next() }
        service?.onActionPrev = { prev() }
        service?.onActionSeek = { sec -> seekTo(sec) }
    }

    fun dismissSplash() {
        _uiState.update { it.copy(showSplash = false) }
    }

    // --- Navigation ---
    fun navigateTo(dest: NavDest) {
        _uiState.update { s ->
            if (s.currentDest == dest) s
            else s.copy(backStack = s.backStack + dest, findActive = false, findQuery = "")
        }
        if (dest is NavDest.Artist) {
            maybeFetchArtistRemote(dest.name)
        }
    }

    fun maybeLoadHomeFeed(force: Boolean = false) {
        val s = _uiState.value
        if (s.homeFeedLoading) return
        if (!force && (s.homeFeed.isNotEmpty() || s.homeFeedError != null)) return
        _uiState.update { it.copy(homeFeedLoading = true, homeFeedError = null) }
        viewModelScope.launch {
            repo.fetchHomeFeed()
                .onSuccess { page ->
                    _uiState.update {
                        it.copy(
                            homeFeed = page.tracks,
                            homeFeedLoading = false,
                            homeFeedContinuation = page.continuation
                        )
                    }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(homeFeedLoading = false, homeFeedError = e.message ?: "feed failed")
                    }
                }
        }
    }

    fun loadMoreHomeFeed() {
        val s = _uiState.value
        val cont = s.homeFeedContinuation ?: return
        if (s.homeFeedLoading || s.homeFeedMoreLoading) return
        _uiState.update { it.copy(homeFeedMoreLoading = true) }
        viewModelScope.launch {
            repo.fetchHomeFeedPage(cont)
                .onSuccess { page ->
                    _uiState.update { cur ->
                        val seen = cur.homeFeed.map { it.id }.toMutableSet()
                        val fresh = page.tracks.filter { seen.add(it.id) }
                        cur.copy(
                            homeFeed = cur.homeFeed + fresh,
                            homeFeedMoreLoading = false,
                            homeFeedContinuation = page.continuation
                        )
                    }
                }
                .onFailure {
                    _uiState.update { it.copy(homeFeedMoreLoading = false) }
                }
        }
    }

    fun watchVideo(track: Track) {
        if (_uiState.value.currentTrack != null) {
            audioPlayer.pause()
            snapshotSession()
        }
        navigateTo(NavDest.Video(track))
    }

    suspend fun resolveVideoStream(videoId: String, maxHeight: Int = 1080): Result<YouTubeClient.VideoStream> =
        repo.resolveVideoStream(videoId, maxHeight)

    suspend fun fetchRelated(videoId: String): Result<List<Track>> =
        repo.fetchRelated(videoId)

    suspend fun fetchComments(videoId: String): Result<List<YouTubeClient.YtComment>> =
        repo.fetchComments(videoId)

    suspend fun fetchChannel(channelId: String): Result<YouTubeClient.YtChannelInfo> =
        repo.fetchChannel(channelId)

    suspend fun resolveChannelId(channelName: String): String? =
        repo.resolveChannelId(channelName)

    suspend fun fetchShorts(): Result<List<Track>> =
        repo.fetchShorts()

    fun switchTab(dest: NavDest) {
        _uiState.update { s ->
            s.copy(backStack = listOf(dest), findActive = false, findQuery = "")
        }
    }

    fun goBack(): Boolean {
        val s = _uiState.value
        if (s.activeModal != null) {
            closeModal()
            return true
        }
        if (s.findActive) {
            _uiState.update { it.copy(findActive = false, findQuery = "") }
            return true
        }
        if (s.backStack.size > 1) {
            _uiState.update { it.copy(backStack = it.backStack.dropLast(1)) }
            return true
        }
        return false
    }

    // --- Modals & Toasts ---
    fun openModal(modal: ActiveModal) {
        _uiState.update { it.copy(activeModal = modal) }
        if (modal is ActiveModal.LyricsSheet) {
            ensureLyrics(modal.track, forceShowLoading = true)
        }
    }

    fun closeModal() {
        val cur = _uiState.value.activeModal
        if (cur is ActiveModal.ThemePicker) {
            _uiState.update { it.copy(activeModal = null, previewTheme = null) }
        } else {
            _uiState.update { it.copy(activeModal = null) }
        }
    }

    fun toastNow(message: String) {
        val now = System.currentTimeMillis()
        _uiState.update { s ->
            val updatedNotices = (s.notices + NoticeItem(message, now)).takeLast(30)
            s.copy(toastMessage = message, notices = updatedNotices)
        }
        toastJob?.cancel()
        toastJob = viewModelScope.launch {
            delay(2800L)
            _uiState.update { it.copy(toastMessage = null) }
        }
    }

    // --- Search ---
    fun onSearchQueryChanged(q: String) {
        _uiState.update { it.copy(searchQuery = q) }
        liveSearchJob?.cancel()
        val trimmed = q.trim()
        if (trimmed.isEmpty()) {
            _uiState.update { it.copy(searchResults = emptyList(), isSearching = false) }
            return
        }
        liveSearchJob = viewModelScope.launch {
            delay(600L)
            performSearch(trimmed, record = false)
        }
    }

    fun submitSearch() {
        liveSearchJob?.cancel()
        val q = _uiState.value.searchQuery.trim()
        if (q.isEmpty()) return
        performSearch(q, record = true)
    }

    fun rerunSearch(q: String) {
        _uiState.update { it.copy(searchQuery = q) }
        if (_uiState.value.currentDest !is NavDest.Search) {
            navigateTo(NavDest.Search)
        }
        performSearch(q, record = true)
    }

    fun setSearchFilter(filter: SearchFilter) {
        _uiState.update { it.copy(searchFilter = filter) }
    }

    fun removeRecentSearch(q: String) {
        viewModelScope.launch {
            repo.removeRecentSearch(q)
            toastNow("Removed search: $q")
        }
    }

    private fun performSearch(query: String, record: Boolean) {
        searchJob?.cancel()
        _uiState.update { it.copy(isSearching = true) }
        searchJob = viewModelScope.launch {
            val result = repo.searchYouTube(query)
            result.onSuccess { tracks ->
                _uiState.update { it.copy(searchResults = tracks, isSearching = false) }
            }.onFailure { err ->
                _uiState.update { it.copy(searchResults = emptyList(), isSearching = false) }
                toastNow("Search failed \u2014 ${err.message ?: "check connection"}")
            }
            if (record) {
                repo.recordRecentSearch(query)
                refreshSimilar(force = false)
            }
        }
    }

    // --- Artist & Views ---
    fun artistLibraryTracks(name: String): List<Track> {
        val norm = SpotUiTextUtils.normArtist(name)
        val seen = mutableSetOf<String>()
        val out = mutableListOf<Track>()
        val s = _uiState.value
        val pools = listOf(s.library.liked, s.library.history, s.queue) + s.library.playlists.map { it.tracks }
        for (src in pools) {
            for (t in src) {
                if (SpotUiTextUtils.normArtist(t.artist) == norm && seen.add(t.id)) {
                    out.add(t)
                }
            }
        }
        return out
    }

    fun artistPlays(name: String): Int {
        val norm = SpotUiTextUtils.normArtist(name)
        return _uiState.value.library.playCounts.values
            .filter { SpotUiTextUtils.normArtist(it.artist) == norm }
            .sumOf { it.count }
    }

    fun artistMinutesText(name: String): String {
        val s = _uiState.value
        val dur = mutableMapOf<String, Int>()
        for (pool in listOf(s.library.liked, s.library.history) + s.library.playlists.map { it.tracks }) {
            for (t in pool) {
                val d = t.durSec
                if (d != null && d > 0) dur.putIfAbsent(t.id, d)
            }
        }
        val norm = SpotUiTextUtils.normArtist(name)
        val sec = s.library.playCounts.entries
            .filter { SpotUiTextUtils.normArtist(it.value.artist) == norm }
            .sumOf { it.value.count.toLong() * (dur[it.key] ?: 0) }
        if (sec < 60) return ""
        return SpotUiTextUtils.fmtListen((sec / 60).toInt())
    }

    private fun maybeFetchArtistRemote(name: String) {
        if (name.isBlank() || artistLibraryTracks(name).isNotEmpty()) return
        val s = _uiState.value
        if (name in s.artistRemoteTracks || name in s.artistBusy) return
        _uiState.update { it.copy(artistBusy = it.artistBusy + name) }
        viewModelScope.launch {
            val res = repo.searchYouTube(name).getOrDefault(emptyList())
                .filter { SpotUiTextUtils.isRealSong(it) }
            val norm = SpotUiTextUtils.normArtist(name)
            val mine = res.filter { SpotUiTextUtils.normArtist(it.artist) == norm }.ifEmpty { res }.take(25)
            _uiState.update {
                it.copy(
                    artistRemoteTracks = it.artistRemoteTracks + (name to mine),
                    artistBusy = it.artistBusy - name
                )
            }
        }
    }

    fun searchMatchingArtists(query: String, limit: Int = 5): List<String> {
        val normQ = SpotUiTextUtils.normArtist(query)
        if (normQ.isEmpty()) return emptyList()
        val seen = mutableSetOf<String>()
        val out = mutableListOf<String>()
        val s = _uiState.value
        fun scan(tracks: List<Track>) {
            for (t in tracks) {
                val a = t.artist.trim()
                val na = SpotUiTextUtils.normArtist(a)
                if (a.isNotEmpty() && na !in seen && normQ in na) {
                    seen.add(na)
                    out.add(a)
                }
            }
        }
        scan(s.library.liked)
        scan(s.library.history)
        s.library.playlists.forEach { scan(it.tracks) }
        scan(s.searchResults)
        return out.take(limit)
    }

    fun searchMatchingPlaylists(query: String, limit: Int = 4): List<Playlist> {
        val nq = query.trim().lowercase()
        if (nq.isEmpty()) return emptyList()
        return _uiState.value.library.playlists.filter { nq in it.name.lowercase() }.take(limit)
    }

    // --- Playback ---
    fun play(tracks: List<Track>, pos: Int, source: String? = null, startRadioAfter: Boolean = false) {
        if (tracks.isEmpty() || pos !in tracks.indices) return
        origQueue = null
        val tagged = tracks.map { t -> if (source != null) t.copy(source = source) else t }
        _uiState.update {
            it.copy(
                queue = tagged,
                qpos = pos,
                playSource = source
            )
        }
        if (_uiState.value.shuffle) {
            applyShuffle(true)
        }
        playCurrent()
        if (startRadioAfter) {
            startRadioBackground(_uiState.value.currentTrack ?: tagged[pos])
        }
    }

    fun resumeSessionOrPlay() {
        val s = _uiState.value
        val hist = s.library.history
        if (s.currentTrack != null || hist.isEmpty()) {
            if (hist.isNotEmpty()) play(hist, 0, "Recently Played", startRadioAfter = true)
            return
        }
        val q = s.queue
        val sess = s.prefs.session
        if (q.isNotEmpty() && s.qpos in q.indices && q[s.qpos].id == hist.first().id) {
            val token = loadToken + 1
            if (sess.positionSec > 5.0) {
                pendingSeekAfterLoad = token to sess.positionSec
            }
            playCurrent()
            return
        }
        play(hist, 0, "Recently Played", startRadioAfter = true)
    }

    fun jumpToQueueIndex(idx: Int) {
        val q = _uiState.value.queue
        if (idx !in q.indices) return
        _uiState.update { it.copy(qpos = idx) }
        playCurrent()
    }

    private fun playCurrent() {
        val s = _uiState.value
        if (s.qpos !in s.queue.indices) return
        val track = s.queue[s.qpos]
        loadToken++
        val token = loadToken
        _uiState.update { it.copy(currentTrack = track) }
        audioPlayer.setLoading(true)
        ensureLyrics(track, forceShowLoading = false)
        maybeAutoplay()

        viewModelScope.launch {
            val streamResult = repo.resolveStreamUrl(track.id)
            if (token != loadToken) return@launch
            streamResult.onSuccess { streamUrl ->
                val seekSec = pendingSeekAfterLoad?.takeIf { it.first == token }?.second ?: 0.0
                if (pendingSeekAfterLoad?.first == token) pendingSeekAfterLoad = null
                audioPlayer.loadStream(streamUrl, track, token, seekSec)
                notePlayHistory(track)
            }.onFailure { err ->
                audioPlayer.setLoading(false)
                toastNow("Couldn't play \u2014 ${err.message ?: "stream unavailable"}")
            }
        }
    }

    private fun notePlayHistory(track: Track) {
        if (_uiState.value.privateSession) return
        viewModelScope.launch {
            val (songCount, _) = repo.recordPlay(track)
            val totalPlays = _uiState.value.library.playCounts.values.sumOf { it.count } + 1
            if (songCount % 25 == 0) {
                toastNow("${track.title} - $songCount plays!")
            } else if (totalPlays % 500 == 0) {
                toastNow("$totalPlays plays on SpotUI!")
            }
            snapshotSession()
            refreshSimilar(force = false)
        }
    }

    private fun snapshotSession() {
        val s = _uiState.value
        val posSec = if (s.currentTrack != null && !s.playerState.isIdle) {
            s.playerState.positionSec
        } else {
            s.prefs.session.positionSec
        }
        viewModelScope.launch {
            repo.setSession(
                PlaybackSession(
                    queue = s.queue.take(500),
                    qpos = s.qpos.coerceAtLeast(0),
                    positionSec = posSec,
                    playSource = s.playSource
                )
            )
        }
    }

    fun togglePlayPause() {
        val s = _uiState.value
        if (s.currentTrack != null) {
            audioPlayer.togglePlayPause()
            snapshotSession()
        } else if (s.queue.isNotEmpty()) {
            if (s.qpos !in s.queue.indices) {
                _uiState.update { it.copy(qpos = 0) }
            }
            playCurrent()
        }
    }

    fun next(auto: Boolean = false) {
        val s = _uiState.value
        if (auto && s.repeat == RepeatMode.ONE && s.currentTrack != null) {
            playCurrent()
            return
        }
        if (s.qpos + 1 < s.queue.size) {
            _uiState.update { it.copy(qpos = it.qpos + 1) }
            playCurrent()
        } else if (auto && s.repeat == RepeatMode.ALL && s.queue.isNotEmpty()) {
            _uiState.update { it.copy(qpos = 0) }
            playCurrent()
        }
    }

    fun prev() {
        val s = _uiState.value
        if (s.playerState.positionSec > 2.5) {
            audioPlayer.seekTo(0.0)
        } else if (s.qpos > 0) {
            _uiState.update { it.copy(qpos = it.qpos - 1) }
            playCurrent()
        }
    }

    fun seekTo(sec: Double) {
        audioPlayer.seekTo(sec)
        snapshotSession()
    }

    fun seekRelative(deltaSec: Double) {
        audioPlayer.seekRelative(deltaSec)
        val dur = _uiState.value.playerState.durationSec
        val target = (_uiState.value.playerState.positionSec + deltaSec).let {
            if (dur > 0) it.coerceIn(0.0, dur) else it.coerceAtLeast(0.0)
        }
        val sign = if (deltaSec >= 0) "+" else "-"
        toastNow("$sign${kotlin.math.abs(deltaSec.toInt())}s - ${SpotUiTextUtils.fmtTimeDouble(target)}")
    }

    fun seekPercent(pct: Int) {
        val dur = _uiState.value.playerState.durationSec
        if (_uiState.value.currentTrack == null || dur <= 0) {
            toastNow("Nothing to seek in")
            return
        }
        audioPlayer.seekTo(dur * pct / 100.0)
        toastNow("Jumped to $pct%")
    }

    // --- Shuffle / Repeat / Radio / Autoplay ---
    fun toggleShuffle() {
        val newVal = !_uiState.value.shuffle
        _uiState.update { it.copy(shuffle = newVal) }
        applyShuffle(newVal)
        toastNow("Shuffle ${if (newVal) "on" else "off"}")
    }

    fun cycleShuffleMode() {
        val modes = ShuffleMode.entries
        val cur = _uiState.value.prefs.shuffleMode
        val next = modes[(modes.indexOf(cur) + 1) % modes.size]
        viewModelScope.launch { repo.setShuffleMode(next) }
        _uiState.update { it.copy(shuffle = true) }
        applyShuffle(false)
        applyShuffle(true, overrideMode = next)
        toastNow("Shuffle: ${next.label}")
    }

    private fun applyShuffle(on: Boolean, overrideMode: ShuffleMode? = null) {
        val s = _uiState.value
        if (s.queue.isEmpty()) return
        if (on) {
            origQueue = s.queue.toList()
            val pos = s.qpos.coerceAtLeast(0)
            val head = s.queue.take(pos + 1)
            val tail = s.queue.drop(pos + 1)
            val prevArtist = head.lastOrNull()?.artist ?: ""
            val recentIds = s.library.history.take(10).map { it.id }.toSet()
            val mode = overrideMode ?: s.prefs.shuffleMode
            val shuffledTail = SpotUiTextUtils.smartShuffle(
                tracks = tail,
                previousArtist = prevArtist,
                recentIds = recentIds,
                mode = mode,
                plays = s.library.playCounts
            )
            _uiState.update { it.copy(queue = head + shuffledTail) }
        } else {
            val orig = origQueue ?: return
            val cur = s.currentTrack
            val newPos = if (cur != null) orig.indexOfFirst { it.id == cur.id }.takeIf { it >= 0 } ?: 0 else s.qpos
            _uiState.update { it.copy(queue = orig, qpos = newPos) }
            origQueue = null
        }
    }

    fun cycleRepeat() {
        val modes = RepeatMode.entries
        val next = modes[(modes.indexOf(_uiState.value.repeat) + 1) % modes.size]
        _uiState.update { it.copy(repeat = next) }
        audioPlayer.setRepeatOne(next == RepeatMode.ONE)
        toastNow(next.label)
    }

    fun startRadio(track: Track) {
        if (_uiState.value.currentTrack?.id != track.id) {
            radioBusy = true
            try {
                play(listOf(track), 0, source = "Radio", startRadioAfter = false)
            } finally {
                radioBusy = false
            }
        }
        toastNow("Starting radio from ${track.title.take(30)}\u2026")
        startRadioBackground(track)
    }

    private fun startRadioBackground(track: Track) {
        if (radioBusy) return
        radioBusy = true
        val startToken = loadToken
        viewModelScope.launch {
            try {
                val items = repo.fetchRadioMix(track.id, limit = 60).getOrDefault(emptyList())
                    .filter { it.id != track.id && SpotUiTextUtils.isRealSong(it) && it.id !in _uiState.value.blockedIds }
                    .shuffled()
                val picks = mutableListOf<Track>()
                val perArtist = mutableMapOf<String, Int>()
                for (t in items) {
                    val a = t.artist.lowercase()
                    val count = perArtist[a] ?: 0
                    if (count >= 2) continue
                    perArtist[a] = count + 1
                    picks.add(t)
                    if (picks.size >= 30) break
                }
                val ch = track.channel
                val sortedPicks = picks.sortedBy { if (ch.isNotEmpty() && it.channel == ch) 0 else 1 }
                if (sortedPicks.isNotEmpty() && _uiState.value.currentTrack?.id == track.id && loadToken == startToken) {
                    origQueue = null
                    _uiState.update { it.copy(queue = listOf(track) + sortedPicks, qpos = 0) }
                    if (_uiState.value.shuffle) applyShuffle(true)
                    toastNow("Radio on \u2014 more from ${track.artist}")
                }
            } finally {
                radioBusy = false
            }
        }
    }

    fun toggleAutoplay() {
        val next = !_uiState.value.prefs.autoplay
        viewModelScope.launch { repo.setAutoplay(next) }
        toastNow(if (next) "Autoplay on \u2014 the music continues after the queue" else "Autoplay off")
    }

    private fun maybeAutoplay() {
        val s = _uiState.value
        if (!s.prefs.autoplay || autoBusy || radioBusy) return
        val cur = s.currentTrack ?: return
        if (s.qpos < s.queue.size - 1) return
        autoBusy = true
        val startToken = loadToken
        viewModelScope.launch {
            try {
                val items = repo.fetchRadioMix(cur.id, limit = 60).getOrDefault(emptyList())
                    .filter { it.id != cur.id && SpotUiTextUtils.isRealSong(it) }
                    .shuffled()
                val have = _uiState.value.queue.map { it.id }.toSet()
                val blocked = _uiState.value.blockedIds
                val picks = mutableListOf<Track>()
                val perArtist = mutableMapOf<String, Int>()
                for (t in items) {
                    if (t.id in have || t.id in blocked) continue
                    val a = t.artist.lowercase()
                    if ((perArtist[a] ?: 0) >= 2) continue
                    perArtist[a] = (perArtist[a] ?: 0) + 1
                    picks.add(t.copy(isAuto = true))
                    if (picks.size >= 25) break
                }
                if (picks.isNotEmpty() && _uiState.value.currentTrack?.id == cur.id && loadToken == startToken) {
                    val wasEnd = _uiState.value.qpos == _uiState.value.queue.size - 1
                    _uiState.update { it.copy(queue = it.queue + picks) }
                    if (_uiState.value.shuffle) {
                        origQueue = null
                        applyShuffle(true)
                    }
                    toastNow("Autoplay \u2014 more from ${cur.artist}")
                    if (wasEnd && _uiState.value.playerState.isIdle) {
                        next(auto = true)
                    }
                }
            } finally {
                autoBusy = false
            }
        }
    }

    // --- Queue operations ---
    fun addToQueue(track: Track) {
        val s = _uiState.value
        if (s.currentTrack == null) {
            play(listOf(track), 0)
            return
        }
        val tagged = track.copy(source = "Added")
        _uiState.update { it.copy(queue = it.queue + tagged) }
        origQueue = origQueue?.plus(tagged)
        toastNow("Added to queue: ${track.title.take(30)}")
    }

    fun playNext(track: Track) {
        val s = _uiState.value
        if (s.currentTrack == null) {
            play(listOf(track), 0)
            return
        }
        val tagged = track.copy(source = "Added")
        val insertIdx = (s.qpos + 1).coerceIn(0, s.queue.size)
        val mutable = s.queue.toMutableList().apply { add(insertIdx, tagged) }
        _uiState.update { it.copy(queue = mutable) }
        origQueue = origQueue?.plus(tagged)
        toastNow("Plays next: ${track.title.take(30)}")
    }

    fun queueAll(tracks: List<Track>) {
        val s = _uiState.value
        val have = s.queue.map { it.id }.toSet()
        val fresh = tracks.filter { it.id !in have }
        if (fresh.isEmpty()) {
            toastNow("Every song is already in the queue")
            return
        }
        if (s.currentTrack == null) {
            play(fresh, 0)
            return
        }
        val tagged = fresh.map { it.copy(source = "Added") }
        _uiState.update { it.copy(queue = it.queue + tagged) }
        origQueue = origQueue?.plus(tagged)
        toastNow("Added ${fresh.size} song${if (fresh.size == 1) "" else "s"} to the queue")
    }

    fun playNextAll(tracks: List<Track>) {
        if (tracks.isEmpty()) {
            toastNow("Nothing to play next")
            return
        }
        val s = _uiState.value
        if (s.currentTrack == null) {
            play(tracks, 0)
            return
        }
        val tagged = tracks.map { it.copy(source = "Added") }
        val insertIdx = (s.qpos + 1).coerceIn(0, s.queue.size)
        val mutable = s.queue.toMutableList().apply { addAll(insertIdx, tagged) }
        _uiState.update { it.copy(queue = mutable) }
        origQueue = origQueue?.plus(tagged)
        toastNow("Play next: ${tagged.size} song${if (tagged.size == 1) "" else "s"}")
    }

    fun moveQueueItem(idx: Int, delta: Int) {
        val s = _uiState.value
        val target = idx + delta
        if (idx <= s.qpos || target <= s.qpos || idx !in s.queue.indices || target !in s.queue.indices) return
        val mutable = s.queue.toMutableList()
        val item = mutable.removeAt(idx)
        mutable.add(target, item)
        _uiState.update { it.copy(queue = mutable) }
    }

    fun moveQueueItemToNext(idx: Int) {
        val s = _uiState.value
        if (idx !in s.queue.indices || idx == s.qpos) return
        val mutable = s.queue.toMutableList()
        val t = mutable.removeAt(idx)
        var newQpos = s.qpos
        if (idx < newQpos) newQpos--
        val insertAt = (newQpos + 1).coerceIn(0, mutable.size)
        mutable.add(insertAt, t)
        _uiState.update { it.copy(queue = mutable, qpos = newQpos) }
        toastNow("Playing soon: ${t.title.take(30)}")
    }

    fun removeQueueAt(idx: Int) {
        val s = _uiState.value
        if (idx !in s.queue.indices) return
        val mutable = s.queue.toMutableList()
        val removed = mutable.removeAt(idx)
        val newQpos = if (idx <= s.qpos) s.qpos - 1 else s.qpos
        origQueue = origQueue?.filterNot { it.id == removed.id }
        _uiState.update { it.copy(queue = mutable, qpos = newQpos) }
        toastNow("Removed from queue: ${removed.title.take(30)}")
    }

    fun clearUpcoming() {
        val s = _uiState.value
        if (s.qpos + 1 >= s.queue.size) {
            toastNow("Nothing upcoming to clear")
            return
        }
        val kept = s.queue.take(s.qpos + 1)
        val removedCount = s.queue.size - kept.size
        val keptIds = kept.map { it.id }.toSet()
        origQueue = origQueue?.filter { it.id in keptIds }
        _uiState.update { it.copy(queue = kept) }
        toastNow("Cleared $removedCount upcoming song${if (removedCount == 1) "" else "s"}")
    }

    fun dropAutoplayed() {
        val s = _uiState.value
        val dropIndices = s.queue.indices.filter { s.queue[it].isAuto && it != s.qpos }.toSet()
        if (dropIndices.isEmpty()) {
            toastNow("No autoplayed songs to drop")
            return
        }
        val newQueue = s.queue.filterIndexed { i, _ -> i !in dropIndices }
        val droppedBefore = dropIndices.count { it < s.qpos }
        val newQpos = (s.qpos - droppedBefore).coerceIn(0, (newQueue.size - 1).coerceAtLeast(0))
        val keptIds = newQueue.map { it.id }.toSet()
        origQueue = origQueue?.filter { it.id in keptIds }
        _uiState.update { it.copy(queue = newQueue, qpos = newQpos) }
        toastNow("Dropped ${dropIndices.size} autoplayed song${if (dropIndices.size == 1) "" else "s"}")
    }

    fun saveQueueAsPlaylist() {
        val s = _uiState.value
        if (s.queue.isEmpty()) {
            toastNow("Queue is empty")
            return
        }
        val seen = mutableSetOf<String>()
        val deduped = s.queue.filter { seen.add(it.id) }.map { it.copy(isAuto = false, source = null) }
        val name = java.text.SimpleDateFormat("Queue MMM dd HH:mm", java.util.Locale.US).format(java.util.Date())
        viewModelScope.launch {
            repo.createPlaylist(name, deduped)
            toastNow("Saved ${deduped.size} songs as $name")
        }
    }

    // --- Mixes & Similar ("Made for you") ---
    fun playMix(mix: DailyMix) {
        val recent = _uiState.value.library.history.take(10).map { it.id }.toSet()
        val shuffled = SpotUiTextUtils.smartShuffle(
            tracks = mix.tracks,
            recentIds = recent,
            mode = _uiState.value.prefs.shuffleMode,
            plays = _uiState.value.library.playCounts
        )
        play(shuffled, 0, source = mix.name)
        toastNow("${mix.name}: ${shuffled.size} songs - ${mix.artist} and more")
    }

    fun queueMix(mix: DailyMix) {
        if (mix.tracks.isEmpty()) return
        queueAll(mix.tracks)
    }

    fun refreshSimilar(force: Boolean) {
        val s = _uiState.value
        val (seed, isArtist, vid) = computeSimilarSeed(s)
        if (seed.isEmpty()) return
        val cache = s.prefs.similarCache
        val nowSec = System.currentTimeMillis() / 1000.0
        if (!force && cache.version == 2 && cache.seed == seed && cache.items.isNotEmpty()) return
        if (simBusy) return
        if (!force && nowSec - lastSimAtSec < 120.0) return

        if (force && cache.pool.isNotEmpty() && cache.seed == seed) {
            val picks = pickSimilar(cache.pool)
            viewModelScope.launch {
                repo.setSimilarCache(cache.copy(items = picks, updatedAtSec = nowSec))
                toastNow("Refreshed Made for you")
            }
            return
        }

        simBusy = true
        lastSimAtSec = nowSec
        val query = if (isArtist) "$seed songs" else seed
        val kind = if (isArtist) "artist" else "query"
        viewModelScope.launch {
            try {
                val items = repo.searchYouTube(query).getOrDefault(emptyList())
                val firstVid = vid ?: items.firstOrNull()?.id
                val pool = items.filter { SpotUiTextUtils.isRealSong(it) }
                val picks = pickSimilar(pool)
                if (picks.isNotEmpty()) {
                    repo.setSimilarCache(
                        SimilarCache(2, seed, kind, firstVid, picks, pool, System.currentTimeMillis() / 1000.0)
                    )
                }
                if (firstVid != null) {
                    val radio = repo.fetchRadioMix(firstVid, limit = 90).getOrDefault(emptyList())
                        .filter { SpotUiTextUtils.isRealSong(it) }
                        .take(90)
                    val upgradedPicks = pickSimilar(radio)
                    if (upgradedPicks.isNotEmpty()) {
                        repo.setSimilarCache(
                            SimilarCache(2, seed, kind, firstVid, upgradedPicks, radio, System.currentTimeMillis() / 1000.0)
                        )
                    }
                }
            } finally {
                simBusy = false
            }
        }
    }

    private fun computeSimilarSeed(s: SpotUiState): Triple<String, Boolean, String?> {
        val hist = s.library.history
        val newestPlay = hist.firstOrNull()?.playedAtSec ?: 0.0
        if (s.prefs.lastSearchEpochSec > newestPlay) {
            s.library.recentSearches.firstOrNull { it.length > 2 }?.let { return Triple(it, false, null) }
        }
        hist.take(6).firstOrNull { it.artist.isNotBlank() }?.let { return Triple(it.artist.trim(), true, it.id) }
        s.library.liked.take(6).firstOrNull { it.artist.isNotBlank() }?.let { return Triple(it.artist.trim(), true, it.id) }
        s.library.recentSearches.firstOrNull { it.length > 2 }?.let { return Triple(it, false, null) }
        return Triple("", false, null)
    }

    private fun pickSimilar(items: List<Track>): List<Track> {
        val s = _uiState.value
        val seenIds = s.library.history.map { it.id }.toSet() + s.library.liked.map { it.id } + s.blockedIds
        val filtered = items.filter { it.id !in seenIds && SpotUiTextUtils.isRealSong(it) }
        val seenTitles = mutableSetOf<String>()
        val uniq = mutableListOf<Track>()
        for (t in filtered) {
            val k = t.title.lowercase().filter { it.isLetterOrDigit() }
            if (k.isNotEmpty() && seenTitles.add(k)) uniq.add(t)
        }
        uniq.shuffle()
        val picks = mutableListOf<Track>()
        val perArtist = mutableMapOf<String, Int>()
        for (t in uniq) {
            val a = t.artist.lowercase()
            if ((perArtist[a] ?: 0) >= 2) continue
            perArtist[a] = (perArtist[a] ?: 0) + 1
            picks.add(t)
            if (picks.size >= 6) break
        }
        return picks
    }

    // --- Library & Playlists ---
    fun toggleLike(track: Track) {
        val likedNow = track.id in _uiState.value.likedIds
        viewModelScope.launch {
            repo.toggleLike(track, likedNow)
            toastNow(if (likedNow) "Removed from Liked Songs" else "Added to Liked Songs")
        }
    }

    fun likeAll(playlist: Playlist) {
        if (playlist.tracks.isEmpty()) {
            toastNow("This playlist is empty")
            return
        }
        viewModelScope.launch {
            val added = repo.likeAll(playlist.tracks, _uiState.value.likedIds)
            if (added == 0) toastNow("Every song in ${playlist.name} is already liked")
            else toastNow("Liked $added song${if (added == 1) "" else "s"} from ${playlist.name}")
        }
    }

    fun toggleBlock(track: Track) {
        val blockedNow = track.id in _uiState.value.blockedIds
        viewModelScope.launch {
            repo.toggleBlock(track.id, blockedNow)
            toastNow(if (blockedNow) "${track.title} is back in suggestions" else "Won't suggest ${track.title} again")
        }
    }

    fun createOrImportPlaylist(input: String, pendingTrack: Track? = null, mergeFrom: Playlist? = null) {
        val trimmed = input.trim()
        if (trimmed.contains("list=") || trimmed.contains("youtube.com/playlist")) {
            toastNow("Importing playlist from YouTube\u2026")
            viewModelScope.launch {
                val res = repo.fetchYouTubePlaylist(trimmed)
                res.onSuccess { (ytTitle, tracks) ->
                    if (tracks.isEmpty()) {
                        toastNow("No songs found at that link")
                    } else {
                        val name = uniquePlaylistName(ytTitle ?: "YouTube import")
                        val newId = repo.createPlaylist(name, tracks)
                        toastNow("Imported $name (${tracks.size} songs)")
                        navigateTo(NavDest.PlaylistDest(newId))
                    }
                }.onFailure { err ->
                    toastNow("Import failed: ${err.message ?: "invalid link"}")
                }
            }
            return
        }
        viewModelScope.launch {
            val tracks = when {
                pendingTrack != null -> listOf(pendingTrack.copy(addedDate = SpotUiTextUtils.todayDateStr()))
                else -> emptyList()
            }
            val newId = repo.createPlaylist(trimmed.ifEmpty { "New Playlist" }, tracks)
            if (mergeFrom != null) {
                val created = Playlist(newId, trimmed.ifEmpty { "New Playlist" }, tracks)
                mergePlaylists(mergeFrom, created)
            } else {
                toastNow("Created playlist: ${trimmed.ifEmpty { "New Playlist" }}")
                navigateTo(NavDest.PlaylistDest(newId))
            }
        }
    }

    fun importPlaylistJsonText(rawJson: String) {
        val parsed = repo.parsePlaylistJson(rawJson)
        if (parsed == null) {
            toastNow("Not a valid SpotUI playlist JSON file")
            return
        }
        val (rawName, tracks) = parsed
        viewModelScope.launch {
            val name = uniquePlaylistName(rawName)
            val id = repo.createPlaylist(name, tracks)
            toastNow("Imported $name (${tracks.size} songs)")
            navigateTo(NavDest.PlaylistDest(id))
        }
    }

    private fun uniquePlaylistName(base: String): String {
        val clean = base.replace(Regex("\\s+"), " ").trim().take(60).ifEmpty { "YouTube import" }
        val existing = _uiState.value.library.playlists.map { it.name }.toSet()
        var candidate = clean
        var n = 2
        while (candidate in existing) {
            candidate = "$clean $n"
            n++
        }
        return candidate
    }

    fun addTrackToPlaylist(playlist: Playlist, track: Track) {
        if (playlist.tracks.any { it.id == track.id }) {
            toastNow("Already in ${playlist.name}")
            return
        }
        val updated = playlist.tracks + track.copy(addedDate = SpotUiTextUtils.todayDateStr())
        viewModelScope.launch {
            repo.replacePlaylistTracks(playlist.id, updated)
            toastNow("Added to ${playlist.name}")
        }
    }

    fun removeTrackFromPlaylist(playlist: Playlist, idx: Int) {
        if (idx !in playlist.tracks.indices) return
        val mutable = playlist.tracks.toMutableList()
        val removed = mutable.removeAt(idx)
        trash = TrashItem.DeletedTrack(playlist.id, idx, removed)
        _uiState.update { it.copy(hasUndo = true) }
        viewModelScope.launch {
            repo.replacePlaylistTracks(playlist.id, mutable)
            toastNow("Removed ${removed.title} (Undo available)")
        }
    }

    fun moveTrackInPlaylist(playlist: Playlist, idx: Int, delta: Int) {
        val target = idx + delta
        if (idx !in playlist.tracks.indices || target !in playlist.tracks.indices) return
        val mutable = playlist.tracks.toMutableList()
        val item = mutable.removeAt(idx)
        mutable.add(target, item)
        viewModelScope.launch {
            repo.replacePlaylistTracks(playlist.id, mutable)
        }
    }

    fun renamePlaylist(playlist: Playlist, newName: String) {
        val clean = newName.trim()
        if (clean.isEmpty()) {
            toastNow("Playlist name cannot be empty")
            return
        }
        viewModelScope.launch {
            repo.renamePlaylist(playlist, clean)
            toastNow("Renamed playlist: $clean")
        }
    }

    fun duplicatePlaylist(playlist: Playlist) {
        val ownTracks = playlist.tracks.filterNot { it.isEnhanced }
        val newName = uniquePlaylistName("${playlist.name} (copy)")
        viewModelScope.launch {
            val id = repo.createPlaylist(newName, ownTracks)
            toastNow("Duplicated as: $newName")
            navigateTo(NavDest.PlaylistDest(id))
        }
    }

    fun mergePlaylists(source: Playlist, dest: Playlist) {
        val have = dest.tracks.map { it.id }.toSet()
        val today = SpotUiTextUtils.todayDateStr()
        val fresh = source.tracks.filter { it.id !in have }.map { it.copy(addedDate = it.addedDate ?: today) }
        if (fresh.isEmpty()) {
            toastNow("${dest.name} already has every song")
            return
        }
        viewModelScope.launch {
            repo.replacePlaylistTracks(dest.id, dest.tracks + fresh)
            toastNow("Merged ${fresh.size} song${if (fresh.size == 1) "" else "s"} into ${dest.name}")
        }
    }

    fun togglePin(playlist: Playlist) {
        val next = !playlist.pinned
        viewModelScope.launch {
            repo.setPlaylistPinned(playlist, next)
            toastNow((if (next) "Pinned " else "Unpinned ") + playlist.name)
        }
    }

    fun toggleEnhance(playlist: Playlist) {
        if (playlist.enhanced) {
            val removedCount = playlist.tracks.count { it.isEnhanced }
            val kept = playlist.tracks.filterNot { it.isEnhanced }
            viewModelScope.launch {
                repo.setPlaylistEnhanced(playlist, false, kept)
                toastNow("Enhance off \u00b7 removed $removedCount suggestion${if (removedCount == 1) "" else "s"}")
            }
            return
        }
        val own = playlist.tracks.filterNot { it.isEnhanced }
        if (own.isEmpty()) {
            toastNow("Add some songs first")
            return
        }
        val candidates = enhanceCandidates(playlist)
        val want = (own.size / 2).coerceIn(1, 30)
        val picks = candidates.take(want)
        if (picks.isEmpty()) {
            toastNow("No suggestions yet \u2014 like or play more songs")
            return
        }
        val today = SpotUiTextUtils.todayDateStr()
        val merged = mutableListOf<Track>()
        var added = 0
        own.forEachIndexed { i, t ->
            merged.add(t)
            if ((i + 1) % 2 == 0 && added < picks.size) {
                merged.add(picks[added].copy(isEnhanced = true, addedDate = today))
                added++
            }
        }
        while (added < picks.size) {
            merged.add(picks[added].copy(isEnhanced = true, addedDate = today))
            added++
        }
        viewModelScope.launch {
            repo.setPlaylistEnhanced(playlist, true, merged)
            toastNow("Enhanced ${playlist.name} \u00b7 $added suggestion${if (added == 1) "" else "s"}")
        }
    }

    private fun enhanceCandidates(pl: Playlist): List<Track> {
        val s = _uiState.value
        val seen = (pl.tracks.map { it.id } + s.blockedIds).toMutableSet()
        val artists = pl.tracks.map { SpotUiTextUtils.normArtist(it.artist) }.toSet()
        val pool = mutableListOf<Track>()
        fun scan(list: List<Track>) {
            for (t in list) {
                if (seen.add(t.id)) pool.add(t)
            }
        }
        scan(s.library.liked)
        scan(s.library.history)
        s.library.playlists.filter { it.id != pl.id }.forEach { scan(it.tracks) }
        return pool.sortedWith(
            compareBy<Track>(
                { if (SpotUiTextUtils.normArtist(it.artist) in artists) 0 else 1 },
                { -(s.library.playCounts[it.id]?.count ?: 0) },
                { it.title.lowercase() }
            )
        )
    }

    fun dedupePlaylist(playlist: Playlist) {
        val seen = mutableSetOf<String>()
        val keep = mutableListOf<Track>()
        val dropped = mutableListOf<Pair<Int, Track>>()
        playlist.tracks.forEachIndexed { i, t ->
            if (seen.add(t.id)) keep.add(t) else dropped.add(i to t)
        }
        if (dropped.isEmpty()) {
            toastNow("No duplicates in ${playlist.name}")
            return
        }
        trash = TrashItem.DedupedTracks(playlist.id, dropped)
        _uiState.update { it.copy(hasUndo = true) }
        viewModelScope.launch {
            repo.replacePlaylistTracks(playlist.id, keep)
            toastNow("Removed ${dropped.size} duplicate${if (dropped.size == 1) "" else "s"} \u2014 Undo available")
        }
    }

    fun deletePlaylist(playlist: Playlist) {
        trash = TrashItem.DeletedPlaylist(playlist)
        _uiState.update { s ->
            val cleanedStack = s.backStack.filterNot { it is NavDest.PlaylistDest && it.playlistId == playlist.id }
                .ifEmpty { listOf(NavDest.Home) }
            s.copy(backStack = cleanedStack, hasUndo = true)
        }
        viewModelScope.launch {
            repo.deletePlaylist(playlist.id)
            toastNow("Deleted playlist: ${playlist.name} (Undo available)")
        }
    }

    fun undoDelete() {
        val item = trash ?: run {
            toastNow("Nothing to restore")
            return
        }
        trash = null
        _uiState.update { it.copy(hasUndo = false) }
        viewModelScope.launch {
            when (item) {
                is TrashItem.DeletedPlaylist -> {
                    repo.createPlaylist(item.playlist.name, item.playlist.tracks, item.playlist.pinned, item.playlist.enhanced)
                    toastNow("Restored playlist: ${item.playlist.name}")
                }
                is TrashItem.DeletedTrack -> {
                    val pl = _uiState.value.library.playlists.firstOrNull { it.id == item.playlistId }
                    if (pl == null) {
                        toastNow("That playlist is gone")
                    } else {
                        val m = pl.tracks.toMutableList()
                        m.add(item.index.coerceIn(0, m.size), item.track)
                        repo.replacePlaylistTracks(pl.id, m)
                        toastNow("Restored ${item.track.title}")
                    }
                }
                is TrashItem.DedupedTracks -> {
                    val pl = _uiState.value.library.playlists.firstOrNull { it.id == item.playlistId }
                    if (pl == null) {
                        toastNow("That playlist is gone")
                    } else {
                        val m = pl.tracks.toMutableList()
                        for ((idx, tr) in item.dropped) {
                            m.add(idx.coerceIn(0, m.size), tr)
                        }
                        repo.replacePlaylistTracks(pl.id, m)
                        toastNow("Restored ${item.dropped.size} duplicate${if (item.dropped.size == 1) "" else "s"}")
                    }
                }
            }
        }
    }

    fun clearHistory() {
        viewModelScope.launch {
            repo.clearHistory()
            toastNow("Play history cleared \u2014 playlists and liked songs kept")
        }
    }

    fun shuffleLiked() {
        val s = _uiState.value
        val pool = s.library.liked.filter { it.id !in s.blockedIds }
        if (pool.isEmpty()) {
            toastNow("Like some songs first")
            return
        }
        val shuffled = SpotUiTextUtils.smartShuffle(pool, mode = s.prefs.shuffleMode, plays = s.library.playCounts)
        play(shuffled, 0, "Liked Songs")
        toastNow("Shuffling Liked Songs - ${shuffled.size} songs")
    }

    fun shuffleLibrary() {
        val s = _uiState.value
        val seen = mutableSetOf<String>()
        val all = mutableListOf<Track>()
        for (src in listOf(s.library.liked, s.library.history) + s.library.playlists.map { it.tracks }) {
            for (t in src) {
                if (t.id !in s.blockedIds && seen.add(t.id)) all.add(t)
            }
        }
        if (all.isEmpty()) {
            toastNow("Your library is empty \u2014 like or add some songs first")
            return
        }
        val shuffled = SpotUiTextUtils.smartShuffle(all, mode = s.prefs.shuffleMode, plays = s.library.playCounts)
        play(shuffled, 0, "Library shuffle")
        toastNow("Shuffling your library - ${shuffled.size} songs")
    }

    // --- Lyrics ---
    fun ensureLyrics(track: Track, forceShowLoading: Boolean = false) {
        if (track.id in _uiState.value.library.lyricsCache || track.id in lyricsInFlight) return
        lyricsInFlight.add(track.id)
        if (forceShowLoading) _uiState.update { it.copy(activeLyricsLoading = true) }
        viewModelScope.launch {
            try {
                repo.getOrFetchLyrics(track)
            } finally {
                lyricsInFlight.remove(track.id)
                _uiState.update { it.copy(activeLyricsLoading = false) }
            }
        }
    }

    // --- Audio / Settings / Theme / Sleep ---
    fun setVolume(vol: Int) {
        val clamped = vol.coerceIn(0, 100)
        mutedFromVol = null
        _uiState.update { it.copy(isMuted = false) }
        audioPlayer.setVolume(clamped)
        viewModelScope.launch { repo.setVolume(clamped) }
    }

    fun toggleMute() {
        val cur = _uiState.value.prefs.volume
        if (mutedFromVol != null) {
            val restore = mutedFromVol!!
            mutedFromVol = null
            _uiState.update { it.copy(isMuted = false) }
            audioPlayer.setVolume(restore)
            viewModelScope.launch { repo.setVolume(restore) }
            toastNow("Volume $restore")
        } else if (cur > 0) {
            mutedFromVol = cur
            _uiState.update { it.copy(isMuted = true) }
            audioPlayer.setVolume(0)
            viewModelScope.launch { repo.setVolume(0) }
            toastNow("Muted")
        }
    }

    fun changeSpeed(deltaIdx: Int) {
        val speeds = SpotUiTextUtils.SPEEDS
        val cur = _uiState.value.playerState.speed
        val idx = speeds.indexOfFirst { kotlin.math.abs(it - cur) < 0.01f }.takeIf { it >= 0 } ?: 1
        val next = speeds[(idx + deltaIdx).coerceIn(0, speeds.lastIndex)]
        audioPlayer.setSpeed(next)
        toastNow("Speed ${next.toString().removeSuffix(".0")}x")
    }

    fun resetSpeed() {
        audioPlayer.setSpeed(1.0f)
        toastNow("Speed 1x")
    }

    fun cycleEq() {
        val presets = EqPreset.entries
        val cur = _uiState.value.prefs.eqPreset
        val next = presets[(presets.indexOf(cur) + 1) % presets.size]
        audioPlayer.setEqPreset(next)
        viewModelScope.launch { repo.setEqPreset(next) }
        toastNow("Equalizer: ${next.label}")
    }

    fun toggleLeveling() {
        val next = !_uiState.value.prefs.volumeLeveling
        audioPlayer.setVolumeLeveling(next)
        viewModelScope.launch { repo.setVolumeLeveling(next) }
        toastNow(if (next) "Volume leveling on \u2014 loud and quiet songs sit closer" else "Volume leveling off")
    }

    fun toggleTimeLeft() {
        val next = !_uiState.value.prefs.timeLeft
        viewModelScope.launch { repo.setTimeLeft(next) }
    }

    fun setSortMode(mode: SortMode) {
        val cur = _uiState.value.prefs.sortMode
        val next = if (cur == mode) SortMode.DEFAULT else mode
        viewModelScope.launch { repo.setSortMode(next) }
        toastNow("Sort: ${next.label}")
    }

    fun cycleSortMode() {
        val modes = SortMode.entries
        val cur = _uiState.value.prefs.sortMode
        val next = modes[(modes.indexOf(cur) + 1) % modes.size]
        viewModelScope.launch { repo.setSortMode(next) }
        toastNow("Sort: ${next.label}")
    }

    fun toggleHistDedupe() {
        val next = !_uiState.value.prefs.histDedupe
        viewModelScope.launch { repo.setHistDedupe(next) }
        toastNow(if (next) "Recently Played: repeats hidden" else "Recently Played: repeats shown")
    }

    fun togglePrivateSession() {
        val next = !_uiState.value.privateSession
        _uiState.update { it.copy(privateSession = next) }
        toastNow(if (next) "Private session on \u00b7 plays won't count" else "Private session off \u00b7 listening counts again")
    }

    fun toggleZenMode() {
        val next = !_uiState.value.prefs.zenMode
        viewModelScope.launch { repo.setZenMode(next) }
        toastNow(if (next) "Sidebar hidden" else "Sidebar shown")
    }

    fun toggleReducedMotion() {
        val next = !_uiState.value.prefs.reducedMotion
        viewModelScope.launch { repo.setReducedMotion(next) }
        toastNow(if (next) "Reduced motion on" else "Reduced motion off")
    }

    fun setFindActive(active: Boolean) {
        _uiState.update { it.copy(findActive = active, findQuery = if (active) it.findQuery else "") }
    }

    fun onFindQueryChange(q: String) {
        _uiState.update { it.copy(findQuery = q) }
    }

    fun previewTheme(theme: SpotTheme) {
        _uiState.update { it.copy(previewTheme = theme) }
    }

    fun applyTheme(theme: SpotTheme) {
        _uiState.update { it.copy(previewTheme = null, activeModal = null) }
        viewModelScope.launch {
            repo.setTheme(theme)
            toastNow("Theme: ${theme.displayName}")
        }
    }

    // --- Sleep Timer ---
    fun setSleepMinutes(mins: Int) {
        if (mins <= 0) {
            sleepDeadlineMs = null
            audioPlayer.setFadeMultiplier(1.0f)
            _uiState.update { it.copy(sleepMinutes = 0, sleepEot = false, sleepRemainingSec = null) }
            toastNow("Sleep timer off")
            return
        }
        val clamped = mins.coerceIn(1, 1440)
        sleepDeadlineMs = System.currentTimeMillis() + clamped * 60_000L
        _uiState.update { it.copy(sleepMinutes = clamped, sleepEot = false, sleepRemainingSec = clamped * 60) }
        toastNow("Sleep timer: $clamped min")
    }

    fun setSleepEndOfTrack() {
        sleepDeadlineMs = null
        _uiState.update { it.copy(sleepMinutes = 0, sleepEot = true, sleepRemainingSec = null) }
        toastNow("Sleep timer: end of track")
    }

    private fun handleTrackEnded() {
        if (_uiState.value.sleepEot) {
            _uiState.update { it.copy(sleepEot = false) }
            audioPlayer.pause()
            audioPlayer.setFadeMultiplier(1.0f)
            toastNow("Sleep timer \u2014 playback paused")
        } else {
            next(auto = true)
        }
    }

    private fun startSleepMonitor() {
        sleepJob?.cancel()
        sleepJob = viewModelScope.launch {
            while (isActive) {
                delay(1000L)
                val s = _uiState.value
                val deadline = sleepDeadlineMs
                var remSec: Double? = null
                if (deadline != null) {
                    remSec = (deadline - System.currentTimeMillis()) / 1000.0
                    _uiState.update { it.copy(sleepRemainingSec = remSec.toInt().coerceAtLeast(0)) }
                    if (remSec <= 0.0) {
                        sleepDeadlineMs = null
                        loadToken++
                        audioPlayer.setLoading(false)
                        audioPlayer.pause()
                        audioPlayer.setFadeMultiplier(1.0f)
                        _uiState.update { it.copy(sleepMinutes = 0, sleepRemainingSec = null) }
                        toastNow("Sleep timer \u2014 playback paused")
                        continue
                    }
                } else if (s.sleepEot && !s.playerState.isIdle && s.playerState.durationSec > 0) {
                    remSec = s.playerState.durationSec - s.playerState.positionSec
                }

                if (remSec != null && remSec > 0.0 && remSec <= 20.0) {
                    audioPlayer.setFadeMultiplier((remSec / 20.0).toFloat().coerceIn(0f, 1f))
                } else {
                    audioPlayer.setFadeMultiplier(1.0f)
                }
            }
        }
    }

    // --- Clipboard / External / Export helpers ---
    fun copyText(text: String, what: String) {
        val cm = getApplication<Application>().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText(what, text))
        toastNow("$what copied to clipboard")
    }

    fun copyTrackLink(track: Track) = copyText(track.url, "Link")

    fun copyTracklist(name: String, tracks: List<Track>) {
        if (tracks.isEmpty()) {
            toastNow("Nothing to copy")
            return
        }
        copyText(SpotUiTextUtils.buildTracklistShareText(name, tracks), "Tracklist")
    }

    fun copyStatsSummary() {
        copyText(SpotUiTextUtils.buildStatsShareText(_uiState.value.stats), "Stats")
    }

    fun openTrackInBrowser(track: Track) {
        runCatching {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(track.url)).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            getApplication<Application>().startActivity(intent)
            toastNow("Opening ${track.title} in browser")
        }.onFailure {
            toastNow("Link: ${track.url}")
        }
    }

    fun buildPlaylistJson(playlist: Playlist): String = repo.exportPlaylistJson(playlist)

    fun openSourcePage(source: String?) {
        val s = _uiState.value
        when {
            source == "Liked Songs" -> navigateTo(NavDest.Liked)
            source == "Recently Played" -> navigateTo(NavDest.History)
            source == "Made for you" -> navigateTo(NavDest.Similar)
            source != null -> {
                val pl = s.library.playlists.firstOrNull { it.name == source }
                if (pl != null) navigateTo(NavDest.PlaylistDest(pl.id))
                else if (artistLibraryTracks(source).isNotEmpty()) navigateTo(NavDest.Artist(source))
                else toastNow("No page for this source")
            }
            else -> toastNow("No page for this source")
        }
    }

    private fun audioPlayerStateSync() {
        _uiState.update { it.copy(playerState = audioPlayer.state.value) }
    }

    override fun onCleared() {
        snapshotSession()
        audioPlayer.releasePlayer()
        super.onCleared()
    }
}
