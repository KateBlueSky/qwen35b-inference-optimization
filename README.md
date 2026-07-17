# Qwen3.6-35B-A3B Inference Optimization

## Result Summary
Starting from the baseline configuration, I evaluated automatic model placement, model quantization, and KV cache quantization.


| Experiment    | Model  | Decode TPS | Avg Wall Time | Correct |
| ------------- | ------ | ---------: | ------------: | :-----: |
| Baseline      | Q4_K_M |         22 |         111 s |    ✅    |
| Auto Fit      | Q4_K_M |         82 |          55 s |    ✅    |
| Q3_K_M        | Q3_K_M |        130 |          25 s |    ✅    |
| IQ2_M         | IQ2_M  |        175 |          20 s |    ✅    |
| IQ1_M         | IQ1_M  |        210 |          44 s |    ❌    |
| IQ2_M + q8 KV | IQ2_M  |        176 |          21 s |    ✅    |
| IQ2_M + q4 KV | IQ2_M  |        188 |          19 s |   ✅ ⭐   |

### Best configuration
| Setting   | Value   |
| --------- | ------- |
| Model     | IQ2_M   |
| Placement | `--fit` |
| KV Cache  | `q4_0`  |
| Context   | 24576   |


### This configuration achieved
- ~8× decode throughput improvement (≈22 → ≈188 tok/s)
- 84% reduction in task completion time
- ~60% reduction in host RAM usage
- 100% correctness on all benchmark tasks

## Overview

This repository contains my solution for the inference optimization take-home assignment.

The objective was to optimize local inference performance for the
Qwen3.6-35B-A3B model while maintaining coding quality for an OpenClaw
coding-agent workload.

The project includes:

- Automated benchmark harness
- Repeatable OpenClaw workloads
- llama.cpp inference server configuration
- Performance metrics collection
- Benchmark results
- Optimization analysis

---

# Repository Layout

```text
.
├── baseline/
│
├── baseline_with_fit/
│
├── iteration1_quantization/
│   ├── IQ1_M/
│   ├── IQ2_M/
│   ├── Q2_K/
│   ├── Q3_K_M/
│   └── Q5_K_M/
│
├── iteration2_engine/
│
├── iteration3_kvcache/
│   ├── IQ1_M_q4/
│   ├── IQ2_M_q4/
│   ├── IQ2_M_q8/
│   ├── IQ2_S_q4/
│   ├── IQ2_XS_q4/
│   ├── Q2_K_q4/
│   ├── Q3_K_M_q4/
│   └── Q5_K_M_q4/
│
├── openclaw/
│   └── openclaw.json
│
├── scripts/
│   ├── results/
│   ├── tasks/
│   ├── collect_metrics.py
│   ├── requirements.txt
│   ├── reset_openclaw.sh
│   └── start_llama_server.sh
│
└── README.md
```

---

# Hardware

| Component | Value |
|------------|------|
| GPU | NVIDIA GeForce RTX 5080 16GB |
| CPU | AMD Ryzen 9 9900X |
| RAM | 32 GB |
| OS | Ubuntu 24.04 |

---

# Software

| Component | Version |
|------------|---------|
| llama.cpp | build 9992 (6eddde06a) |
| OpenClaw | 2026.7.1 (2d2ddc4) |
| Python | 3.10 |
| CUDA | 13.0 |
| Hugging Face Repo used | bartowski/Qwen_Qwen3.6-35B-A3B-GGUF |

---

# Benchmark Methodology

Each benchmark follows the same procedure.

1. Start llama-server using the start_llama_server.sh script.
2. Wait for server readiness
3. Clean OpenClaw session data and restart OpenClaw service. 
4. Run the collect_metrics.py to execute prompts, collect inference metrics, and execute correctness test.
5. Save logs
6. Repeat

Each experiment starts with a clean working directory to ensure reproducibility.

---


# Setup Challenges

