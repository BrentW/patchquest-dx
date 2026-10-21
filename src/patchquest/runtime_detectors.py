"""Capability-gated detectors over revision-bound observations and checked bytes.

No OCR, emulator execution, translation edits or checkpoint approval. Glyph IDs
and geometry are observations supplied by an explicit trusted adapter; private
controls must establish how reliably that instrumentation describes actual pixels.
"""
import copy
import hashlib
import json
import re
import struct
import zlib

from .runtime_contracts import (validate, check_observation, check_finding,
    contract_digest, binding_changes, verify_evidence_bytes, UnsupportedCapability,
    ContractError, expectation_manifest_data, expectation_capture_frame, FINDING_ID_ALGORITHM)

DETECTOR_VERSIONS = {k: '1' for k in ('bounds', 'overlap', 'glyphs', 'source_language',
                                    'completion', 'controls', 'resources', 'image_region')}
_PNG_BYTES = 4 * 1024 * 1024
_PNG_PIXELS = 1024 * 1024
_IMAGE_CHECK_PIXELS = 4 * _PNG_PIXELS
_IMAGE_DECODE_PIXELS = 4 * _PNG_PIXELS
_CONTROL_CAPS = dict(page_complete='page_advance', line_advanced='page_advance',
                     scrolled='native_scroll', input_wait='input', terminated=None)


class DetectorError(ValueError):
    """Invalid expectation, unknown algorithm/version or incompatible identity."""


def _need(condition, message):
    if not condition:
        raise DetectorError(message)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf8')).hexdigest()


def _text(value):
    _need(isinstance(value, str) and bool(value.strip()) and len(value) <= 500, 'Expected bounded text')


