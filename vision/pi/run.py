"""Run the Pi counter, configure live colors, or measure camera delivery."""
from pathlib import Path
import argparse
from datetime import datetime,timezone
from collections import defaultdict
from array import array
from contextlib import ExitStack
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
from yardspi.camera import open_camera,measure_delivery
from stack_lights import StackLights

ROOT=VISION


def summary_latency(samples):
    """Summarize measured stage times; these are not camera sensor latency."""
    return {k:dict(median=float(np.median(v)),p95=float(np.percentile(v,95))) for k,v in samples.items()}


def draw(frame,row,masks,defect_x):
    """Draw masks, counts and host processing measurements for the preview."""
    view=frame.copy();x,y,w,h=row['roi_xywh'];region=view[y:y+h,x:x+w]
    palette={'red':(0,0,255),'green':(0,230,0),'blue':(255,110,40),'unknown':(160,160,160)}
    for o,mask in zip(row['observations'],masks):
        color=palette[o['color']]
        mx,my,mw,mh=cv2.boundingRect(np.asarray(mask,dtype=np.uint8))
        if mw and mh:
            tile=region[my:my+mh,mx:mx+mw];selected=mask[my:my+mh,mx:mx+mw].astype(bool)
            tile[selected]=(tile[selected]*.65+np.asarray(color)*.35).astype(np.uint8)
        a,b,c,d=map(round,o['xyxy_roi'])
        cv2.rectangle(view,(x+a,y+b),(x+c,y+d),color,1)
        cv2.putText(view,f'T{o["track_id"]} {o["color"]}',(x+a,max(15,y+b-3)),0,.45,color,1,cv2.LINE_AA)
    cv2.rectangle(view,(x,y),(x+w,y+h),(0,230,255),2)
    dx=round(x+w*defect_x);cv2.line(view,(dx,y),(dx,y+h),(255,80,230),2)
    view=cv2.copyMakeBorder(view,130,0,0,0,cv2.BORDER_CONSTANT,value=(24,24,24))
    p=row['pack'];counts=p['counts'];recipe=p['recipe']
    timing=row['timing_ms'];fps=row.get('processed_fps',0.)
    messages=['P: start empty box | N: new box | U: undo | A: verified | Q: quit',
              f'BOX {p["box"]} | RED {counts["red"]}/{recipe["red"]}  GREEN {counts["green"]}/{recipe["green"]}  BLUE {counts["blue"]}/{recipe["blue"]} | TOTAL {p["total"]}/{p["target_total"]} | {p["status"]}',
              f'Processed {fps:.1f} FPS | model {timing.get("inference_ms",0):.1f} ms | color {timing["color_ms"]:.1f} ms | analysis {timing["pipeline_ms"]:.1f} ms',
              row.get('framing_warning','')]
    for i,message in enumerate(messages):cv2.putText(view,message,(8,25+30*i),0,.55,(240,240,240),1,cv2.LINE_AA)
    return view


