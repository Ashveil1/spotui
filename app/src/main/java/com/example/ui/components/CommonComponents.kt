package com.example.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode as AnimRepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.QueueMusic
import androidx.compose.material.icons.automirrored.rounded.VolumeOff
import androidx.compose.material.icons.automirrored.rounded.VolumeUp
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.BarChart
import androidx.compose.material.icons.rounded.PlayCircle
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.Block
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.KeyboardArrowUp
import androidx.compose.material.icons.rounded.Lyrics
import androidx.compose.material.icons.rounded.MoreHoriz
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.PushPin
import androidx.compose.material.icons.rounded.Repeat
import androidx.compose.material.icons.rounded.RepeatOne
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Shuffle
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.SkipPrevious
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.example.R
import com.example.data.model.NavDest
import com.example.data.model.Playlist
import com.example.data.model.RepeatMode
import com.example.data.model.ShuffleMode
import com.example.data.model.Track
import com.example.data.util.SpotUiTextUtils
import com.example.player.AudioPlayerState
import com.example.ui.theme.LocalSpotColors
import kotlinx.coroutines.delay

@Composable
fun CoverArt(
    seed: String,
    thumbnailUrl: String?,
    modifier: Modifier = Modifier,
    cornerRadius: Dp = 8.dp,
    fallbackIcon: ImageVector = Icons.Rounded.MusicNote
) {
    val shades = remember(seed) { SpotUiTextUtils.coverShades(seed) }
    val shape = RoundedCornerShape(cornerRadius)
    Box(
        modifier = modifier
            .clip(shape)
            .background(
                Brush.linearGradient(
                    colors = listOf(shades[0], shades[1], shades[2], shades[3])
                )
            ),
        contentAlignment = Alignment.Center
    ) {
        Icon(
            imageVector = fallbackIcon,
            contentDescription = null,
            tint = Color.White.copy(alpha = 0.72f),
            modifier = Modifier.fillMaxSize(0.45f)
        )
        if (!thumbnailUrl.isNullOrBlank()) {
            AsyncImage(
                model = thumbnailUrl,
                contentDescription = stringResource(R.string.cd_cover_art),
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize()
            )
        }
    }
}

@Composable
fun PlaylistMosaicArt(
    playlist: Playlist,
    modifier: Modifier = Modifier,
    cornerRadius: Dp = 8.dp
) {
    val tracks = remember(playlist.tracks) {
        val seen = mutableSetOf<String>()
        playlist.tracks.filter { seen.add(it.id) }.take(4)
    }
    if (tracks.size < 4) {
        val first = tracks.firstOrNull()
        CoverArt(
            seed = first?.id ?: playlist.name,
            thumbnailUrl = first?.thumbnailUrl,
            modifier = modifier,
            cornerRadius = cornerRadius
        )
        return
    }
    Column(
        modifier = modifier.clip(RoundedCornerShape(cornerRadius))
    ) {
        Row(modifier = Modifier.weight(1f).fillMaxWidth()) {
            CoverArt(tracks[0].id, tracks[0].thumbnailUrl, Modifier.weight(1f).fillMaxHeight(), cornerRadius = 0.dp)
            CoverArt(tracks[1].id, tracks[1].thumbnailUrl, Modifier.weight(1f).fillMaxHeight(), cornerRadius = 0.dp)
        }
        Row(modifier = Modifier.weight(1f).fillMaxWidth()) {
            CoverArt(tracks[2].id, tracks[2].thumbnailUrl, Modifier.weight(1f).fillMaxHeight(), cornerRadius = 0.dp)
            CoverArt(tracks[3].id, tracks[3].thumbnailUrl, Modifier.weight(1f).fillMaxHeight(), cornerRadius = 0.dp)
        }
    }
}

