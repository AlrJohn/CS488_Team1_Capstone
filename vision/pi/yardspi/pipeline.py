"""Frozen V4 color, deduplication, observation and counting stages."""
import json
from pathlib import Path
from types import SimpleNamespace
import time
from common.geometry import Boxes,restore_view
from common.color_analysis import sample_colors
from common.instance_quality import deduplicate
from common.instance_memory import context_area,clipped_edges
from common.pack_ledger import PackLedger
from common.pack_crossing import RoiCounter,left_defect_boundary
from common.observer import RoiObserver


class Pipeline:
    def __init__(self,root,backend,*,view=None,runtime=None,colors=None):
        self.root=Path(root);self.backend=backend
        self.config=json.loads(Path(runtime or self.root/'configs/runtime.json').read_text())
        self.view=json.loads(Path(view or self.root/'configs/view.json').read_text())
        colors=json.loads(Path(colors or self.root/'configs/colors.json').read_text())
        self.settings=SimpleNamespace(colors={k:SimpleNamespace(**v) for k,v in colors['colors'].items()})
        self.ledger=PackLedger(self.config['expected_recipe']);self.counter=None
        self.observer=RoiObserver(self.config['tracker']);self.roi=None
    def new_box(self,now):
        closed=self.ledger.new_box(now)
        self.observer=RoiObserver(self.config['tracker']);self.counter=None
        return closed
    def process(self,frame,now):
        start=time.perf_counter();self.roi=restore_view(self.view,frame.shape[:2])
        x,y,w,h=self.roi
        cx,cy,cw,ch=context_area(self.roi,frame.shape[:2],self.config['tracking_context']['padding_fraction'])
        context=frame[cy:cy+ch,cx:cx+cw]
        masks,boxes,timing=self.backend.predict(context)
        detected=time.perf_counter();labels,votes=sample_colors(context,masks,self.settings,interior=True)
        colored=time.perf_counter();keep,suppressed=deduplicate(masks,labels,boxes.conf)
        masks=masks[keep];context_data=boxes.data[keep].copy();data=context_data.copy();labels=[labels[i] for i in keep];votes=[votes[i] for i in keep]
        data[:,[0,2]]+=cx-x;data[:,[1,3]]+=cy-y
        observations,confirmed=self.observer.update(Boxes(data,(h,w)),labels,now)
        warnings=[]
        for o,v,box in zip(observations,votes,context_data[:,:4]):
            o['color_analysis']=v;o['context_edges']=clipped_edges(box,(ch,cw))
            known=o['color'] in ('red','green','blue') or confirmed.get(o['track_id'],{}).get('color') in ('red','green','blue')
            if o['inside_roi'] and known:
                if o['context_edges']:warnings.append('CAN CLIPPED AT TRACKING EDGE: '+', '.join(o['context_edges']))
                elif o['roi_edges']:warnings.append('ROI edge: '+', '.join(o['roi_edges'])+' | following in tracking margin')
        if self.counter is None:self.counter=RoiCounter((h,w),self.ledger,reject_boundary=left_defect_boundary(self.view['defect_exit_x']))
        events=self.counter.update(observations,confirmed,self.observer.index,now)
        timing.update(color_ms=(colored-detected)*1000,tracking_count_ms=(time.perf_counter()-colored)*1000,pipeline_ms=(time.perf_counter()-start)*1000)
        return dict(index=self.observer.index,timestamp_seconds=now,roi_xywh=self.roi,tracking_context_xywh=[cx,cy,cw,ch],
                    roi_group=self.observer.group,observations=observations,confirmed=confirmed,
                    pack=self.counter.snapshot(now),transfer_events=events,timing_ms=timing,suppressed_duplicates=suppressed,
                    frame_shape=list(frame.shape[:2]),framing_warning=' | '.join(dict.fromkeys(warnings))),masks[:,y-cy:y-cy+h,x-cx:x-cx+w]
