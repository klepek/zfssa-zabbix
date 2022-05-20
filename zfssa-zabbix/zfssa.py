#!/usr/bin/env python
#    copyright: Jan Klepek <jan(at)klepek.cz>
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from restclientlib import RestClient, RestException, Status
import urllib2
import json
import pprint
import sys
import argparse, textwrap

user="rest"
password="rest_api"
zabbix_dir="/etc/zabbix/zfssa-zabbix"
management_host="management-host"

def find_cluster_owner(cluster):
	master=None
	for ip in cluster:
		cl = RestClient(ip)
		try:
			result = cl.login(user, password)
		except urllib2.URLError as e:
			print "something went wrong during connection to host: https://"+ip+":215"
			continue
		if result.status != Status.CREATED:
			raise RestException("login failed", result)
			sys.exit()
  
		try: 
			cluster_state = cl.get("/api/hardware/v1/cluster",status=Status.OK)
		except RestException as rest_error:
			print rest_error
			sys.exit()

		if (cluster_state.getdata('cluster')['state'] == "AKCS_OWNER"):
#			print "master found: "+ip
			master=ip
		cl.logout()
	# check if we found any master
	if not master:
		raise RestException("cluster master not found")

	return master

def print_zabbix(metric, value):
#	print metric
#	print value
	print management_host+" zfssa["+metric+"] "+str(value)
	return

def format_num(num):
	# B -> kB
	num = num/1024
	# kB -> MB
	num = num/1024
#	print('%.2f' % num)
	return format(num, '.2f')

def get_pools(client):

	try:
		data = client.get("/api/storage/v1/pools",status=Status.OK)

	except RestException as rest_error:
		print rest_error
		sys.exit()
	data2=data.getdata("pools")
	ret_pools = []
	for s in data2:
		pool_name = s['name']
		ret_pools.append(pool_name)
	return ret_pools

def get_projects(client, pool):
	try:
		data = client.get("/api/storage/v1/pools/%s/projects" % pool,status=Status.OK)

	except RestException as rest_error:
		print rest_error
		sys.exit()

	data2=data.getdata("projects")
	ret_projects = []
	for s in data2:
		ret_projects.append(s['name'])
	return ret_projects

def get_shares(client, pool, project):
	try:
		data = client.get("/api/storage/v1/pools/%s/projects/%s/filesystems" % (pool,project),status=Status.OK)
	except RestException as rest_error:
		print rest_error
		sys.exit()

	data2=data.getdata("filesystems")
	ret_sh = []
	for s in data2:
		ret_sh.append(s['name'])
	return ret_sh

def get_all_pool_usage(client):
	pools = get_pools(client)
	for pool in pools:
		data = get_pool_usage(client,pool)
		print_zabbix('pool_pfree,'+pool,data['pfree']);
		print_zabbix('pool_available,'+pool,format_num(data['available']));
		print_zabbix('pool_total,'+pool,format_num(data['total']));  
	return

def get_pool_usage(client, pool):
	try:
		data = client.get("/api/storage/v1/pools/%s" % pool,status=Status.OK)

	except RestException as rest_error:
		print rest_error
		sys.exit()
# calculate percent free
	a={}
	a['pfree'] = (data.getdata('pool')['usage']['available']/data.getdata('pool')['usage']['total'])*100
	a['available'] = data.getdata('pool')['usage']['available']
	a['total'] = data.getdata('pool')['usage']['total']
	return a

def get_all_project_usage(client):
	pools = get_pools(client)
	for pool in pools:
		projects=get_projects(client, pool)
		for project in projects:
			data = get_project_usage(client,pool,project)
			print_zabbix('project_pfree,'+pool+'/'+project,data['pfree']);
			print_zabbix('project_available,'+pool+'/'+project,format_num(data['available']));
			print_zabbix('project_total,'+pool+'/'+project,format_num(data['total']));
	return

def get_project_usage(client,pool,project):
#	pool = id.split("/")[0]
#	project = id.split("/")[1]                                                           
	
	try:
		data2 = client.get("/api/storage/v1/pools/%s/projects/%s" % (pool, project) ,status=Status.OK)

	except RestException as rest_error:
		print rest_error
 	 	sys.exit()
	#print data2
	data = data2.getdata('project')
	if (data['quota'] == 0):
		quota=data['space_available']
	else:
		quota=data['quota']
	free_space = quota-data['space_data']
	a={}
	a['pfree'] =(free_space/quota)*100
	a['available']  = free_space
	a['total'] = quota
	return a

def get_all_share_usage(client):
	pools = get_pools(client)
	for pool in pools:
		projects=get_projects(client, pool)
		for project in projects:
			shares=get_shares_usage(client, pool, project)
			for share in shares:
				print_zabbix('share_pfree,'+pool+'/'+project+'/'+share['name'],share['pfree']);
				print_zabbix('share_available,'+pool+'/'+project+'/'+share['name'],format_num(share['available']));
				print_zabbix('share_total,'+pool+'/'+project+'/'+share['name'],format_num(share['total']));

def get_replica_status(client, id):
	try:
		data2 = client.get("/api/storage/v1/replication/actions/%s" % id,status=Status.OK)
	except RestException as rest_error:
		print rest_error
		sys.exit()
	data3=data2.getdata('action')
	if data3['enabled']:
		if data3['last_result']=="success":
			return "0"
		else:
			return "1"
	else:
	# disabled replication, consider as ok
			return "0"
	return 

