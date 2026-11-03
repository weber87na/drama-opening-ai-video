#!/usr/bin/env python3
"""Initialize, inspect and validate an editable AI video project.

Paths stored in JSON are relative to project.json, never the shell cwd.
This helper does not download media, generate artwork, or render a video.
"""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import sys


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'Cannot read JSON {path}: {exc}') from exc


def write_json(path, value, exclusive=False):
    with path.open('x' if exclusive else 'w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def project_config(root):
    config = read_json(root / 'project.json')
    if not isinstance(config, dict) or not all(isinstance(config.get(k), dict) for k in ('source', 'output')):
        raise ValueError('project.json must be an object with source and output objects.')
    return config


def resolve(root, value):
    return (root / value).resolve()


def remote(value):
    return isinstance(value, str) and '://' in value


def rate(value):
    try:
        result = Fraction(str(value))
        return result if result > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def probe_json(args):
    try:
        process = subprocess.run(['ffprobe', '-v', 'error', *args, '-of', 'json'],
                                 capture_output=True, text=True, encoding='utf-8')
    except FileNotFoundError as exc:
        raise ValueError('ffprobe is not installed or is not on PATH.') from exc
    if process.returncode:
        raise ValueError(f'ffprobe failed: {process.stderr.strip()}')
    return json.loads(process.stdout)


def probe_media(path, count=False):
    args = (['-count_frames'] if count else []) + ['-show_streams', '-show_format', str(path)]
    data = probe_json(args)
    video = next((s for s in data['streams'] if s.get('codec_type') == 'video'), None)
    if not video:
        raise ValueError(f'No video stream found in {path}')
    fps = rate(video.get('avg_frame_rate')) or rate(video.get('r_frame_rate'))
    duration = float(video.get('duration') or data.get('format', {}).get('duration') or 0)
    periods = []
    windows = sorted(set([0, max(0, duration / 2 - 2), max(0, duration - 5)]))
    for start in windows:
        rows = probe_json(['-select_streams', 'v:0', '-read_intervals', f'{start:.6f}%+5',
                           '-show_entries', 'frame=best_effort_timestamp_time', str(path)])
        stamps = [float(f['best_effort_timestamp_time']) for f in rows.get('frames', [])
                  if 'best_effort_timestamp_time' in f]
        periods.extend(b - a for a, b in zip(stamps, stamps[1:]) if b > a)
    expected = 1 / float(fps) if fps else None
    variable = expected and any(abs(d - expected) > max(.001, expected * .02) for d in periods)
    cadence = 'vfr' if variable else ('sampled-cfr' if periods and expected else 'unknown')
    count_value = video.get('nb_read_frames') if count else video.get('nb_frames')
    rotation = next((s['rotation'] for s in video.get('side_data_list', []) if 'rotation' in s),
                    video.get('tags', {}).get('rotate', 0))
    stat = path.stat()
    return {'width': video['width'], 'height': video['height'],
            'avg_frame_rate': video.get('avg_frame_rate'), 'r_frame_rate': video.get('r_frame_rate'),
            'frame_rate': str(fps) if fps else None, 'duration_seconds': duration,
            'frame_count': int(count_value) if str(count_value).isdigit() else None,
            'sample_aspect_ratio': video.get('sample_aspect_ratio', '1:1'),
            'display_aspect_ratio': video.get('display_aspect_ratio'), 'rotation': rotation,
            'cadence': cadence, 'timing_sample_count': len(periods),
            'timing_note': 'Cadence is sampled at start/middle/end, not a full PTS audit.',
            'audio_streams': sum(s.get('codec_type') == 'audio' for s in data['streams']),
            'file_size': stat.st_size, 'file_mtime_ns': stat.st_mtime_ns}


def initialize(args):
    root = Path(args.project_root).resolve()
    if min(args.width, args.height) <= 0 or (args.fps != 'source' and not rate(args.fps)):
        raise ValueError('Width/height must be positive; --fps must be source or a positive rational.')
    if args.style_start is not None and (not math.isfinite(args.style_start) or args.style_start < 0):
        raise ValueError('--style-start must be finite and nonnegative.')
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'project.json'
    if path.exists():
        read_json(path)
        emit({'status': 'preserved', 'project': str(path),
              'note': 'Existing project was not changed. Edit project.json to apply new options.'})
        return
    config = {'schema_version': 1, 'title': args.title, 'defaults_are_editable': True,
              'source': {'path': args.source, 'start_frame': 0, 'end_frame': None,
                         'crop_xyxy': None, 'timing_strategy': 'auto', 'probe': None},
              'style': {'source': args.style_source, 'start_seconds': args.style_start,
                        'end_seconds': None, 'description': None},
              'output': {'width': args.width, 'height': args.height, 'layout': args.layout,
                         'order': args.order, 'source_share': .5, 'fit': args.fit,
                         'fill': args.fill, 'fps': args.fps, 'audio': args.audio,
                         'path': 'output/final.mp4'}, 'timeline': 'shots.json', 'overlays': []}
    for folder in ('sources', 'references/live', 'references/style', 'assets/ai',
                   'assets/overlays', 'assets/prompts', 'analysis', 'output'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    write_json(path, config, exclusive=True)
    if not (root / 'shots.json').exists():
        write_json(root / 'shots.json', [], exclusive=True)
    emit({'status': 'created', 'project': str(path),
          'note': 'Defaults are editable suggestions. Relative paths resolve from this project directory.'})


def inspect(args):
    root = Path(args.project_root).resolve()
    path = root / 'project.json'
    config = project_config(root)
    source = args.source or config['source'].get('path')
    if not source or remote(source) or not resolve(root, source).is_file():
        raise ValueError('inspect needs an existing local source file; localize URLs first.')
    media = resolve(root, source)
    facts = probe_media(media, args.count_frames)
    if args.write_metadata:
        config['source']['path'] = source
        config['source']['probe'] = facts
        if config['source'].get('end_frame') is None:
            config['source']['end_frame'] = facts['frame_count']
        write_json(path, config)
    duration, fps = facts['duration_seconds'], rate(facts['frame_rate'])
    period = 1 / float(fps) if fps else min(.04, max(.000001, duration * .01))
    tail = max(0, duration - period)
    times = sorted(set([0, min(duration / 2, tail), tail]))
    commands = [['ffmpeg', '-ss', f'{t:.6f}', '-i', str(media), '-frames:v', '1',
                 str(root / f'references/live/inspect_{i:02}.png')] for i, t in enumerate(times)]
    emit({'source': str(media), 'probe': facts, 'metadata_written': args.write_metadata,
          'sample_commands_not_executed': commands,
          'next': 'Measure embedded borders and inspect sample frames. Use --count-frames if count is unknown.'})


def validate(args):
    root = Path(args.project_root).resolve()
    config = project_config(root)
    errors, warnings = [], []
    ready = args.mode == 'render-ready'

    def issue(message, unresolved=False):
        (warnings if unresolved and not ready else errors).append(message)

    def asset(value, label):
        if not isinstance(value, str) or not value or remote(value) or not resolve(root, value).is_file():
            issue(f'{label}: provide an existing local file (paths are relative to project.json).', True)

    def integer(value):
        return type(value) is int

    def span(a, b, label):
        if not integer(a) or not integer(b) or a < 0 or b <= a:
            issue(f'{label}: expected integer [start_frame,end_frame) with 0 <= start < end.')
            return False
        return True

    if config.get('schema_version') != 1:
        issue('Unsupported schema_version; expected 1.')
    source, output = config.get('source', {}), config.get('output', {})
    asset(source.get('path'), 'source.path')
    style = config.get('style', {})
    if not isinstance(style, dict) or not isinstance(style.get('references', []), list):
        raise ValueError('style must be an object; optional style.references must be a list.')
    references = [('style.source', style['source'])] if style.get('source') else []
    for i, value in enumerate(style.get('references', [])):
        if isinstance(value, dict):
            if 'path' not in value:
                raise ValueError(f'style.references[{i}] object requires an explicit path field.')
            value = value['path']
        references.append((f'style.references[{i}]', value))
    for label, value in references:
        if remote(value):
            warnings.append(f'{label}: URL reference was not retrieved; inspect its actual content before generation.')
        else:
            asset(value, label)
    for key in ('start_seconds', 'end_seconds'):
        value = style.get(key)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            issue(f'style.{key} must be a finite nonnegative number, or null.')
    a, b = style.get('start_seconds'), style.get('end_seconds')
    if type(a) in (int, float) and type(b) in (int, float) and b <= a:
        issue('style.end_seconds must be later than style.start_seconds.')
    probe = source.get('probe') or {}
    if not isinstance(probe, dict):
        raise ValueError('source.probe must be an object produced by inspect, or null.')
    if not rate(probe.get('frame_rate')):
        issue('Source FPS unresolved. Run inspect --write-metadata on the local source.', True)
    elif isinstance(source.get('path'), str) and not remote(source['path']) and resolve(root, source['path']).is_file():
        stat = resolve(root, source['path']).stat()
        if (stat.st_size, stat.st_mtime_ns) != (probe.get('file_size'), probe.get('file_mtime_ns')):
            issue('Source file differs from saved probe. Run inspect --write-metadata again.', True)
    strategy = source.get('timing_strategy', 'auto')
    if probe.get('cadence') not in ('cfr', 'sampled-cfr') and strategy != 'pts':
        issue('VFR/unknown cadence needs normalized CFR media and re-inspection, or timing_strategy=pts with a PTS-aware renderer.', True)
    if strategy == 'pts':
        warnings.append('PTS strategy selected: renderer must derive timestamps/durations from decoded source PTS, not frame/FPS.')
    if probe.get('rotation') or probe.get('sample_aspect_ratio', '1:1') not in ('1:1', '0:1', 'N/A', None):
        warnings.append('Source has rotation or non-square pixels; apply display geometry consistently to source/crop/motion references.')
    fps = probe.get('frame_rate') if output.get('fps') == 'source' else output.get('fps')
    if not rate(fps):
        issue('output.fps must be source with measured FPS, or a positive rational.', output.get('fps') == 'source')
    for key in ('width', 'height'):
        if not integer(output.get(key)) or output[key] <= 0:
            issue(f'output.{key} must be a positive integer.')
    share = output.get('source_share', .5)
    if not isinstance(share, (int, float)) or isinstance(share, bool) or not 0 < share < 1:
        issue('output.source_share must be between 0 and 1, exclusive.')
    supported = {'layout': ('stacked', 'side-by-side'), 'order': ('source-first', 'ai-first'),
                 'fit': ('cover', 'contain'), 'fill': ('outer-blur', 'none'), 'audio': ('source', 'none')}
    for key, values in supported.items():
        if output.get(key) not in values:
            warnings.append(f'Custom output.{key}={output.get(key)!r}: implement and verify this mode in the renderer.')
    if output.get('audio') == 'source' and probe.get('audio_streams') == 0:
        warnings.append('Source has no audio stream; render silent output or configure another audio source.')
    crop = source.get('crop_xyxy')
    if crop is not None:
        if not isinstance(crop, list) or len(crop) != 4 or not all(integer(x) for x in crop):
            issue('source.crop_xyxy must be four integers [x0,y0,x1,y1], far edges exclusive.')
        elif not probe.get('width') or not probe.get('height'):
            issue('Cannot validate source crop before inspecting source dimensions.', True)
        elif not (0 <= crop[0] < crop[2] <= probe['width'] and 0 <= crop[1] < crop[3] <= probe['height']):
            issue('source.crop_xyxy is empty or outside measured coded source dimensions.')
    begin, end = source.get('start_frame'), source.get('end_frame')
    if end is None:
        issue('source.end_frame unresolved. Inspect/count source or select an explicit frame range.', True)
    elif span(begin, end, 'source range') and probe.get('frame_count') is not None and end > probe['frame_count']:
        issue('source.end_frame exceeds measured source frame count.')
    timeline = config.get('timeline', 'shots.json')
    shots = read_json(resolve(root, timeline))
    if not isinstance(shots, list):
        raise ValueError('Timeline JSON must be a list of shot objects.')
    if any(not isinstance(shot, dict) for shot in shots):
        raise ValueError('Every timeline entry must be a shot object.')
    if not shots:
        issue('Timeline is empty; analyze representative shots before rendering.', True)
    ids, previous = set(), begin
    for i, shot in enumerate(shots):
        sid = shot.get('id')
        if not isinstance(sid, str) or not sid or sid in ids:
            issue(f'Shot {i}: id must be a unique nonempty string.')
        if isinstance(sid, str):
            ids.add(sid)
        a, b = shot.get('start_frame'), shot.get('end_frame')
        if span(a, b, f'Shot {sid}'):
            if previous is not None and a != previous:
                issue(f'Shot {sid}: timeline gap/overlap; start {a}, expected {previous}.')
            previous = b
            if 'representative_frame' in shot:
                representative = shot['representative_frame']
                if not integer(representative) or not a <= representative < b:
                    issue(f'Shot {sid}: representative_frame must be an integer within [start_frame,end_frame).')
        if shot.get('artwork') is not None:
            asset(shot['artwork'], f'Shot {sid} artwork')
        elif not shot.get('layers'):
            issue(f'Shot {sid}: needs artwork or nonempty layers.', True)
    if shots and end is not None and previous != end:
        issue(f'Timeline ends at {previous}, but source.end_frame is {end}.')
    if not isinstance(config.get('overlays', []), list) or any(not isinstance(s.get('layers', []), list) for s in shots):
        raise ValueError('overlays and per-shot layers must be lists of layer objects.')
    layers = [(x, None) for x in config.get('overlays', [])]
    layers += [(x, s) for s in shots for x in s.get('layers', [])]
    for layer, shot in layers:
        if not isinstance(layer, dict):
            raise ValueError('Every overlay/layer entry must be an object.')
        label = f'Layer {layer.get("id", "(unnamed)")}'
        asset(layer.get('path'), label)
        if layer.get('space') not in ('screen', 'scene'):
            issue(f'{label}: space must explicitly be screen or scene.')
        if layer.get('space') == 'scene' and not shot and layer.get('shot_id') not in ids:
            issue(f'{label}: scene-space layer must reference an existing shot_id.')
        a = layer.get('start_frame', shot.get('start_frame') if shot else None)
        b = layer.get('end_frame', shot.get('end_frame') if shot else None)
        if span(a, b, label) and integer(begin) and integer(end) and not begin <= a < b <= end:
            issue(f'{label}: time range is outside source selection.')
        target = shot or next((s for s in shots if s.get('id') == layer.get('shot_id')), None)
        if layer.get('space') == 'scene' and target and all(integer(x) for x in (a, b, target.get('start_frame'), target.get('end_frame'))):
            if not target['start_frame'] <= a < b <= target['end_frame']:
                issue(f'{label}: scene-space time range must stay within its target shot.')
    emit({'mode': args.mode, 'valid': not errors, 'errors': errors, 'warnings': warnings,
          'shots': len(shots), 'layers': len(layers), 'effective_output_fps': str(rate(fps)) if rate(fps) else None})
    return 1 if errors else 0


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='Create editable configuration; never overwrite an existing project.')
    init.add_argument('--project-root', required=True)
    for name in ('title', 'source', 'style-source'):
        init.add_argument('--' + name)
    init.add_argument('--style-start', type=float)
    init.add_argument('--width', type=int, default=1080)
    init.add_argument('--height', type=int, default=1920)
    for key, values in {'layout': ['stacked', 'side-by-side'], 'order': ['source-first', 'ai-first'],
                        'fit': ['cover', 'contain'], 'fill': ['outer-blur', 'none'], 'audio': ['source', 'none']}.items():
        init.add_argument('--' + key, choices=values, default=values[0])
    init.add_argument('--fps', default='source')
    scan = sub.add_parser('inspect', help='Probe local source; optionally save measured metadata.')
    scan.add_argument('--project-root', required=True)
    scan.add_argument('--source')
    scan.add_argument('--write-metadata', action='store_true')
    scan.add_argument('--count-frames', action='store_true')
    check = sub.add_parser('validate', help='Check drafts or enforce render-ready completeness.')
    check.add_argument('--project-root', required=True)
    check.add_argument('--mode', choices=['draft', 'render-ready'], default='draft')
    args = parser.parse_args()
    try:
        return {'init': initialize, 'inspect': inspect, 'validate': validate}[args.command](args) or 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        emit({'valid': False, 'error': str(exc)})
        return 1


if __name__ == '__main__':
    sys.exit(main())
