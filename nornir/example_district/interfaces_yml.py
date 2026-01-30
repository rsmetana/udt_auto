
import re
import yaml
import os
import sys

# ---------- YAML formatting helpers ----------

class FlowList(list):
    """A list type that should be rendered in YAML flow style (inline)."""
    pass

class CustomDumper(yaml.Dumper):
    """Custom dumper where only FlowList is rendered in flow style."""
    pass

def _represent_flow_list(dumper, data):
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)

# Register only FlowList for flow style; normal list uses default (block) style
CustomDumper.add_representer(FlowList, _represent_flow_list)

# ---------- Parsing logic ----------

def parse_cisco_config(config_str):
    """
    Parses Cisco-like config into a list of interface dictionaries:
    - Supports 'interface <name>' blocks
    - Extracts description, primary IP/mask, secondary IPs, helper addresses
    - Captures admin state via 'shutdown' / 'no shutdown' -> admin_down: true/false
    - SPECIAL CASE: BDI1 -> 'x1' (physical)
    - Other BDIs: BDI<N> -> vlan<N> with 'type: vlan'
    - Only the first primary 'ip address' is kept; 'secondary' lines go to 'secondary_ip'
    """
    # Split at "interface" headers, case-insensitive, line-start aware
    interface_configs = re.split(r'(?im)^\s*interface\s+', config_str)[1:]
    interfaces_list = []

    for config in interface_configs:
        # Normalize lines and drop blanks
        lines = [ln.rstrip() for ln in config.strip().split('\n') if ln.strip()]
        if not lines:
            continue

        # First line is the interface name
        raw_name = lines[0].strip()
        name_upper = raw_name.upper()

        # --- Mapping rules ---
        if name_upper == 'BDI1':
            int_data = {'name': 'x1'}  # Special case: physical port
        elif name_upper.startswith('BDI'):
            vlan_id = raw_name[3:].strip()
            int_data = {'name': f'vlan{vlan_id}', 'type': 'vlan'}
        else:
            int_data = {'name': raw_name}

        # Regex patterns
        desc_pattern = re.compile(r'(?i)^\s*description\s+(.+)$')
        # Capture ip, mask, and whether "secondary" is present
        ip_pattern = re.compile(r'(?i)^\s*ip address\s+([\d.]+)\s+([\d.]+)(\s+secondary)?$')
        helper_pattern = re.compile(r'(?i)^\s*ip helper-address\s+([\d.]+)$')
        # NEW: admin state
        shutdown_pattern = re.compile(r'(?i)^\s*shutdown\s*$')
        no_shutdown_pattern = re.compile(r'(?i)^\s*no\s+shutdown\s*$')

        helper_addresses = []
        secondary_addrs = []

        # Parse the rest of the lines for this interface, starting from the second line
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            m = desc_pattern.match(line)
            if m:
                int_data['description'] = m.group(1).strip()
                continue

            m = ip_pattern.match(line)
            if m:
                ip_addr = m.group(1)
                mask = m.group(2)
                is_secondary = bool(m.group(3))

                if is_secondary:
                    # Append to secondary_ip list
                    secondary_addrs.append({'ip': ip_addr, 'mask': mask})
                else:
                    # Only use the first primary IP (without 'secondary')
                    if 'ip' not in int_data:
                        int_data['ip'] = ip_addr
                        int_data['mask'] = mask
                continue

            m = helper_pattern.match(line)
            if m:
                helper_addresses.append(m.group(1))
                continue

            # --- NEW: capture admin state ---
            m = shutdown_pattern.match(line)
            if m:
                int_data['admin_down'] = True
                continue

            m = no_shutdown_pattern.match(line)
            if m:
                int_data['admin_down'] = False
                continue

        # Attach secondary_ip list if present (block style)
        if secondary_addrs:
            int_data['secondary_ip'] = secondary_addrs

        # Render helpers inline if present
        if helper_addresses:
            int_data['helper'] = FlowList(helper_addresses)

        interfaces_list.append(int_data)

    return interfaces_list

# ---------- YAML generation ----------

def generate_yaml_output(device_name, ip_or_hostname, interfaces):
    """
    Builds YAML structure exactly like requested:
    {device}:
      hostname: {IP}
      groups:
      - fortigates
      data:
        interfaces: ...
    """
    output_structure = {
        device_name: {
            'hostname': ip_or_hostname,
            'groups': ['fortigates'],  # block list under default dumper
            'data': {
                'interfaces': interfaces
            }
        }
    }

    return yaml.dump(
        output_structure,
        Dumper=CustomDumper,
        sort_keys=False,
        explicit_start=False,  # set True if you want the '---' doc start
        indent=2
    )

# ---------- Main ----------

def main():
    # Prompt for device name and hostname/IP
    device = input("Enter device name (used as top-level key and output filename): ").strip()
    while not device:
        device = input("Device name cannot be empty. Enter device name: ").strip()

    hostname_or_ip = input("Enter hostname or IP: ").strip()
    while not hostname_or_ip:
        hostname_or_ip = input("Hostname/IP cannot be empty. Enter hostname or IP: ").strip()

    input_filename = 'input_config.txt'

    # Ensure output directory exists and sanitize filename
    out_dir = 'int_yml'
    os.makedirs(out_dir, exist_ok=True)
    safe_device = "".join(c if c.isalnum() or c in ('-', '_') else '-' for c in device)
    output_filename = os.path.join(out_dir, f"{safe_device}.txt")

    if not os.path.exists(input_filename):
        print(f"Error: Input file '{input_filename}' not found.")
        print("Create 'input_config.txt' in the same directory with your Cisco config.")
        sys.exit(1)

    with open(input_filename, 'r') as f:
        config_data = f.read()

    interfaces = parse_cisco_config(config_data)
    yaml_output = generate_yaml_output(device, hostname_or_ip, interfaces)

    with open(output_filename, 'w') as f:
        f.write(yaml_output)

    print(f"Successfully processed configuration.")
    print(f"- Device: {device}")
    print(f"- Hostname/IP: {hostname_or_ip}")
    print(f"- Interfaces parsed: {len(interfaces)}")
    print(f"- Saved YAML to: {output_filename}")

if __name__ == "__main__":
    main()
