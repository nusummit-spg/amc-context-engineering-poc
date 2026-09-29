"""
Export GLiNER to ONNX INT8 quantized format.
Generates models/gliner_quantized.onnx (~95MB, down from ~380MB fp32).
"""
import os
import sys
from pathlib import Path
import torch

MODEL_ID = os.environ.get("GLINER_MODEL_ID", "urchade/gliner_medium-v2.1")
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "models"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def export_to_onnx():
    from gliner import GLiNER

    print(f"Loading GLiNER model: {MODEL_ID}...")
    try:
        model = GLiNER.from_pretrained(MODEL_ID, local_files_only=True)
    except Exception:
        model = GLiNER.from_pretrained(MODEL_ID)

    # Save tokenizer and config files to models directory for self-contained runtime loading
    print(f"Saving base configuration and tokenizer to {OUTPUT_DIR}...")
    try:
        model.save_pretrained(str(OUTPUT_DIR))
    except Exception as exc:
        print(f"Notice: save_pretrained skipped or partial: {exc}")

    quantized_path = OUTPUT_DIR / "gliner_quantized.onnx"
    fp32_path = OUTPUT_DIR / "gliner_medium_fp32.onnx"

    print(f"Exporting model to ONNX via export_to_onnx...")
    try:
        if hasattr(model, "export_to_onnx"):
            model.export_to_onnx(
                save_dir=str(OUTPUT_DIR),
                onnx_filename="gliner_medium_fp32.onnx",
                quantized_filename="gliner_quantized.onnx",
                quantize=True,
                opset=17,
            )
        else:
            raise AttributeError("GLiNER instance has no export_to_onnx method")
    except Exception as exc:
        print(f"Native export_to_onnx encountered: {exc}. Using onnxruntime dynamic quantization fallback...")
        from onnxruntime.quantization import quantize_dynamic, QuantType

        dummy_input = {
            "input_ids": torch.randint(0, 1000, (1, 128)),
            "attention_mask": torch.ones(1, 128, dtype=torch.long),
        }
        torch.onnx.export(
            model.model,
            (dummy_input,),
            str(fp32_path),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch_size", 1: "sequence"},
                "attention_mask": {0: "batch_size", 1: "sequence"},
                "logits": {0: "batch_size", 1: "sequence"}
            },
            opset_version=14
        )
        quantize_dynamic(
            str(fp32_path),
            str(quantized_path),
            weight_type=QuantType.QInt8,
        )

    # If the exported file was named model_quantized.onnx or similar, ensure gliner_quantized.onnx exists
    if not quantized_path.exists():
        candidates = list(OUTPUT_DIR.glob("*quant*.onnx")) + list(OUTPUT_DIR.glob("*.onnx"))
        if candidates:
            import shutil
            shutil.copy(str(candidates[0]), str(quantized_path))
            print(f"Copied {candidates[0].name} -> {quantized_path.name}")

    if quantized_path.exists():
        size_mb = quantized_path.stat().st_size / (1024 * 1024)
        print(f"Export complete! ONNX model ready at: {quantized_path} ({size_mb:.2f} MB)")
    else:
        print(f"Warning: {quantized_path} not found after export.")

if __name__ == "__main__":
    export_to_onnx()
