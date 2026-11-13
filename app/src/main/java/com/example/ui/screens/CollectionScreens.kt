package com.example.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Undo
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.BarChart
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.DeleteOutline
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.FilterList
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.PushPin
import androidx.compose.material.icons.rounded.QueueMusic
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Repeat
import androidx.compose.material.icons.rounded.RepeatOne
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Shuffle
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.R
import com.example.data.model.NavDest
import com.example.data.model.Playlist
import com.example.data.model.RepeatMode
import com.example.data.model.SortMode
import com.example.data.model.Track
import com.example.data.util.SpotUiTextUtils
import com.example.ui.components.CoverArt
import com.example.ui.components.PlaylistMosaicArt
import com.example.ui.components.TrackRow
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.ActiveModal
import com.example.ui.viewmodel.SpotUiState
import com.example.ui.viewmodel.SpotUiViewModel

@Composable
fun LibraryScreen(
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val playlists = state.library.playlists

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("library_screen"),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = stringResource(R.string.your_library),
                    style = MaterialTheme.typography.headlineSmall,
                    color = spot.textPrimary,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                Button(
                    onClick = { viewModel.openModal(ActiveModal.CreateOrImportPlaylist()) },
                    colors = ButtonDefaults.buttonColors(containerColor = spot.accent, contentColor = spot.onAccent),
                    modifier = Modifier.testTag("lib_create_playlist_btn")
                ) {
                    Icon(Icons.Rounded.Add, null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("New playlist")
                }
            }
        }

        if (state.hasUndo) {
            item {
                UndoBanner(onUndo = { viewModel.undoDelete() })
            }
        }

        item {
            LibraryCollectionCard(
                title = stringResource(R.string.liked_songs),
                subtitle = SpotUiTextUtils.fmtTotal(state.library.liked),
                icon = Icons.Rounded.Favorite,
                iconTint = spot.accent,
                onClick = { viewModel.navigateTo(NavDest.Liked) },
                onPlay = if (state.library.liked.isNotEmpty()) { { viewModel.play(state.library.liked, 0, "Liked Songs") } } else null,
                tag = "lib_card_liked"
            )
        }

        item {
            LibraryCollectionCard(
                title = stringResource(R.string.recently_played),
                subtitle = "${state.library.history.size} recent songs",
                icon = Icons.Rounded.History,
                iconTint = spot.textPrimary,
                onClick = { viewModel.navigateTo(NavDest.History) },
                onPlay = if (state.library.history.isNotEmpty()) { { viewModel.play(state.library.history, 0, "Recently Played") } } else null,
                tag = "lib_card_history"
            )
        }

        item {
            LibraryCollectionCard(
                title = stringResource(R.string.stats_title),
                subtitle = "${state.stats.totalPlays} plays \u00b7 ${state.stats.uniqueSongs} songs",
                icon = Icons.Rounded.BarChart,
                iconTint = spot.accent,
                onClick = { viewModel.navigateTo(NavDest.Stats) },
                onPlay = null,
                tag = "lib_card_stats"
            )
        }

        item {
            Spacer(Modifier.height(6.dp))
            Text(
                text = "Playlists (${playlists.size})",
                style = MaterialTheme.typography.titleMedium,
                color = spot.textPrimary,
                fontWeight = FontWeight.Bold
            )
        }

        if (playlists.isEmpty()) {
            item {
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(12.dp))
                ) {
                    Text(
                        text = "No playlists yet. Tap New playlist to create one or paste a YouTube playlist URL.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = spot.textDim,
                        modifier = Modifier.padding(16.dp)
                    )
                }
            }
        } else {
            items(playlists, key = { it.id }) { pl ->
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, spot.divider, RoundedCornerShape(12.dp))
                        .clickable { viewModel.navigateTo(NavDest.PlaylistDest(pl.id)) }
                        .testTag("lib_playlist_${pl.id}")
                ) {
                    Row(
                        modifier = Modifier.padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        PlaylistMosaicArt(
                            playlist = pl,
                            modifier = Modifier.size(52.dp),
                            cornerRadius = 8.dp
                        )
                        Spacer(Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                if (pl.pinned) {
                                    Icon(Icons.Rounded.PushPin, "Pinned", tint = spot.accent, modifier = Modifier.size(14.dp).padding(end = 4.dp))
                                }
                                if (pl.enhanced) {
                                    Icon(Icons.Rounded.AutoAwesome, "Enhanced", tint = spot.accent, modifier = Modifier.size(14.dp).padding(end = 4.dp))
                                }
                                Text(
                                    text = pl.name,
                                    style = MaterialTheme.typography.titleSmall,
                                    color = spot.textPrimary,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                            }
                            Text(
                                text = SpotUiTextUtils.fmtTotal(pl.tracks),
                                style = MaterialTheme.typography.bodySmall,
                                color = spot.textDim,
                                maxLines = 1
                            )
                        }
                        if (pl.tracks.isNotEmpty()) {
                            IconButton(
                                onClick = { viewModel.play(pl.tracks, 0, pl.name) },
                                modifier = Modifier.minimumInteractiveComponentSize()
                            ) {
                                Icon(Icons.Rounded.PlayArrow, stringResource(R.string.cd_play), tint = spot.accent)
                            }
                        }
                        IconButton(
                            onClick = { viewModel.openModal(ActiveModal.CollectionMenu("playlist", pl)) },
                            modifier = Modifier.minimumInteractiveComponentSize()
                        ) {
                            Icon(Icons.Rounded.MoreVert, stringResource(R.string.cd_more), tint = spot.textDim)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun LibraryCollectionCard(
    title: String,
    subtitle: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    iconTint: Color,
    onClick: () -> Unit,
    onPlay: (() -> Unit)?,
    tag: String
) {
    val spot = LocalSpotColors.current
    Surface(
        color = spot.hover,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, spot.divider, RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .testTag(tag)
    ) {
        Row(
            modifier = Modifier.padding(10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier.size(52.dp).clip(RoundedCornerShape(8.dp)).background(spot.raised),
                contentAlignment = Alignment.Center
            ) {
                Icon(icon, null, tint = iconTint, modifier = Modifier.size(26.dp))
            }
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleSmall, color = spot.textPrimary)
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = spot.textDim)
            }
            if (onPlay != null) {
                IconButton(
                    onClick = onPlay,
                    modifier = Modifier.minimumInteractiveComponentSize()
                ) {
                    Icon(Icons.Rounded.PlayArrow, stringResource(R.string.cd_play), tint = spot.accent)
                }
            }
        }
    }
}