def _digest(value):
    _need(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Expected SHA-256')


def _integer(value, minimum=0, maximum=65536):
    _need(type(value) is int and minimum <= value <= maximum, 'Invalid detector integer')


def _ids(value, *, empty=False):
    _need(type(value) is list and (empty or bool(value)) and len(value) <= 10000, 'Invalid glyph sequence')
    for item in value:
        _text(item)


def expectation_data(value):
    """Validate versioned local expectations without changing pinned contents."""
    _need(type(value) is dict and set(value) == {'schema_version', 'expectation_id', 'case_sha256',
        'basis', 'checks', 'exceptions'}, 'Invalid expectation fields')
    data = copy.deepcopy(value)
    _need(type(data['schema_version']) is int and data['schema_version'] in (1, 2), 'Unknown expectation version')
    _text(data['expectation_id']); _digest(data['case_sha256'])
    basis = data['basis']
    _need(type(basis) is dict and set(basis) == {'method', 'reference_sha256', 'reason'}, 'Independent basis required')
    _need(basis['method'] in ('independent_inspection', 'synthetic_control'), 'Unsupported expectation basis')
    _digest(basis['reference_sha256']); _text(basis['reason'])
    _need(type(data['checks']) is list and 0 < len(data['checks']) <= 1000, 'Explicit bounded checks required')
    seen = set()
    fields = dict(bounds={'rect','padding','tolerance'}, overlap={'maximum_overlap_pixels'},
                  glyphs={'glyph_ids'}, source_language={'source_glyph_ids','mapping_sha256'},
                  completion=set(), controls={'expected'}, resources={'limits'},
                  image_region={'rect', 'rgb_sha256', 'expected_match'})
    for check in data['checks']:
        _need(type(check) is dict and 'kind' in check and isinstance(check['kind'], str) and check['kind'] in DETECTOR_VERSIONS, 'Unknown detector')
        kind = check['kind']
        selector = {'capture'} if kind == 'image_region' and data['schema_version'] == 2 else set()
        _need(set(check) == {'id', 'kind'} | fields[kind] | selector, 'Invalid detector check fields')
        try: expectation_capture_frame(check, data['schema_version'], None)
        except ContractError as error: raise DetectorError(str(error)) from error
        _text(check['id']); _need(check['id'] not in seen, 'Duplicate check identity'); seen.add(check['id'])
        if kind == 'bounds':
            rect = check['rect']
            _need(type(rect) is list and len(rect) == 4, 'Expected x,y,width,height')
            for v in rect[:2]: _integer(v, -65536)
            for v in rect[2:]: _integer(v, 1)
            _integer(check['padding'], 0, 64); _integer(check['tolerance'], 0, 64)
            _need(2 * check['padding'] < min(rect[2:]), 'Padding consumes interior')
        elif kind == 'overlap':
            _integer(check['maximum_overlap_pixels'], 0, 4096)
        elif kind in ('glyphs', 'source_language'):
            _ids(check['glyph_ids'] if kind == 'glyphs' else check['source_glyph_ids'], empty=kind == 'glyphs')
            if kind == 'source_language': _digest(check['mapping_sha256'])
        elif kind == 'controls':
            _need(type(check['expected']) is dict and bool(check['expected']) and
                  set(check['expected']) <= set(_CONTROL_CAPS), 'Invalid control expectations')
            _need(all(type(v) is bool for v in check['expected'].values()), 'Control expectations must be boolean')
        elif kind == 'resources':
            _need(type(check['limits']) is dict and 0 < len(check['limits']) <= 1000, 'Explicit resource limits required')
            for key, limit in check['limits'].items(): _text(key); _integer(limit, 0, 2**63-1)
        elif kind == 'image_region':
            rect = check['rect']
            _need(type(rect) is list and len(rect) == 4, 'Expected image x,y,width,height')
            for v in rect[:2]: _integer(v, 0, 4095)
            for v in rect[2:]: _integer(v, 1, 4096)
            _need(rect[2] * rect[3] <= _PNG_PIXELS, 'Image region exceeds pixel budget')
            _digest(check['rgb_sha256'])
            _need(type(check['expected_match']) is bool, 'Expected explicit image match boolean')
    _need(type(data['exceptions']) is list and len(data['exceptions']) <= 1000, 'Invalid exceptions')
    exceptions = set()
    for item in data['exceptions']:
        _need(type(item) is dict and set(item) == {'check_id','defect_sha256','content_binding_sha256','reason'},
              'Explicit revision-bound exception required')
        _need(item['check_id'] in seen, 'Exception refers to unknown check')
        _digest(item['defect_sha256']); _digest(item['content_binding_sha256']); _text(item['reason'])
        key = (item['check_id'], item['defect_sha256'])
        _need(key not in exceptions, 'Duplicate exception'); exceptions.add(key)
    _hash(data)  # Reject non-JSON/non-finite values, without mutating caller inputs.
    return data


def _expectations_data(value):
    if type(value) is not dict or 'kind' not in value:
        return expectation_data(value)
    # One canonical envelope validator. Detector semantics still examine every
    # inner plan, including cases not selected for this observation.
    try:
        result = expectation_manifest_data(value)
    except ContractError as error:
        raise DetectorError(str(error)) from error
    for case_digest, plan in result['cases'].items():
        result['cases'][case_digest] = expectation_data(plan)
    return result


def expectation_manifest(sequence):
    """Build the complete v1 case manifest; duplicate definitions fail closed.

    List/tuple order does not affect the canonical digest. Check order within an
    individual plan remains meaningful. No caller input is modified.
    """
    _need(type(sequence) in (list, tuple) and 0 < len(sequence) <= 10000,
          'Expected a bounded nonempty sequence of expectation plans')
    cases = {}
    for value in sequence:
        plan = expectation_data(value)
        _need(plan['case_sha256'] not in cases, 'Duplicate case digest')
        cases[plan['case_sha256']] = plan
    return _expectations_data(dict(schema_version=1, kind='RuntimeExpectationManifest',
        finding_id_algorithm=FINDING_ID_ALGORITHM, cases=cases))


def expectation_digest(value):
    """Pin the entire manifest or an explicitly supplied single-case plan."""
    return _hash(_expectations_data(value))


def exception_binding(binding, case_sha256):
    """Pin content/config/versions, excluding only expectation hash to avoid a cycle."""
    b = validate('RunBinding', binding)
    b.pop('expectation_sha256')
    _digest(case_sha256)
    return _hash(dict(binding=b, case_sha256=case_sha256))


def defect_digest(defect):
    """Exact observable-defect signature for an independently reviewed exception."""
    return _hash(defect)


def _png_rgb(raw, *, pixel_budget=None, reserve_pixels=None):
    """Strict RGB8, noninterlaced PNG only; bounded output, chunks and work.

    This deliberately accepts no ancillary chunks, palette, alpha or profiles.
    Such bytes are unknown evidence, never a visual mismatch.
    """
    _need(type(raw) is bytes and 0 < len(raw) <= _PNG_BYTES and
          raw.startswith(b'\x89PNG\r\n\x1a\n'), 'Unsupported or oversized PNG')
    pos = 8; width = height = None; parts = []; ended = False; chunks = 0
    while pos < len(raw):
        _need(pos + 12 <= len(raw), 'Truncated PNG chunk')
        n = int.from_bytes(raw[pos:pos+4], 'big'); kind = raw[pos+4:pos+8]
        end = pos + 12 + n
        _need(end <= len(raw), 'Truncated PNG data')
        data = raw[pos+8:pos+8+n]; chunks += 1
        _need(chunks <= 4096 and zlib.crc32(kind+data) & 0xffffffff ==
              int.from_bytes(raw[end-4:end], 'big'), 'PNG chunk budget or CRC failure')
        if width is None:
            _need(kind == b'IHDR' and n == 13, 'PNG header required first')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            _need(1 <= width <= 4096 and 1 <= height <= 4096 and width*height <= _PNG_PIXELS,
                  'PNG dimensions exceed budget')
            if pixel_budget is not None:
                _need(width*height <= pixel_budget, 'Image decode pixel budget exceeded')
            _need((depth,color,compression,filtering,interlace) == (8,2,0,0,0), 'Unsupported PNG format')
            if reserve_pixels is not None:
                reserve_pixels(width*height)  # Charge before allocation/inflation, including later failures.
        elif kind == b'IDAT':
            parts.append(data)
        elif kind == b'IEND':
            _need(n == 0 and parts and end == len(raw), 'Invalid PNG ending')
            ended = True
        else:
            raise DetectorError('Unsupported PNG chunk')
        pos = end
    _need(ended, 'PNG ending missing')
    stride = width * 3; size = height * (stride+1)
    decoder = zlib.decompressobj()
    try:
        scan = decoder.decompress(b''.join(parts), size+1)
    except zlib.error as error:
        raise DetectorError('Invalid PNG compression') from error
    _need(len(scan) == size and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
          'PNG decompression length or stream differs')
    rgb = bytearray(width*height*3); previous = bytearray(stride)
    for y in range(height):
        offset = y*(stride+1); mode = scan[offset]
        _need(0 <= mode <= 4, 'Unsupported PNG row filter')
        row = bytearray(scan[offset+1:offset+1+stride])
        for x in range(stride):
            left = row[x-3] if x >= 3 else 0; up = previous[x]; corner = previous[x-3] if x >= 3 else 0
            if mode == 1: prediction = left
            elif mode == 2: prediction = up
            elif mode == 3: prediction = (left+up)//2
            elif mode == 4:
                p = left+up-corner; distances = (abs(p-left), abs(p-up), abs(p-corner))
                prediction = (left, up, corner)[distances.index(min(distances))]
            else: prediction = 0
            row[x] = (row[x]+prediction) & 255
        rgb[y*stride:(y+1)*stride] = row; previous = row
    return width, height, bytes(rgb)


def _image_defects(check, image):
    width, height, rgb = image; x,y,w,h = check['rect']
    if x+w > width or y+h > height:
        return [], 'Image region outside captured frame', None
    region = b''.join(rgb[(row*width+x)*3:(row*width+x+w)*3] for row in range(y,y+h))
    actual = hashlib.sha256(region).hexdigest(); matches = actual == check['rgb_sha256']
    measurement = dict(rect=check['rect'], rgb_sha256=actual, observed_match=matches,
                       expected_match=check['expected_match'])
    defects = [] if matches == check['expected_match'] else [dict(code='image_region',
        region=check['rect'], expected_rgb_sha256=check['rgb_sha256'], **measurement)]
    return defects, '', measurement


def _glyph(g):
    return [g[k] for k in ('glyph_id','frame','x','y','width','height')]


def _defects(check, observation):
    """Return (defects, unknown reason); absence of instrumentation is handled outside."""
    kind = check['kind']
    final = observation['frames']
    glyphs = [g for g in observation['glyphs'] or [] if g['frame'] == final]
    defects = []
    if (kind in ('bounds','overlap','glyphs','source_language') and len(glyphs) > 4096) or (kind == 'overlap' and len(glyphs) > 256):
        return [], 'Detector comparison budget exceeded; narrow the declared case'
    if kind in ('bounds','overlap','glyphs','source_language'):
        if observation['controls'].get('page_complete') is not True:
            return [], 'Final page completion is not established; animation may still be in progress'
        if observation['glyphs'] is None:
            return [], 'Glyph observations were not supplied'
        if not glyphs and kind != 'glyphs':
            return [], 'No final-frame glyphs observed; empty text cannot certify visual correctness'
    if kind == 'bounds':
        x,y,w,h = check['rect']; p = check['padding']; t = check['tolerance']
        for g in glyphs:
            if g['x'] < x+p-t or g['y'] < y+p-t or g['x']+g['width'] > x+w-p+t or g['y']+g['height'] > y+h-p+t:
                defects.append(dict(code='bounds', glyph=_glyph(g), region=[g['x'],g['y'],g['width'],g['height']]))
    elif kind == 'overlap':
        for i,a in enumerate(glyphs):
            for b in glyphs[i+1:]:
                x=max(a['x'],b['x']); y=max(a['y'],b['y'])
                w=min(a['x']+a['width'],b['x']+b['width'])-x
                h=min(a['y']+a['height'],b['y']+b['height'])-y
                if w>0 and h>0 and w*h > check['maximum_overlap_pixels']:
                    defects.append(dict(code='overlap', glyphs=[_glyph(a),_glyph(b)], region=[x,y,w,h]))
    elif kind == 'glyphs':
        actual = [g['glyph_id'] for g in glyphs]
        if actual != check['glyph_ids']:
            defects.append(dict(code='glyph_sequence', expected=check['glyph_ids'], actual=actual))
    elif kind == 'source_language':
        for g in glyphs:
            if g['glyph_id'] in check['source_glyph_ids']:
                defects.append(dict(code='source_glyph', glyph=_glyph(g), region=[g['x'],g['y'],g['width'],g['height']]))
    elif kind in ('controls','completion'):
        expected = {'page_complete':True} if kind == 'completion' else check['expected']
        missing = []
        for key,wanted in expected.items():
            actual = observation['controls'].get(key)
            if actual is None: missing.append(key)
            elif actual != wanted: defects.append(dict(code='control', control=key, expected=wanted, actual=actual))
        # Known defects remain failures even if another expected control is unknown.
        if missing: return defects, 'Unobserved controls: ' + ', '.join(sorted(missing))
    elif kind == 'resources':
        observed = observation['resources']
        if observed is None: return [], 'Resource observations were not supplied'
        missing = []
        for key,limit in check['limits'].items():
            if key not in observed: missing.append(key)
            elif observed[key] > limit: defects.append(dict(code='resource_limit', resource=key, maximum=limit, actual=observed[key]))
        if missing: return defects, 'Unobserved resource metrics: ' + ', '.join(sorted(missing))
    return defects, ''


def detect(case, observation, capabilities, expectations, resolve_evidence, *, expected_binding=None):
    """Return immutable-input DetectorFindings; actual control acceptance is separate.

    resolve_evidence is normally RuntimeArtifacts.resolve. Every definite result
    requires checked captured bytes and the plan's selected capture. No OCR is inferred
    from capture capability alone, and no finding upgrades observation provenance.
    """
    c = validate('CaseSpec', case); o = validate('CaseObservation', observation)
    caps = validate('AdapterCapabilities', capabilities); plans = _expectations_data(expectations)
    case_digest = contract_digest('CaseSpec', c)
    if plans.get('kind') == 'RuntimeExpectationManifest':
        _need(case_digest in plans['cases'], 'Expectation manifest has no plan for this case')
        exp = plans['cases'][case_digest]
    else:
        exp = plans
    _need(exp['case_sha256'] == contract_digest('CaseSpec', c) == o['case_sha256'], 'Expectation case definition differs')
    digest = expectation_digest(plans)
    _need(o['binding']['expectation_sha256'] == digest, 'Expectation digest differs from RunBinding')
    capability_error = ''
    try:
        check_observation(c, o, caps)
    except UnsupportedCapability as error:
        capability_error = str(error)
    if expected_binding is not None:
        changed = binding_changes(o['binding'], expected_binding)
    else:
        changed = []
    _need(callable(resolve_evidence), 'Explicit evidence resolver required')
    evidence_ids = [capture['evidence']['evidence_id'] for capture in o['captures']]
    byte_error = ''; final_raw = None; final_hashes = set(); image = None; image_error = ''
    for capture in o['captures']:
        try:
            result = resolve_evidence(copy.deepcopy(capture['evidence']))
            if not isinstance(result, dict) or result.get('available') is not True or not verify_evidence_bytes(capture['evidence'], result.get('data')):
                byte_error = 'Capture bytes are missing, changed or unavailable'
            elif capture['frame'] == o['frames']:
                final_hashes.add(capture['evidence']['sha256'])
                final_raw = result['data'] if capture['evidence']['media_type'] == 'image/png' else None
        except (OSError, ValueError, KeyError, TypeError):
            byte_error = 'Capture integrity could not be established'
    if exp['schema_version'] == 1 and any(check['kind'] == 'image_region' for check in exp['checks']):
        if len(final_hashes) != 1 or final_raw is None:
            image_error = 'Unambiguous final PNG capture unavailable'
        else:
            try: image = _png_rgb(final_raw)
            except DetectorError as error: image_error = str(error)
    images = {}; decoded_pixels = 0
    def reserve_pixels(count):
        nonlocal decoded_pixels
        _need(count <= _IMAGE_DECODE_PIXELS-decoded_pixels, 'Image decode pixel budget exceeded')
        decoded_pixels += count
    def selected_png(capture):
        ref = capture['evidence']; key = ref['sha256']
        if key in images: return images[key]
        selected_image = None; error = ''
        try:
            resolved = resolve_evidence(copy.deepcopy(ref))
            if not isinstance(resolved, dict) or resolved.get('available') is not True or not verify_evidence_bytes(ref, resolved.get('data')):
                error = 'Selected capture bytes are missing, changed or unavailable'
            else:
                selected_image = _png_rgb(resolved['data'], pixel_budget=_IMAGE_DECODE_PIXELS-decoded_pixels,
                                          reserve_pixels=reserve_pixels)
        except (OSError, ValueError, KeyError, TypeError) as failure:
            error = str(failure) if isinstance(failure, DetectorError) else 'Selected capture integrity could not be established'
        images[key] = (selected_image, error)
        return images[key]
    findings = []; compared_pixels = 0
    for check in exp['checks']:
        kind = check['kind']; selected_image_check = kind == 'image_region' and exp['schema_version'] == 2
        version = '2' if selected_image_check else DETECTOR_VERSIONS[kind]
        _need(o['binding']['detectors'].get(kind) == version, 'Detector version absent or incompatible: ' + kind)
        finding_evidence_ids = evidence_ids; selected = None; selection_error = ''; capture_frame = None
        if selected_image_check:
            capture_frame = expectation_capture_frame(check, exp['schema_version'], o['frames'])
            captures = [c for c in o['captures'] if c['frame'] == capture_frame] if capture_frame is not None else []
            finding_evidence_ids = [captures[0]['evidence']['evidence_id']] if len(captures) == 1 else []
            if capture_frame is None: selection_error = 'Requested capture frame exceeds observed frames'
            elif len(captures) != 1: selection_error = 'Exact capture frame is missing or ambiguous'
            elif captures[0]['evidence']['media_type'] != 'image/png': selection_error = 'Selected capture is not a PNG'
            else: selected = captures[0]
        needed = ['capture_frames']
        if kind in ('bounds','overlap','glyphs','source_language'): needed += ['observe_glyphs','page_advance']
        elif kind == 'completion': needed.append('page_advance')
        elif kind == 'resources': needed.append('observe_resources')
        elif kind == 'controls': needed += [_CONTROL_CAPS[k] for k in check['expected'] if _CONTROL_CAPS[k]]
        missing = sorted(k for k in set(needed) if not caps['capabilities'][k])
        status = 'unknown'; reason = ''; defects = []; suppressed = []; unknown = ''; image_measurement = None
        applicable = [e for e in exp['exceptions'] if e['check_id'] == check['id']]
        if capability_error or missing:
            status = 'unsupported'; reason = capability_error or 'Missing instrumentation: ' + ', '.join(missing)
        elif o['validity'] != 'current' or changed:
            reason = 'Stale, invalid or unknown observation binding'
        elif o['execution'] != 'completed':
            reason = 'Execution is incomplete; rendering may still be in progress'
        elif o['provenance'] == 'actual_emulator' and exp['basis']['method'] != 'independent_inspection':
            reason = 'Synthetic expectations cannot calibrate actual emulator evidence'
        elif byte_error or (not selected_image_check and (not evidence_ids or not any(c['frame'] == o['frames'] for c in o['captures']))):
            reason = byte_error or 'Checked final-frame capture unavailable'
        elif selected_image_check and selection_error:
            reason = selection_error
        elif any(e['content_binding_sha256'] != exception_binding(o['binding'], o['case_sha256']) for e in applicable):
            reason = 'Declared exception is stale for the current content/configuration'
        else:
            if kind == 'image_region':
                current_image, current_error = image, image_error
                if selected_image_check: current_image, current_error = selected_png(selected)
                if current_error: defects, unknown = [], current_error
                elif compared_pixels + check['rect'][2]*check['rect'][3] > _IMAGE_CHECK_PIXELS:
                    defects, unknown = [], 'Image region comparison budget exceeded'
                else:
                    compared_pixels += check['rect'][2]*check['rect'][3]
                    defects, unknown, image_measurement = _image_defects(check, current_image)
                    if selected_image_check and image_measurement is not None:
                        image_measurement['capture_frame'] = capture_frame
                        for defect in defects: defect['capture_frame'] = capture_frame
            else: defects, unknown = _defects(check, o)
            active = {e['defect_sha256']: e for e in applicable}
            retained = []
            for defect in defects:
                signature = defect_digest(defect)
                if signature in active: suppressed.append(dict(defect=defect, exception=active[signature]))
                else: retained.append(defect)
            defects = retained
            status = 'failed' if defects else 'unknown' if unknown else 'passed'
            reason = 'Confirmed observable defect' if defects else unknown or ('Explicit revision-bound exceptions applied' if suppressed else '')
        diagnostic = dict(check_id=check['id'], defects=defects, suppressed=suppressed,
                          basis=exp['basis'], synthetic=o['provenance']=='synthetic',
                          unknown_reason=unknown, measurement='adapter_reported_observations')
        if kind == 'image_region':
            diagnostic.update(measurement='scoped_captured_rgb_region', image_region=image_measurement)
            if selected_image_check: diagnostic['capture'] = check['capture']
        region = next((d['region'] for d in defects if 'region' in d), None)
        control = next((d['control'] for d in defects if 'control' in d), None)
        finding = dict(schema_version=1, kind='DetectorFinding',
            finding_id='detector-' + _hash([o['observation_id'],check['id'],digest]),
            observation_id=o['observation_id'], case_id=o['case_id'], case_sha256=o['case_sha256'],
            binding=o['binding'], detector_id=kind, detector_version=version,
            expectation_id=exp['expectation_id'], status=status, evidence_ids=finding_evidence_ids,
            reason=reason, region=region, control=control, extensions={'patchquest:detector':diagnostic})
        findings.append(check_finding(finding, o))
    return findings
