# Recursive Language Models (RLMs) 

## Overview

This repository implements **[Recursive Language Models](https://arxiv.org/abs/2512.24601)**[^1]. I hacked together a minimal RLM prototype in Python using [Ollama](https://ollama.com) for LLM inference and Docker for sandboxed code execution. See [success_trajectory.md](success_trajectory.md) for the best trajectory over all testing.

I was very surprised by how capable the RLM was at one-shot code generation. While leveraging a massive, state-of-the-art model like [`qwen3.5:cloud`](https://ollama.com/library/qwen3.5) (397B) undoubtedly did a lot of the heavy lifting, I noted that models trained with Reinforcement Learning (RL) are perfectly suited for this architecture:
- **Code generation** being a verifiable domain that provides stable reward signals (correctness is easy to test), RL-trained models naturally excel here.
- **Longer-horizon trajectories:** RL models perform better on complex, multi-step tasks like ReAct[^3] (Reasoning and Acting). This is exactly what the  RLM Orchestrator agent is doing as it iteratively reasons about the observations, acts by writing code, and delegates to sub-agents.

## Problem
LLMs suffer from "Lost in the middle" phenomenon or "Context rot" when raw text is fed directly into the context window as prompts. This not only acts as a hard physical limit but has been proven to degrade reasoning ability (See [^2]), and likely encourages hallucinations/ungrounded responses.

## Solution
Instead of stuffing a massive document into a single LLM prompt, the document is loaded into a Python REPL environment as a string variable. The RLM[^1] is instructed to act as an "Orchestrator" agent that must:
1. Interact with the variable by writing Python code.
2. Solve the user's request by intelligently and efficiently chunking the variable and delegating chunks to sub-agents (i.e., separate LLM calls) for analysis.

In this way, the RLM's main context window stays concise and relevant, maintaining reasoning capability while still:
1. Allowing the system to handle arbitrarily large documents.
2. Enforcing strict grounding by design, since the Orchestrator has full access to the entire text via Python code execution and sub-agent responses.

## Failure cases observed during implementation
1. **Brute-force looping** over the entire document with LLM calls, instead of using Python code to first locate relevant sections (e.g. regex-based search).
- This slowed down the system drastically and had to be corrected with explicit prompt instructions.
2. **Internal knowledge bleed:** The Orchestrator and sub-agents used their pre-trained knowledge, instead of deriving search keywords and insights strictly from the user's prompt and the text itself. Whether this should strictly be avoided is up for debate as it might send the system down a reasoning trajectory that is ungrounded and ultimately incorrect. On the other hand, the authors note as a benefit that:
> "... model priors enable the RLM to narrow the search space and process fewer input tokens."
- I attempted to enforce a strict 'Amnesia/Naive Persona' in the system prompt, explicitly forbidding the use of pre-trained knowledge and forcing the model to derive search keywords only from the user's query. However, I still observed (especially in longer trajectories) that the model would "guess" the answer using its internal knowledge and then search for that guess, instead of searching for keywords derived from the prompt or sub-agent responses. With more time to refine the prompts, I believe this could be mitigated further or eliminated.
3. **Infinite looping:** The orchestrator had sometimes already found a reasonable answer, but kept asking sub-agents for more analysis instead of returning directly.
- I attempted to mitigate this by adding a warning message to output an answer explaining limitations (if any) on turn `n-1`
- Nudging the model out of infinite loops is still a hard problem in agent design.
4. **Performance degradation:** I observed heuristically that reasoning capability of the RLM orchestrator itself still degrades even with a more concise context window from the RLM method. For example, the orchestrator would stop outputting `Thought` blocks and proceed to only output `Actions` (See [^3]), a sign of lost reasoning ability.
- I attempted to mitigate this by setting a low temperature (0.2) for the orchestrator to encourage more deterministic outputs, but the problem persisted.

## Prerequisites
- Python 3.13+
- [uv](https://github.com/astral-sh/uv)
- [Docker](https://www.docker.com/)
- [Ollama](https://ollama.com/)

# Usage
1. Copy the sample environment file
```bash
cp env-sample .env
```
2. Start Ollama server and pull your desired model
```bash
ollama serve

ollama pull $OLLAMA_MODEL_NAME # e.g. ollama pull llama3.2
```

3. Edit `.env` and set `OLLAMA_MODEL_NAME`
4. Build Docker container code execution sandbox
```sh
# Ensure the provided Dockerfile, llm_query.py, and rlm.py files
# are in your root directory before building.
docker build -t rlm-sandbox .

# Command to start the docker code execution sandbox
docker run -d \
  --name rlm_worker \
  --add-host=host.docker.internal:host-gateway \
  -m 256m \
  -v $(pwd):/workspace:ro \
  --env-file $(pwd)/.env \
  --cap-drop ALL \
  --user nobody \
  --cpus 0.5 \
  --pids-limit 100 \
  --security-opt no-new-privileges \
  --read-only \
  rlm-sandbox

# Explanation of flags:

# --add-host=host.docker.internal:host-gateway
# Allow container to access host services via host.docker.internal (Ollama at port 11434)

# -m 256m - Limit memory usage to 256MB

# -v $(pwd):/workspace:ro
# Code executed inside cannot modify files on host,
# but can read them via the shared volume

# --env-file $(pwd)/.env - Do not put sensitive environment variables in the .env file
# --cap-drop ALL - Drop all capabilities for better security
# --user nobody - Run as non-root user for better security
# --cpus 0.5 - Limit CPU usage to 50% of a single core
# --pids-limit 100 - Limit number of processes to prevent fork bombs
# --security-opt no-new-privileges - Prevent privilege escalation
# --read-only - Make the container's filesystem read-only for better security

```
5. Install and run the RLM script:
- The script will parse the orchestrator's LLM call and inject a Python script `tmp_execution.py` with the generated code into the container via the shared volume.
- The sandboxed environment will then run that code with access to the `context` variable and the `llm_query` function for sub-agent calls.
- The `llm_query` function routes LLM call requests out of the sandbox to the Ollama server running on the host machine via `host.docker.internal`.

```sh
# Install dependencies
uv sync
# Run main RLM script
uv run rlm.py
```

## Cleanup
To stop and remove the Docker sandbox (runs forever by default):
```bash
docker stop rlm_worker
docker rm rlm_worker
```

# Extensions
1. **Hybrid RAG + RLM:** The problem still remains on what text to load into the `context` variable in the first place. A single-document RLM could itself be a sub-agent. A pre-retrieval step (e.g. RAG) could select the most relevant chunks which could be used to identify the most relevant documents from a larger corpus.
2. **Hierarchichal RLMs:** A master knowledge-base RLM could be responsible for higher-level reasoning; delegating to a swarm of sub-RLMs that each specialise in a specific document or section. This master would aggregate their insights, reason about new searches over files or return a final answer to the user.
3. **Deep Research Agent:** For higher observability and trust, the Orchestrator could be modified to output a citation every time it finds a crucial piece of evidence in the text. This could be a simple Python script that appends the quote, source location and sub-agent insight to a persistent notepad file (e.g., `citations.json`):

````md
# CITATION ENGINE
You have a persistent notepad file located at `/workspace/citations.json`. 
Whenever a sub-agent finds a crucial piece of evidence,
you MUST write a Python script to append the exact quote,
the source location (e.g., character index or chapter),
and the sub-agent's insight to this file.

Example of saving a citation:
```python
import json

citation = {
    "source_index": match.start(),
    "quote": chunk[:100],
    "insight": answer
}

# Append the citation as a JSON object to the citations.json file
with open("/workspace/citations.json", "a") as f:
    f.write(json.dumps(citation) + "\n")
print("Citation saved successfully.")
```
````

[^1]: [Recursive Language Models](https://arxiv.org/abs/2512.24601) - ArXiv paper reference.
[^2]: [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) - Anthropic's article on best practices for context engineering in AI agents.
[^3]: [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) - ReAct paper that introduces the Thought/Action/Observation framework for agent reasoning and interaction.