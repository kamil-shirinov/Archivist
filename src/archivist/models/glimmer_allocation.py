"""Bounded GPU allocation waiting; model calls still enter through the normal backend."""
from __future__ import annotations

import time


class NotAllocated(TimeoutError):
    """Only raised after the declared wait and confirmed cancellation of an unallocated call."""


def wait_for_call(remote, payload, *, allocation_seconds=900, execution_seconds=900,
                  event=lambda record: None, clock=time.monotonic, sleep=time.sleep):
    started = clock()
    call = remote.spawn(payload)
    event({'event': 'submitted', 'function_id': remote.object_id, 'call_id': call.object_id})
    allocated = False
    last_minute = -1
    try:
        while True:
            elapsed = clock() - started
            stats = remote.get_current_stats()
            allocated = allocated or stats.num_total_runners > 0 or stats.num_running_inputs > 0
            minute = int(elapsed // 60)
            if minute != last_minute:
                event({'event': 'allocation_status', 'elapsed_seconds': elapsed,
                       'ever_allocated': allocated, 'runners': stats.num_total_runners,
                       'running_inputs': stats.num_running_inputs, 'backlog': stats.backlog})
                last_minute = minute
            if not allocated and elapsed >= allocation_seconds:
                call.cancel(terminate_containers=True)
                for _ in range(12):
                    confirm = remote.get_current_stats()
                    if (confirm.num_total_runners == 0 and confirm.num_running_inputs == 0
                            and confirm.backlog == 0):
                        event({'event': 'cancelled_unallocated', 'elapsed_seconds': elapsed})
                        raise NotAllocated(f'no GPU allocation within {allocation_seconds} seconds')
                    sleep(5)
                raise RuntimeError('cancellation not confirmed; fallback prohibited')
            if elapsed > allocation_seconds + 300 + execution_seconds + 15:
                raise RuntimeError('overall wait bound exceeded after allocation; no fallback')
            wait = 5 if allocated else min(5, max(.01, allocation_seconds - elapsed))
            try:
                result = call.get(timeout=wait)
                event({'event': 'completed', 'elapsed_seconds': clock() - started})
                return result
            except TimeoutError as error:
                if type(error).__name__ != 'TimeoutError':
                    raise  # A remote execution timeout is not a polling timeout.
    except NotAllocated:
        raise
    except BaseException:
        call.cancel(terminate_containers=True)
        raise
