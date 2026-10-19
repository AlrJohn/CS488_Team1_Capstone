"""Compile an exported one-class ONNX segmenter with Hailo DFC 3.34.0."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Otherwise report prerequisites only')
    parser.add_argument('--onnx', type=Path, default=ROOT/'runs/build/can-camera-v1.onnx')
    parser.add_argument('--calibration', type=Path, default=ROOT/'runs/build/calibration-rgb.npy')
    parser.add_argument('--output', type=Path, default=ROOT/'runs/build/can-camera-v1.hef')
    args = parser.parse_args()
    present = importlib.util.find_spec('hailo_sdk_client') is not None
    version = importlib.metadata.version('hailo-dataflow-compiler') if present else None
    ready = platform.system() == 'Linux' and platform.machine() in ('x86_64','AMD64') and version == '3.34.0'
    print(json.dumps(dict(platform=platform.system(),architecture='hailo8',compiler=version,ready=ready)))
    if not args.run:
        return
    if not ready:
        parser.error('Use the separate Linux x86-64 DFC 3.34.0 environment. The Pi needs HailoRT, not this compiler.')
    if args.output.exists() or args.output.with_suffix('.hef.json').exists():
        parser.error('Use a new build output; the shipped model is preserved.')
    import numpy as np
    from hailo_sdk_client import ClientRunner
    onnx_meta = json.loads(args.onnx.with_suffix('.onnx.json').read_text())
    cal_meta = json.loads(args.calibration.with_suffix('.json').read_text())
    if hashlib.sha256(args.onnx.read_bytes()).hexdigest() != onnx_meta['sha256']:
        raise ValueError('ONNX checksum mismatch')
    if hashlib.sha256(args.calibration.read_bytes()).hexdigest() != cal_meta['sha256']:
        raise ValueError('Calibration checksum mismatch')
    data = np.load(args.calibration)
    if data.ndim != 4 or tuple(data.shape[1:]) != (320,640,3) or data.dtype != np.uint8:
        raise ValueError('Expected Nx320x640x3 RGB uint8 calibration')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    runner = ClientRunner(hw_arch='hailo8')
    runner.translate_onnx_model(str(args.onnx),'yards_can_v4',net_input_shapes={'images':[1,3,320,640]})
    runner.save_har(str(args.output.with_suffix('.parsed.har')))
    runner.load_model_script('normalization1 = normalization([0.0, 0.0, 0.0], [255.0, 255.0, 255.0])\n')
    runner.optimize(data)
    runner.save_har(str(args.output.with_suffix('.quantized.har')))
    args.output.write_bytes(runner.compile())
    metadata = dict(sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        architecture='hailo8',compiler_version=version,documented_hailort_version='4.24.0',
        source_checkpoint_sha256=onnx_meta['source_sha256'],source_onnx_sha256=onnx_meta['sha256'],
        calibration_sha256=cal_meta['sha256'],input=dict(layout='NHWC',range=[0,255],order='RGB',shape=[1,320,640,3]),
        outputs=onnx_meta['outputs'],output_layout='NHWC',nms='host',mask_decode='host',
        hardware_validated=False,status='New build; compare against original model and test on the actual HAT before use')
    args.output.with_suffix('.hef.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(args.output)


if __name__ == '__main__':
    main()