@Composable
fun EqualizerBars(
    isPlaying: Boolean,
    reducedMotion: Boolean,
    color: Color = LocalSpotColors.current.accent,
    barCount: Int = 3,
    modifier: Modifier = Modifier
) {
    val transition = rememberInfiniteTransition(label = "eq_bars")
    val fractions = List(barCount) { idx ->
        if (isPlaying && !reducedMotion) {
            val anim by transition.animateFloat(
                initialValue = 0.22f,
                targetValue = 0.95f,
                animationSpec = infiniteRepeatable(
                    animation = tween(durationMillis = 360 + idx * 130, easing = LinearEasing),
                    repeatMode = AnimRepeatMode.Reverse
                ),
                label = "bar_$idx"
            )
            anim
        } else if (isPlaying) {
            listOf(0.8f, 0.55f, 0.9f, 0.6f)[idx % 4]
        } else {
            0.25f
        }
    }
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.Bottom
    ) {
        fractions.forEach { frac ->
            Box(
                modifier = Modifier
                    .width(3.dp)
                    .fillMaxHeight(frac.coerceIn(0.18f, 1f))
                    .clip(RoundedCornerShape(1.5.dp))
                    .background(color)
            )
        }
    }
}

@Composable
fun HighlightedText(
    text: String,
    query: String,
    color: Color,
    highlightColor: Color,
    fontWeight: FontWeight = FontWeight.Normal,
    maxLines: Int = 1,
    style: androidx.compose.ui.text.TextStyle = MaterialTheme.typography.bodyMedium
) {
    val q = query.trim()
    if (q.isEmpty()) {
        Text(
            text = text,
            color = color,
            fontWeight = fontWeight,
            maxLines = maxLines,
            overflow = TextOverflow.Ellipsis,
            style = style
        )
        return
    }
    val idx = text.lowercase().indexOf(q.lowercase())
    if (idx < 0) {
        Text(
            text = text,
            color = color,
            fontWeight = fontWeight,
            maxLines = maxLines,
            overflow = TextOverflow.Ellipsis,
            style = style
        )
        return
    }
    val annotated = buildAnnotatedString {
        append(text.substring(0, idx))
        withStyle(SpanStyle(color = highlightColor, fontWeight = FontWeight.Bold)) {
            append(text.substring(idx, idx + q.length))
        }
        append(text.substring(idx + q.length))
    }
    Text(
        text = annotated,
        color = color,
        fontWeight = fontWeight,
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
        style = style
    )
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun TrackRow(
    track: Track,
    index: Int,
    isCurrent: Boolean,
    isPlaying: Boolean,
    isLiked: Boolean,
    isBlocked: Boolean,
    reducedMotion: Boolean,
    findQuery: String = "",
    playCount: Int = 0,
    dateOrAgoLabel: String? = null,
    canReorder: Boolean = false,
    onMoveUp: (() -> Unit)? = null,
    onMoveDown: (() -> Unit)? = null,
    onWatch: (() -> Unit)? = null,
    onClick: () -> Unit,
    onLongClick: () -> Unit,
    onArtistClick: (String) -> Unit,
    onToggleLike: () -> Unit,
    onMoreClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val rowBg = if (isCurrent) spot.raised.copy(alpha = 0.65f) else Color.Transparent

    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(rowBg)
            .combinedClickable(
                onClick = onClick,
                onLongClick = onLongClick
            )
            .padding(horizontal = 10.dp, vertical = 8.dp)
            .testTag("track_row_${track.id}"),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier.width(28.dp),
            contentAlignment = Alignment.Center
        ) {
            if (isCurrent) {
                EqualizerBars(
                    isPlaying = isPlaying,
                    reducedMotion = reducedMotion,
                    color = spot.accent,
                    modifier = Modifier.height(16.dp)
                )
            } else {
                Text(
                    text = "${index + 1}",
                    style = MaterialTheme.typography.labelMedium,
                    color = spot.textFaint
                )
            }
        }

        Spacer(Modifier.width(8.dp))

        CoverArt(
            seed = track.id,
            thumbnailUrl = track.thumbnailUrl,
            modifier = Modifier.size(44.dp),
            cornerRadius = 6.dp
        )

        Spacer(Modifier.width(12.dp))

        Column(modifier = Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (track.isAuto || track.isEnhanced) {
                    Icon(
                        imageVector = Icons.Rounded.AutoAwesome,
                        contentDescription = if (track.isAuto) "Autoplayed" else "Enhanced suggestion",
                        tint = spot.accent,
                        modifier = Modifier.size(14.dp).padding(end = 4.dp)
                    )
                }
                if (isBlocked) {
                    Icon(
                        imageVector = Icons.Rounded.Block,
                        contentDescription = "Blocked from suggestions",
                        tint = Color(239, 68, 68),
                        modifier = Modifier.size(14.dp).padding(end = 4.dp)
                    )
                }
                HighlightedText(
                    text = track.title,
                    query = findQuery,
                    color = if (isCurrent) spot.accent else spot.textPrimary,
                    highlightColor = spot.accent,
                    fontWeight = if (isCurrent) FontWeight.SemiBold else FontWeight.Medium,
                    style = MaterialTheme.typography.bodyLarge
                )
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Text(
                    text = track.artist,
                    color = spot.textDim,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier
                        .weight(1f, fill = false)
                        .clickable { onArtistClick(track.artist) }
                        .padding(vertical = 2.dp)
                )
                if (!dateOrAgoLabel.isNullOrBlank()) {
                    Text(
                        text = "\u00b7 $dateOrAgoLabel",
                        color = spot.textFaint,
                        style = MaterialTheme.typography.labelSmall,
                        maxLines = 1
                    )
                }
                if (playCount > 0) {
                    Text(
                        text = "\u00b7 ${playCount}x",
                        color = spot.textFaint,
                        style = MaterialTheme.typography.labelSmall,
                        maxLines = 1
                    )
                }
            }
        }

        if (canReorder) {
            if (onMoveUp != null) {
                IconButton(
                    onClick = onMoveUp,
                    modifier = Modifier.minimumInteractiveComponentSize().testTag("move_up_${track.id}")
                ) {
                    Icon(
                        imageVector = Icons.Rounded.KeyboardArrowUp,
                        contentDescription = "Move up",
                        tint = spot.textDim
                    )
                }
            }
            if (onMoveDown != null) {
                IconButton(
                    onClick = onMoveDown,
                    modifier = Modifier.minimumInteractiveComponentSize().testTag("move_down_${track.id}")
                ) {
                    Icon(
                        imageVector = Icons.Rounded.KeyboardArrowDown,
                        contentDescription = "Move down",
                        tint = spot.textDim
                    )
                }
            }
        }

        if (onWatch != null) {
            IconButton(
                onClick = onWatch,
                modifier = Modifier.minimumInteractiveComponentSize().testTag("watch_btn_${'$'}{track.id}")
            ) {
                Icon(
                    imageVector = Icons.Rounded.PlayCircle,
                    contentDescription = "Watch video",
                    tint = spot.textDim,
                    modifier = Modifier.size(20.dp)
                )
            }
        }

        IconButton(
            onClick = onToggleLike,
            modifier = Modifier.minimumInteractiveComponentSize().testTag("like_btn_${track.id}")
        ) {
            Icon(
                imageVector = if (isLiked) Icons.Rounded.Favorite else Icons.Outlined.FavoriteBorder,
                contentDescription = stringResource(R.string.cd_like),
                tint = if (isLiked) spot.accent else spot.textFaint,
                modifier = Modifier.size(20.dp)
            )
        }

        Text(
            text = SpotUiTextUtils.fmtTime(track.durSec),
            style = MaterialTheme.typography.labelMedium,
            color = spot.textFaint,
            modifier = Modifier.padding(end = 2.dp)
        )

        IconButton(
            onClick = onMoreClick,
            modifier = Modifier.minimumInteractiveComponentSize().testTag("more_btn_${track.id}")
        ) {
            Icon(
                imageVector = Icons.Rounded.MoreVert,
                contentDescription = stringResource(R.string.cd_more),
                tint = spot.textDim,
                modifier = Modifier.size(20.dp)
            )
        }
    }
}

