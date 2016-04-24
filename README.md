# zfssa-zabbix
Zabbix template + scripts for ZFS storage appliance monitoring

Tired of SNMP messages from your Oracle ZFS Storage appliance and complicated processing in zabbix?

There is better way, use this fancy template for Zabbix together with few scripts to get some basic monitoring.

## Why to use this?
- easy to deploy and extend

## How it works

Luckily, guys at Oracle have REST API and this script uses that

## How to:

1] choose server which will talk with your ZFSSA storage and copy *.py files into /usr/local/bin/zabbix-zfssa/ (it can be your zabbix server)
2] add userparameter:
`
UserParameter=zfssa[*],/usr/local/bin/zabbix-zfssa/zfssa.py --host <ip> --action "$1" "$2"
UserParameter=oracle_instances.discovery,/bin/cat /etc/zabbix/oracle_instances

`
edit /usr/local/bin/zabbix-zfssa/zfssa.py and set user/password (Sorry, only one user/password for all monitored storages supported for now)

## What it can do?

- LLD for pools/projects/shares
- items/triggers for disk utilization (ZFSSA native alerts do not work correctly, sigh!)

## Future features

- cpu, caches, etc... utilization
- HW health
- user/password per zfs storage

## Caveats & supported zfssa configs

- ZFSSA can be configured to failover cluster, without any HA ip adress for management interface, in that case you can put both ips into `--host` parameter (ie, `--host 1.1.1.1,1.1.1.2`) the script will try to autodetect "master" and use master for all queries or you can setup ZFSSA to have floating ip adress.
