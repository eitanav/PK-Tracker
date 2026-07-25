package com.pktracker.android.sync

import android.content.Context
import android.content.Intent
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthUserCollisionException
import com.google.firebase.auth.GoogleAuthProvider
import com.pktracker.android.R
import kotlinx.coroutines.tasks.await

/**
 * Google sign-in on top of the anonymous Firebase user. Linking (rather than a
 * plain sign-in) keeps the anonymous account's data — so nothing logged before
 * signing in is lost. If the Google account is already a separate Firebase user
 * (e.g. from another device), we sign into that one instead.
 */
object GoogleAuth {

    private fun options(context: Context): GoogleSignInOptions =
        GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestIdToken(context.getString(R.string.default_web_client_id))
            .requestEmail()
            .build()

    /** Intent to launch the Google account picker. */
    fun signInIntent(context: Context): Intent =
        GoogleSignIn.getClient(context, options(context)).signInIntent

    /** Extract the ID token from the account-picker result (null if cancelled/failed). */
    suspend fun idTokenFrom(data: Intent?): String? {
        if (data == null) return null
        return try {
            GoogleSignIn.getSignedInAccountFromIntent(data).await().idToken
        } catch (e: Exception) {
            null
        }
    }

    /** Link (or sign in) with a Google ID token. Returns the signed-in email. */
    suspend fun signInWithIdToken(idToken: String): String? {
        val cred = GoogleAuthProvider.getCredential(idToken, null)
        val auth = FirebaseAuth.getInstance()
        val current = auth.currentUser
        val result = try {
            if (current != null && current.isAnonymous) current.linkWithCredential(cred).await()
            else auth.signInWithCredential(cred).await()
        } catch (e: FirebaseAuthUserCollisionException) {
            auth.signInWithCredential(cred).await()
        }
        return result.user?.email
    }

    fun signOut(context: Context) {
        FirebaseAuth.getInstance().signOut()
        GoogleSignIn.getClient(context, options(context)).signOut()
    }

    /** The signed-in Google email, or null when only anonymous / signed out. */
    fun currentEmail(): String? =
        FirebaseAuth.getInstance().currentUser?.takeIf { !it.isAnonymous }?.email
}
