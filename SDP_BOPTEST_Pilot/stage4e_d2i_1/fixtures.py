"""FABRICATED SOFTWARE FIXTURES ONLY. Constants/schedules, no building solver.

These values are deliberately artificial; they are not experimental evidence.
"""
from copy import deepcopy
from .common import read,ROOT,FMU_SHA
from .schema import META_PATH
from stage4e_d0.plan import FLAGS,LOW,UP,OCC,TEMP,COOL,FAN,HEAT,SET
from stage4e_d1_v2.validation import REFERENCE,HISTORY_POINTS
from stage4e_d1r.proposed_validation import HEAT as HSET,COOL as CSET

class FakeTransport:
    fault=None
    def __init__(self,base,directory,journal,run,manifest):
        self.run=run;self.manifest=manifest;self.journal=journal
        self.last_receipt_order=None;self.current=run['start'];self.advances=0
        self.command=dict.fromkeys(FLAGS,0);self.samples={};self.stopped=False
        self.meta=read(ROOT/META_PATH)
        if self.fault=='wrong_unit':self.meta['measurements'][TEMP]['Unit']='degC'
        if self.fault=='optional_absent':
            for p in list(self.meta['forecast_points']):
                if p not in (LOW,UP,OCC,'TDryBul','HGloHor'):del self.meta['forecast_points'][p]
    def receipt(self,kind,**fields):
        self.last_receipt_order=self.journal.emit('FABRICATED_'+kind,**fields)
    def deploy(self):self.receipt('deploy');return 'FABRICATED_INSTANCE_NOT_A_SIMULATOR'
    def discover(self):self.receipt('catalog');return deepcopy(self.meta)
    def fmu_identity(self):return {'sha256':FMU_SHA,'evidence':'FABRICATED_EXPECTED_HASH_NOT_RUNTIME_ATTESTATION'}
    def observation(self,t,command=None):
        command=command or dict.fromkeys(FLAGS,0)
        obs={k:0. for kind in ('measurements','inputs') for k in self.meta[kind]}
        pair=REFERENCE.pair(t)
        if REFERENCE.event_pairs(t):pair=REFERENCE.pair(t-1)
        if self.fault=='persistent_native' and t%86400==8*3600+30:pair=REFERENCE.pair(t-300)
        obs.update(time=t,**{HSET:pair[0],CSET:pair[1],TEMP:296.15,COOL:400.,FAN:100.,HEAT:100.,
            'zon_weaSta_reaWeaTDryBul_y':289.15,'zon_weaSta_reaWeaRelHum_y':.45,
            'fcu_oveTSup_u':294.15,'fcu_oveFan_u':.3})
        obs.update(dict.fromkeys(FLAGS,0))
        if command[FLAGS[0]]:
            obs[CSET]=command[SET]+(.1 if self.fault=='wrong_active' else 0)
            obs[FLAGS[0]]=1
        if self.fault=='wrong_time' and self.advances:obs['time']+=1
        return obs
    def forecast(self,body):
        ts=list(range(self.current,self.current+body['horizon']+1,body['interval']))
        out={'time':ts}
        for p in body['point_names']:
            if self.fault=='optional_values_absent' and p not in (LOW,UP,OCC,'TDryBul','HGloHor'):continue
            out[p]=[]
            for t in ts:
                occupied=8*3600<=t%86400<18*3600
                val={LOW:294.15 if occupied else 288.15,UP:297.15 if occupied else 303.15,
                    OCC:1. if occupied else 0.,'TDryBul':289.15,'HGloHor':100.,'relHum':.45,
                    'pAtm':101325.,'winSpe':2.,'winDir':180.}.get(p,50.)
                out[p].append(val)
        return out
    def results(self,body):
        start,end=body['start_time'],body['final_time'];ts=list(range(start,end+1,30))
        if self.fault=='warmup_offgrid' and start==self.run['warmup_start']:
            ts=sorted([t for t in ts if t!=start+30]+[start+15,start+45])
        out={'time':ts}
        for p in body['point_names']:
            if self.fault=='missing_gas' and p==HEAT:continue
            out[p]=[self.samples[t][p] if t in self.samples else self.observation(t)[p] for t in ts]
        return out
    def request(self,method,key,data=None):
        self.journal.emit('FABRICATED_request',method=method,endpoint=key,request=data)
        if (method,key) in (('PUT','initialize'),('PUT','scenario')):
            if self.fault=='initialize_error':raise RuntimeError('FABRICATED initialization API failure')
            obs=self.observation(self.current);self.samples[self.current]=obs
            result=obs if key=='initialize' else {'time_period':obs,'electricity_price':None}
        elif key=='scenario':
            result={'time_period':self.run['initialization']['scenario_key'],'electricity_price':'constant',
                'temperature_uncertainty':None,'solar_uncertainty':None,'seed':None}
        elif key=='step':result=300
        elif key=='forecast':result=self.forecast(data)
        elif key=='results':result=self.results(data)
        elif key=='advance':
            self.advances+=1
            if self.fault=='advance_error':raise RuntimeError('FABRICATED lost advance response; outcome unknown')
            if self.fault=='interrupt':raise KeyboardInterrupt('FABRICATED interruption')
            for t in range(self.current+30,self.current+301,30):self.samples[t]=self.observation(t,data)
            self.current+=300;self.command=deepcopy(data);result=deepcopy(self.samples[self.current])
        elif key=='kpi':
            seconds=self.current-self.run['start'];policy=self.manifest['policy']
            result={'ener_tot':600.*seconds*policy['official_kwh_per_j']/policy['area_m2']}
        else:raise ValueError('Unknown fabricated endpoint '+key)
        self.receipt('response',method=method,endpoint=key)
        return result
    def stop(self):
        if self.stopped:raise RuntimeError('Duplicate fixture cleanup')
        self.stopped=True
        if self.fault=='cleanup_error':raise RuntimeError('FABRICATED removal cannot be confirmed')
        if self.fault=='cleanup_bad_ack':return {'acknowledgement':'UNKNOWN','instance_removed':False}
        self.receipt('cleanup')
        return {'acknowledgement':'OK','instance_removed':True,'evidence':'FABRICATED_NOT_REAL_RUNTIME_CLEANUP'}

def faulty(name):
    return type('Fabricated_'+name,(FakeTransport,),{'fault':name})