During setup I encountered several issues:

- Determining the correct openclaw.json configuration so that OpenClaw could reliably communicate with the local llama.cpp inference server.
- Figuring out how to start a new session with the openclaw agent.
- Learning the difference between OpenClaw's session management and llama.cpp's session management. 
- Determining the appropriate GPU/CPU offload strategy. llama.cpp's new feature --fit helped a lot with this.
- Selecting a quantization that fit within the 16 GB VRAM budget while maintaining coding quality required several iterations.

These issues were resolved prior to establishing the baseline benchmark.

---

# Problem Understanding

## Clarification Questions

- Is latency more important than throughput?
- Is the target a single-user coding assistant or multiple concurrent users?
- Are alternative inference engines (vLLM, TensorRT-LLM, SGLang, etc.) acceptable, or should optimization focus exclusively on llama.cpp? 
- What types of coding tasks will the assistants be expected to perform, and how long are they typically?

## Assumptions

- Single-user interactive coding workload.
- 16 GB VRAM is a hard limit.
- Correctness is more important than maximizing raw throughput.
- Agent logic should remain unchanged.
- All benchmarks should execute through OpenClaw.
- The benchmark suite consists of representative coding and refactoring tasks.
- All coding problems prompts are in Python 3.10


## Definition of Success

I defined success as achieving the lowest end-to-end task completion time while maintaining correctness on representative coding workloads and staying within the available hardware resources.

---


# Benchmark Tasks

## Task 1

**Hello World**

Purpose

- Verify end-to-end functionality

Success Criteria

- hello.py created
- Program executes successfully

Prompt
- Create hello.py that prints Hello World and save 
  it in /home/riverwest/workspace/claw-performance-Qwen3.6-35B-A3B/
  scripts/tasks/hello-world/hello.py

---

## Task 2

**Two Sum**

Purpose

- Small coding task

Success Criteria

- Implementation generated
- Six pytest tests created
- All tests pass

Prompt
- Create twoSum.py containing a function that finds
  two numbers in a list that sum to a target. Also 
  create testTwoSum.py containing six pytest tests. 
  Save both files in the directory 
  /home/riverwest/workspace/claw-performance-Qwen3.6-35B-A3B/scripts/tasks/two-sum

---

## Task 3

**Refactor**

Purpose

- Multi-step coding task

Success Criteria

- Function refactored
- Edge cases handled
- Six pytest tests generated
- All tests pass

Prompt
- Can you refactor this code 
  def process_orders(orders): 
  total = 0 
  for order in orders:
  total += order['price'] * order['quantity'] 
  return total / len(orders)
  make sure to handle edge cases 
  and create 6 pytest for the code. 
  place the code in a python file named calculator.py
  in the directory /home/riverwest/workspace/claw-performance-Qwen3.6-35B-A3B/scripts/tasks/refactor

---

# Metrics Collected

The benchmark harness records:

- Task wall-clock time
- Exit status
- Correctness
- llama.cpp Prometheus metrics (i.e. llamacpp:tokens_predicted_total, llamacpp:prompt_tokens_total, llamacpp:request_duration_seconds)
- GPU utilization
- GPU memory
- System RAM
- Prompt processing speed
- Decode speed

---

# Baseline Configuration 

| Setting | Value |
|---------|------|
| Model | Qwen3.6-35B-A3B Q4_K_M |
| Context | 24576 |
| KV Cache | q4_0 |
| Flash Attention | Enabled |
| mmap | Disabled |

## Performance [:link:](./baseline)
| Task          | Wall Time (s) | Prompt TPS | Decode TPS | Overall TPS | Pass |
| ------------- | ------------: | ---------: | ---------: | ----------: | :--: |
| Hello World   |         76.58 |     1088.9 |      26.27 |       253.3 |   ✅  |
| Two Sum       |        118.26 |      271.0 |      22.77 |        32.2 |   ✅  |
| Refactor Test |        138.03 |      201.1 |      21.92 |        29.0 |   ✅  |


