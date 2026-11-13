package com.example

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.QueueMusic
import androidx.compose.material.icons.rounded.BarChart
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.LibraryMusic
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.ViewSidebar
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.data.model.NavDest
import com.example.data.model.Playlist
import com.example.player.PlaybackService
import com.example.ui.components.DesktopPlayerBar
import com.example.ui.components.MiniPlayerBar
import com.example.ui.components.SplashOverlay
import com.example.ui.components.SpotUiModals
import com.example.ui.components.SpotUiSidebar
import com.example.ui.screens.ArtistScreen
import com.example.ui.screens.CollectionScreen
import com.example.ui.screens.HomeScreen
import com.example.ui.screens.LibraryScreen
import com.example.ui.screens.NowPlayingScreen
import com.example.ui.screens.QueueScreen
import com.example.ui.screens.SearchScreen
import com.example.ui.screens.SimilarScreen
import com.example.ui.screens.StatsScreen
import com.example.ui.theme.LocalSpotColors
import com.example.ui.theme.SpotUiTheme
import com.example.ui.viewmodel.ActiveModal
import com.example.ui.viewmodel.SpotUiState
import com.example.ui.viewmodel.SpotUiViewModel

class MainActivity : ComponentActivity() {

    private val viewModel: SpotUiViewModel by viewModels()
    private var serviceBound = false

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, service: IBinder?) {
            val binder = service as? PlaybackService.LocalBinder
            viewModel.attachPlaybackService(binder?.getService())
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            viewModel.attachPlaybackService(null)
        }
    }

    override fun onStart() {
        super.onStart()
        val intent = Intent(this, PlaybackService::class.java)
        runCatching {
            bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE)
            serviceBound = true
        }
    }

    override fun onStop() {
        if (serviceBound) {
            runCatching { unbindService(serviceConnection) }
            serviceBound = false
        }
        super.onStop()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val state by viewModel.uiState.collectAsStateWithLifecycle()
            SpotUiTheme(spotTheme = state.effectiveTheme) {
                SpotUiRoot(state = state, viewModel = viewModel)
            }
        }
    }
}

