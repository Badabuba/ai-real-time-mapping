"""Online observations, actual creation events, missing data and forced exit."""
import csv
from enum import Enum
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from rt_mapping.contracts.slam import SlamFrame, validate_rows
from rt_mapping.slam.tracking_log import FILES, METADATA, TrackingLog, install_tracking_export, read_tracking_log


def backend():
    class State(Enum):
        NOT_INITIALIZED = 1
        OK = 2
        LOST = 3

    class Map:
        def __init__(self):
            self.retained = []

        def add_keyframe(self, keyframe):
            self.retained.append(keyframe)
            return len(self.retained)-1

    class Slam:
        def __init__(self):
            self.map = Map()
            self.tracking = SimpleNamespace(state=State.NOT_INITIALIZED)
            self.quit_calls = 0
            self.result = object()

        def track(self, img, img_right, depth, img_id, timestamp=None, mask=None, mask_right=None):
            self.mask = mask
            self.tracking.state = (State.NOT_INITIALIZED, State.OK, State.LOST, State.OK)[img_id]
            pose = np.array([[0., -1, 0, img_id+0.1234567891234567],
                             [1, 0, 0, 2], [0, 0, 1, 3], [0, 0, 0, 1]])
            self.live_pose = pose
            self.tracking.f_cur = SimpleNamespace(timestamp=timestamp, Twc=lambda: self.live_pose.copy())
            if img_id == 1:
                # Both initialization keyframes are created now; no backfill.
                self.map.add_keyframe(SimpleNamespace(timestamp=1.))
                self.map.add_keyframe(SimpleNamespace(timestamp=timestamp))
            if img_id == 3:
                self.map.retained.clear()  # earlier creation events must survive culling
                self.map.add_keyframe(SimpleNamespace(timestamp=timestamp))
            return self.result

        def quit(self):
            self.quit_calls += 1
            return "original shutdown"

    frames = [{"frame_id": i, "rgb_timestamp_s": t} for i, t in zip((10,20,30,40),(1.,1.1,1.2,1.3))]
    return Slam, Map, frames


def run_fixture(directory):
    Slam, Map, frames = backend()
    ticks = iter(range(0, 80_000_000, 10_000_000))
    log = install_tracking_export(Slam, Map, directory, frames, clock=lambda: next(ticks))
    slam = Slam()
    for i, frame in enumerate(frames):
        assert slam.track(None, None, None, i, timestamp=frame["rgb_timestamp_s"], mask="mask") is slam.result
    slam.live_pose[:3, 3] = 999  # a later mutation cannot change already observed poses
    assert slam.quit() == "original shutdown"
    assert slam.quit() == "original shutdown"
    assert slam.quit_calls == 2 and slam.mask == "mask"
    return log, frames


def test_causal_rows_creation_events_and_timing(tmp_path):
    log, frames = run_fixture(tmp_path)
    rows, metadata = read_tracking_log(tmp_path, frames)
    assert [r.tracking_state for r in rows] == ["NOT_INITIALIZED","OK","LOST","OK"]
    assert rows[0].T_wc is None and rows[2].T_wc is None
    assert np.allclose(rows[1].T_wc[:3,3], [1.1234567891234567,2,3])
    assert np.allclose(rows[1].T_wc[:3,:3], [[0,-1,0],[1,0,0],[0,0,1]])
    assert [r.created_keyframe_frame_ids for r in rows] == [(),(10,20),(),(40,)]
    assert [r.tracking_ms for r in rows] == [10.]*4
    assert metadata["pose_count"] == 2 and metadata["keyframes_created"] == 3
    assert all(stream.closed for stream in log.streams)
    with (tmp_path / 'timing.csv').open(newline='') as stream:
        timing = list(csv.DictReader(stream))
    assert all(r['mapping_ms'] == r['total_ms'] == '' and r['mapping_reason'] and r['total_reason'] for r in timing)


def test_serialization_is_deterministic_and_refuses_overwrite(tmp_path):
    run_fixture(tmp_path / 'a')
    run_fixture(tmp_path / 'b')
    for name in (*FILES, METADATA):
        data = (tmp_path / 'a' / name).read_bytes()
        assert data == (tmp_path / 'b' / name).read_bytes() and b'\r' not in data
    _, _, frames = backend()
    with pytest.raises(ValueError, match='never overwrite'):
        TrackingLog(tmp_path / 'a', frames)


@pytest.mark.parametrize('unknown', [True, False])
def test_unknown_or_stale_pose_is_explicit(tmp_path, unknown):
    Slam, Map, frames = backend()
    def observe(self, *args, **kwargs):
        self.tracking.state = object() if unknown else SimpleNamespace(name='OK')
        self.tracking.f_cur = SimpleNamespace(timestamp=99., Twc=lambda: np.eye(4))
    Slam.track = observe
    log = install_tracking_export(Slam, Map, tmp_path, frames[:1])
    slam = Slam()
    slam.track(None, None, None, 0, timestamp=1.)
    slam.quit()
    rows, meta = read_tracking_log(tmp_path, frames[:1])
    assert rows[0].T_wc is None
    assert meta['state_counts'] == {'UNKNOWN' if unknown else 'OK': 1}
    assert rows[0].state_reason if unknown else rows[0].pose_reason.startswith('current_pose_unobservable:')


