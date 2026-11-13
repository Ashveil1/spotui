package com.example.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.example.data.model.SpotTheme

@Immutable
data class SpotColors(
    val theme: SpotTheme = SpotTheme.SPOTIFY,
    val accent: Color = SpotTheme.SPOTIFY.accent,
    val background: Color = SpotTheme.SPOTIFY.background,
    val sidebar: Color = Color(8, 8, 8),
    val playerBar: Color = Color(14, 14, 14),
    val hover: Color = SpotTheme.SPOTIFY.hover,
    val raised: Color = SpotTheme.SPOTIFY.raised,
    val avatar: Color = SpotTheme.SPOTIFY.avatar,
    val textPrimary: Color = Color(245, 245, 245),
    val textDim: Color = Color(179, 179, 179),
    val textFaint: Color = Color(130, 130, 130),
    val divider: Color = Color(42, 42, 42),
    val onAccent: Color = Color(10, 10, 10)
)

val LocalSpotColors = staticCompositionLocalOf { SpotColors() }

private val SpotShapes = Shapes(
    small = RoundedCornerShape(6.dp),
    medium = RoundedCornerShape(10.dp),
    large = RoundedCornerShape(14.dp),
    extraLarge = RoundedCornerShape(20.dp)
)

fun buildSpotColors(theme: SpotTheme): SpotColors {
    val bg = theme.background
    val sidebar = Color(
        red = (bg.red * 0.48f).coerceIn(0f, 1f),
        green = (bg.green * 0.48f).coerceIn(0f, 1f),
        blue = (bg.blue * 0.48f).coerceIn(0f, 1f)
    )
    val playerBar = Color(
        red = (bg.red * 0.72f).coerceIn(0f, 1f),
        green = (bg.green * 0.72f).coerceIn(0f, 1f),
        blue = (bg.blue * 0.72f).coerceIn(0f, 1f)
    )
    return SpotColors(
        theme = theme,
        accent = theme.accent,
        background = theme.background,
        sidebar = sidebar,
        playerBar = playerBar,
        hover = theme.hover,
        raised = theme.raised,
        avatar = theme.avatar
    )
}

@Composable
fun SpotUiTheme(
    spotTheme: SpotTheme = SpotTheme.SPOTIFY,
    content: @Composable () -> Unit
) {
    val spotColors = buildSpotColors(spotTheme)
    val colorScheme = darkColorScheme(
        primary = spotColors.accent,
        onPrimary = spotColors.onAccent,
        primaryContainer = spotColors.raised,
        onPrimaryContainer = spotColors.accent,
        secondary = spotColors.accent,
        onSecondary = spotColors.onAccent,
        background = spotColors.background,
        onBackground = spotColors.textPrimary,
        surface = spotColors.hover,
        onSurface = spotColors.textPrimary,
        surfaceVariant = spotColors.raised,
        onSurfaceVariant = spotColors.textDim,
        outline = spotColors.divider,
        error = Color(239, 68, 68),
        onError = Color.White
    )
    CompositionLocalProvider(LocalSpotColors provides spotColors) {
        MaterialTheme(
            colorScheme = colorScheme,
            typography = SpotUiTypography,
            shapes = SpotShapes,
            content = content
        )
    }
}
