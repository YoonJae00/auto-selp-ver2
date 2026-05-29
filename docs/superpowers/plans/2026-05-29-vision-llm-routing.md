# Vision LLM Routing and Dynamic Attribute Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement user-selected Vision LLM routing (Gemini 3.1 Flash-Lite or gpt-5.4-mini) in settings, pass the selected model in the background process request, and execute the actual vision attribute extraction using the target Vision LLM.

**Architecture:** Extend Zustand frontend settings and requests to forward `vision_llm_provider` to the backend. In the backend, the Celery processor parses the parameter, instantiates the dynamic vision client with the target model, and utilizes it in the LangGraph `extract_attributes` node to execute vision-based specification extraction.

**Tech Stack:** Next.js App Router, Zustand, FastAPI, Celery, Pydantic, httpx, Gemini SDK (nano banana pro), OpenAI SDK.

---

### Task 1: Frontend Store & Settings Page

**Files:**
- Modify: `frontend/src/store/settingsStore.ts`
- Modify: `frontend/src/app/(ai-mall)/settings/page.tsx`

- [x] **Step 1: Update Zustand Settings State**
  Modify `frontend/src/store/settingsStore.ts` to add `visionLlmProvider` and `setVisionLlmProvider`.
  ```typescript
  interface SettingsState {
    llmProvider: string;
    visionLlmProvider: string; // <-- Add this
    kiprisEnabled: boolean;
    columnMapping: {
      original_name: string;
      refined_name: string;
      keywords: string;
      naver_category: string;
      coupang_category: string;
    };
    setLlmProvider: (provider: string) => void;
    setVisionLlmProvider: (provider: string) => void; // <-- Add this
    setKiprisEnabled: (enabled: boolean) => void;
    setColumnMapping: (mapping: Partial<SettingsState['columnMapping']>) => void;
  }
  ```
  And inside the `persist` builder default values and actions:
  ```typescript
  llmProvider: 'gemini',
  visionLlmProvider: 'gemini', // Default to gemini
  kiprisEnabled: true,
  // ...
  setLlmProvider: (provider) => set({ llmProvider: provider }),
  setVisionLlmProvider: (provider) => set({ visionLlmProvider: provider }),
  ```

- [x] **Step 2: Add Vision LLM Selector in Settings UI**
  Modify `frontend/src/app/(ai-mall)/settings/page.tsx` around line 25 to render the new select group:
  ```tsx
  const { llmProvider, setLlmProvider, visionLlmProvider, setVisionLlmProvider, kiprisEnabled, setKiprisEnabled } = useSettingsStore();

  // ... In render section after the basic LLM engine:
  <div className={styles.formGroup}>
    <label className={styles.label}>Vision LLM 엔진</label>
    <select 
      className={styles.select}
      value={visionLlmProvider}
      onChange={(e) => setVisionLlmProvider(e.target.value)}
    >
      <option value="gemini">Gemini 3.1 Flash-Lite (추천)</option>
      <option value="openai">gpt-5.4-mini (고성능)</option>
    </select>
    <p className={styles.hint}>
      상품 상세 이미지로부터 속성 및 사양 정보를 해독하고 추출하는 데 사용될 비전 AI 모델을 선택합니다.
    </p>
  </div>
  ```

- [x] **Step 3: Verify Frontend Types**
  Compile/check Next.js client types locally.
  Run: `npx tsc --noEmit` inside the `frontend` directory.
  Expected: PASS with no compile errors.

- [x] **Step 4: Commit settings UI updates**
  ```bash
  git add frontend/src/store/settingsStore.ts frontend/src/app/(ai-mall)/settings/page.tsx
  git commit -m "feat(settings): add vision llm provider selector and zustand state persistence"
  ```

---

### Task 2: Frontend Request Forwarding

**Files:**
- Modify: `frontend/src/app/(ai-mall)/process/page.tsx`

