import sys
from types import ModuleType

from source_doc_converter import docling_tools_entry


def test_runtime_check_resolves_auto_image_processor(monkeypatch, capsys) -> None:
    class FakeAutoImageProcessor:
        pass

    class FakeDocumentConverter:
        pass

    docling_module = ModuleType("docling")
    converter_module = ModuleType("docling.document_converter")
    converter_module.DocumentConverter = FakeDocumentConverter
    pypdf_module = ModuleType("pypdf")
    pypdf_module.PdfReader = type("FakePdfReader", (), {})
    transformers_module = ModuleType("transformers")
    transformers_module.AutoImageProcessor = FakeAutoImageProcessor
    torch_module = ModuleType("torch")
    torch_module.__version__ = "2.14.0"
    torch_module.tensor = lambda values: values
    torchvision_module = ModuleType("torchvision")
    torchvision_module.__version__ = "0.29.0"
    extension_module = ModuleType("torchvision.extension")
    extension_module._has_ops = lambda: True
    ops_module = ModuleType("torchvision.ops")
    ops_module.nms = lambda boxes, scores, iou_threshold: type("NmsResult", (), {"numel": lambda self: 1})()
    torchvision_module.extension = extension_module
    torchvision_module.ops = ops_module
    scipy_module = ModuleType("scipy")
    ndimage_module = ModuleType("scipy.ndimage")
    ndimage_module.gaussian_filter1d = lambda values, sigma: list(values)
    scipy_module.ndimage = ndimage_module
    scipy_external_module = ModuleType("scipy._external")
    scipy_array_api_module = ModuleType("scipy._external.array_api_compat")
    scipy_array_api_numpy_module = ModuleType("scipy._external.array_api_compat.numpy")
    scipy_array_api_fft_module = ModuleType("scipy._external.array_api_compat.numpy.fft")
    monkeypatch.setitem(sys.modules, "docling", docling_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)
    monkeypatch.setitem(sys.modules, "pypdf", pypdf_module)
    monkeypatch.setitem(sys.modules, "transformers", transformers_module)
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.setitem(sys.modules, "torchvision", torchvision_module)
    monkeypatch.setitem(sys.modules, "torchvision.extension", extension_module)
    monkeypatch.setitem(sys.modules, "torchvision.ops", ops_module)
    monkeypatch.setitem(sys.modules, "scipy", scipy_module)
    monkeypatch.setitem(sys.modules, "scipy.ndimage", ndimage_module)
    monkeypatch.setitem(sys.modules, "scipy._external", scipy_external_module)
    monkeypatch.setitem(sys.modules, "scipy._external.array_api_compat", scipy_array_api_module)
    monkeypatch.setitem(sys.modules, "scipy._external.array_api_compat.numpy", scipy_array_api_numpy_module)
    monkeypatch.setitem(sys.modules, "scipy._external.array_api_compat.numpy.fft", scipy_array_api_fft_module)

    assert docling_tools_entry.run_runtime_check() == 0
    output = capsys.readouterr().out
    assert "Torch: 2.14.0" in output
    assert "Torchvision: 0.29.0" in output
    assert "AutoImageProcessor: FakeAutoImageProcessor" in output
    assert "DocumentConverter: FakeDocumentConverter" in output
    assert "PdfReader: FakePdfReader" in output
    assert "SciPyArrayAPI: scipy._external.array_api_compat.numpy.fft" in output
