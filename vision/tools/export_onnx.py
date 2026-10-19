"""Export a local one-class checkpoint as ten raw segmentation heads."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common.torch_support import setup, raw_model, OUTPUT_NAMES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=ROOT/'models/can-camera-v1.pt')
    parser.add_argument('--output', type=Path, default=ROOT/'runs/build/can-camera-v1.onnx')
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.onnx.json').exists():
        parser.error('Use a new output path; existing exports are preserved.')
    torch = setup()
    net = raw_model(args.model).cpu()
    image = torch.zeros(1, 3, 320, 640)
    with torch.inference_mode():
        values = net(image)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(net, image, str(args.output), input_names=['images'],
        output_names=OUTPUT_NAMES, opset_version=11, dynamo=False, do_constant_folding=True)
    import onnx
    graph = onnx.load(str(args.output))
    onnx.checker.check_model(graph)
    source = hashlib.sha256(args.model.read_bytes()).hexdigest()
    onnx.helper.set_model_props(graph, {'source_sha256': source, 'task': 'segment',
        'classes': 'can', 'input_order': 'RGB', 'input_range': '0..1',
        'outputs': 'raw logits, DFL distances, mask coefficients and prototype'})
    onnx.save(graph, str(args.output))
    metadata = dict(sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        source_sha256=source, input=dict(shape=[1,3,320,640],layout='NCHW',range=[0,1],order='RGB'),
        outputs={name:list(value.shape) for name,value in zip(OUTPUT_NAMES, values)},
        task='segment', classes={'0':'can'}, nms='host', mask_decode='host')
    args.output.with_suffix('.onnx.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(args.output)


if __name__ == '__main__':
    main()