## Resource Usage 

| Task          | Peak VRAM (GiB) | Avg GPU Util (%) | Peak GPU Util (%) | Peak RAM (GiB) | Peak CPU (%) |
| ------------- | --------------: | ---------------: | ----------------: | -------------: | -----------: |
| Hello World   |            9.62 |            22.96 |                94 |          19.79 |         55.2 |
| Two Sum       |            9.61 |             7.57 |                85 |          20.04 |         57.5 |
| Refactor Test |            9.58 |             7.39 |                91 |          20.04 |         58.2 |


---

# Optimizations Evaluated

## Experiment 1: Optimize model placement with --fit 

| Setting | Value |
|---------|------|
| Model | Qwen3.6-35B-A3B Q4_K_M |
| Context | 24576 |
| KV Cache | q4_0 |
| parallel | 1 |
| fit | on |
| fit-ctx | 24576 |

## Goal

Reduce manual GPU placement tuning using llama.cpp's :

```
--fit
```

## Result

llama.cpp auto fit option results    

Context:           24576  
n_batch:           2048  
n_ubatch:          512  
KV cache:          unified  
Flash Attention:   auto  

Model placement:  
  GPU:  40 transformer blocks were offloaded to the GPU, while the remaining model components stayed on the CPU.  
  GPU model memory:      11.83 GiB  
  CUDA host memory:       9.14 GiB  
  CPU memory:             0.27 GiB  


--fit automatically selected an improved GPU/CPU layer placement, increasing GPU residency from roughly 10 GiB to over 14 GiB. This likely reduced CPU-GPU data movement during inference and increased decode throughput by more than 3×.

### Performance [:link:](./baseline_with_fit)
| Task          | Wall Time (s) | Prompt Tokens | Output Tokens | Prompt TPS | Decode TPS | Overall TPS | Pass |
| ------------- | ------------: | ------------: | ------------: | ---------: | ---------: | ----------: | :--: |
| Hello World   |         32.11 |        17,931 |         1,543 | **1812.5** |  **86.33** |   **606.8** |   ✅  |
| Two Sum       |         45.09 |         3,245 |         3,165 |  **969.5** |  **82.70** |   **142.1** |   ✅  |
| Refactor Test |         88.19 |         3,645 |         6,668 | **1023.9** |  **81.93** |   **116.9** |   ✅  |

### Resource Usage 

| Task          | Peak VRAM (GiB) | Avg GPU Util (%) | Peak GPU Util (%) | Peak RAM (GiB) | Peak CPU (%) | Avg GPU Power (W) |
| ------------- | --------------: | ---------------: | ----------------: | -------------: | -----------: | ----------------: |
| Hello World   |           14.49 |             58.0 |                99 |          15.14 |         53.0 |             135.1 |
| Two Sum       |           14.50 |             53.7 |                99 |          15.31 |         56.0 |             132.0 |
| Refactor Test |           14.49 |             53.7 |                97 |          15.59 |         54.6 |             137.7 |

### Compared with previous run
| Task        | Previous Decode TPS | New Decode TPS | Improvement |
| ----------- | ------------------: | -------------: | ----------: |
| Hello World |               26.27 |      **86.33** |   **+229%** |
| Two Sum     |               22.77 |      **82.70** |   **+263%** |
| Refactor    |               21.92 |      **81.93** |   **+274%** |

| Task        | Previous |        New |    Improvement |
| ----------- | -------: | ---------: | -------------: |
| Hello World |   76.6 s | **32.1 s** | **58% faster** |
| Two Sum     |  118.3 s | **45.1 s** | **62% faster** |
| Refactor    |  138.0 s | **88.2 s** | **36% faster** |

---

## Experiment 2: Reduce model precision while maintaining correctness.

## Goal
Determine the lowest model quantization that maintains benchmark correctness.

