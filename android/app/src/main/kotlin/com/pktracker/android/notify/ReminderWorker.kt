package com.pktracker.android.notify

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters

/** Periodic check that lets [Reminders] decide whether a nudge is due right now. */
class ReminderWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        return try {
            Reminders.fireIfDue(applicationContext)
            Result.success()
        } catch (e: Exception) {
            Result.success()  // never retry-storm on a transient failure
        }
    }
}
