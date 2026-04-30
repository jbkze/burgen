# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Docker Compose stack for **jbkze.de**, running on a Raspberry Pi (aarch64, Ubuntu 24.04). All services are exposed via a Cloudflare Tunnel — no ports are open to the internet.

## Architecture

- **cloudflared** connects outbound to Cloudflare and routes incoming requests to internal Docker services based on hostname rules in `cloudflared/config.yml`
- Services are only reachable within the Docker network; cloudflared is the sole entry point
- Tunnel ID: `597e6c96-5861-48d2-8f5e-e11cfced1db3`, credentials stored in `~/.cloudflared/`

## Commands

Docker requires `sg docker -c "..."` wrapper in Claude Code sessions (group not inherited). After a fresh login this is unnecessary.

```bash
# Start/stop the stack
sg docker -c "docker compose up -d"
sg docker -c "docker compose down"

# View logs
sg docker -c "docker logs infrastructure-cloudflared-1"
sg docker -c "docker logs infrastructure-audiobookshelf-1"
```

## Adding a new service

1. Add the service to `docker-compose.yml` (no host port mapping needed)
2. Add a hostname → service ingress rule in `cloudflared/config.yml` (above the catch-all 404)
3. Create the DNS route: `sg docker -c "docker run --rm -v ~/.cloudflared:/home/nonroot/.cloudflared cloudflare/cloudflared:latest tunnel route dns jbkze <subdomain>.jbkze.de"`
4. Restart: `sg docker -c "docker compose up -d"`

## Current services

| Subdomain | Service | Internal target |
|---|---|---|
| abs.jbkze.de | Audiobookshelf | http://audiobookshelf:80 |
