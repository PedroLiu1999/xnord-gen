import os
import json
import requests
import uuid
import sys
import time
import subprocess
import re
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# --- Configuration & Settings ---

@dataclass
class Settings:
    nord_private_key: str
    nord_countries: List[str]
    xray_port: int
    enable_direct: bool
    enable_gluetun: bool
    xray_domain: str
    xray_network: Optional[str] = None

    @classmethod
    def load(cls):
        # Check for Helper Commands first (outside of normal flow, but good to have here or in main)
        if len(sys.argv) > 1 and sys.argv[1] == "list-countries":
            return None # Signal to main to handle special command

        nord_private_key = os.environ.get("NORD_PRIVATE_KEY")
        if not nord_private_key:
            cls._print_key_error()
            sys.exit(1)

        nord_countries_env = os.environ.get("NORD_COUNTRIES", "")
        if not nord_countries_env:
            print("\n" + "!" * 60)
            print("ERROR: NORD_COUNTRIES is missing.")
            print("!" * 60)
            print("You must provide a list of country codes (e.g., 'US,JP,UK').")
            sys.exit(1)

        wanted_codes = [c.strip().upper() for c in nord_countries_env.split(',')]
        xray_port = int(os.environ.get("XRAY_PORT", 10000))
        enable_direct = os.environ.get("ENABLE_DIRECT", "false").lower() == "true"
        enable_gluetun = os.environ.get("ENABLE_GLUETUN", "false").lower() == "true"
        xray_domain = os.environ.get("XRAY_DOMAIN", "<YOUR_DOMAIN>")
        xray_network = os.environ.get("XRAY_NETWORK")

        return cls(
            nord_private_key=nord_private_key,
            nord_countries=wanted_codes,
            xray_port=xray_port,
            enable_direct=enable_direct,
            enable_gluetun=enable_gluetun,
            xray_domain=xray_domain,
            xray_network=xray_network
        )

    @staticmethod
    def _print_key_error():
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

# --- NordVPN Client ---

class NordVPNClient:
    API_COUNTRIES = "https://api.nordvpn.com/v1/countries"
    API_SERVERS = "https://api.nordvpn.com/v2/servers"

    def get_all_countries(self) -> List[Dict]:
        """Fetches the list of all available countries from NordVPN."""
        try:
            print("Fetching country list from NordVPN...")
            response = requests.get(self.API_COUNTRIES)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching countries: {e}")
            sys.exit(1)

    def get_recommended_server(self, country_id: int) -> Optional[Dict]:
        """
        Fetches the recommended NordVPN server using V2 API.
        Fetches a batch of servers and sorts by load locally.
        """
        params = {
            "filters[servers_technologies][id]": 35, # WireGuard UDP
            "filters[country_id]": country_id,
            "limit": 30
        }
        
        try:
            data = None
            for attempt in range(3):
                try:
                    response = requests.get(self.API_SERVERS, params=params, timeout=10)
                    response.raise_for_status()
                    json_resp = response.json()
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

# --- Xray Configuration Builder ---

class XrayConfigBuilder:
    def __init__(self, port: int, decryption_key: str):
        self.port = port
        self.decryption_key = decryption_key
        self.clients = []
        self.outbounds = []
        self.routing_rules = []
        
        # Initialize Direct and Blackhole outbounds
        # Default outbound is now blocked for security
        self.outbounds.append({"protocol": "blackhole", "tag": "blocked"})
        self.outbounds.append({"protocol": "freedom", "tag": "direct"})
        
        # Default Blocking Rule for CN
        self.routing_rules.append({
            "type": "field",
            "outboundTag": "blocked",
            "domain": ["geosite:cn"]
        })

    def add_client(self, email: str, flow: str = "xtls-rprx-vision") -> str:
        client_id = str(uuid.uuid4())
        self.clients.append({
            "id": client_id,
            "email": email,
            "flow": flow
        })
        return client_id

    def add_routing_rule(self, user_email: str, outbound_tag: str):
        self.routing_rules.append({
            "type": "field",
            "user": [user_email],
            "outboundTag": outbound_tag
        })
        
    def add_blocking_rule(self, user_email: str, ip_list: List[str] = None, domain_list: List[str] = None):
        """Adds a high-priority blocking rule."""
        rule = {
            "type": "field",
            "user": [user_email],
            "outboundTag": "blocked"
        }
        if ip_list:
            rule["ip"] = ip_list
        if domain_list:
            rule["domain"] = domain_list
            
        self.routing_rules.insert(0, rule)

    def add_wireguard_outbound(self, tag: str, private_key: str, server_address: str, 
                             server_port: int, public_key: str, local_address: str = "10.5.0.2/32"):
        self.outbounds.append({
            "tag": tag,
            "protocol": "wireguard",
            "settings": {
                "secretKey": private_key,
                "address": [local_address],
                "peers": [{
                    "publicKey": public_key,
                    "endpoint": f"{server_address}:{server_port}"
                }]
            }
        })

    def add_socks_outbound(self, tag: str, server_address: str, port: int):
         self.outbounds.append({
            "tag": tag,
            "protocol": "socks",
            "settings": {
                "servers": [{
                    "address": server_address,
                    "port": port
                }]
            }
        })

    def add_shadowsocks_outbound(self, tag: str, server_address: str, port: int, method: str, password: str):
         self.outbounds.append({
            "tag": tag,
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": server_address,
                    "port": port,
                    "method": method,
                    "password": password
                }]
            }
        })

    def build(self) -> Dict:
        return {
            "log": { "loglevel": "warning" },
            "inbounds": [
                {
                    "port": self.port,
                    "listen": "0.0.0.0",
                    "protocol": "vless",
                    "settings": {
                        "clients": self.clients,
                        "decryption": self.decryption_key
                    },
                    "streamSettings": {
                        "network": "xhttp",
                        "xhttpSettings": { "path": "/xray" }
                    }
                }
            ],
            "outbounds": self.outbounds,
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "rules": self.routing_rules
            }
        }
    
    @staticmethod
    def generate_keys() -> Tuple[Optional[str], Optional[str]]:
        try:
            result = subprocess.check_output(["xray", "vlessenc"], text=True)
            dec_match = re.search(r'"decryption":\s*"([^"]+)"', result)
            enc_match = re.search(r'"encryption":\s*"([^"]+)"', result)
            
            if dec_match and enc_match:
                return dec_match.group(1), enc_match.group(1)
            else:
                return None, None
        except Exception as e:
            print(f"Error running xray vlessenc: {e}")
            return None, None

