"""Provider-independent JSON operations shared by CLI and local Studio."""
from .state import Store


READ_ACTIONS = {'overview','progress','list','get','history','memory','proposals','events',
                'issues','issue-history','builds','evidence-list','attachments','attachment-history','jobs','capabilities',
                'agent-context','agent-sessions','work-list','work-history','layout-reports','narrative-context','runtime-reports',
                'assessment-catalog','assessment-context','assessments',
                'verification-plan','verification-report','verification-history','readiness',
                'milestones','milestone-preview','milestone-history',
                'screenshot-selection','screenshot-context','screenshot-preview','screenshot-history',
                'tester-reports','tester-report','tester-context','tester-history','tester-import-preview',
                'release-candidates','release-preview','release-history',
                'review-context','review-get','review-history'}
WRITE_ACTIONS = {'put','upsert','restore','import','activity','issue-put','evidence',
                 'snapshot','snapshot-export','build-report','memory-rebuild','backup','attach','attachment-update','build-submit',
                 'agent-start','agent-heartbeat','agent-close','work-create','work-claim','work-renew','work-publish','work-finish','work-resolve',
                 'migrate-exceptions','provider-result','progress-report',
                 'verification-plan-put','verification-observe','readiness-report',
                 'milestone-put','milestone-review','milestone-select','milestone-export',
                 'screenshot-put','screenshot-review','screenshot-select','screenshot-export',
                 'tester-import','tester-triage','release-put','release-validate','release-review','release-export',
                 'propose','review-create','review-propose','review-decide','review-apply',
                 'review-reserve-call','review-finish-call'}


def execute(store, action, params=None):
    p = params or {}
    if not isinstance(store, Store) or not isinstance(p, dict):
        raise ValueError('Expected store and object parameters')
    from .jobs import Jobs
    from .collaboration import Coordination
    from .agents import context
    from .typography.reports import layout_reports
    from .narrative import narrative_context
    from .runtime import reports as runtime_reports
    from . import assessments
    from .progress import write_report
    from . import verification
    from . import milestones
    from . import screenshot_selection as screenshots
    from . import tester_reports as testers
    from . import releases
    from . import narrative_review as review
    jobs=Jobs(store)
    work=Coordination(store)
    methods = {'overview':store.overview,'progress':store.progress,
               'propose':store.propose,
               'review-context':lambda **params:review.context(store,**params),
               'review-get':lambda **params:review.read(store,**params),
               'review-history':lambda **params:review.history(store,**params),
               'review-create':lambda **params:review.create(store,**params),
               'review-propose':lambda **params:review.propose(store,**params),
               'review-decide':lambda **params:review.decide(store,**params),
               'review-apply':lambda **params:review.apply(store,**params),
               'review-reserve-call':lambda **params:review.reserve_call(store,**params),
               'review-finish-call':lambda **params:review.finish_call(store,**params),
               'release-candidates':lambda:releases.read(store),
               'release-preview':lambda **params:releases.preview(store,**params),
               'release-history':lambda **params:releases.history(store,**params),
               'release-put':lambda **params:releases.put(store,**params),
               'release-validate':lambda **params:releases.validate(store,**params),
               'release-review':lambda **params:releases.review(store,**params),
               'release-export':lambda **params:releases.export(store,**params),
               'tester-reports':lambda **params:testers.list_reports(store,**params),
               'tester-report':lambda **params:testers.get(store,**params),
               'tester-context':lambda **params:testers.context(store,**params),
               'tester-history':lambda **params:testers.history(store,**params),
               'tester-import-preview':lambda **params:testers.preview_import(store,**params),
               'tester-import':lambda **params:testers.import_reports(store,**params),
               'tester-triage':lambda **params:testers.triage(store,**params),
               'screenshot-selection':lambda:screenshots.read(store),
               'screenshot-context':lambda **params:screenshots.context(store,**params),
               'screenshot-preview':lambda:screenshots.preview(store),
               'screenshot-history':lambda **params:screenshots.history(store,**params),
               'screenshot-put':lambda **params:screenshots.put(store,**params),
               'screenshot-review':lambda **params:screenshots.review(store,**params),
               'screenshot-select':lambda **params:screenshots.select(store,**params),
               'screenshot-export':lambda **params:screenshots.export(store,**params),
               'milestones':lambda:milestones.read(store),
               'milestone-preview':lambda:milestones.preview(store),
               'milestone-history':lambda **params:milestones.history(store,**params),
               'milestone-put':lambda **params:milestones.put(store,**params),
               'milestone-review':lambda **params:milestones.review(store,**params),
               'milestone-select':lambda **params:milestones.select(store,**params),
               'milestone-export':lambda **params:milestones.export(store,**params),
               'verification-plan':lambda:verification.plan(store),
               'verification-plan-put':lambda **params:verification.put_plan(store,**params),
               'verification-observe':lambda **params:verification.observe(store,**params),
               'verification-report':lambda **params:verification.report(store,**params),
               'verification-history':lambda **params:verification.history(store,**params),
               'readiness':lambda:verification.summary(store),
               'readiness-report':lambda:verification.write_summary(store),
               'progress-report':lambda:write_report(store),'list':store.list,'get':store.get,
               'assessment-catalog':assessments.catalog,
               'assessment-context':lambda **params:assessments.context(store,**params),
               'assessments':lambda **params:assessments.read(store,**params),
               'migrate-exceptions':lambda **params:assessments.migrate(store,**params),
               'provider-result':lambda **params:assessments.provider_result(store,**params),
               'history':store.history,'memory':store.memory,'proposals':store.proposals,
               'events':store.events,'issues':store.issues,'issue-history':store.issue_history,
               'builds':store.builds,'layout-reports':lambda key:layout_reports(store,key),
               'narrative-context':lambda **params:narrative_context(store,**params),
               'runtime-reports':lambda **params:runtime_reports(store,**params),
               'evidence-list':store.record_evidence,'attachments':store.attachments,
               'attachment-history':store.attachment_history,'attachment-update':store.update_attachment,
               'jobs':jobs.list,'capabilities':jobs.capabilities,'build-submit':jobs.submit,
               'put':store.put,'upsert':store.upsert,'restore':store.restore,'import':store.import_records,
               'activity':store.activity,'issue-put':store.put_issue,'evidence':store.evidence,
               'snapshot':store.snapshot,'snapshot-export':store.export_snapshot,
               'build-report':store.build,'memory-rebuild':store.rebuild_memory,'backup':store.backup,'attach':store.attach,
               'agent-context':lambda:context(store),'agent-sessions':work.sessions,
               'agent-start':work.start,'agent-heartbeat':work.heartbeat,'agent-close':work.close,
               'work-create':work.create,'work-list':work.list,'work-history':work.history,
               'work-claim':work.claim,'work-renew':work.renew,'work-publish':work.publish,
               'work-finish':work.finish,'work-resolve':work.resolve}
    if action not in methods:
        raise ValueError('Unknown state operation')
    return methods[action](**p)