@Composable
fun MiniPlayerBar(
    track: Track,
    playerState: AudioPlayerState,
    isLiked: Boolean,
    onToggleLike: () -> Unit,
    onTogglePlayPause: () -> Unit,
    onNext: () -> Unit,
    onClickBar: () -> Unit,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val dur = playerState.durationSec.takeIf { it > 0 } ?: (track.durSec ?: 0).toDouble()
    val progress = if (dur > 0) (playerState.positionSec / dur).toFloat().coerceIn(0f, 1f) else 0f

    Surface(
        color = spot.playerBar,
        shape = RoundedCornerShape(12.dp),
        tonalElevation = 4.dp,
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 4.dp)
            .border(1.dp, spot.divider, RoundedCornerShape(12.dp))
            .clickable(onClick = onClickBar)
            .testTag("mini_player_bar")
    ) {
        Column {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 10.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                CoverArt(
                    seed = track.id,
                    thumbnailUrl = track.thumbnailUrl,
                    modifier = Modifier.size(44.dp),
                    cornerRadius = 6.dp
                )
                Spacer(Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = track.title,
                        color = spot.textPrimary,
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
                IconButton(
                    onClick = onToggleLike,
                    modifier = Modifier.minimumInteractiveComponentSize().testTag("mini_like_btn")
                ) {
                    Icon(
                        imageVector = if (isLiked) Icons.Rounded.Favorite else Icons.Outlined.FavoriteBorder,
                        contentDescription = stringResource(R.string.cd_like),
                        tint = if (isLiked) spot.accent else spot.textDim
                    )
                }
                IconButton(
                    onClick = onTogglePlayPause,
                    modifier = Modifier.minimumInteractiveComponentSize().testTag("mini_play_pause_btn")
                ) {
                    when {
                        playerState.isLoading -> CircularProgressIndicator(
                            modifier = Modifier.size(22.dp),
                            color = spot.accent,
                            strokeWidth = 2.dp
                        )
                        playerState.isPaused || playerState.isIdle -> Icon(
                            imageVector = Icons.Rounded.PlayArrow,
                            contentDescription = stringResource(R.string.cd_play),
                            tint = spot.textPrimary
                        )
                        else -> Icon(
                            imageVector = Icons.Rounded.Pause,
                            contentDescription = stringResource(R.string.cd_pause),
                            tint = spot.textPrimary
                        )
                    }
                }
                IconButton(
                    onClick = onNext,
                    modifier = Modifier.minimumInteractiveComponentSize().testTag("mini_next_btn")
                ) {
                    Icon(
                        imageVector = Icons.Rounded.SkipNext,
                        contentDescription = stringResource(R.string.cd_next),
                        tint = spot.textPrimary
                    )
                }
            }
            LinearProgressIndicator(
                progress = { progress },
                modifier = Modifier.fillMaxWidth().height(2.dp),
                color = spot.accent,
                trackColor = spot.divider
            )
        }
    }
}

