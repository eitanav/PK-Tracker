package com.pktracker.android.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pktracker.android.R
import com.pktracker.android.ui.theme.Accent
import com.pktracker.android.ui.theme.Blue
import com.pktracker.android.ui.theme.Danger
import com.pktracker.android.ui.theme.Good
import com.pktracker.android.ui.theme.Warn
import com.pktracker.engine.Substance
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val clockFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

fun fmtClock(ms: Long?): String =
    if (ms == null) "—" else Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).format(clockFmt)

fun fmtClockHours(hours: Double): String = fmtClock((hours * 3_600_000.0).toLong())

fun fmtDelta(ms: Long): String {
    val total = (ms / 1000).coerceAtLeast(0)
    val h = total / 3600
    val m = (total % 3600) / 60
    return when {
        h > 0 && m > 0 -> "${h}h ${m}m"
        h > 0 -> "${h}h"
        else -> "${m}m"
    }
}

fun sinceLabel(sinceMs: Long?, nowMs: Long): String =
    if (sinceMs == null) "—" else fmtDelta(nowMs - sinceMs)

@Composable
fun colorForKey(key: String?): Color = when (key) {
    "accent" -> Accent
    "warn" -> Warn
    "danger" -> Danger
    "good" -> Good
    "muted" -> MaterialTheme.colorScheme.onSurfaceVariant
    else -> MaterialTheme.colorScheme.onSurface
}

/** Localised, brand-forward display name for a built-in substance. */
@Composable
fun substanceName(sub: Substance): String {
    val res = when (sub.id) {
        "caffeine" -> R.string.sub_caffeine
        "methylphenidate" -> R.string.sub_methylphenidate
        "methylphenidate_er" -> R.string.sub_methylphenidate_er
        "lisdexamfetamine" -> R.string.sub_lisdexamfetamine
        "mixed_amphetamine_salts" -> R.string.sub_mixed_amphetamine_salts
        "amphetamine_xr" -> R.string.sub_amphetamine_xr
        "alcohol" -> R.string.sub_alcohol
        else -> null
    }
    return if (res != null) stringResource(res) else sub.name
}

@Composable
fun SectionCard(
    title: String? = null,
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(20.dp),
        shadowElevation = 2.dp,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f)),
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            if (title != null) {
                Text(
                    title.uppercase(),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = 0.8.sp,
                )
                Spacer(Modifier.height(10.dp))
            }
            content()
        }
    }
}
