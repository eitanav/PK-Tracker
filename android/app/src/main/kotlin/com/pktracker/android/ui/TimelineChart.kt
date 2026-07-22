package com.pktracker.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.pktracker.android.CurveData
import com.pktracker.android.ui.theme.Accent
import com.pktracker.android.ui.theme.Blue
import com.pktracker.android.ui.theme.Warn
import java.util.Locale

private fun interp(xs: DoubleArray, ys: DoubleArray, x: Double): Double {
    if (xs.isEmpty()) return 0.0
    if (x <= xs.first()) return ys.first()
    if (x >= xs.last()) return ys.last()
    var i = 1
    while (i < xs.size && xs[i] < x) i++
    val x0 = xs[i - 1]; val x1 = xs[i]
    val t = if (x1 == x0) 0.0 else (x - x0) / (x1 - x0)
    return ys[i - 1] + t * (ys[i] - ys[i - 1])
}

@Composable
fun TimelineChart(curve: CurveData, modifier: Modifier = Modifier, description: String? = null) {
    val onSurface = MaterialTheme.colorScheme.onSurface
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val grid = muted.copy(alpha = 0.14f)
    val panel = MaterialTheme.colorScheme.surface
    val levelColor = remember(curve.colorHex) {
        runCatching { Color(android.graphics.Color.parseColor(curve.colorHex)) }.getOrDefault(Accent)
    }
    var touchX by remember { mutableStateOf<Float?>(null) }

    Canvas(
        modifier = modifier
            .then(if (description != null) Modifier.semantics { contentDescription = description } else Modifier)
            .pointerInput(Unit) {
                detectDragGestures(
                    onDragStart = { touchX = it.x },
                    onDragEnd = { touchX = null },
                    onDragCancel = { touchX = null },
                    onDrag = { change, _ -> touchX = change.position.x; change.consume() },
                )
            }
            .pointerInput(Unit) {
                detectTapGestures(onTap = { touchX = it.x })
            },
    ) {
        if (curve.xHours.size < 2) return@Canvas

        val bottomAxis = 22.dp.toPx()
        val topPad = 16.dp.toPx()
        val sidePad = 4.dp.toPx()
        val plotLeft = sidePad
        val plotRight = size.width - sidePad
        val plotTop = topPad
        val plotBottom = size.height - bottomAxis
        val plotW = plotRight - plotLeft
        val plotH = plotBottom - plotTop

        val x0 = curve.xHours.first()
        val x1 = curve.xHours.last()
        val n = curve.xHours.size
        val span = if (x1 == x0) 1.0 else x1 - x0
        fun sx(h: Double): Float = plotLeft + ((h - x0) / span * plotW).toFloat()
        val xs = FloatArray(n) { sx(curve.xHours[it]) }
        fun mapLevel(v: Double): Float = plotBottom - (v / curve.concTop * plotH).toFloat().coerceIn(0f, plotH)
        fun mapEffect(v: Double): Float = plotBottom - (v / curve.effectTop * plotH).toFloat().coerceIn(0f, plotH)

        val dashed = PathEffect.dashPathEffect(floatArrayOf(14f, 12f), 0f)
        var nowIdx = curve.xHours.indexOfFirst { it >= curve.nowHours }
        if (nowIdx < 0) nowIdx = n - 1

        fun drawSeries(mapY: (Double) -> Float, values: DoubleArray, color: Color, fill: Boolean, width: Float) {
            val ys = FloatArray(n) { mapY(values[it]) }
            if (fill && nowIdx >= 1) {
                val area = Path().apply {
                    moveTo(xs[0], plotBottom)
                    for (i in 0..nowIdx) lineTo(xs[i], ys[i])
                    lineTo(xs[nowIdx], plotBottom)
                    close()
                }
                drawPath(area, color.copy(alpha = 0.16f))
            }
            if (nowIdx >= 1) {
                val past = Path().apply {
                    moveTo(xs[0], ys[0])
                    for (i in 1..nowIdx) lineTo(xs[i], ys[i])
                }
                drawPath(past, color, style = Stroke(width))
            }
            if (nowIdx < n - 1) {
                val fut = Path().apply {
                    moveTo(xs[nowIdx], ys[nowIdx])
                    for (i in (nowIdx + 1) until n) lineTo(xs[i], ys[i])
                }
                drawPath(fut, color, style = Stroke(width, pathEffect = dashed))
            }
        }

        for (i in 0..4) {
            val y = plotTop + plotH * i / 4
            drawLine(grid, Offset(plotLeft, y), Offset(plotRight, y), 1f)
        }

        drawSeries(::mapLevel, curve.conc, levelColor, fill = true, width = 3.2f)
        curve.effect?.let { drawSeries(::mapEffect, it, Blue, fill = false, width = 2.6f) }
        curve.simConc?.let { drawSeries(::mapLevel, it, Warn, fill = false, width = 2.6f) }
        curve.simEffect?.let { drawSeries(::mapEffect, it, Warn, fill = false, width = 2.0f) }

        val nx = sx(curve.nowHours)
        drawLine(muted, Offset(nx, plotTop), Offset(nx, plotBottom), 1.4f, pathEffect = dashed)

        val axisPaint = android.graphics.Paint().apply {
            color = muted.toArgb(); textSize = 11.dp.toPx(); isAntiAlias = true
            textAlign = android.graphics.Paint.Align.CENTER
        }
        for (i in 0..4) {
            val h = x0 + span * i / 4
            drawContext.canvas.nativeCanvas.drawText(fmtClockHours(h), sx(h), size.height - 6.dp.toPx(), axisPaint)
        }

        touchX?.let { raw ->
            val clamped = raw.coerceIn(plotLeft, plotRight)
            val h = x0 + (clamped - plotLeft) / plotW * span
            drawLine(onSurface.copy(alpha = 0.55f), Offset(clamped, plotTop), Offset(clamped, plotBottom), 1.2f)
            val lvl = interp(curve.xHours, curve.conc, h)
            val eff = curve.effect?.let { interp(curve.xHours, it, h) }
            val lines = buildList {
                add(fmtClockHours(h))
                add(String.format(Locale.US, "%.2f %s", lvl, curve.concUnit))
                if (eff != null) add("${eff.toInt()}%")
            }
            val textPaint = android.graphics.Paint().apply {
                color = onSurface.toArgb(); textSize = 11.dp.toPx(); isAntiAlias = true
            }
            val bgPaint = android.graphics.Paint().apply { color = panel.toArgb(); isAntiAlias = true }
            val pad = 6.dp.toPx()
            val lineH = 14.dp.toPx()
            val boxW = 82.dp.toPx()
            val boxH = lineH * lines.size + pad
            val boxX = (clamped + 8.dp.toPx()).coerceAtMost(plotRight - boxW)
            val boxY = plotTop
            drawContext.canvas.nativeCanvas.drawRoundRect(boxX, boxY, boxX + boxW, boxY + boxH, 8f, 8f, bgPaint)
            var ty = boxY + lineH
            for (ln in lines) {
                drawContext.canvas.nativeCanvas.drawText(ln, boxX + pad, ty, textPaint)
                ty += lineH
            }
        }
    }
}
