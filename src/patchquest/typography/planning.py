"""Capability-gated, integer-pixel layout plans; no game opcodes or ROM writes.

Plans are derived build artifacts, never edits to translations. Adapters must
encode and validate the result against their actual renderer before insertion.
"""
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import hashlib
import json
import re


@dataclass(frozen=True)
class Run:
    kind: str
    value: str = ''
    width: int = 0


@dataclass(frozen=True)
class Region:
    width: int
    height: int
    padding: tuple = (4, 4, 4, 4)  # left, top, right, bottom
    x: int = 0
    y: int = 0


@dataclass(frozen=True)
class WindowPolicy:
    name: str
    region: Region
    context: str = 'dialogue'
    line_height: int = 8
    line_step: int = 12
    wrap: bool = False
    scroll: bool = False
    paginate: bool = False
    # Evidence identifiers are supplied by the private adapter, never inferred.
    evidence: dict = field(default_factory=dict)
    small_overflow_px: int = 4
    small_overflow_ratio: float = .04
    moderate_overflow_ratio: float = .25
    # Explicitly verified alternatives, including borders/cursors/restoration.
    adjustments: tuple = ()
    resized_regions: tuple = ()
    balance: bool = True
    max_pages: int = 32
    max_lines: int = 128

    def validate(self):
        if not all(type(n) is int for n in (self.line_height,self.line_step,self.small_overflow_px,self.max_pages,self.max_lines)):
            raise ValueError('Pixel metrics and layout limits must be integers')
        if self.context not in ('dialogue', 'notification', 'menu', 'hud', 'fixed'):
            raise ValueError('Unknown window context')
        if not self.name or self.line_height <= 0 or self.line_step < self.line_height:
            raise ValueError('Invalid line metrics')
        if self.small_overflow_px < 0 or not 0 <= self.small_overflow_ratio <= self.moderate_overflow_ratio:
            raise ValueError('Invalid overflow thresholds')
        if self.max_pages < 1 or self.max_lines < 1:
            raise ValueError('Invalid layout limits')
        for capability, enabled in (('wrap', self.wrap), ('scroll', self.scroll),
                                    ('paginate', self.paginate), ('adjust', self.adjustments),
                                    ('resize', self.resized_regions)):
            if enabled and not self.evidence.get(capability):
                raise ValueError('Missing verified capability evidence: '+capability)
        if self.context in ('menu', 'hud', 'fixed') and (self.scroll or self.paginate or self.resized_regions):
            raise ValueError('Restricted UI needs an explicit specialized adapter, not dialogue flow')
        for region in (self.region, *self.adjustments, *self.resized_regions):
            if (not all(isinstance(n, int) and not isinstance(n, bool) for n in
                        (region.width, region.height, region.x, region.y, *region.padding))
                    or len(region.padding) != 4 or min(region.padding) < 0
                    or region.width <= sum(region.padding[::2]) or self.capacity(region) < 1):
                raise ValueError('Invalid padded region')
        for region in self.adjustments:
            if (region.width, region.height) != (self.region.width, self.region.height):
                raise ValueError('A spacing adjustment cannot resize a window')

    def capacity(self, region):
        available = region.height - region.padding[1] - region.padding[3]
        return 0 if available < self.line_height else 1 + (available-self.line_height)//self.line_step


@dataclass
class LayoutPlan:
    decision: str
    policy: str
    region: Region
    pages: list
    widths: list
    visible_lines: int
    overflow_px: int
    horizontal_overflow_px: int
    vertical_overflow_px: int
    severity: str
    input_sha256: str
    reason: str
    evidence: dict
    requires_emulator_review: bool = True

    def require_resolved(self):
        if self.decision == 'unresolved':
            raise ValueError('Unresolved layout for '+self.policy+': '+self.reason)
        return self

    def report(self):
        return asdict(self)


