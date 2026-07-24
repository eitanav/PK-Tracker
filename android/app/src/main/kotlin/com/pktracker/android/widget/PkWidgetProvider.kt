package com.pktracker.android.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import com.pktracker.android.R
import com.pktracker.android.data.AppDatabase
import com.pktracker.android.data.SettingsStore
import com.pktracker.android.data.toDose
import com.pktracker.android.toProfile
import com.pktracker.android.ui.fmtDelta
import com.pktracker.engine.Substances
import com.pktracker.engine.SubstanceTimeline
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.util.Locale
import kotlin.math.roundToInt

/**
 * Home-screen widget for the active substance. Renders the current in-body
 * level (or concentration), its unit and a short "since last dose" line, and
 * re-tints itself to the substance's colour. Tapping it opens the app.
 *
 * Everything is computed by reusing the app's existing infrastructure (Room
 * dose log, DataStore settings, the pure engine timeline) — no PK maths is
 * duplicated here.
 */
class PkWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(context: Context, mgr: AppWidgetManager, ids: IntArray) {
        // Room + DataStore reads are suspending, so hop off the main thread and
        // keep the broadcast alive until every widget id has been rendered.
        val pending = goAsync()
        val appContext = context.applicationContext
        CoroutineScope(Dispatchers.Default).launch {
            try {
                val data = computeData(appContext)
                for (id in ids) {
                    mgr.updateAppWidget(id, buildViews(appContext, data))
                }
            } finally {
                pending.finish()
            }
        }
    }

    private class WidgetData(
        val subName: String,
        val levelText: String,
        val accentColor: Int,
        val statusText: String,
    )

    private suspend fun computeData(context: Context): WidgetData {
        val doses = AppDatabase.get(context).doseDao().allOnce().map { it.toDose() }
        val settings = SettingsStore(context).flow.first()
        val profile = settings.toProfile()
        val sub = Substances.byId(settings.activeSubstanceId) ?: Substances.caffeine

        val nowMs = System.currentTimeMillis()
        val nowH = nowMs / 3_600_000.0
        val tl = SubstanceTimeline(sub, doses, profile)

        val levelText = if (!sub.isAlcohol && sub.vLPerKg != null) {
            "${tl.bodyAmountAt(nowH).roundToInt()} ${context.getString(R.string.mg)}"
        } else {
            "${fmtLevel(tl.concentrationAt(nowH) * sub.concScale)} ${sub.concUnit}"
        }

        val accent = runCatching { android.graphics.Color.parseColor(sub.color) }
            .getOrDefault(0xFFD6A04A.toInt())

        val last = tl.lastDose()
        val statusText = if (last == null) {
            context.getString(R.string.widget_no_doses)
        } else {
            context.getString(R.string.widget_since_last, fmtDelta(nowMs - last.takenAtEpochMs))
        }

        val subName = subNameRes(sub.id).let { if (it != 0) context.getString(it) else sub.name }
        return WidgetData(subName, levelText, accent, statusText)
    }

    private fun buildViews(context: Context, data: WidgetData): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.pk_widget)
        views.setTextViewText(R.id.widget_sub, data.subName)
        views.setTextViewText(R.id.widget_level, data.levelText)
        views.setTextColor(R.id.widget_level, data.accentColor)
        views.setTextViewText(R.id.widget_status, data.statusText)

        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
        if (launch != null) {
            val pi = PendingIntent.getActivity(context, 0, launch, PendingIntent.FLAG_IMMUTABLE)
            views.setOnClickPendingIntent(R.id.widget_root, pi)
        }
        return views
    }

    companion object {
        /** Format a scaled concentration so small (BAC-like) and large values both read cleanly. */
        private fun fmtLevel(v: Double): String = when {
            v >= 100 -> v.roundToInt().toString()
            v >= 1 -> String.format(Locale.US, "%.1f", v)
            else -> String.format(Locale.US, "%.3f", v)
        }

        /** Localised, brand-forward name for a built-in substance (mirror of ui.substanceName). */
        private fun subNameRes(id: String): Int = when (id) {
            "caffeine" -> R.string.sub_caffeine
            "methylphenidate" -> R.string.sub_methylphenidate
            "methylphenidate_er" -> R.string.sub_methylphenidate_er
            "lisdexamfetamine" -> R.string.sub_lisdexamfetamine
            "mixed_amphetamine_salts" -> R.string.sub_mixed_amphetamine_salts
            "amphetamine_xr" -> R.string.sub_amphetamine_xr
            "alcohol" -> R.string.sub_alcohol
            else -> 0
        }

        /**
         * Push a fresh render to every placed instance of this widget. Call after
         * a dose is logged/removed so the widget reflects it without waiting for
         * the periodic update.
         */
        fun refresh(context: Context) {
            val mgr = AppWidgetManager.getInstance(context)
            val ids = mgr.getAppWidgetIds(ComponentName(context, PkWidgetProvider::class.java))
            if (ids.isEmpty()) return
            val intent = Intent(context, PkWidgetProvider::class.java).apply {
                action = AppWidgetManager.ACTION_APPWIDGET_UPDATE
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids)
            }
            context.sendBroadcast(intent)
        }
    }
}