@Composable
private fun SpotUiRoot(
    state: SpotUiState,
    viewModel: SpotUiViewModel
) {
    val spot = LocalSpotColors.current
    val context = LocalContext.current
    var pendingExportPlaylist by remember { mutableStateOf<Playlist?>(null) }
    var askedNotifPerm by remember { mutableStateOf(false) }

    val notifPermLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { _ -> }

    LaunchedEffect(state.currentTrack?.id) {
        if (state.currentTrack != null && !askedNotifPerm && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            askedNotifPerm = true
            val granted = ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) {
                notifPermLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    val openJsonLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            runCatching {
                context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
            }.onSuccess { raw ->
                if (raw != null) viewModel.importPlaylistJsonText(raw)
                else viewModel.toastNow("Could not read file")
            }.onFailure {
                viewModel.toastNow("Import failed")
            }
        }
    }

    val createJsonLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        val pl = pendingExportPlaylist
        pendingExportPlaylist = null
        if (uri != null && pl != null) {
            runCatching {
                context.contentResolver.openOutputStream(uri)?.bufferedWriter()?.use {
                    it.write(viewModel.buildPlaylistJson(pl))
                }
            }.onSuccess {
                viewModel.toastNow("Exported ${pl.name}.json")
            }.onFailure {
                viewModel.toastNow("Export failed")
            }
        }
    }

    BackHandler(enabled = state.activeModal != null || state.findActive || state.backStack.size > 1) {
        viewModel.goBack()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(spot.background)
            .windowInsetsPadding(WindowInsets.safeDrawing)
    ) {
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val isWide = maxWidth >= 720.dp

            Column(modifier = Modifier.fillMaxSize()) {
                Row(modifier = Modifier.weight(1f).fillMaxWidth()) {
                    if (isWide && !state.prefs.zenMode) {
                        SpotUiSidebar(
                            currentDest = state.currentDest,
                            likedCount = state.library.liked.size,
                            historyCount = state.library.history.size,
                            playlists = state.library.playlists,
                            playSource = state.playSource,
                            isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                            reducedMotion = state.prefs.reducedMotion,
                            sleepRemainingSec = state.sleepRemainingSec,
                            sleepEot = state.sleepEot,
                            privateSession = state.privateSession,
                            onNavigate = { dest ->
                                if (dest is NavDest.Home || dest is NavDest.Search || dest is NavDest.Stats) {
                                    viewModel.switchTab(dest)
                                } else {
                                    viewModel.navigateTo(dest)
                                }
                            },
                            onCreatePlaylist = { viewModel.openModal(ActiveModal.CreateOrImportPlaylist()) },
                            onOpenSleepTimer = { viewModel.openModal(ActiveModal.SleepTimerSheet) }
                        )
                        Box(modifier = Modifier.width(1.dp).fillMaxHeight().background(spot.divider))
                    }

                    Column(modifier = Modifier.weight(1f).fillMaxHeight()) {
                        SpotTopBar(
                            state = state,
                            isWide = isWide,
                            onBack = { viewModel.goBack() },
                            onToggleZen = { viewModel.toggleZenMode() },
                            onOpenSleep = { viewModel.openModal(ActiveModal.SleepTimerSheet) },
                            onOpenQueue = { viewModel.navigateTo(NavDest.Queue) },
                            onOpenMenu = { viewModel.openModal(ActiveModal.PlaybackMenu) }
                        )
                        HorizontalDivider(color = spot.divider, thickness = 1.dp)

                        Box(modifier = Modifier.weight(1f).fillMaxWidth()) {
                            when (val dest = state.currentDest) {
                                NavDest.Home -> HomeScreen(state = state, viewModel = viewModel, isWide = isWide)
                                NavDest.Search -> SearchScreen(state = state, viewModel = viewModel)
                                NavDest.Library -> LibraryScreen(state = state, viewModel = viewModel)
                                NavDest.Liked -> CollectionScreen("liked", null, state, viewModel)
                                NavDest.History -> CollectionScreen("history", null, state, viewModel)
                                is NavDest.PlaylistDest -> {
                                    val pl = state.library.playlists.firstOrNull { it.id == dest.playlistId }
                                    CollectionScreen("playlist", pl, state, viewModel)
                                }
                                is NavDest.Artist -> ArtistScreen(dest.name, state, viewModel)
                                NavDest.Queue -> QueueScreen(state, viewModel)
                                NavDest.NowPlaying -> NowPlayingScreen(state, viewModel)
                                NavDest.Stats -> StatsScreen(state, viewModel)
                                NavDest.Similar -> SimilarScreen(state, viewModel)
                            }
                        }
                    }
                }

                if (isWide) {
                    DesktopPlayerBar(
                        track = state.currentTrack,
                        playerState = state.playerState,
                        isLiked = state.currentTrack?.id?.let { it in state.likedIds } == true,
                        shuffle = state.shuffle,
                        shuffleMode = state.prefs.shuffleMode,
                        repeat = state.repeat,
                        timeLeft = state.prefs.timeLeft,
                        isMuted = state.isMuted,
                        onOpenNowPlaying = { viewModel.navigateTo(NavDest.NowPlaying) },
                        onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                        onToggleLike = { state.currentTrack?.let(viewModel::toggleLike) },
                        onToggleShuffle = { viewModel.toggleShuffle() },
                        onPrev = { viewModel.prev() },
                        onTogglePlayPause = { viewModel.togglePlayPause() },
                        onNext = { viewModel.next() },
                        onCycleRepeat = { viewModel.cycleRepeat() },
                        onSeek = { viewModel.seekTo(it) },
                        onToggleTimeLeft = { viewModel.toggleTimeLeft() },
                        onCycleSpeed = {
                            viewModel.changeSpeed(if (state.playerState.speed >= 2.0f) -4 else 1)
                        },
                        onOpenLyrics = {
                            state.currentTrack?.let { viewModel.openModal(ActiveModal.LyricsSheet(it)) }
                        },
                        onOpenQueue = { viewModel.navigateTo(NavDest.Queue) },
                        onToggleMute = { viewModel.toggleMute() },
                        onVolumeChange = { viewModel.setVolume(it) },
                        onOpenPlaybackMenu = { viewModel.openModal(ActiveModal.PlaybackMenu) }
                    )
                } else {
                    if (state.currentTrack != null && state.currentDest !is NavDest.NowPlaying) {
                        MiniPlayerBar(
                            track = state.currentTrack,
                            playerState = state.playerState,
                            isLiked = state.currentTrack.id in state.likedIds,
                            onToggleLike = { viewModel.toggleLike(state.currentTrack) },
                            onTogglePlayPause = { viewModel.togglePlayPause() },
                            onNext = { viewModel.next() },
                            onClickBar = { viewModel.navigateTo(NavDest.NowPlaying) }
                        )
                    }
                    CompactBottomNavBar(
                        currentDest = state.currentDest,
                        onSelectTab = { viewModel.switchTab(it) }
                    )
                }
            }

            // Toast Pill Overlay
            AnimatedVisibility(
                visible = state.toastMessage != null,
                enter = fadeIn(),
                exit = fadeOut(),
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = if (isWide) 104.dp else 132.dp, start = 20.dp, end = 20.dp)
            ) {
                Surface(
                    color = spot.raised,
                    shape = RoundedCornerShape(24.dp),
                    shadowElevation = 6.dp,
                    modifier = Modifier.border(1.dp, spot.accent.copy(alpha = 0.6f), RoundedCornerShape(24.dp))
                ) {
                    Text(
                        text = state.toastMessage ?: "",
                        color = spot.textPrimary,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp)
                    )
                }
            }

            SpotUiModals(
                modal = state.activeModal,
                state = state,
                viewModel = viewModel,
                isWide = isWide,
                onPickJsonFile = { openJsonLauncher.launch(arrayOf("application/json", "text/plain", "*/*")) },
                onExportPlaylistJson = { pl ->
                    pendingExportPlaylist = pl
                    val safeName = pl.name.replace(Regex("[^A-Za-z0-9._-]+"), "_").trim('_').ifEmpty { "playlist" }
                    createJsonLauncher.launch("$safeName.json")
                }
            )
        }

        if (state.showSplash) {
            SplashOverlay(
                reducedMotion = state.prefs.reducedMotion,
                onDismiss = { viewModel.dismissSplash() }
            )
        }
    }
}

