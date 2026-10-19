"""Confirmed cans in the ROI are assumed packed; left defect crossings subtract."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,json,sys,time
ROOT=Path(__file__).resolve().parent
VISION=ROOT.parent
sys.path.insert(0,str(VISION))
import detector as live
from common.pack_ledger import PackLedger
from common.pack_crossing import RoiCounter,left_defect_boundary
from common.instance_memory import context_area,clipped_edges
from common.observer import RoiObserver
from common.recording import Trial as SourceTrial
cv2=live.cv2;np=live.np
WINDOW='Yards 12-pack counter'
HEADER=132


class PackTrial(SourceTrial):
    def __init__(self,metadata,ledger,counter,**kwargs):
        self.ledger=ledger;self.counter=counter;self.last_time=0.
        super().__init__(metadata,kwargs.get('output_root',VISION/'runs/windows'),live.encoder_executable())

    def add(self,frame,view,record):
        self.last_time=record['timestamp_seconds']
        super().add(frame,view,record)

    def close(self):
        if self.closed:return
        try:super().close()
        finally:
            summary_path=self.path/'summary.json'
            if summary_path.exists():
                summary=json.loads(summary_path.read_text())
                summary.update(pack_evaluation=self.counter.snapshot(self.last_time),
                    dataset_role=self.metadata['dataset_role'],
                    claim='Confirmed ROI cans assumed placed in box, minus observed left-side defects; carton placement is not verified')
                live.dump(summary_path,summary)
                final=summary['pack_evaluation']
                print(f'BOX {final["box"]} saved: {final["counts"]} | {final["total"]}/{final["target_total"]} | {final["status"]}',flush=True)
            live.dump(self.path/'pack-events.json',self.ledger.events)

def restore_view(config,shape):
    height,width=shape
    bounds=config['normalized_xywh']
    if len(bounds)!=4 or not all(type(v) in (int,float) and np.isfinite(v) and 0<=v<=1 for v in bounds) or min(bounds[2:])<=0 or bounds[0]+bounds[2]>1.00001 or bounds[1]+bounds[3]>1.00001:
        raise ValueError('Invalid saved detection area')
    roi=[round(bounds[0]*width),round(bounds[1]*height),round(bounds[2]*width),round(bounds[3]*height)]
    roi[2],roi[3]=min(roi[2],width-roi[0]),min(roi[3],height-roi[1])
    if min(roi[2:])<40:raise ValueError('Detection area is too small')
    reject=left_defect_boundary(config['defect_exit_x']) if config.get('defect_exit_x') is not None else None
    # A legacy packaging boundary is deliberately ignored, including its direction.
    return roi,reject

def save_view(path,ui,rotation):
    fh,fw=ui['frame_shape'];x,y,w,h=ui['roi']
    path.parent.mkdir(parents=True,exist_ok=True)
    live.dump(path,{'version':4,'count_policy':'roi-instance-memory-left-defect-v4','normalized_xywh':[x/fw,y/fh,w/fw,h/fh],
        'rotate_180':rotation,'defect_exit_x':ui['reject_boundary'].start[0] if ui.get('reject_boundary') else None,
        'note':'O: count area. D: left defect exit. The detector also sees a tracking margin outside the count area.'})

def click_calibration(ui,path,rotation,event,x,y,flags,parameter):
    if event!=cv2.EVENT_LBUTTONDOWN or not ui['calibrating'] or ui['roi'] is None:return
    px,py=x,y-HEADER;rx,ry,w,h=ui['roi']
    if not rx<=px<=rx+w-1 or not ry<=py<=ry+h-1:
        ui['message']='Click inside the yellow detection area';return
    try:ui['reject_boundary']=left_defect_boundary((px-rx)/w)
    except ValueError as exc:ui['message']=str(exc);return
    ui['calibrating']=False;ui['message']='Defect exit saved. Clear the ROI, start with an empty box, then press P.'
    save_view(path,ui,rotation)

def annotate(frame,roi,masks,observed,confirmed,snapshot,ui,recording,performance,index,last_event):
    visible=[n for n,(mask,item) in enumerate(zip(masks,observed)) if mask.any() or item.get('inside_roi',True)]
    display_masks=masks[visible];display_observed=[observed[n] for n in visible]
    view=live.annotate(frame,roi,display_masks,display_observed,confirmed,'',snapshot['recipe'],performance[0],performance[1],False,index,None)
    view[:HEADER]=24;view[-32:]=24
    region=view[HEADER:HEADER+frame.shape[0]]
    x,y,w,h=roi;reject=ui.get('reject_boundary')
    if reject:
        line_x=round(x+reject.start[0]*w)
        cv2.line(region,(line_x,y),(line_x,y+h-1),(255,80,230),2)
        for offset in (-1,1):
            edge=round(line_x+offset*reject.hysteresis*w)
            cv2.line(region,(edge,y),(edge,y+h-1),(120,65,120),1)
        cv2.putText(region,'<- DEFECT OUT',(min(line_x+8,x+w-160),y+24),0,.55,(255,80,230),2,cv2.LINE_AA)
        cv2.putText(region,'COUNT AREA ->',(min(line_x+8,x+w-160),y+h-12),0,.55,(70,230,100),2,cv2.LINE_AA)
    counts=snapshot['counts'];recipe=snapshot['recipe']
    state=snapshot['status'] if recording else 'SETUP - PRESS D: LEFT DEFECT EXIT' if reject is None else 'SETUP - PRESS P'
    color=(60,240,100) if recording and snapshot['ready'] else (70,160,255) if snapshot['status'] in ('REVIEW','OVER TARGET') else (240,240,240)
    if ui['calibrating']:detail='Click the left defect exit; leave room to see the can cross | '+ui['message']
    elif snapshot['reviews']:detail=snapshot['reviews'][-1]+' | verify counts, then A to acknowledge'
    elif ui.get('framing_warning'):detail=ui['framing_warning']
    else:detail=ui['message'] or last_event
    lines=[f'BOX {snapshot["box"]} | RED {counts["red"]}/{recipe["red"]}   GREEN {counts["green"]}/{recipe["green"]}   BLUE {counts["blue"]}/{recipe["blue"]} | TOTAL {snapshot["total"]}/{snapshot["target_total"]} | {state}',
        f'INSTANCE MEMORY | Active ROI: {sum(item.get("inside_roi",True) for item in observed)} | group {snapshot.get("roi_group",1)} | last: {last_event} | {performance[0]:.1f} FPS',
        'P: start   N: save/new box   D: left defect line   O: area   U: undo   A: verify   Q: quit',detail]
    for i,line in enumerate(lines):
        size=.65 if i==0 else .55
        length=cv2.getTextSize(line,0,size,1)[0][0];size*=min(1.,(view.shape[1]-20)/max(1,length))
        cv2.putText(view,line,(10,25+i*30),0,size,color if i==0 else (240,240,240),1,cv2.LINE_AA)
    cv2.putText(view,'ROI CANS ASSUMED IN BOX | Physical-instance memory + tracking margin. Left defect crossings subtract.',
        (10,view.shape[0]-10),0,.5,(0,210,255),1,cv2.LINE_AA)
    return view

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='0');parser.add_argument('--device',default='0' if live.torch.cuda.is_available() else 'cpu')
    parser.add_argument('--backend',choices=['auto','dshow','msmf','any'],default='dshow')
    parser.add_argument('--model',type=Path,default=VISION/'models/can-camera-v1.pt')
    parser.add_argument('--color-config',type=Path,default=VISION/'configs/colors.json')
    parser.add_argument('--view-config',type=Path,default=VISION/'configs/local/windows-view.json')
    parser.add_argument('--recipe',default='4,4,4')
    parser.add_argument('--output-root',type=Path,default=VISION/'runs/windows')
    parser.add_argument('--rotate-180',action=argparse.BooleanOptionalAction,default=None)
    args=parser.parse_args();recipe=live.parse_recipe(args.recipe)
    settings=live.Settings.load(args.color_config);rotation=settings.rotate_180 if args.rotate_180 is None else args.rotate_180
    checkpoint,model_sha=live.verified_model(args.model)
    config=dict(imgsz=640,conf=.50,iou=.7,max_det=100,retina_masks=True,device=args.device,verbose=False,save=False)
    tracker={**live.TRACKER,'fuse_score':False}
    view_path=args.view_config.resolve()
    initial=json.loads((view_path if view_path.exists() else VISION/'configs/view.json').read_text())
    if view_path.exists() and initial.get('rotate_180',rotation)!=rotation:raise ValueError('Camera rotation changed: recalibrate the saved pack view')
    files=[Path(__file__),Path(live.__file__)]+[VISION/'common'/n for n in
        ['pack_ledger.py','pack_crossing.py','color_analysis.py','instance_quality.py','instance_memory.py','observer.py','recording.py','camera.py','settings.py']]
    archive=args.output_root/'source-versions';archive.mkdir(parents=True,exist_ok=True)
    hashes={};archived={}
    for path in files:
        key=str(path.resolve());digest=live.digest(path);frozen=archive/(digest+'.py')
        if not frozen.exists():frozen.write_bytes(path.read_bytes())
        if live.digest(frozen)!=digest:raise ValueError('Archived source changed')
        hashes[key]=digest;archived[key]=str(frozen)
    metadata={'trial_mode':'pack-count','model':str(checkpoint),'model_sha256':model_sha,
        'expected_recipe':recipe,'color_config':str(args.color_config.resolve()),'color_config_sha256':live.digest(args.color_config),
        'rotate_180':rotation,'inference':config,'tracker':tracker,'source':args.source,
        'source_sha256':hashes,'source_archive':archived,'dataset_role':'evaluation only; not automatically used for training',
        'duplicate_mask_handling':{'enabled':True,'stage':'before tracking','minimum_containment':.95,'minimum_area_ratio':.60},
        'transfer_policy':{'side_frames':2,'max_crossing_gap_images':2,'color_wait_images':5,
            'version':4,'admission':'confirmed physical instance observed in the active ROI; up to 0.40 seconds of context qualification after leaving it',
            'requires_packaging_boundary':False,'repeat_id':'short motion memory reconnects changed tracker IDs to one physical instance',
            'defect_side_entry':'exclude tracks first seen left of the defect line from admission',
            'removal':'right-to-left across the separately calibrated defect exit only',
            'uncounted_defect':'exclude without subtracting a different can',
            'color_confirmation':'actual three-of-five observations','missing_crossing':'review; never infer from disappearance'},
        'roi_group_clear':{'minimum_empty_images':3,'minimum_empty_seconds':.35,
            'effect':'retire lost instances after the active count area clears; visible context tracks remain connected'},
        'tracking_context':{'padding_fraction':.20,'confidence':.50,'instance_memory_seconds':.65,'instance_memory_frames':10},
        'placement_assumption':'Confirmed cans in the active ROI go into the box unless seen leaving through the left defect exit',
        'placement_verified':False,'scope':'Assumed box contents from confirmed ROI cans and observed left-side defects'}
    print('12-PACK MODE | 4 red + 4 green + 4 blue by default | duplicate suppression ON',flush=True)
    print('ROI COUNTING V4 | INSTANCE MEMORY + TRACKING CONTEXT | O: count area. D: left DEFECT exit. P: start EMPTY box. N: save/reset after box trial.',flush=True)
    print('Each confirmed ROI can counts once, assumed packed. Keep waiting stock outside the count area. No packaging line is used.',flush=True)
    model=live.YOLO(str(checkpoint))
    for _ in range(3):live.predict(model,np.zeros((480,640,3),np.uint8),settings,config,color_mode='v2',deduplicate_masks=True)
    cap,camera=live.open_source(args.source,args.backend,1280,720)
    source_rotation=False if camera else live.recorded_rotation(args.source)
    cv2.namedWindow(WINDOW,cv2.WINDOW_NORMAL);cv2.resizeWindow(WINDOW,1280,884)
    ui={'roi':None,'frame_shape':None,'reject_boundary':None,'calibrating':False,'framing_warning':'','message':'Set O: counting area and D: left defect exit. Keep waiting stock outside.'}
    cv2.setMouseCallback(WINDOW,lambda *event:click_calibration(ui,view_path,rotation,*event))
    observer=RoiObserver(tracker);ledger=PackLedger(recipe);counter=None;trial=None
    times=[];fps=0.;last_event='none';event_cursor=0;pattern_seen=False
    try:
        while True:
            started=time.perf_counter();ok,frame=cap.read();capture=time.perf_counter()
            if not ok:
                if camera:raise RuntimeError('Camera stopped delivering images')
                break
            if camera and not live.has_image_signal(frame):raise RuntimeError('Camera image is blank')
            frame=live.orient_frame(frame,rotation,source_rotation)
            if ui['roi'] is None:
                ui['frame_shape']=frame.shape[:2];ui['roi'],ui['reject_boundary']=restore_view(initial,frame.shape[:2])
                if ui['reject_boundary']:ui['message']='ROI and defect exit restored. Clear the ROI, start an empty box, then press P.'
            x,y,w,h=ui['roi'];diagnostics={}
            cx,cy,cw,ch=context_area(ui['roi'],frame.shape[:2])
            context_masks,context_boxes,labels,model_ms=live.predict(model,frame[cy:cy+ch,cx:cx+cw],settings,config,color_mode='v2',diagnostics=diagnostics,deduplicate_masks=True)
            data=context_boxes.data.copy();data[:,[0,2]]+=cx-x;data[:,[1,3]]+=cy-y
            boxes=live.Boxes(data,(h,w))
            masks=context_masks[:,y-cy:y-cy+h,x-cx:x-cx+w]
            now=capture-origin if trial else 0.
            observed,confirmed=observer.update(boxes,labels,now)
            edge_warnings=[]
            for item,votes,box in zip(observed,diagnostics['color_analysis'],context_boxes.xyxy):
                item['color_analysis']=votes;item['context_edges']=clipped_edges(box,(ch,cw))
                if item['inside_roi'] and item['color'] in ('red','green','blue'):
                    if item['context_edges']:edge_warnings.append('CAN CLIPPED AT TRACKING EDGE: '+', '.join(item['context_edges'])+' | move camera back / adjust O')
                    elif item['roi_edges']:edge_warnings.append('ROI edge: '+', '.join(item['roi_edges'])+' | tracking margin is following the full can')
            ui['framing_warning']=edge_warnings[0] if edge_warnings else ''
            if trial:
                counter.update(observed,confirmed,observer.index,now)
                new_events=ledger.events[event_cursor:];event_cursor=len(ledger.events)
                for event in new_events:
                    if event['kind'] in ('pick','defect','defect_excluded'):
                        quantities=', '.join(f'{n} {c}' for c,n in event['quantities'].items() if n)
                        last_event=('+' if event['kind']=='pick' else '- defect ' if event['kind']=='defect' else 'excluded uncounted defect ')+quantities
            else:new_events=[]
            snapshot=counter.snapshot(now) if trial else ledger.snapshot()
            snapshot['roi_group']=observer.group
            if trial:pattern_seen=pattern_seen or snapshot['ready']
            times=(times+[capture])[-10:]
            if len(times)>1:fps=(len(times)-1)/(times[-1]-times[0])
            view=annotate(frame,ui['roi'],masks,observed,confirmed,snapshot,ui,trial is not None,(fps,model_ms),observer.index,last_event)
            if trial:
                trial.add(frame,view,{'index':observer.index,'timestamp_seconds':now,'roi_xywh':ui['roi'],'roi_group':observer.group,
                    'observations':observed,'confirmed':confirmed,'pack':snapshot,'transfer_events':new_events,
                    'tracking_context_xywh':[cx,cy,cw,ch],'framing_warning':ui['framing_warning'],
                    'pattern_matches_now':snapshot['ready'],'pattern_seen':pattern_seen,
                    'five_frame_span_seconds':times[-1]-times[-5] if len(times)>=5 else None,
                    'prediction_ms':model_ms,'timing_ms':{'camera_read':(capture-started)*1000,'model':model_ms,
                        'color':diagnostics['color_ms'],'deduplication':diagnostics['deduplication_ms']},
                    'duplicate_mask_handling':{'suppressed_duplicates':diagnostics['suppressed_duplicates'],
                        'retained_detection_indices':diagnostics['retained_detection_indices']}})
            cv2.imshow(WINDOW,view);key=cv2.waitKey(1)&255
            if ord('A')<=key<=ord('Z'):key+=ord('a')-ord('A')
            if key in (27,ord('q')) or cv2.getWindowProperty(WINDOW,cv2.WND_PROP_VISIBLE)<1:break
            if key==ord('p') and trial is None:
                if ui['reject_boundary'] is None or ui['calibrating']:
                    ui['message']='Press D and click the left defect exit before P';continue
                counter=RoiCounter((h,w),ledger,reject_boundary=ui['reject_boundary'])
                trial_metadata={**metadata,'box_number':ledger.box,'roi_xywh':list(ui['roi']),
                    'tracking_context_xywh':[cx,cy,cw,ch],'defect_boundary':ui['reject_boundary'].as_dict(),'actual_frame_size':[frame.shape[1],frame.shape[0]],
                    'started_utc':datetime.now(timezone.utc).isoformat(),'backend':cap.getBackendName()}
                trial=PackTrial(trial_metadata,ledger,counter,output_root=args.output_root)
                observer=RoiObserver(tracker);origin=time.perf_counter();times=[];fps=0.;event_cursor=len(ledger.events);pattern_seen=False
                ui['message']='Each confirmed can in the active ROI adds once (+); left defect crossings subtract (-).'
            elif key==ord('n') and trial:
                trial.close();trial=None
                box=ledger.box+1;ledger=PackLedger(recipe);ledger.box=box;counter=None
                observer=RoiObserver(tracker);times=[];fps=0.;last_event='none';event_cursor=0;pattern_seen=False
                ui['message']='Previous box saved. Start with the next empty box; press P.'
            elif key==ord('u') and trial:
                event=ledger.undo(now)
                if event:last_event='manual undo of last counted can'
            elif key==ord('a') and trial:
                ledger.acknowledge_review(now);ui['message']='Operator verified the displayed counts.'
            elif key==ord('c'):
                ui['message']='No packaging line is needed. O selects the ROI; D positions the left defect exit.'
            elif key in (ord('d'),ord('o')):
                if trial:ui['message']='Save the active box with N before changing the geometry';continue
                if key==ord('d'):
                    ui['calibrating']=True;ui['message']='Click the left defect exit; keep the can visible after crossing'
                else:
                    selected=cv2.selectROI(WINDOW,frame,showCrosshair=True,fromCenter=False)
                    if min(selected[2:])>=40:
                        ui['roi']=list(map(int,selected));ui['reject_boundary']=None;ui['calibrating']=False
                        save_view(view_path,ui,rotation);ui['message']='ROI saved. Press D to set its left defect exit.'
                observer=RoiObserver(tracker);times=[]
    finally:
        cap.release();cv2.destroyAllWindows()
        if trial:trial.close()

if __name__=='__main__':main()
