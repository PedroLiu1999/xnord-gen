# Xray Config Generator for NordVPN

This tool generates a comprehensive **Xray** configuration file designed to sit behind a **Cloudflare Tunnel**. It provides dedicated routing endpoints for every country supported by NordVPN.

## Features

- **Multi-Country Support**: Automatically creates connection Client IDs for each of NordVPN's 100+ countries.
- **Smart Routing**: Connecting via a specific Client ID routes your traffic strictly through that country's server (e.g., `User-US` -> `Nord-US`).
- **Secure**: Uses WireGuard (NordLynx) for high-performance outbound connections.
- **Filtering**: Optionally convert only specific countries (e.g., just US, UK, JP).
- **Docker Compose Export**: Generates ready-to-use directory with `config.json` and `docker-compose.yaml` (or `.gluetun.yaml`).
- **Enhanced Security**: Blocks Direct connections to local networks and uses random passwords for Shadowsocks integration.
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

### 3. List Available Countries (Helper)
Not sure which code to use? Use this helper command to search or list all countries.

```bash
# List ALL
docker run --rm ghcr.io/pedroliu1999/xnord-gen:latest list-countries

# Search for a specific country
docker run --rm ghcr.io/pedroliu1999/xnord-gen:latest list-countries "United States"
```

### 4. Generate Configuration
Run the generator. You **must** specify the countries you want (e.g., `US,JP`).
The config and a corresponding `docker-compose.yaml` will be saved to `config/`.

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

The tool will verify your key, fetch server details, generate UUIDs, and output:
- `config.json`: The Xray configuration.
- `docker-compose.yaml`: A Docker Compose file to run the stack.

### 5. Run Xray
Use the generated Docker Compose file to start the service.

```bash
docker compose -f docker-compose.yaml up -d
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
    teddysun/xray
```

---

## Configuration Options

| Environment Variable | Description | Default |
|----------------------|-------------|---------|
| `NORD_PRIVATE_KEY`   | **Required**. Your NordLynx Private Key. | N/A |
| `NORD_COUNTRIES`     | **Required**. Comma-separated list of country codes (e.g., `US,JP`). | N/A |
| `ENABLE_DIRECT`      | Set to `true` to generate a dedicated link that bypasses VPN. Securely blocks LAN access. | `false` |
| `XRAY_DOMAIN`        | The domain used in the generated VLESS links. | `<YOUR_DOMAIN>` |
| `XRAY_PORT`          | The inbound listening port for Xray. | `10000` |
| `ENABLE_GLUETUN`     | Set to `true` to generate a `docker-compose.gluetun.yaml` using Gluetun containers. | `false` |
| `XRAY_NETWORK`       | Optional. Name of an external Docker network to use instead of the default bridge. | `None` |

---

## Security & Privileges

To support advanced networking features required for VPN routing, the generated Docker Compose file includes specific privileges for the Xray container:

- **`NET_ADMIN` Capability**: Required to manipulate network interfaces.
- **`/dev/net/tun` Device**: Mounted to allow creation of TUN interfaces.

### Direct Mode Security
When `ENABLE_DIRECT=true` is used, the generator automatically adds a high-priority routing rule to **block** traffic destined for private IP ranges (e.g., `192.168.x.x`, `10.x.x.x`). This prevents external users connecting via "Direct" mode from accessing your local network resources.

---

---

## Gluetun Integration

If you prefer to run Xray with **Gluetun** (a lightweight VPN client) instead of using Xray's built-in WireGuard handling, you can enable Gluetun mode.

### How it works
1. **Enable**: Set `ENABLE_GLUETUN=true`.
2. **Generate**: The tool will generate:
   - `config.json`: Xray config routing traffic to local Gluetun containers via **Shadowsocks**.
   - `docker-compose.gluetun.yaml`: A Docker Compose file defining the `xray` service and one `gluetun` service per requested country.
3. **Shadowsocks**: The system automatically generates a unique password for each Gluetun instance and configures Xray to communicate with it using the `chacha20-ietf-poly1305` method. This replaces the older SOCKS5 implementation for better stability and security.

### Usage
```bash
# 1. Generate the Compose file
docker run --rm \
    -v $(pwd):/app/config \
    -e NORD_PRIVATE_KEY="<YOUR_KEY>" \
    -e NORD_COUNTRIES="US,JP" \
    -e ENABLE_GLUETUN=true \
    ghcr.io/pedroliu1999/xnord-gen:latest

# 2. Start the Stack
docker compose -f config/docker-compose.gluetun.yaml up -d
```
All traffic for `[US]` links will be routed through the `gluetun-us` container, and `[JP]` through `gluetun-jp`.

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
