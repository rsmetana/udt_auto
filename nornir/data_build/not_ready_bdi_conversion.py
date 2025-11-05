import ipaddress

def convert_bdi_to_fortigate(cisco_config):
    """
    Converts Cisco BDI configuration into FortiGate CLI commands.
    BDI interfaces are mapped to FortiGate interfaces and VLANs.
    """
    fortigate_config = []
    lines = cisco_config.strip().splitlines()
    interfaces = {}
    current_interface = None
    dhcp_pools = {}
    current_dhcp = None

    # Parse Cisco config
    for line in lines:
        line = line.strip()
        if line.startswith("interface BDI"):
            interface_name = line.split()[1]
            if interface_name == 'BDI1':
                # Map BDI1 to FortiGate physical interface x1
                interfaces[interface_name] = {'name': 'x1', 'ips': [], 'description': '', 'helper': []}
                current_interface = interface_name
            else:
                # Map other BDIs to VLAN sub-interfaces on x1
                vlan_id = interface_name.replace('BDI', '')
                interfaces[interface_name] = {'name': f'x1', 'vlan': vlan_id, 'ips': [], 'description': '', 'helper': []}
                current_interface = interface_name

        elif line.startswith("ip dhcp pool"):
            pool_name = line.split()[2]
            dhcp_pools[pool_name] = {}
            current_dhcp = pool_name

        elif current_interface and line.startswith("description"):
            interfaces[current_interface]['description'] = ' '.join(line.split()[1:])

        elif current_interface and line.startswith("ip address"):
            parts = line.split()
            ip = parts[2]
            netmask = parts[3]
            interfaces[current_interface]['ips'].append({'ip': ip, 'mask': netmask})

        elif current_interface and line.startswith("ip helper-address"):
            parts = line.split()
            helper_ip = parts[1]
            interfaces[current_interface]['helper'].append(helper_ip)

        elif current_dhcp and line.startswith("network"):
            parts = line.split()
            network = parts[1]
            netmask = parts[2]
            dhcp_pools[current_dhcp]['network'] = ipaddress.IPv4Network(f"{network}/{netmask}", strict=False)

        elif current_dhcp and line.startswith("default-router"):
            parts = line.split()
            dhcp_pools[current_dhcp]['router'] = parts[1]

        elif current_dhcp and line.startswith("option 42"):
            parts = line.split()
            dhcp_pools[current_dhcp]['ntp'] = parts[2:]
        
        elif current_dhcp and line.startswith("option 2"):
            parts = line.split()
            # FortiGate does not support hex format for option 2, so this is skipped.
            # In a real scenario, this would need manual conversion or handling.
            pass
    
    # Generate FortiGate CLI configuration
    
    # Interface configuration
    for bdi_name, props in interfaces.items():
        if 'vlan' in props:
            # VLAN interface
            vlan_id = props['vlan']
            vlan_interface_name = f"{props['name']}.{vlan_id}"
            primary_ip = props['ips'][0]['ip']
            primary_mask = props['ips'][0]['mask']
            
            fortigate_config.append(f"\nconfig system interface")
            fortigate_config.append(f"    edit \"{vlan_interface_name}\"")
            fortigate_config.append(f"        set vlanid {vlan_id}")
            fortigate_config.append(f"        set interface \"{props['name']}\"")
            fortigate_config.append(f"        set ip {primary_ip} {primary_mask}")
            fortigate_config.append(f"        set description \"{props['description']}\"")
            fortigate_config.append(f"        set allowaccess ping https ssh")
            if props['helper']:
                fortigate_config.append(f"        set dhcp-relay-service enable")
                fortigate_config.append(f"        set dhcp-relay-ip \"{'\" \"'.join(props['helper'])}\"")
            fortigate_config.append(f"    next")
            fortigate_config.append(f"end")
            
            # Handle additional IPs as secondary IPs
            for secondary_ip in props['ips'][1:]:
                fortigate_config.append(f"\nconfig system interface")
                fortigate_config.append(f"    edit \"{vlan_interface_name}\"")
                fortigate_config.append(f"        config secondaryip")
                fortigate_config.append(f"            edit 0")
                fortigate_config.append(f"                set ip {secondary_ip['ip']} {secondary_ip['mask']}")
                fortigate_config.append(f"            next")
                fortigate_config.append(f"        end")
                fortigate_config.append(f"    next")
                fortigate_config.append(f"end")
                
        else:
            # Physical interface x1 (BDI1)
            primary_ip = props['ips'][0]['ip']
            primary_mask = props['ips'][0]['mask']
            
            fortigate_config.append(f"\nconfig system interface")
            fortigate_config.append(f"    edit \"{props['name']}\"")
            fortigate_config.append(f"        set ip {primary_ip} {primary_mask}")
            fortigate_config.append(f"        set description \"{props['description']}\"")
            fortigate_config.append(f"        set allowaccess ping https ssh")
            if props['helper']:
                fortigate_config.append(f"        set dhcp-relay-service enable")
                fortigate_config.append(f"        set dhcp-relay-ip \"{'\" \"'.join(props['helper'])}\"")
            fortigate_config.append(f"    next")
            fortigate_config.append(f"end")

            # Handle additional IPs as secondary IPs
            for secondary_ip in props['ips'][1:]:
                fortigate_config.append(f"\nconfig system interface")
                fortigate_config.append(f"    edit \"{props['name']}\"")
                fortigate_config.append(f"        config secondaryip")
                fortigate_config.append(f"            edit 0")
                fortigate_config.append(f"                set ip {secondary_ip['ip']} {secondary_ip['mask']}")
                fortigate_config.append(f"            next")
                fortigate_config.append(f"        end")
                fortigate_config.append(f"    next")
                fortigate_config.append(f"end")

    # DHCP Server configuration (for native FortiGate DHCP scope)
    for pool_name, props in dhcp_pools.items():
        vlan_id = next(v for k, v in interfaces.items() if 'vlan' in v and props['network'].overlaps(v['network'])).get('vlan')
        interface_name = f"x1.{vlan_id}"

        fortigate_config.append(f"\nconfig system dhcp server")
        fortigate_config.append(f"    edit 0") # FortiGate uses a numerical index
        fortigate_config.append(f"        set interface \"{interface_name}\"")
        fortigate_config.append(f"        set dns-server1 8.8.8.8") # Example, should be updated with actual DNS
        fortigate_config.append(f"        set default-gateway {props['router']}")
        fortigate_config.append(f"        set netmask {str(props['network'].netmask)}")
        fortigate_config.append(f"        config ip-range")
        fortigate_config.append(f"            edit 1")
        # FortiGate needs start and end IP, derive from network
        first_host = str(props['network'][1])
        last_host = str(props['network'][-2])
        fortigate_config.append(f"                set start-ip {first_host}")
        fortigate_config.append(f"                set end-ip {last_host}")
        fortigate_config.append(f"            next")
        fortigate_config.append(f"        end")
        if 'ntp' in props:
            fortigate_config.append(f"        set ntp-server1 {' '.join(props['ntp'])}")
        fortigate_config.append(f"    next")
        fortigate_config.append(f"end")

    return "\n".join(fortigate_config)

# Cisco BDI configuration text
cisco_config = """
interface BDI1
 description E A Cox Middle School LAN
 ip address 10.92.180.1 255.255.254.0 secondary
 ip address 10.92.10.1 255.255.254.0 secondary
 ip address 10.10.0.1 255.255.128.0
 ip helper-address 10.92.0.4
 ip helper-address 10.46.0.12
interface BDI10
 description Voice LAN
 ip address 10.93.10.1 255.255.255.0 secondary
 ip address 10.10.128.1 255.255.192.0
 ip helper-address 10.10.0.5
interface BDI20
 description Camera LAN
 ip address 10.94.40.1 255.255.255.0 secondary
 ip address 10.10.192.1 255.255.192.0
 ip helper-address 10.10.0.5
interface BDI50
 description Student Traffic
 ip address 10.11.0.1 255.255.0.0
 ip helper-address 10.10.0.5

ip dhcp pool VoIP
 network 10.10.128.0 255.255.192.0
 default-router 10.10.128.1 
 option 2 hex ffff.aba0
 option 42 ip 10.10.128.1
"""

# Call the function to generate the FortiGate configuration
fortigate_cli = convert_bdi_to_fortigate(cisco_config)
print(fortigate_cli)
