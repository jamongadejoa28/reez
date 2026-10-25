import json
import os
import subprocess
import urllib.request
from PIL import Image,ImageChops
import pytest
from conftest import ROOT

def ui(url,*args):
    p=subprocess.run([str(ROOT/'target/debug/reez-monitor'),'--url',url,*map(str,args)],env={**os.environ,'SDL_VIDEODRIVER':'dummy','REEZ_CLOCK':'12:00:00'},capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stdout+p.stderr
    return p

@pytest.mark.parametrize('page',range(1,6))
def test_exact_c_rust_pixels(page,tmp_path):
    c=tmp_path/'c.bmp';r=tmp_path/'r.bmp'
    subprocess.run([str(ROOT/'artifacts/c-reference'),str(page),str(c)],env={**os.environ,'SDL_VIDEODRIVER':'dummy'},check=True,timeout=10)
    ui('http://127.0.0.1:1','--static-ui','--frames',90,'--page',page,'--screenshot',r)
    a=Image.open(c).convert('RGB');b=Image.open(r).convert('RGB');assert a.size==b.size==(800,480)
    assert ImageChops.difference(a,b).getbbox() is None

def test_real_button_callbacks(demo):
    url,_=demo;ui(url,'--frames',1500,'--exercise-mock')
    state=json.load(urllib.request.urlopen(url+'/api/state'))
    assert state['values']['set_temp']==23.1 and state['values']['power_on']==0 and state['command_status']=='confirmed'

@pytest.mark.parametrize('page',range(1,6))
def test_application_screens(demo,tmp_path,page):
    url,_=demo;path=tmp_path/'app.bmp';ui(url,'--frames',90,'--page',page,'--screenshot',path)
    image=Image.open(path);assert image.size==(800,480);assert len(image.getcolors(800*480))>20

def test_offline_gui(demo,tmp_path):
    url,control=demo;control.write_text('{"offline":true}')
    ui(url,'--frames',90,'--screenshot',tmp_path/'offline.bmp')
    assert not json.load(urllib.request.urlopen(url+'/api/state'))['connected']

def test_stopped_only_lock(demo,tmp_path):
    url,_=demo
    request=urllib.request.Request(url+'/api/command',data=b'{"name":"power_on","value":1}',headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request) as response:assert response.status==202
    script=tmp_path/'script.json';script.write_text(json.dumps([{'frame':70,'select':'temp_calib'},{'frame':80,'click':'increase'},{'frame':90,'click':'apply'}]))
    report=tmp_path/'report.json';ui(url,'--frames',150,'--script',script,'--report',report)
    r=json.loads(report.read_text());assert r['online'];assert r['controls_disabled']['apply'];assert r['values']['temp_calib']==0

def test_offline_locks_controls(demo,tmp_path):
    url,control=demo;control.write_text('{"offline":true}')
    report=tmp_path/'report.json';ui(url,'--frames',100,'--report',report)
    r=json.loads(report.read_text());assert not r['online'];assert all(r['controls_disabled'].values())

def test_alarm_clear_and_reconnect(demo,tmp_path):
    import time
    url,control=demo;report=tmp_path/'report.json'
    proc=subprocess.Popen([str(ROOT/'target/debug/reez-monitor'),'--url',url,'--frames','400','--report',str(report)],env={**os.environ,'SDL_VIDEODRIVER':'dummy','REEZ_CLOCK':'12:00:00'},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        time.sleep(1);control.write_text('{"offline":true}');time.sleep(.8);control.write_text('{"alarm_word1":0,"alarm_word2":0}')
        _,err=proc.communicate(timeout=15);assert proc.returncode==0,err
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    r=json.loads(report.read_text());assert r['online'];assert r['history_count']>=2;assert any('발생' in s for s in r['history']) and any('해제' in s for s in r['history'])

@pytest.mark.parametrize('mode',['reject','lost_response','wrong_id','wrong_value'])
def test_command_failure_never_retries_or_claims_success(demo,tmp_path,mode):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import threading
    baseline=json.load(urllib.request.urlopen(demo[0]+'/api/state'));baseline['command_id']=0;baseline['command_status']='idle';baseline['values']['power_on']=0
    posts=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def response(self,code,body):
            data=json.dumps(body).encode();self.send_response(code);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):self.response(200,baseline)
        def do_POST(self):
            posts.append(self.rfile.read(int(self.headers['Content-Length'])))
            if mode=='reject':self.response(409,{'error':'busy'})
            elif mode=='lost_response':self.close_connection=True
            else:
                baseline['command_id']=2 if mode=='wrong_id' else 1
                baseline['command_status']='confirmed'
                self.response(202,{'command_id':1})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        script=tmp_path/'script.json';script.write_text('[{"frame":70,"click":"run"}]');report=tmp_path/'report.json'
        ui(f'http://127.0.0.1:{server.server_port}','--frames',180,'--script',script,'--report',report)
        r=json.loads(report.read_text());assert len(posts)==1;assert not r['pending'];assert '완료' not in r['notice'];assert '실패' in r['notice']
    finally:server.shutdown();server.server_close();thread.join()
