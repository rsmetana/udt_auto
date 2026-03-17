import csv

with open('hosts.csv') as objects, open("hosts1.yml", "w") as outfile:
    reader = csv.reader(objects)
    object_list = csv.reader(objects)
    for row in object_list:
        school_name = row[0]
        school_ip = row[1]
        outfile.write(f'''
{school_name}:
  hostname: {school_ip}
  groups:
    - fortigates
  data:
    interfaces:
    ''')