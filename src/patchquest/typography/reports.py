"""Read-only Studio projection of revision-bound private layout summaries."""
import json


def layout_reports(store, key):
    record = store.get(key)
    results = []
    for build in store.builds():
        validation=build.get('validation', {})
        report=validation.get('layout', {}) if isinstance(validation,dict) else {}
        if not isinstance(report,dict) or report.get('schema') != 1 or not isinstance(report.get('records'),dict):
            continue
        entry = report.get('records', {}).get(key)
        if not isinstance(entry, dict) or not isinstance(entry.get('variants'),dict):
            continue
        # A report cannot attach a layout to a different frozen revision. No
        # report-supplied filesystem paths are opened by this public endpoint.
        with store.connection() as db:
            row = db.execute('SELECT payload FROM snapshots WHERE digest=?', (build.get('snapshot'),)).fetchone()
        if not row:
            continue
        frozen = next((r for r in json.loads(row[0])['records'] if r['id']==key), None)
        if frozen is None or entry.get('revision') != frozen['revision']:
            continue
        results.append(dict(build_id=build['id'], build_status=build['status'],
                            snapshot=build['snapshot'], revision=entry['revision'],
                            current=entry['revision']==record['revision'],
                            variants=entry.get('variants', {}),
                            verification='Pipeline-reported static layout; emulator review is separate'))
    return results
