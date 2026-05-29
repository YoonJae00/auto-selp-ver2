# Vision LLM Routing and Dynamic Attribute Extraction Design

**Date**: 2026-05-29  
**Status**: Approved  

---

## 1. Objective
Allow users to dynamically select a multi-modal Vision LLM engine separate from the standard text-based LLM engine in the Settings UI. The selected Vision LLM engine (either `Gemini 3.1 Flash-Lite` or `gpt-5.4-mini`) will extract category attributes and specifications from detailed product images during the background LangGraph AI processing pipeline.

---

## 2. Component Design & Changes

### 2-1. Frontend Settings Store & UI
* **Zustand Store** (`frontend/src/store/settingsStore.ts`):
  * Add `visionLlmProvider` state string. Defaults to `'gemini'`.
  * Add `setVisionLlmProvider(provider: string)` action.
* **Settings Page** (`frontend/src/app/(ai-mall)/settings/page.tsx`):
  * Render a new form select option for "Vision LLM 엔진" (Vision LLM Engine):
    * `Gemini 3.1 Flash-Lite (추천)` -> value `'gemini'`
    * `gpt-5.4-mini (고성능)` -> value `'openai'`
* **Process Request Execution** (`frontend/src/app/(ai-mall)/process/page.tsx`):
  * Read both `llmProvider` and `visionLlmProvider` from the Zustand store.
  * Populate `llm_provider` and `vision_llm_provider` in the `POST /process-products` or `POST /process-db` API request payloads.

### 2-2. Backend Schemas & Routes
* **Pydantic Validation Schemas** (`services/processor/schemas.py`):
  * Add `vision_llm_provider: Optional[str] = "gemini"` to `ProcessRequest` and `DBProcessRequest`.
* **API Route Controllers** (`services/processor/main.py`):
  * Update endpoints `POST /process-db` and `POST /process-products` to capture `request.vision_llm_provider` and pass it down when queuing Celery tasks.

### 2-3. Celery Pipeline & LangGraph Context
* **Celery Async Pipeline Task** (`services/processor/tasks.py`):
  * Add `vision_llm_provider: str = "gemini"` parameters to `process_excel_task` and `process_db_products_task`.
  * Inside `_run_db_pipeline` and `_run_pipeline`, instantiate the base and vision clients:
    ```python
    llm_client = get_llm_client(llm_provider, prompt_manager)
    vision_llm_client = get_vision_llm_client(vision_llm_provider, prompt_manager)
    ```
  * Inject both clients into the `ProductProcessingContext` constructor.
* **Context Definition** (`services/processor/graphs/product_processor.py`):
  * Add a `vision_llm_client: Any` field to `ProductProcessingContext`.

### 2-4. Client Dynamic Instantiation & Vision Extraction Logic
* **Dynamic Factory** (`services/processor/clients/llm_factory.py`):
  * Add `get_vision_llm_client(provider: str, prompt_manager: PromptManager = None)`:
    * Returns `OpenAIClient(prompt_manager, model="gpt-5.4-mini")` if provider is `"openai"`.
    * Returns `GeminiClient(prompt_manager, model="gemini-3.1-flash-lite")` otherwise.
* **LLM Clients Base Constructors** (`gemini_client.py` & `openai_client.py`):
  * Parameterize the `model` parameter in `GeminiClient` and `OpenAIClient` constructors to accept target vision model strings.
* **Vision Attribute Extraction** (`extract_product_attributes`):
  * Download detailed page images (using `httpx.AsyncClient` helper).
  * Structure and build prompt detailing the marketplace categories' attribute definitions (names, types, options).
  * Call multi-modal LLM API directly passing text prompts along with image parts (Gemini inline parts / OpenAI Base64 structures).
  * Parse, clean, and validate JSON returned representing target attribute specifications.

---

## 3. Database Schema
No database schema changes are required. The JSONB `mapped_attributes` field on `product_platform_mappings` already supports unstructured list or dictionary payloads.

---

## 4. Testing & Verification Plan
1. **Mock Test Cases**:
   * Verify correct initialization of both models via `llm_factory.py`.
   * Add a test case verifying that `get_vision_llm_client` instantiates OpenAI with `gpt-5.4-mini` and Gemini with `gemini-3.1-flash-lite`.
2. **E2E Integration Verification**:
   * Run a mock product processing step with the new request schemas to ensure zero regressions in task startup and state orchestration.
