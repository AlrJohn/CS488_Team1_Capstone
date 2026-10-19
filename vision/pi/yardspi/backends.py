"""Same raw-head contract for ONNX CPU verification and Hailo-8 execution."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from common.geometry import letterbox
from .decoding import decode


class OnnxBackend:
    def __init__(self,path,config):
        import onnxruntime as ort
        options=ort.SessionOptions();options.intra_op_num_threads=4
        self.session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
        self.config=config
        if self.session.get_inputs()[0].shape!=[1,3,config['height'],config['width']]:raise ValueError('ONNX input contract mismatch')
    def predict(self,bgr):
        start=time.perf_counter();rgb,transform=letterbox(bgr,(self.config['height'],self.config['width']))
        tensor=np.ascontiguousarray(rgb.transpose(2,0,1)[None],dtype=np.float32)/255
        pre=time.perf_counter()
        values=self.session.run(None,{self.session.get_inputs()[0].name:tensor});end=time.perf_counter()
        outputs=dict(zip((o.name for o in self.session.get_outputs()),values))
        masks,boxes=decode(outputs,transform,self.config)
        return masks,boxes,dict(preprocess_ms=(pre-start)*1000,inference_ms=(end-pre)*1000,mask_decode_ms=(time.perf_counter()-end)*1000)
    def close(self):pass


class HailoBackend:
    def __init__(self,path,config):
        # A custom HEF needs a compiler-produced identity/normalization contract.
        from hailo_platform import HEF,VDevice,ConfigureParams,HailoStreamInterface,InferVStreams,InputVStreamParams,OutputVStreamParams,FormatType,FormatOrder
        path=Path(path);meta=json.loads(path.with_suffix('.hef.json').read_text())
        if meta.get('sha256')!=hashlib.sha256(path.read_bytes()).hexdigest() or meta.get('architecture')!='hailo8':raise ValueError('HEF identity/architecture mismatch')
        if meta.get('input')!={'layout':'NHWC','range':[0,255],'order':'RGB','shape':[1,config['height'],config['width'],3]}:raise ValueError('HEF input contract mismatch')
        self.stack=ExitStack()
        try:
            hef=HEF(str(path));self.device=self.stack.enter_context(VDevice())
            groups=self.device.configure(hef,ConfigureParams.create_from_hef(hef,interface=HailoStreamInterface.PCIe))
            if len(groups)!=1:raise ValueError('Expected one network group')
            group=groups[0]
            inputs=InputVStreamParams.make(group,quantized=False,format_type=FormatType.FLOAT32)
            outputs=OutputVStreamParams.make(group,quantized=False,format_type=FormatType.FLOAT32)
            # Raw HEF heads may use FCR. Request a consistent host layout as
            # well as float dequantization before handing tensors to OpenCV.
            for params in (inputs,outputs):
                for stream in params.values():
                    stream.user_buffer_format.order=FormatOrder.NHWC
                    if stream.user_buffer_format.order!=FormatOrder.NHWC:raise ValueError('Cannot request NHWC host buffers')
            self.pipeline=self.stack.enter_context(InferVStreams(group,inputs,outputs))
            self.stack.enter_context(group.activate(group.create_params()))
            infos=hef.get_input_vstream_infos()
            if len(infos)!=1 or tuple(infos[0].shape)!=(config['height'],config['width'],3):raise ValueError('HEF input shape mismatch')
            self.input_name=infos[0].name;self.config=config
        except BaseException:
            self.stack.close();raise
    def predict(self,bgr):
        start=time.perf_counter();rgb,transform=letterbox(bgr,(self.config['height'],self.config['width']))
        tensor=np.ascontiguousarray(rgb[None],dtype=np.float32)
        pre=time.perf_counter();outputs=self.pipeline.infer({self.input_name:tensor});end=time.perf_counter()
        masks,boxes=decode(outputs,transform,self.config,layout='NHWC')
        return masks,boxes,dict(preprocess_ms=(pre-start)*1000,inference_ms=(end-pre)*1000,mask_decode_ms=(time.perf_counter()-end)*1000)
    def close(self):self.stack.close()