# Results 

| Setting | Value |
|---------|------|
| Model | Qwen_Qwen3.6-35B-A3B-GGUF:Q3_K_M |
| Context | 24576 |
| parallel | 1 |
| fit | on |
| fit-ctx | 24576 |

### Performance [:link:](./iteration1_quantization/Q3_K_M) 

| Task          | Wall Time (s) | Prompt Tokens | Output Tokens |  Prompt TPS | Decode TPS | Overall TPS | Pass |
| ------------- | ------------: | ------------: | ------------: | ----------: | ---------: | ----------: | :--: |
| Hello World   |     **22.96** |        17,903 |         1,415 | **2434.13** | **128.21** |   **842.5** |   ✅  |
| Two Sum       |     **28.10** |         1,824 |         3,055 | **1224.16** | **131.14** |   **173.6** |   ✅  |
| Refactor Test |     **23.50** |         1,228 |         2,552 |  **969.22** | **132.16** |   **160.9** |   ✅  |

### Resource Usage

| Task          | Peak VRAM (GiB) | Avg GPU Util (%) | Peak GPU Util (%) | Peak RAM (GiB) | Peak CPU (%) | Avg GPU Power (W) |
| ------------- | --------------: | ---------------: | ----------------: | -------------: | -----------: | ----------------: |
| Hello World   |       **14.48** |            58.96 |                99 |          11.57 |         58.1 |             157.2 |
| Two Sum       |       **14.44** |            53.43 |                59 |          11.63 |         52.8 |             154.2 |
| Refactor Test |       **14.44** |            50.29 |                59 |          11.96 |         51.3 |             152.9 |

### Compared with previous best run
| Metric                | Previous Best |         New |
| --------------------- | ------------: | ----------: |
| Hello World Wall Time |       32.11 s | **22.96 s** |
| Two Sum Wall Time     |       45.09 s | **28.10 s** |
| Refactor Wall Time    |       88.19 s | **23.50 s** |

| Task        |    Previous |              New | Improvement |
| ----------- | ----------: | ---------------: | ----------: |
| Hello World | 86.33 tok/s | **128.21 tok/s** |  **+48.5%** |
| Two Sum     | 82.70 tok/s | **131.14 tok/s** |  **+58.6%** |
| Refactor    | 81.93 tok/s | **132.16 tok/s** |  **+61.3%** |

Decode throughput is now consistently around 130 tok/s, which is excellent consistency across all three workloads.
Prompt throughput increased dramatically as well, especially for the Hello World task.
Peak RAM dropped from about 15–16 GiB to 11–12 GiB, while maintaining essentially the same 14.4–14.5 GiB of VRAM usage.
All three tasks still completed successfully.

| Setting | Value |
|---------|------|
| Model | Qwen_Qwen3.6-35B-A3B-GGUF:IQ2_M |
| Context | 24576 |
| parallel | 1 |
| fit | on |
| fit-ctx | 24576 |

### Performance [:link:](./iteration1_quantization/IQ2_M)

| Task          | Wall Time (s) | Prompt Tokens | Output Tokens |  Prompt TPS | Decode TPS | Overall TPS | Pass |
| ------------- | ------------: | ------------: | ------------: | ----------: | ---------: | ----------: | :--: |
| Hello World   |     **18.59** |        18,024 |         1,641 | **3537.59** | **180.87** |  **1058.0** |   ✅  |
| Two Sum       |     **24.25** |         1,951 |         3,522 | **1752.02** | **174.72** |   **225.7** |   ✅  |
| Refactor Test |     **17.98** |         1,709 |         2,436 | **1633.84** | **172.97** |   **230.6** |   ✅  |

### Resource Usage

