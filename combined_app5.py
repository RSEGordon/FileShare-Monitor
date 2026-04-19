#!/usr/bin/env python3
"""Combined System Monitor + File Share - Light Morandi Theme"""
import os, time, platform
from datetime import datetime
from flask import Flask, jsonify, render_template, send_from_directory, request, redirect, Response
import urllib.parse
import subprocess
import urllib.request
from flask_sock import Sock

app = Flask(__name__)
sock = Sock(app)
SHARE_DIR = '/home/rsegordon/桌面/OpenClawFile/FileShare'
PUBLIC_BASE = os.environ.get('PUBLIC_BASE_URL', 'https://frp-run.com:45775')
PORT = 19995
VNC_HTML = '/tmp/vnc_web/vnc.html'
VNC_STATIC = '/tmp/vnc_web'

# Load Morandi CSS at startup (avoids -- parsing issues in string literals)
with open('/tmp/morandi.css') as f:
    MORANDI_CSS = f.read()

_cpu_prev = {'total':0,'idle':0}
_proc_prev = {}
_proc_first = True
_core_prev = {}

# ── Monitor ──
def _stat():
    with open('/proc/stat') as f: l=f.readline()
    t=sum(int(x) for x in l.split()[1:]); i=int(l.split()[4]); return t,i

def get_cpu_info():
    global _cpu_prev
    try:
        model="Unknown"
        for l in open('/proc/cpuinfo'):
            if l.startswith('model name'): model=l.split(':',1)[1].strip(); break
        cores=len([l for l in open('/proc/cpuinfo') if l.startswith('processor')])
        t0,i0=_stat(); time.sleep(0.12); t1,i1=_stat()
        u=round((1-(i1-i0)/(t1-t0))*100,1) if t1>t0 else 0
        _cpu_prev={'total':t1,'idle':i1}
        return {'model':model,'cores':cores,'usage':u}
    except: return {'model':'Unknown','cores':0,'usage':0}

def get_cpu_per_core():
    global _core_prev
    try:
        cores=[]
        ct=0
        for l in open('/proc/stat'):
            if not l.startswith('cpu') or l.startswith('cpu '): continue
            f=l.split()
            t=sum(int(x) for x in f[1:])
            i=int(f[4])
            prev=_core_prev.get(f[0],{'total':t,'idle':i})
            dt=t-prev['total']
            di=i-prev['idle']
            usage=round((1-di/dt)*100,1) if dt>0 else 0
            cores.append({'name':f[0],'usage':usage})
            _core_prev[f[0]]={'total':t,'idle':i}
        return cores
    except: return []

def get_memory_info():
    try:
        m={}
        for l in open('/proc/meminfo'):
            p=l.split(); m[p[0][:-1]]=int(p[1])
        tot,avail=m.get('MemTotal',0),m.get('MemAvailable',0)
        st,sf=m.get('SwapTotal',0),m.get('SwapFree',0)
        return {'total':round(tot/1048576,2),'used':round((tot-avail)/1048576,2),
                'available':round(avail/1048576,2),'percent':round((tot-avail)/tot*100,1) if tot else 0,
                'swap_total':round(st/1048576,2),'swap_used':round((st-sf)/1048576,2)}
    except: return {'total':0,'used':0,'available':0,'percent':0}

def get_disk_info():
    try:
        import subprocess
        r=subprocess.run(['df','-h','--output=target,size,used,avail,pcent'],capture_output=True,text=True)
        disks=[]
        for l in r.stdout.strip().split('\n')[1:]:
            p=l.split()
            if len(p)>=5 and (p[0].startswith('/dev') or p[0]=='/' or '/home' in p[0] or '/data' in p[0]):
                disks.append({'mount':p[0],'size':p[1],'used':p[2],'available':p[3],'percent':int(p[4].replace('%',''))})
        return disks
    except: return []

