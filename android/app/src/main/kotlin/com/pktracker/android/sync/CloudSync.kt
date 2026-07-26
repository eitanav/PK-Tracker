package com.pktracker.android.sync

import android.content.Context
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.CollectionReference
import com.google.firebase.firestore.DocumentSnapshot
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.ListenerRegistration
import com.pktracker.android.data.AppDatabase
import com.pktracker.android.data.DoseDao
import com.pktracker.android.data.DoseEntity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

/**
 * Cross-device sync of the dose log via Firestore.
 *
 * Model: `users/{uid}/doses/{doseUid}`. Merge is last-write-wins by [DoseEntity.updatedAt]
 * and honours soft-deletes (a `deleted = true` doc removes the row everywhere).
 * Uses anonymous auth for now — a Google sign-in can be linked to the same uid
 * later without losing data. Built for many users: a device only ever touches
 * its own uid, enforced by the Firestore security rules.
 */
object CloudSync {
    @Volatile private var active = false
    private var registration: ListenerRegistration? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    fun isActive(): Boolean = active

    private fun doses(uid: String): CollectionReference =
        FirebaseFirestore.getInstance().collection("users").document(uid).collection("doses")

    private fun toMap(d: DoseEntity): Map<String, Any> = mapOf(
        "substanceId" to d.substanceId,
        "amount" to d.amount,
        "unit" to d.unit,
        "takenAtEpochMs" to d.takenAtEpochMs,
        "note" to d.note,
        "deleted" to d.deleted,
        "updatedAt" to d.updatedAt,
    )

    /** Sign in, reconcile with the cloud once, then keep listening for remote changes. */
    fun start(context: Context) {
        if (active) return
        val app = context.applicationContext
        scope.launch {
            try {
                val uid = signedInUid() ?: return@launch
                val dao = AppDatabase.get(app).doseDao()
                reconcile(dao, doses(uid))
                active = true
                // Keep merging remote changes as they arrive.
                registration = doses(uid).addSnapshotListener { snap, _ ->
                    if (snap == null) return@addSnapshotListener
                    scope.launch {
                        for (change in snap.documentChanges) mergeRemote(dao, change.document)
                    }
                }
            } catch (e: Exception) {
                active = false
            }
        }
    }

    /**
     * Reconcile with the cloud and *wait for it to finish*, so a pull-to-refresh
     * can keep its spinner up for exactly as long as the work takes. Returns
     * true when the round trip succeeded.
     */
    suspend fun refreshNow(context: Context): Boolean {
        val app = context.applicationContext
        return try {
            val uid = signedInUid() ?: return false
            reconcile(AppDatabase.get(app).doseDao(), doses(uid))
            true
        } catch (e: Exception) {
            false
        }
    }

    private suspend fun signedInUid(): String? {
        val auth = FirebaseAuth.getInstance()
        if (auth.currentUser == null) auth.signInAnonymously().await()
        return auth.currentUser?.uid
    }

    /** Pull the cloud in (last-write-wins), then push what it is missing. */
    private suspend fun reconcile(dao: DoseDao, col: CollectionReference) {
        val remote = col.get().await()
        val remoteUpdatedAt = HashMap<String, Long>()
        for (doc in remote.documents) {
            remoteUpdatedAt[doc.id] = doc.getLong("updatedAt") ?: 0L
            mergeRemote(dao, doc)
        }
        for (d in dao.allForSync()) {
            if (d.uid.isEmpty()) continue
            val ru = remoteUpdatedAt[d.uid]
            if (ru == null || d.updatedAt > ru) col.document(d.uid).set(toMap(d)).await()
        }
    }

    fun stop() {
        registration?.remove()
        registration = null
        active = false
    }

    /** Push local rows after a dose is logged/removed. No-op unless sync is live. */
    fun pushLocalChanges(context: Context) {
        if (!active) return
        val app = context.applicationContext
        scope.launch {
            try {
                val uid = FirebaseAuth.getInstance().currentUser?.uid ?: return@launch
                val dao = AppDatabase.get(app).doseDao()
                val col = doses(uid)
                for (d in dao.allForSync()) {
                    if (d.uid.isNotEmpty()) col.document(d.uid).set(toMap(d)).await()
                }
            } catch (_: Exception) {
            }
        }
    }

    private suspend fun mergeRemote(dao: DoseDao, doc: DocumentSnapshot) {
        val uid = doc.id
        val substanceId = doc.getString("substanceId") ?: return
        val updatedAt = doc.getLong("updatedAt") ?: return
        val existing = dao.byUid(uid)
        if (existing != null && existing.updatedAt >= updatedAt) return
        val entity = DoseEntity(
            id = existing?.id ?: 0L,
            uid = uid,
            substanceId = substanceId,
            amount = doc.getDouble("amount") ?: 0.0,
            unit = doc.getString("unit") ?: "mg",
            takenAtEpochMs = doc.getLong("takenAtEpochMs") ?: 0L,
            note = doc.getString("note") ?: "",
            deleted = doc.getBoolean("deleted") ?: false,
            updatedAt = updatedAt,
        )
        if (existing == null) dao.insert(entity) else dao.update(entity)
    }
}
