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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.PlaylistAdd
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.QueueMusic
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.R
import com.example.data.model.NavDest
import com.example.data.model.SearchFilter
import com.example.data.util.SpotUiTextUtils
import com.example.ui.components.CoverArt
import com.example.ui.components.TrackRow
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.ActiveModal
import com.example.ui.viewmodel.SpotUiState
import com.example.ui.viewmodel.SpotUiViewModel

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SearchScreen(
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val keyboard = LocalSoftwareKeyboardController.current
    val q = state.searchQuery
    val trimmed = q.trim()
    val results = state.searchResults

    val matchingArtists = remember(trimmed, results, state.library) {
        if (trimmed.isEmpty()) emptyList() else viewModel.searchMatchingArtists(trimmed, limit = 8)
    }
    val matchingPlaylists = remember(trimmed, state.library.playlists) {
        if (trimmed.isEmpty()) emptyList() else viewModel.searchMatchingPlaylists(trimmed, limit = 4)
    }

    val topArtistName = remember(trimmed, matchingArtists) {
        val normQ = SpotUiTextUtils.normArtist(trimmed)
        if (normQ.length >= 2) {
            matchingArtists.firstOrNull { SpotUiTextUtils.normArtist(it).startsWith(normQ) }
        } else null
    }

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("search_screen"),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Search Input
        item {
            OutlinedTextField(
                value = q,
                onValueChange = { viewModel.onSearchQueryChanged(it) },
                placeholder = {
                    Text(stringResource(R.string.search_placeholder), color = spot.textFaint)
                },
                leadingIcon = {
                    Icon(Icons.Rounded.Search, contentDescription = null, tint = spot.textDim)
                },
                trailingIcon = {
                    if (q.isNotEmpty()) {
                        IconButton(
                            onClick = { viewModel.onSearchQueryChanged("") },
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("search_clear_btn")
                        ) {
                            Icon(Icons.Rounded.Close, contentDescription = "Clear search", tint = spot.textDim)
                        }
                    }
                },
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(
                    onSearch = {
                        keyboard?.hide()
                        viewModel.submitSearch()
                    }
                ),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = spot.accent,
                    unfocusedBorderColor = spot.divider,
                    focusedTextColor = spot.textPrimary,
                    unfocusedTextColor = spot.textPrimary,
                    cursorColor = spot.accent,
                    focusedContainerColor = spot.hover,
                    unfocusedContainerColor = spot.hover
                ),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth().testTag("search_input_field")
            )
            if (state.isSearching) {
                Spacer(Modifier.height(6.dp))
                LinearProgressIndicator(
                    modifier = Modifier.fillMaxWidth().height(2.dp),
                    color = spot.accent,
                    trackColor = spot.divider
                )
            }
        }

        // Empty query state
        if (trimmed.isEmpty()) {
            if (state.library.recentSearches.isNotEmpty()) {
                item {
                    Text(
                        text = stringResource(R.string.recent_searches),
                        style = MaterialTheme.typography.titleMedium,
                        color = spot.textPrimary,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(8.dp))
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        state.library.recentSearches.forEach { term ->
                            Surface(
                                color = spot.hover,
                                shape = RoundedCornerShape(20.dp),
                                modifier = Modifier
                                    .border(1.dp, spot.divider, RoundedCornerShape(20.dp))
                                    .clickable { viewModel.rerunSearch(term) }
                                    .testTag("search_recent_chip_$term")
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(start = 12.dp, end = 4.dp, top = 4.dp, bottom = 4.dp)
                                ) {
                                    Text(term, color = spot.textPrimary, style = MaterialTheme.typography.bodySmall)
                                    IconButton(
                                        onClick = { viewModel.removeRecentSearch(term) },
                                        modifier = Modifier.minimumInteractiveComponentSize()
                                    ) {
                                        Icon(Icons.Rounded.Close, "Remove", tint = spot.textDim, modifier = Modifier.size(16.dp))
                                    }
                                }
                            }
                        }
                    }
                }
            }

            if (state.library.history.isNotEmpty()) {
                val jump = state.library.history.take(6)
                item {
                    Text(
                        text = stringResource(R.string.jump_back_in),
                        style = MaterialTheme.typography.titleMedium,
                        color = spot.textPrimary,
                        fontWeight = FontWeight.Bold
                    )
                }
                itemsIndexed(jump, key = { _, t -> "jump_${t.id}" }) { idx, track ->
                    TrackRow(
                        track = track,
                        index = idx,
                        isCurrent = state.currentTrack?.id == track.id,
                        isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                        isLiked = track.id in state.likedIds,
                        isBlocked = track.id in state.blockedIds,
                        reducedMotion = state.prefs.reducedMotion,
                        dateOrAgoLabel = SpotUiTextUtils.fmtAgo(track.playedAtSec),
                        onClick = { viewModel.play(state.library.history, idx, "Recently Played", startRadioAfter = true) },
                        onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Recently Played")) },
                        onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                        onToggleLike = { viewModel.toggleLike(track) },
                        onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Recently Played")) }
                    )
                }
            } else {
                item {
                    Surface(
                        color = spot.hover,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(12.dp))
                    ) {
                        Column(
                            modifier = Modifier.padding(18.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Text("Search YouTube music", style = MaterialTheme.typography.titleSmall, color = spot.textPrimary)
                            Text(
                                "Type a song title, artist, or vibe to search live and start instant radio.",
                                style = MaterialTheme.typography.bodySmall,
                                color = spot.textDim
                            )
                        }
                    }
                }
            }
        } else {
            // Filter Chips
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SearchFilter.entries.forEach { f ->
                        FilterChip(
                            selected = state.searchFilter == f,
                            onClick = { viewModel.setSearchFilter(f) },
                            label = { Text(f.label) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = spot.accent,
                                selectedLabelColor = spot.onAccent,
                                containerColor = spot.hover,
                                labelColor = spot.textPrimary
                            ),
                            modifier = Modifier.testTag("search_filter_${f.name.lowercase()}")
                        )
                    }
                }
            }

            // Matching Artists & Playlists chips on All tab
            if (state.searchFilter == SearchFilter.ALL && (matchingArtists.isNotEmpty() || matchingPlaylists.isNotEmpty())) {
                item {
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        matchingArtists.take(5).forEach { artistName ->
                            Surface(
                                color = spot.hover,
                                shape = RoundedCornerShape(20.dp),
                                modifier = Modifier
                                    .border(1.dp, spot.divider, RoundedCornerShape(20.dp))
                                    .clickable { viewModel.navigateTo(NavDest.Artist(artistName)) }
                                    .testTag("search_artist_chip_$artistName")
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                                ) {
                                    Icon(Icons.Rounded.Person, null, tint = spot.accent, modifier = Modifier.size(15.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text(artistName, color = spot.textPrimary, style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                        matchingPlaylists.forEach { pl ->
                            Surface(
                                color = spot.hover,
                                shape = RoundedCornerShape(20.dp),
                                modifier = Modifier
                                    .border(1.dp, spot.divider, RoundedCornerShape(20.dp))
                                    .clickable { viewModel.navigateTo(NavDest.PlaylistDest(pl.id)) }
                                    .testTag("search_playlist_chip_${pl.id}")
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                                ) {
                                    Icon(Icons.AutoMirrored.Rounded.PlaylistAdd, null, tint = spot.textDim, modifier = Modifier.size(15.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text("${pl.name} (${pl.tracks.size})", color = spot.textPrimary, style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                    }
                }
            }

            if (state.searchFilter == SearchFilter.ARTISTS) {
                if (matchingArtists.isEmpty()) {
                    item {
                        Text(
                            text = "No matching artists found for \"$trimmed\".",
                            color = spot.textDim,
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                } else {
                    items(matchingArtists, key = { it }) { artistName ->
                        val libCount = viewModel.artistLibraryTracks(artistName).size
                        val plays = viewModel.artistPlays(artistName)
                        Surface(
                            color = spot.hover,
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier
                                .fillMaxWidth()
                                .border(1.dp, spot.divider, RoundedCornerShape(10.dp))
                                .clickable { viewModel.navigateTo(NavDest.Artist(artistName)) }
                                .testTag("search_artist_row_$artistName")
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Box(
                                    modifier = Modifier.size(44.dp).clip(CircleShape).background(spot.avatar),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(Icons.Rounded.Person, null, tint = spot.textPrimary)
                                }
                                Spacer(Modifier.width(12.dp))
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(artistName, color = spot.textPrimary, style = MaterialTheme.typography.titleSmall)
                                    val meta = buildList {
                                        if (libCount > 0) add("$libCount in library")
                                        if (plays > 0) add("$plays plays")
                                    }.joinToString(" \u00b7 ").ifEmpty { "Artist" }
                                    Text(meta, color = spot.textDim, style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                    }
                }
            } else {
                // Top Result Card on All tab
                if (state.searchFilter == SearchFilter.ALL && (topArtistName != null || results.isNotEmpty())) {
                    item {
                        Text(
                            text = "Top result",
                            style = MaterialTheme.typography.titleMedium,
                            color = spot.textPrimary,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(Modifier.height(8.dp))
                        if (topArtistName != null) {
                            Surface(
                                color = spot.hover,
                                shape = RoundedCornerShape(14.dp),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .border(1.dp, spot.divider, RoundedCornerShape(14.dp))
                                    .clickable { viewModel.navigateTo(NavDest.Artist(topArtistName)) }
                                    .testTag("top_result_artist")
                            ) {
                                Row(
                                    modifier = Modifier.padding(16.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Box(
                                        modifier = Modifier.size(64.dp).clip(CircleShape).background(spot.avatar),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Icon(Icons.Rounded.Person, null, tint = spot.textPrimary, modifier = Modifier.size(32.dp))
                                    }
                                    Spacer(Modifier.width(14.dp))
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = topArtistName,
                                            style = MaterialTheme.typography.titleLarge,
                                            color = spot.textPrimary,
                                            fontWeight = FontWeight.Bold
                                        )
                                        Text(
                                            text = "Artist \u00b7 Tap to open artist page",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = spot.textDim
                                        )
                                    }
                                }
                            }
                        } else if (results.isNotEmpty()) {
                            val topSong = results.first()
                            Surface(
                                color = spot.hover,
                                shape = RoundedCornerShape(14.dp),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .border(1.dp, spot.divider, RoundedCornerShape(14.dp))
                                    .clickable { viewModel.play(results, 0, "Search", startRadioAfter = true) }
                                    .testTag("top_result_song")
                            ) {
                                Row(
                                    modifier = Modifier.padding(14.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    CoverArt(
                                        seed = topSong.id,
                                        thumbnailUrl = topSong.thumbnailUrl,
                                        modifier = Modifier.size(68.dp),
                                        cornerRadius = 10.dp
                                    )
                                    Spacer(Modifier.width(14.dp))
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = topSong.title,
                                            style = MaterialTheme.typography.titleMedium,
                                            color = spot.textPrimary,
                                            fontWeight = FontWeight.Bold,
                                            maxLines = 2,
                                            overflow = TextOverflow.Ellipsis
                                        )
                                        Spacer(Modifier.height(2.dp))
                                        Text(
                                            text = "Song \u00b7 ${topSong.artist} \u00b7 ${SpotUiTextUtils.fmtTime(topSong.durSec)}",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = spot.textDim,
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis
                                        )
                                    }
                                    Spacer(Modifier.width(8.dp))
                                    Surface(
                                        shape = CircleShape,
                                        color = spot.accent,
                                        modifier = Modifier
                                            .size(48.dp)
                                            .clickable { viewModel.play(results, 0, "Search", startRadioAfter = true) }
                                            .testTag("top_result_play_btn")
                                    ) {
                                        Box(contentAlignment = Alignment.Center) {
                                            Icon(Icons.Rounded.PlayArrow, stringResource(R.string.cd_play), tint = spot.onAccent)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Songs List
                if (results.isNotEmpty()) {
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "Songs (${results.size})",
                                style = MaterialTheme.typography.titleMedium,
                                color = spot.textPrimary,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.weight(1f)
                            )
                            OutlinedButton(
                                onClick = { viewModel.queueAll(results) },
                                modifier = Modifier.testTag("search_queue_all_btn")
                            ) {
                                Icon(Icons.Rounded.QueueMusic, null, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Queue all")
                            }
                        }
                    }
                    itemsIndexed(results, key = { idx, t -> "${t.id}_$idx" }) { idx, track ->
                        TrackRow(
                            track = track,
                            index = idx,
                            isCurrent = state.currentTrack?.id == track.id,
                            isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                            isLiked = track.id in state.likedIds,
                            isBlocked = track.id in state.blockedIds,
                            reducedMotion = state.prefs.reducedMotion,
                            playCount = state.library.playCounts[track.id]?.count ?: 0,
                            onClick = { viewModel.play(results, idx, "Search", startRadioAfter = true) },
                            onWatch = { viewModel.watchVideo(track) },
                            onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Search")) },
                            onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                            onToggleLike = { viewModel.toggleLike(track) },
                            onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Search")) }
                        )
                    }
                } else if (!state.isSearching) {
                    item {
                        Surface(
                            color = spot.hover,
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.fillMaxWidth().border(1.dp, spot.divider, RoundedCornerShape(12.dp))
                        ) {
                            Column(
                                modifier = Modifier.padding(18.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                Text(
                                    text = "No songs found for \"$trimmed\"",
                                    style = MaterialTheme.typography.titleSmall,
                                    color = spot.textPrimary
                                )
                                Text(
                                    text = "Try pressing Search on your keyboard or check your spelling.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = spot.textDim
                                )
                                Button(
                                    onClick = { viewModel.submitSearch() },
                                    colors = ButtonDefaults.buttonColors(containerColor = spot.accent, contentColor = spot.onAccent),
                                    modifier = Modifier.testTag("search_retry_btn")
                                ) {
                                    Text("Search YouTube")
                                }
                            }
                        }
                    }
                }
            }
        }

        item { Spacer(Modifier.height(16.dp)) }
    }
}
