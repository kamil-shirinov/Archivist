"""CPU-only checks of the declared fallback, offsets and budget. No GPU or archive opened."""
from types import SimpleNamespace

import pytest

from archivist.glimmer.title_audit import folded_offsets, locate_titles
from archivist.models.glimmer_allocation import NotAllocated, wait_for_call


class FakeClock:
    def __init__(self):
        self.now = 0
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds


class FakeRemote:
    object_id = 'fake-function'
    def __init__(self, clock, allocated_at=None, complete_at=None):
        self.clock, self.allocated_at, self.complete_at = clock, allocated_at, complete_at
        self.cancelled = False
        self.call = SimpleNamespace(object_id='fake-call', get=self.get, cancel=self.cancel)
    def spawn(self, payload):
        return self.call
    def get_current_stats(self):
        active = not self.cancelled and self.allocated_at is not None and self.clock() >= self.allocated_at
        return SimpleNamespace(num_total_runners=int(active), num_running_inputs=int(active),
                               backlog=0 if self.cancelled or active else 1)
    def get(self, timeout):
        self.clock.sleep(timeout)
        if self.complete_at is not None and self.clock() >= self.complete_at:
            return {'completed':True}
        raise TimeoutError()
    def cancel(self, terminate_containers):
        assert terminate_containers is True
        self.cancelled = True


def test_fallback_is_permitted_only_after_900_seconds_without_allocation_and_cancel_ack():
    clock = FakeClock()
    remote = FakeRemote(clock)
    events = []
    with pytest.raises(NotAllocated):
        wait_for_call(remote, {}, clock=clock, sleep=clock.sleep, event=events.append)
    assert clock() == 900
    assert remote.cancelled
    assert events[-1]['event'] == 'cancelled_unallocated'


def test_an_allocated_l4_is_not_cancelled_at_the_15_minute_boundary():
    clock = FakeClock()
    remote = FakeRemote(clock, allocated_at=895, complete_at=915)
    result = wait_for_call(remote, {}, clock=clock, sleep=clock.sleep)
    assert result == {'completed':True}
    assert not remote.cancelled


def test_unknown_provider_state_aborts_without_licensing_a_fallback():
    clock = FakeClock()
    remote = FakeRemote(clock)
    remote.get_current_stats = lambda: (_ for _ in ()).throw(RuntimeError('stats unavailable'))
    with pytest.raises(RuntimeError,match='stats unavailable'):
        wait_for_call(remote, {}, clock=clock, sleep=clock.sleep)
    assert remote.cancelled


def test_offsets_refer_to_original_ocr_and_boundary_crossing_is_not_hidden():
    text = 'x'*1024 + 'Short—Term   Foreign Liabilities'
    found = locate_titles(text,['Short-Term Foreign Liabilities'])
    assert found[0]['start_char_1based'] == 1025
    assert found[0]['starts_after_1024']
    assert found[0]['start_chars_past_1024'] == 1
    assert found[0]['end_char_1based'] == len(text)
    crossed = locate_titles('x'*1020 + 'Short-Term Foreign Liabilities',['Short-Term Foreign Liabilities'])[0]
    assert not crossed['starts_after_1024']
    assert crossed['full_title_not_retained_at_1024']
    assert folded_offsets('  A\n  B  ')[0] == 'a b'


def test_retained_reservations_leave_future_room_without_releasing_old_failures(tmp_path, monkeypatch):
    import json
    import archivist.glimmer.development_checks as checks
    monkeypatch.chdir(tmp_path)
    (tmp_path/'results/glimmer/phase2_preparation').mkdir(parents=True)
    (tmp_path/'results/glimmer/cost.json').write_text(json.dumps([{'maximum_usd':15.1296882}]))
    for name, value in [('cost.json',.7271512),('cost_attempt1.json',.8766904)]:
        (tmp_path/'results/glimmer/phase2_preparation'/name).write_text(json.dumps({'maximum_usd':value}))
    output=tmp_path/'output'
    output.mkdir()
    monkeypatch.setattr(checks,'OUT',output)
    record=checks.reserve()
    assert record['retained_after_checks_usd'] == pytest.approx(20.461749)
    assert record['remaining_for_future_run_usd'] == pytest.approx(3.848251)
    assert record['retained_after_checks_usd'] < 24.31
    with pytest.raises(ValueError,match='reserved'):
        checks.reserve()


def test_forecast_uses_selected_hardware_and_remaining_retained_budget():
    from archivist.glimmer.phase2_cost import project, require_budget_fit
    from archivist.models.glimmer_development_backend import RATES
    benchmark={'pages':40,'runtime_seconds':80,'rate_per_second_usd':RATES['L40S'],
               'selected_gpu':'L40S','prospective_function_limit_seconds':5000,
               'startup_allowance_seconds':300,'idle_allowance_seconds':15,
               'arm_results':{'untrained':{'runtime_seconds':40},'trained':{'runtime_seconds':20}}}
    expected=project(benchmark,500)
    assert expected['selected_gpu']=='L40S'
    assert expected['measured_seconds_per_paired_page']==1.5
    assert expected['expected_cost_usd']==pytest.approx((20+750+315)*RATES['L40S'])
    assert require_budget_fit(benchmark,500,20)['fits_runtime_limit']
    with pytest.raises(ValueError,match='retained cap'):
        require_budget_fit(benchmark,500,24)


def test_completed_development_evidence_uses_same_frozen_pages_and_fits_retained_boundary():
    import json
    from pathlib import Path
    from archivist.glimmer.data import load_frozen
    from archivist.glimmer.phase2 import parse_phase2
    from archivist.glimmer.phase2_cost import require_budget_fit
    from archivist.glimmer.metrics import score
    _, rows, families = load_frozen()
    output = Path('results/glimmer/development_checks')
    benchmark = json.loads((output/'benchmark.json').read_text())
    budget = json.loads((output/'budget.json').read_text())
    assert benchmark['input_page_ids'] == [r['page'] for r in rows]
    assert benchmark['ocr_prefix_chars'] == 1024
    assert sum(len(r['ocr']) > 1024 for r in rows) == 16
    labels = [f['family'] for f in families] + ['other']
    expected = {r['page']:r['target'] for r in rows}
    for arm in benchmark['arm_results'].values():
        assert len(arm['outputs']) == 40
        assert [r['index'] for r in arm['outputs']] == list(range(40))
        predicted = {row['page']:parse_phase2(answer['text'],labels,
                     at_token_limit=answer['at_token_limit'])
                     for row,answer in zip(rows,arm['outputs'],strict=True)}
        assert arm['metrics'] == score(expected,predicted,labels)
        assert arm['metrics']['accuracy'] == .975
        assert arm['metrics']['invalid'] == 0
    retained = budget['retained_after_checks_usd']
    assert require_budget_fit(benchmark,952,retained)['fits_runtime_limit']
    with pytest.raises(ValueError,match='runtime limit'):
        require_budget_fit(benchmark,953,retained)
