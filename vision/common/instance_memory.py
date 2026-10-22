"""One-to-one short motion memory; tracker IDs are hints, not new-can events."""
from collections import Counter
from dataclasses import dataclass,field
import math

COLORS=('red','green','blue')

def center(box):return ((box[0]+box[2])/2,(box[1]+box[3])/2)

def iou(a,b):
    area=lambda x:max(0,x[2]-x[0])*max(0,x[3]-x[1])
    overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return overlap/max(1.,area(a)+area(b)-overlap)

def assign_minimum(cost):
    """Rectangular Hungarian assignment; extra zero-cost columns allow new IDs."""
    n=len(cost)
    if not n:return []
    m=len(cost[0]);u=[0.]*(n+1);v=[0.]*(m+1);p=[0]*(m+1);way=[0]*(m+1)
    for row in range(1,n+1):
        p[0]=row;j0=0;minimum=[float('inf')]*(m+1);used=[False]*(m+1)
        while True:
            used[j0]=True;i0=p[j0];delta=float('inf');j1=0
            for j in range(1,m+1):
                if used[j]:continue
                current=cost[i0-1][j-1]-u[i0]-v[j]
                if current<minimum[j]:minimum[j]=current;way[j]=j0
                if minimum[j]<delta:delta=minimum[j];j1=j
            for j in range(m+1):
                if used[j]:u[p[j]]+=delta;v[j]-=delta
                else:minimum[j]-=delta
            j0=j1
            if not p[j0]:break
        while True:
            j1=way[j0];p[j0]=p[j1];j0=j1
            if not j0:break
    return [(p[j]-1,j-1) for j in range(1,m+1) if p[j]]

@dataclass
class Instance:
    identity: int
    box: list
    time: float
    frame: int
    previous: tuple | None=None
    history: list=field(default_factory=list)
    retired: bool=False

    def color(self):
        known=[r['color'] for r in self.history if r['color'] in COLORS]
        return Counter(known).most_common(1)[0][0] if known else None

class InstanceMemory:
    def __init__(self,max_seconds=.65,max_frames=10):
        self.instances={};self.bindings={};self.next_id=1;self.max_seconds=max_seconds;self.max_frames=max_frames

    def _score(self,item,track,now,index,*,bound=False):
        dt=now-track.time
        if track.retired or dt<0 or dt>self.max_seconds or index-track.frame>self.max_frames:return None
        box=item['xyxy_roi'];last=track.box
        area=lambda b:max(1.,(b[2]-b[0])*(b[3]-b[1]))
        if min(area(box),area(last))/max(area(box),area(last))<.15:return None
        color=track.color()
        color_conflict=color and item['color'] in COLORS and item['color']!=color
        if color_conflict and not bound:return None
        predicted=list(last)
        if track.previous:
            old,old_time=track.previous;elapsed=track.time-old_time
            if elapsed>0:
                # A brief extrapolation supports fast hand motion; it never
                # creates an observed position or an admission event.
                scale=min(dt,.20)/elapsed
                dx=(center(last)[0]-center(old)[0])*scale;dy=(center(last)[1]-center(old)[1])*scale
                limit=max(1.,math.hypot(last[2]-last[0],last[3]-last[1]))
                distance=math.hypot(dx,dy)
                if distance>limit:dx*=limit/distance;dy*=limit/distance
                predicted=[last[0]+dx,last[1]+dy,last[2]+dx,last[3]+dy]
        overlap=max(iou(box,last),iou(box,predicted))
        if color_conflict and overlap<.50:return None
        diagonal=max(20.,math.hypot(last[2]-last[0],last[3]-last[1]))
        distance=min(math.dist(center(box),center(last)),math.dist(center(box),center(predicted)))/diagonal
        if overlap<.10 and distance>(1.0 if bound else .65):return None
        score=1.5*overlap+max(0.,1.-distance)-.25*dt/self.max_seconds
        if score<(.30 if bound else .55):return None
        appearance=1. if color and item['color']==color else -.50 if color and item['color']=='unknown' else 0.
        return score+(.10 if bound else 0.)-(.25 if color_conflict else 0.)+appearance

    def update(self,observed,now,index):
        assignments={}
        # Score all visible instances together. A surviving raw ID may have
        # switched between touching cans and must not reserve the wrong one.
        candidates=[identity for identity,track in self.instances.items() if not track.retired and 0<=now-track.time<=self.max_seconds and index-track.frame<=self.max_frames]
        cost=[]
        for item in observed:
            row=[]
            for identity in candidates:
                track=self.instances[identity]
                bound=item['track_id'] is not None and self.bindings.get(item['track_id'])==identity
                score=self._score(item,track,now,index,bound=bound)
                row.append(-score if score is not None and score>0 else 1.e6)
            cost.append(row+[0.]*len(observed))
        for n,column in assign_minimum(cost):
            if column<len(candidates) and cost[n][column]<0:assignments[n]=candidates[column]
        result=[]
        for n,item in enumerate(observed):
            identity=assignments.get(n)
            if identity is None:
                identity=self.next_id;self.next_id+=1
                self.instances[identity]=Instance(identity,list(item['xyxy_roi']),now,index)
            track=self.instances[identity]
            if track.frame!=index:track.previous=(list(track.box),track.time)
            track.box=list(item['xyxy_roi']);track.time=now;track.frame=index
            raw=item['track_id']
            if raw is not None:self.bindings[raw]=identity
            row={**item,'track_id':identity,'tracker_id':raw,'index':index,'instance_memory':True}
            track.history=[r for r in track.history if r['index']>=index-4]+[row]
            result.append(row)
        confirmed={}
        for identity,track in self.instances.items():
            recent=[r for r in track.history if r['index']>=index-4]
            if len(recent)<2 or track.retired:continue
            votes=Counter(r['color'] for r in recent);known=[(votes[c],c) for c in COLORS if votes[c]>=2]
            # Two matching observations can qualify immediately. Conflicting
            # colors tied in the five-frame window must remain unknown.
            winners=[c for count,c in known if count==max(n for n,_ in known)]
            color=winners[0] if len(winners)==1 else 'unknown'
            confirmed[identity]=dict(observations=len(recent),color=color,votes=dict(votes))
        return result,confirmed

    def retire_lost(self,index):
        for track in self.instances.values():
            if track.frame<index:track.retired=True

def context_area(roi,shape,padding=.20):
    fh,fw=shape;x,y,w,h=roi;px=round(w*padding);py=round(h*padding)
    a,b=max(0,x-px),max(0,y-py);c,d=min(fw,x+w+px),min(fh,y+h+py)
    return [a,b,c-a,d-b]

def clipped_edges(box,shape,margin=3):
    h,w=shape;x0,y0,x1,y1=box
    return [name for flag,name in ((x0<=margin,'left'),(y0<=margin,'top'),(x1>=w-margin,'right'),(y1>=h-margin,'bottom')) if flag]
