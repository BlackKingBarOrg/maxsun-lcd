"""Disassemble the N9H26 panel firmware (ARM mode, image at 0 after a 16-byte header).

Usage: arm_dis.py <firmware.bin> <start_hex> <end_hex>
"""
import glob,struct,sys,capstone
fw=sys.argv[1]
img=open(fw,'rb').read()[16:]
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_ARM); md.detail=True; md.skipdata=True
def cstr(a):
    if not (0<=a<len(img)): return None
    e=img.find(b"\0",a); s=img[a:e]
    if 3<=len(s)<80 and all(32<=c<127 for c in s): return repr(s.decode())
    return None
def dis(start,end):
    for ins in md.disasm(img[start:end],start):
        note=''
        if ins.mnemonic.startswith('ldr') and ins.op_str.count('[pc, #')==1 and ins.op_str.endswith(']'):
            off=int(ins.op_str.split('#')[-1].rstrip(']'),0)
            la=ins.address+8+off
            if 0<=la<len(img)-4:
                v=struct.unpack_from('<I',img,la)[0]; s=cstr(v)
                note=f"=0x{v:x}"+(f" {s}" if s else '')
        elif ins.mnemonic in('add','adr') and ', pc, #' in ins.op_str:
            off=int(ins.op_str.split('#')[-1],0); a=ins.address+8+off; s=cstr(a)
            note=f"->0x{a:x}"+(f" {s}" if s else '')
        elif ins.mnemonic=='sub' and ', pc, #' in ins.op_str:
            off=int(ins.op_str.split('#')[-1],0); a=ins.address+8-off; s=cstr(a)
            note=f"->0x{a:x}"+(f" {s}" if s else '')
        print(f"  {ins.address:05x}: {ins.mnemonic:8} {ins.op_str}"+(f"   ; {note}" if note else ''))
a=int(sys.argv[2],16); b=int(sys.argv[3],16); dis(a,b)
