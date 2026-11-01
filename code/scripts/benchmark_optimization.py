"""Offline paired timing and semantic regression checks; no model calls."""
import argparse,copy,csv,hashlib,json,platform,random,statistics,sys,time
from pathlib import Path
CODE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(CODE))
from reference_harness.patch import selective_patch as old_patch,patch_with_audit as old_audit
from reference_harness.changes import detect_changes as old_diff
from harness_adapt.patch import selective_patch as new_patch,patch_with_audit as new_audit
from harness_adapt.changes import detect_changes as new_diff,canonical_digest
from harness_adapt.validation import preservation_report
from harness_adapt.baselines import full_rewrite,no_update

def scenario(n,ratio):
    old={'tools':[],'routing':{},'usage_rules':{},'global_rules':['Preserve unrelated records.']}
    for i in range(n):
        name=f'tool.{i:04}'
        old['tools'].append({'name':name,'description':'Lookup a record by identifier.','inputSchema':{'type':'object','properties':{'id':{'type':'string'}},'required':['id']}})
        old['routing'][name]=f'service/{i}';old['usage_rules'][name]=['Supply id.']
    new=copy.deepcopy(old);k=max(1,round(n*ratio))
    for i in range(k):
        new['tools'][i]['description']='Lookup a record using record_id instead of id.'
        new['tools'][i]['inputSchema']={'type':'object','properties':{'record_id':{'type':'string'}},'required':['record_id']}
        new['usage_rules'][f'tool.{i:04}']=['Supply record_id.']
    return old,new,k

def randomized_equivalence():
    rng=random.Random(6203)
    for case in range(120):
        old,new,_=scenario(rng.randrange(2,35),rng.choice([.01,.1,.5]))
        if case%2:
            removed=new['tools'].pop(0)['name']
            for field in ['routing','usage_rules']:new[field].pop(removed)
        if case%3==0:
            tool=copy.deepcopy(new['tools'][0]);tool['name']='new.tool';new['tools'].append(tool)
            new['routing']['new.tool']='new.route'
        if case%4==0:new['global_rules']=['Unsupported new global rule.']
        if case%5==0:new['tools'][0]['inputSchema']['default']=True
        if case%6==0:old['extra']={'a':False};new['extra']={'a':0}
        rng.shuffle(new['tools'])
        before=canonical_digest(old),canonical_digest(new)
        assert canonical_digest(old_diff(old,new))==canonical_digest(new_diff(old,new))
        p0,a0=old_audit(old,new);p1,a1=new_audit(old,new)
        assert canonical_digest(p0)==canonical_digest(p1)
        assert canonical_digest(a0)==canonical_digest(a1)
        assert preservation_report(old,new,p1)['preserved']
        assert before==(canonical_digest(old),canonical_digest(new))
        assert canonical_digest(new_patch(p1,new))==canonical_digest(p1)
        p1['tools'][0]['description']='mutated output only'
        assert before==(canonical_digest(old),canonical_digest(new))
    return 120

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--repeats',type=int,default=11)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    checks=randomized_equivalence();raw=[];summary=[]
    methods={'no_update':no_update,'full_rewrite':full_rewrite,'selective_original':old_patch,'selective_optimized':new_patch}
    for n in [100,300,1000]:
        for ratio in [.01,.1,.5]:
            old,new,k=scenario(n,ratio);inputs=canonical_digest(old),canonical_digest(new)
            for fn in methods.values():fn(old,new)
            samples={name:[] for name in methods}
            for repeat in range(args.repeats):
                order=list(methods);offset=repeat%len(order);order=order[offset:]+order[:offset]
                for name in order:
                    start=time.perf_counter_ns();result=methods[name](old,new);ms=(time.perf_counter_ns()-start)/1e6
                    samples[name].append(ms);raw.append({'tools':n,'changed':k,'repeat':repeat,'method':name,'elapsed_ms':ms})
                    assert canonical_digest(result)==canonical_digest(old if name=='no_update' else new)
                    assert preservation_report(old,new,result)['preserved']
                    assert inputs==(canonical_digest(old),canonical_digest(new))
            for name,values in samples.items():summary.append({'tools':n,'changed':k,'method':name,'repeats':args.repeats,'median_ms':statistics.median(values),'min_ms':min(values),'max_ms':max(values)})
            print(f'Completed {n} tools, {k} changed',flush=True)
    for filename,rows in [('summary.csv',summary),('raw_timings.csv',raw)]:
        with (args.output/filename).open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    pairs=[]
    for n in [100,300,1000]:
        for ratio in [.01,.1,.5]:
            k=max(1,round(n*ratio));rs={r['method']:r for r in summary if r['tools']==n and r['changed']==k}
            a,b=rs['selective_original']['median_ms'],rs['selective_optimized']['median_ms']
            pairs.append({'tools':n,'changed':k,'original_ms':a,'optimized_ms':b,'full_rewrite_ms':rs['full_rewrite']['median_ms'],'speedup':a/b,'reduction_pct':100*(1-b/a)})
    # Check the actual captured official snapshots as well, without running agents.
    evidence=CODE.parent/'results/supplement_20261029/interrupted_batch/snapshots'
    actual_checks=0
    if evidence.exists():
        old=json.loads((evidence/'early.json').read_text(encoding='utf-8'))
        for stage in ['early','middle','late']:
            new=json.loads((evidence/f'{stage}.json').read_text(encoding='utf-8'))
            assert canonical_digest(old_audit(old,new))==canonical_digest(new_audit(old,new));actual_checks+=1
    facts={'randomized_cases':checks,'official_snapshot_pairs':actual_checks,'measured_executions':len(raw),'scenario_count':9,'repeats':args.repeats,'model_calls':0,'pairs':pairs,'environment':{'python':sys.version,'platform':platform.platform()},'methodology':'One excluded warmup per method/scenario; cyclic order; same process/input/clock. Independent validation outside timing. Both methods retain internal preservation checks. Elapsed wall time, not CPU time.','source_sha256':{str(p.relative_to(CODE)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['harness_adapt','reference_harness'] for p in (CODE/folder).glob('*.py')}}
    (args.output/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(facts['pairs'],indent=2))
if __name__=='__main__':main()
