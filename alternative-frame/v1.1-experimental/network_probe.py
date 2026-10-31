"""Two-host HTTP round-trip measurement; NOT an Agent routing benchmark."""
import argparse,json,statistics,time,urllib.request
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/ping':
            self.send_error(404);return
        blob=b'pong';self.send_response(200);self.send_header('Content-Length',str(len(blob)));self.end_headers();self.wfile.write(blob)
    def log_message(self,*args):pass

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('serve');s.add_argument('--host',default='0.0.0.0');s.add_argument('--port',type=int,default=8765)
    c=sub.add_parser('probe');c.add_argument('--url',required=True);c.add_argument('--count',type=int,default=50);c.add_argument('--output',default='network_rtt.json');c.add_argument('--timeout',type=float,default=3)
    args=p.parse_args()
    if args.command=='serve':
        print(f'HTTP probe on {args.host}:{args.port}',flush=True);ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
    else:
        url=args.url.rstrip('/')+'/ping';samples=[];errors=[]
        for i in range(args.count):
            t=time.perf_counter()
            try:
                with urllib.request.urlopen(url,timeout=args.timeout) as r:
                    body=r.read()
                    if r.status!=200 or body!=b'pong':raise ValueError('unexpected response')
                samples.append(round((time.perf_counter()-t)*1000,3))
            except Exception as ex:errors.append({'sample':i,'error':str(ex)})
        data={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'url':url,'requested':args.count,'success':len(samples),'failed':len(errors),'unit':'ms','measurement':'HTTP round-trip, not Agent end-to-end latency','samples_ms':samples,'errors':errors}
        if samples:
            sorted_s=sorted(samples);data.update({'median_ms':statistics.median(samples),'mean_ms':statistics.mean(samples),'p95_ms':sorted_s[min(len(sorted_s)-1,int(0.95*(len(sorted_s)-1)))],'max_ms':max(samples)})
        with open(args.output,'w',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
        print(json.dumps({k:v for k,v in data.items() if k not in ('samples_ms','errors')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