@Composable
fun CollectionScreen(
    kind: String,
    playlist: Playlist?,
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val rawTracks: List<Track> = when (kind) {
        "liked" -> state.library.liked
        "history" -> {
            if (state.prefs.histDedupe) {
                val seen = mutableSetOf<String>()
                state.library.history.filter { seen.add(it.id) }
            } else state.library.history
        }
        else -> playlist?.tracks ?: emptyList()
    }
    val title = when (kind) {
        "liked" -> stringResource(R.string.liked_songs)
        "history" -> stringResource(R.string.recently_played)
        else -> playlist?.name ?: "Playlist"
    }
    val sourceName = when (kind) {
        "liked" -> "Liked Songs"
        "history" -> "Recently Played"
        else -> playlist?.name ?: "Playlist"
    }

    val sorted = remember(rawTracks, state.prefs.sortMode, state.library.playCounts, kind) {
        if (kind == "history" && state.prefs.sortMode == SortMode.DEFAULT) rawTracks
        else SpotUiTextUtils.sortTracks(rawTracks, state.prefs.sortMode, state.library.playCounts)
    }

    val displayed = remember(sorted, state.findQuery) {
        val fq = state.findQuery.trim().lowercase()
        if (fq.isEmpty()) sorted
        else sorted.filter { fq in it.title.lowercase() || fq in it.artist.lowercase() }
    }

    val totalPlays = remember(rawTracks, state.library.playCounts) {
        rawTracks.map { it.id }.toSet().sumOf { state.library.playCounts[it]?.count ?: 0 }
    }
    val monthPrefix = remember { SpotUiTextUtils.currentYearMonth() }
    val newThisMonth = remember(rawTracks, monthPrefix) {
        rawTracks.count { it.addedDate?.startsWith(monthPrefix) == true }
    }

    val shades = remember(title, rawTracks.firstOrNull()?.id) {
        SpotUiTextUtils.coverShades(rawTracks.firstOrNull()?.id ?: title)
    }
    val canReorder = kind == "playlist" &&
        playlist != null &&
        state.prefs.sortMode == SortMode.DEFAULT &&
        state.findQuery.isBlank()

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("collection_screen_$kind"),
        contentPadding = PaddingValues(bottom = 24.dp)
    ) {
        // Gradient Header
        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(
                        Brush.verticalGradient(
                            colors = listOf(shades[1].copy(alpha = 0.72f), spot.background)
                        )
                    )
                    .padding(horizontal = 16.dp, vertical = 18.dp)
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (playlist != null) {
                            PlaylistMosaicArt(
                                playlist = playlist,
                                modifier = Modifier.size(86.dp),
                                cornerRadius = 10.dp
                            )
                        } else {
                            Box(
                                modifier = Modifier
                                    .size(86.dp)
                                    .clip(RoundedCornerShape(10.dp))
                                    .background(
                                        Brush.linearGradient(listOf(shades[0], shades[2]))
                                    ),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(
                                    imageVector = if (kind == "liked") Icons.Rounded.Favorite else Icons.Rounded.History,
                                    contentDescription = null,
                                    tint = Color.White,
                                    modifier = Modifier.size(38.dp)
                                )
                            }
                        }
                        Spacer(Modifier.width(16.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = when (kind) {
                                    "liked" -> "COLLECTION"
                                    "history" -> "HISTORY"
                                    else -> if (playlist?.pinned == true) "PINNED PLAYLIST" else "PLAYLIST"
                                },
                                style = MaterialTheme.typography.labelSmall,
                                color = spot.textDim,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = title,
                                style = MaterialTheme.typography.headlineSmall,
                                color = spot.textPrimary,
                                fontWeight = FontWeight.Bold,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis
                            )
                            val subParts = buildList {
                                add(SpotUiTextUtils.fmtTotal(rawTracks))
                                if (totalPlays > 0) add("$totalPlays plays")
                                if (newThisMonth > 0 && kind != "history") add("$newThisMonth new this month")
                                if (playlist?.enhanced == true) add("Enhanced")
                                if (kind == "history" && state.prefs.histDedupe) add("repeats hidden")
                            }
                            Text(
                                text = subParts.joinToString(" \u00b7 "),
                                style = MaterialTheme.typography.bodySmall,
                                color = spot.textDim
                            )
                        }
                    }

                    // Controls Row
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Button(
                            onClick = {
                                if (displayed.isEmpty()) viewModel.toastNow("No songs to play")
                                else viewModel.play(displayed, 0, sourceName)
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = spot.accent, contentColor = spot.onAccent),
                            modifier = Modifier.testTag("collection_play_btn")
                        ) {
                            Icon(Icons.Rounded.PlayArrow, null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Play")
                        }
                        OutlinedButton(
                            onClick = {
                                if (displayed.isEmpty()) viewModel.toastNow("No songs to shuffle")
                                else {
                                    val shuf = SpotUiTextUtils.smartShuffle(
                                        displayed,
                                        mode = state.prefs.shuffleMode,
                                        plays = state.library.playCounts
                                    )
                                    viewModel.play(shuf, 0, sourceName)
                                }
                            },
                            modifier = Modifier.testTag("collection_shuffle_btn")
                        ) {
                            Icon(Icons.Rounded.Shuffle, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Shuffle")
                        }
                        IconButton(
                            onClick = { viewModel.cycleRepeat() },
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("collection_repeat_btn")
                        ) {
                            Icon(
                                imageVector = if (state.repeat == RepeatMode.ONE) Icons.Rounded.RepeatOne else Icons.Rounded.Repeat,
                                contentDescription = stringResource(R.string.cd_repeat),
                                tint = if (state.repeat != RepeatMode.OFF) spot.accent else spot.textDim
                            )
                        }
                        IconButton(
                            onClick = { viewModel.setFindActive(!state.findActive) },
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("collection_find_btn")
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.Search,
                                contentDescription = "Filter songs in list",
                                tint = if (state.findActive) spot.accent else spot.textDim
                            )
                        }
                        IconButton(
                            onClick = { viewModel.openModal(ActiveModal.CollectionMenu(kind, playlist)) },
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("collection_more_btn")
                        ) {
                            Icon(Icons.Rounded.MoreVert, stringResource(R.string.cd_more), tint = spot.textPrimary)
                        }
                    }

                    // Sort Chips
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        items(SortMode.entries) { mode ->
                            FilterChip(
                                selected = state.prefs.sortMode == mode,
                                onClick = { viewModel.setSortMode(mode) },
                                label = { Text(mode.label) },
                                colors = FilterChipDefaults.filterChipColors(
                                    selectedContainerColor = spot.accent,
                                    selectedLabelColor = spot.onAccent,
                                    containerColor = spot.hover,
                                    labelColor = spot.textPrimary
                                ),
                                modifier = Modifier.testTag("sort_chip_${mode.key}")
                            )
                        }
                    }

                    // History Specific Controls
                    if (kind == "history") {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            FilterChip(
                                selected = state.prefs.histDedupe,
                                onClick = { viewModel.toggleHistDedupe() },
                                label = { Text("Hide repeats") },
                                leadingIcon = { Icon(Icons.Rounded.FilterList, null, modifier = Modifier.size(16.dp)) },
                                colors = FilterChipDefaults.filterChipColors(
                                    selectedContainerColor = spot.accent,
                                    selectedLabelColor = spot.onAccent,
                                    containerColor = spot.hover,
                                    labelColor = spot.textPrimary
                                ),
                                modifier = Modifier.testTag("history_dedupe_chip")
                            )
                            if (state.library.history.isNotEmpty()) {
                                OutlinedButton(
                                    onClick = { viewModel.openModal(ActiveModal.ConfirmClearHistory) },
                                    modifier = Modifier.testTag("history_clear_btn")
                                ) {
                                    Icon(Icons.Rounded.DeleteOutline, null, modifier = Modifier.size(16.dp))
                                    Spacer(Modifier.width(4.dp))
                                    Text("Clear history")
                                }
                            }
                        }
                    }

                    // Inline Find Input
                    if (state.findActive) {
                        OutlinedTextField(
                            value = state.findQuery,
                            onValueChange = { viewModel.onFindQueryChange(it) },
                            placeholder = { Text("Find in $title...", color = spot.textFaint) },
                            singleLine = true,
                            leadingIcon = { Icon(Icons.Rounded.Search, null, tint = spot.textDim) },
                            trailingIcon = {
                                IconButton(
                                    onClick = { viewModel.setFindActive(false) },
                                    modifier = Modifier.minimumInteractiveComponentSize()
                                ) {
                                    Icon(Icons.Rounded.Close, "Close find", tint = spot.textDim)
                                }
                            },
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = spot.accent,
                                unfocusedBorderColor = spot.divider,
                                focusedTextColor = spot.textPrimary,
                                unfocusedTextColor = spot.textPrimary,
                                focusedContainerColor = spot.hover,
                                unfocusedContainerColor = spot.hover
                            ),
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.fillMaxWidth().testTag("collection_find_input")
                        )
                    }
                }
            }
        }

        if (state.hasUndo) {
            item {
                Box(modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                    UndoBanner(onUndo = { viewModel.undoDelete() })
                }
            }
        }

        if (displayed.isEmpty()) {
            item {
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 12.dp)
                        .border(1.dp, spot.divider, RoundedCornerShape(12.dp))
                ) {
                    Text(
                        text = if (state.findQuery.isNotBlank()) "No songs match \"${state.findQuery}\"."
                        else when (kind) {
                            "liked" -> "No liked songs yet. Tap the heart on any song."
                            "history" -> "No listening history yet. Play something to start tracking."
                            else -> "This playlist has no songs yet. Search for tracks and add them from the song menu."
                        },
                        style = MaterialTheme.typography.bodyMedium,
                        color = spot.textDim,
                        modifier = Modifier.padding(18.dp)
                    )
                }
            }
        } else {
            itemsIndexed(displayed, key = { idx, t -> "${t.id}_$idx" }) { idx, track ->
                val dateLabel = if (kind == "history") {
                    SpotUiTextUtils.fmtAgo(track.playedAtSec)
                } else {
                    SpotUiTextUtils.fmtAdded(track.addedDate, track.playedAtSec)
                }
                val ctx = if (canReorder && playlist != null) playlist to idx else null
                Box(modifier = Modifier.padding(horizontal = 8.dp)) {
                    TrackRow(
                        track = track,
                        index = idx,
                        isCurrent = state.currentTrack?.id == track.id,
                        isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                        isLiked = track.id in state.likedIds,
                        isBlocked = track.id in state.blockedIds,
                        reducedMotion = state.prefs.reducedMotion,
                        findQuery = state.findQuery,
                        playCount = state.library.playCounts[track.id]?.count ?: 0,
                        dateOrAgoLabel = dateLabel,
                        canReorder = canReorder,
                        onMoveUp = if (canReorder && idx > 0 && playlist != null) {
                            { viewModel.moveTrackInPlaylist(playlist, idx, -1) }
                        } else null,
                        onMoveDown = if (canReorder && idx < displayed.lastIndex && playlist != null) {
                            { viewModel.moveTrackInPlaylist(playlist, idx, +1) }
                        } else null,
                        onClick = { viewModel.play(displayed, idx, sourceName) },
                        onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, sourceName, playlistContext = ctx)) },
                        onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                        onToggleLike = { viewModel.toggleLike(track) },
                        onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(track, sourceName, playlistContext = ctx)) }
                    )
                }
            }
        }
    }
}