def get_network_info():
    try:
        ifs={}
        for l in open('/proc/net/dev'):
            if ':' not in l: continue
            iface,rest=l.split(':',1); pts=rest.split()
            if len(pts)>=9: ifs[iface.strip()]={'rx':int(pts[0]),'tx':int(pts[8])}
        return ifs
    except: return {}

def get_top_processes():
    global _proc_prev,_proc_first,_cpu_prev
    try:
        nCPU = os.cpu_count() or 1
        kpid=''
        for l in open('/proc/1/status'):
            if l.startswith('Name:'): kpid=l.split()[1]; break
        ct,ci=_stat()
        procs=[]
        for pid in os.listdir('/proc'):
            if not pid.isdigit(): continue
            try:
                stat=open(f'/proc/{pid}/stat').read().split()
                name=stat[1][1:-1]
                if name==kpid: name='[kernel]'
                ut,st=int(stat[13]),int(stat[14])
                cmd=open(f'/proc/{pid}/cmdline').read().replace('\x00',' ').strip()
                procs.append({'pid':pid,'name':name[:30],'cmdline':cmd[:60],'cpu_time':ut+st})
            except: pass
        res=[]
        dt=ct-_cpu_prev['total']
        for p in procs:
            prev=_proc_prev.get(p['pid'])
            pct=min(100,round((p['cpu_time']-prev['cpu_time'])/dt/nCPU*100,1)) if (prev and not _proc_first and dt>0) else 0
            res.append({**p,'cpu_percent':pct})
            _proc_prev[p['pid']]={'cpu_time':p['cpu_time']}
        _proc_first=False; _cpu_prev={'total':ct,'idle':ci}
        res.sort(key=lambda x:x['cpu_percent'],reverse=True)
        return res[:15]
    except: return []

def get_load_avg():
    try: return [float(x) for x in open('/proc/loadavg').read().split()[:3]]
    except: return [0,0,0]