| Task          | Peak VRAM (GiB) | Avg GPU Util (%) | Peak GPU Util (%) | Peak RAM (GiB) | Peak CPU (%) | Avg GPU Power (W) |
| ------------- | --------------: | ---------------: | ----------------: | -------------: | -----------: | ----------------: |
| Hello World   |       **14.32** |            67.68 |                96 |           8.03 |         42.3 |             174.8 |
| Two Sum       |       **14.32** |            72.29 |                89 |           8.33 |         42.3 |             174.0 |
| Refactor Test |       **14.32** |            64.89 |                82 |           8.55 |         42.4 |             172.7 |

### Compared with previous best run
| Metric        | Previous Best |         New |      Improvement |
| ------------- | ------------: | ----------: | ---------------: |
| Hello World   |       22.96 s | **18.59 s** | **19.0% faster** |
| Two Sum       |       28.10 s | **24.25 s** | **13.7% faster** |
| Refactor Test |       23.50 s | **17.98 s** | **23.5% faster** |

| Task          |     Previous |              New | Improvement |
| ------------- | -----------: | ---------------: | ----------: |
| Hello World   | 128.21 tok/s | **180.87 tok/s** |  **+41.1%** |
| Two Sum       | 131.14 tok/s | **174.72 tok/s** |  **+33.2%** |
| Refactor Test | 132.16 tok/s | **172.97 tok/s** |  **+30.9%** |


Decode throughput is consistently 173–181 tokens/sec, indicating a well-balanced configuration.
Prompt throughput exceeds 3,500 tok/s on the large initial prompt.
Peak RAM is only 8–8.5 GiB, down substantially from your earlier runs while maintaining essentially the same 14.3 GiB of GPU memory usage.
Average GPU utilization increased to roughly 65–72%, showing the GPU is being kept much busier.
All three tasks still passed their correctness checks.

The lower model quantization reduced model memory, allowing a larger portion of the network to remain resident on the GPU. The resulting increase in GPU utilization improved decode throughput while maintaining correctness.

This became the primary configuration used for subsequent tuning because it delivered the best balance of throughput, memory usage, and correctness.

| Setting | Value |
|---------|------|
| Model | Qwen_Qwen3.6-35B-A3B-GGUF:IQ1_M |
| Context | 24576 |
| parallel | 1 |
| fit | on |
| fit-ctx | 24576 |

### Performance [:link:](./iteration1_quantization/IQ1_M)

| Task          | Wall Time (s) | Prompt TPS | Decode TPS | Overall TPS | Correctness |
| ------------- | ------------: | ---------: | ---------: | ----------: | :---------: |
| Hello World   |         60.75 |     1249.5 |      213.3 |       448.2 |      ✅      |
| Two Sum       |         45.13 |      798.5 |      209.4 |       210.6 |      ❌      |
| Refactor Test |         24.79 |      773.2 |      205.2 |       242.2 |      ✅      |

### Resource Usage

| Task          | Peak VRAM (GiB) | Avg GPU Util (%) | Peak GPU Util (%) | Peak RAM (GiB) | Peak CPU (%) |
| ------------- | --------------: | ---------------: | ----------------: | -------------: | -----------: |
| Hello World   |           14.49 |             83.1 |                97 |           7.56 |          7.3 |
| Two Sum       |           14.51 |             87.7 |                97 |           8.85 |         12.6 |
| Refactor Test |           14.45 |             79.9 |                97 |           8.94 |          7.6 |

Although IQ1_M increased decode throughput by approximately 20%, the generated code failed one of the benchmark tasks, indicating that the reduced model precision negatively affected code generation quality.

## Summary

| Configuration           | Decode TPS | Avg Wall Time | Success Rate |
| ----------------------- | ---------: | ------------: | -----------: |
| Baseline                |      22–26 |         111 s |          3/3 |
| Optimized (Selected)    |    173–181 |          20 s |          3/3 |
| Aggressive Quantization |    205–213 |          44 s |    **2/3** ❌ |



## Experiment 3: Tune KV cache precision to maximize throughput. 

## Goal

