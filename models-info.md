# GEMINI 정보
<br />

Gemini 3.1 Flash-Lite is a low-latency, cost-effective multimodal model
optimized for high-frequency, lightweight tasks. The model supports text, image,
video, audio, and PDF inputs, and is designed for high-volume agentic workflows,
simple data extraction, and applications where latency and API cost are the
primary constraints.
[Try in Google AI Studio](https://aistudio.google.com/prompts/new_chat?model=gemini-3.1-flash-lite)

## gemini-3.1-flash-lite

| Property | Description |
|---|---|
| Model code | `gemini-3.1-flash-lite` |
| Supported data types | **Inputs** Text, Image, Video, Audio, and PDF **Output** Text |
| Token limits^[\[\*\]](https://ai.google.dev/gemini-api/docs/tokens)^ | **Input token limit** 1,048,576 **Output token limit** 65,536 |
| Capabilities | **Audio generation** Not supported **Batch API** Supported **Caching** Supported **Code execution** Supported **Computer use** Not supported **File search** Supported **Flex inference** Supported **Function calling** Supported **Grounding with Google Maps** Supported **Image generation** Not supported **Live API** Not supported **Priority inference** Supported **Search grounding** Supported **Structured outputs** Supported **Thinking** Supported **URL context** Supported |
| Versions | Read the [model version patterns](https://ai.google.dev/gemini-api/docs/models/gemini#model-versions) for more details. - `Stable: gemini-3.1-flash-lite` |
| Latest update | May 2026 |
| Knowledge cutoff | January 2025 |

## Developer guide

Gemini 3.1 Flash-Lite is best at handling straightforward tasks at significant
scale. Here are some use cases best suited for Gemini 3.1 Flash-Lite:

- **Translation**: Fast, cheap, high-volume translation, such as processing
  chat messages, reviews, and support tickets at scale. You can use system
  instructions to constrain output to only the translated text with no extra
  commentary:

      text = "Hey, are you down to grab some pizza later? I'm starving!"

      response = client.models.generate_content(
          model="gemini-3.1-flash-lite",
          config={
              "system_instruction": "Only output the translated text"
          },
          contents=f"Translate the following text to German: {text}"
      )

      print(response.text)

- **Transcription**: Process recordings, voice notes, or any audio content
  where you need a text transcript without spinning up a separate
  speech-to-text pipeline. Supports multimodal inputs, so you can pass audio
  files directly for transcription:

      # URL = "https://storage.googleapis.com/generativeai-downloads/data/State_of_the_Union_Address_30_January_1961.mp3"

      # Upload the audio file to the GenAI File API
      uploaded_file = client.files.upload(file='sample.mp3')

      prompt = 'Generate a transcript of the audio.'

      response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=[prompt, uploaded_file]
      )

      print(response.text)

- **Lightweight agentic tasks and data extraction**: Entity extraction,
  classification, and lightweight data processing pipelines supported with
  structured JSON output. For example, extracting structured data from an
  e-commerce customer review:

      from pydantic import BaseModel, Field

      prompt = "Analyze the user review and determine the aspect, sentiment score, summary quote, and return risk"
      input_text = "The boots look amazing and the leather is high quality, but they run way too small. I'm sending them back."

      class ReviewAnalysis(BaseModel):
          aspect: str = Field(description="The feature mentioned (e.g., Price, Comfort, Style, Shipping)")
          summary_quote: str = Field(description="The specific phrase from the review about this aspect")
          sentiment_score: int = Field(description="1 to 5 (1=worst, 5=best)")
          is_return_risk: bool = Field(description="True if the user mentions returning the item")

      response = client.models.generate_content(
          model="gemini-3.1-flash-lite",
          contents=[prompt, input_text],
          config={
              "response_mime_type": "application/json",
              "response_json_schema": ReviewAnalysis.model_json_schema(),
          },
      )

      print(response.text)

- **Document processing and summarization**: Parse PDFs and return concise
  summaries, like for building a document processing pipeline or quickly
  triaging incoming files:

      import httpx

      # Download a sample PDF document
      doc_url = "https://storage.googleapis.com/generativeai-downloads/data/med_gemini.pdf"
      doc_data = httpx.get(doc_url).content

      prompt = "Summarize this document"
      response = client.models.generate_content(
          model="gemini-3.1-flash-lite",
          contents=[
              types.Part.from_bytes(
                  data=doc_data,
                  mime_type='application/pdf',
              ),
              prompt
          ]
      )

      print(response.text)

- **Model routing** : Use a low-latency and low-cost model as a classifier that
  routes queries to the appropriate model based on task complexity. This is a
  real pattern in production --- the open-source [Gemini CLI](https://geminicli.com/docs/core/#model-fallback) uses Flash-Lite to
  classify task complexity and route to Flash or Pro accordingly.

      FLASH_MODEL = 'flash'
      PRO_MODEL = 'pro'

      CLASSIFIER_SYSTEM_PROMPT = f"""
      You are a specialized Task Routing AI. Your sole function is to analyze the user's request and classify its complexity. Choose between `{FLASH_MODEL}` (SIMPLE) or `{PRO_MODEL}` (COMPLEX).
      1.  `{FLASH_MODEL}`: A fast, efficient model for simple, well-defined tasks.
      2.  `{PRO_MODEL}`: A powerful, advanced model for complex, open-ended, or multi-step tasks.

      A task is COMPLEX if it meets ONE OR MORE of the following criteria:
      1.  High Operational Complexity (Est. 4+ Steps/Tool Calls)
      2.  Strategic Planning and Conceptual Design
      3.  High Ambiguity or Large Scope
      4.  Deep Debugging and Root Cause Analysis

      A task is SIMPLE if it is highly specific, bounded, and has Low Operational Complexity (Est. 1-3 tool calls).
      """

      user_input = "I'm getting an error 'Cannot read property 'map' of undefined' when I click the save button. Can you fix it?"

      response_schema = {
        "type": "object",
        "properties": {
          "reasoning": {
            "type": "string",
            "description": "A brief, step-by-step explanation for the model choice, referencing the rubric."
          },
          "model_choice": {
            "type": "string",
            "enum": [FLASH_MODEL, PRO_MODEL]
          }
        },
        "required": ["reasoning", "model_choice"]
      }

      response = client.models.generate_content(
          model="gemini-3.1-flash-lite",
          contents=user_input,
          config={
              "system_instruction": CLASSIFIER_SYSTEM_PROMPT,
              "response_mime_type": "application/json",
              "response_json_schema": response_schema
          },
      )

      print(response.text)

- **Thinking**: For better accuracy for tasks that benefit from step-by-step
  reasoning, configure thinking so the model spends additional compute on
  internal reasoning before producing the final output:

      response = client.models.generate_content(
          model="gemini-3.1-flash-lite",
          contents="How does AI work?",
          config=types.GenerateContentConfig(
              thinking_config=types.ThinkingConfig(thinking_level="high")
          ),
      )

      print(response.text)






# OPENAI 정보
gpt-5.4-mini 사용 할 거임
api docs
# Developer quickstart

import {
  Assistant,
  Camera,
  ChatTripleDots,
  Code,
  Bolt,
  Speed,
  SquarePlus,
} from "@components/react/oai/platform/ui/Icon.react";



















The OpenAI API provides a simple interface to state-of-the-art AI [models](https://developers.openai.com/api/docs/models) for text generation, natural language processing, computer vision, and more. Get started by creating an API Key and running your first API call. Discover how to generate text, analyze images, build agents, and more.

## Create and export an API key



StatsigClient.logEvent("quickstart_create_api_key_click", null, null)
  }
>
  Create an API Key


<p></p>
Before you begin, create an API key in the dashboard, which you'll use to
securely [access the API](https://developers.openai.com/api/docs/api-reference/authentication). Store the key
in a safe location, like a [`.zshrc`
file](https://www.freecodecamp.org/news/how-do-zsh-configuration-files-work/) or
another text file on your computer. Once you've generated an API key, export it
as an [environment variable](https://en.wikipedia.org/wiki/Environment_variable)
in your terminal.



<div data-content-switcher-pane data-value="macOS">
    <div class="hidden">macOS / Linux</div>
    Export an environment variable on macOS or Linux systems

```bash
export OPENAI_API_KEY="your_api_key_here"
```

  </div>
  <div data-content-switcher-pane data-value="windows" hidden>
    <div class="hidden">Windows</div>
    Export an environment variable in PowerShell

```bash
setx OPENAI_API_KEY "your_api_key_here"
```

  </div>



OpenAI SDKs are configured to automatically read your API key from the system environment.

## Install the OpenAI SDK and Run an API Call



<div data-content-switcher-pane data-value="javascript">
    <div class="hidden">JavaScript</div>
    </div>
  <div data-content-switcher-pane data-value="python" hidden>
    <div class="hidden">Python</div>
    </div>
  <div data-content-switcher-pane data-value="csharp" hidden>
    <div class="hidden">.NET</div>
    </div>
  <div data-content-switcher-pane data-value="java" hidden>
    <div class="hidden">Java</div>
    </div>
  <div data-content-switcher-pane data-value="golang" hidden>
    <div class="hidden">Go</div>
    </div>


<a
  href="https://github.com/openai/openai-responses-starter-app"
  target="_blank"
  rel="noreferrer"
>
  

<span slot="icon">
      </span>
    Start building with the Responses API.


</a>

[

<span slot="icon">
      </span>
    Learn more about prompting, message roles, and building conversational apps.

](https://developers.openai.com/api/docs/guides/text)

## Add credits to keep building



StatsigClient.logEvent("quickstart_add_credits_billing_click", null, null)
  }
>
  Go to billing


{/* prettier-ignore */}
<div className="mt-2">Congrats on running a free test API request! Start building real applications with higher limits and use <a href="/api/docs/models" target="_blank">our models</a> to generate text, audio, images, videos and more.</div>

<div className="mt-2">
  Access dashboard features designed to help you ship faster:
</div>
<a
  href="https://platform.openai.com/chat"
  target="_blank"
  rel="noreferrer"
  onClick={() =>
    StatsigClient.logEvent(
      "quickstart_add_credits_chat_playground_click",
      null,
      null
    )
  }
>
  

<span slot="icon">
      </span>
    Build & test conversational prompts and embed them in your app.


</a>
<a
  href="https://platform.openai.com/agent-builder"
  target="_blank"
  rel="noreferrer"
  onClick={() =>
    StatsigClient.logEvent(
      "quickstart_add_credits_agent_builder_click",
      null,
      null
    )
  }
>
  

<span slot="icon">
      </span>
    Build, deploy, and optimize agent workflows.


</a>

## Analyze images and files

Send image URLs, uploaded files, or PDF documents directly to the model to extract text, classify content, or detect visual elements.



<div data-content-switcher-pane data-value="image-url">
    <div class="hidden">Image URL</div>
    </div>
  <div data-content-switcher-pane data-value="file-url" hidden>
    <div class="hidden">File URL</div>
    </div>
  <div data-content-switcher-pane data-value="file-upload" hidden>
    <div class="hidden">Upload file</div>
    </div>



[

<span slot="icon">
      </span>
    Learn to use image inputs to the model and extract meaning from images.

](https://developers.openai.com/api/docs/guides/images)

[

<span slot="icon">
      </span>
    Learn to use file inputs to the model and extract meaning from documents.

](https://developers.openai.com/api/docs/guides/file-inputs)

## Extend the model with tools

Give the model access to external data and functions by attaching [tools](https://developers.openai.com/api/docs/guides/tools). Use built-in tools like web search or file search, or define your own for calling APIs, running code, or integrating with third-party systems.



<div data-content-switcher-pane data-value="web-search">
    <div class="hidden">Web search</div>
    </div>
  <div data-content-switcher-pane data-value="file-search" hidden>
    <div class="hidden">File search</div>
    </div>
  <div data-content-switcher-pane data-value="function-calling" hidden>
    <div class="hidden">Function calling</div>
    </div>
  <div data-content-switcher-pane data-value="remote-mcp" hidden>
    <div class="hidden">Remote MCP</div>
    </div>



[

<span slot="icon">
      </span>
    Learn about powerful built-in tools like web search and file search.

](https://developers.openai.com/api/docs/guides/tools)

[

<span slot="icon">
      </span>
    Learn to enable the model to call your own custom code.

](https://developers.openai.com/api/docs/guides/function-calling)

## Stream responses and build realtime apps

Use server‑sent [streaming events](https://developers.openai.com/api/docs/guides/streaming-responses) to show results as they’re generated, or the [Realtime API](https://developers.openai.com/api/docs/guides/realtime) for interactive voice and multimodal apps.

[

<span slot="icon">
      </span>
    Use server-sent events to stream model responses to users fast.

](https://developers.openai.com/api/docs/guides/streaming-responses)

[

<span slot="icon">
      </span>
    Use WebRTC or WebSockets for super fast speech-to-speech AI apps.

](https://developers.openai.com/api/docs/guides/realtime)

## Build agents

Use the OpenAI platform to build [agents](https://developers.openai.com/api/docs/guides/agents) capable of taking action—like [controlling computers](https://developers.openai.com/api/docs/guides/tools-computer-use)—on behalf of your users. Use the [Agents SDK](https://developers.openai.com/api/docs/guides/agents) to create orchestration logic on the backend.

[

<span slot="icon">
      </span>
    Learn how to use the OpenAI platform to build powerful, capable AI agents.

](https://developers.openai.com/api/docs/guides/agents)