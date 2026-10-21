"""Bounded emulator scenarios and revision-bound private evidence.

Adapters supply actual frames. Synthetic adapters exercise orchestration only.
This module neither discovers emulators nor executes browser-supplied commands.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import time
import zlib

from .core.context import OutputPolicy, confined
from .state import canonical, now

BUTTONS = ('B','Y','Select','Start','Up','Down','Left','Right','A','X','L','R')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Integer outside scenario bounds')
    return value


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    rgb: bytes

    def __post_init__(self):
        bounded(self.width,1,2048); bounded(self.height,1,2048)
        if not isinstance(self.rgb,bytes) or len(self.rgb)!=self.width*self.height*3:
            raise ValueError('Expected packed RGB frame')

    def region(self,rect):
        if not isinstance(rect,list) or len(rect)!=4:raise ValueError('Expected x,y,width,height')
        x,y,w,h=rect
        bounded(x,0,self.width-1);bounded(y,0,self.height-1)
        bounded(w,1,self.width-x);bounded(h,1,self.height-y)
        return b''.join(self.rgb[((y+j)*self.width+x)*3:((y+j)*self.width+x+w)*3] for j in range(h))

    def png(self):
        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        rows=b''.join(b'\0'+self.rgb[y*self.width*3:(y+1)*self.width*3] for y in range(self.height))
        return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',self.width,self.height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')


def scenario_data(data):
    if not isinstance(data,dict) or set(data)-{'schema','id','rom_sha256','snapshot','records','initial','steps','timeout_seconds','notes'}:
        raise ValueError('Unknown scenario fields')
    if type(data.get('schema')) is not int or data['schema']!=1 or not isinstance(data.get('id'),str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',data['id']):raise ValueError('Scenario identity')
    for key in ('rom_sha256','snapshot'):
        if not re.fullmatch('[0-9a-f]{64}',data.get(key,'')):raise ValueError('Pinned ROM and snapshot required')
    records=data.get('records',{})
    if not isinstance(records,dict) or len(records)>200 or any(not isinstance(k,str) or type(v) is not int or v<1 for k,v in records.items()):raise ValueError('Explicit bounded record revisions required')
    initial=data.get('initial',{'kind':'cold_boot'})
    if initial=={'kind':'cold_boot'}:pass
    elif isinstance(initial,dict) and set(initial)=={'kind','path','sha256','rom_sha256','emulator_sha256'} and initial['kind'] in ('state','sram'):
        if not isinstance(initial['path'],str) or not initial['path']:raise ValueError('Explicit initial-data path required')
        for k in ('sha256','rom_sha256','emulator_sha256'):
            if not re.fullmatch('[0-9a-f]{64}',initial[k]):raise ValueError('Pinned state provenance required')
    else:raise ValueError('Unsupported initial state')
    bounded(data.get('timeout_seconds',120),1,600)
    steps=data.get('steps');seen=set();total=0;assertions=0
    if not isinstance(steps,list) or not 1<=len(steps)<=500:raise ValueError('Bounded scenario steps required')
    for step in steps:
        if not isinstance(step,dict) or set(step)-{'frames','buttons','capture','assertions'}:raise ValueError('Unknown step fields')
        total+=bounded(step.get('frames'),1,3600)
        buttons=step.get('buttons',[])
        if not isinstance(buttons,list) or len(buttons)!=len(set(buttons)) or any(b not in BUTTONS for b in buttons):raise ValueError('Invalid controller buttons')
        if 'capture' in step:
            name=step['capture']
            if not isinstance(name,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,80}',name) or name in seen:raise ValueError('Unique safe capture names required')
        checks=step.get('assertions',[])
        if not isinstance(checks,list) or len(checks)>100:raise ValueError('Invalid assertions')
        assertions+=len(checks)
        for check in checks:
            if not isinstance(check,dict) or not isinstance(check.get('label'),str) or not check['label']:raise ValueError('Named assertions required')
            kind=check.get('kind');allowed={'kind','label','rect'}
            allowed|={'sha256'} if kind=='region_hash' else {'color','tolerance','minimum','maximum'} if kind=='color_count' else {'capture','minimum','maximum'} if kind=='difference' else set()
            if kind not in ('region_hash','color_count','difference') or set(check)-allowed:raise ValueError('Unknown runtime assertion')
            if kind=='difference' and check.get('capture') not in seen:raise ValueError('Reference capture must precede comparison')
        if 'capture' in step:seen.add(step['capture'])
    if total>20000 or len(seen)>100 or not seen or not assertions:raise ValueError('Scenario needs captures/assertions within total budget')
    return json.loads(canonical(data))


def assertion(frame,check,captures):
    raw=frame.region(check['rect']);kind=check['kind']
    result={'label':check['label'],'kind':kind,'rect':check['rect']}
    if kind=='region_hash':
        expected=check['sha256']
        if not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('Expected region hash')
        observed=sha(raw);passed=observed==expected;result.update(expected=expected,observed=observed)
    else:
        count=len(raw)//3;minimum=bounded(check.get('minimum',0),0,count);maximum=bounded(check.get('maximum',count),minimum,count)
        if kind=='color_count':
            color=check['color'];tolerance=bounded(check.get('tolerance',0),0,255)
            if not isinstance(color,list) or len(color)!=3:raise ValueError('Expected RGB color')
            for c in color:bounded(c,0,255)
            observed=sum(all(abs(raw[i+c]-color[c])<=tolerance for c in range(3)) for i in range(0,len(raw),3))
        else:
            other=captures[check['capture']]
            if (other.width,other.height)!=(frame.width,frame.height):raise ValueError('Comparison dimensions changed')
            previous=other.region(check['rect']);observed=sum(raw[i:i+3]!=previous[i:i+3] for i in range(0,len(raw),3))
        passed=minimum<=observed<=maximum;result.update(observed=observed,minimum=minimum,maximum=maximum)
    return dict(result,passed=passed)


def run(store,build_id,scenario,adapter,destination):
    """Adapter: describe(), load(rom, workdir), step(buttons)->Frame,
    restore(bytes), load_save_ram(bytes), close(). Initial-data methods are
    required only when selected. Use a bounded child process for native adapters.
    No translation, approval or per-record emulator status is changed here.
    """
    s=scenario_data(scenario);build=next(b for b in store.builds() if b['id']==build_id)
    if build.get('snapshot')!=s['snapshot'] or build['status'] not in ('validated','historical'):raise ValueError('Build snapshot/status differs')
    snapshot=json.loads(Path(store.export_snapshot(s['snapshot'])).read_bytes());records={r['id']:r for r in snapshot['records']}
    if any(k not in records or records[k]['revision']!=v for k,v in s.get('records',{}).items()):raise ValueError('Scenario revisions differ from build')
    rom=store.context.output.check(build['artifacts']['rom']);raw=rom.read_bytes()
    if sha(raw)!=s['rom_sha256']:raise ValueError('Build ROM hash differs')
    out=store.context.output.check(destination)
    if out.exists():raise FileExistsError('Fresh runtime destination required')
    out.mkdir(parents=True);policy=OutputPolicy(out);policy.write_new('scenario.json',(canonical(s)+'\n').encode())
    description=adapter.describe()
    if description.get('kind') not in ('actual_emulator','synthetic'):raise ValueError('Adapter evidence kind required')
    report=dict(schema=1,id=s['id'],build_id=build_id,snapshot=s['snapshot'],rom_sha256=s['rom_sha256'],records=s.get('records',{}),
                scenario_sha256=sha(canonical(s).encode()),emulator=description,configuration_sha256=sha(canonical(description).encode()),
                level='automated_runtime' if description['kind']=='actual_emulator' else 'synthetic',status='running',
                started=now(),captures=[],assertions=[],inputs=[],human_accepted=False,notes=s.get('notes',''))
    frames={};start=time.monotonic();number=0
    try:
        adapter.load(raw,out/'sandbox')
        initial=s.get('initial',{'kind':'cold_boot'})
        if initial['kind'] in ('state','sram'):
            if initial['rom_sha256']!=s['rom_sha256'] or initial['emulator_sha256']!=description.get('sha256'):raise ValueError('State compatibility identity differs')
            state=confined(store.context.root,initial['path']).read_bytes()
            if sha(state)!=initial['sha256']:raise ValueError('State hash differs')
            if initial['kind']=='state':adapter.restore(state)
            else:adapter.load_save_ram(state)
        configured=adapter.describe()
        if configured.get('kind')!=description['kind'] or configured.get('sha256')!=description.get('sha256'):raise ValueError('Adapter identity changed at load')
        report.update(emulator=configured,configuration_sha256=sha(canonical(configured).encode()))
        for step in s['steps']:
            buttons=step.get('buttons',[]);first=number+1
            for _ in range(step['frames']):
                if time.monotonic()-start>s.get('timeout_seconds',120):raise TimeoutError('Scenario time budget exceeded')
                frame=adapter.step(buttons);number+=1
                if time.monotonic()-start>s.get('timeout_seconds',120):raise TimeoutError('Scenario time budget exceeded')
            report['inputs'].append(dict(first_frame=first,last_frame=number,buttons=buttons))
            if 'capture' in step:
                name=step['capture'];png=frame.png();policy.write_new(name+'.png',png);frames[name]=frame
                report['captures'].append(dict(id=name,frame=number,file=name+'.png',sha256=sha(png),width=frame.width,height=frame.height))
            for check in step.get('assertions',[]):
                value=assertion(frame,check,frames);report['assertions'].append(dict(value,frame=number))
                if not value['passed']:raise ValueError('Runtime expectation failed: '+value['label'])
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error={'type':type(error).__name__,'message':str(error)[:2000]})
    finally:
        try:adapter.close()
        except Exception as error:report.update(status='failed',close_error=str(error)[:1000])
    report.update(finished=now(),frames=number,elapsed_seconds=round(time.monotonic()-start,3))
    if callable(getattr(adapter,'observations',None)):report['observations']=adapter.observations()
    if rom.read_bytes()!=raw:report.update(status='failed',error={'message':'Build artifact changed during runtime'})
    policy.write_new('runtime.json',(canonical(report)+'\n').encode())
    return report


def register(store,directory):
    """Register trusted local runner output, preserving immutable evidence.
    This binds provenance, not a cryptographic attestation of an adapter's claims.
    """
    out=store.context.output.check(directory);raw=(out/'runtime.json').read_bytes();r=json.loads(raw)
    s=scenario_data(json.loads((out/'scenario.json').read_bytes()))
    if r.get('schema')!=1 or r.get('status') not in ('passed','failed') or r.get('human_accepted') is not False:raise ValueError('Invalid automated report')
    if any(r[k]!=s[k] for k in ('id','snapshot','rom_sha256')) or r['records']!=s.get('records',{}):raise ValueError('Scenario/report identity differs')
    if sha(canonical(s).encode())!=r['scenario_sha256'] or sha(canonical(r['emulator']).encode())!=r['configuration_sha256']:raise ValueError('Scenario/configuration hash differs')
    level={'actual_emulator':'automated_runtime','synthetic':'synthetic'}.get(r['emulator'].get('kind'))
    if level is None or r['level']!=level:raise ValueError('Evidence level differs from adapter')
    if r['status']=='passed' and (not r['assertions'] or not all(x['passed'] is True for x in r['assertions'])):raise ValueError('Passing report lacks passing assertions')
    build=next(b for b in store.builds() if b['id']==r['build_id'])
    if build['snapshot']!=r['snapshot'] or sha(store.context.output.check(build['artifacts']['rom']).read_bytes())!=r['rom_sha256']:raise ValueError('Evidence belongs to another build')
    snapshot=json.loads(Path(store.export_snapshot(r['snapshot'])).read_bytes());revisions={x['id']:x['revision'] for x in snapshot['records']}
    if any(revisions.get(k)!=v for k,v in r['records'].items()):raise ValueError('Evidence revision mismatch')
    captures=[];checked=[]
    for c in r['captures']:
        data=confined(out,c['file']).read_bytes()
        if sha(data)!=c['sha256']:raise ValueError('Capture changed')
        from .images import inspect
        info=inspect(data)
        if (info['width'],info['height'])!=(c['width'],c['height']):raise ValueError('Capture dimensions differ')
        checked.append((c,data))
    for c,data in checked:
        item=store.upload(data,dict(description=f"{r['level']}: {r['id']} / {c['id']}, frame {c['frame']}. Human acceptance separate.",
                                  build_id=r['build_id'],record_ids=list(r['records']),resource=r['id']))
        captures.append(dict(c,digest=item['digest']))
    summary={k:r[k] for k in ('id','level','status','snapshot','rom_sha256','records','scenario_sha256','configuration_sha256','human_accepted')}
    summary.update(report=str(out/'runtime.json'),report_sha256=sha(raw),captures=captures,assertions=r['assertions'],emulator=r['emulator'])
    expected=build.pop('revision');validation=build.setdefault('validation',{});runs=validation.setdefault('runtime',[])
    if not any(x.get('report_sha256')==summary['report_sha256'] for x in runs):runs.append(summary);store.build(build,expected)
    return summary


def reports(store,key=None):
    result=[]
    for b in store.builds():
        for r in b.get('validation',{}).get('runtime',[]):
            if key is not None and key not in r['records']:continue
            current=all(store.get(k)['revision']==v for k,v in r['records'].items())
            result.append(dict(r,build_id=b['id'],current=current,approval=b.get('approval',{})))
    return result
