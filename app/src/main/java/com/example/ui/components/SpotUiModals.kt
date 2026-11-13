package com.example.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.PlaylistAdd
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.Block
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.DeleteOutline
import androidx.compose.material.icons.rounded.DriveFileRenameOutline
import androidx.compose.material.icons.rounded.Equalizer
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.FileUpload
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.HelpOutline
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.KeyboardArrowUp
import androidx.compose.material.icons.rounded.Lyrics
import androidx.compose.material.icons.rounded.MergeType
import androidx.compose.material.icons.rounded.NotificationsNone
import androidx.compose.material.icons.rounded.OpenInBrowser
import androidx.compose.material.icons.rounded.Palette
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.PushPin
import androidx.compose.material.icons.rounded.QueueMusic
import androidx.compose.material.icons.rounded.Radio
import androidx.compose.material.icons.rounded.Repeat
import androidx.compose.material.icons.rounded.SaveAlt
import androidx.compose.material.icons.rounded.Shuffle
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.data.model.NavDest
import com.example.data.model.Playlist
import com.example.data.model.SpotTheme
import com.example.data.util.SpotUiTextUtils
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.ActiveModal
import com.example.ui.viewmodel.SpotUiState
import com.example.ui.viewmodel.SpotUiViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun SpotUiModals(
    modal: ActiveModal?,
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    isWide: Boolean,
    onPickJsonFile: () -> Unit,
    onExportPlaylistJson: (Playlist) -> Unit
) {
    if (modal == null) return
    val spot = LocalSpotColors.current

    when (modal) {
        is ActiveModal.SongMenu -> {
            val t = modal.track
            val isLiked = t.id in state.likedIds
            val isBlocked = t.id in state.blockedIds
            ModalBottomSheet(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                contentColor = spot.textPrimary,
                sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .verticalScroll(rememberScrollState())
                        .padding(bottom = 24.dp)
                        .testTag("modal_song_menu")
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 18.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        CoverArt(t.id, t.thumbnailUrl, Modifier.size(48.dp), 8.dp)
                        Spacer(Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(t.title, style = MaterialTheme.typography.titleSmall, color = spot.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text("${t.artist} \u00b7 ${SpotUiTextUtils.fmtTime(t.durSec)}", style = MaterialTheme.typography.bodySmall, color = spot.textDim, maxLines = 1)
                        }
                    }
                    HorizontalDivider(color = spot.divider, modifier = Modifier.padding(vertical = 6.dp))
                    ModalActionRow(Icons.Rounded.PlayArrow, "Play now") {
                        viewModel.closeModal()
                        viewModel.play(listOf(t), 0, modal.sourceLabel)
                    }
                    ModalActionRow(Icons.Rounded.QueueMusic, "Play next") {
                        viewModel.closeModal()
                        viewModel.playNext(t)
                    }
                    ModalActionRow(Icons.Rounded.Add, "Add to queue") {
                        viewModel.closeModal()
                        viewModel.addToQueue(t)
                    }
                    ModalActionRow(Icons.Rounded.Radio, "Start radio from song") {
                        viewModel.closeModal()
                        viewModel.startRadio(t)
                    }
                    ModalActionRow(Icons.Rounded.Favorite, if (isLiked) "Remove from Liked Songs" else "Add to Liked Songs") {
                        viewModel.closeModal()
                        viewModel.toggleLike(t)
                    }
                    ModalActionRow(Icons.AutoMirrored.Rounded.PlaylistAdd, "Add to playlist...") {
                        viewModel.openModal(ActiveModal.AddToPlaylistPicker(t))
                    }
                    ModalActionRow(Icons.Rounded.Person, "Open artist: ${t.artist}") {
                        viewModel.closeModal()
                        viewModel.navigateTo(NavDest.Artist(t.artist))
                    }
                    ModalActionRow(Icons.Rounded.Lyrics, "Lyrics") {
                        viewModel.openModal(ActiveModal.LyricsSheet(t))
                    }
                    ModalActionRow(Icons.Rounded.Info, "Song info") {
                        viewModel.openModal(ActiveModal.SongInfo(t))
                    }
                    ModalActionRow(Icons.Rounded.ContentCopy, "Copy YouTube link") {
                        viewModel.closeModal()
                        viewModel.copyTrackLink(t)
                    }
                    ModalActionRow(Icons.Rounded.OpenInBrowser, "Open in YouTube") {
                        viewModel.closeModal()
                        viewModel.openTrackInBrowser(t)
                    }
                    ModalActionRow(Icons.Rounded.Block, if (isBlocked) "Allow in suggestions again" else "Hide from suggestions") {
                        viewModel.closeModal()
                        viewModel.toggleBlock(t)
                    }
                    modal.playlistContext?.let { (pl, idx) ->
                        HorizontalDivider(color = spot.divider, modifier = Modifier.padding(vertical = 6.dp))
                        if (idx > 0) {
                            ModalActionRow(Icons.Rounded.KeyboardArrowUp, "Move up in ${pl.name}") {
                                viewModel.closeModal()
                                viewModel.moveTrackInPlaylist(pl, idx, -1)
                            }
                        }
                        if (idx < pl.tracks.lastIndex) {
                            ModalActionRow(Icons.Rounded.KeyboardArrowDown, "Move down in ${pl.name}") {
                                viewModel.closeModal()
                                viewModel.moveTrackInPlaylist(pl, idx, +1)
                            }
                        }
                        ModalActionRow(Icons.Rounded.DeleteOutline, "Remove from ${pl.name}") {
                            viewModel.closeModal()
                            viewModel.removeTrackFromPlaylist(pl, idx)
                        }
                    }
                    modal.queueIndex?.let { qi ->
                        if (qi != state.qpos) {
                            HorizontalDivider(color = spot.divider, modifier = Modifier.padding(vertical = 6.dp))
                            ModalActionRow(Icons.Rounded.QueueMusic, "Move to play next") {
                                viewModel.closeModal()
                                viewModel.moveQueueItemToNext(qi)
                            }
                            ModalActionRow(Icons.Rounded.DeleteOutline, "Remove from queue") {
                                viewModel.closeModal()
                                viewModel.removeQueueAt(qi)
                            }
                        }
                    }
                }
            }
        }

        is ActiveModal.CollectionMenu -> {
            val pl = modal.playlist
            val tracks = when (modal.kind) {
                "liked" -> state.library.liked
                "history" -> state.library.history
                else -> pl?.tracks ?: emptyList()
            }
            val title = when (modal.kind) {
                "liked" -> "Liked Songs"
                "history" -> "Recently Played"
                else -> pl?.name ?: "Playlist"
            }
            ModalBottomSheet(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                contentColor = spot.textPrimary,
                sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .verticalScroll(rememberScrollState())
                        .padding(bottom = 24.dp)
                        .testTag("modal_collection_menu")
                ) {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleMedium,
                        color = spot.textPrimary,
                        modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp)
                    )
                    HorizontalDivider(color = spot.divider)
                    ModalActionRow(Icons.Rounded.PlayArrow, "Play all") {
                        viewModel.closeModal()
                        if (tracks.isNotEmpty()) viewModel.play(tracks, 0, title)
                    }
                    ModalActionRow(Icons.Rounded.Shuffle, "Shuffle") {
                        viewModel.closeModal()
                        if (tracks.isNotEmpty()) {
                            val shuf = SpotUiTextUtils.smartShuffle(tracks, mode = state.prefs.shuffleMode, plays = state.library.playCounts)
                            viewModel.play(shuf, 0, title)
                        }
                    }
                    ModalActionRow(Icons.Rounded.QueueMusic, "Play next all") {
                        viewModel.closeModal()
                        viewModel.playNextAll(tracks)
                    }
                    ModalActionRow(Icons.Rounded.Add, "Add all to queue") {
                        viewModel.closeModal()
                        viewModel.queueAll(tracks)
                    }
                    ModalActionRow(Icons.Rounded.ContentCopy, "Copy tracklist") {
                        viewModel.closeModal()
                        viewModel.copyTracklist(title, tracks)
                    }
                    if (pl != null) {
                        HorizontalDivider(color = spot.divider, modifier = Modifier.padding(vertical = 4.dp))
                        ModalActionRow(Icons.Rounded.Favorite, "Like all songs in ${pl.name}") {
                            viewModel.closeModal()
                            viewModel.likeAll(pl)
                        }
                        ModalActionRow(Icons.Rounded.PushPin, if (pl.pinned) "Unpin playlist" else "Pin playlist to top") {
                            viewModel.closeModal()
                            viewModel.togglePin(pl)
                        }
                        ModalActionRow(Icons.Rounded.AutoAwesome, if (pl.enhanced) "Turn off Enhance" else "Enhance playlist with suggestions") {
                            viewModel.closeModal()
                            viewModel.toggleEnhance(pl)
                        }
                        ModalActionRow(Icons.Rounded.DriveFileRenameOutline, "Rename playlist") {
                            viewModel.openModal(ActiveModal.RenamePlaylist(pl))
                        }
                        ModalActionRow(Icons.Rounded.Add, "Duplicate playlist") {
                            viewModel.closeModal()
                            viewModel.duplicatePlaylist(pl)
                        }
                        ModalActionRow(Icons.Rounded.MergeType, "Merge into another playlist...") {
                            viewModel.openModal(ActiveModal.MergePlaylistPicker(pl))
                        }
                        ModalActionRow(Icons.Rounded.AutoAwesome, "Remove duplicates") {
                            viewModel.closeModal()
                            viewModel.dedupePlaylist(pl)
                        }
                        ModalActionRow(Icons.Rounded.SaveAlt, "Export playlist JSON...") {
                            viewModel.closeModal()
                            onExportPlaylistJson(pl)
                        }
                        ModalActionRow(Icons.Rounded.DeleteOutline, "Delete playlist") {
                            viewModel.openModal(ActiveModal.ConfirmDeletePlaylist(pl))
                        }
                    }
                    if (modal.kind == "history") {
                        HorizontalDivider(color = spot.divider, modifier = Modifier.padding(vertical = 4.dp))
                        ModalActionRow(Icons.Rounded.DeleteOutline, "Clear play history") {
                            viewModel.openModal(ActiveModal.ConfirmClearHistory)
                        }
                    }
                }
            }
        }

        ActiveModal.PlaybackMenu -> {
            ModalBottomSheet(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                contentColor = spot.textPrimary,
                sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .verticalScroll(rememberScrollState())
                        .padding(bottom = 24.dp)
                        .testTag("modal_playback_menu")
                ) {
                    Text("Playback & Settings", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp))
                    HorizontalDivider(color = spot.divider)
                    ModalActionRow(Icons.Rounded.Shuffle, "Shuffle mode: ${state.prefs.shuffleMode.label}") {
                        viewModel.cycleShuffleMode()
                    }
                    ModalActionRow(Icons.Rounded.Repeat, state.repeat.label) {
                        viewModel.cycleRepeat()
                    }
                    ModalActionRow(Icons.Rounded.AutoAwesome, "Autoplay: ${if (state.prefs.autoplay) "On" else "Off"}") {
                        viewModel.toggleAutoplay()
                    }
                    ModalActionRow(Icons.Rounded.Speed, "Speed: ${state.playerState.speed.toString().removeSuffix(".0")}x (tap to cycle)") {
                        viewModel.changeSpeed(if (state.playerState.speed >= 2.0f) -4 else 1)
                    }
                    ModalActionRow(Icons.Rounded.Equalizer, "Equalizer: ${state.prefs.eqPreset.label}") {
                        viewModel.cycleEq()
                    }
                    ModalActionRow(Icons.Rounded.GraphicEq, "Volume leveling: ${if (state.prefs.volumeLeveling) "On" else "Off"}") {
                        viewModel.toggleLeveling()
                    }
                    ModalActionRow(Icons.Rounded.Bedtime, "Sleep timer...") {
                        viewModel.openModal(ActiveModal.SleepTimerSheet)
                    }
                    ModalActionRow(Icons.Rounded.VisibilityOff, "Private session: ${if (state.privateSession) "On" else "Off"}") {
                        viewModel.togglePrivateSession()
                    }
                    if (isWide) {
                        ModalActionRow(Icons.Rounded.VisibilityOff, if (state.prefs.zenMode) "Show sidebar" else "Hide sidebar (Zen mode)") {
                            viewModel.toggleZenMode()
                        }
                    }
                    ModalActionRow(Icons.Rounded.Palette, "Theme (${state.prefs.theme.displayName}) & Motion") {
                        viewModel.openModal(ActiveModal.ThemePicker)
                    }
                    ModalActionRow(Icons.Rounded.NotificationsNone, "Recent notices (${state.notices.size})") {
                        viewModel.openModal(ActiveModal.RecentNotices)
                    }
                    ModalActionRow(Icons.Rounded.HelpOutline, "Help & features") {
                        viewModel.openModal(ActiveModal.HelpDialog)
                    }
                }
            }
        }

        is ActiveModal.AddToPlaylistPicker -> {
            var filter by remember { mutableStateOf("") }
            val filtered = state.library.playlists.filter { filter.isBlank() || filter.trim().lowercase() in it.name.lowercase() }
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("Add to playlist") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            value = filter,
                            onValueChange = { filter = it },
                            placeholder = { Text("Filter playlists") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                        LazyColumn(modifier = Modifier.heightIn(max = 260.dp)) {
                            itemsIndexed(filtered, key = { _, p -> p.id }) { _, pl ->
                                ModalActionRow(Icons.AutoMirrored.Rounded.PlaylistAdd, "${pl.name} (${pl.tracks.size})") {
                                    viewModel.closeModal()
                                    viewModel.addTrackToPlaylist(pl, modal.track)
                                }
                            }
                        }
                        OutlinedButton(
                            onClick = { viewModel.openModal(ActiveModal.CreateOrImportPlaylist(pendingTrack = modal.track)) },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Icon(Icons.Rounded.Add, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("New playlist with this song")
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Close", color = spot.accent) }
                }
            )
        }

        is ActiveModal.MergePlaylistPicker -> {
            var filter by remember { mutableStateOf("") }
            val candidates = state.library.playlists.filter {
                it.id != modal.sourcePlaylist.id && (filter.isBlank() || filter.trim().lowercase() in it.name.lowercase())
            }
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("Merge ${modal.sourcePlaylist.name} into...") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            value = filter,
                            onValueChange = { filter = it },
                            placeholder = { Text("Filter playlists") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                        LazyColumn(modifier = Modifier.heightIn(max = 240.dp)) {
                            itemsIndexed(candidates, key = { _, p -> p.id }) { _, pl ->
                                ModalActionRow(Icons.Rounded.MergeType, "${pl.name} (${pl.tracks.size})") {
                                    viewModel.closeModal()
                                    viewModel.mergePlaylists(modal.sourcePlaylist, pl)
                                }
                            }
                        }
                        OutlinedButton(
                            onClick = { viewModel.openModal(ActiveModal.CreateOrImportPlaylist(mergeFrom = modal.sourcePlaylist)) },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text("New playlist from merge")
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Cancel", color = spot.accent) }
                }
            )
        }

        is ActiveModal.CreateOrImportPlaylist -> {
            var text by remember { mutableStateOf("") }
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("New playlist or import") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(
                            "Enter a playlist name or paste a YouTube playlist URL.",
                            style = MaterialTheme.typography.bodySmall,
                            color = spot.textDim
                        )
                        OutlinedTextField(
                            value = text,
                            onValueChange = { text = it },
                            placeholder = { Text("Playlist name or youtube.com/playlist?list=...") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth().testTag("create_playlist_input")
                        )
                        if (modal.pendingTrack == null && modal.mergeFrom == null) {
                            OutlinedButton(
                                onClick = {
                                    viewModel.closeModal()
                                    onPickJsonFile()
                                },
                                modifier = Modifier.fillMaxWidth().testTag("import_json_btn")
                            ) {
                                Icon(Icons.Rounded.FileUpload, null, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Import .json playlist file")
                            }
                        }
                    }
                },
                confirmButton = {
                    Button(
                        onClick = {
                            val v = text.trim()
                            if (v.isNotEmpty()) {
                                viewModel.closeModal()
                                viewModel.createOrImportPlaylist(v, modal.pendingTrack, modal.mergeFrom)
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = spot.accent, contentColor = spot.onAccent),
                        modifier = Modifier.testTag("create_playlist_confirm_btn")
                    ) { Text("Create") }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Cancel", color = spot.textDim) }
                }
            )
        }

        is ActiveModal.RenamePlaylist -> {
            var text by remember(modal.playlist.id) { mutableStateOf(modal.playlist.name) }
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("Rename playlist") },
                text = {
                    OutlinedTextField(
                        value = text,
                        onValueChange = { text = it },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                },
                confirmButton = {
                    Button(
                        onClick = {
                            viewModel.closeModal()
                            viewModel.renamePlaylist(modal.playlist, text)
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = spot.accent, contentColor = spot.onAccent)
                    ) { Text("Save") }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Cancel", color = spot.textDim) }
                }
            )
        }

        is ActiveModal.ConfirmDeletePlaylist -> {
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("Delete playlist?") },
                text = { Text("Delete \"${modal.playlist.name}\" (${modal.playlist.tracks.size} songs)? You can undo right after.") },
                confirmButton = {
                    Button(
                        onClick = {
                            viewModel.closeModal()
                            viewModel.deletePlaylist(modal.playlist)
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
                    ) { Text("Delete") }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Cancel", color = spot.textDim) }
                }
            )
        }

        ActiveModal.ConfirmClearHistory -> {
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("Clear listening history?") },
                text = { Text("This clears Recently Played and play counts. Liked Songs and playlists will be kept.") },
                confirmButton = {
                    Button(
                        onClick = {
                            viewModel.closeModal()
                            viewModel.clearHistory()
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
                    ) { Text("Clear history") }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Cancel", color = spot.textDim) }
                }
            )
        }

        is ActiveModal.SongInfo -> {
            val t = modal.track
            val plays = state.library.playCounts[t.id]?.count ?: 0
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("Song info") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("Title: ${t.title}", style = MaterialTheme.typography.bodyMedium)
                        Text(
                            "Artist: ${t.artist}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = spot.accent,
                            modifier = Modifier.clickable {
                                viewModel.closeModal()
                                viewModel.navigateTo(NavDest.Artist(t.artist))
                            }
                        )
                        Text("Duration: ${SpotUiTextUtils.fmtTime(t.durSec)}", style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                        Text("Plays: $plays", style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                        if (t.channel.isNotBlank()) Text("Channel: ${t.channel}", style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                        if (!t.source.isNullOrBlank()) Text("Source: ${t.source}", style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                        if (!t.addedDate.isNullOrBlank()) Text("Added: ${t.addedDate}", style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                        Text("YouTube ID: ${t.id}", style = MaterialTheme.typography.bodySmall, color = spot.textFaint)
                    }
                },
                confirmButton = {
                    TextButton(onClick = {
                        viewModel.copyTrackLink(t)
                    }) { Text("Copy link", color = spot.accent) }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Close", color = spot.textDim) }
                }
            )
        }

        is ActiveModal.LyricsSheet -> {
            val t = modal.track
            val lyrics = state.library.lyricsCache[t.id]
            val posSec = state.playerState.positionSec
            val isThisPlaying = state.currentTrack?.id == t.id
            val activeLineIdx = remember(lyrics, posSec, isThisPlaying) {
                if (!isThisPlaying || lyrics == null || lyrics.synced.isEmpty()) -1
                else lyrics.synced.indexOfLast { it.timeSec <= posSec + 0.25 }
            }
            val listState = rememberLazyListState()
            LaunchedEffect(activeLineIdx) {
                if (activeLineIdx >= 2) {
                    listState.animateScrollToItem((activeLineIdx - 2).coerceAtLeast(0))
                }
            }
            ModalBottomSheet(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                contentColor = spot.textPrimary,
                sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp).padding(bottom = 24.dp).testTag("modal_lyrics_sheet")
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(t.title, style = MaterialTheme.typography.titleMedium, color = spot.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(
                                text = t.artist + if (lyrics?.hasSynced == true) " \u00b7 synced (tap line to seek)" else "",
                                style = MaterialTheme.typography.bodySmall,
                                color = spot.textDim
                            )
                        }
                        if (lyrics?.hasAny == true) {
                            IconButton(onClick = {
                                val textToCopy = if (lyrics.synced.isNotEmpty()) {
                                    lyrics.synced.joinToString("\n") { it.text }
                                } else lyrics.plainText ?: ""
                                viewModel.copyText(textToCopy, "Lyrics")
                            }) {
                                Icon(Icons.Rounded.ContentCopy, "Copy lyrics", tint = spot.accent)
                            }
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    HorizontalDivider(color = spot.divider)
                    Spacer(Modifier.height(10.dp))
                    when {
                        state.activeLyricsLoading && lyrics == null -> {
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 32.dp),
                                horizontalArrangement = Arrangement.Center,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                CircularProgressIndicator(color = spot.accent, modifier = Modifier.size(22.dp), strokeWidth = 2.dp)
                                Spacer(Modifier.width(10.dp))
                                Text("Looking up lyrics...", color = spot.textDim)
                            }
                        }
                        lyrics != null && lyrics.synced.isNotEmpty() -> {
                            LazyColumn(state = listState, modifier = Modifier.heightIn(max = 420.dp)) {
                                itemsIndexed(lyrics.synced) { idx, line ->
                                    val active = idx == activeLineIdx
                                    Text(
                                        text = line.text.ifBlank { "\u266a" },
                                        style = if (active) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyLarge,
                                        fontWeight = if (active) FontWeight.Bold else FontWeight.Normal,
                                        color = if (active) spot.accent else if (idx < activeLineIdx) spot.textDim else spot.textPrimary,
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .clip(RoundedCornerShape(8.dp))
                                            .clickable(enabled = isThisPlaying) { viewModel.seekTo(line.timeSec) }
                                            .padding(vertical = 8.dp, horizontal = 6.dp)
                                    )
                                }
                            }
                        }
                        !lyrics?.plainText.isNullOrBlank() -> {
                            Column(modifier = Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState())) {
                                Text(lyrics!!.plainText!!, style = MaterialTheme.typography.bodyLarge, color = spot.textPrimary)
                            }
                        }
                        else -> {
                            Text(
                                "No lyrics found on LRCLIB for this song.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = spot.textDim,
                                modifier = Modifier.padding(vertical = 24.dp)
                            )
                        }
                    }
                }
            }
        }

        ActiveModal.ThemePicker -> {
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("Theme & Motion") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        SpotTheme.entries.forEach { th ->
                            val selected = state.effectiveTheme == th
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(10.dp))
                                    .border(1.dp, if (selected) th.accent else spot.divider, RoundedCornerShape(10.dp))
                                    .background(if (selected) spot.raised else spot.background)
                                    .clickable { viewModel.previewTheme(th) }
                                    .padding(horizontal = 12.dp, vertical = 10.dp)
                                    .testTag("theme_option_${th.name.lowercase()}"),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Box(modifier = Modifier.size(20.dp).clip(CircleShape).background(th.accent))
                                Spacer(Modifier.width(12.dp))
                                Text(th.displayName, style = MaterialTheme.typography.bodyLarge, color = spot.textPrimary, modifier = Modifier.weight(1f))
                                if (selected) Text("Selected", style = MaterialTheme.typography.labelSmall, color = th.accent)
                            }
                        }
                        HorizontalDivider(color = spot.divider)
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("Reduced motion", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                            Switch(
                                checked = state.prefs.reducedMotion,
                                onCheckedChange = { viewModel.toggleReducedMotion() }
                            )
                        }
                    }
                },
                confirmButton = {
                    Button(
                        onClick = { viewModel.applyTheme(state.effectiveTheme) },
                        colors = ButtonDefaults.buttonColors(containerColor = spot.accent, contentColor = spot.onAccent),
                        modifier = Modifier.testTag("theme_apply_btn")
                    ) { Text("Apply") }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Cancel", color = spot.textDim) }
                }
            )
        }

        ActiveModal.SleepTimerSheet -> {
            var customMin by remember { mutableStateOf("") }
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("Sleep timer") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        val activeLabel = when {
                            state.sleepEot -> "Active: pausing at end of current track"
                            state.sleepRemainingSec != null -> "Active: ${SpotUiTextUtils.fmtTime(state.sleepRemainingSec)} remaining (20s fade-out)"
                            else -> "Timer is off"
                        }
                        Text(activeLabel, style = MaterialTheme.typography.bodySmall, color = spot.accent)
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            listOf(5, 10, 15, 30, 45, 60).forEach { m ->
                                OutlinedButton(onClick = {
                                    viewModel.closeModal()
                                    viewModel.setSleepMinutes(m)
                                }) { Text("${m}m") }
                            }
                        }
                        OutlinedButton(
                            onClick = {
                                viewModel.closeModal()
                                viewModel.setSleepEndOfTrack()
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) { Text("End of current track") }
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(
                                value = customMin,
                                onValueChange = { customMin = it.filter { ch -> ch.isDigit() } },
                                placeholder = { Text("Custom minutes (1-1440)") },
                                singleLine = true,
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                modifier = Modifier.weight(1f)
                            )
                            Button(
                                onClick = {
                                    val m = customMin.toIntOrNull()
                                    if (m != null && m in 1..1440) {
                                        viewModel.closeModal()
                                        viewModel.setSleepMinutes(m)
                                    }
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = spot.accent, contentColor = spot.onAccent)
                            ) { Text("Set") }
                        }
                    }
                },
                confirmButton = {
                    if (state.sleepEot || state.sleepRemainingSec != null) {
                        TextButton(onClick = {
                            viewModel.closeModal()
                            viewModel.setSleepMinutes(0)
                        }) { Text("Turn off", color = MaterialTheme.colorScheme.error) }
                    }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Close", color = spot.textDim) }
                }
            )
        }

        ActiveModal.RecentNotices -> {
            val fmt = remember { SimpleDateFormat("HH:mm:ss", Locale.US) }
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("Recent notices") },
                text = {
                    if (state.notices.isEmpty()) {
                        Text("No notices yet.", color = spot.textDim)
                    } else {
                        LazyColumn(modifier = Modifier.heightIn(max = 320.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            itemsIndexed(state.notices.asReversed()) { _, n ->
                                Row(verticalAlignment = Alignment.Top) {
                                    Text(fmt.format(Date(n.timestampMs)), style = MaterialTheme.typography.labelSmall, color = spot.textFaint)
                                    Spacer(Modifier.width(8.dp))
                                    Text(n.message, style = MaterialTheme.typography.bodySmall, color = spot.textPrimary)
                                }
                            }
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Close", color = spot.accent) }
                }
            )
        }

        ActiveModal.HelpDialog -> {
            AlertDialog(
                onDismissRequest = { viewModel.closeModal() },
                containerColor = spot.hover,
                titleContentColor = spot.textPrimary,
                textContentColor = spot.textPrimary,
                title = { Text("SpotUI Guide") },
                text = {
                    Column(
                        modifier = Modifier.verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text("Search & Radio: Search YouTube songs and auto-start radio mixes from any track.", style = MaterialTheme.typography.bodySmall)
                        Text("Smart Shuffle: Switch between Artist Spread, Discovery (least played), and Mood (most played).", style = MaterialTheme.typography.bodySmall)
                        Text("Playlists: Create, pin, enhance with recommendations, dedupe, merge, or import/export YouTube links & JSON files.", style = MaterialTheme.typography.bodySmall)
                        Text("Lyrics: Synced and plain lyrics via LRCLIB — tap any synced line to jump directly.", style = MaterialTheme.typography.bodySmall)
                        Text("Audio & Sleep: Adjustable speed, 4 EQ presets, volume leveling, and sleep timer with 20s gentle fade-out.", style = MaterialTheme.typography.bodySmall)
                        Text("Private Session: Pause listening history & play count tracking whenever you want.", style = MaterialTheme.typography.bodySmall)
                    }
                },
                confirmButton = {
                    TextButton(onClick = { viewModel.closeModal() }) { Text("Got it", color = spot.accent) }
                }
            )
        }
    }
}

@Composable
private fun ModalActionRow(
    icon: ImageVector,
    label: String,
    onClick: () -> Unit
) {
    val spot = LocalSpotColors.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, null, tint = spot.textDim, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(14.dp))
        Text(label, style = MaterialTheme.typography.bodyLarge, color = spot.textPrimary)
    }
}