def test_original_exception_is_preserved_and_partial_row_flushed(tmp_path):
    Slam, Map, frames = backend()
    failure = RuntimeError('backend failure')
    def fail(self, *args, **kwargs):
        raise failure
    Slam.track = fail
    log = install_tracking_export(Slam, Map, tmp_path, frames)
    with pytest.raises(RuntimeError) as caught:
        Slam().track(None, None, None, 0, timestamp=1.)
    assert caught.value is failure
    data = (tmp_path / FILES[0]).read_text()
    assert 'track_raised:RuntimeError' in data
    with pytest.raises(ValueError, match='row count'):
        log.finish()
    assert not (tmp_path / METADATA).exists()


@pytest.mark.parametrize('change', ['partial_pose','nonfinite','quaternion','future_event','fake_timing','metadata_count','missing_row'])
def test_readback_rejects_corrupt_semantics_even_with_updated_hash(tmp_path, change):
    _, frames = run_fixture(tmp_path)
    name = 'timing.csv' if change == 'fake_timing' else FILES[0]
    path = tmp_path / name
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    if change == 'partial_pose': rows[1]['qw'] = ''
    if change == 'nonfinite': rows[1]['tx'] = 'nan'
    if change == 'quaternion': rows[1]['qw'] = '2'
    if change == 'future_event': rows[0]['is_keyframe_created'], rows[0]['created_keyframe_frame_ids'] = '1', '[40]'
    if change == 'fake_timing': rows[1]['mapping_ms'] = '0'
    if change == 'missing_row': rows.pop()
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    metadata = json.loads((tmp_path / METADATA).read_text())
    metadata['files'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if change == 'metadata_count': metadata['frame_count'] = 99
    (tmp_path / METADATA).write_text(json.dumps(metadata))
    with pytest.raises(ValueError): read_tracking_log(tmp_path, frames)


def test_checksum_and_input_identity_are_checked(tmp_path):
    log, frames = run_fixture(tmp_path)
    with pytest.raises(ValueError, match='IDs/timestamps'):
        validate_rows(log.rows, [{**f, 'frame_id': f['frame_id']+1} for f in frames])
    (tmp_path / FILES[0]).write_text('corrupt')
    with pytest.raises(ValueError, match='checksum'):
        read_tracking_log(tmp_path, frames)


def test_completed_log_survives_real_forced_process_exit(tmp_path):
    root = Path(__file__).resolve().parents[1]
    code = (f"import runpy,sys,os; sys.path.insert(0,{str(root/'src')!r}); "
            f"ns=runpy.run_path({str(Path(__file__).resolve())!r}); "
            f"ns['run_fixture']({str(tmp_path)!r}); os._exit(0)")
    done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=25)
    assert done.returncode == 0, done.stdout+done.stderr
    _, _, frames = backend()
    assert read_tracking_log(tmp_path, frames)[1]['frame_count'] == 4


@pytest.mark.parametrize('unknown', [False, True])
def test_runner_requires_valid_observations_and_degrades_unknown(tmp_path, monkeypatch, unknown):
    from rt_mapping.slam import smoke
    frames = [{'frame_id': i, 'rgb_timestamp_s': t} for i, t in enumerate((1.,1.1))]
    config = {'upstream': {'revision': 'a'*40, 'repo': 'https://example.invalid/pyslam'},
              'seed': 0, 'dataset_manifest': 'manifest.json', 'split': 'smoke'}
    (tmp_path / 'manifest.json').write_text(json.dumps({'splits': {'smoke': {'frames': frames}}}))
    interpreter = tmp_path / 'python'
    interpreter.touch()
    monkeypatch.setattr(smoke, 'verify_dataset', lambda *a: {'sequence': 'synthetic', 'archive_sha256': 'b'*64})
    monkeypatch.setattr(smoke, 'inspect_source', lambda *a: {'status': 'ok'})
    def metadata(argv, **kwargs):
        if 'rev-parse' in argv: return 'a'*40
        if 'status' in argv: return ''
        return json.dumps({'python': '3.11', 'numpy': '1.26', 'torch': '2.6', 'opencv_python': '4.11', 'ram_gb': 32.})
    monkeypatch.setattr(smoke.subprocess, 'check_output', metadata)
    def prepare(root, source, output, config, **kwargs):
        trajectory = output / 'trajectory'
        trajectory.mkdir(parents=True)
        np.savetxt(trajectory / 'trajectory_final.txt', [[1.,0,0,0,0,0,0,1],[1.1,1,0,0,0,0,0,1]])
        (trajectory / 'other_metrics_info.txt').write_text('num_total_frames: 2\nnum_processed_frames: 2\nnum_lost_frames: 0\n')
        return {'frames': frames, 'python_flags': [], 'argv_after_python': ['main_slam.py']}
    monkeypatch.setattr(smoke, 'prepare_baseline', prepare)
    def execute(argv, **kwargs):
        assert 'install_tracking_export' in argv[2]
        log = TrackingLog(tmp_path / 'results/runs/test_tracking', frames)
        for i, frame in enumerate(frames):
            missing = unknown and i == 0
            log.append(SlamFrame(frame['frame_id'], frame['rgb_timestamp_s'], 'UNKNOWN' if missing else 'OK',
                'unobservable' if missing else None, None if missing else np.eye(4),
                'unobservable' if missing else None, (), None, 1.))
        log.finish()
        return 0
    monkeypatch.setattr(smoke, 'execute_upstream', execute)
    path = smoke.run_smoke(tmp_path, tmp_path, interpreter, config, run_id='test_tracking', frames=2)
    record = json.loads((path / 'run.json').read_text())
    assert record['status'] == ('degraded' if unknown else 'ok'), record['reason']
    assert all(k in record['artifacts'] for k in ('trajectory_all','tracking_timing','tracking_export'))
