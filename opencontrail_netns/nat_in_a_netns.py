import argparse
import sys

from instance_provisioner import Provisioner
from lxc_manager import LxcManager
from vrouter_control import interface_register
from service_manage import ServiceManager

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
        'api-server': '127.0.0.1',
        'api-port': 8082,
        'project': 'default-domain:default-project',
        'network': 'default-network',
    }
    parser.set_defaults(**defaults)
    parser.add_argument("-s", "--api-server", help="API server address")
    parser.add_argument("-p", "--api-port", type=int, help="API server port")
    parser.add_argument("-p", "--project", help="OpenStack project name")
    parser.add_argument("-n", "--left-network", help="Primary network")
    parser.add_argument("-o", "--right-network", help="Outbound traffic network")
    parser.add_argument("daemon", help="Daemon Name")

    arguments = parser.parse_args(sys.argv)

    lxc = LxcManager()
    provisioner = Provisioner(api_server=arguments.api_server,
                              api_port=arguments.api_port,
                              project=arguments.project)

    instance_name = '%s-%s' % (socket.gethostname(), arguments.daemon)
    vm = provisioner.virtual_machine_locate(instance_name)

    vmi_left = provisioner.vmi_locate(vm, arguments.left_network, 'veth0')
    vmi_right = provisioner.vmi_locate(vm, arguments.right_network, 'veth1')

    lxc.namespace_init(arguments.daemon)
    if vmi_left:
        ifname = lxc.interface_update(arguments.daemon, vmi_left, 'veth0')
        interface_register(vm, vmi_left, ifname)
    if vmi_right:
        ifname = lxc.interface_update(arguments.daemon, vmi_right, 'veth1')
        interface_register(vm, vmi_right, ifname)

    ip_prefix = provisioner.get_interface_ip_prefix(vmi_left)
    lxc.interface_config(arguments.daemon, 'veth0', ip_prefix=ip_prefix)

    service_chain = ServiceManager(arguments.api_server, arguments.api_port,
                                   arguments.left_network,
                                   arguments.right_network,
                                   project=arguments.project)
    service_chain.create_service_template()
    service_chain.create_service_instance()
    service_chain.create_policy_service_chain()

def main(args_str=None):
    service_chain_start()
# end main

if __name__ == "__main__":
    main()
