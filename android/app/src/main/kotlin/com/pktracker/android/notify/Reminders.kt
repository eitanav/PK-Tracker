package com.pktracker.android.notify

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.pktracker.android.R
import com.pktracker.android.nextTimeMs
import com.pktracker.android.toProfile
import com.pktracker.android.data.AppDatabase
import com.pktracker.android.data.AppSettings
import com.pktracker.android.data.SettingsStore
import com.pktracker.android.data.toDose
import com.pktracker.engine.Scheduler
import com.pktracker.engine.Substance
import com.pktracker.engine.SubstanceTimeline
import com.pktracker.engine.Substances
import com.pktracker.engine.UserProfile
import kotlinx.coroutines.flow.first
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit

/**
 * Smart reminders: opt-in, model-driven nudges. Each fires only when the
 * pharmacokinetic model says there's a real decision to make right now —
 * never on a fixed schedule — so they stay worth reading.
 */
object Reminders {
    const val CHANNEL_ID = "smart_reminders"
    private const val WORK_NAME = "pk_smart_reminders"
    private const val NOTIF_ID = 4201
    private const val H_MS = 3_600_000.0
    private val clock: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

    private class Reminder(val kind: String, val title: String, val body: String)

    fun schedule(context: Context) {
        val req = PeriodicWorkRequestBuilder<ReminderWorker>(20, TimeUnit.MINUTES).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, req)
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
    }

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                CHANNEL_ID, context.getString(R.string.reminders_channel), NotificationManager.IMPORTANCE_DEFAULT,
            ).apply { description = context.getString(R.string.reminders_channel_desc) }
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
    }

    suspend fun fireIfDue(context: Context) {
        val store = SettingsStore(context)
        val s = store.flow.first()
        val r = computeReminder(context, s) ?: return
        post(context, r)
        val now = System.currentTimeMillis()
        store.update {
            when (r.kind) {
                "cutoff" -> reminderLastCutoffMs(now)
                "redose" -> reminderLastRedoseMs(now)
            }
        }
    }

    private fun effTargetMg(s: AppSettings): Int =
        if (s.sleepMode == "preset") (Scheduler.SLEEP_SENSITIVITY_MG[s.sleepSensitivity] ?: 50.0).toInt() else s.sleepMg

    private fun caffeineCutoffMs(tl: SubstanceTimeline, sub: Substance, profile: UserProfile, s: AppSettings, nowMs: Long): Long? {
        val bedtimeMs = nextTimeMs(nowMs, s.bedtime)
        val bedtimeH = bedtimeMs / H_MS
        val nowH = nowMs / H_MS
        val res = if (s.sleepMode == "hours") {
            Scheduler.sleepCutoffHours(tl, nowH, bedtimeH, s.sleepHours.toDouble())
        } else {
            val v = sub.volumeLiters(profile.bodyMassKg)
            val t = effTargetMg(s).toDouble()
            Scheduler.sleepCutoff(tl, nowH, bedtimeH, absoluteTarget = if (v > 0) t / v else null)
        }
        return if (res.feasible) res.cutoffAtHours?.let { (it * H_MS).toLong() } else null
    }

    private suspend fun computeReminder(context: Context, s: AppSettings): Reminder? {
        if (!s.remindersEnabled) return null
        val zone = ZoneId.systemDefault()
        val nowMs = System.currentTimeMillis()
        val nowZ = Instant.ofEpochMilli(nowMs).atZone(zone)
        if (nowZ.hour < 7 || nowZ.hour >= 23) return null  // quiet hours

        val doses = AppDatabase.get(context).doseDao().allOnce().map { it.toDose() }
        val caffeine = Substances.caffeine
        val profile = s.toProfile()
        val tl = SubstanceTimeline(caffeine, doses, profile)
        val nowH = nowMs / H_MS
        val today = nowZ.toLocalDate()

        val activeCaffeine = doses.any { it.substanceId == "caffeine" && nowMs - it.takenAtEpochMs in 0..(16 * 3_600_000L) }
        val cutoffMs = caffeineCutoffMs(tl, caffeine, profile, s, nowMs)

        // A. Last coffee before the sleep cutoff — the one you asked for.
        if (activeCaffeine && cutoffMs != null) {
            val minsToCutoff = (cutoffMs - nowMs) / 60_000L
            if (minsToCutoff in 0..45) {
                val lastDay = if (s.reminderLastCutoffMs > 0)
                    Instant.ofEpochMilli(s.reminderLastCutoffMs).atZone(zone).toLocalDate() else null
                if (lastDay != today) {
                    val hhmm = clock.format(Instant.ofEpochMilli(cutoffMs).atZone(zone))
                    return Reminder(
                        "cutoff",
                        context.getString(R.string.reminder_cutoff_title),
                        context.getString(R.string.reminder_cutoff_body, hhmm),
                    )
                }
            }
        }

        // B. Redose window open (focus dip) — but never nudge caffeine past the cutoff.
        val ri = Scheduler.redoseInfo(tl, nowH)
        if (ri.overdue && (cutoffMs == null || nowMs < cutoffMs)) {
            if (nowMs - s.reminderLastRedoseMs > 3 * 3_600_000L) {
                return Reminder(
                    "redose",
                    context.getString(R.string.reminder_redose_title),
                    context.getString(R.string.reminder_redose_body),
                )
            }
        }
        return null
    }

    private fun post(context: Context, r: Reminder) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        ensureChannel(context)
        val open = context.packageManager.getLaunchIntentForPackage(context.packageName)
        val pi = open?.let {
            PendingIntent.getActivity(
                context, 0, it,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
        }
        val notif = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_pk)
            .setContentTitle(r.title)
            .setContentText(r.body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(r.body))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()
        NotificationManagerCompat.from(context).notify(NOTIF_ID, notif)
    }
}
