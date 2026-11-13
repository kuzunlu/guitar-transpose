"""Small WAV reader and writer. PCM 16/24/32 bit and 32-bit float. NumPy only."""
import struct

import numpy as np


def read_wav(path):
    """Return (samples as float64 array of shape (frames, channels), sample_rate)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos = 12
    fmt = None
    while pos + 8 <= len(data):
        cid = data[pos: pos + 4]
        size = struct.unpack("<I", data[pos + 4: pos + 8])[0]
        body = data[pos + 8: pos + 8 + size]
        if cid == b"fmt ":
            tag, ch, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE and size >= 26:              # extensible: real tag is further in
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, ch, rate, bits)
        elif cid == b"data":
            if fmt is None:
                raise ValueError("data before fmt")
            tag, ch, rate, bits = fmt
            if tag == 3 and bits == 32:
                x = np.frombuffer(body, dtype="<f4").astype(np.float64)
            elif tag == 1 and bits == 16:
                x = np.frombuffer(body, dtype="<i2").astype(np.float64) / 32768.0
            elif tag == 1 and bits == 24:
                b = np.frombuffer(body[: len(body) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
                v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
                x = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float64) / 8388608.0
            elif tag == 1 and bits == 32:
                x = np.frombuffer(body, dtype="<i4").astype(np.float64) / 2147483648.0
            else:
                raise ValueError(f"unsupported WAV format: tag {tag}, {bits} bit")
            return x[: len(x) // ch * ch].reshape(-1, ch), rate
        pos += 8 + size + (size & 1)
    raise ValueError("no data chunk")


def write_wav(path, x, rate):
    """Write a float array of shape (frames,) or (frames, channels) as 24-bit PCM."""
    x = np.atleast_2d(x.T).T if x.ndim == 1 else x
    v = np.clip(np.round(x * 8388607.0), -8388608, 8388607).astype(np.int32).reshape(-1)
    raw = np.empty((len(v), 3), dtype=np.uint8)
    raw[:, 0] = v & 0xFF
    raw[:, 1] = (v >> 8) & 0xFF
    raw[:, 2] = (v >> 16) & 0xFF
    body = raw.tobytes()
    ch = x.shape[1]
    header = b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVE" \
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, ch, int(rate), int(rate) * ch * 3, ch * 3, 24) \
        + b"data" + struct.pack("<I", len(body))
    with open(path, "wb") as f:
        f.write(header + body)
