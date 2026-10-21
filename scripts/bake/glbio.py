"""Minimal GLB reader/writer with numpy (enough for scan + rebuild GLBs)."""
import json, struct
import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    b = open(path, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    off = 20 + jl
    bl = struct.unpack("<I", b[off:off + 4])[0]
    binc = b[off + 8: off + 8 + bl]
    return j, binc


def accessor(j, binc, idx):
    a = j["accessors"][idx]
    bv = j["bufferViews"][a["bufferView"]]
    dt = np.dtype(CT[a["componentType"]])
    n = NC[a["type"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    cnt = a["count"]
    if stride and stride != dt.itemsize * n:
        raw = np.frombuffer(binc, dtype=np.uint8, count=stride * (cnt - 1) + dt.itemsize * n, offset=start)
        out = np.stack([np.frombuffer(raw[i * stride:i * stride + dt.itemsize * n].tobytes(), dtype=dt) for i in range(cnt)])
    else:
        out = np.frombuffer(binc, dtype=dt, count=cnt * n, offset=start).reshape(cnt, n) if n > 1 else np.frombuffer(binc, dtype=dt, count=cnt, offset=start)
    if a.get("normalized") and dt != np.float32:
        out = out.astype(np.float32) / np.iinfo(dt).max
    return np.array(out)


def image_bytes(j, binc, img_idx):
    bv = j["bufferViews"][j["images"][img_idx]["bufferView"]]
    s = bv.get("byteOffset", 0)
    return binc[s:s + bv["byteLength"]]


class Writer:
    def __init__(self):
        self.bin = bytearray()
        self.j = {"asset": {"version": "2.0", "generator": "scan-bake"}, "buffers": [], "bufferViews": [], "accessors": [],
                  "meshes": [], "nodes": [], "scenes": [], "scene": 0, "materials": [], "images": [], "textures": [], "samplers": []}

    def _view(self, data: bytes, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.bin += data
        self.j["bufferViews"].append(v)
        return len(self.j["bufferViews"]) - 1

    def add_accessor(self, arr, kind, index=False):
        arr = np.ascontiguousarray(arr)
        ct = {np.dtype(np.float32): 5126, np.dtype(np.uint32): 5125, np.dtype(np.uint16): 5123}[arr.dtype]
        v = self._view(arr.tobytes(), 34963 if index else 34962)
        a = {"bufferView": v, "componentType": ct, "count": int(arr.shape[0]), "type": kind}
        if kind == "VEC3" and not index:
            a["min"] = arr.min(0).tolist(); a["max"] = arr.max(0).tolist()
        self.j["accessors"].append(a)
        return len(self.j["accessors"]) - 1

    def add_image(self, data: bytes, mime, name):
        v = self._view(data)
        self.j["images"].append({"bufferView": v, "mimeType": mime, "name": name})
        if not self.j["samplers"]:
            self.j["samplers"].append({"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071})
        self.j["textures"].append({"sampler": 0, "source": len(self.j["images"]) - 1})
        return len(self.j["textures"]) - 1

    def save(self, path):
        while len(self.bin) % 4:
            self.bin.append(0)
        self.j["buffers"] = [{"byteLength": len(self.bin)}]
        js = json.dumps(self.j, separators=(",", ":")).encode()
        while len(js) % 4:
            js += b" "
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
            f.write(struct.pack("<II", len(self.bin), 0x004E4942)); f.write(self.bin)
