"""Independently authored teaching model; no ROM, font or private inputs.

Four-letter botanical/material words stand for opaque four-byte tiles. The tiny
bank windows and descriptor costs are invented, not console parameters. This is
not a shipped runtime loader or a hardware timing estimate. See TYPOGRAPHY.md.
"""
import json


def _integer(value, minimum):
    if type(value) is not int or value < minimum:
        raise ValueError('Invalid nonnegative/positive integer')
    return value


def deduplicate(payloads, tile_bytes):
    """Return exact-byte dictionary and maps, stable in supplied payload order.

    Callers must first verify expanded payload lengths and compatible encodings.
    This model checks only divisibility, not the expected size of an asset.
    """
    _integer(tile_bytes, 1)
    tiles, lookup, maps = [], {}, []
    for payload in payloads:
        if not isinstance(payload, bytes) or len(payload) % tile_bytes:
            raise ValueError('Payload must contain complete byte tiles')
        indices = []
        for start in range(0, len(payload), tile_bytes):
            tile = payload[start:start + tile_bytes]
            if tile not in lookup:
                lookup[tile] = len(tiles)
                tiles.append(tile)
            indices.append(lookup[tile])
        maps.append(tuple(indices))
    return b''.join(tiles), tuple(maps)


def coalesce(indices, *, tile_bytes, dictionary_tiles, source_start,
             bank_bytes, max_run_bytes):
    """Return (source, destination, length) byte spans in an abstract address space.

    Destination is contiguous from zero and all copies have the same mode. The
    source is linearly addressed; bank boundaries are multiples of bank_bytes.
    These assumptions do not implement a cartridge mapper or a console DMA mode.
    Reject a tile that itself crosses a bank rather than guessing how to split it.
    """
    for value in (tile_bytes, bank_bytes, max_run_bytes):
        _integer(value, 1)
    _integer(dictionary_tiles, 0)
    _integer(source_start, 0)
    if max_run_bytes < tile_bytes:
        raise ValueError('A tile exceeds the transfer limit')
    runs = []
    for position, index in enumerate(indices):
        _integer(index, 0)
        if index >= dictionary_tiles:
            raise ValueError('Dictionary index out of range')
        source = source_start + index * tile_bytes
        destination = position * tile_bytes
        if source // bank_bytes != (source + tile_bytes - 1) // bank_bytes:
            raise ValueError('A tile crosses a bank')
        if runs:
            old_source, old_destination, length = runs[-1]
            if (old_source + length == source
                    and old_destination + length == destination
                    and old_source // bank_bytes == source // bank_bytes
                    and length + tile_bytes <= max_run_bytes):
                runs[-1] = (old_source, old_destination, length + tile_bytes)
                continue
        runs.append((source, destination, tile_bytes))
    return tuple(runs)


def worked_example():
    # Invented byte patterns, order and costs; no glyphs or game-derived fixtures.
    payloads = (b'mossreedfernrock' * 4, b'rockfernreedmoss' * 2)
    dictionary, maps = deduplicate(payloads, 4)
    plans = tuple(coalesce(m, tile_bytes=4, dictionary_tiles=len(dictionary) // 4,
                           source_start=8, bank_bytes=16, max_run_bytes=12)
                  for m in maps)
    # Pretend format: two-byte source + one-byte length, implicit destination.
    descriptors = sum(len(plan) for plan in plans) * 3
    loader, lookup, padding = 12, 5, 3
    return {
        'evidence': 'synthetic model only',
        'original_payload_bytes': sum(map(len, payloads)),
        'dictionary_bytes': len(dictionary),
        'descriptor_bytes': descriptors,
        'loader_bytes': loader, 'lookup_bytes': lookup, 'padding_bytes': padding,
        'total_stored_bytes': len(dictionary) + descriptors + loader + lookup + padding,
        'transfer_count': sum(map(len, plans)),
        'uncoalesced_transfer_count': sum(map(len, maps)),
    }


if __name__ == '__main__':
    print(json.dumps(worked_example(), indent=2))
