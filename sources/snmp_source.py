
import ipaddress
from pysnmp.hlapi import *
from pysnmp.smi import builder, view
from sources.base import DataSource
from utils.snmp_utils import load_mibs

class SNMPDataSource(DataSource):
    def __init__(self, config):
        super().__init__(config)
        self.mib_view = None

    def authenticate(self):
        # SNMP doesn't require separate authentication
        pass

    def fetch_data(self):
        self.mib_view = load_mibs(self.config['mibs'])

        community_string = self.config['auth_params']['community_string']
        oid_mapping = self.config['oid_mapping']
        results = []

        targets = self.config['auth_params'].get('targets', [])
        target_ranges = self.config['auth_params'].get('target_ranges', [])

        for target in targets:
            results.append(self.query_snmp_target(community_string, target, oid_mapping))

        for target_range in target_ranges:
            ip_network = ipaddress.ip_network(target_range)
            for host in ip_network.hosts():
                results.append(self.query_snmp_target(community_string, str(host), oid_mapping))

        return results

    def query_snmp_target(self, community_string, target, oid_mapping):
        snmp_engine = SnmpEngine()
        community_data = CommunityData(community_string)
        udp_transport_target = UdpTransportTarget((target, 161))

        target_results = {}
        for key, oid_name in oid_mapping.items():
            oid_obj = ObjectIdentity(oid_name).resolveWithMib(self.mib_view)
            iterator = nextCmd(snmp_engine, community_data, udp_transport_target, ContextData(),
                               ObjectType(oid_obj), lexicographicMode=False)
            for errorIndication, errorStatus, errorIndex, varBinds in iterator:
                if errorIndication or errorStatus:
                    continue
                else:
                    target_results[key] = varBinds[0][1].prettyPrint()

        return {target: target_results}
