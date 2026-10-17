package com.awinlink.calls

import android.content.ComponentName
import android.content.Intent
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.os.Build
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.telecom.DisconnectCause
import android.telecom.PhoneAccountHandle
import android.telecom.TelecomManager
import com.facebook.react.HeadlessJsTaskService
import com.google.firebase.messaging.RemoteMessage
import expo.modules.notifications.service.ExpoFirebaseMessagingService
import io.wazo.callkeep.Constants
import io.wazo.callkeep.RNCallKeepBackgroundMessagingService
import io.wazo.callkeep.VoiceConnectionService
import org.json.JSONObject

// Preserve Expo delivery for all ordinary notifications; only call data is intercepted.
class AwinlinkMessagingService : ExpoFirebaseMessagingService() {
  override fun onMessageReceived(message: RemoteMessage) {
    val data = try { JSONObject(message.data["body"] ?: "{}") } catch (_: Exception) { JSONObject() }
    if (data.optString("type") != "incoming_call") { super.onMessageReceived(message); return }
    val id = data.optLong("call_id", 0)
    if (id <= 0 || id > 0xffffffffffffL) return
    val uuid = "a7100000-0000-4000-8000-" + id.toString(16).padStart(12, '0')
    if (VoiceConnectionService.getConnection(uuid) != null) return
    val remaining = ((data.optDouble("expires_at", 0.0) * 1000).toLong() - System.currentTimeMillis()).coerceAtMost(30000)
    if (remaining <= 0) return
    try {
      val telecom = getSystemService(TELECOM_SERVICE) as TelecomManager
      val label = applicationInfo.loadLabel(packageManager).toString()
      val account = PhoneAccountHandle(ComponentName(this, VoiceConnectionService::class.java), label)
      if (telecom.getPhoneAccount(account)?.isEnabled != true) { showFallback(data, id, remaining); return }
      // Warm the JS bridge before the user can answer/decline the system call UI.
      val task = Intent(this, RNCallKeepBackgroundMessagingService::class.java)
      task.putExtra("callUUID", uuid)
      task.putExtra("handle", id.toString())
      task.putExtra("name", data.optString("caller_name", "Awinlink user"))
      startService(task)
      HeadlessJsTaskService.acquireWakeLockNow(applicationContext)
      val extras = Bundle().apply {
        putParcelable(TelecomManager.EXTRA_INCOMING_CALL_ADDRESS, Uri.fromParts("tel", id.toString(), null))
        putString(Constants.EXTRA_CALL_UUID, uuid)
        putString(Constants.EXTRA_CALLER_NAME, data.optString("caller_name", "Awinlink user"))
        putString(Constants.EXTRA_HAS_VIDEO, (data.optString("call_type") == "VIDEO").toString())
      }
      telecom.addNewIncomingCall(account, extras)
      Handler(Looper.getMainLooper()).postDelayed({
        VoiceConnectionService.getConnection(uuid)?.let { connection ->
          if (connection.state == android.telecom.Connection.STATE_RINGING) {
            connection.setDisconnected(DisconnectCause(DisconnectCause.MISSED))
            connection.destroy()
          }
        }
      }, remaining)
    } catch (_: Exception) { showFallback(data, id, remaining) }
  }

  private fun showFallback(data: JSONObject, id: Long, remaining: Long) {
    val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
    if (Build.VERSION.SDK_INT >= 26) manager.createNotificationChannel(NotificationChannel("incoming-calls", "Incoming calls", NotificationManager.IMPORTANCE_HIGH))
    val uri = Uri.parse("awinlink://call/$id").buildUpon().appendQueryParameter("mode", "incoming")
      .appendQueryParameter("callType", data.optString("call_type", "VOICE"))
      .appendQueryParameter("conversationId", data.optString("conversation_id")).build()
    val intent = Intent(Intent.ACTION_VIEW, uri).setPackage(packageName).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    val pending = PendingIntent.getActivity(this, id.toInt(), intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, "incoming-calls") else Notification.Builder(this)
    val notification = builder.setSmallIcon(applicationInfo.icon).setContentTitle("Incoming Awinlink call")
      .setContentText(data.optString("caller_name", "Awinlink user")).setCategory(Notification.CATEGORY_CALL)
      .setContentIntent(pending).setAutoCancel(true).build()
    try { manager.notify(id.toInt(), notification) } catch (_: SecurityException) { return }
    Handler(Looper.getMainLooper()).postDelayed({ manager.cancel(id.toInt()) }, remaining)
  }
}