def text_runs(text):
    """Only literal text/newlines. Game escape parsing belongs to the adapter."""
    parts = text.split('\n')
    result = []
    for i, part in enumerate(parts):
        if i:
            result.append(Run('line'))
        result.append(Run('text', part))
    return tuple(result)


def pixel_measure(font, runs, left=0):
    """Visible bounds plus atom advances; opaque controls must be layout-inert.

    An atom reserves its verified maximum width (e.g. a dynamic number). A
    control carries an adapter-validated non-geometric event at this position.
    State-changing controls must instead be split/resolved by the adapter.
    """
    pen = left
    right = left
    pending = ''

    def flush():
        nonlocal pen, right, pending
        if pending:
            metrics = font.measure(pending)
            right = max(right, pen + metrics['width'])
            pen += metrics['advance']
            pending = ''

    for run in runs:
        if run.kind == 'text':
            pending += run.value
        else:
            flush()
            if run.kind == 'atom':
                pen += run.width
                right = max(right, pen)
            elif run.kind != 'control':
                raise ValueError('Unexpected line-measurement event')
    flush()
    return right


def plan_layout(font, runs, policy, measure=None):
    """Choose only supported presentations, preserving explicit event order.

    ``measure(runs, left_padding)`` may account for tile/segment quantization.
    It must return the occupied right edge, not a character count. Soft wrap
    consumes separator spaces, but never rewrites the authoritative input.
    """
    policy.validate()
    runs = tuple(runs)
    if any(not isinstance(r,Run) or not isinstance(r.value,str) or type(r.width) is not int
           or r.width < 0 or (r.kind != 'atom' and r.width != 0) for r in runs):
        raise ValueError('Invalid semantic run')
    if policy.line_height < font.height:
        raise ValueError('Policy line box would clip the font')
    if len(runs)>4096 or sum(len(r.value) for r in runs)>32768:
        raise ValueError('Layout input exceeds bounded planning budget')
    fingerprint = hashlib.sha256(json.dumps([asdict(r) for r in runs],
                                 ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    adapter_measure = measure or (lambda line, left: pixel_measure(font, line, left))
    def measure(line, left):
        width=adapter_measure(line,left)
        if type(width) is not int or width < 0:
            raise ValueError('Adapter must measure nonnegative integer pixels')
        return width
    original = [[[]]]
    for run in runs:
        if run.kind not in ('text', 'atom', 'control', 'line', 'page'):
            raise ValueError('Unknown semantic control; adapter must resolve it')
        if not isinstance(run.value, str) or not isinstance(run.width, int) or run.width < 0:
            raise ValueError('Invalid semantic run')
        if run.kind == 'text' and any(c in run.value for c in '\r\n\t'):
            raise ValueError('Use explicit line events; normalize formatting deliberately')
        if run.kind == 'page':
            original.append([[]])
        elif run.kind == 'line':
            original[-1].append([])
        else:
            original[-1][-1].append(run)
    if sum(map(len, original)) > policy.max_lines or len(original) > policy.max_pages:
        raise ValueError('Explicit layout exceeds configured limits')
    base = policy.region
    base_widths = [[measure(tuple(line), base.padding[0]) for line in page] for page in original]
    horizontal = max(0, max(w for page in base_widths for w in page) - (base.width-base.padding[2]))
    vertical = max(0, (max(map(len,original))-1)*policy.line_step+policy.line_height+base.padding[1]+base.padding[3]-base.height)
    overflow = max(horizontal,vertical)
    ratio = max(horizontal / (base.width-base.padding[0]-base.padding[2]), vertical / (base.height-base.padding[1]-base.padding[3]))
    small = overflow <= policy.small_overflow_px or ratio <= policy.small_overflow_ratio
    severity = 'none' if not overflow else 'small' if small else 'moderate' if ratio <= policy.moderate_overflow_ratio else 'large'

    def result(kind, region, pages, reason):
        widths = [[measure(tuple(line), region.padding[0]) for line in page] for page in pages]
        return LayoutPlan(kind, policy.name, region, pages, widths, policy.capacity(region),
                          overflow, horizontal, vertical, severity, fingerprint, reason, dict(policy.evidence))

    def fits(pages, region):
        return (len(pages) <= policy.max_pages and sum(map(len, pages)) <= policy.max_lines
                and all(len(page) <= policy.capacity(region) for page in pages)
                and all(measure(tuple(line), region.padding[0]) <= region.width-region.padding[2]
                        for page in pages for line in page))

    if len(original) > 1 and not policy.paginate:
        return result('unresolved', base, original, 'Explicit page event requires verified pagination')
    if any(len(page) > 1 for page in original) and not policy.wrap:
        return result('unresolved', base, original, 'Explicit newline requires verified line advancement')
    if fits(original, base):
        return result('original', base, original, 'Original presentation fits')
    if small:
        for region in policy.adjustments:
            if fits(original, region):
                return result('adjusted', region, original, 'Verified minor positioning/padding adjustment')

    def wrapped(region):
        output = []
        for page in original:
            lines = []
            for paragraph in page:
                if not policy.wrap:
                    lines.append(paragraph)
                    continue
                tokens = []
                for run in paragraph:
                    if run.kind == 'text':
                        tokens.extend(Run('text', t) for t in re.findall(r' +|[^ ]+', run.value))
                    else:
                        tokens.append(run)
                if len(tokens)>512:
                    raise ValueError('Paragraph exceeds bounded planning budget')
                if measure(tuple(tokens), region.padding[0]) <= region.width-region.padding[2]:
                    lines.append(tokens)
                    continue
                # Only spaces are soft-break opportunities. Opaque events stay
                # attached to their neighbors and cannot be lost/reordered.
                @lru_cache(None)
                def width(start, end):
                    return measure(tuple(tokens[start:end]), region.padding[0])
                ends = [i for i, token in enumerate(tokens) if token.kind == 'text' and token.value.isspace() and i > 0]
                ends.append(len(tokens))
                # Minimum line count first, then balanced visible lengths.
                # No arbitrary split of words, substitutions or control atoms.
                @lru_cache(None)
                def solve(start):
                    if start == len(tokens):
                        return (0, 0, ())
                    best = None
                    for end in ends:
                        if end <= start:
                            continue
                        occupied = width(start, end)
                        if occupied > region.width-region.padding[2]:
                            continue
                        following = end+1 if end < len(tokens) else end
                        tail = solve(following)
                        if tail is None:
                            continue
                        slack = region.width-region.padding[2]-occupied
                        score = slack*slack if policy.balance else -end
                        candidate = (1+tail[0], score+tail[1], ((start, end),)+tail[2])
                        if best is None or candidate[:2] < best[:2]:
                            best = candidate
                    return best
                solution = solve(0)
                if solution is None:
                    return None
                lines.extend(tokens[a:b] for a, b in solution[2])
            output.append(lines)
        return output

    flow = wrapped(base)
    if flow is not None and fits(flow, base):
        return result('wrapped', base, flow, 'Logical lines fit the original window')
    if (flow is not None and policy.scroll and sum(map(len, flow)) <= policy.max_lines
            and all(measure(tuple(line), base.padding[0]) <= base.width-base.padding[2] for page in flow for line in page)):
        return result('scrolled', base, flow, 'Verified native scrolling handles logical lines without enlarging the window')
    for region in policy.resized_regions:
        resized = wrapped(region)
        if resized is not None and fits(resized, region):
            return result('resized', region, resized, 'Explicitly verified alternate geometry')
    if flow is not None and policy.paginate:
        capacity = policy.capacity(base)
        pages = [page[start:start+capacity] for page in flow for start in range(0, len(page), capacity)]
        if fits(pages, base):
            return result('paginated', base, pages, 'Verified page advance preserves the original window')
    return result('unresolved', base, original, 'No verified strategy can display all content within bounds')