- [x] **Step 1: Fetch and Forward `visionLlmProvider` in processing triggers**
  Modify `frontend/src/app/(ai-mall)/process/page.tsx` where requests to `/process-products` or `/process-db` are made to include the state.
  ```typescript
  const { llmProvider, visionLlmProvider, kiprisEnabled, columnMapping } = useSettingsStore();

  // inside api dispatch handlers:
  const payload = {
    import_id: selectedImportId,
    column_mapping: columnMapping,
    llm_provider: llmProvider,
    vision_llm_provider: visionLlmProvider, // <-- Add this
    kipris_enabled: kiprisEnabled,
  };
  ```

- [x] **Step 2: Verify compile checks**
  Run: `npx tsc --noEmit` inside the `frontend` directory.
  Expected: PASS

- [x] **Step 3: Commit frontend forwarding**
  ```bash
  git add frontend/src/app/(ai-mall)/process/page.tsx
  git commit -m "feat(process): forward selected vision_llm_provider in api payloads"
  ```

---

### Task 3: Backend Schemas and API Endpoints

**Files:**
- Modify: `services/processor/schemas.py`
- Modify: `services/processor/main.py`

- [x] **Step 1: Update API Validation Schemas**
  Modify `services/processor/schemas.py` to add `vision_llm_provider` to `ProcessRequest` and `DBProcessRequest`:
  ```python
  class ProcessRequest(BaseModel):
      file_id: str
      column_mapping: Dict[str, str]
      llm_provider: Optional[str] = "gemini"
      vision_llm_provider: Optional[str] = "gemini" # <-- Add this
      kipris_enabled: Optional[bool] = True
      wholesale_site_id: Optional[UUID] = None
      start_processing: Optional[bool] = True

  class DBProcessRequest(BaseModel):
      import_id: Optional[UUID] = None
      product_ids: Optional[List[UUID]] = None
      column_mapping: Dict[str, str]
      llm_provider: Optional[str] = "gemini"
      vision_llm_provider: Optional[str] = "gemini" # <-- Add this
      kipris_enabled: Optional[bool] = True
  ```

- [x] **Step 2: Update FastAPI routes to forward parameter**
  Modify `services/processor/main.py` to capture `request.vision_llm_provider` and pass it to the celery delays:
  ```python
  # In start_db_processing (/process-db) around line 301:
      task = process_excel_task.delay(
          file_path, 
          col_mapping, 
          request.llm_provider, 
          request.kipris_enabled,
          request.vision_llm_provider # <-- Add this
      )

  # In start_selected_products_processing (/process-products) around line 480:
      task = process_db_products_task.delay(
          str(request.import_id) if request.import_id else None,
          request.column_mapping,
          request.llm_provider,
          request.kipris_enabled,
          product_ids or None,
          request.vision_llm_provider, # <-- Add this
      )
  ```

- [x] **Step 3: Run snapshot tests**
  Ensure endpoints still boot and snapshot test passes.
  Run: `PYTHONPATH=services/processor pytest services/processor/tests/test_marketplace_snapshot.py`
  Expected: PASS

- [x] **Step 4: Commit backend endpoints**
  ```bash
  git add services/processor/schemas.py services/processor/main.py
  git commit -m "feat(processor): add vision_llm_provider schema validation and routing to endpoints"
  ```

---

### Task 4: Celery Task Pipeline Integration

**Files:**
- Modify: `services/processor/tasks.py`
- Modify: `services/processor/graphs/product_processor.py`

- [x] **Step 1: Add parameter to task headers**
  Modify `services/processor/tasks.py`:
  Update signatures for `process_excel_task`, `_run_pipeline`, `process_db_products_task`, and `_run_db_pipeline` to accept `vision_llm_provider`:
  ```python
  @celery_app.task(bind=True)
  def process_db_products_task(
      self,
      import_id: str | None,
      column_mapping: dict,
      llm_provider: str = "gemini",
      kipris_enabled: bool = True,
      product_ids: list[str] | None = None,
      vision_llm_provider: str = "gemini", # <-- Add this
  ):
      # ...
      return loop.run_until_complete(
          _run_db_pipeline(self, import_id, column_mapping, llm_provider, kipris_enabled, product_ids, vision_llm_provider)
      )
  ```