@Composable
private fun UndoBanner(onUndo: () -> Unit) {
    val spot = LocalSpotColors.current
    Surface(
        color = spot.raised,
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.fillMaxWidth().border(1.dp, spot.accent.copy(alpha = 0.5f), RoundedCornerShape(10.dp))
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Item removed", style = MaterialTheme.typography.bodySmall, color = spot.textPrimary, modifier = Modifier.weight(1f))
            TextButton(onClick = onUndo, modifier = Modifier.testTag("undo_delete_btn")) {
                Icon(Icons.AutoMirrored.Rounded.Undo, null, tint = spot.accent, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("Undo", color = spot.accent)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ArtistScreen(
    artistName: String,
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val libTracks = remember(artistName, state.library, state.queue) {
        viewModel.artistLibraryTracks(artistName)
    }
    val tracks = if (libTracks.isNotEmpty()) libTracks else (state.artistRemoteTracks[artistName] ?: emptyList())
    val isBusy = artistName in state.artistBusy
    val plays = remember(artistName, state.library.playCounts) { viewModel.artistPlays(artistName) }
    val minsText = remember(artistName, state.library) { viewModel.artistMinutesText(artistName) }
    val shades = remember(artistName) { SpotUiTextUtils.coverShades(artistName) }

    val popular = remember(tracks, state.library.playCounts) {
        tracks.sortedByDescending { state.library.playCounts[it.id]?.count ?: 0 }
            .filter { (state.library.playCounts[it.id]?.count ?: 0) > 0 }
            .take(5)
    }

    val otherArtists = remember(artistName, state.library.playCounts) {
        val normSelf = SpotUiTextUtils.normArtist(artistName)
        state.library.playCounts.values
            .groupBy { it.artist }
            .mapValues { (_, list) -> list.sumOf { it.count } }
            .entries
            .filter { SpotUiTextUtils.normArtist(it.key) != normSelf && it.key.isNotBlank() }
            .sortedByDescending { it.value }
            .take(6)
            .map { it.key }
    }

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("artist_screen"),
        contentPadding = PaddingValues(bottom = 24.dp)
    ) {
        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Brush.verticalGradient(listOf(shades[1].copy(alpha = 0.72f), spot.background)))
                    .padding(horizontal = 16.dp, vertical = 18.dp)
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CoverArt(
                            seed = artistName,
                            thumbnailUrl = tracks.firstOrNull()?.thumbnailUrl,
                            modifier = Modifier.size(84.dp),
                            cornerRadius = 42.dp,
                            fallbackIcon = Icons.Rounded.Person
                        )
                        Spacer(Modifier.width(16.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text("ARTIST", style = MaterialTheme.typography.labelSmall, color = spot.textDim, fontWeight = FontWeight.Bold)
                            Text(
                                text = artistName,
                                style = MaterialTheme.typography.headlineSmall,
                                color = spot.textPrimary,
                                fontWeight = FontWeight.Bold
                            )
                            val meta = buildList {
                                add(SpotUiTextUtils.fmtTotal(tracks))
                                if (plays > 0) add("$plays plays")
                                if (minsText.isNotEmpty()) add("$minsText listened")
                            }.joinToString(" \u00b7 ")
                            Text(meta, style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                        }
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = {
                                if (tracks.isEmpty()) viewModel.toastNow("No songs for $artistName yet")
                                else viewModel.play(tracks, 0, artistName)
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = spot.accent, contentColor = spot.onAccent),
                            modifier = Modifier.testTag("artist_play_btn")
                        ) {
                            Icon(Icons.Rounded.PlayArrow, null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Play")
                        }
                        OutlinedButton(
                            onClick = {
                                if (tracks.isNotEmpty()) {
                                    val shuf = SpotUiTextUtils.smartShuffle(
                                        tracks,
                                        mode = state.prefs.shuffleMode,
                                        plays = state.library.playCounts
                                    )
                                    viewModel.play(shuf, 0, artistName)
                                }
                            },
                            modifier = Modifier.testTag("artist_shuffle_btn")
                        ) {
                            Icon(Icons.Rounded.Shuffle, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Shuffle")
                        }
                        OutlinedButton(
                            onClick = { viewModel.playNextAll(tracks) },
                            modifier = Modifier.testTag("artist_play_next_btn")
                        ) {
                            Icon(Icons.Rounded.QueueMusic, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Play next")
                        }
                    }
                }
            }
        }

        if (popular.isNotEmpty()) {
            item {
                Text(
                    text = "POPULAR",
                    style = MaterialTheme.typography.labelMedium,
                    color = spot.textDim,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                )
            }
            itemsIndexed(popular, key = { _, t -> "pop_${t.id}" }) { idx, track ->
                Box(modifier = Modifier.padding(horizontal = 8.dp)) {
                    TrackRow(
                        track = track,
                        index = idx,
                        isCurrent = state.currentTrack?.id == track.id,
                        isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                        isLiked = track.id in state.likedIds,
                        isBlocked = track.id in state.blockedIds,
                        reducedMotion = state.prefs.reducedMotion,
                        playCount = state.library.playCounts[track.id]?.count ?: 0,
                        onClick = { viewModel.play(popular, idx, artistName) },
                        onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, artistName)) },
                        onArtistClick = {},
                        onToggleLike = { viewModel.toggleLike(track) },
                        onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(track, artistName)) }
                    )
                }
            }
        }

        if (otherArtists.isNotEmpty()) {
            item {
                Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp)) {
                    Text(
                        text = "MORE ARTISTS YOU PLAY",
                        style = MaterialTheme.typography.labelMedium,
                        color = spot.textDim,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(8.dp))
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        otherArtists.forEach { a ->
                            Surface(
                                color = spot.hover,
                                shape = RoundedCornerShape(20.dp),
                                modifier = Modifier
                                    .border(1.dp, spot.divider, RoundedCornerShape(20.dp))
                                    .clickable { viewModel.navigateTo(NavDest.Artist(a)) }
                            ) {
                                Text(
                                    text = a,
                                    color = spot.textPrimary,
                                    style = MaterialTheme.typography.bodySmall,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                                )
                            }
                        }
                    }
                }
            }
        }

        item {
            Text(
                text = if (libTracks.isNotEmpty()) "IN YOUR LIBRARY" else "TRACKS ON YOUTUBE",
                style = MaterialTheme.typography.labelMedium,
                color = spot.textDim,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
            )
        }

        if (isBusy && tracks.isEmpty()) {
            item {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(24.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    CircularProgressIndicator(color = spot.accent, modifier = Modifier.size(22.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(10.dp))
                    Text("Finding tracks by $artistName...", color = spot.textDim)
                }
            }
        } else if (tracks.isEmpty()) {
            item {
                Text(
                    text = "No songs found yet for $artistName.",
                    color = spot.textDim,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                )
            }
        } else {
            itemsIndexed(tracks, key = { idx, t -> "art_${t.id}_$idx" }) { idx, track ->
                Box(modifier = Modifier.padding(horizontal = 8.dp)) {
                    TrackRow(
                        track = track,
                        index = idx,
                        isCurrent = state.currentTrack?.id == track.id,
                        isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                        isLiked = track.id in state.likedIds,
                        isBlocked = track.id in state.blockedIds,
                        reducedMotion = state.prefs.reducedMotion,
                        playCount = state.library.playCounts[track.id]?.count ?: 0,
                        onClick = { viewModel.play(tracks, idx, artistName, startRadioAfter = libTracks.isEmpty()) },
                        onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, artistName)) },
                        onArtistClick = {},
                        onToggleLike = { viewModel.toggleLike(track) },
                        onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(track, artistName)) }
                    )
                }
            }
        }
    }
}

