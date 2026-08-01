# CPU tuning for poor hardware

Start conservative:
```env
LOCAL_AI_CTX=4096
LOCAL_AI_BATCH=256
LOCAL_AI_UBATCH=64
LOCAL_AI_PARALLEL=1
LOCAL_AI_THREADS=4
LOCAL_AI_CACHE_TYPE_K=q8_0
LOCAL_AI_CACHE_TYPE_V=q8_0
```

If swap appears:
```env
LOCAL_AI_CTX=2048
LOCAL_AI_BATCH=128
LOCAL_AI_UBATCH=32
LOCAL_AI_CACHE_TYPE_K=q4_0
LOCAL_AI_CACHE_TYPE_V=q4_0
```

If stable and RAM allows:
```env
LOCAL_AI_CTX=8192
LOCAL_AI_PREDICT=2048
```

Do not blindly use all CPU threads. Test 2, 4, 6, 8.


## DwarfStar4 / DeepSeek V4 Flash on Intel

Use `conf/local-ai-ds4-intel.env` instead of the 16 GB defaults. Start with:

```env
LOCAL_AI_CTX=8192
LOCAL_AI_BATCH=128
LOCAL_AI_UBATCH=32
LOCAL_AI_PARALLEL=1
LOCAL_AI_THREADS=8
LOCAL_AI_CACHE_TYPE_K=q8_0
LOCAL_AI_CACHE_TYPE_V=q8_0
```

If memory pressure appears, reduce context first, then batch sizes:

```env
LOCAL_AI_CTX=4096
LOCAL_AI_BATCH=64
LOCAL_AI_UBATCH=16
LOCAL_AI_CACHE_TYPE_K=q4_0
LOCAL_AI_CACHE_TYPE_V=q4_0
```

Do not use the DS4 profile on 16 GB RAM. The q2 GGUF is an 80+ GB class model
file and needs a 128 GB class host before it is operationally meaningful.
