package com.example.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.MergingMediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.ui.PlayerView
import com.example.data.model.NavDest
import com.example.data.model.Track
import com.example.data.remote.YouTubeClient
import com.example.ui.components.TrackRow
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.ActiveModal
import com.example.ui.viewmodel.SpotUiViewModel
import kotlinx.coroutines.launch

@OptIn(UnstableApi::class)
@Composable
fun VideoScreen(track: Track, viewModel: SpotUiViewModel, onClose: () -> Unit) {
    val spot = LocalSpotColors.current
    val context = LocalContext.current
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var stream by remember { mutableStateOf<YouTubeClient.VideoStream?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var related by remember { mutableStateOf<List<Track>?>(null) }
    var comments by remember { mutableStateOf<List<YouTubeClient.YtComment>?>(null) }
    var details by remember { mutableStateOf<YouTubeClient.YtVideoDetails?>(null) }
    var descExpanded by remember { mutableStateOf(false) }
    var maxQuality by remember { mutableStateOf(1080) }

    val player = remember { ExoPlayer.Builder(context).build() }

    LaunchedEffect(track.id, maxQuality) {
        error = null
        stream = null
        player.stop()
        viewModel.resolveVideoStream(track.id, maxQuality)
            .onSuccess { vs ->
                stream = vs
                val ds = DefaultHttpDataSource.Factory().setUserAgent("SpotUI/1.0 (Android)")
                val videoSource = ProgressiveMediaSource.Factory(ds)
                    .createMediaSource(MediaItem.fromUri(vs.videoUrl))
                val source = if (vs.audioUrl != null) {
                    MergingMediaSource(
                        videoSource,
                        ProgressiveMediaSource.Factory(ds)
                            .createMediaSource(MediaItem.fromUri(vs.audioUrl))
                    )
                } else {
                    videoSource
                }
                player.setMediaSource(source)
                player.prepare()
                player.playWhenReady = true
            }
            .onFailure { error = it.message ?: "No playable video stream found" }
    }

    LaunchedEffect(track.id) {
        related = null
        comments = null
        details = null
        descExpanded = false
        details = viewModel.fetchVideoDetails(track.id)
        comments = viewModel.fetchComments(track.id).getOrNull()
        related = viewModel.fetchRelated(track.id).getOrNull()
    }

    DisposableEffect(related) {
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED) {
                    val next = related?.firstOrNull() ?: return
                    viewModel.navigateTo(NavDest.Video(next))
                }
            }
        }
        player.addListener(listener)
        onDispose {
            player.removeListener(listener)
        }
    }

    DisposableEffect(Unit) {
        onDispose { player.release() }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 4.dp, vertical = 2.dp)
        ) {
            IconButton(onClick = onClose) {
                Icon(
                    imageVector = Icons.AutoMirrored.Rounded.ArrowBack,
                    contentDescription = "Back",
                    tint = Color.White
                )
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = track.title,
                    color = Color.White,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = track.artist,
                    color = spot.accent,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.clickable {
                        scope.launch {
                            viewModel.resolveChannelId(track.artist)?.let { id ->
                                viewModel.navigateTo(NavDest.Channel(id, track.artist))
                            }
                        }
                    }
                )
            }
            Box {
                var qualityMenu by remember { mutableStateOf(false) }
                TextButton(onClick = { qualityMenu = true }) {
                    Text(
                        text = stream?.qualityLabel ?: "Quality",
                        color = spot.accent,
                        style = MaterialTheme.typography.labelMedium
                    )
                }
                DropdownMenu(
                    expanded = qualityMenu,
                    onDismissRequest = { qualityMenu = false }
                ) {
                    listOf(1080, 720, 480, 360).forEach { q ->
                        DropdownMenuItem(
                            text = { Text("${q}p" + if (q == maxQuality) " ✓" else "") },
                            onClick = {
                                maxQuality = q
                                qualityMenu = false
                            }
                        )
                    }
                }
            }
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f),
            contentAlignment = Alignment.Center
        ) {
            AndroidView(
                factory = { ctx ->
                    PlayerView(ctx).apply {
                        this.player = player
                        useController = true
                        keepScreenOn = true
                    }
                },
                modifier = Modifier.fillMaxSize()
            )
            when {
                error != null -> Text(
                    text = error ?: "",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(24.dp)
                )
                stream == null -> Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    CircularProgressIndicator(color = spot.accent)
                    Text(
                        text = "Finding stream...",
                        color = spot.textDim,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }

        LazyColumn(modifier = Modifier.fillMaxWidth().weight(1f)) {
            val rel = related
            val com = comments
            val det = details
            if (det != null) {
                item {
                    Column(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp)
                    ) {
                        val views = det.viewCount.toLongOrNull()?.let { "%,d".format(it) }
                        val meta = listOfNotNull(
                            views?.let { "$it views" },
                            det.uploadDate.takeIf { d -> d.isNotBlank() }
                        ).joinToString("  ·  ")
                        if (meta.isNotBlank()) {
                            Text(
                                text = meta,
                                color = spot.textDim,
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        if (det.description.isNotBlank()) {
                            Text(
                                text = det.description,
                                color = Color(0xFFE0E0E0),
                                style = MaterialTheme.typography.bodySmall,
                                maxLines = if (descExpanded) Int.MAX_VALUE else 3,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier
                                    .padding(top = 4.dp)
                                    .clickable { descExpanded = !descExpanded }
                            )
                        }
                    }
                }
            }
            if (!com.isNullOrEmpty()) {
                item {
                    Text(
                        text = "Comments",
                        color = Color.White,
                        style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                }
                itemsIndexed(com, key = { idx, _ -> "comment_${'$'}idx" }) { _, c ->
                    CommentRow(c)
                }
            }
            item {
                Text(
                    text = "Up next",
                    color = Color.White,
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                )
            }
            if (rel == null) {
                item {
                    Row(
                        horizontalArrangement = Arrangement.Center,
                        modifier = Modifier.fillMaxWidth().padding(24.dp)
                    ) {
                        CircularProgressIndicator(color = spot.accent)
                    }
                }
            } else {
                itemsIndexed(rel, key = { idx, t -> "rel_${'$'}{t.id}_${'$'}idx" }) { idx, t ->
                    TrackRow(
                        track = t,
                        index = idx,
                        isCurrent = false,
                        isPlaying = false,
                        isLiked = t.id in state.likedIds,
                        isBlocked = t.id in state.blockedIds,
                        reducedMotion = state.prefs.reducedMotion,
                        playCount = state.library.playCounts[t.id]?.count ?: 0,
                        onClick = { viewModel.navigateTo(NavDest.Video(t)) },
                        onLongClick = { viewModel.openModal(ActiveModal.SongMenu(t, "Up next")) },
                        onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                        onToggleLike = { viewModel.toggleLike(t) },
                        onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(t, "Up next")) }
                    )
                }
            }
        }
    }
}


@Composable
private fun CommentRow(comment: YouTubeClient.YtComment) {
    val spot = LocalSpotColors.current
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = comment.author,
                color = Color.White,
                style = MaterialTheme.typography.labelMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false)
            )
            if (comment.timeLabel.isNotBlank()) {
                Text(
                    text = "  " + comment.timeLabel,
                    color = spot.textFaint,
                    style = MaterialTheme.typography.labelSmall,
                    maxLines = 1
                )
            }
        }
        Text(
            text = comment.text,
            color = Color(0xFFE0E0E0),
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(top = 2.dp)
        )
        val meta = buildString {
            if (comment.likes > 0) append(comment.likes).append(" likes")
            if (comment.replyCount > 0) {
                if (isNotEmpty()) append("  ·  ")
                append(comment.replyCount).append(" replies")
            }
        }
        if (meta.isNotEmpty()) {
            Text(
                text = meta,
                color = spot.textFaint,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 2.dp)
            )
        }
    }
}
