"""Decode one-class YOLOv8 segmentation heads without PyTorch on the Pi."""
import math
import cv2
import numpy as np
from common.geometry import Boxes


def output_heads(outputs,config,layout):
    """Match by strict tensor shapes, avoiding compiler-dependent layer names."""
    h,w=config['height'],config['width'];spec={}
    for stride in config['strides']:
        for kind,channels in [('box',4*config['reg_max']),('score',config['classes']),('coeff',config['mask_channels'])]:
            spec[f'{kind}_s{stride}']=(channels,h//stride,w//stride)
    spec['proto']=(config['mask_channels'],h//4,w//4)
    found={}
    for name,value in outputs.items():
        a=np.asarray(value,dtype=np.float32)
        if a.ndim!=4 or a.shape[0]!=1:raise ValueError(f'Expected batch-one raw head: {name} {a.shape}')
        a=a[0] if layout=='NCHW' else a[0].transpose(2,0,1) if layout=='NHWC' else None
        if a is None:raise ValueError('Unknown output layout')
        matches=[key for key,shape in spec.items() if a.shape==shape]
        if len(matches)!=1 or matches[0] in found:raise ValueError(f'Unexpected or duplicate head: {name} {a.shape}')
        found[matches[0]]=a
    if set(found)!=set(spec):raise ValueError(f'Incomplete raw segmentation outputs: {set(spec)-set(found)}')
    return found


def nms(boxes,scores,threshold,limit):
    order=np.argsort(-scores,kind='stable');keep=[]
    while len(order) and len(keep)<limit:
        i=int(order[0]);keep.append(i);rest=order[1:]
        if not len(rest):break
        a=boxes[i];b=boxes[rest]
        wh=np.maximum(0,np.minimum(a[2:],b[:,2:])-np.maximum(a[:2],b[:,:2]))
        inter=wh[:,0]*wh[:,1]
        area=np.prod(np.maximum(0,a[2:]-a[:2]))+np.prod(np.maximum(0,b[:,2:]-b[:,:2]),axis=1)-inter
        overlap=inter/np.maximum(area,1e-7)
        order=rest[overlap<=threshold]
    return np.asarray(keep,dtype=int)


def native_masks(proto,coeff,boxes,shape):
    """Mirror the frozen native mask path, including sub-prototype padding."""
    c,mh,mw=proto.shape;h,w=shape
    logits=(coeff@proto.reshape(c,-1)).reshape(-1,mh,mw)
    gain=min(4*mh/h,4*mw/w)
    pad=(4*mh-round(h*gain)) | (4*mw-round(w*gain))
    factor=4//math.gcd(4,pad | pad//2)
    result=np.zeros((len(logits),h,w),np.uint8)
    xx=np.arange(w)[None,:];yy=np.arange(h)[:,None]
    for i,mask in enumerate(logits):
        if factor>1:mask=cv2.resize(mask,(mw*factor,mh*factor),interpolation=cv2.INTER_LINEAR)
        ih,iw=mask.shape;ratio=min(ih/h,iw/w)
        top,left=round((ih-round(h*ratio))/2-.1),round((iw-round(w*ratio))/2-.1)
        content=mask[top:top+round(h*ratio),left:left+round(w*ratio)]
        full=cv2.resize(content,(w,h),interpolation=cv2.INTER_LINEAR)>0
        x0,y0,x1,y1=boxes[i]
        result[i]=full & (xx>=x0) & (xx<x1) & (yy>=y0) & (yy<y1)
    return result


def decode(outputs,transform,config,layout='NCHW'):
    heads=output_heads(outputs,config,layout)
    boxes=[];scores=[];coeffs=[];reg=config['reg_max']
    for stride in config['strides']:
        logits=heads[f'score_s{stride}'].reshape(-1)
        probability=1/(1+np.exp(-np.clip(logits,-80,80)))
        chosen=np.flatnonzero(probability>config['conf'])
        if not len(chosen):continue
        raw=heads[f'box_s{stride}'].reshape(4,reg,-1)[:,:,chosen]
        raw=np.exp(raw-raw.max(axis=1,keepdims=True));raw/=raw.sum(axis=1,keepdims=True)
        distances=(raw*np.arange(reg,dtype=np.float32)[None,:,None]).sum(axis=1).T
        cols=config['width']//stride
        centers=np.stack((chosen%cols+.5,chosen//cols+.5),axis=1)
        boxes.append(np.concatenate((centers-distances[:,:2],centers+distances[:,2:]),axis=1)*stride)
        scores.append(probability[chosen]);coeffs.append(heads[f'coeff_s{stride}'].reshape(config['mask_channels'],-1)[:,chosen].T)
    shape=transform.original
    if not boxes:return np.zeros((0,*shape),np.uint8),Boxes(np.zeros((0,6)),shape)
    xyxy=np.concatenate(boxes);confidence=np.concatenate(scores);coeff=np.concatenate(coeffs)
    keep=nms(xyxy,confidence,config['iou'],config['max_det'])
    xyxy=xyxy[keep];confidence=confidence[keep];coeff=coeff[keep]
    left,top=transform.padding
    xyxy-=np.array([left,top,left,top],np.float32)
    # Match the frozen version's per-axis gains after the resize is rounded.
    gain_x=round(shape[1]*transform.gain)/shape[1]
    gain_y=round(shape[0]*transform.gain)/shape[0]
    xyxy/=np.array([gain_x,gain_y,gain_x,gain_y],np.float32)
    xyxy[:,[0,2]]=xyxy[:,[0,2]].clip(0,shape[1]);xyxy[:,[1,3]]=xyxy[:,[1,3]].clip(0,shape[0])
    masks=native_masks(heads['proto'],coeff,xyxy,shape)
    valid=masks.any(axis=(1,2))
    data=np.concatenate((xyxy,confidence[:,None],np.zeros((len(xyxy),1),np.float32)),axis=1)
    return masks[valid],Boxes(data[valid],shape)
