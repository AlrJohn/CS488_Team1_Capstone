"""Confirmed ROI cans are assumed packed; only observed left defect exits subtract."""
from dataclasses import dataclass,field
import math

COLORS=('red','green','blue')

@dataclass
class Boundary:
    start: list
    end: list
    packing: list
    hysteresis: float=.025

    def __post_init__(self):
        for point in (self.start,self.end,self.packing):
            if len(point)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in point):
                raise ValueError('Boundary points must be inside the detection area')
        if math.dist(self.start,self.end)<.10:raise ValueError('Draw a longer boundary')
        if not .005<=self.hysteresis<=.15:raise ValueError('Invalid boundary dead band')
        if abs(self.distance(self.packing))<=self.hysteresis:raise ValueError('Click clearly on the destination side')

    def distance(self,point):
        ax,ay=self.start;bx,by=self.end
        return ((bx-ax)*(point[1]-ay)-(by-ay)*(point[0]-ax))/math.hypot(bx-ax,by-ay)

    def side(self,point):
        value=self.distance(point)*(1 if self.distance(self.packing)>0 else -1)
        return 1 if value>self.hysteresis else -1 if value < -self.hysteresis else 0

    def as_dict(self):return dict(start=self.start,end=self.end,packing=self.packing,hysteresis=self.hysteresis)

def left_defect_boundary(x):
    """Vertical exit inside the visible ROI; leftward travel removes a can."""
    if type(x) not in (int,float) or not math.isfinite(x) or not .08<=x<=.80:
        raise ValueError('Put the defect line between 8% and 80% of the detection area width, leaving visible space on its left')
    return Boundary([x,0.],[x,1.],[0.,.5])

@dataclass
class GateState:
    stable_side: int=0
    candidate_side: int=0
    side_hits: int=0
    saw_band: bool=False
    pending: dict | None=None

@dataclass
class RoiTrack:
    identity: int
    last_frame: int
    qualified_color: str | None=None
    counted: bool=False
    removed: bool=False
    blocked: bool=False
    first_side: int=0
    missing_reviewed: bool=False
    point: tuple=(0.,0.)
    defect: GateState=field(default_factory=GateState)
    roi_seen_at: float | None=None
    roi_color_hits: int=0
    roi_strong_hits: int=0
    loss_review: str | None=None
    gate_frame: int | None=None

