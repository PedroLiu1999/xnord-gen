# Setting up Cloudflare Tunnel for Xray

This guide explains how to expose your Xray server securely using Cloudflare Tunnel, without opening ports on your router.

## Prerequisites
- A Cloudflare account.
- A domain name managed by Cloudflare.

## Step 1: Create the Tunnel

1.  Go to **Zero Trust Dashboard** -> **Networks** -> **Tunnels**.
2.  Click **Create a Tunnel**.
3.  Choose **Cloudflared** (Connector).
4.  Name your tunnel (e.g., `xray-server`).
5.  **Save Tunnel**.

## Step 2: Get the Token

On the "Install and Run Connector" page, you will see a command like:
`cloudflared service install eyJhIjoi...`

The long string starting with `ey` is your **TUNNEL_TOKEN**. Copy it.

## Step 3: Configure the Public Hostname

1.  Click **Next** in the Cloudflare dashboard.
2.  **Public Hostname**:
    - **Subdomain**: `xray` (or whatever you prefer).
    - **Domain**: `yourdomain.com`.
3.  **Service**:
    - **Type**: `HTTP` (or `WS` if you prefer, but HTTP works for Xray WS).
    - **URL**: `xray:10000` (This matches the service name and port in `docker-compose.yml`).

## Step 4: Run with Docker Compose

1.  Create a `.env` file in the same folder as your `docker-compose.yml`:
    ```env
    TUNNEL_TOKEN=eyJhIjoi...
    ```
2.  Start the services:
    ```bash
    docker-compose up -d
    ```

Your Xray server is now accessible at `xray.yourdomain.com`!