@Composable
fun DesktopPlayerBar(
    track: Track?,
    playerState: AudioPlayerState,
    isLiked: Boolean,
    shuffle: Boolean,
    shuffleMode: ShuffleMode,
    repeat: RepeatMode,
    timeLeft: Boolean,
    isMuted: Boolean,
    onOpenNowPlaying: () -> Unit,
    onArtistClick: (String) -> Unit,
    onToggleLike: () -> Unit,
    onToggleShuffle: () -> Unit,
    onPrev: () -> Unit,
    onTogglePlayPause: () -> Unit,
    onNext: () -> Unit,
    onCycleRepeat: () -> Unit,
    onSeek: (Double) -> Unit,
    onToggleTimeLeft: () -> Unit,
    onCycleSpeed: () -> Unit,
    onOpenLyrics: () -> Unit,
    onOpenQueue: () -> Unit,
    onToggleMute: () -> Unit,
    onVolumeChange: (Int) -> Unit,
    onOpenPlaybackMenu: () -> Unit,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    val dur = playerState.durationSec.takeIf { it > 0 } ?: (track?.durSec ?: 0).toDouble()
    var draggingPos by remember { mutableFloatStateOf(0f) }
    var isDragging by remember { mutableStateOf(false) }
    val pos = if (isDragging) draggingPos.toDouble() else playerState.positionSec

    Surface(
        color = spot.playerBar,
        modifier = modifier
            .fillMaxWidth()
            .testTag("desktop_player_bar")
    ) {
        Column {
            HorizontalDivider(color = spot.divider, thickness = 1.dp)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Left: track info
                Row(
                    modifier = Modifier
                        .weight(0.28f)
                        .clickable(enabled = track != null, onClick = onOpenNowPlaying),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (track != null) {
                        CoverArt(
                            seed = track.id,
                            thumbnailUrl = track.thumbnailUrl,
                            modifier = Modifier.size(52.dp),
                            cornerRadius = 6.dp
                        )
                        Spacer(Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = track.title,
                                color = spot.textPrimary,
                                style = MaterialTheme.typography.titleSmall,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                            Text(
                                text = track.artist,
                                color = spot.textDim,
                                style = MaterialTheme.typography.bodySmall,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.clickable { onArtistClick(track.artist) }
                            )
                        }
                        IconButton(
                            onClick = onToggleLike,
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("desktop_like_btn")
                        ) {
                            Icon(
                                imageVector = if (isLiked) Icons.Rounded.Favorite else Icons.Outlined.FavoriteBorder,
                                contentDescription = stringResource(R.string.cd_like),
                                tint = if (isLiked) spot.accent else spot.textDim
                            )
                        }
                    } else {
                        Text(
                            text = "Nothing playing",
                            color = spot.textFaint,
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }

                // Center: transport & seekbar
                Column(
                    modifier = Modifier.weight(0.44f),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        IconButton(
                            onClick = onToggleShuffle,
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("desktop_shuffle_btn")
                        ) {
                            Box(contentAlignment = Alignment.TopEnd) {
                                Icon(
                                    imageVector = Icons.Rounded.Shuffle,
                                    contentDescription = stringResource(R.string.cd_shuffle),
                                    tint = if (shuffle) spot.accent else spot.textDim
                                )
                                if (shuffle && shuffleMode.badge.isNotEmpty()) {
                                    Text(
                                        text = shuffleMode.badge,
                                        fontSize = 9.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = spot.accent
                                    )
                                }
                            }
                        }
                        IconButton(
                            onClick = onPrev,
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("desktop_prev_btn")
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.SkipPrevious,
                                contentDescription = stringResource(R.string.cd_prev),
                                tint = spot.textPrimary
                            )
                        }
                        Surface(
                            shape = CircleShape,
                            color = spot.textPrimary,
                            modifier = Modifier
                                .size(40.dp)
                                .clickable(onClick = onTogglePlayPause)
                                .testTag("desktop_play_pause_btn")
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                when {
                                    playerState.isLoading -> CircularProgressIndicator(
                                        modifier = Modifier.size(20.dp),
                                        color = spot.onAccent,
                                        strokeWidth = 2.dp
                                    )
                                    playerState.isPaused || playerState.isIdle -> Icon(
                                        imageVector = Icons.Rounded.PlayArrow,
                                        contentDescription = stringResource(R.string.cd_play),
                                        tint = spot.onAccent
                                    )
                                    else -> Icon(
                                        imageVector = Icons.Rounded.Pause,
                                        contentDescription = stringResource(R.string.cd_pause),
                                        tint = spot.onAccent
                                    )
                                }
                            }
                        }
                        IconButton(
                            onClick = onNext,
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("desktop_next_btn")
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.SkipNext,
                                contentDescription = stringResource(R.string.cd_next),
                                tint = spot.textPrimary
                            )
                        }
                        IconButton(
                            onClick = onCycleRepeat,
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("desktop_repeat_btn")
                        ) {
                            Icon(
                                imageVector = if (repeat == RepeatMode.ONE) Icons.Rounded.RepeatOne else Icons.Rounded.Repeat,
                                contentDescription = stringResource(R.string.cd_repeat),
                                tint = if (repeat != RepeatMode.OFF) spot.accent else spot.textDim
                            )
                        }
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = SpotUiTextUtils.fmtTimeDouble(pos),
                            style = MaterialTheme.typography.labelSmall,
                            color = spot.textDim
                        )
                        Slider(
                            value = if (dur > 0) pos.toFloat().coerceIn(0f, dur.toFloat()) else 0f,
                            onValueChange = {
                                isDragging = true
                                draggingPos = it
                            },
                            onValueChangeFinished = {
                                isDragging = false
                                onSeek(draggingPos.toDouble())
                            },
                            valueRange = 0f..(dur.toFloat().coerceAtLeast(1f)),
                            enabled = track != null && dur > 0,
                            colors = SliderDefaults.colors(
                                thumbColor = spot.textPrimary,
                                activeTrackColor = spot.accent,
                                inactiveTrackColor = spot.divider
                            ),
                            modifier = Modifier.weight(1f).padding(horizontal = 8.dp).testTag("desktop_seek_slider")
                        )
                        val rightLabel = if (timeLeft && dur > 0) {
                            "-" + SpotUiTextUtils.fmtTimeDouble((dur - pos).coerceAtLeast(0.0))
                        } else {
                            SpotUiTextUtils.fmtTimeDouble(dur.takeIf { it > 0 })
                        }
                        Text(
                            text = rightLabel,
                            style = MaterialTheme.typography.labelSmall,
                            color = spot.textDim,
                            modifier = Modifier.clickable(onClick = onToggleTimeLeft)
                        )
                        if (kotlin.math.abs(playerState.speed - 1.0f) > 0.01f) {
                            Spacer(Modifier.width(6.dp))
                            Surface(
                                color = spot.raised,
                                shape = RoundedCornerShape(6.dp),
                                modifier = Modifier.clickable(onClick = onCycleSpeed)
                            ) {
                                Text(
                                    text = "${playerState.speed.toString().removeSuffix(".0")}x",
                                    color = spot.accent,
                                    style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp)
                                )
                            }
                        }
                    }
                }

                // Right: lyrics, queue, volume, menu
                Row(
                    modifier = Modifier.weight(0.28f),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.End
                ) {
                    if (track != null) {
                        IconButton(
                            onClick = onOpenLyrics,
                            modifier = Modifier.minimumInteractiveComponentSize().testTag("desktop_lyrics_btn")
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.Lyrics,
                                contentDescription = "Lyrics",
                                tint = spot.textDim
                            )
                        }
                    }
                    IconButton(
                        onClick = onOpenQueue,
                        modifier = Modifier.minimumInteractiveComponentSize().testTag("desktop_queue_btn")
                    ) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Rounded.QueueMusic,
                            contentDescription = stringResource(R.string.cd_queue),
                            tint = spot.textDim
                        )
                    }
                    IconButton(
                        onClick = onToggleMute,
                        modifier = Modifier.minimumInteractiveComponentSize().testTag("desktop_mute_btn")
                    ) {
                        Icon(
                            imageVector = if (isMuted || playerState.volume == 0) Icons.AutoMirrored.Rounded.VolumeOff else Icons.AutoMirrored.Rounded.VolumeUp,
                            contentDescription = stringResource(R.string.cd_mute),
                            tint = spot.textDim
                        )
                    }
                    Slider(
                        value = playerState.volume.toFloat(),
                        onValueChange = { onVolumeChange(it.toInt()) },
                        valueRange = 0f..100f,
                        colors = SliderDefaults.colors(
                            thumbColor = spot.textPrimary,
                            activeTrackColor = spot.accent,
                            inactiveTrackColor = spot.divider
                        ),
                        modifier = Modifier.width(88.dp).testTag("desktop_volume_slider")
                    )
                    IconButton(
                        onClick = onOpenPlaybackMenu,
                        modifier = Modifier.minimumInteractiveComponentSize().testTag("desktop_playback_menu_btn")
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.MoreHoriz,
                            contentDescription = "Playback options",
                            tint = spot.textDim
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun SpotUiSidebar(
    currentDest: NavDest,
    likedCount: Int,
    historyCount: Int,
    playlists: List<Playlist>,
    playSource: String?,
    isPlaying: Boolean,
    reducedMotion: Boolean,
    sleepRemainingSec: Int?,
    sleepEot: Boolean,
    privateSession: Boolean,
    onNavigate: (NavDest) -> Unit,
    onCreatePlaylist: () -> Unit,
    onOpenSleepTimer: () -> Unit,
    modifier: Modifier = Modifier
) {
    val spot = LocalSpotColors.current
    Surface(
        color = spot.sidebar,
        modifier = modifier.width(248.dp).fillMaxHeight()
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp, vertical = 14.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp)
            ) {
                Icon(
                    imageVector = Icons.Rounded.GraphicEq,
                    contentDescription = null,
                    tint = spot.accent,
                    modifier = Modifier.size(26.dp)
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = "SpotUI",
                    color = spot.textPrimary,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
            }

            Spacer(Modifier.height(10.dp))

            SidebarNavRow(
                icon = Icons.Rounded.Home,
                label = "Home",
                selected = currentDest is NavDest.Home,
                onClick = { onNavigate(NavDest.Home) },
                tag = "side_nav_home"
            )
            SidebarNavRow(
                icon = Icons.Rounded.Search,
                label = "Search",
                selected = currentDest is NavDest.Search,
                onClick = { onNavigate(NavDest.Search) },
                tag = "side_nav_search"
            )
            SidebarNavRow(
                icon = Icons.Rounded.BarChart,
                label = "Stats",
                selected = currentDest is NavDest.Stats,
                onClick = { onNavigate(NavDest.Stats) },
                tag = "side_nav_stats"
            )
            SidebarNavRow(
                icon = Icons.AutoMirrored.Rounded.QueueMusic,
                label = "Queue",
                selected = currentDest is NavDest.Queue,
                onClick = { onNavigate(NavDest.Queue) },
                tag = "side_nav_queue"
            )

            if (sleepRemainingSec != null || sleepEot || privateSession) {
                Spacer(Modifier.height(8.dp))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.padding(horizontal = 4.dp)
                ) {
                    if (sleepRemainingSec != null || sleepEot) {
                        val txt = if (sleepEot) "Sleep: EOT" else "Sleep ${SpotUiTextUtils.fmtTime(sleepRemainingSec)}"
                        Surface(
                            color = spot.raised,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.clickable(onClick = onOpenSleepTimer)
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(Icons.Rounded.Bedtime, null, tint = spot.accent, modifier = Modifier.size(13.dp))
                                Spacer(Modifier.width(4.dp))
                                Text(txt, color = spot.accent, style = MaterialTheme.typography.labelSmall)
                            }
                        }
                    }
                    if (privateSession) {
                        Surface(color = spot.raised, shape = RoundedCornerShape(8.dp)) {
                            Row(
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(Icons.Rounded.VisibilityOff, null, tint = spot.textDim, modifier = Modifier.size(13.dp))
                                Spacer(Modifier.width(4.dp))
                                Text("Private", color = spot.textDim, style = MaterialTheme.typography.labelSmall)
                            }
                        }
                    }
                }
            }

            Spacer(Modifier.height(14.dp))
            HorizontalDivider(color = spot.divider)
            Spacer(Modifier.height(10.dp))

            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = stringResource(R.string.your_library),
                    color = spot.textDim,
                    style = MaterialTheme.typography.labelLarge,
                    modifier = Modifier.weight(1f)
                )
                IconButton(
                    onClick = onCreatePlaylist,
                    modifier = Modifier.minimumInteractiveComponentSize().testTag("sidebar_create_playlist_btn")
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Add,
                        contentDescription = stringResource(R.string.cd_add_playlist),
                        tint = spot.textPrimary
                    )
                }
            }

            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(2.dp)
            ) {
                item {
                    SidebarLibraryRow(
                        label = stringResource(R.string.liked_songs),
                        subtitle = "$likedCount songs",
                        icon = Icons.Rounded.Favorite,
                        iconTint = spot.accent,
                        selected = currentDest is NavDest.Liked,
                        isActiveSource = playSource == "Liked Songs",
                        isPlaying = isPlaying,
                        reducedMotion = reducedMotion,
                        onClick = { onNavigate(NavDest.Liked) },
                        tag = "side_liked_btn"
                    )
                }
                item {
                    SidebarLibraryRow(
                        label = stringResource(R.string.recently_played),
                        subtitle = "$historyCount recent",
                        icon = Icons.Rounded.History,
                        iconTint = spot.textDim,
                        selected = currentDest is NavDest.History,
                        isActiveSource = playSource == "Recently Played",
                        isPlaying = isPlaying,
                        reducedMotion = reducedMotion,
                        onClick = { onNavigate(NavDest.History) },
                        tag = "side_history_btn"
                    )
                }
                items(playlists, key = { it.id }) { pl ->
                    SidebarLibraryRow(
                        label = pl.name,
                        subtitle = "${pl.tracks.size} songs",
                        icon = if (pl.pinned) Icons.Rounded.PushPin else Icons.Rounded.MusicNote,
                        iconTint = if (pl.pinned) spot.accent else spot.textDim,
                        selected = currentDest is NavDest.PlaylistDest && currentDest.playlistId == pl.id,
                        isActiveSource = playSource == pl.name,
                        isPlaying = isPlaying,
                        reducedMotion = reducedMotion,
                        onClick = { onNavigate(NavDest.PlaylistDest(pl.id)) },
                        tag = "side_playlist_${pl.id}"
                    )
                }
            }
        }
    }
}

