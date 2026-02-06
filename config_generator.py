import os
import json
import requests
import uuid
import sys
import time
import subprocess
import re
import yaml

def get_xray_vless_keys():
    """
    Generates VLESS encryption keys using 'xray vlessenc'.
    Returns (decryption_key, encryption_key) or (None, None) if failed.
    """
    try:
        # Run xray vlessenc
        # We expect xray to be in PATH (from Dockerfile /usr/bin/xray)
        # Using list args is safer and shell=False is default
        result = subprocess.check_output(["xray", "vlessenc"], text=True)
        
        # Parse output for X25519 keys (first block typically)
        # Search for: "decryption": "KEY"
        # and "encryption": "KEY"
        
        dec_match = re.search(r'"decryption":\s*"([^"]+)"', result)
        enc_match = re.search(r'"encryption":\s*"([^"]+)"', result)
        
        if dec_match and enc_match:
            return dec_match.group(1), enc_match.group(1)
        else:
            print("Could not parse xray vlessenc output.")
            return None, None
            
    except Exception as e:
        print(f"Error running xray vlessenc: {e}")
        return None, None

def get_all_countries():
    """Fetches the list of all available countries from NordVPN."""
    try:
        print("Fetching country list from NordVPN...")
        response = requests.get("https://api.nordvpn.com/v1/countries")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching countries: {e}")
        sys.exit(1)

def get_nordvpn_server_details(country_id=None):
    """
    Fetches the recommended NordVPN server using V2 API.
    Fetches a batch of servers and sorts by load locally.
    """
    url = "https://api.nordvpn.com/v2/servers"
    params = {
        "filters[servers_technologies][id]": 35,
        "limit": 30
    }
    
    if country_id:
        params["filters[country_id]"] = country_id

    try:
        # Retry logic for robustness when making many requests
        data = None
        for attempt in range(3):
            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                json_resp = response.json()
                # V2 returns a dict with 'servers' key
                data = json_resp.get('servers')
                if data:
                    break
            except requests.RequestException:
                if attempt == 2: raise
                time.sleep(1)
        
        if not data:
            return None
            
        # Sort by load (ascending)
        data.sort(key=lambda x: x.get('load', 100))
        
        server = data[0]
        hostname = server['hostname']
        station_ip = server['station']
        
        # Extract public key
        public_key = None
        for tech in server.get('technologies', []):
             # V2 API uses ID 35 for Wireguard UDP
             if tech.get('id') == 35:
                 for meta in tech.get('metadata', []):
                     if meta['name'] == 'public_key':
                         public_key = meta['value']
                         break
        
        if not public_key:
             return None

        return {
            "address": station_ip,
            "port": 51820,
            "public_key": public_key,
            "hostname": hostname,
            "country": server.get('locations', [{}])[0].get('country', {}).get('code', 'UNKNOWN')
        }

    except Exception:
        return None



def generate_uuid():
    return str(uuid.uuid4())

