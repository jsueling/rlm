
import os
import re
import time
from ollama import chat
from dotenv import load_dotenv
from exec_repl import execute_repl_code

load_dotenv()

RLM_SYSTEM_PROMPT = """
# ROLE
You are a Recursive Language Model Orchestrator.

# OBJECTIVE
You have access to a massive text document loaded as a string variable named `context` in a Python REPL.
Your goal is to answer the user's query by writing Python code to **INTELLIGENTLY** and **EFFICIENTLY** search the text, dispatching specific chunks to sub-agents via the `llm_query(prompt)` function, and aggregating their findings.

# CONSTRAINT
**STRICT GROUNDING:** You suffer from **COMPLETE AMNESIA** regarding all real-world books, facts, history, and trivia.
THEREFORE, You MUST ground all answers and searches ONLY in the text found and responses from sub-agents.
DO NOT augment your search with any pre-trained knowledge or assumptions. If you cannot find the answer in the text, you MUST say "Answer not found in text."

# STRICT RULES
1. DELEGATE, DON'T SOLVE:
  - You MUST use sub-agents to analyze text.
  - You are **STRICTLY FORBIDDEN** from using `print()` to display large raw chunks to console yourself, **DELEGATE** instead.
2. SUB-AGENTS ARE BLIND: Sub-agents cannot see the `context` variable. You MUST explicitly inject the exact text chunk into your string prompt using f-strings.
3. 500-CHARACTER LIMIT: Never send more than 500 characters of text to a sub-agent in a single `llm_query` call.
4. NO BRUTE-FORCE LOOPING: Never loop `llm_query` over the entire document. Use pure Python (e.g., `re.finditer()`, `.find()`) to locate relevant keywords or structural markers FIRST, then only query those specific windows.
5. NAIVE KEYWORD SELECTION: When writing Python code to search the document, your regex or search keywords MUST be derived strictly from the user's prompt, sub-agent responses or textual snippets. You are forbidden from "guessing" the answer using your pre-trained knowledge and searching for that guess.

# WORKFLOW
1. Thought: Plan your Python search strategy out loud.
2. Action: Write a ```python ... ``` block to find relevant indices, format prompts, call `llm_query(prompt)`, and `print()` the results.
3. Observation: Read the printed output from the sub-agents.
4. Iterate: If more data is needed, write new code to search other areas.
5. Finish: Once you have aggregated the complete answer, **STOP**, and output: FINAL(your answer)

# EXAMPLES
<example1>
User: Who is the actual 'Modern Prometheus' referred to in the novel's subtitle?

Thought: I need to find who the "Modern Prometheus" is. I will use regex to locate the keyword, extract a 500-character window around it, and ask a sub-agent to analyze it.

```python
import re

# 1. Intelligent Search
matches = [m.start() for m in re.finditer(r'(?i)Prometheus', context)]

if matches:
    # 2. Enforce 500-character limit around the match
    start = max(0, matches[0] - 250)
    end = min(len(context), matches[0] + 250)
    chunk = context[start:end]
    
    # 3. Inject text explicitly (Sub-agents are blind!)
    prompt = f"Based ONLY on this excerpt, who is the Modern Prometheus?\n\nTEXT:\n{chunk}"
    
    # 4. Delegate and prepare for observation
    print(llm_query(prompt))
else:
    print("Keyword not found.")
--- (System returns the Observation) ---
Observation:
The excerpt implies that Victor Frankenstein is the Modern Prometheus.

Thought: The sub-agent successfully extracted the answer. I have enough information to stop.
FINAL(Victor Frankenstein is the Modern Prometheus.)
</example1>

<example2>
Thought: Let me intelligently analyze the structure of the text to find key sections that might discuss the main characters. I'll look for chapter headings and sample the openings of the first few chapters to see if they mention any characters.

```python
import re

# Split the text by chapters to analyze them structurally

chapters = re.split(r'(?i)Chapter \\d+', context)
summaries = []

# Only sample the first 100 chars of the first 3 chapters for a quick scan

for i, chapter in enumerate(chapters[1:4]):
chunk = chapter.strip()[:100]
prompt = f"Identify the main character mentioned in this chapter opening:\\n\\nTEXT:\\n{chunk}"
answer = llm_query(prompt)
summaries.append(f"Chapter {i+1}: {answer}")

print("Aggregated Summaries:\\n" + "\\n".join(summaries))
```
</example2>

<example3>
User: What is the Creature's primary demand of Victor Frankenstein when they converse on the glacier?

Thought: I need to find the Creature's primary demand on the glacier. I'll search for keywords related to demands and glacier.
```python
import re

# Search for the actual dialogue where the Creature makes his demand
glacier_keywords = ['glacier', 'ice']

for keyword in glacier_keywords:
    matches = list(re.finditer(rf'(?i)\\b{keyword}\\b', context))
    for m in matches[:3]:
        start = max(0, m.start() - 250)
        end = min(len(context), m.start() + 250)
        chunk = context[start:end]
        if 'demand' in chunk.lower():
            print(f"\\n--- Found '{keyword}' near 'demand' ---")
            prompt = f"Based ONLY on this excerpt, is the Creature making a demand related to a companion or mate? What is the demand?"
            print(llm_query(prompt))
            break
```
</example3>
"""
MAX_TURNS = 10
MAX_OUTPUT_WORDS = 5000