# --- Docker Compose Builder ---

class ComposeBuilder:
    def __init__(self, network_name: str = None):
        self.services = {}
        self.version = "3"
        
        if network_name:
            self.networks = {
                "xray_net": {
                    "name": network_name,
                    "external": True
                }
            }
        else:
            self.networks = {
                "xray_net": {
                    "driver": "bridge"
                }
            }
            
        self.xray_depends_on = []

    def add_gluetun_service(self, name: str, nord_private_key: str, 
                          server_hostname: str = None, country: str = None, ss_password: str = None):
        env_vars = [
            "VPN_SERVICE_PROVIDER=nordvpn",
            "VPN_TYPE=wireguard",
            "DNS_ADDRESS=1.1.1.1",
            f"WIREGUARD_PRIVATE_KEY={nord_private_key}",
        ]
        
        if server_hostname:
            env_vars.append(f"SERVER_HOSTNAME={server_hostname}")
        elif country:
            # specialized for Gluetun
            env_vars.append(f"SERVER_COUNTRIES={country}")
        
        if ss_password:
             env_vars.extend([
                "SHADOWSOCKS=on",
                f"SHADOWSOCKS_PASSWORD={ss_password}",
                "SHADOWSOCKS_METHOD=chacha20-ietf-poly1305"
             ])

        self.services[name] = {
            "image": "qmcgaw/gluetun",
            "container_name": name,
            "cap_add": ["NET_ADMIN"],
            "environment": env_vars,
            "networks": ["xray_net"],
            "restart": "always"
        }
        self.xray_depends_on.append(name)

    def add_xray_service(self, port: int):
        service = {
            "image": "teddysun/xray",
            "container_name": "xray",
            "volumes": ["./config.json:/etc/xray/config.json"],
            "ports": [f"{port}:{port}"],
            "networks": ["xray_net"],
            "restart": "always"
        }
        if self.xray_depends_on:
            service["depends_on"] = self.xray_depends_on
            
        self.services["xray"] = service

    def build(self) -> Dict:
        return {
            "version": self.version,
            "services": self.services,
            "networks": self.networks
        }

# --- Output Handler ---

class OutputHandler:
    @staticmethod
    def print_vless_links(clients: List[Dict], domain: str, port: int, encryption_key: str):
        print("\n" + "-" * 55)
        print("VLESS Links & QR Codes:")
        print("-" * 55)
        
        import qrcode
        
        for c in clients:
            if c['email'] == "direct.user@example.com":
                code = "DIRECT"
                tag_suffix = "Direct"
            else:
                code = c['email'].split('.')[0].upper()
                tag_suffix = f"Nord-{code}"
                
            link = f"vless://{c['id']}@{domain}:{443}?type=xhttp&path=/xray&encryption={encryption_key}&security=tls&flow=xtls-rprx-vision#{tag_suffix}"
            
            if domain == "<YOUR_DOMAIN>":
                 print(f"\nExample for [{code}] (Replace <YOUR_DOMAIN> first!):")
            else:
                 print(f"\nLink for [{code}]:")
                 
            print(f"{link}")
            
            qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
            qr.add_data(link)
            qr.print_ascii(invert=True)
            print("-" * 40)

    @staticmethod
    def print_country_list(countries: List[Dict], search_term: str = None):
        print(f"{'Name':<35} | {'Code':<5} | {'ID':<10}")
        print("-" * 55)
        
        found = False
        for c in countries:
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


