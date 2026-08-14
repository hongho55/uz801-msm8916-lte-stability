#!/usr/bin/env python3
"""Read-only MPSS core/MDT correlation; emits only bounded forensic metadata."""
from __future__ import annotations
import argparse, hashlib, json, mmap, re, struct
from pathlib import Path

EH='<16sHHIIIIIHHHHHH'; PH='<IIIIIIII'; PT_LOAD=1

def elf(path):
    data=path.read_bytes(); h=struct.unpack_from(EH,data)
    if h[0][:6] != b'\x7fELF\x01\x01': raise ValueError(f'not ELF32 LSB: {path}')
    rows=[]
    for i in range(h[10]):
        t,o,v,p,fs,ms,fl,al=struct.unpack_from(PH,data,h[5]+i*h[9])
        rows.append(dict(index=i,type=t,offset=o,vaddr=v,paddr=p,filesz=fs,memsz=ms,flags=fl,align=al))
    return dict(size=len(data),sha256=hashlib.sha256(data).hexdigest(),type=h[1],machine=h[2],entry=h[4],phnum=h[10]),rows

def locate(addr, rows, key='paddr', memory=True):
    for x in rows:
        if x['type'] != PT_LOAD: continue
        size=x['memsz'] if memory else x['filesz']
        if x[key] <= addr < x[key]+size:
            return {'index':x['index'],'delta':addr-x[key],'file_offset':x['offset']+addr-x[key],
                    'paddr':x['paddr']+addr-x[key],'vaddr':x['vaddr']+addr-x[key],
                    'file_backed':addr-x[key] < x['filesz']}

def hx(x): return None if x is None else f'0x{x:08x}'
def shown(loc):
    if not loc:return None
    return {k:(hx(v) if k in ('delta','file_offset','paddr','vaddr') else v) for k,v in loc.items()}

def all_offsets(mm, needle):
    out=[]; pos=0
    while True:
        pos=mm.find(needle,pos)
        if pos<0:return out
        out.append(pos); pos+=1

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('core',type=Path); parser.add_argument('mdt',type=Path)
    parser.add_argument('--blob-dir',type=Path,required=True); parser.add_argument('--out',type=Path,required=True); args=parser.parse_args()
    ch,cp=elf(args.core); mh,mp=elf(args.mdt); cl=[x for x in cp if x['type']==PT_LOAD]; ml=[x for x in mp if x['type']==PT_LOAD]
    comparisons=[]
    with args.core.open('rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
        for c in cl:
            m=next((x for x in ml if x['paddr']==c['paddr'] and x['memsz']==c['memsz']),None)
            blob=args.blob_dir/f"modem.b{m['index']:02d}" if m else None
            row={'core_segment':c['index'],'paddr':hx(c['paddr']),'memsz':c['memsz'],'mdt_phdr':m['index'] if m else None,
                 'firmware_blob':blob.name if blob and blob.exists() else None}
            if blob and blob.exists():
                b=blob.read_bytes(); cur=mm[c['offset']:c['offset']+min(len(b),c['filesz'])]
                diffs=sum(x!=y for x,y in zip(b,cur)); first=next((i for i,(x,y) in enumerate(zip(b,cur)) if x!=y),None)
                row.update(blob_size=len(b),compared=len(cur),equal=(len(cur)==len(b) and diffs==0),different_bytes=diffs,
                           first_difference=hx(first),blob_sha256=hashlib.sha256(b).hexdigest(),core_prefix_sha256=hashlib.sha256(cur).hexdigest())
            else: row['classification']='runtime/BSS (no file payload)' if m and not m['filesz'] else 'unmatched'
            comparisons.append(row)

        # Map crash registers in both physical core and MDT virtual address spaces.
        report_anchor=max(all_offsets(mm,b'ERR crash log report'), key=lambda o:sum(x in mm[o:o+0x10000] for x in [b'Error in file',b'Register values',b'REX_TCB ptr:']))
        text=''.join(chr(x) if 32<=x<127 else ' ' for x in mm[report_anchor:report_anchor+0x10000])
        regs={n:int(v,16) for n,v in re.findall(r'(QDSP6_[A-Z0-9_]+)\s*:\s*(0x[0-9a-f]+)',text,re.I)}
        regmaps={n:{'value':hx(v),'core_physical':shown(locate(v,cl,'paddr')),'mdt_virtual':shown(locate(v,ml,'vaddr'))} for n,v in regs.items()}

        # Bounded stack scan: retain only words resolving into MPSS virtual code/data or core physical ranges.
        stack=[]; sp=regs.get('QDSP6_SP'); sploc=locate(sp or 0,cl,'paddr',False)
        if sploc:
            off=sploc['file_offset']
            for d in range(0,0x1000,4):
                val=struct.unpack_from('<I',mm,off+d)[0]; vl=locate(val,ml,'vaddr'); pl=locate(val,cl,'paddr')
                if vl or pl: stack.append({'sp_delta':hx(d),'value':hx(val),'mdt_virtual':shown(vl),'core_physical':shown(pl)})

        # Exact, allow-listed terms only; classify static file-backed versus runtime/BSS locations.
        terms=['QuRT','qurt','SMEM','smem','ML1 GM','lte_ml1_common.c','Assert 0 failed','ERR crash log report','REX_TCB','tcb.task_name','End Dog Report','DATA ERR']
        searches={}
        for term in terms:
            hits=[]
            for off in all_offsets(mm,term.encode()):
                loc=next(({'index':x['index'],'paddr':x['paddr']+off-x['offset'],'delta':off-x['offset']} for x in cl if x['offset']<=off<x['offset']+x['filesz']),None)
                hits.append({'file_offset':hx(off),'core_segment':loc['index'] if loc else None,'paddr':hx(loc['paddr']) if loc else None})
            searches[term]={'count':len(hits),'first_hits':hits[:12]}

        # Locate static source-name instances, corresponding virtual addresses, and all pointer references.
        source=[]
        for off in all_offsets(mm,b'lte_ml1_common.c'):
            c=next((x for x in cl if x['offset']<=off<x['offset']+x['filesz']),None)
            if not c:continue
            paddr=c['paddr']+off-c['offset']; m=locate(paddr,ml,'paddr'); vaddr=m['vaddr'] if m else None
            refs=all_offsets(mm,struct.pack('<I',vaddr)) if vaddr is not None else []
            source.append({'file_offset':hx(off),'paddr':hx(paddr),'vaddr':hx(vaddr),'mdt_phdr':m['index'] if m else None,
                           'pointer_reference_count':len(refs),'pointer_reference_offsets':[hx(x) for x in refs[:12]]})

    out={'core':ch,'mdt':mh,'pt_load':{'core_count':len(cl),'mdt_count':len(ml),'core_file_bytes':sum(x['filesz'] for x in cl),
         'core_memory_bytes':sum(x['memsz'] for x in cl),'core_first_paddr':hx(min(x['paddr'] for x in cl)),
         'core_last_end':hx(max(x['paddr']+x['memsz'] for x in cl))},'segment_comparisons':comparisons,
         'register_mappings':regmaps,'stack_mapped_words_first_4k':stack,'allowlisted_searches':searches,'source_name_correlations':source}
    args.out.write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps({'out':str(args.out),'comparisons':len(comparisons),'stack_mapped_words':len(stack),'source_instances':len(source)}))
if __name__=='__main__': main()
