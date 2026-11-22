"""Strict shared-channel reproducibility, as-issued forecasts and common prefixes."""
import json
from .campaign import first_divergence
from stage4e_d2i_1.common import require, read, finite

def compare_endpoints(left,right,through,common_only=False):
    a={r['time']:r for r in left}; b={r['time']:r for r in right}
    times=[t for t in a if t<=through]
    require(times and times==[t for t in b if t<=through], 'Endpoint comparison grid mismatch')
    count=0
    for t in times:
        if not common_only:require(a[t].keys()==b[t].keys(),'Endpoint catalog mismatch')
        keys=a[t].keys() & b[t].keys()
        require('zon_reaTRooAir_y' in keys, 'Mandatory temperature absent')
        for k in keys:
            require(abs(finite(a[t][k])-finite(b[t][k]))<=1e-7, f'Endpoint mismatch at {t}: {k}')
            count+=1
    return dict(endpoints=len(times), fields_compared=count, through_s=through, tolerance=1e-7)

def compare_runs(a,b,run_a,run_b,archived=False):
    a,b=__import__('pathlib').Path(a),__import__('pathlib').Path(b)
    through=run_a['end'] if archived else first_divergence(run_a,run_b)
    result=compare_endpoints(read(a/'endpoints.json'),read(b/'endpoints.json'),through,archived)
    core={'Occupancy[1]','LowerSetp[1]','UpperSetp[1]','TDryBul','HGloHor','time'}
    for i in range(864):
        x=read(a/f'forecast_{i:04d}.json')['data'];y=read(b/f'forecast_{i:04d}.json')['data']
        require(core<=x.keys() and core<=y.keys(),'Missing common core forecasts')
        if not archived:require(x.keys()==y.keys(),'New-arm forecast profiles differ')
        for k in x.keys() & y.keys():
            require(len(x[k])==len(y[k]) and all(abs(finite(v)-finite(w))<=1e-7 for v,w in zip(x[k],y[k])), 'Issued forecast mismatch: '+k)
    result.update(forecast_origins=864, archived_common_channels_only=archived)
    return result