# --- Main ---

def main():
    # 0. Handle CLI commands
    if len(sys.argv) > 1 and sys.argv[1] == "list-countries":
        client = NordVPNClient()
        countries = client.get_all_countries()
        search_term = " ".join(sys.argv[2:]).lower() if len(sys.argv) > 2 else None
        OutputHandler.print_country_list(countries, search_term)
        sys.exit(0)

    # 1. Load Settings
    settings = Settings.load()
    if not settings:
        sys.exit(0)

    # 2. Key Generation
    print("Generating Xray VLESS keys...")
    dec_key, enc_key = XrayConfigBuilder.generate_keys()
    if not dec_key:
        print("WARNING: Failed to generate keys. Falling back to encryption=none")
        dec_key, enc_key = "none", "none"
    else:
        print("Keys generated.")

    # 3. Initialize Builders
    xray_builder = XrayConfigBuilder(settings.xray_port, dec_key)
    compose_builder = ComposeBuilder(settings.xray_network)
    nord_client = NordVPNClient()

    # 4. Filter Countries
    all_countries = nord_client.get_all_countries()
    target_countries = [c for c in all_countries if c['code'].upper() in settings.nord_countries]
    
    if not target_countries:
        print("No matching countries found based on your filter.")
        sys.exit(1)

    print(f"Generating configuration for {len(target_countries)} countries...")

    # 5. Process Countries
    for country in target_countries:
        c_code = country['code']
        c_name = country['name']
        
        sys.stdout.write(f"Processing {c_name} ({c_code})... ")
        sys.stdout.flush()
        
        sys.stdout.write(f"Processing {c_name} ({c_code})... ")
        sys.stdout.flush()
        
        server = None
        if not settings.enable_gluetun:
            server = nord_client.get_recommended_server(country['id'])
            if not server:
                print("No WireGuard server found. Skipping.")
                continue
            print(f"Server: {server['hostname']}")
        
        # User Config
        email = f"{c_code.lower()}.user@example.com"
        tag = f"nordvpn-{c_code.lower()}"
        client_id = xray_builder.add_client(email)
        
        if settings.enable_gluetun:
            service_name = f"gluetun-{c_code.lower()}"
            ss_password = str(uuid.uuid4())
            
            # Add Gluetun Service (with SS)
            # Use country name for Gluetun auto-selection
            compose_builder.add_gluetun_service(
                name=service_name,
                nord_private_key=settings.nord_private_key,
                country=c_name, 
                ss_password=ss_password
            )
            
            # Add Xray Outbound (Shadowsocks)
            xray_builder.add_shadowsocks_outbound(
                tag=tag,
                server_address=service_name,
                port=8388,
                method="chacha20-ietf-poly1305",
                password=ss_password
            )
            print(f"Gluetun Service: {service_name} (Country: {c_name})")
        else:
            # Standard WireGuard Mode
            xray_builder.add_wireguard_outbound(
                tag=tag,
                private_key=settings.nord_private_key,
                server_address=server['address'],
                server_port=server['port'],
                public_key=server['public_key']
            )

        # Route User -> Tag
        xray_builder.add_routing_rule(email, tag)

    # 6. Process Direct Access
    if settings.enable_direct:
        print("Enable Direct Route: YES")
        direct_email = "direct.user@example.com"
        xray_builder.add_client(direct_email)
        
        # Security: Blocking Rule for Direct User
        # Block private IPs (geoip:private) AND private domains (geosite:private)
        xray_builder.add_blocking_rule(direct_email, ip_list=["geoip:private"], domain_list=["geosite:private"])
        
        # Allow Rule
        xray_builder.add_routing_rule(direct_email, "direct")

    # 7. Finalize & Write Configs
    compose_builder.add_xray_service(settings.xray_port)
    
    base_dir = "/app/config" if os.path.exists("/app") else "./config"
    os.makedirs(base_dir, exist_ok=True)
    
    # Write Xray Config
    config_path = os.path.join(base_dir, "config.json")
    with open(config_path, "w") as f:
        json.dump(xray_builder.build(), f, indent=4)
        
    print("\n✅ Xray configuration generated: config.json")

    # Write Docker Compose
    filename = "docker-compose.gluetun.yaml" if settings.enable_gluetun else "docker-compose.yaml"
    compose_path = os.path.join(base_dir, filename)
    with open(compose_path, "w") as f:
        yaml.dump(compose_builder.build(), f, default_flow_style=False, sort_keys=False)

    print(f"✅ Docker Compose generated: {filename}")
    print(f"   (Use: docker compose -f {compose_path} up -d)")

    # 8. Output Links
    OutputHandler.print_vless_links(
        xray_builder.clients, 
        settings.xray_domain, 
        settings.xray_port, 
        enc_key
    )

if __name__ == "__main__":
    main()
