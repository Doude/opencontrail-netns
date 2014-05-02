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
    parser.add_argument("left_network", help="Left network")
    parser.add_argument("right_network", help="Right network")
    parser.add_argument("daemon", help="Daemon Name")
    parser.add_argument("-s", "--api-server", help="API server address")
    parser.add_argument("-p", "--api-port", type=int, help="API server port")
    parser.add_argument("--domain", help="OpenStack domain name",
                        action="store")
    parser.add_argument("--project", help="OpenStack project name",
                        action="store")

    arguments = parser.parse_args()

    lxc = LxcManager()
    provisioner = Provisioner(api_server=arguments.api_server,
                              api_port=arguments.api_port,
                              project=arguments.project)

    instance_name = '%s-%s' % (socket.gethostname(), arguments.daemon)

    vm = provisioner.virtual_machine_locate(instance_name)

    left_network = build_network_name(arguments.domain, arguments.project, arguments.left_network)
    vmi_left = provisioner.vmi_locate(vm, left_network, 'int0', 'left')
    right_network = build_network_name(arguments.domain, arguments.project, arguments.right_network)
    vmi_right = provisioner.vmi_locate(vm, right_network, 'gw', 'right')

    lxc.namespace_init(arguments.daemon)
    if vmi_left:
        ifname = lxc.interface_update(arguments.daemon, vmi_left, 'int0')
        interface_register(vm, vmi_left, ifname)
    if vmi_right:
        ifname = lxc.interface_update(arguments.daemon, vmi_right, 'gw')
        interface_register(vm, vmi_right, ifname)

    ip_prefix = provisioner.get_interface_ip_prefix(vmi_left)
    lxc.interface_config(arguments.daemon, 'int0', advertise_default=False,
                         ip_prefix=ip_prefix)

    ip_prefix = provisioner.get_interface_ip_prefix(vmi_right)
    lxc.interface_config(arguments.daemon, 'gw', advertise_default=False,
                         ip_prefix=ip_prefix)

    left_cidr = provisioner.get_network_subnet_cidr(left_network)
    right_gw = provisioner.get_network_gateway(right_network)
    lxc.set_nat(arguments.daemon, left_cidr)
    lxc.set_default_route(right_gw, 'gw')

    service_chain = ServiceManager(arguments.api_server, arguments.api_port,
                                   arguments.left_network,
                                   arguments.right_network,
                                   project=arguments.project)
    st_uuid = service_chain.create_service_template()
    si_uuid = service_chain.create_service_instance()
    service_chain.create_policy_service_chain()
    vm_uuid = service_chain.associate_virtual_machine(vm.uuid)
    rt_uuid = service_chain.create_default_route()

if __name__ == "__main__":
    service_chain_start()
