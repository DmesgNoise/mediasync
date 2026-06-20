<p align="center">
  <img src="app/static/img/mediasync-logo.png" alt="MediaSync">
</p>

<p align="center">
  <strong>Media Pipeline Visibility and Automation</strong>
</p>

<p align="center">
  MediaSync provides visibility across the entire media pipeline, connecting requests, downloads, imports, scans, and media server availability into a single dashboard.
</p>

<p align="center">
  <strong>Request Tracking</strong> •
  <strong>Live Download Visibility</strong> •
  <strong>Service Health Monitoring</strong> •
  <strong>Queue-Aware TV Synchronization</strong> •
  <strong>Multi-Instance Support</strong>
</p>

---

## Why MediaSync?

Modern media stacks are made up of several independent applications.

Requests happen in one application. Downloads happen in another. Imports, scans, and media server availability are tracked somewhere else.

MediaSync brings the entire process together into a single view, allowing you to follow content from request through availability while also monitoring the health of the services that power your media ecosystem.

---

## Screenshots

### Dashboard

![Dashboard](app/static/img/screenshots/dashboard.png)

Monitor media servers, request applications, automation platforms, download clients, libraries, updates, warnings, and recent activity from a single dashboard.

---

### Movie Request Tracking

![Movie Lifecycle](app/static/img/screenshots/movie_lifecycle.png)

Track a movie from request through availability. MediaSync correlates requests, downloads, imports, scans, and media server updates into a single timeline while displaying metadata, quality profiles, poster artwork, and timing metrics.

---

### Live TV Download Tracking

![TV Download](app/static/img/screenshots/tv_downloading.png)

Monitor active TV downloads in real time, including progress percentage, transfer speed, ETA, downloader status, and current processing stage.

---

### TV Series Tracking and Synchronization

![TV Lifecycle](app/static/img/screenshots/tv_lifecycle.png)

Follow TV content from Sonarr through download, import, queue-aware synchronization, smart scan processing, and final availability in your media server.

---

## Features

### Request Tracking

Track content from request through download, import, scan, and availability.

### Live Download Visibility

Monitor supported download clients directly from MediaSync, including progress percentage, speed, ETA, status, and downloader activity.

### Availability Confirmation

MediaSync verifies that content is available in the media server before reporting completion.

### Immediate Movie Scans

Movie imports trigger immediate library scans so new content becomes available quickly.

### Queue-Aware TV Synchronization

TV imports are handled differently than movies.

MediaSync performs an initial scan after import, monitors active download queues, optionally performs interim scans during long-running download sessions, and executes a final scan when the queue becomes empty.

### Service Health Monitoring

Monitor connected services directly from the dashboard.

Status indicators include:

- Healthy
- Update Available
- Configuration Warnings
- Connection Failures

### Multiple Instance Support

Run multiple instances of supported applications while maintaining accurate tracking throughout the media pipeline.

### Rich Media Information

MediaSync enriches tracked content with information gathered from connected services, including:

- Poster artwork
- Quality profiles
- Request source
- Requester information
- TMDB IDs
- TVDB IDs
- IMDB IDs

### Live Activity Feed

Track requests, downloads, imports, scans, availability events, and service activity as they happen.

### Authentication

MediaSync includes first-run account setup and session-based authentication.

### Progressive Web App

Install MediaSync on mobile devices and use it like a native application.

---

## Supported Integrations

### Request Applications

- Seerr

### Media Automation

- Radarr
- Sonarr

Multiple instances are supported.

### Download Clients

- SABnzbd
- qBittorrent
- Transmission

Multiple instances are supported.

### Media Servers

- Emby
- Jellyfin
- Plex

---

## Deployment

```yaml
services:
  mediasync:
    image: ghcr.io/dmesgnoise/mediasync:latest
    container_name: mediasync
    restart: unless-stopped
    ports:
      - "8097:8097"
    volumes:
      - mediasync_config:/config

volumes:
  mediasync_config:
```

Build locally:

```bash
docker compose up -d --build
```

---

## Future Plans

### Mobile Companion App

A dedicated mobile companion app is planned for MediaSync.

The goal is to provide visibility for both administrators and end users.

Planned capabilities include:

- Request status tracking
- Download progress visibility
- Availability notifications
- Push notifications
- Service health alerts
- Queue monitoring
- Remote administration features

End users will be able to see where requested content is in the process without requiring access to Seerr, Radarr, Sonarr, or download clients.

### Additional Roadmap Items

- Unmanic Integration
- Tdarr Integration
- Transcoding Visibility
- Storage Savings Tracking
- Additional Themes
- Additional UI Customization

---

## License

MediaSync is licensed under the GNU Affero General Public License v3.0.

See LICENSE for details.
