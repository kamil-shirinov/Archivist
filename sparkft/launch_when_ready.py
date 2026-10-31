"""Detached local handoff from a recorded preparation call to the bounded experiment."""
import fcntl
import json
from pathlib import Path

from sparkft.cloud import OUT,WallBudgetTimeout,cpu,cpu_wall_seconds,require_owned,stop_owned,wait
from sparkft.runtime import MODEL,REVISION


def verify_preparation(result):
    if (result.get('model'),result.get('revision'),result.get('weight_shards')) != (MODEL,REVISION,65):
        raise ValueError('Recorded preparation did not stage the exact BF16 release')


def next_stage(index):
    if index not in (0,1):raise ValueError('No further weight-download continuation funded')
    return index+1


def main():
    import modal
    from sparkft.backend import run
    lock=Path('results/scratch/sparkft/launch.lock')
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('w') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stages=['download_bf16','download_bf16_resume','download_bf16_resume2']
        index=max(i for i,stage in enumerate(stages) if (OUT/(stage+'_call.json')).exists())
        while True:
            stage=stages[index];record=OUT/(stage+'_call.json')
            try:
                if record.exists():
                    saved=json.loads(record.read_text());require_owned(saved['app_id'])
                    result=wait(modal.FunctionCall.from_id(saved['call_id']),'recorded '+stage,
                                app_id=saved['app_id'],wall_seconds=cpu_wall_seconds(stage))
                else:
                    result=cpu(stage,download=True)
                break
            except (modal.exception.FunctionTimeoutError,WallBudgetTimeout) as error:
                saved=json.loads(record.read_text())
                if not isinstance(error,WallBudgetTimeout):stop_owned(saved['app_id'])
                index=next_stage(index)
                print('Download hit its hard bound; declared continuation',stages[index],flush=True)
        verify_preparation(result)
        (OUT/'download_bf16.json').write_text(json.dumps(result,indent=2)+'\n')
        print('Exact BF16 preparation completed; handing off to frozen registry backend',flush=True)
        run()


if __name__=='__main__':main()
