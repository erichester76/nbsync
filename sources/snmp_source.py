from sources.base import DataSource
from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UsmUserData, UdpTransportTarget, ContextData, 
    ObjectType, ObjectIdentity, nextCmd, usmHMACMD5AuthProtocol, 
    usmDESPrivProtocol
)

class SNMPDataSource(DataSource):
    def __init__(self, config):
        super().__init__(config)
        self.snmp_engine = SnmpEngine()

    def authenticate(self):
        auth_params = self.config['auth_params']
        version = auth_params['version']

        if version == 'v2':
            # SNMPv2 uses community string for authentication
            self.auth_data = CommunityData(auth_params['community_string'])

        elif version == 'v3':
            # SNMPv3 uses user-based authentication
            self.auth_data = UsmUserData(
                userName=auth_params['username'],
                authKey=auth_params.get('auth_key'),
                privKey=auth_params.get('priv_key'),
                authProtocol=getattr(usmHMACMD5AuthProtocol, auth_params.get('auth_protocol', 'usmHMACMD5AuthProtocol')),
                privProtocol=getattr(usmDESPrivProtocol, auth_params.get('priv_protocol', 'usmDESPrivProtocol'))
            )

        else:
            raise ValueError(f"Unsupported SNMP version: {version}")

    def fetch_data(self):
        # Fetch data by performing SNMP walk or get based on OIDs in the config
        targets = self.config['auth_params']['targets']
        oids = self.config['oid_mapping']
        results = []

        for target in targets:
            transport_target = UdpTransportTarget((target, 161))
            for oid_name, oid_value in oids.items():
                oid_obj = ObjectIdentity(oid_value)
                iterator = nextCmd(
                    self.snmp_engine,
                    self.auth_data,
                    transport_target,
                    ContextData(),
                    ObjectType(oid_obj),
                    lexicographicMode=False
                )

                for errorIndication, errorStatus, errorIndex, varBinds in iterator:
                    if errorIndication or errorStatus:
                        continue
                    else:
                        results.append({oid_name: varBinds[0][1].prettyPrint()})

        return results
