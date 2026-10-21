"""Private CSV round trips for Studio; never interpret cells as executable data."""
import csv
import io

FIELDS = ('project_id', 'id', 'revision', 'source', 'target', 'scene', 'speaker', 'category')
FILTERS = {'kind','query','scene','speaker','category','status','exception','content',
           'severity','investigation','stale'}


def export_csv(store, filters):
    if set(filters) - FILTERS:
        raise ValueError('Unsupported CSV filter')
    rows = store.list(**filters, limit=None)['items']
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: store.context.manifest['project_id'] if key == 'project_id'
                         else row[key] for key in FIELDS})
    return '\ufeff' + output.getvalue()


def import_csv(store, content):
    if not isinstance(content, str):
        raise ValueError('CSV text required')
    reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff'), newline=''), strict=True)
    if reader.fieldnames != list(FIELDS):
        raise ValueError('Use the exported CSV columns in their original order')
    changes = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Incomplete CSV row')
        if row['project_id'] != store.context.manifest['project_id']:
            raise ValueError('CSV belongs to another project')
        revision = int(row['revision'])
        if revision < 1:
            raise ValueError('Invalid revision')
        changes.append({'id': row['id'], 'revision': revision, 'target': row['target']})
    return store.correct_targets(changes)
