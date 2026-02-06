# Xray Config Generator for NordVPN

This tool generates a comprehensive **Xray** configuration file designed to sit behind a **Cloudflare Tunnel**. It provides dedicated routing endpoints for every country supported by NordVPN.

## Features

- **Multi-Country Support**: Automatically creates connection Client IDs for each of NordVPN's 100+ countries.
- **Smart Routing**: Connecting via a specific Client ID routes your traffic strictly through that country's server (e.g., `User-US` -> `Nord-US`).
- **Secure**: Uses WireGuard (NordLynx) for high-performance outbound connections.
- **Filtering**: Optionally convert only specific countries (e.g., just US, UK, JP).
- **Helper Utilities**: Includes tools to fetch your private key using a NordVPN Access Token.

## Prerequisites

- **Docker**: Must be installed.
- **NordVPN Account**: You need your **WireGuard Private Key** (not your login password).
- **Cloudflare Tunnel**: You should have a tunnel pointing to the Xray inbound port (default `10000`).

## Quick Start

### 1. Pull the Image
We recommend using the pre-built image from GitHub Container Registry (supports AMD64 & ARM64).

```bash
docker pull ghcr.io/pedroliu1999/xnord-gen:latest
```

### 2. Get Your NordVPN Private Key
You need your specific **WireGuard Private Key**.
- **If you have a NordVPN Access Token** (from Dashboard -> Access Token):
  ```bash
  docker run --rm ghcr.io/pedroliu1999/xnord-gen:latest fetch-nord-key <YOUR_TOKEN>
  ```
  *Copy the key output from this command.*

- **If you don't have a token**, create one in the NordVPN dashboard or extract the key from a running Linux client (`wg show nordlynx private-key`).

### 3. Generate Configuration
Run the generator. You **must** specify the countries you want (e.g., `US,JP`).
The config will be saved to `config.json`.

```bash
# Create a folder for the config
mkdir -p config

docker run --rm \
    -v $(pwd):/app/config \
    -e NORD_PRIVATE_KEY="<YOUR_PRIVATE_KEY>" \
    -e NORD_COUNTRIES="US,JP" \
    -e XRAY_DOMAIN="yourdomain.com" \
    ghcr.io/pedroliu1999/xnord-gen:latest
```

### 4. Run Xray
Use the generated configuration to run the Xray server.

```bash
docker run -d --name xray \
    -v $(pwd)/config/config.json:/etc/xray/config.json \
    -p 10000:10000 \
    ghcr.io/xtls/xray-core
```

---

## Deployment Guide

Once you have generated your `config.json`, you can deploy Xray manually or use our **Docker Compose** examples.

### 📚 Documentation
- [**Cloudflare Tunnel Setup Guide**](docs/cloudflared-setup.md): Complete instructions on setting up a secure tunnel.
- [**Triggering Automated Builds**](docs/triggering-builds.md): Guide on GitHub Actions builds.
- [**Docker Compose Example**](examples/docker-compose.yml): a ready-to-use Compose file for running Xray and Cloudflared together.

### Manual Run
```bash
docker run -d --name xray \
    -v $(pwd)/config.json:/etc/xray/config.json \
    -p 10000:10000 \
    ghcr.io/xtls/xray-core
```

---

## Configuration Options

| Environment Variable | Description | Default |
|----------------------|-------------|---------|
| `NORD_PRIVATE_KEY`   | **Required**. Your NordLynx Private Key. | N/A |
| `NORD_COUNTRIES`     | **Required**. Comma-separated list of country codes (e.g., `US,JP`). | N/A |
| `ENABLE_DIRECT`      | Set to `true` to generate a dedicated link that bypasses VPN. | `false` |
| `XRAY_DOMAIN`        | The domain used in the generated VLESS links. | `<YOUR_DOMAIN>` |
| `XRAY_PORT`          | The inbound listening port for Xray. | `10000` |

---

## Build Locally (Optional)
If you prefer to build the image yourself:

```bash
docker build -t xnord-gen .
docker run --rm -v $(pwd)/config:/app/config ... xnord-gen
```

## Output Format

The tool outputs a list of VLESS connection links **and QR codes** for easy mobile scanning.

```text
[JP] vless://<UUID>@<DOMAIN>:443?path=/xray...#Nord-JP
(QR Code Here)
```

- **Connect to [JP] link** -> Traffic exits via **Japan**.
- **Connect to [US] link** -> Traffic exits via **United States**.
