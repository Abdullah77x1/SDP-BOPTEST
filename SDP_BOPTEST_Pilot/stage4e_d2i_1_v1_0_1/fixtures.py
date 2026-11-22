"""Fabricated test fixtures. Mirror discovery's real file-write side effect."""
import json
from pathlib import Path
from urllib.parse import urlparse
from stage4e_d2i_1.fixtures import FakeTransport as OriginalFakeTransport
from stage4e_d0.runner import OrderedClient

class FakeTransport(OriginalFakeTransport):
    def __init__(self,base,directory,journal,run,manifest):
        super().__init__(base,directory,journal,run,manifest)
        self.directory=Path(directory);self.base=base
    def discover(self):
        metadata=super().discover()
        # Exactly the side effect of the preserved real client's discovery.
        (self.directory/'runtime_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        return metadata

def faulty(name):return type('Fabricated_'+name,(FakeTransport,),{'fault':name})

class FabricatedResponse:
    status=200
    def __init__(self,value):self.value=value
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self):return json.dumps({'status':200,'message':'FABRICATED SOFTWARE TEST ONLY','payload':self.value}).encode()

class ActualDiscoveryFixture(FakeTransport):
    """Actual OrderedClient.discover()/HTTP parsing, fabricated HTTP responses.

    Other model operations remain inherited constant/schedule fixtures, not a
    physical simulator. Nothing here connects to a socket or dispatches a process.
    """
    def discover(self):
        client=OrderedClient(self.base,self.directory,self.journal)
        client.testid='FABRICATED_NOT_A_REAL_BOPTEST_INSTANCE'
        values={**self.meta,'step':300,'scenario':{
            'time_period':self.run['initialization']['scenario_key'],'electricity_price':'constant',
            'temperature_uncertainty':None,'solar_uncertainty':None,'seed':None}}
        def opener(request,timeout):
            key=urlparse(request.full_url).path.strip('/').split('/')[0]
            return FabricatedResponse(values[key])
        client.opener=opener
        metadata=client.discover()
        self.last_receipt_order=client.last_receipt_order
        return metadata
