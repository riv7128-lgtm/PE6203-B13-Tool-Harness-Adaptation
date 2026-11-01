"""Run existing tests with a writable temp folder and optional official checkout."""
import argparse,os,sys,tempfile,unittest
from pathlib import Path
CODE=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path);ap.add_argument('--log',type=Path,required=True);args=ap.parse_args()
    args.log.parent.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(CODE))
    with tempfile.TemporaryDirectory(prefix='offline_',dir=args.log.parent) as tmp:
        tempfile.tempdir=tmp
        tests=Path(tmp)/'tests';tests.mkdir()
        for p in (CODE/'tests').glob('test_*.py'):
            text=p.read_text(encoding='utf-8')
            if args.repo:
                repo=args.repo.resolve()
                text=text.replace('Path(__file__).resolve().parents[5] / "work/official/MCPEvol-Bench"',repr_path(repo))
                text=text.replace('root = Path(__file__).resolve().parents[5]','root = '+repr_path(repo))
                text=text.replace('root / "work/official/MCPEvol-Bench/src/custom/analysis/answer/evolutionary_volatility.py"',repr_path(repo/'src/custom/analysis/answer/evolutionary_volatility.py'))
            (tests/p.name).write_text(text,encoding='utf-8')
        with args.log.open('w',encoding='utf-8') as f:
            result=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.discover(str(tests)))
        summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
        print(summary)
        return int(not result.wasSuccessful())
def repr_path(p):return 'Path('+repr(str(p))+')'
if __name__=='__main__':sys.exit(main())
