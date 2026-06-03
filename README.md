<p align="center">
  <img src="app/static/img/default.png" alt="MediaSync" width="72">
  <img src="app/static/img/emby.png" alt="Emby" width="72">
  <img src="app/static/img/plex.png" alt="Plex" width="72">
  <img src="app/static/img/jellyfin.png" alt="Jellyfin" width="72">
</p>

<h1 align="center">MediaSync</h1>

<p align="center">
  <strong>Media Server Automation and Visibility</strong>
</p>

<p align="center">
  MediaSync keeps your media stack responsive by connecting automation tools directly to Emby, Jellyfin, and Plex.
  Movies scan immediately, TV imports are handled with queue-aware smart sync, and live activity monitoring keeps
  library updates visible without app-hopping.
</p>

<p align="center">
  <strong>Immediate Movie Scans</strong> •
  <strong>Queue-Aware TV Sync</strong> •
  <strong>Smart Library Mapping</strong> •
  <strong>Live Activity Monitoring</strong> •
  <strong>Emby / Jellyfin / Plex</strong>
</p>

---

## What MediaSync Does

MediaSync connects your Arr stack to your media server so newly imported content appears quickly and reliably.

Instead of waiting for scheduled media-server scans or manually refreshing libraries, MediaSync listens for completed imports from Radarr and Sonarr, then triggers the correct mapped media-server library scan automatically.

It is designed for real homelab media workflows where responsiveness matters, but scan spam does not.

---

## Features

### Immediate Movie Scans

Movie imports trigger immediate mapped library scans.

When Radarr reports a completed movie import, MediaSync scans the mapped movie library right away so new movies become available quickly.

### Queue-Aware TV Sync

TV imports are handled differently than movies.

A movie library typically receives one import at a time. TV libraries often receive entire seasons, multiple episodes, or large batches over an extended period.

Instead of triggering a full library scan for every imported episode, MediaSync monitors the Sonarr queue and intelligently coordinates library refreshes.

TV sync workflow:

```text
First TV import
→ immediate mapped library scan
→ queue monitoring begins
→ optional interim scans while imports continue
→ queue empty
→ final authoritative library scan
```

This approach keeps newly imported content available quickly while avoiding excessive media-server scans during large download or import sessions.

### Smart Source → Library Mapping

MediaSync maps each source to the correct media-server library.

Examples:

```text
Radarr → Movies
Sonarr → TV Shows
Radarr 4K → Movies 4K
```

Multiple source instances are supported, so users can map different Radarr or Sonarr instances to different libraries without special-case configuration.

### Multi-Platform Media Server Support

MediaSync currently supports Emby, Jellyfin, and Plex.

Supported media server behavior includes:

- library discovery
- smart source mapping
- immediate movie scans
- queue-aware TV synchronization
- manual library scans
- activity monitoring
- dynamic UI theming by selected media server

### Live Activity Monitoring

The dashboard and activity page provide real-time visibility into import and scan behavior.

Track events such as:

- source imports
- immediate movie scans
- TV smart scan starts and updates
- queue monitoring
- interim scans
- final scans
- scan failures
- manual scans

Activity timestamps follow the configured timezone, and file display can be switched between filenames and full paths.

### Authentication and PWA Support

MediaSync includes first-run admin account creation, login/logout support, and session-based authentication.

MediaSync also supports Progressive Web App behavior, including iPhone Home Screen installation when deployed behind HTTPS.

### First-Run Setup and Ongoing Settings

MediaSync includes a guided first-run setup process.

After setup, all configuration is managed from the Settings page:

- media server connection
- MediaSync URL
- source connections
- source testing
- library mapping
- TV sync behavior
- activity display behavior
- manual reset/recovery

---

## Supported Integrations

### Current

Media servers:

- Emby
- Jellyfin
- Plex

Sources:

- Radarr
- Sonarr

### Planned

Pipeline and processing:

- downloader tracking and queue visibility
- Unmanic integration
- transcoding visibility
- storage optimization insight
- real-time space savings feedback
- service health monitoring
- request-to-availability tracking
- end-to-end media pipeline visibility

---

## MediaSync 2.x Vision

MediaSync is evolving beyond library synchronization into a complete media pipeline visibility platform.

The goal is to provide a single dashboard showing the health and status of the entire media workflow.

Target workflow:

```text
Request
↓
Arr Applications
↓
Downloader
↓
Import
↓
MediaSync
↓
Media Server
```

Planned capabilities include:

- connected application health monitoring
- green/red connection status indicators
- yellow/red warning and issue indicators
- service warning and update notifications
- request-to-availability tracking
- downloader queue visibility
- import progress monitoring
- library synchronization status
- Unmanic integration
- transcoding visibility
- storage optimization insights
- end-to-end media pipeline observability

The long-term objective is a single pane of glass where users can immediately determine the health and status of their entire media stack without jumping between multiple applications.

The planned dashboard direction includes service health tokens on the left side of connected applications to show whether each service is reachable, authenticated, and healthy, with warning tokens on the right side for updates, failed tasks, unreachable paths, configuration issues, and other actionable problems.

---

## Screenshots

<p align="center">
  <img src="screenshots/mediasync_dashboard.png" alt="MediaSync Dashboard" width="100%">
</p>

<p align="center">
  <img src="screenshots/mediasync_setup.png" alt="MediaSync Setup Wizard" width="100%">
</p>

---

## Deployment

MediaSync is designed to run as a Docker container.

A typical deployment uses Docker Compose or a Portainer stack.

Example Compose file:

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

For local development or self-building:

```bash
docker compose up -d --build
```

After deployment:

1. Open the MediaSync web UI.
2. Complete first-run setup.
3. Configure the MediaSync URL.
4. Add Radarr and/or Sonarr sources.
5. Test each source.
6. Select compatible media-server libraries.
7. Save mappings.
8. Trigger an import and confirm activity appears in the dashboard.

---

## Notes

MediaSync should be reachable by Radarr and Sonarr at the configured MediaSync URL so automatic webhook registration can function correctly.

If using a reverse proxy, configure the MediaSync URL with the externally reachable address, for example:

```text
https://mediasync.example.com
```

or a local network address:

```text
http://192.168.1.50:8097
```

---

## License

MediaSync is licensed under the GNU Affero General Public License v3.0.

See [`LICENSE`](LICENSE) for details.

The AGPLv3 ensures MediaSync and modified versions remain open source, including when modified versions are run as network services.
