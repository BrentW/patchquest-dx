"""Provider-independent JSON operations shared by CLI and local Studio."""
from .state import Store


READ_ACTIONS = {'overview','list','get','history','memory','proposals','events',
                'issues','issue-history','builds','evidence-list','attachments','attachment-history','jobs','capabilities',
                'agent-context','agent-sessions','work-list','work-history','layout-reports'}
WRITE_ACTIONS = {'put','restore','import','activity','issue-put','evidence',
                 'snapshot','snapshot-export','build-report','memory-rebuild','backup','attach','attachment-update','build-submit',
                 'agent-start','agent-heartbeat','agent-close','work-create','work-claim','work-renew','work-publish','work-finish','work-resolve'}


def execute(store, action, params=None):
    p = params or {}
    if not isinstance(store, Store) or not isinstance(p, dict):
        raise ValueError('Expected store and object parameters')
    from .jobs import Jobs
    from .collaboration import Coordination
    from .agents import context
    from .typography.reports import layout_reports
    jobs=Jobs(store)
    work=Coordination(store)
    methods = {'overview':store.overview,'list':store.list,'get':store.get,
               'history':store.history,'memory':store.memory,'proposals':store.proposals,
               'events':store.events,'issues':store.issues,'issue-history':store.issue_history,
               'builds':store.builds,'layout-reports':lambda key:layout_reports(store,key),
               'evidence-list':store.record_evidence,'attachments':store.attachments,
               'attachment-history':store.attachment_history,'attachment-update':store.update_attachment,
               'jobs':jobs.list,'capabilities':jobs.capabilities,'build-submit':jobs.submit,
               'put':store.put,'restore':store.restore,'import':store.import_records,
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
