"""Hash-pinned immutable inputs and expected-byte edits."""
import hashlib

def load_source(path, expected_hash):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("Source SHA-256 mismatch")
    return data


def build(source, edits):
    result = bytearray(source)
    used = set()
    for edit in edits:
        start = int(edit["offset"], 0)
        old, new = bytes.fromhex(edit["expected_hex"]), bytes.fromhex(edit["replacement_hex"])
        end = start + len(old)
        if not old or start < 0 or end > len(source) or len(old) != len(new):
            raise ValueError("Edits must be nonempty, in bounds, and equal length")
        if source[start:end] != old or any(i in used for i in range(start, end)):
            raise ValueError("Original bytes mismatch or overlapping edits")
        used.update(range(start, end))
        result[start:end] = new
    return bytes(result)



def extract(source, ranges, table=None):
    """Explicit one-byte table; unknown tokens retain their byte identity."""
    records=[]
    for item in ranges:
        start=int(item["offset"],0);size=item["length"]
        if start<0 or size<=0 or start+size>len(source):
            raise ValueError("Range out of bounds")
        raw=source[start:start+size]
        records.append(dict(item,original_hex=raw.hex(),text="".join((table or {}).get(f"{b:02X}",f"<{b:02X}>") for b in raw),translation=""))
    return records
