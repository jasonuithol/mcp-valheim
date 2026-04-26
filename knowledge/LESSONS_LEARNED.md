# mcp-knowledge: Lessons Learned

Notes from building, integrating, and seeding the knowledge service.
Written 2026-04-13 after the initial bring-up.

---

## ChromaDB embedding model downloads at runtime

ChromaDB's default embedding function (`all-MiniLM-L6-v2`, 79MB ONNX model)
downloads from S3 the first time you embed anything. Inside a container this
means:

- First `seed_docs` or `seed_decompile` call blocks for minutes while it downloads
- If the container is recreated, it downloads again

**Fix:** Download the model once on the host (scripted in `build-container.sh`),
mount it into the container at `/root/.cache/chroma/onnx_models/all-MiniLM-L6-v2`.
Zero runtime downloads.

---

## ChromaDB has a max batch size of 5,461

`collection.upsert()` silently accepts large lists but ChromaDB throws
`InternalError: Batch size of N is greater than max batch size of 5461` if
you exceed it. A full DLL decompile produces ~16,000 chunks.

**Fix:** Batch upserts in groups of 5,000.

---

## onnxruntime-gpu is a meta-package

Do NOT `pip uninstall onnxruntime` after installing `onnxruntime-gpu`.
The GPU package is a thin wrapper that depends on the base `onnxruntime`
package. Removing it leaves an empty namespace with no actual runtime.

Symptom: `module 'onnxruntime' has no attribute '__version__'`

**Fix:** Install both. `onnxruntime-gpu` adds GPU providers alongside the
existing CPU provider.

---

## CDI device injection gives you the driver, not CUDA

The NVIDIA Container Toolkit + CDI spec (`--device nvidia.com/gpu=all`)
injects the GPU device nodes and driver libraries into the container. But
it does NOT provide CUDA toolkit libraries (`libcublas`, `libcudnn`, etc.).

Symptom: `get_available_providers()` lists `CUDAExecutionProvider` but
embedding falls back to CPU with `libcublas.so.12: cannot open shared object file`

**Fix:** Use `nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04` as the base
image instead of `python:3.12-slim-bookworm`. This provides the CUDA + cuDNN
runtime libraries that `onnxruntime-gpu` links against.

---

## Full DLL decompile output breaks shell argument limits

`assembly_valheim.dll` decompiles to ~143,000 lines. Passing this through
shell variables or command-line arguments hits `Argument list too long`.

**Fix:** Write decompile output to a temp file, then build the JSON payload
in Python reading from the file, piped directly to curl via stdin
(`--data-binary @-`). Never materialize the full payload as a shell variable.

---

## Decompiled C# produces duplicate chunk IDs

Two sources of duplicates:

1. **Overloaded methods** — multiple methods named `Invoke` in the same class
   produce the same ID `decompile/assembly_valheim/RoutedMethod/Invoke`.
2. **Generic class variants** — `RoutedMethod<T>` and `RoutedMethod<T,U>` both
   have class name `RoutedMethod` after the regex strips generics.

**Fix:** Two-level dedup. Per-class counter for overloaded methods (appends
`_2`, `_3`, etc.), plus a global pass after all chunks are generated to catch
cross-class duplicates.

---

## The method extraction regex is too greedy

The regex that splits decompiled source by method boundaries also matches
C# keywords like `foreach`, `if`, `delegate` when they appear at the
expected indentation level. This creates junk chunks.

**Status:** Known issue, not yet fixed. The chunks are low quality but
harmless — they get low similarity scores and rarely surface in queries.
A proper fix would use a C# parser or at least require a return type
before the method name.

---

## TensorRT warnings are harmless

When CUDA is available, `onnxruntime-gpu` also tries TensorRT. It fails
with `libnvinfer.so.10: cannot open shared object file` and falls back to
CUDA. This is expected and doesn't affect functionality. The warning is
noisy but can't be suppressed without code changes to ChromaDB.

---

## seed_decompile should accept bulk input

The original design had `seed_decompile(class_name, decompiled_source)` —
one class at a time. This meant decompiling the full DLL and then somehow
splitting and looping in a shell script, or decompiling the DLL once per
class (wasteful).

**Fix:** Changed to `seed_decompile(decompiled_source)` — accepts output
from a single class or an entire DLL. The chunker splits by class
boundaries automatically using a regex on class declarations. One decompile
call, one seed call.

---

## NVIDIA Container Toolkit is host infrastructure

The toolkit (`nvidia-ctk`, CDI spec generation) must be installed on the
host, not inside any container. It teaches the container runtime (podman)
how to expose GPUs. Scripted in `setup-gpu.sh` for reproducibility.

Requires sudo for:
- Adding the NVIDIA apt repository
- Installing the toolkit package
- Generating the CDI spec at `/etc/cdi/nvidia.yaml`
