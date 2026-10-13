# -*- coding: utf-8 -*-
"""vsdec.py - pure Python (stdlib only) replacement of vsdec.js + the vidsrc WASM decryptor.
Used by plugins/vidsrcembed.py. Ported 25.09.2026 from plugin.video.zenoplay/_analiz/vidsrc/vsdec.py
(without the timing-only decrypt_interpreted). Any structure it does not recognise -> VsDecError.

The API data.vidsrc.sh/api.php?...&stream_urls returns data.stream_urls as
base64(nonce[12] || ChaCha20 ciphertext) plus vs.wasm_url (or vs.wasm) - a WASM
module per 5-minute window. The module has no imports; exports alloc/decrypt.
decrypt(ptr, n): nonce = ptr[0:12] -> mem; for block counter 0,1,...: blockfn(counter)
writes 64 bytes keystream; XOR in place at ptr+12. The block function is an unrolled
ChaCha20 (20 rounds, sigma "expand 32-byte k") whose key words are built from data
segments (in window 5967845: key = mem[0:32] XOR mem[3200:3232]; other segments are decoys).

This module does NOT hard-code offsets: it parses the WASM, runs the straight-line
prologue of the block function with a tiny evaluator over the initialised memory and
reads the 16 initial state words. It then checks the structure (sigma, counter slot,
rotl constants) and fails loudly if anything is different.

API:
    urls = decrypt_stream_urls(wasm_bytes, enc_b64)  -> list of str
    plain = decrypt_bytes(wasm_bytes, enc_bytes)      -> bytes
"""
import base64
import struct

SIGMA = (0x61707865, 0x3320646e, 0x79622d32, 0x6b206574)
M32 = 0xffffffff


class VsDecError(Exception):
    pass


# ---------------------------------------------------------------- WASM parsing
def _uleb(b, i):
    r = s = 0
    while True:
        x = b[i]; i += 1
        r |= (x & 0x7f) << s; s += 7
        if not x & 0x80:
            return r, i


def _sleb(b, i):
    r = s = 0
    while True:
        x = b[i]; i += 1
        r |= (x & 0x7f) << s; s += 7
        if not x & 0x80:
            break
    if x & 0x40:
        r -= 1 << s
    return r, i


def _decode(code):
    """Decode a function body (after locals) into [(op, arg)]. Only the ops the
    vidsrc module uses are accepted; anything else -> VsDecError."""
    ops = []; i = 0
    while i < len(code):
        op = code[i]; i += 1; arg = None
        if op in (0x02, 0x03, 0x04):
            arg = code[i]; i += 1
        elif op in (0x0c, 0x0d, 0x10, 0x20, 0x21, 0x22, 0x23, 0x24):
            arg, i = _uleb(code, i)
        elif 0x28 <= op <= 0x3e:
            _, i = _uleb(code, i); arg, i = _uleb(code, i)
        elif op in (0x3f, 0x40):
            i += 1
        elif op == 0x41:
            arg, i = _sleb(code, i); arg &= M32
        elif op in (0x05, 0x0b, 0x0f, 0x1a, 0x45, 0x46, 0x47, 0x49, 0x4b, 0x4d, 0x4f) or 0x6a <= op <= 0x78:
            pass
        else:
            raise VsDecError('unknown WASM opcode 0x%02x' % op)
        ops.append((op, arg))
    return ops


def parse_wasm(wasm):
    if wasm[:4] != b'\0asm':
        raise VsDecError('not a WASM module (magic %r)' % wasm[:4])
    i = 8; types = []; ftypes = []; exports = {}; bodies = []; mem = bytearray(65536); nimp = 0
    while i < len(wasm):
        sid = wasm[i]; n, i = _uleb(wasm, i + 1); d = wasm[i:i + n]; i += n
        if sid == 1:
            c, j = _uleb(d, 0)
            for _ in range(c):
                j += 1; pn, j = _uleb(d, j); j += pn; rn, j = _uleb(d, j); j += rn
                types.append(pn)
        elif sid == 2:
            nimp, _ = _uleb(d, 0)
            if nimp:
                raise VsDecError('WASM has %d imports (expected 0)' % nimp)
        elif sid == 3:
            c, j = _uleb(d, 0)
            for _ in range(c):
                t, j = _uleb(d, j); ftypes.append(t)
        elif sid == 7:
            c, j = _uleb(d, 0)
            for _ in range(c):
                ln, j = _uleb(d, j); nm = d[j:j + ln].decode('latin-1'); j += ln
                k = d[j]; idx, j = _uleb(d, j + 1)
                if k == 0:
                    exports[nm] = idx
        elif sid == 10:
            c, j = _uleb(d, 0)
            for _ in range(c):
                sz, j = _uleb(d, j); body = d[j:j + sz]; j += sz
                k = 0; nl, k = _uleb(body, k); nloc = 0
                for _ in range(nl):
                    cnt, k = _uleb(body, k); k += 1; nloc += cnt
                bodies.append((nloc, body[k:]))
        elif sid == 11:
            c, j = _uleb(d, 0)
            for _ in range(c):
                fl, j = _uleb(d, j)
                if fl != 0 or d[j] != 0x41:
                    raise VsDecError('unsupported data segment form')
                off, j = _sleb(d, j + 1)
                if d[j] != 0x0b:
                    raise VsDecError('unsupported data segment offset expr')
                ln, j = _uleb(d, j + 1)
                if off + ln > len(mem):
                    mem.extend(b'\0' * (off + ln - len(mem)))
                mem[off:off + ln] = d[j:j + ln]; j += ln
    funcs = [(types[ftypes[k]], nl, ops) for k, (nl, ops) in enumerate(bodies)]
    return funcs, exports, mem


