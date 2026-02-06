#!/usr/bin/env python3
import requests
import sys

def verify_filters(country_id=228, tech_id=35, limit=5):
    """
    Verifies that the NordVPN V2 API correctly respects the provided filters.
    Defaults: US (228) and WireGuard UDP (35).
    """
    url = "https://api.nordvpn.com/v2/servers"
    params = {
        "limit": limit,
        "filters[servers_technologies][id]": tech_id,
        "filters[country_id]": country_id
    }
    
    print(f"Testing NordVPN API V2 Filters...")
    print(f"URL: {url}")
    print(f"Filters: Country ID={country_id}, Tech ID={tech_id}")
    print("-" * 60)
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        print(f"Full URL: {resp.url}\n")
        resp.raise_for_status()
        data = resp.json()
        
        servers = data.get('servers', [])
        locations_map = {loc['id']: loc for loc in data.get('locations', [])}
        
        print(f"API returned {len(servers)} servers.\n")
        
        if not servers:
            print("⚠️  No servers returned. Cannot verify filters (but this might be expected if no servers match).")
            return

        failure_count = 0
        
        for server in servers:
            s_name = server.get('name')
            s_id = server.get('id')
            
            # 1. Verify Country
            # Server has "location_ids", which map to "locations" in the root response
            s_country_id = None
            loc_ids = server.get('location_ids', [])
            if loc_ids:
                first_loc_id = loc_ids[0]
                loc_obj = locations_map.get(first_loc_id)
                if loc_obj and 'country' in loc_obj:
                    s_country_id = loc_obj['country'].get('id')
            
            # 2. Verify Technology
            tech_ids = [t.get('id') for t in server.get('technologies', [])]
            
            # Check compliance
            country_match = (s_country_id == country_id)
            tech_match = (tech_id in tech_ids)
            
            status_country = "✅" if country_match else f"❌ (Is {s_country_id})"
            status_tech = "✅" if tech_match else f"❌ (Is {tech_ids})"
            
            print(f"Server: {s_name:<25} | ID: {s_id}")
            print(f"  Country Matched: {status_country}")
            print(f"  Tech Matched:    {status_tech}")
            
            if not country_match or not tech_match:
                failure_count += 1
                
            print("-" * 20)
            
        if failure_count == 0:
            print(f"\n✅ SUCCESS: All {len(servers)} servers matched the filters.")
        else:
            print(f"\n❌ FAILURE: {failure_count} servers failed validation.")
            sys.exit(1)

    except Exception as e:
        print(f"Error executing request: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Allow command line overrides: python3 verify_nord_filters.py [COUNTRY_ID] [TECH_ID]
    c_id = int(sys.argv[1]) if len(sys.argv) > 1 else 228
    t_id = int(sys.argv[2]) if len(sys.argv) > 2 else 35
    
    verify_filters(country_id=c_id, tech_id=t_id)
