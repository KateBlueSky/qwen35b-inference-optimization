llama-server -hf bartowski/Qwen_Qwen3.6-35B-A3B-GGUF:F16 --alias qwen-coder --fit on --fit-ctx 24576 -fa on --parallel 1 --host 127.0.0.1 --port 8080 --jinja --metrics --no-mmap 
