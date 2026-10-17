"""Invented text/geometry only; no private renderer evidence or fixtures."""
import _bootstrap
from dataclasses import replace
import unittest
from patchquest.typography.layout import Font
from patchquest.typography.planning import Run, Region, WindowPolicy, plan_layout, text_runs


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.font = Font()
        self.policy = WindowPolicy('invented-dialogue', Region(104, 32), wrap=True,
                                   paginate=True, evidence={'wrap':'synthetic contract', 'paginate':'synthetic contract'})

    def plan(self, text, **changes):
        return plan_layout(self.font, text_runs(text), replace(self.policy, **changes))

    def test_proportional_ink_and_exact_fit(self):
        self.assertLess(self.font.measure('iii')['width'], self.font.measure('WWW')['width'])
        width = self.font.measure('A short note.')['width']+8
        self.assertEqual(self.plan('A short note.', region=Region(width,32)).decision, 'original')
        self.assertNotEqual(self.plan('A short note.', region=Region(width-1,32)).decision, 'original')

    def test_threshold_boundaries_never_allow_clipping(self):
        text = 'Welcome'
        width = self.font.measure(text)['width']+8
        for overflow in (4,5):
            region = Region(width-overflow,32)
            policy = replace(self.policy, region=region, small_overflow_ratio=0,
                             adjustments=(replace(region,padding=(0,4,4,4)),),
                             evidence=dict(self.policy.evidence,adjust='synthetic margin audit'))
            plan = plan_layout(self.font,text_runs(text),policy)
            self.assertEqual(plan.severity, 'small' if overflow==4 else 'moderate')
            self.assertEqual(plan.decision, 'adjusted' if overflow==4 else 'unresolved')
        with self.assertRaises(ValueError):
            plan.require_resolved()

    def test_wrapping_and_balanced_pages(self):
        text = 'Bring a lantern and meet us beside the old harbor gate.'
        wrapped = self.plan(text,region=Region(150,56))
        self.assertEqual(wrapped.decision,'wrapped')
        paged = self.plan(text,region=Region(150,16))
        self.assertEqual(paged.decision,'paginated')
        words = ' '.join(''.join(r.value for r in line).strip() for page in paged.pages for line in page)
        self.assertEqual(words,text)
        self.assertTrue(all(len(page)==1 for page in paged.pages))

    def test_scrolling_precedes_resize_and_pagination(self):
        p=replace(self.policy,region=Region(120,16),scroll=True,resized_regions=(Region(200,80),),
                  evidence=dict(self.policy.evidence,scroll='synthetic advance/input/termination checks',resize='synthetic occupancy check'))
        result=plan_layout(self.font,text_runs('The courier left a note beside the garden fountain.'),p)
        self.assertEqual(result.decision,'scrolled')
        self.assertEqual(result.region,p.region)
        self.assertGreater(len(result.pages[0]),result.visible_lines)

    def test_newline_does_not_prove_scrolling(self):
        p=self.plan('One\nTwo\nThree',region=Region(90,16),paginate=False)
        self.assertEqual(p.decision,'unresolved')
        with self.assertRaisesRegex(ValueError,'scroll'):
            self.plan('One\nTwo',scroll=True)

    def test_explicit_lines_pages_and_blank_lines(self):
        r=self.plan('One\n\nTwo',region=Region(90,48))
        self.assertEqual(r.decision,'original')
        self.assertEqual(len(r.pages[0]),3)
        runs=(Run('text','One'),Run('page'),Run('text','Two'))
        p=plan_layout(self.font,runs,self.policy)
        self.assertEqual(len(p.pages),2)
        self.assertEqual(plan_layout(self.font,runs,replace(self.policy,paginate=False)).decision,'unresolved')

    def test_controls_and_dynamic_widths_preserved(self):
        runs=(Run('text','Please take '),Run('control','pause'),Run('atom','number',30),
              Run('text',' coins to the gate.'))
        p=plan_layout(self.font,runs,self.policy).require_resolved()
        events=[r for page in p.pages for line in page for r in line if r.kind!='text']
        self.assertEqual(events,[runs[1],runs[2]])
        self.assertEqual(plan_layout(self.font,(Run('atom','oversize',200),),self.policy).decision,'unresolved')
        with self.assertRaises(ValueError):
            plan_layout(self.font,(Run('unknown','opcode'),),self.policy)

    def test_restricted_windows(self):
        for context in ('menu','hud','fixed'):
            p=replace(self.policy,context=context,wrap=False,paginate=False)
            self.assertEqual(plan_layout(self.font,text_runs('A long label that must not change its interaction area'),p).decision,'unresolved')
            with self.assertRaises(ValueError):
                plan_layout(self.font,text_runs('Short'),replace(p,paginate=True))

    def test_only_verified_alternative_regions(self):
        p=replace(self.policy,region=Region(72,16),paginate=False,resized_regions=(Region(140,44,x=8,y=12),),
                  evidence=dict(self.policy.evidence,resize='synthetic border/cursor/restore test'))
        self.assertEqual(plan_layout(self.font,text_runs('A message for the gate guard.'),p).decision,'resized')
        with self.assertRaises(ValueError):
            plan_layout(self.font,text_runs('Hello'),replace(p,evidence={}))

    def test_quantized_adapter_measurement(self):
        def tile_width(runs,left):
            from patchquest.typography.planning import pixel_measure
            return ((pixel_measure(self.font,runs,left)+7)//8)*8
        text='Wiii'
        width=self.font.measure(text)['width']
        self.assertNotEqual(width%8,0)
        p=replace(self.policy,region=Region(width,16,(0,4,0,4)),wrap=False,paginate=False)
        self.assertEqual(plan_layout(self.font,text_runs(text),p).decision,'original')
        self.assertEqual(plan_layout(self.font,text_runs(text),p,measure=tile_width).decision,'unresolved')

    def test_vertical_bounds_and_invalid_metrics(self):
        p=self.plan('First\nSecond',region=Region(100,16))
        self.assertGreater(p.vertical_overflow_px,0)
        self.assertEqual(p.horizontal_overflow_px,0)
        self.assertEqual(p.decision,'paginated')
        with self.assertRaises(ValueError): self.plan('A',line_height=7)
        with self.assertRaises(ValueError): self.plan('A',line_step=12.5)
        with self.assertRaises(ValueError): plan_layout(self.font,text_runs('A'),self.policy,measure=lambda runs,left:-1)

    def test_long_word_missing_glyph_and_limits_fail_closed(self):
        self.assertEqual(self.plan('W'*50).decision,'unresolved')
        with self.assertRaises(ValueError): self.plan('\u2603')
        self.assertEqual(self.plan('One two three four five six seven eight nine ten',region=Region(80,16),max_pages=1).decision,'unresolved')
        with self.assertRaises(ValueError): self.plan('one\ntwo',max_lines=1)

    def test_planning_never_mutates_protected_input(self):
        record={'target':'Please meet us beside the quiet river.','revision':7,'human_corrected':True}
        before=dict(record)
        a=self.plan(record['target']);b=self.plan(record['target'])
        self.assertEqual(record,before)
        self.assertEqual(a.report(),b.report())
        self.assertTrue(a.requires_emulator_review)


if __name__=='__main__': unittest.main()
