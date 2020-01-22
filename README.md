# zfssa-zabbix
Zabbix template + scripts for ZFS storage appliance monitoring

Tired of SNMP messages from your Oracle ZFS Storage appliance and complicated processing in zabbix?

There is better way, use this template for Zabbix together with few scripts to get some basic monitoring.

## Why to use this?
- easy to deploy and extend

## How it works

Luckily, guys at Oracle implemented REST API and this script uses this to obtain data

## How to:

1] choose server which will talk with your ZFSSA storage and copy *.py files into /usr/local/bin/zabbix-zfssa/ (it can be your zabbix server)
2] setup cron  (replace <storage> and <zabbix-ip> with your values):
```
0 * * * * /usr/local/bin/zabbix-zfssa/zfssa.py --host <storage> --action all_pool_usage | zabbix_sender -i - -z <zabbix-ip> > /dev/null 2>&1
*/10 * * * * /usr/local/bin/zabbix-zfssa/zfssa.py --host <storage> --action all_share_usage | zabbix_sender -i - -z <zabbix-ip> > /dev/null 2>&1
0 * * * * /usr/local/bin/zabbix-zfssa/zfssa.py --host <storage> --action all_project_usage | zabbix_sender -i - -z <zabbix-ip> > /dev/null 2>&1
0 0 * * * /usr/local/bin/zabbix-zfssa/zfssa.py --host <storage> --action discovery
0 * * * * /usr/local/bin/zabbix-zfssa/zfssa.py --host <storage> --action hw_status | zabbix_sender -i - -z <zabbix-ip> > /dev/null 2>&1
0 0 * * * /usr/local/bin/zabbix-zfssa/zfssa.py --host <storage> --action replication_status | zabbix_sender -i - -z <zabbix-ip> > /dev/null 2>&1
```
3] add userparameter:
```
UserParameter=zfssa[*],/usr/local/bin/zabbix-zfssa/zfssa.py --host 1.1.1.1 --action "$1" "$2"
UserParameter=zfssa_pools.discovery,/bin/cat /etc/zabbix/zfssa_pool_discovery
UserParameter=zfssa_projects.discovery,/bin/cat /etc/zabbix/zfssa_project_discovery
UserParameter=zfssa_shares.discovery,/bin/cat /etc/zabbix/zfssa_share_discovery
UserParameter=zfssa_replica.discovery,/bin/cat /etc/zabbix/zfssa-zabbix/zfssa_replica_discovery
```
edit /usr/local/bin/zabbix-zfssa/zfssa.py and set user/password (Sorry, only one user/password for all monitored storages supported for now) and set management host to hostname which is set in zabbix.

4] import template and assign it to management host

## What it can do?

- LLD for pools/projects/shares/replicas
- items/triggers for disk utilization (ZFSSA native alerts do not work correctly, sigh!)
- some basic HW fault detection
- replica failure detection

## Future features

- cpu, caches, etc... utilization
- Better HW health (well, on the other hand, it would increase number of api calls :/ )
- IO operations/analytics datasets

## Limitations, Caveats & supported zfssa configs

- ZFSSA can be configured to failover cluster, without any HA ip adress for management interface, in that case you can put both ips into `--host` parameter (ie, `--host 1.1.1.1,1.1.1.2`) the script will try to autodetect "master" and use master for all queries or you can setup ZFSSA to have floating ip adress.
- only one ZFSSA cluster/host per management station (due to local cache of discovery file)
