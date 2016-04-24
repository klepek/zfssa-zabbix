# 	 copyright: Jan Klepek <jan(at)klepek.cz>
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
password="rest"
zabbix_dir="/etc/zabbix"

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
			print "master found: "+ip
			master=ip
		cl.logout()
	# check if we found any master
	if not master:
		raise RestException("cluster master not found")

	return master

def print_num(num):
	# B -> kB
	num = num/1024
	# kB -> MB
	num = num/1024
	print('%.2f' % num)
	return

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

def get_pool_usage(client, pool, type):
	try:
		data = client.get("/api/storage/v1/pools/%s" % pool,status=Status.OK)

	except RestException as rest_error:
		print rest_error
		sys.exit()	
	data2 = data.getdata('pool')['usage'][type]
	print_num(data2)
	return

def get_project_usage(client, id, type):
	pool = id.split("/")[0]
	project = id.split("/")[1]                                                           
	
	try:
		data = client.get("/api/storage/v1/pools/%s/projects/%s" % (pool, project) ,status=Status.OK)

	except RestException as rest_error:
		print rest_error
  	sys.exit()
	data2 = data.getdata('project')['usage'][type]
	return

def get_share_usage(client, id, type):
	pool = id.split("/")[0]  
	project = id.split("/")[1]
	share = id.split("/")[2]
	try:
		data = client.get("/api/storage/v1/pools/%s/projects/%s/filesystems/%s" % (pool,project,share) ,status=Status.OK)

	except RestException as rest_error:
		print rest_error
		sys.exit()
	if (type == "total"):
		print_num(data.getdata('filesystem')['quota'])
	if (type == "available"):
		if (data.getdata('filesystem')['quota_snap'] == "false"):
			print_num(data.getdata('filesystem')['space_data'])
		else:
			print_num(data.getdata('filesystem')['space_data']+data.getdata('filesystem')['space_snapshots'])
#	data2 = data.getdata('filesystems')['usage'][type]
#	print json.dumps(data.getdata('filesystem'))
	return

def build_discovery(client,uid):
	s = open(zabbix_dir+'/'+uid+'_zfssa_share_discovery','w')
	pr = open(zabbix_dir+'/'+uid+'_zfssa_project_discovery','w')
	p = open(zabbix_dir+'/'+uid+'_zfssa_pool_discovery','w')
	pools=get_pools(client)
	for pool in pools:
		projects=get_projects(client, pool)	
		p.write(pool+"\n")
		for project in projects:
			shares=get_shares(client, pool, project)
			pr.write(pool+'/'+project+"\n")
			for share in shares:
				s.write(pool+'/'+project+'/'+share+'\n')
	s.close()
	pr.close()
	p.close()
	return

if __name__ == "__main__":

# parse args
	parser = argparse.ArgumentParser()
	parser.add_argument("--host", help="ip/hostname of storage device, use two ips separated by comma if your storages have HA cluster", required = True)
	parser.add_argument("--action",nargs='*', help= "see below")
	parser.add_argument('discovery',nargs='*', help="(re)discover pools/projects/shares")
	parser.add_argument('pool_total',nargs='*', help="pool_total [pool] - pool total space/quota of [pool]")
	parser.add_argument('pool_available', nargs='*',help="pool_available [pool] - pool free space of [pool]")
	parser.add_argument('project_total', nargs='*',help="project_total [pool/project] - project total space/quota of [pool/project]")
	parser.add_argument('share_total', nargs='*',help="share_total [pool/project/share] - pool free space of [pool/project/share]")
	parser.add_argument('share_available', nargs='*',help="share_available [pool/project/share] - pool free space of [pool/project/share]")
	parser.add_argument('project_available', nargs='*',help="project_available [pool/project] - pool free space of [pool/project]")

	args = parser.parse_args()
#	print args
	temp=vars(args)
#	print json.dumps(temp)
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
	target = host

# connect to zfssa master host
	client = RestClient(host)
	result = client.login(user, password)

	if result.status != Status.CREATED:
		raise RestException("login failed", result)
		sys.exit()
	
	if (action == "discovery"):
		build_discovery(client,uid)
	if (action == 'pool_total'):
		get_pool_usage(client,target,'total')
	if (action == 'pool_available'):
		get_pool_usage(client,target,'available')
	if (action == 'project_total'):
		get_project_usage(client,target,'total')  
	if (action == 'project_available'):
		get_project_usage(client,target,'available')  
	if (action == 'share_total'):
		get_share_usage(client,target,'total')
	if (action == 'share_available'):
		get_share_usage(client,target,'available')

