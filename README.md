<p align="center">
  <img src="app/static/img/default.png" alt="MediaSync" width="72">
  <img src="app/static/img/emby.png" alt="Emby" width="72">
  <img src="app/static/img/plex.png" alt="Plex" width="72">
  <img src="app/static/img/jellyfin.png" alt="Jellyfin" width="72">
</p>

<h1 align="center">MediaSync</h1>

<p align="center">
  <strong>Media Pipeline Visibility and Automation</strong>
</p>

<p align="center">
  MediaSync connects your request application, download client, media automation stack, and media server into a single dashboard. Track content from request through download, import, scan, and availability while monitoring the health of your media ecosystem from one place.
</p>

<p align="center">
  <strong>Request Tracking</strong> •
  <strong>Download Visibility</strong> •
  <strong>Service Health Monitoring</strong> •
  <strong>Smart TV Sync</strong> •
  <strong>Multiple Instance Support</strong>
</p>

---

## Why MediaSync?

Modern media stacks are made up of multiple independent applications.

Requests, downloads, imports, scans, and media server availability are often spread across several dashboards.

MediaSync brings the entire process together into a single view, providing visibility from request through availability.

---

## Screenshots

### Dashboard

![Dashboard](app/static/img/screenshots/dashboard.png)

The dashboard provides a live view of your media ecosystem.

Features include:

- Service health monitoring
- Request tracking
- Download visibility
- Library statistics
- Availability tracking
- Recent activity
- Connected service status

### Movie Progress Tracking

![Movie Progress](app/static/img/screenshots/movie_download.png)

Track a movie from request through availability:

Requested
↓
Sent to Media Automation
↓
Downloading
↓
Imported
↓
Library Scan
↓
Available

The movie progress window provides:

- Live download percentage
- Import detection
- Scan tracking
- Availability confirmation
- Request details
- Media metadata

### TV Progress Tracking

![TV Progress](app/static/img/screenshots/tv_download.png)

Track TV episodes from request through availability:

Requested
↓
Sent to Media Automation
↓
Downloading
↓
Imported
↓
Smart Scan
↓
Available

The TV progress window provides:

- Live download tracking
- Queue visibility
- Episode tracking
- Smart scan status
- Availability confirmation
- Series information

---

## Features

### Request Tracking

MediaSync tracks requests from creation through download, import, scan, and availability.

### Download Visibility

Monitor supported download clients directly from MediaSync, including live progress percentages, status, speed, and download activity.

### Availability Confirmation

MediaSync verifies that content is actually available in your media server before reporting completion.

### Immediate Movie Scans

Movie imports trigger immediate library scans so new content appears quickly.

### Queue Aware TV Synchronization

TV imports are handled differently than movies.

MediaSync performs an immediate scan on the first import, monitors the active queue, performs optional interim scans during active download sessions, and executes a final authoritative scan when the queue becomes empty.

This keeps content available quickly without creating unnecessary scan activity during large download batches.

### Service Health Monitoring

MediaSync monitors the health of connected services and displays status directly on the dashboard.

Status indicators include:

- Healthy
- Update Available
- Configuration Warnings
- Connection Failures

### Multiple Instance Support

MediaSync supports multiple instances of supported applications.

Requests, downloads, imports, scans, and availability tracking remain associated with the correct application instance throughout the process.

### Library Statistics

Monitor library totals directly from the dashboard.

Library counts update automatically after successful scans.

### Live Activity Feed

Track events including:

- Requests
- Downloads
- Imports
- Movie scans
- TV smart scans
- Availability confirmation
- Manual scans
- Service events

### Authentication

MediaSync includes first-run account setup and session-based authentication.

### Progressive Web App

MediaSync can be installed directly to mobile devices and used like a native application.

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

MediaSync is designed for containerized deployment using Docker and Docker Compose.

Example:

```yaml
version: '3.8'

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

- Additional Download Clients
- Unmanic Integration
- Tdarr Integration
- Transcoding Visibility
- Space Savings Tracking
- Additional Themes and UI Customization

---

## License

MediaSync is licensed under the GNU Affero General Public License v3.0.

See LICENSE for details.
