package com.example.ui.screens

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.basicMarquee
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.BookmarkAdd
import androidx.compose.material.icons.rounded.ClearAll
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Equalizer
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.KeyboardArrowUp
import androidx.compose.material.icons.rounded.Lyrics
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Radio
import androidx.compose.material.icons.rounded.Repeat
import androidx.compose.material.icons.rounded.RepeatOne
import androidx.compose.material.icons.rounded.Shuffle
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.SkipPrevious
import androidx.compose.material.icons.rounded.VerticalAlignTop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.R
import com.example.data.model.NavDest
import com.example.data.model.RepeatMode
import com.example.data.util.SpotUiTextUtils
import com.example.ui.components.CoverArt
import com.example.ui.components.EqualizerBars
import com.example.ui.components.TrackRow
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.ActiveModal
import com.example.ui.viewmodel.SpotUiState
import com.example.ui.viewmodel.SpotUiViewModel

@Composable
fun QueueScreen(
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val queue = state.queue
    val qpos = state.qpos
    val current = queue.getOrNull(qpos)
    val upcoming = if (qpos >= 0 && qpos + 1 < queue.size) queue.subList(qpos + 1, queue.size) else emptyList()
    val remainingList = if (current != null) listOf(current) + upcoming else upcoming
    val remainingLabel = SpotUiTextUtils.fmtRemaining(remainingList)
    val endsLabel = SpotUiTextUtils.fmtEnds(remainingList, state.playerState.positionSec.toInt())
    val autoCount = upcoming.count { it.isAuto }
    val autoMin = upcoming.filter { it.isAuto }.sumOf { it.durSec ?: 0 } / 60

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("queue_screen"),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = stringResource(R.string.queue_title),
                    style = MaterialTheme.typography.headlineSmall,
                    color = spot.textPrimary,
                    fontWeight = FontWeight.Bold
                )
                val subtitle = buildList {
                    add("${queue.size} song${if (queue.size == 1) "" else "s"}")
                    if (remainingLabel.isNotEmpty()) add(remainingLabel)
                    if (endsLabel.isNotEmpty()) add(endsLabel)
                    if (!state.playSource.isNullOrBlank()) add("From ${state.playSource}")
                }.joinToString(" \u00b7 ")
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = spot.textDim)

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
                    if (upcoming.isNotEmpty()) {
                        OutlinedButton(
                            onClick = { viewModel.clearUpcoming() },
                            modifier = Modifier.testTag("queue_clear_upcoming_btn")
                        ) {
                            Icon(Icons.Rounded.ClearAll, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Clear upcoming")
                        }
                    }
                    if (queue.isNotEmpty()) {
                        OutlinedButton(
                            onClick = { viewModel.saveQueueAsPlaylist() },
                            modifier = Modifier.testTag("queue_save_playlist_btn")
                        ) {
                            Icon(Icons.Rounded.BookmarkAdd, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Save as playlist")
                        }
                    }
                    if (autoCount > 0) {
                        OutlinedButton(
                            onClick = { viewModel.dropAutoplayed() },
                            modifier = Modifier.testTag("queue_drop_auto_btn")
                        ) {
                            Icon(Icons.Rounded.AutoAwesome, null, tint = spot.accent, modifier = Modifier.size(15.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Drop $autoCount auto${if (autoMin > 0) " (${autoMin}m)" else ""}")
                        }
                    }
                }
            }
        }

        if (current != null) {
            item {
                Text(
                    text = stringResource(R.string.now_playing),
                    style = MaterialTheme.typography.labelMedium,
                    color = spot.textDim,
                    fontWeight = FontWeight.Bold
                )
                Spacer(Modifier.height(6.dp))
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, spot.accent.copy(alpha = 0.5f), RoundedCornerShape(12.dp))
                        .clickable { viewModel.navigateTo(NavDest.NowPlaying) }
                        .testTag("queue_now_playing_card")
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CoverArt(
                                seed = current.id,
                                thumbnailUrl = current.thumbnailUrl,
                                modifier = Modifier.size(54.dp),
                                cornerRadius = 8.dp
                            )
                            Spacer(Modifier.width(12.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = current.title,
                                    style = MaterialTheme.typography.titleSmall,
                                    color = spot.accent,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                                Text(
                                    text = current.artist,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = spot.textDim,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                            }
                            EqualizerBars(
                                isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                                reducedMotion = state.prefs.reducedMotion,
                                color = spot.accent,
                                modifier = Modifier.height(18.dp)
                            )
                            IconButton(
                                onClick = { viewModel.openModal(ActiveModal.SongMenu(current, current.source ?: state.playSource, qpos)) },
                                modifier = Modifier.minimumInteractiveComponentSize()
                            ) {
                                Icon(Icons.Rounded.MoreVert, stringResource(R.string.cd_more), tint = spot.textDim)
                            }
                        }
                        val dur = state.playerState.durationSec.takeIf { it > 0 } ?: (current.durSec ?: 0).toDouble()
                        if (dur > 0) {
                            Slider(
                                value = state.playerState.positionSec.toFloat().coerceIn(0f, dur.toFloat()),
                                onValueChange = { viewModel.seekTo(it.toDouble()) },
                                valueRange = 0f..dur.toFloat(),
                                colors = SliderDefaults.colors(
                                    thumbColor = spot.textPrimary,
                                    activeTrackColor = spot.accent,
                                    inactiveTrackColor = spot.divider
                                )
                            )
                        }
                    }
                }
            }
        }

        item {
            Text(
                text = "NEXT UP (${upcoming.size})",
                style = MaterialTheme.typography.labelMedium,
                color = spot.textDim,
                fontWeight = FontWeight.Bold
            )
        }

        if (upcoming.isEmpty()) {
            item {
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(12.dp))
                ) {
                    Text(
                        text = if (current == null) "Queue is empty. Play something from Home or Search."
                        else "Nothing upcoming in the queue.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = spot.textDim,
                        modifier = Modifier.padding(16.dp)
                    )
                }
            }
        } else {
            itemsIndexed(upcoming, key = { offset, t -> "q_${qpos + 1 + offset}_${t.id}" }) { offset, track ->
                val actualIdx = qpos + 1 + offset
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, spot.divider, RoundedCornerShape(10.dp))
                        .clickable { viewModel.jumpToQueueIndex(actualIdx) }
                        .testTag("queue_item_$actualIdx")
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        CoverArt(track.id, track.thumbnailUrl, Modifier.size(42.dp), 6.dp)
                        Spacer(Modifier.width(10.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                if (track.isAuto) {
                                    Icon(Icons.Rounded.AutoAwesome, "Autoplayed", tint = spot.accent, modifier = Modifier.size(13.dp).padding(end = 4.dp))
                                }
                                Text(
                                    text = track.title,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = spot.textPrimary,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                            }
                            Text(
                                text = "${track.artist} \u00b7 ${SpotUiTextUtils.fmtTime(track.durSec)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = spot.textDim,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                        if (offset > 0) {
                            IconButton(
                                onClick = { viewModel.moveQueueItemToNext(actualIdx) },
                                modifier = Modifier.minimumInteractiveComponentSize()
                            ) {
                                Icon(Icons.Rounded.VerticalAlignTop, "Play next", tint = spot.textDim, modifier = Modifier.size(18.dp))
                            }
                            IconButton(
                                onClick = { viewModel.moveQueueItem(actualIdx, -1) },
                                modifier = Modifier.minimumInteractiveComponentSize()
                            ) {
                                Icon(Icons.Rounded.KeyboardArrowUp, "Move up", tint = spot.textDim)
                            }
                        }
                        if (offset < upcoming.lastIndex) {
                            IconButton(
                                onClick = { viewModel.moveQueueItem(actualIdx, +1) },
                                modifier = Modifier.minimumInteractiveComponentSize()
                            ) {
                                Icon(Icons.Rounded.KeyboardArrowDown, "Move down", tint = spot.textDim)
                            }
                        }
                        IconButton(
                            onClick = { viewModel.removeQueueAt(actualIdx) },
                            modifier = Modifier.minimumInteractiveComponentSize()
                        ) {
                            Icon(Icons.Rounded.Close, "Remove from queue", tint = spot.textFaint, modifier = Modifier.size(18.dp))
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class, ExperimentalLayoutApi::class)
@Composable
fun NowPlayingScreen(
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val track = state.currentTrack
    val pState = state.playerState

    if (track == null) {
        Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Nothing playing right now", style = MaterialTheme.typography.titleMedium, color = spot.textPrimary)
                OutlinedButton(onClick = { viewModel.navigateTo(NavDest.Search) }) {
                    Text("Search music")
                }
            }
        }
        return
    }

    val dur = pState.durationSec.takeIf { it > 0 } ?: (track.durSec ?: 0).toDouble()
    var draggingPos by remember(track.id) { mutableFloatStateOf(0f) }
    var isDragging by remember(track.id) { mutableStateOf(false) }
    val pos = if (isDragging) draggingPos.toDouble() else pState.positionSec
    val plays = state.library.playCounts[track.id]?.count ?: 0
    val lyricsData = state.library.lyricsCache[track.id]
    val moreFromArtist = remember(track.id, state.library) {
        viewModel.artistLibraryTracks(track.artist).filter { it.id != track.id }.take(6)
    }
    val upNext = remember(state.queue, state.qpos) {
        if (state.qpos >= 0 && state.qpos + 1 < state.queue.size) {
            state.queue.subList(state.qpos + 1, state.queue.size).take(3)
        } else emptyList()
    }

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("now_playing_screen"),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Column(
                modifier = Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Box(
                    modifier = Modifier
                        .widthIn(max = 320.dp)
                        .fillMaxWidth(0.86f)
                        .aspectRatio(1f)
                        .combinedClickable(
                            onClick = { viewModel.togglePlayPause() },
                            onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, state.playSource, state.qpos)) }
                        )
                        .testTag("np_cover_art")
                ) {
                    CoverArt(
                        seed = track.id,
                        thumbnailUrl = track.thumbnailUrl,
                        modifier = Modifier.fillMaxSize(),
                        cornerRadius = 16.dp
                    )
                }

                Spacer(Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = track.title,
                            style = MaterialTheme.typography.headlineSmall,
                            color = spot.textPrimary,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1,
                            modifier = Modifier.basicMarquee()
                        )
                        Spacer(Modifier.height(2.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = track.artist,
                                style = MaterialTheme.typography.bodyMedium,
                                color = spot.accent,
                                modifier = Modifier.clickable { viewModel.navigateTo(NavDest.Artist(track.artist)) }
                            )
                            val src = track.source ?: state.playSource
                            if (!src.isNullOrBlank()) {
                                Text(
                                    text = " \u00b7 From $src",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = spot.textDim,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    modifier = Modifier.clickable { viewModel.openSourcePage(src) }
                                )
                            }
                        }
                        if (plays > 0) {
                            Text(
                                text = "Played $plays time${if (plays == 1) "" else "s"}",
                                style = MaterialTheme.typography.labelSmall,
                                color = spot.textFaint
                            )
                        }
                    }

                    IconButton(
                        onClick = { viewModel.toggleLike(track) },
                        modifier = Modifier.minimumInteractiveComponentSize().testTag("np_like_btn")
                    ) {
                        Icon(
                            imageVector = if (track.id in state.likedIds) Icons.Rounded.Favorite else Icons.Outlined.FavoriteBorder,
                            contentDescription = stringResource(R.string.cd_like),
                            tint = if (track.id in state.likedIds) spot.accent else spot.textDim
                        )
                    }
                    IconButton(
                        onClick = { viewModel.openModal(ActiveModal.SongMenu(track, state.playSource, state.qpos)) },
                        modifier = Modifier.minimumInteractiveComponentSize().testTag("np_more_btn")
                    ) {
                        Icon(Icons.Rounded.MoreVert, stringResource(R.string.cd_more), tint = spot.textPrimary)
                    }
                }
            }
        }

        // Seekbar + Quick Jumps
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Slider(
                    value = if (dur > 0) pos.toFloat().coerceIn(0f, dur.toFloat()) else 0f,
                    onValueChange = {
                        isDragging = true
                        draggingPos = it
                    },
                    onValueChangeFinished = {
                        isDragging = false
                        viewModel.seekTo(draggingPos.toDouble())
                    },
                    valueRange = 0f..(dur.toFloat().coerceAtLeast(1f)),
                    enabled = dur > 0,
                    colors = SliderDefaults.colors(
                        thumbColor = spot.textPrimary,
                        activeTrackColor = spot.accent,
                        inactiveTrackColor = spot.divider
                    ),
                    modifier = Modifier.fillMaxWidth().testTag("np_seek_slider")
                )
                Row(modifier = Modifier.fillMaxWidth()) {
                    Text(SpotUiTextUtils.fmtTimeDouble(pos), style = MaterialTheme.typography.labelSmall, color = spot.textDim)
                    Spacer(Modifier.weight(1f))
                    val rightText = if (state.prefs.timeLeft && dur > 0) {
                        "-" + SpotUiTextUtils.fmtTimeDouble((dur - pos).coerceAtLeast(0.0))
                    } else SpotUiTextUtils.fmtTimeDouble(dur.takeIf { it > 0 })
                    Text(
                        text = rightText,
                        style = MaterialTheme.typography.labelSmall,
                        color = spot.textDim,
                        modifier = Modifier.clickable { viewModel.toggleTimeLeft() }
                    )
                }

                // Transport buttons
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(
                        onClick = { viewModel.toggleShuffle() },
                        modifier = Modifier.minimumInteractiveComponentSize().testTag("np_shuffle_btn")
                    ) {
                        Icon(
                            Icons.Rounded.Shuffle,
                            stringResource(R.string.cd_shuffle),
                            tint = if (state.shuffle) spot.accent else spot.textDim
                        )
                    }
                    IconButton(
                        onClick = { viewModel.prev() },
                        modifier = Modifier.minimumInteractiveComponentSize().testTag("np_prev_btn")
                    ) {
                        Icon(Icons.Rounded.SkipPrevious, stringResource(R.string.cd_prev), tint = spot.textPrimary, modifier = Modifier.size(34.dp))
                    }
                    Surface(
                        shape = CircleShape,
                        color = spot.accent,
                        modifier = Modifier
                            .size(64.dp)
                            .clickable { viewModel.togglePlayPause() }
                            .testTag("np_play_pause_btn")
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            when {
                                pState.isLoading -> CircularProgressIndicator(color = spot.onAccent, modifier = Modifier.size(28.dp), strokeWidth = 3.dp)
                                pState.isPaused || pState.isIdle -> Icon(Icons.Rounded.PlayArrow, stringResource(R.string.cd_play), tint = spot.onAccent, modifier = Modifier.size(34.dp))
                                else -> Icon(Icons.Rounded.Pause, stringResource(R.string.cd_pause), tint = spot.onAccent, modifier = Modifier.size(34.dp))
                            }
                        }
                    }
                    IconButton(
                        onClick = { viewModel.next() },
                        modifier = Modifier.minimumInteractiveComponentSize().testTag("np_next_btn")
                    ) {
                        Icon(Icons.Rounded.SkipNext, stringResource(R.string.cd_next), tint = spot.textPrimary, modifier = Modifier.size(34.dp))
                    }
                    IconButton(
                        onClick = { viewModel.cycleRepeat() },
                        modifier = Modifier.minimumInteractiveComponentSize().testTag("np_repeat_btn")
                    ) {
                        Icon(
                            if (state.repeat == RepeatMode.ONE) Icons.Rounded.RepeatOne else Icons.Rounded.Repeat,
                            stringResource(R.string.cd_repeat),
                            tint = if (state.repeat != RepeatMode.OFF) spot.accent else spot.textDim
                        )
                    }
                }

                // Quick seek % chips
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    listOf(0, 25, 50, 75, 90).forEach { pct ->
                        TextButton(
                            onClick = { viewModel.seekPercent(pct) },
                            modifier = Modifier.testTag("np_jump_${pct}")
                        ) {
                            Text("$pct%", color = spot.textDim, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
        }

        // State Chips (Speed, EQ, Shuffle mode, Autoplay, Sleep Timer, Lyrics, Radio)
        item {
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatePill(
                    label = "Lyrics" + if (lyricsData?.hasSynced == true) " (synced)" else "",
                    active = lyricsData?.hasAny == true,
                    onClick = { viewModel.openModal(ActiveModal.LyricsSheet(track)) },
                    tag = "np_chip_lyrics"
                )
                StatePill(
                    label = "Speed ${pState.speed.toString().removeSuffix(".0")}x",
                    active = kotlin.math.abs(pState.speed - 1.0f) > 0.01f,
                    onClick = { viewModel.changeSpeed(if (pState.speed >= 2.0f) -4 else 1) },
                    tag = "np_chip_speed"
                )
                StatePill(
                    label = "EQ: ${pState.eqPreset.label}",
                    active = pState.eqPreset != com.example.data.model.EqPreset.OFF,
                    onClick = { viewModel.cycleEq() },
                    tag = "np_chip_eq"
                )
                StatePill(
                    label = "Shuffle: ${state.prefs.shuffleMode.label.substringBefore(" (")}",
                    active = state.shuffle,
                    onClick = { viewModel.cycleShuffleMode() },
                    tag = "np_chip_shuffle_mode"
                )
                StatePill(
                    label = if (state.prefs.autoplay) "Autoplay on" else "Autoplay off",
                    active = state.prefs.autoplay,
                    onClick = { viewModel.toggleAutoplay() },
                    tag = "np_chip_autoplay"
                )
                StatePill(
                    label = when {
                        state.sleepEot -> "Sleep: EOT"
                        state.sleepRemainingSec != null -> "Sleep ${SpotUiTextUtils.fmtTime(state.sleepRemainingSec)}"
                        else -> "Sleep timer"
                    },
                    active = state.sleepEot || state.sleepRemainingSec != null,
                    onClick = { viewModel.openModal(ActiveModal.SleepTimerSheet) },
                    tag = "np_chip_sleep"
                )
                StatePill(
                    label = "Start radio",
                    active = false,
                    onClick = { viewModel.startRadio(track) },
                    tag = "np_chip_radio"
                )
            }
        }

        // Animated EQ note
        item {
            Surface(
                color = spot.hover,
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(10.dp))
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    EqualizerBars(
                        isPlaying = !pState.isPaused && !pState.isIdle && !pState.isLoading,
                        reducedMotion = state.prefs.reducedMotion,
                        barCount = 6,
                        color = spot.accent,
                        modifier = Modifier.height(18.dp)
                    )
                    Spacer(Modifier.width(12.dp))
                    Text(
                        text = "Visual animation (ambient rhythm, not live audio spectrum)",
                        style = MaterialTheme.typography.labelSmall,
                        color = spot.textFaint
                    )
                }
            }
        }

        // Up Next 3 preview
        if (upNext.isNotEmpty()) {
            item {
                Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("UP NEXT", style = MaterialTheme.typography.labelMedium, color = spot.textDim, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    TextButton(onClick = { viewModel.navigateTo(NavDest.Queue) }) {
                        Text("Open Queue", color = spot.accent)
                    }
                }
            }
            itemsIndexed(upNext, key = { idx, t -> "np_next_${idx}_${t.id}" }) { offset, t ->
                val actualIdx = state.qpos + 1 + offset
                TrackRow(
                    track = t,
                    index = offset,
                    isCurrent = false,
                    isPlaying = false,
                    isLiked = t.id in state.likedIds,
                    isBlocked = t.id in state.blockedIds,
                    reducedMotion = state.prefs.reducedMotion,
                    onClick = { viewModel.jumpToQueueIndex(actualIdx) },
                    onLongClick = { viewModel.openModal(ActiveModal.SongMenu(t, state.playSource, actualIdx)) },
                    onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                    onToggleLike = { viewModel.toggleLike(t) },
                    onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(t, state.playSource, actualIdx)) }
                )
            }
        }

        // More from artist
        if (moreFromArtist.isNotEmpty()) {
            item {
                Text(
                    text = "MORE FROM ${track.artist.uppercase()}",
                    style = MaterialTheme.typography.labelMedium,
                    color = spot.textDim,
                    fontWeight = FontWeight.Bold
                )
            }
            itemsIndexed(moreFromArtist, key = { idx, t -> "np_art_${idx}_${t.id}" }) { idx, t ->
                TrackRow(
                    track = t,
                    index = idx,
                    isCurrent = state.currentTrack.id == t.id,
                    isPlaying = !pState.isPaused && !pState.isIdle,
                    isLiked = t.id in state.likedIds,
                    isBlocked = t.id in state.blockedIds,
                    reducedMotion = state.prefs.reducedMotion,
                    onClick = { viewModel.play(moreFromArtist, idx, track.artist) },
                    onLongClick = { viewModel.openModal(ActiveModal.SongMenu(t, track.artist)) },
                    onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                    onToggleLike = { viewModel.toggleLike(t) },
                    onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(t, track.artist)) }
                )
            }
        }
    }
}

@Composable
private fun StatePill(
    label: String,
    active: Boolean,
    onClick: () -> Unit,
    tag: String
) {
    val spot = LocalSpotColors.current
    Surface(
        color = if (active) spot.accent.copy(alpha = 0.16f) else spot.hover,
        shape = RoundedCornerShape(20.dp),
        modifier = Modifier
            .border(1.dp, if (active) spot.accent else spot.divider, RoundedCornerShape(20.dp))
            .clickable(onClick = onClick)
            .testTag(tag)
    ) {
        Text(
            text = label,
            color = if (active) spot.accent else spot.textPrimary,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
        )
    }
}
