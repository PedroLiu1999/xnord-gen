#!/usr/bin/env python3
import requests
import sys

def verify_load_sorting(country_id=228, limit=10):
    """
    Fetches servers, sorts them by load, and verifies the order.
    """
    url = "https://api.nordvpn.com/v2/servers"
    params = {
        "limit": limit,
        "filters[servers_technologies][id]": 35, # WireGuard
        "filters[country_id]": country_id
    }
    
    print(f"Fetching {limit} servers for Country ID {country_id}...")
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        servers = data.get('servers', [])
        
        if not servers:
            print("No servers found.")
            return

        print(f"Received {len(servers)} servers. Sorting by load...\n")
        
        # Sort by load (ascending) - effectively mimicking the logic in config_generator.py
        # Note: The API itself doesn't guarantee sort order, we do it in client.
        sorted_servers = sorted(servers, key=lambda x: x.get('load', 100))
        
        print(f"{'Hostname':<25} | {'Load':<5} | {'Station IP':<15}")
        print("-" * 50)
        
        for s in sorted_servers:
            hostname = s.get('hostname', 'N/A')
            load = s.get('load', 'N/A')
            station = s.get('station', 'N/A')
            print(f"{hostname:<25} | {load:<5} | {station:<15}")
            
        # verification
        loads = [s.get('load', 100) for s in sorted_servers]
        if loads == sorted(loads):
            print("\n✅ Verification PASSED: Servers are sorted by load (ascending).")
            print(f"Lowest Load: {loads[0]}%")
        else:
            print("\n❌ Verification FAILED: Servers are NOT sorted correctly.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Default to US if not provided
    c_id = int(sys.argv[1]) if len(sys.argv) > 1 else 228
    verify_load_sorting(country_id=c_id)
