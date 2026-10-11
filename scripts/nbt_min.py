"""Minimal NBT (Java edition) reader/writer: enough for map data files."""
import gzip, struct

END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LIST, COMPOUND, INT_ARRAY, LONG_ARRAY = range(13)


class Tag:
    def __init__(self, kind, value):
        self.kind, self.value = kind, value

    def __repr__(self):
        v = self.value
        if self.kind in (BYTE_ARRAY, INT_ARRAY, LONG_ARRAY):
            v = f'<{len(v)} items>'
        return f'Tag({self.kind}, {v!r})'


def _read(buf, pos, kind):
    if kind == BYTE:
        return Tag(kind, struct.unpack_from('>b', buf, pos)[0]), pos + 1
    if kind == SHORT:
        return Tag(kind, struct.unpack_from('>h', buf, pos)[0]), pos + 2
    if kind == INT:
        return Tag(kind, struct.unpack_from('>i', buf, pos)[0]), pos + 4
    if kind == LONG:
        return Tag(kind, struct.unpack_from('>q', buf, pos)[0]), pos + 8
    if kind == FLOAT:
        return Tag(kind, struct.unpack_from('>f', buf, pos)[0]), pos + 4
    if kind == DOUBLE:
        return Tag(kind, struct.unpack_from('>d', buf, pos)[0]), pos + 8
    if kind == BYTE_ARRAY:
        n = struct.unpack_from('>i', buf, pos)[0]
        return Tag(kind, bytes(buf[pos + 4:pos + 4 + n])), pos + 4 + n
    if kind == STRING:
        n = struct.unpack_from('>H', buf, pos)[0]
        return Tag(kind, buf[pos + 2:pos + 2 + n].decode('utf-8')), pos + 2 + n
    if kind == LIST:
        sub = buf[pos]
        n = struct.unpack_from('>i', buf, pos + 1)[0]
        pos += 5
        items = []
        for _ in range(n):
            t, pos = _read(buf, pos, sub)
            items.append(t)
        return Tag(kind, (sub, items)), pos
    if kind == COMPOUND:
        d = {}
        while True:
            k = buf[pos]
            pos += 1
            if k == END:
                return Tag(kind, d), pos
            n = struct.unpack_from('>H', buf, pos)[0]
            name = buf[pos + 2:pos + 2 + n].decode('utf-8')
            pos += 2 + n
            d[name], pos = _read(buf, pos, k)
    if kind == INT_ARRAY:
        n = struct.unpack_from('>i', buf, pos)[0]
        return Tag(kind, list(struct.unpack_from(f'>{n}i', buf, pos + 4))), pos + 4 + 4 * n
    if kind == LONG_ARRAY:
        n = struct.unpack_from('>i', buf, pos)[0]
        return Tag(kind, list(struct.unpack_from(f'>{n}q', buf, pos + 4))), pos + 4 + 8 * n
    raise ValueError(kind)


def load(path):
    raw = open(path, 'rb').read()
    buf = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
    kind = buf[0]
    n = struct.unpack_from('>H', buf, 1)[0]
    name = buf[3:3 + n].decode('utf-8')
    tag, _ = _read(buf, 3 + n, kind)
    return name, tag


def _write(t):
    k, v = t.kind, t.value
    if k == BYTE: return struct.pack('>b', v)
    if k == SHORT: return struct.pack('>h', v)
    if k == INT: return struct.pack('>i', v)
    if k == LONG: return struct.pack('>q', v)
    if k == FLOAT: return struct.pack('>f', v)
    if k == DOUBLE: return struct.pack('>d', v)
    if k == BYTE_ARRAY: return struct.pack('>i', len(v)) + bytes(v)
    if k == STRING:
        b = v.encode('utf-8'); return struct.pack('>H', len(b)) + b
    if k == LIST:
        sub, items = v
        return bytes([sub]) + struct.pack('>i', len(items)) + b''.join(_write(i) for i in items)
    if k == COMPOUND:
        out = b''
        for name, child in v.items():
            nb = name.encode('utf-8')
            out += bytes([child.kind]) + struct.pack('>H', len(nb)) + nb + _write(child)
        return out + b'\x00'
    if k == INT_ARRAY: return struct.pack('>i', len(v)) + struct.pack(f'>{len(v)}i', *v)
    if k == LONG_ARRAY: return struct.pack('>i', len(v)) + struct.pack(f'>{len(v)}q', *v)
    raise ValueError(k)


def save(path, tag, name=''):
    nb = name.encode('utf-8')
    data = bytes([tag.kind]) + struct.pack('>H', len(nb)) + nb + _write(tag)
    with open(path, 'wb') as f:
        f.write(gzip.compress(data))