Evaluate the effect of KV cache quantization on inference performance using the Qwen_Qwen3.6-35B-A3B-GGUF:IQ2_M model.

### Performance [:link:](./iteration3_kvcache/IQ2_M_q8)

| Setting | Value |
|---------|------|
| Model | Qwen_Qwen3.6-35B-A3B-GGUF:IQ2_M |
| Context | 24576 |
| parallel | 1 |
| fit | on |
| fit-ctx | 24576 |
| ctk | q8_0 |
| ctv | q8_0 |


| Task          | Wall Time (s) | Prompt Tokens | Output Tokens |  Prompt TPS | Decode TPS | Overall TPS | Pass |
| ------------- | ------------: | ------------: | ------------: | ----------: | ---------: | ----------: | :--: |
| Hello World   |     **18.78** |        18,080 |         1,736 | **3445.78** | **183.20** |  **1044.5** |   ✅  |
| Two Sum       |     **25.23** |         3,050 |         3,540 | **2032.65** | **171.64** |   **261.3** |   ✅  |
| Refactor Test |     **19.88** |         1,772 |         2,779 | **1737.25** | **173.72** |   **229.0** |   ✅  |

### Resource Usage
| Task          | Peak VRAM (GiB) | Avg GPU Util (%) | Peak GPU Util (%) | Peak RAM (GiB) | Peak CPU (%) | Avg GPU Power (W) |
| ------------- | --------------: | ---------------: | ----------------: | -------------: | -----------: | ----------------: |
| Hello World   |       **14.47** |            76.05 |                99 |           7.21 |        100.0 |             200.6 |
| Two Sum       |       **14.47** |            77.56 |                96 |           7.60 |          8.2 |             203.5 |
| Refactor Test |       **14.46** |            85.05 |                96 |           7.55 |          8.2 |             199.8 |

### Compared with previous best run
| Metric                | Previous Best |    This Run |
| --------------------- | ------------: | ----------: |
| Hello World Wall Time |   **18.59 s** |     18.78 s |
| Two Sum Wall Time     |   **24.25 s** |     25.23 s |
| Refactor Wall Time    |       17.98 s | **19.88 s** |

| Task        |         Previous |         This Run |
| ----------- | ---------------: | ---------------: |
| Hello World |     180.87 tok/s | **183.20 tok/s** |
| Two Sum     | **174.72 tok/s** |     171.64 tok/s |
| Refactor    |     172.97 tok/s | **173.72 tok/s** |

This configuration produced performance nearly identical to the previous experiment, indicating that decreasing the KV cache precision from FP16 to q8_0 provided little measurable benefit for these workloads.

| Setting | Value |
|---------|------|
| Model | Qwen_Qwen3.6-35B-A3B-GGUF:IQ2_M |
| Context | 24576 |
| parallel | 1 |
| fit | on |
| fit-ctx | 24576 |
| ctk | q4_0 |
| ctv | q4_0 |


### Performance [:link:](./iteration3_kvcache/IQ2_M_q4)

| Task          | Wall Time (s) | Prompt Tokens | Output Tokens |  Prompt TPS | Decode TPS | Overall TPS | Pass |
| ------------- | ------------: | ------------: | ------------: | ----------: | ---------: | ----------: | :--: |
| Hello World   |     **17.61** |        17,996 |         1,689 | **3794.22** | **192.94** |  **1117.7** |   ✅  |
| Two Sum       |     **18.17** |         1,703 |         2,705 | **1730.69** | **187.86** |   **242.6** |   ✅  |
| Refactor Test |     **20.21** |         2,598 |         2,962 | **1979.85** | **187.84** |   **275.1** |   ✅  |

### Resource Usage

