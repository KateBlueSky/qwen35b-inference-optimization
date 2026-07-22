# Inference Runtime Optimization for Qwen3.6-35B-A3B
### Intel Take-Home Project – Inference Optimization Engineer

## Overview

This repository documents the optimization of the **Qwen3.6-35B-A3B** Mixture-of-Experts model running as the backend for **open-claw** on a constrained workstation.

The goal of this project was to:

- Run a 35B MoE model on a **16 GB RTX 5080**
- Establish an end-to-end baseline using open-claw
- Iteratively optimize inference performance
- Measure improvements using representative coding tasks
- Analyze trade-offs between latency, throughput, memory usage, and task reliability

---

# System Configuration

| Component | Specification |
|-----------|---------------|
| OS | Ubuntu 24.04 |
| GPU | NVIDIA GeForce RTX 5080 (16 GB VRAM) |
| CPU | AMD Ryzen 9 9900X (12 cores / 24 threads) |
| Memory | 32 GB DDR5 |
| CUDA | CUDA 12.x |
| Inference Engine | llama.cpp |
| Agent | open-claw |

---

# Repository Layout

```
.
├── README.md
├── report/
│   └── inference_optimization_report.md
├── scripts/
│   ├── start_llama_server.sh
│   ├── collect_metrics.py
│   └── benchmark.py
├── configs/
├── tasks/
├── results/
│   ├── baseline/
│   ├── iteration1/
│   ├── iteration2/
│   ├── iteration3/
│   └── summary/
└── logs/
```

---

# Phase 1 – Baseline

The baseline configuration used:

- llama.cpp
- Q4_K_M GGUF quantization
- Flash Attention enabled
- GPU layer offloading
- open-claw running representative coding tasks

Representative workloads:

- Hello World
- Two Sum
- Python Refactoring + Unit Tests

Baseline metrics collected included:

- Total task runtime
- Time-to-first-token (TTFT)
- Decode throughput
- GPU utilization
- CPU utilization
- VRAM usage
- System RAM usage
- Power consumption
- Task correctness

---

# Phase 2 – Optimization Iterations

Several optimization passes were performed.

## Iteration 1

### Goal

Optimize GPU utilization and reduce task runtime.

### Changes

- Increased GPU layer offload
- Enabled Flash Attention
- Tuned CPU worker threads

### Result

Improved overall task latency while maintaining task correctness.

---

## Iteration 2

### Goal

Reduce memory overhead.

### Changes

- Tested alternative KV cache quantization
- Reduced CPU memory traffic
- Tuned context size

### Result

Lower memory usage with minimal impact on generation quality.

---

## Iteration 3

### Goal

Maximize end-to-end throughput.

### Changes

- Tuned batch parameters
- Optimized model placement
- Additional llama.cpp runtime configuration

### Result

Produced the fastest stable configuration for open-claw workloads.

---

# Results Summary

| Configuration | Runtime | TTFT | Tokens/sec | Peak VRAM | Peak RAM | Success |
|---------------|---------|------|------------|-----------|----------|---------|
| Baseline | | | | | | |
| Iteration 1 | | | | | | |
| Iteration 2 | | | | | | |
| Iteration 3 | | | | | | |

---

# Key Findings

- GPU offloading had the largest impact on overall performance.
- Flash Attention significantly reduced prompt processing latency.
- KV cache quantization reduced memory usage with minimal quality loss.
- CPU thread tuning improved utilization during prompt evaluation.
- End-to-end agent runtime is a more meaningful metric than raw token throughput alone.

---

# Reproducing the Results

## 1. Clone the repository

```bash
git clone <repo>
cd <repo>
```

## 2. Build llama.cpp

```bash
cmake -B build
cmake --build build -j
```

## 3. Start the inference server

```bash
./scripts/start_llama_server.sh
```

## 4. Run benchmarks

```bash
python scripts/benchmark.py
```

## 5. Collect metrics

```bash
python scripts/collect_metrics.py
```

Results will be written to:

```
results/
```

---

# Measurement Methodology

Each configuration was evaluated using identical open-claw tasks.

Metrics collected:

- Wall-clock execution time
- Time-to-first-token
- Decode throughput
- Prompt throughput
- GPU utilization
- CPU utilization
- VRAM usage
- RAM usage
- GPU power
- GPU temperature
- Task correctness

---

# Trade-offs

| Optimization | Benefit | Cost |
|--------------|---------|------|
| Higher GPU offload | Faster inference | Higher VRAM usage |
| KV cache quantization | Lower memory usage | Slight quality degradation |
| Larger context | Better agent reasoning | Increased latency |
| Aggressive batching | Higher throughput | Longer TTFT |

---

# Future Work

Given additional time, the next areas to investigate would include:

- TensorRT-LLM
- SGLang
- KTransformers
- Continuous batching
- Speculative decoding
- Multi-session KV cache reuse
- Additional GGUF quantization strategies

---

# Report

A detailed analysis of the optimization process, experimental methodology, benchmark results, and conclusions is available in:

```
report/inference_optimization_report.md
```

---

# Acknowledgements

This repository was created as part of the Intel Inference Optimization Engineer take-home project focused on optimizing large language model inference for agentic coding workloads.
