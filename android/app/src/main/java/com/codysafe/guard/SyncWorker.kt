package com.codysafe.guard

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.util.concurrent.TimeUnit

class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val store = Store(applicationContext)
        if (store.token.isEmpty()) return@withContext Result.success()
        try {
            Sync.uploadNewFiles(applicationContext, store)
            Sync.checkAlerts(applicationContext, store)
            Result.success()
        } catch (e: IOException) {
            Result.retry()
        }
    }

    companion object {
        private val NETWORK = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        /** 안드로이드의 주기 작업 최소 간격은 15분입니다. */
        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES).setConstraints(NETWORK).build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork("guard-sync", ExistingPeriodicWorkPolicy.KEEP, request)
        }

        fun runNow(context: Context) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>().setConstraints(NETWORK).build()
            WorkManager.getInstance(context).enqueueUniqueWork("guard-now", ExistingWorkPolicy.REPLACE, request)
        }
    }
}