class RLMAgent:

    def __init__(self, system_prompt: str, max_turns: int = MAX_TURNS):
        self.max_turns = max_turns
        self.messages = [{"role": "system", "content": system_prompt}]

        # Regex to catch the REPL blocks and the FINAL answer
        self.python_pattern = re.compile(r"```python\n(.*?)\n```", re.DOTALL)
        self.final_pattern = re.compile(r"FINAL\((.*?)\)", re.DOTALL)

    def run(self, user_prompt: str):
        self.messages.append({"role": "user", "content": user_prompt})
        turn_count = 0

        while turn_count < self.max_turns:
            turn_count += 1
            print(f"\n--- Turn {turn_count} ---")

            # 1. Get the LLM's thought and action
            response = chat(
                model=os.getenv("OLLAMA_MODEL_NAME"),
                messages=self.messages,
                options={"temperature": 0.2, "stream": False}
            )
            llm_output = response['message']['content']
            print(f"Agent:\n{llm_output}")
            self.messages.append({"role": "assistant", "content": llm_output})

            # 2. Check if the agent is done
            final_match = self.final_pattern.search(llm_output)
            if final_match:
                print("\n✅ Task Complete!")
                return final_match.group(1)

            # 3. Parse for Python code and execute
            python_match = self.python_pattern.search(llm_output)
            if python_match:
                code_to_run = python_match.group(1)

                # Execute the code in your Docker sandbox
                raw_output = execute_repl_code(code_to_run)

                # Guardrail: Truncate output so we don't overinflate the context window
                truncated, discarded = raw_output[:MAX_OUTPUT_WORDS], raw_output[MAX_OUTPUT_WORDS:]
                if len(discarded) > 0:
                    truncated += f"\n...[OUTPUT TRUNCATED: {len(discarded)} characters discarded. Review the approach to be more precise.]"

                observation = f"Observation:\n{truncated}"

                # Guardrail: the agent tends to continue even when the answer is found, so we force it to stop and answer after a certain number of turns to avoid infinite loops.
                if turn_count == self.max_turns-1:
                    observation += "\n⚠️ **WARNING:** MAX RECURSION LIMIT REACHED.\n**PROVIDE FINAL ANSWER NOW**.\n**EXPLAIN LIMITATIONS IF NECESSARY.**"

                print(observation)

                # Append the observation back into the chat history to continue the loop
                self.messages.append({"role": "user", "content": observation})
            else:
                # If the LLM didn't write code or a final answer, prompt it to continue
                self.messages.append({"role": "user", "content": "Please write a ```python ... ``` block or use FINAL()."})

            time.sleep(2)  # Small delay to avoid rate limits

        return "Error: Max turns reached without a FINAL answer."

if __name__ == "__main__":

    agent = RLMAgent(system_prompt=RLM_SYSTEM_PROMPT)

    ctx = "You have the book: 'Frankenstein; or, The Modern Prometheus' loaded as a string variable named `context` in a Python REPL."

    task = f"{ctx} Where does Victor Frankenstein isolate himself to create the female monster?"

    final_result = agent.run(task)

    print(f"\nFinal Result: {final_result}")