@Composable
private fun SpotTopBar(
    state: SpotUiState,
    isWide: Boolean,
    onBack: () -> Unit,
    onToggleZen: () -> Unit,
    onOpenSleep: () -> Unit,
    onOpenQueue: () -> Unit,
    onOpenMenu: () -> Unit
) {
    val spot = LocalSpotColors.current
    val dest = state.currentDest
    val title = when (dest) {
        NavDest.Home -> "SpotUI"
        NavDest.Search -> "Search"
        NavDest.Library -> stringResource(R.string.your_library)
        NavDest.Liked -> stringResource(R.string.liked_songs)
        NavDest.History -> stringResource(R.string.recently_played)
        is NavDest.PlaylistDest -> state.library.playlists.firstOrNull { it.id == dest.playlistId }?.name ?: "Playlist"
        is NavDest.Artist -> dest.name
        NavDest.Queue -> stringResource(R.string.queue_title)
        NavDest.NowPlaying -> "Now Playing"
        NavDest.Stats -> stringResource(R.string.stats_title)
        NavDest.Similar -> stringResource(R.string.made_for_you)
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(spot.background)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (state.backStack.size > 1) {
            IconButton(
                onClick = onBack,
                modifier = Modifier.minimumInteractiveComponentSize().testTag("top_back_btn")
            ) {
                Icon(Icons.AutoMirrored.Rounded.ArrowBack, stringResource(R.string.cd_back), tint = spot.textPrimary)
            }
        } else if (isWide && !state.prefs.zenMode) {
            Spacer(Modifier.width(8.dp))
        }

        if (isWide) {
            IconButton(
                onClick = onToggleZen,
                modifier = Modifier.minimumInteractiveComponentSize().testTag("top_zen_btn")
            ) {
                Icon(
                    Icons.Rounded.ViewSidebar,
                    stringResource(R.string.cd_zen),
                    tint = if (state.prefs.zenMode) spot.accent else spot.textDim
                )
            }
        }

        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            color = spot.textPrimary,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f).padding(horizontal = 6.dp)
        )

        if (state.privateSession) {
            Icon(
                Icons.Rounded.VisibilityOff,
                "Private session active",
                tint = spot.accent,
                modifier = Modifier.padding(end = 6.dp).size(18.dp)
            )
        }

        if (state.sleepEot || state.sleepRemainingSec != null) {
            IconButton(
                onClick = onOpenSleep,
                modifier = Modifier.minimumInteractiveComponentSize().testTag("top_sleep_btn")
            ) {
                Icon(Icons.Rounded.Bedtime, "Sleep timer active", tint = spot.accent)
            }
        }

        if (!isWide) {
            IconButton(
                onClick = onOpenQueue,
                modifier = Modifier.minimumInteractiveComponentSize().testTag("top_queue_btn")
            ) {
                Icon(Icons.AutoMirrored.Rounded.QueueMusic, stringResource(R.string.cd_queue), tint = spot.textPrimary)
            }
        }

        IconButton(
            onClick = onOpenMenu,
            modifier = Modifier.minimumInteractiveComponentSize().testTag("top_settings_btn")
        ) {
            Icon(Icons.Rounded.Settings, "Playback settings and themes", tint = spot.textPrimary)
        }
    }
}

@Composable
private fun CompactBottomNavBar(
    currentDest: NavDest,
    onSelectTab: (NavDest) -> Unit
) {
    val spot = LocalSpotColors.current
    NavigationBar(
        containerColor = spot.sidebar,
        contentColor = spot.textPrimary
    ) {
        val navItems = listOf(
            Triple(NavDest.Home, "Home", Icons.Rounded.Home),
            Triple(NavDest.Search, "Search", Icons.Rounded.Search),
            Triple(NavDest.Library, "Library", Icons.Rounded.LibraryMusic),
            Triple(NavDest.Stats, "Stats", Icons.Rounded.BarChart)
        )
        navItems.forEach { (dest, label, icon) ->
            val selected = currentDest == dest ||
                (dest == NavDest.Library && (currentDest is NavDest.Liked || currentDest is NavDest.History || currentDest is NavDest.PlaylistDest))
            NavigationBarItem(
                selected = selected,
                onClick = { onSelectTab(dest) },
                icon = { Icon(icon, contentDescription = label) },
                label = { Text(label, maxLines = 1) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = spot.accent,
                    selectedTextColor = spot.accent,
                    indicatorColor = spot.raised,
                    unselectedIconColor = spot.textDim,
                    unselectedTextColor = spot.textDim
                ),
                modifier = Modifier.testTag("bottom_nav_${label.lowercase()}")
            )
        }
    }
}
