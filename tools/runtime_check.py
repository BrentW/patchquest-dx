"""Explicit local runtime runner. Never downloads cores or discovers ROMs.

Native execution is bounded in a child process. No server route calls this tool.
"""
import argparse,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from patchquest.runtime import run,register,scenario_data
from patchquest.state import Store

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest');p.add_argument('--build',required=True)
    p.add_argument('--scenario',required=True);p.add_argument('--core',required=True);p.add_argument('--core-sha256',required=True)
    p.add_argument('--destination',required=True);p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    a=p.parse_args();store=Store(a.manifest);s=scenario_data(json.loads(Path(a.scenario).read_text(encoding='utf8')))
    out=store.context.output.check(a.destination)
    if out.exists():raise FileExistsError('Fresh runtime output required')
    if a.worker:
        from patchquest.libretro_runtime import Libretro
        adapter=Libretro(a.core,a.core_sha256);result=run(store,a.build,s,adapter,a.destination)
        print(json.dumps({'status':result['status'],'report':str(out/'runtime.json'),'frames':result['frames']}))
        return 0 if result['status']=='passed' else 1
    try:
        result=subprocess.run([sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),*sys.argv[1:],'--worker'],
                              timeout=s.get('timeout_seconds',120)+15,capture_output=True,text=True,encoding='utf8',
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except subprocess.TimeoutExpired:
        out.mkdir(parents=True,exist_ok=True)
        store.context.output.write_new(out/'worker-failure.json',b'{"status":"failed","reason":"Native worker exceeded wall-clock limit; no success claimed"}\n')
        print('Runtime worker timed out; private failure retained.');return 1
    out.mkdir(parents=True,exist_ok=True)
    store.context.output.write_new(out/'worker.log',(result.stdout+'\n'+result.stderr).encode())
    if (out/'runtime.json').is_file():register(store,out)
    print(result.stdout.strip() or 'Worker failed before producing a runtime report; inspect private worker.log.')
    return result.returncode

if __name__=='__main__':raise SystemExit(main())