# ---------------------------------------------------------- straight-line evaluator
def _rotl(x, n):
    n &= 31
    return ((x << n) | (x >> (32 - n))) & M32


_BIN = {
    0x6a: lambda a, b: (a + b) & M32, 0x6b: lambda a, b: (a - b) & M32, 0x6c: lambda a, b: (a * b) & M32,
    0x71: lambda a, b: a & b, 0x72: lambda a, b: a | b, 0x73: lambda a, b: a ^ b,
    0x74: lambda a, b: (a << (b & 31)) & M32, 0x76: lambda a, b: a >> (b & 31),
    0x77: _rotl, 0x78: lambda a, b: _rotl(a, 32 - (b & 31)),
}


def run_straight(ops, locs, mem, stop=None):
    """Evaluate straight-line i32 code. stop(locs, k) -> True stops before op k.
    Returns the index where evaluation stopped."""
    st = []
    for k, (op, a) in enumerate(ops):
        if stop is not None and stop(k):
            return k
        if op == 0x41:
            st.append(a)
        elif op == 0x20:
            st.append(locs[a])
        elif op == 0x21:
            locs[a] = st.pop()
        elif op == 0x22:
            locs[a] = st[-1]
        elif op == 0x28:
            p = st.pop() + a; st.append(struct.unpack_from('<I', mem, p)[0])
        elif op == 0x36:
            v = st.pop(); p = st.pop() + a; struct.pack_into('<I', mem, p, v)
        elif op in _BIN:
            b = st.pop(); x = st.pop(); st.append(_BIN[op](x, b))
        elif op == 0x0b and k == len(ops) - 1:
            return k
        else:
            raise VsDecError('op 0x%02x at %d is not straight-line i32' % (op, k))
    return len(ops)


# ------------------------------------------------------------------ the analysis
class Module(object):
    def __init__(self, wasm):
        self.funcs, self.exports, self.mem0 = parse_wasm(wasm)
        if 'decrypt' not in self.exports:
            raise VsDecError('no export decrypt (exports: %s)' % sorted(self.exports))
        dec = self.funcs[self.exports['decrypt']]
        self.dec_ops = _decode(dec[2])
        calls = [a for (op, a) in self.dec_ops if op == 0x10]
        if len(calls) != 1:
            raise VsDecError('decrypt calls %d functions (expected 1)' % len(calls))
        blk = self.funcs[calls[0]]
        if blk[0] != 2:
            raise VsDecError('block function has %d params (expected 2)' % blk[0])
        self.blk_nparams = blk[0]; self.blk_nloc = blk[1]
        self.blk_ops = _decode(blk[2])
        self._check_structure()
        self._find_layout()

    def _check_structure(self):
        rot = {}
        for k, (op, a) in enumerate(self.blk_ops):
            if op == 0x77:
                p = self.blk_ops[k - 1]
                c = p[1] if p[0] == 0x41 else None
                rot[c] = rot.get(c, 0) + 1
        if rot != {16: 80, 12: 80, 8: 80, 7: 80}:
            raise VsDecError('block function is not 20-round ChaCha (rotl counts %s)' % rot)
        if any(op in (0x02, 0x03, 0x04, 0x0c, 0x0d, 0x10) for op, _ in self.blk_ops):
            raise VsDecError('block function has control flow (expected straight-line)')

    def _find_layout(self):
        """From decrypt: where the nonce goes, where the keystream is read, the data offset."""
        ops = self.dec_ops
        # prologue: 3x (const DST; local.get 0 [; const k; add]; load; store) before first local.set
        self.nonce_dst = []
        k = 0
        while ops[k][0] != 0x21:
            if ops[k][0] == 0x36:
                self.nonce_dst.append(None)
            k += 1
        mem = bytearray(self.mem0)
        probe = 0x9000
        mem.extend(b'\0' * max(0, probe + 64 - len(mem)))
        mem[probe:probe + 12] = bytes(range(1, 13))
        locs = [probe, 12] + [0] * 16
        before = bytes(mem)
        run_straight(ops[:k], locs, mem)
        diff = [i for i in range(len(before)) if before[i] != mem[i]]
        if len(diff) != 12 or bytes(mem[diff[0]:diff[0] + 12]) != bytes(range(1, 13)) or diff[-1] - diff[0] != 11:
            raise VsDecError('decrypt prologue does not copy a 12-byte nonce (changed bytes %s)' % diff[:20])
        self.nonce_off = diff[0]
        # data offset: first "local.get 0; i32.const N; i32.add; local.set" after the prologue
        self.data_off = None
        for j in range(k - 3, len(ops) - 3):
            if ops[j] == (0x20, 0) and ops[j + 1][0] == 0x41 and ops[j + 2][0] == 0x6a and ops[j + 3][0] == 0x21:
                self.data_off = ops[j + 1][1]; break
        if self.data_off != 12:
            raise VsDecError('decrypt data offset %s (expected 12)' % self.data_off)
        # keystream buffer: "i32.const KS; local.get x; i32.add; i32.load8_u" inside the xor loop
        self.ks_off = None
        for j in range(len(ops) - 3):
            if ops[j][0] == 0x41 and ops[j + 1][0] == 0x20 and ops[j + 2][0] == 0x6a and ops[j + 3][0] == 0x2d:
                self.ks_off = ops[j][1]
        if self.ks_off is None:
            raise VsDecError('keystream offset not found in decrypt')
        self.state_locals = list(range(self.blk_nparams, self.blk_nparams + 16))

    def initial_state(self, nonce, counter=0):
        """Run the block-function prologue until each of the 16 state locals is set once."""
        mem = bytearray(self.mem0)
        mem[self.nonce_off:self.nonce_off + 12] = nonce
        locs = [counter, 64] + [None] * self.blk_nloc
        seen = set(); want = set(self.state_locals)
        # stop right after the op that sets the last state local for the first time
        idx = {'n': None}
        for k, (op, a) in enumerate(self.blk_ops):
            if op == 0x21 and a in want:
                seen.add(a)
                if seen == want:
                    idx['n'] = k + 1; break
        if idx['n'] is None:
            raise VsDecError('block prologue does not set all 16 state locals')
        run_straight(self.blk_ops[:idx['n']], locs, mem)
        st = [locs[i] for i in self.state_locals]
        if tuple(st[0:4]) != SIGMA:
            raise VsDecError('state[0:4] is not sigma: %s' % [hex(x) for x in st[0:4]])
        if st[12] != counter:
            raise VsDecError('state[12] is not the block counter')
        if struct.pack('<3I', *st[13:16]) != bytes(nonce):
            raise VsDecError('state[13:16] is not the nonce')
        return st

    def key(self):
        st = self.initial_state(bytes(12), 0)
        return struct.pack('<8I', *st[4:12])


