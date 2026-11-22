"""Budget and pinned-API mutation boundary; no default client constructor."""
from .common import require,ContractError
from stage4e_d0.plan import FLAGS
from stage4e_d1r.proposed_validation import command_schema

class BudgetedTransport:
    def __init__(self,inner,run):
        self.inner=inner;self.run=run;self.deploy_attempts=0;self.initialization_attempts=0
        self.advance_attempts=0;self.stop_attempts=0;self.initialized=False;self.step_confirmed=False
    @property
    def last_receipt_order(self):return self.inner.last_receipt_order
    def deploy(self):
        require(self.deploy_attempts==0,'Deployment retry prohibited')
        self.deploy_attempts+=1;return self.inner.deploy()
    def discover(self):return self.inner.discover()
    def fmu_identity(self):return self.inner.fmu_identity()
    def request(self,method,key,data=None):
        if key in ('initialize','scenario') and method=='PUT':
            require(self.initialization_attempts==0,'Initialization/scenario retry or substitution prohibited')
            init=self.run['initialization']
            expected_key='initialize' if init['method']=='custom' else 'scenario'
            expected={'start_time':init['start_time'],'warmup_period':604800} if expected_key=='initialize' else {'time_period':init['scenario_key'],'electricity_price':'constant'}
            require(key==expected_key and data==expected,'Initialization differs from manifest')
            self.initialization_attempts+=1
            result=self.inner.request(method,key,data);self.initialized=True;return result
        if key=='step' and method=='PUT':require(data=={'step':300},'Wrong step or unapproved change')
        if key=='advance':
            require(method=='POST' and self.initialized and self.step_confirmed,'Advance before qualified initialization/step')
            require(self.advance_attempts<self.run['maximum_advances'],'Advance budget exhausted; no extra followup')
            command_schema(data)
            require(data[FLAGS[0]] or data==dict.fromkeys(FLAGS,0),'Inactive command must be canonical native body')
            if self.run['mode']=='native':require(data==dict.fromkeys(FLAGS,0),'Native policy intervention prohibited')
            self.advance_attempts+=1
        allowed={('GET','scenario'),('PUT','step'),('GET','step'),('PUT','results'),('PUT','forecast'),('GET','kpi'),('POST','advance')}
        require((method,key) in allowed,'Unapproved transport operation')
        result=self.inner.request(method,key,data)
        if (method,key)==('GET','step'):
            require(float(result)==300,'Step readback rejected');self.step_confirmed=True
        return result
    def stop(self):
        require(self.stop_attempts==0,'Stop retry prohibited')
        self.stop_attempts+=1;return self.inner.stop()

def initialize_run(client,run):
    init=run['initialization']
    if init['method']=='custom':return client.request('PUT','initialize',{'start_time':init['start_time'],'warmup_period':604800})
    return client.request('PUT','scenario',{'time_period':init['scenario_key'],'electricity_price':'constant'})['time_period']
