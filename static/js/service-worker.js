self.addEventListener("push", (event) => {
    let notification = {};

    try {
        notification = event.data ? event.data.json() : {};
    } catch (error) {
        notification = {
            title: "Awinlink",
            body: event.data ? event.data.text() : "You have a new notification.",
        };
    }

    event.waitUntil((async () => {
        const windows = await self.clients.matchAll({
            type: "window",
            includeUncontrolled: true,
        });
        const visibleWindow = windows.find((client) => client.visibilityState === "visible");

        if (visibleWindow) {
            visibleWindow.postMessage({
                type: "awinlink:push-notification",
                notification,
            });
            return;
        }

        await self.registration.showNotification(notification.title || "Awinlink", {
            body: notification.body || "You have a new notification.",
            tag: notification.tag || "awinlink-notification",
            icon: "/static/img/awinlink-app.svg",
            badge: "/static/img/awinlink-app.svg",
            silent: false,
            vibrate: [120, 80, 120],
            data: { url: notification.url || "/notifications/" },
        });
    })());
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const target = event.notification.data && event.notification.data.url;
    const url = typeof target === "string" && target.startsWith("/") && !target.startsWith("//")
        ? new URL(target, self.location.origin).href
        : new URL("/notifications/", self.location.origin).href;

    event.waitUntil((async () => {
        const windows = await self.clients.matchAll({
            type: "window",
            includeUncontrolled: true,
        });
        const existing = windows.find((client) => client.url.startsWith(self.location.origin));

        if (existing) {
            await existing.focus();
            if ("navigate" in existing && existing.url !== url) {
                await existing.navigate(url);
            }
            return;
        }

        await self.clients.openWindow(url);
    })());
});