# ------------------------------------------------------------------ ChaCha20
def _qr(x, a, b, c, d):
    x[a] = (x[a] + x[b]) & M32; x[d] ^= x[a]; x[d] = ((x[d] << 16) | (x[d] >> 16)) & M32
    x[c] = (x[c] + x[d]) & M32; x[b] ^= x[c]; x[b] = ((x[b] << 12) | (x[b] >> 20)) & M32
    x[a] = (x[a] + x[b]) & M32; x[d] ^= x[a]; x[d] = ((x[d] << 8) | (x[d] >> 24)) & M32
    x[c] = (x[c] + x[d]) & M32; x[b] ^= x[c]; x[b] = ((x[b] << 7) | (x[b] >> 25)) & M32


def chacha20_xor(key, nonce, data, counter=0):
    """RFC 8439 ChaCha20, pure Python."""
    k = struct.unpack('<8I', key); n = struct.unpack('<3I', nonce)
    out = bytearray(len(data))
    for off in range(0, len(data), 64):
        s = list(SIGMA) + list(k) + [(counter + off // 64) & M32] + list(n)
        x = s[:]
        for _ in range(10):
            _qr(x, 0, 4, 8, 12); _qr(x, 1, 5, 9, 13); _qr(x, 2, 6, 10, 14); _qr(x, 3, 7, 11, 15)
            _qr(x, 0, 5, 10, 15); _qr(x, 1, 6, 11, 12); _qr(x, 2, 7, 8, 13); _qr(x, 3, 4, 9, 14)
        ks = struct.pack('<16I', *[(x[i] + s[i]) & M32 for i in range(16)])
        chunk = data[off:off + 64]
        out[off:off + len(chunk)] = bytes(a ^ b for a, b in zip(chunk, ks))
    return bytes(out)


def decrypt_bytes(wasm, enc):
    if len(enc) < 12:
        raise VsDecError('ciphertext shorter than nonce')
    m = Module(wasm)
    return chacha20_xor(m.key(), enc[:12], enc[12:], 0)


def decrypt_stream_urls(wasm, enc_b64):
    plain = decrypt_bytes(wasm, base64.b64decode(enc_b64))
    try:
        txt = plain.decode('utf-8')
    except UnicodeDecodeError:
        raise VsDecError('plaintext is not UTF-8 (wrong key/WASM changed)')
    urls = [u for u in txt.split('\n') if u]
    if not urls or not all(u.startswith('http') for u in urls):
        raise VsDecError('plaintext is not a URL list: %r' % txt[:80])
    return urls