def main():
    # 1. Check for Helper Commands
    if len(sys.argv) > 1 and sys.argv[1] == "list-countries":
        all_countries = get_all_countries()
        search_term = None
        if len(sys.argv) > 2:
            search_term = " ".join(sys.argv[2:]).lower()
        
        print(f"{'Name':<35} | {'Code':<5} | {'ID':<10}")
        print("-" * 55)
        
        found = False
        for c in all_countries:
            c_name = c['name']
            c_code = c['code']
            c_id = c['id']
            
            if search_term:
                if search_term in c_name.lower() or search_term == c_code.lower():
                    print(f"{c_name:<35} | {c_code:<5} | {c_id:<10}")
                    found = True
            else:
                print(f"{c_name:<35} | {c_code:<5} | {c_id:<10}")
                found = True
                
        if search_term and not found:
            print(f"No countries found matching '{search_term}'")
            
        sys.exit(0)

    # 2. Strict Key Requirement
    nord_private_key = os.environ.get("NORD_PRIVATE_KEY")
    xray_port = int(os.environ.get("XRAY_PORT", 10000))
    nord_countries_env = os.environ.get("NORD_COUNTRIES", "")
    enable_direct = os.environ.get("ENABLE_DIRECT", "false").lower() == "true"
    enable_gluetun = os.environ.get("ENABLE_GLUETUN", "false").lower() == "true"
    
    if not nord_private_key:

        print("\n" + "!" * 60)
        print("ERROR: NORD_PRIVATE_KEY is missing.")
        print("!" * 60)
        print("You must provide your NordVPN WireGuard Private Key.")
        print("\nOPTIONS:")
        print("A) I have a NordVPN Access Token:")
        print("   Run this command to fetch your key:")
        print("   docker run --rm xray-gen fetch-nord-key <YOUR_TOKEN>")
        print("\nB) I need to find my key manually:")
        print("   Check your NordVPN Dashboard 'Service Credentials' or use a running client.")
        print("\nC) I need to generate a NEW key:")
        print("   (You can use 'wg genkey' locally, this tool no longer auto-generates keys)")
        print("\n" + "!" * 60)
        sys.exit(1)

    all_countries = get_all_countries()
    
    # Filter countries
    target_countries = []
    if not nord_countries_env:
        print("\n" + "!" * 60)
        print("ERROR: NORD_COUNTRIES is missing.")
        print("!" * 60)
        print("You must provide a list of country codes (e.g., 'US,JP,UK').")
        sys.exit(1)

    wanted_codes = [c.strip().upper() for c in nord_countries_env.split(',')]
    print(f"Filtering for countries: {wanted_codes}")
    for c in all_countries:
        if c['code'].upper() in wanted_codes:
            target_countries.append(c)
        
    if not target_countries:
        print("No matching countries found based on your filter.")
        sys.exit(1)

    clients = []
    outbounds = []
    routing_rules = []

    # Generate keys
    print("Generating Xray VLESS keys...")
    decryption_key, encryption_key = get_xray_vless_keys()
    
    if not decryption_key:
        print("WARNING: Failed to generate keys. Falling back to encryption=none")
        decryption_key = "none"
        encryption_key = "none"
    else:
        print(f"Keys generated.")

    print(f"Generating configuration for {len(target_countries)} countries...")

    # Add the Direct outbound first
    outbounds.append({
        "protocol": "freedom",
        "tag": "direct"
    })
    
    # Block rule
    routing_rules.append({
        "type": "field",
        "outboundTag": "direct",
        "domain": ["geosite:cn"]
    })

    # Gluetun Docker Compose Structure
    docker_compose = {
        "version": "3",
        "services": {},
        "networks": {
            "xray_net": {
                "driver": "bridge"
            }
        }
    }
    
    # Add Xray service to compose (will accumulate depends_on)
    xray_service_depends_on = []

    for country in target_countries:
        c_code = country['code']
        c_name = country['name']
        c_id = country['id']
        
        # Skip if no WireGuard technology roughly (optimization), but simpler to just try fetch
        sys.stdout.write(f"Processing {c_name} ({c_code})... ")
        sys.stdout.flush()
        
        server = get_nordvpn_server_details(country_id=c_id)
        
        if not server:
            print("No WireGuard server found. Skipping.")
            continue
            
        print(f"Server: {server['hostname']}")
        
        # Generate Client for this country
        client_id = generate_uuid()
        email = f"{c_code.lower()}.user@example.com"
        tag = f"nordvpn-{c_code.lower()}"
        
        # Add Client
        clients.append({
            "id": client_id,
            "email": email,
            "flow": "xtls-rprx-vision"
        })
        
        if enable_gluetun:
            # GLUETUN MODE
            service_name = f"gluetun-{c_code.lower()}"
            
            # Add Gluetun Service
            docker_compose["services"][service_name] = {
                "image": "qmcgaw/gluetun",
                "container_name": service_name,
                "cap_add": ["NET_ADMIN"],
                "environment": [
                    "VPN_SERVICE_PROVIDER=nordvpn",
                    "VPN_TYPE=wireguard",
                    f"WIREGUARD_PRIVATE_KEY={nord_private_key}",
                    f"SERVER_HOSTNAME={server['hostname']}"
                ],
                "networks": ["xray_net"],
                "restart": "always"
            }
            
            xray_service_depends_on.append(service_name)
            
            # Add Socks Outbound via Gluetun
            outbounds.append({
                "tag": tag,
                "protocol": "socks",
                "settings": {
                    "servers": [{
                        "address": service_name,
                        "port": 1080 # Internal port of Gluetun
                    }]
                }
            })
            
        else:
            # STANDARD WIREGUARD MODE
            # Add Outbound
            outbounds.append({
                "tag": tag,
                "protocol": "wireguard",
                "settings": {
                    "secretKey": nord_private_key,
                    "address": ["10.5.0.2/32"], # Shared internal IP for all outbounds usually works in Xray logic
                    "peers": [{
                        "publicKey": server['public_key'],
                        "endpoint": f"{server['address']}:{server['port']}"
                    }],
                    "kernelMode": False
                }
            })
        
        # Add Routing Rule
        # Route traffic from this specific user email to this specific outbound tag
        routing_rules.append({
            "type": "field",
            "user": [email],
            "outboundTag": tag
        })
        
        # Add fallbacks or print link immediately
        # We'll print links at the end (outside loop)

    
    # -------------------------------------------------------------
    # Direct Route (Host Internet)
    # -------------------------------------------------------------
    if enable_direct:
        print("Enable Direct Route: YES")
        direct_id = generate_uuid()
        direct_email = "direct.user@example.com"
        
        clients.append({
            "id": direct_id,
            "email": direct_email,
            "flow": "xtls-rprx-vision"
        })
        
        routing_rules.append({
            "type": "field",
            "user": [direct_email],
            "outboundTag": "direct"
        })
        
    # -------------------------------------------------------------
    # Config Construction
    # -------------------------------------------------------------
    config = {
        "log": { "loglevel": "warning" },
        "inbounds": [
            {
                "port": xray_port,
                "listen": "0.0.0.0",
                "protocol": "vless",
                "settings": {
                    "clients": clients,
                    "decryption": decryption_key
                },
                "streamSettings": {
                    "network": "xhttp",
                    "xhttpSettings": { "path": "/xray" }
                }
            }
        ],
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": routing_rules
        }
    }
    
    # Ensure directory exists
    # If /app exists (Docker), use /app/config. Otherwise local ./config
    if os.path.exists("/app"):
        base_dir = "/app/config"
    else:
        base_dir = "./config"
        
    os.makedirs(base_dir, exist_ok=True)
    config_path = os.path.join(base_dir, "config.json")
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)
        
    if enable_gluetun:
        # Add Xray service to the generated compose
        # We assume the image is built or available as 'xray-gen:latest' or similar, 
        # but for a production compose we might want to use the same image as the generator or a standard one.
        # Let's use ghcr.io/xtls/xray-core:latest + volume mount for config
        
        docker_compose["services"]["xray"] = {
            "image": "ghcr.io/xtls/xray-core:latest",
            "container_name": "xray",
            "volumes": ["./config/config.json:/etc/xray/config.json"],
            "ports": [f"{xray_port}:{xray_port}"],
            "networks": ["xray_net"],
            "restart": "always",
            "depends_on": xray_service_depends_on
        }

        # Write docker-compose.gluetun.yaml
        compose_path = os.path.join(base_dir, "docker-compose.gluetun.yaml")
        
        with open(compose_path, "w") as f:
            yaml.dump(docker_compose, f, default_flow_style=False, sort_keys=False)
            
        print(f"\n✅ Gluetun Compose generated: docker-compose.gluetun.yaml")
        print(f"   (Use: docker compose -f {compose_path} up -d)")

    print("\n✅ Xray configuration generated: config.json")
    print("-------------------------------------------------------")
    print("VLESS Links & QR Codes:")
    print("-------------------------------------------------------")
    
    # Assuming the domain is a placeholder, user needs to replace it.
    domain_placeholder = os.environ.get("XRAY_DOMAIN", "<YOUR_DOMAIN>")
    
    import qrcode
    
    for c in clients:
        # Check if direct
        if c['email'] == "direct.user@example.com":
            code = "DIRECT"
            tag_suffix = "Direct"
        else:
            # reverse lookup country code from email
            code = c['email'].split('.')[0].upper()
            tag_suffix = f"Nord-{code}"
            
        # VLESS Link for XHTTP
        # Format: vless://UUID@DOMAIN:443?encryption=ENCRYPTION_KEY&security=tls&type=xhttp&path=/xray&flow=xtls-rprx-vision&host=DOMAIN#Tag
        link = f"vless://{c['id']}@{domain_placeholder}:{443}?type=xhttp&path=/xray&encryption={encryption_key}&security=tls&flow=xtls-rprx-vision#{tag_suffix}"
        
        
        if domain_placeholder == "<YOUR_DOMAIN>":
             print(f"\nExample for [{code}] (Replace <YOUR_DOMAIN> first!):")
        else:
             print(f"\nLink for [{code}]:")
             
        print(f"{link}")
        
        # Generate QR
        qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
        qr.add_data(link)
        qr.print_ascii(invert=True)
        print("-" * 40)
        
    print("-------------------------------------------------------")

if __name__ == "__main__":
    main()
