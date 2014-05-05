#!/usr/bin/env python

import argparse
import socket
import sys

from instance_provisioner import Provisioner
from lxc_manager import LxcManager
from vrouter_control import interface_register
from service_manage import ServiceManager

def build_network_name(domain_name, project_name, network_name):
    if len(network_name.split(':')) == 3:
        return network_name
    return "%s:%s:%s" % (domain_name, project_name, network_name.split(':')[-1])

def service_chain_start():
    """
    Creates a virtual-machine and vmi object in the API server.
    Creates a namespace and a veth interface pair.
    Associates the veth interface in the master instance with the vrouter.
    Create a service template.
    Create a service instance with the netns virtual machine created.
    Create a network policy between nets to pass through the virtual-machine.
    """
    parser = argparse.ArgumentParser()
    defaults = {
        'api_server': '127.0.0.1',
        'api_port': 8082,
        'domain': 'default-domain',
        'project': 'default-project',
        'network': 'default-network',
    }
    parser.set_defaults(**defaults)
    parser.add_argument("-s", "--api-server", help="API server address")
    parser.add_argument("-p", "--api-port", type=int, help="API server port")
    parser.add_argument("--domain", help="OpenStack domain name",
                        action="store")
    parser.add_argument("--project", help="OpenStack project name",
                        action="store")
    parser.add_argument("public_network", help="Public network")
    parser.add_argument("-n", "--network", action='append', default=[], dest='networks',
                        help="Private network natted to the public")
    parser.add_argument("nat", help="Nat router name")
    args = parser.parse_args()

    lxc = LxcManager()
    provisioner = Provisioner(api_server=args.api_server,
                              api_port=args.api_port,
                              project=args.project)

    instance_name = '%s-%s' % (socket.gethostname(), args.nat)
    vm = provisioner.virtual_machine_locate(instance_name)

    left_network = build_network_name(args.domain, args.project, '%s-snat-net' % args.nat)
    provisioner.net_locate(left_network)
    vmi_left = provisioner.vmi_locate(vm, left_network, 'snat_itf', itf_type='left')
    right_network = build_network_name(args.domain, args.project, args.public_network)
    vmi_right = provisioner.vmi_locate(vm, right_network, 'gw', itf_type='right')

    lxc.namespace_init(args.nat)
    if vmi_left:
        ifname = lxc.interface_update(args.nat, vmi_left, 'snat_itf')
        interface_register(vm, vmi_left, ifname)
    if vmi_right:
        ifname = lxc.interface_update(args.nat, vmi_right, 'gw')
        interface_register(vm, vmi_right, ifname)

    ip_prefix = provisioner.get_interface_ip_prefix(vmi_left)
    lxc.interface_config(args.nat, 'snat_itf', advertise_default=False,
                         ip_prefix=ip_prefix)

    ip_prefix = provisioner.get_interface_ip_prefix(vmi_right)
    lxc.interface_config(args.nat, 'gw', advertise_default=False,
                         ip_prefix=ip_prefix)

    right_gw = provisioner.get_network_gateway(right_network)
    lxc.set_default_route(args.nat, right_gw, 'gw')

    service_chain = ServiceManager(args.api_server, args.api_port,
                                   left_network,
                                   right_network,
                                   project=args.project)
    st_uuid = service_chain.create_service_template()
    si_uuid = service_chain.create_service_instance()
    service_chain.create_policy_service_chain()
    vm_uuid = service_chain.associate_virtual_machine(vm.uuid)

    rt_obj = service_chain.create_default_route()
    for network in args.networks:
        network_name = build_network_name(args.domain, args.project, network)
        network_cidr = provisioner.get_network_subnet_cidr(network_name)
        lxc.set_nat(args.nat, network_cidr, 'snat_itf')
        lxc.set_route_via_interface(args.nat, network_cidr, 'snat_itf')
        service_chain.add_route_table(rt_obj, network)

if __name__ == "__main__":
    service_chain_start()
