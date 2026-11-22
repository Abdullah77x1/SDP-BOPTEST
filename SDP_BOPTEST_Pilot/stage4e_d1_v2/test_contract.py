"""Offline fabricated and preserved-development evidence tests; no simulator."""
import base64,copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import asdict
from . import validation as v
from .runner import *

REF=read(ROOT/'evidence/local_matched_AB/A/runtime_metadata.json')
FMU=read(ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json')['building_fmu_sha256']

def obs(t,old_event=True,command=None):
    pair=v.REFERENCE.pair(t)
    if old_event and v.REFERENCE.event_pairs(t):pair=v.REFERENCE.event_pairs(t)[0]
    x=dict.fromkeys([*REF['measurements'],*REF['inputs']],0.)
    x.update(time=t,**{v.HEAT:pair[0],v.COOL:pair[1],TEMP:296.15,HEAT:100.,**v.NATIVE})
    if command:
        x.update(command)
        x[COOL]=1000. if command[FLAGS[0]] else 0.
        x[FAN]=200. if command[FLAGS[0]] else 0.
    return x

def comfort(t):
    occupied=28800<=t%86400<65400
    return {'time':t,'LowerSetp[1]':294.15 if occupied else 288.15,
        'UpperSetp[1]':297.15 if occupied else 303.15,'Occupancy[1]':2 if occupied else 0}

def fc(t,origin=None):
    c=comfort(t)
    return {'time':t,'issued_at':t-300 if origin is None else origin,
        'lower_k':c[LOW],'upper_k':c[UP],'occupancy':c[OCC]}

def check(x,command=None,orders=None):
    return v.endpoint(x['time']-300,command or v.NATIVE,x,fc(x['time']),
        orders or {'observation':1,'forecast':2,'cutoff':3,'response':4},.1)

def native_window(event,duplicate=False):
    ts=list(range(event-300,event+301,30));data={'time':ts}
    for key in v.HISTORY_POINTS:data[key]=[obs(t,old_event=True)[key] for t in ts]
    if duplicate:
        i=data['time'].index(event)+1
        for k in data:data[k].insert(i,event if k=='time' else obs(event,False)[k])
    return data

class ContractTests(unittest.TestCase):
    def test_normal_native_and_evening_comfort_separation(self):
        for t in (28500,29100,64500,65100,65400):
            with self.subTest(t=t):self.assertEqual(check(obs(t)).status,'VERIFIED_REFERENCE')
        self.assertNotEqual(check(obs(65100)).observed_pair,check(obs(65100)).comfort_pair)
    def test_both_events_old_pending_new_accepted(self):
        for t in (28800,64800):
            with self.subTest(t=t):
                self.assertEqual(check(obs(t)).status,'PENDING_EVENT_VERIFICATION')
                self.assertEqual(check(obs(t,False)).status,'VERIFIED_EVENT_NEW_REFERENCE')
    def test_mixed_unknown_persistent_fail(self):
        for t,heat,cool in ((28800,288.15,297.15),(64800,290.,300.),(29100,288.15,303.15),(65100,294.15,297.15)):
            x=obs(t);x.update({v.HEAT:heat,v.COOL:cool})
            with self.subTest(t=t),self.assertRaises(v.Violation):check(x)
    def test_strict_active_command(self):
        command=dict(v.NATIVE,con_oveTSetCoo_activate=1,con_oveTSetCoo_u=296.90)
        x=obs(33000,command=command)
        self.assertTrue(check(x,command).external_control_verified)
        for key,value in ((v.COOL,297.15),(FLAGS[0],0),(FLAGS[1],1),(v.HEAT,296.8)):
            bad=dict(x,**{key:value})
            with self.subTest(key=key),self.assertRaises(v.Violation):check(bad,command)
    def test_event_never_excuses_bad_active_readback(self):
        command=dict(v.NATIVE,con_oveTSetCoo_activate=1,con_oveTSetCoo_u=296.90)
        for t in (28800,64800):
            with self.subTest(t=t),self.assertRaises(v.Violation):check(obs(t,command={**command,v.COOL:297.15}),command)
    def test_active_old_heating_cannot_become_pending(self):
        command=dict(v.NATIVE,con_oveTSetCoo_activate=1,con_oveTSetCoo_u=296.90)
        with self.assertRaises(v.Violation):check(obs(28800,command=command),command)
    def test_missing_nonfinite_signals(self):
        for name in (v.HEAT,v.COOL,TEMP,*FLAGS):
            for value in (None,float('nan'),True):
                x=obs(29100);x[name]=value
                with self.subTest(name=name,value=value),self.assertRaises(v.Violation):check(x)
    def test_causal_receipts_and_clock(self):
        for orders in ({'observation':5,'forecast':2,'cutoff':3,'response':4},
                       {'observation':1,'forecast':4,'cutoff':3,'response':5},
                       {'observation':1,'forecast':2,'cutoff':3,'response':3}):
            with self.subTest(orders=orders),self.assertRaises(v.Violation):check(obs(29100),orders=orders)
        x=obs(29100)
        for age in (-1,30.01):
            with self.assertRaises(v.Violation):v.endpoint(28800,v.NATIVE,x,fc(29100),{'observation':1,'forecast':2,'cutoff':3,'response':4},age)
        for badfc in (dict(fc(29100),issued_at=29100),dict(fc(29100),time=29400),dict(fc(29100),occupancy=None)):
            with self.assertRaises(v.Violation):v.endpoint(28800,v.NATIVE,x,badfc,{'observation':1,'forecast':2,'cutoff':3,'response':4},.1)
    def test_command_safety_and_age(self):
        t=32700;current=obs(t);boundary=comfort(t)
        for target in (270.,309.,294.3,297.2):
            command=dict(v.NATIVE,con_oveTSetCoo_activate=1,con_oveTSetCoo_u=target)
            with self.subTest(target=target),self.assertRaises(v.Violation):v.command_guard(command,current,boundary,t,.1)
        command=dict(v.NATIVE,con_oveTSetCoo_activate=1,con_oveTSetCoo_u=296.9)
        with self.assertRaises(v.Violation):v.command_guard(command,current,dict(boundary,**{OCC:0}),t,.1)
        with self.assertRaises(v.Violation):v.command_guard(v.NATIVE,current,boundary,t,31)
    def test_original_safety_thresholds_and_latched_veto_unchanged(self):
        c=read(HERE/'campaign.json');r=c['runs'][1];t=r['start']+32400
        safety=Safety(c);proposal=nominal(r,t,c);x=obs(t);x[TEMP]=294.6
        command,reason=safety.decide(proposal,x,comfort(t),.1)
        self.assertEqual(command,v.NATIVE);self.assertIn('cold',reason)
        proposal=nominal(r,t+300,c);x=obs(t+300);x[TEMP]=296.15
        self.assertIn('latched',safety.decide(proposal,x,comfort(t+300),.1)[1])

class DeferredTests(unittest.TestCase):
    def tracker(self,event=28800):
        tracker=v.EventTracker();x=obs(event);tracker.register(x,check(x),4);return tracker,x
    def test_pending_success_both_events_preserves_original(self):
        for event in (28800,64800):
            for duplicate in (False,True):
                tracker,x=self.tracker(event);saved=copy.deepcopy(x)
                tracker.guard(event,v.NATIVE,x,.1,1)
                result=tracker.resolve(native_window(event,duplicate),obs(event+300),check(obs(event+300)),7,9)
                self.assertIsNone(tracker.pending);self.assertEqual(x,saved)
                self.assertEqual(result['endpoint_at_event'],saved)
                self.assertFalse(result['extra_advance_inserted'])
    def test_pending_no_extra_wrong_origin_stale_or_external(self):
        tracker,x=self.tracker()
        for t,cmd,age,left in ((28800,v.NATIVE,.1,0),(29100,v.NATIVE,.1,1),(28800,v.NATIVE,31,1),
            (28800,dict(v.NATIVE,con_oveTSetCoo_activate=1,con_oveTSetCoo_u=296.9),.1,1)):
            with self.subTest(t=t,cmd=cmd,age=age,left=left),self.assertRaises(v.Violation):tracker.guard(t,cmd,x,age,left)
    def test_every_native_power_channel_required(self):
        for key in (COOL,FAN,HEAT):
            data=native_window(28800);del data[key]
            with self.subTest(key=key),self.assertRaises(v.Violation):v.history(data,28500,29100)
    def test_missing_and_bad_duplicate_samples_fail(self):
        data=native_window(28800)
        i=data['time'].index(28830)
        for k in data:data[k].pop(i)
        with self.assertRaises(v.Violation):v.history(data,28500,29100)
        data=native_window(28800,True);i=data['time'].index(28800)
        for k in data:data[k][i],data[k][i+1]=data[k][i+1],data[k][i]
        tracker,x=self.tracker()
        with self.assertRaises(v.Violation):tracker.resolve(data,obs(29100),check(obs(29100)),7,9)
    def test_persistent_flags_or_wrong_endpoint_fail(self):
        for fault in ('persistent','mixed','activation','wrong_endpoint','receipt'):
            tracker,x=self.tracker();data=native_window(28800);end=obs(29100);i=data['time'].index(28830)
            if fault=='persistent':data[v.HEAT][i]=288.15;data[v.COOL][i]=303.15
            if fault=='mixed':data[v.HEAT][i]=288.15
            if fault=='activation':data[FLAGS[0]][i]=1
            if fault=='wrong_endpoint':end['time']+=300
            with self.subTest(fault=fault),self.assertRaises(v.Violation):tracker.resolve(data,end,check(obs(29100)),7,6 if fault=='receipt' else 9)
            self.assertIsNotNone(tracker.pending)

class PreservedEvidenceTests(unittest.TestCase):
    def test_actual_failed_D1_96_responses(self):
        d=ROOT/'stage4e_d0/campaign_evidence/Q01_N'
        raw=[json.loads(x) for x in (d/'raw_api.jsonl').read_text().splitlines()]
        forecasts={};advances=[]
        for r in raw:
            if '/forecast/' in r['url']:
                f=json.loads(base64.b64decode(r['raw_body_base64']))['payload'];forecasts[f['time'][0]]=f
            if r['method']=='POST' and '/advance/' in r['url']:advances.append(r)
        journal=[json.loads(x) for x in (d/'receipt_order.jsonl').read_text().splitlines()]
        for i,r in enumerate(advances):
            x=json.loads(base64.b64decode(r['raw_body_base64']))['payload'];origin=x['time']-300;f=forecasts[origin]
            cutoff=next(e for e in journal if e['kind']=='origin_cutoff' and e['sim_time']==origin)
            response=next(e for e in journal if e['kind']=='api_received' and e['raw_sequence']==r['sequence'])
            result=v.endpoint(origin,r['request'],x,{'time':x['time'],'issued_at':origin,'lower_k':f[LOW][1],'upper_k':f[UP][1],'occupancy':f[OCC][1]},
                {'observation':cutoff['observation_received_order'],'forecast':cutoff['forecast_received_order'],'cutoff':cutoff['order'],'response':response['order']},.1)
            self.assertEqual(result.status,'PENDING_EVENT_VERIFICATION' if i==95 else 'VERIFIED_REFERENCE')
        self.assertEqual(len(advances),96)
        self.assertEqual(read(ROOT/'stage4e_d0/campaign_evidence/CAMPAIGN_COMPLETED.json')['classification'],'FAILED')
    def test_actual_BM01_morning_raw_and_history(self):
        d=ROOT/'stage4e_d1r_bm01/evidence/D1R_BM01'
        first=read(d/'ADVANCE_ENDPOINT_1.json');last=read(d/'ADVANCE_ENDPOINT_2.json')
        journal=[json.loads(line) for line in (d/'receipt_order.jsonl').read_text().splitlines()]
        cutoffs=[r for r in journal if r['kind']=='diagnostic_origin_cutoff']
        for i,(x,cutoff) in enumerate(zip((first,last),cutoffs),1):
            forecast=read(d/f'FORECAST_AT_ORIGIN_{i}.json')['data']
            receipt=next(r for r in journal if r['kind']=='api_received' and r['endpoint']=='advance' and r['order']>cutoff['order'])
            result=v.endpoint(x['time']-300,v.NATIVE,x,{'time':x['time'],'issued_at':x['time']-300,
                'lower_k':forecast[LOW][1],'upper_k':forecast[UP][1],'occupancy':forecast[OCC][1]},
                {'observation':cutoff['observation_receipt_order'],'forecast':cutoff['forecast_receipt_order'],
                 'cutoff':cutoff['order'],'response':receipt['order']},cutoff['observation_age_s'])
            self.assertEqual(result.status,'PENDING_EVENT_VERIFICATION' if i==1 else 'VERIFIED_REFERENCE')
        data=read(d/'ORDERED_NATIVE_TRANSITION_HISTORY.json')
        ids=[i for i,t in enumerate(data['time']) if t>=first['time']]
        post={k:[values[i] for i in ids] for k,values in data.items()}
        self.assertEqual(v.validate_boundary_followup_history(first['time'],post)['status'],'FOLLOWUP_REFERENCE_VERIFIED_IN_DIAGNOSTIC')
        # BM01 did not request scored gas power. Never invent it to pass v2 history.
        with self.assertRaises(v.Violation):v.history(data,first['time']-300,last['time'])
    def test_actual_Stage4C_morning_evening_and_1805(self):
        d=ROOT/'evidence/local_matched_AB/A';data=read(d/'native_results.json');base=data['time'][0]
        published=read(d/'boundary_forecast_NOT_ML.json')
        raw=[json.loads(x) for x in (d/'raw_api.jsonl').read_text().splitlines()]
        endpoints={}
        for r in raw:
            if r['method']=='POST' and '/advance/' in r['url']:
                body=json.loads(base64.b64decode(r['raw_body_base64']));x=body.get('payload',body);endpoints[x['time']]=x
        for offset in (28800,64800):
            e=base+offset;first=endpoints[e];last=endpoints[e+300]
            self.assertEqual(check(first).status,'PENDING_EVENT_VERIFICATION')
            tracker=v.EventTracker();tracker.register(first,check(first),4)
            ids=[i for i,t in enumerate(data['time']) if e-300<=t<=e+300]
            window={k:[data[k][i] for i in ids] for k in ('time',*v.HISTORY_POINTS)}
            tracker.resolve(window,last,check(last),7,9)
        t=base+65100;j=published['time'].index(t)
        last=v.endpoint(t-300,v.NATIVE,endpoints[t],{'time':t,'issued_at':t-300,
            'lower_k':published[LOW][j],'upper_k':published[UP][j],'occupancy':published[OCC][j]},
            {'observation':1,'forecast':2,'cutoff':3,'response':4},.1)
        self.assertEqual(last.status,'VERIFIED_REFERENCE')
        self.assertNotEqual(last.observed_pair,last.comfort_pair)

class FakeClient:
    """Fabricated scheduling/plumbing fixtures only, no thermal simulation."""
    fault=None;instances=[]
    def __init__(self,base,directory,journal):
        self.journal=journal;self.last_receipt_order=0;self.calls=[];self.testid='FABRICATED';self.data=None
        type(self).instances.append(self)
    def deploy(self):self.journal.emit('fabricated_deployment');return self.testid
    def discover(self):return REF
    def request(self,method,key,data=None,instance=True):
        self.calls.append((method,key,copy.deepcopy(data)))
        self.journal.emit('fabricated_request',method=method,endpoint=key)
        if key=='scenario' and method=='PUT':
            self.scenario=data['time_period'];self.t=(146 if self.scenario=='typical_cool_day' else 44)*86400
            self.start=self.t;x=obs(self.t);self.data={'time':[self.t],**{k:[x[k]] for k in v.HISTORY_POINTS}}
            out={'time_period':x}
        elif key=='scenario':out={'time_period':self.scenario,'electricity_price':'constant'}
        elif key=='step':out=300
        elif key=='forecast':
            ts=list(range(self.t,self.t+1801,300));out={'time':ts}
            for name in POINTS:out[name]=[comfort(t).get(name,290. if name=='TDryBul' else 0.) for t in ts]
        elif key=='advance':
            if self.fault=='lost':raise RuntimeError('FABRICATED transport loss; attempt consumed')
            if self.fault in ('duplicate','reverting_duplicate') and v.REFERENCE.event_pairs(self.t):
                x=obs(self.t,False)
                for k in self.data:self.data[k].append(self.t if k=='time' else x[k])
                if self.fault=='reverting_duplicate':
                    x=obs(self.t)
                    for k in self.data:self.data[k].append(self.t if k=='time' else x[k])
            for t in range(self.t+30,self.t+301,30):
                x=obs(t,command=data)
                if self.fault=='persistent' and t%86400==28830:x.update({v.HEAT:288.15,v.COOL:303.15})
                for k in self.data:self.data[k].append(t if k=='time' else x[k])
            self.t+=300;out=obs(self.t,command=data)
            if self.fault=='wrong_command' and data[FLAGS[0]]:out[v.COOL]+=.1
        elif key=='results':
            start,end=data['start_time'],data['final_time']
            if start<self.start:
                ts=list(range(start,end+1,30));out={'time':ts,**{k:[0.]*len(ts) for k in data['point_names']}}
            else:
                begin=self.data['time'].index(start);finish=self.data['time'].index(end)+1
                out={'time':self.data['time'][begin:finish],**{k:self.data[k][begin:finish] for k in data['point_names']}}
                if self.fault=='missing_power':out.pop(FAN)
                if self.fault=='missing_sample' and end%86400==29100:
                    target=end-270;i=out['time'].index(target)
                    for k in out:out[k].pop(i)
        elif key=='kpi':
            from core import integrate
            total=sum(integrate(self.data['time'],self.data[k],self.start,self.t) for k in (COOL,FAN,HEAT))
            out={'ener_tot':total*2.77778e-7/48.}
        else:raise AssertionError(key)
        self.last_receipt_order=self.journal.emit('fabricated_received',endpoint=key);return out
    def stop(self):self.journal.emit('fabricated_stop_ACK')

class CollectorTests(unittest.TestCase):
    def collect(self,fault=None,mode='scheduled_variation'):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);directory=Path(tmp.name)/'run'
        class Fixture(FakeClient):pass
        Fixture.fault=fault;Fixture.instances=[]
        c=read(HERE/'campaign.json');r=c['runs'][1 if mode=='scheduled_variation' else 0]
        status=collect_one(r,c,directory,REF,{'proposal_sha256':'FABRICATED'},Fixture,
            lambda _: {'sha256':FMU},lambda _: [{'instance_directory_exists':False}])
        return status,directory,Fixture.instances[0]
    def test_full_72h_pending_success_no_added_step_and_causal_records(self):
        status,d,c=self.collect()
        self.assertEqual(status['classification'],'PASS_VALID_RAW',status)
        self.assertEqual(status['advance_requests_attempted'],864);self.assertEqual(status['endpoints'],865)
        self.assertEqual(status['pending_events_resolved'],6)
        records=[json.loads(x) for x in (d/'steps.jsonl').read_text().splitlines()]
        event=records[95];next_step=records[96]
        self.assertEqual(event['setpoint_validation_at_receipt']['status'],'PENDING_EVENT_VERIFICATION')
        self.assertFalse(event['readback_verified'])
        self.assertEqual(next_step['validation_state_at_origin'],'PENDING_EVENT_VERIFICATION')
        self.assertEqual(next_step['current_observation'][v.COOL],303.15)
        self.assertEqual(next_step['applied_command'],v.NATIVE)
        self.assertNotIn('event_resolutions',next_step)
        self.assertEqual(read(d/'endpoint_0096.json')[v.COOL],303.15)
        self.assertEqual(len([x for x in c.calls if x[1]=='advance']),864)
        self.assertEqual(status['coverage']['verified_full_pulses'],9)
        with self.assertRaises(FileExistsError):collect_one({}, {},d,REF,{},FakeClient)
    def test_full_native_72h(self):
        status,_,c=self.collect(mode='native');self.assertEqual(status['classification'],'PASS_VALID_RAW',status)
        self.assertTrue(all(body==v.NATIVE for method,key,body in c.calls if key=='advance'))
    def test_duplicate_history_preserved(self):
        status,d,_=self.collect('duplicate');self.assertEqual(status['classification'],'PASS_VALID_RAW',status)
        hist=read(d/'whole_native_results.json');self.assertGreater(len(hist['time']),len(set(hist['time'])))
    def test_pending_failures_stop_and_quarantine(self):
        for fault in ('persistent','missing_sample','reverting_duplicate'):
            with self.subTest(fault=fault):
                status,d,c=self.collect(fault)
                self.assertEqual(status['classification'],'FAILED',status)
                self.assertEqual(status['advance_requests_attempted'],97)
                self.assertTrue((d/'QUARANTINE.json').exists());self.assertFalse(status['training_release'])
                self.assertEqual(len([x for x in c.calls if x[1]=='advance']),97)
    def test_missing_power_transport_loss_and_wrong_actuation(self):
        for fault,count in (('missing_power',1),('lost',1),('wrong_command',109)):
            with self.subTest(fault=fault):
                status,d,_=self.collect(fault)
                self.assertEqual(status['classification'],'FAILED',status)
                self.assertEqual(status['advance_requests_attempted'],count)
                self.assertTrue((d/'QUARANTINE.json').exists())
    def test_original_physics_schedule_and_thresholds_identical(self):
        old=read(ROOT/'stage4e_d0/campaign.json');new=read(HERE/'campaign.json')
        for key in old:
            if key not in ('runs','protocol'):self.assertEqual(new[key],old[key],key)
        for a,b in zip(old['runs'],new['runs']):
            for key in a:
                if key not in ('attempt_id','evidence_directory'):self.assertEqual(a[key],b[key],key)
        self.assertFalse((HERE/'campaign_evidence').exists())
    def test_authorization_cannot_reuse_original_or_template(self):
        with self.assertRaises(ContractError):authorize(HERE/'execution_authorization.template.json','unused',read(HERE/'campaign.json'))
        self.assertFalse((HERE/'campaign_evidence').exists())
    def test_client_no_retry_extra_step_or_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=BoundedClient('http://unused',Path(tmp),Journal(Path(tmp)/'journal'))
            with self.assertRaises(ContractError):c.request('PUT','initialize',{})
            with patch.object(OrderedClient,'request',return_value={}):
                c.advance_attempts=863;c.request('POST','advance',v.NATIVE)
                with self.assertRaises(ContractError):c.request('POST','advance',v.NATIVE)
            with patch.object(OrderedClient,'deploy',side_effect=RuntimeError('fixture')):
                with self.assertRaises(RuntimeError):c.deploy()
                with self.assertRaises(ContractError):c.deploy()
    def test_default_cli_never_constructs_client(self):
        import contextlib,io
        from . import runner
        with patch('sys.argv',['offline']),patch.object(runner,'verify_frozen',return_value='FABRICATED'),patch.object(runner,'execute') as execute,contextlib.redirect_stdout(io.StringIO()):
            runner.main();execute.assert_not_called()
    def test_manifest_bound_new_ids_only(self):
        config=read(HERE/'campaign.json')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'approval'
            a={'status':'EXPLICITLY_AUTHORIZED','campaign_id':CAMPAIGN_ID,'proposal_sha256':'FABRICATED',
                'maximum_advances':3456,'attempt_ids':[r['attempt_id'] for r in config['runs']],
                'user_authorization_text':'FABRICATED TEST ONLY','authorized_utc':'FABRICATED'}
            save_new(p,a);self.assertEqual(authorize(p,'FABRICATED',config)['proposal_sha256'],'FABRICATED')
            for key,value in (('proposal_sha256','OLD'),('campaign_id','OLD'),('attempt_ids',['Q01_N','Q02_X','Q03_N','Q04_X']),('maximum_advances',3457)):
                bad=Path(tmp)/key;save_new(bad,dict(a,**{key:value}))
                with self.subTest(key=key),self.assertRaises(ContractError):authorize(bad,'FABRICATED',config)
    def test_orchestrator_one_failure_consumes_one_new_slot_no_retry(self):
        from . import runner,runtime
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);save_new(root/'campaign.json',read(HERE/'campaign.json'))
            def fail(run,config,d,ref,binding):
                d.mkdir();save_new(d/'ATTEMPT_STARTED.json',{'run':run})
                return {'attempt_id':run['attempt_id'],'classification':'FAILED'}
            with patch.object(runner,'HERE',root),patch.object(runner,'verify_frozen',return_value='FABRICATED'),patch.object(runner,'authorize',return_value={'proposal_sha256':'FABRICATED'}),patch.object(runtime,'verify_runtime',return_value={'classification':'PASS','fabricated':True}),patch.object(runner,'collect_one',side_effect=fail) as collect:
                result=runner.execute('unused')
                self.assertEqual(collect.call_count,1);self.assertEqual(len(result['unused_attempt_ids']),3)
                self.assertEqual(result['classification'],'FAILED')
                with self.assertRaises(FileExistsError):runner.execute('unused')
    def test_quarantined_or_unresolved_evidence_not_handed_off(self):
        from . import handoff
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);r=read(HERE/'campaign.json')['runs'][0]
            save_new(p/'CAMPAIGN_COMPLETED.json',{'campaign_id':CAMPAIGN_ID,'classification':'FAILED','binding':{'proposal_sha256':'FABRICATED'}})
            save_new(p/'ARTIFACT_MANIFEST.json',{'files':files_manifest(p)})
            with patch.object(handoff,'verify_frozen',return_value='FABRICATED'),self.assertRaises(ContractError):handoff.read_qualified_run(p,r)

if __name__=='__main__':unittest.main(verbosity=2)