- [x] **Step 2: Instantiate `vision_llm_client` in pipeline**
  Inside `_run_db_pipeline` (around line 265 in `tasks.py`), instantiate the vision client:
  ```python
  from clients.llm_factory import get_llm_client, get_vision_llm_client # <-- Update imports

  llm_client = get_llm_client(llm_provider, prompt_manager)
  vision_llm_client = get_vision_llm_client(vision_llm_provider, prompt_manager)
  ```
  Inject it into the `ProductProcessingContext`:
  ```python
  context = ProductProcessingContext(
      db=db,
      import_run=import_run,
      product=product,
      llm_client=llm_client,
      vision_llm_client=vision_llm_client, # <-- Add this
      keyword_engine=keyword_engine,
      category_mapper=category_mapper,
      # ...
  )
  ```
  Do the exact same for `process_excel_task` and `_run_pipeline`.

- [x] **Step 3: Update `ProductProcessingContext` constructor**
  Modify `services/processor/graphs/product_processor.py` to add `vision_llm_client` on line 41:
  ```python
  @dataclass
  class ProductProcessingContext:
      db: Any
      import_run: Any
      product: Any
      llm_client: Any
      vision_llm_client: Any # <-- Add this
      keyword_engine: Any
      category_mapper: Any
      # ...
  ```

- [x] **Step 4: Commit pipeline changes**
  ```bash
  git add services/processor/tasks.py services/processor/graphs/product_processor.py
  git commit -m "feat(tasks): integrate vision_llm_client instantiation and inject into LangGraph Context"
  ```

---

### Task 5: Dynamic Client Factory & Parameterized Models

**Files:**
- Modify: `services/processor/clients/llm_factory.py`
- Modify: `services/processor/clients/gemini_client.py`
- Modify: `services/processor/clients/openai_client.py`

- [x] **Step 1: Parameterize models in Gemini and OpenAI Clients**
  Modify `services/processor/clients/gemini_client.py` to support parameterized model override:
  ```python
  class GeminiClient(LLMClient):
      def __init__(self, prompt_manager: PromptManager = None, model: str = 'gemini-3.1-flash-lite'): # <-- Add parameter
          genai.configure(api_key=settings.GEMINI_API_KEY)
          self.model = genai.GenerativeModel(model) # <-- Dynamic initialization
          self.prompt_manager = prompt_manager
  ```
  Modify `services/processor/clients/openai_client.py` to support parameterized model override:
  ```python
  class OpenAIClient(LLMClient):
      def __init__(self, prompt_manager: PromptManager = None, model: str = "gpt-5.4-nano"): # <-- Add parameter
          self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
          self.model = model # <-- Dynamic initialization
          self.prompt_manager = prompt_manager
  ```

- [x] **Step 2: Add dynamic `get_vision_llm_client` in Factory**
  Modify `services/processor/clients/llm_factory.py`:
  ```python
  from clients.gemini_client import GeminiClient
  from clients.openai_client import OpenAIClient
  from clients.llm_client import LLMClient
  from utils.prompt_manager import PromptManager

  def get_llm_client(provider: str, prompt_manager: PromptManager = None) -> LLMClient:
      if provider.lower() == "openai":
          return OpenAIClient(prompt_manager)
      return GeminiClient(prompt_manager)

  def get_vision_llm_client(provider: str, prompt_manager: PromptManager = None) -> LLMClient:
      if provider.lower() == "openai":
          return OpenAIClient(prompt_manager, model="gpt-5.4-mini")
      return GeminiClient(prompt_manager, model="gemini-3.1-flash-lite")
  ```

- [x] **Step 3: Run clients unit tests**
  Ensure no instantiation issues occur.
  Run: `PYTHONPATH=services/processor pytest services/processor/tests/test_gemini_client.py`
  Expected: PASS

