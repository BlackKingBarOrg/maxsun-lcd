"""Static analysis helper for MAXSUN_View.exe (x86-64 PE).

Usage: pe_re.py <exe> imports|callers|strref|imm|dump|xref <args...>
Function bounds come from .pdata; string and IAT references are annotated."""
import bisect
import struct
import sys

import capstone
import pefile

PATH = sys.argv[1]
pe = pefile.PE(PATH)
BASE = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()

# --- imports: IAT VA -> "dll!name"
iat = {}
for e in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in e.imports:
        name = imp.name.decode() if imp.name else f"ord{imp.ordinal}"
        iat[imp.address] = f"{e.dll.decode()}!{name}"

# --- functions from .pdata (RUNTIME_FUNCTION entries)
funcs = []
for rf in getattr(pe, "DIRECTORY_ENTRY_EXCEPTION", []):
    funcs.append((BASE + rf.struct.BeginAddress, BASE + rf.struct.EndAddress))
funcs.sort()
starts = [f[0] for f in funcs]


def func_of(va):
    i = bisect.bisect_right(starts, va) - 1
    if i >= 0 and funcs[i][0] <= va < funcs[i][1]:
        return funcs[i]
    return None


text = next(s for s in pe.sections if s.Name.startswith(b".text"))
TEXT_VA = BASE + text.VirtualAddress
TEXT = img[text.VirtualAddress: text.VirtualAddress + text.Misc_VirtualSize]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


# jmp [rip+d] thunks into the IAT
thunks = {}
for _i in range(len(TEXT) - 6):
    if TEXT[_i] == 0xFF and TEXT[_i + 1] == 0x25:
        _t = TEXT_VA + _i + 6 + struct.unpack_from("<i", TEXT, _i + 2)[0]
        if _t in iat:
            thunks[TEXT_VA + _i] = iat[_t]


def read_str(va, maxlen=200):
    rva = va - BASE
    if not (0 <= rva < len(img)):
        return None
    b = img[rva: rva + maxlen]
    # ascii
    end = b.find(b"\0")
    if end >= 4 and all(32 <= c < 127 or c in (9, 10, 13) for c in b[:end]):
        return repr(b[:end].decode())
    # utf-16le
    try:
        end = 0
        while end + 1 < len(b) and (b[end] or b[end + 1]):
            end += 2
        if end >= 8:
            s = b[:end].decode("utf-16le")
            if all(c.isprintable() for c in s):
                return "u" + repr(s)
    except Exception:
        pass
    return None


def insns(start, end):
    off = start - TEXT_VA
    return md.disasm(TEXT[off: off + (end - start)], start)


def rip_target(ins):
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def annotate(ins):
    note = ""
    t = rip_target(ins)
    if t is not None:
        if t in iat:
            note = iat[t]
        else:
            s = read_str(t)
            if s:
                note = s
    elif ins.mnemonic == "call" and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
        tgt = ins.operands[0].imm
        f = func_of(tgt)
        note = thunks.get(tgt) or (f"sub_{tgt:x}" if f else "")
    return note


def dump(start, end, out=sys.stdout):
    for ins in insns(start, end):
        n = annotate(ins)
        print(f"  {ins.address:x}: {ins.mnemonic:6} {ins.op_str}" + (f"   ; {n}" if n else ""), file=out)


def scan():
    """Yield (ins) over whole .text, function by function (pdata-driven)."""
    for s, e in funcs:
        if TEXT_VA <= s < TEXT_VA + len(TEXT):
            yield from insns(s, e)


if __name__ == "__main__":
    cmd = sys.argv[2]
    if cmd == "imports":
        for a, n in sorted(iat.items(), key=lambda x: x[1]):
            if any(k in n.lower() for k in sys.argv[3:]):
                print(f"{a:x} {n}")
    elif cmd == "callers":  # callers of IAT names containing substr
        wanted = {a: n for a, n in iat.items() if any(k in n for k in sys.argv[3:])}
        for ins in scan():
            t = rip_target(ins)
            if t in wanted and ins.mnemonic in ("call", "mov", "lea", "jmp"):
                f = func_of(ins.address)
                print(f"{ins.address:x} in sub_{f[0]:x} ({f[1]-f[0]}B): {ins.mnemonic} {wanted[t]}")
    elif cmd == "strref":  # functions referencing strings containing substr
        subs = sys.argv[3:]
        for ins in scan():
            t = rip_target(ins)
            if t is None or t in iat:
                continue
            s = read_str(t)
            if s and any(k in s for k in subs):
                f = func_of(ins.address)
                print(f"{ins.address:x} in sub_{f[0]:x}: {s}")
    elif cmd == "imm":  # instructions with immediate == value
        vals = {int(v, 0) for v in sys.argv[3:]}
        for ins in scan():
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_IMM and op.imm in vals:
                    f = func_of(ins.address)
                    print(f"{ins.address:x} in sub_{f[0]:x}: {ins.mnemonic} {ins.op_str}")
    elif cmd == "dump":
        for a in sys.argv[3:]:
            va = int(a, 16)
            f = func_of(va)
            print(f"== sub_{f[0]:x} .. {f[1]:x} ({f[1]-f[0]} bytes)")
            dump(*f)
    elif cmd == "xref":  # direct calls to given function addrs
        tg = {int(a, 16) for a in sys.argv[3:]}
        for ins in scan():
            if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM and ins.operands[0].imm in tg:
                f = func_of(ins.address)
                print(f"{ins.address:x} in sub_{f[0]:x} -> {ins.operands[0].imm:x}")
            else:
                t = rip_target(ins)
                if t in tg:
                    f = func_of(ins.address)
                    print(f"{ins.address:x} in sub_{f[0]:x} refs {t:x} ({ins.mnemonic})")