class RoiCounter:
    def __init__(self,shape,ledger,*,reject_boundary,side_frames=2,max_gap=2,color_wait=5):
        self.reject_boundary=reject_boundary;self.height,self.width=shape
        if min(shape)<=0 or min(side_frames,max_gap,color_wait)<1:raise ValueError('Invalid ROI counter settings')
        if reject_boundary.start[0]!=reject_boundary.end[0] or reject_boundary.side([0.,.5])!=1:
            raise ValueError('The defect exit must be vertical and point left')
        self.ledger=ledger;self.side_frames=side_frames;self.max_gap=max_gap;self.color_wait=color_wait
        self.tracks={};self.index=0;self.last_change=None;self.unassigned=False

    def _review(self,track,reason,now):
        track.blocked=True;track.defect.pending=None
        self.ledger.review(f'T{track.identity}: {reason}',now)

    def _advance_defect(self,track,side,index,gap,now):
        gate=track.defect
        if gap:gate.candidate_side=0;gate.side_hits=0
        if gap>self.max_gap and gate.stable_side and (side==0 or side!=gate.stable_side):
            self._review(track,'defect crossing was not continuously observed; verify count',now)
        if side==0:
            gate.saw_band=True;gate.candidate_side=0;gate.side_hits=0
            return
        if gate.candidate_side==side:gate.side_hits+=1
        else:gate.candidate_side=side;gate.side_hits=1
        if gate.side_hits<self.side_frames:return
        if not gate.stable_side:
            if side==1 and (track.first_side==-1 or gate.saw_band):
                self._review(track,'defect origin was not established before crossing; verify count',now)
            gate.stable_side=side
        elif side!=gate.stable_side:
            source=gate.stable_side;gate.stable_side=side
            if gate.pending:self._review(track,'defect reversed before color confirmation; verify count',now)
            elif side==1:
                gate.pending={'source_side':source,'crossing_frame':index,'event_id':f'T{track.identity}/defect'}

    def _resolve_defect(self,track,side,qualified,index,now):
        pending=track.defect.pending
        if not pending or track.blocked:return
        if qualified in COLORS and qualified==track.qualified_color and side==1:
            event=self.ledger.apply(pending['event_id'],{qualified:1},-1 if track.counted else 0,now,
                box=self.ledger.box,evidence={'track_id':track.identity,'gate':'left_defect','source_side':pending['source_side'],
                    'destination_side':1,'crossing_frame':pending['crossing_frame'],'confirmed_frame':index,
                    'center_normalized':track.point,'placement_verified':False})
            if event['kind']=='defect':self.last_change=now
            track.removed=True;track.defect.pending=None
        elif index-pending['crossing_frame']>=self.color_wait:
            self._review(track,'defect crossed without a confirmed color; verify count',now)

    def update(self,observed,confirmed,index,now):
        if index!=self.index+1:raise ValueError('Only new, consecutive observations may advance the counter')
        self.index=index;start=len(self.ledger.events);current=set()
        self.unassigned=any(item['track_id'] is None for item in observed)
        for item in observed:
            identity=item['track_id']
            if identity is None:continue
            if identity in current:raise ValueError('An ID was observed more than once')
            current.add(identity)
            x0,y0,x1,y1=item['xyxy_roi'];point=((x0+x1)/2/self.width,(y0+y1)/2/self.height)
            if any(not math.isfinite(v) for v in point):raise ValueError('Observation center must be finite')
            inside=all(0<=v<=1 for v in point)
            side=self.reject_boundary.side(point)
            track=self.tracks.get(identity)
            if track is None:track=RoiTrack(identity,index);self.tracks[identity]=track;gap=0
            else:gap=index-track.last_frame-1
            track.last_frame=index;track.point=point;track.missing_reviewed=False
            if inside and track.first_side==0 and side:track.first_side=side
            if inside and side==-1:
                track.roi_seen_at=now
                if item['color'] in COLORS:track.roi_color_hits+=1
                if item.get('confidence',0)>=.8:track.roi_strong_hits+=1
            qualified=confirmed.get(identity,confirmed.get(str(identity),{})).get('color')
            if qualified in COLORS:
                if track.counted and track.qualified_color is not None and track.qualified_color!=qualified and not track.removed:
                    self._review(track,'color/identity changed; verify the box count',now)
                else:track.qualified_color=qualified
            if track.blocked or track.removed:continue
            # The narrow strip to the left monitors rejects, not fresh picks.
            # A track first seen there cannot re-enter and inflate the box count.
            if track.first_side==1:
                if qualified in COLORS:
                    self.ledger.apply(f'T{identity}/defect-side-excluded',{qualified:1},0,now,
                        evidence={'track_id':identity,'gate':'defect_side_entry','confirmed_frame':index,
                            'reason':'First observed on the defect side; no observed active-area admission'})
                    track.removed=True
                continue
            # Context above/below the ROI cannot establish a defect crossing.
            if 0<=point[1]<=1:
                gate_gap=index-track.gate_frame-1 if track.gate_frame is not None else 0
                self._advance_defect(track,side,index,gate_gap,now)
                self._resolve_defect(track,side,qualified,index,now)
                track.gate_frame=index
            else:
                track.defect.candidate_side=0;track.defect.side_hits=0
            if track.blocked or track.removed:continue
            # Admission needs actual current ROI evidence and existing 2-of-5
            # identity/color confirmation, with no packaging line or direction.
            recently_inside=track.roi_seen_at is not None and now-track.roi_seen_at<=.40
            if not track.counted and not track.defect.pending and side==-1 and qualified in COLORS and recently_inside:
                self.ledger.apply(f'T{identity}/roi',{qualified:1},1,now,box=self.ledger.box,
                    evidence={'track_id':identity,'gate':'roi_admission','confirmed_frame':index,
                        'center_normalized':point,'last_roi_observation_seconds':track.roi_seen_at,
                        'confirmed_in_context':not inside,'placement_verified':False})
                track.counted=True;self.last_change=now
                if track.loss_review:self.ledger.resolve_review(track.loss_review,now);track.loss_review=None
        for track in self.tracks.values():
            missing=index-track.last_frame
            if missing>self.max_gap and not track.missing_reviewed:
                if track.defect.pending:self._review(track,'lost before defect/color confirmation; verify count',now)
                elif not track.counted and not track.removed and not track.blocked and track.first_side!=1 and (track.roi_color_hits>=2 or track.roi_strong_hits>=3):
                    # A credible but unconfirmed candidate warrants review,
                    # not a permanent ban on later valid observations.
                    track.loss_review=f'T{track.identity}: credible ROI can lost before confirmation; verify count'
                    self.ledger.review(track.loss_review,now)
                track.missing_reviewed=True
            # Retain per-box track tombstones; a confirmed ID cannot count twice.
        return self.ledger.events[start:]

    def pending(self,index):
        return self.unassigned or any(not t.blocked and not t.removed and t.first_side!=1 and (
            t.defect.pending is not None or (t.last_frame==index and (
                ((t.roi_color_hits>=1 or t.roi_strong_hits>=3) and (not t.counted or t.qualified_color is None)) or
                (t.counted and 0<=t.point[1]<=1 and (t.defect.candidate_side!=t.defect.stable_side or t.defect.candidate_side==0)))))
            for t in self.tracks.values())

    def snapshot(self,now):
        settling=self.last_change is not None and now-self.last_change<.30
        return {**self.ledger.snapshot(pending=self.pending(self.index) or settling),
            'placement_verified':False,'count_basis':'Confirmed ROI cans assumed packed, minus observed left-side defects'}
