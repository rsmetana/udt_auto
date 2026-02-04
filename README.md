If you are copying over BDI/Vlan information provide by ENA. You are able to copy out the BDIs/Vlans out of the txt documents and paste them into input_config.txt
file. Once the BDI information is in the txt doc you can run interfaces_yml.py. This python script will ask for the hostname and ip you plan on assigning to the Fortigate.
Interfaces.py will build a singlular host file with your interfaces already defined. These files will be located in the int_yml folder. Once you have all the host files you are able
to copy these outputs to hosts.yml file for a singular location to adjust any vars you want. config_build.py in the nornir folder will build LAN handoff information you define under a host 
in the hosts.yml file. The legend below shows availble options you are able to define.

example-school:
  hostname: 100.64.0.100
  groups:
    - fortigates
  data:
    interfaces:
      - name: x1
        ip: 10.43.0.1
        mask: 255.255.252.0
        description: ::LAN
        route_down: 
        - dest: 10.0.0.0 255.255.0.0
          next_hop: 10.43.3.10
        secondary_ip:
        - ip: 154.9.32.1
          mask: 255.255.255.248
      - name: vlan100
        type: vlan
        ip: 192.168.0.1
        mask: 255.255.255.0
        description: Voice
        build_dhcp_server: True
      - name: vlan101
        type: vlan
        ip: 10.123.0.1
        mask: 255.255.255.0
        description: data#2
        helper_ip: [10.10.10.1,10.10.10.2]
        set_port: port9