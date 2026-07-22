package com.pktracker.android.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

/**
 * A circular gauge. [fraction] (0..1) sweeps clockwise from the top and
 * animates on change. [center] is drawn in the middle.
 */
@Composable
fun Gauge(
    fraction: Float,
    color: Color,
    modifier: Modifier = Modifier,
    center: @Composable () -> Unit,
) {
    val track = MaterialTheme.colorScheme.outlineVariant
    val anim by animateFloatAsState(
        targetValue = fraction.coerceIn(0f, 1f),
        animationSpec = tween(1000),
        label = "gauge",
    )
    Box(modifier, contentAlignment = Alignment.Center) {
        Canvas(Modifier.matchParentSize()) {
            val stroke = 11.dp.toPx()
            val d = size.minDimension - stroke
            val tl = Offset((size.width - d) / 2f, (size.height - d) / 2f)
            drawArc(
                color = track, startAngle = -90f, sweepAngle = 360f, useCenter = false,
                topLeft = tl, size = Size(d, d), style = Stroke(stroke),
            )
            if (anim > 0f) drawArc(
                color = color, startAngle = -90f, sweepAngle = 360f * anim, useCenter = false,
                topLeft = tl, size = Size(d, d), style = Stroke(stroke, cap = StrokeCap.Round),
            )
        }
        center()
    }
}
