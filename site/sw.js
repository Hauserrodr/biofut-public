// BioFut notifications: the server sends {title, body, url} (push.py); a tap opens that page of the site
self.addEventListener("push", e => {
  const m = e.data ? e.data.json() : {};
  e.waitUntil(self.registration.showNotification(m.title || "BioFut", {body: m.body || "", icon: "/logo.png", badge: "/logo.png", data: {url: m.url || "/"}}));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data.url));
});
