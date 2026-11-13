package com.example.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
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
import com.example.data.model.Track
import com.example.data.remote.YouTubeClient
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.SpotUiViewModel

@OptIn(UnstableApi::class)
@Composable
fun VideoScreen(track: Track, viewModel: SpotUiViewModel, onClose: () -> Unit) {
    val spot = LocalSpotColors.current
    val context = LocalContext.current
    var stream by remember { mutableStateOf<YouTubeClient.VideoStream?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    val player = remember { ExoPlayer.Builder(context).build() }

    LaunchedEffect(track.id) {
        error = null
        viewModel.resolveVideoStream(track.id)
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
                    color = spot.textDim,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            stream?.let {
                Text(
                    text = it.qualityLabel,
                    color = spot.accent,
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.padding(horizontal = 12.dp)
                )
            }
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
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
    }
}
