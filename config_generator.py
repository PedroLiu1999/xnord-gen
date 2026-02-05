import os
import json
import requests
import uuid
import sys
import time

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
    Fetches the recommended NordVPN server.
    Uses country_id if provided (more reliable for the API).
    """
    url = "https://api.nordvpn.com/v1/servers/recommendations"
    params = {
        "filters[servers_technologies][identifier]": "wireguard_udp",
        "limit": 1
    }
    
    if country_id:
        params["filters[country_id]"] = country_id

    try:
        # Retry logic for robustness when making many requests
        for attempt in range(3):
            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data:
                    break
            except requests.RequestException:
                if attempt == 2: raise
                time.sleep(1)
        
        if not data:
            # print(f"No servers found for country ID {country_id}")
            return None
            
        server = data[0]
        hostname = server['hostname']
        station_ip = server['station']
        
        # Extract public key
        public_key = None
        for tech in server.get('technologies', []):
             if tech['identifier'] == 'wireguard_udp':
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
    # 2. Strict Key Requirement
    nord_private_key = os.environ.get("NORD_PRIVATE_KEY")
    xray_port = int(os.environ.get("XRAY_PORT", 10000))
    nord_countries_env = os.environ.get("NORD_COUNTRIES", "")
    
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
        print("We no longer default to 'ALL' to prevent abuse/excessive API usage.")
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
            "email": email
        })
        
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
        # We'll print links at the end
    
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
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "ws",
                    "wsSettings": { "path": "/xray" }
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
    os.makedirs("/app/config", exist_ok=True)
    
    with open("/app/config/config.json", "w") as f:
        json.dump(config, f, indent=4)
        
    print("\n✅ Xray configuration generated: config.json")
    print("-------------------------------------------------------")
    print("VLESS Links & QR Codes:")
    print("-------------------------------------------------------")
    
    # Assuming the domain is a placeholder, user needs to replace it.
    domain_placeholder = os.environ.get("XRAY_DOMAIN", "<YOUR_DOMAIN>")
    
    import qrcode
    
    for c in clients:
        # reverse lookup country code from email
        code = c['email'].split('.')[0].upper()
        # Ensure we use the domain correctly in the link
        link = f"vless://{c['id']}@{domain_placeholder}:{443}?type=ws&path=/xray&encryption=none&security=tls#Nord-{code}"
        
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
