const MEDIASYNC_CACHE_NAME = "mediasync-pwa-v1";
const MEDIASYNC_STATIC_ASSETS = [
    "/static/css/app.css?v=ui-final11",
    "/static/js/app.js?v=ui-final3",
    "/static/js/ui-final.js?v=ui-final11",
    "/static/img/default.png",
    "/static/img/emby.png",
    "/static/img/jellyfin.png",
    "/static/img/plex.png",
    "/static/img/radarr-logo.png",
    "/static/img/sonarr-logo.png",
    "/manifest.webmanifest"
];

self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(MEDIASYNC_CACHE_NAME).then(function (cache) {
            return cache.addAll(MEDIASYNC_STATIC_ASSETS);
        }).catch(function () {
            return Promise.resolve();
        })
    );

    self.skipWaiting();
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (cacheNames) {
            return Promise.all(
                cacheNames.map(function (cacheName) {
                    if (cacheName !== MEDIASYNC_CACHE_NAME) {
                        return caches.delete(cacheName);
                    }

                    return Promise.resolve();
                })
            );
        })
    );

    self.clients.claim();
});

self.addEventListener("fetch", function (event) {
    const request = event.request;
    const url = new URL(request.url);

    if (request.method !== "GET") {
        return;
    }

    if (url.origin !== self.location.origin) {
        return;
    }

    if (
        url.pathname.startsWith("/api") ||
        url.pathname === "/login" ||
        url.pathname === "/logout" ||
        url.pathname === "/auth/setup"
    ) {
        return;
    }

    if (
        url.pathname.startsWith("/static/") ||
        url.pathname === "/manifest.webmanifest"
    ) {
        event.respondWith(
            caches.match(request).then(function (cachedResponse) {
                if (cachedResponse) {
                    return cachedResponse;
                }

                return fetch(request).then(function (networkResponse) {
                    const responseClone = networkResponse.clone();

                    caches.open(MEDIASYNC_CACHE_NAME).then(function (cache) {
                        cache.put(request, responseClone);
                    });

                    return networkResponse;
                });
            })
        );
    }
});
