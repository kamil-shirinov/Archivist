"""Detached local handoff from a recorded preparation call to the bounded experiment."""
import fcntl
import json
from pathlib import Path

from sparkft.cloud import OUT,cpu,require_owned,stop_owned,wait
from sparkft.runtime import MODEL,REVISION


def verify_preparation(result):
    if (result.get('model'),result.get('revision'),result.get('weight_shards')) != (MODEL,REVISION,65):
        raise ValueError('Recorded preparation did not stage the exact BF16 release')


def main():
    import modal
    from sparkft.backend import run
    lock=Path('results/scratch/sparkft/launch.lock')
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('w') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        saved=json.loads((OUT/'download_bf16_call.json').read_text())
        require_owned(saved['app_id'])
        continued=OUT/'download_bf16_resume_call.json'
        if continued.exists():
            saved=json.loads(continued.read_text());require_owned(saved['app_id'])
            result=wait(modal.FunctionCall.from_id(saved['call_id']),'recorded BF16 continuation')
        else:
            try:
                result=wait(modal.FunctionCall.from_id(saved['call_id']),'recorded BF16 preparation')
            except modal.exception.FunctionTimeoutError:
                stop_owned(saved['app_id'])  # Ensure the first writer is terminated before resuming.
                print('Initial preparation hit its hard bound; one declared CPU continuation',flush=True)
                result=cpu('download_bf16_resume',download=True)
        verify_preparation(result)
        (OUT/'download_bf16.json').write_text(json.dumps(result,indent=2)+'\n')
        print('Exact BF16 preparation completed; handing off to frozen registry backend',flush=True)
        run()


if __name__=='__main__':main()
