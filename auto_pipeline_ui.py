"""Launch and poll one durable upload pipeline without blocking Streamlit."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
import html
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import streamlit as st


def _read_json(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else None
    except (OSError,ValueError):
        return None


def _write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def _process_alive(pid):
    """Read process liveness only. Never signal or terminate a saved PID."""
    if not isinstance(pid,int) or isinstance(pid,bool) or pid<=0:return False
    if os.name=='nt':
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return False
        try:
            code=wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
        finally:kernel.CloseHandle(handle)
    try:
        os.kill(pid,0)
        return True
    except (OSError,ProcessLookupError):return False


def worker_record(job_id,root):
    from panorama_pipeline import job_dir
    return _read_json(job_dir(job_id,root=root)/'ui_worker.json')


def worker_is_running(job_id,root,status=None):
    record=worker_record(job_id,root)
    if record and record.get('job_id')==job_id and _process_alive(record.get('pid')):
        return True
    status=status or {}
    return _process_alive(status.get('worker_pid'))


def save_uploaded_input(raw,title,root):
    from panorama_pipeline import job_id_for,job_dir
    root=Path(root).resolve();job_id=job_id_for(raw)
    folder=job_dir(job_id,root=root);folder.mkdir(parents=True,exist_ok=True)
    target=folder/'uploaded_input.bin'
    if target.is_file():
        if hashlib.sha256(target.read_bytes()).hexdigest()!=hashlib.sha256(raw).hexdigest():
            raise ValueError('已保存的上传图片与当前任务不一致。')
    else:
        temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
        temporary.write_bytes(raw);temporary.replace(target)
    request=folder/'ui_request.json'
    if not request.exists():
        _write_json(request,{'job_id':job_id,'input_sha256':hashlib.sha256(raw).hexdigest(),
            'input_file':str(target),'title':str(title)[:160],
            'created_utc':datetime.now(timezone.utc).isoformat()})
    return job_id,target


def _saved_upload_request(job_id,root):
    """Read metadata only from a direct, real job directory in this workspace."""
    if not isinstance(job_id,str) or len(job_id)!=64 or any(c not in '0123456789abcdef' for c in job_id):
        return None
    workspace=Path(root).resolve();base=(workspace/'outputs'/'auto_panorama').resolve()
    if not base.is_relative_to(workspace):return None
    candidate=base/job_id;folder=candidate.resolve()
    if folder!=candidate or not folder.is_dir():return None
    request_path=folder/'ui_request.json'
    if request_path.resolve().parent!=folder:return None
    request=_read_json(request_path)
    if not request or request.get('job_id')!=job_id or request.get('input_sha256')!=job_id:return None
    filename=request.get('input_file')
    if not isinstance(filename,str) or not filename:return None
    source=Path(filename)
    if not source.is_absolute():source=folder/source
    # Reject paths outside the job before resolving or reading their contents.
    if source.parent!=folder:return None
    source=source.resolve()
    if source.parent!=folder or not source.is_file() or not 0<source.stat().st_size<=45_000_000:return None
    status_path=folder/'status.json'
    status=_read_json(status_path) if status_path.resolve().parent==folder else None
    modified=max(request_path.stat().st_mtime,status_path.stat().st_mtime if status_path.is_file() and status_path.resolve().parent==folder else 0)
    return {'job_id':job_id,'input_file':str(source),'title':str(request.get('title') or '我的全景图')[:160],
            'status':(status or {}).get('status','pending'),'modified':modified}


def recent_upload_requests(root,limit=5):
    """List up to five saved uploads; listing never reads image bytes or starts work."""
    workspace=Path(root).resolve();base=(workspace/'outputs'/'auto_panorama').resolve()
    if not base.is_relative_to(workspace) or not base.is_dir():return []
    result=[]
    for folder in base.iterdir():
        try:
            item=_saved_upload_request(folder.name,workspace)
            if item:result.append(item)
        except (OSError,ValueError):continue
    return sorted(result,key=lambda item:item['modified'],reverse=True)[:max(1,min(int(limit),5))]


def load_saved_upload(job_id,root):
    """Read the selected saved file only after containment and exact SHA checks."""
    from panorama_pipeline import job_id_for
    request=_saved_upload_request(job_id,root)
    if request is None:raise ValueError('这条任务没有可安全读取的本机上传文件。')
    raw=Path(request['input_file']).read_bytes()
    if job_id_for(raw)!=job_id:raise ValueError('已保存图片与任务指纹不一致，请重新上传原图。')
    return {**request,'raw':raw}


def render_recent_auto_upload(root):
    """Recover a task after a browser refresh has cleared the upload widget."""
    items=recent_upload_requests(root)
    if not items:
        st.caption('最近还没有可恢复的本机全景任务。')
        return None
    by_id={item['job_id']:item for item in items}
    labels={'pending':'待开始','running':'处理中','complete':'已完成','failed':'需重试','cancelled':'已停止'}
    st.caption('也可以找回最近的本机任务，无需重新上传；仍会核对原始图片与完整结果。')
    selected=st.selectbox('继续查看最近的全景任务',list(by_id),index=None,
        placeholder='选择一条本机任务',format_func=lambda job:by_id[job]['title']+' · '+labels.get(by_id[job]['status'],'待查看'),
        key='recent_auto_upload_job')
    if selected is None:return None
    try:
        saved=load_saved_upload(selected,root)
        return render_auto_upload(saved['raw'],saved['title'],root)
    except (OSError,ValueError,RuntimeError) as exc:
        st.error('这条本机任务暂时无法恢复。已有文件会保留，可重新上传原图。')
        with st.expander('查看恢复信息'):st.code(f'{type(exc).__name__}: {exc}',language=None)
        return None


@contextmanager
def _launch_lock(folder):
    lock=Path(folder)/'.ui_launch.lock'
    try:
        descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        # A launch operation only writes one Popen and registry. A process
        # crash may leave this small lock, so recover only an old dead owner.
        previous=_read_json(lock)
        if (previous and _process_alive(previous.get('pid'))) or time.time()-lock.stat().st_mtime<30:
            yield False;return
        lock.unlink(missing_ok=True)
        try:descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:yield False;return
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as output:
            json.dump({'pid':os.getpid(),'created':time.time()},output)
        yield True
    finally:lock.unlink(missing_ok=True)


def launch_pipeline_worker(raw,title,root,retry=False):
    """Start at most one hidden worker; filenames never enter a shell string."""
    from panorama_pipeline import load_job,job_dir,clear_cancellation
    root=Path(root).resolve();job_id,input_file=save_uploaded_input(raw,title,root)
    folder=job_dir(job_id,root=root)
    with _launch_lock(folder) as owned:
        if not owned:return {'job_id':job_id,'started':False,'reason':'launch_in_progress'}
        status=load_job(job_id,root=root) or {}
        if status.get('status')=='complete' and not retry:return {'job_id':job_id,'started':False,'reason':'complete'}
        if worker_is_running(job_id,root,status):return {'job_id':job_id,'started':False,'reason':'running'}
        previous=worker_record(job_id,root)
        if previous and not retry:return {'job_id':job_id,'started':False,'reason':'interrupted'}
        if status.get('status') in {'failed','cancelled'} and not retry:
            return {'job_id':job_id,'started':False,'reason':status['status']}
        if retry:clear_cancellation(job_id,root=root)
        python=root/'.venv'/'Scripts'/'python.exe';script=root/'panorama_pipeline.py'
        if not python.is_file() or not script.is_file():raise RuntimeError('自动生成环境尚未就绪。')
        command=[str(python),str(script),'--input',str(input_file),'--title',str(title)[:160],'--root',str(root)]
        environment=os.environ.copy();environment['PYTHONIOENCODING']='utf-8';environment['PYTHONUNBUFFERED']='1'
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0x08000000) if os.name=='nt' else 0
        with (folder/'ui_worker.log').open('a',encoding='utf-8') as log:
            process=subprocess.Popen(command,cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                env=environment,creationflags=flags,shell=False)
        _write_json(folder/'ui_worker.json',{'job_id':job_id,'pid':process.pid,
            'worker_script':str(script),'input_file':str(input_file),'command':command,
            'started_utc':datetime.now(timezone.utc).isoformat(),'hidden_console':os.name=='nt'})
        return {'job_id':job_id,'started':True,'pid':process.pid}


def _show_steps(status):
    steps=status.get('steps',[])
    completed=sum(item.get('status') in {'complete','cached'} for item in steps)
    message=status.get('message') or '正在准备自动生成…'
    if status.get('status')=='failed':
        message='本次生成暂未完成，已完成的步骤已保留。'
    elif status.get('status')=='cancelled':
        message='本次生成已停止，已完成的步骤已保留。'
    st.progress(completed/max(len(steps),5),text=message)
    symbols={'complete':'✓','cached':'✓','running':'●','pending':'○','failed':'!','cancelled':'－'}
    names={'complete':'已完成','cached':'已完成 · 已保留','running':'正在处理','pending':'稍后开始','failed':'可以继续重试','cancelled':'已停止'}
    cards=[]
    for step in steps:
        kind=step.get('status','pending')
        cards.append('<li data-state="'+html.escape(kind)+'"><strong>'+symbols.get(kind,'○')+' '+
            html.escape(str(step.get('label',step.get('id',''))))+'</strong>'+names.get(kind,'稍后开始')+'</li>')
    st.markdown('<ol class="ls-pipeline" aria-label="自动生成进度">'+''.join(cards)+'</ol>',unsafe_allow_html=True)


@st.fragment(run_every='2s')
def _pipeline_progress(job_id,root,raw,title):
    from panorama_pipeline import load_job,load_pipeline_result,request_cancel
    status=load_job(job_id,root=root) or {'status':'pending','message':'正在启动自动生成…','steps':[]}
    _show_steps(status)
    kind=status.get('status')
    if kind=='complete':
        if load_pipeline_result(job_id,root=root,verify=True):
            st.success('GPT理解、专属声景和自然配音已完成。')
            st.rerun(scope='app')
        elif worker_is_running(job_id,root,status):
            st.caption('正在重新核验与恢复这张全景的完整结果…')
        else:
            st.warning('本图缓存未通过完整校验，可保留有效步骤并重新生成缺失内容。')
            if st.button('重新核验并继续生成',key='repair_auto_'+job_id):
                launch_pipeline_worker(raw,title,root,retry=True)
                st.rerun(scope='app')
    elif kind in {'failed','cancelled'} or (worker_record(job_id,root) and not worker_is_running(job_id,root,status)):
        st.warning('本次自动生成已停止，已完成的步骤会保留。可继续重试。')
        error_text=str(status.get('error','')).lower()
        if any(term in error_text for term in ('ram available','system ram','memory deferred','system memory')):
            st.caption('电脑当前可用内存有些紧张。稍后点击继续即可，图片理解和已完成内容不需要重做。')
        if st.button('继续自动生成',key='retry_auto_'+job_id):
            launch_pipeline_worker(raw,title,root,retry=True)
            st.rerun(scope='app')
        detail=status.get('error')
        if detail:
            with st.expander('查看本次信息'):st.code(str(detail),language=None)
    else:
        st.caption('可以继续查看进度。刷新页面不会重复启动同一张图的任务。')
        if st.button('停止本次生成',key='cancel_auto_'+job_id):
            request_cancel(job_id,root=root)
            st.info('已请求停止，当前步骤结束后会保留结果并停止后续步骤。')


def render_auto_upload(raw,title,root):
    """Return only a fully verified completed result, otherwise show progress."""
    from panorama_pipeline import load_job,load_pipeline_result
    job_id,_=save_uploaded_input(raw,title,root)
    status=load_job(job_id,root=root)
    if status and status.get('status')=='complete':
        result=load_pipeline_result(job_id,root=root,verify=True)
        if not result:
            st.error('已保存的完整结果没有通过校验，暂不加载试听。')
            _pipeline_progress(job_id,root,raw,title)
            return None
        st.success('这张全景已自动完成GPT理解、专属声景与自然配音。')
        st.caption('已加载本图完整结果。重新打开同一张图片时会核验缓存，不重新发送到GPT。')
        return result
    launch_pipeline_worker(raw,title,root)
    _pipeline_progress(job_id,root,raw,title)
    return None
