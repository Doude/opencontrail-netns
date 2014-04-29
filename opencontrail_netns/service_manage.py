#!/bin/env python

from vnc_api.vnc_api import *


class ServiceManager(object):
    def __init__(self, api_server, api_port, left, right, project='default-project'):
        self._client = VncApi(api_server_host=api_server,
                              api_server_port=api_port)
        self._default_domain = 'default-domain'
        self._project = project
        self._st_name = "netns-nat-template"
        self._si_name = "netns-nat-instance"
        self._np_name = "netns_nat_policy"
        self._left = left
        self._right = right

    def create_service_template(self, name=None):
        if name:
            self._st_name = name
        print "Creating service template %s" % (self._st_name)
        st_fq_name = [self._default_domain, self._st_name]
        try:
            st_obj = self._client.service_template_read(fq_name=st_fq_name)
            st_uuid = st_obj.uuid
        except NoIdError:
            domain = self._client.domain_read(fq_name_str=self._default_domain)
            st_obj = ServiceTemplate(name=self._st_name, domain_obj=domain)
            st_uuid = self._client.service_template_create(st_obj)

        svc_properties = ServiceTemplateType()
        #svc_properties.set_image_name(self._args.image_name)
        svc_properties.set_service_scaling(False)
        svc_properties.set_service_type('firewall')
        svc_properties.set_service_mode('in-network-nat')

        if_list = [['left', False], ['right', False]]
        for itf in if_list:
            if_type = ServiceTemplateInterfaceType(shared_ip=itf[1])
            if_type.set_service_interface_type(itf[0])
            svc_properties.add_interface_type(if_type)

        st_obj.set_service_template_properties(svc_properties)
        self._client.service_template_update(st_obj)

        return st_uuid

    def create_service_instance(self, name=None):
        if name:
            self._si_name = name
        st_fq_name = [self._default_domain, self._st_name]
        # get service template
        try:
            st_obj = self._client.service_template_read(fq_name=st_fq_name)
            st_prop = st_obj.get_service_template_properties()
            if st_prop is None:
                print "Error: Service template %s properties not found"\
                    % (self._st_name)
                return
        except NoIdError:
            print "Error: Service template %s not found"\
                % (self._st_name)
            return

        # create si
        print "Creating service instance %s" % (self._si_name)
        si_fq_name = [self._default_domain, self._project, self._si_name]
        left_fq_name = [self._default_domain, self._project, self._left]
        right_fq_name = [self._default_domain, self._project, self._right]
        project = self._client.project_read(fq_name=[self._default_domain, self._project])
        try:
            si_obj = self._client.service_instance_read(fq_name=si_fq_name)
            si_uuid = si_obj.uuid
        except NoIdError:
            si_obj = ServiceInstance(self._si_name, parent_obj=project)
            si_uuid = self._client.service_instance_create(si_obj)

        si_prop = ServiceInstanceType(
            management_virtual_network=None,
            left_virtual_network=left_fq_name,
            right_virtual_network=right_fq_name)

        # set scale out
        scale_out = ServiceScaleOutType(max_instances=1, auto_scale=False)
        si_prop.set_scale_out(scale_out)

        si_obj.set_service_instance_properties(si_prop)
        st_obj = self._client.service_template_read(id=st_obj.uuid)
        si_obj.set_service_template(st_obj)
        self._client.service_instance_update(si_obj)

        return si_uuid

    def create_policy_service_chain(self, name=None):
        if name:
            self._np_name = name

        si_fq_name = [self._default_domain, self._project, self._si_name]
        vn_fq_list = [[self._default_domain, self._project, self._left],
                      [self._default_domain, self._project, self._right]]

        print "Create and attach policy %s" % (self._np_name)
        project = self._client.project_read(fq_name=[self._default_domain, self._project])
        try:
            vn_obj_list = [self._client.virtual_network_read(vn)
                           for vn in vn_fq_list]
        except NoIdError:
            print "Error: VN(s) %s not found" % (self.vn_fq_list)
            return

        addr_list = [AddressType(virtual_network=vn.get_fq_name_str())
                     for vn in vn_obj_list]

        port = PortType(0, -1)
        action = "pass"
        action_list = ActionListType(apply_service=[':'.join(si_fq_name)],
                                     service_chain_type='in-network-nat')
        action = None
        timer = None

        prule = PolicyRuleType(direction="<>", simple_action="pass",
                               protocol="any", src_addresses=[addr_list[0]],
                               dst_addresses=[addr_list[1]], src_ports=[port],
                               dst_ports=[port], action_list=action_list)
        pentry = PolicyEntriesType([prule])
        np_obj = NetworkPolicy(name=self._np_name,
                               network_policy_entries=pentry,
                               parent_obj=project)
        np_uuid = self._client.network_policy_create(np_obj)

        seq = SequenceType(1, 1)
        vn_policy = VirtualNetworkPolicyType(seq, timer)
        for vn in vn_obj_list:
            vn.set_network_policy(np_obj, vn_policy)
            self._client.virtual_network_update(vn)

        return np_uuid
