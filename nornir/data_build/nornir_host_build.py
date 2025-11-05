import csv
with open('devs.csv') as info:
    info_list = csv.reader(info)
    for row in info_list:
        device = row[0]
        loopback = row[1]
        print(f'''{device}:
  hostname: {loopback}
  groups:
    - fortigates
  data:
  interfaces:''')