def main(argv=None):
    """Validate command-line options before opening a camera, model or GPIO."""
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--backend',choices=['onnx','hailo'],help='Required for counting; not used by --probe-camera')
    ap.add_argument('--model',type=Path)
    source=ap.add_mutually_exclusive_group(required=True)
    source.add_argument('--source',help='USB camera index, or a video path')
    source.add_argument('--session',type=Path,help='Complete lossless original session with observations.jsonl and source_frames')
    ap.add_argument('--view-config',type=Path)
    ap.add_argument('--runtime-config',type=Path)
    ap.add_argument('--color-config',type=Path)
    ap.add_argument('--config-dir',type=Path,help='Station folder containing runtime.json, colors.json and view.json; individual flags override it')
    ap.add_argument('--output',type=Path,default=ROOT/'runs/pi')
    ap.add_argument('--headless',action='store_true')
    ap.add_argument('--auto-start',action='store_true',help='Start counting immediately; begin with an empty box')
    ap.add_argument('--already-oriented',action='store_true',help='Input pixels already have the configured rotation applied')
    ap.add_argument('--camera-format',choices=['MJPG','YUYV'],default='MJPG',help='USB capture format; MJPG avoids the slow uncompressed mode on this camera')
    ap.add_argument('--camera-fps',type=float,default=30.,help='Requested camera rate; measured capture/application rates can be lower')
    ap.add_argument('--camera-width',type=int,default=1280)
    ap.add_argument('--camera-height',type=int,default=720)
    ap.add_argument('--probe-camera',action='store_true',help='Measure camera delivery only: no model, preview, GPIO or image saving')
    ap.add_argument('--calibrate',action='store_true',help='Collect and verify live color examples, save a local profile, then open the counter in setup')
    ap.add_argument('--calibration-config',type=Path,default=ROOT/'configs/calibration.json',help='Capture, fitting and verification controls')
    ap.add_argument('--calibration-output',type=Path,default=ROOT/'configs/local/color-profiles',help='Folder for new color profiles; existing profiles are not overwritten')
    ap.add_argument('--warmup-seconds',type=float,default=2.,help='Camera-only measurement warmup')
    ap.add_argument('--preview-fps',type=float,default=10.,help='Limit GUI drawing without limiting analysis; 0 draws every analyzed frame')
    ap.add_argument('--max-frames',type=int)
    ap.add_argument('--seconds',type=float)
    ap.add_argument('--save-preview',action='store_true',help='Include JPEG saving in measured host loop time')
    ap.add_argument('--save-source',action='store_true',help='Save oriented lossless PNGs; include their cost in measured loop time')
    ap.add_argument('--gpio',action='store_true',help='Enable status outputs: BCM17 red, BCM27 yellow, BCM22 green')
    ap.add_argument('--gpio-active-low',action='store_true',help='LOW activates a verified 3.3 V compatible relay input; requires --gpio')
    ap.add_argument('--gpio-chip',type=int,help='Override RP1 /dev/gpiochip number; detected by controller label otherwise')
    args=ap.parse_args(argv)
    if args.calibrate and (args.probe_camera or args.headless or args.auto_start or args.session
                           or not args.source or not args.source.isdecimal()):
        ap.error('--calibrate requires a numeric camera source and interactive setup; do not combine with probe, session, headless or auto-start')
    if args.headless and not args.auto_start and not args.probe_camera:ap.error('Headless mode requires --auto-start')
    if args.max_frames is not None and args.max_frames<1:ap.error('--max-frames must be positive')
    if args.seconds is not None and (not np.isfinite(args.seconds) or args.seconds<=0):ap.error('--seconds must be positive and finite')
    if not np.isfinite(args.camera_fps) or args.camera_fps<=0:ap.error('--camera-fps must be positive and finite')
    if min(args.camera_width,args.camera_height)<1:ap.error('Camera dimensions must be positive')
    if not np.isfinite(args.preview_fps) or args.preview_fps<0:ap.error('--preview-fps must be nonnegative and finite')
    if not np.isfinite(args.warmup_seconds) or args.warmup_seconds<0:ap.error('--warmup-seconds must be nonnegative and finite')
    if args.gpio_chip is not None and args.gpio_chip<0:ap.error('--gpio-chip must be nonnegative')
    if args.gpio_chip is not None and not args.gpio:ap.error('--gpio-chip requires --gpio')
    if args.gpio_active_low and not args.gpio:ap.error('--gpio-active-low requires --gpio')
    if args.probe_camera:
        if args.session or not args.source.isdecimal():ap.error('--probe-camera requires a numeric --source')
        if args.gpio or args.save_source or args.save_preview:ap.error('The camera probe does not use GPIO or image saving')
        capture,info=open_camera(args.source,args.camera_width,args.camera_height,args.camera_format,args.camera_fps)
        try:
            print(json.dumps({'camera':info}),flush=True)
            result=measure_delivery(capture,args.seconds or 30.,args.warmup_seconds)
        finally:capture.release()
        result['camera']=info
        args.output.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ')
        path=args.output/f'camera-probe-{stamp}.json'
        result['output']=str(path);path.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2));return
    if not args.backend:ap.error('Counting requires --backend hailo or --backend onnx')
    folder=args.config_dir or ROOT/'configs'
    for option,name in [('runtime_config','runtime.json'),('color_config','colors.json'),('view_config','view.json')]:
        if getattr(args,option) is None:setattr(args,option,folder/name)
        if not getattr(args,option).is_file():ap.error('Missing configuration: '+str(getattr(args,option)))
    if args.calibrate:
        from common.color_calibration import CalibrationPolicy
        try:args.calibration_policy=CalibrationPolicy.load(args.calibration_config)
        except (OSError,ValueError,TypeError) as exc:ap.error('Invalid calibration configuration: '+str(exc))
    # Lights close before model/camera resources, including on startup failure.
    with ExitStack() as resources, StackLights(enabled=args.gpio,chip=args.gpio_chip,active_low=args.gpio_active_low) as lights:
        lights.update()  # Yellow throughout setup/model loading.
        run(args,ap,lights,resources)


