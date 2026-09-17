## 🎯 **Streaming Implementation Plan**

### **Phase 1: Backend Streaming Infrastructure** 

#### **1.1 LLM Client Streaming Support**
**File: `backend/app/core/llm.py`**

**Changes:**
- Add `complete_stream()` and `complete_structured_stream()` methods
- Implement provider-specific streaming:
  - Groq: Use `stream=True` parameter
  - OpenAI: Use `stream=True` with delta parsing
  - Gemini: Use `stream=True` with chunk parsing
- Yield text chunks as they arrive with error recovery

**Edge Cases:**
- **Rate limit mid-stream**: Buffer chunks, retry with exponential backoff, resume
- **Connection timeout**: Detect stalled streams (no chunks for 30s), reconnect transparently
- **Partial JSON in structured mode**: Buffer until valid JSON, validate incrementally
- **Provider switch mid-stream**: If fallback triggered, send continuation marker to client
- **Token limit exceeded**: Graceful truncation with warning chunk

#### **1.2 Orchestrator Streaming Integration**
**File: `backend/app/retrieval/orchestrator.py`**

**Changes:**
- Convert `answer()` to `answer_stream()` generator function
- Stream progress updates for each pipeline step:
  - Step 0-6: Send metadata chunks (intent, entities, sources)
  - Step 7: Stream LLM synthesis chunks
- Use async generators (`async def answer_stream() -> AsyncGenerator[dict, None]`)

**Edge Cases:**
- **Cache hit**: Stream complete cached response immediately
- **Early termination**: Client disconnect detection, cleanup resources
- **Step failure**: Stream error chunk with context, continue with degraded response
- **Multi-turn context**: Preserve conversation state if stream interrupted

#### **1.3 FastAPI SSE Endpoints**
**Files: `backend/app/api/routes/query.py`, `backend/app/api/routes/chat.py`**

**Add new streaming endpoints:**
```python
@router.post("/stream", response_class=StreamingResponse)
async def query_stream(request: QueryRequest, container: Container = Depends(get_container)):
    return StreamingResponse(
        _stream_generator(request, container),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive"
        }
    )

@router.post("/chat/stream", response_class=StreamingResponse)
async def chat_stream(request: ChatRequest, container: Container = Depends(get_container)):
    return StreamingResponse(
        _chat_stream_generator(request, container),
        media_type="text/event-stream"
    )
```

**Stream event format (SSE):**
```
event: metadata
data: {"type":"intent","intent":"pricing_query","confidence":0.92}

event: sources
data: {"type":"sources","sources":[...]}

event: chunk
data: {"type":"answer_chunk","text":"The pricing for","index":0}

event: chunk
data: {"type":"answer_chunk","text":" AMC Master is","index":1}

event: done
data: {"type":"complete","response_id":"resp_abc123"}

event: error
data: {"type":"error","message":"LLM timeout","recoverable":true}
```

**Edge Cases:**
- **Client disconnect**: Use `request.is_disconnected()` check, log metrics, cleanup
- **Slow consumer**: Implement backpressure with bounded queue (max 100 chunks)
- **Double streaming**: Prevent concurrent streams per session_id
- **Legacy fallback**: If streaming fails, return synchronous response
- **CORS preflight**: Handle OPTIONS requests properly for streaming

---

### **Phase 2: Frontend Streaming Consumption**

#### **2.1 Streaming API Client**
**File: `mf-context-engine/src/services/api.js`**

