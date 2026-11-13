package com.example.ui.screens

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.PushPin
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Shuffle
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.R
import com.example.data.model.DailyMix
import com.example.data.model.NavDest
import com.example.data.model.Playlist
import com.example.data.model.Track
import com.example.data.util.SpotUiTextUtils
import com.example.ui.components.CoverArt
import com.example.ui.components.PlaylistMosaicArt
import com.example.ui.components.TrackRow
import com.example.ui.theme.LocalSpotColors
import com.example.ui.viewmodel.ActiveModal
import com.example.ui.viewmodel.SpotUiState
import com.example.ui.viewmodel.SpotUiViewModel
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun HomeScreen(
    state: SpotUiState,
    viewModel: SpotUiViewModel,
    isWide: Boolean,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val greeting = remember {
        val hr = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        when {
            hr < 12 -> "Good morning"
            hr < 18 -> "Good afternoon"
            else -> "Good evening"
        }
    }
    val dateLabel = remember {
        SimpleDateFormat("EEE, MMM d", Locale.US).format(Date())
    }

    val history = state.library.history
    val liked = state.library.liked
    val playlists = state.library.playlists
    val stats = state.stats
    val mixes = state.dailyMixes
    val similar = state.prefs.similarCache

    val resumeOffsetSec: Double? = remember(history, state.prefs.session, state.currentTrack) {
        val first = history.firstOrNull()
        val sess = state.prefs.session
        val sessTrack = sess.queue.getOrNull(sess.qpos)
        if (state.currentTrack == null && first != null && sessTrack?.id == first.id && sess.positionSec > 5.0) {
            sess.positionSec
        } else null
    }

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("home_screen"),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(22.dp)
    ) {
        // Greeting + Streak
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    text = greeting,
                    style = MaterialTheme.typography.headlineMedium,
                    color = spot.textPrimary,
                    fontWeight = FontWeight.Bold
                )
                val subParts = buildList {
                    add(dateLabel)
                    if (stats.streakDays > 0) add("${stats.streakDays}-day streak")
                    if (stats.todayMinutes > 0) add("${stats.todayMinutes} min today")
                }
                Text(
                    text = subParts.joinToString(" \u00b7 "),
                    style = MaterialTheme.typography.bodySmall,
                    color = spot.textDim
                )
            }
        }

        // Continue Listening Hero Card
        if (history.isNotEmpty()) {
            val latest = history.first()
            item {
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, spot.divider, RoundedCornerShape(14.dp))
                        .clickable { viewModel.resumeSessionOrPlay() }
                        .testTag("continue_listening_card")
                ) {
                    Row(
                        modifier = Modifier.padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        CoverArt(
                            seed = latest.id,
                            thumbnailUrl = latest.thumbnailUrl,
                            modifier = Modifier.size(64.dp),
                            cornerRadius = 10.dp
                        )
                        Spacer(Modifier.width(14.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = stringResource(R.string.continue_listening),
                                style = MaterialTheme.typography.labelSmall,
                                color = spot.accent,
                                fontWeight = FontWeight.Bold
                            )
                            Spacer(Modifier.height(2.dp))
                            Text(
                                text = latest.title,
                                style = MaterialTheme.typography.titleMedium,
                                color = spot.textPrimary,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                            val sub = buildString {
                                append(latest.artist)
                                if (resumeOffsetSec != null) {
                                    append(" \u00b7 left off at ${SpotUiTextUtils.fmtTimeDouble(resumeOffsetSec)}")
                                }
                            }
                            Text(
                                text = sub,
                                style = MaterialTheme.typography.bodySmall,
                                color = spot.textDim,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                        Spacer(Modifier.width(10.dp))
                        Surface(
                            shape = CircleShape,
                            color = spot.accent,
                            modifier = Modifier
                                .size(48.dp)
                                .clickable { viewModel.resumeSessionOrPlay() }
                                .testTag("continue_play_btn")
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Icon(
                                    imageVector = Icons.Rounded.PlayArrow,
                                    contentDescription = stringResource(R.string.cd_play),
                                    tint = spot.onAccent
                                )
                            }
                        }
                    }
                }
            }
        }

        // Welcome Card for Fresh Library
        if (state.isLibFresh) {
            item {
                Surface(
                    color = spot.hover,
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, spot.divider, RoundedCornerShape(16.dp))
                        .testTag("welcome_card")
                ) {
                    Column {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .aspectRatio(16f / 7f)
                        ) {
                            Image(
                                painter = painterResource(R.drawable.img_welcome_hero),
                                contentDescription = "SpotUI welcome artwork",
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxSize()
                            )
                            Box(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .background(
                                        Brush.verticalGradient(
                                            listOf(
                                                spot.background.copy(alpha = 0.08f),
                                                spot.hover
                                            )
                                        )
                                    )
                            )
                        }
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            Text(
                                text = "Welcome to SpotUI",
                                style = MaterialTheme.typography.titleLarge,
                                color = spot.textPrimary,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Search YouTube tracks, build custom playlists, follow synced lyrics, and listen with smart shuffle and EQ.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = spot.textDim
                            )
                            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text("1. Search for any song or artist on YouTube", style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                                Text("2. Tap the heart to build Liked Songs & Daily Mixes", style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                                Text("3. Create a playlist or paste a YouTube playlist URL", style = MaterialTheme.typography.bodySmall, color = spot.textDim)
                            }
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                                modifier = Modifier.padding(top = 4.dp)
                            ) {
                                Button(
                                    onClick = { viewModel.navigateTo(NavDest.Search) },
                                    colors = ButtonDefaults.buttonColors(
                                        containerColor = spot.accent,
                                        contentColor = spot.onAccent
                                    ),
                                    modifier = Modifier.testTag("welcome_search_btn")
                                ) {
                                    Icon(Icons.Rounded.Search, null, modifier = Modifier.size(18.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text("Search songs")
                                }
                                OutlinedButton(
                                    onClick = { viewModel.openModal(ActiveModal.CreateOrImportPlaylist()) },
                                    modifier = Modifier.testTag("welcome_create_pl_btn")
                                ) {
                                    Icon(Icons.Rounded.Add, null, modifier = Modifier.size(18.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text("New playlist")
                                }
                            }
                        }
                    }
                }
            }
        }

        // Shortcut Tiles (Liked Songs, Recently Played, Playlists)
        item {
            val cols = if (isWide) 3 else 2
            val shortcuts = buildList<@Composable (Modifier) -> Unit> {
                add { mod ->
                    ShortcutTile(
                        title = stringResource(R.string.liked_songs),
                        subtitle = SpotUiTextUtils.fmtTotal(liked),
                        pinned = true,
                        onClick = { viewModel.navigateTo(NavDest.Liked) },
                        onPlay = if (liked.isNotEmpty()) { { viewModel.play(liked, 0, "Liked Songs") } } else null,
                        art = {
                            Box(
                                modifier = Modifier
                                    .size(50.dp)
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(
                                        Brush.linearGradient(listOf(spot.accent, spot.raised))
                                    ),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(Icons.Rounded.Favorite, null, tint = spot.onAccent, modifier = Modifier.size(22.dp))
                            }
                        },
                        tag = "shortcut_liked",
                        modifier = mod
                    )
                }
                add { mod ->
                    ShortcutTile(
                        title = stringResource(R.string.recently_played),
                        subtitle = "${history.size} recent",
                        pinned = false,
                        onClick = { viewModel.navigateTo(NavDest.History) },
                        onPlay = if (history.isNotEmpty()) { { viewModel.play(history, 0, "Recently Played") } } else null,
                        art = {
                            Box(
                                modifier = Modifier
                                    .size(50.dp)
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(spot.raised),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(Icons.Rounded.History, null, tint = spot.textPrimary, modifier = Modifier.size(22.dp))
                            }
                        },
                        tag = "shortcut_history",
                        modifier = mod
                    )
                }
                playlists.take(if (isWide) 7 else 4).forEach { pl ->
                    add { mod ->
                        ShortcutTile(
                            title = pl.name,
                            subtitle = SpotUiTextUtils.fmtTotal(pl.tracks),
                            pinned = pl.pinned,
                            onClick = { viewModel.navigateTo(NavDest.PlaylistDest(pl.id)) },
                            onPlay = if (pl.tracks.isNotEmpty()) { { viewModel.play(pl.tracks, 0, pl.name) } } else null,
                            art = {
                                PlaylistMosaicArt(
                                    playlist = pl,
                                    modifier = Modifier.size(50.dp),
                                    cornerRadius = 8.dp
                                )
                            },
                            tag = "shortcut_playlist_${pl.id}",
                            modifier = mod
                        )
                    }
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                shortcuts.chunked(cols).forEach { rowItems ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        rowItems.forEach { render -> render(Modifier.weight(1f)) }
                        repeat(cols - rowItems.size) {
                            Spacer(Modifier.weight(1f))
                        }
                    }
                }
                if (liked.isNotEmpty() || playlists.any { it.tracks.isNotEmpty() }) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { viewModel.shuffleLibrary() },
                            modifier = Modifier.testTag("home_shuffle_library_btn")
                        ) {
                            Icon(Icons.Rounded.Shuffle, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Shuffle library")
                        }
                        if (liked.isNotEmpty()) {
                            OutlinedButton(
                                onClick = { viewModel.shuffleLiked() },
                                modifier = Modifier.testTag("home_shuffle_liked_btn")
                            ) {
                                Icon(Icons.Rounded.Favorite, null, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Shuffle liked")
                            }
                        }
                    }
                }
            }
        }

        // Daily Mixes Shelf
        if (mixes.isNotEmpty()) {
            item {
                SectionHeader(title = stringResource(R.string.your_mixes))
                Spacer(Modifier.height(10.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(mixes, key = { it.index }) { mix ->
                        MixCard(
                            mix = mix,
                            onClick = { viewModel.playMix(mix) },
                            onLongClick = { viewModel.queueMix(mix) }
                        )
                    }
                }
            }
        }

        // Trending on YouTube shelf (real YouTube home feed - tap to watch the video)
        if (state.homeFeed.isNotEmpty()) {
            item {
                SectionHeader(
                    title = "Trending on YouTube",
                    subtitle = "From YouTube's home feed - tap a card to watch",
                    trailing = {
                        IconButton(
                            onClick = { viewModel.maybeLoadHomeFeed(force = true) },
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("home_refresh_yt_btn")
                        ) {
                            Icon(Icons.Rounded.Refresh, "Refresh YouTube feed", tint = spot.textDim)
                        }
                    }
                )
                Spacer(Modifier.height(8.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    itemsIndexed(state.homeFeed, key = { _, t -> "yt_${'$'}{t.id}" }) { _, track ->
                        TrackShelfCard(
                            track = track,
                            badge = "Video",
                            onClick = { viewModel.watchVideo(track) },
                            onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, "YouTube")) }
                        )
                    }
                    if (state.homeFeedContinuation != null) {
                        item(key = "yt_load_more") {
                            Box(
                                contentAlignment = Alignment.Center,
                                modifier = Modifier
                                    .width(120.dp)
                                    .height(150.dp)
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(spot.raised)
                                    .clickable(enabled = !state.homeFeedMoreLoading) {
                                        viewModel.loadMoreHomeFeed()
                                    }
                            ) {
                                if (state.homeFeedMoreLoading) {
                                    CircularProgressIndicator(
                                        color = spot.accent,
                                        modifier = Modifier.size(24.dp)
                                    )
                                } else {
                                    Text(
                                        text = "More",
                                        color = spot.accent,
                                        style = MaterialTheme.typography.labelLarge
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        // Made for you Shelf
        if (similar.items.isNotEmpty()) {
            item {
                val seedDesc = if (similar.seed.isNotBlank()) {
                    if (similar.kind == "artist") "Because you listen to ${similar.seed}"
                    else "Because you searched \"${similar.seed}\""
                } else null
                SectionHeader(
                    title = stringResource(R.string.made_for_you),
                    subtitle = seedDesc,
                    trailing = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            IconButton(
                                onClick = { viewModel.refreshSimilar(force = true) },
                                modifier = Modifier.minimumInteractiveComponentSize().testTag("home_refresh_similar_btn")
                            ) {
                                Icon(Icons.Rounded.Refresh, "Refresh recommendations", tint = spot.textDim)
                            }
                            TextButton(
                                onClick = { viewModel.navigateTo(NavDest.Similar) },
                                modifier = Modifier.testTag("home_see_all_similar_btn")
                            ) {
                                Text("See all", color = spot.accent)
                            }
                        }
                    }
                )
                Spacer(Modifier.height(8.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    itemsIndexed(similar.items, key = { _, t -> "sim_${t.id}" }) { idx, track ->
                        TrackShelfCard(
                            track = track,
                            badge = null,
                            onClick = { viewModel.play(similar.items, idx, "Made for you", startRadioAfter = true) },
                            onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Made for you")) }
                        )
                    }
                }
            }
        }

        // On Repeat Shelf
        if (stats.onRepeat.isNotEmpty()) {
            item {
                SectionHeader(
                    title = stringResource(R.string.on_repeat),
                    subtitle = "Played 2+ times in the last 7 days",
                    trailing = {
                        TextButton(
                            onClick = { viewModel.navigateTo(NavDest.Stats) },
                            modifier = Modifier.testTag("home_open_stats_btn")
                        ) {
                            Text("Open Stats", color = spot.accent)
                        }
                    }
                )
                Spacer(Modifier.height(8.dp))
                val repeatTracks = stats.onRepeat.map { it.first }
                LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    itemsIndexed(stats.onRepeat, key = { _, pair -> "rep_${pair.first.id}" }) { idx, (track, count) ->
                        TrackShelfCard(
                            track = track,
                            badge = "${count}x",
                            onClick = { viewModel.play(repeatTracks, idx, "On repeat", startRadioAfter = true) },
                            onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, "On repeat")) }
                        )
                    }
                }
            }
        }

        // Recently Played Compact List
        if (history.isNotEmpty()) {
            item {
                SectionHeader(
                    title = stringResource(R.string.recently_played),
                    trailing = {
                        TextButton(
                            onClick = { viewModel.navigateTo(NavDest.History) },
                            modifier = Modifier.testTag("home_open_history_btn")
                        ) {
                            Text("See all", color = spot.accent)
                        }
                    }
                )
                Spacer(Modifier.height(6.dp))
                val preview = history.take(5)
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    preview.forEachIndexed { idx, track ->
                        TrackRow(
                            track = track,
                            index = idx,
                            isCurrent = state.currentTrack?.id == track.id,
                            isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                            isLiked = track.id in state.likedIds,
                            isBlocked = track.id in state.blockedIds,
                            reducedMotion = state.prefs.reducedMotion,
                            dateOrAgoLabel = SpotUiTextUtils.fmtAgo(track.playedAtSec),
                            onClick = { viewModel.play(history, idx, "Recently Played", startRadioAfter = true) },
                            onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Recently Played")) },
                            onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                            onToggleLike = { viewModel.toggleLike(track) },
                            onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Recently Played")) }
                        )
                    }
                }
            }
        }

        // Songs You Like Compact List
        if (liked.isNotEmpty()) {
            item {
                SectionHeader(
                    title = stringResource(R.string.songs_you_like),
                    trailing = {
                        TextButton(
                            onClick = { viewModel.navigateTo(NavDest.Liked) },
                            modifier = Modifier.testTag("home_open_liked_btn")
                        ) {
                            Text("See all", color = spot.accent)
                        }
                    }
                )
                Spacer(Modifier.height(6.dp))
                val preview = liked.take(5)
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    preview.forEachIndexed { idx, track ->
                        TrackRow(
                            track = track,
                            index = idx,
                            isCurrent = state.currentTrack?.id == track.id,
                            isPlaying = !state.playerState.isPaused && !state.playerState.isIdle,
                            isLiked = true,
                            isBlocked = track.id in state.blockedIds,
                            reducedMotion = state.prefs.reducedMotion,
                            dateOrAgoLabel = track.addedDate,
                            onClick = { viewModel.play(liked, idx, "Liked Songs") },
                            onLongClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Liked Songs")) },
                            onArtistClick = { viewModel.navigateTo(NavDest.Artist(it)) },
                            onToggleLike = { viewModel.toggleLike(track) },
                            onMoreClick = { viewModel.openModal(ActiveModal.SongMenu(track, "Liked Songs")) }
                        )
                    }
                }
            }
        }

        // Recent Searches
        if (state.library.recentSearches.isNotEmpty()) {
            item {
                SectionHeader(title = stringResource(R.string.recent_searches))
                Spacer(Modifier.height(8.dp))
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    state.library.recentSearches.forEach { q ->
                        Surface(
                            color = spot.hover,
                            shape = RoundedCornerShape(20.dp),
                            modifier = Modifier
                                .border(1.dp, spot.divider, RoundedCornerShape(20.dp))
                                .clickable { viewModel.rerunSearch(q) }
                                .testTag("home_recent_search_$q")
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.padding(start = 12.dp, end = 4.dp, top = 4.dp, bottom = 4.dp)
                            ) {
                                Text(q, color = spot.textPrimary, style = MaterialTheme.typography.bodySmall)
                                IconButton(
                                    onClick = { viewModel.removeRecentSearch(q) },
                                    modifier = Modifier.minimumInteractiveComponentSize()
                                ) {
                                    Icon(Icons.Rounded.Close, "Remove recent search", tint = spot.textDim, modifier = Modifier.size(16.dp))
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

@Composable
private fun SectionHeader(
    title: String,
    subtitle: String? = null,
    trailing: (@Composable () -> Unit)? = null
) {
    val spot = LocalSpotColors.current
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                color = spot.textPrimary,
                fontWeight = FontWeight.Bold
            )
            if (!subtitle.isNullOrBlank()) {
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = spot.textDim
                )
            }
        }
        trailing?.invoke()
    }
}

@Composable
private fun ShortcutTile(
    title: String,
    subtitle: String,
    pinned: Boolean,
    onClick: () -> Unit,
    onPlay: (() -> Unit)?,
    art: @Composable () -> Unit,
    tag: String,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    Surface(
        color = spot.hover,
        shape = RoundedCornerShape(10.dp),
        modifier = modifier
            .border(1.dp, spot.divider, RoundedCornerShape(10.dp))
            .clickable(onClick = onClick)
            .testTag(tag)
    ) {
        Row(
            modifier = Modifier.padding(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            art()
            Spacer(Modifier.width(10.dp))
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (pinned) {
                        Icon(
                            Icons.Rounded.PushPin,
                            null,
                            tint = spot.accent,
                            modifier = Modifier.size(12.dp).padding(end = 3.dp)
                        )
                    }
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleSmall,
                        color = spot.textPrimary,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.labelSmall,
                    color = spot.textFaint,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            if (onPlay != null) {
                IconButton(
                    onClick = onPlay,
                    modifier = Modifier.minimumInteractiveComponentSize().testTag("${tag}_play")
                ) {
                    Icon(
                        imageVector = Icons.Rounded.PlayArrow,
                        contentDescription = stringResource(R.string.cd_play),
                        tint = spot.accent
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun MixCard(
    mix: DailyMix,
    onClick: () -> Unit,
    onLongClick: () -> Unit
) {
    val spot = LocalSpotColors.current
    val lead = mix.tracks.firstOrNull()
    val subtitle = if (mix.withArtists.isEmpty()) mix.artist else "${mix.artist}, ${mix.withArtists.joinToString(", ")}"

    Surface(
        color = spot.hover,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier
            .width(156.dp)
            .border(1.dp, spot.divider, RoundedCornerShape(12.dp))
            .combinedClickable(onClick = onClick, onLongClick = onLongClick)
            .testTag("mix_card_${mix.index}")
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Box(modifier = Modifier.fillMaxWidth().aspectRatio(1f)) {
                CoverArt(
                    seed = mix.name + mix.artist,
                    thumbnailUrl = lead?.thumbnailUrl,
                    modifier = Modifier.fillMaxSize(),
                    cornerRadius = 8.dp
                )
                Surface(
                    color = spot.background.copy(alpha = 0.85f),
                    shape = RoundedCornerShape(6.dp),
                    modifier = Modifier.align(Alignment.BottomStart).padding(6.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Rounded.AutoAwesome, null, tint = spot.accent, modifier = Modifier.size(12.dp))
                        Spacer(Modifier.width(3.dp))
                        Text("Mix ${mix.index + 1}", style = MaterialTheme.typography.labelSmall, color = spot.textPrimary)
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(
                text = mix.name,
                style = MaterialTheme.typography.titleSmall,
                color = spot.textPrimary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = spot.textDim,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun TrackShelfCard(
    track: Track,
    badge: String?,
    onClick: () -> Unit,
    onLongClick: () -> Unit
) {
    val spot = LocalSpotColors.current
    Surface(
        color = spot.hover,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier
            .width(152.dp)
            .border(1.dp, spot.divider, RoundedCornerShape(12.dp))
            .combinedClickable(onClick = onClick, onLongClick = onLongClick)
            .testTag("shelf_card_${track.id}")
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Box(modifier = Modifier.fillMaxWidth().aspectRatio(1f)) {
                CoverArt(
                    seed = track.id,
                    thumbnailUrl = track.thumbnailUrl,
                    modifier = Modifier.fillMaxSize(),
                    cornerRadius = 8.dp
                )
                if (!badge.isNullOrBlank()) {
                    Surface(
                        color = spot.accent,
                        shape = RoundedCornerShape(6.dp),
                        modifier = Modifier.align(Alignment.TopEnd).padding(6.dp)
                    ) {
                        Text(
                            text = badge,
                            color = spot.onAccent,
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(
                text = track.title,
                style = MaterialTheme.typography.titleSmall,
                color = spot.textPrimary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = track.artist,
                style = MaterialTheme.typography.bodySmall,
                color = spot.textDim,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}