def run(args,ap,lights,resources):
    """Process live images or a replay using code and models from this checkout."""
    config=json.loads(args.runtime_config.read_text())
    model=args.model or ROOT/'models'/('can-camera-v1.onnx' if args.backend=='onnx' else 'can-camera-v1.hef')
    if not model.is_file():ap.error(f'Model is not available: {model}')
    identity=model.with_suffix(model.suffix+'.json')
    if not identity.is_file() or json.loads(identity.read_text()).get('sha256')!=hashlib.sha256(model.read_bytes()).hexdigest():ap.error('Model identity is missing or changed')
    model_metadata=json.loads(identity.read_text())
    if model_metadata.get('source_sha256',model_metadata.get('source_checkpoint_sha256'))!=config['model_sha256']:ap.error('Model was built from another checkpoint')
    backend=(OnnxBackend if args.backend=='onnx' else HailoBackend)(model,config['inference'])
    resources.callback(backend.close)
    pipeline=Pipeline(ROOT,backend,view=args.view_config,runtime=args.runtime_config,colors=args.color_config)
    samples=defaultdict(lambda:array('d'));last_record=None;cap=None;pending_reset=False;active=args.auto_start;start=None;processed=0;frame_number=0
    source_rows=None;camera_info=None;capture_stamps=array('d');last_preview_at=float('-inf')
    if args.session:
        source_rows=[json.loads(s) for s in (args.session/'observations.jsonl').read_text().splitlines()]
        if not all((args.session/'source_frames'/f'{r.get("source_index",r["index"]):06d}.png').is_file() for r in source_rows):
            raise ValueError('Full source sequence required. The small release evaluation set contains selected frames only.')
    else:
        source_value=int(args.source) if args.source.isdecimal() else args.source
        camera=isinstance(source_value,int)
        if camera:
            cap,camera_info=open_camera(source_value,args.camera_width,args.camera_height,args.camera_format,args.camera_fps)
        else:cap=cv2.VideoCapture(source_value,cv2.CAP_ANY)
        resources.callback(cap.release)
        if not cap.isOpened():raise RuntimeError('Could not open input camera/video')
        if camera:print(json.dumps({'camera':camera_info}),flush=True)
    if args.calibrate:
        from yardspi.calibration import configure_camera
        resources.callback(cv2.destroyAllWindows)
        profile=configure_camera(cap,backend,config,pipeline.view,json.loads(args.color_config.read_text()),
                                 args.calibration_policy,args.calibration_output,camera_info=camera_info,
                                 already_oriented=args.already_oriented,preview_fps=args.preview_fps)
        if profile is None:
            print('Color setup cancelled; no pack counting started.',flush=True)
            return
        args.color_config=profile
        pipeline=Pipeline(ROOT,backend,view=args.view_config,runtime=args.runtime_config,colors=profile)
        print('Using calibrated colors: '+str(profile.resolve())+' | clear the count area and press P.',flush=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ');out=args.output/stamp;out.mkdir(parents=True)
    metadata=dict(backend=args.backend,model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
        original_model_sha256=config['model_sha256'],input_source=str(args.session or args.source),runtime=config,
        started_utc=stamp,placement_verified=False,timing_basis='Host read/processing/display/save intervals; sensor exposure and pre-existing driver queue age are not measured',
        dataset_role='evaluation only',camera=camera_info,
        camera_queue='Synchronous processing; buffer-size request is backend-dependent and must be measured on the Pi',
        stack_lights=lights.metadata(),code_root=str(ROOT),entry_point=str(Path(__file__).resolve()),
        python_executable=sys.executable,preview_fps_limit=args.preview_fps,
        configurations={name:{'path':str(path.resolve()),'contents':json.loads(path.read_text())}
                        for name,path in [('runtime',args.runtime_config),('colors',args.color_config),('view',args.view_config)]})
    print('Running source: '+metadata['entry_point'],flush=True)
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    log=resources.enter_context((out/'observations.jsonl').open('w',encoding='utf-8'));failure=None
    if not args.headless:resources.callback(cv2.destroyAllWindows)
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
                lights.update(row['pack'])
                row['stack_light']=lights.state
                count_done=time.perf_counter()
                row['source_index']=frame_number
                row['timing_ms']['read_ms']=(read_done-loop)*1000
                row['timing_ms']['capture_to_count_ms']=(count_done-read_done)*1000
                row['timing_ms']['read_to_count_ms']=(count_done-loop)*1000
                if row['transfer_events']:print(json.dumps({'seconds':now,'events':row['transfer_events']}),flush=True)
                recent=capture_stamps[-30:]
                row['processed_fps']=(len(recent)-1)/(recent[-1]-recent[0]) if len(recent)>1 else 0.
            else:
                row=None
            render_start=time.perf_counter()
            preview_due=not args.headless and (args.preview_fps==0 or render_start-last_preview_at>=1/args.preview_fps)
            preview=None
            if row and (preview_due or args.save_preview):preview=draw(frame,row,masks,pipeline.view['defect_exit_x'])
            elif not row and preview_due:preview=frame
            render_done=time.perf_counter()
            key=-1
            if not args.headless:
                if preview_due:
                    canvas=preview if row else cv2.copyMakeBorder(preview,130,0,0,0,cv2.BORDER_CONSTANT,value=(24,24,24))
                    if not row:cv2.putText(canvas,'SETUP: press P with an empty box | Q: quit',(8,25),0,.55,(240,240,240),1,cv2.LINE_AA)
                    cv2.imshow('Yards Pi counter',canvas);last_preview_at=time.perf_counter()
                key=cv2.waitKey(1)&255
            display_done=time.perf_counter()
            if args.save_preview and row:
                folder=out/'preview';folder.mkdir(exist_ok=True)
                if not cv2.imwrite(str(folder/f'{frame_number:06d}.jpg'),preview):raise OSError('Could not save preview')
            if args.save_source and row:
                folder=out/'source_frames';folder.mkdir(exist_ok=True)
                if not cv2.imwrite(str(folder/f'{frame_number:06d}.png'),frame):raise OSError('Could not save source image')
            if row:
                row['timing_ms'].update(render_ms=(render_done-render_start)*1000,
                    display_ms=(display_done-render_done)*1000,image_save_ms=(time.perf_counter()-display_done)*1000)
                row['timing_ms']['host_read_to_result_ms']=(time.perf_counter()-loop)*1000
                log.write(json.dumps(row)+'\n');log.flush()
                row['timing_ms']['host_loop_with_log_ms']=(time.perf_counter()-loop)*1000
                for name,value in row['timing_ms'].items():samples[name].append(value)
                last_record=row
            if key in (ord('q'),27):break
            if key==ord('p') and not active:
                lights.update()
                active=True;pipeline=Pipeline(ROOT,backend,view=args.view_config,runtime=args.runtime_config,colors=args.color_config);start=time.perf_counter()
            if key==ord('n') and active:pending_reset=True;lights.update()
            if key==ord('u') and active:
                pipeline.ledger.undo(now);lights.update(pipeline.counter.snapshot(now) if pipeline.counter else pipeline.ledger.snapshot())
            if key==ord('a') and active:
                pipeline.ledger.acknowledge_review(now);lights.update(pipeline.counter.snapshot(now) if pipeline.counter else pipeline.ledger.snapshot())
            if args.max_frames and processed>=args.max_frames:break
            if args.seconds and time.perf_counter()-start>=args.seconds:break
    except BaseException as exc:
        failure=repr(exc);raise
    finally:
        lights.show('off')
        log.flush()
        final=pipeline.counter.snapshot(last_record['timestamp_seconds']) if last_record and pipeline.counter else pipeline.ledger.snapshot()
        (out/'pack-events.json').write_text(json.dumps(pipeline.ledger.events,indent=2)+'\n')
        np.savez(out/'timing-samples.npz',**{k:np.asarray(v) for k,v in samples.items()})
        intervals=np.diff(np.asarray(capture_stamps))*1000
        result=dict(processed_frames=processed,final=final,timing_ms=summary_latency(samples),hardware_validated=False,
            effective_processed_fps=(len(capture_stamps)-1)/(capture_stamps[-1]-capture_stamps[0]) if len(capture_stamps)>1 else None,
            capture_intervals_ms={'median':float(np.median(intervals)),'p95':float(np.percentile(intervals,95))} if len(intervals) else None,
            capture_intervals_basis='Intervals between reads in the processing loop; use --probe-camera for camera-only delivery',
            recording_status='failed' if failure else 'complete',failure=failure,
            hardware_inference_executed=args.backend=='hailo' and processed>0,
            claim='Assumed packed from V4 ROI admission; carton placement is not verified',
            source_timing='Original observation timestamps' if args.session else 'Video PTS' if args.source and not args.source.isdecimal() else 'Host camera read completion',
            recording_mode=dict(save_preview=args.save_preview,save_source=args.save_source,headless=args.headless,
                                preview_fps_limit=args.preview_fps),output=str(out))
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