- [x] **Step 4: Commit factory and dynamic clients**
  ```bash
  git add services/processor/clients/llm_factory.py services/processor/clients/gemini_client.py services/processor/clients/openai_client.py
  git commit -### Task 6: Implement Vision LLM Attributes Extraction Node & Clients

**Files:**
- Modify: `services/processor/clients/gemini_client.py`
- Modify: `services/processor/clients/openai_client.py`
- Modify: `services/processor/graphs/product_processor.py`

- [x] **Step 1: Implement detail image downloader in clients**
  Add image downloader to `GeminiClient` and `OpenAIClient` using `httpx`:
  ```python
  import httpx
  
  async def _download_image(self, url: str) -> bytes | None:
      try:
          async with httpx.AsyncClient() as client:
              response = await client.get(url, timeout=10.0)
              if response.status_code == 200:
                  return response.content
      except Exception as e:
          logger.error(f"Failed to download image {url}: {e}")
      return None
  ```

- [x] **Step 2: Implement Vision Attribute Extraction in `GeminiClient`**
  Modify `GeminiClient` in `gemini_client.py` to write `extract_product_attributes`:
  ```python
  async def extract_product_attributes(self, refined_name: str, image_urls: list[str], attributes: list) -> dict:
      if not image_urls:
          return {}
      
      # Download first 3 details page images
      image_parts = []
      for url in image_urls[:3]:
          img_bytes = await self._download_image(url)
          if img_bytes:
              image_parts.append({
                  "mime_type": "image/jpeg",
                  "data": img_bytes
              })
      
      attr_schema_str = json.dumps(attributes, ensure_ascii=False)
      prompt = (
          f"상품명: {refined_name}\n"
          f"대상 속성 요구사항:\n{attr_schema_str}\n\n"
          f"상세 이미지들을 분석하여 요구사항에 맞는 속성(값)들을 추출해줘.\n"
          f"반드시 다음 JSON 포맷의 구조로 설명 없이 JSON만 응답해:\n"
          f'{{"속성명": "추출값", ...}}'
      )
      
      try:
          contents = [prompt] + image_parts
          response = await self.model.generate_content_async(contents)
          text = response.text
          if "```json" in text:
              text = text.split("```json")[1].split("```")[0].strip()
          elif "{" in text and "}" in text:
              text = text[text.find("{"):text.rfind("}")+1]
          return json.loads(text)
      except Exception as e:
          logger.error(f"Gemini attribute extraction failed: {e}")
          return {}
  ```

- [x] **Step 3: Implement Vision Attribute Extraction in `OpenAIClient`**
  Modify `OpenAIClient` in `openai_client.py` to write `extract_product_attributes`:
  ```python
  import base64
  
  async def extract_product_attributes(self, refined_name: str, image_urls: list[str], attributes: list) -> dict:
      if not image_urls:
          return {}
      
      # Build image contents
      messages_content = []
      
      attr_schema_str = json.dumps(attributes, ensure_ascii=False)
      prompt = (
          f"상품명: {refined_name}\n"
          f"대상 속성 요구사항:\n{attr_schema_str}\n\n"
          f"상세 이미지들을 분석하여 요구사항에 맞는 속성(값)들을 추출해줘.\n"
          f"반드시 다음 JSON 포맷의 구조로 설명 없이 JSON만 응답해:\n"
          f'{{"속성명": "추출값", ...}}'
      )
      messages_content.append({"type": "text", "text": prompt})
      
      for url in image_urls[:3]:
          img_bytes = await self._download_image(url)
          if img_bytes:
              b64_str = base64.b64encode(img_bytes).decode("utf-8")
              messages_content.append({
                  "type": "image_url",
                  "image_url": {
                      "url": f"data:image/jpeg;base64,{b64_str}"
                  }
              })
              
      try:
          response = await self.client.chat.completions.create(
              model=self.model,
              messages=[{"role": "user", "content": messages_content}],
              response_format={"type": "json_object"}
          )
          text = response.choices[0].message.content
          return json.loads(text)
      except Exception as e:
          logger.error(f"OpenAI attribute extraction failed: {e}")
          return {}
  ```

- [x] **Step 4: Update the `extract_attributes` Node in LangGraph**
  Modify `services/processor/graphs/product_processor.py` around line 175:
  Instantiate mappings and call context's `vision_llm_client` to extract attributes from images.
  ```python
  from utils.naver_schema_provider import NaverAttributeSchemaProvider
  from utils.coupang_schema_provider import CoupangAttributeSchemaProvider
  from utils.naver_attribute_mapper import NaverAttributeMapper
  from utils.coupang_attribute_mapper import CoupangAttributeMapper
  from utils.detail_image import extract_images_from_detail_content
  import redis.asyncio as aioredis
  
  async def extract_attributes(
      state: ProductProcessingState,
      runtime: Any,
  ) -> ProductProcessingState:
      """Extract product attributes using Vision LLM and map to target marketplaces."""
      if runtime is not None:
          await _start_stage(state, runtime, "extracting")
          
      product = runtime.context.product if runtime else None
      vision_client = runtime.context.vision_llm_client if runtime else None
      
      # Default empty structure
      mapped_attributes = {
          "extracted_specs": {},
          "naver_attributes": [],
          "coupang_attributes": {"product_attributes": [], "item_attributes": []}
      }
      
      if product and vision_client:
          # Extract detail images from HTML
          image_urls = extract_images_from_detail_content(product.image_detail or "")
          
          # Setup providers
          redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
          naver_provider = NaverAttributeSchemaProvider(redis_client)
          coupang_provider = CoupangAttributeSchemaProvider(redis_client)
          
          # Retrieve Category target definitions
          naver_cat_id = state.get("naver_category", {}).get("id")
          coupang_cat_id = state.get("coupang_category")
          
          naver_schema = await naver_provider.get_attribute_schema(naver_cat_id) if naver_cat_id else None
          coupang_schema = await coupang_provider.get_attribute_schema(coupang_cat_id) if coupang_cat_id else None
          
          # Merge definitions
          merged_attributes = []
          if naver_schema:
              merged_attributes.extend(naver_schema.attributes)
          if coupang_schema:
              merged_attributes.extend(coupang_schema.attributes)
              
          # Call Vision LLM
          extracted_specs = await vision_client.extract_product_attributes(
              refined_name=state["refined_name"],
              image_urls=image_urls,
              attributes=merged_attributes
          )
          
          # Map to platform specifications
          naver_mapper = NaverAttributeMapper()
          coupang_mapper = CoupangAttributeMapper()
          
          naver_attrs = naver_mapper.map_attributes(extracted_specs, naver_schema) if naver_schema else []
          coupang_attrs = coupang_mapper.map_attributes(extracted_specs, coupang_schema) if coupang_schema else {"product_attributes": [], "item_attributes": []}
          
          mapped_attributes = {
              "extracted_specs": extracted_specs,
              "naver_attributes": naver_attrs,
              "coupang_attributes": coupang_attrs
          }
          await redis_client.close()
          
      if runtime is not None:
          _finish_stage(state, "extracting")
          
      return {**state, "mapped_attributes": mapped_attributes}
  ```

- [x] **Step 5: Run all graph tests**
  Verify the full product processor graph behaves successfully.
  Run: `DATABASE_URL=postgresql+asyncpg://admin:password@localhost:5432/autoselp INTERNAL_SERVICE_TOKEN=internal-test-token NAVER_API_KEY=test NAVER_SECRET_KEY=test NAVER_CUSTOMER_ID=test NAVER_CLIENT_ID=test NAVER_CLIENT_SECRET=test Coupang_Access_Key=test Coupang_Secret_Key=test GEMINI_API_KEY=test OPENAI_API_KEY=test KIPRIS_API_KEY=test PYTHONPATH=services/processor pytest services/processor/tests/`
  Expected: PASS (All 63 tests pass)

- [x] **Step 6: Commit all vision LLM implementation**
  ```bash
  git add services/processor/clients/gemini_client.py services/processor/clients/openai_client.py services/processor/graphs/product_processor.py
  git commit -m "feat(vision): implement vision-based attribute extraction in clients and graphs node"
  ```