**Add streaming functions:**
```javascript
export async function sendQueryStream({ query, mode = "both", top_k = 8, onChunk, onMetadata, onError, onComplete }) {
  const response = await fetch(`${API_BASE}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode, top_k }),
  });

  if (!response.ok) {
    throw new Error(`Stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // Keep incomplete line

      for (const line of lines) {
        if (!line.trim() || line.startsWith(":")) continue;
        
        if (line.startsWith("event:")) {
          const eventType = line.slice(6).trim();
          continue;
        }
        
        if (line.startsWith("data:")) {
          const data = JSON.parse(line.slice(5).trim());
          
          if (data.type === "answer_chunk") {
            onChunk(data);
          } else if (data.type === "metadata" || data.type === "sources") {
            onMetadata(data);
          } else if (data.type === "error") {
            onError(data);
          } else if (data.type === "complete") {
            onComplete(data);
          }
        }
      }
    }
  } catch (err) {
    onError({ message: err.message, recoverable: false });
  } finally {
    reader.releaseLock();
  }
}
```

**Edge Cases:**
- **Network interruption**: Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s max)
- **Malformed SSE**: Skip invalid lines, continue streaming
- **Partial JSON**: Buffer until complete, validate before parsing
- **Tab visibility**: Pause/resume streaming when tab inactive
- **Memory leak**: Clear chunk buffers after 1000 chunks

#### **2.2 React Streaming UI Component**
**File: `mf-context-engine/src/views/ChatTab.jsx`**

**Changes:**
```javascript
const [streamingAnswer, setStreamingAnswer] = useState("");
const [isStreaming, setIsStreaming] = useState(false);
const [streamMetadata, setStreamMetadata] = useState(null);

const sendChatMessage = async () => {
  setIsStreaming(true);
  setStreamingAnswer("");
  
  try {
    await sendChatStream({
      query: chatQuery,
      history: history.filter(m => !m.loading),
      session_id: chatSessionId,
      mode: "contextgraph",
      
      onChunk: (chunk) => {
        setStreamingAnswer(prev => prev + chunk.text);
      },
      
      onMetadata: (meta) => {
        setStreamMetadata(prev => ({ ...prev, ...meta }));
      },
      
      onError: (error) => {
        if (error.recoverable) {
          pushToast(`Streaming issue: ${error.message}`, "⚠️");
        } else {
          setHistory(prev => [...prev.slice(0, -1), {
            role: "assistant",
            content: { error: error.message },
            error_hybrid: error.message
          }]);
        }
      },
      
      onComplete: (data) => {
        setHistory(prev => [...prev.slice(0, -1), {
          role: "assistant",
          content: { 
            answer: { answer: streamingAnswer, ...streamMetadata },
            sources: streamMetadata?.sources || [],
            response_id: data.response_id
          },
          hybrid: { ...streamMetadata, answer: streamingAnswer }
        }]);
        setIsStreaming(false);
      }
    });
  } catch (err) {
    pushToast(`Failed to send message: ${err.message}`, "❌");
    setIsStreaming(false);
  }
};
```

**Streaming display component:**
```jsx
{isStreaming && (
  <div className="streaming-answer">
    <MarkdownRenderer content={streamingAnswer} />
    <span className="cursor-blink">▊</span>
  </div>
)}
```

**Edge Cases:**
- **Fast typing**: Debounce 50ms to avoid re-render storms
- **Long answers**: Virtualize rendering for >10k characters
- **Markdown parsing**: Parse incrementally, handle incomplete syntax
- **Stop button**: Add abort controller, send disconnect signal
- **Resume after error**: Allow retry from last successful chunk

---

### **Phase 3: Advanced Streaming Features**

#### **3.1 Progressive Citation Rendering**
**Display sources as they're identified, before full answer completes**

**Implementation:**
```jsx
const [progressiveSources, setProgressiveSources] = useState([]);

onMetadata: (meta) => {
  if (meta.type === "sources") {
    setProgressiveSources(prev => [...prev, ...meta.sources]);
  }
}

// Render sources panel while streaming
<SourcesPanel sources={progressiveSources} partial={isStreaming} />
```

#### **3.2 Streaming Analytics & Telemetry**
**Track streaming performance metrics**

**Metrics to capture:**
- Time-to-first-chunk (TTFC)
- Chunks per second
- Total streaming duration
- Client-side buffering delays
- Reconnection count
- Completion rate

**Implementation:**
```javascript
const streamMetrics = {
  startTime: Date.now(),
  firstChunkTime: null,
  chunkCount: 0,
  reconnections: 0,
};

onChunk: (chunk) => {
  if (!streamMetrics.firstChunkTime) {
    streamMetrics.firstChunkTime = Date.now();
    const ttfc = streamMetrics.firstChunkTime - streamMetrics.startTime;
    console.log(`TTFC: ${ttfc}ms`);
  }
  streamMetrics.chunkCount++;
}
```

#### **3.3 Hybrid Streaming + Caching**
**Use semantic cache for instant streaming replay**

**Strategy:**
- Check cache before streaming
- If hit: Stream cached response instantly (simulate typing effect)
- If miss: Stream live, cache chunks for future use
- TTL: 1 hour for intent cache, 24h for full responses

#### **3.4 Graceful Degradation**
**Fallback chain when streaming unavailable**

**Priority order:**
1. **Streaming endpoint** (best UX)
2. **Chunked transfer encoding** (if SSE blocked)
3. **Polling with incremental results** (if streaming blocked by firewall)
4. **Full synchronous response** (compatibility mode)

**Detection logic:**
```javascript
async function detectStreamingSupport() {
  try {
    const response = await fetch(`${API_BASE}/health/stream-test`, {
      method: "GET",
      headers: { "Accept": "text/event-stream" }
    });
    return response.headers.get("Content-Type")?.includes("event-stream");
  } catch {
    return false;
  }
}
```

---

### **Phase 4: Complex Edge Cases & Error Recovery**

#### **4.1 Mid-Stream Failures**

**Scenario: LLM provider fails after 50% completion**

**Recovery Strategy:**
1. Detect failure in orchestrator
2. Stream error event: `{"type":"error","recoverable":true,"checkpoint":"50%"}`
3. Trigger fallback provider
4. Continue streaming with marker: `[Continued from backup provider]`
5. Log seamless failure for monitoring

#### **4.2 Client Reconnection**

**Scenario: Network drops, user still on page**

**Implementation:**
- **Server-side**: Store stream state with response_id for 5 minutes
- **Client-side**: Send `Last-Event-ID` header on reconnect
- **Resume from checkpoint**: Server resends from last acknowledged chunk

```python
@router.post("/stream/resume/{response_id}")
async def resume_stream(response_id: str, last_event_id: int = 0):
    cached_chunks = stream_cache.get(response_id)
    for chunk in cached_chunks[last_event_id:]:
        yield chunk
```

#### **4.3 Concurrent Streaming Limits**

**Scenario: User sends 5 queries simultaneously**

**Protection:**
- Max 2 concurrent streams per session_id
- Queue additional requests
- Show "Previous query still processing" warning
- Cancel old stream on new request option

#### **4.4 Streaming + Traditional Mode**

**Scenario: User requests "both" mode (traditional + contextgraph)**

**Strategy:**
- Stream traditional results first (faster)
- Stream contextgraph results in parallel
- Merge streams with event tags: `event: traditional_chunk`, `event: hybrid_chunk`
- Frontend renders side-by-side streaming panels

#### **4.5 Mobile Network Handling**

**Scenario: User on unstable 3G connection**

**Optimization:**
- Adaptive chunk sizing: Larger chunks on slow connections
- Increase keepalive interval: 15s → 30s
- Reduce metadata verbosity
- Enable compression: gzip SSE stream

#### **4.6 Browser Compatibility**

**Edge cases:**
- **Safari 15**: Buggy ReadableStream, use polyfill
- **IE11**: No SSE support, fallback to long-polling
- **Brave**: Privacy features may block streaming, detect and fallback

---

### **Phase 5: Testing & Monitoring**

#### **5.1 Streaming Integration Tests**

**Test scenarios:**
```python
@pytest.mark.asyncio
async def test_stream_complete_answer():
    chunks = []
    async for chunk in query_stream(QueryRequest(query="pricing")):
        chunks.append(chunk)
    assert len(chunks) > 0
    assert chunks[-1]["type"] == "complete"

@pytest.mark.asyncio
async def test_stream_mid_failure_recovery():
    # Simulate LLM failure at 50%
    # Verify fallback kicks in
    # Verify complete answer delivered

@pytest.mark.asyncio
async def test_stream_client_disconnect():
    # Simulate disconnect
    # Verify cleanup happens
    # Verify no resource leaks
```

#### **5.2 Performance Monitoring**

**CloudWatch/DataDog metrics:**
- `streaming.ttfc.p95` (Time to first chunk)
- `streaming.duration.p99` (Total stream time)
- `streaming.error_rate` (Failures per hour)
- `streaming.reconnection_rate` (Client reconnects)
- `streaming.completion_rate` (% streams fully completed)

#### **5.3 Load Testing**

**Scenarios:**
- 100 concurrent streams
- 1000 chunks/second aggregate throughput
- Sustained streaming for 5 minutes per connection
- Verify no memory leaks

---

### **Phase 6: Rollout Strategy**

#### **6.1 Feature Flag**
```python
# backend/app/config.py
class Settings(BaseSettings):
    enable_streaming: bool = Field(default=False, env="ENABLE_STREAMING")
    streaming_rollout_percentage: int = Field(default=0, env="STREAMING_ROLLOUT_PCT")
```

#### **6.2 Canary Rollout**
- **Week 1**: 5% users → Monitor TTFC, error rates
- **Week 2**: 25% users → Validate mobile performance
- **Week 3**: 50% users → Monitor server load
- **Week 4**: 100% users → Full rollout

#### **6.3 Rollback Plan**
- Feature flag instant disable
- Automatic fallback to sync endpoints
- Keep sync endpoints active for 2 weeks post-rollout

---

## 📊 **Implementation Priority Matrix**

| Component | Impact | Complexity | Priority |
|-----------|--------|------------|----------|
| LLM streaming (Phase 1.1) | 🔥 High | Medium | **P0** |
| SSE endpoints (Phase 1.3) | 🔥 High | Medium | **P0** |
| Frontend streaming client (Phase 2.1) | 🔥 High | Medium | **P0** |
| React UI integration (Phase 2.2) | 🔥 High | Low | **P0** |
| Error recovery (Phase 4.1-4.3) | Medium | High | **P1** |
| Progressive citations (Phase 3.1) | Medium | Low | **P1** |
| Graceful degradation (Phase 3.4) | Medium | Medium | **P2** |
| Monitoring (Phase 5.2) | High | Low | **P1** |
| Load testing (Phase 5.3) | Medium | Medium | **P2** |

---

## ⚠️ **Critical Considerations**

1. **Backwards Compatibility**: Keep all existing sync endpoints, add new `/stream` endpoints
2. **Database Connections**: Stream chunks without holding DB connections open
3. **Authentication**: Verify JWT before starting stream, not per chunk
4. **Rate Limiting**: Apply per-session, not per-chunk
5. **Compliance/Audit**: Log stream initiation + completion, not every chunk