@Composable
private fun SidebarNavRow(
    icon: ImageVector,
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    tag: String
) {
    val spot = LocalSpotColors.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(if (selected) spot.raised else Color.Transparent)
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 10.dp)
            .testTag(tag),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = if (selected) spot.accent else spot.textDim,
            modifier = Modifier.size(20.dp)
        )
        Spacer(Modifier.width(12.dp))
        Text(
            text = label,
            color = if (selected) spot.textPrimary else spot.textDim,
            style = MaterialTheme.typography.titleSmall,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium
        )
    }
}

@Composable
private fun SidebarLibraryRow(
    label: String,
    subtitle: String,
    icon: ImageVector,
    iconTint: Color,
    selected: Boolean,
    isActiveSource: Boolean,
    isPlaying: Boolean,
    reducedMotion: Boolean,
    onClick: () -> Unit,
    tag: String
) {
    val spot = LocalSpotColors.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(if (selected) spot.raised else Color.Transparent)
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 8.dp)
            .testTag(tag),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, null, tint = iconTint, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = label,
                color = if (isActiveSource) spot.accent else spot.textPrimary,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = subtitle,
                color = spot.textFaint,
                style = MaterialTheme.typography.labelSmall,
                maxLines = 1
            )
        }
        if (isActiveSource) {
            EqualizerBars(
                isPlaying = isPlaying,
                reducedMotion = reducedMotion,
                color = spot.accent,
                modifier = Modifier.height(14.dp)
            )
        }
    }
}

@Composable
fun SplashOverlay(
    reducedMotion: Boolean,
    onDismiss: () -> Unit
) {
    val spot = LocalSpotColors.current
    LaunchedEffect(reducedMotion) {
        if (reducedMotion) {
            onDismiss()
        } else {
            delay(1500L)
            onDismiss()
        }
    }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(spot.background)
            .clickable(onClick = onDismiss)
            .testTag("splash_overlay"),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            EqualizerBars(
                isPlaying = true,
                reducedMotion = reducedMotion,
                barCount = 5,
                color = spot.accent,
                modifier = Modifier.height(38.dp)
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(12.dp)
                        .clip(CircleShape)
                        .background(spot.accent)
                )
                Spacer(Modifier.width(12.dp))
                Text(
                    text = "S P O T U I",
                    color = spot.textPrimary,
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold
                )
            }
            Text(
                text = "your music, in your pocket",
                color = spot.textDim,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}
