"""Game-independent integer pixel typography. No ROM addresses/encoding here.

Measures ink and advances separately. Explicit newlines/indentation survive;
only a soft-wrap separator is removed. Refuses long words, missing glyphs and
overflow. Semantic control/substitution streams must be resolved by adapters.
"""
import hashlib
import json
import re
from pathlib import Path

from patchquest.typography.font import DEFAULT_FONT, load_font, bounds

PROFILES = DEFAULT_FONT.with_name('compact-profiles.json')


class Font:
    def __init__(self, profile='compact-ui', path=PROFILES):
        manifest = json.loads(Path(path).read_text(encoding='utf-8'))
        source = Path(path).parent / manifest['source']
        if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['source_sha256']:
            raise ValueError('Artwork differs from pinned source')
        _, original = load_font(source)
        self.name = profile
        self.profile = p = manifest['profiles'][profile]
        self.height, self.baseline, self.line_step = p['height'], p['baseline'], p['line_step']
        self.glyphs = {}
        for c, raw in original.items():
            box = bounds(raw)
            scale = p['scale']
            if 'fixed_advance' in p:
                advance = p['fixed_advance']
                matrix = [[v for v in r for _ in range(scale)] for r in raw for _ in range(scale)]
                bearing = 0
            else:
                bearing = box[0] if box else 0
                width = box[2]-box[0] if box else p['space']
                matrix = [r[bearing:bearing+width] for r in raw]
                advance = width+p['gap'] if box else p['space']
            yoff = self.baseline-(6*scale+scale-1)
            pixels = [[0]*len(matrix[0]) for _ in range(self.height)]
            for y, row in enumerate(matrix):
                if 0 <= y+yoff < self.height:
                    pixels[y+yoff] = row
                elif any(row):
                    raise ValueError('Profile clips ink')
            self.glyphs[c] = dict(pixels=pixels, advance=advance, ink=bounds(pixels), source_left=bearing)

    def measure(self, text):
        pen, points = 0, []
        for c in text:
            if c not in self.glyphs:
                raise ValueError(f'Unsupported glyph U+{ord(c):04X}')
            g = self.glyphs[c]
            if g['ink']:
                x0,y0,x1,y1 = g['ink'];points += [(pen+x0,y0),(pen+x1,y1)]
            pen += g['advance']
        ink = [min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)] if points else None
        return dict(advance=pen, ink=ink, width=ink[2] if ink else pen)

    def metrics(self):
        return dict(profile=self.name,height=self.height,baseline=self.baseline,line_step=self.line_step,
                    glyphs={f'{ord(c):04X}':{k:v for k,v in g.items() if k!='pixels'} for c,g in self.glyphs.items()})


def wrap(font, text, width, avoid_orphans=True):
    """Preserve hard breaks and internal spacing; no silent long-word splits."""
    if width <= 0 or '\r' in text or '\t' in text:
        raise ValueError('Invalid width or unnormalized formatting')
    result=[]
    for paragraph in text.split('\n'):
        if not paragraph:
            result.append('');continue
        words = re.findall(r' *[^ ]+| +$', paragraph)
        lines=[];line=''
        for word in words:
            trial=line+word
            if font.measure(trial)['width']<=width:
                line=trial;continue
            if not line or not word.strip():
                raise ValueError('Unbreakable text/indentation exceeds width')
            lines.append(line);line=word.lstrip(' ')
            if font.measure(line)['width']>width:
                raise ValueError('Unbreakable word exceeds width')
        lines.append(line)
        # Only rebalance soft lines inside the same paragraph. Never cross a
        # hard break or discard deliberate multiple spaces/indentation.
        if avoid_orphans and len(lines)>1 and len(lines[-1].split(' '))==1:
            prev=lines[-2]
            if prev==prev.strip() and '  ' not in prev and prev.count(' ')>=2:
                head,last=prev.rsplit(' ',1);trial=last+' '+lines[-1]
                if font.measure(trial)['width']<=width:
                    lines[-2:]=[head,trial]
        result.extend(lines)
    return result


def layout(font, text, width, height, padding=(4,4,4,4), align='left', valign='center', wrapping=True, vertical_metrics='ink'):
    """Return a binary raster and measurable block. Padding = left/top/right/bottom.

    Left alignment preserves intentional indentation. Center/right use actual
    line ink; vertical alignment uses the complete block including blank lines.
    vertical_metrics='font' aligns related rows to a common font box, retaining
    descender room independently of each string. The default preserves ink
    centering and existing build output.
    """
    if align not in ('left','center','right') or valign not in ('top','center','bottom'):
        raise ValueError('Unknown alignment')
    if vertical_metrics not in ('ink','font'):
        raise ValueError('Unknown vertical metrics')
    left,top,right,bottom=padding
    if min(width,height)<=0 or min(padding)<0:
        raise ValueError('Invalid region/padding')
    available=width-left-right
    lines=wrap(font,text,available) if wrapping else text.split('\n')
    measures=[font.measure(s) for s in lines]
    if any(m['width']>available for m in measures):raise ValueError('Horizontal overflow')
    nonempty=[(i,m['ink']) for i,m in enumerate(measures) if m['ink']]
    if vertical_metrics == 'font':
        ymin=0;ymax=(len(lines)-1)*font.line_step+font.height
    elif nonempty:
        ymin=min(i*font.line_step+b[1] for i,b in nonempty)
        ymax=max(i*font.line_step+b[3] for i,b in nonempty)
        if not lines[0]:ymin=0
        if not lines[-1]:ymax=(len(lines)-1)*font.line_step+font.height
    else:ymin=0;ymax=max(font.height,(len(lines)-1)*font.line_step+font.height)
    blockheight=ymax-ymin;free=height-top-bottom-blockheight
    if free<0:raise ValueError('Vertical overflow')
    start=top+(free//2 if valign=='center' else free if valign=='bottom' else 0)-ymin
    raster=[[0]*width for _ in range(height)];positions=[]
    for i,(line,m) in enumerate(zip(lines,measures)):
        ink=m['ink'];inkwidth=ink[2]-ink[0] if ink else 0
        x=left if align=='left' else left+(available-inkwidth)//2-(ink[0] if ink else 0) if align=='center' else width-right-(ink[2] if ink else 0)
        y=start+i*font.line_step;pen=x
        for c in line:
            g=font.glyphs[c]
            for gy,row in enumerate(g['pixels']):
                for gx,bit in enumerate(row):
                    if bit:
                        xx,yy=pen+gx,y+gy
                        if not left<=xx<width-right or not top<=yy<height-bottom:raise ValueError('Ink outside padded region')
                        raster[yy][xx]=1
            pen+=g['advance']
        positions.append(dict(text=line,x=x,y=y,baseline=y+font.baseline,**m))
    return dict(width=width,height=height,padding=list(padding),align=align,valign=valign,
                lines=positions,ink=bounds(raster),raster=raster)


def resolve_runs(runs, values):
    """Layout staging adapter contract, not a game opcode interpreter.

    Preserve opaque controls at character positions for the owning adapter.
    Page/wait semantics are NOT inferred; the caller must split pages before
    layout. Substitutions must resolve before measurement, never afterwards.
    """
    text='';events=[]
    for r in runs:
        if set(r)=={'text'}:text+=r['text']
        elif set(r)=={'variable'}:
            if r['variable'] not in values:raise ValueError('Unresolved substitution')
            text+=str(values[r['variable']])
        elif r=={'break':True}:text+='\n'
        elif set(r)=={'control'}:events.append(dict(position=len(text),control=r['control']))
        else:raise ValueError('Unknown run')
    return text,events
