"""USB camera / recorded-session runner for the frozen V4 deployment candidate."""
from pathlib import Path
import argparse
from datetime import datetime,timezone
from collections import defaultdict
from array import array
import hashlib
import json
import time
import sys
VISION=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(VISION))
import cv2
import numpy as np
from yardspi.backends import OnnxBackend,HailoBackend
from yardspi.pipeline import Pipeline

ROOT=VISION


def summary_latency(samples):
    return {k:dict(median=float(np.median(v)),p95=float(np.percentile(v,95))) for k,v in samples.items()}


def draw(frame,row,masks,defect_x):
    view=frame.copy();x,y,w,h=row['roi_xywh'];region=view[y:y+h,x:x+w]
    palette={'red':(0,0,255),'green':(0,230,0),'blue':(255,110,40),'unknown':(160,160,160)}
    for o,mask in zip(row['observations'],masks):
        color=palette[o['color']];selected=mask.astype(bool)
        region[selected]=(region[selected]*.65+np.asarray(color)*.35).astype(np.uint8)
        a,b,c,d=map(round,o['xyxy_roi'])
        cv2.rectangle(view,(x+a,y+b),(x+c,y+d),color,1)
        cv2.putText(view,f'T{o["track_id"]} {o["color"]}',(x+a,max(15,y+b-3)),0,.45,color,1,cv2.LINE_AA)
    cv2.rectangle(view,(x,y),(x+w,y+h),(0,230,255),2)
    dx=round(x+w*defect_x);cv2.line(view,(dx,y),(dx,y+h),(255,80,230),2)
    view=cv2.copyMakeBorder(view,100,0,0,0,cv2.BORDER_CONSTANT,value=(24,24,24))
    p=row['pack'];counts=p['counts'];recipe=p['recipe']
    messages=['P: start empty box | N: new box | U: undo | A: verified | Q: quit',
              f'BOX {p["box"]} | RED {counts["red"]}/{recipe["red"]}  GREEN {counts["green"]}/{recipe["green"]}  BLUE {counts["blue"]}/{recipe["blue"]} | TOTAL {p["total"]}/{p["target_total"]} | {p["status"]}',row.get('framing_warning','')]
    for i,message in enumerate(messages):cv2.putText(view,message,(8,25+30*i),0,.55,(240,240,240),1,cv2.LINE_AA)
    return view


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--backend',choices=['onnx','hailo'],required=True)
    ap.add_argument('--model',type=Path)
    source=ap.add_mutually_exclusive_group(required=True)
    source.add_argument('--source',help='USB camera index, or a video path')
    source.add_argument('--session',type=Path,help='Complete lossless original session with observations.jsonl and source_frames')
    ap.add_argument('--view-config',type=Path)
    ap.add_argument('--runtime-config',type=Path,default=ROOT/'configs/runtime.json')
    ap.add_argument('--color-config',type=Path,default=ROOT/'configs/colors.json')
    ap.add_argument('--output',type=Path,default=ROOT/'runs/pi')
    ap.add_argument('--headless',action='store_true')
    ap.add_argument('--auto-start',action='store_true',help='Start counting immediately; begin with an empty box')
    ap.add_argument('--already-oriented',action='store_true',help='Input pixels already have the configured rotation applied')
    ap.add_argument('--camera-format',choices=['MJPG','YUYV'],default='MJPG',help='USB capture format; MJPG avoids the slow uncompressed mode on this camera')
    ap.add_argument('--camera-fps',type=float,default=30.,help='Requested camera rate; measured capture/application rates can be lower')
    ap.add_argument('--max-frames',type=int)
    ap.add_argument('--seconds',type=float)
    ap.add_argument('--save-preview',action='store_true',help='Include JPEG saving in measured host loop time')
    ap.add_argument('--save-source',action='store_true',help='Save oriented lossless PNGs; include their cost in measured loop time')
    args=ap.parse_args(argv)
    if args.headless and not args.auto_start:ap.error('Headless mode requires --auto-start')
    if args.max_frames is not None and args.max_frames<1:ap.error('--max-frames must be positive')
    if args.seconds is not None and args.seconds<=0:ap.error('--seconds must be positive')
    if args.camera_fps<=0:ap.error('--camera-fps must be positive')
    config=json.loads(args.runtime_config.read_text())
    model=args.model or ROOT/'models'/('can-camera-v1.onnx' if args.backend=='onnx' else 'can-camera-v1.hef')
    if not model.is_file():ap.error(f'Model is not available: {model}')
    identity=model.with_suffix(model.suffix+'.json')
    if not identity.is_file() or json.loads(identity.read_text()).get('sha256')!=hashlib.sha256(model.read_bytes()).hexdigest():ap.error('Model identity is missing or changed')
    model_metadata=json.loads(identity.read_text())
    if model_metadata.get('source_sha256',model_metadata.get('source_checkpoint_sha256'))!=config['model_sha256']:ap.error('Model was built from another checkpoint')
    backend=(OnnxBackend if args.backend=='onnx' else HailoBackend)(model,config['inference'])
    pipeline=Pipeline(ROOT,backend,view=args.view_config,runtime=args.runtime_config,colors=args.color_config)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ');out=args.output/stamp;out.mkdir(parents=True)
    samples=defaultdict(lambda:array('d'));last_record=None;cap=None;pending_reset=False;active=args.auto_start;start=None;processed=0;frame_number=0
    source_rows=None;camera_info=None;capture_stamps=array('d')
    if args.session:
        source_rows=[json.loads(s) for s in (args.session/'observations.jsonl').read_text().splitlines()]
        if not all((args.session/'source_frames'/f'{r.get("source_index",r["index"]):06d}.png').is_file() for r in source_rows):
            raise ValueError('Full source sequence required. The small release evaluation set contains selected frames only.')
    else:
        source_value=int(args.source) if args.source.isdecimal() else args.source
        camera=isinstance(source_value,int)
        cap=cv2.VideoCapture(source_value,cv2.CAP_V4L2 if camera and __import__('sys').platform.startswith('linux') else cv2.CAP_ANY)
        if not cap.isOpened():raise RuntimeError('Could not open input camera/video')
        if camera:
            accepted={'format':cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*args.camera_format)),
                'width':cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280),'height':cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720),
                'fps':cap.set(cv2.CAP_PROP_FPS,args.camera_fps),'buffer':cap.set(cv2.CAP_PROP_BUFFERSIZE,1)}
            fourcc=int(cap.get(cv2.CAP_PROP_FOURCC))
            camera_info={'requested_format':args.camera_format,'requested_fps':args.camera_fps,
                'accepted_requests':accepted,'actual_fourcc':''.join(chr(fourcc>>(8*i)&255) for i in range(4)),
                'reported_fps':cap.get(cv2.CAP_PROP_FPS),
                'actual_size':[cap.get(cv2.CAP_PROP_FRAME_WIDTH),cap.get(cv2.CAP_PROP_FRAME_HEIGHT)]}
            print(json.dumps({'camera':camera_info}),flush=True)
    metadata=dict(backend=args.backend,model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
        original_model_sha256=config['model_sha256'],input_source=str(args.session or args.source),runtime=config,
        started_utc=stamp,placement_verified=False,timing_basis='Host read/processing/display/save intervals; sensor exposure and pre-existing driver queue age are not measured',
        dataset_role='evaluation only',camera=camera_info,
        camera_queue='Synchronous processing; buffer-size request is backend-dependent and must be measured on the Pi')
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    log=(out/'observations.jsonl').open('w',encoding='utf-8');failure=None
    try:
        while True:
            loop=time.perf_counter();frame_number+=1
            if source_rows is not None:
                if frame_number>len(source_rows):break
                source_record=source_rows[frame_number-1]
                frame=cv2.imread(str(args.session/'source_frames'/f'{source_record.get("source_index",source_record["index"]):06d}.png'))
                source_time=source_record['timestamp_seconds']
            else:
                ok,frame=cap.read()
                if not ok:
                    if camera:raise RuntimeError('Camera stopped delivering images')
                    break
                source_time=cap.get(cv2.CAP_PROP_POS_MSEC)/1000 if not camera else None
                if not args.already_oriented and config['rotate_180']:frame=cv2.rotate(frame,cv2.ROTATE_180)
            read_done=time.perf_counter()
            if start is None:start=read_done
            now=source_time if source_time is not None else read_done-start
            if pending_reset:pipeline.new_box(now);pending_reset=False
            if active:
                capture_stamps.append(read_done)
                row,masks=pipeline.process(frame,now);processed+=1
                count_done=time.perf_counter()
                row['source_index']=frame_number
                row['timing_ms']['read_ms']=(read_done-loop)*1000
                row['timing_ms']['capture_to_count_ms']=(count_done-read_done)*1000
                row['timing_ms']['read_to_count_ms']=(count_done-loop)*1000
                if row['transfer_events']:print(json.dumps({'seconds':now,'events':row['transfer_events']}),flush=True)
                preview=draw(frame,row,masks,pipeline.view['defect_exit_x']) if not args.headless or args.save_preview else None
            else:
                row=None;preview=frame.copy()
            key=-1
            if not args.headless:
                canvas=preview if row else cv2.copyMakeBorder(preview,100,0,0,0,cv2.BORDER_CONSTANT,value=(24,24,24))
                if not row:cv2.putText(canvas,'SETUP: press P with an empty box | Q: quit',(8,25),0,.55,(240,240,240),1,cv2.LINE_AA)
                cv2.imshow('Yards Pi candidate',canvas);key=cv2.waitKey(1)&255
            if args.save_preview and row:
                folder=out/'preview';folder.mkdir(exist_ok=True)
                if not cv2.imwrite(str(folder/f'{frame_number:06d}.jpg'),preview):raise OSError('Could not save preview')
            if args.save_source and row:
                folder=out/'source_frames';folder.mkdir(exist_ok=True)
                if not cv2.imwrite(str(folder/f'{frame_number:06d}.png'),frame):raise OSError('Could not save source image')
            if row:
                row['timing_ms']['host_read_to_result_ms']=(time.perf_counter()-loop)*1000
                log.write(json.dumps(row)+'\n');log.flush()
                row['timing_ms']['host_loop_with_log_ms']=(time.perf_counter()-loop)*1000
                for name,value in row['timing_ms'].items():samples[name].append(value)
                last_record=row
            if key in (ord('q'),27):break
            if key==ord('p') and not active:
                active=True;pipeline=Pipeline(ROOT,backend,view=args.view_config,runtime=args.runtime_config,colors=args.color_config);start=time.perf_counter()
            if key==ord('n') and active:pending_reset=True
            if key==ord('u') and active:pipeline.ledger.undo(now)
            if key==ord('a') and active:pipeline.ledger.acknowledge_review(now)
            if args.max_frames and processed>=args.max_frames:break
            if args.seconds and time.perf_counter()-start>=args.seconds:break
    except BaseException as exc:
        failure=repr(exc);raise
    finally:
        log.close()
        if cap is not None:cap.release()
        backend.close()
        if not args.headless:cv2.destroyAllWindows()
        final=pipeline.counter.snapshot(last_record['timestamp_seconds']) if last_record else pipeline.ledger.snapshot()
        (out/'pack-events.json').write_text(json.dumps(pipeline.ledger.events,indent=2)+'\n')
        np.savez(out/'timing-samples.npz',**{k:np.asarray(v) for k,v in samples.items()})
        intervals=np.diff(np.asarray(capture_stamps))*1000
        result=dict(processed_frames=processed,final=final,timing_ms=summary_latency(samples),hardware_validated=False,
            effective_processed_fps=(len(capture_stamps)-1)/(capture_stamps[-1]-capture_stamps[0]) if len(capture_stamps)>1 else None,
            capture_intervals_ms={'median':float(np.median(intervals)),'p95':float(np.percentile(intervals,95))} if len(intervals) else None,
            recording_status='failed' if failure else 'complete',failure=failure,
            hardware_inference_executed=args.backend=='hailo' and processed>0,
            claim='Assumed packed from V4 ROI admission; carton placement is not verified',
            source_timing='Original observation timestamps' if args.session else 'Video PTS' if args.source and not args.source.isdecimal() else 'Host camera read completion',
            recording_mode=dict(save_preview=args.save_preview,save_source=args.save_source,headless=args.headless),output=str(out))
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
