(() => {
    const prompt = document.getElementById("notificationPermissionPrompt");
    const message = document.getElementById("notificationPromptMessage");
    const title = document.getElementById("notificationPromptTitle");
    const enableButton = document.getElementById("enableNotificationsButton");
    const dismissButton = document.getElementById("dismissNotificationsButton");
    const seenNotifications = new Set();
    let serviceWorkerRegistration = null;
    let audioContext = null;

    if (!prompt) return;

    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
    const isStandalone = navigator.standalone === true
        || window.matchMedia("(display-mode: standalone)").matches;
    const canPush = "serviceWorker" in navigator
        && "PushManager" in window
        && "Notification" in window;
    const dismissed = () => sessionStorage.getItem("awinlink-notifications-dismissed") === "yes";

    function getAudioContext() {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return null;
        audioContext = audioContext || new AudioContextClass();
        return audioContext;
    }

    function showPrompt() {
        prompt.hidden = false;
    }

    function base64ToBytes(value) {
        const padded = `${value}${"=".repeat((4 - value.length % 4) % 4)}`;
        const decoded = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
        return Uint8Array.from(decoded, (character) => character.charCodeAt(0));
    }

    function csrfToken() {
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    async function getPushConfig() {
        const response = await fetch("/notifications/push/config/", {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error("Unable to load notification settings.");
        return response.json();
    }

    async function saveSubscription(subscription, action = "subscribe") {
        const response = await fetch("/notifications/push/subscriptions/", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
            },
            body: JSON.stringify({
                action,
                endpoint: subscription.endpoint,
                keys: subscription.toJSON().keys,
            }),
        });
        if (!response.ok) throw new Error("Unable to save this device for notifications.");
    }

    async function registerPush(config) {
        if (!config.configured || !config.public_key) return false;

        serviceWorkerRegistration = await navigator.serviceWorker.register("/service-worker.js", {
            scope: "/",
        });
        await navigator.serviceWorker.ready;

        let subscription = await serviceWorkerRegistration.pushManager.getSubscription();
        if (!subscription) {
            subscription = await serviceWorkerRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: base64ToBytes(config.public_key),
            });
        }

        await saveSubscription(subscription);
        return true;
    }

    function playNotificationSound() {
        if (localStorage.getItem("awinlink-notification-sound") === "off") return;

        try {
            audioContext = getAudioContext();
            if (!audioContext) return;
            if (audioContext.state === "suspended") audioContext.resume();

            const start = audioContext.currentTime;
            [880, 1175].forEach((frequency, index) => {
                const oscillator = audioContext.createOscillator();
                const gain = audioContext.createGain();
                const noteStart = start + index * 0.13;

                oscillator.type = "sine";
                oscillator.frequency.setValueAtTime(frequency, noteStart);
                gain.gain.setValueAtTime(0.001, noteStart);
                gain.gain.exponentialRampToValueAtTime(0.11, noteStart + 0.025);
                gain.gain.exponentialRampToValueAtTime(0.001, noteStart + 0.12);
                oscillator.connect(gain);
                gain.connect(audioContext.destination);
                oscillator.start(noteStart);
                oscillator.stop(noteStart + 0.13);
            });
        } catch (error) {
            console.warn("Unable to play notification sound:", error);
        }
    }

    async function showForegroundNotification(notification) {
        if (!notification || !notification.id || seenNotifications.has(notification.id)) return;
        seenNotifications.add(notification.id);
        if (seenNotifications.size > 100) seenNotifications.delete(seenNotifications.values().next().value);

        playNotificationSound();

        if (document.visibilityState !== "visible" || Notification.permission !== "granted") return;

        try {
            serviceWorkerRegistration = serviceWorkerRegistration
                || await navigator.serviceWorker.ready;
            await serviceWorkerRegistration.showNotification(notification.title || "Awinlink", {
                body: notification.body || "You have a new notification.",
                tag: notification.tag || `awinlink-notification-${notification.id}`,
                icon: "/static/img/awinlink-app.svg",
                badge: "/static/img/awinlink-app.svg",
                silent: false,
                vibrate: [120, 80, 120],
                data: { url: notification.url || "/notifications/" },
            });
        } catch (error) {
            console.warn("Unable to show browser notification:", error);
        }
    }

    window.addEventListener("awinlink:notification", (event) => {
        showForegroundNotification(event.detail);
    });

    navigator.serviceWorker?.addEventListener("message", (event) => {
        if (event.data?.type === "awinlink:push-notification") {
            showForegroundNotification(event.data.notification);
        }
    });

    dismissButton?.addEventListener("click", () => {
        sessionStorage.setItem("awinlink-notifications-dismissed", "yes");
        prompt.hidden = true;
    });

    enableButton?.addEventListener("click", async () => {
        enableButton.disabled = true;
        enableButton.textContent = "Enabling...";

        try {
            audioContext = getAudioContext();
            if (audioContext) await audioContext.resume();

            const permission = await Notification.requestPermission();
            if (permission !== "granted") {
                title.textContent = "Notifications are off";
                message.textContent = "Allow notifications for Awinlink in your browser or device settings to receive message and call alerts.";
                enableButton.hidden = true;
                return;
            }

            const config = await getPushConfig();
            const saved = await registerPush(config);
            if (!saved) {
                title.textContent = "Alerts need setup";
                message.textContent = "Browser permission is on, but device delivery is not configured on this site yet.";
                enableButton.hidden = true;
                return;
            }

            localStorage.setItem("awinlink-notification-sound", "on");
            playNotificationSound();
            prompt.hidden = true;
        } catch (error) {
            title.textContent = "Could not enable alerts";
            message.textContent = error.message || "Please try again in a moment.";
            enableButton.disabled = false;
            enableButton.textContent = "Try again";
        }
    });

    async function initialize() {
        if (!canPush) return;

        const config = await getPushConfig().catch(() => ({ configured: false }));
        const permission = Notification.permission;

        if (permission === "granted" && config.configured) {
            registerPush(config).catch((error) => {
                console.warn("Unable to restore push subscription:", error);
            });
            return;
        }

        if (dismissed()) return;

        if (isIOS && !isStandalone) {
            title.textContent = "Add Awinlink to your Home Screen";
            message.textContent = "On iPhone and iPad, install Awinlink to your Home Screen before enabling alerts.";
            enableButton.hidden = true;
            showPrompt();
            return;
        }

        if (permission === "denied") {
            title.textContent = "Notifications are blocked";
            message.textContent = "Allow Awinlink notifications in your browser or device settings to receive message and call alerts.";
            enableButton.hidden = true;
            showPrompt();
            return;
        }

        if (!config.configured) {
            message.textContent = "Device notifications are not available until this site finishes its push setup.";
            enableButton.disabled = true;
            enableButton.textContent = "Not available yet";
        }

        showPrompt();
    }

    const soundToggle = document.getElementById("notificationSoundToggle");
    if (soundToggle) {
        soundToggle.checked = localStorage.getItem("awinlink-notification-sound") !== "off";
        soundToggle.addEventListener("change", () => {
            localStorage.setItem(
                "awinlink-notification-sound",
                soundToggle.checked ? "on" : "off"
            );
            if (soundToggle.checked) {
                audioContext = getAudioContext();
                audioContext?.resume().then(playNotificationSound);
            }
        });
    }

    initialize();
})();