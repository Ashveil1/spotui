package com.example.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.TextButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.data.model.NavDest
import com.example.data.remote.YouTubeClient
import com.example.ui.components.TrackRow
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.ActiveModal
import com.example.ui.viewmodel.SpotUiViewModel

@Composable
fun ChannelScreen(
    channelId: String,
    channelName: String,
    viewModel: SpotUiViewModel,
    onClose: () -> Unit
) {
    val spot = LocalSpotColors.current
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    var info by remember { mutableStateOf<YouTubeClient.YtChannelInfo?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(channelId) {
        info = null
        error = null
        viewModel.fetchChannel(channelId)
            .onSuccess { info = it }
            .onFailure { error = it.message ?: "Could not load channel" }
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
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = info?.name ?: channelName,
                    color = Color.White,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                val subs = info?.subscribers.orEmpty()
                Text(
                    text = subs.ifBlank { "Channel" },
                    color = spot.textDim,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            val followed = state.followedChannels.any { it.id == channelId }
            TextButton(onClick = {
                viewModel.toggleFollowChannel(channelId, info?.name ?: channelName)
            }) {
                Text(
                    text = if (followed) "Following" else "Follow",
                    color = if (followed) spot.textDim else spot.accent,
                    style = MaterialTheme.typography.labelLarge
                )
            }
        }

        val loaded = info
        when {
            error != null -> Text(
                text = error ?: "",
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(24.dp)
            )
            loaded == null -> Row(
                horizontalArrangement = Arrangement.Center,
                modifier = Modifier.fillMaxWidth().padding(48.dp)
            ) {
                CircularProgressIndicator(color = spot.accent)
            }
            else -> LazyColumn(modifier = Modifier.fillMaxWidth().weight(1f)) {
                item {
                    Text(
                        text = "Videos",
                        color = Color.White,
                        style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                }
                itemsIndexed(loaded.videos, key = { idx, t -> "ch_${'$'}{t.id}_${'$'}idx" }) { idx, t ->
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
                        onLongClick = { viewModel.openModal(ActiveModal.SongMenu(t, loaded.name)) },
                        onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                        onToggleLike = { viewModel.toggleLike(t) },
                        onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(t, loaded.name)) }
                    )
                }
            }
        }
    }
}