@Composable
fun SimilarScreen(
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val similar = state.prefs.similarCache
    val tracks = similar.items

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("similar_screen"),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = stringResource(R.string.made_for_you),
                    style = MaterialTheme.typography.headlineSmall,
                    color = spot.textPrimary,
                    fontWeight = FontWeight.Bold
                )
                if (similar.seed.isNotBlank()) {
                    Text(
                        text = if (similar.kind == "artist") "Inspired by ${similar.seed}" else "Inspired by \"${similar.seed}\"",
                        style = MaterialTheme.typography.bodySmall,
                        color = spot.textDim
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
                    Button(
                        onClick = { if (tracks.isNotEmpty()) viewModel.play(tracks, 0, "Made for you", startRadioAfter = true) },
                        colors = ButtonDefaults.buttonColors(containerColor = spot.accent, contentColor = spot.onAccent),
                        modifier = Modifier.testTag("similar_play_all_btn")
                    ) {
                        Icon(Icons.Rounded.PlayArrow, null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Play all")
                    }
                    OutlinedButton(
                        onClick = { viewModel.refreshSimilar(force = true) },
                        modifier = Modifier.testTag("similar_reroll_btn")
                    ) {
                        Icon(Icons.Rounded.Refresh, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Reroll picks")
                    }
                }
            }
        }

        if (tracks.isEmpty()) {
            item {
                Text(
                    text = "Play or search a few songs first to build personalized picks.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = spot.textDim
                )
            }
        } else {
            itemsIndexed(tracks, key = { idx, t -> "simscreen_${t.id}_$idx" }) { idx, track ->
                TrackRow(
                    track = track,
                    index = idx,
                    isCurrent = state.currentTrack?.id == track.id,
                    isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                    isLiked = track.id in state.likedIds,
                    isBlocked = track.id in state.blockedIds,
                    reducedMotion = state.prefs.reducedMotion,
                    onClick = { viewModel.play(tracks, idx, "Made for you", startRadioAfter = true) },
                    onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Made for you")) },
                    onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                    onToggleLike = { viewModel.toggleLike(track) },
                    onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Made for you")) }
                )
            }
        }
    }
}