| Task          | Peak VRAM (GiB) | Avg GPU Util (%) | Peak GPU Util (%) | Peak RAM (GiB) | Peak CPU (%) | Avg GPU Power (W) |
| ------------- | --------------: | ---------------: | ----------------: | -------------: | -----------: | ----------------: |
| Hello World   |       **14.45** |            68.61 |                99 |           7.59 |          7.3 |             203.3 |
| Two Sum       |       **14.46** |            76.78 |                96 |           7.99 |          7.2 |             197.7 |
| Refactor Test |       **14.46** |            85.75 |                97 |           8.15 |          7.3 |             204.3 |


### Compared with previous best run
| Metric                | Previous Best |    This Run |
| --------------------- | ------------: | ----------: |
| Hello World Wall Time |       18.59 s | **17.61 s** |
| Two Sum Wall Time     |       24.25 s | **18.17 s** |
| Refactor Wall Time    |   **17.98 s** |     20.21 s |

| Task          | Previous Best |         This Run |
| ------------- | ------------: | ---------------: |
| Hello World   |  180.87 tok/s | **192.94 tok/s** |
| Two Sum       |  174.72 tok/s | **187.86 tok/s** |
| Refactor Test |  172.97 tok/s | **187.84 tok/s** |


The q4_0 KV cache consistently achieved higher decode throughput while preserving correctness, suggesting that the reduced KV cache precision was sufficient for these tasks and reduced memory bandwidth enough to outweigh any potential accuracy benefit.

### Conclusion 
For the coding tasks, a q4_0 KV cache provided the best balance of throughput and correctness. Upgrading the KV cache to q8_0 increased precision but did not produce measurable performance or quality improvements.

## Tradeoffs

### Throughput vs. Correctness

Lower model quantization substantially improved inference speed.
However, reducing the model to IQ1_M introduced correctness failures,
demonstrating that throughput gains must be balanced against coding quality.

### Model Size vs. Memory

More aggressive model quantization reduced host memory usage while
allowing more of the model to remain resident on the GPU.

### KV Cache Precision

For these workloads, reducing KV cache precision from q8_0 to q4_0
improved throughput without affecting correctness, suggesting that
memory bandwidth was a larger bottleneck than KV cache precision.

---

# Future Work

- Benchmark all three tasks within a single persistent OpenClaw session instead of isolated sessions.  
- Compare persistent-session performance against the current isolated-session benchmark methodology.  
- Measure the impact of session reuse on throughput, latency, and correctness.  
- Evaluate speculative decoding with a smaller draft model.  
- Benchmark multiple concurrent OpenClaw sessions.    
- Measure throughput under continuous batching.  
- Compare additional GGUF quantizations (IQ3_M, IQ3_S, etc.).  
- Evaluate larger context windows and their impact on throughput and memory.  
- Compare llama.cpp against vLLM for the same coding-agent workload.
- Evaluate on a more representative real-world benchmark such as SWE-bench and SWE-bench Multilingual to measure performance across multiple programming languages.     


---

# Reproducibility

Example server launch

```bash
./scripts/start_llama_server.sh \
    Q4_K_M \
    99 \
    16 \
    24576 \
    q4_0 \
    q4_0
```
Use the provided `openclaw.json` configuration before running the benchmark harness.

Run benchmarks

```bash
python scripts/benchmark.py
```

Results are written to

```
results/
```

---

## Conclusions

Starting from the baseline configuration, I evaluated automatic model
placement, model quantization, and KV cache quantization for the
Qwen3.6-35B-A3B model running under llama.cpp.

The largest performance gains came from enabling automatic model fitting
and selecting the IQ2_M model quantization. Together these changes
increased decode throughput from approximately 22 tokens/sec to nearly
188 tokens/sec while reducing end-to-end task completion time by more
than 80%.

Further reducing the model to IQ1_M increased raw throughput beyond
200 tokens/sec but introduced correctness failures on one benchmark
task, demonstrating the tradeoff between aggressive quantization and
coding quality.

The best overall configuration used the IQ2_M model with `--fit` and a
`q4_0` KV cache, providing the best balance of throughput, memory
efficiency, and correctness.