def get_replication_status(client, discovery=0):
	try:
		data2 = client.get("/api/storage/v1/replication/actions",status=Status.OK)

	except RestException as rest_error:
		print rest_error
		sys.exit()
	data3=data2.getdata('actions')
	b=[]
	for data in data3:
		path = None
		if data.has_key("pool"):
			path=data['pool']
		if data.has_key("project"):
			path=path+"/"+data['project']
		if data.has_key("share"):
			path=path+"/"+data['share']
		if (discovery==0):
			status = get_replica_status(client, data['id'])
			print_zabbix('replication_status,'+path,status)
		else:
			b.append(path)
	if (discovery==1):
		return b
	return

def get_shares_usage(client, pool,project):
#	pool = id.split("/")[0]  
#	project = id.split("/")[1]
#	share = id.split("/")[2]
	try:
		data2 = client.get("/api/storage/v1/pools/%s/projects/%s/filesystems" % (pool,project) ,status=Status.OK)

	except RestException as rest_error:
		print rest_error
		sys.exit()
	b=[]
	data3=data2.getdata('filesystems')
	for data in data3:
		a={}
		if (data['quota'] == 0):
			quota=data['space_available']
		else:
			quota=data['quota']
		if (data['quota_snap'] is False):
			free_space = quota-data['space_data']
		else:
			free_space = quota-(data['space_data']+data['space_snapshots'])
		a['name'] = data['name']
		a['pfree'] = (free_space/quota)*100
		a['total']=quota
		a['available']=free_space
		b.append(a)
	return b

def get_hw_status(client):
	try:
		data2 = client.get("/api/hardware/v1/chassis" ,status=Status.OK)

	except RestException as rest_error:
		print rest_error
		sys.exit()
	data3=data2.getdata('chassis')
	fault=0
	for data in data3:
		if (data['faulted'] is True):
			fault+=1
	print_zabbix('hw_fault',fault)
	return

def build_discovery(client,uid):
	s = open(zabbix_dir+'/zfssa_share_discovery','w')
	pr = open(zabbix_dir+'/zfssa_project_discovery','w')
	p = open(zabbix_dir+'/zfssa_pool_discovery','w')
	r = open(zabbix_dir+'/zfssa_replica_discovery','w')

	pools=get_pools(client)
	pool_data=[]
	project_data=[]
	share_data=[]
	replica_data=[]
	for pool in pools:
		projects=get_projects(client, pool)
		pool_tmp = {}
		pool_tmp["{#POOL}"] = pool
		pool_data.append(pool_tmp) 
		for project in projects:
			shares=get_shares(client, pool, project)
			pr_tmp = {}
			pr_tmp["{#PROJECT}"] = pool+'/'+project
			project_data.append(pr_tmp)
			#pr.write(pool+'/'+project+"\n")
			for share in shares:
				sh_tmp = {}
				sh_tmp["{#SHARE}"] = pool+'/'+project+'/'+share
				share_data.append(sh_tmp)
				#s.write(pool+'/'+project+'/'+share+'\n')
	data={}
	data["data"]=pool_data
	p.write(json.dumps(data, indent=4))
	data["data"]=project_data
	pr.write(json.dumps(data, indent=4))
	data["data"]=share_data
	s.write(json.dumps(data, indent=4))
	dt2 = get_replication_status(client, 1)
	for dt in dt2:
		dt_temp = {}
		dt_temp["{#REPLICA}"] = dt
		replica_data.append(dt_temp)
	data["data"]=replica_data
	r.write(json.dumps(data, indent=4))
	s.close()
	pr.close()
	p.close()
	r.close()
	return

if __name__ == "__main__":

# parse args
	parser = argparse.ArgumentParser()
	parser.add_argument("--host", help="ip/hostname of storage device, use two ips separated by comma if your storages have HA cluster", required = True)
	parser.add_argument("--action",nargs='*', help= "see below")
	parser.add_argument('discovery',nargs='*', help="(re)discover pools/projects/shares")
	parser.add_argument('all_pool_usage',nargs='*', help="all_pool_data - pool total space/quota of all pools")
	parser.add_argument('all_project_usage',nargs='*', help="all_project_data - project total space/quota of all projects")
	parser.add_argument('all_share_usage',nargs='*', help="all_share_data - share total space/quota of all shares")
	parser.add_argument('hw_status',nargs='*', help="get any hw fault")
	parser.add_argument('replication_status',nargs='*', help="get replication statuses")

	args = parser.parse_args()
#	print args
	temp=vars(args)
	#print json.dumps(temp)
	host=temp['host']
# check if we have two hosts or not
	cluster=host.split(',')
	uid=host
	if (len(cluster)==1):
# single node
		host=cluster[0]
	else:
# clusterware
		try:
			host=find_cluster_owner(cluster)
		except RestException as e:
			print "unable to find cluster master"
			sys.exit()
	action=temp['action'][0]
	if (len(temp['action'])>1):
		target = temp['action'][1]

# connect to zfssa master host
	client = RestClient(host)
	result = client.login(user, password)

	if result.status != Status.CREATED:
		raise RestException("login failed", result)
		sys.exit()
	
	if (action == "discovery"):
		build_discovery(client,uid)
	if (action == "all_pool_usage"):
		get_all_pool_usage(client)
	if (action == "all_project_usage"):
		get_all_project_usage(client)
	if (action == "all_share_usage"):
		get_all_share_usage(client)
	if (action == "replication_status"):
		get_replication_status(client)
	if (action == "hw_status"):
		get_hw_status(client)

