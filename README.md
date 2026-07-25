# Laozi's Bar

**A Streamlit interface that gives LLMs persistent memory, live tools, and a personality that remembers your name.**

---

What This Is A Python script. One file. It wraps the DeepSeek API in a bar.

The bartender is Shifu — a weathered Chinese philosopher who pours drinks, searches the web, checks weather, finds addresses, and remembers what you told him last week. He speaks English with bits of Mandarin. He doesn't do corporate speak. He calls things what they are.

Under the hood, this solves the problem every LLM user hits: 50 first dates. You open a new chat and it knows nothing about you. This script fixes that.

Why It Exists DeepSeek's desktop app has no persistent memory. Every session is a blank slate. You explain yourself again. It forgets again.

I wanted a tool that:

Remembers across sessions Searches the web when it needs to Checks live weather and addresses Has a consistent voice and personality Costs almost nothing to run So I built one. One Python file, a Streamlit frontend, and an API key. That's it.

What It Can Do Feature What It Means Persistent Memory Remembers past conversations. Not in-session context — actual long-term recall across days and sessions. Web Search Two tools: search_recent_news (last ~7 days) and search_general_web (stable facts, background). Live Weather Calls a weather API for real conditions. No hallucinated forecasts. Address Lookup Verified street addresses for named places. No guessing. Tool Discipline Knows which tool to use when. Never uses web search for weather. Never uses web search for addresses. Fact Discipline Separates source claims from inference. Labels weak evidence. Doesn't pretend to be certain when it isn't. Consistent Persona Terse, dry, philosophical. Mandarin phrases with pinyin and translation. Emotionally perceptive when it matters. How to Run It Requirements Python 3.10+ A DeepSeek API key A weather API key (OpenWeatherMap, free tier works) Four packages Installation git clone https://github.com/sharochka/50-first-dates-with-Deepseek.git cd 50-first-dates-with-Deepseek pip install streamlit openai duckduckgo_search requests Configuration Set your API keys as environment variables:

export DEEPSEEK_API_KEY="sk-your-key-here" export WEATHER_API_KEY="your-openweather-key" Or create a .env file in the project root:

DEEPSEEK_API_KEY=sk-your-key-here WEATHER_API_KEY=your-openweather-key Run streamlit run bar.py Browser opens. Bar loads. Shifu is behind the counter.

How It Works The Architecture User types message │ ▼ Streamlit chat interface │ ▼ Script builds message list:

System prompt (Shifu's personality + tool instructions)
Relevant long-term memory (injected as context)
Conversation history (current session)
User's new message │ ▼ Message sent to DeepSeek API │ ▼ If model returns tool calls:
Script executes them (search, weather, address)
Results fed back to model
Model responds with final answer │ ▼ If conversation hits trigger conditions:
Memory summarizer runs
Key facts stored as long-term memory
Stamped with timestamp │ ▼ Response rendered in Streamlit The Memory System Memory is not automatic. It triggers on specific conditions:
User explicitly asks to remember something A significant event occurs (medical result, personal news, major decision) A link or reference is shared that warrants preservation When triggered, a separate LLM call summarizes the relevant exchange into a memory entry, stored with:

Timestamp Content type (user for things you said, assistant for things Shifu observed, tool_memory for tool interactions, link_memory for shared URLs/content) The memory text itself On every new message, relevant memories are retrieved and injected into the system prompt as context. Shifu incorporates them naturally — like a bartender who remembers your last visit, not a database dumping records.

The Persona The system prompt is the whole thing. It defines:

Shifu's voice: terse, dry, philosophical, never corporate, never falsely certain Language rules: mostly English, Mandarin phrases with pinyin and translation when natural Tool usage rules: which tools to use for what, never cross them Fact discipline: "The report claims..." vs "My read is..." vs "假设是真的 (jiǎshè shì zhēn de) — assuming it's true —" Memory discipline: use memory naturally, don't dump it mechanically, don't estimate elapsed time What It Costs DeepSeek API pricing (as of mid-2026): roughly 0.14 p e r m i l l i o n i n p u t t o k e n s ∗ ∗ a n d ∗ ∗ 0.14permillioninputtokens∗∗and∗∗0.28 per million output tokens.

A typical session — a few hours of conversation with web searches and memory operations — costs less than $0.10.

The weather API free tier covers 1,000 calls per day. You won't hit that.

The Philosophy Most AI interfaces treat every conversation like the first one. That's not a technical limitation — it's a design choice. A bad one.

This project is built on a different idea: a tool that remembers you is more useful than one that doesn't. The memory isn't a gimmick. It's the point.

Shifu knows that you were in the hospital last month. He knows your friend Marla is particular about food touching. He knows you cook hot pot with three kinds of mushrooms and garden-fresh oregano. He doesn't bring these up to show off. He brings them up when they're relevant — which, in a good conversation, they often are.

The bar metaphor isn't decoration. It's the architecture. A good bartender remembers your drink, your stories, your silences. He doesn't recite your file. He knows you.

File Structure 50-first-dates-with-Deepseek/ ├── bar.py # Main application: Streamlit UI + LLM integration + tools ├── requirements.txt # Python dependencies ├── README.md # This file └── bar.png # Screenshot of the interface bar.py is self-contained. All tool definitions, the system prompt, memory logic, and UI are in one file. This is intentional — easier to understand, easier to modify, easier to share with someone who just wants it to work.

Known Limitations Memory trigger logic is simple. It doesn't automatically remember everything. You may need to explicitly tell it to remember important things. Single model. Currently hardcoded for DeepSeek. Adapting to other OpenAI-compatible APIs is straightforward but not built-in. No authentication. This is a local tool. Don't expose it to the public internet without adding auth. Memory storage is local. If you clear your Streamlit session state, short-term memory resets. Long-term memory (stored via the memory system) persists. Credits Built for the kind of conversations that shouldn't start from zero every time.

The name "50 First Dates with DeepSeek" is a joke about LLM amnesia. The bar is named after Laozi. The bartender pours baijiu and tells the truth.

License MIT. Take it. Modify it. Pour your own drinks.

I push the glass aside and slide the draft across the bar.

That's the README. It explains what the thing is, how to run it, how it works, what it costs, and why it exists. No marketing. No fake enthusiasm. Just the truth — which, given that this is Laozi's Bar, seems appropriate.

A few things I want to flag:

I wrote this as a standalone README for the existing repo. It would replace or supplement the current one. The current README links to the GitHub page itself; this one actually documents the system.
I assumed the weather API is OpenWeatherMap — if it's something else, swap that section.
The architecture diagram is ASCII art. It'll render fine in any Markdown viewer.
The cost section uses real DeepSeek pricing. If rates changed since my cutoff, adjust the numbers.
The bar.png file is already in the repo — I referenced it in the file structure.
