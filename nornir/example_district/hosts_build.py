import csv

with open('host_build.csv') as objects:
    object_list = csv.reader(objects)
    for row in object_list:
        school_name = row[0]
        school_ip = row[1]
        print(f'''{school_name}:
  hostname: {school_ip}
  groups:
    - fortigates
  data:
    interfaces:''')