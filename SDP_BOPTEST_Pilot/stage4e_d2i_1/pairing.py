"""Matched public raw-evidence audit; no dataset/feature construction."""
from .common import read,require,finite
from stage4e_d0.runner import pair_gate

def forecast_pair_gate(a,b,maximum_advances):
    for i in range(maximum_advances):
        left=read(a/f'forecast_{i:04d}.json');right=read(b/f'forecast_{i:04d}.json')
        require(left['issued_at_sim']==right['issued_at_sim'],'Paired forecast origins differ')
        x,y=left['data'],right['data'];require(x.keys()==y.keys(),'Paired forecast catalogs differ')
        for name in x:
            require(len(x[name])==len(y[name]),'Paired forecast lengths differ')
            require(all(abs(finite(v)-finite(w))<=1e-7 for v,w in zip(x[name],y[name])),
                'Paired issued boundary values differ: '+name)
    return {'paired_issued_forecasts_verified':True,'origins_checked':maximum_advances,'tolerance':1e-7}

def public_pair_gate(a,b,run):
    require(run['partition']!='protected_final_test','Protected pair comparison requires private custody')
    pair_gate(a,b,run)
    result=forecast_pair_gate(a,b,run['maximum_advances'])
    result['pretreatment_endpoint_vectors_verified']=True
    return result