def get_uptime():
    try:
        s=float(open('/proc/uptime').read().split()[0])
        d,h,m=int(s//86400),int(s%86400//3600),int(s%3600//60)
        return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"
    except: return "Unknown"

def get_gpu_info():
    try:
        import subprocess
        r=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu'],capture_output=True,text=True,timeout=5)
        if r.returncode==0:
            parts=[p.strip() for p in r.stdout.strip().split(',')]
            if len(parts)>=5: return {'name':parts[0],'memory_total':parts[1]+' MB','memory_used':parts[2]+' MB','utilization':parts[3]+'%','temperature':parts[4]+'C','available':True}
    except: pass
    return {'available':False}

def get_openclaw_info():
    try:
        results=[]
        for line in subprocess.check_output(['ps','aux'],text=True).splitlines():
            if 'openclaw-gateway' not in line: continue
            parts=line.split()
            if len(parts)<11: continue
            pid=parts[1]
            cpu=float(parts[2])
            mem=float(parts[3])
            # identify by state dir in /proc/pid/fd
            state_dir=''
            try:
                for fd in os.listdir(f'/proc/{pid}/fd'):
                    try:
                        link=os.readlink(f'/proc/{pid}/fd/{fd}')
                        for seg in ['.openclaw-state-jim','.openclaw-state-hjkv','.openclaw']:
                            if seg in link:
                                state_dir=seg
                                break
                    except: pass
            except: pass
            if 'jim' in state_dir: name='jim'
            elif 'hjkv' in state_dir: name='hjkv'
            elif '.openclaw' in state_dir: name='main'
            else: name=f'pid:{pid}'
            results.append({'pid':pid,'name':name,'cpu':round(cpu,1),'mem':round(mem,1)})
        return results[:4]
    except: return []

@app.route('/api/status')
def api_status():
    return jsonify({'timestamp':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'hostname':platform.node(),'os':f"{platform.system()} {platform.release()}",
        'uptime':get_uptime(),'cpu':get_cpu_info(),'cpu_per_core':get_cpu_per_core(),
        'memory':get_memory_info(),'disks':get_disk_info(),'network':get_network_info(),
        'top_processes':get_top_processes(),'load_average':get_load_avg(),'gpu':get_gpu_info(),
        'openclaw':get_openclaw_info()})

# ── Shared Page Structure ──
def page_head(page):
    return '<!DOCTYPE html>\n<html lang="zh-CN"><head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>'+page+'</title>\n<style>\n'+MORANDI_CSS+'\n</style>\n</head><body>'

def page_nav(page):
    items=[('/', '📊 监控'), ('/files', '📁 共享'), ('https://clawblog.rseg.club/', '📝 博客')]
    print(f'DEBUG page_nav called with page={page}, items={items}')
    nav='<div class="nav">'
    for u,t in items:
        active=' class="active"' if u==page else ''
        nav+=f'<a href="{u}"{active}>{t}</a>'
    nav+='</div>'
    return nav

def page_foot():
    return '<div class="footer">OpenClaw · 监控+共享</div>'

def fsize(fp):
    s=os.path.getsize(fp)
    if s>=1073741824: return f"{s/1073741824:.1f} GB"
    elif s>=1048576: return f"{s/1048576:.1f} MB"
    elif s>=1024: return f"{s/1024:.0f} KB"
    else: return f"{s} B"

# ── File Share ──
def file_share_html(path, sb, od):
    if path:
        cur = os.path.join(SHARE_DIR, path)
        if not os.path.isdir(cur): return 'Not found', 404
        bc = '根目录 / ' + ' / '.join(os.path.basename(p) for p in path.split('/') if p)
        parent = f'<li class="dir"><a href="/files?path={urllib.parse.quote(os.path.dirname(path))}">📁 ..</a></li>'
    else:
        cur = SHARE_DIR; bc = '根目录'; parent = ''

    try: items = os.listdir(cur)
    except PermissionError: return 'Forbidden', 403

    dirs = [x for x in items if os.path.isdir(os.path.join(cur, x))]
    files = [x for x in items if os.path.isfile(os.path.join(cur, x))]
    rev = od == 'desc'

    def sk(x):
        p = os.path.join(cur, x)
        if sb == 'size': return os.path.getsize(p) if os.path.isfile(p) else 0
        if sb == 'date': return os.path.getmtime(p)
        return x.lower()
    dirs.sort(key=sk, reverse=rev); files.sort(key=sk, reverse=rev)

    def su(b, nd): return f'/files?path={urllib.parse.quote(path)}&sort={b}&order={nd}'
    def to(sbb): return 'desc' if (sb == sbb and od == 'asc') else 'asc'
    ia = {'name': '↑' if (sb == 'name' and od == 'asc') else '↓' if sb == 'name' else '',
          'size': '↑' if (sb == 'size' and od == 'asc') else '↓' if sb == 'size' else '',
          'date': '↑' if (sb == 'date' and od == 'asc') else '↓' if sb == 'date' else ''}

    sort_ui = f'''<div class="sort-bar">
      <span class="sort-label">排序：</span>
      <a href="{su("name", to("name"))}" class="sort-link {"active" if sb == "name" else ""}">名称 {ia["name"]}</a>
      <a href="{su("size", to("size"))}" class="sort-link {"active" if sb == "size" else ""}">大小 {ia["size"]}</a>
      <a href="{su("date", to("date"))}" class="sort-link {"active" if sb == "date" else ""}">时间 {ia["date"]}</a>
    </div>'''

    dirs_h = '\n'.join(f'<li class="dir"><a href="/files?path={urllib.parse.quote(os.path.join(path, x) if path else x)}">📁 {x}</a></li>' for x in sorted(dirs, key=sk, reverse=rev))

    files_h = ''
    for item in sorted(files, key=sk, reverse=rev):
        iup = os.path.join(path, item) if path else item
        fu = PUBLIC_BASE + '/files/download/' + iup
        enc = urllib.parse.quote(item, safe='')
        dec = urllib.parse.unquote(enc)
        dl = '/files/download/' + iup
        files_h += f'''<li class="file-item">
  <span class="file-icon">📄</span>
  <div class="file-info">
    <span class="file-name" onclick="showFilename(this, '{dec}')" title="{dec}">{item}</span>
    <span class="file-size">{fsize(os.path.join(cur, item))}</span>
  </div>
  <div class="file-actions">
    <a href="/files/download/{iup}" class="btn btn-download" download="{dec}">⬇</a>
    <button class="btn btn-share" onclick="shareFile('{fu}', '{dec}')">🔗</button>
  </div>
</li>
'''

    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>📁 文件共享</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #FAFAF8; color: #333; padding: 0; }}
.nav {{ background: #fff; border-bottom: 1px solid #E8E4E1; padding: 10px 16px; display: flex; justify-content: center; gap: 8px; position: sticky; top: 0; z-index: 100; }}
.nav a {{ color: #9B9B9B; text-decoration: none; font-size: 13px; font-weight: 500; padding: 6px 18px; border-radius: 20px; transition: all .2s; display: flex; align-items: center; gap: 6px; }}
.nav a:hover {{ background: #F0EFED; color: #4A4A4A; }}
.nav a.active {{ background: #8BA5B5; color: #fff; font-weight: 600; }}
.container {{ max-width: 900px; margin: 20px auto; background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
h1 {{ color: #222; margin-bottom: 16px; font-size: 1.5rem; }}
.breadcrumb {{ color: #999; margin-bottom: 16px; font-size: 0.9rem; }}
.breadcrumb a {{ color: #5B7E96; text-decoration: none; }}
.breadcrumb a:hover {{ text-decoration: underline; }}
.upload-form {{ background: #F0EFED; border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }}
.upload-row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
.upload-btn {{ background: #D4D0CC; color: #5a5650; padding: 8px 14px; border-radius: 6px; font-size: 0.88rem; cursor: pointer; white-space: nowrap; transition: background 0.2s; }}
.upload-btn:hover {{ background: #C8C4C0; }}
.upload-form input[type="file"] {{ display: none; }}
.upload-filelist {{ display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }}
.upload-file-item {{ display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: #666; background: rgba(255,255,255,0.6); padding: 4px 8px; border-radius: 4px; position: relative; overflow: hidden; }}
.upload-file-item .fname {{ flex: 1; overflow: hidden; text-overflow: ellipsis; }}
.upload-file-item .fremove {{ color: #aaa; cursor: pointer; flex-shrink: 0; font-size: 0.9rem; }}
.upload-file-item .fremove:hover {{ color: #888; }}
.upload-file-item .file-progress-bar {{ height: 100%; width: 0%; background: rgba(91,126,150,0.40); transition: width 0.15s; }}
.upload-file-item .file-progress-text {{ font-size: 0.72rem; color: #888; white-space: nowrap; flex-shrink: 0; }}
.upload-submit {{ background: #8BA5B5; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 0.88rem; white-space: nowrap; transition: background 0.2s; flex-shrink: 0; }}
.upload-submit:hover {{ background: #7A95A5; }}
ul {{ list-style: none }}
li {{ padding: 7px 8px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 10px; min-height: 36px; }}
li:last-child {{ border-bottom: none; }}
li:hover {{ background: #fafafa; }}
.dir {{ background: #F8F9FF; }}
.dir a {{ color: #333; text-decoration: none; font-size: 0.88rem; }}
.dir a:hover {{ color: #5B7E96; }}
.dir:hover {{ background: #F0F2FF; }}
.file-icon {{ font-size: 1.1rem; width: 24px; text-align: center; flex-shrink: 0; }}
.file-info {{ flex: 1; display: flex; align-items: center; gap: 8px; overflow: hidden; }}
.file-name {{ color: #333; font-size: 0.88rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 320px; cursor: pointer; }}
.file-name:hover {{ color: #5B7E96; }}
.filename-toast {{ display: none; position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: rgba(50,50,50,0.9); color: #fff; padding: 10px 20px; border-radius: 8px; font-size: 0.85rem; max-width: 90vw; word-break: break-all; z-index: 2000; box-shadow: 0 4px 16px rgba(0,0,0,0.2); }}
.filename-toast.show {{ display: block; }}
.file-size {{ color: #aaa; font-size: 0.75rem; white-space: nowrap; flex-shrink: 0; margin-left: auto; padding-right: 4px; }}
.sort-bar {{ display: flex; align-items: center; gap: 4px; margin-bottom: 12px; padding: 8px 0; border-bottom: 1px solid #eee; font-size: 0.8rem; }}
.sort-label {{ color: #aaa; margin-right: 4px; }}
.sort-link {{ color: #aaa; text-decoration: none; padding: 3px 8px; border-radius: 4px; }}
.sort-link:hover {{ background: #f0f0f0; color: #666; }}
.sort-link.active {{ color: #5B7E96; background: #EEF2F5; font-weight: 500; }}
.file-actions {{ display: flex; gap: 6px; flex-shrink: 0; }}
.btn {{ display: inline-flex; align-items: center; justify-content: center; padding: 4px 10px; border-radius: 6px; font-size: 0.78rem; text-decoration: none; cursor: pointer; border: none; transition: all 0.2s; flex-shrink: 0; letter-spacing: 0; }}
.btn-download {{ background: #C8D4DE; color: #5A6A7A; }}
.btn-download:hover {{ background: #B0C0D0; }}
.btn-share {{ background: #E0DCD8; color: #7A7068; }}
.btn-share:hover {{ background: #D0CCC8; }}
.modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.4); z-index: 1000; justify-content: center; align-items: center; }}
.modal.show {{ display: flex; }}
.modal-content {{ background: #fff; border-radius: 12px; padding: 24px; max-width: 480px; width: 90%; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }}
.modal-title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 12px; color: #222; }}
.modal-filename {{ font-size: 0.85rem; color: #666; word-break: break-all; margin-bottom: 12px; }}
.modal-url-box {{ display: flex; gap: 8px; }}
.modal-url {{ flex: 1; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 0.85rem; color: #333; background: #f9f9f9; word-break: break-all; }}
.modal-copy {{ background: #5B7E96; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 0.85rem; white-space: nowrap; }}
.modal-copy:hover {{ background: #4A6E86; }}
.modal-copy.copied {{ background: #6A9B6A; }}
.modal-close {{ background: #f0f0f0; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 0.85rem; }}
.modal-close:hover {{ background: #e0e0e0; }}
</style>
</head>
<body>
{{nav}}
<div class="container">
  <h1>📁 文件共享</h1>
  <div class="breadcrumb">{bc}</div>
  {sort_ui}
  <form method="post" enctype="multipart/form-data" id="uploadForm" class="upload-form" onsubmit="submitUpload(event)">
    <input type="hidden" name="path" value="{path}">
    <div class="upload-row">
      <label class="upload-btn" for="fileInput">📤 上传文件</label>
      <input type="file" id="fileInput" multiple onchange="showSelectedFile(this)">
      <input type="submit" value="上传" class="upload-submit">
    </div>
    <div class="upload-filelist" id="uploadFilelist"></div>
  </form>
  <ul>
    {parent}
    {dirs_h}
    {files_h}
  </ul>
</div>

<div id="filenameToast" class="filename-toast"></div>

<div class="modal" id="shareModal">
  <div class="modal-content">
    <div class="modal-title">🔗 分享链接</div>
    <div class="modal-filename" id="modalFilename"></div>
    <div class="modal-url-box">
      <input type="text" class="modal-url" id="modalUrl" readonly>
      <button class="modal-copy" id="copyBtn" onclick="copyUrl()">复制</button>
    </div>
    <br>
    <div style="text-align:right">
      <button class="modal-close" onclick="closeModal()">关闭</button>
    </div>
  </div>
</div>

<script>
let uploadFileList=[];
function uidFor(f){{if(!f._uid)f._uid=Date.now()+'.'+Math.random();return f._uid}}
function showSelectedFile(el){{if(!el.files||!el.files.length)return;var ek={{}};for(var i=0;i<uploadFileList.length;i++)ek[uploadFileList[i].name+'|'+uploadFileList[i].size]=true;for(var i=0;i<el.files.length;i++){{var f=el.files[i];var key=f.name+'|'+f.size;if(!ek[key]){{uidFor(f);f.uploading=false;uploadFileList.push(f);ek[key]=true;appendFileItem(f)}}}}el.value=''}}
function appendFileItem(f){{var list=document.getElementById('uploadFilelist');if(!list)return;var item=document.createElement('div');item.className='upload-file-item';item.id='file-item-'+f._uid;var progBar=document.createElement('div');progBar.className='file-progress-bar';progBar.id='file-progress-'+f._uid;progBar.style.cssText='position:absolute;left:0;top:0;bottom:0;width:0%;background:rgba(91,126,150,0.40);transition:width 0.15s;';var span=document.createElement('span');span.className='fremove';span.textContent=String.fromCharCode(10005);span.style.cssText='cursor:pointer;color:#aaa;flex-shrink:0;position:relative;z-index:2;line-height:1;';span.dataset.uid=f._uid;span.onclick=(function(uid){{return function(){{removeFile(uid)}}}})(f._uid);var nameSpan=document.createElement('span');nameSpan.className='fname';nameSpan.textContent=f.name;nameSpan.title=f.name;nameSpan.style.cssText='flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;position:relative;z-index:2;';var progText=document.createElement('span');progText.className='file-progress-text';progText.id='file-progress-text-'+f._uid;progText.style.cssText='font-size:0.72rem;color:#888;white-space:nowrap;flex-shrink:0;';item.appendChild(progBar);item.appendChild(span);item.appendChild(nameSpan);item.appendChild(progText);list.appendChild(item)}}
function renderFileList(){{var list=document.getElementById('uploadFilelist');if(!list)return;list.innerHTML='';for(var i=0;i<uploadFileList.length;i++)appendFileItem(uploadFileList[i])}}
function removeFile(uid){{var nl=[];for(var i=0;i<uploadFileList.length;i++)if(String(uploadFileList[i]._uid)!==String(uid))nl.push(uploadFileList[i]);uploadFileList=nl;renderFileList()}}
function setFileProgress(uid,pct,status){{var bar=document.getElementById('file-progress-'+uid);var text=document.getElementById('file-progress-text-'+uid);if(bar)bar.style.width=pct+'%';if(text)text.textContent=status}}
function submitUpload(e){{e.preventDefault();if(!uploadFileList.length){{alert('请先选择文件');return}}var toUpload=uploadFileList.filter(function(f){{return !f.uploading&&!f.done}});if(!toUpload.length){{alert('文件正在上传中，请稍候');return}}var pathInput=document.querySelector('#uploadForm input[name="path"]');var path=pathInput?pathInput.value:'';toUpload.forEach(function(f){{f.uploading=true;var xhr=new XMLHttpRequest();var formData=new FormData();formData.append('file',f);xhr.upload.onprogress=function(evt){{if(evt.lengthComputable){{var pct=Math.round((evt.loaded/evt.total)*100);setFileProgress(f._uid,pct,pct+'%')}}}};xhr.onload=function(){{f.uploading=false;if(xhr.status===200||xhr.status===302){{f.done=true;setFileProgress(f._uid,100,'OK')}}else{{setFileProgress(f._uid,0,'ERR')}}}};xhr.onerror=function(){{f.uploading=false;setFileProgress(f._uid,0,'ERR')}};setFileProgress(f._uid,0,'0%');xhr.open('POST','/files/upload?path='+encodeURIComponent(path),true);xhr.send(formData)}})}}
function shareFile(url,filename){{var modal=document.getElementById('shareModal');document.getElementById('modalUrl').value=url;document.getElementById('modalFilename').textContent=filename;document.getElementById('copyBtn').textContent='复制';document.getElementById('copyBtn').classList.remove('copied');modal.classList.add('show');document.getElementById('modalUrl').select()}}
function copyUrl(){{var url=document.getElementById('modalUrl').value;if(navigator.clipboard&&navigator.clipboard.writeText){{navigator.clipboard.writeText(url).then(function(){{var btn=document.getElementById('copyBtn');btn.textContent='已复制';btn.classList.add('copied')}}).catch(function(){{}})}}document.getElementById('modalUrl').select();try{{document.execCommand('copy')}}catch(e){{}}}}
function closeModal(){{document.getElementById('shareModal').classList.remove('show')}}
var filenameToastTimer=null;function showFilename(el,name){{var toast=document.getElementById('filenameToast');toast.textContent=name;toast.classList.add('show');if(filenameToastTimer)clearTimeout(filenameToastTimer);filenameToastTimer=setTimeout(function(){{toast.classList.remove('show')}},2500)}}
document.getElementById('shareModal').addEventListener('click',function(e){{if(e.target===this)closeModal()}});document.addEventListener('keydown',function(e){{if(e.key==='Escape')closeModal()}});
</script>
</body>
</html>'''

    return html, 200


# ── Routes ──
@app.route('/')
def index(): return render_template('index.html')

@app.route('/debug_nav')
def debug_nav():
    return page_nav('/files')

@app.route('/files')
def files_page():
    path=request.args.get('path','')
    sb=request.args.get('sort','name')
    od=request.args.get('order','asc')
    body,st=file_share_html(path,sb,od)
    print(f'DEBUG files_page: body has {{nav}}={("{nav}" in body)}, body[300:350]={repr(body[300:350])}')
    body = body.replace('{nav}', page_nav('/files'))
    print(f'DEBUG after replace: body has nav={"class=\"nav\"" in body}')
    return body, st

@app.route('/files/upload',methods=['POST'])
def files_upload():
    up=request.form.get('path','')
    td=os.path.join(SHARE_DIR,up) if up else SHARE_DIR
    os.makedirs(td,exist_ok=True)
    uploaded=[]
    for fname in request.files:
        f=request.files[fname]
        if f.filename:
            fp=os.path.join(td,os.path.basename(f.filename))
            f.save(fp); uploaded.append(f.filename)
    nxt='/files'+(f'?path={urllib.parse.quote(up)}' if up else '')
    return redirect(nxt)

@app.route('/files/download/<path:filename>')
def files_dl(filename):
    dec=urllib.parse.unquote(filename)
    rp=os.path.realpath(os.path.join(SHARE_DIR,dec))
    if not rp.startswith(os.path.realpath(SHARE_DIR)): return 'Not found',404
    if not os.path.isfile(rp): return 'Not found',404
    return send_from_directory(SHARE_DIR,dec,as_attachment=True)

@app.route('/css/morandi')
def css_morandi():
    with open('/tmp/morandi.css') as f:
        return f.read(), 200, {'Content-Type':'text/css'}

@app.route('/api/weather')
def api_weather():
    try:
        import urllib.request, json
        url = "https://wttr.in/Weihai?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent":"curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read())
        cc = d["current_condition"][0]
        w = d["weather"][0]
        uv = int(cc.get("uvIndex","0"))
        uv_text = "无" if uv==0 else "弱" if uv<=3 else "中等" if uv<=5 else "强"
        return {"temp":cc["temp_C"],"feels":cc["FeelsLikeC"],
                "humidity":cc["humidity"],"wind":cc["windspeedKmph"],
                "uv":uv_text,"desc":"晴" if cc["cloudcover"]=="0" else "多云",
                "mintemp":w["mintempC"],"maxtemp":w["maxtempC"],
                "sunrise":w["astronomy"][0]["sunrise"],"sunset":w["astronomy"][0]["sunset"]}
    except: return {"temp":"--","desc":"--"}



if __name__=='__main__':
    print(f"Combined server on http://0.0.0.0:{PORT}")
    app.run(host='0.0.0.0',port=PORT,debug=False)
