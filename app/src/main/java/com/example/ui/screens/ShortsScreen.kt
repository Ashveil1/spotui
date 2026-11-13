package com.example.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.pager.VerticalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.MergingMediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import com.example.data.model.NavDest
import com.example.data.model.Track
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.SpotUiViewModel

@androidx.annotation.OptIn(UnstableApi::class)
@Composable
fun ShortsScreen(viewModel: SpotUiViewModel, onClose: () -> Unit) {
    val spot = LocalSpotColors.current
    val context = androidx.compose.ui.platform.LocalContext.current
    var shorts by remember { mutableStateOf<List<Track>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    val player = remember { ExoPlayer.Builder(context).build() }
    var playingId by remember { mutableStateOf<String?>(null) }
    var pageError by remember { mutableStateOf<String?>(null) }

    DisposableEffect(Unit) {
        onDispose { player.release() }
    }

    LaunchedEffect(Unit) {
        viewModel.fetchShorts()
            .onSuccess { shorts = it }
            .onFailure { error = it.message ?: "Could not load shorts" }
    }

    Column(modifier = Modifier.fillMaxSize()) {
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
            Text(
                text = "Shorts",
                color = Color.White,
                style = MaterialTheme.typography.titleMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }

        val list = shorts
        when {
            error != null -> Text(
                text = error ?: "",
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(24.dp)
            )
            list == null -> Row(
                horizontalArrangement = Arrangement.Center,
                modifier = Modifier.fillMaxWidth().padding(48.dp)
            ) {
                CircularProgressIndicator(color = spot.accent)
            }
            list.isEmpty() -> Text(
                text = "No shorts found",
                color = spot.textDim,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(24.dp)
            )
            else -> {
                val pagerState = rememberPagerState(pageCount = { list.size })

                LaunchedEffect(pagerState.settledPage, list) {
                    val t = list.getOrNull(pagerState.settledPage) ?: return@LaunchedEffect
                    player.stop()
                    playingId = null
                    pageError = null
                    viewModel.resolveVideoStream(t.id, 720)
                        .onSuccess { vs ->
                            if (list.getOrNull(pagerState.settledPage)?.id != t.id) return@onSuccess
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
                            playingId = t.id
                            player.setMediaSource(source)
                            player.prepare()
                            player.playWhenReady = true
                        }
                        .onFailure { pageError = it.message }
                }

                VerticalPager(
                    state = pagerState,
                    modifier = Modifier.fillMaxSize()
                ) { page ->
                    val track = list[page]
                    val isActive = track.id == playingId
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .clickable {
                                if (isActive) {
                                    player.playWhenReady = !player.isPlaying
                                }
                            }
                    ) {
                        if (isActive) {
                            AndroidView(
                                factory = { ctx ->
                                    PlayerView(ctx).apply {
                                        this.player = player
                                        useController = false
                                        keepScreenOn = true
                                    }
                                },
                                modifier = Modifier.fillMaxSize()
                            )
                        } else {
                            AsyncImage(
                                model = track.thumbnailUrl,
                                contentDescription = track.title,
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxSize()
                            )
                            if (page == pagerState.settledPage) {
                                if (pageError != null) {
                                    Text(
                                        text = pageError ?: "",
                                        color = MaterialTheme.colorScheme.error,
                                        style = MaterialTheme.typography.bodySmall,
                                        modifier = Modifier
                                            .align(Alignment.Center)
                                            .padding(24.dp)
                                    )
                                } else {
                                    CircularProgressIndicator(
                                        color = spot.accent,
                                        modifier = Modifier
                                            .align(Alignment.Center)
                                            .size(36.dp)
                                    )
                                }
                            }
                        }
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .align(Alignment.BottomCenter)
                                .background(
                                    Brush.verticalGradient(
                                        listOf(Color.Transparent, Color(0xCC000000))
                                    )
                                )
                                .padding(16.dp)
                        ) {
                            Column {
                                Text(
                                    text = track.title,
                                    color = Color.White,
                                    style = MaterialTheme.typography.titleSmall,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis
                                )
                                Text(
                                    text = if (isActive) "Tap to pause - comments and up next in the player" else "Swipe for more",
                                    color = spot.textDim,
                                    style = MaterialTheme.typography.bodySmall,
                                    modifier = Modifier
                                        .padding(top = 4.dp)
                                        .clickable {
                                            player.pause()
                                            viewModel.navigateTo(NavDest.Video(track))
                                        }
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
